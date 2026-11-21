// KoboaExpress : reçoit des livres par e-mail sur une liseuse Kobo.
//
// À chaque connexion Wi-Fi (ou depuis NickelMenu), KoboaExpress relève une boîte mail
// en IMAP, enregistre les livres reçus en pièce jointe dans KoboaExpress/Livres sur la
// liseuse, puis demande à la Kobo de les ajouter à sa bibliothèque.
package main

import (
	"bufio"
	"crypto/x509"
	_ "embed"
	"errors"
	"flag"
	"fmt"
	"log"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"syscall"
	"time"
)

const version = "1.1"

//go:embed autorites.pem
var autoritesPEM []byte

//go:embed reglages.ini
var modeleReglages string

// ------------------------------------------------------------------ réglages

type Reglages struct {
	Adresse        string
	MotDePasse     string
	Serveur        string
	Port           int
	FiltreAdresse  string
	FiltreObjet    string
	SupprimerEmail bool
	DossierIMAP    string
	Actualisation  string // auto, usb, non
	JoursPremiere  int
}

func lireReglages(chemin string) (*Reglages, error) {
	f, err := os.Open(chemin)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	r := &Reglages{Serveur: "imap.gmail.com", Port: 993, DossierIMAP: "INBOX", Actualisation: "auto", JoursPremiere: 30}
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		l := strings.TrimSpace(strings.TrimPrefix(sc.Text(), "\uFEFF"))
		if l == "" || strings.HasPrefix(l, "#") || strings.HasPrefix(l, ";") {
			continue
		}
		cle, val, ok := strings.Cut(l, "=")
		if !ok {
			continue
		}
		cle = strings.ToLower(strings.TrimSpace(cle))
		val = strings.TrimSpace(val)
		switch cle {
		case "adresse":
			r.Adresse = val
		case "mot_de_passe":
			r.MotDePasse = val
		case "serveur":
			if val != "" {
				r.Serveur = val
			}
		case "port":
			if n, err := strconv.Atoi(val); err == nil && n > 0 {
				r.Port = n
			}
		case "filtre_adresse":
			r.FiltreAdresse = val
		case "filtre_objet":
			r.FiltreObjet = val
		case "supprimer_email":
			r.SupprimerEmail = oui(val)
		case "dossier_imap":
			if val != "" {
				r.DossierIMAP = val
			}
		case "actualisation":
			if val != "" {
				r.Actualisation = strings.ToLower(val)
			}
		case "jours_premiere_fois":
			if n, err := strconv.Atoi(val); err == nil && n > 0 {
				r.JoursPremiere = n
			}
		}
	}
	return r, sc.Err()
}

func oui(s string) bool {
	switch strings.ToLower(strings.TrimSpace(s)) {
	case "oui", "o", "yes", "y", "vrai", "true", "1":
		return true
	}
	return false
}

// ------------------------------------------------------------------ état

// Etat : dernier message traité, pour ne jamais traiter deux fois le même.
type Etat struct {
	UIDValidity uint64
	DernierUID  uint32
}

func lireEtat(chemin string) Etat {
	var e Etat
	b, err := os.ReadFile(chemin)
	if err != nil {
		return e
	}
	for _, l := range strings.Split(string(b), "\n") {
		cle, val, _ := strings.Cut(strings.TrimSpace(l), "=")
		n, _ := strconv.ParseUint(strings.TrimSpace(val), 10, 64)
		switch strings.TrimSpace(cle) {
		case "uidvalidity":
			e.UIDValidity = n
		case "dernier_uid":
			e.DernierUID = uint32(n)
		}
	}
	return e
}

func ecrireEtat(chemin string, e Etat) error {
	tmp := chemin + ".tmp"
	contenu := fmt.Sprintf("# état de KoboaExpress (ne pas modifier)\nuidvalidity=%d\ndernier_uid=%d\n", e.UIDValidity, e.DernierUID)
	if err := os.WriteFile(tmp, []byte(contenu), 0o644); err != nil {
		return err
	}
	return os.Rename(tmp, chemin)
}

// ------------------------------------------------------------------ Kobo

// Kobo : ce qui touche à la liseuse (notifications, bibliothèque). Remplaçable pour les tests.
type Kobo interface {
	Message(texte string)
	ActualiserBibliotheque(mode string)
}

type vraieKobo struct{ journal *log.Logger }

func qndb() string {
	for _, p := range []string{"/usr/bin/qndb", "/usr/local/bin/qndb"} {
		if _, err := os.Stat(p); err == nil {
			return p
		}
	}
	if p, err := exec.LookPath("qndb"); err == nil {
		return p
	}
	return ""
}

// Message : petite bulle à l'écran (si NickelDBus est installé).
func (k vraieKobo) Message(texte string) {
	if q := qndb(); q != "" {
		exec.Command(q, "-m", "mwcToast", "4000", texte).Run()
	}
}

