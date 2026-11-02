import SwiftUI

struct DuplicateFinderView: View {
    @ObservedObject var state = AppState.shared
    @State private var searchPath: String = "~"
    @State private var minSizeMB: Double = 10
    @State private var isScanning: Bool = false
    @State private var scannedCount: Int = 0
    @State private var groups: [DuplicateGroupModel] = []
    @State private var cancellationToken: OpaquePointer?

    var totalWastedBytes: UInt64 {
        groups.reduce(0) { $0 + ($1.size * UInt64($1.files.count - 1)) }
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 16) {
                HStack {
                    Image(systemName: "folder")
                        .foregroundColor(.secondary)
                    TextField("Directory", text: $searchPath)
                        .textFieldStyle(PlainTextFieldStyle())
                }
                .padding(6)
                .background(Color(NSColor.textBackgroundColor))
                .cornerRadius(6)
                .frame(width: 220)

                HStack {
                    Text("Min Size: \(Int(minSizeMB)) MB")
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
                }
            }
            .padding()
            .background(Color(NSColor.windowBackgroundColor))

            Divider()

            if isScanning {
                VStack(spacing: 8) {
                    ProgressView()
                    Text("Searching duplicate files... (\(scannedCount) files scanned)")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if groups.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "doc.on.doc.fill")
                        .font(.system(size: 48))
                        .foregroundColor(.blue)
                    Text("Byte-for-Byte Duplicate Finder")
                        .font(.title2)
                        .fontWeight(.semibold)
                    Text("MacMaid verifies identical file contents using fast prefix and full SHA-256 hashing. Read-only.")
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: 420)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                VStack(spacing: 0) {
                    HStack {
                        Text("\(groups.count) duplicate groups · \(MacMaidBridge.formatBytes(totalWastedBytes)) recoverable space")
                            .font(.headline)
                        Spacer()
                    }
                    .padding()
                    .background(Color(NSColor.controlBackgroundColor))

                    Divider()

                    List {
                        ForEach(groups) { grp in
                            VStack(alignment: .leading, spacing: 6) {
                                HStack {
                                    Text("Identical Files (\(grp.files.count) copies)")
                                        .fontWeight(.semibold)
                                    Spacer()
                                    Text("\(MacMaidBridge.formatBytes(grp.size)) each")
                                        .foregroundColor(.secondary)
                                }

                                Text("SHA-256: \(grp.hash)")
                                    .font(.system(.caption2, design: .monospaced))
                                    .foregroundColor(.secondary)

                                ForEach(grp.files, id: \.self) { file in
                                    HStack {
                                        Image(systemName: "doc")
                                            .font(.caption)
                                            .foregroundColor(.secondary)
                                        Text(file)
                                            .font(.caption)
                                            .lineLimit(1)
                                            .truncationMode(.middle)
                                        Spacer()
                                        Button("Reveal") {
                                            NSWorkspace.shared.selectFile(file, inFileViewerRootedAtPath: "")
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
    }

    private func startScan() {
        isScanning = true
        scannedCount = 0
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
                if let token = self.cancellationToken {
                    macmaid_cancellation_token_free(token)
                    self.cancellationToken = nil
                }
            }
        }
    }
}
