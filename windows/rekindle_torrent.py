# -*- coding: utf-8 -*-
"""
Rekindle — récupération des livres contenus dans un fichier .torrent.

Ne télécharge QUE les livres (EPUB, MOBI, AZW3, PDF) du torrent, pas le reste.
Le torrent reste partagé tant que Rekindle est ouvert.
"""

import os
import sys
import threading
import time

try:
    import libtorrent as lt
    _ERREUR_IMPORT = None
except Exception as exc:  # module absent, ou DLL manquante sous Windows
    lt = None
    _ERREUR_IMPORT = exc

EXT_LIVRES = (".epub", ".mobi", ".azw", ".azw3", ".prc", ".pdf")
DELAI_SANS_SOURCE = 10 * 60      # abandon si rien ne bouge pendant 10 min
LIEN_VCREDIST = "https://aka.ms/vs/17/release/vc_redist.x64.exe"


class ErreurTorrent(Exception):
    pass


def disponible():
    return lt is not None


def raison_indisponible():
    if lt is not None:
        return None
    txt = str(_ERREUR_IMPORT)
    if "DLL" in txt or "dll" in txt:
        return ("Il manque un composant de Windows (« Visual C++ Redistributable ») pour les torrents. "
                "Installe-le depuis %s puis relance Rekindle." % LIEN_VCREDIST)
    v = sys.version_info
    if (v.major, v.minor) >= (3, 14) or (v.major, v.minor) < (3, 10):
        return ("Le module torrent n'existe que pour Python 3.10 à 3.13, et Rekindle tourne avec "
                "Python %d.%d. Installe Python 3.13 (par exemple en tapant « winget install -e --id "
                "Python.Python.3.13 » dans un terminal), puis relance « Lancer Rekindle.bat » : "
                "il choisira tout seul la bonne version." % (v.major, v.minor))
    return "Le module torrent (libtorrent) n'est pas installé : relance « Lancer Rekindle.bat »."


# --------------------------------------------------------------------------
# Lecture du .torrent sans libtorrent (pour afficher le nom tout de suite)
# --------------------------------------------------------------------------

def _bdecode(data, i=0):
    c = data[i:i + 1]
    if c == b"i":
        fin = data.index(b"e", i)
        return int(data[i + 1:fin]), fin + 1
    if c == b"l":
        i += 1
        out = []
        while data[i:i + 1] != b"e":
            v, i = _bdecode(data, i)
            out.append(v)
        return out, i + 1
    if c == b"d":
        i += 1
        out = {}
        while data[i:i + 1] != b"e":
            k, i = _bdecode(data, i)
            v, i = _bdecode(data, i)
            out[k] = v
        return out, i + 1
    if c.isdigit():
        sep = data.index(b":", i)
        n = int(data[i:sep])
        return data[sep + 1:sep + 1 + n], sep + 1 + n
    raise ValueError("bencode invalide")


def _txt(b):
    if isinstance(b, bytes):
        for enc in ("utf-8", "cp1252", "latin-1"):
            try:
                return b.decode(enc)
            except UnicodeDecodeError:
                pass
    return str(b)


def lire(chemin):
    """{'nom', 'fichiers': [(index, chemin_relatif, taille)], 'livres': [...même format...]}"""
    try:
        with open(chemin, "rb") as f:
            data = f.read()
        meta, _ = _bdecode(data)
        info = meta[b"info"]
    except Exception:
        raise ErreurTorrent("ce fichier .torrent est illisible")
    nom = _txt(info.get(b"name.utf-8") or info.get(b"name") or b"torrent")
    fichiers = []
    if b"files" in info:                       # torrent v1 multi-fichiers
        for i, f in enumerate(info[b"files"]):
            if f.get(b"attr", b"") and b"p" in f.get(b"attr", b""):
                continue                        # fichier de remplissage
            parties = f.get(b"path.utf-8") or f.get(b"path") or []
            fichiers.append((i, "/".join([nom] + [_txt(p) for p in parties]), f.get(b"length", 0)))
    elif b"length" in info:                     # un seul fichier
        fichiers.append((0, nom, info[b"length"]))
    elif b"file tree" in info:                  # torrent v2 pur
        def parcourir(arbre, prefixe):
            for k, v in arbre.items():
                if b"" in v:
                    fichiers.append((len(fichiers), prefixe + [_txt(k)], v[b""].get(b"length", 0)))
                else:
                    parcourir(v, prefixe + [_txt(k)])
        parcourir(info[b"file tree"], [nom])
        fichiers = [(i, "/".join(p), t) for i, p, t in fichiers]
    livres = [f for f in fichiers if os.path.splitext(f[1])[1].lower() in EXT_LIVRES]
    return {"nom": nom, "fichiers": fichiers, "livres": livres}


