import SwiftUI

struct SmartDownloadsView: View {
    @ObservedObject var state = AppState.shared
    @State private var olderThanDays: Double = 30
    @State private var report: SmartDownloadsReportModel?
    @State private var isScanning: Bool = false

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 16) {
                HStack {
                    Text("Older than: \(Int(olderThanDays)) days")
                        .font(.caption)
                    Slider(value: $olderThanDays, in: 7...180, step: 7)
                        .frame(width: 160)
                }

                Spacer()

                Button(action: startScan) {
                    Label(state.t("Scan"), systemImage: "arrow.down.circle.fill")
                }
                .buttonStyle(.borderedProminent)
            }
            .padding()
            .background(Color(NSColor.windowBackgroundColor))

            Divider()

            if isScanning {
                VStack(spacing: 8) {
                    ProgressView()
                    Text("Categorizing Downloads...")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let rep = report {
                ScrollView {
                    VStack(alignment: .leading, spacing: 20) {
                        HStack {
                            Text("Downloads Cleanup Potential: \(MacMaidBridge.formatBytes(rep.totalBytes))")
                                .font(.title3)
                                .fontWeight(.bold)
                            Spacer()
                        }

                        // Installers Section
                        DownloadCategoryCard(title: "Installers (.dmg, .pkg, .iso)", items: rep.installers, icon: "shippingbox.fill", color: .blue)

                        // Archives Section
                        DownloadCategoryCard(title: "Archives (.zip, .tar, .7z)", items: rep.archives, icon: "doc.zipper", color: .purple)

                        // Incomplete Downloads Section
                        DownloadCategoryCard(title: "Incomplete Downloads (.crdownload, .part)", items: rep.incomplete, icon: "exclamationmark.arrow.triangle.2.circlepath", color: .orange)

                        // Duplicates Section
                        DownloadCategoryCard(title: "Duplicate Downloads (e.g. file (1).ext)", items: rep.duplicates, icon: "doc.on.doc", color: .teal)
                    }
                    .padding()
                }
            } else {
                VStack(spacing: 12) {
                    Image(systemName: "arrow.down.circle.fill")
                        .font(.system(size: 48))
                        .foregroundColor(.blue)
                    Text("Smart Downloads Categorizer")
                        .font(.title2)
                        .fontWeight(.semibold)
                    Text("Automatically groups installers, old archives, broken downloads, and duplicate copies in ~/Downloads.")
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: 420)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .onAppear(perform: startScan)
    }

    private func startScan() {
        isScanning = true
        DispatchQueue.global(qos: .userInitiated).async {
            let res = MacMaidBridge.shared.scanSmartDownloads(olderThanDays: UInt64(olderThanDays), token: nil)
            DispatchQueue.main.async {
                self.isScanning = false
                self.report = res
            }
        }
    }
}

struct DownloadCategoryCard: View {
    let title: String
    let items: [DownloadItemModel]
    let icon: String
    let color: Color

    var totalBytes: UInt64 {
        items.reduce(0) { $0 + $1.size }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Label(title, systemImage: icon)
                    .font(.headline)
                    .foregroundColor(color)
                Spacer()
                Text("\(items.count) files · \(MacMaidBridge.formatBytes(totalBytes))")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
            }

            if items.isEmpty {
                Text("No items found.")
                    .font(.caption)
                    .foregroundColor(.secondary)
            } else {
                ForEach(items.prefix(5)) { item in
                    HStack {
                        Text(item.name)
                            .font(.caption)
                            .lineLimit(1)
                        Spacer()
                        Text("\(item.ageDays)d ago")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                        Text(MacMaidBridge.formatBytes(item.size))
                            .font(.caption2)
                            .foregroundColor(.secondary)
                            .frame(width: 70, alignment: .trailing)
                    }
                }
            }
        }
        .padding()
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(10)
    }
}
