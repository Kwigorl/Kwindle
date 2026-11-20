package fr.kwigorl.kwindle

import android.content.Context
import androidx.lifecycle.Lifecycle
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.chaquo.python.Python
import org.json.JSONArray
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.libtorrent4j.SessionManager
import org.libtorrent4j.TorrentInfo
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
        val ti = TorrentInfo(f)  // charge la bibliothèque native libtorrent4j
        assertEquals(4, ti.files().numFiles())
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
