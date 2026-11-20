package fr.kwigorl.kwindle

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.core.content.IntentCompat
import org.json.JSONObject
import java.io.File

private val Encre = Color(0xFF1F3B4D)
private val Orange = Color(0xFFE6781E)
private val Vert = Color(0xFF1D7A3A)
private val Rouge = Color(0xFFC0262D)
private val Bleu = Color(0xFF2459A6)

class MainActivity : ComponentActivity() {
    private val vm: KwindleVM by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        if (savedInstanceState == null) recevoir(intent)
        setContent { ThemeKwindle { Racine(vm) } }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        recevoir(intent)
    }

    /** Fichiers reçus via « Partager » ou « Ouvrir avec ». */
    private fun recevoir(intent: Intent?) {
        intent ?: return
        val uris = mutableListOf<Uri>()
        when (intent.action) {
            Intent.ACTION_SEND ->
                IntentCompat.getParcelableExtra(intent, Intent.EXTRA_STREAM, Uri::class.java)?.let { uris += it }
            Intent.ACTION_SEND_MULTIPLE ->
                IntentCompat.getParcelableArrayListExtra(intent, Intent.EXTRA_STREAM, Uri::class.java)?.let { uris += it }
            Intent.ACTION_VIEW -> intent.data?.let { uris += it }
        }
        if (uris.isNotEmpty()) vm.ajouter(uris)
    }
}

@Composable
fun ThemeKwindle(contenu: @Composable () -> Unit) {
    val couleurs = if (isSystemInDarkTheme()) {
        darkColorScheme(primary = Color(0xFF9CC3DA), secondary = Orange, tertiary = Orange)
    } else {
        lightColorScheme(
            primary = Encre, secondary = Orange, tertiary = Orange,
            background = Color(0xFFF7F4EE), surface = Color(0xFFF7F4EE),
        )
    }
    MaterialTheme(colorScheme = couleurs, content = contenu)
}

@Composable
fun Racine(vm: KwindleVM) {
    var reglagesOuverts by rememberSaveable { mutableStateOf(false) }
    if (reglagesOuverts) {
        BackHandler { reglagesOuverts = false }
        EcranReglages(vm) { reglagesOuverts = false }
    } else {
        EcranPrincipal(vm) { reglagesOuverts = true }
    }
    val alerte = vm.alerte
    if (alerte != null) {
        AlertDialog(
            onDismissRequest = { vm.alerte = null },
            title = { Text("Envoi impossible") },
            text = { Text(alerte) },
            confirmButton = {
                TextButton(onClick = { vm.alerte = null; reglagesOuverts = true }) { Text("Réglages") }
            },
            dismissButton = { TextButton(onClick = { vm.alerte = null }) { Text("OK") } },
        )
    }
}

fun ouvrirLien(context: Context, lien: String) {
    try {
        context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(lien)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    } catch (e: Exception) {
        // pas de navigateur
    }
}

private fun titreAffiche(el: Element): String =
    if (el.titre != null) el.titre + (el.auteur?.let { "  —  $it" } ?: "") else el.nom

// ====================================================================== écran principal

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun EcranPrincipal(vm: KwindleVM, ouvrirReglages: () -> Unit) {
    val ctx = LocalContext.current
    val choisir = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris ->
        vm.ajouter(uris)
    }
    val permissionNotif = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        vm.lancer()
    }
    val lancer: () -> Unit = {
        val besoinPermission = !vm.enCours && Build.VERSION.SDK_INT >= 33 && !vm.permissionDemandee &&
            ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        if (besoinPermission) {
            vm.permissionDemandee = true
            permissionNotif.launch(Manifest.permission.POST_NOTIFICATIONS)
        } else {
            vm.lancer()
        }
    }
    val snack = remember { SnackbarHostState() }
    LaunchedEffect(vm.annonce) {
        val a = vm.annonce
        if (a != null) {
            vm.annonce = null
            snack.showSnackbar(a)
        }
    }
    var detail by remember { mutableStateOf<Long?>(null) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("Kwindle", fontWeight = FontWeight.Bold)
                        Text(
                            "Récupère, répare et envoie tes livres",
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                },
                actions = {
                    IconButton(onClick = ouvrirReglages) { Text("⚙", fontSize = 24.sp) }
                },
            )
        },
        floatingActionButton = {
            if (!vm.enCours) {
                ExtendedFloatingActionButton(
                    onClick = { choisir.launch(arrayOf("*/*")) },
                    icon = { Icon(painterResource(R.drawable.ic_ajouter), contentDescription = null) },
                    text = { Text("Ajouter") },
                    containerColor = Orange,
                    contentColor = Color.White,
                )
            }
        },
        bottomBar = { BarreBas(vm, lancer) },
        snackbarHost = { SnackbarHost(snack) },
    ) { marges ->
        if (vm.elements.isEmpty()) {
            Vide(Modifier.padding(marges))
        } else {
            LazyColumn(
                modifier = Modifier.padding(marges).fillMaxSize(),
                contentPadding = PaddingValues(start = 12.dp, top = 8.dp, end = 12.dp, bottom = 96.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                items(vm.elements, key = { it.id }) { el -> CarteElement(el) { detail = el.id } }
            }
        }
    }

    val choisi = detail?.let { id -> vm.elements.firstOrNull { it.id == id } }
    if (choisi != null) {
        Details(
            el = choisi,
            retirable = !vm.enCours,
            onFermer = { detail = null },
            onRetirer = { vm.retirer(choisi.id); detail = null },
            onPartager = { choisi.sortie?.let { Fichiers.partager(ctx, File(it)) } },
        )
    }
}

