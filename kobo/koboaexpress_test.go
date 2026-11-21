package main

import (
	"bufio"
	"bytes"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/base64"
	"fmt"
	"io"
	"log"
	"math/big"
	"net"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"
)

// ------------------------------------------------------------ faux serveur IMAP

type message struct {
	uid      uint32
	brut     string
	drapeaux map[string]bool
	date     time.Time
}

type fauxServeur struct {
	mu         sync.Mutex
	messages   []*message
	validite   uint64
	motDePasse string
	ecoute     net.Listener
	commandes  []string
}

func certificatDeTest(t *testing.T) (tls.Certificate, *x509.CertPool) {
	cle, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	modele := &x509.Certificate{
		SerialNumber: big.NewInt(1), Subject: pkix.Name{CommonName: "localhost"},
		DNSNames: []string{"localhost"}, NotBefore: time.Now().Add(-time.Hour), NotAfter: time.Now().Add(time.Hour),
		KeyUsage: x509.KeyUsageDigitalSignature, ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
	}
	der, err := x509.CreateCertificate(rand.Reader, modele, modele, &cle.PublicKey, cle)
	if err != nil {
		t.Fatal(err)
	}
	cert, _ := x509.ParseCertificate(der)
	pool := x509.NewCertPool()
	pool.AddCert(cert)
	return tls.Certificate{Certificate: [][]byte{der}, PrivateKey: cle}, pool
}

func demarrerServeur(t *testing.T, s *fauxServeur) (int, *x509.CertPool) {
	cert, pool := certificatDeTest(t)
	l, err := tls.Listen("tcp", "127.0.0.1:0", &tls.Config{Certificates: []tls.Certificate{cert}})
	if err != nil {
		t.Fatal(err)
	}
	s.ecoute = l
	t.Cleanup(func() { l.Close() })
	go func() {
		for {
			conn, err := l.Accept()
			if err != nil {
				return
			}
			go s.servir(conn)
		}
	}()
	return l.Addr().(*net.TCPAddr).Port, pool
}

var reSet = regexp.MustCompile(`^[0-9,:*]+$`)

func (s *fauxServeur) servir(conn net.Conn) {
	defer conn.Close()
	r := bufio.NewReader(conn)
	w := bufio.NewWriter(conn)
	ecrire := func(f string, a ...interface{}) { fmt.Fprintf(w, f, a...); w.Flush() }
	ecrire("* OK Gimap ready for requests\r\n")
	connecte := false
	for {
		ligne, err := r.ReadString('\n')
		if err != nil {
			return
		}
		ligne = strings.TrimRight(ligne, "\r\n")
		// littéraux envoyés par le client
		for {
			m := regexp.MustCompile(`\{(\d+)\}$`).FindStringSubmatchIndex(ligne)
			if m == nil {
				break
			}
			n, _ := strconv.Atoi(ligne[m[2]:m[3]])
			ecrire("+ go ahead\r\n")
			buf := make([]byte, n)
			io.ReadFull(r, buf)
			reste, _ := r.ReadString('\n')
			ligne = ligne[:m[0]] + strconv.Quote(string(buf)) + strings.TrimRight(reste, "\r\n")
		}
		s.mu.Lock()
		s.commandes = append(s.commandes, ligne)
		s.mu.Unlock()
		tag, cmd, _ := strings.Cut(ligne, " ")
		haut := strings.ToUpper(cmd)
		switch {
		case strings.HasPrefix(haut, "LOGIN "):
			args := lireArgs(cmd[6:])
			if len(args) == 2 && args[1] == s.motDePasse {
				connecte = true
				ecrire("* CAPABILITY IMAP4rev1\r\n%s OK %s authenticated (Success)\r\n", tag, args[0])
			} else {
				ecrire("%s NO [AUTHENTICATIONFAILED] Invalid credentials (Failure)\r\n", tag)
			}
		case !connecte && !strings.HasPrefix(haut, "LOGOUT"):
			ecrire("%s BAD not authenticated\r\n", tag)
		case strings.HasPrefix(haut, "SELECT "):
			s.mu.Lock()
			ecrire("* FLAGS (\\Answered \\Flagged \\Draft \\Deleted \\Seen)\r\n* OK [UIDVALIDITY %d] UIDs valid.\r\n* %d EXISTS\r\n%s OK [READ-WRITE] INBOX selected. (Success)\r\n",
				s.validite, len(s.messages), tag)
			s.mu.Unlock()
		case strings.HasPrefix(haut, "UID SEARCH "):
			ecrire("* SEARCH%s\r\n%s OK SEARCH completed (Success)\r\n", s.chercher(cmd[11:]), tag)
		case strings.HasPrefix(haut, "UID FETCH "):
			champs := strings.SplitN(cmd[10:], " ", 2)
			s.recuperer(ecrire, champs[0], champs[1])
			ecrire("%s OK Success\r\n", tag)
		case strings.HasPrefix(haut, "UID STORE "):
			champs := strings.Fields(cmd[10:])
			uid, _ := strconv.ParseUint(champs[0], 10, 32)
			s.mu.Lock()
			for _, m := range s.messages {
				if m.uid == uint32(uid) {
					for _, d := range regexp.MustCompile(`\\\w+`).FindAllString(cmd, -1) {
						m.drapeaux[d] = true
					}
				}
			}
			s.mu.Unlock()
			ecrire("%s OK Success\r\n", tag)
		case haut == "EXPUNGE":
			s.mu.Lock()
			var gardes []*message
			for i, m := range s.messages {
				if m.drapeaux[`\Deleted`] {
					ecrire("* %d EXPUNGE\r\n", i+1)
				} else {
					gardes = append(gardes, m)
				}
			}
			s.messages = gardes
			s.mu.Unlock()
			ecrire("%s OK Success\r\n", tag)
		case haut == "LOGOUT":
			ecrire("* BYE LOGOUT Requested\r\n%s OK 73 good day (Success)\r\n", tag)
			return
		default:
			ecrire("%s BAD Unknown command\r\n", tag)
		}
	}
}

