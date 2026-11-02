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
    @State private var showConfirmSheet: Bool = false
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
                Picker("Profile", selection: $profile) {
                    Text("Safe").tag("safe")
                    Text("Deep").tag("deep")
                    Text("Developer").tag("developer")
                    Text("Aggressive").tag("aggressive")
                }
                .pickerStyle(SegmentedPickerStyle())
                .frame(width: 320)

                Toggle("Include Trash", isOn: $includeTrash)
                Toggle("System Temp", isOn: $includeTemp)

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
                        Button(action: { showConfirmSheet = true }) {
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
            CleanConfirmationSheet(
                items: selectedItems,
                onConfirm: {
                    showConfirmSheet = false
                    executeCleanup()
                },
                onCancel: {
                    showConfirmSheet = false
                }
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

    private func executeCleanup() {
        isCleaning = true
        cancellationToken = macmaid_cancellation_token_new()

        DispatchQueue.global(qos: .userInitiated).async {
            let res = MacMaidBridge.shared.executeClean(
                items: selectedItems,
                apply: true,
                allowManual: false,
                token: cancellationToken
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

struct CleanConfirmationSheet: View {
    let items: [CleanupItemModel]
    let onConfirm: () -> Void
    let onCancel: () -> Void

    var totalBytes: UInt64 {
        items.reduce(0) { $0 + $1.estimatedBytes }
    }

    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 44))
                .foregroundColor(.orange)

            Text("Confirm Cleanup Execution")
                .font(.title2)
                .fontWeight(.bold)

            Text("MacMaid will safely clean \(items.count) item(s) reclaiming approximately \(MacMaidBridge.formatBytes(totalBytes)).")
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 420)

            VStack(alignment: .leading, spacing: 4) {
                Text("Pre-condition checks:")
                    .font(.caption)
                    .fontWeight(.medium)
                Text("• Whitelist rules will be revalidated at execution time.")
                    .font(.caption)
                    .foregroundColor(.secondary)
                Text("• Root/symlink traversal protection is strictly enforced.")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            .padding(10)
            .background(Color(NSColor.controlBackgroundColor))
            .cornerRadius(8)

            HStack(spacing: 16) {
                Button("Cancel", action: onCancel)
                    .keyboardShortcut(.cancelAction)

                Button("Clean \(MacMaidBridge.formatBytes(totalBytes))", action: onConfirm)
                    .buttonStyle(.borderedProminent)
                    .tint(.red)
                    .keyboardShortcut(.defaultAction)
            }
        }
        .padding(24)
        .frame(width: 480)
    }
}