// ActualiserBibliotheque fait apparaître les nouveaux livres dans la bibliothèque.
func (k vraieKobo) ActualiserBibliotheque(mode string) {
	if mode == "non" {
		return
	}
	if q := qndb(); q != "" && mode != "usb" {
		if err := exec.Command(q, "-m", "pfmRescanBooksFull").Run(); err == nil {
			k.journal.Printf("bibliothèque actualisée (NickelDBus)")
			return
		}
	}
	// méthode classique : on simule le branchement puis le débranchement d'un câble USB
	etat := "/tmp/nickel-hardware-status"
	if _, err := os.Stat(etat); err != nil {
		k.journal.Printf("impossible d'actualiser la bibliothèque : %s absent", etat)
		return
	}
	ecrire := func(s string) {
		fait := make(chan struct{})
		go func() {
			if f, err := os.OpenFile(etat, os.O_WRONLY|os.O_APPEND, 0); err == nil {
				f.WriteString(s + "\n")
				f.Close()
			}
			close(fait)
		}()
		select {
		case <-fait:
		case <-time.After(5 * time.Second):
		}
	}
	ecrire("usb plug add")
	time.Sleep(8 * time.Second)
	ecrire("usb plug remove")
	k.journal.Printf("bibliothèque actualisée (câble USB simulé)")
}

// ------------------------------------------------------------------ travail

type Bilan struct {
	Livres  []string
	Ignores []string
}

type KoboaExpress struct {
	Dossier string // dossier KoboaExpress sur la liseuse (réglages, journal, état, Livres)
	Racines *x509.CertPool
	Journal *log.Logger
	Kobo    Kobo
	Delai   time.Duration
	Attente time.Duration // attente maximale du réseau
}

func (rk *KoboaExpress) cheminReglages() string { return filepath.Join(rk.Dossier, "reglages.ini") }
func (rk *KoboaExpress) cheminEtat() string     { return filepath.Join(rk.Dossier, ".etat") }
func (rk *KoboaExpress) dossierLivres() string  { return filepath.Join(rk.Dossier, "Livres") }

var ErrPasConfigure = errors.New("KoboaExpress n'est pas encore réglé")

func (rk *KoboaExpress) attendreReseau(serveur string) error {
	limite := time.Now().Add(rk.Attente)
	for {
		if _, err := net.LookupHost(serveur); err == nil {
			return nil
		} else if time.Now().After(limite) {
			return fmt.Errorf("pas de connexion Internet (%v)", err)
		}
		time.Sleep(3 * time.Second)
	}
}