func lireArgs(s string) []string {
	var res []string
	for len(s) > 0 {
		s = strings.TrimLeft(s, " ")
		if strings.HasPrefix(s, `"`) {
			v, err := strconv.QuotedPrefix(s)
			if err != nil {
				break
			}
			u, _ := strconv.Unquote(v)
			res = append(res, u)
			s = s[len(v):]
			continue
		}
		mot, reste, _ := strings.Cut(s, " ")
		res = append(res, mot)
		s = reste
	}
	return res
}

func (s *fauxServeur) chercher(criteres string) string {
	s.mu.Lock()
	defer s.mu.Unlock()
	var uids []uint32
	if strings.HasPrefix(criteres, "UID ") {
		debut, _ := strconv.ParseUint(strings.TrimSuffix(criteres[4:], ":*"), 10, 32)
		var max uint32
		for _, m := range s.messages {
			if m.uid >= uint32(debut) {
				uids = append(uids, m.uid)
			}
			if m.uid > max {
				max = m.uid
			}
		}
		if len(uids) == 0 && max > 0 {
			uids = append(uids, max) // particularité d'IMAP : « n:* » contient toujours le dernier
		}
	} else if strings.HasPrefix(criteres, "SINCE ") {
		depuis, _ := time.Parse("2-Jan-2006", criteres[6:])
		for _, m := range s.messages {
			if !m.date.Before(depuis) {
				uids = append(uids, m.uid)
			}
		}
	}
	var b strings.Builder
	for i := len(uids) - 1; i >= 0; i-- { // désordre volontaire
		fmt.Fprintf(&b, " %d", uids[i])
	}
	return b.String()
}

func (s *fauxServeur) recuperer(ecrire func(string, ...interface{}), ensemble, partie string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	voulus := map[uint32]bool{}
	for _, x := range strings.Split(ensemble, ",") {
		n, _ := strconv.ParseUint(x, 10, 32)
		voulus[uint32(n)] = true
	}
	for i, m := range s.messages {
		if !voulus[m.uid] {
			continue
		}
		contenu := m.brut
		cle := "BODY[]"
		if strings.Contains(partie, "HEADER.FIELDS") {
			entete, _, _ := strings.Cut(m.brut, "\r\n\r\n")
			contenu = entete + "\r\n\r\n"
			cle = "BODY[HEADER.FIELDS (TO CC DELIVERED-TO X-ORIGINAL-TO ENVELOPE-TO SUBJECT)]"
		}
		if i%2 == 0 {
			ecrire("* %d FETCH (UID %d %s {%d}\r\n%s)\r\n", i+1, m.uid, cle, len(contenu), contenu)
		} else { // l'ordre des éléments varie selon les serveurs
			ecrire("* %d FETCH (%s {%d}\r\n%s UID %d)\r\n", i+1, cle, len(contenu), contenu, m.uid)
		}
	}
	// une notification spontanée glissée au milieu, comme le font certains serveurs
	ecrire("* %d FETCH (FLAGS (\\Seen) UID 1)\r\n", len(s.messages))
}

