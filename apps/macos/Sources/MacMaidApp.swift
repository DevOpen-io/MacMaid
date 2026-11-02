import SwiftUI
import AppKit

@main
struct MacMaidApp: App {
    @StateObject private var appState = AppState.shared

    var body: some Scene {
        WindowGroup {
            NavigationSplitView {
                SidebarView()
            } detail: {
                switch appState.selectedTab {
                case .clean:
                    SmartCleanView()
                case .analyzer:
                    DiskAnalyzerView()
                case .treemap:
                    StorageTreemapView()
                case .apps:
                    AppUninstallerView()
                case .memory:
                    MemoryManagementView()
                case .developer:
                    DeveloperStorageView()
                case .duplicates:
                    DuplicateFinderView()
                case .largeFiles:
                    LargeFilesView()
                case .downloads:
                    SmartDownloadsView()
                case .purge:
                    ProjectPurgeView()
                case .health:
                    HealthDoctorView()
                case .history:
                    HistoryView()
                case .settings:
                    SettingsView()
                }
            }
            .navigationTitle("MacMaid")
            .frame(minWidth: 960, minHeight: 620)
        }
        .commands {
            SidebarCommands()

            CommandGroup(replacing: .appInfo) {
                Button("About MacMaid") {
                    NSApplication.shared.orderFrontStandardAboutPanel(
                        options: [
                            NSApplication.AboutPanelOptionKey.applicationName: "MacMaid",
                            NSApplication.AboutPanelOptionKey.applicationVersion: "0.15.35",
                            NSApplication.AboutPanelOptionKey(rawValue: "Copyright"): "© 2026 DevOpen.io",
                        ]
                    )
                }
            }

            CommandMenu("View") {
                Button("Smart Clean") {
                    appState.selectedTab = .clean
                }
                .keyboardShortcut("1", modifiers: .command)

                Button("Disk Analyzer") {
                    appState.selectedTab = .analyzer
                }
                .keyboardShortcut("2", modifiers: .command)

                Button("Storage Treemap") {
                    appState.selectedTab = .treemap
                }
                .keyboardShortcut("3", modifiers: .command)

                Button("App Uninstaller") {
                    appState.selectedTab = .apps
                }
                .keyboardShortcut("4", modifiers: .command)

                Button("Memory Management") {
                    appState.selectedTab = .memory
                }
                .keyboardShortcut("5", modifiers: .command)

                Button("Developer Tools") {
                    appState.selectedTab = .developer
                }
                .keyboardShortcut("6", modifiers: .command)

                Divider()

                Button("Refresh") {
                    appState.refreshHealth()
                }
                .keyboardShortcut("r", modifiers: .command)
            }
        }
    }
}
