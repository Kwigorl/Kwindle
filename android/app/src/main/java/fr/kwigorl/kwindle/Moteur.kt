package fr.kwigorl.kwindle

import android.content.Context
import com.chaquo.python.PyObject
import com.chaquo.python.Python
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/** Appels au moteur Python (le même que la version PC). */
object Moteur {
    private val module: PyObject by lazy { Python.getInstance().getModule("rekindle_android") }

    @Volatile
    private var pret = false

    fun init(context: Context) {
        if (pret) return
        synchronized(this) {
            if (!pret) {
                module.callAttr("init", File(context.cacheDir, "python").absolutePath)
                pret = true
            }
        }
    }

    private fun json(o: PyObject): JSONObject = JSONObject(o.toString())

    fun traiter(context: Context, livre: File, dossierSortie: File, langue: String): JSONObject {
        init(context)
        dossierSortie.mkdirs()
        return json(module.callAttr("traiter", livre.absolutePath, dossierSortie.absolutePath, langue))
    }

    fun envoyer(context: Context, cfg: JSONObject, chemin: String, titre: String?, auteur: String?): JSONObject {
        init(context)
        return json(module.callAttr("envoyer", cfg.toString(), chemin, titre ?: "", auteur ?: ""))
    }

    /** Début d'un passage « Réparer et envoyer ». */
    fun debut(context: Context) {
        init(context)
        module.callAttr("debut")
    }

    /** Regroupe des livres en e-mails : {"lots": [[id…]…], "trop_gros": [{id, message}…]}. */
    fun lots(context: Context, cfg: JSONObject, livres: JSONArray): JSONObject {
        init(context)
        return json(module.callAttr("lots", cfg.toString(), livres.toString()))
    }

    /** Envoie plusieurs livres dans un seul e-mail (une seule vérification Amazon). */
    fun envoyerLot(context: Context, cfg: JSONObject, livres: JSONArray): JSONObject {
        init(context)
        return json(module.callAttr("envoyer_lot", cfg.toString(), livres.toString()))
    }

    fun tester(context: Context, cfg: JSONObject): JSONObject {
        init(context)
        return json(module.callAttr("tester", cfg.toString()))
    }

    fun lireTorrent(context: Context, fichier: File): JSONObject {
        init(context)
        return json(module.callAttr("lire_torrent", fichier.absolutePath))
    }
}
