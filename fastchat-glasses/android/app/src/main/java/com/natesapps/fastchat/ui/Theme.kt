package com.natesapps.fastchat.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

val Ink = Color(0xFF0E1116)
val Panel = Color(0xFF181D25)
val Line = Color(0xFF2A313C)
val Signal = Color(0xFF5BE49B)
val Paper = Color(0xFFF2F4F7)
val Muted = Color(0xFF9AA4B2)
val Alert = Color(0xFFFFB454)

private val colors = darkColorScheme(
    primary = Signal,
    onPrimary = Ink,
    secondary = Signal,
    background = Ink,
    onBackground = Paper,
    surface = Panel,
    onSurface = Paper,
    surfaceVariant = Panel,
    onSurfaceVariant = Muted,
    outline = Line,
    error = Alert,
)

// One dark, high-contrast look: the phone is read at arm's length by someone who has never seen
// the app, so the type is large and there is very little of it.
private val type = Typography().run {
    copy(
        displaySmall = TextStyle(fontSize = 40.sp, lineHeight = 46.sp, fontWeight = FontWeight.SemiBold),
        headlineMedium = TextStyle(fontSize = 28.sp, lineHeight = 34.sp, fontWeight = FontWeight.SemiBold),
        titleLarge = TextStyle(fontSize = 22.sp, lineHeight = 28.sp, fontWeight = FontWeight.SemiBold),
        bodyLarge = TextStyle(fontSize = 18.sp, lineHeight = 26.sp),
        bodyMedium = TextStyle(fontSize = 15.sp, lineHeight = 22.sp),
        labelLarge = TextStyle(fontSize = 16.sp, lineHeight = 20.sp, fontWeight = FontWeight.SemiBold),
    )
}

@Composable
fun FastChatTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = colors, typography = type, content = content)
}
