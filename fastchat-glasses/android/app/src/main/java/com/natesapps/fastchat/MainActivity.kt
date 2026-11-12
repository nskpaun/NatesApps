package com.natesapps.fastchat

import android.Manifest
import android.content.Intent
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts.RequestMultiplePermissions
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.meta.wearable.dat.core.Wearables
import com.natesapps.fastchat.core.Dpad
import com.natesapps.fastchat.core.GlassesInput
import com.natesapps.fastchat.core.Phase
import com.natesapps.fastchat.ui.FastChatScreen
import com.natesapps.fastchat.ui.FastChatTheme
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {

    private val fastChat: FastChat get() = (application as FastChatApp).fastChat

    /** What to do once the user has answered the permission prompt. */
    private var afterPermissions: (() -> Unit)? = null

    private val permissions = registerForActivityResult(RequestMultiplePermissions()) {
        if (granted(Manifest.permission.BLUETOOTH_CONNECT)) startGlasses()
        afterPermissions?.invoke()
        afterPermissions = null
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            FastChatTheme {
                FastChatScreen(
                    fastChat = fastChat,
                    onStart = ::startConversation,
                    onConnectGlasses = ::connectGlasses,
                    onDisconnectGlasses = { fastChat.glasses.unregister(this) },
                )
            }
        }

        // The partner is holding the phone: keep the screen on for as long as a conversation runs.
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                fastChat.conversation.map { it.phase != Phase.Off }.distinctUntilChanged().collect { running ->
                    if (running) window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                    else window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                }
            }
        }

        if (granted(Manifest.permission.BLUETOOTH_CONNECT)) startGlasses()
        handleDebugExtras(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleRegistration(intent)
        handleDebugExtras(intent)
    }

    /**
     * Debug builds only: drive the app from a computer, e.g.
     * `adb shell am start -n com.natesapps.fastchat/.MainActivity --es heard "Want some lunch?"`
     * `--es gesture up|right|down|left|cw|ccw|tap|back`, `--ez reset true` to forget the conversation,
     * `--es name ...` / `--es about ...` to set the wearer's details, and `--ez simulated true|false`.
     * See the README.
     */
    private fun handleDebugExtras(intent: Intent?) {
        if (intent == null || applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE == 0) return
        if (intent.getBooleanExtra("start", false)) startConversation()
        if (intent.getBooleanExtra("stop", false)) fastChat.stop()
        if (intent.getBooleanExtra("reset", false)) fastChat.debugReset()
        if (intent.hasExtra("simulated")) {
            val on = intent.getBooleanExtra("simulated", false)
            fastChat.settings.update { it.copy(simulatedGlasses = on) }
        }
        intent.getStringExtra("name")?.let { name -> fastChat.settings.update { it.copy(name = name) } }
        intent.getStringExtra("about")?.let { about -> fastChat.settings.update { it.copy(about = about) } }
        intent.getStringExtra("heard")?.let(fastChat::debugHeard)
        val gesture = when (intent.getStringExtra("gesture")) {
            "up" -> GlassesInput.Highlight(Dpad.UP)
            "right" -> GlassesInput.Highlight(Dpad.RIGHT)
            "down" -> GlassesInput.Highlight(Dpad.DOWN)
            "left" -> GlassesInput.Highlight(Dpad.LEFT)
            "cw" -> GlassesInput.Turn(clockwise = true)
            "ccw" -> GlassesInput.Turn(clockwise = false)
            "tap" -> GlassesInput.Confirm
            "back" -> GlassesInput.Back
            else -> null
        }
        gesture?.let(fastChat::debugGesture)
    }

    private fun startGlasses() {
        fastChat.glasses.start()
        handleRegistration(intent)
    }

    /** Lets the Meta AI app start connecting FastChat from its side. */
    private fun handleRegistration(intent: Intent?) {
        if (intent?.data == null || !fastChat.glasses.isStarted) return
        Wearables.handleIntent(intent) { request -> request.continueRegistration(this) }
    }

    private fun startConversation() = withPermissions(Manifest.permission.RECORD_AUDIO) {
        if (granted(Manifest.permission.RECORD_AUDIO)) fastChat.start()
    }

    private fun connectGlasses() = withPermissions(Manifest.permission.BLUETOOTH_CONNECT) {
        if (granted(Manifest.permission.BLUETOOTH_CONNECT)) fastChat.glasses.register(this)
    }

    private fun withPermissions(vararg needed: String, then: () -> Unit) {
        val missing = needed.filterNot(::granted)
        if (missing.isEmpty()) {
            then()
        } else {
            afterPermissions = then
            permissions.launch(missing.toTypedArray())
        }
    }

    private fun granted(permission: String): Boolean =
        ContextCompat.checkSelfPermission(this, permission) == PackageManager.PERMISSION_GRANTED
}