func (s *fauxServeur) ajouter(uid uint32, brut string, il time.Duration) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.messages = append(s.messages, &message{uid: uid, brut: strings.ReplaceAll(brut, "\n", "\r\n"),
		drapeaux: map[string]bool{}, date: time.Now().Add(-il)})
}

func (s *fauxServeur) drapeau(uid uint32, d string) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	for _, m := range s.messages {
		if m.uid == uid {
			return m.drapeaux[d]
		}
	}
	return false
}

// ------------------------------------------------------------ e-mails de test

func b64(b []byte) string {
	s := base64.StdEncoding.EncodeToString(b)
	var res strings.Builder
	for len(s) > 76 {
		res.WriteString(s[:76] + "\n")
		s = s[76:]
	}
	return res.String() + s
}

var (
	epub1 = append([]byte("PK\x03\x04application/epub+zip "), bytes.Repeat([]byte{0, 1, 2, 250}, 3000)...)
	pdf1  = []byte("%PDF-1.4 rêve\n%%EOF")
	mobi1 = []byte("BOOKMOBI contenu é=à")
	epub2 = []byte("PK\x03\x04 transféré")
)

func mailLivre() string {
	return `From: Nico <nico@example.com>
To: Kim <kim+kobo@gmail.com>
Delivered-To: kim+kobo@gmail.com
Subject: =?UTF-8?B?TGUgVHLDtG5lIGRlIGZlcg==?=
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="AAA"

--AAA
Content-Type: text/plain; charset=UTF-8

Bonne lecture !
--AAA
Content-Type: application/epub+zip
Content-Disposition: attachment; filename*=UTF-8''L%C3%A9gende%20dor%C3%A9e.epub
Content-Transfer-Encoding: base64

` + b64(epub1) + `
--AAA--
`
}

func mailPerso() string {
	return `From: Banque <banque@example.com>
To: kim@gmail.com
Subject: Votre relevé
Content-Type: multipart/mixed; boundary="B"

--B
Content-Type: text/plain

Relevé en pièce jointe.
--B
Content-Type: application/pdf; name="releve.pdf"
Content-Disposition: attachment; filename="releve.pdf"
Content-Transfer-Encoding: base64

` + b64([]byte("%PDF releve")) + `
--B--
`
}

func mailMelange() string {
	return `From: Nico <nico@example.com>
To: "Kim" <KIM+KOBO@gmail.com>
Subject: Deux livres et une photo
Content-Type: multipart/mixed; boundary="ext"

--ext
Content-Type: multipart/alternative; boundary="int"

--int
Content-Type: text/plain

texte
--int
Content-Type: text/html

<p>texte</p>
--int--
--ext
Content-Type: image/jpeg; name="photo.jpg"
Content-Disposition: attachment; filename="photo.jpg"
Content-Transfer-Encoding: base64

` + b64([]byte{0xFF, 0xD8, 0xFF}) + `
--ext
Content-Type: application/pdf; name="=?ISO-8859-1?Q?R=EAve.pdf?="
Content-Disposition: attachment; filename="=?ISO-8859-1?Q?R=EAve.pdf?="
Content-Transfer-Encoding: base64

` + b64(pdf1) + `
--ext
Content-Type: application/x-mobipocket-ebook
Content-Disposition: attachment; filename="Fondation : tome 1?.mobi"
Content-Transfer-Encoding: quoted-printable

BOOKMOBI contenu =C3=A9=3D=C3=A0
--ext--
`
}

func mailTransfere() string {
	return `From: Nico <nico@example.com>
To: kim+kobo@gmail.com
Subject: Fwd: un livre
Content-Type: multipart/mixed; boundary="F"

--F
Content-Type: text/plain

voir ci-dessous
--F
Content-Type: message/rfc822

From: Quelqu'un <q@example.com>
Subject: le livre
Content-Type: multipart/mixed; boundary="G"

--G
Content-Type: application/epub+zip; name="Transfere.epub"
Content-Transfer-Encoding: base64

` + b64(epub2) + `
--G--
--F--
`
}

// ------------------------------------------------------------ fausse Kobo

type fausseKobo struct {
	messages       []string
	actualisations int
}

func (k *fausseKobo) Message(t string)                   { k.messages = append(k.messages, t) }
func (k *fausseKobo) ActualiserBibliotheque(mode string) { k.actualisations++ }

