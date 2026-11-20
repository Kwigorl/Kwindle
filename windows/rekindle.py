#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rekindle — répare tes livres (EPUB, MOBI renommés…) pour Send to Kindle
et les envoie directement à ton adresse Kindle.

  Interface :     python rekindle.py
  Ligne de cmd :  python rekindle.py livre.epub [--envoyer] [--verifier] [--sortie DOSSIER]
"""

import argparse
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)

from rekindle_moteur import traiter_livre  # noqa: E402
import rekindle_mail as km                 # noqa: E402
import rekindle_torrent as kt              # noqa: E402

VERSION = "1.1"
SYMBOLES = {"info": "ℹ", "corrige": "✓", "alerte": "⚠", "erreur": "✗"}
EXTENSIONS = (".epub", ".mobi", ".azw", ".azw3", ".prc", ".pdf", ".torrent")


def dossier_torrents(cfg):
    return os.path.join(cfg["dossier_sortie"], "Torrents")
FORMATS = {"zip": "EPUB", "mobi": "MOBI / AZW", "pdf": "PDF", "topaz": "Topaz",
           "kfx": "KFX", "palmdoc": "PalmDoc", "inconnu": "?"}


def ouvrir(chemin, selectionner=False):
    try:
        if sys.platform.startswith("win"):
            if selectionner and os.path.isfile(chemin):
                subprocess.Popen(["explorer", "/select,", os.path.normpath(chemin)])
            else:
                os.startfile(chemin)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R" if selectionner else "", chemin])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(chemin) if selectionner else chemin])
    except Exception:
        pass


# ==========================================================================
# Ligne de commande
# ==========================================================================

def ligne_de_commande(args):
    cfg = km.Reglages()
    sortie = args.sortie or (tempfile.mkdtemp(prefix="rekindle_") if args.verifier else cfg["dossier_sortie"])
    code = 0
    livres = []
    for chemin in args.livres:
        if not chemin.lower().endswith(".torrent"):
            livres.append(chemin)
            continue
        try:
            info = kt.lire(chemin)
            print("⇣ Torrent « %s » : %d livre(s) sur %d fichier(s)"
                  % (info["nom"], len(info["livres"]), len(info["fichiers"])))
            if not kt.disponible():
                raise kt.ErreurTorrent(kt.raison_indisponible())

            def prog(frac, pairs, debit, verif):
                sys.stdout.write("\r    %3d %%  ·  %d source(s)  ·  %.0f ko/s   "
                                 % (frac * 100, pairs, debit / 1024))
                sys.stdout.flush()
            recus = kt.Telechargeur.get().telecharger(chemin, os.path.join(sortie, "Torrents"), prog)
            print("\r    ✓ %d livre(s) récupéré(s)                    " % len(recus))
            livres += recus
        except kt.ErreurTorrent as exc:
            print("    ✗ %s" % exc)
            code = 1
    if args.envoyer and cfg.probleme():
        print("✗ Envoi impossible : " + cfg.probleme())
        return 1
    prets = []
    prises = set()
    for chemin in livres:
        res = traiter_livre(chemin, sortie, {"langue": cfg.get("langue", "fr"), "sorties_prises": prises})
        print(("✓ " if res.ok else "✗ ") + os.path.basename(chemin))
        for niv, msg in res.rapport.lignes():
            print("    %s %s" % (SYMBOLES[niv], msg))
        if not res.ok:
            code = 1
            continue
        if not args.verifier:
            print("    → %s" % res.sortie)
        prets.append({"chemin": res.sortie, "titre": res.titre, "auteur": res.auteur})
    if args.envoyer and prets:
        lots, trop_gros = km.faire_lots(prets, cfg)
        for e in trop_gros:
            print("✗ « %s » : %s" % (e["titre"], km.message_trop_gros(cfg, e["chemin"])))
            code = 1
        for lot in lots:
            titres = ", ".join("« %s »" % e["titre"] for e in lot)
            try:
                km.envoyer_lot(cfg, [(e["chemin"], e["titre"], e["auteur"]) for e in lot])
                print("✉ Envoyé à %s en un seul e-mail : %s" % (cfg["kindle"], titres))
            except km.ErreurEnvoi as exc:
                print("✗ Envoi de %s : %s" % (titres, exc))
                code = 1
                if exc.bloquant:
                    return code
        if lots:
            print("  Si Amazon envoie un mail « Vérifiez votre demande », clique sur le lien (un par e-mail).")
    return code


# ==========================================================================
# Interface graphique
# ==========================================================================

def charger_polices():
    """Rend les polices de Rekindle (dossier polices) utilisables par l'appli, sans les installer."""
    dossier = os.path.join(ICI, "polices")
    try:
        import ctypes
        for f in os.listdir(dossier):
            if f.lower().endswith(".ttf"):
                ctypes.windll.gdi32.AddFontResourceExW(os.path.join(dossier, f), 0x10, 0)  # FR_PRIVATE
    except Exception:
        pass


