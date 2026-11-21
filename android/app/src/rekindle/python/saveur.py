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


def probleme_destination(adresse):
    a = (adresse or "").strip().lower()
    if not a:
        return "Indique ton adresse Kindle dans les réglages."
    if not (a.endswith("@kindle.com") or a.endswith("@free.kindle.com")):
        return "L'adresse Kindle doit finir par @kindle.com."
    return None
