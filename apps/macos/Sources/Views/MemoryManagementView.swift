import SwiftUI
import Combine

struct ProcessGroup: Identifiable {
    var id: String { name }
    let name: String
    var totalRss: UInt64
    var totalCpu: Float
    var processes: [ProcessInfoModel]
}

struct MemoryManagementView: View {
    @ObservedObject var state = AppState.shared
    @State private var processes: [ProcessInfoModel] = []
    @State private var searchText: String = ""
    @State private var filterCategory: String = "all"
    @State private var sortColumn: String = "memory"
    @State private var sortAscending: Bool = false
    @State private var groupByApp: Bool = true
    @State private var selectedPid: UInt32?
    @State private var stagedPlan: StagedPlanModel?
    @State private var pendingProcess: ProcessInfoModel?
    @State private var showConfirmSheet: Bool = false
    @State private var alertMessage: String?
    @State private var showAlert: Bool = false
    @State private var timer = Timer.publish(every: 5, on: .main, in: .common).autoconnect()

    var selectedProcess: ProcessInfoModel? {
        guard let pid = selectedPid else { return nil }
        return processes.first { $0.pid == pid }
    }

    var filteredProcesses: [ProcessInfoModel] {
        var list = processes
        if !searchText.isEmpty {
            list = list.filter {
                $0.name.localizedCaseInsensitiveContains(searchText) ||
                String($0.pid).contains(searchText)
            }
        }
        if filterCategory != "all" {
            list = list.filter { $0.category.lowercased() == filterCategory }
        }

        list.sort { a, b in
            let res: Bool
            switch sortColumn {
            case "cpu": res = a.cpuPercent < b.cpuPercent
            case "name": res = a.name.localizedCompare(b.name) == .orderedAscending
            case "pid": res = a.pid < b.pid
            case "growth": res = a.growthBytesPerSec < b.growthBytesPerSec
            default: res = a.rssBytes < b.rssBytes
            }
            return sortAscending ? res : !res
        }
        return list
    }

    var processGroups: [ProcessGroup] {
        var groups: [String: [ProcessInfoModel]] = [:]
        for proc in filteredProcesses {
            let key = appGroupName(for: proc)
            groups[key, default: []].append(proc)
        }

        return groups.map { name, procs in
            let totalRss = procs.reduce(0) { $0 + $1.rssBytes }
            let totalCpu = procs.reduce(0.0) { $0 + $1.cpuPercent }
            return ProcessGroup(name: name, totalRss: totalRss, totalCpu: totalCpu, processes: procs)
        }.sorted { a, b in
            if sortColumn == "cpu" {
                return sortAscending ? a.totalCpu < b.totalCpu : a.totalCpu > b.totalCpu
            } else if sortColumn == "name" {
                return sortAscending ? a.name < b.name : a.name > b.name
            }
            return sortAscending ? a.totalRss < b.totalRss : a.totalRss > b.totalRss
        }
    }

    private func appGroupName(for proc: ProcessInfoModel) -> String {
        if proc.executable.contains(".app/Contents/") {
            let parts = proc.executable.components(separatedBy: ".app/Contents/")
            if let first = parts.first {
                return (first as NSString).lastPathComponent + ".app"
            }
        }
        return proc.name
    }

