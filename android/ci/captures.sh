#!/bin/sh
# Captures d'écran de l'appli sur l'émulateur (lancé par le workflow de tests).
# usage : captures.sh <saveur> <paquet>   (rekindle fr.kwigorl.kwindle, koboa fr.kwigorl.koboa)
S=${1:-rekindle}
P=${2:-fr.kwigorl.kwindle}
D=../captures/$S
mkdir -p $D

centre_de() {
  # centre du premier élément dont l'attribut correspond (motif grep), d'après uiautomator
  adb shell uiautomator dump /sdcard/ui.xml >/dev/null 2>&1
  adb pull /sdcard/ui.xml /tmp/ui.xml >/dev/null 2>&1
  grep -o "<node [^>]*>" /tmp/ui.xml | grep "$1" | head -1 \
    | grep -o 'bounds="\[[0-9]*,[0-9]*\]\[[0-9]*,[0-9]*\]"' \
    | sed -E 's/bounds="\[([0-9]+),([0-9]+)\]\[([0-9]+),([0-9]+)\]"/\1 \2 \3 \4/' \
    | awk '{ printf "%d %d", ($1+$3)/2, ($2+$4)/2 }'
}

toucher() {
  XY=$(centre_de "$1")
  echo "toucher $1 -> $XY"
  [ -n "$XY" ] && adb shell input tap $XY
}

adb install -r app/build/outputs/apk/$S/debug/app-$S-debug.apk
adb shell pm grant $P android.permission.POST_NOTIFICATIONS
adb shell am start -W -n $P/fr.kwigorl.kwindle.MainActivity
sleep 6
adb exec-out screencap -p > $D/1_accueil.png

adb push app/src/androidTest/assets/test_casse.epub /data/local/tmp/Livre_casse.epub
adb push app/src/androidTest/assets/pack.torrent /data/local/tmp/Pack_JDR.torrent
adb shell chmod 644 /data/local/tmp/Livre_casse.epub /data/local/tmp/Pack_JDR.torrent
adb shell am start -W -a android.intent.action.VIEW -t application/epub+zip \
  -d file:///data/local/tmp/Livre_casse.epub -n $P/fr.kwigorl.kwindle.MainActivity
sleep 3
adb shell am start -W -a android.intent.action.VIEW -t application/x-bittorrent \
  -d file:///data/local/tmp/Pack_JDR.torrent -n $P/fr.kwigorl.kwindle.MainActivity
sleep 4
adb exec-out screencap -p > $D/2_liste.png

# on décoche « Envoyer à ma Kindle / Kobo » puis « Transformer »
toucher 'checkable="true"'
sleep 1
toucher 'text="Transformer"'
sleep 8
adb exec-out screencap -p > $D/3_repare.png

# détail du livre
toucher 'text="Test Kwindle'
sleep 2
adb exec-out screencap -p > $D/4_detail.png
adb shell input keyevent KEYCODE_BACK
sleep 1

# réglages
toucher 'content-desc="Réglages"'
sleep 2
adb exec-out screencap -p > $D/5_reglages.png
ls -la $D
