package fr.kwigorl.kwindle

import org.libtorrent4j.Priority
import org.libtorrent4j.SessionManager
import org.libtorrent4j.TcpEndpoint
import org.libtorrent4j.TorrentHandle
import org.libtorrent4j.TorrentInfo
import org.libtorrent4j.TorrentStatus
import org.libtorrent4j.swig.torrent_flags_t
import java.io.File

/** Récupère uniquement les livres d'un fichier .torrent (libtorrent4j). */
object Torrents {
    private val EXT_LIVRES = setOf("epub", "mobi", "azw", "azw3", "prc", "pdf")
    private const val DELAI_SANS_SOURCE = 10 * 60 * 1000L

    class ErreurTorrent(message: String) : Exception(message)

    private var session: SessionManager? = null

    @Synchronized
    private fun session(): SessionManager {
        session?.let { if (it.isRunning) return it }
        val s = SessionManager(false)
        s.start()
        session = s
        return s
    }

    /**
     * Télécharge les livres du torrent dans [dossier] et renvoie leurs fichiers.
     * [progression] reçoit (fraction, sources, débit en o/s, vérification en cours).
     * [pairs] : sources connues à contacter directement (utile pour les tests).
     * Sur téléphone, on ne continue pas à partager une fois le téléchargement fini
     * (données mobiles et batterie).
     */
    fun telecharger(
        fichier: File,
        dossier: File,
        arrete: () -> Boolean,
        pairs: List<TcpEndpoint> = emptyList(),
        progression: (Float, Int, Int, Boolean) -> Unit,
    ): List<File> {
        val ti = try {
            TorrentInfo(fichier)
        } catch (e: Throwable) {
            throw ErreurTorrent("ce fichier .torrent est illisible")
        }
        val fs = ti.files()
        val n = fs.numFiles()
        val priorites = Array(n) { Priority.IGNORE }
        val voulus = mutableListOf<Int>()
        for (i in 0 until n) {
            val ext = fs.filePath(i).substringAfterLast('.', "").lowercase()
            if (ext in EXT_LIVRES && !fs.padFileAt(i)) {
                priorites[i] = Priority.DEFAULT
                voulus += i
            }
        }
        if (voulus.isEmpty()) throw ErreurTorrent("ce torrent ne contient aucun livre (EPUB, MOBI, AZW3 ou PDF)")
        dossier.mkdirs()

        val s = session()
        s.download(ti, dossier, null, priorites, pairs, torrent_flags_t())

        var h: TorrentHandle? = null
        var dernierFait = -1L
        var tDernier = System.currentTimeMillis()
        try {
            while (true) {
                if (arrete()) throw ErreurTorrent("téléchargement arrêté")
                val maintenant = System.currentTimeMillis()
                val poignee = h?.takeIf { it.isValid } ?: s.find(ti.infoHash())
                h = poignee
                if (poignee == null || !poignee.isValid) {
                    if (maintenant - tDernier > 60_000) throw ErreurTorrent("impossible d'ouvrir ce torrent")
                    Thread.sleep(300)
                    continue
                }
                val st = poignee.status()
                val err = st.errorCode()
                if (err != null && err.isError) throw ErreurTorrent("erreur du torrent : " + err.message)
                val etat = st.state()
                val verif = etat == TorrentStatus.State.CHECKING_FILES || etat == TorrentStatus.State.CHECKING_RESUME_DATA
                val total = st.totalWanted()
                val fait = st.totalWantedDone()
                progression(if (total > 0) fait.toFloat() / total else 0f, st.numPeers(), st.downloadRate(), verif)
                if (total > 0 && fait >= total && !verif) break
                if (fait != dernierFait) {
                    dernierFait = fait
                    tDernier = maintenant
                } else if (maintenant - tDernier > DELAI_SANS_SOURCE) {
                    throw ErreurTorrent(
                        if (fait <= 0) "personne ne partage ce torrent en ce moment (aucune source en 10 min)"
                        else "le téléchargement est bloqué depuis 10 min (plus aucune source)"
                    )
                }
                Thread.sleep(500)
            }
        } finally {
            h?.let { if (it.isValid) s.remove(it) }
        }
        Thread.sleep(500) // laisse libtorrent fermer les fichiers

        val recus = voulus.map { File(dossier, fs.filePath(it)) to fs.fileSize(it) }
            .filter { (f, taille) -> f.isFile && f.length() == taille }
            .map { it.first }
        if (recus.isEmpty()) throw ErreurTorrent("téléchargement terminé mais fichiers introuvables")
        return recus
    }
}
