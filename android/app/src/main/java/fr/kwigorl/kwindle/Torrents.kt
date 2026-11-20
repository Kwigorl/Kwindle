package fr.kwigorl.kwindle

import android.system.Os
import org.libtorrent4j.Priority
import org.libtorrent4j.SessionManager
import org.libtorrent4j.SessionParams
import org.libtorrent4j.SettingsPack
import org.libtorrent4j.TcpEndpoint
import org.libtorrent4j.TorrentHandle
import org.libtorrent4j.TorrentInfo
import org.libtorrent4j.TorrentStatus
import org.libtorrent4j.swig.settings_pack
import org.libtorrent4j.swig.torrent_flags_t
import java.io.File
import java.net.URI
import java.security.KeyStore
import java.security.cert.X509Certificate
import java.util.Base64

/** Récupère uniquement les livres d'un fichier .torrent (libtorrent4j). */
object Torrents {
    private val EXT_LIVRES = setOf("epub", "mobi", "azw", "azw3", "prc", "pdf")
    private const val DELAI_RIEN_TROUVE = 5 * 60 * 1000L     // aucune source connue
    private const val DELAI_SANS_SOURCE = 10 * 60 * 1000L    // des sources, mais rien ne vient

    class ErreurTorrent(message: String, val details: List<String> = emptyList()) : Exception(message)

    /** Où en est le téléchargement, avec de quoi comprendre un blocage. */
    data class Etat(
        val fraction: Float,
        val sources: Int,            // sources connectées
        val debit: Int,
        val verification: Boolean,
        val connues: Int,            // sources trouvées (connectées ou non)
        val partageurs: Int,         // partageurs annoncés par les trackers (-1 : inconnu)
        val noeudsDht: Long,
        val trackers: Int,
        val erreursTrackers: List<String>,
        val secondes: Long,
    ) {
        fun details(): List<String> = buildList {
            add(
                if (trackers == 0) "Trackers : aucun dans ce torrent (recherche par le réseau DHT seulement)"
                else if (erreursTrackers.isEmpty()) "Trackers : $trackers, pas d'erreur" +
                    (if (partageurs >= 0) " ($partageurs partageur${if (partageurs > 1) "s" else ""} annoncé${if (partageurs > 1) "s" else ""})" else "")
                else "Trackers en erreur : " + erreursTrackers.joinToString(" ; ")
            )
            add("Réseau DHT : $noeudsDht nœud${if (noeudsDht > 1) "s" else ""} joignable${if (noeudsDht > 1) "s" else ""}")
            add("Sources : $connues trouvée${if (connues > 1) "s" else ""}, $sources connectée${if (sources > 1) "s" else ""}")
        }
    }

    private var session: SessionManager? = null

    @Synchronized
    private fun session(dossierCerts: File): SessionManager {
        session?.let { if (it.isRunning) return it }
        val s = nouvelleSession(dossierCerts)
        session = s
        return s
    }

    /**
     * Session libtorrent adaptée à Android. libtorrent cherche les autorités de certification
     * aux emplacements de Linux, qui n'existent pas sur un téléphone : sans elles, tous les
     * trackers en HTTPS échouent. On lui donne donc celles du téléphone (SSL_CERT_FILE).
     * [certificats] = false : comportement d'origine (pour les tests).
     */
    fun nouvelleSession(dossierCerts: File, dht: Boolean = true, certificats: Boolean = true): SessionManager {
        val sp = SettingsPack()
        if (certificats) {
            val pem = exporterCertificats(dossierCerts)
            val ok = pem != null && runCatching { Os.setenv("SSL_CERT_FILE", pem.absolutePath, true) }.isSuccess
            if (!ok) {
                // pas d'autorités utilisables : mieux vaut un tracker non vérifié que pas de tracker
                sp.setBoolean(settings_pack.bool_types.validate_https_trackers.swigValue(), false)
            }
        }
        if (!dht) sp.setBoolean(settings_pack.bool_types.enable_dht.swigValue(), false)
        val s = SessionManager(false)
        s.start(SessionParams(sp))
        return s
    }

    /** Écrit les autorités de certification du téléphone dans un fichier PEM (pour OpenSSL). */
    private fun exporterCertificats(dossier: File): File? = try {
        val ks = KeyStore.getInstance("AndroidCAStore")
        ks.load(null)
        val enc = Base64.getMimeEncoder(64, "\n".toByteArray())
        val sb = StringBuilder()
        var n = 0
        for (alias in ks.aliases().toList()) {
            val c = ks.getCertificate(alias) as? X509Certificate ?: continue
            sb.append("-----BEGIN CERTIFICATE-----\n").append(enc.encodeToString(c.encoded))
                .append("\n-----END CERTIFICATE-----\n")
            n++
        }
        if (n == 0) null else {
            dossier.mkdirs()
            File(dossier, "autorites.pem").also { it.writeText(sb.toString()) }
        }
    } catch (e: Exception) {
        null
    }

