"""Fabrique le zip Windows d'une saveur : Rekindle (par défaut) ou Koboa.

    python fabriquer_zip.py rekindle DOSSIER_SORTIE
    python fabriquer_zip.py koboa DOSSIER_SORTIE
"""
import os
import subprocess
import sys
import zipfile

ICI = os.path.dirname(os.path.abspath(__file__))


def fichiers_suivis():
    sortie = subprocess.run(["git", "ls-files", "."], cwd=ICI, capture_output=True, text=True, check=True).stdout
    return [f for f in sortie.splitlines() if f and not f.startswith("saveurs/") and f != "fabriquer_zip.py"]


def fabriquer(saveur, dossier_sortie):
    nom = {"rekindle": "Rekindle", "koboa": "Koboa"}[saveur]
    contenu = {}
    for f in fichiers_suivis():
        with open(os.path.join(ICI, f), "rb") as h:
            contenu[f] = h.read()
    if saveur == "koboa":
        s = os.path.join(ICI, "saveurs", "koboa")
        for racine, _, noms in os.walk(s):
            for n in noms:
                chemin = os.path.join(racine, n)
                rel = os.path.relpath(chemin, s).replace(os.sep, "/")
                with open(chemin, "rb") as h:
                    contenu[rel] = h.read()
        # lanceurs : mêmes scripts, autre nom
        bat = contenu.pop("Lancer Rekindle.bat").decode("utf-8")
        contenu["Lancer Koboa.bat"] = bat.replace("Rekindle", "Koboa").encode("utf-8")
        rac = contenu["Creer un raccourci sur le Bureau.bat"].decode("utf-8")
        rac = rac.replace("Remove-Item -LiteralPath ($d+'\\Kwindle.lnk') -ErrorAction SilentlyContinue; ", "")
        rac = rac.replace("Rekindle", "Koboa").replace("ta Kindle", "ta Kobo")
        contenu["Creer un raccourci sur le Bureau.bat"] = rac.encode("utf-8")
        # LISEZMOI en fins de ligne Windows
        contenu["LISEZMOI.txt"] = contenu["LISEZMOI.txt"].replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    os.makedirs(dossier_sortie, exist_ok=True)
    zip_chemin = os.path.join(dossier_sortie, nom + ".zip")
    with zipfile.ZipFile(zip_chemin, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in sorted(contenu):
            z.writestr(nom + "/" + rel, contenu[rel])
    return zip_chemin


if __name__ == "__main__":
    print(fabriquer(sys.argv[1] if len(sys.argv) > 1 else "rekindle",
                    sys.argv[2] if len(sys.argv) > 2 else os.path.join(ICI, "..", "construction")))
