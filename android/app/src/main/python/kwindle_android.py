# -*- coding: utf-8 -*-
"""
Pont entre l'appli Android (Kotlin) et le moteur Python de Kwindle.
Toutes les fonctions renvoient du JSON (texte) pour rester simples côté Kotlin.
"""

import json
import os
import tempfile


def init(dossier_temp):
    """Android n'a pas de /tmp : on donne un dossier temporaire à Python."""
    os.makedirs(dossier_temp, exist_ok=True)
    os.environ["TMPDIR"] = dossier_temp
    tempfile.tempdir = dossier_temp
    return "ok"


def traiter(chemin, dossier_sortie, langue):
    from kwindle_moteur import traiter_livre
    res = traiter_livre(chemin, dossier_sortie, {"langue": langue or "fr"})
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
    """Ce que kwindle_mail attend d'un objet de réglages."""

    @property
    def login(self):
        return (self.get("identifiant") or self.get("expediteur") or "").strip()

    def mot_de_passe(self):
        return self.get("mdp", "")


def envoyer(cfg_json, chemin, titre, auteur):
    import kwindle_mail as km
    cfg = _Reglages(json.loads(cfg_json))
    try:
        km.envoyer_livre(cfg, chemin, titre or None, auteur or None)
        return json.dumps({"ok": True})
    except km.ErreurEnvoi as exc:
        return json.dumps({"ok": False, "erreur": str(exc), "bloquant": exc.bloquant}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"ok": False, "erreur": "Erreur inattendue : %s" % exc, "bloquant": False},
                          ensure_ascii=False)


def tester(cfg_json):
    import kwindle_mail as km
    cfg = _Reglages(json.loads(cfg_json))
    try:
        km.tester(cfg)
        return json.dumps({"ok": True, "message": "Connexion réussie : Kwindle peut envoyer depuis %s."
                           % cfg.get("expediteur", "")}, ensure_ascii=False)
    except km.ErreurEnvoi as exc:
        return json.dumps({"ok": False, "message": str(exc)}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"ok": False, "message": "Erreur : %s" % exc}, ensure_ascii=False)


def lire_torrent(chemin):
    import kwindle_torrent as kt
    try:
        info = kt.lire(chemin)
        return json.dumps({"ok": True, "nom": info["nom"], "livres": len(info["livres"]),
                           "fichiers": len(info["fichiers"])}, ensure_ascii=False)
    except kt.ErreurTorrent as exc:
        return json.dumps({"ok": False, "erreur": str(exc)}, ensure_ascii=False)
