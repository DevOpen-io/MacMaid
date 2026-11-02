import SwiftUI
import AppKit

struct SettingsView: View {
    @ObservedObject var state = AppState.shared
    @State private var rules: [String] = []
    @State private var newRuleText: String = ""
    @State private var selectedRule: String?
    @State private var updateStatus: UpdateStatusModel?
    @State private var isCheckingUpdates: Bool = false
    @State private var alertMessage: String?
    @State private var showAlert: Bool = false

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text(state.t("Settings"))
                    .font(.title2)
                    .fontWeight(.bold)
                Spacer()
            }
            .padding()
            .background(Color(NSColor.windowBackgroundColor))

            Divider()

            Form {
                Section(header: Text("Interface Language")) {
                    Picker("Language / Dil", selection: Binding(
                        get: { state.language },
                        set: { newLang in
                            state.setLanguage(newLang)
                        }
                    )) {
                        Text("English").tag("en")
                        Text("Türkçe").tag("tr")
                    }
                    .pickerStyle(SegmentedPickerStyle())
                    .frame(width: 200)

                    Text("Interface language persists across app launches and CLI.")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }

                Section(header: Text("Whitelist Protection Rules (~/.config/macmaid/whitelist)")) {
                    Text("Paths and glob patterns in this list are strictly protected from every cleanup operation.")
                        .font(.caption)
                        .foregroundColor(.secondary)

                    HStack {
                        TextField("Enter absolute path or glob (e.g. ~/MyProject/*.bak)", text: $newRuleText)
                            .textFieldStyle(RoundedBorderTextFieldStyle())

                        Button("Add Path...") {
                            choosePathForWhitelist()
                        }

                        Button("Add Rule") {
                            addRule()
                        }
                        .disabled(newRuleText.trimmingCharacters(in: .whitespaces).isEmpty)
                    }

                    List(rules, id: \.self, selection: $selectedRule) { rule in
                        HStack {
                            Image(systemName: "shield.lefthalf.filled")
                                .foregroundColor(.blue)
                            Text(rule)
                                .font(.system(.body, design: .monospaced))
                            Spacer()
                            Button("Remove") {
                                removeRule(rule)
                            }
                            .buttonStyle(.borderless)
                            .foregroundColor(.red)
                        }
                    }
                    .frame(minHeight: 180)
                }

                Section(header: Text(state.t("Software Updates & Release Channel"))) {
                    HStack {
                        VStack(alignment: .leading, spacing: 3) {
                            HStack {
                                Text(state.t("Installation Channel:"))
                                    .fontWeight(.medium)
                                Text(updateStatus?.channel ?? "detecting...")
                                    .font(.system(.caption, design: .monospaced))
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 2)
                                    .background(Color.secondary.opacity(0.15))
                                    .cornerRadius(4)
                            }
                            if let s = updateStatus {
                                Text("\(state.t("Installed")): v\(s.installedVersion)")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                        }

                        Spacer()

                        if isCheckingUpdates {
                            ProgressView()
                                .frame(width: 80)
                        } else {
                            Button(action: checkForUpdates) {
                                Label(state.t("Check for Updates"), systemImage: "arrow.triangle.2.circlepath")
                            }
                        }
                    }

                    if let s = updateStatus {
                        if s.available, let latest = s.latestVersion {
                            HStack {
                                Image(systemName: "arrow.up.circle.fill")
                                    .foregroundColor(.green)
                                VStack(alignment: .leading, spacing: 2) {
                                    Text("\(state.t("New version available")): v\(latest)")
                                        .fontWeight(.semibold)
                                    if let cmd = s.updateCommand {
                                        Text("Update via: \(cmd)")
                                            .font(.system(.caption, design: .monospaced))
                                            .foregroundColor(.secondary)
                                    }
                                }
                                Spacer()
                                Button(state.t("View Release")) {
                                    if let url = URL(string: s.updateUrl) {
                                        NSWorkspace.shared.open(url)
                                    }
                                }
                                .buttonStyle(.borderedProminent)
                            }
                            .padding(8)
                            .background(Color.green.opacity(0.1))
                            .cornerRadius(8)
                        } else if s.checked {
                            HStack {
                                Image(systemName: "checkmark.circle.fill")
                                    .foregroundColor(.green)
                                Text(state.t("MacMaid is up to date."))
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                        } else if let reason = s.reason {
                            Text(reason)
                                .font(.caption2)
                                .foregroundColor(.secondary)
                        }
                    }
                }
            }
            .padding()
        }
        .onAppear {
            loadRules()
            checkForUpdates()
        }
        .alert(isPresented: $showAlert) {
            Alert(title: Text("Notice"), message: Text(alertMessage ?? ""), dismissButton: .default(Text("OK")))
        }
    }

    private func checkForUpdates() {
        isCheckingUpdates = true
        DispatchQueue.global(qos: .userInitiated).async {
            let status = MacMaidBridge.shared.checkUpdates()
            DispatchQueue.main.async {
                self.isCheckingUpdates = false
                self.updateStatus = status
            }
        }
    }

    private func loadRules() {
        rules = MacMaidBridge.shared.loadWhitelist()
    }

    private func addRule() {
        let trimmed = newRuleText.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { return }
        if MacMaidBridge.shared.addWhitelistRule(trimmed) {
            newRuleText = ""
            loadRules()
        }
    }

    private func removeRule(_ rule: String) {
        if MacMaidBridge.shared.removeWhitelistRule(rule) {
            loadRules()
        }
    }

    private func choosePathForWhitelist() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        if panel.runModal() == .OK, let url = panel.url {
            newRuleText = url.path
        }
    }
}
