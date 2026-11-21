# -*- coding: utf-8 -*-
"""
Pont entre l'appli Android (Kotlin) et le moteur Python de Rekindle.
Toutes les fonctions renvoient du JSON (texte) pour rester simples côté Kotlin.
"""

import json
import os
import tempfile

_PRISES = set()   # fichiers de sortie déjà produits pendant ce passage (titres identiques)


def debut():
    """Nouveau passage « Réparer et envoyer »."""
    _PRISES.clear()
    return "ok"


def init(dossier_temp):
    """Android n'a pas de /tmp : on donne un dossier temporaire à Python."""
    os.makedirs(dossier_temp, exist_ok=True)
    os.environ["TMPDIR"] = dossier_temp
    tempfile.tempdir = dossier_temp
    return "ok"


def traiter(chemin, dossier_sortie, langue, tome_dans_titre=True):
    from rekindle_moteur import traiter_livre
    import saveur
    res = traiter_livre(chemin, dossier_sortie, {"langue": langue or "fr", "sorties_prises": _PRISES,
                                                 "tome_dans_titre": bool(tome_dans_titre),
                                                 "liseuse": saveur.LISEUSE})
    return json.dumps({
        "ok": res.ok,
        "sortie": res.sortie or "",
        "titre": res.titre or "",
        "auteur": res.auteur or "",
        "format": res.format_source or "",
        "taille": res.taille,
        "lignes": [[niv, msg] for niv, msg in res.rapport.lignes()],
    }, ensure_ascii=False)


class _Reglages(dict):
    """Ce que rekindle_mail attend d'un objet de réglages."""

    @property
    def login(self):
        return (self.get("identifiant") or self.get("expediteur") or "").strip()

    def mot_de_passe(self):
        return self.get("mdp", "")


def envoyer(cfg_json, chemin, titre, auteur):
    import rekindle_mail as km
    cfg = _Reglages(json.loads(cfg_json))
    try:
        km.envoyer_livre(cfg, chemin, titre or None, auteur or None)
        return json.dumps({"ok": True})
    except km.ErreurEnvoi as exc:
        return json.dumps({"ok": False, "erreur": str(exc), "bloquant": exc.bloquant}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"ok": False, "erreur": "Erreur inattendue : %s" % exc, "bloquant": False},
                          ensure_ascii=False)


def lots(cfg_json, livres_json):
    """Regroupe les livres en e-mails. livres : [{id, chemin, titre, auteur}]."""
    import rekindle_mail as km
    cfg = _Reglages(json.loads(cfg_json))
    livres = json.loads(livres_json)
    groupes, trop_gros = km.faire_lots(livres, cfg)
    return json.dumps({
        "lots": [[l["id"] for l in g] for g in groupes],
        "trop_gros": [{"id": l["id"], "message": km.message_trop_gros(cfg, l["chemin"])} for l in trop_gros],
    }, ensure_ascii=False)


def envoyer_lot(cfg_json, livres_json):
    """Un seul e-mail pour plusieurs livres. livres : [{chemin, titre, auteur}]."""
    import rekindle_mail as km
    cfg = _Reglages(json.loads(cfg_json))
    livres = [(l["chemin"], l.get("titre") or None, l.get("auteur") or None) for l in json.loads(livres_json)]
    try:
        km.envoyer_lot(cfg, livres)
        return json.dumps({"ok": True})
    except km.ErreurEnvoi as exc:
        return json.dumps({"ok": False, "erreur": str(exc), "bloquant": exc.bloquant}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"ok": False, "erreur": "Erreur inattendue : %s" % exc, "bloquant": False},
                          ensure_ascii=False)


def tester(cfg_json):
    import rekindle_mail as km
    cfg = _Reglages(json.loads(cfg_json))
    try:
        km.tester(cfg)
        return json.dumps({"ok": True, "message": "Connexion réussie : %s peut envoyer depuis %s."
                           % (km.saveur.NOM, cfg.get("expediteur", ""))}, ensure_ascii=False)
    except km.ErreurEnvoi as exc:
        return json.dumps({"ok": False, "message": str(exc)}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"ok": False, "message": "Erreur : %s" % exc}, ensure_ascii=False)


def lire_torrent(chemin):
    import rekindle_torrent as kt
    try:
        info = kt.lire(chemin)
        return json.dumps({"ok": True, "nom": info["nom"], "livres": len(info["livres"]),
                           "fichiers": len(info["fichiers"])}, ensure_ascii=False)
    except kt.ErreurTorrent as exc:
        return json.dumps({"ok": False, "erreur": str(exc)}, ensure_ascii=False)
