# Rekindle

<img src="windows/images/mascotte.png" alt="Le requin lecteur, mascotte de Rekindle" width="120" align="right">

Récupère, répare et envoie des livres numériques vers une Kindle (Send to Kindle).
Anciennement Kwindle (et Kindlixo avant) : les réglages sont repris automatiquement.

- Répare les EPUB que Send to Kindle refuse (langue absente ou invalide, encodage,
  HTML cassé, polices obfusquées, manifeste faux, liens vers `<body>`, images WebP…).
- Convertit les MOBI / AZW3 (même renommés en `.epub`) en vrai EPUB.
- Récupère uniquement les livres (EPUB, MOBI, AZW3, PDF) d'un fichier `.torrent`.
- Envoie les livres par e-mail à l'adresse `@kindle.com`, regroupés dans un seul e-mail
  (jusqu'à 25 livres) pour n'avoir qu'une vérification Amazon à valider.
- Refuse les livres protégés par DRM.

## Dossiers

| Dossier    | Contenu |
|------------|---------|
| `windows/` | Version PC (Python + Tkinter). Lancer `Lancer Rekindle.bat`, voir `LISEZMOI.txt`. |
| `android/` | Version Android (Kotlin + Jetpack Compose ; le moteur Python tourne via Chaquopy, les torrents via libtorrent4j). |

Le moteur de réparation (`rekindle_moteur.py`) est le même dans les deux versions.

## Identité visuelle

Mascotte : un requin à lunettes qui lit. Couleurs : bleu marine `#0A2E4A`,
corail `#FF6B57`, crème `#F4F1E8`, écume `#E9F6FA`. Polices : Lilita One (nom)
et Nunito (texte), sous licence SIL OFL (voir `windows/polices/`).
Dans le nom, « Rekin » est en corail et « dle » en crème (ou bleu marine sur fond clair).

## APK Android

L'APK est compilé par GitHub Actions à chaque modification de `android/` :
page **Releases › Rekindle Android**, ou onglet **Actions** → dernier passage vert →
artefact **Rekindle-apk**. On peut aussi le relancer à la main (« Run workflow »).

L'APK est signé avec `android/app/kwindle.jks`, toujours la même clé, et garde
l'identifiant `fr.kwigorl.kwindle`, pour que chaque nouvelle version s'installe
par-dessus l'ancienne (Kwindle compris). Le dépôt est privé : ne pas le rendre
public sans changer de clé.
