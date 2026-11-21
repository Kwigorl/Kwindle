package fr.kwigorl.kwindle

import android.app.Application
import android.content.IntentSender
import android.net.Uri
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicLong

enum class Type { LIVRE, TORRENT }
enum class Phase { ATTENTE, ERREUR, PRET, ENVOYE, ECHEC_ENVOI, TELECHARGE }
enum class Ton { NEUTRE, EN_COURS, OK, KO }

data class Element(
    val id: Long,
    val type: Type,
    val fichier: File,
    val nom: String,
    val parent: Long? = null,
    val format: String = "",
    val statut: String = "En attente",
    val ton: Ton = Ton.NEUTRE,
    val progression: Float? = null,
    val phase: Phase = Phase.ATTENTE,
    val sortie: String? = null,
    val titre: String? = null,
    val auteur: String? = null,
    val lignes: List<Pair<String, String>> = emptyList(),
    val origine: String? = null,     // adresse du fichier ouvert dans Rekindle
    val copie: String? = null,       // copie rangée dans Téléchargements/Rekindle
    val nettoye: Boolean = false,    // fichiers déjà effacés après l'envoi
)

private val FORMATS = mapOf("zip" to "EPUB", "mobi" to "MOBI / AZW", "pdf" to "PDF", "topaz" to "Topaz", "kfx" to "KFX")

class RekindleVM(app: Application) : AndroidViewModel(app) {
    val reglages = Reglages(app)
    val elements = mutableStateListOf<Element>()

    var enCours by mutableStateOf(false)
        private set
    var arretDemande by mutableStateOf(false)
        private set
    var envoyer by mutableStateOf(reglages.envoyer)
        private set
    var annonce by mutableStateOf<String?>(null)
    /** Fichiers d'origine qu'Android doit faire confirmer avant de les effacer. */
    var demandeSuppression by mutableStateOf<IntentSender?>(null)
    private var attenteConfirmation = emptyList<Long>()
    var alerte by mutableStateOf<String?>(null)
    var permissionDemandee = false

    /** Torrents en cours de téléchargement (ils démarrent dès qu'on les ajoute). */
    val telechargements = mutableStateListOf<Long>()

    private val arret = AtomicBoolean(false)
    private val arretsTorrents = ConcurrentHashMap<Long, AtomicBoolean>()
    private var travaux = 0      // réparations + téléchargements en cours (service au premier plan)
    private val compteur = AtomicLong(1)
    private val dossierSortie = File(app.filesDir, "sortie")
    private val dossierTorrents = File(app.filesDir, "torrents")

    init {
        viewModelScope.launch(Dispatchers.IO) {
            // la liste repart à zéro à chaque lancement : les copies internes d'avant ne servent plus
            for (d in listOf(File(app.cacheDir, "entrees"), dossierTorrents, dossierSortie)) {
                runCatching { d.deleteRecursively() }
            }
            // démarre Python en avance pour que le premier livre aille vite
            runCatching { Moteur.init(app) }
        }
    }

    private val ctx get() = getApplication<Application>()

    fun changerEnvoi(v: Boolean) {
        envoyer = v
        reglages.envoyer = v
    }

    // ---------------------------------------------------------------- liste
    fun ajouter(uris: List<Uri>) {
        if (uris.isEmpty()) return
        viewModelScope.launch(Dispatchers.IO) {
            for (uri in uris) {
                try {
                    Fichiers.garderAcces(ctx, uri)
                    val f = Fichiers.copier(ctx, uri)
                    val el = if (Fichiers.estTorrent(f)) {
                        val info = runCatching { Moteur.lireTorrent(ctx, f) }.getOrNull()
                        val nom = if (info != null && info.optBoolean("ok")) {
                            val n = info.optInt("livres")
                            "${info.optString("nom")}  ($n livre${if (n > 1) "s" else ""})"
                        } else f.name
                        Element(compteur.getAndIncrement(), Type.TORRENT, f, nom, format = "Torrent", origine = uri.toString())
                    } else {
                        Element(compteur.getAndIncrement(), Type.LIVRE, f, f.name, origine = uri.toString())
                    }
                    withContext(Dispatchers.Main) {
                        elements.add(el)
                        if (el.type == Type.TORRENT) telecharger(el.id)
                    }
                } catch (e: Exception) {
                    withContext(Dispatchers.Main) { annonce = "Impossible de lire ce fichier (${e.message})" }
                }
            }
        }
    }

