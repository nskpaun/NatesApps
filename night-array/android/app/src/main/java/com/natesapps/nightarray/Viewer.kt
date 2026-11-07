package com.natesapps.nightarray

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Color
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.ViewGroup
import android.webkit.JavascriptInterface
import android.webkit.RenderProcessGoneDetail
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.widget.FrameLayout
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import androidx.webkit.WebResourceErrorCompat
import androidx.webkit.WebViewAssetLoader
import androidx.webkit.WebViewClientCompat
import androidx.webkit.WebViewCompat
import org.json.JSONObject
import java.net.URLEncoder

/** Kotlin side of the ViewerState in SPEC.md §4. Compose-observable; every change is mirrored to JS. */
class ViewerState {
    var mode by mutableStateOf("work")
    var style by mutableStateOf("studio")
    var finish by mutableStateOf("titanium")
    /** 0.8 = the viewer's DEFAULT_STATE (state.js) and the stills' BASE_STATE (render_stills.mjs), so still → live doesn't shift. */
    var amber by mutableFloatStateOf(0.8f)
    var explode by mutableFloatStateOf(0f)
    var sectionOn by mutableStateOf(false)
    var sectionAxis by mutableStateOf("x")
    var sectionT by mutableFloatStateOf(0.5f)
    var dims by mutableStateOf(false)
    var autorotate by mutableStateOf(false)
    var isolate by mutableStateOf<String?>(null)
    var selected by mutableStateOf<String?>(null)
    var quality by mutableStateOf("high")
    var cinematic by mutableStateOf(false)

    fun section(): Any = if (sectionOn) JSONObject().put("axis", sectionAxis).put("t", sectionT.toDouble()) else JSONObject.NULL

    fun toJson(): JSONObject = JSONObject()
        .put("mode", mode).put("style", style).put("finish", finish).put("amber", amber.toDouble())
        .put("explode", explode.toDouble()).put("section", section()).put("dims", dims).put("autorotate", autorotate)
        .put("isolate", isolate ?: JSONObject.NULL).put("selected", selected ?: JSONObject.NULL)
        .put("quality", quality).put("cinematic", cinematic)
}

/** A one-shot "See it live" setup applied before opening the Studio. */
data class Preset(
    val mode: String? = null, val style: String? = null, val finish: String? = null, val amber: Float? = null,
    val explode: Float? = null, val section: String? = null, val dims: Boolean? = null, val camera: String? = null,
    val dock: String? = null, val isolate: String? = null, val clearIsolate: Boolean = true,
)

enum class LiveStatus { Idle, Loading, Ready, Error }

/**
 * Owns the single WebView that runs the three.js viewer. It is created once (lazily, on first use),
 * lives above navigation and is re-parented between whichever [ViewerSlot]s are on screen. Kotlin→JS
 * calls are queued until the page has loaded; JS→Kotlin events arrive through [Bridge] and are handled
 * on the main thread.
 */
class ViewerHost(private val appContext: Context) {
    val state = ViewerState()
    var status by mutableStateOf(LiveStatus.Idle); private set
    var errorMessage by mutableStateOf<String?>(null); private set
    /** Group the user tapped in the 3D view (drives the part sheet). */
    var picked by mutableStateOf<String?>(null)
    /** Last dockStep event (align/lower/release/lift), null when idle or done. */
    var dockStep by mutableStateOf<String?>(null); private set
    var dockPlaying by mutableStateOf(false); private set
    var lastCamera by mutableStateOf("hero"); private set
    /** Bumped on every event; handy for UI that reacts to "something happened". */
    var events by mutableIntStateOf(0); private set
    /** Bumped each time a page load starts (first load and every Retry), so UI timers can restart. */
    var loadGeneration by mutableIntStateOf(0); private set

    /** Replaced in tests to capture what would be sent to the page. */
    var evaluator: ((String) -> Unit)? = null

    private val main = Handler(Looper.getMainLooper())
    private var webView: WebView? = null
    private var pageLoaded = false
    private var resumed = true
    private val queue = ArrayList<Any>() // String (raw JS) or JSONObject (partial state, merged)
    private val slots = ArrayList<FrameLayout>()
    private var destroyed = false

    val bridge = Bridge()

