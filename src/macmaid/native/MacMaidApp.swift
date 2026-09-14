import Cocoa
import WebKit

class MacMaidWebView: WKWebView {
    override func mouseDown(with event: NSEvent) {
        let loc = convert(event.locationInWindow, from: nil)
        // In WKWebView (isFlipped == true):
        // loc.y == 0 is the top edge. loc.y <= 28 matches the vertical height of macOS traffic light buttons.
        // loc.x >= 80 leaves room for native traffic lights (close, minimize, zoom).
        if loc.y >= 0 && loc.y <= 28 && loc.x >= 80 {
            if event.clickCount == 2 {
                window?.zoom(nil)
            } else {
                window?.performDrag(with: event)
            }
            return
        }
        super.mouseDown(with: event)
    }
}

class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate {
    var window: NSWindow!
    var webView: MacMaidWebView!
    var serverProcess: Process?
    var targetURL = URL(string: "http://127.0.0.1:8123")!
    var isConnected = false
    var retryCount = 0
    let maxRetries = 80 // 80 * 0.15s = 12 seconds max

    func applicationDidFinishLaunching(_ notification: Notification) {
        let app = NSApplication.shared
        app.setActivationPolicy(.regular)
        setupMenu()
        setupWindow()
        launchBackendIfNeeded()
        connectToWeb()
    }

