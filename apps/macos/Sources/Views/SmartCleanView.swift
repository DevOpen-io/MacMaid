import SwiftUI

struct SmartCleanView: View {
    @ObservedObject var state = AppState.shared
    @State private var profile: String = "safe"
    @State private var includeTrash: Bool = false
    @State private var includeTemp: Bool = false
    @State private var isScanning: Bool = false
    @State private var isCleaning: Bool = false
    @State private var scanPercent: Int = 0
    @State private var currentPhase: String = ""
    @State private var currentPath: String = ""
    @State private var scanResult: ScanResultModel?
    @State private var selectedItemIds: Set<String> = []
    @State private var stagedPlan: StagedPlanModel?
    @State private var showConfirmSheet: Bool = false
    @State private var errorMessage: String?
    @State private var showError: Bool = false
    @State private var operationResult: OperationResultModel?
    @State private var cancellationToken: OpaquePointer?

    var selectedItems: [CleanupItemModel] {
        guard let res = scanResult else { return [] }
        return res.items.filter { selectedItemIds.contains($0.id) }
    }

    var selectedBytes: UInt64 {
        selectedItems.reduce(0) { $0 + $1.estimatedBytes }
    }

    var body: some View {
        VStack(spacing: 0) {
            // Header / Controls Bar
            HStack(spacing: 16) {
                Picker(state.t("Profile"), selection: $profile) {
                    Text(state.t("Safe")).tag("safe")
                    Text(state.t("Deep")).tag("deep")
                    Text(state.t("Developer")).tag("developer")
                    Text(state.t("Aggressive")).tag("aggressive")
                }
                .pickerStyle(SegmentedPickerStyle())
                .frame(width: 320)

                Toggle(state.t("Include Trash"), isOn: $includeTrash)
                Toggle(state.t("System Temp"), isOn: $includeTemp)

                Spacer()

                if isScanning || isCleaning {
                    Button(action: cancelCurrentOperation) {
                        Label(state.t("Cancel"), systemImage: "xmark.circle")
                    }
                    .buttonStyle(.bordered)
                } else {
                    Button(action: startScan) {
                        Label(state.t("Scan"), systemImage: "magnifyingglass")
                    }
                    .buttonStyle(.borderedProminent)

                    if let res = scanResult, !res.items.isEmpty {
                        Button(action: prepareClean) {
                            Label(state.t("Clean"), systemImage: "sparkles")
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(.red)
                        .disabled(selectedItemIds.isEmpty)
                    }
                }
            }
            .padding()
            .background(Color(NSColor.windowBackgroundColor))

            Divider()

            // Progress / Status Bar
            if isScanning {
                VStack(spacing: 6) {
                    ProgressView(value: Double(scanPercent), total: 100)
                        .progressViewStyle(LinearProgressViewStyle())
                    HStack {
                        Text("\(scanPercent)% · \(currentPhase)")
                            .font(.caption)
                            .foregroundColor(.secondary)
                        Spacer()
                        Text(currentPath)
                            .font(.caption2)
                            .foregroundColor(.secondary)
                            .lineLimit(1)
                            .truncationMode(.middle)
                    }
                }
                .padding()
                .background(Color(NSColor.controlBackgroundColor))
                Divider()
            }

            // Results List / Empty State
            if let result = scanResult {
                if result.items.isEmpty {
                    VStack(spacing: 12) {
                        Image(systemName: "checkmark.circle.fill")
                            .font(.system(size: 48))
                            .foregroundColor(.green)
                        Text("Your Mac is spotless!")
                            .font(.title2)
                        Text("No disposable cleanup candidates found for profile '\(profile)'.")
                            .foregroundColor(.secondary)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    VStack(spacing: 0) {
                        HStack {
                            Text("\(result.items.count) candidates found · \(MacMaidBridge.formatBytes(result.totalBytes))")
                                .font(.headline)
                            Spacer()
                            Text("Selected: \(selectedItems.count) items (\(MacMaidBridge.formatBytes(selectedBytes)))")
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                        }
                        .padding(.horizontal)
                        .padding(.vertical, 8)
                        .background(Color(NSColor.controlBackgroundColor))

                        Divider()

                        List {
                            ForEach(result.items) { item in
                                HStack {
                                    Toggle(isOn: Binding(
                                        get: { selectedItemIds.contains(item.id) },
                                        set: { if $0 { selectedItemIds.insert(item.id) } else { selectedItemIds.remove(item.id) } }
                                    )) {
                                        EmptyView()
                                    }
                                    .labelsHidden()

                                    VStack(alignment: .leading, spacing: 2) {
                                        HStack {
                                            Text(item.label)
                                                .fontWeight(.medium)
                                            Spacer()
                                            Text(MacMaidBridge.formatBytes(item.estimatedBytes))
                                                .font(.callout)
                                                .foregroundColor(.secondary)
                                        }

                                        HStack(spacing: 8) {
                                            Text(item.category)
                                                .font(.caption2)
                                                .padding(.horizontal, 6)
                                                .padding(.vertical, 2)
                                                .background(Color.blue.opacity(0.15))
                                                .foregroundColor(.blue)
                                                .cornerRadius(4)

                                            Text(item.risk)
                                                .font(.caption2)
                                                .padding(.horizontal, 6)
                                                .padding(.vertical, 2)
                                                .background(riskColor(item.risk).opacity(0.15))
                                                .foregroundColor(riskColor(item.risk))
                                                .cornerRadius(4)

                                            if let app = item.requiresAppClosed {
                                                Text("Requires \(app) closed")
                                                    .font(.caption2)
                                                    .foregroundColor(.orange)
                                            }

                                            Spacer()

                                            if let p = item.path {
                                                Text(p)
                                                    .font(.caption2)
                                                    .foregroundColor(.secondary)
                                                    .lineLimit(1)
                                                    .truncationMode(.middle)
                                            }
                                        }
                                    }
                                }
                                .padding(.vertical, 4)
                            }
                        }
                    }
                }
            } else {
                VStack(spacing: 16) {
                    Image(systemName: "sparkles")
                        .font(.system(size: 56))
                        .foregroundColor(.blue)
                    Text("Deep Clean Your Mac Safely")
                        .font(.title)
                        .fontWeight(.semibold)
                    Text("Select a cleanup profile and click Scan to safely discover caches, logs, and temporary files.")
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: 400)
                    Button(action: startScan) {
                        Label(state.t("Scan"), systemImage: "magnifyingglass")
                            .padding(.horizontal, 16)
                            .padding(.vertical, 8)
                    }
                    .buttonStyle(.borderedProminent)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .sheet(isPresented: $showConfirmSheet) {
            if let staged = stagedPlan {
                ReviewConfirmationSheet(
                    stagedPlan: staged,
                    onConfirm: { token, extraOptIn in
                        showConfirmSheet = false
                        executeCleanup(reviewToken: token, allowManual: extraOptIn)
                    },
                    onCancel: {
                        showConfirmSheet = false
                    }
                )
            }
        }
        .alert(isPresented: $showError) {
            Alert(
                title: Text(state.t("Notice")),
                message: Text(errorMessage ?? ""),
                dismissButton: .default(Text(state.t("OK")))
            )
        }
    }

    private func riskColor(_ risk: String) -> Color {
        switch risk.uppercased() {
        case "SAFE": return .green
        case "MODERATE": return .yellow
        case "AGGRESSIVE": return .orange
        default: return .red
        }
    }

    private func startScan() {
        isScanning = true
        scanPercent = 0
        currentPhase = "Initializing..."
        currentPath = ""
        cancellationToken = macmaid_cancellation_token_new()

        DispatchQueue.global(qos: .userInitiated).async {
            let res = MacMaidBridge.shared.scan(
                profile: profile,
                includeTrash: includeTrash,
                includeTemp: includeTemp,
                token: cancellationToken
            ) { pct, phase, path in
                DispatchQueue.main.async {
                    self.scanPercent = pct
                    self.currentPhase = phase
                    self.currentPath = path
                }
            }

            DispatchQueue.main.async {
                self.isScanning = false
                self.scanResult = res
                if let items = res?.items {
                    self.selectedItemIds = Set(items.map { $0.id })
                }
                if let token = self.cancellationToken {
                    macmaid_cancellation_token_free(token)
                    self.cancellationToken = nil
                }
            }
        }
    }

    private func prepareClean() {
        guard !selectedItems.isEmpty else { return }
        guard let jsonData = try? JSONEncoder().encode(selectedItems),
              let jsonStr = String(data: jsonData, encoding: .utf8) else {
            errorMessage = "Failed to encode selected items"
            showError = true
            return
        }

        let res = MacMaidBridge.shared.stageReviewPlan(scope: "clean", payloadJson: jsonStr)
        switch res {
        case .success(let staged):
            self.stagedPlan = staged
            self.showConfirmSheet = true
        case .failure(let err):
            self.errorMessage = "Review staging failed: \(err.message)"
            self.showError = true
        }
    }

    private func executeCleanup(reviewToken: String, allowManual: Bool) {
        isCleaning = true
        cancellationToken = macmaid_cancellation_token_new()

        DispatchQueue.global(qos: .userInitiated).async {
            let res = MacMaidBridge.shared.executeClean(
                items: selectedItems,
                apply: true,
                allowManual: allowManual,
                reviewToken: reviewToken
            ) { idx, total, label, outcome in
                DispatchQueue.main.async {
                    self.currentPhase = "Cleaning [\(idx)/\(total)] \(label)"
                }
            }

            DispatchQueue.main.async {
                self.isCleaning = false
                self.operationResult = res
                self.startScan() // Refresh scan
                state.refreshHealth()
                if let token = self.cancellationToken {
                    macmaid_cancellation_token_free(token)
                    self.cancellationToken = nil
                }
            }
        }
    }

    private func cancelCurrentOperation() {
        if let token = cancellationToken {
            macmaid_cancellation_token_cancel(token)
        }
        isScanning = false
        isCleaning = false
    }
}
