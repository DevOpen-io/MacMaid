import SwiftUI
import AppKit

struct TreemapRect: Identifiable {
    let id = UUID()
    let node: AnalyzerNodeModel
    let rect: CGRect
    let color: Color
    let percentage: Double
}

struct StorageTreemapView: View {
    @ObservedObject var state = AppState.shared
    @State private var targetPath: String = "~"
    @State private var isAnalyzing: Bool = false
    @State private var report: AnalyzerReportModel?
    @State private var currentNode: AnalyzerNodeModel?
    @State private var history: [AnalyzerNodeModel] = []
    @State private var hoveredNode: AnalyzerNodeModel?
    @State private var selectedNode: AnalyzerNodeModel?
    @State private var stagedPlan: StagedPlanModel?
    @State private var pendingTrashNode: AnalyzerNodeModel?
    @State private var showConfirmSheet: Bool = false
    @State private var alertMessage: String?
    @State private var showAlert: Bool = false
    @State private var cancellationToken: OpaquePointer?

    private let palette: [Color] = [
        Color(red: 0.23, green: 0.51, blue: 0.96), // Blue
        Color(red: 0.02, green: 0.71, blue: 0.83), // Cyan
        Color(red: 0.55, green: 0.36, blue: 0.96), // Purple
        Color(red: 0.06, green: 0.73, blue: 0.51), // Emerald
        Color(red: 0.96, green: 0.62, blue: 0.04), // Amber
        Color(red: 0.93, green: 0.28, blue: 0.60), // Pink
        Color(red: 0.39, green: 0.40, blue: 0.95), // Indigo
        Color(red: 0.08, green: 0.72, blue: 0.65), // Teal
        Color(red: 0.95, green: 0.44, blue: 0.13), // Orange
        Color(red: 0.30, green: 0.69, blue: 0.31), // Green
    ]