    inner class Bridge {
        /** Called by the viewer page: window.NightArrayHost.post(JSON.stringify(evt)). Runs on a WebView thread. */
        @JavascriptInterface
        fun post(json: String?) {
            if (json == null) return
            main.post { handle(json) }
        }
    }

    // ---------- events (JS → Kotlin) ----------
    fun handle(raw: String) {
        if (destroyed) return
        val o = try { JSONObject(raw) } catch (_: Exception) { return }
        events++
        when (o.optString("type")) {
            "ready" -> {
                status = LiveStatus.Ready; errorMessage = null
                autoRecreates = 0 // a renderer that got this far may be rebuilt quietly again after the next reclaim
                // The page is evidently alive; make sure nothing is left waiting even if onPageFinished was missed.
                if (!pageLoaded) onPageLoaded() else flush()
            }
            "pick" -> {
                if (state.cinematic) return
                val g = if (o.isNull("group")) null else o.optString("group", "").ifBlank { null }
                picked = g
                if (state.selected != g) { state.selected = g; push(JSONObject().put("selected", g ?: JSONObject.NULL)) }
            }
            "dockStep" -> {
                // The page is driving the sequence itself: it takes over from any stills fallback.
                main.removeCallbacks(dockWatchdog); cancelLocalDock()
                when (val s = o.optString("step")) {
                    "done" -> { dockStep = null; dockPlaying = false }
                    "align", "lower", "release", "lift" -> dockStep = s
                }
            }
            "error" -> fail(o.optString("message", "").ifBlank { "the live renderer stopped" })
        }
    }

    // ---------- state & commands (Kotlin → JS) ----------
    fun setMode(v: String) { state.mode = v; push("mode", v) }
    fun setStyle(v: String) { state.style = v; push("style", v) }
    fun setFinish(v: String) { state.finish = v; push("finish", v) }
    fun setAmber(v: Float) { state.amber = v.coerceIn(0f, 1f); push("amber", state.amber.toDouble()) }
    fun setExplode(v: Float) { state.explode = v.coerceIn(0f, 1f); push("explode", state.explode.toDouble()) }
    fun setSection(on: Boolean, axis: String = state.sectionAxis, t: Float = state.sectionT) {
        state.sectionOn = on; state.sectionAxis = axis; state.sectionT = t.coerceIn(0f, 1f); push(JSONObject().put("section", state.section()))
    }
    fun setDims(v: Boolean) { state.dims = v; push("dims", v) }
    fun setAutorotate(v: Boolean) { state.autorotate = v; push("autorotate", v) }
    fun setQuality(v: String) { state.quality = v; push("quality", v) }
    fun setCinematic(v: Boolean) { state.cinematic = v; push("cinematic", v); if (v) picked = null }
    fun setIsolate(g: String?) {
        state.isolate = g; push(JSONObject().put("isolate", g ?: JSONObject.NULL))
        // A page created while isolated never got the saved preset (see ensureWebView): bring it back on "Show all".
        if (g == null && cameraOwed) { cameraOwed = false; if (lastCamera != "hero" && !state.cinematic) camera(lastCamera) }
    }
    /** True when the current page was created while a group was isolated, so it still owes the lastCamera preset. */
    private var cameraOwed = false
    fun select(g: String?) { state.selected = g; push(JSONObject().put("selected", g ?: JSONObject.NULL)) }

    fun camera(name: String) { lastCamera = name; call("NA.camera(${JSONObject.quote(name)})") }
    fun frame(group: String) { call("NA.frame(${JSONObject.quote(group)})") }
    fun dock(step: String) {
        cancelLocalDock(); main.removeCallbacks(dockWatchdog)
        when (step) {
            "play" -> { dockPlaying = true; dockStep = null }
            "reset" -> { dockPlaying = false; dockStep = null }
            else -> { dockPlaying = false; dockStep = step }
        }
        if (step == "play" && !liveCanPlay) {
            // No live page will ever report the steps (not bundled, no WebGL2, model failed): play them in the stills.
            dropQueuedDock(); playLocalDock(); return
        }
        call("NA.dock(${JSONObject.quote(step)})")
        if (step == "play") { dockWaits = 0; main.postDelayed(dockWatchdog, DOCK_WATCHDOG_MS) }
    }