    fun retirer(id: Long) {
        val telechargeEncore = id in telechargements
        if (enCours && !telechargeEncore) return
        arretsTorrents[id]?.set(true)      // annule le téléchargement s'il tourne
        elements.removeAll { it.id == id || it.parent == id }
    }

    fun vider() {
        if (enCours) return
        for (a in arretsTorrents.values) a.set(true)
        elements.clear()
    }

    fun enTelechargement(id: Long) = id in telechargements

    // ------------------------------------------- service au premier plan
    /** À appeler sur le fil principal. */
    private fun debutTravail(texte: String) {
        if (travaux++ == 0) TravailService.demarrer(ctx, texte) else TravailService.maj(ctx, texte)
    }

    private fun finTravail() {
        if (--travaux <= 0) {
            travaux = 0
            TravailService.arreter(ctx)
        }
    }

    // ------------------------------------------------------- téléchargements
    /** Lance (ou relance) le téléchargement d'un torrent de la liste. */
    fun telecharger(id: Long) {
        if (id in telechargements) return
        val el = elements.firstOrNull { it.id == id && it.type == Type.TORRENT } ?: return
        val stop = AtomicBoolean(false)
        arretsTorrents[id] = stop
        telechargements += id
        debutTravail("Téléchargement du torrent…")
        val i = elements.indexOfFirst { it.id == id }
        if (i >= 0) elements[i] = elements[i].copy(
            phase = Phase.ATTENTE, statut = "Recherche de sources…", ton = Ton.EN_COURS, progression = 0f, lignes = emptyList(),
        )
        viewModelScope.launch(Dispatchers.IO) {
            var nouveaux = 0
            try {
                nouveaux = travailTorrent(el, stop)
            } catch (e: Exception) {
                maj(id) {
                    it.copy(
                        phase = Phase.ERREUR, statut = "✗ Échec", ton = Ton.KO, progression = null,
                        lignes = it.lignes + ("erreur" to "Erreur inattendue : ${e.message}"),
                    )
                }
            } finally {
                withContext(NonCancellable + Dispatchers.Main) {
                    telechargements.remove(id)
                    arretsTorrents.remove(id)
                    finTravail()
                    if (nouveaux > 0 && !enCours) {
                        annonce = if (nouveaux > 1) "$nouveaux livres récupérés : appuie sur « ${texteBouton()} »."
                        else "Livre récupéré : appuie sur « ${texteBouton()} »."
                    }
                }
            }
        }
    }

    private fun texteBouton() = if (envoyer) "Réparer et envoyer" else "Réparer"

    private suspend fun trouver(id: Long): Element? =
        withContext(Dispatchers.Main) { elements.firstOrNull { it.id == id } }

    private suspend fun maj(id: Long, f: (Element) -> Element) = withContext(Dispatchers.Main) {
        val i = elements.indexOfFirst { it.id == id }
        if (i >= 0) elements[i] = f(elements[i])
    }