@Composable
fun Vide(modifier: Modifier) {
    Column(
        modifier = modifier.fillMaxSize().padding(32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Image(painterResource(R.drawable.logo), contentDescription = null, modifier = Modifier.size(120.dp))
        Spacer(Modifier.height(20.dp))
        Text(
            "Ajoute un livre ou un fichier .torrent",
            style = MaterialTheme.typography.titleMedium,
            textAlign = TextAlign.Center,
        )
        Spacer(Modifier.height(8.dp))
        Text(
            "Bouton « Ajouter », ou depuis une autre appli : Partager › Kwindle.\n" +
                "EPUB, MOBI, AZW3, PDF et .torrent.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
        )
    }
}

@Composable
fun CarteElement(el: Element, onClick: () -> Unit) {
    val couleur = when (el.ton) {
        Ton.OK -> Vert
        Ton.KO -> Rouge
        Ton.EN_COURS -> Bleu
        Ton.NEUTRE -> MaterialTheme.colorScheme.outline
    }
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .padding(start = if (el.parent != null) 28.dp else 0.dp)
            .clickable(onClick = onClick),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
    ) {
        Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(10.dp).clip(CircleShape).background(couleur))
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    (if (el.parent != null) "↳ " else "") + titreAffiche(el),
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    listOf(el.format, el.statut).filter { it.isNotBlank() }.joinToString("  ·  "),
                    style = MaterialTheme.typography.bodySmall,
                    color = couleur,
                )
                val p = el.progression
                if (p != null) {
                    Spacer(Modifier.height(6.dp))
                    LinearProgressIndicator(progress = { p }, modifier = Modifier.fillMaxWidth())
                }
            }
        }
    }
}

@Composable
fun BarreBas(vm: KwindleVM, lancer: () -> Unit) {
    Surface(tonalElevation = 3.dp, shadowElevation = 8.dp) {
        Row(
            Modifier.fillMaxWidth().navigationBarsPadding().padding(horizontal = 16.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Switch(checked = vm.envoyer, onCheckedChange = { vm.changerEnvoi(it) }, enabled = !vm.enCours)
            Spacer(Modifier.width(8.dp))
            Text("Envoyer à\nma Kindle", style = MaterialTheme.typography.bodySmall)
            Spacer(Modifier.weight(1f))
            Button(
                onClick = lancer,
                enabled = !vm.arretDemande,
                colors = if (vm.enCours) ButtonDefaults.buttonColors(containerColor = Rouge) else ButtonDefaults.buttonColors(),
                contentPadding = PaddingValues(horizontal = 22.dp, vertical = 12.dp),
            ) {
                Text(
                    when {
                        vm.arretDemande -> "Arrêt…"
                        vm.enCours -> "Arrêter"
                        vm.envoyer -> "Réparer et envoyer"
                        else -> "Réparer"
                    },
                    fontWeight = FontWeight.Bold,
                )
            }
        }
    }
}

@Composable
fun Details(el: Element, retirable: Boolean, onFermer: () -> Unit, onRetirer: () -> Unit, onPartager: () -> Unit) {
    AlertDialog(
        onDismissRequest = onFermer,
        title = { Text(titreAffiche(el), maxLines = 3, overflow = TextOverflow.Ellipsis) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                if (el.lignes.isEmpty()) Text(el.statut)
                for ((niveau, msg) in el.lignes) {
                    val (symbole, couleur) = when (niveau) {
                        "corrige", "envoi" -> "✓" to Vert
                        "alerte" -> "⚠" to Orange
                        "erreur" -> "✗" to Rouge
                        else -> "ℹ" to Bleu
                    }
                    Row(Modifier.padding(vertical = 3.dp)) {
                        Text(symbole, color = couleur, modifier = Modifier.width(22.dp))
                        Text(msg, color = couleur, style = MaterialTheme.typography.bodyMedium)
                    }
                }
                if (retirable) {
                    Spacer(Modifier.height(8.dp))
                    TextButton(onClick = onRetirer) { Text("Retirer de la liste") }
                }
            }
        },
        confirmButton = {
            if (el.sortie != null) TextButton(onClick = onPartager) { Text("Partager…") }
        },
        dismissButton = { TextButton(onClick = onFermer) { Text("Fermer") } },
    )
}