    // ---------- the dock sequence without the live page ----------
    /** Pending steps of a sequence played in Kotlin (stills + sketch), when the live page can't play it. */
    private val localDock = ArrayList<Runnable>()

    /** True while a live page exists, or is about to be created, that can play the sequence and report its steps. */
    private val liveCanPlay: Boolean
        get() = !destroyed && status != LiveStatus.Error && (evaluator != null || webView != null || bundled(appContext))

    private fun cancelLocalDock() { localDock.forEach(main::removeCallbacks); localDock.clear() }

    private fun dropQueuedDock() { queue.removeAll { it is String && it.startsWith("NA.dock(") } }

    /** Steps the sequence in Kotlin on the app.js timings (a little slower: these are stills). Resumes from the current step. */
    private fun playLocalDock() {
        cancelLocalDock()
        val start = LOCAL_DOCK.indexOfFirst { it.first == dockStep }.coerceAtLeast(0)
        val t0 = LOCAL_DOCK[start].second
        LOCAL_DOCK.drop(start).forEach { (s, at) ->
            val r = Runnable {
                if (s == "done") { localDock.clear(); dockStep = null; dockPlaying = false } else dockStep = s
            }
            localDock += r
            main.postDelayed(r, at - t0)
        }
    }

    /** Watchdog periods that passed without a dockStep since the last NA.dock("play"). */
    private var dockWaits = 0

    /**
     * A page that took NA.dock("play") but never reported a step: finish the sequence in Kotlin rather than stay "Playing…".
     * While the page is still loading it waits a little longer (the page plays it once the model is up), but not forever:
     * a page that never gets going must not leave the button stuck either. A step reported later takes over again.
     */
    private val dockWatchdog = object : Runnable {
        override fun run() {
            if (!dockPlaying || localDock.isNotEmpty()) return
            dockWaits++
            if (status == LiveStatus.Ready || status == LiveStatus.Error || dockWaits >= DOCK_WATCHDOG_PERIODS) playLocalDock()
            else main.postDelayed(this, DOCK_WATCHDOG_MS)
        }
    }

    /** The live view can't go on: the still takes over, and a dock sequence in progress carries on in the stills. */
    private fun fail(message: String) {
        status = LiveStatus.Error; errorMessage = message
        main.removeCallbacks(dockWatchdog)
        dropQueuedDock() // so a later Retry doesn't replay stale dock commands
        if (dockPlaying && localDock.isEmpty()) playLocalDock()
    }

    fun closeSheet() { picked = null; if (state.selected != null) select(null) }

    /**
     * Same as a pick event from the page, for picks made in Compose (the Parts list). The Parts list offers every group,
     * hidden ones too: while another group is isolated the isolation moves to the picked one (one merged setState), so the
     * camera never frames a hidden group and the "Isolated · …" banner names what's on screen.
     */
    fun pickLocal(group: String) {
        picked = group
        if (state.selected != group) select(group)
        if (state.isolate != null && state.isolate != group) setIsolate(group)
        frame(group)
    }

    fun toggleIsolate(group: String) {
        if (state.isolate == group) setIsolate(null) else { setIsolate(group); frame(group) }
    }

    // ---------- saved state ----------
    /** The viewer state to keep across Activity recreation / process death: never mid-Night shift, nothing selected. */
    fun snapshot(): JSONObject {
        val o = state.toJson().put("cinematic", false).put("selected", JSONObject.NULL)
        beforeNight?.let { b -> b.keys().forEach { k -> o.put(k, b.get(k)) } }
        return o
    }

