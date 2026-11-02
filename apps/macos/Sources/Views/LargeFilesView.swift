import SwiftUI
import AppKit

struct LargeFilesView: View {
    @ObservedObject var state = AppState.shared
    @State private var searchPath: String = "~"
    @State private var minSizeOption: UInt64 = 500 * 1024 * 1024 // 500MB
    @State private var olderThanDays: UInt64 = 0 // Any age
    @State private var files: [LargeOldFileModel] = []
    @State private var selectedPaths: Set<String> = []
    @State private var isScanning: Bool = false
    @State private var stagedPlan: StagedPlanModel?
    @State private var showConfirmSheet: Bool = false
    @State private var alertMessage: String?
    @State private var showAlert: Bool = false
    @State private var cancellationToken: OpaquePointer?

    var totalBytes: UInt64 {
        files.reduce(0) { $0 + $1.size }
    }

    var selectedBytes: UInt64 {
        files.filter { selectedPaths.contains($0.path) }.reduce(0) { $0 + $1.size }
    }

    var body: some View {
        VStack(spacing: 0) {
            // Controls Bar
            HStack(spacing: 16) {
                HStack {
                    Image(systemName: "folder")
                        .foregroundColor(.secondary)
                    TextField(state.t("Directory"), text: $searchPath)
                        .textFieldStyle(PlainTextFieldStyle())
                }
                .padding(6)
                .background(Color(NSColor.textBackgroundColor))
                .cornerRadius(6)
                .frame(width: 200)

                Picker(state.t("Min Size"), selection: $minSizeOption) {
                    Text("100 MB").tag(UInt64(100 * 1024 * 1024))
                    Text("500 MB").tag(UInt64(500 * 1024 * 1024))
                    Text("1 GB").tag(UInt64(1024 * 1024 * 1024))
                    Text("5 GB").tag(UInt64(5 * 1024 * 1024 * 1024))
                }
                .frame(width: 130)

                Picker(state.t("Age"), selection: $olderThanDays) {
                    Text(state.t("Any Time")).tag(UInt64(0))
                    Text("> 30 Days").tag(UInt64(30))
                    Text("> 90 Days").tag(UInt64(90))
                    Text("> 180 Days").tag(UInt64(180))
                    Text("> 1 Year").tag(UInt64(365))
                }
                .frame(width: 140)

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
                        Label(state.t("Scan"), systemImage: "arrow.up.bin.fill")
                    }
                    .buttonStyle(.borderedProminent)

                    if !files.isEmpty {
                        Button(action: toggleSelectAll) {
                            Text(selectedPaths.count == files.count ? state.t("Deselect All") : state.t("Select All"))
                        }
                        .buttonStyle(.bordered)

                        Button(action: prepareTrash) {
                            Label(state.t("Trash Selected"), systemImage: "trash")
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(.red)
                        .disabled(selectedPaths.isEmpty)
                    }
                }
            }
            .padding()
            .background(Color(NSColor.windowBackgroundColor))

            Divider()

            if isScanning {
                VStack(spacing: 8) {
                    ProgressView()
                    Text(state.t("Scanning large and old files..."))
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if files.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "arrow.up.bin.fill")
                        .font(.system(size: 48))
                        .foregroundColor(.blue)
                    Text(state.t("Large & Old User Files"))
                        .font(.title2)
                        .fontWeight(.semibold)
                    Text(state.t("Filter files by minimum size and modification age. Select items to safely move them to Trash."))
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                VStack(spacing: 0) {
                    HStack {
                        Text("\(files.count) files · \(MacMaidBridge.formatBytes(totalBytes))")
                            .font(.headline)
                        Spacer()
                        if !selectedPaths.isEmpty {
                            Text("\(selectedPaths.count) selected · \(MacMaidBridge.formatBytes(selectedBytes))")
                                .font(.subheadline)
                                .foregroundColor(.accentColor)
                        }
                    }
                    .padding()
                    .background(Color(NSColor.controlBackgroundColor))

                    Divider()

                    List(files) { f in
                        HStack {
                            Toggle(isOn: Binding(
                                get: { selectedPaths.contains(f.path) },
                                set: { if $0 { selectedPaths.insert(f.path) } else { selectedPaths.remove(f.path) } }
                            )) {
                                EmptyView()
                            }
                            .labelsHidden()

                            Image(systemName: "doc.fill")
                                .foregroundColor(.secondary)

                            VStack(alignment: .leading, spacing: 2) {
                                Text(f.name)
                                    .fontWeight(.medium)
                                Text(f.path)
                                    .font(.caption2)
                                    .foregroundColor(.secondary)
                                    .lineLimit(1)
                                    .truncationMode(.middle)
                            }

                            Spacer()

                            Text(MacMaidBridge.formatBytes(f.size))
                                .font(.callout)
                                .foregroundColor(.secondary)
                                .frame(width: 100, alignment: .trailing)

                            Button(action: {
                                NSWorkspace.shared.selectFile(f.path, inFileViewerRootedAtPath: "")
                            }) {
                                Label(state.t("Finder"), systemImage: "macwindow")
                            }
                            .buttonStyle(.borderless)
                            .font(.caption)
                        }
                        .padding(.vertical, 2)
                    }
                }
            }
        }
        .sheet(isPresented: $showConfirmSheet) {
            if let staged = stagedPlan {
                ReviewConfirmationSheet(
                    stagedPlan: staged,
                    onConfirm: { token, _ in
                        showConfirmSheet = false
                        executeTrash(reviewToken: token)
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

    private func toggleSelectAll() {
        if selectedPaths.count == files.count {
            selectedPaths.removeAll()
        } else {
            selectedPaths = Set(files.map { $0.path })
        }
    }

    private func startScan() {
        isScanning = true
        selectedPaths.removeAll()
        cancellationToken = macmaid_cancellation_token_new()

        DispatchQueue.global(qos: .userInitiated).async {
            let res = MacMaidBridge.shared.scanLargeFiles(
                paths: [searchPath],
                minSize: minSizeOption,
                olderThanDays: olderThanDays,
                token: cancellationToken
            )

            DispatchQueue.main.async {
                self.isScanning = false
                self.files = res
                if let token = self.cancellationToken {
                    macmaid_cancellation_token_free(token)
                    self.cancellationToken = nil
                }
            }
        }
    }

    private func prepareTrash() {
        guard !selectedPaths.isEmpty else { return }

        struct LargeFilesTrashPayload: Codable {
            let paths: [String]
            let estimatedBytes: UInt64
        }
        let payload = LargeFilesTrashPayload(paths: Array(selectedPaths), estimatedBytes: selectedBytes)
        guard let jsonData = try? JSONEncoder().encode(payload),
              let jsonStr = String(data: jsonData, encoding: .utf8) else {
            alertMessage = "Failed to encode large files trash payload"
            showAlert = true
            return
        }

        let res = MacMaidBridge.shared.stageReviewPlan(scope: "large-files", payloadJson: jsonStr)
        switch res {
        case .success(let staged):
            self.stagedPlan = staged
            self.showConfirmSheet = true
        case .failure(let err):
            self.alertMessage = "Large files review staging failed: \(err.message)"
            self.showAlert = true
        }
    }

    private func executeTrash(reviewToken: String) {
        let toTrash = Array(selectedPaths)
        DispatchQueue.global(qos: .userInitiated).async {
            let res = MacMaidBridge.shared.trashLargeFiles(
                paths: toTrash,
                estimatedBytes: selectedBytes,
                reviewToken: reviewToken
            )

            DispatchQueue.main.async {
                switch res {
                case .success(let reclaimed):
                    self.alertMessage = "Moved \(toTrash.count) large file(s) to Trash. Reclaimed \(MacMaidBridge.formatBytes(reclaimed))."
                    self.showAlert = true
                    self.startScan()
                case .failure(let err):
                    self.alertMessage = "Large files trash failed: \(err.message)"
                    self.showAlert = true
                }
            }
        }
    }
}
