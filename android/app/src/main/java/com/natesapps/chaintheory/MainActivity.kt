package com.natesapps.chaintheory

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.animation.*
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge(statusBarStyle = SystemBarStyle.dark(android.graphics.Color.TRANSPARENT), navigationBarStyle = SystemBarStyle.dark(android.graphics.Color.TRANSPARENT))
        super.onCreate(savedInstanceState)
        val store = Store(applicationContext)
        setContent { AppTheme { App(store) } }
    }
}

class Nav(start: String) {
    val stack = mutableStateListOf(start)
    var forward by mutableStateOf(true)
    val top get() = stack.last()
    fun go(route: String) { if (route != top) { forward = true; stack.add(route) } }
    fun tab(route: String) { forward = true; stack.clear(); stack.add(route) }
    fun back(): Boolean { if (stack.size <= 1) return false; forward = false; stack.removeAt(stack.lastIndex); return true }
    fun replace(route: String) { stack[stack.lastIndex] = route }
    /** Handle in-content links such as "#l2" or "#read/comp/224". */
    fun link(href: String) {
        val h = href.removePrefix("#").substringBefore('?')
        go(when {
            h in listOf("l1", "l2", "l3", "primer") -> "article/$h"
            h == "l4" -> "map"
            h.startsWith("read/") -> "reader/" + h.removePrefix("read/")
            h.isEmpty() || h == "home" -> "home"
            else -> h
        })
    }
}

data class Tab(val route: String, val label: String, val icon: ImageVector)
val TABS = listOf(
    Tab("home", "Home", Icons.Rounded.Home),
    Tab("learn", "Learn", Icons.Rounded.School),
    Tab("play", "Play", Icons.Rounded.SportsEsports),
    Tab("library", "Library", Icons.Rounded.MenuBook),
    Tab("search", "Search", Icons.Rounded.Search),
)

fun tabOf(route: String): String = when {
    route.startsWith("article") || route == "map" || route == "calc" || route == "glossary" || route == "learn" -> "learn"
    route.startsWith("quiz") || route == "flash" || route == "play" -> "play"
    route.startsWith("reader") || route == "library" -> "library"
    route == "search" -> "search"
    else -> "home"
}

@Composable
fun App(store: Store, nav: Nav = remember { Nav("home") }) {
    val ctx = LocalContext.current
    val content = remember { Repo.content(ctx) }
    BackHandler(enabled = nav.stack.size > 1) { nav.back() }
    val route = nav.top
    val immersive = route.startsWith("reader") || route.startsWith("quiz") || route == "flash"

    Box(Modifier.fillMaxSize()) {
        Scaffold(
            containerColor = C.bg,
            bottomBar = {
                AnimatedVisibility(!immersive, enter = slideInVertically { it } + fadeIn(), exit = slideOutVertically { it } + fadeOut()) {
                    NavigationBar(containerColor = C.panel, tonalElevation = 0.dp) {
                        val cur = tabOf(route)
                        TABS.forEach { t ->
                            NavigationBarItem(
                                selected = cur == t.route, onClick = { nav.tab(t.route) },
                                icon = { Icon(t.icon, t.label) }, label = { Text(t.label, fontSize = 11.sp) },
                                colors = NavigationBarItemDefaults.colors(selectedIconColor = C.bg, indicatorColor = C.accent, selectedTextColor = C.accent, unselectedIconColor = C.muted, unselectedTextColor = C.muted)
                            )
                        }
                    }
                }
            }
        ) { pad ->
            AnimatedContent(
                targetState = route,
                transitionSpec = {
                    val dir = if (nav.forward) 1 else -1
                    (slideInHorizontally(tween(320)) { it / 5 * dir } + fadeIn(tween(320))) togetherWith
                        (slideOutHorizontally(tween(260)) { -it / 6 * dir } + fadeOut(tween(200)))
                },
                modifier = Modifier.fillMaxSize().padding(bottom = pad.calculateBottomPadding()),
                label = "nav"
            ) { r ->
                val parts = r.split("/")
                when (parts[0]) {
                    "home" -> HomeScreen(store, content, nav)
                    "learn" -> LearnScreen(store, nav)
                    "article" -> ArticleScreen(store, content, nav, parts[1])
                    "map" -> MapScreen(store, content, nav)
                    "calc" -> CalcScreen(store, content, nav)
                    "glossary" -> GlossaryScreen(content, nav)
                    "play" -> PlayScreen(store, content, nav)
                    "quiz" -> QuizScreen(store, content, nav, parts[1].toInt())
                    "flash" -> FlashScreen(store, content, nav)
                    "library" -> LibraryScreen(store, nav)
                    "reader" -> ReaderScreen(store, nav, parts[1], parts.getOrNull(2)?.substringBefore('?')?.toIntOrNull() ?: store.pos(parts[1]),
                        r.substringAfter("?q=", "").ifEmpty { null })
                    "search" -> SearchScreen(store, content, nav)
                    else -> HomeScreen(store, content, nav)
                }
            }
        }
        ConfettiLayer(store.confetti.value)
        ToastHost(store)
    }
}

@Composable
fun BoxScope.ToastHost(store: Store) {
    val msg = store.toast.value
    var shown by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(msg) {
        if (msg != null) { shown = msg; delay(2800); store.toast.value = null }
    }
    AnimatedVisibility(
        msg != null, enter = slideInVertically { it * 2 } + fadeIn(), exit = slideOutVertically { it * 2 } + fadeOut(),
        modifier = Modifier.align(Alignment.BottomCenter).navigationBarsPadding().padding(bottom = 92.dp, start = 20.dp, end = 20.dp)
    ) {
        Text(shown ?: "", color = C.bg, fontWeight = FontWeight.SemiBold, fontSize = 15.sp,
            modifier = Modifier.clip(RoundedCornerShape(16.dp)).background(C.accent2).padding(horizontal = 18.dp, vertical = 12.dp))
    }
}

