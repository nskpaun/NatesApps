package com.natesapps.fastchat.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

val Cream = Color(0xFFFFF3DF)
val Linen = Color(0xFFF7E8D2)
val Line = Color(0xFFD9C4AB)
val Terracotta = Color(0xFFA94F30)
val Cocoa = Color(0xFF432C22)
val Muted = Color(0xFF785E50)
val Alert = Color(0xFF9A3A26)

private val colors = lightColorScheme(
    primary = Terracotta,
    onPrimary = Cream,
    secondary = Terracotta,
    background = Cream,
    onBackground = Cocoa,
    surface = Cream,
    onSurface = Cocoa,
    surfaceVariant = Linen,
    onSurfaceVariant = Muted,
    outline = Line,
    error = Alert,
)

// Warm paper and cocoa, with large quiet type that can be read at arm's length.
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