    /**
     * Restores a [snapshot]. Call it before the first [claim], so the page's initial URL carries the state.
     * Unknown values are ignored; an isolated group the scene doesn't know is dropped.
     */
    fun restore(json: String, camera: String?, knownGroup: (String) -> Boolean) {
        val o = try { JSONObject(json) } catch (_: Exception) { return }
        fun choice(key: String, options: List<Pair<String, String>>, cur: String) = o.optString(key, cur).takeIf { v -> options.any { it.first == v } } ?: cur
        fun unit(key: String, cur: Float) = o.optDouble(key, cur.toDouble()).toFloat().takeIf { !it.isNaN() }?.coerceIn(0f, 1f) ?: cur
        state.mode = choice("mode", MODE_TABS, state.mode)
        state.style = choice("style", STYLES, state.style)
        state.finish = choice("finish", FINISHES, state.finish)
        state.quality = choice("quality", QUALITIES, state.quality)
        state.amber = unit("amber", state.amber)
        state.explode = unit("explode", state.explode)
        val sec = o.optJSONObject("section")
        state.sectionOn = sec != null
        if (sec != null) {
            state.sectionAxis = sec.optString("axis", "x").takeIf { it == "x" || it == "z" } ?: "x"
            state.sectionT = sec.optDouble("t", .5).toFloat().takeIf { !it.isNaN() }?.coerceIn(0f, 1f) ?: .5f
        }
        state.dims = o.optBoolean("dims", false)
        state.autorotate = o.optBoolean("autorotate", false)
        state.isolate = if (o.isNull("isolate")) null else o.optString("isolate").takeIf { it.isNotBlank() && knownGroup(it) }
        state.selected = null; state.cinematic = false; picked = null; beforeNight = null
        if (camera != null && CAMERAS.any { it.first == camera }) lastCamera = camera
        push(state.toJson())
    }

    // ---------- Night shift ----------
    private var beforeNight: JSONObject? = null

    /** Cinematic, slowly orbiting, no picking. The state before is restored by [exitNight]. */
    fun enterNight() {
        if (state.cinematic) return
        beforeNight = JSONObject().put("autorotate", state.autorotate).put("style", state.style).put("explode", state.explode.toDouble())
            .put("dims", state.dims).put("section", state.section()).put("isolate", state.isolate ?: JSONObject.NULL)
        picked = null
        state.cinematic = true; state.autorotate = false; state.style = "studio"; state.explode = 0f; state.dims = false
        state.sectionOn = false; state.isolate = null; state.selected = null
        push(JSONObject().put("cinematic", true).put("autorotate", false).put("style", "studio").put("explode", 0.0).put("dims", false)
            .put("section", JSONObject.NULL).put("isolate", JSONObject.NULL).put("selected", JSONObject.NULL))
    }

    fun exitNight() {
        if (!state.cinematic) return
        state.cinematic = false
        val b = beforeNight; beforeNight = null
        val o = JSONObject().put("cinematic", false)
        if (b != null) {
            state.autorotate = b.optBoolean("autorotate"); state.style = b.optString("style", "studio")
            state.explode = b.optDouble("explode", 0.0).toFloat(); state.dims = b.optBoolean("dims")
            val sec = b.optJSONObject("section")
            state.sectionOn = sec != null
            if (sec != null) { state.sectionAxis = sec.optString("axis", "x"); state.sectionT = sec.optDouble("t", .5).toFloat() }
            state.isolate = if (b.isNull("isolate")) null else b.optString("isolate")
            o.put("autorotate", state.autorotate).put("style", state.style).put("explode", state.explode.toDouble()).put("dims", state.dims)
                .put("section", state.section()).put("isolate", state.isolate ?: JSONObject.NULL)
        }
        push(o)
        camera(lastCamera)
    }

    /** Apply a "See it live" preset. */
    fun apply(p: Preset) {
        val o = JSONObject()
        p.mode?.let { state.mode = it; o.put("mode", it) }
        p.style?.let { state.style = it; o.put("style", it) }
        p.finish?.let { state.finish = it; o.put("finish", it) }
        p.amber?.let { state.amber = it; o.put("amber", it.toDouble()) }
        p.explode?.let { state.explode = it; o.put("explode", it.toDouble()) }
        p.dims?.let { state.dims = it; o.put("dims", it) }
        if (p.section != null) { state.sectionOn = true; state.sectionAxis = p.section; state.sectionT = 0.5f; o.put("section", state.section()) }
        else if (state.sectionOn) { state.sectionOn = false; o.put("section", JSONObject.NULL) }
        if (p.isolate != null) { state.isolate = p.isolate; o.put("isolate", p.isolate) }
        else if (p.clearIsolate && state.isolate != null) { state.isolate = null; o.put("isolate", JSONObject.NULL) }
        picked = null
        if (state.selected != null) { state.selected = null; o.put("selected", JSONObject.NULL) }
        if (o.length() > 0) push(o)
        p.camera?.let { camera(it) }
        p.dock?.let { dock(it) }
    }

