package com.natesapps.chaintheory

import androidx.compose.animation.*
import androidx.compose.animation.core.*
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch

@Composable
fun PlayScreen(store: Store, content: Content, nav: Nav) {
    Column(Modifier.fillMaxSize()) {
        TopBar("Play", nav, subtitle = "Clear a deck with 70%+ to forge a link")
        LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            itemsIndexed(content.decks) { i, d ->
                Appear(i) {
                    val done = store.earned.containsKey("q$i")
                    PressCard({ nav.go("quiz/$i") }, border = if (done) C.thm.copy(alpha = .6f) else C.line) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Box(Modifier.size(52.dp).clip(CircleShape).background(Brush.linearGradient(listOf(C.accent, Color(0xFF9A4B16)))), contentAlignment = Alignment.Center) {
                                Text(listOf("⚡", "🔭", "∑", "🧠")[i % 4], fontSize = 24.sp, color = Color.White)
                            }
                            Spacer(Modifier.width(14.dp))
                            Column(Modifier.weight(1f)) {
                                Text("${d.level.uppercase()} · ${d.questions.size} QUESTIONS", color = C.accent, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
                                Text(d.name, fontWeight = FontWeight.Bold, fontSize = 19.sp, color = C.ink)
                                Text(d.desc, color = C.muted, fontSize = 14.sp)
                                store.best[i]?.let { Text("Best: $it/${d.questions.size}", color = C.accent2, fontSize = 13.sp, fontWeight = FontWeight.SemiBold) }
                            }
                            if (done) Text("⛓", fontSize = 22.sp)
                        }
                    }
                }
            }
            item {
                Appear(4) {
                    PressCard({ nav.go("flash") }) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Box(Modifier.size(52.dp).clip(CircleShape).background(Brush.linearGradient(listOf(C.violet, Color(0xFF5A3FA0)))), contentAlignment = Alignment.Center) {
                                Text("🃏", fontSize = 24.sp)
                            }
                            Spacer(Modifier.width(14.dp))
                            Column(Modifier.weight(1f)) {
                                Text("FLASHCARDS · ${content.glossary.size} CARDS", color = C.violet, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
                                Text("Glossary flip cards", fontWeight = FontWeight.Bold, fontSize = 19.sp, color = C.ink)
                                Text("Tap to flip. Cards you miss come back sooner. Known so far: ${store.flashKnown.value}", color = C.muted, fontSize = 14.sp)
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun QuizScreen(store: Store, content: Content, nav: Nav, deckIndex: Int) {
    val deck = content.decks[deckIndex]
    var round by remember { mutableIntStateOf(0) }
    val order = remember(round) { deck.questions.indices.shuffled() }
    var at by remember(round) { mutableIntStateOf(0) }
    var score by remember(round) { mutableIntStateOf(0) }
    var streak by remember(round) { mutableIntStateOf(0) }
    var picked by remember(round) { mutableStateOf<Int?>(null) }
    var finished by remember(round) { mutableStateOf(false) }
    val haptic = LocalHapticFeedback.current
    val prog by animateFloatAsState((at + if (picked != null) 1 else 0) / deck.questions.size.toFloat(), tween(400), label = "qp")

    Column(Modifier.fillMaxSize().statusBarsPadding()) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = { nav.back() }) { Icon(Icons.Rounded.Close, "Quit", tint = C.ink) }
            LinearProgressIndicator(progress = { prog }, modifier = Modifier.weight(1f).height(10.dp).clip(CircleShape), color = C.accent, trackColor = C.line, drawStopIndicator = {})
            Spacer(Modifier.width(12.dp))
            AnimatedContent(streak, label = "streak", transitionSpec = { (scaleIn(initialScale = 1.8f) + fadeIn()) togetherWith fadeOut() }) {
                Text(if (it >= 2) "🔥$it" else "⭐$score", fontWeight = FontWeight.Bold, color = C.accent2, fontSize = 17.sp, modifier = Modifier.padding(end = 10.dp))
            }
        }
        if (finished) {
            Results(deck, score, onAgain = { round++ }, onBack = { nav.back() })
        } else {
            AnimatedContent(at, transitionSpec = {
                (slideInHorizontally(tween(350)) { it } + fadeIn()) togetherWith (slideOutHorizontally(tween(300)) { -it } + fadeOut())
            }, label = "q", modifier = Modifier.weight(1f)) { idx ->
                val q = deck.questions[order[idx]]
                val opts = remember(idx, round) { q.options.indices.shuffled() }
                LazyColumn(contentPadding = PaddingValues(20.dp)) {
                    item {
                        Text("${deck.name.uppercase()} · ${idx + 1} OF ${deck.questions.size}", color = C.accent, fontWeight = FontWeight.Bold, fontSize = 12.sp, letterSpacing = 1.5.sp)
                        Text(q.q, fontSize = 23.sp, fontWeight = FontWeight.Bold, lineHeight = 30.sp, color = C.ink, modifier = Modifier.padding(top = 8.dp, bottom = 18.dp))
                    }
                    itemsIndexed(opts) { j, k ->
                        Appear(j) {
                            OptionButton(q.options[k], state = when {
                                picked == null -> 0; k == q.answer -> 1; k == picked -> 2; else -> 3
                            }) {
                                if (picked == null) {
                                    picked = k
                                    if (k == q.answer) {
                                        score++; streak++
                                        haptic.performHapticFeedback(HapticFeedbackType.TextHandleMove)
                                        if (streak == 3) store.toast.value = "🔥 3 in a row!"
                                        if (streak == 5) store.toast.value = "🔥🔥 5 streak. Entangled with the truth."
                                    } else { streak = 0; haptic.performHapticFeedback(HapticFeedbackType.LongPress) }
                                }
                            }
                        }
                    }
                    item {
                        AnimatedVisibility(picked != null, enter = expandVertically() + fadeIn()) {
                            val right = picked == q.answer
                            Column(Modifier.padding(top = 16.dp).fillMaxWidth().clip(RoundedCornerShape(16.dp))
                                .background((if (right) C.thm else C.open).copy(alpha = .12f)).border(1.dp, (if (right) C.thm else C.open).copy(alpha = .5f), RoundedCornerShape(16.dp)).padding(16.dp)) {
                                Text(if (right) "Correct!" else "Not quite.", fontWeight = FontWeight.Bold, color = if (right) C.thm else C.open, fontSize = 17.sp)
                                Text(q.explain, fontFamily = Serif, fontSize = 16.sp, lineHeight = 23.sp, color = C.ink, modifier = Modifier.padding(top = 4.dp))
                                Spacer(Modifier.height(12.dp))
                                Button(onClick = {
                                    picked = null
                                    if (at + 1 < deck.questions.size) at++ else {
                                        finished = true
                                        store.setBest(deckIndex, score)
                                        if (score >= deck.questions.size * 0.7) { store.confetti.value += 1; store.earn("q$deckIndex") }
                                    }
                                }, modifier = Modifier.fillMaxWidth().height(50.dp), shape = RoundedCornerShape(14.dp)) {
                                    Text(if (at + 1 < deck.questions.size) "Next" else "See results", fontWeight = FontWeight.Bold, fontSize = 16.sp)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun OptionButton(text: String, state: Int, onClick: () -> Unit) {
    // state: 0 idle, 1 correct, 2 wrong pick, 3 other after answer
    val shake = remember { Animatable(0f) }
    LaunchedEffect(state) {
        if (state == 2) for (x in listOf(-14f, 12f, -9f, 6f, -3f, 0f)) shake.animateTo(x, tween(45))
    }
    val bounce by animateFloatAsState(if (state == 1) 1.03f else 1f, spring(dampingRatio = .35f, stiffness = 400f), label = "b")
    val border by animateColorAsState(when (state) { 1 -> C.thm; 2 -> C.open; else -> C.line }, label = "bc")
    val bg by animateColorAsState(when (state) { 1 -> C.thm.copy(alpha = .16f); 2 -> C.open.copy(alpha = .14f); else -> C.panel }, label = "bg")
    val alpha by animateFloatAsState(if (state == 3) .45f else 1f, label = "a")
    Row(
        Modifier.padding(vertical = 5.dp).fillMaxWidth().graphicsLayer { translationX = shake.value * density; scaleX = bounce; scaleY = bounce; this.alpha = alpha }
            .clip(RoundedCornerShape(16.dp)).background(bg).border(2.dp, border, RoundedCornerShape(16.dp)).clickable(onClick = onClick).padding(16.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(text, fontSize = 17.sp, color = C.ink, lineHeight = 23.sp, modifier = Modifier.weight(1f))
        if (state == 1) Icon(Icons.Rounded.CheckCircle, null, tint = C.thm)
        if (state == 2) Icon(Icons.Rounded.Cancel, null, tint = C.open)
    }
}

@Composable
fun Results(deck: Deck, score: Int, onAgain: () -> Unit, onBack: () -> Unit) {
    val n = deck.questions.size; val pct = score / n.toFloat()
    val pop = remember { Animatable(0f) }
    LaunchedEffect(Unit) { pop.animateTo(1f, spring(dampingRatio = .4f, stiffness = 200f)) }
    var shown by remember { mutableIntStateOf(0) }
    LaunchedEffect(Unit) { for (i in 0..score) { shown = i; kotlinx.coroutines.delay(90) } }
    Column(Modifier.fillMaxSize().padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
        Text(when { pct == 1f -> "🏆"; pct >= .7f -> "⛓"; pct >= .4f -> "🤔"; else -> "🌀" }, fontSize = 96.sp,
            modifier = Modifier.graphicsLayer { scaleX = pop.value; scaleY = pop.value; rotationZ = (1 - pop.value) * -40 })
        Text("$shown / $n", fontSize = 48.sp, fontWeight = FontWeight.Black, color = C.ink)
        Text(when { pct == 1f -> "Flawless. Maximally entangled with the material."; pct >= .7f -> "Deck cleared! A new link is forged."; else -> "You need 70% to forge this link. Review the level and try again." },
            textAlign = TextAlign.Center, color = C.muted, fontSize = 17.sp, modifier = Modifier.padding(vertical = 12.dp))
        Button(onClick = onAgain, modifier = Modifier.fillMaxWidth().height(52.dp), shape = RoundedCornerShape(14.dp)) { Text("Play again", fontWeight = FontWeight.Bold) }
        Spacer(Modifier.height(10.dp))
        OutlinedButton(onClick = onBack, modifier = Modifier.fillMaxWidth().height(52.dp), shape = RoundedCornerShape(14.dp)) { Text("All decks") }
    }
}

@Composable
fun FlashScreen(store: Store, content: Content, nav: Nav) {
    val queue = remember { mutableStateListOf<Term>().apply { addAll(content.glossary.shuffled()) } }
    var flipped by remember { mutableStateOf(false) }
    var cardKey by remember { mutableIntStateOf(0) }
    val rot by animateFloatAsState(if (flipped) 180f else 0f, tween(450, easing = FastOutSlowInEasing), label = "flip")
    val scope = rememberCoroutineScope()
    val swipe = remember { Animatable(0f) }
    fun advance(known: Boolean) {
        scope.launch {
            swipe.animateTo(if (known) 1f else -1f, tween(220))
            val c = queue.removeAt(0)
            if (known) { queue.add(c); store.knowCard() } else queue.add(minOf(3, queue.size), c)
            flipped = false; cardKey++
            swipe.snapTo(0f)
        }
    }
    Column(Modifier.fillMaxSize().statusBarsPadding()) {
        Row(Modifier.fillMaxWidth().padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = { nav.back() }) { Icon(Icons.Rounded.Close, "Close", tint = C.ink) }
            Text("Flashcards", fontWeight = FontWeight.Bold, fontSize = 18.sp, color = C.ink, modifier = Modifier.weight(1f))
            Text("😎 ${store.flashKnown.value}", color = C.accent2, fontWeight = FontWeight.Bold, modifier = Modifier.padding(end = 12.dp))
        }
        val card = queue.first()
        Box(Modifier.weight(1f).fillMaxWidth().padding(24.dp), contentAlignment = Alignment.Center) {
            Box(
                Modifier.fillMaxWidth().fillMaxHeight(.82f)
                    .graphicsLayer {
                        rotationY = rot; cameraDistance = 14 * density
                        translationX = swipe.value * size.width * 1.2f; rotationZ = swipe.value * 14f
                    }
                    .clip(RoundedCornerShape(26.dp))
                    .background(if (rot <= 90f) Brush.linearGradient(listOf(Color(0xFF3A2312), C.panel)) else Brush.linearGradient(listOf(C.panel2, C.panel)))
                    .border(1.5.dp, if (rot <= 90f) C.accent.copy(alpha = .6f) else C.violet.copy(alpha = .6f), RoundedCornerShape(26.dp))
                    .clickable { flipped = !flipped }.padding(26.dp),
                contentAlignment = Alignment.Center
            ) {
                if (rot <= 90f) Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(card.term, fontSize = 30.sp, fontWeight = FontWeight.Black, color = C.accent2, textAlign = TextAlign.Center, lineHeight = 36.sp)
                    Spacer(Modifier.height(18.dp)); Text("tap to flip", color = C.muted, fontSize = 13.sp)
                } else Box(Modifier.graphicsLayer { rotationY = 180f }.verticalScroll(rememberScrollState())) {
                    Text(card.def, fontFamily = Serif, fontSize = 19.sp, lineHeight = 28.sp, color = C.ink, textAlign = TextAlign.Center)
                }
            }
        }
        Row(Modifier.fillMaxWidth().navigationBarsPadding().padding(20.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            OutlinedButton(onClick = { advance(false) }, Modifier.weight(1f).height(56.dp), shape = RoundedCornerShape(16.dp)) { Text("😕 Again", fontSize = 16.sp) }
            Button(onClick = { advance(true) }, Modifier.weight(1f).height(56.dp), shape = RoundedCornerShape(16.dp)) { Text("😎 Knew it", fontSize = 16.sp, fontWeight = FontWeight.Bold) }
        }
    }
}
