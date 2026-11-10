package com.natesapps.fastchat.models

import java.io.File
import java.io.IOException
import java.net.InetAddress
import java.net.ServerSocket
import java.net.Socket
import java.security.MessageDigest
import kotlin.concurrent.thread
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class ModelStoreTest {

    @get:Rule val folder = TemporaryFolder()

    private lateinit var server: ServerSocket
    private val payload = ByteArray(300_000) { (it * 31 % 251).toByte() }
    private val ranges = mutableListOf<String?>()

    private fun sha(bytes: ByteArray) =
        MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }

    /**
     * A minimal HTTP server: /moved/x redirects to /files/x (like Hugging Face redirecting to its
     * CDN), and /files/x serves [payload], honouring a `Range: bytes=N-` header.
     */
    @Before
    fun startServer() {
        server = ServerSocket(0, 10, InetAddress.getLoopbackAddress())
        thread(isDaemon = true) {
            while (!server.isClosed) {
                val socket = runCatching { server.accept() }.getOrNull() ?: break
                socket.use(::serve)
            }
        }
    }

    private fun serve(socket: Socket) {
        val reader = socket.getInputStream().bufferedReader()
        val path = reader.readLine()?.split(" ")?.getOrNull(1) ?: return
        var range: String? = null
        while (true) {
            val line = reader.readLine()
            if (line.isNullOrEmpty()) break
            if (line.startsWith("Range:", ignoreCase = true)) range = line.substringAfter(":").trim()
        }
        val out = socket.getOutputStream()
        if (path.startsWith("/moved/")) {
            val target = path.replace("/moved/", "/files/")
            out.write("HTTP/1.1 302 Found\r\nLocation: $target\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".toByteArray())
        } else {
            ranges += range
            val from = range?.removePrefix("bytes=")?.removeSuffix("-")?.toInt() ?: 0
            val status = if (range != null) "206 Partial Content" else "200 OK"
            out.write("HTTP/1.1 $status\r\nContent-Length: ${payload.size - from}\r\nConnection: close\r\n\r\n".toByteArray())
            out.write(payload, from, payload.size - from)
        }
        out.flush()
    }

    @After
    fun stopServer() = server.close()

    private fun model(path: String = "llm/model.gguf", sha256: String? = sha(payload)) =
        ModelFile(path, "http://127.0.0.1:${server.localPort}/moved/model.gguf", payload.size.toLong(), sha256)

    @Test
    fun `downloads a missing file through a redirect and verifies it`() = runBlocking {
        val model = model()
        val store = ModelStore(folder.root, listOf(model))
        assertEquals(listOf(model), store.missing())

        val progress = mutableListOf<ModelStore.Progress>()
        store.download { progress += it }

        assertTrue(store.missing().isEmpty())
        assertArrayEquals(payload, store.file(model).readBytes())
        assertEquals(payload.size.toLong(), progress.last().doneBytes)
        assertFalse(File(folder.root, "llm/model.gguf.part").exists())
    }

    @Test
    fun `resumes from the bytes already saved`() = runBlocking {
        val model = model()
        val store = ModelStore(folder.root, listOf(model))
        File(folder.root, "llm").mkdirs()
        File(folder.root, "llm/model.gguf.part").writeBytes(payload.copyOfRange(0, 100_000))
        assertEquals(100_000L, store.presentBytes())

        store.download { }

        assertEquals(listOf<String?>("bytes=100000-"), ranges)
        assertArrayEquals(payload, store.file(model).readBytes())
    }

    @Test
    fun `a file that is already complete is not downloaded again`() = runBlocking {
        val model = model()
        val store = ModelStore(folder.root, listOf(model))
        store.file(model).apply { parentFile!!.mkdirs() }.writeBytes(payload)

        store.download { }

        assertTrue(ranges.isEmpty())
    }

    @Test
    fun `a corrupted download is rejected and thrown away`() = runBlocking {
        val model = model(sha256 = "00".repeat(32))
        val store = ModelStore(folder.root, listOf(model))
        try {
            store.download { }
            fail("expected the checksum to fail")
        } catch (e: IOException) {
            assertTrue(e.message!!.contains("corrupted"))
        }
        assertEquals(listOf(model), store.missing())
        assertEquals(0L, store.presentBytes())
    }

    @Test
    fun `the catalogue adds up to about three and a half gigabytes with unique paths`() {
        assertEquals(Models.ALL.size, Models.ALL.map { it.path }.toSet().size)
        assertTrue(Models.ALL.sumOf { it.bytes } in 3_300_000_000L..3_500_000_000L)
        assertTrue(Models.ALL.all { it.url.startsWith("https://") })
    }
}
