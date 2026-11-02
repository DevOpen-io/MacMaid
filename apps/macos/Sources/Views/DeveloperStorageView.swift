import SwiftUI

struct DeveloperStorageView: View {
    @ObservedObject var state = AppState.shared
    @State private var sections: [DeveloperSectionModel] = []
    @State private var isLoading: Bool = false
    @State private var stagedPlan: StagedPlanModel?
    @State private var pendingSection: DeveloperSectionModel?
    @State private var showConfirmSheet: Bool = false
    @State private var alertMessage: String?
    @State private var showAlert: Bool = false

    var totalBytes: UInt64 {
        sections.reduce(0) { $0 + $1.bytes }
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Developer Storage")
                        .font(.title2)
                        .fontWeight(.bold)
                    Text("Total detected: \(MacMaidBridge.formatBytes(totalBytes)) across Xcode, Cargo, Node, Docker, etc.")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }

                Spacer()

                Button(action: loadStorage) {
                    Label(state.t("Refresh"), systemImage: "arrow.clockwise")
                }
            }
            .padding()
            .background(Color(NSColor.windowBackgroundColor))

            Divider()

            if isLoading {
                VStack(spacing: 8) {
                    ProgressView()
                    Text("Scanning developer storage locations...")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollView {
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 320), spacing: 16)], spacing: 16) {
                        ForEach(sections) { sec in
                            VStack(alignment: .leading, spacing: 12) {
                                HStack {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(sec.name)
                                            .font(.headline)
                                        Text(sec.description)
                                            .font(.caption)
                                            .foregroundColor(.secondary)
                                            .lineLimit(2)
                                    }
                                    Spacer()
                                    Text(MacMaidBridge.formatBytes(sec.bytes))
                                        .font(.title3)
                                        .fontWeight(.semibold)
                                }

                                if let p = sec.path {
                                    Text(p)
                                        .font(.caption2)
                                        .foregroundColor(.secondary)
                                        .lineLimit(1)
                                        .truncationMode(.middle)
                                }

                                HStack {
                                    Spacer()
                                    if sec.cleanable {
                                        Button(state.t("Clean")) {
                                            prepareClean(sec)
                                        }
                                        .buttonStyle(.borderedProminent)
                                        .tint(.red)
                                        .disabled(sec.bytes == 0)
                                    } else {
                                        Text(state.t("Managed tool / runtime"))
                                            .font(.caption2)
                                            .foregroundColor(.secondary)
                                    }
                                }
                            }
                            .padding()
                            .background(Color(NSColor.controlBackgroundColor))
                            .cornerRadius(10)
                            .shadow(color: Color.black.opacity(0.04), radius: 2, y: 1)
                        }
                    }
                    .padding()
                }
            }
        }
        .onAppear(perform: loadStorage)
        .sheet(isPresented: $showConfirmSheet) {
            if let staged = stagedPlan, let sec = pendingSection {
                ReviewConfirmationSheet(
                    stagedPlan: staged,
                    onConfirm: { token, _ in
                        showConfirmSheet = false
                        executeClean(section: sec, reviewToken: token)
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

    private func loadStorage() {
        isLoading = true
        DispatchQueue.global(qos: .userInitiated).async {
            let list = MacMaidBridge.shared.getDeveloperStorage(token: nil)
            DispatchQueue.main.async {
                self.sections = list
                self.isLoading = false
            }
        }
    }

    private func prepareClean(_ section: DeveloperSectionModel) {
        guard let jsonData = try? JSONEncoder().encode(section),
              let jsonStr = String(data: jsonData, encoding: .utf8) else {
            alertMessage = "Failed to encode section payload"
            showAlert = true
            return
        }

        let res = MacMaidBridge.shared.stageReviewPlan(scope: "developer", payloadJson: jsonStr)
        switch res {
        case .success(let staged):
            self.pendingSection = section
            self.stagedPlan = staged
            self.showConfirmSheet = true
        case .failure(let err):
            self.alertMessage = "Developer review staging failed: \(err.message)"
            self.showAlert = true
        }
    }

    private func executeClean(section: DeveloperSectionModel, reviewToken: String) {
        DispatchQueue.global(qos: .userInitiated).async {
            let res = MacMaidBridge.shared.cleanDeveloperSection(section: section, reviewToken: reviewToken)
            DispatchQueue.main.async {
                switch res {
                case .success(let reclaimed):
                    self.alertMessage = "Cleaned \(section.name). Reclaimed \(MacMaidBridge.formatBytes(reclaimed))."
                    self.showAlert = true
                    self.loadStorage()
                case .failure(let err):
                    self.alertMessage = "Cleaning failed: \(err.message)"
                    self.showAlert = true
                }
            }
        }
    }
}
