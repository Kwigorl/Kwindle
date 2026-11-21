package fr.kwigorl.kwindle

import android.content.ContentUris
import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.content.IntentSender
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.DocumentsContract
import android.provider.MediaStore
import android.provider.OpenableColumns
import androidx.core.content.FileProvider
import java.io.File
import java.util.UUID

object Fichiers {

    /** Nom du fichier derrière une adresse content:// ou file://. */
    fun nom(context: Context, uri: Uri): String {
        var nom: String? = null
        if (uri.scheme == "content") {
            try {
                context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)
                    ?.use { c -> if (c.moveToFirst() && !c.isNull(0)) nom = c.getString(0) }
            } catch (e: Exception) {
                // certaines applis ne donnent pas le nom
            }
        }
        if (nom.isNullOrBlank()) nom = uri.lastPathSegment?.substringAfterLast('/')
        return (nom ?: "fichier").replace(Regex("[\\\\/:*?\"<>|\\x00-\\x1f]"), "_").ifBlank { "fichier" }
    }

    /** Copie le fichier reçu dans le cache de l'appli (les autres applis ne le prêtent que brièvement). */
    fun copier(context: Context, uri: Uri): File {
        val dossier = File(context.cacheDir, "entrees/" + UUID.randomUUID().toString().take(8))
        dossier.mkdirs()
        val f = File(dossier, nom(context, uri))
        val entree = context.contentResolver.openInputStream(uri)
            ?: throw IllegalStateException("fichier illisible")
        entree.use { i -> f.outputStream().use { o -> i.copyTo(o) } }
        return f
    }

    fun estTorrent(f: File): Boolean {
        if (f.name.lowercase().endsWith(".torrent")) return true
        return try {
            f.inputStream().use { flux ->
                val b = ByteArray(24)
                val n = flux.read(b)
                if (n <= 0) return false
                val debut = String(b, 0, n, Charsets.ISO_8859_1)
                listOf("d8:announce", "d13:announce", "d4:info", "d7:comment", "d10:created").any { debut.startsWith(it) }
            }
        } catch (e: Exception) {
            false
        }
    }

    fun mime(nom: String): String = when (nom.substringAfterLast('.', "").lowercase()) {
        "epub" -> "application/epub+zip"
        "pdf" -> "application/pdf"
        "mobi", "azw", "azw3", "prc" -> "application/x-mobipocket-ebook"
        "torrent" -> "application/x-bittorrent"
        else -> "application/octet-stream"
    }

    /** Range une copie dans Téléchargements/Rekindle (visible dans l'appli Fichiers) ; renvoie son adresse. */
    fun enregistrer(context: Context, f: File): Uri? {
        return try {
            val valeurs = ContentValues().apply {
                put(MediaStore.Downloads.DISPLAY_NAME, f.name)
                put(MediaStore.Downloads.MIME_TYPE, mime(f.name))
                put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/Rekindle")
            }
            val uri = context.contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, valeurs)
                ?: return null
            context.contentResolver.openOutputStream(uri)?.use { o -> f.inputStream().use { it.copyTo(o) } }
            uri
        } catch (e: Exception) {
            null
        }
    }

    /** Efface une copie rangée par Rekindle dans Téléchargements (elle lui appartient). */
    fun supprimerCopie(context: Context, uri: String) {
        runCatching { context.contentResolver.delete(Uri.parse(uri), null, null) }
    }

    enum class Suppression { FAITE, A_CONFIRMER, IMPOSSIBLE }

    /** Garde, si possible, le droit de modifier le fichier choisi (pour pouvoir l'effacer plus tard). */
    fun garderAcces(context: Context, uri: Uri) {
        runCatching {
            context.contentResolver.takePersistableUriPermission(
                uri, Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION,
            )
        }
    }

    /**
     * Efface le fichier d'origine (celui qu'on a ouvert dans Rekindle). Ça marche quand Android
     * nous en donne le droit (fichier choisi avec le bouton +) ; un fichier d'une autre appli
     * rangé dans la médiathèque d'Android peut être effacé après confirmation (A_CONFIRMER).
     */
    fun supprimerOrigine(context: Context, uri: Uri): Suppression {
        if (uri.scheme == "file") {
            return if (uri.path?.let { File(it).delete() } == true) Suppression.FAITE else Suppression.IMPOSSIBLE
        }
        val cr = context.contentResolver
        try {
            if (DocumentsContract.isDocumentUri(context, uri) && DocumentsContract.deleteDocument(cr, uri)) {
                return Suppression.FAITE
            }
        } catch (e: Exception) {
            // pas le droit, ou fichier déjà parti
        }
        try {
            if (cr.delete(uri, null, null) > 0) return Suppression.FAITE
        } catch (e: Exception) {
            // idem
        }
        return if (Build.VERSION.SDK_INT >= 30 && uriMediatheque(context, uri) != null) Suppression.A_CONFIRMER
        else Suppression.IMPOSSIBLE
    }

    /** Adresse du fichier dans la médiathèque d'Android, pour une demande de suppression. */
    fun uriMediatheque(context: Context, uri: Uri): Uri? {
        if (uri.authority == MediaStore.AUTHORITY) return uri
        if (uri.authority == "com.android.providers.downloads.documents" && DocumentsContract.isDocumentUri(context, uri)) {
            val id = DocumentsContract.getDocumentId(uri)
            if (id.startsWith("msf:")) {
                id.removePrefix("msf:").toLongOrNull()?.let {
                    return ContentUris.withAppendedId(MediaStore.Files.getContentUri("external"), it)
                }
            }
        }
        return null
    }

    /** Demande à Android (une seule fenêtre de confirmation) d'effacer ces fichiers. */
    fun demandeSuppression(context: Context, uris: List<Uri>): IntentSender? {
        if (Build.VERSION.SDK_INT < 30 || uris.isEmpty()) return null
        return try {
            MediaStore.createDeleteRequest(context.contentResolver, uris).intentSender
        } catch (e: Exception) {
            null
        }
    }

    /** Ouvre le menu « Partager » d'Android (appli Kindle, Gmail, Drive…). */
    fun partager(context: Context, f: File) {
        val uri = FileProvider.getUriForFile(context, context.packageName + ".fichiers", f)
        val envoi = Intent(Intent.ACTION_SEND).apply {
            type = mime(f.name)
            putExtra(Intent.EXTRA_STREAM, uri)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        context.startActivity(
            Intent.createChooser(envoi, "Envoyer « ${f.name} »").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        )
    }
}
