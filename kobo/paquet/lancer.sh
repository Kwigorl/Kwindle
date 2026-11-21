#!/bin/sh
# Rekobo : relève la boîte mail et range sur la Kobo les livres reçus en pièce jointe.
# Lancé par udev quand le Wi-Fi s'allume (« wifi »), ou depuis NickelMenu (« manuel »).
ORIGINE="${1:-manuel}"
RACINE=/usr/local/rekobo
DOSSIER=/mnt/onboard/Rekobo
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

# la mémoire de la liseuse doit être disponible (pas pendant une connexion USB)
[ -d /mnt/onboard/.kobo ] || exit 0

# désinstallation : un fichier (vide) nommé DESINSTALLER dans le dossier Rekobo
if [ -e "$DOSSIER/DESINSTALLER" ]; then
    rm -f /etc/udev/rules.d/97-rekobo.rules /mnt/onboard/.adds/nm/rekobo "$DOSSIER/DESINSTALLER"
    echo "$(date '+%Y/%m/%d %H:%M:%S') Rekobo désinstallé" >> "$DOSSIER/journal.log"
    rm -rf "$RACINE"
    exit 0
fi

# udev attend la fin de ce qu'il lance : on continue en arrière-plan
if [ -z "$REKOBO_DETACHE" ]; then
    export REKOBO_DETACHE=1
    if command -v setsid >/dev/null 2>&1; then
        setsid "$0" "$ORIGINE" </dev/null >/dev/null 2>&1 &
    else
        nohup "$0" "$ORIGINE" </dev/null >/dev/null 2>&1 &
    fi
    exit 0
fi

# le Wi-Fi vient de s'allumer : on laisse le temps à la connexion de s'établir
[ "$ORIGINE" = "wifi" ] && sleep 8
exec "$RACINE/rekobo" -dossier "$DOSSIER" -origine "$ORIGINE"
