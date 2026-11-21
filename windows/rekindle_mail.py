# -*- coding: utf-8 -*-
"""Réglages et envoi des livres par e-mail vers la liseuse (Kindle ou Kobo, selon la saveur)."""

import json
import os
import smtplib
import socket
import ssl
import sys
from collections import OrderedDict
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

import saveur
from rekindle_moteur import nom_fichier_sur

try:
    import keyring
except Exception:
    keyring = None

SERVICE = saveur.NOM
ANCIENS_NOMS = tuple(saveur.ANCIENS_NOMS)

FOURNISSEURS = OrderedDict([
    ("Gmail", dict(serveur="smtp.gmail.com", port=465, securite="SSL",
                   aide="Gmail demande un « mot de passe d'application » (16 lettres), pas ton mot de "
                        "passe habituel. Active la validation en 2 étapes puis crée-le sur "
                        "myaccount.google.com/apppasswords.",
                   lien="https://myaccount.google.com/apppasswords", limite=25)),
    ("Yahoo", dict(serveur="smtp.mail.yahoo.com", port=465, securite="SSL",
                   aide="Yahoo demande un « mot de passe d'application » (Sécurité du compte).",
                   lien="https://login.yahoo.com/myaccount/security/", limite=25)),
    ("iCloud", dict(serveur="smtp.mail.me.com", port=587, securite="STARTTLS",
                    aide="iCloud demande un « mot de passe pour app » créé sur account.apple.com.",
                    lien="https://account.apple.com/", limite=20)),
    ("Orange", dict(serveur="smtp.orange.fr", port=465, securite="SSL",
                    aide="Adresse et mot de passe de ta messagerie Orange.", lien="", limite=None)),
    ("Free", dict(serveur="smtp.free.fr", port=465, securite="SSL",
                  aide="Adresse et mot de passe de ta messagerie Free.", lien="", limite=None)),
    ("SFR", dict(serveur="smtp.sfr.fr", port=465, securite="SSL",
                 aide="Adresse et mot de passe de ta messagerie SFR.", lien="", limite=None)),
    ("La Poste", dict(serveur="smtp.laposte.net", port=465, securite="SSL",
                      aide="Adresse et mot de passe de ta messagerie laposte.net.", lien="", limite=None)),
    ("Outlook / Hotmail", dict(serveur="smtp-mail.outlook.com", port=587, securite="STARTTLS",
                               aide="⚠ Microsoft a coupé l'envoi par mot de passe pour les comptes "
                                    "Outlook.com / Hotmail personnels : ça ne marchera pas. "
                                    "Utilise plutôt une adresse Gmail.", lien="", limite=None)),
    ("Autre", dict(serveur="", port=465, securite="SSL",
                   aide="Renseigne le serveur d'envoi (SMTP) de ta messagerie.", lien="", limite=None)),
])

PAGE_AMAZON = saveur.PAGE_AIDE


def dossier_config():
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    d = os.path.join(base, saveur.NOM)
    os.makedirs(d, exist_ok=True)
    return d


def dossier_documents():
    docs = os.path.join(os.path.expanduser("~"), "Documents")
    return os.path.join(docs if os.path.isdir(docs) else os.path.expanduser("~"), saveur.NOM)


DEFAUTS = {
    "kindle": "",
    "expediteur": "",
    "identifiant": "",
    "fournisseur": "Gmail",
    "serveur": "smtp.gmail.com",
    "port": 465,
    "securite": "SSL",
    "dossier_sortie": "",
    "envoyer": True,
    "langue": "fr",
    "tome_dans_titre": saveur.TOME_DANS_TITRE,
}


