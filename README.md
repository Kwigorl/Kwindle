# Kwindle

Récupère, répare et envoie des livres numériques vers une Kindle (Send to Kindle).

- Répare les EPUB que Send to Kindle refuse (langue absente ou invalide, encodage,
  HTML cassé, polices obfusquées, manifeste faux, liens vers `<body>`, images WebP…).
- Convertit les MOBI / AZW3 (même renommés en `.epub`) en vrai EPUB.
- Récupère uniquement les livres (EPUB, MOBI, AZW3, PDF) d'un fichier `.torrent`.
- Envoie chaque livre par e-mail à l'adresse `@kindle.com`.
- Refuse les livres protégés par DRM.

## Dossiers

| Dossier    | Contenu |
|------------|---------|
| `windows/` | Version PC (Python + Tkinter). Lancer `Lancer Kwindle.bat`, voir `LISEZMOI.txt`. |
| `android/` | Version Android (Kotlin + Jetpack Compose ; le moteur Python tourne via Chaquopy, les torrents via libtorrent4j). |

Le moteur de réparation (`kwindle_moteur.py`) est le même dans les deux versions.

## APK Android

L'APK est compilé par GitHub Actions à chaque modification de `android/` :
onglet **Actions** → dernier passage vert → artefact **Kwindle-apk**.
On peut aussi le relancer à la main (« Run workflow »).

L'APK est signé avec `android/app/kwindle.jks`, toujours la même clé, pour que
chaque nouvelle version s'installe par-dessus l'ancienne. Le dépôt est privé :
ne pas le rendre public sans changer de clé.
