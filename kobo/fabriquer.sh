#!/bin/sh
# Fabrique KoboaExpress.zip : à copier sur la Kobo.
# Compiler avec Go 1.23 au plus : Go 1.24 exige un noyau Linux 3.2, plus récent que celui des vieilles Kobo.
set -e
cd "$(dirname "$0")"
C=construction
rm -rf "$C"
mkdir -p "$C/racine/usr/local/koboaexpress" "$C/racine/etc/udev/rules.d" \
         "$C/zip/A copier sur la Kobo/.kobo" "$C/zip/A copier sur la Kobo/.adds/nm" "$C/zip/A copier sur la Kobo/KoboaExpress"

CGO_ENABLED=0 GOOS=linux GOARCH=arm GOARM=7 go build -trimpath -ldflags "-s -w" -o "$C/racine/usr/local/koboaexpress/koboaexpress" .
cp paquet/lancer.sh "$C/racine/usr/local/koboaexpress/lancer.sh"
chmod 755 "$C/racine/usr/local/koboaexpress/koboaexpress" "$C/racine/usr/local/koboaexpress/lancer.sh"
cp paquet/97-koboaexpress.rules "$C/racine/etc/udev/rules.d/97-koboaexpress.rules"
chmod 644 "$C/racine/etc/udev/rules.d/97-koboaexpress.rules"
# seulement nos fichiers (et notre dossier) : on ne touche pas aux droits de /usr, /etc…
tar --format=gnu --owner=0 --group=0 --numeric-owner --no-recursion -czf "$C/zip/A copier sur la Kobo/.kobo/KoboRoot.tgz" \
    -C "$C/racine" usr/local/koboaexpress usr/local/koboaexpress/koboaexpress usr/local/koboaexpress/lancer.sh etc/udev/rules.d/97-koboaexpress.rules

K="$C/zip/A copier sur la Kobo"
cp paquet/nickelmenu "$K/.adds/nm/koboaexpress"
# fins de ligne Windows : le fichier s'ouvre proprement dans n'importe quel Bloc-notes
sed 's/$/\r/' reglages.ini > "$K/KoboaExpress/reglages.ini"
sed 's/$/\r/' LISEZ-MOI.txt > "$C/zip/LISEZ-MOI.txt"
(cd "$C/zip" && rm -f ../KoboaExpress.zip && zip -qrX ../KoboaExpress.zip "LISEZ-MOI.txt" "A copier sur la Kobo")
echo "$C/KoboaExpress.zip"