    /** Back to a calm default view. */
    fun resetView() {
        apply(Preset(style = "studio", explode = 0f, dims = false, camera = "hero"))
        if (state.autorotate) setAutorotate(false)
        dock("reset")
    }

    private fun push(key: String, value: Any) = push(JSONObject().put(key, value))

    private fun push(partial: JSONObject) {
        val last = queue.lastOrNull()
        if (last is JSONObject) partial.keys().forEach { k -> last.put(k, partial.get(k)) } else queue.add(partial)
        scheduleFlush()
    }

    private fun call(js: String) { queue.add(js); scheduleFlush() }

    private var flushPosted = false
    private fun scheduleFlush() {
        if (flushPosted) return
        flushPosted = true
        main.post { flushPosted = false; flush() }
    }

    /** Sends queued calls, in order, once the page has loaded. Before that they wait in the queue. */
    fun flush() {
        if (!pageLoaded || queue.isEmpty()) return
        val ev = evaluator
        val wv = webView
        if (ev == null && wv == null) return
        val items = ArrayList(queue); queue.clear()
        for (it in items) {
            val js = if (it is JSONObject) "NA.setState($it)" else it as String
            if (ev != null) ev(js)
            else wv?.evaluateJavascript("(function(){try{if(window.NA){$js;}}catch(e){console.error(e);}})();", null)
        }
    }

    /** Number of calls waiting for the page (for tests and diagnostics). */
    val pending: Int get() = queue.size

    fun onPageLoaded() {
        pageLoaded = true
        flush()
    }

    // ---------- the WebView ----------
    fun viewerUrl(): String {
        val json = state.toJson().toString()
        return "https://${WebViewAssetLoader.DEFAULT_DOMAIN}/assets/viewer/index.html?state=" + URLEncoder.encode(json, "UTF-8").replace("+", "%20")
    }

    /** Tests set this to exercise the WebView path before the viewer bundle exists. */
    var assumeBundled = false

    private fun bundled(ctx: Context) = assumeBundled || AssetIndex.exists(ctx, "viewer/index.html")

    /** The container currently showing the WebView (for tests and diagnostics). */
    val attachedTo: ViewGroup? get() = webView?.parent as? ViewGroup
    val slotCount: Int get() = slots.size

    @SuppressLint("SetJavaScriptEnabled")
    private fun ensureWebView(ctx: Context): WebView? {
        webView?.let { return it }
        if (destroyed) return null
        if (!bundled(ctx)) { fail("live renderer not in this build"); return null }
        val wv = try { WebView(ctx) } catch (e: Throwable) {
            // e.g. WebView provider missing or being updated
            Log.w(TAG, "WebView unavailable", e); fail("WebView unavailable on this device"); return null
        }
        // Let the viewer's developers inspect the page from Chrome in debuggable builds only.
        if ((ctx.applicationInfo.flags and android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE) != 0) runCatching { WebView.setWebContentsDebuggingEnabled(true) }
        val loader = WebViewAssetLoader.Builder()
            .addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(ctx))
            .build()
        wv.setBackgroundColor(Color.TRANSPARENT)
        wv.isVerticalScrollBarEnabled = false
        wv.isHorizontalScrollBarEnabled = false
        wv.overScrollMode = WebView.OVER_SCROLL_NEVER
        wv.settings.apply {
            javaScriptEnabled = true
            allowFileAccess = false
            allowContentAccess = false
            mediaPlaybackRequiresUserGesture = true
            setSupportZoom(false)
            builtInZoomControls = false
            displayZoomControls = false
        }
        wv.addJavascriptInterface(bridge, "NightArrayHost")
        wv.webViewClient = object : WebViewClientCompat() {
            override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? =
                loader.shouldInterceptRequest(request.url)

            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean =
                request.url.host != WebViewAssetLoader.DEFAULT_DOMAIN // never navigate away from the bundled viewer

            override fun onPageFinished(view: WebView, url: String) {
                if (view !== webView) return
                // viewer.js installs window.NA the moment it runs. A page without it (a WebView too old to parse the
                // bundle, a missing or truncated viewer.js) would swallow every call, and can't report an error either:
                // the viewer's error reporter lives in that same script. So check before letting the queue go.
                view.evaluateJavascript(NA_PROBE) { r ->
                    if (view !== webView || destroyed) return@evaluateJavascript
                    if (r == "true") onPageLoaded()
                    else if (status == LiveStatus.Loading) fail(noViewerMessage(appContext))
                }
            }

            override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceErrorCompat) {
                if (request.isForMainFrame && view === webView) fail("the live renderer couldn't load")
            }

