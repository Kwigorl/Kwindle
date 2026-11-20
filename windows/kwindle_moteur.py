# -*- coding: utf-8 -*-
"""
Kwindle — moteur de réparation / conversion.

Prend un livre (EPUB, ou MOBI/AZW3 même renommé en .epub), corrige tout ce qui
fait refuser un fichier par Send to Kindle, et produit un EPUB propre.
Ne touche pas aux livres protégés par DRM.
"""

import codecs
import contextlib
import datetime
import hashlib
import html as html_mod
import io
import os
import posixpath
import re
import shutil
import struct
import unicodedata
import uuid
import zipfile
from collections import OrderedDict
from urllib.parse import unquote, urlsplit

from lxml import etree
from lxml import html as lhtml

try:
    from PIL import Image
except ImportError:  # Pillow est facultatif
    Image = None

# --------------------------------------------------------------------------
# Constantes
# --------------------------------------------------------------------------

OPF = "http://www.idpf.org/2007/opf"
DC = "http://purl.org/dc/elements/1.1/"
XHTML = "http://www.w3.org/1999/xhtml"
NCX = "http://www.daisy.org/z3986/2005/ncx/"
EPUB = "http://www.idpf.org/2007/ops"
SVG = "http://www.w3.org/2000/svg"
XLINK = "http://www.w3.org/1999/xlink"
MATHML = "http://www.w3.org/1998/Math/MathML"
XMLNS = "http://www.w3.org/XML/1998/namespace"
CONTAINER = "urn:oasis:names:tc:opendocument:xmlns:container"
ENC = "http://www.w3.org/2001/04/xmlenc#"

LIMITE_MAIL = 50 * 1024 * 1024          # limite Send to Kindle par e-mail
CIBLE_MAIL = 48 * 1024 * 1024           # on vise un peu en dessous

CONTAINER_XML = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
    '  <rootfiles>\n'
    '    <rootfile full-path="{}" media-type="application/oebps-package+xml"/>\n'
    '  </rootfiles>\n'
    '</container>\n'
)

DOCTYPE_EPUB2 = ('<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" '
                 '"http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">')
DOCTYPE_EPUB3 = "<!DOCTYPE html>"

TYPES_MEDIA = {
    ".xhtml": "application/xhtml+xml", ".html": "application/xhtml+xml",
    ".htm": "application/xhtml+xml", ".xml": "application/xhtml+xml",
    ".css": "text/css", ".ncx": "application/x-dtbncx+xml",
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".gif": "image/gif", ".svg": "image/svg+xml", ".webp": "image/webp",
    ".bmp": "image/bmp", ".tif": "image/tiff", ".tiff": "image/tiff",
    ".ttf": "font/ttf", ".otf": "font/otf", ".woff": "font/woff",
    ".woff2": "font/woff2", ".js": "application/javascript",
    ".smil": "application/smil+xml", ".mp3": "audio/mpeg",
    ".mp4": "video/mp4", ".pls": "application/pls+xml",
}
IMAGES_OK = {"image/jpeg", "image/png", "image/gif", "image/svg+xml"}
IMAGES_A_CONVERTIR = {"image/webp", "image/bmp", "image/tiff"}

VIDES = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
         "meta", "param", "source", "track", "wbr"}
ATTRS_REF = ("href", "src", "poster", "data")
NOM_XML = re.compile(r"^[A-Za-z_][\w.\-]*$")
CARS_INTERDITS_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")
SVG_ATTRS = {a.lower(): a for a in (
    "viewBox", "preserveAspectRatio", "gradientTransform", "gradientUnits",
    "patternUnits", "patternTransform", "clipPathUnits", "textLength",
    "lengthAdjust", "markerWidth", "markerHeight", "refX", "refY",
    "stdDeviation", "spreadMethod", "startOffset")}
SVG_TAGS = {t.lower(): t for t in (
    "linearGradient", "radialGradient", "clipPath", "foreignObject",
    "textPath", "feGaussianBlur", "feOffset", "feBlend", "feColorMatrix")}

ISO639_1 = set("""aa ab ae af ak am an ar as av ay az ba be bg bh bi bm bn bo br bs
ca ce ch co cr cs cu cv cy da de dv dz ee el en eo es et eu fa ff fi fj fo fr fy
ga gd gl gn gu gv ha he hi ho hr ht hu hy hz ia id ie ig ii ik io is it iu ja jv
ka kg ki kj kk kl km kn ko kr ks ku kv kw ky la lb lg li ln lo lt lu lv mg mh mi
mk ml mn mr ms mt my na nb nd ne ng nl nn no nr nv ny oc oj om or os pa pi pl ps
pt qu rm rn ro ru rw sa sc sd se sg si sk sl sm sn so sq sr ss st su sv sw ta te
tg th ti tk tl tn to tr ts tt tw ty ug uk ur uz ve vi vo wa wo xh yi yo za zh zu""".split())
LANGUES_3 = {
    "fre": "fr", "fra": "fr", "eng": "en", "ger": "de", "deu": "de", "spa": "es",
    "ita": "it", "por": "pt", "dut": "nl", "nld": "nl", "jpn": "ja", "chi": "zh",
    "zho": "zh", "rus": "ru", "ara": "ar", "pol": "pl", "swe": "sv", "dan": "da",
    "nor": "no", "nob": "nb", "fin": "fi", "gre": "el", "ell": "el", "tur": "tr",
    "cat": "ca", "bre": "br", "baq": "eu", "eus": "eu", "lat": "la", "kor": "ko",
    "heb": "he", "cze": "cs", "ces": "cs", "hun": "hu", "rum": "ro", "ron": "ro",
    "ukr": "uk", "oci": "oc", "cos": "co", "glg": "gl", "isl": "is", "ice": "is",
}
NOMS_LANGUES = {
    "francais": "fr", "français": "fr", "french": "fr", "anglais": "en",
    "english": "en", "allemand": "de", "german": "de", "deutsch": "de",
    "espagnol": "es", "spanish": "es", "español": "es", "italien": "it",
    "italian": "it", "italiano": "it", "portugais": "pt", "portuguese": "pt",
    "neerlandais": "nl", "néerlandais": "nl", "dutch": "nl",
}
MOTS_LANGUES = {
    "fr": "le la les des et est une dans pour que qui pas du au il elle ne se sur avec".split(),
    "en": "the and of to is in that it was for he she with his her not on".split(),
    "es": "el los las de que y en un por con no una su para es lo".split(),
    "de": "der die und das ist nicht mit sich des dem ein eine zu auf".split(),
    "it": "il di che la per non un sono gli della le si con una".split(),
    "pt": "o os de que e do da em um para com não uma se no".split(),
    "nl": "de het een en van ik te dat die in is niet zijn op".split(),
}


class LivreProtege(Exception):
    """Le livre est verrouillé par DRM : on n'y touche pas."""


class FormatNonGere(Exception):
    """Fichier illisible ou format inconnu."""


# --------------------------------------------------------------------------
# Rapport
# --------------------------------------------------------------------------

class Rapport:
    def __init__(self):
        self.corrections = []
        self.alertes = []
        self.erreurs = []
        self.infos = []

    def corrige(self, msg):
        if msg not in self.corrections:
            self.corrections.append(msg)

    def alerte(self, msg):
        if msg not in self.alertes:
            self.alertes.append(msg)

    def erreur(self, msg):
        self.erreurs.append(msg)

    def info(self, msg):
        self.infos.append(msg)

    def lignes(self):
        out = []
        out += [("info", m) for m in self.infos]
        out += [("corrige", m) for m in self.corrections]
        out += [("alerte", m) for m in self.alertes]
        out += [("erreur", m) for m in self.erreurs]
        return out


class Resultat:
    def __init__(self, source):
        self.source = source
        self.sortie = None
        self.titre = None
        self.auteur = None
        self.format_source = None
        self.rapport = Rapport()
        self.ok = False

    @property
    def taille(self):
        return os.path.getsize(self.sortie) if self.sortie and os.path.exists(self.sortie) else 0


# --------------------------------------------------------------------------
# Petits utilitaires
# --------------------------------------------------------------------------

def q(ns, tag):
    return "{%s}%s" % (ns, tag)


def nom_local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def texte_propre(s):
    return CARS_INTERDITS_XML.sub("", s) if s else s


def ajouter_texte(parent, texte):
    """Ajoute du texte à la fin d'un élément (dans le tail du dernier enfant)."""
    if not texte:
        return
    texte = texte_propre(texte)
    if len(parent):
        dernier = parent[-1]
        dernier.tail = (dernier.tail or "") + texte
    else:
        parent.text = (parent.text or "") + texte


def retirer_element(el):
    """Supprime un élément sans perdre le texte qui le suit."""
    parent = el.getparent()
    if parent is None:
        return
    tail = el.tail
    prev = el.getprevious()
    parent.remove(el)
    if tail:
        if prev is not None:
            prev.tail = (prev.tail or "") + tail
        else:
            parent.text = (parent.text or "") + tail


def deballer_element(el):
    """Remplace un élément par son contenu."""
    parent = el.getparent()
    if parent is None:
        return
    idx = parent.index(el)
    prev = el.getprevious()
    if el.text:
        if prev is not None:
            prev.tail = (prev.tail or "") + el.text
        else:
            parent.text = (parent.text or "") + el.text
    enfants = list(el)
    for i, c in enumerate(enfants):
        parent.insert(idx + i, c)
    dernier = enfants[-1] if enfants else el.getprevious()
    if el.tail:
        if dernier is not None and dernier is not el:
            dernier.tail = (dernier.tail or "") + el.tail
        else:
            parent.text = (parent.text or "") + el.tail
    parent.remove(el)


def sans_accents(s):
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def nom_fichier_sur(s, ascii_seul=False, maxi=120):
    s = s or "livre"
    if ascii_seul:
        s = sans_accents(s).encode("ascii", "ignore").decode()
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", s)
    s = re.sub(r"\s+", " ", s).strip(" .")
    return (s[:maxi].strip(" .") or "livre")


def nom_interne_sur(chemin):
    """Nom de fichier interne sans espace ni caractère exotique."""
    dossier, nom = posixpath.split(chemin)
    base, ext = posixpath.splitext(nom)
    base = sans_accents(base)
    base = re.sub(r"[^A-Za-z0-9_\-.]+", "_", base).strip("_") or "f"
    ext = re.sub(r"[^A-Za-z0-9.]+", "", ext.lower())
    morceaux = []
    for d in dossier.split("/") if dossier else []:
        d2 = re.sub(r"[^A-Za-z0-9_\-.]+", "_", sans_accents(d)).strip("_") or "d"
        morceaux.append(d2)
    return posixpath.join(*(morceaux + [base + ext]))


