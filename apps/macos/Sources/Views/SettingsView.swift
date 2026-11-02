import SwiftUI
import AppKit

struct SettingsView: View {
    @ObservedObject var state = AppState.shared
    @State private var rules: [String] = []
    @State private var newRuleText: String = ""
    @State private var selectedRule: String?
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
            }
            .padding()
        }
        .onAppear(perform: loadRules)
        .alert(isPresented: $showAlert) {
            Alert(title: Text("Notice"), message: Text(alertMessage ?? ""), dismissButton: .default(Text("OK")))
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
