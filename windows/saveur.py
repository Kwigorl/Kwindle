"""Saveur de l'appli : Rekindle, pour les liseuses Kindle (Send to Kindle).

La même base de code donne aussi Koboa (Kobo) : seul ce fichier, les images et
les couleurs changent (voir saveurs/koboa).
"""

NOM = "Rekindle"
# le nom en deux morceaux ; True = morceau en couleur (« Rekin » en corail)
PARTIES_NOM = (("Rekin", True), ("dle", False))
LISEUSE = "Kindle"
ANCIENS_NOMS = ("Kwindle", "Kindlixo")      # pour reprendre les anciens réglages

# options par défaut
TOME_DANS_TITRE = True        # la Kindle ne range pas les séries des documents envoyés
KEPUB = False                # pas de KEPUB : c'est un format Kobo

# envoi par e-mail
MAX_PJ = 25                          # Amazon : 25 pièces jointes maximum par e-mail
MAX_MAIL = 50 * 1024 * 1024          # Amazon : 50 Mo par e-mail
MAX_LOT = None                       # pas de limite propre pour les e-mails groupés
NOMS_PJ_ASCII = True                 # Amazon digère mal les accents dans les noms de pièces jointes
LIBELLE_DESTINATION = "Adresse Kindle"
EXEMPLE_DESTINATION = "prenom_xxx@kindle.com"
DESTINATION_REFUSEE = "Adresse Kindle refusée : vérifie-la dans les réglages."
CONSEIL_GROS_FICHIER = "Utilise amazon.fr/sendtokindle (jusqu'à 200 Mo)."
PAGE_AIDE = "https://www.amazon.fr/mycd"
LIBELLE_PAGE_AIDE = "Ouvrir la page Amazon"
AIDE_DESTINATION = ("Tu la trouves sur amazon.fr → Gérer votre contenu et vos appareils → Préférences → "
                    "Paramètres des documents personnels. Sur la même page, ajoute l'adresse d'envoi "
                    "ci-dessous à la « liste des adresses e-mail approuvées », sinon Amazon ignore les livres.")


# interface
SLOGAN = "Répare tes livres et les envoie à ta Kindle  ·  EPUB, MOBI, PDF, torrents"
ID_WINDOWS = "Kwigorl.Rekindle"
COULEURS = {
    "principale": "#0A2E4A", "principale_claire": "#123E5F", "principale_survol": "#1B4868",
    "secondaire": "#127C9E", "accent": "#FF6B57", "accent_clair": "#FF8A78",
    "creme": "#F4F1E8", "brume": "#A9C7DA", "fond": "#E9F6FA", "bordure": "#CFE6EE",
    "survol": "#DCEFF5", "selection": "#D7EEF5", "barre_active": "#B5D7E3", "inactif": "#8AA4B8",
    "texte_doux": "#3F5566",
}
# après l'envoi
APRES_UN_ENVOI = ("Envoyé en un seul e-mail. Si Amazon t'envoie un mail « Vérifiez votre demande », clique "
                  "sur le lien : sans ça, les livres n'arrivent pas. Ensuite, ils arrivent sur ta Kindle en "
                  "quelques minutes (Wi-Fi activé).")
APRES_PLUSIEURS_ENVOIS = ("Envoyé en %d e-mails. Amazon peut demander une vérification pour CHACUN : Gmail range "
                          "ces mails « Vérifiez votre demande » dans une seule conversation, ouvre-les tous et "
                          "clique sur chaque lien.")
APRES_ENVOI_COURT = "Si Amazon envoie un mail « Vérifiez votre demande », clique sur le lien (un par e-mail)."

def probleme_destination(adresse):
    a = (adresse or "").strip().lower()
    if not a:
        return "Indique ton adresse Kindle dans les réglages."
    if not (a.endswith("@kindle.com") or a.endswith("@free.kindle.com")):
        return "L'adresse Kindle doit finir par @kindle.com."
    return None