func preparer(t *testing.T, s *fauxServeur, reglages string) (*KoboaExpress, *fausseKobo, *bytes.Buffer) {
	port, pool := demarrerServeur(t, s)
	dossier := t.TempDir()
	reglages = strings.ReplaceAll(reglages, "PORT", strconv.Itoa(port))
	if err := os.WriteFile(filepath.Join(dossier, "reglages.ini"), []byte(reglages), 0o644); err != nil {
		t.Fatal(err)
	}
	var journal bytes.Buffer
	k := &fausseKobo{}
	rk := &KoboaExpress{Dossier: dossier, Racines: pool, Journal: log.New(&journal, "", 0), Kobo: k,
		Delai: 10 * time.Second, Attente: 5 * time.Second}
	return rk, k, &journal
}

const reglagesTest = "\uFEFF# test\r\nadresse = kim@gmail.com\r\nmot_de_passe = abcd efgh ijkl mnop\r\nserveur = localhost\r\nport = PORT\r\nfiltre_adresse = +kobo\r\n"

func livresDans(t *testing.T, dossier string) []string {
	entrees, _ := os.ReadDir(filepath.Join(dossier, "Livres"))
	var noms []string
	for _, e := range entrees {
		noms = append(noms, e.Name())
	}
	sort.Strings(noms)
	return noms
}

// ------------------------------------------------------------ tests

func TestReleveComplete(t *testing.T) {
	s := &fauxServeur{validite: 7, motDePasse: "abcd efgh ijkl mnop"}
	s.ajouter(90, mailLivre(), 60*24*time.Hour) // trop ancien pour la première relève
	s.ajouter(101, mailLivre(), time.Hour)
	s.ajouter(102, mailPerso(), time.Hour)
	s.ajouter(103, mailMelange(), time.Hour)
	s.ajouter(104, mailTransfere(), time.Hour)
	rk, _, journal := preparer(t, s, reglagesTest)

	bilan, err := rk.Executer()
	if err != nil {
		t.Fatalf("relève : %v\n%s", err, journal)
	}
	attendus := []string{"Fondation _ tome 1_.mobi", "Légende dorée.epub", "Rêve.pdf", "Transfere.epub"}
	if got := livresDans(t, rk.Dossier); strings.Join(got, "|") != strings.Join(attendus, "|") {
		t.Fatalf("livres reçus : %q, attendus %q\n%s", got, attendus, journal)
	}
	if len(bilan.Livres) != 4 {
		t.Errorf("bilan : %v", bilan.Livres)
	}
	verifier := func(nom string, attendu []byte) {
		b, err := os.ReadFile(filepath.Join(rk.Dossier, "Livres", nom))
		if err != nil || !bytes.Equal(b, attendu) {
			t.Errorf("contenu de %s incorrect (%d octets, attendu %d)", nom, len(b), len(attendu))
		}
	}
	verifier("Légende dorée.epub", epub1)
	verifier("Rêve.pdf", pdf1)
	verifier("Fondation _ tome 1_.mobi", mobi1)
	verifier("Transfere.epub", epub2)

	for _, u := range []uint32{101, 103, 104} {
		if !s.drapeau(u, `\Seen`) {
			t.Errorf("l'e-mail %d devrait être marqué comme lu", u)
		}
	}
	if s.drapeau(102, `\Seen`) || s.drapeau(90, `\Seen`) {
		t.Error("un e-mail personnel (sans +kobo) ou trop ancien a été touché")
	}
	if e := lireEtat(rk.cheminEtat()); e.UIDValidity != 7 || e.DernierUID != 104 {
		t.Errorf("état : %+v", e)
	}

	// deuxième relève : rien de nouveau (malgré la particularité de « 105:* »)
	bilan, err = rk.Executer()
	if err != nil || len(bilan.Livres) != 0 {
		t.Fatalf("2e relève : %v %v\n%s", bilan, err, journal)
	}

	// un nouvel e-mail, dont un livre déjà reçu
	s.ajouter(105, mailLivre(), 0)
	bilan, err = rk.Executer()
	if err != nil {
		t.Fatal(err)
	}
	if len(bilan.Livres) != 0 || len(livresDans(t, rk.Dossier)) != 4 {
		t.Errorf("un livre déjà reçu ne doit pas être dupliqué : %v", livresDans(t, rk.Dossier))
	}
	if !strings.Contains(journal.String(), "déjà reçu") {
		t.Errorf("journal : %s", journal)
	}
}

func TestMotDePasseRefuse(t *testing.T) {
	s := &fauxServeur{validite: 1, motDePasse: "autre"}
	rk, _, _ := preparer(t, s, reglagesTest)
	_, err := rk.Executer()
	if err == nil || !strings.Contains(err.Error(), "identification refusée") {
		t.Fatalf("erreur attendue, reçu %v", err)
	}
}

