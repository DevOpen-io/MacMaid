import SwiftUI

struct ReviewConfirmationSheet: View {
    @ObservedObject var state = AppState.shared
    let stagedPlan: StagedPlanModel
    let onConfirm: (String, Bool) -> Void
    let onCancel: () -> Void

    @State private var extraOptInAccepted: Bool = false

    var plan: ReviewPlanModel {
        stagedPlan.plan
    }

    var canAuthorize: Bool {
        if plan.requiresExtraOptIn {
            return extraOptInAccepted
        }
        return true
    }

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack(spacing: 14) {
                Image(systemName: "shield.lefthalf.filled.badge.checkmark")
                    .font(.system(size: 32))
                    .foregroundColor(plan.requiresExtraOptIn ? .orange : .accentColor)

                VStack(alignment: .leading, spacing: 3) {
                    Text(plan.title)
                        .font(.title3)
                        .fontWeight(.bold)
                    Text(plan.impact)
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .lineLimit(2)
                }

                Spacer()

                VStack(alignment: .trailing, spacing: 2) {
                    Text("\(plan.items.count) items")
                        .font(.subheadline)
                        .fontWeight(.medium)
                    if plan.totalBytes > 0 {
                        Text(MacMaidBridge.formatBytes(plan.totalBytes))
                            .font(.headline)
                            .foregroundColor(.secondary)
                    }
                }
            }
            .padding()
            .background(Color(NSColor.windowBackgroundColor))

            Divider()

            // Itemized list
            ScrollView {
                VStack(spacing: 8) {
                    ForEach(plan.items) { item in
                        HStack(alignment: .top, spacing: 10) {
                            Circle()
                                .fill(riskColor(item.risk))
                                .frame(width: 8, height: 8)
                                .padding(.top, 5)

                            VStack(alignment: .leading, spacing: 2) {
                                HStack(spacing: 6) {
                                    Text(item.label)
                                        .font(.subheadline)
                                        .fontWeight(.medium)
                                        .lineLimit(1)

                                    Text(item.risk)
                                        .font(.caption2)
                                        .padding(.horizontal, 4)
                                        .padding(.vertical, 1)
                                        .background(riskColor(item.risk).opacity(0.15))
                                        .foregroundColor(riskColor(item.risk))
                                        .cornerRadius(3)

                                    if item.userData {
                                        Text("User Data")
                                            .font(.caption2)
                                            .padding(.horizontal, 4)
                                            .padding(.vertical, 1)
                                            .background(Color.red.opacity(0.15))
                                            .foregroundColor(.red)
                                            .cornerRadius(3)
                                    }

                                    if let appName = item.requiresAppClosed {
                                        Text("Close \(appName)")
                                            .font(.caption2)
                                            .padding(.horizontal, 4)
                                            .padding(.vertical, 1)
                                            .background(Color.yellow.opacity(0.15))
                                            .foregroundColor(.orange)
                                            .cornerRadius(3)
                                    }
                                }

                                Text(item.target)
                                    .font(.caption2)
                                    .foregroundColor(.secondary)
                                    .lineLimit(1)
                                    .truncationMode(.middle)

                                HStack {
                                    Text("Action: \(item.action)")
                                        .font(.caption2)
                                        .foregroundColor(.secondary)
                                    Text("·")
                                        .foregroundColor(.secondary)
                                    Text(item.reason)
                                        .font(.caption2)
                                        .foregroundColor(.secondary)
                                        .lineLimit(1)
                                }
                            }

                            Spacer()

                            if item.estimatedBytes > 0 {
                                Text(MacMaidBridge.formatBytes(item.estimatedBytes))
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                        }
                        .padding(8)
                        .background(Color(NSColor.controlBackgroundColor))
                        .cornerRadius(6)
                    }
                }
                .padding()
            }
            .frame(maxHeight: 280)

            Divider()

            // Footer / Explicit Authorization
            VStack(alignment: .leading, spacing: 12) {
                if !plan.estimateNote.isEmpty {
                    HStack(spacing: 6) {
                        Image(systemName: "info.circle")
                            .foregroundColor(.secondary)
                            .font(.caption)
                        Text(plan.estimateNote)
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                }

                if plan.requiresExtraOptIn {
                    Toggle(isOn: $extraOptInAccepted) {
                        Text("I have reviewed the items and explicitly authorize aggressive / user-data modifications.")
                            .font(.caption)
                            .fontWeight(.medium)
                            .foregroundColor(.primary)
                    }
                    .toggleStyle(CheckboxToggleStyle())
                }

                HStack(spacing: 14) {
                    Button("Cancel", action: onCancel)
                        .keyboardShortcut(.cancelAction)

                    Spacer()

                    // Crucial safety contract: NO .keyboardShortcut(.defaultAction) on destructive confirm
                    Button(action: {
                        onConfirm(stagedPlan.token, extraOptInAccepted)
                    }) {
                        Text(plan.requiresExtraOptIn ? "Confirm & Execute (Opted In)" : "Confirm & Execute")
                            .fontWeight(.semibold)
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(.red)
                    .disabled(!canAuthorize)
                }
            }
            .padding()
            .background(Color(NSColor.windowBackgroundColor))
        }
        .frame(minWidth: 540, maxWidth: 620)
    }

    private func riskColor(_ risk: String) -> Color {
        switch risk.uppercased() {
        case "SAFE": return .green
        case "MODERATE": return .yellow
        case "AGGRESSIVE": return .orange
        default: return .red
        }
    }
}