// ====================================================================== réglages

@Composable
private fun Section(titre: String) {
    Text(
        titre,
        style = MaterialTheme.typography.titleMedium,
        fontWeight = FontWeight.Bold,
        modifier = Modifier.padding(top = 8.dp),
    )
}

@Composable
private fun Aide(texte: String, alerte: Boolean = false) {
    Text(
        texte,
        style = MaterialTheme.typography.bodySmall,
        color = if (alerte) Rouge else MaterialTheme.colorScheme.onSurfaceVariant,
    )
}

@Composable
private fun ChoixFournisseur(valeur: String, onChoix: (String) -> Unit) {
    var ouvert by remember { mutableStateOf(false) }
    Box {
        OutlinedTextField(
            value = valeur,
            onValueChange = {},
            readOnly = true,
            label = { Text("Messagerie") },
            trailingIcon = { Text("▾") },
            modifier = Modifier.fillMaxWidth(),
        )
        Box(Modifier.matchParentSize().clickable { ouvert = true })
        DropdownMenu(expanded = ouvert, onDismissRequest = { ouvert = false }) {
            for (f in FOURNISSEURS) {
                DropdownMenuItem(text = { Text(f.nom) }, onClick = { onChoix(f.nom); ouvert = false })
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun EcranReglages(vm: KwindleVM, retour: () -> Unit) {
    val r = vm.reglages
    val ctx = LocalContext.current
    var kindle by rememberSaveable { mutableStateOf(r.kindle) }
    var nomFournisseur by rememberSaveable { mutableStateOf(r.fournisseur) }
    var expediteur by rememberSaveable { mutableStateOf(r.expediteur) }
    var mdp by rememberSaveable { mutableStateOf(r.motDePasse) }
    var voir by rememberSaveable { mutableStateOf(false) }
    var serveur by rememberSaveable { mutableStateOf(r.serveur) }
    var port by rememberSaveable { mutableStateOf(r.port.toString()) }
    var securite by rememberSaveable { mutableStateOf(r.securite) }
    var identifiant by rememberSaveable { mutableStateOf(r.identifiant) }
    var langue by rememberSaveable { mutableStateOf(r.langue) }
    var avance by rememberSaveable { mutableStateOf(false) }
    var resultatTest by remember { mutableStateOf<String?>(null) }
    var testEnCours by remember { mutableStateOf(false) }
    val f = fournisseur(nomFournisseur)

    val choisirFournisseur: (String) -> Unit = { nom ->
        nomFournisseur = nom
        val p = fournisseur(nom)
        if (nom != "Autre") {
            serveur = p.serveur
            port = p.port.toString()
            securite = p.securite
        } else {
            avance = true
        }
    }
    val enregistrer: () -> Unit = {
        r.kindle = kindle.trim()
        r.fournisseur = nomFournisseur
        r.expediteur = expediteur.trim()
        r.motDePasse = mdp
        r.serveur = serveur.trim()
        r.port = port.toIntOrNull() ?: 465
        r.securite = securite
        r.identifiant = identifiant.trim()
        r.langue = langue.trim().ifBlank { "fr" }
        retour()
    }
    val tester: () -> Unit = {
        testEnCours = true
        val cfg = JSONObject().apply {
            put("kindle", kindle.trim())
            put("fournisseur", nomFournisseur)
            put("expediteur", expediteur.trim())
            put("identifiant", identifiant.trim())
            put("serveur", serveur.trim())
            put("port", port.toIntOrNull() ?: 465)
            put("securite", securite)
            put("mdp", mdp)
        }
        vm.tester(cfg) { msg ->
            resultatTest = msg
            testEnCours = false
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Réglages") },
                navigationIcon = {
                    IconButton(onClick = retour) {
                        Icon(painterResource(R.drawable.ic_retour), contentDescription = "Retour")
                    }
                },
            )
        },
        bottomBar = {
            Surface(tonalElevation = 3.dp, shadowElevation = 8.dp) {
                Row(
                    Modifier.fillMaxWidth().navigationBarsPadding().imePadding()
                        .padding(horizontal = 16.dp, vertical = 10.dp),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    OutlinedButton(onClick = tester, enabled = !testEnCours, modifier = Modifier.weight(1f)) {
                        Text(if (testEnCours) "Connexion…" else "Tester")
                    }
                    Button(onClick = enregistrer, modifier = Modifier.weight(1f)) { Text("Enregistrer") }
                }
            }
        },
    ) { marges ->
        Column(
            Modifier.padding(marges).fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Section("Ta Kindle")
            OutlinedTextField(
                value = kindle, onValueChange = { kindle = it },
                label = { Text("Adresse Kindle") },
                placeholder = { Text("prenom_xxx@kindle.com") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
                modifier = Modifier.fillMaxWidth(),
            )
            Aide(
                "Sur amazon.fr : Gérer votre contenu et vos appareils → Préférences → Paramètres des " +
                    "documents personnels. Sur la même page, ajoute l'adresse d'envoi ci-dessous à la « liste " +
                    "des adresses e-mail approuvées », sinon Amazon ignore les livres."
            )
            OutlinedButton(onClick = { ouvrirLien(ctx, PAGE_AMAZON) }) { Text("Ouvrir la page Amazon") }

            Section("La messagerie qui envoie")
            ChoixFournisseur(nomFournisseur, choisirFournisseur)
            OutlinedTextField(
                value = expediteur, onValueChange = { expediteur = it },
                label = { Text("Adresse e-mail") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
                modifier = Modifier.fillMaxWidth(),
            )
            OutlinedTextField(
                value = mdp, onValueChange = { mdp = it },
                label = { Text("Mot de passe") },
                singleLine = true,
                visualTransformation = if (voir) VisualTransformation.None else PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                trailingIcon = {
                    TextButton(onClick = { voir = !voir }) { Text(if (voir) "Masquer" else "Afficher") }
                },
                modifier = Modifier.fillMaxWidth(),
            )
            Aide(f.aide, alerte = f.aide.startsWith("⚠"))
            if (f.lien.isNotEmpty()) {
                OutlinedButton(onClick = { ouvrirLien(ctx, f.lien) }) { Text("Créer le mot de passe d'application") }
            }

            TextButton(onClick = { avance = !avance }) {
                Text(if (avance) "Réglages avancés ▾" else "Réglages avancés ▸")
            }
            if (avance) {
                OutlinedTextField(
                    value = serveur, onValueChange = { serveur = it },
                    label = { Text("Serveur SMTP") }, singleLine = true, modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = port, onValueChange = { port = it.filter(Char::isDigit).take(5) },
                    label = { Text("Port") }, singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    modifier = Modifier.fillMaxWidth(),
                )
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("Sécurité")
                    Spacer(Modifier.width(12.dp))
                    for (option in listOf("SSL", "STARTTLS")) {
                        RadioButton(selected = securite == option, onClick = { securite = option })
                        Text(option, modifier = Modifier.clickable { securite = option })
                        Spacer(Modifier.width(12.dp))
                    }
                }
                OutlinedTextField(
                    value = identifiant, onValueChange = { identifiant = it },
                    label = { Text("Identifiant (vide = l'adresse e-mail)") },
                    singleLine = true, modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = langue, onValueChange = { langue = it },
                    label = { Text("Langue par défaut des livres") },
                    supportingText = { Text("Utilisée si un livre n'en indique aucune") },
                    singleLine = true, modifier = Modifier.fillMaxWidth(),
                )
            }
            Spacer(Modifier.height(8.dp))
        }
    }

    val res = resultatTest
    if (res != null) {
        AlertDialog(
            onDismissRequest = { resultatTest = null },
            title = { Text("Test de connexion") },
            text = { Text(res) },
            confirmButton = { TextButton(onClick = { resultatTest = null }) { Text("OK") } },
        )
    }
}
