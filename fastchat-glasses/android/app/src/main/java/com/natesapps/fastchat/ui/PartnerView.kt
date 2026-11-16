package com.natesapps.fastchat.ui

import android.animation.ValueAnimator
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.keyframes
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.natesapps.fastchat.core.PartnerTurn

/** The active phone is a turn-taking sign. Private reply choices stay on the glasses. */
@Composable
internal fun PartnerView(turn: PartnerTurn, name: String, modifier: Modifier = Modifier) {
    val title = when (turn) {
        PartnerTurn.YOUR_TURN -> "Your turn"
        PartnerTurn.WEARERS_TURN -> name.trim().takeIf { it.isNotEmpty() }?.let { "${it}’s turn" } ?: "Please wait"
        PartnerTurn.RECONNECTING -> "One moment"
        PartnerTurn.PAUSED -> "Paused"
    }
    BoxWithConstraints(modifier.fillMaxSize()) {
        val compact = maxHeight < 340.dp
        Column(
            modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            if (turn == PartnerTurn.YOUR_TURN || turn == PartnerTurn.WEARERS_TURN) {
                LookUpArrow(Modifier.size(if (compact) 72.dp else 116.dp))
                Spacer(Modifier.height(if (compact) 20.dp else 36.dp))
            }
            Text(
                title,
                modifier = Modifier.fillMaxWidth().semantics { liveRegion = LiveRegionMode.Polite },
                style = MaterialTheme.typography.displaySmall.copy(
                    fontSize = if (compact) 34.sp else 44.sp,
                    lineHeight = if (compact) 40.sp else 52.sp,
                    fontWeight = FontWeight.Medium,
                ),
                color = Cocoa,
                textAlign = TextAlign.Center,
            )
            if (turn == PartnerTurn.RECONNECTING) {
                Spacer(Modifier.height(12.dp))
                Text("Reconnecting", style = MaterialTheme.typography.bodyLarge, color = Muted)
            }
        }
    }
}

/** A small upward invitation, followed by a long rest so attention can return to the wearer. */
@Composable
private fun LookUpArrow(modifier: Modifier = Modifier) {
    val motion = remember { ValueAnimator.areAnimatorsEnabled() }
    val offset = if (motion) {
        val transition = rememberInfiniteTransition(label = "Look toward the wearer")
        val value by transition.animateFloat(
            initialValue = 0f,
            targetValue = 0f,
            animationSpec = infiniteRepeatable(keyframes {
                durationMillis = 2_400
                0f at 0
                0f at 700 using FastOutSlowInEasing
                -8f at 1_050 using FastOutSlowInEasing
                0f at 1_450
                0f at 2_400
            }),
            label = "Gentle upward cue",
        )
        value
    } else 0f
    Canvas(modifier.clearAndSetSemantics { }.graphicsLayer { translationY = offset.dp.toPx() }) {
        val path = Path().apply {
            moveTo(size.width * 0.42f, size.height * 0.88f)
            cubicTo(size.width * 0.32f, size.height * 0.66f, size.width * 0.48f, size.height * 0.44f, size.width * 0.5f, size.height * 0.16f)
            moveTo(size.width * 0.26f, size.height * 0.4f)
            lineTo(size.width * 0.5f, size.height * 0.16f)
            lineTo(size.width * 0.74f, size.height * 0.4f)
        }
        drawPath(path, Terracotta, style = Stroke(width = size.width * 0.065f, cap = StrokeCap.Round, join = StrokeJoin.Round))
    }
}
