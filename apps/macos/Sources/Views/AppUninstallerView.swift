import SwiftUI
import AppKit

struct AppUninstallerView: View {
    @ObservedObject var state = AppState.shared
    @State private var apps: [InstalledAppModel] = []
    @State private var selectedApp: InstalledAppModel?
    @State private var components: [AppComponentModel] = []
    @State private var selectedComponentPaths: Set<String> = []
    @State private var searchText: String = ""
    @State private var isLoading: Bool = false
    @State private var isUninstalling: Bool = false
    @State private var stagedPlan: StagedPlanModel?
    @State private var showConfirmSheet: Bool = false
    @State private var alertMessage: String?
    @State private var showAlert: Bool = false
    @State private var cancellationToken: OpaquePointer?

    var filteredApps: [InstalledAppModel] {
        if searchText.isEmpty { return apps }
        return apps.filter {
            $0.name.localizedCaseInsensitiveContains(searchText) ||
            $0.bundleId.localizedCaseInsensitiveContains(searchText)
        }
    }

    var totalReclaimBytes: UInt64 {
        let appBytes = selectedApp?.bytes ?? 0
        let compBytes = components.filter { selectedComponentPaths.contains($0.path) }.reduce(0) { $0 + $1.bytes }
        return appBytes + compBytes
    }

