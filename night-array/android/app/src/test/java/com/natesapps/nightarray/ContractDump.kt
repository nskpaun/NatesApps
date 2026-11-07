package com.natesapps.nightarray

import android.content.Context
import android.os.Looper
import android.webkit.RenderProcessGoneDetail
import android.webkit.ValueCallback
import android.webkit.WebView
import android.widget.FrameLayout
import androidx.compose.runtime.saveable.SaverScope
import androidx.test.core.app.ApplicationProvider
import androidx.webkit.WebViewAssetLoader
import kotlinx.coroutines.cancel
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import org.robolectric.annotation.Implementation
import org.robolectric.annotation.Implements
import org.robolectric.shadow.api.Shadow
import org.robolectric.shadows.ShadowWebView
import java.io.File

/**
 * The Kotlin half of the Kotlin <-> JS contract test; `viewer/test/bridge.mjs` (`npm run test:bridge`) is the other half.
 *
 * Drives the real [AppState] / [ViewerHost] code through realistic sessions, with the real WebView path (no evaluator
 * hook): a recording WebView shadow captures the exact URL every new page is loaded with and every string the app hands
 * `evaluateJavascript()`, the onPageFinished `window.NA` probe included. Events the page would post go in through the real
 * [ViewerHost.Bridge.post]. After every step it records the state the Kotlin side now believes the page is in.
 *
 * Writes `android/app/build/contract/kotlin-dump.json`. The JS side loads those URLs in headless Chromium the way
 * WebViewAssetLoader serves them, replays the strings verbatim and asserts that the viewer ends up where Kotlin thinks
 * it is, and that every event it posts back is one ViewerHost.handle() understands.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], shadows = [ContractDump.RecordingWebView::class])
class ContractDump {
    private val ctx: Context get() = ApplicationProvider.getApplicationContext()
    private fun idle() = shadowOf(Looper.getMainLooper()).idle()

    /** One thing the app handed a WebView: a loadUrl() or an evaluateJavascript(). */
    class Call(val view: RecordingWebView, val load: Boolean, val text: String, val callback: ValueCallback<String>?)

    /** Records, in order, what the app hands every WebView it creates (and still behaves like Robolectric's own shadow). */
    @Implements(WebView::class)
    class RecordingWebView : ShadowWebView() {
        @Implementation
        override fun loadUrl(url: String?) {
            calls += Call(this, true, url ?: "", null)
            super.loadUrl(url)
        }

        @Implementation
        override fun evaluateJavascript(script: String?, callback: ValueCallback<String>?) {
            calls += Call(this, false, script ?: "", callback)
            super.evaluateJavascript(script, callback)
        }
    }

    private val sessions = JSONArray()

    @Before fun setup() { Img.synchronous = true; Repo.reset(); calls.clear() }

    /** A recorded session: an [AppState] whose host drives a real (shadowed) WebView. */
    private inner class Session(val name: String, val app: AppState) {
        val host get() = app.host
        val steps = JSONArray()
        /** The Studio's ViewerSlot container, and the Night shift screen's. */
        val studioSlot = FrameLayout(ctx)
        val nightSlot = FrameLayout(ctx)
        private val answers = HashMap<Call, String>()
        var loads = 0; private set
        var readies = 0; private set

        init { host.assumeBundled = true }

        private fun record(label: String, kind: String, extra: JSONObject? = null, body: () -> Unit) {
            val mark = calls.size
            body(); idle()
            val mine = calls.subList(mark, calls.size).toList()
            val o = JSONObject().put("label", label).put("kind", kind)
            extra?.keys()?.forEach { k -> o.put(k, extra.get(k)) }
            val urls = mine.filter { it.load }
            assertTrue("$name / $label: one page load per step at most", urls.size <= 1)
            urls.firstOrNull()?.let { o.put("load", it.text); loads++ }
            val current = host.currentWebView?.let { Shadow.extract<RecordingWebView>(it) }
            val js = JSONArray()
            for (c in mine.filter { !it.load }) {
                assertTrue("$name / $label: script handed to a WebView that is no longer the live one: ${c.text}", c.view === current)
                if (c.callback != null) {
                    // only the onPageFinished probe asks for an answer
                    assertEquals("$name / $label", ViewerHost.NA_PROBE, c.text)
                    o.put("probe", JSONObject().put("js", c.text).put("answer", answers[c] ?: JSONObject.NULL))
                } else js.put(c.text)
            }
            o.put("js", js)
            o.put("expect", JSONObject()
                .put("state", host.state.toJson())
                .put("camera", host.lastCamera)
                .put("dockStep", host.dockStep ?: JSONObject.NULL)
                .put("dockPlaying", host.dockPlaying)
                .put("picked", host.picked ?: JSONObject.NULL)
                .put("status", host.status.name)
                .put("webView", host.hasWebView))
            steps.put(o)
        }

        /** Something the user (or the app) does. */
        fun step(label: String, body: () -> Unit) = record(label, "action", null, body)

        /** onPageFinished for the live WebView: the app probes for window.NA, gets "true" back, and lets its queue go. */
        fun pageFinished(label: String = "onPageFinished: window.NA probe answers true, the queue goes out") = record(label, "pageFinished") {
            val wv = host.currentWebView!!
            val sh = Shadow.extract<RecordingWebView>(wv)
            val mark = calls.size
            sh.webViewClient.onPageFinished(wv, sh.lastLoadedUrl)
            val probe = calls.subList(mark, calls.size).single { !it.load && it.callback != null }
            answers[probe] = "true"
            probe.callback!!.onReceiveValue("true")
        }

        /** An event the page posts through window.NightArrayHost; [tap] says what the user tapped to cause it, if anything. */
        fun event(label: String, json: String, tap: String? = null) =
            record(label, "event", JSONObject().put("event", json).put("tap", tap ?: JSONObject.NULL)) {
                host.bridge.post(json)
                if (JSONObject(json).optString("type") == "ready") readies++
            }

        fun ready() = event("page: ready", """{"type":"ready"}""")

        /** The page's Play sequence events, as app.js posts them. */
        fun dockEvents() { for (s in DOCK_EVENTS) event("page: dockStep $s", """{"type":"dockStep","step":"$s"}""") }

        fun renderGone(crash: Boolean) {
            val wv = host.currentWebView!!
            val detail = object : RenderProcessGoneDetail() { override fun didCrash() = crash; override fun rendererPriorityAtExit() = 0 }
            assertTrue(shadowOf(wv).webViewClient.onRenderProcessGone(wv, detail))
        }
    }

    private fun session(name: String, about: String, app: AppState = AppState(ctx), body: Session.() -> Unit) {
        val s = Session(name, app)
        s.body()
        assertTrue("$name: every page that was loaded got its ready", s.loads > 0 && s.readies == s.loads)
        assertEquals("$name ends live", LiveStatus.Ready, s.host.status)
        sessions.put(JSONObject().put("name", name).put("about", about).put("steps", s.steps))
        s.host.destroy(); s.app.scope.cancel()
    }

    /** What the app saves when the Activity goes away, and the AppState it comes back as (process death). */
    private fun recreated(prep: (AppState) -> Unit): AppState {
        val saver = appStateSaver(ctx)
        val a = AppState(ctx)
        prep(a)
        val saved = with(saver) { SaverScope { true }.save(a) }!!
        a.host.destroy(); a.scope.cancel()
        return saver.restore(saved)!!
    }

    @Test fun dump() {
        val scene = Repo.scene(ctx)
        val groups = scene.groups.map { it.id }
        assertTrue("the packaged scene.json parses (not the built-in envelope)", groups.size > 3)
        val pick = { g: String? -> JSONObject().put("type", "pick").put("group", g ?: JSONObject.NULL).toString() }
        val rotated = { l: List<Pair<String, String>> -> (l.drop(1) + l.take(1)).map { it.first } }

        session("studio", "Explore -> Studio cold start, every Studio control, a tap round trip, the dock, Night shift, the stories, Files, Reset view and a Retry") {
            step("Explore: Open the Studio (no page yet)") { app.openStudio(Preset(mode = "work", camera = "hero")) }
            step("Studio: its ViewerSlot creates the WebView, which loads the page") { host.claim(studioSlot) }
            step("Camera chip Trays while the page loads") { host.camera("trays") }
            step("Tools: Explode 40 % while the page loads") { host.setExplode(.4f) }
            pageFinished()
            ready()
            for (m in rotated(MODE_TABS)) step("Mode tab $m") { host.setMode(m) }
            for (s in rotated(STYLES)) step("Style chip $s") { host.setStyle(s) }
            for (f in rotated(FINISHES)) step("Finish $f") { host.setFinish(f) }
            step("Amber slider flung 0 -> 100 % within one main-loop turn (21 updates)") { for (i in 0..20) host.setAmber(i / 20f) }
            for (i in 0..10) step("Amber slider drag ${100 - 10 * i} %") { host.setAmber(1f - i / 10f) }
            step("Amber slider 80 %") { host.setAmber(.8f) }
            for (i in 0..10) step("Explode slider drag ${10 * i} %") { host.setExplode(i / 10f) }
            step("Explode slider flung back to assembled (11 updates)") { for (i in 10 downTo 0) host.setExplode(i / 10f) }
            step("Section on") { host.setSection(true) }
            for (i in 0..10) step("Section plane drag ${10 * i} %") { host.setSection(true, t = i / 10f) }
            step("Section axis Front-back (Z)") { host.setSection(true, axis = "z") }
            step("Section axis Across (X)") { host.setSection(true, axis = "x") }
            step("Section off") { host.setSection(false) }
            step("Dimensions on") { host.setDims(true) }
            step("Dimensions off") { host.setDims(false) }
            step("Auto-rotate on") { host.setAutorotate(true) }
            step("Auto-rotate off") { host.setAutorotate(false) }
            for (q in rotated(QUALITIES)) step("Quality $q") { host.setQuality(q) }
            step("Cinematic on (setCinematic)") { host.setCinematic(true) }
            step("Cinematic off (setCinematic)") { host.setCinematic(false) }
            for ((c, _) in CAMERAS) step("Camera chip $c") { host.camera(c) }
            for (g in groups) step("Part sheet Frame: $g") { host.frame(g) }
            for (g in groups) step("Parts chip $g") { host.pickLocal(g) }
            step("Part sheet closed") { host.closeSheet() }
            step("Select display") { host.select("display") }
            step("Select none") { host.select(null) }
            for (g in groups) step("Part sheet Isolate: $g") { host.toggleIsolate(g) }
            step("Parts chip mouse while ${groups.last()} is isolated (the isolation follows the pick)") { host.pickLocal("mouse") }
            step("Part sheet Show all") { host.toggleIsolate("mouse") }
            step("Isolate dock (setIsolate)") { host.setIsolate("dock") }
            step("Isolated notice: Show all") { host.setIsolate(null) }
            step("Part sheet closed") { host.closeSheet() }
            // a tap round trip: the page posts the pick, the app selects the group and opens its sheet
            step("Camera chip hero") { host.camera("hero") }
            event("page: pick keyboard (a finger tap on the keyboard)", pick("keyboard"), tap = "keyboard")
            step("Part sheet closed") { host.closeSheet() }
            event("page: pick null (a tap on empty space)", pick(null), tap = "empty")
            // the dock panel
            step("Dock panel: Play sequence") { host.camera("dock"); host.dock("play") }
            dockEvents()
            for (s in dockUiSteps(scene)) step("Dock step card ${s.n} (${s.id})") { host.dock(dockCard(s, host)) }
            step("Dock step card 3 again (lift)") { host.dock(dockCard(dockUiSteps(scene)[2], host)) }
            step("Dock panel: Reset") { host.dock("reset") }
            step("Dock panel: Play sequence") { host.camera("dock"); host.dock("play") }
            event("page: dockStep align", """{"type":"dockStep","step":"align"}""")
            step("Dock panel: Reset mid-sequence") { host.dock("reset") }
            step("Explore dock strip: step 2 (lower)") { app.openStudio(Preset(mode = "stow", camera = "dock", dock = "lower")) }
            step("Dock panel: Reset") { host.dock("reset") }
            // Night shift over an isolated group: the Night screen takes the WebView and gives it back
            step("Mode tab work") { host.setMode("work") }
            step("Part sheet Isolate: dock") { host.pickLocal("dock"); host.toggleIsolate("dock") }
            step("Night shift (the Night screen's slot takes the WebView)") { app.startNight(); host.claim(nightSlot) }
            step("Night shift: Back") { app.stopNight(); host.release(nightSlot) }
            step("Part sheet closed") { host.closeSheet() }
            // every story's "See it live"
            for (st in STORIES) {
                step("Story ${st.id}: ${st.liveLabel}") { app.openStudio(st.preset) }
                if (st.preset.dock == "play") dockEvents()
            }
            step("Explore: mode card Standalone") { app.openStudio(Preset(mode = "standalone", style = "studio", camera = "hero", explode = 0f)) }
            step("Files -> Laptop -> View in Studio") { app.openStudio(Preset(isolate = "laptop", style = "studio", explode = 0f)); host.frame("laptop") }
            step("Files -> Internals -> View in Studio") { app.openStudio(Preset(isolate = "internals", style = "xray", explode = 0f)); host.frame("internals") }
            step("Files: Open in Studio") { app.openStudio(Preset(mode = "stow", style = "cad", camera = "hero", explode = .6f)) }
            step("Reset view") { host.resetView() }
            // Retry: a new page, whose URL carries the selection and section, gets the camera preset back
            step("Camera chip top") { host.camera("top") }
            step("Section on, Z at 25 %") { host.setSection(true, "z", .25f) }
            step("Parts chip mouse") { host.pickLocal("mouse") }
            step("Live notice: Retry (the WebView is recreated)") { host.retry(ctx) }
            pageFinished()
            ready()
            step("Part sheet closed") { host.closeSheet() }
        }

        session("restored", "Process death and back (saved state: stow, x-ray, oxblood, amber, explode, section, balanced, camera Trays)",
            recreated { a ->
                with(a.host) { setMode("stow"); setStyle("xray"); setFinish("oxblood"); setAmber(.15f); setExplode(.35f); setSection(true, "z", .3f); setQuality("balanced"); setAutorotate(true); camera("trays") }
            }) {
            step("Studio: the restored app's first page") { host.claim(studioSlot) }
            pageFinished()
            ready()
            step("Dimensions on") { host.setDims(true) }
        }

        session("restored-isolated", "Process death and back while a group was isolated (camera Trays, internals isolated and selected)",
            recreated { a -> with(a.host) { setStyle("xray"); camera("trays"); setIsolate("internals"); select("internals") } }) {
            step("Studio: the restored app's first page") { host.claim(studioSlot) }
            pageFinished()
            ready()
            step("Isolated notice: Show all") { host.setIsolate(null) }
            step("Camera chip trays") { host.camera("trays") }
        }

        session("night-cold", "Explore's Night shift card before any live page existed, then back and into the Studio") {
            step("Explore: Night shift card (no page yet)") { app.startNight() }
            step("Night shift: its slot creates the WebView") { host.claim(nightSlot) }
            pageFinished()
            ready()
            step("Night shift: Back") { app.stopNight(); host.release(nightSlot) }
            step("Explore: Open the Studio (its slot takes the WebView)") { app.openStudio(Preset(mode = "work", camera = "hero")); host.claim(studioSlot) }
            step("Camera chip display") { host.camera("display") }
        }

        session("dock-story-cold", "Story 03 'Play the sequence live' as the first thing after launch: camera and play queued before the page") {
            step("Story dock: Play the sequence live (no page yet)") { app.openStudio(STORIES.first { it.id == "dock" }.preset) }
            step("Studio: its ViewerSlot creates the WebView") { host.claim(studioSlot) }
            pageFinished()
            ready()
            dockEvents()
        }

        session("files-cold", "Files -> Laptop -> View in Studio in Standalone (the laptop is hidden by the pose) before any live page") {
            step("Studio: Mode tab standalone (no page yet)") { host.setMode("standalone") }
            step("Files -> Laptop -> View in Studio (no page yet)") { app.openStudio(Preset(isolate = "laptop", style = "studio", explode = 0f)); host.frame("laptop") }
            step("Studio: its ViewerSlot creates the WebView") { host.claim(studioSlot) }
            step("Parts chip laptop while the page loads") { host.pickLocal("laptop") }
            pageFinished()
            ready()
            step("Parts chip keyboard (the isolation moves to it)") { host.pickLocal("keyboard") }
            step("Isolated notice: Show all") { host.setIsolate(null) }
            step("Part sheet closed") { host.closeSheet() }
        }

        session("recreate", "The system reclaims the renderer while the app is in the background; it is rebuilt on resume") {
            step("Explore: Open the Studio") { app.openStudio(Preset(mode = "work", camera = "hero")); host.claim(studioSlot) }
            pageFinished()
            ready()
            step("Camera chip side") { host.camera("side") }
            step("Style chip blueprint") { host.setStyle("blueprint") }
            step("App goes to the background") { host.onPause() }
            step("Renderer reclaimed (onRenderProcessGone, didCrash = false)") { renderGone(crash = false) }
            step("Style chip cad (queued: no page)") { host.setStyle("cad") }
            step("Back in the app: the renderer is rebuilt") { host.onResume() }
            pageFinished()
            ready()
            step("Camera chip front") { host.camera("front") }
        }

        val dump = JSONObject()
            .put("format", 1)
            .put("generator", "android/app/src/test/java/com/natesapps/nightarray/ContractDump.kt")
            .put("assetHost", WebViewAssetLoader.DEFAULT_DOMAIN)
            .put("probe", ViewerHost.NA_PROBE)
            .put("groups", JSONArray(groups))
            .put("cameras", JSONArray(CAMERAS.map { it.first }))
            .put("sessions", sessions)
        val out = dumpFile()
        out.parentFile!!.mkdirs()
        out.writeText(dump.toString(1) + "\n")
        println("ContractDump: ${sessions.length()} sessions -> ${out.absolutePath}")
    }

    companion object {
        /** Everything the shadows recorded, across WebViews, in order. */
        val calls = ArrayList<Call>()

        /** The dockStep events a Play sequence posts (app.js DOCK_PLAY; 'done' once the reset motion starts). */
        val DOCK_EVENTS = listOf("align", "lower", "release", "lift", "done")

        /** What a Studio dock step card sends (Studio.kt DockPanel): card 3 tapped while released lifts the laptop out. */
        fun dockCard(s: DockUiStep, host: ViewerHost) = if (s.n == 3 && host.dockStep == "release") "lift" else s.id

        /** android/app/build/contract/kotlin-dump.json (Gradle runs unit tests in the module directory). */
        fun dumpFile(): File {
            val dir = File(System.getProperty("user.dir") ?: ".").absoluteFile
            val module = if (File(dir, "src/test").isDirectory) dir else File(dir, "app")
            return File(module, "build/contract/kotlin-dump.json")
        }
    }
}
