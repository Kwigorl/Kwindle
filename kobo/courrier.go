package main

// Lecture des e-mails : en-têtes utiles et pièces jointes (MIME).

import (
	"bytes"
	"encoding/base64"
	"fmt"
	"io"
	"mime"
	"mime/multipart"
	"mime/quotedprintable"
	"net/mail"
	"net/textproto"
	"path"
	"strings"
	"unicode/utf8"
)

type PieceJointe struct {
	Nom     string
	Donnees []byte
}

// Formats que la Kobo sait lire.
var formatsKobo = map[string]bool{
	"epub": true, "kepub": true, "pdf": true, "mobi": true, "cbz": true, "cbr": true,
	"txt": true, "rtf": true, "html": true, "htm": true, "xhtml": true,
}

func extension(nom string) string {
	return strings.ToLower(strings.TrimPrefix(path.Ext(nom), "."))
}

func estLivre(nom string) bool { return formatsKobo[extension(nom)] }

// décodeur des en-têtes « =?UTF-8?B?…?= », y compris en Latin-1 / Windows-1252
var decodeurMots = &mime.WordDecoder{CharsetReader: lecteurJeuCaracteres}

func lecteurJeuCaracteres(jeu string, entree io.Reader) (io.Reader, error) {
	jeu = strings.ToLower(jeu)
	switch jeu {
	case "utf-8", "utf8", "us-ascii", "ascii":
		return entree, nil
	case "iso-8859-1", "iso-8859-15", "latin1", "windows-1252", "cp1252":
		donnees, err := io.ReadAll(entree)
		if err != nil {
			return nil, err
		}
		return strings.NewReader(depuisWindows1252(donnees)), nil
	}
	return nil, fmt.Errorf("jeu de caractères non pris en charge : %s", jeu)
}

// caractères 0x80–0x9F de Windows-1252 (le reste correspond à Latin-1)
var cp1252 = [32]rune{'€', 0x81, '‚', 'ƒ', '„', '…', '†', '‡', 'ˆ', '‰', 'Š', '‹', 'Œ', 0x8D, 'Ž', 0x8F,
	0x90, '‘', '’', '“', '”', '•', '–', '—', '˜', '™', 'š', '›', 'œ', 0x9D, 'ž', 'Ÿ'}

func depuisWindows1252(b []byte) string {
	var s strings.Builder
	for _, c := range b {
		switch {
		case c >= 0x80 && c < 0xA0:
			s.WriteRune(cp1252[c-0x80])
		default:
			s.WriteRune(rune(c))
		}
	}
	return s.String()
}

// DecoderEntete rend un en-tête lisible (encodage RFC 2047).
func DecoderEntete(s string) string {
	if d, err := decodeurMots.DecodeHeader(s); err == nil {
		s = d
	}
	if !utf8.ValidString(s) {
		s = depuisWindows1252([]byte(s))
	}
	return strings.TrimSpace(s)
}

// EntetesCorrespondent : vrai si l'un des destinataires ou l'objet contient les filtres.
func EntetesCorrespondent(entetes []byte, filtreAdresse, filtreObjet string) bool {
	if filtreAdresse == "" && filtreObjet == "" {
		return true
	}
	msg, err := mail.ReadMessage(io.MultiReader(bytes.NewReader(entetes), strings.NewReader("\r\n\r\n")))
	if err != nil {
		return false
	}
	h := msg.Header
	ok := true
	if filtreAdresse != "" {
		dest := strings.ToLower(strings.Join([]string{h.Get("To"), h.Get("Cc"), h.Get("Delivered-To"),
			h.Get("X-Original-To"), h.Get("Envelope-To")}, " "))
		ok = strings.Contains(dest, strings.ToLower(filtreAdresse))
	}
	if ok && filtreObjet != "" {
		ok = strings.Contains(strings.ToLower(DecoderEntete(h.Get("Subject"))), strings.ToLower(filtreObjet))
	}
	return ok
}

// PiecesJointes renvoie l'objet du message et ses pièces jointes (toutes, livres ou non).
func PiecesJointes(brut []byte) (string, []PieceJointe, error) {
	msg, err := mail.ReadMessage(bytes.NewReader(brut))
	if err != nil {
		return "", nil, err
	}
	objet := DecoderEntete(msg.Header.Get("Subject"))
	var pj []PieceJointe
	err = parcourir(textproto.MIMEHeader(msg.Header), msg.Body, &pj, 0)
	return objet, pj, err
}

