package com.natesapps.ackoff

import androidx.compose.animation.*
import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import kotlin.math.abs

val MACHINE = Color(0xFFE8956B)

/** Swipe each statement left (Machine Age) or right (Systems Age). */
@Composable
fun SortScreen(store: Store, content: Content, nav: Nav) {
    var round by remember { mutableIntStateOf(0) }
    val deck = remember(round) { content.sort.shuffled() }
    var at by remember(round) { mutableIntStateOf(0) }
    var score by remember(round) { mutableIntStateOf(0) }
    var streak by remember(round) { mutableIntStateOf(0) }
    var flash by remember { mutableStateOf<Boolean?>(null) }
    val dx = remember { Animatable(0f) }
    val scope = rememberCoroutineScope()
    val haptic = LocalHapticFeedback.current
    var widthPx by remember { mutableFloatStateOf(1000f) }
    val done = at >= deck.size

    fun answer(systems: Boolean) {
        if (done) return
        val card = deck[at]
        val right = card.systems == systems
        if (right) { score++; streak++; haptic.performHapticFeedback(HapticFeedbackType.TextHandleMove) } else { streak = 0; haptic.performHapticFeedback(HapticFeedbackType.LongPress) }
        if (streak == 5) store.toast.value = "🔥 5 in a row: thinking in wholes!"
        flash = right
        scope.launch {
            dx.animateTo(if (systems) widthPx * 1.3f else -widthPx * 1.3f, tween(220))
            at++
            dx.snapTo(0f)
            if (at >= deck.size) {
                store.setSortBest(score)
                if (score >= deck.size * 0.8) { store.earn("sort") } else store.confetti.value += 0
                if (score == deck.size) store.confetti.value += 1
            }
            kotlinx.coroutines.delay(350); flash = null
        }
    }

    val bgFlash by animateColorAsState(when (flash) { true -> C.thm.copy(alpha = .18f); false -> C.open.copy(alpha = .18f); null -> C.bg }, tween(200), label = "f")
    Column(Modifier.fillMaxSize().background(bgFlash).statusBarsPadding().onSizeChanged { widthPx = it.width.toFloat() }) {
        Row(Modifier.fillMaxWidth().padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = { nav.back() }) { Icon(Icons.Rounded.Close, "Close", tint = C.ink) }
            LinearProgressIndicator(progress = { (at.toFloat() / deck.size).coerceIn(0f, 1f) }, modifier = Modifier.weight(1f).height(10.dp).clip(CircleShape), color = C.accent, trackColor = C.line, drawStopIndicator = {})
            Text(if (streak >= 2) "  🔥$streak" else "  ⭐$score", color = C.accent2, fontWeight = FontWeight.Bold, fontSize = 17.sp, modifier = Modifier.padding(end = 10.dp))
        }
        if (done) {
            val pct = score / deck.size.toFloat()
            val pop = remember { Animatable(0f) }
            LaunchedEffect(Unit) { pop.animateTo(1f, spring(dampingRatio = .4f, stiffness = 200f)) }
            Column(Modifier.fillMaxSize().padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
                Text(if (pct == 1f) "🏆" else if (pct >= .8f) "◉" else "⚙︎", fontSize = 96.sp, color = C.accent2, modifier = Modifier.graphicsLayer { scaleX = pop.value; scaleY = pop.value })
                Text("$score / ${deck.size}", fontSize = 48.sp, fontWeight = FontWeight.Black, color = C.ink)
                Text(when {
                    pct == 1f -> "Perfect. You think in wholes."
                    pct >= .8f -> "Systems thinker! A new part of your system connects."
                    else -> "Still a bit mechanistic. Score 80% to connect this part. Reread the talk's takeaways table."
                }, textAlign = TextAlign.Center, color = C.muted, fontSize = 17.sp, modifier = Modifier.padding(vertical = 12.dp))
                Button(onClick = { round++ }, Modifier.fillMaxWidth().height(52.dp), shape = RoundedCornerShape(14.dp)) { Text("Play again", fontWeight = FontWeight.Bold) }
                Spacer(Modifier.height(10.dp))
                OutlinedButton(onClick = { nav.go("article/talk") }, Modifier.fillMaxWidth().height(52.dp), shape = RoundedCornerShape(14.dp)) { Text("Review the talk") }
            }
            return@Column
        }
        Text("Which age does this idea belong to?", color = C.muted, fontSize = 15.sp, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth().padding(top = 8.dp))
        Row(Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 10.dp)) {
            Text("← MACHINE AGE", color = MACHINE, fontWeight = FontWeight.Bold, fontSize = 13.sp, modifier = Modifier.weight(1f))
            Text("SYSTEMS AGE →", color = C.accent, fontWeight = FontWeight.Bold, fontSize = 13.sp)
        }
        Box(Modifier.weight(1f).fillMaxWidth().padding(horizontal = 24.dp), contentAlignment = Alignment.Center) {
            // next card peeking behind
            if (at + 1 < deck.size) Box(Modifier.fillMaxWidth(.92f).fillMaxHeight(.62f).graphicsLayer { translationY = 30f; alpha = .5f }
                .clip(RoundedCornerShape(26.dp)).background(C.panel))
            val tilt = dx.value / widthPx
            val lean = when { tilt > .08f -> C.accent; tilt < -.08f -> MACHINE; else -> C.line }
            Box(
                Modifier.fillMaxWidth().fillMaxHeight(.66f)
                    .graphicsLayer { translationX = dx.value; rotationZ = tilt * 18f }
                    .clip(RoundedCornerShape(26.dp))
                    .background(Brush.linearGradient(listOf(C.panel2, C.panel)))
                    .border(2.dp, lean, RoundedCornerShape(26.dp))
                    .pointerInput(at, round) {
                        detectDragGestures(
                            onDragEnd = {
                                when {
                                    dx.value > size.width * .28f -> answer(true)
                                    dx.value < -size.width * .28f -> answer(false)
                                    else -> scope.launch { dx.animateTo(0f, spring(dampingRatio = .5f)) }
                                }
                            },
                            onDrag = { change, drag -> change.consume(); scope.launch { dx.snapTo(dx.value + drag.x) } }
                        )
                    }
                    .padding(28.dp),
                contentAlignment = Alignment.Center
            ) {
                AnimatedContent(deck[at].text, transitionSpec = { (fadeIn() + scaleIn(initialScale = .9f)) togetherWith fadeOut() }, label = "card") {
                    Text("“$it”", fontFamily = Serif, fontSize = 25.sp, lineHeight = 34.sp, color = C.ink, textAlign = TextAlign.Center)
                }
                if (abs(tilt) > .08f) Text(if (tilt > 0) "SYSTEMS" else "MACHINE", color = lean, fontWeight = FontWeight.Black, fontSize = 14.sp, letterSpacing = 2.sp,
                    modifier = Modifier.align(if (tilt > 0) Alignment.TopStart else Alignment.TopEnd))
            }
        }
        Text("${at + 1} of ${deck.size} · swipe or tap", color = C.muted, fontSize = 13.sp, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth())
        Row(Modifier.fillMaxWidth().navigationBarsPadding().padding(20.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            OutlinedButton(onClick = { answer(false) }, Modifier.weight(1f).height(58.dp), shape = RoundedCornerShape(16.dp),
                colors = ButtonDefaults.outlinedButtonColors(contentColor = MACHINE)) { Text("⚙︎  Machine", fontSize = 16.sp, fontWeight = FontWeight.Bold) }
            Button(onClick = { answer(true) }, Modifier.weight(1f).height(58.dp), shape = RoundedCornerShape(16.dp)) { Text("Systems  ◉", fontSize = 16.sp, fontWeight = FontWeight.Bold) }
        }
    }
}