    func setupMenu() {
        let mainMenu = NSMenu()

        // 1. Application Menu (MacMaid)
        let appMenuItem = NSMenuItem()
        let appMenu = NSMenu(title: "MacMaid")
        appMenu.addItem(withTitle: "About MacMaid", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        appMenu.addItem(NSMenuItem.separator())
        appMenu.addItem(withTitle: "Hide MacMaid", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        let hideOthers = NSMenuItem(title: "Hide Others", action: #selector(NSApplication.hideOtherApplications(_:)), keyEquivalent: "h")
        hideOthers.keyEquivalentModifierMask = [.command, .option]
        appMenu.addItem(hideOthers)
        appMenu.addItem(withTitle: "Show All", action: #selector(NSApplication.unhideAllApplications(_:)), keyEquivalent: "")
        appMenu.addItem(NSMenuItem.separator())
        appMenu.addItem(withTitle: "Quit MacMaid", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appMenuItem.submenu = appMenu
        mainMenu.addItem(appMenuItem)

        // 2. Edit Menu (Copy, Paste, Cut, Select All, Undo, Redo)
        let editMenuItem = NSMenuItem()
        let editMenu = NSMenu(title: "Edit")
        editMenu.addItem(withTitle: "Undo", action: #selector(UndoManager.undo), keyEquivalent: "z")
        let redoItem = NSMenuItem(title: "Redo", action: #selector(UndoManager.redo), keyEquivalent: "z")
        redoItem.keyEquivalentModifierMask = [.command, .shift]
        editMenu.addItem(redoItem)
        editMenu.addItem(NSMenuItem.separator())
        editMenu.addItem(withTitle: "Cut", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        editMenu.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        editMenu.addItem(withTitle: "Paste", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        editMenu.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        editMenuItem.submenu = editMenu
        mainMenu.addItem(editMenuItem)

        // 3. View Menu (Reload, Fullscreen)
        let viewMenuItem = NSMenuItem()
        let viewMenu = NSMenu(title: "View")
        viewMenu.addItem(withTitle: "Reload", action: #selector(reloadPage), keyEquivalent: "r")
        let forceReload = NSMenuItem(title: "Force Reload", action: #selector(forceReloadPage), keyEquivalent: "r")
        forceReload.keyEquivalentModifierMask = [.command, .shift]
        viewMenu.addItem(forceReload)
        viewMenu.addItem(NSMenuItem.separator())
        let fullScreen = NSMenuItem(title: "Toggle Full Screen", action: #selector(NSWindow.toggleFullScreen(_:)), keyEquivalent: "f")
        fullScreen.keyEquivalentModifierMask = [.command, .control]
        viewMenu.addItem(fullScreen)
        viewMenuItem.submenu = viewMenu
        mainMenu.addItem(viewMenuItem)

        // 4. Window Menu
        let windowMenuItem = NSMenuItem()
        let windowMenu = NSMenu(title: "Window")
        windowMenu.addItem(withTitle: "Minimize", action: #selector(NSWindow.miniaturize(_:)), keyEquivalent: "m")
        windowMenu.addItem(withTitle: "Zoom", action: #selector(NSWindow.zoom(_:)), keyEquivalent: "")
        windowMenuItem.submenu = windowMenu
        mainMenu.addItem(windowMenuItem)

        NSApplication.shared.mainMenu = mainMenu
    }

    func setupWindow() {
        let width: CGFloat = 1200
        let height: CGFloat = 800
        let screenRect = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: width, height: height)
        let x = screenRect.midX - (width / 2)
        let y = screenRect.midY - (height / 2)
        let frame = NSRect(x: x, y: y, width: width, height: height)

        window = NSWindow(
            contentRect: frame,
            styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        window.title = "MacMaid Pro"
        window.titlebarAppearsTransparent = true
        window.titleVisibility = .hidden
        window.isMovableByWindowBackground = false
        window.minSize = NSSize(width: 960, height: 640)
        window.isReleasedWhenClosed = false
        window.delegate = self
        window.appearance = NSAppearance(named: .darkAqua)
        window.backgroundColor = NSColor(red: 0.027, green: 0.039, blue: 0.063, alpha: 1.0) // #070a10

        let contentView = window.contentView!

        let config = WKWebViewConfiguration()
        config.preferences.setValue(true, forKey: "developerExtrasEnabled")
        webView = MacMaidWebView(frame: contentView.bounds, configuration: config)
        webView.autoresizingMask = [.width, .height]
        webView.navigationDelegate = self
        webView.setValue(false, forKey: "drawsBackground")
        webView.customUserAgent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) MacMaidApp/1.0"
        contentView.addSubview(webView)

        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApplication.shared.activate(ignoringOtherApps: true)
    }

    func launchBackendIfNeeded() {
        let sock = socket(AF_INET, SOCK_STREAM, 0)
        var addr = sockaddr_in()
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_port = UInt16(8123).bigEndian
        inet_pton(AF_INET, "127.0.0.1", &addr.sin_addr)

        var isListening = false
        withUnsafePointer(to: &addr) { ptr in
            ptr.withMemoryRebound(to: sockaddr.self, capacity: 1) { sa in
                if connect(sock, sa, socklen_t(MemoryLayout<sockaddr_in>.size)) == 0 {
                    isListening = true
                }
            }
        }
        close(sock)

        if isListening {
            return
        }

        let exeURL = URL(fileURLWithPath: CommandLine.arguments[0])
        let bundleDir = exeURL.deletingLastPathComponent()
        let binPath = bundleDir.appendingPathComponent("macmaid-bin").path

        let process = Process()
        if FileManager.default.isExecutableFile(atPath: binPath) {
            process.executableURL = URL(fileURLWithPath: binPath)
            process.arguments = ["ui", "--no-open"]
        } else {
            let home = FileManager.default.homeDirectoryForCurrentUser.path
            let localBin = "\(home)/.local/bin/macmaid"
            let brewBin = "/opt/homebrew/bin/macmaid"
            let usrLocalBin = "/usr/local/bin/macmaid"

            if FileManager.default.isExecutableFile(atPath: localBin) {
                process.executableURL = URL(fileURLWithPath: localBin)
                process.arguments = ["ui", "--no-open"]
            } else if FileManager.default.isExecutableFile(atPath: brewBin) {
                process.executableURL = URL(fileURLWithPath: brewBin)
                process.arguments = ["ui", "--no-open"]
            } else if FileManager.default.isExecutableFile(atPath: usrLocalBin) {
                process.executableURL = URL(fileURLWithPath: usrLocalBin)
                process.arguments = ["ui", "--no-open"]
            } else {
                process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
                process.arguments = ["macmaid", "ui", "--no-open"]
            }
        }

        var env = ProcessInfo.processInfo.environment
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        let currentPath = env["PATH"] ?? ""
        let extraPaths = ["/opt/homebrew/bin", "/usr/local/bin", "\(home)/.local/bin", "/usr/bin", "/bin"]
        env["PATH"] = (extraPaths + [currentPath]).joined(separator: ":")
        process.environment = env

        try? process.run()
        self.serverProcess = process
    }

    func connectToWeb() {
        let request = URLRequest(url: targetURL, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 5)
        webView.load(request)
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        isConnected = true
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        if !isConnected && retryCount < maxRetries {
            retryCount += 1
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) { [weak self] in
                self?.connectToWeb()
            }
        }
    }

    @objc func reloadPage() {
        webView.reload()
    }

    @objc func forceReloadPage() {
        webView.reloadFromOrigin()
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url else {
            decisionHandler(.allow)
            return
        }

        // Open external URLs in the user's default browser
        if let host = url.host, host != "127.0.0.1" && host != "localhost" {
            NSWorkspace.shared.open(url)
            decisionHandler(.cancel)
            return
        }
        decisionHandler(.allow)
    }

    func windowShouldClose(_ sender: NSWindow) -> Bool {
        NSApplication.shared.terminate(nil)
        return true
    }

    func applicationWillTerminate(_ notification: Notification) {
        if let proc = serverProcess, proc.isRunning {
            proc.terminate()
        }
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
