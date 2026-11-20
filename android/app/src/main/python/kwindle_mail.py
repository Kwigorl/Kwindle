# -*- coding: utf-8 -*-
"""Kwindle — réglages et envoi vers l'adresse Send to Kindle."""

import json
import os
import smtplib
import socket
import ssl
import sys
from collections import OrderedDict
from email.message import EmailMessage

from kwindle_moteur import nom_fichier_sur

try:
    import keyring
except Exception:
    keyring = None

SERVICE = "Kwindle"

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

PAGE_AMAZON = "https://www.amazon.fr/mycd"


def dossier_config():
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    d = os.path.join(base, "Kwindle")
    os.makedirs(d, exist_ok=True)
    return d


def dossier_documents():
    docs = os.path.join(os.path.expanduser("~"), "Documents")
    return os.path.join(docs if os.path.isdir(docs) else os.path.expanduser("~"), "Kwindle")


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
}


class Reglages(dict):
    def __init__(self):
        super().__init__(DEFAUTS)
        self.chemin = os.path.join(dossier_config(), "reglages.json")
        source = self.chemin
        if not os.path.exists(source):
            # l'appli s'appelait Kindlixo : on reprend ses réglages s'il y en a
            ancien = os.path.join(os.path.dirname(dossier_config()), "Kindlixo", "reglages.json")
            if os.path.exists(ancien):
                source = ancien
        try:
            with open(source, encoding="utf-8") as f:
                self.update(json.load(f))
        except (OSError, ValueError):
            pass
        ancien_defaut = os.path.join(os.path.dirname(dossier_documents()), "Kindlixo")
        if not self.get("dossier_sortie") or self.get("dossier_sortie") == ancien_defaut:
            self["dossier_sortie"] = dossier_documents()

    def enregistrer(self):
        with open(self.chemin, "w", encoding="utf-8") as f:
            json.dump(dict(self), f, ensure_ascii=False, indent=2)

    @property
    def login(self):
        return (self.get("identifiant") or self.get("expediteur") or "").strip()

    def mot_de_passe(self):
        if keyring and self.login:
            for service in (SERVICE, "Kindlixo"):     # ancien nom de l'appli
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
        k = (self.get("kindle") or "").strip().lower()
        if not k:
            return "Indique ton adresse Kindle dans les réglages."
        if not (k.endswith("@kindle.com") or k.endswith("@free.kindle.com")):
            return "L'adresse Kindle doit finir par @kindle.com."
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


def envoyer_livre(cfg, chemin, titre=None, auteur=None):
    """Envoie un livre (un e-mail par livre). Lève ErreurEnvoi en cas de souci."""
    taille = os.path.getsize(chemin)
    if taille > 50 * 1024 * 1024:
        raise ErreurEnvoi("Fichier de %.0f Mo : Amazon limite l'e-mail à 50 Mo. "
                          "Utilise amazon.fr/sendtokindle (jusqu'à 200 Mo)." % (taille / 1048576))
    limite = FOURNISSEURS.get(cfg.get("fournisseur"), {}).get("limite")
    if limite and taille * 1.37 > limite * 1024 * 1024:
        raise ErreurEnvoi("Fichier de %.0f Mo : trop gros pour %s (pièces jointes limitées à %d Mo). "
                          "Utilise amazon.fr/sendtokindle." % (taille / 1048576, cfg["fournisseur"], limite))
    ext = os.path.splitext(chemin)[1].lower()
    sous_type = {".epub": "epub+zip", ".pdf": "pdf"}.get(ext, "octet-stream")
    base = titre or os.path.splitext(os.path.basename(chemin))[0]
    if auteur:
        base += " - " + auteur
    nom_pj = nom_fichier_sur(base, ascii_seul=True) + ext

    msg = EmailMessage()
    msg["From"] = cfg["expediteur"].strip()
    msg["To"] = cfg["kindle"].strip()
    msg["Subject"] = titre or "Livre"
    msg.set_content("Livre envoyé par Kwindle.\n")
    with open(chemin, "rb") as f:
        msg.add_attachment(f.read(), maintype="application", subtype=sous_type, filename=nom_pj)
    s = connexion(cfg)
    try:
        s.send_message(msg)
    except smtplib.SMTPRecipientsRefused:
        raise ErreurEnvoi("Adresse Kindle refusée : vérifie-la dans les réglages.")
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