            override fun onRenderProcessGone(view: WebView, detail: RenderProcessGoneDetail): Boolean {
                // Either way: drop this WebView, keep the app alive.
                if (view !== webView) { runCatching { (view.parent as? ViewGroup)?.removeView(view); view.destroy() }; return true }
                discardWebView(view)
                if (!detail.didCrash() && autoRecreates < MAX_AUTO_RECREATES) {
                    // The system reclaimed the renderer's memory (a heavy WebGL page, typically while we're in the
                    // background). That's no error: rebuild it quietly, now if it's on screen, else at the next
                    // onResume / claim. Capped, so a device that keeps reclaiming it ends up on the stills + Retry.
                    autoRecreates++
                    resetForReload()
                    if (resumed && slots.isNotEmpty()) main.post { recreateIfIdle() }
                } else fail("the live renderer stopped")
                return true
            }
        }
        webView = wv
        pageLoaded = false
        if (!resumed) runCatching { wv.pauseTimers() } else runCatching { wv.resumeTimers() }
        status = LiveStatus.Loading; errorMessage = null
        // The full state travels in the URL, so drop queued state merges; keep commands (camera, dock, frame).
        queue.removeAll { it is JSONObject }
        // The camera doesn't travel in the URL, and a new page (Retry, a renderer rebuilt, a restored process) boots at
        // "hero": bring back the preset the Camera chips and the still underneath show. Queued commands run before the
        // first frame, so it's a jump, not a move. Not while isolated (the page frames that group itself) or in Night
        // shift (its own orbit; exitNight() sends the camera). In front, so commands queued since (frame, dock) win.
        cameraOwed = state.isolate != null && lastCamera != "hero"
        if (!state.cinematic && state.isolate == null && lastCamera != "hero" && queue.none { it is String && it.startsWith("NA.camera(") })
            queue.add(0, "NA.camera(${JSONObject.quote(lastCamera)})")
        loadGeneration++
        wv.loadUrl(viewerUrl())
        if (!resumed) wv.onPause()
        return wv
    }

    private fun discardWebView(view: WebView) {
        webView = null; pageLoaded = false
        runCatching { (view.parent as? ViewGroup)?.removeView(view) }
        runCatching { view.destroy() }
    }

    /** Recreate the renderer after an error (or a page that never got ready). The dock sequence starts over too. */
    fun retry(ctx: Context) {
        webView?.let { discardWebView(it) }
        resetForReload()
        if (slots.isNotEmpty()) { ensureWebView(ctx); attachTop() }
    }

    /** Between two pages: no dock sequence carries over (the new page starts it over), and nothing is wrong (yet). */
    private fun resetForReload() {
        cancelLocalDock(); main.removeCallbacks(dockWatchdog); dropQueuedDock()
        dockPlaying = false; dockStep = null
        status = LiveStatus.Idle; errorMessage = null
    }

    /** Quiet rebuilds after the system reclaimed the renderer, since the last page that got ready. */
    private var autoRecreates = 0

    /** Rebuilds a renderer the system reclaimed ([LiveStatus.Idle], no WebView) once a slot shows it and we're in front. */
    private fun recreateIfIdle() {
        if (webView != null || destroyed || !resumed || status != LiveStatus.Idle || slots.isEmpty()) return
        ensureWebView(slots.last().context); attachTop()
    }

    fun claim(container: FrameLayout) {
        slots.remove(container); slots.add(container)
        ensureWebView(container.context)
        attachTop()
    }

    fun release(container: FrameLayout) {
        slots.remove(container)
        webView?.let { if (it.parent === container) container.removeView(it) }
        attachTop()
    }

    private fun attachTop() {
        val wv = webView ?: return
        val top = slots.lastOrNull()
        if (top == null) { runCatching { wv.onPause() }; return }
        if (wv.parent !== top) {
            (wv.parent as? ViewGroup)?.removeView(wv)
            top.addView(wv, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        }
        if (resumed) runCatching { wv.onResume() }
    }

    fun onResume() {
        resumed = true
        val wv = webView
        if (wv == null) recreateIfIdle() // the system reclaimed the renderer while we were away
        else { runCatching { wv.resumeTimers() }; if (slots.isNotEmpty()) runCatching { wv.onResume() } }
    }

    fun onPause() {
        resumed = false
        // Single-WebView app: pausing timers stops the render loop and JS work entirely while we're in the background.
        webView?.let { wv -> runCatching { wv.onPause() }; runCatching { wv.pauseTimers() } }
    }

    val hasWebView: Boolean get() = webView != null
    /** The live WebView, if one exists (tests check it is created once and re-parented, never duplicated). */
    val currentWebView: WebView? get() = webView
    val isAttached: Boolean get() = webView?.parent != null

    fun destroy() {
        destroyed = true
        main.removeCallbacksAndMessages(null)
        queue.clear()
        webView?.let { wv ->
            runCatching { (wv.parent as? ViewGroup)?.removeView(wv) }
            runCatching { wv.removeJavascriptInterface("NightArrayHost") }
            runCatching { wv.stopLoading(); wv.destroy() }
        }
        webView = null
        slots.clear()
    }

    companion object {
        const val TAG = "NightArray"
        /** Stills timings for the dock sequence (ms from the start), after app.js playDock. */
        private val LOCAL_DOCK = listOf("align" to 0L, "lower" to 1500L, "release" to 3000L, "lift" to 4300L, "done" to 6000L)
        private const val DOCK_WATCHDOG_MS = 15_000L
        /** Watchdog periods a still-loading page gets to report a dock step before the stills play the sequence. */
        private const val DOCK_WATCHDOG_PERIODS = 2
        /** Renderers reclaimed by the system that are rebuilt without asking, before one gets ready again. */
        private const val MAX_AUTO_RECREATES = 2
        /** Evaluates to true once viewer.js has run (it installs window.NA first thing). */
        const val NA_PROBE = "typeof window.NA==='object'"
        /** viewer.js is built for Chrome 87 (build.mjs `target`); an older WebView may not parse it. */
        private const val BUNDLE_CHROME = 87

        /** The major version of the WebView implementation, or null if unknown. */
        fun webViewMajor(versionName: String?): Int? = versionName?.trim()?.substringBefore('.')?.toIntOrNull()

        /** Why a page came up without the viewer: an actionable message when the WebView is known to be too old. */
        private fun noViewerMessage(ctx: Context): String {
            val major = runCatching { webViewMajor(WebViewCompat.getCurrentWebViewPackage(ctx)?.versionName) }.getOrNull()
            return if (major != null && major < BUNDLE_CHROME) "the live view needs a newer Android System WebView"
            else "the live renderer couldn't start on this device"
        }
    }
}

