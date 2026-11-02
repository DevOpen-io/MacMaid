import SwiftUI
import Combine

struct MemoryManagementView: View {
    @ObservedObject var state = AppState.shared
    @State private var processes: [ProcessInfoModel] = []
    @State private var searchText: String = ""
    @State private var filterCategory: String = "all"
    @State private var sortColumn: String = "memory"
    @State private var sortAscending: Bool = false
    @State private var selectedPid: UInt32?
    @State private var alertMessage: String?
    @State private var showAlert: Bool = false
    @State private var timer = Timer.publish(every: 5, on: .main, in: .common).autoconnect()

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

    var body: some View {
        VStack(spacing: 0) {
            // Controls Bar
            HStack(spacing: 12) {
                HStack {
                    Image(systemName: "magnifyingglass")
                        .foregroundColor(.secondary)
                    TextField("Filter processes...", text: $searchText)
                        .textFieldStyle(PlainTextFieldStyle())
                }
                .padding(6)
                .background(Color(NSColor.textBackgroundColor))
                .cornerRadius(6)
                .frame(width: 240)

                Picker("Category", selection: $filterCategory) {
                    Text("All").tag("all")
                    Text("Applications").tag("applications")
                    Text("Developer").tag("developer")
                    Text("High Memory").tag("high")
                    Text("Protected").tag("protected")
                }
                .pickerStyle(MenuPickerStyle())
                .frame(width: 160)

                Spacer()

                if let pid = selectedPid {
                    Button("Terminate PID \(pid)") {
                        terminateProcess(pid: pid)
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(.red)
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
                Button("Name") { toggleSort("name") }
                    .frame(width: 220, alignment: .leading)
                Button("Memory") { toggleSort("memory") }
                    .frame(width: 110, alignment: .trailing)
                Button("CPU%") { toggleSort("cpu") }
                    .frame(width: 70, alignment: .trailing)
                Button("Growth") { toggleSort("growth") }
                    .frame(width: 110, alignment: .trailing)
                Text("Category")
                    .frame(width: 100, alignment: .leading)
                Spacer()
            }
            .font(.caption)
            .fontWeight(.semibold)
            .foregroundColor(.secondary)
            .padding(.horizontal)
            .padding(.vertical, 8)
            .background(Color(NSColor.controlBackgroundColor))

            Divider()

            // Process Table
            List(filteredProcesses, selection: $selectedPid) { proc in
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
                    .frame(width: 220, alignment: .leading)

                    Text(MacMaidBridge.formatBytes(proc.rssBytes))
                        .font(.callout)
                        .frame(width: 110, alignment: .trailing)

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
                        .frame(width: 100, alignment: .leading)

                    Spacer()
                }
                .tag(proc.pid)
                .padding(.vertical, 2)
            }
        }
        .onAppear(perform: refreshProcesses)
        .onReceive(timer) { _ in
            refreshProcesses()
        }
        .alert(isPresented: $showAlert) {
            Alert(title: Text("Notice"), message: Text(alertMessage ?? ""), dismissButton: .default(Text("OK")))
        }
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

    private func terminateProcess(pid: UInt32) {
        DispatchQueue.global(qos: .userInitiated).async {
            let res = MacMaidBridge.shared.terminateProcess(pid: pid)
            DispatchQueue.main.async {
                switch res {
                case .success:
                    self.alertMessage = "Successfully terminated PID \(pid)."
                    self.showAlert = true
                    self.refreshProcesses()
                case .failure(let err):
                    self.alertMessage = "Termination failed: \(err)"
                    self.showAlert = true
                }
            }
        }
    }
}