class Reglages(dict):
    def __init__(self):
        super().__init__(DEFAUTS)
        self.chemin = os.path.join(dossier_config(), "reglages.json")
        source = self.chemin
        if not os.path.exists(source):
            # l'appli s'appelait Kwindle, et Kindlixo avant : on reprend leurs réglages s'il y en a
            for ancien_nom in ANCIENS_NOMS:
                ancien = os.path.join(os.path.dirname(dossier_config()), ancien_nom, "reglages.json")
                if os.path.exists(ancien):
                    source = ancien
                    break
        try:
            with open(source, encoding="utf-8") as f:
                self.update(json.load(f))
        except (OSError, ValueError):
            pass
        anciens_defauts = [os.path.join(os.path.dirname(dossier_documents()), n) for n in ANCIENS_NOMS]
        if not self.get("dossier_sortie") or self.get("dossier_sortie") in anciens_defauts:
            self["dossier_sortie"] = dossier_documents()

    def enregistrer(self):
        with open(self.chemin, "w", encoding="utf-8") as f:
            json.dump(dict(self), f, ensure_ascii=False, indent=2)

    @property
    def login(self):
        return (self.get("identifiant") or self.get("expediteur") or "").strip()

    def mot_de_passe(self):
        if keyring and self.login:
            for service in (SERVICE,) + ANCIENS_NOMS:     # anciens noms de l'appli
                try:
                    mdp = keyring.get_password(service, self.login)
                    if mdp:
                        return mdp
                except Exception:
                    pass
        return self.get("mdp_secours", "")

    def definir_mot_de_passe(self, mdp):
        if keyring and self.login:
            try:
                keyring.set_password(SERVICE, self.login, mdp)
                self.pop("mdp_secours", None)
                return "coffre"
            except Exception:
                pass
        self["mdp_secours"] = mdp
        return "fichier"

    def probleme(self):
        """Ce qui manque pour pouvoir envoyer (None si tout va bien)."""
        p = saveur.probleme_destination(self.get("kindle"))
        if p:
            return p
        if not (self.get("expediteur") or "").strip():
            return "Indique l'adresse e-mail qui envoie les livres."
        if not (self.get("serveur") or "").strip():
            return "Indique le serveur d'envoi (SMTP)."
        if not self.mot_de_passe():
            return "Indique le mot de passe de ta messagerie."
        return None


class ErreurEnvoi(Exception):
    """bloquant=True : problème de connexion/identifiants, inutile d'essayer les livres suivants."""

    def __init__(self, msg, bloquant=False):
        super().__init__(msg)
        self.bloquant = bloquant


def contexte_ssl():
    """Contexte TLS ; sur Android, on complète avec les certificats de certifi si besoin."""
    ctx = ssl.create_default_context()
    try:
        if not ctx.cert_store_stats().get("x509_ca"):
            import certifi
            ctx.load_verify_locations(certifi.where())
    except Exception:
        pass
    return ctx


def connexion(cfg, mdp=None):
    mdp = mdp if mdp is not None else cfg.mot_de_passe()
    serveur = cfg["serveur"].strip()
    port = int(cfg["port"])
    ctx = contexte_ssl()
    try:
        if cfg.get("securite") == "SSL":
            s = smtplib.SMTP_SSL(serveur, port, context=ctx, timeout=60)
        else:
            s = smtplib.SMTP(serveur, port, timeout=60)
            s.ehlo()
            if cfg.get("securite") == "STARTTLS":
                s.starttls(context=ctx)
                s.ehlo()
        s.login(cfg.login, mdp)
        return s
    except smtplib.SMTPAuthenticationError as exc:
        msg = "Adresse ou mot de passe refusé par %s." % serveur
        if "gmail" in serveur:
            msg += (" Pour Gmail, il faut un mot de passe d'application (16 lettres), "
                    "pas ton mot de passe habituel.")
        elif "outlook" in serveur or "office365" in serveur or "basic authentication" in str(exc).lower():
            msg += (" Microsoft n'accepte plus l'envoi par mot de passe pour les comptes "
                    "Outlook/Hotmail personnels : utilise une autre adresse (Gmail par exemple).")
        raise ErreurEnvoi(msg, bloquant=True)
    except smtplib.SMTPException as exc:
        raise ErreurEnvoi("Le serveur a refusé la connexion : %s" % exc, bloquant=True)
    except (socket.gaierror, socket.timeout, ConnectionError, OSError) as exc:
        if isinstance(exc, ssl.SSLError):
            raise ErreurEnvoi("Problème de chiffrement avec %s:%d : essaie l'autre réglage de sécurité "
                              "(SSL ↔ STARTTLS) ou l'autre port (465 ↔ 587)." % (serveur, port), bloquant=True)
        raise ErreurEnvoi("Impossible de joindre %s:%d (connexion internet ? serveur ou port ?)."
                          % (serveur, port), bloquant=True)


def tester(cfg, mdp=None):
    s = connexion(cfg, mdp)
    try:
        s.quit()
    except Exception:
        pass


MAX_PJ = saveur.MAX_PJ           # pièces jointes par e-mail (Amazon : 25)
MAX_AMAZON = saveur.MAX_MAIL     # taille d'un e-mail côté liseuse (Amazon : 50 Mo)
MAX_LOT_INCONNU = 18 * 1024 * 1024


def limites(cfg):
    """(taille max d'un fichier seul, taille max d'un e-mail groupé), en octets avant encodage."""
    limite = FOURNISSEURS.get(cfg.get("fournisseur"), {}).get("limite")
    if limite:
        m = min(MAX_AMAZON, int(limite * 1024 * 1024 / 1.37))   # +37 % une fois encodé
        return m, m
    return MAX_AMAZON, MAX_LOT_INCONNU


