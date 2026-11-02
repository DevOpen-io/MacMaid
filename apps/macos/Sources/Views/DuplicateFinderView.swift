import SwiftUI
import AppKit

struct DuplicateFinderView: View {
    @ObservedObject var state = AppState.shared
    @State private var searchPath: String = "~"
    @State private var minSizeMB: Double = 10
    @State private var isScanning: Bool = false
    @State private var scannedCount: Int = 0
    @State private var groups: [DuplicateGroupModel] = []
    @State private var selectedPaths: Set<String> = []
    @State private var stagedPlan: StagedPlanModel?
    @State private var showConfirmSheet: Bool = false
    @State private var alertMessage: String?
    @State private var showAlert: Bool = false
    @State private var cancellationToken: OpaquePointer?

    var totalWastedBytes: UInt64 {
        groups.reduce(0) { $0 + ($1.size * UInt64($1.files.count - 1)) }
    }

    var selectedBytes: UInt64 {
        var bytes: UInt64 = 0
        for grp in groups {
            let countInGrp = grp.files.filter { selectedPaths.contains($0) }.count
            bytes += grp.size * UInt64(countInGrp)
        }
        return bytes
    }

    var body: some View {
        VStack(spacing: 0) {
            // Filter / Controls bar
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
                .frame(width: 220)

                HStack {
                    Text("\(state.t("Min Size")): \(Int(minSizeMB)) MB")
                        .font(.caption)
                    Slider(value: $minSizeMB, in: 1...200, step: 5)
                        .frame(width: 140)
                }

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
                        Label(state.t("Scan"), systemImage: "doc.on.doc.fill")
                    }
                    .buttonStyle(.borderedProminent)

                    if !groups.isEmpty {
                        Button(action: selectAllRedundant) {
                            Text(state.t("Select Duplicates"))
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
                    Text("\(state.t("Searching duplicate files...")) (\(scannedCount) \(state.t("files scanned")))")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if groups.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "doc.on.doc.fill")
                        .font(.system(size: 48))
                        .foregroundColor(.blue)
                    Text(state.t("Byte-for-Byte Duplicate Finder"))
                        .font(.title2)
                        .fontWeight(.semibold)
                    Text(state.t("MacMaid verifies identical file contents using fast prefix and full SHA-256 hashing. Select redundant copies to safely move them to Trash."))
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: 440)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                VStack(spacing: 0) {
                    HStack {
                        Text("\(groups.count) duplicate groups · \(MacMaidBridge.formatBytes(totalWastedBytes)) recoverable space")
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

                    List {
                        ForEach(groups) { grp in
                            VStack(alignment: .leading, spacing: 6) {
                                HStack {
                                    Text("Identical Content (\(grp.files.count) copies)")
                                        .fontWeight(.semibold)
                                    Spacer()
                                    Text("\(MacMaidBridge.formatBytes(grp.size)) each")
                                        .foregroundColor(.secondary)
                                }

                                Text("SHA-256: \(grp.hash)")
                                    .font(.system(.caption2, design: .monospaced))
                                    .foregroundColor(.secondary)

                                ForEach(Array(grp.files.enumerated()), id: \.element) { idx, file in
                                    HStack {
                                        Toggle(isOn: Binding(
                                            get: { selectedPaths.contains(file) },
                                            set: { checked in
                                                toggleFile(file, in: grp, select: checked)
                                            }
                                        )) {
                                            EmptyView()
                                        }
                                        .labelsHidden()

                                        if idx == 0 {
                                            Text(state.t("Original"))
                                                .font(.caption2)
                                                .padding(.horizontal, 4)
                                                .padding(.vertical, 1)
                                                .background(Color.green.opacity(0.15))
                                                .foregroundColor(.green)
                                                .cornerRadius(3)
                                        } else {
                                            Text(state.t("Duplicate"))
                                                .font(.caption2)
                                                .padding(.horizontal, 4)
                                                .padding(.vertical, 1)
                                                .background(Color.orange.opacity(0.15))
                                                .foregroundColor(.orange)
                                                .cornerRadius(3)
                                        }

                                        Text(file)
                                            .font(.caption)
                                            .lineLimit(1)
                                            .truncationMode(.middle)

                                        Spacer()

                                        Button(action: {
                                            NSWorkspace.shared.selectFile(file, inFileViewerRootedAtPath: "")
                                        }) {
                                            Label(state.t("Finder"), systemImage: "macwindow")
                                        }
                                        .buttonStyle(.borderless)
                                        .font(.caption2)
                                    }
                                }
                            }
                            .padding(.vertical, 6)
                        }
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

    // Safety contract: Never allow selecting all copies in a group (must preserve at least one master copy)
    private func toggleFile(_ file: String, in group: DuplicateGroupModel, select: Bool) {
        if select {
            let currentlySelected = group.files.filter { selectedPaths.contains($0) }
            if currentlySelected.count + 1 >= group.files.count {
                alertMessage = "Safety safeguard: You cannot select all copies of a duplicate group. At least one original copy must be preserved."
                showAlert = true
                return
            }
            selectedPaths.insert(file)
        } else {
            selectedPaths.remove(file)
        }
    }

    private func selectAllRedundant() {
        var newSelected = Set<String>()
        for grp in groups {
            // Keep first copy safe; select all subsequent copies
            for file in grp.files.dropFirst() {
                newSelected.insert(file)
            }
        }
        selectedPaths = newSelected
    }

    private func startScan() {
        isScanning = true
        scannedCount = 0
        selectedPaths.removeAll()
        cancellationToken = macmaid_cancellation_token_new()

        DispatchQueue.global(qos: .userInitiated).async {
            let res = MacMaidBridge.shared.findDuplicates(
                paths: [searchPath],
                minSize: UInt64(minSizeMB * 1024 * 1024),
                token: cancellationToken
            ) { count, _ in
                DispatchQueue.main.async {
                    self.scannedCount = count
                }
            }

            DispatchQueue.main.async {
                self.isScanning = false
                self.groups = res
                self.selectAllRedundant()
                if let token = self.cancellationToken {
                    macmaid_cancellation_token_free(token)
                    self.cancellationToken = nil
                }
            }
        }
    }

    private func prepareTrash() {
        guard !selectedPaths.isEmpty else { return }

        struct DuplicatesTrashPayload: Codable {
            let paths: [String]
            let estimatedBytes: UInt64
        }
        let payload = DuplicatesTrashPayload(paths: Array(selectedPaths), estimatedBytes: selectedBytes)
        guard let jsonData = try? JSONEncoder().encode(payload),
              let jsonStr = String(data: jsonData, encoding: .utf8) else {
            alertMessage = "Failed to encode duplicate trash payload"
            showAlert = true
            return
        }

        let res = MacMaidBridge.shared.stageReviewPlan(scope: "duplicates", payloadJson: jsonStr)
        switch res {
        case .success(let staged):
            self.stagedPlan = staged
            self.showConfirmSheet = true
        case .failure(let err):
            self.alertMessage = "Duplicates review staging failed: \(err.message)"
            self.showAlert = true
        }
    }

    private func executeTrash(reviewToken: String) {
        let toTrash = Array(selectedPaths)
        DispatchQueue.global(qos: .userInitiated).async {
            let res = MacMaidBridge.shared.trashDuplicateItems(
                paths: toTrash,
                estimatedBytes: selectedBytes,
                reviewToken: reviewToken
            )

            DispatchQueue.main.async {
                switch res {
                case .success(let reclaimed):
                    self.alertMessage = "Moved \(toTrash.count) duplicate file(s) to Trash. Reclaimed \(MacMaidBridge.formatBytes(reclaimed))."
                    self.showAlert = true
                    self.startScan()
                case .failure(let err):
                    self.alertMessage = "Duplicate trash failed: \(err.message)"
                    self.showAlert = true
                }
            }
        }
    }
}