// Executer relève la boîte et range les livres reçus.
func (rk *KoboaExpress) Executer() (*Bilan, error) {
	reg, err := lireReglages(rk.cheminReglages())
	if errors.Is(err, os.ErrNotExist) {
		os.MkdirAll(rk.Dossier, 0o755)
		os.WriteFile(rk.cheminReglages(), []byte(modeleReglages), 0o644)
		return nil, ErrPasConfigure
	}
	if err != nil {
		return nil, fmt.Errorf("réglages illisibles : %v", err)
	}
	if reg.Adresse == "" || reg.MotDePasse == "" {
		return nil, ErrPasConfigure
	}
	if time.Now().Year() < 2025 {
		rk.Journal.Printf("attention : l'horloge de la Kobo indique %s ; si la connexion échoue, synchronise la Kobo pour la remettre à l'heure", time.Now().Format("02/01/2006"))
	}
	if err := rk.attendreReseau(reg.Serveur); err != nil {
		return nil, err
	}
	c, err := Connecter(reg.Serveur, reg.Port, rk.Racines, rk.Delai)
	if err != nil {
		var errCert x509.UnknownAuthorityError
		var errDate x509.CertificateInvalidError
		if errors.As(err, &errDate) && errDate.Reason == x509.Expired {
			return nil, fmt.Errorf("connexion sécurisée refusée : l'horloge de la Kobo n'est sans doute pas à l'heure (%v)", err)
		}
		if errors.As(err, &errCert) {
			return nil, fmt.Errorf("certificat du serveur inconnu (%v)", err)
		}
		return nil, fmt.Errorf("connexion à %s impossible : %v", reg.Serveur, err)
	}
	defer c.Fermer()
	if err := c.Identifier(reg.Adresse, reg.MotDePasse); err != nil {
		return nil, fmt.Errorf("identification refusée pour %s : vérifie l'adresse et le mot de passe d'application (%v)", reg.Adresse, err)
	}
	validite, err := c.Selectionner(reg.DossierIMAP)
	if err != nil {
		return nil, err
	}

	etat := lireEtat(rk.cheminEtat())
	var uids []uint32
	if etat.UIDValidity != 0 && etat.UIDValidity == validite && etat.DernierUID > 0 {
		uids, err = c.Chercher(fmt.Sprintf("UID %d:*", etat.DernierUID+1))
	} else {
		// première fois : seulement les e-mails récents
		depuis := time.Now().AddDate(0, 0, -reg.JoursPremiere)
		rk.Journal.Printf("première relève : e-mails des %d derniers jours", reg.JoursPremiere)
		uids, err = c.Chercher("SINCE " + depuis.Format("2-Jan-2006"))
		etat = Etat{UIDValidity: validite}
	}
	if err != nil {
		return nil, err
	}
	var nouveaux []uint32
	for _, u := range uids {
		if u > etat.DernierUID {
			nouveaux = append(nouveaux, u)
		}
	}
	bilan := &Bilan{}
	if len(nouveaux) == 0 {
		rk.Journal.Printf("aucun nouvel e-mail")
		ecrireEtat(rk.cheminEtat(), etat)
		return bilan, nil
	}

	// tri par les en-têtes (destinataire « +kobo », objet) avant de tout télécharger
	retenus := nouveaux
	if reg.FiltreAdresse != "" || reg.FiltreObjet != "" {
		entetes, err := c.Recuperer(nouveaux, "BODY.PEEK[HEADER.FIELDS (TO CC DELIVERED-TO X-ORIGINAL-TO ENVELOPE-TO SUBJECT)]")
		if err != nil {
			return nil, err
		}
		retenus = nil
		for _, u := range nouveaux {
			if EntetesCorrespondent(entetes[u], reg.FiltreAdresse, reg.FiltreObjet) {
				retenus = append(retenus, u)
			}
		}
	}
	rk.Journal.Printf("%d nouvel(s) e-mail(s), %d pour la Kobo", len(nouveaux), len(retenus))

	if err := os.MkdirAll(rk.dossierLivres(), 0o755); err != nil {
		return nil, err
	}
	pourKobo := map[uint32]bool{}
	for _, u := range retenus {
		pourKobo[u] = true
	}
	for _, u := range nouveaux {
		if pourKobo[u] {
			if err := rk.traiterMessage(c, reg, u, bilan); err != nil {
				ecrireEtat(rk.cheminEtat(), etat)
				return bilan, err
			}
		}
		etat.DernierUID = u
		if err := ecrireEtat(rk.cheminEtat(), etat); err != nil {
			return bilan, fmt.Errorf("impossible d'enregistrer l'état : %v", err)
		}
	}
	if reg.SupprimerEmail && len(retenus) > 0 {
		c.Purger()
	}
	return bilan, nil
}

func (rk *KoboaExpress) traiterMessage(c *ClientIMAP, reg *Reglages, uid uint32, bilan *Bilan) error {
	contenus, err := c.Recuperer([]uint32{uid}, "BODY.PEEK[]")
	if err != nil {
		return err
	}
	brut, ok := contenus[uid]
	if !ok {
		rk.Journal.Printf("e-mail %d introuvable (supprimé entre-temps ?)", uid)
		return nil
	}
	objet, pieces, err := PiecesJointes(brut)
	if err != nil {
		rk.Journal.Printf("e-mail %d illisible : %v", uid, err)
	}
	if objet == "" {
		objet = "(sans objet)"
	}
	trouves := 0
	for _, p := range pieces {
		if !estLivre(p.Nom) {
			bilan.Ignores = append(bilan.Ignores, p.Nom)
			rk.Journal.Printf("  « %s » ignoré : la Kobo ne lit pas ce format", p.Nom)
			continue
		}
		nom, deja, err := rk.enregistrer(p)
		if err != nil {
			return fmt.Errorf("impossible d'enregistrer « %s » : %v", p.Nom, err)
		}
		trouves++
		if deja {
			rk.Journal.Printf("  « %s » déjà reçu", nom)
			continue
		}
		bilan.Livres = append(bilan.Livres, nom)
		rk.Journal.Printf("  ✓ %s (%d Ko)", nom, (len(p.Donnees)+1023)/1024)
	}
	rk.Journal.Printf("e-mail « %s » : %d livre(s)", objet, trouves)
	drapeaux := `\Seen`
	if reg.SupprimerEmail {
		drapeaux += ` \Deleted`
	}
	if err := c.Marquer(uid, drapeaux); err != nil {
		rk.Journal.Printf("  impossible de marquer l'e-mail comme lu : %v", err)
	}
	return nil
}

