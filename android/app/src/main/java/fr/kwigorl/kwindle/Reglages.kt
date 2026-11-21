package fr.kwigorl.kwindle

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import androidx.core.content.edit
import org.json.JSONObject
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

data class Fournisseur(
    val nom: String,
    val serveur: String,
    val port: Int,
    val securite: String,
    val aide: String,
    val lien: String = "",
)

const val PAGE_AMAZON = "https://www.amazon.fr/mycd"

val FOURNISSEURS = listOf(
    Fournisseur(
        "Gmail", "smtp.gmail.com", 465, "SSL",
        "Gmail demande un « mot de passe d'application » (16 lettres), pas ton mot de passe habituel. " +
            "Active la validation en 2 étapes puis crée-le sur myaccount.google.com/apppasswords.",
        "https://myaccount.google.com/apppasswords",
    ),
    Fournisseur(
        "Yahoo", "smtp.mail.yahoo.com", 465, "SSL",
        "Yahoo demande un « mot de passe d'application » (Sécurité du compte).",
        "https://login.yahoo.com/myaccount/security/",
    ),
    Fournisseur(
        "iCloud", "smtp.mail.me.com", 587, "STARTTLS",
        "iCloud demande un « mot de passe pour app » créé sur account.apple.com.",
        "https://account.apple.com/",
    ),
    Fournisseur("Orange", "smtp.orange.fr", 465, "SSL", "Adresse et mot de passe de ta messagerie Orange."),
    Fournisseur("Free", "smtp.free.fr", 465, "SSL", "Adresse et mot de passe de ta messagerie Free."),
    Fournisseur("SFR", "smtp.sfr.fr", 465, "SSL", "Adresse et mot de passe de ta messagerie SFR."),
    Fournisseur("La Poste", "smtp.laposte.net", 465, "SSL", "Adresse et mot de passe de ta messagerie laposte.net."),
    Fournisseur(
        "Outlook / Hotmail", "smtp-mail.outlook.com", 587, "STARTTLS",
        "⚠ Microsoft a coupé l'envoi par mot de passe pour les comptes Outlook.com / Hotmail " +
            "personnels : ça ne marchera pas. Utilise plutôt une adresse Gmail.",
    ),
    Fournisseur("Autre", "", 465, "SSL", "Renseigne le serveur d'envoi (SMTP) de ta messagerie."),
)

fun fournisseur(nom: String): Fournisseur = FOURNISSEURS.firstOrNull { it.nom == nom } ?: FOURNISSEURS.last()

/** Réglages enregistrés sur le téléphone ; le mot de passe est chiffré par le coffre Android. */
class Reglages(context: Context) {
    private val p = context.getSharedPreferences("reglages", Context.MODE_PRIVATE)

    private fun texte(cle: String, defaut: String = "") = p.getString(cle, defaut) ?: defaut
    private fun ecrire(cle: String, v: String) = p.edit { putString(cle, v) }

    var kindle: String
        get() = texte("kindle")
        set(v) = ecrire("kindle", v)
    var fournisseur: String
        get() = texte("fournisseur", "Gmail")
        set(v) = ecrire("fournisseur", v)
    var expediteur: String
        get() = texte("expediteur")
        set(v) = ecrire("expediteur", v)
    var identifiant: String
        get() = texte("identifiant")
        set(v) = ecrire("identifiant", v)
    var serveur: String
        get() = texte("serveur", "smtp.gmail.com")
        set(v) = ecrire("serveur", v)
    var port: Int
        get() = p.getInt("port", 465)
        set(v) = p.edit { putInt("port", v) }
    var securite: String
        get() = texte("securite", "SSL")
        set(v) = ecrire("securite", v)
    var langue: String
        get() = texte("langue", "fr")
        set(v) = ecrire("langue", v)
    var envoyer: Boolean
        get() = p.getBoolean("envoyer", true)
        set(v) = p.edit { putBoolean("envoyer", v) }

    /** Après un envoi réussi : effacer les copies faites par Rekindle (livre réparé, téléchargements). */
    var supprimerApresEnvoi: Boolean
        get() = p.getBoolean("supprimer_apres_envoi", false)
        set(v) = p.edit { putBoolean("supprimer_apres_envoi", v) }

    /** … et aussi le fichier d'origine (le .torrent ou le livre ouvert dans Rekindle). */
    var supprimerOrigine: Boolean
        get() = p.getBoolean("supprimer_origine", false)
        set(v) = p.edit { putBoolean("supprimer_origine", v) }

    var motDePasse: String
        get() = dechiffrer(p.getString("mdp", null))
        set(v) = ecrire("mdp", chiffrer(v))

    fun probleme(): String? {
        val k = kindle.trim().lowercase()
        return when {
            k.isEmpty() -> "Indique ton adresse Kindle dans les réglages."
            !(k.endsWith("@kindle.com") || k.endsWith("@free.kindle.com")) ->
                "L'adresse Kindle doit finir par @kindle.com."
            expediteur.isBlank() -> "Indique l'adresse e-mail qui envoie les livres."
            serveur.isBlank() -> "Indique le serveur d'envoi (SMTP)."
            motDePasse.isEmpty() -> "Indique le mot de passe de ta messagerie."
            else -> null
        }
    }

    fun versJson(): JSONObject = JSONObject().apply {
        put("kindle", kindle.trim())
        put("fournisseur", fournisseur)
        put("expediteur", expediteur.trim())
        put("identifiant", identifiant.trim())
        put("serveur", serveur.trim())
        put("port", port)
        put("securite", securite)
        put("mdp", motDePasse)
    }

    // ------------------------------------------------------------ chiffrement
    private fun cle(): SecretKey {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getKey(ALIAS, null) as? SecretKey)?.let { return it }
        val kg = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        kg.init(
            KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .build()
        )
        return kg.generateKey()
    }

    private fun chiffrer(t: String): String {
        if (t.isEmpty()) return ""
        return try {
            val c = Cipher.getInstance("AES/GCM/NoPadding")
            c.init(Cipher.ENCRYPT_MODE, cle())
            Base64.encodeToString(c.iv + c.doFinal(t.toByteArray(Charsets.UTF_8)), Base64.NO_WRAP)
        } catch (e: Exception) {
            ""
        }
    }

    private fun dechiffrer(s: String?): String {
        if (s.isNullOrEmpty()) return ""
        return try {
            val b = Base64.decode(s, Base64.NO_WRAP)
            val c = Cipher.getInstance("AES/GCM/NoPadding")
            c.init(Cipher.DECRYPT_MODE, cle(), GCMParameterSpec(128, b, 0, 12))
            String(c.doFinal(b, 12, b.size - 12), Charsets.UTF_8)
        } catch (e: Exception) {
            ""
        }
    }

    companion object {
        private const val ALIAS = "kwindle_mdp"
    }
}