# --------------------------------------------------------------------------
# Téléchargement
# --------------------------------------------------------------------------

class Telechargeur:
    """Une seule session BitTorrent pour toute l'appli."""
    _instance = None
    _verrou = threading.Lock()

    @classmethod
    def get(cls):
        with cls._verrou:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        if lt is None:
            raise ErreurTorrent(raison_indisponible())
        self.ses = lt.session({
            "listen_interfaces": "0.0.0.0:6881,[::]:6881",
            "enable_dht": True,
            "enable_lsd": True,
            "enable_upnp": True,
            "enable_natpmp": True,
            "dht_bootstrap_nodes": ("dht.libtorrent.org:25401,router.bittorrent.com:6881,"
                                    "router.utorrent.com:6881,dht.transmissionbt.com:6881"),
            "user_agent": "Rekindle/1.1 libtorrent/" + lt.__version__,
            "stop_tracker_timeout": 2,
        })
        self.handles = {}

    def ajouter_pair(self, h, hote, port):
        h.connect_peer((hote, port))

    def telecharger(self, chemin_torrent, dossier, progression=None, arret=None,
                    delai_sans_source=DELAI_SANS_SOURCE, pairs=()):
        """Télécharge les livres du torrent dans `dossier`. Renvoie leurs chemins."""
        infos = lire(chemin_torrent)
        if not infos["livres"]:
            raise ErreurTorrent("ce torrent ne contient aucun livre (EPUB, MOBI, AZW3 ou PDF)")
        try:
            if hasattr(lt, "load_torrent_file"):
                # libtorrent 2.1 : les trackers et sources web sont dans add_torrent_params
                atp = lt.load_torrent_file(chemin_torrent)
                ti = atp.ti
            else:
                atp = lt.add_torrent_params()
                ti = atp.ti = lt.torrent_info(chemin_torrent)
        except Exception:
            raise ErreurTorrent("ce fichier .torrent est illisible")
        fs = ti.files()
        voulus = []
        prios = []
        for i in range(fs.num_files()):
            chemin = fs.file_path(i)
            est_livre = os.path.splitext(chemin)[1].lower() in EXT_LIVRES and \
                not (fs.file_flags(i) & fs.flag_pad_file)
            prios.append(4 if est_livre else 0)
            if est_livre:
                voulus.append(i)
        os.makedirs(dossier, exist_ok=True)

        cle = str(ti.info_hashes())
        h = self.handles.get(cle)
        if h is None or not h.is_valid():
            atp.save_path = dossier
            atp.file_priorities = prios
            h = self.ses.add_torrent(atp)
            self.handles[cle] = h
        else:
            h.prioritize_files(prios)
            h.resume()
        for hote, port in pairs:
            self.ajouter_pair(h, hote, port)

        dernier_fait = -1
        t_dernier = time.time()
        while True:
            if arret is not None and arret.is_set():
                self.ses.remove_torrent(h)
                self.handles.pop(cle, None)
                raise ErreurTorrent("téléchargement arrêté")
            s = h.status()
            if s.errc.value():
                raise ErreurTorrent("erreur du torrent : %s" % s.errc.message())
            total = s.total_wanted
            fait = s.total_wanted_done
            if progression:
                progression(fait / total if total else 0.0, s.num_peers, s.download_rate,
                            s.state == lt.torrent_status.checking_files)
            if total and fait >= total and s.state not in (lt.torrent_status.checking_files,
                                                            lt.torrent_status.checking_resume_data):
                break
            if fait != dernier_fait:
                dernier_fait = fait
                t_dernier = time.time()
            elif time.time() - t_dernier > delai_sans_source:
                self.ses.remove_torrent(h)
                self.handles.pop(cle, None)
                if fait == 0:
                    raise ErreurTorrent("personne ne partage ce torrent en ce moment "
                                        "(aucune source en %d min)" % (delai_sans_source // 60))
                raise ErreurTorrent("le téléchargement est bloqué depuis %d min (plus aucune source)"
                                    % (delai_sans_source // 60))
            time.sleep(0.5)

        chemins = []
        for i in voulus:
            p = os.path.join(dossier, *fs.file_path(i).replace("\\", "/").split("/"))
            if os.path.isfile(p) and os.path.getsize(p) == fs.file_size(i):
                chemins.append(p)
        if not chemins:
            raise ErreurTorrent("téléchargement terminé mais fichiers introuvables")
        return chemins

    def arreter(self):
        try:
            self.ses.pause()
        except Exception:
            pass