    // -------------------------------------------------------------- travail
    fun lancer() {
        if (enCours) {
            arret.set(true)
            arretDemande = true
            return
        }
        val envoi = envoyer
        val etats = mutableSetOf(Phase.ATTENTE, Phase.ERREUR, Phase.ECHEC_ENVOI)
        if (envoi) etats += Phase.PRET
        val aFaire = elements.filter { it.type == Type.LIVRE && it.phase in etats }.map { it.id }
        if (aFaire.isEmpty()) {
            annonce = when {
                elements.isEmpty() -> "Ajoute d'abord un livre ou un fichier .torrent."
                telechargements.isNotEmpty() ->
                    "Le torrent est en cours de téléchargement : ses livres apparaîtront dans la liste."
                else -> "Tout est déjà traité."
            }
            return
        }
        if (envoi) reglages.probleme()?.let {
            alerte = it
            return
        }
        arret.set(false)
        arretDemande = false
        enCours = true
        debutTravail("Rekindle travaille…")

        viewModelScope.launch(Dispatchers.IO) {
            var bloque: String? = null
            var nbMails = 0
            val file = ArrayDeque(aFaire)
            val aEnvoyer = mutableListOf<Long>()
            try {
                runCatching { Moteur.debut(ctx) }
                while (file.isNotEmpty() && !arret.get()) {
                    val id = file.removeFirst()
                    val el = trouver(id) ?: continue
                    try {
                        val phase = travailLivre(el)
                        if (phase == Phase.PRET || phase == Phase.ECHEC_ENVOI) aEnvoyer += id
                    } catch (e: Exception) {
                        maj(id) {
                            it.copy(
                                phase = Phase.ERREUR, statut = "✗ Impossible", ton = Ton.KO, progression = null,
                                lignes = it.lignes + ("erreur" to "Erreur inattendue : ${e.message}"),
                            )
                        }
                    }
                }
                if (envoi && aEnvoyer.isNotEmpty() && !arret.get()) {
                    val r = envoyerGroupes(aEnvoyer)
                    bloque = r.first
                    nbMails = r.second
                    if (nbMails > 0 && reglages.supprimerApresEnvoi) nettoyer(reglages.supprimerOrigine)
                }
            } finally {
                val arrete = arret.get()
                withContext(NonCancellable + Dispatchers.Main) {
                    enCours = false
                    arretDemande = false
                    finTravail()
                    when {
                        bloque != null -> alerte = bloque
                        arrete -> annonce = "Arrêté. Appuie à nouveau sur le bouton pour reprendre."
                        envoi && nbMails == 1 ->
                            annonce = "Envoyé en un seul e-mail. Si Amazon demande « Vérifiez votre demande », " +
                                "clique sur le lien du mail : sans ça, les livres n'arrivent pas."
                        envoi && nbMails > 1 ->
                            annonce = "Envoyé en $nbMails e-mails. Amazon peut demander une vérification pour " +
                                "chacun : clique sur chaque lien « Vérifier la demande »."
                        elements.any { it.phase == Phase.PRET } ->
                            annonce = "Livres réparés : une copie est dans Téléchargements › Rekindle."
                    }
                }
            }
        }
    }

    private suspend fun travailTorrent(el: Element, stop: AtomicBoolean): Int {
        TravailService.maj(ctx, "Torrent : recherche de sources…")
        var dernier = 0L
        val recus = try {
            Torrents.telecharger(el.fichier, File(dossierTorrents, el.id.toString()), { stop.get() }) { e ->
                val t = System.currentTimeMillis()
                if (t - dernier > 400) {
                    dernier = t
                    val pc = (e.fraction * 100).toInt()
                    val min = if (e.secondes >= 60) " (${e.secondes / 60} min)" else ""
                    val txt = when {
                        e.verification -> "Vérification…"
                        e.sources > 0 || e.fraction > 0f ->
                            "⇣ $pc %  ·  ${e.sources} source${if (e.sources > 1) "s" else ""}"
                        e.connues > 0 -> "Connexion à ${e.connues} source${if (e.connues > 1) "s" else ""}…$min"
                        e.secondes >= 20 && e.trackers > 0 && e.erreursTrackers.size >= e.trackers ->
                            "Tracker injoignable, recherche…$min"
                        else -> "Recherche de sources…$min"
                    }
                    val lignes = e.details().map { "info" to it }
                    viewModelScope.launch(Dispatchers.Main) {
                        val i = elements.indexOfFirst { it.id == el.id }
                        if (i >= 0) elements[i] = elements[i].copy(statut = txt, progression = e.fraction, lignes = lignes)
                    }
                    TravailService.maj(ctx, "Torrent : $pc %")
                }
            }
        } catch (e: Torrents.ErreurTorrent) {
            val arrete = stop.get()
            maj(el.id) {
                it.copy(
                    phase = Phase.ERREUR, statut = if (arrete) "■ Arrêté" else "✗ Échec", ton = Ton.KO, progression = null,
                    lignes = if (arrete) it.lignes
                    else listOf("erreur" to "Torrent : ${e.message}") + e.details.map { d -> "info" to d },
                )
            }
            return 0
        }
        if (stop.get()) return 0
        val n = recus.size
        val s = if (n > 1) "s" else ""
        maj(el.id) {
            it.copy(
                phase = Phase.TELECHARGE, statut = "✓ $n livre$s récupéré$s", ton = Ton.OK, progression = null,
                lignes = listOf("info" to "Récupéré : " + recus.joinToString(", ") { f -> f.name }),
            )
        }
        val nouveaux = recus.map { f -> Element(compteur.getAndIncrement(), Type.LIVRE, f, f.name, parent = el.id) }
        withContext(Dispatchers.Main) {
            var pos = elements.indexOfFirst { it.id == el.id } + 1
            while (pos < elements.size && elements[pos].parent == el.id) pos++
            if (pos > 0) elements.addAll(pos, nouveaux)   // pos = 0 : torrent retiré entre-temps
        }
        return nouveaux.size
    }

