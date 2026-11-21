"""Saveur de l'appli : Koboa, pour les liseuses Kobo.

Les livres partent par e-mail vers la boîte que relève KoboaExpress sur la Kobo
(par exemple prenom+kobo@gmail.com).
"""

NOM = "Koboa"
# le nom en deux morceaux ; True = morceau en couleur (« boa » en ambre)
PARTIES_NOM = (("Ko", False), ("boa", True))
LISEUSE = "Kobo"
ANCIENS_NOMS = ()

# options par défaut
TOME_DANS_TITRE = False       # la Kobo range elle-même les séries (informations calibre)

# envoi par e-mail
MAX_PJ = 25
MAX_MAIL = 50 * 1024 * 1024          # Gmail reçoit jusqu'à 50 Mo par e-mail
NOMS_PJ_ASCII = False                # KoboaExpress garde les accents
LIBELLE_DESTINATION = "Adresse de la Kobo"
EXEMPLE_DESTINATION = "prenom+kobo@gmail.com"
DESTINATION_REFUSEE = "Adresse de la Kobo refusée : vérifie-la dans les réglages."
CONSEIL_GROS_FICHIER = "Copie-le sur la Kobo avec un câble USB."
PAGE_AIDE = "https://github.com/Kwigorl/Kwindle/releases/tag/kobo"
LIBELLE_PAGE_AIDE = "Télécharger KoboaExpress"
AIDE_DESTINATION = ("C'est l'adresse que relève KoboaExpress, installé sur la Kobo : les livres envoyés "
                    "là arrivent tout seuls sur la liseuse à la connexion Wi-Fi suivante. Avec Gmail, "
                    "prenom+kobo@gmail.com arrive dans la boîte prenom@gmail.com.")


# interface
SLOGAN = "Répare tes livres et les envoie à ta Kobo  ·  EPUB, MOBI, PDF, torrents"
ID_WINDOWS = "Kwigorl.Koboa"
COULEURS = {
    "principale": "#12372A", "principale_claire": "#1E4D3A", "principale_survol": "#28614A",
    "secondaire": "#3E9B5A", "accent": "#F4A93B", "accent_clair": "#FFC46B",
    "creme": "#F6F1DE", "brume": "#A8CBB4", "fond": "#EFF6EA", "bordure": "#D3E6CF",
    "survol": "#E2F1DE", "selection": "#DCEFD6", "barre_active": "#BFDDB8", "inactif": "#9DB8A5",
    "texte_doux": "#46604F",
}
# après l'envoi
APRES_UN_ENVOI = ("Envoyé ! Les livres arriveront sur la Kobo à sa prochaine connexion Wi-Fi "
                  "(KoboaExpress relève la boîte mail).")
APRES_PLUSIEURS_ENVOIS = ("Envoyé en %d e-mails. Les livres arriveront sur la Kobo à sa prochaine connexion Wi-Fi "
                          "(KoboaExpress relève la boîte mail).")
APRES_ENVOI_COURT = "Les livres arriveront sur la Kobo à sa prochaine connexion Wi-Fi (KoboaExpress)."

def probleme_destination(adresse):
    a = (adresse or "").strip()
    if not a:
        return "Indique l'adresse e-mail de la Kobo (celle que relève KoboaExpress) dans les réglages."
    if "@" not in a or " " in a or a.startswith("@") or a.endswith("@"):
        return "L'adresse de la Kobo n'est pas une adresse e-mail valide."
    return None
