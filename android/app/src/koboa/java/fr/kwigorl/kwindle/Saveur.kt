package fr.kwigorl.kwindle

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.DpSize
import androidx.compose.ui.unit.dp

/**
 * Saveur Koboa : envoi à la Kobo (la boîte mail que relève KoboaExpress), boa lecteur,
 * habillage jungle. L'autre saveur (Rekindle) a le même fichier dans src/rekindle.
 */
object Saveur {
    const val NOM = "Koboa"
    /** Le nom en morceaux : true = morceau dans la couleur d'accent (« boa » en ambre). */
    val PARTIES_NOM = listOf("Ko" to false, "boa" to true)
    const val LISEUSE = "Kobo"
    const val TOME_DANS_TITRE = false        // la Kobo range elle-même les séries (informations calibre)

    // ------------------------------------------------------------------ couleurs
    val principale = Color(0xFF12372A)        // vert jungle
    val principaleClaire = Color(0xFF1E4D3A)
    val secondaire = Color(0xFF3E9B5A)        // vert feuille
    val accent = Color(0xFFF4A93B)            // ambre (les yeux du boa)
    val accentClair = Color(0xFFFFC46B)
    val creme = Color(0xFFF6F1DE)
    val brume = Color(0xFFA8CBB4)
    val primaireSombre = Color(0xFF9FDCB0)
    val varianteClaire = Color(0xFFE2F1DE)
    val contourClair = Color(0xFF9DB8A5)
    val contourSombre = Color(0xFF5E7E69)

    val paletteClaire = Palette(
        fond = Color(0xFFEFF6EA), carte = Color.White, bordure = Color(0xFFD3E6CF), bordureKo = Color(0xFFF3D3D3),
        texte = principale, texteDoux = Color(0xFF46604F), vagueVide = Color(0xFFD3E6CF),
        bouton = principale, texteBouton = creme,
        puces = mapOf(
            "envoye" to (Color(0xFFD9EFD9) to Color(0xFF1F5E33)),
            "repare" to (Color(0xFFFFEBCB) to Color(0xFF8A5200)),
            "ko" to (Color(0xFFFCE4E4) to Color(0xFF9B1C1C)),
            "encours" to (Color(0xFFE2F1DE) to Color(0xFF2E7A47)),
            "neutre" to (Color(0xFFE6ECE4) to Color(0xFF3A4D40)),
            "torrent" to (Color(0xFFEDE3D3) to Color(0xFF5E4526)),
        ),
    )

    val paletteSombre = Palette(
        fond = Color(0xFF0B2419), carte = Color(0xFF123425), bordure = Color(0xFF28614A), bordureKo = Color(0xFF6B2A2A),
        texte = Color(0xFFE8F2EA), texteDoux = brume, vagueVide = Color(0xFF28614A),
        bouton = secondaire, texteBouton = Color.White,
        puces = mapOf(
            "envoye" to (Color(0xFF1A4A2E) to Color(0xFFC2EBCD)),
            "repare" to (Color(0xFF5A4116) to Color(0xFFFFD9A0)),
            "ko" to (Color(0xFF5A1F1F) to Color(0xFFFFC4C4)),
            "encours" to (Color(0xFF1C4630) to Color(0xFFB5E3C2)),
            "neutre" to (Color(0xFF203A2C) to Color(0xFFCADBD0)),
            "torrent" to (Color(0xFF4A3A1E) to Color(0xFFEAD7B0)),
        ),
    )

    // ------------------------------------------------------------------ images (taille affichée)
    val tailleTete = DpSize(36.dp, 33.dp)
    val tailleTeteBarre = DpSize(34.dp, 31.dp)
    val tailleMascotte = DpSize(122.dp, 135.dp)
    val tailleDeco = DpSize(40.dp, 34.dp)
    val tailleProgression = DpSize(28.dp, 21.dp)
    val tailleTransforme = DpSize(33.dp, 28.dp)
    const val DESCRIPTION_MASCOTTE = "Le boa lecteur de Koboa"

    // ------------------------------------------------------------------ textes
    const val ENVOYER_A = "Envoyer à ma Kobo"
    const val SECTION_LISEUSE = "Ta Kobo"
    const val LIBELLE_ADRESSE = "Adresse de la Kobo"
    const val EXEMPLE_ADRESSE = "prenom+kobo@gmail.com"
    const val ADRESSE_A_REGLER = "Adresse de la Kobo à régler ›"
    const val AIDE_ADRESSE =
        "C'est l'adresse que relève KoboaExpress, installé sur la Kobo : les livres envoyés là " +
            "arrivent tout seuls sur la liseuse à la connexion Wi-Fi suivante. Avec Gmail, " +
            "prenom+kobo@gmail.com arrive dans la boîte prenom@gmail.com."
    const val PAGE_AIDE = "https://github.com/Kwigorl/Kwindle/releases/tag/kobo"
    const val LIBELLE_PAGE_AIDE = "Télécharger KoboaExpress"
    const val AIDE_TOME =
        "Pour ranger les séries dans l'ordre quand la Kobo trie par titre : « Le Trône de fer, " +
            "Tome 3 : La Bataille des rois » devient « Le Trône de fer 03 — La Bataille des rois ». " +
            "Pas indispensable : la Kobo sait lire la série dans les informations du livre (calibre)."
    const val VERS_LA_LISEUSE = "à la Kobo"

    fun apresUnEnvoi() =
        "Envoyé ! Les livres arriveront sur la Kobo à sa prochaine connexion Wi-Fi " +
            "(KoboaExpress relève la boîte mail)."

    fun apresPlusieursEnvois(n: Int) =
        "Envoyé en $n e-mails. Les livres arriveront sur la Kobo à sa prochaine connexion Wi-Fi " +
            "(KoboaExpress relève la boîte mail)."

    /** Ce qui ne va pas dans l'adresse de la liseuse, ou null. */
    fun problemeAdresse(adresse: String): String? {
        val a = adresse.trim()
        return when {
            a.isEmpty() -> "Indique l'adresse e-mail de la Kobo (celle que relève KoboaExpress) dans les réglages."
            "@" !in a || " " in a || a.startsWith("@") || a.endsWith("@") ->
                "L'adresse de la Kobo n'est pas une adresse e-mail valide."
            else -> null
        }
    }
}