func TestMotDePasseAccentue(t *testing.T) {
	// un mot de passe avec accent part en « littéral » IMAP
	s := &fauxServeur{validite: 1, motDePasse: "pâté \"secret\""}
	rk, _, journal := preparer(t, s, strings.Replace(reglagesTest, "abcd efgh ijkl mnop", `pâté "secret"`, 1))
	if _, err := rk.Executer(); err != nil {
		t.Fatalf("%v\n%s", err, journal)
	}
}

func TestSansFiltreEtSuppression(t *testing.T) {
	s := &fauxServeur{validite: 3, motDePasse: "abcd efgh ijkl mnop"}
	s.ajouter(1, mailPerso(), time.Hour)
	s.ajouter(2, mailLivre(), time.Hour)
	reglages := strings.Replace(reglagesTest, "filtre_adresse = +kobo", "filtre_adresse =\r\nsupprimer_email = oui", 1)
	rk, _, journal := preparer(t, s, reglages)
	bilan, err := rk.Executer()
	if err != nil {
		t.Fatalf("%v\n%s", err, journal)
	}
	if len(bilan.Livres) != 2 {
		t.Errorf("sans filtre, tous les livres sont pris : %v", bilan.Livres)
	}
	s.mu.Lock()
	reste := len(s.messages)
	s.mu.Unlock()
	if reste != 0 {
		t.Errorf("les e-mails traités devraient être supprimés (%d restants)", reste)
	}
}

func TestChangementDeBoite(t *testing.T) {
	// si UIDVALIDITY change (boîte recréée), on repart des e-mails récents
	s := &fauxServeur{validite: 5, motDePasse: "abcd efgh ijkl mnop"}
	s.ajouter(3, mailLivre(), time.Hour)
	rk, _, _ := preparer(t, s, reglagesTest)
	ecrireEtat(rk.cheminEtat(), Etat{UIDValidity: 4, DernierUID: 900})
	bilan, err := rk.Executer()
	if err != nil || len(bilan.Livres) != 1 {
		t.Fatalf("%v %v", bilan, err)
	}
}

func TestPremiereFoisSansReglages(t *testing.T) {
	dossier := t.TempDir()
	rk := &KoboaExpress{Dossier: dossier, Journal: log.New(io.Discard, "", 0), Kobo: &fausseKobo{}}
	if _, err := rk.Executer(); err != ErrPasConfigure {
		t.Fatalf("attendu ErrPasConfigure, reçu %v", err)
	}
	b, err := os.ReadFile(filepath.Join(dossier, "reglages.ini"))
	if err != nil || !strings.Contains(string(b), "mot_de_passe =") {
		t.Fatal("le modèle de réglages doit être créé")
	}
	reg, err := lireReglages(filepath.Join(dossier, "reglages.ini"))
	if err != nil || reg.Serveur != "imap.gmail.com" || reg.Port != 993 || reg.FiltreAdresse != "+kobo" {
		t.Fatalf("modèle mal lu : %+v %v", reg, err)
	}
}

func TestNomsDeFichiers(t *testing.T) {
	cas := map[string]string{
		`Fondation : tome 1?.mobi`:        "Fondation _ tome 1_.mobi",
		`../../etc/passwd.epub`:           "passwd.epub",
		`C:\Livres\Dune.epub`:             "Dune.epub",
		` .Caché. `:                       "Caché",
		`Le Livre.kepub.epub`:             "Le Livre.kepub.epub",
		strings.Repeat("é", 200) + ".pdf": strings.Repeat("é", 120) + ".pdf",
	}
	for entree, attendu := range cas {
		if got := NomDeFichierSur(entree); got != attendu {
			t.Errorf("NomDeFichierSur(%q) = %q, attendu %q", entree, got, attendu)
		}
	}
	if !estLivre("x.KEPUB.EPUB") || estLivre("photo.jpg") || !estLivre("a.cbz") {
		t.Error("estLivre")
	}
}

func TestEntetes(t *testing.T) {
	if got := DecoderEntete("=?windows-1252?Q?=93Dune=94_=80?="); got != "“Dune” €" {
		t.Errorf("windows-1252 : %q", got)
	}
	h := []byte("To: Kim <kim+Kobo@gmail.com>\r\nSubject: =?UTF-8?Q?Livre_pour_la_Kobo?=\r\n")
	if !EntetesCorrespondent(h, "+kobo", "") || !EntetesCorrespondent(h, "", "kobo") || EntetesCorrespondent(h, "+kindle", "") {
		t.Error("filtres")
	}
}
