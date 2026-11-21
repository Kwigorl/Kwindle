package main

// Client IMAP minimal : juste ce qu'il faut pour relever une boîte et récupérer
// des pièces jointes (connexion TLS, LOGIN, SELECT, UID SEARCH / FETCH / STORE).
// Seule la bibliothèque standard de Go est utilisée : le programme reste petit
// et se compile pour n'importe quelle Kobo.

import (
	"bufio"
	"bytes"
	"crypto/tls"
	"crypto/x509"
	"errors"
	"fmt"
	"io"
	"net"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"
)

// ErreurIMAP : le serveur a répondu NO ou BAD.
type ErreurIMAP struct {
	Commande string
	Statut   string
	Texte    string
}

func (e *ErreurIMAP) Error() string {
	return fmt.Sprintf("le serveur refuse « %s » : %s %s", e.Commande, e.Statut, e.Texte)
}

// Reponse : une réponse non étiquetée (« * … »), avec ses littéraux {n}.
type Reponse struct {
	Texte     string   // la ligne, littéraux remplacés par « {L0} », « {L1} »…
	Litteraux [][]byte // contenu des littéraux
}

type ClientIMAP struct {
	conn  net.Conn
	r     *bufio.Reader
	tag   int
	delai time.Duration
}

// Connecter ouvre une connexion IMAP chiffrée (port 993 en général).
func Connecter(serveur string, port int, racines *x509.CertPool, delai time.Duration) (*ClientIMAP, error) {
	d := &net.Dialer{Timeout: delai}
	conf := &tls.Config{ServerName: serveur, RootCAs: racines, MinVersion: tls.VersionTLS12}
	conn, err := tls.DialWithDialer(d, "tcp", net.JoinHostPort(serveur, strconv.Itoa(port)), conf)
	if err != nil {
		return nil, err
	}
	c := &ClientIMAP{conn: conn, r: bufio.NewReaderSize(conn, 64*1024), delai: delai}
	c.conn.SetDeadline(time.Now().Add(delai))
	salut, err := c.lireLigne()
	if err != nil {
		conn.Close()
		return nil, err
	}
	if !strings.HasPrefix(salut, "* OK") && !strings.HasPrefix(salut, "* PREAUTH") {
		conn.Close()
		return nil, fmt.Errorf("accueil inattendu du serveur : %s", salut)
	}
	return c, nil
}

func (c *ClientIMAP) Fermer() {
	if c.conn != nil {
		c.conn.SetDeadline(time.Now().Add(5 * time.Second))
		c.Commande("LOGOUT")
		c.conn.Close()
		c.conn = nil
	}
}

func (c *ClientIMAP) lireLigne() (string, error) {
	l, err := c.r.ReadString('\n')
	if err != nil {
		return "", err
	}
	return strings.TrimRight(l, "\r\n"), nil
}

var reLitteral = regexp.MustCompile(`\{(\d+)\+?\}$`)

// lireReponse lit une réponse complète du serveur, littéraux compris.
func (c *ClientIMAP) lireReponse() (*Reponse, error) {
	rep := &Reponse{}
	var texte strings.Builder
	for {
		ligne, err := c.lireLigne()
		if err != nil {
			return nil, err
		}
		m := reLitteral.FindStringSubmatchIndex(ligne)
		if m == nil {
			texte.WriteString(ligne)
			break
		}
		n, err := strconv.Atoi(ligne[m[2]:m[3]])
		if err != nil || n < 0 || n > 200*1024*1024 {
			return nil, fmt.Errorf("littéral IMAP invalide : %q", ligne)
		}
		texte.WriteString(ligne[:m[0]])
		fmt.Fprintf(&texte, "{L%d}", len(rep.Litteraux))
		donnees := make([]byte, n)
		if _, err := io.ReadFull(c.r, donnees); err != nil {
			return nil, err
		}
		rep.Litteraux = append(rep.Litteraux, donnees)
	}
	rep.Texte = texte.String()
	return rep, nil
}

// Chaîne IMAP : entre guillemets si possible, sinon littéral (accents, retours à la ligne).
type argument struct {
	texte    string
	litteral bool
}