func parcourir(h textproto.MIMEHeader, corps io.Reader, pj *[]PieceJointe, profondeur int) error {
	if profondeur > 12 {
		return nil
	}
	ct := h.Get("Content-Type")
	if ct == "" {
		ct = "text/plain"
	}
	mt, params, err := mime.ParseMediaType(ct)
	if err != nil && mt == "" {
		mt, params = "application/octet-stream", map[string]string{}
	}
	if strings.HasPrefix(mt, "multipart/") && params["boundary"] != "" {
		mr := multipart.NewReader(corps, params["boundary"])
		for {
			p, err := mr.NextRawPart()
			if err == io.EOF {
				return nil
			}
			if err != nil {
				return err
			}
			if err := parcourir(p.Header, p, pj, profondeur+1); err != nil {
				return err
			}
		}
	}
	nom := nomPiece(h, params)
	if mt == "message/rfc822" && nom == "" {
		// e-mail transféré en pièce jointe : on regarde dedans
		donnees, err := decoder(h.Get("Content-Transfer-Encoding"), corps)
		if err != nil {
			return err
		}
		inclus, err := mail.ReadMessage(bytes.NewReader(donnees))
		if err != nil {
			return nil
		}
		return parcourir(textproto.MIMEHeader(inclus.Header), inclus.Body, pj, profondeur+1)
	}
	if nom == "" {
		return nil // texte du message
	}
	donnees, err := decoder(h.Get("Content-Transfer-Encoding"), corps)
	if err != nil {
		return fmt.Errorf("pièce jointe « %s » illisible : %v", nom, err)
	}
	*pj = append(*pj, PieceJointe{Nom: nom, Donnees: donnees})
	return nil
}

func nomPiece(h textproto.MIMEHeader, paramsType map[string]string) string {
	if cd := h.Get("Content-Disposition"); cd != "" {
		if _, p, err := mime.ParseMediaType(cd); err == nil && p["filename"] != "" {
			return DecoderEntete(p["filename"])
		}
		// en-tête mal formé : on tente de lire filename="…" à la main
		if i := strings.Index(strings.ToLower(cd), "filename="); i >= 0 {
			v := strings.Trim(strings.TrimSpace(strings.SplitN(cd[i+9:], ";", 2)[0]), `"`)
			if v != "" {
				return DecoderEntete(v)
			}
		}
	}
	if paramsType["name"] != "" {
		return DecoderEntete(paramsType["name"])
	}
	return ""
}

func decoder(encodage string, r io.Reader) ([]byte, error) {
	switch strings.ToLower(strings.TrimSpace(encodage)) {
	case "base64":
		brut, err := io.ReadAll(r)
		if err != nil {
			return nil, err
		}
		propre := make([]byte, 0, len(brut))
		for _, c := range brut {
			if c != '\r' && c != '\n' && c != ' ' && c != '\t' {
				propre = append(propre, c)
			}
		}
		if d, err := base64.StdEncoding.DecodeString(string(propre)); err == nil {
			return d, nil
		}
		return base64.RawStdEncoding.DecodeString(strings.TrimRight(string(propre), "="))
	case "quoted-printable":
		return io.ReadAll(quotedprintable.NewReader(r))
	default:
		return io.ReadAll(r)
	}
}

// NomDeFichierSur rend un nom accepté par la mémoire de la Kobo (FAT32).
func NomDeFichierSur(nom string) string {
	nom = path.Base(strings.ReplaceAll(nom, `\`, "/"))
	var s strings.Builder
	for _, r := range nom {
		switch {
		case r < 32 || strings.ContainsRune(`"*/:<>?\|`, r):
			s.WriteRune('_')
		default:
			s.WriteRune(r)
		}
	}
	res := strings.Trim(s.String(), " .")
	ext := path.Ext(res)
	if strings.HasSuffix(strings.ToLower(res), ".kepub.epub") {
		ext = res[len(res)-len(".kepub.epub"):]
	}
	base := strings.TrimSuffix(res, ext)
	for utf8.RuneCountInString(base) > 120 { // FAT32 : 255 caractères au plus, on reste large
		_, taille := utf8.DecodeLastRuneInString(base)
		base = base[:len(base)-taille]
	}
	if base == "" {
		base = "livre"
	}
	return base + ext
}