// enregistrer range un livre dans KoboaExpress/Livres (sans écraser un autre livre du même nom).
func (rk *KoboaExpress) enregistrer(p PieceJointe) (string, bool, error) {
	nom := NomDeFichierSur(p.Nom)
	ext := filepath.Ext(nom)
	if strings.HasSuffix(strings.ToLower(nom), ".kepub.epub") {
		ext = nom[len(nom)-len(".kepub.epub"):]
	}
	base := strings.TrimSuffix(nom, ext)
	for i := 1; ; i++ {
		candidat := nom
		if i > 1 {
			candidat = fmt.Sprintf("%s (%d)%s", base, i, ext)
		}
		chemin := filepath.Join(rk.dossierLivres(), candidat)
		info, err := os.Stat(chemin)
		if err == nil {
			if info.Size() == int64(len(p.Donnees)) {
				if existant, err := os.ReadFile(chemin); err == nil && string(existant) == string(p.Donnees) {
					return candidat, true, nil
				}
			}
			continue
		}
		tmp := filepath.Join(rk.dossierLivres(), ".reception.tmp")
		if err := os.WriteFile(tmp, p.Donnees, 0o644); err != nil {
			os.Remove(tmp)
			return "", false, err
		}
		if err := os.Rename(tmp, chemin); err != nil {
			return "", false, err
		}
		return candidat, false, nil
	}
}

// ------------------------------------------------------------------ programme

func racinesCertificats() *x509.CertPool {
	pool, err := x509.SystemCertPool()
	if err != nil || pool == nil {
		pool = x509.NewCertPool()
	}
	// les certificats de la Kobo peuvent dater : on ajoute ceux de Mozilla
	pool.AppendCertsFromPEM(autoritesPEM)
	return pool
}

func ouvrirJournal(dossier string) (*log.Logger, *os.File) {
	os.MkdirAll(dossier, 0o755)
	chemin := filepath.Join(dossier, "journal.log")
	if info, err := os.Stat(chemin); err == nil && info.Size() > 256*1024 {
		if b, err := os.ReadFile(chemin); err == nil {
			os.WriteFile(chemin, b[len(b)/2:], 0o644)
		}
	}
	f, err := os.OpenFile(chemin, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644)
	if err != nil {
		return log.New(os.Stderr, "", log.LstdFlags), nil
	}
	return log.New(f, "", log.LstdFlags), f
}

// verrou : une seule relève à la fois (Wi-Fi + NickelMenu en même temps, par ex.)
func verrouiller() (*os.File, bool) {
	f, err := os.OpenFile("/tmp/koboaexpress.lock", os.O_CREATE|os.O_RDWR, 0o644)
	if err != nil {
		return nil, true
	}
	if err := syscall.Flock(int(f.Fd()), syscall.LOCK_EX|syscall.LOCK_NB); err != nil {
		f.Close()
		return nil, false
	}
	return f, true
}

func main() {
	dossier := flag.String("dossier", "/mnt/onboard/KoboaExpress", "dossier de KoboaExpress sur la liseuse")
	origine := flag.String("origine", "manuel", "qui lance KoboaExpress (wifi, manuel)")
	flag.Parse()

	journal, fichier := ouvrirJournal(*dossier)
	if fichier != nil {
		defer fichier.Close()
	}
	verrou, ok := verrouiller()
	if !ok {
		journal.Printf("relève déjà en cours, rien à faire")
		return
	}
	if verrou != nil {
		defer verrou.Close()
	}
	kobo := vraieKobo{journal: journal}
	journal.Printf("— KoboaExpress %s (%s)", version, *origine)
	rk := &KoboaExpress{Dossier: *dossier, Racines: racinesCertificats(), Journal: journal, Kobo: kobo,
		Delai: 90 * time.Second, Attente: 90 * time.Second}
	bilan, err := rk.Executer()
	switch {
	case errors.Is(err, ErrPasConfigure):
		journal.Printf("à régler : remplis KoboaExpress/reglages.ini (adresse et mot de passe)")
		if *origine == "manuel" {
			kobo.Message("KoboaExpress : remplis d'abord le fichier KoboaExpress/reglages.ini")
		}
		return
	case err != nil:
		journal.Printf("ERREUR : %v", err)
		if *origine == "manuel" || !strings.Contains(err.Error(), "pas de connexion") {
			kobo.Message("KoboaExpress : " + err.Error())
		}
	}
	if bilan == nil {
		return
	}
	if n := len(bilan.Livres); n > 0 {
		sort.Strings(bilan.Livres)
		texte := fmt.Sprintf("KoboaExpress : %d nouveau livre reçu", n)
		if n > 1 {
			texte = fmt.Sprintf("KoboaExpress : %d nouveaux livres reçus", n)
		}
		kobo.Message(texte)
		reg, _ := lireReglages(rk.cheminReglages())
		mode := "auto"
		if reg != nil {
			mode = reg.Actualisation
		}
		kobo.ActualiserBibliotheque(mode)
	} else if *origine == "manuel" && err == nil {
		kobo.Message("KoboaExpress : pas de nouveau livre")
	}
}