    /** Erreurs des trackers et nombre de partageurs qu'ils annoncent (-1 : inconnu). */
    fun etatTrackers(h: TorrentHandle): Triple<Int, List<String>, Int> {
        val erreurs = mutableListOf<String>()
        var partageurs = -1
        val liste = try { h.trackers() } catch (e: Throwable) { emptyList() }
        for (t in liste) {
            val hote = runCatching { URI(t.url()).host }.getOrNull() ?: t.url()
            for (ep in t.endpoints()) {
                for (ih in listOf(ep.infohashV1(), ep.infohashV2())) {
                    val brut = ih.swig()
                    partageurs = maxOf(partageurs, brut.getScrape_complete())
                    if (ih.fails() > 0) {
                        val m = ih.message().ifBlank { runCatching { brut.getLast_error().message() }.getOrDefault("") }
                        erreurs += "$hote (${m.ifBlank { "pas de réponse" }})"
                    }
                }
            }
        }
        return Triple(liste.size, erreurs.distinct(), partageurs)
    }

    /**
     * Télécharge les livres du torrent dans [dossier] et renvoie leurs fichiers.
     * [progression] reçoit l'état du téléchargement environ deux fois par seconde.
     * [pairs] : sources connues à contacter directement (utile pour les tests).
     * Sur téléphone, on ne continue pas à partager une fois le téléchargement fini
     * (données mobiles et batterie).
     */
    fun telecharger(
        fichier: File,
        dossier: File,
        arrete: () -> Boolean,
        pairs: List<TcpEndpoint> = emptyList(),
        progression: (Etat) -> Unit,
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

        val s = session(dossier.absoluteFile.parentFile ?: dossier)
        s.download(ti, dossier, null, priorites, pairs, torrent_flags_t())

        val debut = System.currentTimeMillis()
        var h: TorrentHandle? = null
        var dernierFait = -1L
        var tDernier = debut
        var tTrackers = 0L
        var trackers = Triple(0, emptyList<String>(), -1)
        var etat: Etat? = null
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
                val e = st.state()
                val verif = e == TorrentStatus.State.CHECKING_FILES || e == TorrentStatus.State.CHECKING_RESUME_DATA
                val total = st.totalWanted()
                val fait = st.totalWantedDone()
                if (maintenant - tTrackers > 3000) {
                    tTrackers = maintenant
                    trackers = etatTrackers(poignee)
                }
                val et = Etat(
                    fraction = if (total > 0) fait.toFloat() / total else 0f,
                    sources = st.numPeers(),
                    debit = st.downloadRate(),
                    verification = verif,
                    connues = maxOf(st.listPeers(), st.connectCandidates()),
                    partageurs = maxOf(trackers.third, st.numComplete()),
                    noeudsDht = runCatching { s.dhtNodes() }.getOrDefault(-1L),
                    trackers = trackers.first,
                    erreursTrackers = trackers.second,
                    secondes = (maintenant - debut) / 1000,
                )
                etat = et
                progression(et)
                if (total > 0 && fait >= total && !verif) break
                if (fait != dernierFait) {
                    dernierFait = fait
                    tDernier = maintenant
                } else {
                    val rienTrouve = fait <= 0 && et.connues == 0 && et.partageurs <= 0
                    if (maintenant - tDernier > if (rienTrouve) DELAI_RIEN_TROUVE else DELAI_SANS_SOURCE) {
                        throw ErreurTorrent(explication(et, fait > 0), et.details())
                    }
                }
                Thread.sleep(500)
            }
        } catch (ex: ErreurTorrent) {
            if (ex.details.isEmpty() && etat != null) throw ErreurTorrent(ex.message ?: "", etat.details())
            throw ex
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

    private fun explication(e: Etat, commence: Boolean): String = when {
        commence -> "le téléchargement est bloqué depuis 10 min (plus aucune source)"
        e.connues > 0 || e.partageurs > 0 ->
            "des partageurs existent mais aucun n'accepte la connexion (pare-feu, ou logiciel fermé). " +
                "Réessaie plus tard, ou sur une autre connexion (Wi-Fi ou 4G)"
        e.trackers > 0 && e.erreursTrackers.size >= e.trackers ->
            "le ou les trackers ne répondent pas, et le réseau DHT n'a trouvé personne"
        e.trackers == 0 && e.noeudsDht <= 0 ->
            "ce torrent n'a pas de tracker et le réseau DHT est injoignable depuis cette connexion"
        else -> "personne ne partage ce torrent en ce moment (aucune source en 5 min)"
    }
}