def faire_lots(livres, cfg):
    """Regroupe des livres en e-mails (pour la Kindle : un e-mail = une seule vérification Amazon).

    `livres` : liste de dicts avec au moins la clé "chemin".
    Renvoie (lots, trop_gros) : liste de listes de livres, et livres impossibles à envoyer par e-mail.
    """
    max_fichier, max_lot = limites(cfg)
    lots, courant, total, trop_gros = [], [], 0, []
    for livre in livres:
        t = os.path.getsize(livre["chemin"])
        if t > max_fichier:
            trop_gros.append(livre)
            continue
        if t > max_lot:                      # gros fichier : tout seul dans son e-mail
            lots.append([livre])
            continue
        if courant and (total + t > max_lot or len(courant) >= MAX_PJ):
            lots.append(courant)
            courant, total = [], 0
        courant.append(livre)
        total += t
    if courant:
        lots.append(courant)
    return lots, trop_gros


def message_trop_gros(cfg, chemin):
    taille = os.path.getsize(chemin) / 1048576
    limite = FOURNISSEURS.get(cfg.get("fournisseur"), {}).get("limite")
    if limite and taille <= MAX_AMAZON / 1048576:
        return ("Fichier de %.0f Mo : trop gros pour %s (pièces jointes limitées à %d Mo). %s"
                % (taille, cfg["fournisseur"], limite, saveur.CONSEIL_GROS_FICHIER))
    return ("Fichier de %.0f Mo : trop gros pour un e-mail vers la %s (%d Mo au plus). %s"
            % (taille, saveur.LISEUSE, MAX_AMAZON / 1048576, saveur.CONSEIL_GROS_FICHIER))


def envoyer_lot(cfg, livres):
    """Envoie plusieurs livres dans UN seul e-mail. `livres` : liste de (chemin, titre, auteur)."""
    expediteur = cfg["expediteur"].strip()
    msg = EmailMessage()
    msg["From"] = expediteur
    msg["To"] = cfg["kindle"].strip()
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=expediteur.split("@")[-1] or None)
    if len(livres) == 1:
        msg["Subject"] = livres[0][1] or "Livre"
    else:
        msg["Subject"] = "%s : %d livres" % (saveur.NOM, len(livres))
    msg.set_content("Livres envoyés par %s :\n" % saveur.NOM + "\n".join(
        "- %s%s" % (titre or os.path.basename(chemin), " (%s)" % auteur if auteur else "")
        for chemin, titre, auteur in livres) + "\n")
    noms = set()
    for chemin, titre, auteur in livres:
        ext = os.path.splitext(chemin)[1].lower()
        sous_type = {".epub": "epub+zip", ".pdf": "pdf"}.get(ext, "octet-stream")
        if chemin.lower().endswith(".kepub.epub"):      # KEPUB (Kobo) : la double extension compte
            ext = ".kepub.epub"
        base = titre or os.path.splitext(os.path.basename(chemin))[0]
        if auteur:
            base += " - " + auteur
        base = nom_fichier_sur(base, ascii_seul=saveur.NOMS_PJ_ASCII)
        nom_pj, n = base + ext, 2
        while nom_pj.lower() in noms:
            nom_pj = "%s (%d)%s" % (base, n, ext)
            n += 1
        noms.add(nom_pj.lower())
        with open(chemin, "rb") as f:
            msg.add_attachment(f.read(), maintype="application", subtype=sous_type, filename=nom_pj)
    s = connexion(cfg)
    try:
        s.send_message(msg)
    except smtplib.SMTPRecipientsRefused:
        raise ErreurEnvoi(saveur.DESTINATION_REFUSEE)
    except smtplib.SMTPSenderRefused as exc:
        raise ErreurEnvoi("Expéditeur refusé par le serveur (%s)." % exc.smtp_error.decode("utf-8", "ignore"))
    except smtplib.SMTPDataError as exc:
        raise ErreurEnvoi("Le serveur a refusé le message : %s" % exc.smtp_error.decode("utf-8", "ignore"))
    except smtplib.SMTPException as exc:
        raise ErreurEnvoi("Échec de l'envoi : %s" % exc)
    finally:
        try:
            s.quit()
        except Exception:
            pass


def envoyer_livre(cfg, chemin, titre=None, auteur=None):
    """Envoie un seul livre. Lève ErreurEnvoi en cas de souci."""
    max_fichier, _ = limites(cfg)
    if os.path.getsize(chemin) > max_fichier:
        raise ErreurEnvoi(message_trop_gros(cfg, chemin))
    envoyer_lot(cfg, [(chemin, titre, auteur)])
