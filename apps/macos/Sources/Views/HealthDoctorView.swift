import SwiftUI
import AppKit

struct HealthDoctorView: View {
    @ObservedObject var state = AppState.shared
    @State private var checks: [DiagnosticCheck] = []
    @State private var health: SystemHealthReport?
    @State private var snapshots: [SnapshotInfoModel] = []
    @State private var thinTargetGB: UInt64 = 10
    @State private var stagedPlan: StagedPlanModel?
    @State private var showConfirmSheet: Bool = false
    @State private var alertMessage: String?
    @State private var showAlert: Bool = false
    @State private var isLoading: Bool = false
    @State private var isThinning: Bool = false

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(state.t("Mac Health & Diagnostics"))
                        .font(.title2)
                        .fontWeight(.bold)
                    Text(state.t("Evaluates macOS permissions, disk space, and system tools."))
                        .font(.caption)
                        .foregroundColor(.secondary)
                }

                Spacer()

                Button(action: openFullDiskAccessSettings) {
                    Label(state.t("System Settings"), systemImage: "lock.shield")
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
                    Section(header: Text(state.t("System Diagnostics"))) {
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
                        Section(header: Text(state.t("Storage Overview"))) {
                            if let d = h.disk {
                                HStack {
                                    Text(state.t("Primary Disk Total"))
                                    Spacer()
                                    Text(MacMaidBridge.formatBytes(d.totalBytes))
                                        .foregroundColor(.secondary)
                                }
                                HStack {
                                    Text(state.t("Available Disk Space"))
                                    Spacer()
                                    Text(MacMaidBridge.formatBytes(d.availableBytes))
                                        .foregroundColor(.green)
                                        .fontWeight(.semibold)
                                }
                            }
                        }
                    }

                    // Time Machine APFS Snapshots Section
                    Section(header: Text(state.t("Time Machine APFS Snapshots"))) {
                        HStack(spacing: 12) {
                            Text("\(snapshots.count) \(state.t("local snapshot(s)"))")
                                .font(.subheadline)
                                .fontWeight(.medium)

                            Spacer()

                            Picker(state.t("Target"), selection: $thinTargetGB) {
                                Text("5 GB").tag(UInt64(5))
                                Text("10 GB").tag(UInt64(10))
                                Text("20 GB").tag(UInt64(20))
                                Text("50 GB").tag(UInt64(50))
                            }
                            .frame(width: 120)

                            Button(action: prepareThinSnapshots) {
                                Label(state.t("Thin Snapshots"), systemImage: "clock.arrow.circlepath")
                            }
                            .buttonStyle(.borderedProminent)
                            .tint(.orange)
                            .disabled(snapshots.isEmpty || isThinning)
                        }
                        .padding(.vertical, 2)

                        if snapshots.isEmpty {
                            Text(state.t("No local APFS snapshots found on root volume."))
                                .font(.caption)
                                .foregroundColor(.secondary)
                        } else {
                            ForEach(snapshots) { snap in
                                HStack {
                                    Image(systemName: "camera.aperture")
                                        .foregroundColor(.secondary)
                                    VStack(alignment: .leading, spacing: 1) {
                                        Text(snap.name)
                                            .font(.caption)
                                            .lineLimit(1)
                                        Text("Snapshot date: \(snap.date)")
                                            .font(.caption2)
                                            .foregroundColor(.secondary)
                                    }
                                    Spacer()
                                }
                                .padding(.vertical, 2)
                            }
                        }
                    }
                }
            }
        }
        .onAppear(perform: loadDiagnostics)
        .sheet(isPresented: $showConfirmSheet) {
            if let staged = stagedPlan {
                ReviewConfirmationSheet(
                    stagedPlan: staged,
                    onConfirm: { token, _ in
                        showConfirmSheet = false
                        executeThin(reviewToken: token)
                    },
                    onCancel: {
                        showConfirmSheet = false
                    }
                )
            }
        }
        .alert(isPresented: $showAlert) {
            Alert(title: Text(state.t("Notice")), message: Text(alertMessage ?? ""), dismissButton: .default(Text(state.t("OK"))))
        }
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
            let resSnaps = MacMaidBridge.shared.listSnapshots()
            DispatchQueue.main.async {
                self.checks = resChecks
                self.health = resHealth
                self.snapshots = resSnaps
                self.isLoading = false
            }
        }
    }

    private func openFullDiskAccessSettings() {
        let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles")!
        NSWorkspace.shared.open(url)
    }

    private func prepareThinSnapshots() {
        struct SnapshotPayload: Codable {
            let target_gb: UInt64
        }
        let payload = SnapshotPayload(target_gb: thinTargetGB)
        guard let jsonData = try? JSONEncoder().encode(payload),
              let jsonStr = String(data: jsonData, encoding: .utf8) else {
            alertMessage = "Failed to encode snapshot payload"
            showAlert = true
            return
        }

        let res = MacMaidBridge.shared.stageReviewPlan(scope: "snapshots", payloadJson: jsonStr)
        switch res {
        case .success(let staged):
            self.stagedPlan = staged
            self.showConfirmSheet = true
        case .failure(let err):
            self.alertMessage = "Snapshot review failed: \(err.message)"
            self.showAlert = true
        }
    }

    private func executeThin(reviewToken: String) {
        isThinning = true
        DispatchQueue.global(qos: .userInitiated).async {
            let res = MacMaidBridge.shared.thinSnapshots(targetGb: thinTargetGB, reviewToken: reviewToken)
            DispatchQueue.main.async {
                self.isThinning = false
                switch res {
                case .success(let thinRes):
                    let deltaStr = thinRes.observedFreeBytesDelta != nil ? "\(MacMaidBridge.formatBytes(UInt64(abs(thinRes.observedFreeBytesDelta!)))) space change observed." : ""
                    self.alertMessage = "Thin request completed. \(deltaStr)"
                    self.showAlert = true
                    self.loadDiagnostics()
                    state.refreshHealth()
                case .failure(let err):
                    self.alertMessage = "Thinning failed: \(err.message)"
                    self.showAlert = true
                }
            }
        }
    }
}