def chemin_valide(chemin):
    return re.fullmatch(r"[A-Za-z0-9_\-./]+", chemin) is not None


def resoudre(base_doc, ref):
    """Chemin d'un lien relatif à un document, dans le zip. None si externe."""
    if not ref:
        return None, ""
    ref = ref.strip()
    parts = urlsplit(ref)
    if parts.scheme or parts.netloc or ref.startswith("//"):
        return None, ""
    chemin = unquote(parts.path)
    frag = parts.fragment
    if not chemin:
        return base_doc, frag
    abs_ = posixpath.normpath(posixpath.join(posixpath.dirname(base_doc), chemin))
    if abs_.startswith("../"):
        abs_ = abs_.lstrip("./")
    return abs_, frag


def relatif(depuis_doc, cible):
    return posixpath.relpath(cible, posixpath.dirname(depuis_doc) or ".")


def decoder_texte(data):
    """Renvoie (texte, encodage_detecte, encodage_declare)."""
    declare = None
    if data.startswith(codecs.BOM_UTF8):
        return data[3:].decode("utf-8", "replace"), "utf-8", "utf-8"
    if data.startswith(codecs.BOM_UTF16_LE) or data.startswith(codecs.BOM_UTF16_BE):
        return data.decode("utf-16", "replace"), "utf-16", "utf-16"
    m = re.match(rb"\s*<\?xml[^>]*encoding=[\"']([\w.:\-]+)", data[:300])
    if m:
        declare = m.group(1).decode("ascii", "ignore").lower()
    else:
        m = re.search(rb"<meta[^>]+charset=[\"']?([\w.:\-]+)", data[:4096], re.I)
        if m:
            declare = m.group(1).decode("ascii", "ignore").lower()
        else:
            m = re.match(rb"\s*@charset\s+[\"']([\w.:\-]+)", data[:200])
            if m:
                declare = m.group(1).decode("ascii", "ignore").lower()
    try:
        return data.decode("utf-8"), "utf-8", declare
    except UnicodeDecodeError:
        pass
    for enc in (declare, "cp1252", "latin-1"):
        if not enc:
            continue
        try:
            return data.decode(enc), enc, declare
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", "replace"), "utf-8", declare


def remplacer_entites(texte):
    """Entités HTML (&nbsp; &eacute;…) -> caractères ; & isolés -> &amp;."""
    def rep(m):
        nom = m.group(1)
        if nom in ("amp", "lt", "gt", "quot", "apos"):
            return m.group(0)
        car = html_mod.entities.html5.get(nom + ";")
        if car is None:
            return "&amp;" + nom + ";"
        return {"&": "&amp;", "<": "&lt;", ">": "&gt;"}.get(car, car)
    texte = re.sub(r"&([A-Za-z][A-Za-z0-9]*);", rep, texte)
    texte = re.sub(r"&(?!(?:#\d+|#[xX][0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]*);)", "&amp;", texte)
    return texte


def parser_xml_tolerant(data):
    parser = etree.XMLParser(recover=True, resolve_entities=False, no_network=True,
                             huge_tree=True, remove_comments=False)
    texte, _, _ = decoder_texte(data)
    texte = re.sub(r"^\s*<\?xml[^>]*\?>", "", texte)
    texte = remplacer_entites(texte)
    return etree.fromstring(texte.encode("utf-8"), parser)


def parser_xml_strict(texte):
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=True)
    return etree.fromstring(texte.encode("utf-8"), parser)


def serialiser_xml(root, doctype=None):
    corps = etree.tostring(root, encoding="unicode")
    tete = '<?xml version="1.0" encoding="utf-8"?>\n'
    if doctype:
        tete += doctype + "\n"
    return (tete + corps + "\n").encode("utf-8")


# --------------------------------------------------------------------------
# HTML abîmé -> XHTML propre
# --------------------------------------------------------------------------

def html_vers_xhtml(src_root):
    """Recopie un arbre lxml.html (tolérant) en arbre XHTML bien formé."""
    root = etree.Element(q(XHTML, "html"), nsmap={None: XHTML, "epub": EPUB})

    def copier_attrs(src, dst, ns):
        for k, v in src.attrib.items():
            k = k.strip()
            kl = k.lower()
            v = texte_propre(v)
            if kl == "xmlns" or kl.startswith("xmlns:"):
                continue
            if kl in ("xml:lang", "lang") and ns == XHTML:
                dst.set(q(XMLNS, "lang") if kl == "xml:lang" else "lang", v)
                continue
            if kl == "xlink:href":
                dst.set(q(XLINK, "href"), v)
                continue
            if kl == "epub:type":
                dst.set(q(EPUB, "type"), v)
                continue
            if ns == SVG:
                k = SVG_ATTRS.get(kl, k)
            if ":" in k or not NOM_XML.match(k):
                continue
            if dst.get(k) is None:
                dst.set(k, v)

    def construire(src, dst, ns):
        for enfant in src:
            if not isinstance(enfant.tag, str):
                ajouter_texte(dst, enfant.tail)
                continue
            nom = enfant.tag.strip()
            nom_l = nom.lower()
            if nom_l in ("script", "noscript"):
                ajouter_texte(dst, enfant.tail)
                continue
            if ":" in nom_l or not NOM_XML.match(nom_l):
                # balise inconnue (mbp:..., o:p…) : on garde son contenu
                ajouter_texte(dst, enfant.text)
                construire(enfant, dst, ns)
                ajouter_texte(dst, enfant.tail)
                continue
            ns_e = SVG if nom_l == "svg" else MATHML if nom_l == "math" else ns
            if ns_e == SVG:
                nom = SVG_TAGS.get(nom_l, nom)
            elif ns_e == XHTML:
                nom = nom_l
            if nom_l == "svg" and ns != SVG:
                el = etree.SubElement(dst, q(SVG, "svg"), nsmap={None: SVG, "xlink": XLINK})
            elif nom_l == "math" and ns != MATHML:
                el = etree.SubElement(dst, q(MATHML, "math"), nsmap={None: MATHML})
            else:
                el = etree.SubElement(dst, q(ns_e, nom))
            copier_attrs(enfant, el, ns_e)
            if ns_e == XHTML and nom_l in VIDES:
                el.tail = texte_propre(enfant.text or "") + (texte_propre(enfant.tail) or "") or None
                continue
            el.text = texte_propre(enfant.text)
            construire(enfant, el, ns_e)
            el.tail = texte_propre(enfant.tail)

    # src_root est l'élément <html> d'un document lxml.html
    tete_src = src_root.find("head")
    corps_src = src_root.find("body")
    head = etree.SubElement(root, q(XHTML, "head"))
    if tete_src is not None:
        construire(tete_src, head, XHTML)
    body = etree.SubElement(root, q(XHTML, "body"))
    if corps_src is not None:
        copier_attrs(corps_src, body, XHTML)
        body.text = texte_propre(corps_src.text)
        construire(corps_src, body, XHTML)
    else:
        construire(src_root, body, XHTML)
    for k, v in src_root.attrib.items():
        if k.lower() in ("lang", "dir"):
            root.set(k.lower(), v)
        elif k.lower() == "xml:lang":
            root.set(q(XMLNS, "lang"), v)
    return root


def mettre_namespace_xhtml(root):
    """Un XHTML sans xmlns : on met tous les éléments dans l'espace XHTML."""
    change = False
    for el in root.iter():
        if isinstance(el.tag, str) and not el.tag.startswith("{"):
            el.tag = q(XHTML, el.tag)
            change = True
    if change:
        etree.cleanup_namespaces(root)
    return change


# --------------------------------------------------------------------------
# Détection du format
# --------------------------------------------------------------------------

def detecter_format(chemin):
    with open(chemin, "rb") as f:
        tete = f.read(128)
    if tete[:2] == b"PK":
        return "zip"
    if tete[60:68] == b"BOOKMOBI":
        return "mobi"
    if tete[:3] == b"TPZ":
        return "topaz"
    if tete[:5] == b"%PDF-":
        return "pdf"
    if tete[:4] == b"CONT" or tete[:8] == b"\xeaDRMION\xee":
        return "kfx"
    if tete[60:68] == b"TEXtREAd":
        return "palmdoc"
    return "inconnu"


def mobi_est_protege(chemin):
    with open(chemin, "rb") as f:
        d = f.read(4096)
    try:
        off = struct.unpack(">I", d[78:82])[0]
        with open(chemin, "rb") as f:
            f.seek(off)
            r0 = f.read(16)
        return struct.unpack(">H", r0[12:14])[0] != 0
    except Exception:
        return False


# --------------------------------------------------------------------------
# MOBI / AZW3 -> EPUB
# --------------------------------------------------------------------------

FONT_TAILLES = {"1": "0.67em", "2": "0.83em", "3": "1em", "4": "1.17em",
                "5": "1.5em", "6": "2em", "7": "2.5em", "+1": "1.17em",
                "+2": "1.5em", "+3": "2em", "-1": "0.83em", "-2": "0.67em"}


def _longueur(v):
    v = v.strip()
    if re.fullmatch(r"-?\d+(\.\d+)?", v):
        return v + "em" if v not in ("0",) else "0"
    if re.fullmatch(r"-?\d+(\.\d+)?(em|ex|pt|px|%|cm|mm|in|pc|rem)", v):
        return v
    return None


def _nul(v):
    return v is None or re.fullmatch(r"-?0+(\.0+)?(em|ex|pt|px|%|cm|mm|in|pc|rem)?", v.strip()) is not None


