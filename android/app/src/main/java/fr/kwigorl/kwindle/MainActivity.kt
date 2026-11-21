package fr.kwigorl.kwindle

import android.Manifest
import android.app.Activity
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.IntentSenderRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.clipRect
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.coerceIn
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.core.content.IntentCompat
import org.json.JSONObject
import java.io.File

// ====================================================================== couleurs et polices

// les couleurs propres à chaque saveur (Rekindle, Koboa) sont dans Saveur.kt
val Principale = Saveur.principale
private val PrincipaleClaire = Saveur.principaleClaire
private val Secondaire = Saveur.secondaire
private val Accent = Saveur.accent
private val AccentClair = Saveur.accentClair
private val Creme = Saveur.creme
private val Brume = Saveur.brume
private val Vert = Color(0xFF1D7A3A)
private val Orange = Color(0xFFB35C00)
private val Rouge = Color(0xFFC0262D)
private val Bleu = Color(0xFF0E6A86)

data class Palette(
    val fond: Color,
    val carte: Color,
    val bordure: Color,
    val bordureKo: Color,
    val texte: Color,
    val texteDoux: Color,
    val vagueVide: Color,
    val bouton: Color,
    val texteBouton: Color,
    val puces: Map<String, Pair<Color, Color>>,   // fond, texte
)

val LocalPalette = staticCompositionLocalOf { Saveur.paletteClaire }

val Nunito = FontFamily(
    Font(R.font.nunito_medium, FontWeight.Normal),
    Font(R.font.nunito_medium, FontWeight.Medium),
    Font(R.font.nunito_bold, FontWeight.SemiBold),
    Font(R.font.nunito_bold, FontWeight.Bold),
    Font(R.font.nunito_extrabold, FontWeight.ExtraBold),
)
val Lilita = FontFamily(Font(R.font.lilita_one))

private fun typographie(): Typography {
    val t = Typography()
    fun TextStyle.n() = copy(fontFamily = Nunito)
    return Typography(
        displayLarge = t.displayLarge.n(), displayMedium = t.displayMedium.n(), displaySmall = t.displaySmall.n(),
        headlineLarge = t.headlineLarge.n(), headlineMedium = t.headlineMedium.n(), headlineSmall = t.headlineSmall.n(),
        titleLarge = t.titleLarge.n().copy(fontWeight = FontWeight.ExtraBold),
        titleMedium = t.titleMedium.n().copy(fontWeight = FontWeight.ExtraBold),
        titleSmall = t.titleSmall.n().copy(fontWeight = FontWeight.Bold),
        bodyLarge = t.bodyLarge.n(), bodyMedium = t.bodyMedium.n(), bodySmall = t.bodySmall.n(),
        labelLarge = t.labelLarge.n().copy(fontWeight = FontWeight.Bold),
        labelMedium = t.labelMedium.n(), labelSmall = t.labelSmall.n(),
    )
}

