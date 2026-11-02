import SwiftUI
import AppKit

struct SmartDownloadsView: View {
    @ObservedObject var state = AppState.shared
    @State private var olderThanDays: Double = 30
    @State private var report: SmartDownloadsReportModel?
    @State private var selectedPaths: Set<String> = []
    @State private var isScanning: Bool = false
    @State private var stagedPlan: StagedPlanModel?
    @State private var showConfirmSheet: Bool = false
    @State private var alertMessage: String?
    @State private var showAlert: Bool = false

    var allItems: [DownloadItemModel] {
        guard let rep = report else { return [] }
        return rep.installers + rep.archives + rep.incomplete + rep.duplicates
    }

    var selectedBytes: UInt64 {
        allItems.filter { selectedPaths.contains($0.path) }.reduce(0) { $0 + $1.size }
    }

    var body: some View {
        VStack(spacing: 0) {
            // Controls Bar
            HStack(spacing: 16) {
                HStack {
                    Text("\(state.t("Older than")): \(Int(olderThanDays)) \(state.t("days"))")
                        .font(.caption)
                    Slider(value: $olderThanDays, in: 7...180, step: 7)
                        .frame(width: 160)
                }

                Spacer()

                if isScanning {
                    ProgressView()
                        .frame(width: 80)
                } else {
                    Button(action: startScan) {
                        Label(state.t("Scan"), systemImage: "arrow.down.circle.fill")
                    }
                    .buttonStyle(.borderedProminent)

                    if report != nil && !allItems.isEmpty {
                        Button(action: selectAllInstallersAndIncomplete) {
                            Text(state.t("Select Safe Cleanable"))
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
                    Text(state.t("Categorizing Downloads..."))
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let rep = report {
                ScrollView {
                    VStack(alignment: .leading, spacing: 18) {
                        HStack {
                            Text("\(state.t("Downloads Cleanup Potential")): \(MacMaidBridge.formatBytes(rep.totalBytes))")
                                .font(.title3)
                                .fontWeight(.bold)
                            Spacer()
                            if !selectedPaths.isEmpty {
                                Text("\(selectedPaths.count) selected · \(MacMaidBridge.formatBytes(selectedBytes))")
                                    .font(.subheadline)
                                    .foregroundColor(.accentColor)
                            }
                        }

                        // Installers Section
                        DownloadCategoryCard(
                            title: state.t("Installers (.dmg, .pkg, .iso)"),
                            items: rep.installers,
                            icon: "shippingbox.fill",
                            color: .blue,
                            selectedPaths: $selectedPaths
                        )

                        // Incomplete Downloads Section
                        DownloadCategoryCard(
                            title: state.t("Incomplete Downloads (.crdownload, .part)"),
                            items: rep.incomplete,
                            icon: "exclamationmark.arrow.triangle.2.circlepath",
                            color: .orange,
                            selectedPaths: $selectedPaths
                        )

                        // Duplicate Downloads Section
                        DownloadCategoryCard(
                            title: state.t("Duplicate Downloads (e.g. file (1).ext)"),
                            items: rep.duplicates,
                            icon: "doc.on.doc",
                            color: .teal,
                            selectedPaths: $selectedPaths
                        )

                        // Archives Section
                        DownloadCategoryCard(
                            title: state.t("Archives (.zip, .tar, .7z)"),
                            items: rep.archives,
                            icon: "doc.zipper",
                            color: .purple,
                            selectedPaths: $selectedPaths
                        )
                    }
                    .padding()
                }
            } else {
                VStack(spacing: 12) {
                    Image(systemName: "arrow.down.circle.fill")
                        .font(.system(size: 48))
                        .foregroundColor(.blue)
                    Text(state.t("Smart Downloads Categorizer"))
                        .font(.title2)
                        .fontWeight(.semibold)
                    Text(state.t("Automatically groups installers, old archives, broken downloads, and duplicate copies in ~/Downloads. Select files to safely move them to Trash."))
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: 440)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .onAppear(perform: startScan)
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

    private func selectAllInstallersAndIncomplete() {
        guard let rep = report else { return }
        var newSelected = selectedPaths
        for item in rep.installers {
            newSelected.insert(item.path)
        }
        for item in rep.incomplete {
            newSelected.insert(item.path)
        }
        for item in rep.duplicates {
            newSelected.insert(item.path)
        }
        selectedPaths = newSelected
    }

    private func startScan() {
        isScanning = true
        selectedPaths.removeAll()

        DispatchQueue.global(qos: .userInitiated).async {
            let res = MacMaidBridge.shared.scanSmartDownloads(olderThanDays: UInt64(olderThanDays), token: nil)
            DispatchQueue.main.async {
                self.isScanning = false
                self.report = res
            }
        }
    }

    private func prepareTrash() {
        guard !selectedPaths.isEmpty else { return }

        struct DownloadsTrashPayload: Codable {
            let paths: [String]
            let estimatedBytes: UInt64
        }
        let payload = DownloadsTrashPayload(paths: Array(selectedPaths), estimatedBytes: selectedBytes)
        guard let jsonData = try? JSONEncoder().encode(payload),
              let jsonStr = String(data: jsonData, encoding: .utf8) else {
            alertMessage = "Failed to encode downloads trash payload"
            showAlert = true
            return
        }

        let res = MacMaidBridge.shared.stageReviewPlan(scope: "downloads", payloadJson: jsonStr)
        switch res {
        case .success(let staged):
            self.stagedPlan = staged
            self.showConfirmSheet = true
        case .failure(let err):
            self.alertMessage = "Downloads review staging failed: \(err.message)"
            self.showAlert = true
        }
    }

    private func executeTrash(reviewToken: String) {
        let toTrash = Array(selectedPaths)
        DispatchQueue.global(qos: .userInitiated).async {
            let res = MacMaidBridge.shared.trashDownloadItems(
                paths: toTrash,
                estimatedBytes: selectedBytes,
                reviewToken: reviewToken
            )

            DispatchQueue.main.async {
                switch res {
                case .success(let reclaimed):
                    self.alertMessage = "Moved \(toTrash.count) download file(s) to Trash. Reclaimed \(MacMaidBridge.formatBytes(reclaimed))."
                    self.showAlert = true
                    self.startScan()
                case .failure(let err):
                    self.alertMessage = "Downloads trash failed: \(err.message)"
                    self.showAlert = true
                }
            }
        }
    }
}

struct DownloadCategoryCard: View {
    let title: String
    let items: [DownloadItemModel]
    let icon: String
    let color: Color
    @Binding var selectedPaths: Set<String>

    @State private var isExpanded: Bool = true

    var totalBytes: UInt64 {
        items.reduce(0) { $0 + $1.size }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Button(action: { withAnimation { isExpanded.toggle() } }) {
                    HStack(spacing: 6) {
                        Image(systemName: isExpanded ? "chevron.down" : "chevron.right")
                            .font(.caption)
                            .foregroundColor(.secondary)
                        Label(title, systemImage: icon)
                            .font(.headline)
                            .foregroundColor(color)
                    }
                }
                .buttonStyle(.plain)

                Spacer()

                if !items.isEmpty {
                    Button(action: toggleCategorySelection) {
                        Text(allCategorySelected ? "Deselect" : "Select All")
                            .font(.caption)
                    }
                    .buttonStyle(.borderless)
                }

                Text("\(items.count) files · \(MacMaidBridge.formatBytes(totalBytes))")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
            }

            if items.isEmpty {
                Text("No matching files found.")
                    .font(.caption)
                    .foregroundColor(.secondary)
            } else if isExpanded {
                VStack(spacing: 4) {
                    ForEach(items) { item in
                        HStack {
                            Toggle(isOn: Binding(
                                get: { selectedPaths.contains(item.path) },
                                set: { if $0 { selectedPaths.insert(item.path) } else { selectedPaths.remove(item.path) } }
                            )) {
                                EmptyView()
                            }
                            .labelsHidden()

                            Text(item.name)
                                .font(.caption)
                                .lineLimit(1)
                                .truncationMode(.middle)

                            Spacer()

                            Text("\(item.ageDays)d ago")
                                .font(.caption2)
                                .foregroundColor(.secondary)

                            Text(MacMaidBridge.formatBytes(item.size))
                                .font(.caption2)
                                .foregroundColor(.secondary)
                                .frame(width: 75, alignment: .trailing)

                            Button(action: {
                                NSWorkspace.shared.selectFile(item.path, inFileViewerRootedAtPath: "")
                            }) {
                                Image(systemName: "macwindow")
                                    .font(.caption2)
                            }
                            .buttonStyle(.borderless)
                        }
                        .padding(.vertical, 2)
                    }
                }
            }
        }
        .padding()
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(10)
    }

    private var allCategorySelected: Bool {
        !items.isEmpty && items.allSatisfy { selectedPaths.contains($0.path) }
    }

    private func toggleCategorySelection() {
        if allCategorySelected {
            for item in items {
                selectedPaths.remove(item.path)
            }
        } else {
            for item in items {
                selectedPaths.insert(item.path)
            }
        }
    }
}
