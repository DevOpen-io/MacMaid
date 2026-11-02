import SwiftUI

struct ProjectPurgeView: View {
    @ObservedObject var state = AppState.shared
    @State private var searchPath: String = "~"
    @State private var artifacts: [ProjectArtifactModel] = []
    @State private var isScanning: Bool = false
    @State private var stagedPlan: StagedPlanModel?
    @State private var pendingArtifact: ProjectArtifactModel?
    @State private var showConfirmSheet: Bool = false
    @State private var alertMessage: String?
    @State private var showAlert: Bool = false
    @State private var cancellationToken: OpaquePointer?

    var totalBytes: UInt64 {
        artifacts.reduce(0) { $0 + $1.bytes }
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                HStack {
                    Image(systemName: "folder")
                        .foregroundColor(.secondary)
                    TextField("Project workspace root", text: $searchPath)
                        .textFieldStyle(PlainTextFieldStyle())
                }
                .padding(6)
                .background(Color(NSColor.textBackgroundColor))
                .cornerRadius(6)
                .frame(width: 260)

                Spacer()

                if isScanning {
                    Button(state.t("Cancel")) {
                        if let token = cancellationToken {
                            macmaid_cancellation_token_cancel(token)
                        }
                    }
                    .buttonStyle(.bordered)
                } else {
                    Button(action: startScan) {
                        Label(state.t("Scan"), systemImage: "trash.slash.fill")
                    }
                    .buttonStyle(.borderedProminent)
                }
            }
            .padding()
            .background(Color(NSColor.windowBackgroundColor))

            Divider()

            if isScanning {
                VStack(spacing: 8) {
                    ProgressView()
                    Text("Scanning project repositories for build artifacts...")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if artifacts.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "trash.slash.fill")
                        .font(.system(size: 48))
                        .foregroundColor(.blue)
                    Text("Project Artifact Purge")
                        .font(.title2)
                        .fontWeight(.semibold)
                    Text("Discovers rebuildable target/, node_modules/, and .venv/ directories inside verified project roots. Moves artifacts safely to Trash.")
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: 440)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                VStack(spacing: 0) {
                    HStack {
                        Text("\(artifacts.count) artifacts · \(MacMaidBridge.formatBytes(totalBytes))")
                            .font(.headline)
                        Spacer()
                    }
                    .padding()
                    .background(Color(NSColor.controlBackgroundColor))

                    Divider()

                    List(artifacts) { art in
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                HStack {
                                    Text(art.projectName)
                                        .fontWeight(.semibold)
                                    Text(art.name)
                                        .font(.caption)
                                        .padding(.horizontal, 6)
                                        .padding(.vertical, 2)
                                        .background(Color.orange.opacity(0.15))
                                        .foregroundColor(.orange)
                                        .cornerRadius(4)
                                }
                                Text(art.path)
                                    .font(.caption2)
                                    .foregroundColor(.secondary)
                                    .lineLimit(1)
                                    .truncationMode(.middle)
                            }

                            Spacer()

                            Text(MacMaidBridge.formatBytes(art.bytes))
                                .font(.callout)
                                .foregroundColor(.secondary)
                                .frame(width: 90, alignment: .trailing)

                            Button(state.t("Purge to Trash")) {
                                preparePurge(art)
                            }
                            .buttonStyle(.bordered)
                            .tint(.red)
                        }
                        .padding(.vertical, 4)
                    }
                }
            }
        }
        .sheet(isPresented: $showConfirmSheet) {
            if let staged = stagedPlan, let art = pendingArtifact {
                ReviewConfirmationSheet(
                    stagedPlan: staged,
                    onConfirm: { token, _ in
                        showConfirmSheet = false
                        executePurge(artifact: art, reviewToken: token)
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

    private func startScan() {
        isScanning = true
        cancellationToken = macmaid_cancellation_token_new()

        DispatchQueue.global(qos: .userInitiated).async {
            let res = MacMaidBridge.shared.scanProjectPurge(paths: [searchPath], token: cancellationToken)
            DispatchQueue.main.async {
                self.isScanning = false
                self.artifacts = res
                if let token = self.cancellationToken {
                    macmaid_cancellation_token_free(token)
                    self.cancellationToken = nil
                }
            }
        }
    }

    private func preparePurge(_ artifact: ProjectArtifactModel) {
        guard let jsonData = try? JSONEncoder().encode([artifact]),
              let jsonStr = String(data: jsonData, encoding: .utf8) else {
            alertMessage = "Failed to encode artifact payload"
            showAlert = true
            return
        }

        let res = MacMaidBridge.shared.stageReviewPlan(scope: "purge", payloadJson: jsonStr)
        switch res {
        case .success(let staged):
            self.pendingArtifact = artifact
            self.stagedPlan = staged
            self.showConfirmSheet = true
        case .failure(let err):
            self.alertMessage = "Purge review staging failed: \(err.message)"
            self.showAlert = true
        }
    }

    private func executePurge(artifact: ProjectArtifactModel, reviewToken: String) {
        DispatchQueue.global(qos: .userInitiated).async {
            let res = MacMaidBridge.shared.purgeArtifact(artifact: artifact, reviewToken: reviewToken)
            DispatchQueue.main.async {
                switch res {
                case .success(let bytes):
                    self.alertMessage = "Purged \(artifact.name) from \(artifact.projectName). Reclaimed \(MacMaidBridge.formatBytes(bytes))."
                    self.showAlert = true
                    self.startScan()
                case .failure(let err):
                    self.alertMessage = "Purge failed: \(err.message)"
                    self.showAlert = true
                }
            }
        }
    }
}
