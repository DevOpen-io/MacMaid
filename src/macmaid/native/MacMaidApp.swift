import Cocoa
import Darwin
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
    var launchOverlay: NSView?
    var serverProcess: Process?
    var targetURL = URL(string: "http://127.0.0.1:8123")!
    var isConnected = false
    var retryCount = 0
    let maxRetries = 300 // 300 * 0.04s = 12 seconds max

    func applicationDidFinishLaunching(_ notification: Notification) {
        let app = NSApplication.shared
        app.setActivationPolicy(.regular)
        setupMenu()
        setupWindow()
        guard configureBackendPort() else { return }
        launchBackend()
        probeBackend()
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
        // Use the visible frame so the initial window stays clear of the Dock and menu bar.
        let preferredSize = NSSize(width: 1240, height: 800)
        let screenRect = NSScreen.main?.visibleFrame
            ?? NSRect(origin: .zero, size: preferredSize)
        let width = min(preferredSize.width, screenRect.width * 0.92)
        let height = min(preferredSize.height, screenRect.height * 0.90)
        let frame = NSRect(
            x: screenRect.midX - (width / 2),
            y: screenRect.midY - (height / 2),
            width: width,
            height: height
        ).integral

        window = NSWindow(
            contentRect: frame,
            styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        window.title = "MacMaid Pro"
        window.titlebarAppearsTransparent = true
        window.titleVisibility = .hidden
        window.titlebarSeparatorStyle = .none
        window.toolbarStyle = .unifiedCompact
        window.isMovableByWindowBackground = false
        // Preserve the table-oriented minimum while adapting to smaller displays.
        window.minSize = NSSize(width: min(960, width), height: min(640, height))
        window.isReleasedWhenClosed = false
        window.delegate = self
        // Follow the system appearance; WebUI themes remain user-selectable inside the app.
        window.appearance = nil
        window.isOpaque = false
        window.backgroundColor = .clear

        let contentView = window.contentView!
        let materialView = NSVisualEffectView(frame: contentView.bounds)
        materialView.autoresizingMask = [.width, .height]
        materialView.blendingMode = .behindWindow
        materialView.material = .underWindowBackground
        materialView.state = .followsWindowActiveState
        contentView.addSubview(materialView)

        let config = WKWebViewConfiguration()
        config.preferences.setValue(true, forKey: "developerExtrasEnabled")
        webView = MacMaidWebView(frame: contentView.bounds, configuration: config)
        webView.autoresizingMask = [.width, .height]
        webView.navigationDelegate = self
        webView.setValue(false, forKey: "drawsBackground")
        webView.customUserAgent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) MacMaidApp/1.0"
        contentView.addSubview(webView)

        let overlay = NSView(frame: contentView.bounds)
        overlay.autoresizingMask = [.width, .height]
        overlay.wantsLayer = true
        overlay.layer?.backgroundColor = NSColor.windowBackgroundColor.cgColor
        let loadingLabel = NSTextField(labelWithString: "MacMaid")
        loadingLabel.font = NSFont.systemFont(ofSize: 25, weight: .semibold)
        loadingLabel.textColor = .labelColor
        loadingLabel.alignment = .center

        let launchStack = NSStackView()
        launchStack.orientation = .vertical
        launchStack.alignment = .centerX
        launchStack.spacing = 14
        if let logoURL = Bundle.main.resourceURL?.appendingPathComponent("MacMaid-Logo.png"),
           let logo = NSImage(contentsOf: logoURL) {
            let logoView = NSImageView(image: logo)
            logoView.imageScaling = .scaleProportionallyUpOrDown
            logoView.translatesAutoresizingMaskIntoConstraints = false
            NSLayoutConstraint.activate([
                logoView.widthAnchor.constraint(equalToConstant: 92),
                logoView.heightAnchor.constraint(equalToConstant: 92),
            ])
            launchStack.addArrangedSubview(logoView)
        }
        launchStack.addArrangedSubview(loadingLabel)
        launchStack.translatesAutoresizingMaskIntoConstraints = false
        overlay.addSubview(launchStack)
        NSLayoutConstraint.activate([
            launchStack.centerXAnchor.constraint(equalTo: overlay.centerXAnchor),
            launchStack.centerYAnchor.constraint(equalTo: overlay.centerYAnchor),
        ])
        contentView.addSubview(overlay)
        launchOverlay = overlay

        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApplication.shared.activate(ignoringOtherApps: true)
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(systemColorsDidChange(_:)),
            name: NSColor.systemColorsDidChangeNotification,
            object: nil
        )
    }

    @objc func systemColorsDidChange(_ notification: Notification) {
        updateWebAccentColor()
    }

    func updateWebAccentColor() {
        guard isConnected,
              let accent = NSColor.controlAccentColor.usingColorSpace(.sRGB) else { return }
        let red = Int(round(accent.redComponent * 255))
        let green = Int(round(accent.greenComponent * 255))
        let blue = Int(round(accent.blueComponent * 255))
        let cssColor = String(format: "#%02X%02X%02X", red, green, blue)
        webView.evaluateJavaScript(
            "document.documentElement.style.setProperty('--system-accent', '\(cssColor)')"
        )
    }

    func configureBackendPort() -> Bool {
        let socketFD = socket(AF_INET, SOCK_STREAM, 0)
        guard socketFD >= 0 else { return false }
        defer { close(socketFD) }

        var address = sockaddr_in()
        address.sin_family = sa_family_t(AF_INET)
        address.sin_addr.s_addr = inet_addr("127.0.0.1")
        address.sin_port = 0
        let bound = withUnsafePointer(to: &address) { pointer in
            pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                Darwin.bind(socketFD, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
            }
        }
        guard bound == 0 else { return false }

        var assigned = sockaddr_in()
        var length = socklen_t(MemoryLayout<sockaddr_in>.size)
        let received = withUnsafeMutablePointer(to: &assigned) { pointer in
            pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                Darwin.getsockname(socketFD, $0, &length)
            }
        }
        guard received == 0 else { return false }
        let port = UInt16(bigEndian: assigned.sin_port)
        targetURL = URL(string: "http://127.0.0.1:\(port)")!
        return true
    }

    func launchBackend() {
        let port = targetURL.port!
        let exeURL = URL(fileURLWithPath: CommandLine.arguments[0])
        let bundleDir = exeURL.deletingLastPathComponent()
        let binPath = bundleDir.appendingPathComponent("macmaid-bin").path

        let process = Process()
        if FileManager.default.isExecutableFile(atPath: binPath) {
            process.executableURL = URL(fileURLWithPath: binPath)
            process.arguments = ["ui", "--no-open", "--port", "\(port)"]
        } else {
            let home = FileManager.default.homeDirectoryForCurrentUser.path
            let localBin = "\(home)/.local/bin/macmaid"
            let brewBin = "/opt/homebrew/bin/macmaid"
            let usrLocalBin = "/usr/local/bin/macmaid"

            if FileManager.default.isExecutableFile(atPath: localBin) {
                process.executableURL = URL(fileURLWithPath: localBin)
                process.arguments = ["ui", "--no-open", "--port", "\(port)"]
            } else if FileManager.default.isExecutableFile(atPath: brewBin) {
                process.executableURL = URL(fileURLWithPath: brewBin)
                process.arguments = ["ui", "--no-open", "--port", "\(port)"]
            } else if FileManager.default.isExecutableFile(atPath: usrLocalBin) {
                process.executableURL = URL(fileURLWithPath: usrLocalBin)
                process.arguments = ["ui", "--no-open", "--port", "\(port)"]
            } else {
                process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
                process.arguments = ["macmaid", "ui", "--no-open", "--port", "\(port)"]
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

    func probeBackend() {
        guard !isConnected && retryCount < maxRetries else { return }
        retryCount += 1
        var request = URLRequest(url: targetURL, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 0.25)
        request.httpMethod = "HEAD"
        URLSession.shared.dataTask(with: request) { [weak self] _, response, _ in
            guard let self else { return }
            if let http = response as? HTTPURLResponse, http.statusCode == 200 {
                DispatchQueue.main.async { self.connectToWeb() }
            } else {
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.04) { self.probeBackend() }
            }
        }.resume()
    }

    func connectToWeb() {
        let request = URLRequest(url: targetURL, cachePolicy: .useProtocolCachePolicy, timeoutInterval: 5)
        webView.load(request)
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        isConnected = true
        updateWebAccentColor()
        NSAnimationContext.runAnimationGroup { context in
            context.duration = 0.12
            launchOverlay?.animator().alphaValue = 0
        } completionHandler: { [weak self] in
            self?.launchOverlay?.removeFromSuperview()
            self?.launchOverlay = nil
        }
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        if !isConnected {
            probeBackend()
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
        NotificationCenter.default.removeObserver(self)
        if let proc = serverProcess, proc.isRunning {
            proc.terminate()
        }
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
