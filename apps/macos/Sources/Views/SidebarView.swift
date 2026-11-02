import SwiftUI

struct SidebarView: View {
    @ObservedObject var state = AppState.shared

    var body: some View {
        List(selection: $state.selectedTab) {
            Section(header: Text(state.t("Clean"))) {
                NavigationLink(value: NavigationTab.clean) {
                    Label(state.t("Clean"), systemImage: NavigationTab.clean.iconName)
                }
                NavigationLink(value: NavigationTab.analyzer) {
                    Label(state.t("Disk Analyzer"), systemImage: NavigationTab.analyzer.iconName)
                }
                NavigationLink(value: NavigationTab.treemap) {
                    Label(state.t("Storage Treemap"), systemImage: NavigationTab.treemap.iconName)
                }
            }

            Section(header: Text(state.t("System & History"))) {
                NavigationLink(value: NavigationTab.apps) {
                    Label(state.t("Uninstall Apps"), systemImage: NavigationTab.apps.iconName)
                }
                NavigationLink(value: NavigationTab.memory) {
                    Label(state.t("Memory Management"), systemImage: NavigationTab.memory.iconName)
                }
                NavigationLink(value: NavigationTab.developer) {
                    Label(state.t("Developer Tools"), systemImage: NavigationTab.developer.iconName)
                }
                NavigationLink(value: NavigationTab.purge) {
                    Label(state.t("Project Purge"), systemImage: NavigationTab.purge.iconName)
                }
            }

            Section(header: Text(state.t("Files & Storage"))) {
                NavigationLink(value: NavigationTab.duplicates) {
                    Label(state.t("Duplicate Finder"), systemImage: NavigationTab.duplicates.iconName)
                }
                NavigationLink(value: NavigationTab.largeFiles) {
                    Label(state.t("Large & Old Files"), systemImage: NavigationTab.largeFiles.iconName)
                }
                NavigationLink(value: NavigationTab.downloads) {
                    Label(state.t("Smart Downloads"), systemImage: NavigationTab.downloads.iconName)
                }
            }

            Section(header: Text(state.t("Settings"))) {
                NavigationLink(value: NavigationTab.health) {
                    Label(state.t("Mac Health"), systemImage: NavigationTab.health.iconName)
                }
                NavigationLink(value: NavigationTab.history) {
                    Label(state.t("History & Restore"), systemImage: NavigationTab.history.iconName)
                }
                NavigationLink(value: NavigationTab.settings) {
                    Label(state.t("Settings"), systemImage: NavigationTab.settings.iconName)
                }
            }
        }
        .listStyle(SidebarListStyle())
        .frame(minWidth: 200, idealWidth: 220)
        .safeAreaInset(edge: .bottom) {
            if let disk = state.diskStats {
                VStack(alignment: .leading, spacing: 4) {
                    Divider()
                    HStack {
                        Image(systemName: "internaldrive")
                            .foregroundColor(.secondary)
                        VStack(alignment: .leading) {
                            Text("Macintosh HD")
                                .font(.caption)
                                .fontWeight(.medium)
                            Text("\(MacMaidBridge.formatBytes(disk.availableBytes)) available")
                                .font(.caption2)
                                .foregroundColor(.secondary)
                        }
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                }
            }
        }
    }
}