class MainActivity : ComponentActivity() {
    private val vm: RekindleVM by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // barre d'état claire sur l'en-tête bleu marine
        enableEdgeToEdge(statusBarStyle = SystemBarStyle.dark(android.graphics.Color.TRANSPARENT))
        if (savedInstanceState == null) recevoir(intent)
        setContent { ThemeAppli { Racine(vm) } }
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
fun ThemeAppli(contenu: @Composable () -> Unit) {
    val sombre = isSystemInDarkTheme()
    val pal = if (sombre) Saveur.paletteSombre else Saveur.paletteClaire
    val couleurs = if (sombre) {
        darkColorScheme(
            primary = Saveur.primaireSombre, onPrimary = Principale, secondary = Accent, onSecondary = Principale,
            tertiary = Accent, background = pal.fond, surface = pal.fond, onSurface = pal.texte,
            surfaceVariant = pal.carte, onSurfaceVariant = pal.texteDoux, surfaceContainerHigh = pal.carte,
            outline = Saveur.contourSombre, error = Color(0xFFFFB4AB),
        )
    } else {
        lightColorScheme(
            primary = Principale, onPrimary = Creme, secondary = Accent, onSecondary = Principale,
            tertiary = Accent, background = pal.fond, surface = pal.fond, onSurface = pal.texte,
            surfaceVariant = Saveur.varianteClaire, onSurfaceVariant = pal.texteDoux,
            surfaceContainerHigh = Color.White, outline = Saveur.contourClair, error = Rouge,
        )
    }
    CompositionLocalProvider(LocalPalette provides pal) {
        MaterialTheme(colorScheme = couleurs, typography = typographie(), content = contenu)
    }
}

@Composable
fun Racine(vm: RekindleVM) {
    var reglagesOuverts by rememberSaveable { mutableStateOf(false) }
    val confirmer = rememberLauncherForActivityResult(ActivityResultContracts.StartIntentSenderForResult()) {
        vm.suppressionConfirmee(it.resultCode == Activity.RESULT_OK)
    }
    val demande = vm.demandeSuppression
    LaunchedEffect(demande) {
        if (demande != null) {
            vm.demandeSuppression = null
            runCatching { confirmer.launch(IntentSenderRequest.Builder(demande).build()) }
                .onFailure { vm.suppressionConfirmee(false) }
        }
    }
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

private fun pluriel(n: Int, mot: String) = "$n $mot" + if (n > 1) "s" else ""

/** Le nom de l'appli : certains morceaux dans la couleur d'accent (« Rekin » en corail, « boa » en ambre). */
@Composable
fun NomAppli(taille: TextUnit, couleur: Color, modifier: Modifier = Modifier) {
    Text(
        buildAnnotatedString {
            for ((morceau, enCouleur) in Saveur.PARTIES_NOM) {
                if (enCouleur) withStyle(SpanStyle(color = Accent)) { append(morceau) } else append(morceau)
            }
        },
        fontFamily = Lilita, fontSize = taille, color = couleur, modifier = modifier,
    )
}

// ====================================================================== écran principal

@Composable
fun EcranPrincipal(vm: RekindleVM, ouvrirReglages: () -> Unit) {
    val ctx = LocalContext.current
    val pal = LocalPalette.current
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

    // ce que l'en-tête raconte
    val hauts = vm.elements.filter { it.parent == null }
    val livresAFaire = vm.elements.count {
        it.type == Type.LIVRE && (it.phase in setOf(Phase.ATTENTE, Phase.ERREUR, Phase.ECHEC_ENVOI) ||
            (vm.envoyer && it.phase == Phase.PRET))
    }
    val nDl = vm.telechargements.size
    val dlEnCours = pluriel(nDl, "torrent") + " en cours"
    val (surTitre, titre) = when {
        vm.enCours -> "Au travail" to (if (vm.envoyer) "Transformation et envoi…" else "Transformation…")
        hauts.isEmpty() -> "Bienvenue" to "Aucun livre pour l'instant"
        livresAFaire > 0 -> (if (vm.envoyer) "Prêt à envoyer" else "Prêt à transformer") to
            (pluriel(livresAFaire, "livre") + if (nDl > 0) " · $dlEnCours" else "")
        nDl > 0 -> "Téléchargement" to dlEnCours
        else -> "Tout est fait" to (pluriel(hauts.size, "élément") + " traité" + if (hauts.size > 1) "s" else "")
    }
    val kindle = vm.reglages.kindle
    val sousTitre = if (kindle.isNotBlank()) "vers $kindle" else Saveur.ADRESSE_A_REGLER

    Scaffold(
        containerColor = pal.fond,
        bottomBar = { BarreBas(vm, lancer) { choisir.launch(arrayOf("*/*")) } },
        snackbarHost = { SnackbarHost(snack) },
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
    ) { marges ->
        Column(Modifier.padding(marges).fillMaxSize()) {
            EnTete(surTitre, titre, sousTitre, if (kindle.isBlank()) ouvrirReglages else null, ouvrirReglages)
            if (vm.elements.isEmpty()) {
                Vide(Modifier.weight(1f))
            } else {
                Row(
                    Modifier.fillMaxWidth().padding(start = 20.dp, end = 20.dp, top = 4.dp, bottom = 10.dp),
                    verticalAlignment = Alignment.Bottom,
                ) {
                    Text(
                        "MES LIVRES", fontWeight = FontWeight.ExtraBold, fontSize = 14.sp, letterSpacing = 1.5.sp,
                        color = pal.texte, modifier = Modifier.weight(1f),
                    )
                    val nl = hauts.count { it.type == Type.LIVRE } + vm.elements.count { it.parent != null }
                    val nt = hauts.count { it.type == Type.TORRENT }
                    Text(
                        listOfNotNull(
                            if (nl > 0) pluriel(nl, "livre") else null,
                            if (nt > 0) pluriel(nt, "torrent") else null,
                        ).joinToString(" · "),
                        fontSize = 13.sp, color = pal.texteDoux,
                    )
                }
                LazyColumn(
                    modifier = Modifier.weight(1f).fillMaxWidth(),
                    contentPadding = PaddingValues(start = 20.dp, top = 0.dp, end = 20.dp, bottom = 16.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    items(vm.elements, key = { it.id }) { el -> CarteElement(el) { detail = el.id } }
                }
            }
        }
    }

    val choisi = detail?.let { id -> vm.elements.firstOrNull { it.id == id } }
    if (choisi != null) {
        val dl = vm.enTelechargement(choisi.id)
        Details(
            el = choisi,
            retirable = !vm.enCours || dl,
            enTelechargement = dl,
            onReessayer = if (choisi.type == Type.TORRENT && choisi.phase == Phase.ERREUR && !dl) {
                { vm.telecharger(choisi.id); detail = null }
            } else null,
            onFermer = { detail = null },
            onRetirer = { vm.retirer(choisi.id); detail = null },
            onPartager = { choisi.sortie?.let { Fichiers.partager(ctx, File(it)) } },
        )
    }
}

@Composable
fun EnTete(surTitre: String, titre: String, sousTitre: String, onSousTitre: (() -> Unit)?, ouvrirReglages: () -> Unit) {
    val pal = LocalPalette.current
    Box(Modifier.fillMaxWidth().background(Principale)) {
        Column(
            Modifier.fillMaxWidth().statusBarsPadding()
                .padding(start = 20.dp, end = 16.dp, top = 12.dp, bottom = 40.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    Modifier.size(42.dp).clip(RoundedCornerShape(12.dp)).background(PrincipaleClaire),
                    contentAlignment = Alignment.Center,
                ) {
                    Image(painterResource(R.drawable.tete), contentDescription = null, modifier = Modifier.size(Saveur.tailleTete))
                }
                Spacer(Modifier.width(10.dp))
                NomAppli(30.sp, Creme, Modifier.weight(1f))
                IconButton(
                    onClick = ouvrirReglages,
                    modifier = Modifier.size(44.dp).clip(RoundedCornerShape(14.dp)).background(PrincipaleClaire),
                ) {
                    Icon(
                        painterResource(R.drawable.ic_reglages), contentDescription = "Réglages",
                        tint = Creme, modifier = Modifier.size(22.dp),
                    )
                }
            }
            Spacer(Modifier.height(18.dp))
            Text(
                surTitre.uppercase(), color = AccentClair, fontSize = 12.sp,
                fontWeight = FontWeight.ExtraBold, letterSpacing = 1.5.sp,
            )
            Text(
                titre, color = Color.White, fontSize = 26.sp, lineHeight = 30.sp, fontWeight = FontWeight.ExtraBold,
                maxLines = 2, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(end = 56.dp),
            )
            Text(
                sousTitre, color = if (onSousTitre != null) AccentClair else Brume, fontSize = 13.sp,
                maxLines = 1, overflow = TextOverflow.Ellipsis,
                modifier = if (onSousTitre != null) Modifier.clickable(onClick = onSousTitre) else Modifier,
            )
        }
        Image(
            painterResource(R.drawable.deco_entete), contentDescription = null,
            modifier = Modifier.align(Alignment.BottomEnd).padding(end = 34.dp, bottom = 12.dp).size(Saveur.tailleDeco),
        )
        Vague(pal.fond, Modifier.align(Alignment.BottomStart).fillMaxWidth().height(26.dp))
    }
}

/** Bord inférieur en vagues. */
@Composable
fun Vague(couleur: Color, modifier: Modifier) {
    Canvas(modifier) {
        val periode = 48.dp.toPx()
        val milieu = size.height * 0.5f
        val chemin = Path().apply {
            moveTo(0f, milieu)
            var x = 0f
            var haut = true
            while (x < size.width) {
                quadraticTo(x + periode / 4, if (haut) 0f else size.height, x + periode / 2, milieu)
                x += periode / 2
                haut = !haut
            }
            lineTo(x, size.height + 1)
            lineTo(0f, size.height + 1)
            close()
        }
        drawPath(chemin, couleur)
    }
}

@Composable
fun Vide(modifier: Modifier) {
    val pal = LocalPalette.current
    Column(
        modifier = modifier.fillMaxWidth().padding(horizontal = 32.dp, vertical = 16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Image(
            painterResource(R.drawable.mascotte), contentDescription = Saveur.DESCRIPTION_MASCOTTE,
            modifier = Modifier.size(Saveur.tailleMascotte),
        )
        Spacer(Modifier.height(14.dp))
        Text(
            "Ajoute un livre ou un fichier .torrent",
            style = MaterialTheme.typography.titleMedium, color = pal.texte, textAlign = TextAlign.Center,
        )
        Spacer(Modifier.height(6.dp))
        Text(
            "Bouton +, ou depuis une autre appli : Partager › ${Saveur.NOM}.\nEPUB, MOBI, AZW3, PDF et .torrent (téléchargé dès l'ajout).",
            style = MaterialTheme.typography.bodyMedium, color = pal.texteDoux, textAlign = TextAlign.Center,
        )
    }
}

private fun cleDePuce(el: Element): String = when {
    el.ton == Ton.EN_COURS -> "encours"
    el.ton == Ton.KO -> "ko"
    el.phase == Phase.ENVOYE -> "envoye"
    el.phase == Phase.PRET || el.phase == Phase.TELECHARGE -> "repare"
    else -> "neutre"
}

private fun texteDePuce(el: Element): String {
    var t = el.statut.trimStart('✓', '✗', '■', ' ')
    if (el.phase == Phase.PRET) {
        val n = el.lignes.count { it.first == "corrige" }
        if (n > 0) t += " · " + pluriel(n, "correction")
    }
    return t
}

@Composable
fun Puce(texte: String, cle: String, modifier: Modifier = Modifier) {
    val (fond, encre) = LocalPalette.current.puces.getValue(cle)
    Text(
        texte, color = encre, fontSize = 12.sp, fontWeight = FontWeight.Bold, maxLines = 1,
        modifier = modifier.clip(RoundedCornerShape(50)).background(fond).padding(horizontal = 10.dp, vertical = 4.dp),
    )
}

@Composable
fun CarteElement(el: Element, onClick: () -> Unit) {
    val pal = LocalPalette.current
    val ko = el.ton == Ton.KO
    Column(
        Modifier
            .fillMaxWidth()
            .padding(start = if (el.parent != null) 20.dp else 0.dp)
            .clip(RoundedCornerShape(20.dp))
            .background(pal.carte)
            .border(1.5.dp, if (ko) pal.bordureKo else pal.bordure, RoundedCornerShape(20.dp))
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 13.dp),
    ) {
        val p = el.progression
        val sousTitre = when {
            el.type == Type.TORRENT -> null
            el.auteur != null -> el.auteur
            el.format.isNotBlank() -> el.format
            else -> null
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(
                    el.titre ?: el.nom, color = pal.texte, fontSize = 16.sp, fontWeight = FontWeight.ExtraBold,
                    maxLines = 2, overflow = TextOverflow.Ellipsis,
                )
                if (sousTitre != null) {
                    Text(sousTitre, color = pal.texteDoux, fontSize = 13.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
            }
            Spacer(Modifier.width(10.dp))
            if (el.type == Type.TORRENT && (p != null || el.ton == Ton.NEUTRE)) {
                Puce("Torrent", "torrent")
            } else {
                Puce(texteDePuce(el), cleDePuce(el))
            }
        }
        if (el.type == Type.TORRENT && (p != null || el.ton == Ton.NEUTRE)) {
            if (p != null) {
                Spacer(Modifier.height(6.dp))
                ProgressionVague(p)
            }
            Text(
                el.statut, color = if (p != null) Bleu else pal.texteDoux, fontSize = 12.sp,
                fontWeight = FontWeight.ExtraBold, maxLines = 1, overflow = TextOverflow.Ellipsis,
            )
        } else if (p != null) {
            Spacer(Modifier.height(6.dp))
            ProgressionVague(p)
        }
    }
}

/** Barre de progression en forme de vague, avec la mascotte (aileron, boa) qui avance. */
@Composable
fun ProgressionVague(p: Float) {
    val pal = LocalPalette.current
    val q = p.coerceIn(0f, 1f)
    BoxWithConstraints(Modifier.fillMaxWidth().height(26.dp)) {
        Canvas(Modifier.fillMaxSize()) {
            val y = size.height * 0.62f
            val amp = 3.dp.toPx()
            val periode = 20.dp.toPx()
            val chemin = Path().apply {
                moveTo(0f, y)
                var x = 0f
                var haut = true
                while (x < size.width) {
                    quadraticTo(x + periode / 4, if (haut) y - 2 * amp else y + 2 * amp, x + periode / 2, y)
                    x += periode / 2
                    haut = !haut
                }
            }
            val trait = Stroke(3.dp.toPx(), cap = StrokeCap.Round)
            drawPath(chemin, pal.vagueVide, style = trait)
            clipRect(right = size.width * q) { drawPath(chemin, Secondaire, style = trait) }
        }
        Image(
            painterResource(R.drawable.ic_progression), contentDescription = null,
            modifier = Modifier.offset(
                x = (maxWidth * q - Saveur.tailleProgression.width / 2)
                    .coerceIn(0.dp, maxWidth - Saveur.tailleProgression.width),
                y = 0.dp,
            ).size(Saveur.tailleProgression),
        )
    }
}

@Composable
fun BarreBas(vm: RekindleVM, lancer: () -> Unit, ajouter: () -> Unit) {
    val pal = LocalPalette.current
    Column(
        Modifier.fillMaxWidth().background(pal.fond).navigationBarsPadding()
            .padding(start = 20.dp, end = 20.dp, top = 4.dp, bottom = 14.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                Saveur.ENVOYER_A, color = pal.texte, fontWeight = FontWeight.Bold, fontSize = 15.sp,
                modifier = Modifier.weight(1f),
            )
            Switch(
                checked = vm.envoyer, onCheckedChange = { vm.changerEnvoi(it) }, enabled = !vm.enCours,
                colors = SwitchDefaults.colors(checkedTrackColor = Secondaire, checkedThumbColor = Color.White),
            )
        }
        Spacer(Modifier.height(8.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Button(
                onClick = ajouter,
                enabled = !vm.enCours,
                shape = RoundedCornerShape(18.dp),
                colors = ButtonDefaults.buttonColors(containerColor = Accent, contentColor = Principale),
                contentPadding = PaddingValues(0.dp),
                modifier = Modifier.size(58.dp),
            ) {
                Icon(
                    painterResource(R.drawable.ic_ajouter), contentDescription = "Ajouter un livre ou un torrent",
                    modifier = Modifier.size(28.dp),
                )
            }
            Button(
                onClick = lancer,
                enabled = !vm.arretDemande,
                shape = RoundedCornerShape(18.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = if (vm.enCours) Rouge else pal.bouton,
                    contentColor = if (vm.enCours) Color.White else pal.texteBouton,
                ),
                contentPadding = PaddingValues(horizontal = 14.dp),
                modifier = Modifier.weight(1f).height(58.dp),
            ) {
                if (!vm.enCours) {
                    // la mascotte, transformée (dorée, lunettes de soleil)
                    Image(
                        painterResource(R.drawable.ic_transforme), contentDescription = null,
                        modifier = Modifier.size(Saveur.tailleTransforme),
                    )
                    Spacer(Modifier.width(10.dp))
                }
                Text(
                    when {
                        vm.arretDemande -> "Arrêt…"
                        vm.enCours -> "Arrêter"
                        vm.envoyer -> "Transformer et envoyer"
                        else -> "Transformer"
                    },
                    // tient sur une ligne dès ~360 dp de large ; en dessous, passe à la ligne
                    fontWeight = FontWeight.ExtraBold, fontSize = 17.sp, lineHeight = 19.sp,
                    textAlign = TextAlign.Center,
                )
            }
        }
    }
}

@Composable
fun Details(
    el: Element,
    retirable: Boolean,
    enTelechargement: Boolean,
    onReessayer: (() -> Unit)?,
    onFermer: () -> Unit,
    onRetirer: () -> Unit,
    onPartager: () -> Unit,
) {
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
                if (onReessayer != null) {
                    Spacer(Modifier.height(8.dp))
                    TextButton(onClick = onReessayer) { Text("Réessayer le téléchargement") }
                }
                if (retirable) {
                    if (onReessayer == null) Spacer(Modifier.height(8.dp))
                    TextButton(onClick = onRetirer) {
                        Text(if (enTelechargement) "Annuler le téléchargement" else "Retirer de la liste")
                    }
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
private fun LigneInterrupteur(
    titre: String,
    aide: String,
    coche: Boolean,
    actif: Boolean = true,
    onChange: (Boolean) -> Unit,
) {
    val pal = LocalPalette.current
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp))
            .clickable(enabled = actif) { onChange(!coche) }.padding(vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f).padding(end = 12.dp)) {
            Text(
                titre, fontWeight = FontWeight.Bold, fontSize = 15.sp,
                color = if (actif) pal.texte else pal.texteDoux,
            )
            Text(aide, style = MaterialTheme.typography.bodySmall, color = pal.texteDoux)
        }
        Switch(
            checked = coche, onCheckedChange = onChange, enabled = actif,
            colors = SwitchDefaults.colors(checkedTrackColor = Secondaire, checkedThumbColor = Color.White),
        )
    }
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
fun EcranReglages(vm: RekindleVM, retour: () -> Unit) {
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
    var tome by rememberSaveable { mutableStateOf(r.tomeDansTitre) }
    var supprimer by rememberSaveable { mutableStateOf(r.supprimerApresEnvoi) }
    var supprimerOrigine by rememberSaveable { mutableStateOf(r.supprimerOrigine) }
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
        r.tomeDansTitre = tome
        r.supprimerApresEnvoi = supprimer
        r.supprimerOrigine = supprimer && supprimerOrigine
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
        containerColor = LocalPalette.current.fond,
        topBar = {
            TopAppBar(
                title = { Text("Réglages", fontWeight = FontWeight.ExtraBold) },
                navigationIcon = {
                    IconButton(onClick = retour) {
                        Icon(painterResource(R.drawable.ic_retour), contentDescription = "Retour")
                    }
                },
                actions = {
                    Image(
                        painterResource(R.drawable.tete), contentDescription = null,
                        modifier = Modifier.padding(end = 14.dp).size(Saveur.tailleTeteBarre),
                    )
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = Principale,
                    titleContentColor = Creme,
                    navigationIconContentColor = Creme,
                ),
            )
        },
        bottomBar = {
            Surface(color = LocalPalette.current.fond, shadowElevation = 8.dp) {
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
            Section(Saveur.SECTION_LISEUSE)
            OutlinedTextField(
                value = kindle, onValueChange = { kindle = it },
                label = { Text(Saveur.LIBELLE_ADRESSE) },
                placeholder = { Text(Saveur.EXEMPLE_ADRESSE) },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
                modifier = Modifier.fillMaxWidth(),
            )
            Aide(Saveur.AIDE_ADRESSE)
            OutlinedButton(onClick = { ouvrirLien(ctx, Saveur.PAGE_AIDE) }) { Text(Saveur.LIBELLE_PAGE_AIDE) }

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

            Section("Livres")
            LigneInterrupteur(
                "Numéro de tome dans le titre",
                Saveur.AIDE_TOME,
                tome,
            ) { tome = it }

            Section("Après l'envoi")
            LigneInterrupteur(
                "Supprimer les fichiers une fois envoyés",
                "${Saveur.NOM} efface le livre réparé (y compris sa copie dans Téléchargements › ${Saveur.NOM}) " +
                    "et les fichiers téléchargés par torrent, dès que l'envoi ${Saveur.VERS_LA_LISEUSE} a réussi.",
                supprimer,
            ) { supprimer = it }
            LigneInterrupteur(
                "Supprimer aussi le fichier d'origine",
                "Le .torrent ou le livre que tu as ouvert (par exemple dans Téléchargements). Ça marche à " +
                    "coup sûr pour un fichier ajouté avec le bouton + ; pour un fichier venu d'une autre appli, " +
                    "Android peut te demander de confirmer, ou refuser.",
                supprimer && supprimerOrigine,
                actif = supprimer,
            ) { supprimerOrigine = it }

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
