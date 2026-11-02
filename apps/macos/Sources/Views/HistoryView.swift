import SwiftUI

struct HistoryView: View {
    @ObservedObject var state = AppState.shared
    @State private var records: [OperationRecordModel] = []
    @State private var restorable: [RestorableItemModel] = []
    @State private var selectedTab: Int = 0
    @State private var alertMessage: String?
    @State private var showAlert: Bool = false

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Picker("", selection: $selectedTab) {
                    Text("Audit Log").tag(0)
                    Text("Restorable Trash Items").tag(1)
                }
                .pickerStyle(SegmentedPickerStyle())
                .frame(width: 280)

                Spacer()

                Button(action: loadHistory) {
                    Label(state.t("Refresh"), systemImage: "arrow.clockwise")
                }
            }
            .padding()
            .background(Color(NSColor.windowBackgroundColor))

            Divider()

            if selectedTab == 0 {
                // Audit records
                if records.isEmpty {
                    VStack(spacing: 8) {
                        Image(systemName: "clock.arrow.circlepath")
                            .font(.system(size: 44))
                            .foregroundColor(.secondary)
                        Text("No operation history logged yet.")
                            .foregroundColor(.secondary)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    List(records) { r in
                        HStack(spacing: 12) {
                            Image(systemName: r.status == "success" ? "checkmark.circle.fill" : "xmark.circle.fill")
                                .foregroundColor(r.status == "success" ? .green : .red)

                            VStack(alignment: .leading, spacing: 2) {
                                HStack {
                                    Text(r.label ?? r.eventType ?? "Operation")
                                        .fontWeight(.medium)
                                    Spacer()
                                    Text(r.status)
                                        .font(.caption2)
                                        .padding(.horizontal, 6)
                                        .padding(.vertical, 2)
                                        .background(r.status == "success" ? Color.green.opacity(0.15) : Color.red.opacity(0.15))
                                        .cornerRadius(4)
                                }

                                if let p = r.path {
                                    Text(p)
                                        .font(.caption2)
                                        .foregroundColor(.secondary)
                                        .lineLimit(1)
                                        .truncationMode(.middle)
                                }

                                Text(r.timestamp)
                                    .font(.caption2)
                                    .foregroundColor(.secondary)
                            }

                            Spacer()

                            Text(MacMaidBridge.formatBytes(r.estimatedReclaimedBytes))
                                .font(.callout)
                                .foregroundColor(.secondary)
                        }
                        .padding(.vertical, 2)
                    }
                }
            } else {
                // Restorable items
                if restorable.isEmpty {
                    VStack(spacing: 8) {
                        Image(systemName: "trash")
                            .font(.system(size: 44))
                            .foregroundColor(.secondary)
                        Text("No restorable items found in Trash.")
                            .foregroundColor(.secondary)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    List(restorable) { item in
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(item.label)
                                    .fontWeight(.medium)
                                Text("Original: \(item.originalPath)")
                                    .font(.caption2)
                                    .foregroundColor(.secondary)
                                    .lineLimit(1)
                                    .truncationMode(.middle)
                            }

                            Spacer()

                            Text(MacMaidBridge.formatBytes(item.bytes))
                                .font(.caption)
                                .foregroundColor(.secondary)

                            Button("Restore") {
                                restoreItem(item)
                            }
                            .buttonStyle(.borderedProminent)
                            .disabled(!item.existsInTrash)
                        }
                        .padding(.vertical, 2)
                    }
                }
            }
        }
        .onAppear(perform: loadHistory)
        .alert(isPresented: $showAlert) {
            Alert(title: Text("Notice"), message: Text(alertMessage ?? ""), dismissButton: .default(Text("OK")))
        }
    }

    private func loadHistory() {
        DispatchQueue.global(qos: .userInitiated).async {
            let recs = MacMaidBridge.shared.readHistory(limit: 50)
            let rest = MacMaidBridge.shared.listRestorable(limit: 30)
            DispatchQueue.main.async {
                self.records = recs
                self.restorable = rest
            }
        }
    }

    private func restoreItem(_ item: RestorableItemModel) {
        DispatchQueue.global(qos: .userInitiated).async {
            let res = MacMaidBridge.shared.restoreTrashItem(trashPath: item.trashPath, origPath: item.originalPath, allowCopy: true)
            DispatchQueue.main.async {
                switch res {
                case .success(let path):
                    self.alertMessage = "Restored successfully to:\n\(path)"
                    self.showAlert = true
                    self.loadHistory()
                case .failure(let err):
                    self.alertMessage = "Restore failed: \(err)"
                    self.showAlert = true
                }
            }
        }
    }
}
