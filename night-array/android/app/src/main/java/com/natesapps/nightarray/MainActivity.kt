package com.natesapps.nightarray

import android.content.Context
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.animation.*
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Explore
import androidx.compose.material.icons.outlined.FolderOpen
import androidx.compose.material.icons.outlined.Straighten
import androidx.compose.material.icons.outlined.ViewInAr
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.listSaver
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(android.graphics.Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.dark(android.graphics.Color.TRANSPARENT),
        )
        super.onCreate(savedInstanceState)
        setContent {
            // The back stack, the viewer state and the Studio/Specs choices survive recreation and process death.
            val app = rememberSaveable(saver = appStateSaver(applicationContext)) { AppState(applicationContext) }
            AppTheme { App(app) }
        }
    }
}

/** Back stack of string routes: explore, story/<id>, board, studio, files, group/<id>, drawing/<id>, specs[/<section>]. */
class Nav(start: String = "explore") {
    val stack = mutableStateListOf(start)
    var forward by mutableStateOf(true); private set
    var tabSwitch by mutableStateOf(false); private set
    val top: String get() = stack.last()
    val canBack: Boolean get() = stack.size > 1 || top != "explore"

    fun go(route: String) { if (route != top) { forward = true; tabSwitch = false; stack.add(route) } }
    fun tab(route: String) {
        forward = TABS.indexOfFirst { it.route == route } >= TABS.indexOfFirst { it.route == tabOf(top) }
        tabSwitch = true; stack.clear(); stack.add(route)
    }
    /** Pops a screen; at a tab root other than Explore, returns to Explore. */
    fun back(): Boolean {
        if (stack.size > 1) { forward = false; tabSwitch = false; stack.removeAt(stack.lastIndex); return true }
        if (top != "explore") { tab("explore"); forward = false; return true }
        return false
    }
}

data class Tab(val route: String, val label: String, val icon: ImageVector)
val TABS = listOf(
    Tab("explore", "Explore", Icons.Outlined.Explore),
    Tab("studio", "Studio", Icons.Outlined.ViewInAr),
    Tab("files", "Files", Icons.Outlined.FolderOpen),
    Tab("specs", "Specs", Icons.Outlined.Straighten),
)

fun tabOf(route: String): String = when (route.substringBefore('/')) {
    "studio" -> "studio"
    "files", "group", "drawing" -> "files"
    "specs" -> "specs"
    else -> "explore"
}

/** Everything that outlives a single screen: navigation, the shared live viewer, overlays. */
class AppState(ctx: Context, start: String = "explore") {
    val nav = Nav(start)
    val host = ViewerHost(ctx.applicationContext)
    var nightShift by mutableStateOf(false); private set
    var toast by mutableStateOf<String?>(null)
    /** Which Studio control tab is open (null = collapsed). Survives navigation. */
    var studioPanel by mutableStateOf<String?>(null)
    /** Scroll positions that should survive a trip into a detail screen and back. */
    val exploreList = LazyListState()
    val filesList = LazyListState()
    /** Specs tab + the desk you entered in Desk fit (cm). */
    var specsTab by mutableStateOf("sheet")
    var deskW by mutableIntStateOf(160)
    var deskD by mutableIntStateOf(80)
    /** Work that should finish even if the screen that started it goes away (e.g. a Save copy). Cancelled with the app UI. */
    val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)

    /** Opens the Studio, optionally with a preset. Pushes so Back returns to where you were. */
    fun openStudio(p: Preset? = null) {
        if (p != null) {
            host.apply(p)
            studioPanel = when {
                p.dock != null -> "dock"
                p.finish != null || p.amber != null -> "finish"
                p.isolate != null -> null
                else -> studioPanel
            }
        }
        if (nav.top == "studio") return
        if (tabOf(nav.top) == "studio") nav.tab("studio") else nav.go("studio")
    }

    /** Opens a Specs segment (sheet, bom, fit, buy). Pushes like [openStudio] so Back returns to where you were. */
    fun openSpecs(section: String) {
        specsTab = section
        if (tabOf(nav.top) == "specs") nav.tab("specs") else nav.go("specs")
    }

    init {
        // Lighter rendering on low-memory phones; the user can still pick High in Tools.
        val am = ctx.getSystemService(Context.ACTIVITY_SERVICE) as? android.app.ActivityManager
        if (am?.isLowRamDevice == true) host.state.quality = "balanced"
    }

    fun startNight() { if (!nightShift) { host.enterNight(); nightShift = true } }
    fun stopNight() { if (nightShift) { nightShift = false; host.exitNight() } }
}