    var body: some View {
        VStack(spacing: 0) {
            // Controls Bar
            HStack(spacing: 12) {
                HStack {
                    Image(systemName: "magnifyingglass")
                        .foregroundColor(.secondary)
                    TextField(state.t("Filter processes..."), text: $searchText)
                        .textFieldStyle(PlainTextFieldStyle())
                }
                .padding(6)
                .background(Color(NSColor.textBackgroundColor))
                .cornerRadius(6)
                .frame(width: 220)

                Picker(state.t("Category"), selection: $filterCategory) {
                    Text(state.t("All")).tag("all")
                    Text(state.t("Applications")).tag("applications")
                    Text(state.t("Developer")).tag("developer")
                    Text(state.t("High Memory")).tag("high")
                    Text(state.t("Protected")).tag("protected")
                }
                .pickerStyle(MenuPickerStyle())
                .frame(width: 150)

                Toggle(state.t("Group by App"), isOn: $groupByApp)
                    .toggleStyle(CheckboxToggleStyle())

                Spacer()

                if let proc = selectedProcess {
                    Button(action: { prepareTerminate(proc, force: false) }) {
                        Label(state.t("Terminate (SIGTERM)"), systemImage: "xmark.circle")
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(.red)
                    .disabled(proc.isProtected)

                    Button(action: { prepareTerminate(proc, force: true) }) {
                        Label(state.t("Kill (SIGKILL)"), systemImage: "bolt.fill")
                    }
                    .buttonStyle(.bordered)
                    .tint(.red)
                    .disabled(proc.isProtected)
                }

                Button(action: refreshProcesses) {
                    Label(state.t("Refresh"), systemImage: "arrow.clockwise")
                }
            }
            .padding()
            .background(Color(NSColor.windowBackgroundColor))

            Divider()

            // Header Row
            HStack {
                Button("PID") { toggleSort("pid") }
                    .frame(width: 70, alignment: .leading)
                Button("Process / App Name") { toggleSort("name") }
                    .frame(width: 240, alignment: .leading)
                Button("RSS (Resident)") { toggleSort("memory") }
                    .frame(width: 120, alignment: .trailing)
                Button("CPU%") { toggleSort("cpu") }
                    .frame(width: 70, alignment: .trailing)
                Button("Growth Rate") { toggleSort("growth") }
                    .frame(width: 110, alignment: .trailing)
                Text("Category")
                    .frame(width: 90, alignment: .leading)
                Spacer()
            }
            .font(.caption)
            .fontWeight(.semibold)
            .foregroundColor(.secondary)
            .padding(.horizontal)
            .padding(.vertical, 8)
            .background(Color(NSColor.controlBackgroundColor))

            Divider()

            // Process View: Grouped vs Flat
            if groupByApp {
                List(selection: $selectedPid) {
                    ForEach(processGroups) { group in
                        DisclosureGroup(
                            content: {
                                ForEach(group.processes) { proc in
                                    processRow(proc)
                                        .tag(proc.pid)
                                }
                            },
                            label: {
                                HStack {
                                    Text(group.name)
                                        .fontWeight(.semibold)
                                    Text("(\(group.processes.count) procs)")
                                        .font(.caption2)
                                        .foregroundColor(.secondary)

                                    Spacer()

                                    Text(MacMaidBridge.formatBytes(group.totalRss))
                                        .font(.caption)
                                        .fontWeight(.medium)
                                        .frame(width: 120, alignment: .trailing)

                                    Text(String(format: "%.1f%%", group.totalCpu))
                                        .font(.caption)
                                        .frame(width: 70, alignment: .trailing)
                                }
                                .padding(.vertical, 2)
                            }
                        )
                    }
                }
            } else {
                List(filteredProcesses, selection: $selectedPid) { proc in
                    processRow(proc)
                        .tag(proc.pid)
                }
            }
        }
        .onAppear(perform: refreshProcesses)
        .onReceive(timer) { _ in
            refreshProcesses()
        }
        .sheet(isPresented: $showConfirmSheet) {
            if let staged = stagedPlan, let proc = pendingProcess {
                ReviewConfirmationSheet(
                    stagedPlan: staged,
                    onConfirm: { token, extraOptIn in
                        showConfirmSheet = false
                        executeTerminate(proc: proc, reviewToken: token, force: extraOptIn)
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
    private func processRow(_ proc: ProcessInfoModel) -> some View {
        HStack {
            Text("\(proc.pid)")
                .font(.system(.caption, design: .monospaced))
                .frame(width: 70, alignment: .leading)

            HStack(spacing: 6) {
                Text(proc.name)
                    .fontWeight(.medium)
                    .lineLimit(1)
                if proc.isProtected {
                    Image(systemName: "lock.shield.fill")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
            }
            .frame(width: 240, alignment: .leading)

            Text(MacMaidBridge.formatBytes(proc.rssBytes))
                .font(.callout)
                .frame(width: 120, alignment: .trailing)

            Text(String(format: "%.1f%%", proc.cpuPercent))
                .font(.caption)
                .frame(width: 70, alignment: .trailing)

            if proc.growthBytesPerSec > 1024.0 {
                Text(String(format: "+%@/s", MacMaidBridge.formatBytes(UInt64(proc.growthBytesPerSec))))
                    .font(.caption2)
                    .foregroundColor(.red)
                    .fontWeight(.bold)
                    .frame(width: 110, alignment: .trailing)
            } else {
                Text("-")
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .frame(width: 110, alignment: .trailing)
            }

            Text(proc.category)
                .font(.caption2)
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(Color.secondary.opacity(0.15))
                .cornerRadius(4)
                .frame(width: 90, alignment: .leading)

            Spacer()
        }
        .padding(.vertical, 2)
    }

    private func toggleSort(_ col: String) {
        if sortColumn == col {
            sortAscending.toggle()
        } else {
            sortColumn = col
            sortAscending = false
        }
    }

    private func refreshProcesses() {
        DispatchQueue.global(qos: .userInitiated).async {
            let list = MacMaidBridge.shared.getMemorySnapshot()
            DispatchQueue.main.async {
                self.processes = list
            }
        }
    }

    private func prepareTerminate(_ proc: ProcessInfoModel, force: Bool) {
        if proc.isProtected {
            alertMessage = "Process '\(proc.name)' is protected and cannot be terminated."
            showAlert = true
            return
        }

        struct MemoryPayload: Codable {
            let process: ProcessInfoModel
            let force: Bool
        }
        let payload = MemoryPayload(process: proc, force: force)
        guard let jsonData = try? JSONEncoder().encode(payload),
              let jsonStr = String(data: jsonData, encoding: .utf8) else {
            alertMessage = "Failed to encode process review payload"
            showAlert = true
            return
        }

        let res = MacMaidBridge.shared.stageReviewPlan(scope: "memory", payloadJson: jsonStr)
        switch res {
        case .success(let staged):
            self.pendingProcess = proc
            self.stagedPlan = staged
            self.showConfirmSheet = true
        case .failure(let err):
            self.alertMessage = "Termination review failed: \(err.message)"
            self.showAlert = true
        }
    }

    private func executeTerminate(proc: ProcessInfoModel, reviewToken: String, force: Bool) {
        DispatchQueue.global(qos: .userInitiated).async {
            let res = MacMaidBridge.shared.terminateProcess(
                pid: proc.pid,
                expectedStartTime: proc.startTime ?? 0,
                force: force,
                reviewToken: reviewToken
            )
            DispatchQueue.main.async {
                switch res {
                case .success:
                    self.alertMessage = "Successfully terminated PID \(proc.pid) (\(proc.name))."
                    self.showAlert = true
                    self.selectedPid = nil
                    self.refreshProcesses()
                case .failure(let err):
                    self.alertMessage = "Termination failed: \(err.message)"
                    self.showAlert = true
                }
            }
        }
    }
}
