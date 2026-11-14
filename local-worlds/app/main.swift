import Cocoa
import WebKit

// Nate's Worlds: a window around the viewer page. Starts the project's private local server
// (thread/server.py, path stored in Resources/root.txt), shows the page, stops the server on quit.
final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate {
    var window: NSWindow!
    var web: WKWebView!
    var server: Process?
    var port = 0
    var tries = 0

    func freePort() -> Int {
        let s = socket(AF_INET, SOCK_STREAM, 0)
        var a = sockaddr_in(); a.sin_family = sa_family_t(AF_INET); a.sin_addr.s_addr = inet_addr("127.0.0.1"); a.sin_port = 0
        var len = socklen_t(MemoryLayout<sockaddr_in>.size)
        _ = withUnsafeMutablePointer(to: &a) { $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { Darwin.bind(s, $0, len) } }
        _ = withUnsafeMutablePointer(to: &a) { $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { getsockname(s, $0, &len) } }
        close(s)
        return Int(UInt16(bigEndian: a.sin_port))
    }

    func applicationDidFinishLaunching(_ n: Notification) {
        let rootFile = Bundle.main.url(forResource: "root", withExtension: "txt")!
        let root = try! String(contentsOf: rootFile, encoding: .utf8).trimmingCharacters(in: .whitespacesAndNewlines)
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1280, height: 820),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "Nate\u{2019}s Worlds"; window.center()
        web = WKWebView(frame: window.contentView!.bounds); web.autoresizingMask = [.width, .height]; web.navigationDelegate = self; web.uiDelegate = self
        window.contentView!.addSubview(web); window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
        guard FileManager.default.fileExists(atPath: root + "/viewer/index.html"), FileManager.default.fileExists(atPath: root + "/.venv/bin/python") else {
            web.loadHTMLString("<body style='font:16px system-ui;padding:40px'><h2>Project folder not set up</h2><p>Expected the viewer and its Python environment in:</p><p>\(root)</p><p>See the README for build steps.</p></body>", baseURL: nil); return
        }
        port = freePort()
        let p = Process(); p.executableURL = URL(fileURLWithPath: root + "/.venv/bin/python")
        p.arguments = [root + "/server.py", String(port)]; p.currentDirectoryURL = URL(fileURLWithPath: root)
        // tools the pipelines call (colmap, ollama) live in Homebrew, which apps do not get on PATH by default
        var env = ProcessInfo.processInfo.environment
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + (env["PATH"] ?? "/usr/bin:/bin")
        p.environment = env
        p.standardOutput = FileHandle.nullDevice; p.standardError = FileHandle.nullDevice
        try? p.run(); server = p
        load()
    }
    func load() { web.load(URLRequest(url: URL(string: "http://127.0.0.1:\(port)/viewer/index.html")!)) }
    // the server needs a moment to start: retry until the page answers
    func webView(_ w: WKWebView, didFailProvisionalNavigation nav: WKNavigation!, withError e: Error) {
        tries += 1
        if tries < 40 { DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) { self.load() } }
    }
    // lets <input type="file"> open the normal macOS file picker
    func webView(_ w: WKWebView, runOpenPanelWith p: WKOpenPanelParameters, initiatedByFrame f: WKFrameInfo, completionHandler done: @escaping ([URL]?) -> Void) {
        let panel = NSOpenPanel(); panel.allowsMultipleSelection = p.allowsMultipleSelection; panel.canChooseDirectories = false
        panel.beginSheetModal(for: window) { r in done(r == .OK ? panel.urls : nil) }
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ s: NSApplication) -> Bool { true }
    func applicationWillTerminate(_ n: Notification) { server?.terminate() }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
let menu = NSMenu(); let item = NSMenuItem(); menu.addItem(item); let sub = NSMenu()
sub.addItem(NSMenuItem(title: "Quit Nate\u{2019}s Worlds", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")); item.submenu = sub; app.mainMenu = menu
app.run()
