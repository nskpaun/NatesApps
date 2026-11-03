package com.natesapps.chaintheory

import android.content.Context
import android.content.SharedPreferences
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

/** A run of inline text: text, style flags (b,i,c), optional link target. */
data class Span(val text: String, val style: String, val link: String)

sealed class Block {
    data class Text(val kind: String, val spans: List<Span>, val number: Int? = null, val id: String? = null) : Block()
    data class Container(val kind: String, val variant: String, val blocks: List<Block>) : Block()
    data class Table(val rows: List<List<Pair<Boolean, List<Span>>>>) : Block()
}

data class Term(val term: String, val def: String)
data class Part(val title: String, val desc: String, val page: Int?, val counts: List<Int>?)
data class Question(val q: String, val options: List<String>, val answer: Int, val explain: String)
data class Deck(val name: String, val level: String, val desc: String, val questions: List<Question>)
data class OutlineItem(val title: String, val depth: Int, val page: Int) // page 1-based
data class Doc(val key: String, val title: String, val short: String, val pages: List<String>, val outline: List<OutlineItem>) {
    val lower: List<String> by lazy { pages.map { it.lowercase() } }
    fun sectionFor(page: Int): OutlineItem? = outline.lastOrNull { it.page <= page && it.depth <= 1 }
}

class Content(
    val articles: Map<String, List<Block>>,
    val glossary: List<Term>,
    val parts: List<Part>,
    val decks: List<Deck>,
)

private fun spans(arr: JSONArray): List<Span> = (0 until arr.length()).map {
    val s = arr.getJSONArray(it); Span(s.getString(0), s.getString(1), s.getString(2))
}

private fun blocks(arr: JSONArray): List<Block> = (0 until arr.length()).mapNotNull { i ->
    val o = arr.getJSONObject(i)
    when (val k = o.getString("k")) {
        "callout", "card" -> Block.Container(k, o.optString("kind", ""), blocks(o.getJSONArray("blocks")))
        "table" -> {
            val rows = o.getJSONArray("rows")
            Block.Table((0 until rows.length()).map { r ->
                val row = rows.getJSONArray(r)
                (0 until row.length()).map { c -> val cell = row.getJSONObject(c); cell.getBoolean("h") to spans(cell.getJSONArray("s")) }
            })
        }
        else -> Block.Text(k, spans(o.getJSONArray("s")), if (o.has("n") && !o.isNull("n")) o.getInt("n") else null,
            if (o.has("id") && !o.isNull("id")) o.getString("id") else null)
    }
}

object Repo {
    @Volatile private var content: Content? = null
    private val docs = HashMap<String, Doc>()
    private val lock = Mutex()

    fun content(ctx: Context): Content = content ?: synchronized(this) {
        content ?: run {
            val o = JSONObject(ctx.assets.open("content.json").bufferedReader().readText())
            val arts = listOf("l1", "l2", "primer", "l3", "l4", "calc").associateWith { blocks(o.getJSONArray(it)) }
            val gl = o.getJSONArray("glossary").let { a -> (0 until a.length()).map { val t = a.getJSONObject(it); Term(t.getString("t"), t.getString("d")) } }
            val parts = o.getJSONArray("parts").let { a ->
                (0 until a.length()).map {
                    val p = a.getJSONArray(it)
                    Part(p.getString(0), p.getString(1), if (p.isNull(2)) null else p.getInt(2),
                        if (p.isNull(3)) null else p.getJSONArray(3).let { c -> (0 until c.length()).map { c.getInt(it) } })
                }
            }
            val decks = o.getJSONArray("decks").let { a ->
                (0 until a.length()).map {
                    val d = a.getJSONObject(it); val qs = d.getJSONArray("qs")
                    Deck(d.getString("name"), d.getString("lv"), d.getString("desc"), (0 until qs.length()).map { q ->
                        val x = qs.getJSONArray(q); val op = x.getJSONArray(1)
                        Question(x.getString(0), (0 until op.length()).map { op.getString(it) }, x.getInt(2), x.getString(3))
                    })
                }
            }
            Content(arts, gl, parts, decks).also { content = it }
        }
    }

    suspend fun doc(ctx: Context, key: String): Doc = lock.withLock {
        docs[key] ?: withContext(Dispatchers.IO) {
            val o = JSONObject(ctx.assets.open("$key.json").bufferedReader().readText())
            val p = o.getJSONArray("pages"); val ol = o.getJSONArray("outline")
            Doc(key, o.getString("title"), o.getString("short"),
                (0 until p.length()).map { p.getString(it) },
                (0 until ol.length()).map { val x = ol.getJSONObject(it); OutlineItem(x.getString("t"), x.getInt("d"), x.getInt("p") + 1) })
        }.also { docs[key] = it }
    }
}

val DOC_KEYS = listOf("talk", "alpha", "comp")
val DOC_SHORT = mapOf("talk" to "Talk", "alpha" to "Letter", "comp" to "Compendium")