func Chaine(s string) argument {
	for _, r := range s {
		if r > 126 || r < 32 {
			return argument{texte: s, litteral: true}
		}
	}
	return argument{texte: `"` + strings.NewReplacer(`\`, `\\`, `"`, `\"`).Replace(s) + `"`}
}

func Brut(s string) argument { return argument{texte: s} }

// Commande envoie une commande et renvoie ses réponses non étiquetées.
func (c *ClientIMAP) Commande(nom string, args ...argument) ([]*Reponse, error) {
	if c.conn == nil {
		return nil, errors.New("connexion fermée")
	}
	c.tag++
	tag := fmt.Sprintf("R%03d", c.tag)
	c.conn.SetDeadline(time.Now().Add(c.delai))

	envoyer := func(s string) error {
		_, err := io.WriteString(c.conn, s)
		return err
	}
	ligne := tag + " " + nom
	for _, a := range args {
		if !a.litteral {
			ligne += " " + a.texte
			continue
		}
		// littéral : on annonce la taille, le serveur répond « + », puis on envoie
		ligne += fmt.Sprintf(" {%d}\r\n", len(a.texte))
		if err := envoyer(ligne); err != nil {
			return nil, err
		}
		for {
			l, err := c.lireLigne()
			if err != nil {
				return nil, err
			}
			if strings.HasPrefix(l, "+") {
				break
			}
			if strings.HasPrefix(l, tag+" ") {
				return nil, &ErreurIMAP{Commande: nom, Statut: "BAD", Texte: l}
			}
		}
		ligne = a.texte
	}
	if err := envoyer(ligne + "\r\n"); err != nil {
		return nil, err
	}

	var reponses []*Reponse
	for {
		rep, err := c.lireReponse()
		if err != nil {
			return reponses, err
		}
		if strings.HasPrefix(rep.Texte, tag+" ") {
			reste := strings.TrimPrefix(rep.Texte, tag+" ")
			statut, texte, _ := strings.Cut(reste, " ")
			if statut != "OK" {
				return reponses, &ErreurIMAP{Commande: nom, Statut: statut, Texte: texte}
			}
			return reponses, nil
		}
		if strings.HasPrefix(rep.Texte, "+") {
			continue
		}
		reponses = append(reponses, rep)
	}
}

func (c *ClientIMAP) Identifier(adresse, motDePasse string) error {
	_, err := c.Commande("LOGIN", Chaine(adresse), Chaine(motDePasse))
	return err
}

var reUIDValidity = regexp.MustCompile(`(?i)\[UIDVALIDITY (\d+)\]`)

// Selectionner ouvre un dossier et renvoie son UIDVALIDITY.
func (c *ClientIMAP) Selectionner(dossier string) (uint64, error) {
	reps, err := c.Commande("SELECT", Chaine(dossier))
	if err != nil {
		return 0, err
	}
	for _, r := range reps {
		if m := reUIDValidity.FindStringSubmatch(r.Texte); m != nil {
			return strconv.ParseUint(m[1], 10, 64)
		}
	}
	return 0, nil
}

// Chercher renvoie, triés, les UID qui répondent aux critères (ex. « UID 12:* », « SINCE 1-Nov-2026 »).
func (c *ClientIMAP) Chercher(criteres string) ([]uint32, error) {
	reps, err := c.Commande("UID SEARCH", Brut(criteres))
	if err != nil {
		return nil, err
	}
	var uids []uint32
	for _, r := range reps {
		champs := strings.Fields(r.Texte)
		if len(champs) < 2 || !strings.EqualFold(champs[1], "SEARCH") {
			continue
		}
		for _, f := range champs[2:] {
			if n, err := strconv.ParseUint(f, 10, 32); err == nil {
				uids = append(uids, uint32(n))
			}
		}
	}
	sort.Slice(uids, func(i, j int) bool { return uids[i] < uids[j] })
	return uids, nil
}

var reUID = regexp.MustCompile(`(?i)\bUID (\d+)`)

// Recuperer lit une partie (« BODY.PEEK[] », « BODY.PEEK[HEADER.FIELDS (TO)] »…) de plusieurs
// messages. Renvoie UID -> contenu.
func (c *ClientIMAP) Recuperer(uids []uint32, partie string) (map[uint32][]byte, error) {
	res := map[uint32][]byte{}
	for debut := 0; debut < len(uids); debut += 50 {
		fin := debut + 50
		if fin > len(uids) {
			fin = len(uids)
		}
		liste := make([]string, 0, fin-debut)
		for _, u := range uids[debut:fin] {
			liste = append(liste, strconv.FormatUint(uint64(u), 10))
		}
		reps, err := c.Commande("UID FETCH", Brut(strings.Join(liste, ",")), Brut("(UID "+partie+")"))
		if err != nil {
			return res, err
		}
		for _, r := range reps {
			if !strings.Contains(strings.ToUpper(r.Texte), " FETCH ") {
				continue
			}
			m := reUID.FindStringSubmatch(r.Texte)
			if m == nil {
				continue
			}
			u, _ := strconv.ParseUint(m[1], 10, 32)
			var contenu []byte
			if len(r.Litteraux) > 0 {
				contenu = r.Litteraux[len(r.Litteraux)-1]
			} else if i := strings.Index(r.Texte, "] \""); i >= 0 {
				// petite valeur renvoyée entre guillemets
				s := r.Texte[i+3:]
				if j := strings.LastIndex(s, "\""); j >= 0 {
					contenu = []byte(s[:j])
				}
			}
			if prec, ok := res[uint32(u)]; ok && len(prec) > 0 && len(contenu) == 0 {
				continue
			}
			res[uint32(u)] = bytes.Clone(contenu)
		}
	}
	return res, nil
}

// Marquer ajoute des drapeaux (ex. « \Seen ») à un message.
func (c *ClientIMAP) Marquer(uid uint32, drapeaux string) error {
	_, err := c.Commande("UID STORE", Brut(strconv.FormatUint(uint64(uid), 10)), Brut("+FLAGS.SILENT ("+drapeaux+")"))
	return err
}

func (c *ClientIMAP) Purger() error {
	_, err := c.Commande("EXPUNGE")
	return err
}
