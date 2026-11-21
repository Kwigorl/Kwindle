package fr.kwigorl.kwindle

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.DpSize
import androidx.compose.ui.unit.dp

/**
 * Saveur Rekindle : envoi à la Kindle (adresse @kindle.com), requin lecteur, habillage océan.
 * L'autre saveur (Koboa) a le même fichier dans src/koboa.
 */
object Saveur {
    const val NOM = "Rekindle"
    /** Le nom en morceaux : true = morceau dans la couleur d'accent (« Rekin » en corail). */
    val PARTIES_NOM = listOf("Rekin" to true, "dle" to false)
    const val LISEUSE = "Kindle"
    const val TOME_DANS_TITRE = true

    // ------------------------------------------------------------------ couleurs
    val principale = Color(0xFF0A2E4A)        // bleu marine
    val principaleClaire = Color(0xFF123E5F)
    val secondaire = Color(0xFF127C9E)        // océan
    val accent = Color(0xFFFF6B57)            // corail
    val accentClair = Color(0xFFFF8A78)
    val creme = Color(0xFFF4F1E8)
    val brume = Color(0xFFA9C7DA)
    val primaireSombre = Color(0xFF8FD0E6)
    val varianteClaire = Color(0xFFDCEFF5)
    val contourClair = Color(0xFF8AA4B8)
    val contourSombre = Color(0xFF5B7488)

    val paletteClaire = Palette(
        fond = Color(0xFFE9F6FA), carte = Color.White, bordure = Color(0xFFCFE6EE), bordureKo = Color(0xFFF3D3D3),
        texte = principale, texteDoux = Color(0xFF3F5566), vagueVide = Color(0xFFCFE6EE),
        bouton = principale, texteBouton = creme,
        puces = mapOf(
            "envoye" to (Color(0xFFD7F0F6) to Color(0xFF0B5A70)),
            "repare" to (Color(0xFFFFE2DC) to Color(0xFFA8321F)),
            "ko" to (Color(0xFFFCE4E4) to Color(0xFF9B1C1C)),
            "encours" to (Color(0xFFDCEFF5) to Color(0xFF0E6A86)),
            "neutre" to (Color(0xFFE4ECF1) to Color(0xFF34495A)),
            "torrent" to (Color(0xFFF6E7C8) to Color(0xFF6E4A00)),
        ),
    )

    val paletteSombre = Palette(
        fond = Color(0xFF06213A), carte = Color(0xFF0D3050), bordure = Color(0xFF1B4868), bordureKo = Color(0xFF6B2A2A),
        texte = Color(0xFFE8F1F6), texteDoux = brume, vagueVide = Color(0xFF1B4868),
        bouton = secondaire, texteBouton = Color.White,
        puces = mapOf(
            "envoye" to (Color(0xFF0F4B5E) to Color(0xFFBDEBF7)),
            "repare" to (Color(0xFF5A2A22) to Color(0xFFFFC9BE)),
            "ko" to (Color(0xFF5A1F1F) to Color(0xFFFFC4C4)),
            "encours" to (Color(0xFF123F5C) to Color(0xFFA9DDEE)),
            "neutre" to (Color(0xFF1E3D55) to Color(0xFFC9D8E3)),
            "torrent" to (Color(0xFF4A3A14) to Color(0xFFF6DFA8)),
        ),
    )

    // ------------------------------------------------------------------ images (taille affichée)
    val tailleTete = DpSize(32.dp, 36.dp)
    val tailleTeteBarre = DpSize(30.dp, 34.dp)
    val tailleMascotte = DpSize(128.dp, 135.dp)
    val tailleDeco = DpSize(40.dp, 34.dp)
    val tailleProgression = DpSize(26.dp, 22.dp)
    val tailleTransforme = DpSize(27.dp, 30.dp)
    const val DESCRIPTION_MASCOTTE = "Le requin lecteur de Rekindle"

    // ------------------------------------------------------------------ textes
    const val ENVOYER_A = "Envoyer à ma Kindle"
    const val SECTION_LISEUSE = "Ta Kindle"
    const val LIBELLE_ADRESSE = "Adresse Kindle"
    const val EXEMPLE_ADRESSE = "prenom_xxx@kindle.com"
    const val ADRESSE_A_REGLER = "Adresse Kindle à régler ›"
    const val AIDE_ADRESSE =
        "Sur amazon.fr : Gérer votre contenu et vos appareils → Préférences → Paramètres des " +
            "documents personnels. Sur la même page, ajoute l'adresse d'envoi ci-dessous à la « liste " +
            "des adresses e-mail approuvées », sinon Amazon ignore les livres."
    const val PAGE_AIDE = "https://www.amazon.fr/mycd"
    const val LIBELLE_PAGE_AIDE = "Ouvrir la page Amazon"
    const val AIDE_TOME =
        "Pour que la Kindle range les séries dans l'ordre quand elle trie par titre : « Le Trône de " +
            "fer, Tome 3 : La Bataille des rois » devient « Le Trône de fer 03 — La Bataille des rois ». " +
            "Le numéro vient des informations du livre (calibre) ou de son titre."
    const val VERS_LA_LISEUSE = "à ta Kindle"

    fun apresUnEnvoi() =
        "Envoyé en un seul e-mail. Si Amazon demande « Vérifiez votre demande », " +
            "clique sur le lien du mail : sans ça, les livres n'arrivent pas."

    fun apresPlusieursEnvois(n: Int) =
        "Envoyé en $n e-mails. Amazon peut demander une vérification pour " +
            "chacun : clique sur chaque lien « Vérifier la demande »."

    /** Ce qui ne va pas dans l'adresse de la liseuse, ou null. */
    fun problemeAdresse(adresse: String): String? {
        val k = adresse.trim().lowercase()
        return when {
            k.isEmpty() -> "Indique ton adresse Kindle dans les réglages."
            !(k.endsWith("@kindle.com") || k.endsWith("@free.kindle.com")) ->
                "L'adresse Kindle doit finir par @kindle.com."
            else -> null
        }
    }
}
