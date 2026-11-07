package com.natesapps.nightarray

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Looper
import androidx.activity.ComponentActivity
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.core.app.ApplicationProvider
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import java.io.File
import java.net.URLDecoder

/** Renders every screen of the app and exercises its main interactions, including fake viewer events through the bridge. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], qualifiers = "w411dp-h891dp-xxhdpi")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class SmokeTest {
    @get:Rule val rule = createAndroidComposeRule<ComponentActivity>()
    private val ctx: Context get() = ApplicationProvider.getApplicationContext()
    private lateinit var app: AppState
    private val sent = mutableListOf<String>()
    private val scene: Scene get() = Repo.scene(ctx)

    @Before fun setup() { Img.synchronous = true; Repo.reset() }

    // ---------- helpers ----------
    private fun show(route: String = "explore", prep: (AppState) -> Unit = {}, body: () -> Unit) {
        app = AppState(ctx)
        app.host.evaluator = { sent += it }
        when {
            route == "explore" -> {}
            TABS.any { it.route == route } -> app.nav.tab(route)
            else -> app.nav.go(route)
        }
        prep(app)
        rule.mainClock.autoAdvance = false
        rule.setContent { AppTheme { App(app) } }
        tick(2500)
        body()
    }

    private fun idle() = shadowOf(Looper.getMainLooper()).idle()
    private fun tick(ms: Long = 1000) { repeat((ms / 250).toInt().coerceAtLeast(1)) { rule.mainClock.advanceTimeBy(250); idle(); rule.waitForIdle() } }
    private fun tag(t: String) = rule.onNodeWithTag(t)
    private fun act(t: String) { tag(t).performSemanticsAction(SemanticsActions.OnClick); tick() }
    private fun texts(s: String) = rule.onAllNodesWithText(s, substring = true, ignoreCase = true)
    /** Measurements are displayed with non-breaking spaces (see nbUnits), so accept either spelling. */
    private fun shows(s: String) = texts(s).fetchSemanticsNodes().isNotEmpty() || texts(s.nbUnits()).fetchSemanticsNodes().isNotEmpty()
    /** Instant, key-based scrolling (animated scrolls never finish while the test clock is paused). */
    private fun scrollTo(list: String, key: String) { tag(list).performScrollToKey(key); tick(500) }
    private fun back() { rule.runOnUiThread { rule.activity.onBackPressedDispatcher.onBackPressed() }; tick(1200) }
    private fun post(json: String) { app.host.bridge.post(json); idle(); tick(700) }
    private fun waitFor(timeoutMs: Long = 8000, cond: () -> Boolean) {
        val end = System.currentTimeMillis() + timeoutMs
        while (!cond() && System.currentTimeMillis() < end) { Thread.sleep(25); idle(); rule.mainClock.advanceTimeBy(16); rule.waitForIdle() }
        assertTrue("timed out waiting", cond())
    }
    private fun setSlider(t: String, v: Float) { tag(t).performSemanticsAction(SemanticsActions.SetProgress) { it(v) }; tick(500) }

    // ---------- Explore ----------
    @Test fun exploreRendersEverySection() = show {
        assertTrue(shows("NIGHT ARRAY"))
        assertTrue(shows("Your hardware. Your OS."))
        scrollTo("explore", "modes"); tag("mode-work").assertExists()
        scrollTo("explore", "s-dual"); tag("story-dual").assertExists()
        scrollTo("explore", "s-cablefree"); tag("story-cablefree").assertExists()
        scrollTo("explore", "dock"); tag("dock-strip").assertExists()
        scrollTo("explore", "materials"); tag("swatch-oxblood").assertExists()
        scrollTo("explore", "principles"); assertTrue(shows("DESIGN PRINCIPLES")); assertTrue(shows("SHOW THE SEAM"))
        scrollTo("explore", "board"); tag("board-card").assertExists()
        scrollTo("explore", "night"); tag("night-card").assertExists()
        scrollTo("explore", "footer"); assertTrue(shows("Every number in this app"))
    }

    @Test fun modeCardsOpenTheStudioInThatMode() = show {
        for (m in MODES) {
            scrollTo("explore", "modes")
            tag("modes-row").performScrollToKey(m.id); tick(500)
            act("mode-${m.id}")
            assertEquals("studio", app.nav.top)
            assertEquals(m.id, app.host.state.mode)
            tag("studio").assertExists()
            back()
            assertEquals("explore", app.nav.top)
        }
        // the hero CTA and a finish swatch also open the Studio
        scrollTo("explore", "hero")
        act("cta-studio"); assertEquals("studio", app.nav.top); back()
        scrollTo("explore", "materials"); act("swatch-graphite")
        assertEquals("graphite", app.host.state.finish); assertEquals("finish", app.studioPanel)
    }

    @Test fun everyStoryRendersAndSeesItLive() = show("story/dual") {
        scrollTo("story", "diagram"); tag("dual-diagram").assertExists()
        for (s in STORIES) {
            if (app.nav.top != "story/${s.id}") { rule.runOnUiThread { app.nav.go("story/${s.id}") }; tick(1500) }
            scrollTo("story", "head")
            assertTrue("title of ${s.id}", shows(s.title))
            scrollTo("story", "specs")
            assertEquals(storySpecs(s, scene).size, storySpecs(s, scene).count { shows(it.value) })
            act("see-live")
            assertEquals("studio", app.nav.top)
            s.preset.mode?.let { assertEquals(it, app.host.state.mode) }
            s.preset.style?.let { assertEquals(it, app.host.state.style) }
            s.preset.finish?.let { assertEquals(it, app.host.state.finish) }
            if (s.id == "dock") { assertTrue(app.host.dockPlaying); assertEquals("dock", app.studioPanel) }
            back()
            assertEquals("story/${s.id}", app.nav.top)
        }
        // "next" walks the stories in order
        scrollTo("story", "next"); act("next-story")
        assertEquals("story/${STORIES.first().id}", app.nav.top)
    }

    @Test fun storyDockStripPlaysThatStep() = show("story/dock") {
        scrollTo("story", "seq")
        act("dock-strip-lower")
        assertEquals("studio", app.nav.top)
        assertEquals("lower", app.host.dockStep)
    }

    @Test fun boardZoomsAndBackReturns() = show("board") {
        tag("board-zoom").performTouchInput { doubleClick() }; tick()
        assertTrue(shows("What changed"))
        back()
        assertEquals("explore", app.nav.top)
    }

    @Test fun nightShiftTakesOverAndBackLeavesFirst() = show("story/dual") {
        app.host.setAutorotate(true)
        rule.runOnUiThread { app.startNight() }; tick(2000)
        tag("night").assertExists()
        assertTrue(app.host.state.cinematic)
        assertFalse("Night shift orbits on its own", app.host.state.autorotate)
        assertTrue(shows(NIGHT_LINES[0]))
        tick(7500)
        assertTrue(shows(NIGHT_LINES[1]))
        post("""{"type":"pick","group":"dock"}""")
        assertNull("no picking in Night shift", app.host.picked)
        back()
        tag("night").assertDoesNotExist()
        assertFalse(app.host.state.cinematic)
        assertTrue("state before Night shift is restored", app.host.state.autorotate)
        assertEquals("story/dual", app.nav.top) // back went to Night shift first, not the story
        // the close button also leaves
        rule.runOnUiThread { app.startNight() }; tick(1500)
        rule.onNodeWithContentDescription("Exit Night shift").performClick(); tick(1500)
        tag("night").assertDoesNotExist()
    }

    // ---------- Studio + the shared WebView ----------
    @Test fun oneWebViewIsCreatedAndReparentedBetweenStudioAndNightShift() = show("studio", prep = { it.host.assumeBundled = true }) {
        val wv = app.host.currentWebView
        assertNotNull("Studio creates the WebView", wv)
        val sh = shadowOf(wv)
        assertTrue(sh.lastLoadedUrl.startsWith("https://appassets.androidplatform.net/assets/viewer/index.html?state="))
        assertNotNull("JS bridge registered", sh.getJavascriptInterface("NightArrayHost"))
        val studioSlot = app.host.attachedTo
        assertNotNull(studioSlot)
        rule.runOnUiThread { app.startNight() }; tick(2000)
        assertSame("same WebView in Night shift", wv, app.host.currentWebView)
        assertNotSame("moved into the Night shift slot", studioSlot, app.host.attachedTo)
        back(); tick(1000)
        assertSame(wv, app.host.currentWebView)
        assertSame("back in the Studio slot", studioSlot, app.host.attachedTo)
        act("tab-files"); tick(1000)
        assertSame("kept alive across navigation", wv, app.host.currentWebView)
        assertNull("detached while no screen shows it", app.host.attachedTo)
        act("tab-studio"); tick(1000)
        assertSame(wv, app.host.currentWebView)
        assertNotNull(app.host.attachedTo)
        // the still stays underneath until ready
        tag("live-notice").assertExists()
        post("""{"type":"ready"}"""); tick(1500)
        tag("live-notice").assertDoesNotExist()
    }

    @Test fun studioControlsDriveTheViewerState() = show("studio") {
        app.host.onPageLoaded() // pretend the page is up so calls flow to the evaluator
        act("mode-stow"); assertEquals("stow", app.host.state.mode)
        assertTrue(sent.any { it == """NA.setState({"mode":"stow"})""" })
        act("panel-view")
        act("style-cad"); assertEquals("cad", app.host.state.style)
        act("camera-dock"); assertEquals("dock", app.host.lastCamera); assertTrue(sent.contains("""NA.camera("dock")"""))
        act("panel-finish")
        act("finish-oxblood"); assertEquals("oxblood", app.host.state.finish)
        setSlider("amber-slider", .2f); assertEquals(.2f, app.host.state.amber, .02f)
        act("panel-tools")
        setSlider("explode-slider", .5f); assertEquals(.5f, app.host.state.explode, .02f)
        act("section-toggle"); assertTrue(app.host.state.sectionOn)
        act("axis-z"); assertEquals("z", app.host.state.sectionAxis)
        setSlider("section-slider", .3f); assertEquals(.3f, app.host.state.sectionT, .02f)
        assertTrue(sent.last().contains("\"section\":{\"axis\":\"z\""))
        act("dims-toggle"); assertTrue(app.host.state.dims)
        act("autorotate-toggle"); assertTrue(app.host.state.autorotate)
        act("quality-battery"); assertEquals("battery", app.host.state.quality)
        act("panel-dock")
        act("dock-play"); assertTrue(app.host.dockPlaying); assertTrue(sent.contains("""NA.dock("play")"""))
        act("panel-parts")
        act("part-keyboard")
        tag("part-sheet").assertExists()
        assertTrue(shows(scene.group("keyboard")!!.name))
        assertTrue(sent.contains("""NA.frame("keyboard")"""))
        act("sheet-isolate"); assertEquals("keyboard", app.host.state.isolate)
        tag("isolate-notice").assertExists()
        back()
        tag("part-sheet").assertDoesNotExist()
        assertEquals("studio", app.nav.top) // back closed the sheet, not the screen
        act("panel-toggle"); assertNull(app.studioPanel)
        act("reset"); assertEquals("studio", app.host.state.style); assertEquals(0f, app.host.state.explode)
        act("studio-night"); assertTrue(app.nightShift)
    }

    @Test fun bridgeEventsDriveTheUi() = show("studio", prep = { it.studioPanel = "dock" }) {
        tag("live-notice").assertExists()
        // Kotlin → JS waits for the page
        app.host.setStyle("xray"); idle()
        assertTrue(app.host.pending > 0); assertTrue(sent.isEmpty())
        post("""{"type":"ready"}""")
        assertEquals(LiveStatus.Ready, app.host.status)
        assertTrue("queued state flushed once ready", sent.any { it.startsWith("NA.setState(") && it.contains("\"style\":\"xray\"") })
        tick(1200)
        tag("live-notice").assertDoesNotExist()
        assertTrue(shows("Live"))
        // pick → part sheet
        post("""{"type":"pick","group":"dock"}""")
        tag("part-sheet").assertExists()
        assertTrue(shows(scene.group("dock")!!.name))
        assertEquals("dock", app.host.state.selected)
        act("sheet-files"); assertEquals("group/dock", app.nav.top); back()
        assertEquals("studio", app.nav.top)
        back() // closes the sheet
        tag("part-sheet").assertDoesNotExist()
        post("""{"type":"pick","group":null}""")
        tag("part-sheet").assertDoesNotExist()
        // a group the scene doesn't know opens nothing, and Back still leaves normally afterwards
        post("""{"type":"pick","group":"not_a_group"}""")
        tag("part-sheet").assertDoesNotExist()
        post("""{"type":"pick","group":null}""")
        // dockStep sequence highlights the active step
        tag("dock-panel").assertExists()
        post("""{"type":"dockStep","step":"align"}""")
        tag("dock-step-align").assertIsSelected(); tag("dock-step-lower").assertIsNotSelected()
        post("""{"type":"dockStep","step":"lower"}""")
        tag("dock-step-lower").assertIsSelected(); tag("dock-step-align").assertIsNotSelected()
        assertTrue(shows(dockUiSteps(scene)[1].caption))
        post("""{"type":"dockStep","step":"release"}""")
        tag("dock-step-release").assertIsSelected()
        post("""{"type":"dockStep","step":"lift"}""")
        tag("dock-step-release").assertIsSelected()
        post("""{"type":"dockStep","step":"done"}""")
        listOf("align", "lower", "release").forEach { tag("dock-step-$it").assertIsNotSelected() }
        assertFalse(app.host.dockPlaying)
        // tapping step 3 twice: release, then lift
        act("dock-step-release"); assertTrue(sent.contains("""NA.dock("release")"""))
        act("dock-step-release"); assertTrue(sent.contains("""NA.dock("lift")"""))
        // error → still + notice with the message
        post("""{"type":"error","message":"WebGL2 unavailable"}""")
        assertEquals(LiveStatus.Error, app.host.status)
        tag("live-notice").assertExists()
        assertTrue(shows("WebGL2 unavailable"))
        // garbage is ignored
        post("not json"); post("""{"type":"mystery"}""")
        tag("studio").assertExists()
    }

    @Test fun unknownPickDoesNotSwallowBack() = show("studio") {
        post("""{"type":"pick","group":"not_a_group"}""")
        tag("part-sheet").assertDoesNotExist()
        back()
        assertEquals("explore", app.nav.top)
    }

    // ---------- Files ----------
    @Test fun filesLibraryAndEveryGroupDetail() = show("files") {
        tag("assembly-card").assertExists()
        for (g in scene.groups) {
            scrollTo("files", g.id)
            act("group-${g.id}")
            assertEquals("group/${g.id}", app.nav.top)
            assertTrue(shows(g.name))
            scrollTo("group", "drawing"); tag("drawing-panel").assertExists()
            scrollTo("group", "files"); tag("group-files").assertExists()
            back()
            assertEquals("files", app.nav.top)
        }
    }

    @Test fun groupDetailViewInStudioIsolates() = show("group/dock") {
        app.host.onPageLoaded()
        scrollTo("group", "studio"); act("view-in-studio")
        assertEquals("studio", app.nav.top)
        assertEquals("dock", app.host.state.isolate)
        assertTrue(sent.contains("""NA.frame("dock")"""))
        back(); assertEquals("group/dock", app.nav.top)
    }

    @Test fun shareAndSaveCopyTheRealFile() = show("group/base") {
        val f = scene.files.firstOrNull { it.group == "base" && AssetIndex.exists(ctx, it.path) }
        scrollTo("group", "files")
        if (f == null) {
            assertTrue("missing files say so", shows("Not in this build"))
            return@show
        }
        // Share: cache copy + FileProvider + chooser with the right MIME type
        act("share-${f.id}")
        waitFor { shadowOf(rule.activity).peekNextStartedActivity() != null }
        val chooser = shadowOf(rule.activity).nextStartedActivity
        assertEquals(Intent.ACTION_CHOOSER, chooser.action)
        @Suppress("DEPRECATION") val send = chooser.getParcelableExtra<Intent>(Intent.EXTRA_INTENT)!!
        assertEquals(mimeOf(f.format, f.path), send.type)
        @Suppress("DEPRECATION") val uri = send.getParcelableExtra<Uri>(Intent.EXTRA_STREAM)!!
        assertEquals(ctx.packageName + ".files", uri.authority)
        val copy = File(File(ctx.cacheDir, "share"), Exporter.fileName(f))
        assertTrue(copy.exists())
        assertEquals(ctx.assets.open(f.path).use { it.readBytes().size.toLong() }, copy.length())
        // Save: CreateDocument with the right MIME type, then a stream copy into the chosen document
        act("save-${f.id}")
        val req = shadowOf(rule.activity).nextStartedActivityForResult
        assertEquals(Intent.ACTION_CREATE_DOCUMENT, req.intent.action)
        assertEquals(mimeOf(f.format, f.path), req.intent.type)
        val dest = File(ctx.filesDir, "saved-" + Exporter.fileName(f))
        val target = Uri.parse("content://com.example.documents/document/" + dest.name)
        shadowOf(rule.activity.contentResolver).registerOutputStream(target, java.io.FileOutputStream(dest))
        shadowOf(rule.activity).receiveResult(req.intent, Activity.RESULT_OK, Intent().setData(target))
        waitFor { dest.length() == copy.length() && app.toast != null }
        tick(500)
        assertTrue(app.toast!!.startsWith("Saved"))
        assertTrue(shows("Saved " + Exporter.fileName(f)))
    }

    @Test fun drawingOpensFullScreenWhenBundled() = show("group/base") {
        scrollTo("group", "drawing")
        if (texts("Drawing sheet not in this build").fetchSemanticsNodes().isEmpty()) {
            act("drawing-expand")
            assertEquals("drawing/base", app.nav.top)
            tag("drawing").assertExists()
            back(); assertEquals("group/base", app.nav.top)
        } else {
            rule.runOnUiThread { app.nav.go("drawing/base") }; tick(1500)
            tag("drawing").assertExists()
        }
    }

    // ---------- Specs ----------
    @Test fun specsSheetBomAndDeskFit() = show("specs") {
        val sc = scene.screen
        assertTrue(shows("${sc.canvasW} × ${sc.canvasH}"))
        scrollTo("spec-sheet", "Dimensions"); assertTrue(shows("DIMENSIONS"))
        act("specs-bom")
        tag("bom").assertExists()
        scene.groups.forEach { scrollTo("bom", "g-${it.id}"); tag("bom-${it.id}").assertExists() }
        act("specs-fit")
        tag("desk-fit").assertExists()
        tag("desk-width").performTextReplacement("120"); tick()
        assertEquals(120, app.deskW)
        assertTrue(shows("Doesn't fit"))
        act("desk-180")
        assertEquals(180, app.deskW); assertEquals(90, app.deskD)
        assertTrue(shows("It fits"))
        tag("desk-depth").performTextReplacement("50"); tick()
        assertTrue(shows("Fits stowed only"))
        rule.onNodeWithContentDescription("Increase Desk depth").performClick(); tick()
        assertEquals(55, app.deskD)
        act("plan-stow")
        tag("desk-plan").assertExists()
    }

    @Test fun deskFitMath() {
        val fp = footprint(Fallback.scene)
        assertEquals(1415.0, fp.widthMm, 1.0)
        assertEquals(300.0, fp.baseDepthMm, 1.0)
        assertEquals(685.0, fp.workDepthMm, 1.0)
        assertEquals(Fit.Fits, fitOf(fp, 160, 80))
        assertEquals(Fit.StowOnly, fitOf(fp, 150, 60))
        assertEquals(Fit.No, fitOf(fp, 120, 80))
        assertEquals(Fit.No, fitOf(fp, 160, 25))
        val real = footprint(Repo.scene(ctx))
        assertTrue(real.widthMm in 1300.0..1600.0)
        assertTrue(real.workDepthMm > real.baseDepthMm + 100)
    }

    // ---------- navigation ----------
    @Test fun backNavigationAcrossTabs() = show {
        act("tab-files"); assertEquals("files", app.nav.top)
        scrollTo("files", "dock"); act("group-dock"); assertEquals("group/dock", app.nav.top)
        tag("tab-files").assertIsSelected()
        back(); assertEquals("files", app.nav.top)
        back(); assertEquals("explore", app.nav.top)
        act("tab-specs"); act("tab-studio"); assertEquals("studio", app.nav.top)
        back(); assertEquals("explore", app.nav.top)
        scrollTo("explore", "s-charge"); act("story-charge"); assertEquals("story/charge", app.nav.top)
        rule.onNodeWithContentDescription("Back").performClick(); tick()
        assertEquals("explore", app.nav.top)
        assertFalse(app.nav.canBack)
    }

    // ---------- layouts ----------
    @Config(qualifiers = "w891dp-h411dp-xxhdpi")
    @Test fun landscapePhoneStudioUsesASidePanel() = show("studio") {
        tag("panel-view").assertExists()
        tag("controls").assertDoesNotExist()
        post("""{"type":"pick","group":"display"}""")
        tag("part-sheet").assertExists()
        back(); tag("part-sheet").assertDoesNotExist()
    }

    @Config(qualifiers = "w1280dp-h800dp-mdpi")
    @Test fun tabletRendersEveryTab() = show {
        assertTrue(shows("NIGHT ARRAY"))
        listOf("studio", "files", "specs").forEach { act("tab-$it"); assertEquals(it, app.nav.top) }
        act("specs-fit"); tag("desk-plan").assertExists()
        rule.runOnUiThread { app.nav.go("story/dual") }; tick(1500)
        scrollTo("story", "diagram"); tag("dual-diagram").assertExists()
    }

    // ---------- data ----------
    @Test fun sceneLoadsAndParsesDefensively() {
        val s = Repo.scene(ctx)
        val bundled = AssetIndex.exists(ctx, "model/scene.json")
        assertEquals(bundled, s.fromFile)
        assertEquals(GROUP_ORDER.filter { id -> s.groups.any { it.id == id } }, s.groups.map { it.id })
        assertTrue(s.groups.size >= 9)
        assertTrue(s.parts.isNotEmpty())
        assertEquals(2, s.screen.panels)
        assertEquals(5120, s.screen.canvasW)
        assertTrue(s.groups.all { g -> s.partsOf(g.id).isNotEmpty() })
        assertEquals(listOf("align", "lower", "release"), dockUiSteps(s).map { it.id })
        // partial / hostile input never throws and falls back sensibly
        val p = SceneParser.parse("""{"groups":[{"id":"base","bbox_mm":"oops"},{"nope":1},5],"parts":[{"id":"base_shell","group":"base","mass_g":"x"}],
            "screen":{"panels":"two","resolution_each":[2560],"seam_mm":-3},"dock_sequence":[],"files":[{"path":"files/parts/base.step"}],"bounds":{"min":[0]}}""")
        assertEquals("base", p.groups.single().id)
        assertEquals(2, p.screen.panels); assertEquals(listOf(2560, 1440), p.screen.resEach); assertEquals(14.0, p.screen.seamMm, 0.0)
        assertEquals("STEP", p.files.single().format)
        assertEquals(4, p.dockSteps.size)
        val empty = SceneParser.parse("{}")
        assertEquals(Fallback.scene.groups.size, empty.groups.size)
        assertEquals(mimeOf("STEP"), "model/step"); assertEquals(mimeOf("STL"), "model/stl"); assertEquals(mimeOf("GLB"), "model/gltf-binary")
        assertEquals(mimeOf("SVG"), "image/svg+xml"); assertEquals(mimeOf("DXF"), "image/vnd.dxf")
    }

    /** A snapshot of the real cad/export/model/scene.json (build.py output), so the parser is pinned to the real format. */
    @Test fun parsesTheRealCadExportFormat() {
        val text = javaClass.classLoader!!.getResourceAsStream("scene-fixture.json")!!.bufferedReader().use { it.readText() }
        val s = SceneParser.parse(text)
        assertTrue(s.fromFile)
        assertEquals(GROUP_ORDER, s.groups.map { it.id })
        assertTrue(s.parts.size >= 40)
        assertTrue("every part belongs to a known group", s.parts.all { it.group in GROUP_ORDER })
        assertTrue("groups carry mass and size", s.groups.all { it.massG > 0 && it.bboxMm.size == 3 && it.bboxMm.all { v -> v > 0 } })
        assertTrue(s.groups.all { g -> g.parts.isNotEmpty() && g.parts.all { pid -> s.parts.any { it.id == pid } } })
        // files: assembly STEP + GLB, then STEP/STL/SVG/DXF per group, all with real sizes
        assertEquals(setOf("STEP", "GLB"), s.filesOf(null).map { it.format }.toSet())
        GROUP_ORDER.forEach { g -> assertEquals(g, setOf("STEP", "STL", "SVG", "DXF"), s.filesOf(g).map { it.format }.toSet()) }
        assertTrue(s.files.all { it.bytes > 0 })
        assertEquals(GROUP_ORDER.toSet(), s.drawings.keys)
        // the dual display
        assertEquals(5120, s.screen.canvasW); assertEquals(1440, s.screen.canvasH)
        assertEquals(14.0, s.screen.seamMm, 0.0); assertEquals(10.0, s.screen.toeInDeg, 0.0)
        assertTrue(s.displayWidthMm in 1150.0..1260.0)
        // params drive the stories, the spec sheet and Desk fit
        assertEquals(20.0, s.span("dock.slot.x")!!, 0.0)
        assertEquals(listOf(376.0, 136.0), s.nums("base.kb_pocket.size"))
        assertTrue(storySpecs(story("dock")!!, s).any { it.value.startsWith("20 × 224 mm") })
        assertTrue(storySpecs(story("work-stow")!!, s).any { it.value == "14 mm below the deck" })
        val fp = footprint(s)
        assertEquals(150.0, fp.workGapMm, 0.5); assertEquals(1415.0, fp.widthMm, 1.0); assertEquals(685.0, fp.workDepthMm, 1.0)
        assertTrue(s.stationMassG in 15_000.0..60_000.0)
        assertEquals("Neutral Titanium", s.materialLabel("titanium"))
        assertTrue(s.materialSpecs["titanium"].orEmpty().contains("titanium", ignoreCase = true))
        assertEquals(listOf("align", "lower", "release", "lift"), s.dockSteps.map { it.step })
        assertTrue(s.dims.any { it.id == "seam" } && s.dims.any { it.pose == "work" })
        specSheet(s).flatMap { it.rows }.forEach { assertFalse(it.label, it.value.contains("null") || it.value.contains("NaN")) }
        STORIES.forEach { st -> storySpecs(st, s).forEach { assertFalse(it.label, it.value.contains("null") || it.value.contains("NaN")) } }
    }

    @Test fun viewerHostQueuesUntilLoadedAndRestoresAfterNight() {
        val host = ViewerHost(ctx)
        val out = mutableListOf<String>()
        host.evaluator = { out += it }
        host.setMode("stow"); host.setFinish("graphite"); host.camera("dock"); host.dock("play"); idle()
        assertTrue(out.isEmpty())
        assertEquals(3, host.pending) // the two state changes merge into one setState
        host.onPageLoaded()
        assertEquals(listOf("""NA.setState({"mode":"stow","finish":"graphite"})""", """NA.camera("dock")""", """NA.dock("play")"""), out)
        val url = host.viewerUrl()
        val st = JSONObject(URLDecoder.decode(url.substringAfter("state="), "UTF-8"))
        listOf("mode", "style", "finish", "amber", "explode", "section", "dims", "autorotate", "isolate", "selected", "quality", "cinematic").forEach { assertTrue(it, st.has(it)) }
        assertEquals("stow", st.getString("mode"))
        host.setExplode(.6f); host.setStyle("cad")
        host.enterNight(); assertTrue(host.state.cinematic); assertEquals("studio", host.state.style)
        host.exitNight(); assertFalse(host.state.cinematic); assertEquals("cad", host.state.style); assertEquals(.6f, host.state.explode, .001f)
        host.handle("""{"type":"dockStep","step":"done"}"""); assertFalse(host.dockPlaying)
        host.destroy()
        host.handle("""{"type":"ready"}""") // ignored after destroy
        assertNotEquals(LiveStatus.Ready, host.status)
    }

    @Test fun stillsMatchTheViewerState() {
        val st = ViewerState()
        assertEquals("hero-work.jpg", stillsFor(st).first())
        st.style = "xray"; assertEquals("xray.jpg", stillsFor(st).first())
        st.isolate = "dock"; assertEquals("part-dock.jpg", stillsFor(st).first())
        st.isolate = null; st.style = "studio"
        assertEquals("trays.jpg", stillsFor(st, camera = "trays").first())
        assertEquals("dock-lower.jpg", stillsFor(st, dockStep = "lower").first())
        assertEquals("display", stillFocus("renders/display.jpg")); assertEquals("release", stillDockStep("dock-release.jpg"))
    }
}