    var body: some View {
        HSplitView {
            // Left: Apps list
            VStack(spacing: 0) {
                HStack {
                    Image(systemName: "magnifyingglass")
                        .foregroundColor(.secondary)
                    TextField("Search applications...", text: $searchText)
                        .textFieldStyle(PlainTextFieldStyle())
                }
                .padding(8)
                .background(Color(NSColor.textBackgroundColor))
                .cornerRadius(6)
                .padding(10)

                Divider()

                if isLoading {
                    VStack {
                        ProgressView()
                        Text("Discovering applications...")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    List(filteredApps, selection: $selectedApp) { app in
                        HStack(spacing: 12) {
                            Image(nsImage: NSWorkspace.shared.icon(forFile: app.path))
                                .resizable()
                                .frame(width: 32, height: 32)

                            VStack(alignment: .leading, spacing: 2) {
                                HStack {
                                    Text(app.name)
                                        .fontWeight(.medium)
                                        .lineLimit(1)
                                    if app.brewCask != nil {
                                        Text("brew")
                                            .font(.caption2)
                                            .padding(.horizontal, 4)
                                            .padding(.vertical, 1)
                                            .background(Color.orange.opacity(0.15))
                                            .foregroundColor(.orange)
                                            .cornerRadius(3)
                                    }
                                }

                                Text(app.bundleId)
                                    .font(.caption2)
                                    .foregroundColor(.secondary)
                                    .lineLimit(1)
                            }

                            Spacer()

                            Text(MacMaidBridge.formatBytes(app.bytes))
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                        .padding(.vertical, 4)
                        .tag(app)
                    }
                }
            }
            .frame(minWidth: 320, idealWidth: 360)

            // Right: Selected app details and leftovers
            VStack(spacing: 0) {
                if let app = selectedApp {
                    VStack(alignment: .leading, spacing: 16) {
                        HStack(spacing: 16) {
                            Image(nsImage: NSWorkspace.shared.icon(forFile: app.path))
                                .resizable()
                                .frame(width: 48, height: 48)
                            VStack(alignment: .leading, spacing: 4) {
                                Text(app.name)
                                    .font(.title2)
                                    .fontWeight(.bold)
                                Text("Version \(app.version) · \(app.bundleId)")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                                Text(app.path)
                                    .font(.caption2)
                                    .foregroundColor(.secondary)
                            }
                            Spacer()
                            Button(action: prepareUninstall) {
                                Label(state.t("Uninstall"), systemImage: "trash.fill")
                            }
                            .buttonStyle(.borderedProminent)
                            .tint(.red)
                        }
                        .padding()
                        .background(Color(NSColor.controlBackgroundColor))

                        Divider()

                        Text("Application Components & Leftovers")
                            .font(.headline)
                            .padding(.horizontal)
                            .padding(.top, 8)

                        if components.isEmpty {
                            Text("No additional Library leftovers detected for this bundle.")
                                .foregroundColor(.secondary)
                                .font(.caption)
                                .padding()
                        } else {
                            List {
                                ForEach(components) { comp in
                                    HStack {
                                        Toggle(isOn: Binding(
                                            get: { selectedComponentPaths.contains(comp.path) },
                                            set: { if $0 { selectedComponentPaths.insert(comp.path) } else { selectedComponentPaths.remove(comp.path) } }
                                        )) {
                                            EmptyView()
                                        }
                                        .labelsHidden()

                                        VStack(alignment: .leading, spacing: 2) {
                                            HStack {
                                                Text(comp.label)
                                                    .fontWeight(.medium)
                                                Spacer()
                                                Text(MacMaidBridge.formatBytes(comp.bytes))
                                                    .foregroundColor(.secondary)
                                            }
                                            Text(comp.path)
                                                .font(.caption2)
                                                .foregroundColor(.secondary)
                                                .lineLimit(1)
                                        }
                                    }
                                }
                            }
                        }
                    }
                } else {
                    VStack(spacing: 12) {
                        Image(systemName: "app.badge.xmark")
                            .font(.system(size: 48))
                            .foregroundColor(.secondary)
                        Text("Select an application to view bundle info and leftover components.")
                            .foregroundColor(.secondary)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
            .frame(minWidth: 400)
        }
        .onAppear(perform: loadApplications)
        .onChange(of: selectedApp?.id) { _ in
            loadComponents()
        }
        .sheet(isPresented: $showConfirmSheet) {
            if let staged = stagedPlan {
                ReviewConfirmationSheet(
                    stagedPlan: staged,
                    onConfirm: { token, extraOptIn in
                        showConfirmSheet = false
                        executeUninstall(reviewToken: token, allowUserData: extraOptIn)
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

    private func loadApplications() {
        isLoading = true
        DispatchQueue.global(qos: .userInitiated).async {
            let list = MacMaidBridge.shared.scanApplications(token: nil)
            DispatchQueue.main.async {
                self.apps = list
                self.isLoading = false
            }
        }
    }

    private func loadComponents() {
        guard let app = selectedApp else {
            components = []
            selectedComponentPaths = []
            return
        }

        DispatchQueue.global(qos: .userInitiated).async {
            let comps = MacMaidBridge.shared.scanAppComponents(bundleId: app.bundleId)
            DispatchQueue.main.async {
                self.components = comps
                self.selectedComponentPaths = Set(comps.filter { $0.selected }.map { $0.path })
            }
        }
    }

    private func prepareUninstall() {
        guard let app = selectedApp else { return }
        let selectedComps = components.filter { selectedComponentPaths.contains($0.path) }

        struct UninstallPayload: Codable {
            let app: InstalledAppModel
            let components: [AppComponentModel]
        }
        let payload = UninstallPayload(app: app, components: selectedComps)
        guard let jsonData = try? JSONEncoder().encode(payload),
              let jsonStr = String(data: jsonData, encoding: .utf8) else {
            alertMessage = "Failed to encode uninstall review payload"
            showAlert = true
            return
        }

        let res = MacMaidBridge.shared.stageReviewPlan(scope: "apps", payloadJson: jsonStr)
        switch res {
        case .success(let staged):
            self.stagedPlan = staged
            self.showConfirmSheet = true
        case .failure(let err):
            self.alertMessage = "Uninstall review failed: \(err.message)"
            self.showAlert = true
        }
    }

    private func executeUninstall(reviewToken: String, allowUserData: Bool) {
        guard let app = selectedApp else { return }
        isUninstalling = true

        DispatchQueue.global(qos: .userInitiated).async {
            let res = MacMaidBridge.shared.uninstallApplication(
                app: app,
                components: Array(selectedComponentPaths),
                reviewToken: reviewToken,
                allowUserData: allowUserData
            )

            DispatchQueue.main.async {
                self.isUninstalling = false
                switch res {
                case .success(let reclaimed):
                    alertMessage = "Successfully uninstalled \(app.name). Reclaimed \(MacMaidBridge.formatBytes(reclaimed))."
                    showAlert = true
                    selectedApp = nil
                    loadApplications()
                case .failure(let err):
                    alertMessage = "Uninstall failed: \(err.message)"
                    showAlert = true
                }
            }
        }
    }
}