def interface():
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    try:
        from tkinterdnd2 import TkinterDnD, DND_FILES
    except Exception:
        TkinterDnD = None

    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
            # icône Rekindle dans la barre des tâches (et pas celle de Python)
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Kwigorl.Rekindle")
        except Exception:
            pass
        charger_polices()

    root = TkinterDnD.Tk() if TkinterDnD else tk.Tk()

    from tkinter import font as tkfont
    familles = set(tkfont.families(root))
    if "Nunito" in familles:
        POLICE = "Nunito"
    else:
        POLICE = "Segoe UI" if sys.platform.startswith("win") else "DejaVu Sans"
    if sys.platform.startswith("win") and "Nunito ExtraBold" in familles:
        def forte(taille):
            return ("Nunito ExtraBold", taille)
    else:
        def forte(taille):
            return (POLICE, taille, "bold")
    POLICE_TITRE = "Lilita One" if "Lilita One" in familles else None
    echelle = max(1.0, root.winfo_fpixels("1i") / 96.0)

    # couleurs de Rekindle
    MARINE, MARINE_CLAIR, OCEAN = "#0A2E4A", "#123E5F", "#127C9E"
    CORAIL, CORAIL_CLAIR, CREME, BRUME = "#FF6B57", "#FF8A78", "#F4F1E8", "#A9C7DA"
    ECUME, BORDURE, BLANC = "#E9F6FA", "#CFE6EE", "#FFFFFF"
    GRIS = "#3F5566"
    VERT, ORANGE, ROUGE, BLEU = "#1d7a3a", "#b35c00", "#c0262d", "#0E6A86"

    root.configure(background=ECUME)
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", font=(POLICE, 10), background=ECUME, foreground=MARINE, bordercolor=BORDURE,
                    lightcolor=BLANC, darkcolor=BORDURE, troughcolor=ECUME, focuscolor=OCEAN,
                    selectbackground=BORDURE, selectforeground=MARINE, fieldbackground=BLANC,
                    insertcolor=MARINE)
    style.configure("TLabel", background=ECUME, foreground=MARINE)
    style.configure("Titre.TLabel", font=(POLICE_TITRE, 20) if POLICE_TITRE else forte(20))
    style.configure("Sous.TLabel", font=(POLICE, 10), foreground=GRIS)
    style.configure("Aide.TLabel", font=(POLICE, 9), foreground=GRIS)
    style.configure("Section.TLabel", font=forte(11), foreground=MARINE)
    style.configure("TButton", background=BLANC, foreground=MARINE, bordercolor=BORDURE, lightcolor=BLANC,
                    darkcolor=BLANC, padding=(12, 5), relief="flat", font=(POLICE, 10, "bold"))
    style.map("TButton", background=[("disabled", ECUME), ("pressed", BORDURE), ("active", "#DCEFF5")],
              foreground=[("disabled", "#8AA4B8")])
    for nom, fond, texte, survol in (("Primaire", MARINE, CREME, MARINE_CLAIR),
                                     ("Corail", CORAIL, MARINE, CORAIL_CLAIR),
                                     ("Stop", ROUGE, BLANC, "#a51f25"),
                                     ("Entete", MARINE_CLAIR, CREME, "#1B4868")):
        style.configure(nom + ".TButton", background=fond, foreground=texte, bordercolor=fond,
                        lightcolor=fond, darkcolor=fond, font=(POLICE, 11 if nom != "Entete" else 10, "bold"),
                        padding=(20, 9) if nom in ("Primaire", "Stop") else (14, 7))
        style.map(nom + ".TButton", background=[("disabled", "#8AA4B8"), ("pressed", survol), ("active", survol)],
                  foreground=[("disabled", ECUME)], bordercolor=[("active", survol)],
                  lightcolor=[("active", survol)], darkcolor=[("active", survol)])
    style.configure("Grand.TButton", font=(POLICE, 11, "bold"), padding=(18, 8))
    style.configure("Treeview", background=BLANC, fieldbackground=BLANC, foreground=MARINE,
                    rowheight=int(30 * echelle), bordercolor=BORDURE, lightcolor=BORDURE, darkcolor=BORDURE)
    style.map("Treeview", background=[("selected", "#D7EEF5")], foreground=[("selected", MARINE)])
    style.configure("Treeview.Heading", background="#DCEFF5", foreground=MARINE, font=(POLICE, 10, "bold"),
                    relief="flat", bordercolor=BORDURE, lightcolor="#DCEFF5", darkcolor="#DCEFF5", padding=(6, 5))
    style.map("Treeview.Heading", background=[("active", BORDURE)])
    style.configure("TCheckbutton", background=ECUME, foreground=MARINE, font=(POLICE, 10, "bold"),
                    indicatorbackground=BLANC, indicatorforeground=BLANC, indicatormargin=(0, 0, 6, 0))
    style.map("TCheckbutton", background=[("active", ECUME)],
              indicatorbackground=[("selected", OCEAN), ("active", "#DCEFF5")])
    style.configure("TScrollbar", background=BORDURE, troughcolor=ECUME, bordercolor=ECUME,
                    lightcolor=BORDURE, darkcolor=BORDURE, arrowcolor=MARINE)
    style.map("TScrollbar", background=[("active", "#B5D7E3")])
    style.configure("TLabelframe", background=ECUME, bordercolor=BORDURE)
    style.configure("TLabelframe.Label", background=ECUME, foreground=MARINE, font=forte(10))
    style.configure("TEntry", fieldbackground=BLANC, bordercolor=BORDURE, lightcolor=BLANC, padding=4)
    style.map("TEntry", bordercolor=[("focus", OCEAN)], lightcolor=[("focus", OCEAN)])
    style.configure("TCombobox", fieldbackground=BLANC, background=BLANC, bordercolor=BORDURE,
                    arrowcolor=MARINE, padding=4)
    style.map("TCombobox", fieldbackground=[("readonly", BLANC)], bordercolor=[("focus", OCEAN)],
              selectbackground=[("readonly", BLANC)], selectforeground=[("readonly", MARINE)])
    root.option_add("*TCombobox*Listbox.background", BLANC)
    root.option_add("*TCombobox*Listbox.selectBackground", BORDURE)
    root.option_add("*TCombobox*Listbox.selectForeground", MARINE)
    root.option_add("*TCombobox*Listbox.font", (POLICE, 10))

    images = {}

    def image(nom, hauteur):
        """Image de windows/images, à la hauteur voulue (en pixels écran)."""
        cle = (nom, hauteur)
        if cle not in images:
            chemin = os.path.join(ICI, "images", nom + ".png")
            try:
                from PIL import Image, ImageTk
                im = Image.open(chemin).convert("RGBA")
                im = im.resize((max(1, round(im.width * hauteur / im.height)), hauteur), Image.LANCZOS)
                images[cle] = ImageTk.PhotoImage(im, master=root)
            except Exception:
                try:
                    im = tk.PhotoImage(file=chemin, master=root)
                    images[cle] = im.subsample(max(1, im.height() // hauteur))
                except Exception:
                    images[cle] = None
        return images[cle]

    # ------------------------------------------------------------------
    class FenetreReglages(tk.Toplevel):
        def __init__(self, app):
            super().__init__(app.root)
            self.app = app
            cfg = app.cfg
            self.title("Réglages — Rekindle")
            self.configure(background=ECUME)
            self.transient(app.root)
            self.resizable(False, False)
            self.v = {
                "kindle": tk.StringVar(value=cfg.get("kindle", "")),
                "fournisseur": tk.StringVar(value=cfg.get("fournisseur", "Gmail")),
                "expediteur": tk.StringVar(value=cfg.get("expediteur", "")),
                "mdp": tk.StringVar(value=cfg.mot_de_passe()),
                "serveur": tk.StringVar(value=cfg.get("serveur", "")),
                "port": tk.StringVar(value=str(cfg.get("port", 465))),
                "securite": tk.StringVar(value=cfg.get("securite", "SSL")),
                "identifiant": tk.StringVar(value=cfg.get("identifiant", "")),
                "dossier_sortie": tk.StringVar(value=cfg.get("dossier_sortie", "")),
                "langue": tk.StringVar(value=cfg.get("langue", "fr")),
            }
            f = ttk.Frame(self, padding=18)
            f.pack(fill="both", expand=True)
            f.columnconfigure(1, weight=1)
            f.columnconfigure(0, minsize=140)
            r = 0

            ttk.Label(f, text="Ta Kindle", style="Section.TLabel").grid(row=r, column=0, columnspan=3,
                                                                       sticky="w")
            r += 1
            ttk.Label(f, text="Adresse Kindle").grid(row=r, column=0, sticky="w", pady=4)
            ttk.Entry(f, textvariable=self.v["kindle"], width=42).grid(row=r, column=1, columnspan=2,
                                                                      sticky="we", pady=4)
            r += 1
            ttk.Label(f, style="Aide.TLabel", wraplength=470, justify="left",
                      text="Tu la trouves sur amazon.fr → Gérer votre contenu et vos appareils → "
                           "Préférences → Paramètres des documents personnels. Sur la même page, "
                           "ajoute l'adresse d'envoi ci-dessous à la « liste des adresses e-mail "
                           "approuvées », sinon Amazon ignore les livres.").grid(
                row=r, column=0, columnspan=3, sticky="w")
            r += 1
            ttk.Button(f, text="Ouvrir la page Amazon",
                       command=lambda: webbrowser.open(km.PAGE_AMAZON)).grid(row=r, column=0, columnspan=3,
                                                                              sticky="w", pady=(4, 12))
            r += 1

            ttk.Label(f, text="La messagerie qui envoie", style="Section.TLabel").grid(
                row=r, column=0, columnspan=3, sticky="w")
            r += 1
            ttk.Label(f, text="Messagerie").grid(row=r, column=0, sticky="w", pady=4)
            cb = ttk.Combobox(f, textvariable=self.v["fournisseur"], values=list(km.FOURNISSEURS),
                              state="readonly", width=22)
            cb.grid(row=r, column=1, sticky="w", pady=4)
            cb.bind("<<ComboboxSelected>>", lambda e: self.fournisseur_change(True))
            r += 1
            ttk.Label(f, text="Adresse e-mail").grid(row=r, column=0, sticky="w", pady=4)
            ttk.Entry(f, textvariable=self.v["expediteur"], width=42).grid(row=r, column=1, columnspan=2,
                                                                          sticky="we", pady=4)
            r += 1
            ttk.Label(f, text="Mot de passe").grid(row=r, column=0, sticky="w", pady=4)
            self.champ_mdp = ttk.Entry(f, textvariable=self.v["mdp"], show="•", width=30)
            self.champ_mdp.grid(row=r, column=1, sticky="we", pady=4)
            self.voir = tk.BooleanVar(value=False)
            ttk.Checkbutton(f, text="Afficher", variable=self.voir,
                            command=lambda: self.champ_mdp.configure(show="" if self.voir.get() else "•")
                            ).grid(row=r, column=2, sticky="w", padx=(8, 0))
            r += 1
            self.aide = ttk.Label(f, style="Aide.TLabel", wraplength=470, justify="left")
            self.aide.grid(row=r, column=0, columnspan=3, sticky="w")
            r += 1
            self.bouton_lien = ttk.Button(f, text="Créer le mot de passe d'application")
            self.bouton_lien.grid(row=r, column=0, columnspan=3, sticky="w", pady=(4, 0))
            r += 1

            self.avance = ttk.Frame(f)
            self.avance.columnconfigure(1, weight=1)
            self.avance.columnconfigure(0, minsize=140)
            self.bouton_avance = ttk.Button(f, text="Réglages avancés ▸", command=self.basculer_avance)
            self.bouton_avance.grid(row=r, column=0, columnspan=3, sticky="w", pady=(10, 0))
            r += 1
            self.ligne_avance = r
            a = self.avance
            ttk.Label(a, text="Serveur SMTP").grid(row=0, column=0, sticky="w", pady=3)
            ttk.Entry(a, textvariable=self.v["serveur"], width=30).grid(row=0, column=1, sticky="we", pady=3)
            ttk.Label(a, text="Port").grid(row=1, column=0, sticky="w", pady=3)
            ttk.Entry(a, textvariable=self.v["port"], width=8).grid(row=1, column=1, sticky="w", pady=3)
            ttk.Label(a, text="Sécurité").grid(row=2, column=0, sticky="w", pady=3)
            ttk.Combobox(a, textvariable=self.v["securite"], values=["SSL", "STARTTLS"], state="readonly",
                         width=10).grid(row=2, column=1, sticky="w", pady=3)
            ttk.Label(a, text="Identifiant").grid(row=3, column=0, sticky="w", pady=3)
            ttk.Entry(a, textvariable=self.v["identifiant"], width=30).grid(row=3, column=1, sticky="we", pady=3)
            ttk.Label(a, text="(vide = l'adresse e-mail)", style="Aide.TLabel").grid(row=4, column=1, sticky="w")
            ttk.Label(a, text="Langue par défaut").grid(row=5, column=0, sticky="w", pady=3)
            ttk.Entry(a, textvariable=self.v["langue"], width=8).grid(row=5, column=1, sticky="w", pady=3)
            ttk.Label(a, text="(utilisée si un livre n'en indique aucune)", style="Aide.TLabel").grid(
                row=6, column=1, sticky="w")
            r += 1

            ttk.Label(f, text="Livres réparés", style="Section.TLabel").grid(row=r, column=0, columnspan=3,
                                                                            sticky="w", pady=(12, 0))
            r += 1
            ttk.Label(f, text="Dossier").grid(row=r, column=0, sticky="w", pady=4)
            ttk.Entry(f, textvariable=self.v["dossier_sortie"], width=34).grid(row=r, column=1, sticky="we", pady=4)
            ttk.Button(f, text="Parcourir…", command=self.choisir_dossier).grid(row=r, column=2, sticky="w",
                                                                               padx=(8, 0))
            r += 1

            b = ttk.Frame(f)
            b.grid(row=r, column=0, columnspan=3, sticky="we", pady=(18, 0))
            self.bouton_test = ttk.Button(b, text="Tester la connexion", command=self.tester)
            self.bouton_test.pack(side="left")
            ttk.Button(b, text="Enregistrer", style="Primaire.TButton", command=self.enregistrer).pack(side="right")
            ttk.Button(b, text="Annuler", command=self.destroy).pack(side="right", padx=8)

            self.fournisseur_change(False)
            self.bind("<Escape>", lambda e: self.destroy())
            self.grab_set()
            self.update_idletasks()
            x = app.root.winfo_rootx() + (app.root.winfo_width() - self.winfo_width()) // 2
            y = app.root.winfo_rooty() + 30
            self.geometry("+%d+%d" % (max(x, 0), max(y, 0)))

        def basculer_avance(self):
            if self.avance.winfo_ismapped():
                self.avance.grid_forget()
                self.bouton_avance.configure(text="Réglages avancés ▸")
            else:
                self.avance.grid(row=self.ligne_avance, column=0, columnspan=3, sticky="we", pady=(6, 0))
                self.bouton_avance.configure(text="Réglages avancés ▾")

        def fournisseur_change(self, appliquer):
            p = km.FOURNISSEURS.get(self.v["fournisseur"].get(), km.FOURNISSEURS["Autre"])
            if appliquer and self.v["fournisseur"].get() != "Autre":
                self.v["serveur"].set(p["serveur"])
                self.v["port"].set(str(p["port"]))
                self.v["securite"].set(p["securite"])
            if appliquer and self.v["fournisseur"].get() == "Autre" and not self.avance.winfo_ismapped():
                self.basculer_avance()
            self.aide.configure(text=p["aide"],
                                foreground=ROUGE if p["aide"].startswith("⚠") else GRIS)
            if p.get("lien"):
                self.bouton_lien.configure(command=lambda: webbrowser.open(p["lien"]))
                self.bouton_lien.grid()
            else:
                self.bouton_lien.grid_remove()

        def choisir_dossier(self):
            d = filedialog.askdirectory(parent=self, initialdir=self.v["dossier_sortie"].get() or None)
            if d:
                self.v["dossier_sortie"].set(d)

        def cfg_temporaire(self):
            c = km.Reglages()
            c.update({k: v.get().strip() for k, v in self.v.items() if k != "mdp"})
            try:
                c["port"] = int(c["port"])
            except ValueError:
                c["port"] = 465
            return c

        def tester(self):
            c = self.cfg_temporaire()
            mdp = self.v["mdp"].get()
            self.bouton_test.configure(state="disabled", text="Connexion…")

            def fil():
                try:
                    km.tester(c, mdp)
                    msg = (True, "Connexion réussie : Rekindle peut envoyer depuis %s." % c["expediteur"])
                except km.ErreurEnvoi as exc:
                    msg = (False, str(exc))
                except Exception as exc:
                    msg = (False, "Erreur : %s" % exc)
                self.after(0, lambda: self.fin_test(*msg))
            threading.Thread(target=fil, daemon=True).start()

        def fin_test(self, ok, msg):
            if not self.winfo_exists():
                return
            self.bouton_test.configure(state="normal", text="Tester la connexion")
            (messagebox.showinfo if ok else messagebox.showerror)("Test de connexion", msg, parent=self)

        def enregistrer(self):
            k = self.v["kindle"].get().strip()
            if k and not (k.lower().endswith("@kindle.com") or k.lower().endswith("@free.kindle.com")):
                if not messagebox.askyesno("Adresse Kindle",
                                           "Une adresse Kindle finit normalement par @kindle.com.\n"
                                           "Enregistrer quand même ?", parent=self):
                    return
            c = self.app.cfg
            for cle, var in self.v.items():
                if cle != "mdp":
                    c[cle] = var.get().strip()
            try:
                c["port"] = int(c["port"])
            except ValueError:
                c["port"] = 465
            if self.v["mdp"].get():
                c.definir_mot_de_passe(self.v["mdp"].get())
            c.enregistrer()
            self.app.maj_barre()
            self.destroy()

    # ------------------------------------------------------------------
    class Application:
        def __init__(self, root):
            self.root = root
            self.cfg = km.Reglages()
            self.q = queue.Queue()
            self.livres = {}
            self.en_cours = False
            self.arret = threading.Event()
            self.bloque = None
            root.title("Rekindle — tes livres vers ta Kindle")
            root.geometry("920x680")
            root.minsize(720, 520)
            icone = os.path.join(ICI, "icone.png")
            if os.path.exists(icone):
                try:
                    self.img_icone = tk.PhotoImage(file=icone)
                    root.iconphoto(True, self.img_icone)
                except Exception:
                    pass
            if sys.platform.startswith("win") and os.path.exists(os.path.join(ICI, "icone.ico")):
                try:
                    root.iconbitmap(default=os.path.join(ICI, "icone.ico"))
                except Exception:
                    pass

            self.entete = tk.Canvas(root, height=int(118 * echelle), background=MARINE, highlightthickness=0,
                                    borderwidth=0)
            self.entete.pack(fill="x")
            self.b_reglages = ttk.Button(self.entete, text="Réglages", style="Entete.TButton",
                                         command=self.ouvrir_reglages)
            self.entete.bind("<Configure>", lambda e: self.dessiner_entete())

            principal = ttk.Frame(root, padding=(18, 4, 18, 10))
            principal.pack(fill="both", expand=True)

            bas = ttk.Frame(principal)
            bas.pack(side="bottom", fill="x", pady=(6, 0))
            self.etat = ttk.Label(bas, style="Aide.TLabel")
            self.etat.pack(side="left")
            ttk.Button(bas, text="Ouvrir le dossier des livres", command=self.ouvrir_sortie).pack(side="right")

            cadre = ttk.Frame(principal)
            cadre.pack(fill="both", expand=True, pady=(6, 10))
            self.arbre = ttk.Treeview(cadre, columns=("livre", "format", "etat"), show="headings",
                                      selectmode="extended", height=8)
            self.arbre.heading("livre", text="Livre", anchor="w")
            self.arbre.heading("format", text="Format", anchor="w")
            self.arbre.heading("etat", text="État", anchor="w")
            self.arbre.column("livre", width=460, stretch=True)
            self.arbre.column("format", width=110, stretch=False)
            self.arbre.column("etat", width=200, stretch=False)
            self.arbre.tag_configure("ok", foreground=VERT)
            self.arbre.tag_configure("ko", foreground=ROUGE)
            self.arbre.tag_configure("encours", foreground=BLEU)
            sb = ttk.Scrollbar(cadre, orient="vertical", command=self.arbre.yview)
            self.arbre.configure(yscrollcommand=sb.set)
            self.arbre.pack(side="left", fill="both", expand=True)
            sb.pack(side="right", fill="y")
            self.arbre.bind("<Double-1>", self.double_clic)
            self.arbre.bind("<Delete>", lambda e: self.retirer())
            self.vide = tk.Label(self.arbre, justify="center", background=BLANC, foreground=GRIS,
                                 font=(POLICE, 11), image=image("mascotte", int(150 * echelle)), compound="top",
                                 text=("\nGlisse tes livres ou tes fichiers .torrent ici\n"
                                       "ou clique sur « + Ajouter des livres… »"
                                       if TkinterDnD else "\nClique sur « + Ajouter des livres… »"))
            self.vide.place(relx=0.5, rely=0.55, anchor="center")
            if TkinterDnD:
                for w in (self.arbre, self.vide):
                    w.drop_target_register(DND_FILES)
                    w.dnd_bind("<<Drop>>", self.deposer)

            barre = ttk.Frame(principal)
            barre.pack(fill="x")
            self.b_ajout = ttk.Button(barre, text="+  Ajouter des livres…", style="Corail.TButton",
                                      command=self.ajouter_dialogue)
            self.b_ajout.pack(side="left")
            self.b_retirer = ttk.Button(barre, text="Retirer", command=self.retirer)
            self.b_retirer.pack(side="left", padx=(8, 0))
            self.b_vider = ttk.Button(barre, text="Vider la liste", command=self.vider)
            self.b_vider.pack(side="left", padx=(8, 0))
            self.var_envoyer = tk.BooleanVar(value=bool(self.cfg.get("envoyer", True)))
            self.b_go = ttk.Button(barre, style="Primaire.TButton", command=self.lancer)
            self.b_go.pack(side="right")
            ttk.Checkbutton(barre, text="Envoyer à ma Kindle", variable=self.var_envoyer,
                            command=self.envoi_change).pack(side="right", padx=(0, 14))
            self.envoi_change(sauver=False)

            jcadre = ttk.LabelFrame(principal, text=" Détails ", padding=(8, 6))
            jcadre.pack(fill="both", expand=True, pady=(12, 0))
            self.journal = tk.Text(jcadre, height=11, wrap="word", relief="flat", borderwidth=0,
                                   font=(POLICE, 10), background=BLANC, foreground=MARINE,
                                   selectbackground=BORDURE, selectforeground=MARINE, highlightthickness=0,
                                   padx=6, pady=4, state="disabled", cursor="arrow")
            js = ttk.Scrollbar(jcadre, orient="vertical", command=self.journal.yview)
            self.journal.configure(yscrollcommand=js.set)
            self.journal.pack(side="left", fill="both", expand=True)
            js.pack(side="right", fill="y")
            self.journal.tag_configure("titre", font=forte(10), spacing1=6)
            self.journal.tag_configure("corrige", foreground=VERT, lmargin1=14, lmargin2=30)
            self.journal.tag_configure("alerte", foreground=ORANGE, lmargin1=14, lmargin2=30)
            self.journal.tag_configure("erreur", foreground=ROUGE, lmargin1=14, lmargin2=30)
            self.journal.tag_configure("info", foreground=BLEU, lmargin1=14, lmargin2=30)
            self.journal.tag_configure("neutre", foreground=GRIS, lmargin1=14, lmargin2=30)
            self.journal.tag_configure("envoi", foreground=VERT, font=(POLICE, 10, "bold"), lmargin1=14)

            self.maj_barre()

            if not self.cfg.get("kindle"):
                self.ecrire("Bienvenue !", "titre")
                self.ecrire("Commence par « Réglages » (en haut à droite) pour indiquer ton adresse Kindle et la "
                            "messagerie qui enverra les livres. Ensuite, ajoute un livre et clique sur "
                            "« Réparer et envoyer ».", "neutre")
            root.after(100, self.pomper)

        # -------------------------------------------------------- en-tête
        def dessiner_entete(self):
            c = self.entete
            c.delete("all")
            l, h = c.winfo_width(), c.winfo_height()
            e = echelle
            x = int(22 * e)
            tete = image("tete", int(54 * e))
            if tete is not None:
                c.create_image(x, int(16 * e), image=tete, anchor="nw")
                x += tete.width() + int(14 * e)
            y = int(16 * e)
            police_titre = (POLICE_TITRE, 26) if POLICE_TITRE else forte(24)
            t1 = c.create_text(x, y, text="Rekin", fill=CORAIL, font=police_titre, anchor="nw")
            x2 = c.bbox(t1)[2]
            c.create_text(x2, y, text="dle", fill=CREME, font=police_titre, anchor="nw")
            y2 = c.bbox(t1)[3] + int(2 * e)
            c.create_text(x, y2, text="Répare tes livres et les envoie à ta Kindle  ·  EPUB, MOBI, PDF, torrents",
                          fill=BRUME, font=(POLICE, 10), anchor="nw")
            c.create_window(l - int(20 * e), int(18 * e), window=self.b_reglages, anchor="ne")
            aileron = image("aileron", int(30 * e))
            if aileron is not None:
                c.create_image(l - int(70 * e), h - int(9 * e), image=aileron, anchor="se")
            # vagues
            periode, amp, base = 48 * e, 6 * e, h - 9 * e
            pts = [-20, h + 40, -20, base]      # points hors champ : le lissage ne mord pas sur le bas
            xx = 0.0
            haut = True
            while xx <= l + periode:
                pts += [xx, base, xx + periode / 4, base - amp if haut else base + amp]
                xx += periode / 2
                haut = not haut
            pts += [xx, base, xx + 20, h + 40]
            c.create_polygon(pts, fill=ECUME, outline="", smooth=True)

        # ---------------------------------------------------------- liste
        def ajouter(self, chemins):
            deja = {l["chemin"] for l in self.livres.values()}
            n = 0
            for c in chemins:
                c = os.path.abspath(c)
                if os.path.isdir(c):
                    for racine, _, fs in os.walk(c):
                        self.ajouter([os.path.join(racine, x) for x in fs if x.lower().endswith(EXTENSIONS)])
                    continue
                if c in deja or not os.path.isfile(c):
                    continue
                if c.lower().endswith(".torrent"):
                    try:
                        info = kt.lire(c)
                        nom = "%s  (%d livre%s)" % (info["nom"], len(info["livres"]),
                                                    "s" if len(info["livres"]) > 1 else "")
                    except kt.ErreurTorrent:
                        nom = os.path.basename(c)
                    iid = self.arbre.insert("", "end", values=(nom, "Torrent", "En attente"), open=True)
                    self.livres[iid] = {"chemin": c, "etat": "attente", "res": None, "type": "torrent",
                                        "nom": nom}
                else:
                    iid = self.arbre.insert("", "end", values=(os.path.basename(c), "", "En attente"))
                    self.livres[iid] = {"chemin": c, "etat": "attente", "res": None, "type": "livre"}
                n += 1
            self.maj_vide()
            return n

        def ajouter_dialogue(self):
            chemins = filedialog.askopenfilenames(
                parent=self.root, title="Choisis des livres ou des fichiers .torrent",
                filetypes=[("Livres et torrents", "*.epub *.mobi *.azw *.azw3 *.prc *.pdf *.torrent"),
                           ("Torrents", "*.torrent"), ("Tous les fichiers", "*.*")])
            if chemins:
                self.ajouter(chemins)

        def deposer(self, event):
            self.ajouter(self.root.tk.splitlist(event.data))

        def oublier(self, iid):
            for enfant in self.arbre.get_children(iid):
                self.livres.pop(enfant, None)
            self.livres.pop(iid, None)
            if self.arbre.exists(iid):
                self.arbre.delete(iid)

        def retirer(self):
            if self.en_cours:
                return
            for iid in self.arbre.selection():
                self.oublier(iid)
            self.maj_vide()

        def vider(self):
            if self.en_cours:
                return
            for iid in self.arbre.get_children(""):
                self.oublier(iid)
            self.livres.clear()
            self.maj_vide()

        def maj_vide(self):
            if self.livres:
                self.vide.place_forget()
            else:
                self.vide.place(relx=0.5, rely=0.55, anchor="center")

        def double_clic(self, event):
            iid = self.arbre.identify_row(event.y)
            l = self.livres.get(iid)
            if not l:
                return
            if l["type"] == "torrent":
                if l.get("recus"):
                    ouvrir(l["recus"][0], selectionner=True)
            elif l["res"] is not None:
                self.afficher_rapport(l["res"])
                if l["res"].sortie:
                    ouvrir(l["res"].sortie, selectionner=True)

        # ------------------------------------------------------ journal
        def ecrire(self, texte, tag="neutre"):
            self.journal.configure(state="normal")
            self.journal.insert("end", texte + "\n", tag)
            self.journal.configure(state="disabled")
            self.journal.see("end")

        def afficher_rapport(self, res):
            nom = res.titre or os.path.basename(res.source)
            self.ecrire("▸ " + nom + ("  —  " + res.auteur if res.auteur else ""), "titre")
            for niv, msg in res.rapport.lignes():
                self.ecrire("%s  %s" % (SYMBOLES[niv], msg), niv)
            if res.ok and res.sortie and res.sortie != res.source:
                self.ecrire("→  Enregistré : %s (%.1f Mo)" % (res.sortie, res.taille / 1048576), "neutre")

        # ------------------------------------------------------- barre
        def maj_barre(self):
            k = self.cfg.get("kindle")
            if k:
                self.etat.configure(text="Envoi vers %s  ·  depuis %s" % (k, self.cfg.get("expediteur") or "?"),
                                    foreground=GRIS)
            else:
                self.etat.configure(text="Adresse Kindle pas encore réglée : clique sur « Réglages ».",
                                    foreground=ORANGE)

        def envoi_change(self, sauver=True):
            if not self.en_cours:
                self.b_go.configure(text="Réparer et envoyer" if self.var_envoyer.get() else "Réparer")
            if sauver:
                self.cfg["envoyer"] = bool(self.var_envoyer.get())
                self.cfg.enregistrer()

        def ouvrir_sortie(self):
            d = self.cfg["dossier_sortie"]
            os.makedirs(d, exist_ok=True)
            ouvrir(d)

        def ouvrir_reglages(self):
            fen = FenetreReglages(self)
            self.root.wait_window(fen)

        # ------------------------------------------------------ travail
        def lancer(self):
            if self.en_cours:                 # le bouton sert alors à arrêter
                self.arret.set()
                self.b_go.configure(text="Arrêt en cours…", state="disabled")
                return
            envoyer = bool(self.var_envoyer.get())
            etats = {"attente", "erreur", "echec_envoi"} | ({"pret"} if envoyer else set())
            a_faire = [i for i, l in self.livres.items() if l["etat"] in etats]
            a_faire.sort(key=lambda i: self.position(i))
            if not a_faire:
                if not self.livres:
                    self.ajouter_dialogue()
                else:
                    messagebox.showinfo("Rekindle", "Tous les livres de la liste sont déjà traités.",
                                        parent=self.root)
                return
            if envoyer and self.cfg.probleme():
                messagebox.showwarning("Réglages incomplets", self.cfg.probleme(), parent=self.root)
                self.ouvrir_reglages()
                if self.cfg.probleme():
                    return
            self.en_cours = True
            self.arret = threading.Event()
            for b in (self.b_ajout, self.b_retirer, self.b_vider):
                b.configure(state="disabled")
            self.b_go.configure(text="Arrêter", style="Stop.TButton")
            threading.Thread(target=self.travail, args=(a_faire, envoyer), daemon=True).start()

        def position(self, iid):
            parent = self.arbre.parent(iid)
            if parent:
                return (self.arbre.index(parent), self.arbre.index(iid) + 1)
            return (self.arbre.index(iid), 0)

        def travail(self, iids, envoyer):
            self.bloque = None
            self.nb_mails = 0
            self.sorties_prises = set()
            a_envoyer = []
            file = list(iids)
            while file:
                if self.arret.is_set():
                    break
                iid = file.pop(0)
                l = self.livres.get(iid)
                if l is None:
                    continue
                try:
                    if l["type"] == "torrent":
                        file[0:0] = self.travail_torrent(iid, l)
                    else:
                        self.travail_livre(iid, l)
                        if l["etat"] in ("pret", "echec_envoi"):
                            a_envoyer.append(iid)
                except Exception as exc:  # filet de sécurité : on passe au suivant
                    l["etat"] = "erreur"
                    self.q.put(("etat", iid, "✗ Impossible", "ko", None))
                    self.q.put(("log", "✗  Erreur inattendue : %s" % exc, "erreur"))
            if envoyer and a_envoyer and not self.arret.is_set():
                self.envoyer_groupes(a_envoyer)
            self.q.put(("fin", envoyer, self.bloque, self.arret.is_set(), self.nb_mails))

        def envoyer_groupes(self, iids):
            """Un seul e-mail pour plusieurs livres : Amazon ne demande alors qu'une vérification."""
            livres = []
            for iid in iids:
                res = self.livres[iid]["res"]
                livres.append({"iid": iid, "chemin": res.sortie, "titre": res.titre, "auteur": res.auteur})
            lots, trop_gros = km.faire_lots(livres, self.cfg)
            for e in trop_gros:
                self.livres[e["iid"]]["etat"] = "echec_envoi"
                self.q.put(("etat", e["iid"], "✗ Trop gros", "ko", None))
                self.q.put(("log", "✗  « %s » : %s" % (e["titre"], km.message_trop_gros(self.cfg, e["chemin"])),
                            "erreur"))
            for lot in lots:
                if self.arret.is_set():
                    break
                if self.bloque:
                    for e in lot:
                        self.livres[e["iid"]]["etat"] = "echec_envoi"
                        self.q.put(("etat", e["iid"], "✗ Pas envoyé", "ko", None))
                    continue
                for e in lot:
                    self.q.put(("etat", e["iid"], "Envoi…", "encours", None))
                titres = ", ".join("« %s »" % e["titre"] for e in lot)
                try:
                    km.envoyer_lot(self.cfg, [(e["chemin"], e["titre"], e["auteur"]) for e in lot])
                    self.nb_mails += 1
                    for e in lot:
                        self.livres[e["iid"]]["etat"] = "envoye"
                        self.q.put(("etat", e["iid"], "✓ Envoyé", "ok", None))
                    if len(lot) == 1:
                        self.q.put(("log", "✉  %s envoyé à %s" % (titres, self.cfg["kindle"]), "envoi"))
                    else:
                        self.q.put(("log", "✉  %d livres envoyés en un seul e-mail à %s : %s"
                                    % (len(lot), self.cfg["kindle"], titres), "envoi"))
                except Exception as exc:
                    for e in lot:
                        self.livres[e["iid"]]["etat"] = "echec_envoi"
                        self.q.put(("etat", e["iid"], "✗ Envoi raté", "ko", None))
                    self.q.put(("log", "✗  Envoi de %s : %s" % (titres, exc), "erreur"))
                    if getattr(exc, "bloquant", False):
                        self.bloque = exc

        def travail_torrent(self, iid, l):
            if not kt.disponible():
                l["etat"] = "erreur"
                self.q.put(("etat", iid, "✗ Impossible", "ko", "Torrent"))
                self.q.put(("log", "▸ " + l["nom"], "titre"))
                self.q.put(("log", "✗  " + kt.raison_indisponible(), "erreur"))
                return []
            self.q.put(("etat", iid, "Recherche de sources…", "encours", "Torrent"))
            dernier = [0.0]

            def prog(frac, pairs, debit, verif):
                maintenant = time.time()
                if maintenant - dernier[0] < 0.4:
                    return
                dernier[0] = maintenant
                if verif:
                    txt = "Vérification…"
                elif pairs == 0 and frac == 0:
                    txt = "Recherche de sources…"
                else:
                    txt = "⇣ %d %%  ·  %d source%s" % (frac * 100, pairs, "s" if pairs > 1 else "")
                self.q.put(("etat", iid, txt, "encours", "Torrent"))
            try:
                recus = kt.Telechargeur.get().telecharger(l["chemin"], dossier_torrents(self.cfg), prog,
                                                          self.arret)
            except kt.ErreurTorrent as exc:
                l["etat"] = "erreur"
                arrete = self.arret.is_set()
                self.q.put(("etat", iid, "■ Arrêté" if arrete else "✗ Échec", "ko", "Torrent"))
                if not arrete:
                    self.q.put(("log", "▸ " + l["nom"], "titre"))
                    self.q.put(("log", "✗  Torrent : %s" % exc, "erreur"))
                return []
            l["etat"] = "telecharge"
            l["recus"] = recus
            self.q.put(("etat", iid, "✓ %d livre%s récupéré%s" % (len(recus), "s" if len(recus) > 1 else "",
                                                                    "s" if len(recus) > 1 else ""), "ok", "Torrent"))
            self.q.put(("log", "▸ " + l["nom"], "titre"))
            self.q.put(("log", "⇣  Téléchargé dans %s — le torrent reste partagé tant que Rekindle est ouvert."
                        % os.path.dirname(recus[0]), "info"))
            nouveaux = []
            for n, chemin in enumerate(recus):
                niid = "%s_%d" % (iid, n)
                self.livres[niid] = {"chemin": chemin, "etat": "attente", "res": None, "type": "livre",
                                     "parent": iid}
                self.q.put(("ajout", niid, iid, os.path.basename(chemin)))
                nouveaux.append(niid)
            return nouveaux

        def travail_livre(self, iid, l):
            if l["etat"] not in ("attente", "erreur"):
                return
            self.q.put(("etat", iid, "Réparation…", "encours", None))
            res = traiter_livre(l["chemin"], self.cfg["dossier_sortie"],
                                {"langue": self.cfg.get("langue") or "fr", "sorties_prises": self.sorties_prises})
            l["res"] = res
            self.q.put(("rapport", res))
            fmt = FORMATS.get(res.format_source, "?")
            if not res.ok:
                l["etat"] = "erreur"
                self.q.put(("etat", iid, "✗ Impossible", "ko", fmt))
                return
            l["etat"] = "pret"
            self.q.put(("etat", iid, "✓ Réparé", "ok", fmt))

        def pomper(self):
            try:
                while True:
                    m = self.q.get_nowait()
                    if m[0] == "etat":
                        _, iid, txt, tag, fmt = m
                        if self.arbre.exists(iid) and iid in self.livres:
                            l = self.livres[iid]
                            vals = list(self.arbre.item(iid, "values"))
                            vals[2] = txt
                            if fmt:
                                vals[1] = fmt
                            res = l["res"]
                            if res is not None and res.titre:
                                vals[0] = ("      ↳  " if l.get("parent") else "") + res.titre + \
                                    ("  —  " + res.auteur if res.auteur else "")
                            self.arbre.item(iid, values=vals, tags=(tag,))
                    elif m[0] == "ajout":
                        _, niid, parent, nom = m
                        if self.arbre.exists(parent):
                            self.arbre.insert(parent, "end", iid=niid,
                                              values=("      ↳  " + nom, "", "En attente"))
                            self.arbre.item(parent, open=True)
                    elif m[0] == "rapport":
                        self.afficher_rapport(m[1])
                    elif m[0] == "log":
                        self.ecrire(m[1], m[2])
                    elif m[0] == "fin":
                        self.en_cours = False
                        for b in (self.b_go, self.b_ajout, self.b_retirer, self.b_vider):
                            b.configure(state="normal")
                        self.b_go.configure(style="Primaire.TButton")
                        self.envoi_change(sauver=False)
                        _, envoyer, bloque, arrete, nb_mails = m
                        if arrete:
                            self.ecrire("■  Arrêté. Clique à nouveau sur le bouton pour reprendre.", "neutre")
                        elif envoyer and nb_mails == 1:
                            self.ecrire("Envoyé en un seul e-mail. Si Amazon t'envoie un mail « Vérifiez votre "
                                        "demande », clique sur le lien : sans ça, les livres n'arrivent pas. "
                                        "Ensuite, ils arrivent sur ta Kindle en quelques minutes (Wi-Fi activé).",
                                        "neutre")
                        elif envoyer and nb_mails > 1:
                            self.ecrire("Envoyé en %d e-mails. Amazon peut demander une vérification pour "
                                        "CHACUN : Gmail range ces mails « Vérifiez votre demande » dans une seule "
                                        "conversation, ouvre-les tous et clique sur chaque lien." % nb_mails,
                                        "neutre")
                        if bloque:
                            messagebox.showerror("Envoi impossible", str(bloque), parent=self.root)
            except queue.Empty:
                pass
            self.root.after(120, self.pomper)

    Application(root)
    root.mainloop()


def main():
    p = argparse.ArgumentParser(prog="rekindle", description="Répare des livres pour Send to Kindle et les envoie.")
    p.add_argument("livres", nargs="*", help="fichiers EPUB / MOBI / AZW3 / PDF")
    p.add_argument("--envoyer", action="store_true", help="envoyer à la Kindle (réglages de l'interface)")
    p.add_argument("--verifier", action="store_true", help="diagnostic seulement, sans garder de fichier")
    p.add_argument("--sortie", help="dossier où enregistrer les livres réparés")
    args = p.parse_args()
    if args.livres:
        sys.exit(ligne_de_commande(args))
    interface()


if __name__ == "__main__":
    main()
