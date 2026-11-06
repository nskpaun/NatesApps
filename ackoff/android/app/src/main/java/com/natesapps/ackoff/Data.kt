package com.natesapps.ackoff

import android.content.Context
import android.content.SharedPreferences
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/** A run of inline text: text, style flags (b,i,c), optional link target. */
data class Span(val text: String, val style: String, val link: String)

sealed class Block {
    data class Text(val kind: String, val spans: List<Span>, val number: Int? = null, val id: String? = null) : Block()
    data class Container(val kind: String, val variant: String, val blocks: List<Block>) : Block()
    data class Table(val rows: List<List<Pair<Boolean, List<Span>>>>) : Block()
}

data class Term(val term: String, val def: String)
data class Question(val q: String, val options: List<String>, val answer: Int, val explain: String)
data class Deck(val name: String, val level: String, val desc: String, val questions: List<Question>)
data class SortCard(val text: String, val systems: Boolean)

class Content(
    val articles: Map<String, List<Block>>,
    val glossary: List<Term>,
    val decks: List<Deck>,
    val sort: List<SortCard>,
)

val ARTICLES = listOf("l1", "talk", "lead", "tools", "apply", "library")

private fun spans(arr: JSONArray): List<Span> = (0 until arr.length()).map {
    val s = arr.getJSONArray(it); Span(s.getString(0), s.getString(1), s.getString(2))
}

private fun blocks(arr: JSONArray): List<Block> = (0 until arr.length()).map { i ->
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
    fun content(ctx: Context): Content = content ?: synchronized(this) {
        content ?: run {
            val o = JSONObject(ctx.assets.open("content.json").bufferedReader().readText())
            val arts = ARTICLES.associateWith { blocks(o.getJSONArray(it)) }
            val gl = o.getJSONArray("glossary").let { a -> (0 until a.length()).map { val t = a.getJSONObject(it); Term(t.getString("t"), t.getString("d")) } }
            val decks = o.getJSONArray("decks").let { a ->
                (0 until a.length()).map {
                    val d = a.getJSONObject(it); val qs = d.getJSONArray("qs")
                    Deck(d.getString("name"), d.getString("lv"), d.getString("desc"), (0 until qs.length()).map { q ->
                        val x = qs.getJSONArray(q); val op = x.getJSONArray(1)
                        Question(x.getString(0), (0 until op.length()).map { op.getString(it) }, x.getInt(2), x.getString(3))
                    })
                }
            }
            val sort = o.getJSONArray("sort").let { a -> (0 until a.length()).map { val x = a.getJSONArray(it); SortCard(x.getString(0), x.getInt(1) == 1) } }
            Content(arts, gl, decks, sort).also { content = it }
        }
    }
}

data class ChainLink(val id: String, val label: String, val target: String)
val LINKS = listOf(
    ChainLink("l1", "Read Ackoff in three minutes", "#l1"), ChainLink("talk", "Study the 1993 talk", "#talk"),
    ChainLink("lead", "Read Leadership as aesthetics", "#lead"), ChainLink("tools", "Explore the toolkit", "#tools"),
    ChainLink("apply", "Read Use it on Monday", "#apply"),
    ChainLink("q0", "Clear the Basics quiz", "#play"), ChainLink("q1", "Clear the Talk quiz", "#play"),
    ChainLink("q2", "Clear the Leadership quiz", "#play"), ChainLink("q3", "Clear the Toolkit quiz", "#play"),
    ChainLink("sort", "Score 80% in Machine or Systems?", "#sort"), ChainLink("flash", "Know 10 flashcards", "#flash"),
    ChainLink("search", "Search the guide", "#search"),
)

/** Persistent, observable app state. */
class Store(ctx: Context) {
    private val sp: SharedPreferences = ctx.getSharedPreferences("ackoff", Context.MODE_PRIVATE)
    val pdfDir = File(ctx.filesDir, "pdfs").apply { mkdirs() }
    val earned = mutableStateMapOf<String, Long>()
    val best = mutableStateMapOf<Int, Int>()
    val fontScale = mutableStateOf(sp.getFloat("fontScale", 1f))
    val flashKnown = mutableStateOf(sp.getInt("flashKnown", 0))
    val sortBest = mutableStateOf(sp.getInt("sortBest", 0))
    val pdfs = mutableStateOf(listPdfs())
    val toast = mutableStateOf<String?>(null)
    val confetti = mutableStateOf(0)
    var lastQuery = ""

    init {
        JSONObject(sp.getString("earned", "{}")!!).let { o -> o.keys().forEach { earned[it] = o.getLong(it) } }
        JSONObject(sp.getString("best", "{}")!!).let { o -> o.keys().forEach { best[it.toInt()] = o.getInt(it) } }
    }

    fun listPdfs(): List<File> = pdfDir.listFiles { f -> f.name.endsWith(".pdf") }?.sortedBy { it.name.lowercase() } ?: emptyList()
    fun refreshPdfs() { pdfs.value = listPdfs() }

    fun earn(id: String) {
        if (LINKS.none { it.id == id } || earned.containsKey(id)) return
        earned[id] = System.currentTimeMillis()
        sp.edit().putString("earned", JSONObject(earned.toMap() as Map<*, *>).toString()).apply()
        val n = earned.size
        val label = LINKS.first { it.id == id }.label
        if (n == LINKS.size) {
            toast.value = "🏆 Whole system complete! Ackoff would call that development, not just growth."
            confetti.value += 3
        } else {
            toast.value = "◉ Part connected: $label · $n/${LINKS.size}"
            confetti.value += 1
        }
    }

    fun setBest(deck: Int, score: Int) {
        if ((best[deck] ?: -1) < score) {
            best[deck] = score
            sp.edit().putString("best", JSONObject(best.mapKeys { it.key.toString() } as Map<*, *>).toString()).apply()
        }
    }

    fun setSortBest(score: Int) { if (score > sortBest.value) { sortBest.value = score; sp.edit().putInt("sortBest", score).apply() } }
    fun setFontScale(f: Float) { fontScale.value = f; sp.edit().putFloat("fontScale", f).apply() }
    fun knowCard() { flashKnown.value += 1; sp.edit().putInt("flashKnown", flashKnown.value).apply(); if (flashKnown.value >= 10) earn("flash") }
}