    /** Répare un livre (si ce n'est pas déjà fait) et renvoie sa nouvelle phase. */
    private suspend fun travailLivre(el: Element): Phase {
        if (el.phase != Phase.ATTENTE && el.phase != Phase.ERREUR) return el.phase
        maj(el.id) { it.copy(statut = "Réparation…", ton = Ton.EN_COURS) }
        TravailService.maj(ctx, "Réparation : ${el.nom}")
        val r = Moteur.traiter(ctx, el.fichier, dossierSortie, reglages.langue)
        val tab = r.optJSONArray("lignes")
        val lignes = (0 until (tab?.length() ?: 0)).map { i ->
            val l = tab!!.getJSONArray(i)
            l.getString(0) to l.getString(1)
        }
        val format = FORMATS[r.optString("format")] ?: ""
        if (!r.optBoolean("ok")) {
            maj(el.id) { it.copy(phase = Phase.ERREUR, statut = "✗ Impossible", ton = Ton.KO, format = format, lignes = lignes) }
            return Phase.ERREUR
        }
        val sortie = r.optString("sortie")
        val copie = Fichiers.enregistrer(ctx, File(sortie))?.toString()
        maj(el.id) {
            it.copy(
                phase = Phase.PRET, statut = "✓ Réparé", ton = Ton.OK, format = format, sortie = sortie, copie = copie,
                titre = r.optString("titre").ifBlank { null }, auteur = r.optString("auteur").ifBlank { null },
                lignes = lignes,
            )
        }
        return Phase.PRET
    }

    /**
     * Envoie les livres en regroupant plusieurs livres par e-mail : Amazon demande
     * une vérification par e-mail, pas par livre. Renvoie (erreur bloquante, nombre d'e-mails).
     */
    private suspend fun envoyerGroupes(ids: List<Long>): Pair<String?, Int> {
        val cfg = reglages.versJson()
        val livres = JSONArray()
        val parId = mutableMapOf<Long, Element>()
        for (id in ids) {
            val el = trouver(id) ?: continue
            val sortie = el.sortie ?: continue
            parId[id] = el
            livres.put(JSONObject().apply {
                put("id", id)
                put("chemin", sortie)
                put("titre", el.titre ?: el.nom)
                put("auteur", el.auteur ?: "")
            })
        }
        if (parId.isEmpty()) return null to 0
        val repartition = Moteur.lots(ctx, cfg, livres)
        val tropGros = repartition.optJSONArray("trop_gros") ?: JSONArray()
        for (i in 0 until tropGros.length()) {
            val t = tropGros.getJSONObject(i)
            val msg = t.optString("message")
            maj(t.getLong("id")) {
                it.copy(phase = Phase.ECHEC_ENVOI, statut = "✗ Trop gros", ton = Ton.KO, lignes = it.lignes + ("erreur" to msg))
            }
        }
        var bloque: String? = null
        var nbMails = 0
        val lots = repartition.optJSONArray("lots") ?: JSONArray()
        for (n in 0 until lots.length()) {
            if (arret.get()) break
            val groupe = lots.getJSONArray(n)
            val membres = (0 until groupe.length()).mapNotNull { parId[groupe.getLong(it)] }
            if (bloque != null) {
                for (el in membres) maj(el.id) { it.copy(phase = Phase.ECHEC_ENVOI, statut = "✗ Pas envoyé", ton = Ton.KO) }
                continue
            }
            for (el in membres) maj(el.id) { it.copy(statut = "Envoi…", ton = Ton.EN_COURS) }
            TravailService.maj(ctx, "Envoi de ${membres.size} livre(s)…")
            val contenu = JSONArray()
            for (el in membres) {
                contenu.put(JSONObject().apply {
                    put("chemin", el.sortie)
                    put("titre", el.titre ?: el.nom)
                    put("auteur", el.auteur ?: "")
                })
            }
            val r = Moteur.envoyerLot(ctx, cfg, contenu)
            if (r.optBoolean("ok")) {
                nbMails++
                val k = reglages.kindle
                val note = if (membres.size > 1) "Envoyé à $k (un seul e-mail pour ${membres.size} livres)" else "Envoyé à $k"
                for (el in membres) {
                    maj(el.id) { it.copy(phase = Phase.ENVOYE, statut = "✓ Envoyé", ton = Ton.OK, lignes = it.lignes + ("envoi" to note)) }
                }
            } else {
                val msg = r.optString("erreur")
                for (el in membres) {
                    maj(el.id) {
                        it.copy(phase = Phase.ECHEC_ENVOI, statut = "✗ Envoi raté", ton = Ton.KO, lignes = it.lignes + ("erreur" to "Envoi : $msg"))
                    }
                }
                if (r.optBoolean("bloquant")) bloque = msg
            }
        }
        return bloque to nbMails
    }