data class ChainLink(val id: String, val label: String, val target: String)
val LINKS = listOf(
    ChainLink("l1", "Read Level 1", "#l1"), ChainLink("l2", "Read Level 2", "#l2"), ChainLink("l3", "Read Level 3", "#l3"),
    ChainLink("l4", "Explore the compendium map", "#l4"), ChainLink("calc", "Break the formula in the α calculator", "#calc"),
    ChainLink("q0", "Clear the Basics quiz", "#play"), ChainLink("q1", "Clear the Big Picture quiz", "#play"), ChainLink("q2", "Clear the Math quiz", "#play"),
    ChainLink("flash", "Know 10 flashcards", "#flash"), ChainLink("letter", "Read 5 pages of the alpha Letter", "#read/alpha/1"),
    ChainLink("comp", "Read 25 compendium pages", "#read/comp/2"), ChainLink("search", "Search the sources", "#search"),
)

data class Bookmark(val doc: String, val page: Int, val label: String)

/** Persistent, observable app state. */
class Store(ctx: Context) {
    private val sp: SharedPreferences = ctx.getSharedPreferences("ct", Context.MODE_PRIVATE)
    val earned = mutableStateMapOf<String, Long>()
    val best = mutableStateMapOf<Int, Int>()
    val bookmarks = mutableStateOf<List<Bookmark>>(emptyList())
    val lastDoc = mutableStateOf(sp.getString("lastDoc", null))
    val lastPage = mutableStateOf(sp.getInt("lastPage", 1))
    val fontScale = mutableStateOf(sp.getFloat("fontScale", 1f))
    val flashKnown = mutableStateOf(sp.getInt("flashKnown", 0))
    val toast = mutableStateOf<String?>(null)
    val confetti = mutableStateOf(0)
    var lastPopped = mutableStateOf<String?>(null)
    var lastQuery = ""

    init {
        JSONObject(sp.getString("earned", "{}")!!).let { o -> o.keys().forEach { earned[it] = o.getLong(it) } }
        JSONObject(sp.getString("best", "{}")!!).let { o -> o.keys().forEach { best[it.toInt()] = o.getInt(it) } }
        bookmarks.value = JSONArray(sp.getString("bm", "[]")!!).let { a ->
            (0 until a.length()).map { val b = a.getJSONObject(it); Bookmark(b.getString("doc"), b.getInt("page"), b.optString("label")) }
        }
    }

    fun earn(id: String) {
        if (LINKS.none { it.id == id } || earned.containsKey(id)) return
        earned[id] = System.currentTimeMillis()
        sp.edit().putString("earned", JSONObject(earned.toMap() as Map<*, *>).toString()).apply()
        val n = earned.size
        val label = LINKS.firstOrNull { it.id == id }?.label ?: id
        lastPopped.value = id
        if (n == LINKS.size) {
            toast.value = "🏆 Full chain! You are now dangerously qualified to argue about α on a plane."
            confetti.value += 3
        } else {
            toast.value = "⛓ Link forged: $label · $n/${LINKS.size}"
            confetti.value += 1
        }
    }

    fun setBest(deck: Int, score: Int) {
        if ((best[deck] ?: -1) < score) {
            best[deck] = score
            sp.edit().putString("best", JSONObject(best.mapKeys { it.key.toString() } as Map<*, *>).toString()).apply()
        }
    }

    fun read(doc: String, page: Int) {
        lastDoc.value = doc; lastPage.value = page
        val key = "seen_$doc"
        val set = sp.getStringSet(key, emptySet())!!.toMutableSet()
        if (set.add(page.toString())) sp.edit().putStringSet(key, set).apply()
        sp.edit().putString("lastDoc", doc).putInt("lastPage", page).putInt("pos_$doc", page).apply()
        if (doc == "alpha" && set.size >= 5) earn("letter")
        if (doc == "comp" && set.size >= 25) earn("comp")
    }

    fun pos(doc: String) = sp.getInt("pos_$doc", 1)

    fun toggleBookmark(doc: String, page: Int, label: String) {
        val cur = bookmarks.value
        bookmarks.value = if (cur.any { it.doc == doc && it.page == page }) cur.filterNot { it.doc == doc && it.page == page }
        else cur + Bookmark(doc, page, label)
        val a = JSONArray(); bookmarks.value.forEach { a.put(JSONObject().put("doc", it.doc).put("page", it.page).put("label", it.label)) }
        sp.edit().putString("bm", a.toString()).apply()
    }

    fun setFontScale(f: Float) { fontScale.value = f; sp.edit().putFloat("fontScale", f).apply() }
    fun knowCard() { flashKnown.value += 1; sp.edit().putInt("flashKnown", flashKnown.value).apply(); if (flashKnown.value >= 10) earn("flash") }
}
