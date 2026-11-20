package fr.kwigorl.kwindle

import android.content.Context
import androidx.lifecycle.Lifecycle
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.chaquo.python.Python
import org.json.JSONArray
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.libtorrent4j.Priority
import org.libtorrent4j.SessionManager
import org.libtorrent4j.SessionParams
import org.libtorrent4j.SettingsPack
import org.libtorrent4j.TcpEndpoint
import org.libtorrent4j.TorrentInfo
import org.libtorrent4j.swig.torrent_flags_t
import java.io.File

/** Tests « de fumée » lancés sur un émulateur par GitHub Actions. */
@RunWith(AndroidJUnit4::class)
class FumeeTest {
    private val ctx: Context get() = InstrumentationRegistry.getInstrumentation().targetContext
    private val testCtx: Context get() = InstrumentationRegistry.getInstrumentation().context

    private fun asset(nom: String): File {
        val f = File(ctx.cacheDir, "test/$nom")
        f.parentFile!!.mkdirs()
        testCtx.assets.open(nom).use { i -> f.outputStream().use { o -> i.copyTo(o) } }
        return f
    }

    @Test
    fun modulesPython() {
        Moteur.init(ctx)
        val py = Python.getInstance()
        for (m in listOf("lxml.etree", "PIL.Image", "mobi", "certifi", "kwindle_moteur", "kwindle_mail")) {
            py.getModule(m)
        }
        val stats = py.getModule("kwindle_mail").callAttr("contexte_ssl").callAttr("cert_store_stats")
        val ca = stats.callAttr("get", "x509_ca").toInt()
        assertTrue("certificats TLS disponibles ($ca)", ca > 0)
    }

    @Test
    fun reparationEpub() {
        val r = Moteur.traiter(ctx, asset("test_casse.epub"), File(ctx.cacheDir, "test/sortie"), "fr")
        assertTrue(r.toString(), r.getBoolean("ok"))
        assertEquals("Test Kwindle", r.getString("titre"))
        val lignes: JSONArray = r.getJSONArray("lignes")
        assertTrue("des corrections attendues", lignes.length() >= 3)
        assertTrue(File(r.getString("sortie")).length() > 0)
    }

    @Test
    fun lectureTorrent() {
        val f = asset("test.torrent")
        val r = Moteur.lireTorrent(ctx, f)
        assertTrue(r.toString(), r.getBoolean("ok"))
        assertEquals(2, r.getInt("livres"))
        val fs = TorrentInfo(f).files()  // charge la bibliothèque native libtorrent4j
        // les fichiers de « remplissage » (pad) du torrent ne comptent pas
        assertEquals(4, (0 until fs.numFiles()).count { !fs.padFileAt(it) })
    }

    @Test
    fun telechargementTorrent() {
        // une 2e session sur l'émulateur partage un faux pack de JDR…
        val base = File(ctx.cacheDir, "test/partage")
        base.deleteRecursively()
        for (nom in listOf("Livret.pdf", "Scenario.epub", "Cartes/carte.png", "LISEZ-MOI.txt")) {
            val f = File(base, "Pack JDR test/$nom")
            f.parentFile!!.mkdirs()
            testCtx.assets.open("pack/$nom").use { i -> f.outputStream().use { o -> i.copyTo(o) } }
        }
        val torrent = asset("pack.torrent")
        val ti = TorrentInfo(torrent)
        val sp = SettingsPack().listenInterfaces("127.0.0.1:43000")
        sp.setEnableDht(false)
        sp.setEnableLsd(false)
        val partageur = SessionManager(false)
        partageur.start(SessionParams(sp))
        try {
            partageur.download(ti, base, null, Array(ti.numFiles()) { Priority.DEFAULT }, emptyList(), torrent_flags_t())
            val limite = System.currentTimeMillis() + 60_000
            while (true) {
                val h = partageur.find(ti.infoHash())
                if (h != null && h.isValid && h.status().isSeeding) break
                assertTrue("le partageur n'a pas démarré", System.currentTimeMillis() < limite)
                Thread.sleep(200)
            }
            // … et Kwindle ne doit récupérer que les livres
            val dl = File(ctx.cacheDir, "test/recu")
            dl.deleteRecursively()
            val recus = Torrents.telecharger(torrent, dl, { false }, listOf(TcpEndpoint("127.0.0.1", 43000))) { _, _, _, _ -> }
            assertEquals(setOf("Livret.pdf", "Scenario.epub"), recus.map { it.name }.toSet())
            for (f in recus) {
                assertArrayEquals(File(base, "Pack JDR test/${f.name}").readBytes(), f.readBytes())
            }
            assertFalse(File(dl, "Pack JDR test/Cartes/carte.png").exists())
        } finally {
            partageur.stop()
        }
    }

    @Test
    fun sessionTorrent() {
        val s = SessionManager(false)
        s.start()
        assertTrue(s.isRunning)
        s.stop()
    }

    @Test
    fun ecranPrincipal() {
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            scenario.moveToState(Lifecycle.State.RESUMED)
            Thread.sleep(1500)
            scenario.onActivity { assertTrue(!it.isFinishing) }
        }
    }
}