    // ------------------------------------------------- ménage après l'envoi
    /**
     * Efface ce qui ne sert plus une fois les livres envoyés : copies internes, livre réparé rangé
     * dans Téléchargements/Rekindle, fichiers téléchargés par torrent et, si demandé, le fichier
     * d'origine. Un torrent n'est nettoyé que quand tous ses livres sont partis.
     */
    private suspend fun nettoyer(origineAussi: Boolean) {
        val tous = withContext(Dispatchers.Main) { elements.toList() }
        val aConfirmer = mutableListOf<Pair<Long, Uri>>()
        fun effacerOrigine(el: Element): String? {
            if (!origineAussi) return null
            val uri = el.origine?.let(Uri::parse) ?: return null
            return when (Fichiers.supprimerOrigine(ctx, uri)) {
                Fichiers.Suppression.FAITE -> "Fichier d'origine supprimé"
                Fichiers.Suppression.A_CONFIRMER -> {
                    Fichiers.uriMediatheque(ctx, uri)?.let { aConfirmer += el.id to it }
                    null
                }
                Fichiers.Suppression.IMPOSSIBLE ->
                    "Fichier d'origine gardé : l'appli d'où il vient ne permet pas de l'effacer " +
                        "(il sera effaçable s'il est ajouté avec le bouton +)"
            }
        }
        for (el in tous) {
            if (el.nettoye) continue
            val notes = mutableListOf<String>()
            when {
                el.type == Type.LIVRE && el.phase == Phase.ENVOYE -> {
                    el.copie?.let { Fichiers.supprimerCopie(ctx, it) }
                    el.sortie?.let { runCatching { File(it).delete() } }
                    runCatching { el.fichier.delete() }    // copie reçue, ou fichier venu du torrent
                    notes += "Copies effacées du téléphone (y compris dans Téléchargements › Rekindle)"
                    if (el.parent == null) effacerOrigine(el)?.let { notes += it }
                }
                el.type == Type.TORRENT && el.phase == Phase.TELECHARGE && el.id !in telechargements -> {
                    val livres = tous.filter { it.parent == el.id }
                    if (livres.isEmpty() || livres.any { it.phase != Phase.ENVOYE }) continue
                    runCatching { File(dossierTorrents, el.id.toString()).deleteRecursively() }
                    runCatching { el.fichier.delete() }
                    notes += "Fichiers du torrent effacés du téléphone"
                    effacerOrigine(el)?.let { notes += it }
                }
                else -> continue
            }
            maj(el.id) {
                it.copy(nettoye = true, sortie = null, copie = null, lignes = it.lignes + notes.map { n -> "info" to n })
            }
        }
        if (aConfirmer.isNotEmpty()) {
            val demande = Fichiers.demandeSuppression(ctx, aConfirmer.map { it.second })
            withContext(Dispatchers.Main) {
                if (demande != null) {
                    attenteConfirmation = aConfirmer.map { it.first }
                    demandeSuppression = demande
                }
            }
        }
    }

    /** Réponse de la fenêtre d'Android « Autoriser Rekindle à supprimer… ». */
    fun suppressionConfirmee(ok: Boolean) {
        val note = if (ok) "Fichier d'origine supprimé" else "Fichier d'origine gardé (suppression refusée)"
        for (id in attenteConfirmation) {
            val i = elements.indexOfFirst { it.id == id }
            if (i >= 0) elements[i] = elements[i].copy(lignes = elements[i].lignes + ("info" to note))
        }
        attenteConfirmation = emptyList()
    }

    // ------------------------------------------------------------- réglages
    fun tester(cfg: JSONObject, resultat: (String) -> Unit) {
        viewModelScope.launch(Dispatchers.IO) {
            val msg = try {
                Moteur.tester(ctx, cfg).optString("message")
            } catch (e: Exception) {
                "Erreur : ${e.message}"
            }
            withContext(Dispatchers.Main) { resultat(msg) }
        }
    }
}
