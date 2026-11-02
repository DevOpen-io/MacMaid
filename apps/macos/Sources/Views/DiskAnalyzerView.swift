import SwiftUI
import AppKit

struct DiskAnalyzerView: View {
    @ObservedObject var state = AppState.shared
    @State private var targetPath: String = "~"
    @State private var minSizeStr: String = "100MB"
    @State private var isAnalyzing: Bool = false
    @State private var scannedCount: Int = 0
    @State private var report: AnalyzerReportModel?
    @State private var currentNode: AnalyzerNodeModel?
    @State private var breadcrumbStack: [AnalyzerNodeModel] = []
    @State private var stagedPlan: StagedPlanModel?
    @State private var pendingTrashNode: AnalyzerNodeModel?
    @State private var showConfirmSheet: Bool = false
    @State private var alertMessage: String?
    @State private var showAlert: Bool = false
    @State private var cancellationToken: OpaquePointer?

    var body: some View {
        VStack(spacing: 0) {
            // Path and Control Bar
            HStack(spacing: 12) {
                HStack {
                    Image(systemName: "folder")
                        .foregroundColor(.secondary)
                    TextField("Path to analyze", text: $targetPath)
                        .textFieldStyle(PlainTextFieldStyle())
                }
                .padding(6)
                .background(Color(NSColor.textBackgroundColor))
                .cornerRadius(6)

                Button("Browse...") {
                    let panel = NSOpenPanel()
                    panel.canChooseFiles = false
                    panel.canChooseDirectories = true
                    panel.allowsMultipleSelection = false
                    if panel.runModal() == .OK, let url = panel.url {
                        targetPath = url.path
                        startAnalysis()
                    }
                }

                if isAnalyzing {
                    Button("Cancel") {
                        if let token = cancellationToken {
                            macmaid_cancellation_token_cancel(token)
                        }
                    }
                    .buttonStyle(.bordered)
                } else {
                    Button(state.t("Analyze")) {
                        startAnalysis()
                    }
                    .buttonStyle(.borderedProminent)
                }
            }
            .padding()
            .background(Color(NSColor.windowBackgroundColor))

            Divider()

            if isAnalyzing {
                VStack(spacing: 8) {
                    ProgressView()
                    Text("Scanning files... (\(scannedCount) items scanned)")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let rep = report {
                VStack(spacing: 0) {
                    // Breadcrumbs bar
                    HStack(spacing: 6) {
                        Button(action: {
                            breadcrumbStack.removeAll()
                            currentNode = rep.tree
                        }) {
                            Image(systemName: "house.fill")
                        }
                        .buttonStyle(.plain)

                        ForEach(breadcrumbStack.indices, id: \.self) { idx in
                            Image(systemName: "chevron.right")
                                .font(.caption2)
                                .foregroundColor(.secondary)
                            Button(breadcrumbStack[idx].name) {
                                let target = breadcrumbStack[idx]
                                breadcrumbStack = Array(breadcrumbStack.prefix(idx))
                                currentNode = target
                            }
                            .buttonStyle(.plain)
                        }

                        if let curr = currentNode, curr.path != rep.tree.path {
                            Image(systemName: "chevron.right")
                                .font(.caption2)
                                .foregroundColor(.secondary)
                            Text(curr.name)
                                .fontWeight(.medium)
                        }

                        Spacer()

                        if let curr = currentNode {
                            Text("\(MacMaidBridge.formatBytes(curr.bytes)) (\(curr.itemCount) items)")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                    .padding(.horizontal)
                    .padding(.vertical, 8)
                    .background(Color(NSColor.controlBackgroundColor))

                    Divider()

                    // Children Table
                    if let curr = currentNode, let children = curr.children, !children.isEmpty {
                        List {
                            ForEach(children) { child in
                                HStack {
                                    Image(systemName: child.isDir ? "folder.fill" : "doc.fill")
                                        .foregroundColor(child.isDir ? .blue : .secondary)

                                    if child.isDir {
                                        Button(action: {
                                            breadcrumbStack.append(curr)
                                            currentNode = child
                                        }) {
                                            Text(child.name)
                                                .fontWeight(.medium)
                                        }
                                        .buttonStyle(.plain)
                                    } else {
                                        Text(child.name)
                                    }

                                    Spacer()

                                    Text(MacMaidBridge.formatBytes(child.bytes))
                                        .foregroundColor(.secondary)
                                        .frame(width: 100, alignment: .trailing)

                                    Menu {
                                        Button(state.t("Move to Trash")) {
                                            prepareTrash(child)
                                        }
                                        Button(state.t("Reveal in Finder")) {
                                            NSWorkspace.shared.selectFile(child.path, inFileViewerRootedAtPath: "")
                                        }
                                    } label: {
                                        Image(systemName: "ellipsis.circle")
                                    }
                                    .menuStyle(BorderlessButtonMenuStyle())
                                    .frame(width: 30)
                                }
                                .padding(.vertical, 2)
                            }
                        }
                    } else {
                        VStack(spacing: 8) {
                            Text("No subdirectories or files found in this folder.")
                                .foregroundColor(.secondary)
                        }
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                    }
                }
            } else {
                VStack(spacing: 12) {
                    Image(systemName: "chart.pie.fill")
                        .font(.system(size: 56))
                        .foregroundColor(.blue)
                    Text("Interactive Disk Usage Analyzer")
                        .font(.title2)
                        .fontWeight(.semibold)
                    Text("Browse any directory to find space-consuming folders and files.")
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .sheet(isPresented: $showConfirmSheet) {
            if let staged = stagedPlan, let item = pendingTrashNode {
                ReviewConfirmationSheet(
                    stagedPlan: staged,
                    onConfirm: { token, _ in
                        showConfirmSheet = false
                        executeTrash(item: item, reviewToken: token)
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

    private func startAnalysis() {
        isAnalyzing = true
        scannedCount = 0
        cancellationToken = macmaid_cancellation_token_new()

        DispatchQueue.global(qos: .userInitiated).async {
            let res = MacMaidBridge.shared.analyzeDirectory(
                path: targetPath,
                topLimit: 50,
                minSize: 10_000_000,
                token: cancellationToken
            ) { count, _ in
                DispatchQueue.main.async {
                    self.scannedCount = count
                }
            }

            DispatchQueue.main.async {
                self.isAnalyzing = false
                self.report = res
                self.currentNode = res?.tree
                self.breadcrumbStack.removeAll()
                if let token = self.cancellationToken {
                    macmaid_cancellation_token_free(token)
                    self.cancellationToken = nil
                }
            }
        }
    }

    private func prepareTrash(_ item: AnalyzerNodeModel) {
        struct AnalyzerTrashPayload: Codable {
            let paths: [String]
            let estimatedBytes: UInt64
        }
        let payload = AnalyzerTrashPayload(paths: [item.path], estimatedBytes: item.bytes)
        guard let jsonData = try? JSONEncoder().encode(payload),
              let jsonStr = String(data: jsonData, encoding: .utf8) else {
            alertMessage = "Failed to encode trash payload"
            showAlert = true
            return
        }

        let res = MacMaidBridge.shared.stageReviewPlan(scope: "analyzer", payloadJson: jsonStr)
        switch res {
        case .success(let staged):
            self.pendingTrashNode = item
            self.stagedPlan = staged
            self.showConfirmSheet = true
        case .failure(let err):
            self.alertMessage = "Trash review failed: \(err.message)"
            self.showAlert = true
        }
    }

    private func executeTrash(item: AnalyzerNodeModel, reviewToken: String) {
        DispatchQueue.global(qos: .userInitiated).async {
            let res = MacMaidBridge.shared.moveAnalyzerItemToTrash(
                path: item.path,
                estimatedBytes: item.bytes,
                reviewToken: reviewToken
            )
            DispatchQueue.main.async {
                switch res {
                case .success(let dest):
                    self.alertMessage = "Moved to Trash:\n\(dest)"
                    self.showAlert = true
                    self.startAnalysis()
                case .failure(let err):
                    self.alertMessage = "Cannot move to Trash: \(err.message)"
                    self.showAlert = true
                }
            }
        }
    }
}