/** A place on screen where the shared WebView appears. The most recently composed slot owns it. */
@Composable
fun ViewerSlot(host: ViewerHost, modifier: Modifier = Modifier) {
    AndroidView(
        factory = { ctx -> FrameLayout(ctx).also { host.claim(it) } },
        modifier = modifier,
        onRelease = { host.release(it) },
    )
}

/** Candidate stills that match the current viewer state, best match first (SPEC.md §4 names). */
fun stillsFor(s: ViewerState, camera: String = "hero", dockStep: String? = null): List<String> = buildList {
    s.isolate?.let { add("part-$it.jpg") }
    if (s.cinematic) add("night.jpg")
    when (dockStep) { "align" -> add("dock-align.jpg"); "lower" -> add("dock-lower.jpg"); "release", "lift" -> add("dock-release.jpg") }
    when (s.style) { "cad" -> add("cad.jpg"); "xray" -> add("xray.jpg"); "blueprint" -> add("blueprint.jpg") }
    if (s.sectionOn) add("section.jpg")
    if (s.explode > 0.25f) add("exploded.jpg")
    if (s.style == "studio") when (camera) { "dock" -> add("dock-lower.jpg"); "trays" -> add("trays.jpg"); "display" -> add("display.jpg") }
    if (s.finish != "titanium") add("finish-${s.finish}.jpg")
    if (s.amber < 0.05f) add("amber-off.jpg")
    add("hero-${s.mode}.jpg")
    add("hero-work.jpg")
}

