import SwiftUI
import AppKit

struct HealthDoctorView: View {
    @ObservedObject var state = AppState.shared
    @State private var checks: [DiagnosticCheck] = []
    @State private var health: SystemHealthReport?
    @State private var isLoading: Bool = false

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Mac Health & Diagnostics")
                        .font(.title2)
                        .fontWeight(.bold)
                    Text("Evaluates macOS permissions, disk space, and system tools.")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }

                Spacer()

                Button(action: openFullDiskAccessSettings) {
                    Label("System Settings", systemImage: "lock.shield")
                }

                Button(action: loadDiagnostics) {
                    Label(state.t("Refresh"), systemImage: "arrow.clockwise")
                }
                .buttonStyle(.borderedProminent)
            }
            .padding()
            .background(Color(NSColor.windowBackgroundColor))

            Divider()

            if isLoading {
                ProgressView()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List {
                    Section(header: Text("System Diagnostics")) {
                        ForEach(checks) { check in
                            HStack(spacing: 12) {
                                Image(systemName: iconForStatus(check.status))
                                    .foregroundColor(colorForStatus(check.status))
                                    .font(.title3)

                                VStack(alignment: .leading, spacing: 2) {
                                    HStack {
                                        Text(check.title)
                                            .fontWeight(.medium)
                                        Spacer()
                                        Text(check.value)
                                            .font(.callout)
                                            .foregroundColor(.secondary)
                                    }
                                    Text(check.detail)
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                }
                            }
                            .padding(.vertical, 4)
                        }
                    }

                    if let h = health {
                        Section(header: Text("Storage Overview")) {
                            if let d = h.disk {
                                HStack {
                                    Text("Primary Disk Total")
                                    Spacer()
                                    Text(MacMaidBridge.formatBytes(d.totalBytes))
                                        .foregroundColor(.secondary)
                                }
                                HStack {
                                    Text("Available Disk Space")
                                    Spacer()
                                    Text(MacMaidBridge.formatBytes(d.availableBytes))
                                        .foregroundColor(.green)
                                        .fontWeight(.semibold)
                                }
                            }
                        }
                    }
                }
            }
        }
        .onAppear(perform: loadDiagnostics)
    }

    private func iconForStatus(_ status: String) -> String {
        switch status {
        case "ok": return "checkmark.circle.fill"
        case "warning": return "exclamationmark.circle.fill"
        default: return "xmark.circle.fill"
        }
    }

    private func colorForStatus(_ status: String) -> Color {
        switch status {
        case "ok": return .green
        case "warning": return .yellow
        default: return .red
        }
    }

    private func loadDiagnostics() {
        isLoading = true
        DispatchQueue.global(qos: .userInitiated).async {
            let resChecks = MacMaidBridge.shared.runDiagnostics()
            let resHealth = MacMaidBridge.shared.getSystemHealth()
            DispatchQueue.main.async {
                self.checks = resChecks
                self.health = resHealth
                self.isLoading = false
            }
        }
    }

    private func openFullDiskAccessSettings() {
        let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles")!
        NSWorkspace.shared.open(url)
    }
}