/**
 * Saved as [viewer state JSON, camera, Studio panel, Specs tab, "deskW,deskD", routes…]. A bundle that holds only
 * routes (from an older build) still restores its back stack.
 */
fun appStateSaver(ctx: Context) = listSaver<AppState, String>(
    save = { listOf(it.host.snapshot().toString(), it.host.lastCamera, it.studioPanel ?: "", it.specsTab, "${it.deskW},${it.deskD}") + it.nav.stack.toList() },
    restore = { saved ->
        AppState(ctx).apply {
            val routes = if (saved.firstOrNull()?.startsWith("{") == true && saved.size >= 5) {
                val scene = Repo.scene(ctx)
                host.restore(saved[0], saved[1]) { scene.group(it) != null }
                studioPanel = saved[2].ifBlank { null }
                specsTab = saved[3].ifBlank { specsTab }
                saved[4].split(',').mapNotNull { it.trim().toIntOrNull() }.takeIf { it.size == 2 }?.let { (w, d) ->
                    deskW = w.coerceIn(1, 999); deskD = d.coerceIn(1, 999)
                }
                saved.drop(5)
            } else saved
            if (routes.isNotEmpty()) { nav.stack.clear(); nav.stack.addAll(routes) }
        }
    },
)

@Composable
fun App(app: AppState) {
    val ctx = LocalContext.current
    val scene = remember { Repo.scene(ctx) }
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    DisposableEffect(lifecycle, app.host) {
        val obs = LifecycleEventObserver { _, e ->
            when (e) {
                Lifecycle.Event.ON_RESUME -> app.host.onResume()
                Lifecycle.Event.ON_PAUSE -> app.host.onPause()
                else -> {}
            }
        }
        lifecycle.addObserver(obs)
        onDispose { lifecycle.removeObserver(obs); app.host.destroy(); app.scope.cancel() }
    }
    BackHandler(enabled = app.nav.canBack && !app.nightShift) { app.nav.back() }

    BoxWithConstraints(Modifier.fillMaxSize().background(C.bg)) {
        val wide = (maxWidth >= 600.dp && maxWidth > maxHeight) || maxWidth >= 840.dp
        val route = app.nav.top
        val content: @Composable (Modifier) -> Unit = { m -> Routes(app, scene, route, m) }
        if (wide) {
            Row(Modifier.fillMaxSize()) {
                SideRail(app.nav, route)
                content(Modifier.weight(1f).fillMaxHeight())
            }
        } else {
            Column(Modifier.fillMaxSize()) {
                content(Modifier.weight(1f).fillMaxWidth())
                BottomBar(app.nav, route)
            }
        }
        AnimatedVisibility(app.nightShift, enter = fadeIn(tween(700)), exit = fadeOut(tween(450))) {
            NightShift(app, scene)
        }
        ToastHost(app)
    }
}