def nettoyer_balisage_mobi(body, classes):
    """Attributs « Mobipocket » (height, width, align, <font>…) -> CSS."""
    for el in list(body.iter()):
        if not isinstance(el.tag, str):
            continue
        tag = el.tag.lower()
        styles = []
        if tag in ("p", "div", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6", "li", "dd", "dt"):
            h = el.attrib.pop("height", None)
            w = el.attrib.pop("width", None)
            if h and not _nul(h) and _longueur(h):
                styles.append("margin-top:" + _longueur(h))
            if w and not _nul(w) and _longueur(w):
                if tag == "blockquote":
                    styles.append("margin-left:" + _longueur(w))
                else:
                    styles.append("text-indent:" + _longueur(w))
        if tag == "hr":
            w = el.attrib.pop("width", None)
            if w and _longueur(w):
                styles.append("width:" + _longueur(w))
            el.attrib.pop("size", None)
            el.attrib.pop("noshade", None)
        if tag == "img":
            a = el.attrib.pop("align", None)
            if a in ("left", "right"):
                styles.append("float:" + a)
            for attr in ("hspace", "vspace", "border", "hisrc", "losrc", "mediarecindex", "recindex"):
                el.attrib.pop(attr, None)
        else:
            a = el.attrib.pop("align", None)
            if a and a.lower() in ("center", "left", "right", "justify"):
                styles.append("text-align:" + a.lower())
        if tag == "font":
            taille = el.attrib.pop("size", None)
            couleur = el.attrib.pop("color", None)
            el.attrib.pop("face", None)
            if taille and taille.strip() in FONT_TAILLES:
                styles.append("font-size:" + FONT_TAILLES[taille.strip()])
            if couleur:
                styles.append("color:" + couleur)
            el.tag = "span"
        elif tag == "center":
            el.tag = "div"
            styles.append("text-align:center")
        elif tag in ("big", "small"):
            styles.append("font-size:" + ("1.2em" if tag == "big" else "0.83em"))
            el.tag = "span"
        elif tag in ("strike", "s"):
            styles.append("text-decoration:line-through")
            el.tag = "span"
        elif tag == "tt":
            styles.append("font-family:monospace")
            el.tag = "span"
        for attr in ("filepos", "bgcolor", "valign"):
            el.attrib.pop(attr, None)
        if styles:
            existant = el.get("style")
            if existant:
                styles.append(existant.strip().rstrip(";"))
            cle = ";".join(styles)
            if cle not in classes:
                classes[cle] = "k%d" % (len(classes) + 1)
            el.attrib.pop("style", None)
            anciennes = el.get("class")
            el.set("class", (anciennes + " " if anciennes else "") + classes[cle])


def construire_epub_depuis_mobi7(dossier, rapport):
    """Fabrique un EPUB 3 à partir de la sortie « mobi7 » de KindleUnpack."""
    with open(os.path.join(dossier, "book.html"), "rb") as f:
        brut = f.read()
    texte, _, _ = decoder_texte(brut)

    # métadonnées d'origine
    opf_src = None
    chemin_opf = os.path.join(dossier, "content.opf")
    if os.path.exists(chemin_opf):
        with open(chemin_opf, "rb") as f:
            opf_src = parser_xml_tolerant(f.read())
    ncx_src = None
    chemin_ncx = os.path.join(dossier, "toc.ncx")
    if os.path.exists(chemin_ncx):
        with open(chemin_ncx, "rb") as f:
            ncx_src = parser_xml_tolerant(f.read())

    m = re.search(r"<body[^>]*>(.*)</body>", texte, re.S | re.I)
    corps = m.group(1) if m else texte
    COUPE = "\u0000COUPE\u0000"
    corps = re.sub(r"<mbp:pagebreak\s*/?\s*>|</mbp:pagebreak\s*>", COUPE, corps, flags=re.I)
    corps = re.sub(r"</?mbp:[^>]*>", "", corps, flags=re.I)
    # <a id="x" /> en HTML ouvre une balise qui avale la suite : on la ferme
    corps = re.sub(r"<(?!(?:%s)\b)([A-Za-z][\w.\-]*)(\s[^<>]*?)?\s*/>" % "|".join(VIDES),
                   lambda mm: "<%s%s></%s>" % (mm.group(1), mm.group(2) or "", mm.group(1)), corps)
    morceaux = corps.split(COUPE)

    # les ancres juste avant un saut de page vont au début de la page suivante
    ancres_fin = re.compile(r"((?:\s|<br\s*/?>|<a\s+id=\"[^\"]*\"\s*>\s*</a>|</?div>)*)$", re.I)
    for i in range(len(morceaux) - 1):
        m2 = ancres_fin.search(morceaux[i])
        if m2 and m2.group(1):
            ancres = re.findall(r"<a\s+id=\"[^\"]*\"\s*>\s*</a>", m2.group(1), re.I)
            if ancres:
                morceaux[i] = morceaux[i][:m2.start(1)] + re.sub(
                    r"<a\s+id=\"[^\"]*\"\s*>\s*</a>", "", m2.group(1), flags=re.I)
                morceaux[i + 1] = "".join(ancres) + morceaux[i + 1]

    def vide(s):
        sans = re.sub(r"<a\s+id=\"[^\"]*\"\s*>\s*</a>", "", s, flags=re.I)
        if re.search(r"<(img|svg|hr|table)\b", sans, re.I):
            return False
        sans = re.sub(r"<[^>]+>", "", sans)
        return not html_mod.unescape(sans).strip()

    pages = []
    report = ""
    for s in morceaux:
        if vide(s):
            report += "".join(re.findall(r"<a\s+id=\"[^\"]*\"\s*>\s*</a>", s, re.I))
            continue
        pages.append(report + s)
        report = ""
    if report and pages:
        pages[-1] += report
    if not pages:
        raise FormatNonGere("le MOBI ne contient pas de texte lisible")

    classes = OrderedDict()
    fichiers = OrderedDict()
    pages_xhtml = []          # (chemin, root)
    id_vers_page = {}
    images_utilisees = OrderedDict()

    for n, s in enumerate(pages, 1):
        doc = lhtml.document_fromstring("<html><head></head><body>%s</body></html>" % s)
        body = doc.find("body")
        nettoyer_balisage_mobi(body, classes)
        root = html_vers_xhtml(doc)
        chemin = "OEBPS/texte/page%03d.xhtml" % n
        for el in root.iter():
            if not isinstance(el.tag, str):
                continue
            i = el.get("id")
            if i:
                id_vers_page.setdefault(i, chemin)
            if nom_local(el.tag) == "img":
                srcv = el.get("src", "")
                ext = posixpath.splitext(srcv)[1].lower()
                if ext == ".jpeg":
                    ext = ".jpg"
                nom_img = images_utilisees.setdefault(
                    srcv, "OEBPS/images/" + nom_interne_sur(posixpath.basename(posixpath.splitext(srcv)[0])) + ext)
                el.set("src", relatif(chemin, nom_img))
                if not el.get("alt"):
                    el.set("alt", "")
        pages_xhtml.append((chemin, root))

    # liens internes (#fileposNNN) -> bonne page
    for chemin, root in pages_xhtml:
        for el in root.iter(q(XHTML, "a")):
            h = el.get("href")
            if not h:
                continue
            if h.startswith("#") or h.startswith("book.html#"):
                frag = h.split("#", 1)[1]
                cible = id_vers_page.get(frag)
                if cible:
                    el.set("href", (relatif(chemin, cible) if cible != chemin else "") + "#" + frag)
                else:
                    del el.attrib["href"]

    # métadonnées
    def dc_texte(nom):
        if opf_src is None:
            return []
        return [e for e in opf_src.iter(q(DC, nom))]
    titre = next((e.text.strip() for e in dc_texte("title") if e.text and e.text.strip()), None)
    auteurs = [e.text.strip() for e in dc_texte("creator") if e.text and e.text.strip()]
    langue = next((e.text.strip() for e in dc_texte("language") if e.text and e.text.strip()), None)

    # couverture
    couverture_src = None
    if opf_src is not None:
        id_couv = None
        for meta in opf_src.iter(q(OPF, "meta")):
            if meta.get("name") == "cover":
                id_couv = meta.get("content")
        for item in opf_src.iter(q(OPF, "item")):
            if item.get("id") == id_couv:
                couverture_src = item.get("href")
    if couverture_src and not os.path.exists(os.path.join(dossier, couverture_src)):
        couverture_src = None

    # images : on copie celles qui servent (+ la couverture)
    if couverture_src and couverture_src not in images_utilisees:
        ext = posixpath.splitext(couverture_src)[1].lower().replace(".jpeg", ".jpg")
        images_utilisees[couverture_src] = "OEBPS/images/couverture" + ext
        couverture_dans_texte = False
    else:
        couverture_dans_texte = bool(couverture_src)
    for srcv, dest in images_utilisees.items():
        p = os.path.join(dossier, srcv)
        if os.path.exists(p):
            with open(p, "rb") as f:
                fichiers[dest] = f.read()
        else:
            rapport.alerte("Image introuvable dans le MOBI : %s" % srcv)

    # CSS
    css = ["body { margin: 0; padding: 0; }",
           "p { margin: 0; text-indent: 0; }",
           "img { max-width: 100%; }",
           "div.couverture { text-align: center; margin: 0; padding: 0; }",
           "div.couverture img { height: 100%; max-width: 100%; }"]
    for regle, nom in classes.items():
        css.append(".%s { %s; }" % (nom, regle.replace(";", "; ")))
    fichiers["OEBPS/styles.css"] = ("\n".join(css) + "\n").encode("utf-8")

    # page de couverture
    spine = []
    if couverture_src and not couverture_dans_texte:
        img = images_utilisees[couverture_src]
        page_couv = "OEBPS/texte/couverture.xhtml"
        fichiers[page_couv] = (
            '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">\n'
            '<head><title>Couverture</title><link rel="stylesheet" type="text/css" href="../styles.css"/></head>\n'
            '<body><div class="couverture"><img src="%s" alt="Couverture"/></div></body>\n</html>\n'
            % relatif(page_couv, img)).encode("utf-8")
        spine.append(("couverture", page_couv))

    titre_doc = titre or "Livre"
    for n, (chemin, root) in enumerate(pages_xhtml, 1):
        head = root.find(q(XHTML, "head"))
        for e in list(head):
            head.remove(e)
        t = etree.SubElement(head, q(XHTML, "title"))
        t.text = titre_doc
        link = etree.SubElement(head, q(XHTML, "link"))
        link.set("rel", "stylesheet")
        link.set("type", "text/css")
        link.set("href", relatif(chemin, "OEBPS/styles.css"))
        if langue:
            root.set("lang", langue)
            root.set(q(XMLNS, "lang"), langue)
        fichiers[chemin] = serialiser_xml(root, DOCTYPE_EPUB3)
        spine.append(("page%03d" % n, chemin))

    # sommaire
    entrees = []
    if ncx_src is not None:
        for np_ in ncx_src.iter(q(NCX, "navPoint")):
            lab = np_.find(q(NCX, "navLabel"))
            cont = np_.find(q(NCX, "content"))
            if lab is None or cont is None:
                continue
            txt = "".join(lab.itertext())
            lignes = [l.strip() for l in txt.splitlines() if l.strip()]
            txt = " – ".join(lignes)
            srcv = cont.get("src", "")
            frag = srcv.split("#", 1)[1] if "#" in srcv else ""
            cible = id_vers_page.get(frag)
            if not cible:
                continue
            entrees.append((txt or "Chapitre", cible + "#" + frag))
    if not entrees:
        for chemin, root in pages_xhtml:
            for h in root.iter(q(XHTML, "h1"), q(XHTML, "h2")):
                txt = " ".join("".join(h.itertext()).split())
                if txt:
                    entrees.append((txt[:80], chemin))
                    break
    if not entrees:
        entrees.append((titre_doc, pages_xhtml[0][0]))
        rapport.alerte("Pas de sommaire dans le MOBI : sommaire minimal créé.")

    livre = {
        "fichiers": fichiers,
        "titre": titre_doc,
        "auteurs": auteurs,
        "langue": langue,
        "opf_src": opf_src,
        "spine": spine,
        "entrees": entrees,
        "couverture": images_utilisees.get(couverture_src) if couverture_src else None,
    }
    return assembler_epub3(livre)


def assembler_epub3(livre):
    """Écrit OPF, NCX et nav pour un livre construit de zéro."""
    fichiers = livre["fichiers"]
    ident = "urn:uuid:" + str(uuid.uuid4())
    maintenant = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    pkg = etree.Element(q(OPF, "package"), nsmap={None: OPF},
                        version="3.0", **{"unique-identifier": "bookid"})
    pkg.set(q(XMLNS, "lang"), livre.get("langue") or "fr")
    meta = etree.SubElement(pkg, q(OPF, "metadata"), nsmap={"dc": DC, "opf": OPF})
    e = etree.SubElement(meta, q(DC, "identifier"), id="bookid")
    e.text = ident
    e = etree.SubElement(meta, q(DC, "title"))
    e.text = livre["titre"]
    if livre.get("langue"):
        e = etree.SubElement(meta, q(DC, "language"))
        e.text = livre["langue"]
    for a in livre.get("auteurs") or []:
        e = etree.SubElement(meta, q(DC, "creator"))
        e.text = a
    src = livre.get("opf_src")
    if src is not None:
        dates = set()
        for nom in ("publisher", "subject", "description", "date", "rights", "contributor"):
            for d in src.iter(q(DC, nom)):
                if not d.text or not d.text.strip():
                    continue
                if nom == "contributor" and "calibre" in d.text.lower():
                    continue
                if nom == "date":
                    if d.text in dates:
                        continue
                    dates.add(d.text)
                    if len(dates) > 1:
                        continue
                e = etree.SubElement(meta, q(DC, nom))
                e.text = d.text.strip()
        for d in src.iter(q(DC, "identifier")):
            sch = d.get(q(OPF, "scheme")) or ""
            if sch.upper() == "ISBN" and d.text:
                e = etree.SubElement(meta, q(DC, "identifier"))
                e.text = "urn:isbn:" + d.text.strip()
    e = etree.SubElement(meta, q(OPF, "meta"), property="dcterms:modified")
    e.text = maintenant
    if livre.get("couverture"):
        etree.SubElement(meta, q(OPF, "meta"), name="cover", content="couverture-img")

    manifest = etree.SubElement(pkg, q(OPF, "manifest"))
    etree.SubElement(manifest, q(OPF, "item"), id="ncx", href="toc.ncx",
                     **{"media-type": "application/x-dtbncx+xml"})
    etree.SubElement(manifest, q(OPF, "item"), id="nav", href="nav.xhtml",
                     properties="nav", **{"media-type": "application/xhtml+xml"})
    ids_spine = {}
    for ident_page, chemin in livre["spine"]:
        etree.SubElement(manifest, q(OPF, "item"), id=ident_page,
                         href=relatif("OEBPS/content.opf", chemin),
                         **{"media-type": "application/xhtml+xml"})
        ids_spine[chemin] = ident_page
    n = 0
    for chemin in fichiers:
        if chemin in ids_spine:
            continue
        ext = posixpath.splitext(chemin)[1].lower()
        mt = TYPES_MEDIA.get(ext)
        if not mt:
            continue
        n += 1
        attrs = {"media-type": mt}
        ident_item = "res%03d" % n
        if chemin == livre.get("couverture"):
            ident_item = "couverture-img"
            attrs["properties"] = "cover-image"
        etree.SubElement(manifest, q(OPF, "item"), id=ident_item,
                         href=relatif("OEBPS/content.opf", chemin), **attrs)
    spine = etree.SubElement(pkg, q(OPF, "spine"), toc="ncx")
    for ident_page, chemin in livre["spine"]:
        etree.SubElement(spine, q(OPF, "itemref"), idref=ident_page)

    fichiers["OEBPS/content.opf"] = serialiser_xml(pkg)
    fichiers["OEBPS/toc.ncx"] = fabriquer_ncx(livre["entrees"], ident, livre["titre"], "OEBPS/toc.ncx")
    fichiers["OEBPS/nav.xhtml"] = fabriquer_nav(livre["entrees"], livre["titre"], "OEBPS/nav.xhtml",
                                                livre.get("langue"))
    fichiers["META-INF/container.xml"] = CONTAINER_XML.format("OEBPS/content.opf").encode("utf-8")
    sortie = OrderedDict()
    sortie["mimetype"] = b"application/epub+zip"
    sortie.update(fichiers)
    return sortie


def fabriquer_ncx(entrees, ident, titre, chemin_ncx):
    ncx = etree.Element(q(NCX, "ncx"), nsmap={None: NCX}, version="2005-1")
    head = etree.SubElement(ncx, q(NCX, "head"))
    for nom, val in (("dtb:uid", ident), ("dtb:depth", "1"),
                     ("dtb:totalPageCount", "0"), ("dtb:maxPageNumber", "0")):
        etree.SubElement(head, q(NCX, "meta"), name=nom, content=val)
    dt = etree.SubElement(ncx, q(NCX, "docTitle"))
    etree.SubElement(dt, q(NCX, "text")).text = titre
    nm = etree.SubElement(ncx, q(NCX, "navMap"))
    for i, (txt, cible) in enumerate(entrees, 1):
        np_ = etree.SubElement(nm, q(NCX, "navPoint"), id="np%d" % i, playOrder=str(i))
        lab = etree.SubElement(np_, q(NCX, "navLabel"))
        etree.SubElement(lab, q(NCX, "text")).text = txt
        chemin, _, frag = cible.partition("#")
        etree.SubElement(np_, q(NCX, "content"),
                         src=relatif(chemin_ncx, chemin) + ("#" + frag if frag else ""))
    return serialiser_xml(ncx)


def fabriquer_nav(entrees, titre, chemin_nav, langue=None):
    root = etree.Element(q(XHTML, "html"), nsmap={None: XHTML, "epub": EPUB})
    if langue:
        root.set("lang", langue)
        root.set(q(XMLNS, "lang"), langue)
    head = etree.SubElement(root, q(XHTML, "head"))
    etree.SubElement(head, q(XHTML, "title")).text = titre
    body = etree.SubElement(root, q(XHTML, "body"))
    nav = etree.SubElement(body, q(XHTML, "nav"), id="toc")
    nav.set(q(EPUB, "type"), "toc")
    etree.SubElement(nav, q(XHTML, "h1")).text = "Sommaire"
    ol = etree.SubElement(nav, q(XHTML, "ol"))
    for txt, cible in entrees:
        li = etree.SubElement(ol, q(XHTML, "li"))
        chemin, _, frag = cible.partition("#")
        a = etree.SubElement(li, q(XHTML, "a"), href=relatif(chemin_nav, chemin) + ("#" + frag if frag else ""))
        a.text = txt
    return serialiser_xml(root, DOCTYPE_EPUB3)


def mobi_vers_epub(chemin, rapport):
    """Renvoie (type, données) : ('epub', OrderedDict de fichiers) ou ('pdf', bytes)."""
    if mobi_est_protege(chemin):
        raise LivreProtege()
    try:
        import mobi
    except ImportError:
        raise FormatNonGere("le module « mobi » n'est pas installé (pip install mobi)")
    try:
        from loguru import logger
        logger.remove()
    except Exception:
        pass
    puits = io.StringIO()
    with contextlib.redirect_stdout(puits), contextlib.redirect_stderr(puits):
        try:
            tmp, sortie = mobi.extract(chemin)
        except Exception as exc:
            raise FormatNonGere("impossible de lire ce fichier Kindle (%s)" % exc)
    try:
        if sortie.lower().endswith(".epub"):
            rapport.corrige("Fichier Kindle (AZW3/KF8) converti en EPUB.")
            return "epub", lire_zip(sortie, rapport)
        if sortie.lower().endswith(".pdf"):
            with open(sortie, "rb") as f:
                return "pdf", f.read()
        livre = construire_epub_depuis_mobi7(os.path.dirname(sortie), rapport)
        rapport.corrige("Ancien format MOBI converti en vrai EPUB.")
        return "epub", livre
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# Lecture du zip
# --------------------------------------------------------------------------

DECHETS = re.compile(r"(^|/)(__MACOSX/|\.DS_Store$|Thumbs\.db$|desktop\.ini$|\._)", re.I)


def lire_zip(chemin, rapport):
    fichiers = OrderedDict()
    try:
        z = zipfile.ZipFile(chemin)
    except zipfile.BadZipFile:
        raise FormatNonGere("l'archive EPUB est abîmée (zip illisible)")
    with z:
        infos = z.infolist()
        if infos:
            premier = infos[0]
            if premier.filename != "mimetype" or premier.compress_type != zipfile.ZIP_STORED:
                rapport.corrige("Fichier « mimetype » remis en tête, non compressé (exigé par la norme).")
        dechets = 0
        for info in infos:
            if info.is_dir():
                continue
            nom = info.filename.replace("\\", "/").lstrip("/")
            if DECHETS.search(nom):
                dechets += 1
                continue
            try:
                donnees = z.read(info)
            except Exception:
                rapport.alerte("Fichier illisible dans l'archive, ignoré : %s" % nom)
                continue
            if nom in fichiers:
                rapport.corrige("Fichier en double dans l'archive : %s" % nom)
            fichiers[nom] = donnees
        if dechets:
            rapport.corrige("%d fichier(s) parasite(s) retiré(s) (__MACOSX, .DS_Store…)." % dechets)
    mt = fichiers.get("mimetype", b"").strip()
    if mt != b"application/epub+zip":
        rapport.corrige("Fichier « mimetype » absent ou incorrect : recréé.")
    fichiers["mimetype"] = b"application/epub+zip"
    fichiers.move_to_end("mimetype", last=False)
    return fichiers


# --------------------------------------------------------------------------
# Polices obfusquées (Adobe / IDPF) — ce n'est pas un DRM
# --------------------------------------------------------------------------

def _est_police(d):
    return d[:4] in (b"\x00\x01\x00\x00", b"OTTO", b"true", b"wOFF", b"wOF2", b"ttcf", b"typ1")


ALGOS_POLICES = ("http://www.idpf.org/2008/embedding", "http://ns.adobe.com/pdf/enc#RC")


def verifier_drm(fichiers):
    """Lève LivreProtege si le livre est verrouillé (Adobe, Apple, LCP, Kobo…)."""
    if any(n in fichiers for n in ("META-INF/rights.xml", "META-INF/sinf.xml", "META-INF/license.lcpl")):
        raise LivreProtege()
    enc = fichiers.get("META-INF/encryption.xml")
    if enc:
        root = parser_xml_tolerant(enc)
        if root is not None:
            for meth in root.iter(q(ENC, "EncryptionMethod")):
                if meth.get("Algorithm") not in ALGOS_POLICES:
                    raise LivreProtege()


def traiter_chiffrement(fichiers, identifiants, rapport):
    enc = fichiers.get("META-INF/encryption.xml")
    verifier_drm(fichiers)
    if enc is None:
        return
    root = parser_xml_tolerant(enc)
    if root is None:
        del fichiers["META-INF/encryption.xml"]
        return
    tout_traite = True
    remises = 0
    for ed in root.iter(q(ENC, "EncryptedData")):
        meth = ed.find(q(ENC, "EncryptionMethod"))
        algo = meth.get("Algorithm") if meth is not None else ""
        ref = ed.find(".//" + q(ENC, "CipherReference"))
        uri = unquote(ref.get("URI", "")) if ref is not None else ""
        if algo not in ALGOS_POLICES:
            raise LivreProtege()
        if uri not in fichiers:
            continue
        d = fichiers[uri]
        if _est_police(d):
            continue  # déjà en clair
        resultat = None
        if algo == "http://www.idpf.org/2008/embedding":
            for ident in identifiants:
                cle = hashlib.sha1(re.sub(r"[ \u0009\u000d\u000a]", "", ident).encode("utf-8")).digest()
                tete = bytes(b ^ cle[i % 20] for i, b in enumerate(d[:1040]))
                if _est_police(tete):
                    resultat = tete + d[1040:]
                    break
        else:
            for ident in identifiants:
                hexa = re.sub(r"[^0-9a-fA-F]", "", ident.replace("urn:uuid:", ""))
                if len(hexa) != 32:
                    continue
                cle = bytes.fromhex(hexa)
                tete = bytes(b ^ cle[i % 16] for i, b in enumerate(d[:1024]))
                if _est_police(tete):
                    resultat = tete + d[1024:]
                    break
        if resultat:
            fichiers[uri] = resultat
            remises += 1
        else:
            tout_traite = False
            del fichiers[uri]
            rapport.alerte("Police intégrée illisible retirée : %s (la Kindle utilisera ses polices)."
                           % posixpath.basename(uri))
    del fichiers["META-INF/encryption.xml"]
    if remises and tout_traite:
        rapport.corrige("%d police(s) « obfusquée(s) » remise(s) en clair (Amazon les refuse sinon)."
                        % remises)
    elif remises:
        rapport.corrige("%d police(s) « obfusquée(s) » remise(s) en clair." % remises)


# --------------------------------------------------------------------------
# Langue
# --------------------------------------------------------------------------

def normaliser_langue(v):
    """'fr-FR' -> 'fr-FR' ; 'fre' -> 'fr' ; 'Français' -> 'fr' ; invalide -> None."""
    if not v:
        return None
    v = v.strip()
    vl = sans_accents(v.lower())
    if vl in NOMS_LANGUES or v.lower() in NOMS_LANGUES:
        return NOMS_LANGUES.get(v.lower(), NOMS_LANGUES.get(vl))
    m = re.fullmatch(r"([A-Za-z]{2,3})((?:[-_][A-Za-z0-9]{1,8})*)", v)
    if not m:
        return None
    prim = m.group(1).lower()
    suite = m.group(2).replace("_", "-")
    if len(prim) == 3:
        prim = LANGUES_3.get(prim)
        if not prim:
            return None
    if prim not in ISO639_1:
        return None
    return prim + suite


def deviner_langue(textes):
    mots = re.findall(r"[a-zàâäéèêëîïôöùûüçñß]+", " ".join(textes)[:60000].lower())
    if len(mots) < 50:
        return None
    compte = {}
    for lang, liste in MOTS_LANGUES.items():
        s = set(liste)
        compte[lang] = sum(1 for w in mots if w in s)
    meilleur = max(compte, key=compte.get)
    total = sum(compte.values()) or 1
    if compte[meilleur] / len(mots) > 0.08 and compte[meilleur] / total > 0.4:
        return meilleur
    return None


# --------------------------------------------------------------------------
# Réparation d'un EPUB
# --------------------------------------------------------------------------

class Reparateur:
    def __init__(self, fichiers, rapport, options):
        self.f = fichiers
        self.r = rapport
        self.opt = options
        self.lower = {}
        self.rebuild_lower()

    def rebuild_lower(self):
        self.lower = {}
        for k in self.f:
            self.lower.setdefault(k.lower(), k)

    def trouver(self, chemin):
        """Retrouve un fichier, même si la casse ou l'encodage du nom diffère."""
        if chemin is None:
            return None
        if chemin in self.f:
            return chemin
        alt = self.lower.get(chemin.lower())
        if alt:
            return alt
        alt = unicodedata.normalize("NFC", chemin)
        if alt in self.f:
            return alt
        alt = self.lower.get(unicodedata.normalize("NFC", chemin).lower())
        if alt:
            return alt
        return None

    # ---------------------------------------------------------------- OPF
    def localiser_opf(self):
        cont = self.f.get("META-INF/container.xml")
        chemin = None
        if cont:
            root = parser_xml_tolerant(cont)
            if root is not None:
                for rf in root.iter():
                    if nom_local(rf.tag) == "rootfile" and rf.get("full-path"):
                        chemin = self.trouver(unquote(rf.get("full-path")).lstrip("/"))
                        if chemin:
                            break
        if not chemin:
            opfs = [k for k in self.f if k.lower().endswith(".opf")]
            if not opfs:
                raise FormatNonGere("aucun fichier OPF : ce n'est pas un EPUB exploitable")
            chemin = sorted(opfs, key=len)[0]
            self.r.corrige("Fichier META-INF/container.xml absent ou faux : recréé.")
        self.chemin_opf = chemin
        self.dossier_opf = posixpath.dirname(chemin)
        self.f["META-INF/container.xml"] = CONTAINER_XML.format(chemin).encode("utf-8")

    def parser_opf(self):
        data = self.f[self.chemin_opf]
        texte, enc, _ = decoder_texte(data)
        try:
            root = parser_xml_strict(remplacer_entites(re.sub(r"^\s*<\?xml[^>]*\?>", "", texte)))
        except etree.XMLSyntaxError:
            root = parser_xml_tolerant(data)
            if root is None:
                raise FormatNonGere("le fichier OPF est illisible")
            self.r.corrige("Fichier OPF mal formé : réparé.")
        if nom_local(root.tag) != "package":
            raise FormatNonGere("le fichier OPF est illisible")
        if not root.tag.startswith("{"):
            for el in root.iter():
                if isinstance(el.tag, str) and not el.tag.startswith("{"):
                    el.tag = q(OPF, el.tag)
            self.r.corrige("Espace de noms OPF manquant : ajouté.")
        self.opf = root
        self.version = (root.get("version") or "2.0").strip()
        if not re.fullmatch(r"[23]\.\d", self.version):
            self.version = "2.0"
            root.set("version", "2.0")
            self.r.corrige("Version EPUB invalide dans l'OPF : remise à 2.0.")
        self.epub3 = self.version.startswith("3")
        self.metadata = root.find(q(OPF, "metadata"))
        if self.metadata is None:
            self.metadata = etree.Element(q(OPF, "metadata"), nsmap={"dc": DC, "opf": OPF})
            root.insert(0, self.metadata)
            self.r.corrige("Bloc de métadonnées absent : recréé.")
        self.manifest = root.find(q(OPF, "manifest"))
        if self.manifest is None:
            raise FormatNonGere("l'OPF n'a pas de manifeste")
        self.spine = root.find(q(OPF, "spine"))
        if self.spine is None:
            self.spine = etree.SubElement(root, q(OPF, "spine"))

    def identifiants(self):
        ids = []
        uid = self.opf.get("unique-identifier")
        for e in self.metadata.iter(q(DC, "identifier")):
            if e.text and e.get("id") == uid:
                ids.insert(0, e.text.strip())
            elif e.text:
                ids.append(e.text.strip())
        return ids

    def chemin_item(self, href):
        return posixpath.normpath(posixpath.join(self.dossier_opf, unquote(href or "")))

    def href_item(self, chemin):
        return posixpath.relpath(chemin, self.dossier_opf or ".")

    # ---------------------------------------------------------- métadonnées
    def reparer_metadonnees(self, nom_source):
        md = self.metadata
        # titre
        titres = [e for e in md.iter(q(DC, "title")) if e.text and e.text.strip()]
        if not titres:
            for e in list(md.iter(q(DC, "title"))):
                md.remove(e)
            t = etree.SubElement(md, q(DC, "title"))
            t.text = posixpath.splitext(os.path.basename(nom_source))[0].replace("_", " ")
            self.r.corrige("Titre absent : « %s » utilisé." % t.text)
            titres = [t]
        self.titre = " ".join(titres[0].text.split())
        auteurs = [" ".join(e.text.split()) for e in md.iter(q(DC, "creator")) if e.text and e.text.strip()]
        self.auteur = auteurs[0] if auteurs else None
        if not auteurs:
            self.r.alerte("Aucun auteur indiqué dans le livre.")

        # langue : LA cause n°1 des refus d'Amazon
        langs = list(md.iter(q(DC, "language")))
        valides = []
        for e in langs:
            n = normaliser_langue(e.text)
            if n:
                valides.append((e, n))
        devinee = deviner_langue(self.textes_echantillon())
        if not valides:
            choix = devinee or self.opt.get("langue", "fr")
            for e in langs:
                md.remove(e)
            nouv = etree.SubElement(md, q(DC, "language"))
            nouv.text = choix
            if langs:
                ancien = ", ".join(repr(e.text or "") for e in langs)
                self.r.corrige("Langue invalide (%s) remplacée par « %s » — cause n°1 des refus Amazon."
                               % (ancien, choix))
            else:
                self.r.corrige("Langue absente : « %s » ajoutée — cause n°1 des refus Amazon." % choix)
            self.langue = choix
        else:
            e0, n0 = valides[0]
            if (e0.text or "").strip() != n0:
                self.r.corrige("Code de langue corrigé : « %s » -> « %s »." % (e0.text.strip(), n0))
                e0.text = n0
            for e in langs:
                if e is not e0:
                    md.remove(e)
            if len(langs) > 1:
                self.r.corrige("Plusieurs langues déclarées : une seule gardée (« %s »)." % n0)
            self.langue = n0
            if devinee and devinee != n0.split("-")[0]:
                self.r.alerte("La langue déclarée est « %s » mais le texte ressemble à du « %s »."
                              % (n0, devinee))

        # identifiant unique
        uid = self.opf.get("unique-identifier")
        idents = list(md.iter(q(DC, "identifier")))
        if not any(e.get("id") == uid and e.text and e.text.strip() for e in idents):
            cible = next((e for e in idents if e.text and e.text.strip()), None)
            if cible is None:
                cible = etree.SubElement(md, q(DC, "identifier"))
                cible.text = "urn:uuid:" + str(uuid.uuid4())
            if not cible.get("id"):
                cible.set("id", uid or "bookid")
            self.opf.set("unique-identifier", cible.get("id"))
            self.r.corrige("Identifiant unique du livre manquant ou cassé : réparé.")

        if self.epub3:
            mods = [m for m in md.iter(q(OPF, "meta")) if m.get("property") == "dcterms:modified"]
            if not mods:
                m = etree.SubElement(md, q(OPF, "meta"), property="dcterms:modified")
                m.text = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            elif len(mods) > 1:
                for m in mods[1:]:
                    md.remove(m)

    def textes_echantillon(self):
        textes = []
        total = 0
        for item in self.manifest.iter(q(OPF, "item")):
            mt = item.get("media-type", "")
            if "html" not in mt:
                continue
            ch = self.trouver(self.chemin_item(item.get("href")))
            if not ch:
                continue
            t = re.sub(r"<[^>]+>", " ", decoder_texte(self.f[ch])[0])
            textes.append(html_mod.unescape(t))
            total += len(t)
            if total > 80000:
                break
        return textes

    # ------------------------------------------------------------ manifeste
    def reparer_manifeste(self):
        vus_ids = set()
        vus_chemins = {}
        self.items = OrderedDict()   # id -> (item, chemin)
        retires = []
        for item in list(self.manifest):
            if not isinstance(item.tag, str) or nom_local(item.tag) != "item":
                continue
            href = item.get("href")
            chemin = self.trouver(self.chemin_item(href)) if href else None
            if not chemin:
                retires.append(href or "(vide)")
                self.manifest.remove(item)
                continue
            if self.href_item(chemin) != unquote(href or ""):
                item.set("href", self.href_item(chemin))
                self.r.corrige("Lien du manifeste corrigé (majuscules/accents) : %s" % posixpath.basename(chemin))
            if chemin in vus_chemins:
                ancien_id = vus_chemins[chemin]
                self.remplacer_idref(item.get("id"), ancien_id)
                self.manifest.remove(item)
                self.r.corrige("Fichier déclaré deux fois dans le manifeste : doublon retiré.")
                continue
            ident = item.get("id") or ""
            if not NOM_XML.match(ident) or ident in vus_ids:
                nouvel = "item%d" % (len(vus_ids) + 1)
                while nouvel in vus_ids:
                    nouvel += "x"
                self.remplacer_idref(ident, nouvel)
                item.set("id", nouvel)
                ident = nouvel
                self.r.corrige("Identifiant de manifeste invalide ou en double : corrigé.")
            vus_ids.add(ident)
            vus_chemins[chemin] = ident
            ext = posixpath.splitext(chemin)[1].lower()
            mt = (item.get("media-type") or "").strip().lower()
            attendu = TYPES_MEDIA.get(ext)
            if attendu and mt != attendu:
                polices = ("font/", "application/font", "application/vnd.ms-opentype", "application/x-font")
                if not (attendu.startswith("font/") and mt.startswith(polices)) and \
                        not (ext == ".xml" and mt):
                    item.set("media-type", attendu)
                    self.r.corrige("Type de fichier corrigé dans le manifeste : %s (%s -> %s)."
                                   % (posixpath.basename(chemin), mt or "vide", attendu))
            self.items[ident] = (item, chemin)
        if retires:
            self.r.corrige("%d fichier(s) déclaré(s) mais absent(s) du livre : retiré(s) du manifeste (%s)."
                           % (len(retires), ", ".join(posixpath.basename(x) for x in retires[:5])))

        # fichiers présents mais non déclarés
        declares = {c for _, c in self.items.values()}
        ajoutes = 0
        jetes = []
        for chemin in list(self.f):
            if chemin in declares or chemin in ("mimetype", self.chemin_opf) or chemin.startswith("META-INF/"):
                continue
            ext = posixpath.splitext(chemin)[1].lower()
            mt = TYPES_MEDIA.get(ext)
            if not mt or mt == "application/javascript":
                jetes.append(chemin)
                del self.f[chemin]
                continue
            n = 1
            while "ajout%d" % n in self.items:
                n += 1
            item = etree.SubElement(self.manifest, q(OPF, "item"), id="ajout%d" % n,
                                    href=self.href_item(chemin), **{"media-type": mt})
            self.items["ajout%d" % n] = (item, chemin)
            ajoutes += 1
        if ajoutes:
            self.r.corrige("%d fichier(s) présent(s) mais non déclaré(s) : ajouté(s) au manifeste." % ajoutes)
        if jetes:
            self.r.corrige("%d fichier(s) inutile(s) retiré(s) (%s)."
                           % (len(jetes), ", ".join(posixpath.basename(x) for x in jetes[:4])))
        self.rebuild_lower()

    def remplacer_idref(self, ancien, nouveau):
        if not ancien:
            return
        for ir in self.spine.iter(q(OPF, "itemref")):
            if ir.get("idref") == ancien:
                ir.set("idref", nouveau)
        if self.spine.get("toc") == ancien:
            self.spine.set("toc", nouveau)
        for m in self.metadata.iter(q(OPF, "meta")):
            if m.get("name") == "cover" and m.get("content") == ancien:
                m.set("content", nouveau)

    # ---------------------------------------------------------------- spine
    def reparer_spine(self):
        vus = set()
        retires = 0
        for ir in list(self.spine):
            if not isinstance(ir.tag, str) or nom_local(ir.tag) != "itemref":
                continue
            idr = ir.get("idref")
            ok = idr in self.items and "html" in (self.items[idr][0].get("media-type") or "")
            if not ok or idr in vus:
                self.spine.remove(ir)
                retires += 1
                continue
            vus.add(idr)
        if retires:
            self.r.corrige("%d entrée(s) invalide(s) retirée(s) de l'ordre de lecture." % retires)
        if not len(self.spine.findall(q(OPF, "itemref"))):
            for ident, (item, chemin) in self.items.items():
                props = item.get("properties") or ""
                if item.get("media-type") == "application/xhtml+xml" and "nav" not in props.split():
                    etree.SubElement(self.spine, q(OPF, "itemref"), idref=ident)
            self.r.corrige("Ordre de lecture vide : reconstruit à partir des fichiers du livre.")

    # ------------------------------------------------------- documents XHTML
    def reparer_documents(self):
        self.docs = OrderedDict()     # chemin -> root
        self.doctypes = {}
        reencodes, reconstruits, decl = [], [], []
        scripts = 0
        for ident, (item, chemin) in self.items.items():
            if item.get("media-type") != "application/xhtml+xml":
                continue
            data = self.f[chemin]
            texte, enc, declare = decoder_texte(data)
            if enc != "utf-8" or (declare and declare.replace("_", "-") not in ("utf-8", "utf8")):
                reencodes.append(posixpath.basename(chemin))
            elif not re.match(rb"(\xef\xbb\xbf)?\s*<\?xml[^>]*encoding=[\"']utf-?8[\"']", data[:300], re.I):
                decl.append(chemin)
            texte = re.sub(r"^\s*<\?xml[^>]*\?>", "", texte)
            m = re.match(r"\s*(<!DOCTYPE[^>\[]*(\[[^\]]*\])?\s*>)", texte, re.I)
            doctype = m.group(1) if m else None
            if doctype and "[" in doctype:
                doctype = None
            corps = texte[m.end():] if m else texte
            corps = remplacer_entites(corps)
            root = None
            try:
                root = parser_xml_strict(corps)
                if nom_local(root.tag) != "html":
                    raise ValueError("pas un document html")
                if mettre_namespace_xhtml(root):
                    self.r.corrige("Espace de noms XHTML ajouté : %s" % posixpath.basename(chemin))
            except (etree.XMLSyntaxError, ValueError):
                try:
                    doc = lhtml.document_fromstring(corps if corps.strip() else "<html><body></body></html>")
                    root = html_vers_xhtml(doc)
                    reconstruits.append(posixpath.basename(chemin))
                    doctype = None
                except Exception:
                    self.r.alerte("Fichier illisible laissé tel quel : %s" % posixpath.basename(chemin))
                    continue
            # nettoyage
            for s in list(root.iter(q(XHTML, "script"))):
                retirer_element(s)
                scripts += 1
            head = root.find(q(XHTML, "head"))
            if head is None:
                head = etree.Element(q(XHTML, "head"))
                root.insert(0, head)
            if root.find(q(XHTML, "body")) is None:
                body = etree.SubElement(root, q(XHTML, "body"))
                for e in list(root):
                    if e is not head and e is not body:
                        body.append(e)
            titre = head.find(q(XHTML, "title"))
            if titre is None:
                titre = etree.Element(q(XHTML, "title"))
                head.insert(0, titre)
            if not (titre.text or "").strip():
                titre.text = self.titre
            for meta in head.findall(q(XHTML, "meta")):
                if meta.get("charset") and meta.get("charset").lower() != "utf-8":
                    meta.set("charset", "utf-8")
                ct = meta.get("content") or ""
                if (meta.get("http-equiv") or "").lower() == "content-type" and "charset" in ct.lower() \
                        and "utf-8" not in ct.lower():
                    meta.set("content", "text/html; charset=utf-8")
            self.docs[chemin] = root
            self.doctypes[chemin] = doctype
        if decl:
            self.r.corrige("Déclaration d'encodage UTF-8 ajoutée en tête de %d fichier(s) "
                           "(sans elle, Amazon lit le texte de travers et peut refuser le livre)." % len(decl))
        if reencodes:
            self.r.corrige("Texte réencodé en UTF-8 : %s" % ", ".join(reencodes[:5]) +
                           (" …" if len(reencodes) > 5 else ""))
        if reconstruits:
            self.r.corrige("HTML mal formé réparé dans %d fichier(s) : %s" %
                           (len(reconstruits), ", ".join(reconstruits[:5]) + (" …" if len(reconstruits) > 5 else "")))
        if scripts:
            self.r.corrige("%d script(s) retiré(s) (non pris en charge par la Kindle)." % scripts)

    # ------------------------------------------------------- sommaire NCX/nav
    def item_par_prop(self, prop):
        for ident, (item, chemin) in self.items.items():
            if prop in (item.get("properties") or "").split():
                return ident, item, chemin
        return None

    def entrees_depuis_spine(self):
        entrees = []
        for ir in self.spine.iter(q(OPF, "itemref")):
            item, chemin = self.items[ir.get("idref")]
            root = self.docs.get(chemin)
            txt = None
            if root is not None:
                for h in root.iter(q(XHTML, "h1"), q(XHTML, "h2"), q(XHTML, "h3")):
                    txt = " ".join("".join(h.itertext()).split())
                    if txt:
                        break
            if txt:
                entrees.append((txt[:80], chemin))
        if not entrees:
            for n, ir in enumerate(self.spine.iter(q(OPF, "itemref")), 1):
                entrees.append(("Partie %d" % n, self.items[ir.get("idref")][1]))
        return entrees

    def entrees_depuis_ncx(self, chemin_ncx):
        root = parser_xml_tolerant(self.f[chemin_ncx])
        entrees = []
        if root is None:
            return entrees
        for np_ in root.iter(q(NCX, "navPoint")):
            lab = np_.find(q(NCX, "navLabel"))
            cont = np_.find(q(NCX, "content"))
            if lab is None or cont is None:
                continue
            cible, frag = resoudre(chemin_ncx, cont.get("src"))
            cible = self.trouver(cible)
            if cible:
                entrees.append((" ".join("".join(lab.itertext()).split()) or "Chapitre",
                                cible + ("#" + frag if frag else "")))
        return entrees

    def reparer_sommaires(self):
        toc_id = self.spine.get("toc")
        ncx = None
        if toc_id in self.items and self.items[toc_id][0].get("media-type") == "application/x-dtbncx+xml":
            ncx = self.items[toc_id][1]
        else:
            for ident, (item, chemin) in self.items.items():
                if item.get("media-type") == "application/x-dtbncx+xml":
                    ncx = chemin
                    self.spine.set("toc", ident)
                    if toc_id != ident:
                        self.r.corrige("Lien vers le sommaire (NCX) réparé.")
                    break
        nav = self.item_par_prop("nav") if self.epub3 else None
        if self.epub3 and nav is None:
            entrees = self.entrees_depuis_ncx(ncx) if ncx else []
            entrees = entrees or self.entrees_depuis_spine()
            chemin_nav = posixpath.join(self.dossier_opf, "nav_kwindle.xhtml")
            self.f[chemin_nav] = fabriquer_nav(entrees, self.titre, chemin_nav, self.langue)
            item = etree.SubElement(self.manifest, q(OPF, "item"), id="nav_kwindle",
                                    href=self.href_item(chemin_nav), properties="nav",
                                    **{"media-type": "application/xhtml+xml"})
            self.items["nav_kwindle"] = (item, chemin_nav)
            self.docs[chemin_nav] = parser_xml_strict(self.f[chemin_nav].decode("utf-8").split("\n", 2)[2])
            self.doctypes[chemin_nav] = DOCTYPE_EPUB3
            self.r.corrige("Sommaire EPUB 3 (nav) absent : créé.")
        if ncx is None and not self.epub3:
            entrees = self.entrees_depuis_spine()
            chemin_ncx = posixpath.join(self.dossier_opf, "toc.ncx")
            while chemin_ncx in self.f:
                chemin_ncx = chemin_ncx.replace(".ncx", "_k.ncx")
            uid = self.identifiants()[0] if self.identifiants() else "inconnu"
            self.f[chemin_ncx] = fabriquer_ncx(entrees, uid, self.titre, chemin_ncx)
            etree.SubElement(self.manifest, q(OPF, "item"), id="ncx_kwindle",
                             href=self.href_item(chemin_ncx), **{"media-type": "application/x-dtbncx+xml"})
            self.items["ncx_kwindle"] = (self.manifest[-1], chemin_ncx)
            self.spine.set("toc", "ncx_kwindle")
            self.r.corrige("Sommaire (toc.ncx) absent : créé à partir des chapitres.")
        self.chemin_ncx = ncx if ncx else (self.items.get("ncx_kwindle", (None, None))[1])
        self.rebuild_lower()

    # --------------------------------------------- images (format / poids)
    def traiter_images(self, agressif=False):
        if Image is None:
            if agressif:
                self.r.alerte("Pillow n'est pas installé : impossible d'alléger les images.")
            return {}
        renommages = {}
        allegees = 0
        converties = 0
        cote_max = 1600 if agressif else 3000
        poids_max = 600 * 1024 if agressif else 4 * 1024 * 1024
        for ident, (item, chemin) in list(self.items.items()):
            mt = item.get("media-type")
            if mt not in IMAGES_OK and mt not in IMAGES_A_CONVERTIR:
                continue
            if mt == "image/svg+xml":
                continue
            data = self.f.get(chemin)
            if not data:
                continue
            try:
                img = Image.open(io.BytesIO(data))
                img.load()
            except Exception:
                continue
            convertir = mt in IMAGES_A_CONVERTIR
            trop_grande = max(img.size) > cote_max or len(data) > poids_max
            if not convertir and not trop_grande:
                continue
            if mt == "image/gif" and getattr(img, "is_animated", False):
                continue
            if trop_grande and max(img.size) > cote_max:
                img.thumbnail((cote_max, cote_max), Image.LANCZOS)
            transparence = img.mode in ("RGBA", "LA", "P") and (
                "transparency" in img.info or img.mode in ("RGBA", "LA"))
            buf = io.BytesIO()
            if mt == "image/png" or (convertir and transparence):
                fmt, ext, nmt = "PNG", ".png", "image/png"
                if agressif and not transparence:
                    img = img.convert("L") if img.mode in ("L", "LA") else img.convert("RGB")
                    fmt, ext, nmt = "JPEG", ".jpg", "image/jpeg"
            elif mt == "image/gif" and not convertir:
                fmt, ext, nmt = "GIF", ".gif", "image/gif"
            else:
                fmt, ext, nmt = "JPEG", ".jpg", "image/jpeg"
            if fmt == "JPEG" and img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            kw = {"quality": 80 if agressif else 88, "optimize": True} if fmt == "JPEG" else {"optimize": True}
            try:
                img.save(buf, fmt, **kw)
            except Exception:
                continue
            nouv = buf.getvalue()
            if fmt == "PNG" and not transparence and len(nouv) > 2 * 1024 * 1024:
                # un PNG opaque de plus de 2 Mo, c'est une photo ou un scan : JPEG
                buf = io.BytesIO()
                img2 = img.convert("L") if img.mode in ("L", "LA") else img.convert("RGB")
                img2.save(buf, "JPEG", quality=80 if agressif else 88, optimize=True)
                nouv, ext, nmt = buf.getvalue(), ".jpg", "image/jpeg"
            if not convertir and nmt == mt and len(nouv) >= len(data):
                continue
            nouveau_chemin = chemin
            if nmt != mt:
                base = posixpath.splitext(chemin)[0]
                nouveau_chemin = base + ext
                while nouveau_chemin in self.f and nouveau_chemin != chemin:
                    base += "_k"
                    nouveau_chemin = base + ext
                del self.f[chemin]
                renommages[chemin] = nouveau_chemin
                item.set("media-type", nmt)
                item.set("href", self.href_item(nouveau_chemin))
                self.items[ident] = (item, nouveau_chemin)
            self.f[nouveau_chemin] = nouv
            if convertir:
                converties += 1
            else:
                allegees += 1
        if converties:
            self.r.corrige("%d image(s) dans un format refusé par la Kindle (WebP, BMP, TIFF) convertie(s)."
                           % converties)
        if allegees:
            self.r.corrige("%d image(s) trop lourde(s) allégée(s)%s." %
                           (allegees, " pour passer sous la limite de 50 Mo" if agressif else ""))
        self.rebuild_lower()
        return renommages

    # ---------------------------------------- noms de fichiers à problèmes
    def assainir_noms(self):
        renommages = {}
        pris = set(self.f)
        for ident, (item, chemin) in list(self.items.items()):
            if chemin_valide(chemin):
                continue
            nouveau = nom_interne_sur(chemin)
            base, ext = posixpath.splitext(nouveau)
            n = 1
            while nouveau in pris:
                nouveau = "%s_%d%s" % (base, n, ext)
                n += 1
            pris.add(nouveau)
            self.f[nouveau] = self.f.pop(chemin)
            renommages[chemin] = nouveau
            item.set("href", self.href_item(nouveau))
            self.items[ident] = (item, nouveau)
            if chemin in self.docs:
                self.docs[nouveau] = self.docs.pop(chemin)
                self.doctypes[nouveau] = self.doctypes.pop(chemin)
            if chemin == self.chemin_ncx:
                self.chemin_ncx = nouveau
        if renommages:
            self.r.corrige("%d fichier(s) interne(s) au nom problématique (espaces, accents…) renommé(s)."
                           % len(renommages))
        self.rebuild_lower()
        return renommages

    # --------------------------------------------- liens dans les documents
    def reecrire_liens(self, renommages):
        ids_body = {}
        for chemin, root in self.docs.items():
            body = root.find(q(XHTML, "body"))
            if body is not None and body.get("id"):
                ids_body[chemin] = body.get("id")
        ren_lower = {k.lower(): v for k, v in renommages.items()}
        liens_body = 0
        liens_morts = 0
        images_mortes = 0

        def nouvelle_ref(depuis, val, est_lien):
            nonlocal liens_body
            abs_, frag = resoudre(depuis, val)
            if abs_ is None:
                return val
            if abs_ in renommages:
                vraie = renommages[abs_]
            else:
                vraie = self.trouver(abs_) or ren_lower.get(abs_.lower())
            if vraie is None or vraie not in self.f:
                return None
            if frag and ids_body.get(vraie) == frag:
                frag = ""
                liens_body += 1
            rel = relatif(depuis, vraie) if vraie != depuis else ""
            if not rel and not frag:
                rel = posixpath.basename(vraie)
            return rel + ("#" + frag if frag else "")

        for chemin, root in self.docs.items():
            for el in list(root.iter()):
                if not isinstance(el.tag, str):
                    continue
                for attr in ATTRS_REF + (q(XLINK, "href"),):
                    val = el.get(attr)
                    if val is None:
                        continue
                    if attr == "src" and nom_local(el.tag) == "img" and not val.strip():
                        retirer_element(el)
                        images_mortes += 1
                        break
                    if attr == "href" and nom_local(el.tag) == "a" and val.startswith("#"):
                        frag = val[1:]
                        if ids_body.get(chemin) == frag:
                            el.set("href", posixpath.basename(chemin))
                            liens_body += 1
                        continue
                    nouv = nouvelle_ref(chemin, val, nom_local(el.tag) == "a")
                    if nouv is None:
                        tag = nom_local(el.tag)
                        if tag == "img":
                            retirer_element(el)
                            images_mortes += 1
                            break
                        elif tag == "a":
                            del el.attrib[attr]
                            liens_morts += 1
                        elif tag == "link":
                            retirer_element(el)
                            break
                        else:
                            del el.attrib[attr]
                    elif nouv != val:
                        el.set(attr, nouv)
        # NCX
        if self.chemin_ncx and self.chemin_ncx in self.f:
            ncx = parser_xml_tolerant(self.f[self.chemin_ncx])
            if ncx is not None:
                for cont in ncx.iter(q(NCX, "content")):
                    val = cont.get("src")
                    nouv = nouvelle_ref(self.chemin_ncx, val, True) if val else None
                    if nouv is None:
                        np_ = cont.getparent()
                        par = np_.getparent() if np_ is not None else None
                        if par is not None and nom_local(np_.tag) == "navPoint":
                            par.remove(np_)
                            liens_morts += 1
                    elif nouv != val:
                        cont.set("src", nouv)
                uid = self.identifiants()
                for meta in ncx.iter(q(NCX, "meta")):
                    if meta.get("name") == "dtb:uid" and uid:
                        meta.set("content", uid[0])
                self.f[self.chemin_ncx] = serialiser_xml(ncx)
        # CSS
        for ident, (item, chemin) in self.items.items():
            if item.get("media-type") != "text/css":
                continue
            texte, enc, declare = decoder_texte(self.f[chemin])
            texte2 = re.sub(r"@charset\s+[\"'][^\"']*[\"']\s*;", '@charset "utf-8";', texte, count=1)

            def rep_url(m):
                val = m.group(2).strip()
                nouv = nouvelle_ref(chemin, val, False)
                if nouv is None or nouv == val:
                    return m.group(0)
                return "url(%s%s%s)" % (m.group(1), nouv, m.group(1))

            def rep_import(m):
                val = m.group(2).strip()
                nouv = nouvelle_ref(chemin, val, False)
                if nouv is None or nouv == val:
                    return m.group(0)
                return "@import %s%s%s" % (m.group(1), nouv, m.group(1))
            texte2 = re.sub(r"url\(\s*([\"']?)([^\"')]+)\1\s*\)", rep_url, texte2)
            texte2 = re.sub(r"@import\s+([\"'])([^\"']+)\1", rep_import, texte2)
            if texte2 != texte or enc != "utf-8":
                self.f[chemin] = texte2.encode("utf-8")
        # guide (EPUB 2)
        guide = self.opf.find(q(OPF, "guide"))
        if guide is not None:
            for ref in list(guide):
                if not isinstance(ref.tag, str):
                    continue
                val = ref.get("href")
                nouv = nouvelle_ref(self.chemin_opf, val, True) if val else None
                if nouv is None:
                    guide.remove(ref)
                elif nouv != val:
                    ref.set("href", nouv)
            if not len(guide):
                self.opf.remove(guide)
        if liens_body:
            self.r.corrige("%d lien(s) vers un identifiant de <body> corrigé(s) (bug connu de Send to Kindle)."
                           % liens_body)
        if liens_morts:
            self.r.corrige("%d lien(s) vers des pages inexistantes neutralisé(s)." % liens_morts)
        if images_mortes:
            self.r.corrige("%d image(s) manquante(s) ou vide(s) retirée(s) du texte." % images_mortes)

    # ---------------------------------------------------------- couverture
    def reparer_couverture(self):
        cover_meta = None
        for m in self.metadata.iter(q(OPF, "meta")):
            if m.get("name") == "cover":
                cover_meta = m
        prop = self.item_par_prop("cover-image")
        if cover_meta is not None and cover_meta.get("content") not in self.items:
            # parfois content = chemin de l'image au lieu de l'id
            cible = self.trouver(self.chemin_item(cover_meta.get("content")))
            ident = next((i for i, (it, c) in self.items.items() if c == cible), None)
            if ident:
                cover_meta.set("content", ident)
                self.r.corrige("Référence de couverture réparée.")
            elif prop:
                cover_meta.set("content", prop[0])
            else:
                self.metadata.remove(cover_meta)
                cover_meta = None
        if cover_meta is None and prop:
            etree.SubElement(self.metadata, q(OPF, "meta"), name="cover", content=prop[0])
        if self.epub3 and cover_meta is not None and not prop:
            item = self.items.get(cover_meta.get("content"), (None,))[0]
            if item is not None and (item.get("media-type") or "").startswith("image/"):
                props = (item.get("properties") or "").split()
                item.set("properties", " ".join(props + ["cover-image"]))

    # ----------------------------------------------------------- écriture
    def serialiser(self):
        for chemin, root in self.docs.items():
            if chemin not in self.f:
                continue
            dt = self.doctypes.get(chemin) or (DOCTYPE_EPUB3 if self.epub3 else DOCTYPE_EPUB2)
            data = serialiser_xml(root, dt)
            try:
                parser_xml_strict(data.decode("utf-8").split("\n", 2)[2])
            except etree.XMLSyntaxError:
                self.r.alerte("Vérification finale ratée pour %s : fichier d'origine gardé."
                              % posixpath.basename(chemin))
                continue
            self.f[chemin] = data
        self.f[self.chemin_opf] = serialiser_xml(self.opf)

    def executer(self, nom_source):
        verifier_drm(self.f)
        self.localiser_opf()
        self.parser_opf()
        traiter_chiffrement(self.f, self.identifiants(), self.r)
        self.rebuild_lower()
        self.reparer_manifeste()
        self.reparer_metadonnees(nom_source)
        self.reparer_spine()
        self.reparer_documents()
        self.reparer_sommaires()
        self.reparer_couverture()
        renommages = self.assainir_noms()
        ren_images = self.traiter_images(agressif=False)
        for ancien, nouveau in list(renommages.items()):
            while nouveau in ren_images:        # renommé puis converti
                nouveau = ren_images[nouveau]
            renommages[ancien] = nouveau
        for ancien, nouveau in ren_images.items():
            renommages.setdefault(ancien, nouveau)
        self.reecrire_liens(renommages)
        self.serialiser()
        if len(ecrire_epub(self.f)) > CIBLE_MAIL and Image is not None:
            ren2 = self.traiter_images(agressif=True)
            if ren2:
                self.reecrire_liens(ren2)
            self.serialiser()
        return self.f


def ecrire_epub(fichiers):
    buf = io.BytesIO()
    maintenant = datetime.datetime.now().timetuple()[:6]
    with zipfile.ZipFile(buf, "w") as z:
        zi = zipfile.ZipInfo("mimetype", date_time=maintenant)
        zi.compress_type = zipfile.ZIP_STORED
        z.writestr(zi, b"application/epub+zip")
        cont = fichiers.get("META-INF/container.xml")
        if cont:
            z.writestr(zipfile.ZipInfo("META-INF/container.xml", date_time=maintenant), cont,
                       compress_type=zipfile.ZIP_DEFLATED)
        for nom, data in fichiers.items():
            if nom in ("mimetype", "META-INF/container.xml"):
                continue
            ext = posixpath.splitext(nom)[1].lower()
            meth = zipfile.ZIP_STORED if ext in (".jpg", ".jpeg", ".png", ".gif", ".woff2") else zipfile.ZIP_DEFLATED
            z.writestr(zipfile.ZipInfo(nom, date_time=maintenant), data, compress_type=meth)
    return buf.getvalue()


# --------------------------------------------------------------------------
# Point d'entrée
# --------------------------------------------------------------------------

def traiter_livre(chemin, dossier_sortie, options=None):
    """Répare/convertit un livre. Renvoie un Resultat (jamais d'exception)."""
    options = options or {}
    res = Resultat(chemin)
    r = res.rapport
    try:
        fmt = detecter_format(chemin)
        ext = os.path.splitext(chemin)[1].lower()
        res.format_source = fmt
        if fmt == "zip":
            fichiers = lire_zip(chemin, r)
        elif fmt == "mobi":
            if ext == ".epub":
                r.info("Ce fichier n'est pas un vrai EPUB : c'est un MOBI (ancien format Kindle) "
                       "renommé en .epub. C'est pour ça qu'Amazon le refusait.")
            else:
                r.info("Fichier au format Kindle (MOBI/AZW) : Amazon ne l'accepte plus par e-mail, "
                       "conversion en EPUB.")
            genre, donnees = mobi_vers_epub(chemin, r)
            if genre == "pdf":
                os.makedirs(dossier_sortie, exist_ok=True)
                res.sortie = os.path.join(dossier_sortie, nom_fichier_sur(
                    os.path.splitext(os.path.basename(chemin))[0]) + ".pdf")
                with open(res.sortie, "wb") as f:
                    f.write(donnees)
                res.titre = os.path.splitext(os.path.basename(chemin))[0]
                r.info("Livre « Print Replica » : extrait en PDF (accepté tel quel par Amazon).")
                res.ok = True
                return res
            fichiers = donnees
        elif fmt == "pdf":
            res.titre = os.path.splitext(os.path.basename(chemin))[0]
            res.sortie = chemin
            r.info("PDF : Amazon l'accepte tel quel, aucune conversion nécessaire.")
            res.ok = True
            return res
        elif fmt in ("topaz", "kfx"):
            raise FormatNonGere("format Kindle %s : impossible à convertir ici" % fmt.upper())
        elif fmt == "palmdoc":
            raise FormatNonGere("ancien format PalmDoc non pris en charge")
        else:
            raise FormatNonGere("ce fichier n'est ni un EPUB ni un fichier Kindle reconnu")

        rep = Reparateur(fichiers, r, options)
        fichiers = rep.executer(chemin)
        res.titre, res.auteur = rep.titre, rep.auteur
        donnees = ecrire_epub(fichiers)

        os.makedirs(dossier_sortie, exist_ok=True)
        nom = nom_fichier_sur(res.titre + (" - " + res.auteur if res.auteur else ""))
        res.sortie = os.path.join(dossier_sortie, nom + ".epub")
        if os.path.abspath(res.sortie) == os.path.abspath(chemin):
            res.sortie = os.path.join(dossier_sortie, nom + " (Kindle).epub")
        with open(res.sortie, "wb") as f:
            f.write(donnees)
        if len(donnees) > LIMITE_MAIL:
            r.alerte("Le livre fait %.0f Mo : trop gros pour l'e-mail (50 Mo max). "
                     "Passe par amazon.fr/sendtokindle (jusqu'à 200 Mo)." % (len(donnees) / 1048576))
        if not r.corrections and fmt == "zip":
            r.info("Aucun problème trouvé : le livre était déjà propre.")
        res.ok = True
    except LivreProtege:
        r.erreur("Ce livre est protégé par des DRM : impossible de le modifier ou de l'envoyer. "
                 "Il faut le récupérer depuis la boutique ou la plateforme qui le fournit.")
    except FormatNonGere as exc:
        r.erreur("Impossible de traiter ce fichier : %s." % exc)
    except Exception as exc:  # on ne plante jamais l'appli
        r.erreur("Erreur inattendue : %s: %s" % (type(exc).__name__, exc))
    return res
