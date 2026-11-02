import SwiftUI
import Combine

public enum NavigationTab: String, CaseIterable, Identifiable {
    case clean = "Clean"
    case analyzer = "Disk Analyzer"
    case treemap = "Storage Treemap"
    case apps = "Uninstall Apps"
    case memory = "Memory Management"
    case developer = "Developer Tools"
    case duplicates = "Duplicate Finder"
    case largeFiles = "Large & Old Files"
    case downloads = "Smart Downloads"
    case purge = "Project Purge"
    case health = "Mac Health"
    case history = "History & Restore"
    case settings = "Settings"

    public var id: String { rawValue }

    public var iconName: String {
        switch self {
        case .clean: return "sparkles"
        case .analyzer: return "chart.pie.fill"
        case .treemap: return "square.split.2x2.fill"
        case .apps: return "app.badge.xmark"
        case .memory: return "memorychip"
        case .developer: return "hammer.fill"
        case .duplicates: return "doc.on.doc.fill"
        case .largeFiles: return "arrow.up.bin.fill"
        case .downloads: return "arrow.down.circle.fill"
        case .purge: return "trash.slash.fill"
        case .health: return "waveform.path.ecg"
        case .history: return "clock.arrow.circlepath"
        case .settings: return "gearshape.fill"
        }
    }
}

public final class AppState: ObservableObject {
    public static let shared = AppState()

    @Published public var selectedTab: NavigationTab = .clean
    @Published public var language: String = "en"
    @Published public var diskStats: DiskStats?
    @Published public var isScanning: Bool = false
    @Published public var statusMessage: String = ""

    private init() {
        let settings = MacMaidBridge.shared.loadSettings()
        self.language = settings.language
        refreshHealth()
    }

    public func t(_ key: String) -> String {
        MacMaidBridge.shared.translate(key, lang: language)
    }

    public func setLanguage(_ newLang: String) {
        self.language = newLang
        _ = MacMaidBridge.shared.saveSettings(AppSettingsModel(language: newLang))
    }

    public func refreshHealth() {
        DispatchQueue.global(qos: .userInitiated).async {
            let health = MacMaidBridge.shared.getSystemHealth()
            DispatchQueue.main.async {
                self.diskStats = health?.disk
            }
        }
    }
}
