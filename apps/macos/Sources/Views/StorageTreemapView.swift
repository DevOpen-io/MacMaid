import SwiftUI

struct TreemapRect: Identifiable {
    let id = UUID()
    let node: AnalyzerNodeModel
    let rect: CGRect
    let color: Color
}

struct StorageTreemapView: View {
    @ObservedObject var state = AppState.shared
    @State private var targetPath: String = "~"
    @State private var isAnalyzing: Bool = false
    @State private var report: AnalyzerReportModel?
    @State private var currentNode: AnalyzerNodeModel?
    @State private var history: [AnalyzerNodeModel] = []
    @State private var hoveredNode: AnalyzerNodeModel?
    @State private var cancellationToken: OpaquePointer?

    private let palette: [Color] = [
        Color.blue, Color.purple, Color.indigo, Color.teal, Color.cyan,
        Color.orange, Color.pink, Color.mint, Color.yellow, Color.green
    ]

    var body: some View {
        VStack(spacing: 0) {
            // Header bar
            HStack {
                if !history.isEmpty {
                    Button(action: goBack) {
                        Label("Back", systemImage: "chevron.left")
                    }
                    .buttonStyle(.bordered)
                }

                if let curr = currentNode {
                    Text(curr.path)
                        .font(.headline)
                        .lineLimit(1)
                    Text("(\(MacMaidBridge.formatBytes(curr.bytes)))")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                } else {
                    Text("Storage Treemap")
                        .font(.headline)
                }

                Spacer()

                if let hovered = hoveredNode {
                    Text("\(hovered.name) · \(MacMaidBridge.formatBytes(hovered.bytes))")
                        .font(.callout)
                        .fontWeight(.medium)
                        .foregroundColor(.accentColor)
                }

                Button(action: startScan) {
                    Label(report == nil ? "Generate Treemap" : state.t("Refresh"), systemImage: "arrow.clockwise")
                }
                .buttonStyle(.borderedProminent)
            }
            .padding()
            .background(Color(NSColor.windowBackgroundColor))

            Divider()

            // Main Canvas / Visualization Area
            if isAnalyzing {
                VStack(spacing: 12) {
                    ProgressView()
                    Text("Analyzing storage hierarchy for Treemap...")
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let curr = currentNode, let children = curr.children, !children.isEmpty {
                GeometryReader { geo in
                    let rects = layoutTreemap(nodes: children, in: CGRect(origin: .zero, size: geo.size))
                    ZStack(alignment: .topLeading) {
                        ForEach(rects) { item in
                            Rectangle()
                                .fill(item.color.opacity(0.85))
                                .border(Color.black.opacity(0.2), width: 1)
                                .frame(width: max(0, item.rect.width), height: max(0, item.rect.height))
                                .position(x: item.rect.midX, y: item.rect.midY)
                                .overlay(
                                    VStack(alignment: .leading, spacing: 2) {
                                        if item.rect.width > 50 && item.rect.height > 30 {
                                            Text(item.node.name)
                                                .font(.caption)
                                                .fontWeight(.bold)
                                                .foregroundColor(.white)
                                                .lineLimit(1)
                                            if item.rect.height > 45 {
                                                Text(MacMaidBridge.formatBytes(item.node.bytes))
                                                    .font(.caption2)
                                                    .foregroundColor(.white.opacity(0.85))
                                            }
                                        }
                                    }
                                    .padding(4)
                                    .position(x: item.rect.midX, y: item.rect.midY)
                                )
                                .onHover { isHovered in
                                    if isHovered {
                                        hoveredNode = item.node
                                    } else if hoveredNode?.id == item.node.id {
                                        hoveredNode = nil
                                    }
                                }
                                .onTapGesture {
                                    if item.node.isDir && item.node.children?.isEmpty == false {
                                        history.append(curr)
                                        currentNode = item.node
                                    }
                                }
                        }
                    }
                }
                .padding(8)
            } else if report != nil {
                VStack(spacing: 8) {
                    Text("No further subdivisions in this folder.")
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                VStack(spacing: 16) {
                    Image(systemName: "square.split.2x2.fill")
                        .font(.system(size: 60))
                        .foregroundColor(.indigo)
                    Text("Visual Storage Treemap")
                        .font(.title)
                        .fontWeight(.semibold)
                    Text("Visualize disk space consumption with interactive proportional boxes.")
                        .foregroundColor(.secondary)
                    Button(action: startScan) {
                        Label("Scan Home Directory", systemImage: "sparkles")
                            .padding(.horizontal, 16)
                            .padding(.vertical, 8)
                    }
                    .buttonStyle(.borderedProminent)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .onAppear {
            if report == nil {
                startScan()
            }
        }
    }

    private func goBack() {
        if let prev = history.popLast() {
            currentNode = prev
        }
    }

    private func startScan() {
        isAnalyzing = true
        cancellationToken = macmaid_cancellation_token_new()

        DispatchQueue.global(qos: .userInitiated).async {
            let res = MacMaidBridge.shared.analyzeDirectory(
                path: targetPath,
                topLimit: 100,
                minSize: 5_000_000,
                token: cancellationToken
            ) { _, _ in }

            DispatchQueue.main.async {
                self.isAnalyzing = false
                self.report = res
                self.currentNode = res?.tree
                self.history.removeAll()
                if let token = self.cancellationToken {
                    macmaid_cancellation_token_free(token)
                    self.cancellationToken = nil
                }
            }
        }
    }

    // Squarified/Slice-and-dice treemap algorithm
    private func layoutTreemap(nodes: [AnalyzerNodeModel], in bounds: CGRect) -> [TreemapRect] {
        var results: [TreemapRect] = []
        guard bounds.width > 2 && bounds.height > 2 else { return results }

        let validNodes = nodes.filter { $0.bytes > 0 }
        let totalBytes = Double(validNodes.reduce(0) { $0 + $1.bytes })
        guard totalBytes > 0 else { return results }

        var currentBounds = bounds
        let isHorizontal = currentBounds.width >= currentBounds.height

        for (idx, node) in validNodes.enumerated() {
            let ratio = Double(node.bytes) / totalBytes
            let color = palette[idx % palette.count]

            if isHorizontal {
                let w = currentBounds.width * CGFloat(ratio)
                let itemRect = CGRect(x: currentBounds.minX, y: currentBounds.minY, width: w, height: currentBounds.height)
                results.push_rect(node: node, rect: itemRect, color: color)
                currentBounds = CGRect(x: currentBounds.minX + w, y: currentBounds.minY, width: currentBounds.width - w, height: currentBounds.height)
            } else {
                let h = currentBounds.height * CGFloat(ratio)
                let itemRect = CGRect(x: currentBounds.minX, y: currentBounds.minY, width: currentBounds.width, height: h)
                results.push_rect(node: node, rect: itemRect, color: color)
                currentBounds = CGRect(x: currentBounds.minX, y: currentBounds.minY + h, width: currentBounds.width, height: currentBounds.height - h)
            }
        }

        return results
    }
}

private extension Array where Element == TreemapRect {
    mutating func push_rect(node: AnalyzerNodeModel, rect: CGRect, color: Color) {
        if rect.width > 1 && rect.height > 1 {
            self.append(TreemapRect(node: node, rect: rect, color: color))
        }
    }
}