@Composable
private fun Routes(app: AppState, scene: Scene, route: String, modifier: Modifier) {
    val nav = app.nav
    AnimatedContent(
        targetState = route,
        transitionSpec = {
            if (nav.tabSwitch) fadeIn(tween(320, delayMillis = 60)) togetherWith fadeOut(tween(200))
            else {
                val dir = if (nav.forward) 1 else -1
                (slideInHorizontally(tween(380, easing = FastOutSlowInEasing)) { it / 6 * dir } + fadeIn(tween(340))) togetherWith
                    (slideOutHorizontally(tween(300, easing = FastOutSlowInEasing)) { -it / 8 * dir } + fadeOut(tween(220)))
            }
        },
        modifier = modifier.background(C.bg),
        label = "nav",
    ) { r ->
        val parts = r.split("/")
        when (parts[0]) {
            "story" -> StoryScreen(app, scene, parts.getOrElse(1) { "" })
            "board" -> BoardScreen(app)
            "studio" -> StudioScreen(app, scene)
            "files" -> FilesScreen(app, scene)
            "group" -> GroupScreen(app, scene, parts.getOrElse(1) { "" })
            "drawing" -> DrawingScreen(app, scene, parts.getOrElse(1) { "" })
            "specs" -> SpecsScreen(app, scene, parts.getOrNull(1))
            else -> ExploreScreen(app, scene)
        }
    }
}

@Composable
private fun BottomBar(nav: Nav, route: String) {
    val cur = tabOf(route)
    Column(Modifier.fillMaxWidth().background(C.bg)) {
        Box(Modifier.fillMaxWidth().height(1.dp).background(C.line))
        // grows with large font scales instead of clipping the labels
        Row(Modifier.fillMaxWidth().navigationBarsPadding().heightIn(min = 62.dp), verticalAlignment = Alignment.CenterVertically) {
            TABS.forEach { t -> NavItem(t, cur == t.route, Modifier.weight(1f)) { nav.tab(t.route) } }
        }
    }
}

@Composable
private fun SideRail(nav: Nav, route: String) {
    val cur = tabOf(route)
    Row(Modifier.fillMaxHeight()) {
        Column(
            Modifier.fillMaxHeight().width(88.dp).background(C.bg).statusBarsPadding().navigationBarsPadding().padding(vertical = 18.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text("N·A", color = C.amber, fontSize = 13.sp, letterSpacing = 3.sp)
            Spacer(Modifier.height(28.dp))
            TABS.forEach { t -> NavItem(t, cur == t.route, Modifier.padding(vertical = 6.dp).width(76.dp).heightIn(min = 64.dp)) { nav.tab(t.route) } }
        }
        Box(Modifier.fillMaxHeight().width(1.dp).background(C.line))
    }
}

@Composable
private fun NavItem(t: Tab, selected: Boolean, modifier: Modifier, onClick: () -> Unit) {
    val w by animateDpAsState(if (selected) 18.dp else 0.dp, tween(260), label = "navw")
    Column(
        modifier.semantics { this.selected = selected }.testTag("tab-${t.route}").clip(RoundedCornerShape(12.dp))
            .clickable(role = Role.Tab, onClick = onClick).padding(vertical = 6.dp),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center,
    ) {
        Box(Modifier.width(w).height(1.5.dp).background(C.amber))
        Spacer(Modifier.height(6.dp))
        Icon(t.icon, null, tint = if (selected) C.ink else C.muted, modifier = Modifier.size(22.dp))
        Spacer(Modifier.height(4.dp))
        // Tracked() tightens the letter spacing by itself at large font scales, so the label stays on one line
        Tracked(t.label, size = Type.Micro, color = if (selected) C.ink else C.muted, tracking = 0.2f, weight = androidx.compose.ui.text.font.FontWeight.Normal, maxLines = 1)
    }
}

@Composable
private fun BoxScope.ToastHost(app: AppState) {
    val msg = app.toast
    var shown by remember { mutableStateOf("") }
    LaunchedEffect(msg) { if (msg != null) { shown = msg; delay(2600); app.toast = null } }
    AnimatedVisibility(
        msg != null, enter = slideInVertically { it } + fadeIn(), exit = slideOutVertically { it } + fadeOut(),
        modifier = Modifier.align(Alignment.BottomCenter).navigationBarsPadding().padding(bottom = 80.dp, start = 24.dp, end = 24.dp),
    ) {
        Text(
            shown, color = C.ink, fontSize = 14.sp,
            modifier = Modifier.clip(RoundedCornerShape(14.dp)).background(C.panel2).padding(horizontal = 18.dp, vertical = 12.dp),
        )
    }
}