    var body: some View {
        VStack(spacing: 0) {
            // Header / Breadcrumbs Bar
            HStack(spacing: 10) {
                if !history.isEmpty {
                    Button(action: goBack) {
                        Label(state.t("Back"), systemImage: "chevron.left")
                    }
                    .buttonStyle(.bordered)
                }

                // Breadcrumb path trail
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 4) {
                        ForEach(Array(history.enumerated()), id: \.offset) { idx, node in
                            Button(action: { jumpToHistoryIndex(idx) }) {
                                Text(node.name.isEmpty ? "~" : node.name)
                                    .font(.subheadline)
                                    .foregroundColor(.secondary)
                            }
                            .buttonStyle(.plain)

                            Image(systemName: "chevron.right")
                                .font(.caption2)
                                .foregroundColor(.secondary)
                        }

                        if let curr = currentNode {
                            Text(curr.name.isEmpty ? "~" : curr.name)
                                .font(.subheadline)
                                .fontWeight(.bold)
                            Text("(\(MacMaidBridge.formatBytes(curr.bytes)))")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                }

                Spacer()

                Button(action: startScan) {
                    Label(report == nil ? state.t("Scan Disk") : state.t("Refresh"), systemImage: "arrow.clockwise")
                }
                .buttonStyle(.borderedProminent)
            }
            .padding(.horizontal)
            .padding(.vertical, 10)
            .background(Color(NSColor.windowBackgroundColor))

            Divider()

            // Main Canvas Area
            if isAnalyzing {
                VStack(spacing: 12) {
                    ProgressView()
                    Text(state.t("Analyzing storage hierarchy for Treemap..."))
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let curr = currentNode, let children = curr.children, !children.isEmpty {
                GeometryReader { geo in
                    let rects = layoutSquarifiedTreemap(nodes: children, in: CGRect(origin: .zero, size: geo.size))
                    ZStack(alignment: .topLeading) {
                        ForEach(rects) { item in
                            treemapTile(item)
                        }
                    }
                }
                .padding(6)
            } else if report != nil {
                VStack(spacing: 12) {
                    Image(systemName: "folder")
                        .font(.system(size: 40))
                        .foregroundColor(.secondary)
                    Text(state.t("No further subdivisions in this folder."))
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                VStack(spacing: 16) {
                    Image(systemName: "square.split.2x2.fill")
                        .font(.system(size: 60))
                        .foregroundColor(.indigo)
                    Text(state.t("Visual Storage Treemap"))
                        .font(.title)
                        .fontWeight(.semibold)
                    Text(state.t("Visualize disk space consumption with interactive proportional boxes."))
                        .foregroundColor(.secondary)
                    Button(action: startScan) {
                        Label(state.t("Scan Home Directory"), systemImage: "sparkles")
                            .padding(.horizontal, 16)
                            .padding(.vertical, 8)
                    }
                    .buttonStyle(.borderedProminent)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }

            Divider()

            // Inspector / Hover Details Footer
            let activeNode = hoveredNode ?? selectedNode ?? currentNode
            HStack(spacing: 14) {
                if let node = activeNode {
                    Image(systemName: node.isDir ? "folder.fill" : "doc.fill")
                        .foregroundColor(node.isDir ? .accentColor : .secondary)
                        .font(.title3)

                    VStack(alignment: .leading, spacing: 2) {
                        HStack(spacing: 8) {
                            Text(node.name)
                                .fontWeight(.semibold)
                                .lineLimit(1)
                            Text(MacMaidBridge.formatBytes(node.bytes))
                                .font(.caption)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 1)
                                .background(Color.accentColor.opacity(0.15))
                                .foregroundColor(.accentColor)
                                .cornerRadius(4)
                        }
                        Text(node.path)
                            .font(.caption2)
                            .foregroundColor(.secondary)
                            .lineLimit(1)
                            .truncationMode(.middle)
                    }

                    Spacer()

                    if !node.path.starts_with_virtual() {
                        Button(action: { revealInFinder(node.path) }) {
                            Label(state.t("Reveal in Finder"), systemImage: "macwindow")
                        }
                        .buttonStyle(.bordered)

                        Button(action: { prepareTrash(node) }) {
                            Label(state.t("Move to Trash"), systemImage: "trash")
                        }
                        .buttonStyle(.bordered)
                        .tint(.red)
                    }
                } else {
                    Text(state.t("Hover or click a block to inspect details and actions."))
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Spacer()
                }
            }
            .padding(.horizontal)
            .padding(.vertical, 8)
            .background(Color(NSColor.windowBackgroundColor))
        }
        .onAppear {
            if report == nil {
                startScan()
            }
        }
        .sheet(isPresented: $showConfirmSheet) {
            if let staged = stagedPlan, let node = pendingTrashNode {
                ReviewConfirmationSheet(
                    stagedPlan: staged,
                    onConfirm: { token, _ in
                        showConfirmSheet = false
                        executeTrash(node: node, reviewToken: token)
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

    @ViewBuilder
    private func treemapTile(_ item: TreemapRect) -> some View {
        let isSelected = selectedNode?.id == item.node.id
        let isHovered = hoveredNode?.id == item.node.id
        let pad: CGFloat = (item.rect.width > 30 && item.rect.height > 30) ? 2 : 1

        ZStack(alignment: .topLeading) {
            RoundedRectangle(cornerRadius: 4)
                .fill(item.color.opacity(isHovered ? 0.95 : (isSelected ? 0.90 : 0.80)))
                .overlay(
                    RoundedRectangle(cornerRadius: 4)
                        .stroke(isSelected ? Color.white : (isHovered ? Color.white.opacity(0.8) : Color.black.opacity(0.2)), lineWidth: isSelected ? 2 : 1)
                )

            // Content within tile
            if item.rect.width > 45 && item.rect.height > 26 {
                VStack(alignment: .leading, spacing: 2) {
                    Text(item.node.name)
                        .font(.system(size: item.rect.width > 90 ? 12 : 10, weight: .bold))
                        .foregroundColor(.white)
                        .lineLimit(1)
                        .shadow(color: Color.black.opacity(0.6), radius: 1, x: 0, y: 1)

                    if item.rect.height > 40 {
                        Text("\(MacMaidBridge.formatBytes(item.node.bytes)) · \(String(format: "%.1f%%", item.percentage))")
                            .font(.system(size: 9))
                            .foregroundColor(.white.opacity(0.9))
                            .lineLimit(1)
                            .shadow(color: Color.black.opacity(0.6), radius: 1, x: 0, y: 1)
                    }

                    if item.rect.width > 120 && item.rect.height > 75 && !item.node.path.starts_with_virtual() {
                        HStack(spacing: 6) {
                            Button(action: { revealInFinder(item.node.path) }) {
                                Text("Finder")
                                    .font(.system(size: 9, weight: .medium))
                                    .padding(.horizontal, 4)
                                    .padding(.vertical, 2)
                                    .background(Color.black.opacity(0.3))
                                    .foregroundColor(.white)
                                    .cornerRadius(3)
                            }
                            .buttonStyle(.plain)

                            if item.node.isDir && item.node.children?.isEmpty == false {
                                Button(action: { drillDown(item.node) }) {
                                    Text("Drill down")
                                        .font(.system(size: 9, weight: .medium))
                                        .padding(.horizontal, 4)
                                        .padding(.vertical, 2)
                                        .background(Color.black.opacity(0.3))
                                        .foregroundColor(.white)
                                        .cornerRadius(3)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                        .padding(.top, 2)
                    }
                }
                .padding(4)
            }
        }
        .frame(width: max(0, item.rect.width - pad * 2), height: max(0, item.rect.height - pad * 2))
        .position(x: item.rect.midX, y: item.rect.midY)
        .onHover { hovering in
            if hovering {
                hoveredNode = item.node
            } else if hoveredNode?.id == item.node.id {
                hoveredNode = nil
            }
        }
        .onTapGesture {
            selectedNode = item.node
        }
        .simultaneousGesture(
            TapGesture(count: 2).onEnded {
                if item.node.isDir && item.node.children?.isEmpty == false {
                    drillDown(item.node)
                }
            }
        )
        .contextMenu {
            if !item.node.path.starts_with_virtual() {
                Button(action: { revealInFinder(item.node.path) }) {
                    Label(state.t("Reveal in Finder"), systemImage: "macwindow")
                }
                if item.node.isDir && item.node.children?.isEmpty == false {
                    Button(action: { drillDown(item.node) }) {
                        Label(state.t("Drill Down"), systemImage: "arrow.down.right.and.arrow.up.left")
                    }
                }
                Divider()
                Button(role: .destructive, action: { prepareTrash(item.node) }) {
                    Label(state.t("Move to Trash"), systemImage: "trash")
                }
            }
        }
    }

    private func drillDown(_ node: AnalyzerNodeModel) {
        if let curr = currentNode {
            history.append(curr)
        }
        currentNode = node
        selectedNode = nil
        hoveredNode = nil
    }

    private func goBack() {
        if let prev = history.popLast() {
            currentNode = prev
            selectedNode = nil
            hoveredNode = nil
        }
    }

    private func jumpToHistoryIndex(_ idx: Int) {
        guard idx < history.count else { return }
        let target = history[idx]
        history = Array(history[0..<idx])
        currentNode = target
        selectedNode = nil
        hoveredNode = nil
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
                self.selectedNode = nil
                self.hoveredNode = nil
                if let token = self.cancellationToken {
                    macmaid_cancellation_token_free(token)
                    self.cancellationToken = nil
                }
            }
        }
    }

    private func revealInFinder(_ path: String) {
        let url = URL(fileURLWithPath: path)
        NSWorkspace.shared.activateFileViewerSelecting([url])
    }

    private func prepareTrash(_ node: AnalyzerNodeModel) {
        struct AnalyzerTrashPayload: Codable {
            let paths: [String]
            let estimatedBytes: UInt64
        }
        let payload = AnalyzerTrashPayload(paths: [node.path], estimatedBytes: node.bytes)
        guard let jsonData = try? JSONEncoder().encode(payload),
              let jsonStr = String(data: jsonData, encoding: .utf8) else {
            alertMessage = "Failed to encode trash payload"
            showAlert = true
            return
        }

        let res = MacMaidBridge.shared.stageReviewPlan(scope: "analyzer", payloadJson: jsonStr)
        switch res {
        case .success(let staged):
            self.pendingTrashNode = node
            self.stagedPlan = staged
            self.showConfirmSheet = true
        case .failure(let err):
            self.alertMessage = "Trash review failed: \(err.message)"
            self.showAlert = true
        }
    }

    private func executeTrash(node: AnalyzerNodeModel, reviewToken: String) {
        DispatchQueue.global(qos: .userInitiated).async {
            let res = MacMaidBridge.shared.moveAnalyzerItemToTrash(
                path: node.path,
                estimatedBytes: node.bytes,
                reviewToken: reviewToken
            )
            DispatchQueue.main.async {
                switch res {
                case .success(let dest):
                    self.alertMessage = "Moved '\(node.name)' to Trash (\(dest))."
                    self.showAlert = true
                    self.startScan()
                case .failure(let err):
                    self.alertMessage = "Move to Trash failed: \(err.message)"
                    self.showAlert = true
                }
            }
        }
    }

    // MARK: - Recursive Binary Space Partitioning Treemap
    private func layoutSquarifiedTreemap(nodes: [AnalyzerNodeModel], in bounds: CGRect) -> [TreemapRect] {
        guard bounds.width > 4 && bounds.height > 4 else { return [] }

        let validNodes = nodes
            .filter { $0.bytes > 0 }
            .sorted { $0.bytes > $1.bytes }

        let totalBytes = Double(validNodes.reduce(0) { $0 + $1.bytes })
        guard totalBytes > 0 else { return [] }

        // Group items < 0.5% into "Other" node to prevent razor-thin slivers
        var primaryNodes: [AnalyzerNodeModel] = []
        var otherNodes: [AnalyzerNodeModel] = []

        for node in validNodes {
            let ratio = Double(node.bytes) / totalBytes
            if ratio >= 0.005 || primaryNodes.count < 6 {
                primaryNodes.append(node)
            } else {
                otherNodes.append(node)
            }
        }

        if !otherNodes.isEmpty {
            let otherTotal = otherNodes.reduce(0) { $0 + $1.bytes }
            let otherVirtual = AnalyzerNodeModel(
                name: "Other (\(otherNodes.count) items)",
                path: "virtual:other",
                bytes: otherTotal,
                isDir: true,
                itemCount: otherNodes.count,
                children: otherNodes
            )
            primaryNodes.append(otherVirtual)
        }

        var results: [TreemapRect] = []
        splitTreemapItems(
            nodes: primaryNodes,
            x: bounds.minX,
            y: bounds.minY,
            width: bounds.width,
            height: bounds.height,
            totalBytes: totalBytes,
            out: &results
        )

        return results
    }

    private func splitTreemapItems(
        nodes: [AnalyzerNodeModel],
        x: CGFloat,
        y: CGFloat,
        width: CGFloat,
        height: CGFloat,
        totalBytes: Double,
        out: inout [TreemapRect]
    ) {
        guard !nodes.isEmpty, width >= 1, height >= 1 else { return }

        if nodes.count == 1 {
            let node = nodes[0]
            let color = colorForNode(node)
            let pct = totalBytes > 0 ? (Double(node.bytes) / totalBytes) * 100.0 : 0.0
            out.append(TreemapRect(
                node: node,
                rect: CGRect(x: x, y: y, width: width, height: height),
                color: color,
                percentage: pct
            ))
            return
        }

        let total = Double(nodes.reduce(0) { $0 + $1.bytes })
        guard total > 0 else { return }

        var running: Double = 0
        var splitIndex: Int = 1
        for i in 0..<(nodes.count - 1) {
            let next = running + Double(nodes[i].bytes)
            if abs(total / 2.0 - next) <= abs(total / 2.0 - running) {
                running = next
                splitIndex = i + 1
            } else {
                break
            }
        }

        let first = Array(nodes[0..<splitIndex])
        let second = Array(nodes[splitIndex...])
        let firstTotal = Double(first.reduce(0) { $0 + $1.bytes })
        let ratio = CGFloat(firstTotal / total)

        if width >= height {
            let firstWidth = max(1, round(width * ratio))
            splitTreemapItems(nodes: first, x: x, y: y, width: firstWidth, height: height, totalBytes: totalBytes, out: &out)
            splitTreemapItems(nodes: second, x: x + firstWidth, y: y, width: width - firstWidth, height: height, totalBytes: totalBytes, out: &out)
        } else {
            let firstHeight = max(1, round(height * ratio))
            splitTreemapItems(nodes: first, x: x, y: y, width: width, height: firstHeight, totalBytes: totalBytes, out: &out)
            splitTreemapItems(nodes: second, x: x, y: y + firstHeight, width: width, height: height - firstHeight, totalBytes: totalBytes, out: &out)
        }
    }

    private func colorForNode(_ node: AnalyzerNodeModel) -> Color {
        if node.path.starts_with_virtual() {
            return Color.gray
        }
        var hasher = Hasher()
        hasher.combine(node.name)
        let hashVal = abs(hasher.finalize())
        return palette[hashVal % palette.count]
    }
}

private extension String {
    func starts_with_virtual() -> Bool {
        self.starts(with: "virtual:")
    }
}
