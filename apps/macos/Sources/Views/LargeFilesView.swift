import SwiftUI
import AppKit

struct LargeFilesView: View {
    @ObservedObject var state = AppState.shared
    @State private var searchPath: String = "~"
    @State private var minSizeOption: UInt64 = 500 * 1024 * 1024 // 500MB
    @State private var olderThanDays: UInt64 = 0 // Any age
    @State private var files: [LargeOldFileModel] = []
    @State private var isScanning: Bool = false
    @State private var cancellationToken: OpaquePointer?

    var totalBytes: UInt64 {
        files.reduce(0) { $0 + $1.size }
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
                .frame(width: 200)

                Picker("Min Size", selection: $minSizeOption) {
                    Text("100 MB").tag(UInt64(100 * 1024 * 1024))
                    Text("500 MB").tag(UInt64(500 * 1024 * 1024))
                    Text("1 GB").tag(UInt64(1024 * 1024 * 1024))
                    Text("5 GB").tag(UInt64(5 * 1024 * 1024 * 1024))
                }
                .frame(width: 130)

                Picker("Age", selection: $olderThanDays) {
                    Text("Any Time").tag(UInt64(0))
                    Text("> 30 Days").tag(UInt64(30))
                    Text("> 90 Days").tag(UInt64(90))
                    Text("> 180 Days").tag(UInt64(180))
                    Text("> 1 Year").tag(UInt64(365))
                }
                .frame(width: 140)

                Spacer()

                Button(action: startScan) {
                    Label(state.t("Scan"), systemImage: "arrow.up.bin.fill")
                }
                .buttonStyle(.borderedProminent)
            }
            .padding()
            .background(Color(NSColor.windowBackgroundColor))

            Divider()

            if isScanning {
                VStack(spacing: 8) {
                    ProgressView()
                    Text("Scanning large and old files...")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if files.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "arrow.up.bin.fill")
                        .font(.system(size: 48))
                        .foregroundColor(.blue)
                    Text("Large & Old User Files")
                        .font(.title2)
                        .fontWeight(.semibold)
                    Text("Filter files by minimum size and modification age.")
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                VStack(spacing: 0) {
                    HStack {
                        Text("\(files.count) files · \(MacMaidBridge.formatBytes(totalBytes))")
                            .font(.headline)
                        Spacer()
                    }
                    .padding()
                    .background(Color(NSColor.controlBackgroundColor))

                    Divider()

                    List(files) { f in
                        HStack {
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

                            Button("Reveal") {
                                NSWorkspace.shared.selectFile(f.path, inFileViewerRootedAtPath: "")
                            }
                            .buttonStyle(.borderless)
                            .font(.caption)
                        }
                        .padding(.vertical, 2)
                    }
                }
            }
        }
    }

    private func startScan() {
        isScanning = true
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
}
