import Foundation

// MARK: - Models

public struct MacMaidError: Error, LocalizedError {
    public let message: String
    public init(_ msg: String) { self.message = msg }
    public var errorDescription: String? { message }
}

public struct DiagnosticCheck: Identifiable, Codable {
    public var id: String
    public var title: String
    public var status: String
    public var value: String
    public var detail: String
}

public struct DiskStats: Codable {
    public var totalBytes: UInt64
    public var freeBytes: UInt64
    public var availableBytes: UInt64
}

public struct PermissionGroup: Identifiable, Codable {
    public var id: String
    public var status: String
    public var accessible: Int
    public var total: Int
    public var entries: [String]
}

public struct PermissionReport: Codable {
    public var launchContext: String
    public var fullDiskAccess: String
    public var checks: [PermissionGroup]
    public var note: String
}

public struct SystemHealthReport: Codable {
    public var permissions: PermissionReport
    public var disk: DiskStats?
    public var version: String
}

public struct CleanupActionModel: Codable {
    public var kind: String
    public var executable: String?
    public var arguments: [String]?
}

public struct CleanupItemModel: Identifiable, Codable {
    public var id: String
    public var category: String
    public var label: String
    public var path: String?
    public var estimatedBytes: UInt64
    public var risk: String
    public var reason: String
    public var action: CleanupActionModel
    public var requiresAppClosed: String?
}

public struct ScanResultModel: Codable {
    public var items: [CleanupItemModel]
    public var notes: [String]
    public var status: String
    public var issues: [String]

    public var totalBytes: UInt64 {
        items.reduce(0) { $0 + $1.estimatedBytes }
    }
}

public struct OperationResultModel: Codable {
    public var freed: UInt64
    public var failed: Int
    public var skipped: Int
    public var details: [String]
    public var scannedEstimatedBytes: UInt64
    public var processedEstimatedBytes: UInt64
    public var trashMovedEstimatedBytes: UInt64
    public var observedFreeBytesDelta: Int64?
    public var unknownReclaimCount: Int
    public var measurementNotes: [String]
}

public struct AnalyzerNodeModel: Identifiable, Codable {
    public var id: String { path }
    public var name: String
    public var path: String
    public var bytes: UInt64
    public var isDir: Bool
    public var itemCount: Int
    public var children: [AnalyzerNodeModel]?
}

public struct AnalyzerReportModel: Codable {
    public var rootPath: String
    public var totalBytes: UInt64
    public var totalItems: Int
    public var topItems: [AnalyzerNodeModel]
    public var tree: AnalyzerNodeModel
}

public struct InstalledAppModel: Identifiable, Codable, Hashable {
    public var id: String { bundleId.isEmpty ? path : bundleId }
    public var name: String
    public var path: String
    public var bundleId: String
    public var version: String
    public var bytes: UInt64
    public var brewCask: String?
}

public struct AppComponentModel: Identifiable, Codable {
    public var id: String { path }
    public var label: String
    public var path: String
    public var bytes: UInt64
    public var risk: String
    public var selected: Bool
}

public struct ReviewItemModel: Identifiable, Codable {
    public var id: String { key }
    public var key: String
    public var label: String
    public var target: String
    public var action: String
    public var risk: String
    public var reason: String
    public var estimatedBytes: UInt64
    public var requiresAppClosed: String?
    public var userData: Bool
}

public struct ReviewPlanModel: Codable {
    public var scope: String
    public var title: String
    public var items: [ReviewItemModel]
    public var impact: String
    public var estimateNote: String
    public var totalBytes: UInt64
    public var requiresExtraOptIn: Bool
}

public struct StagedPlanModel: Codable {
    public var token: String
    public var plan: ReviewPlanModel
}

public struct SnapshotInfoModel: Identifiable, Codable {
    public var id: String { name }
    public var name: String
    public var date: String
}

public struct SnapshotThinResultModel: Codable {
    public var success: Bool
    public var output: String
    public var error: String
    public var requestedReclaimBytes: UInt64
    public var observedFreeBytesDelta: Int64?
}

public struct UpdateStatusModel: Codable {
    public var channel: String
    public var installed: Bool
    public var canApply: Bool
    public var available: Bool
    public var checked: Bool
    public var installedVersion: String
    public var latestVersion: String?
    public var updateCommand: String?
    public var updateUrl: String
    public var reason: String?
}

public struct ProcessInfoModel: Identifiable, Codable {
    public var id: UInt32 { pid }
    public var pid: UInt32
    public var ppid: UInt32
    public var name: String
    public var executable: String
    public var rssBytes: UInt64
    public var cpuPercent: Float
    public var category: String
    public var isProtected: Bool
    public var growthBytesPerSec: Double
    public var startTime: UInt64?
    public var uid: UInt32?
}

public struct DeveloperSectionModel: Identifiable, Codable {
    public var id: String { name }
    public var name: String
    public var path: String?
    public var bytes: UInt64
    public var description: String
    public var cleanable: Bool
    public var actionType: String
}

public struct DuplicateGroupModel: Identifiable, Codable {
    public var id: String { hash }
    public var hash: String
    public var size: UInt64
    public var files: [String]
}

public struct LargeOldFileModel: Identifiable, Codable {
    public var id: String { path }
    public var path: String
    public var name: String
    public var size: UInt64
    public var modified: String
    public var extensionName: String

    enum CodingKeys: String, CodingKey {
        case path, name, size, modified
        case extensionName = "extension"
    }
}

public struct DownloadItemModel: Identifiable, Codable {
    public var id: String { path }
    public var name: String
    public var path: String
    public var size: UInt64
    public var category: String
    public var ageDays: UInt64
}

public struct SmartDownloadsReportModel: Codable {
    public var totalBytes: UInt64
    public var installers: [DownloadItemModel]
    public var archives: [DownloadItemModel]
    public var incomplete: [DownloadItemModel]
    public var duplicates: [DownloadItemModel]
}

public struct ProjectArtifactModel: Identifiable, Codable {
    public var id: String { path }
    public var name: String
    public var path: String
    public var projectPath: String
    public var projectName: String
    public var bytes: UInt64
    public var artifactType: String
}

public struct OperationRecordModel: Identifiable, Codable {
    public var id: String { "\(operationId)-\(timestamp)-\(path ?? "")" }
    public var timestamp: String
    public var operationId: String
    public var eventType: String?
    public var category: String?
    public var label: String?
    public var path: String?
    public var status: String
    public var error: String?
    public var trashPath: String?
    public var processedEstimatedBytes: UInt64
    public var estimatedReclaimedBytes: UInt64
    public var reclaimStatus: String?
}

public struct RestorableItemModel: Identifiable, Codable {
    public var id: String { "\(operationId)-\(trashPath)" }
    public var operationId: String
    public var timestamp: String
    public var originalPath: String
    public var trashPath: String
    public var label: String
    public var bytes: UInt64
    public var existsInTrash: Bool
}

public struct AppSettingsModel: Codable {
    public var language: String
}

// MARK: - Bridge Class

public final class MacMaidBridge {
    public static let shared = MacMaidBridge()

    private let jsonDecoder = JSONDecoder()
    private let jsonEncoder = JSONEncoder()

    private init() {}

    // Utility: Format bytes
    public static func formatBytes(_ bytes: UInt64) -> String {
        let doubleBytes = Double(bytes)
        let units = ["B", "KB", "MB", "GB", "TB"]
        var amount = doubleBytes
        var unitIndex = 0

        while amount >= 1024.0 && unitIndex < units.count - 1 {
            amount /= 1024.0
            unitIndex += 1
        }

        if unitIndex == 0 {
            return String(format: "%.0f %@", amount, units[unitIndex])
        } else {
            return String(format: "%.1f %@", amount, units[unitIndex])
        }
    }

    // Diagnostics
    public func runDiagnostics() -> [DiagnosticCheck] {
        guard let cStr = macmaid_run_diagnostics() else { return [] }
        defer { macmaid_free_string(cStr) }
        let str = String(cString: cStr)
        guard let data = str.data(using: .utf8) else { return [] }
        return (try? jsonDecoder.decode([DiagnosticCheck].self, from: data)) ?? []
    }

    // Health
    public func getSystemHealth() -> SystemHealthReport? {
        guard let cStr = macmaid_get_system_health() else { return nil }
        defer { macmaid_free_string(cStr) }
        let str = String(cString: cStr)
        guard let data = str.data(using: .utf8) else { return nil }
        return try? jsonDecoder.decode(SystemHealthReport.self, from: data)
    }

    // Smart Clean Scan
    public func scan(
        profile: String,
        includeTrash: Bool,
        includeTemp: Bool,
        token: OpaquePointer?,
        onProgress: @escaping (Int, String, String) -> Void
    ) -> ScanResultModel? {
        class Context {
            var callback: (Int, String, String) -> Void
            init(_ cb: @escaping (Int, String, String) -> Void) { self.callback = cb }
        }
        let ctx = Context(onProgress)
        let ctxPtr = Unmanaged.passRetained(ctx).toOpaque()

        let cCallback: ScanProgressCallback = { percent, phasePtr, pathPtr, userData in
            let phase = phasePtr != nil ? String(cString: phasePtr!) : ""
            let path = pathPtr != nil ? String(cString: pathPtr!) : ""
            if let userPtr = userData {
                let context = Unmanaged<Context>.fromOpaque(userPtr).takeUnretainedValue()
                context.callback(percent, phase, path)
            }
        }

        let cProfile = profile.cString(using: .utf8)!
        let cResult = macmaid_scan(
            cProfile,
            includeTrash,
            includeTemp,
            token,
            cCallback,
            ctxPtr
        )
        _ = Unmanaged<Context>.fromOpaque(ctxPtr).takeRetainedValue()

        guard let cResult = cResult else { return nil }
        defer { macmaid_free_string(cResult) }
        let str = String(cString: cResult)
        guard let data = str.data(using: .utf8) else { return nil }
        return try? jsonDecoder.decode(ScanResultModel.self, from: data)
    }

    // MARK: - Safety Review Plan Staging
    public func stageReviewPlan(scope: String, payloadJson: String) -> Result<StagedPlanModel, MacMaidError> {
        let cScope = scope.cString(using: .utf8)!
        let cPayload = payloadJson.cString(using: .utf8)!
        guard let cResult = macmaid_stage_review_plan(cScope, cPayload) else {
            return .failure(MacMaidError("Null response from FFI in stageReviewPlan"))
        }
        defer { macmaid_free_string(cResult) }
        let str = String(cString: cResult)
        guard let data = str.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return .failure(MacMaidError("Invalid response JSON in stageReviewPlan"))
        }
        if let err = json["error"] as? String {
            return .failure(MacMaidError(err))
        }
        if let dataObj = json["data"],
           let subData = try? JSONSerialization.data(withJSONObject: dataObj),
           let staged = try? jsonDecoder.decode(StagedPlanModel.self, from: subData) {
            return .success(staged)
        }
        return .failure(MacMaidError("Failed to decode staged review plan"))
    }

    // Execute Clean
    public func executeClean(
        items: [CleanupItemModel],
        apply: Bool,
        allowManual: Bool,
        reviewToken: String?,
        onProgress: @escaping (Int, Int, String, String) -> Void
    ) -> OperationResultModel? {
        class Context {
            var callback: (Int, Int, String, String) -> Void
            init(_ cb: @escaping (Int, Int, String, String) -> Void) { self.callback = cb }
        }
        let ctx = Context(onProgress)
        let ctxPtr = Unmanaged.passRetained(ctx).toOpaque()

        let cCallback: CleanProgressCallback = { idx, total, labelPtr, outcomePtr, userData in
            let label = labelPtr != nil ? String(cString: labelPtr!) : ""
            let outcome = outcomePtr != nil ? String(cString: outcomePtr!) : ""
            if let userPtr = userData {
                let context = Unmanaged<Context>.fromOpaque(userPtr).takeUnretainedValue()
                context.callback(idx, total, label, outcome)
            }
        }

        guard let jsonData = try? jsonEncoder.encode(items),
              let jsonStr = String(data: jsonData, encoding: .utf8) else {
            _ = Unmanaged<Context>.fromOpaque(ctxPtr).takeRetainedValue()
            return nil
        }

        let cItems = jsonStr.cString(using: .utf8)!
        let cToken = (reviewToken ?? "").cString(using: .utf8)!
        let cResult = macmaid_execute_clean(
            cItems,
            apply,
            allowManual,
            cToken,
            cCallback,
            ctxPtr
        )
        _ = Unmanaged<Context>.fromOpaque(ctxPtr).takeRetainedValue()

        guard let cResult = cResult else { return nil }
        defer { macmaid_free_string(cResult) }
        let str = String(cString: cResult)
        guard let data = str.data(using: .utf8) else { return nil }
        return try? jsonDecoder.decode(OperationResultModel.self, from: data)
    }

    // Disk Analyzer
    public func analyzeDirectory(
        path: String,
        topLimit: Int,
        minSize: UInt64,
        token: OpaquePointer?,
        onProgress: @escaping (Int, String) -> Void
    ) -> AnalyzerReportModel? {
        class Context {
            var callback: (Int, String) -> Void
            init(_ cb: @escaping (Int, String) -> Void) { self.callback = cb }
        }
        let ctx = Context(onProgress)
        let ctxPtr = Unmanaged.passRetained(ctx).toOpaque()

        let cCallback: AnalyzerProgressCallback = { count, pathPtr, userData in
            let path = pathPtr != nil ? String(cString: pathPtr!) : ""
            if let userPtr = userData {
                let context = Unmanaged<Context>.fromOpaque(userPtr).takeUnretainedValue()
                context.callback(count, path)
            }
        }

        let cPath = path.cString(using: .utf8)!
        let cResult = macmaid_analyze_directory(
            cPath,
            topLimit,
            minSize,
            token,
            cCallback,
            ctxPtr
        )
        _ = Unmanaged<Context>.fromOpaque(ctxPtr).takeRetainedValue()

        guard let cResult = cResult else { return nil }
        defer { macmaid_free_string(cResult) }
        let str = String(cString: cResult)
        guard let data = str.data(using: .utf8) else { return nil }
        return try? jsonDecoder.decode(AnalyzerReportModel.self, from: data)
    }

    public func moveAnalyzerItemToTrash(path: String, estimatedBytes: UInt64, reviewToken: String) -> Result<String, MacMaidError> {
        let cPath = path.cString(using: .utf8)!
        let cToken = reviewToken.cString(using: .utf8)!
        guard let cResult = macmaid_move_analyzer_item_to_trash(cPath, estimatedBytes, cToken) else {
            return .failure(MacMaidError("Null response from FFI"))
        }
        defer { macmaid_free_string(cResult) }
        let str = String(cString: cResult)
        guard let data = str.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return .failure(MacMaidError("Invalid response JSON"))
        }
        if let err = json["error"] as? String {
            return .failure(MacMaidError(err))
        }
        if let dest = (json["data"] as? [String: Any])?["destination"] as? String {
            return .success(dest)
        }
        return .failure(MacMaidError("Unknown response"))
    }

    // App Uninstaller
    public func scanApplications(token: OpaquePointer?) -> [InstalledAppModel] {
        guard let cStr = macmaid_scan_applications(token) else { return [] }
        defer { macmaid_free_string(cStr) }
        let str = String(cString: cStr)
        guard let data = str.data(using: .utf8) else { return [] }
        return (try? jsonDecoder.decode([InstalledAppModel].self, from: data)) ?? []
    }

    public func scanAppComponents(bundleId: String) -> [AppComponentModel] {
        let cBundleId = bundleId.cString(using: .utf8)!
        guard let cStr = macmaid_scan_app_components(cBundleId) else { return [] }
        defer { macmaid_free_string(cStr) }
        let str = String(cString: cStr)
        guard let data = str.data(using: .utf8) else { return [] }
        return (try? jsonDecoder.decode([AppComponentModel].self, from: data)) ?? []
    }

    public func uninstallApplication(
        app: InstalledAppModel,
        components: [String],
        reviewToken: String,
        allowUserData: Bool
    ) -> Result<UInt64, MacMaidError> {
        guard let appData = try? jsonEncoder.encode(app),
              let appStr = String(data: appData, encoding: .utf8),
              let compsData = try? jsonEncoder.encode(components),
              let compsStr = String(data: compsData, encoding: .utf8) else {
            return .failure(MacMaidError("Failed to encode arguments"))
        }
        let cApp = appStr.cString(using: .utf8)!
        let cComps = compsStr.cString(using: .utf8)!
        let cToken = reviewToken.cString(using: .utf8)!
        guard let cResult = macmaid_uninstall_application(cApp, cComps, cToken, allowUserData) else {
            return .failure(MacMaidError("Null response from FFI"))
        }
        defer { macmaid_free_string(cResult) }
        let str = String(cString: cResult)
        guard let data = str.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return .failure(MacMaidError("Invalid response JSON"))
        }
        if let err = json["error"] as? String {
            return .failure(MacMaidError(err))
        }
        if let reclaimed = (json["data"] as? [String: Any])?["reclaimed"] as? UInt64 {
            return .success(reclaimed)
        }
        return .failure(MacMaidError("Unknown response"))
    }

    // Memory
    public func getMemorySnapshot() -> [ProcessInfoModel] {
        guard let cStr = macmaid_memory_snapshot() else { return [] }
        defer { macmaid_free_string(cStr) }
        let str = String(cString: cStr)
        guard let data = str.data(using: .utf8) else { return [] }
        return (try? jsonDecoder.decode([ProcessInfoModel].self, from: data)) ?? []
    }

    public func terminateProcess(
        pid: UInt32,
        expectedStartTime: UInt64,
        force: Bool,
        reviewToken: String
    ) -> Result<Void, MacMaidError> {
        let cToken = reviewToken.cString(using: .utf8)!
        guard let cResult = macmaid_terminate_process(pid, expectedStartTime, force, cToken) else {
            return .failure(MacMaidError("Null response from FFI"))
        }
        defer { macmaid_free_string(cResult) }
        let str = String(cString: cResult)
        guard let data = str.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return .failure(MacMaidError("Invalid response JSON"))
        }
        if let err = json["error"] as? String {
            return .failure(MacMaidError(err))
        }
        return .success(())
    }

    // Developer Storage
    public func getDeveloperStorage(token: OpaquePointer?) -> [DeveloperSectionModel] {
        guard let cStr = macmaid_developer_storage(token) else { return [] }
        defer { macmaid_free_string(cStr) }
        let str = String(cString: cStr)
        guard let data = str.data(using: .utf8) else { return [] }
        return (try? jsonDecoder.decode([DeveloperSectionModel].self, from: data)) ?? []
    }

    public func cleanDeveloperSection(section: DeveloperSectionModel, reviewToken: String) -> Result<UInt64, MacMaidError> {
        guard let secData = try? jsonEncoder.encode(section),
              let secStr = String(data: secData, encoding: .utf8) else {
            return .failure(MacMaidError("Failed to encode section"))
        }
        let cSec = secStr.cString(using: .utf8)!
        let cToken = reviewToken.cString(using: .utf8)!
        guard let cResult = macmaid_developer_clean(cSec, cToken) else {
            return .failure(MacMaidError("Null response from FFI"))
        }
        defer { macmaid_free_string(cResult) }
        let str = String(cString: cResult)
        guard let data = str.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return .failure(MacMaidError("Invalid response JSON"))
        }
        if let err = json["error"] as? String {
            return .failure(MacMaidError(err))
        }
        if let reclaimed = (json["data"] as? [String: Any])?["reclaimed"] as? UInt64 {
            return .success(reclaimed)
        }
        return .failure(MacMaidError("Unknown response"))
    }

    // Duplicates
    public func findDuplicates(
        paths: [String],
        minSize: UInt64,
        token: OpaquePointer?,
        onProgress: @escaping (Int, String) -> Void
    ) -> [DuplicateGroupModel] {
        class Context {
            var callback: (Int, String) -> Void
            init(_ cb: @escaping (Int, String) -> Void) { self.callback = cb }
        }
        let ctx = Context(onProgress)
        let ctxPtr = Unmanaged.passRetained(ctx).toOpaque()

        let cCallback: DuplicateProgressCallback = { count, pathPtr, userData in
            let path = pathPtr != nil ? String(cString: pathPtr!) : ""
            if let userPtr = userData {
                let context = Unmanaged<Context>.fromOpaque(userPtr).takeUnretainedValue()
                context.callback(count, path)
            }
        }

        let pathsJson = (try? String(data: jsonEncoder.encode(paths), encoding: .utf8)) ?? "[]"
        let cPaths = pathsJson.cString(using: .utf8)!
        let cResult = macmaid_find_duplicates(
            cPaths,
            minSize,
            token,
            cCallback,
            ctxPtr
        )
        _ = Unmanaged<Context>.fromOpaque(ctxPtr).takeRetainedValue()

        guard let cResult = cResult else { return [] }
        defer { macmaid_free_string(cResult) }
        let str = String(cString: cResult)
        guard let data = str.data(using: .utf8) else { return [] }
        return (try? jsonDecoder.decode([DuplicateGroupModel].self, from: data)) ?? []
    }

    public func trashDuplicateItems(paths: [String], estimatedBytes: UInt64, reviewToken: String) -> Result<UInt64, MacMaidError> {
        let pathsJson = (try? String(data: jsonEncoder.encode(paths), encoding: .utf8)) ?? "[]"
        let cPaths = pathsJson.cString(using: .utf8)!
        let cToken = reviewToken.cString(using: .utf8)!
        guard let cResult = macmaid_trash_duplicate_items(cPaths, estimatedBytes, cToken) else {
            return .failure(MacMaidError("Null response from FFI"))
        }
        defer { macmaid_free_string(cResult) }
        let str = String(cString: cResult)
        guard let data = str.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return .failure(MacMaidError("Invalid response JSON"))
        }
        if let err = json["error"] as? String {
            return .failure(MacMaidError(err))
        }
        let reclaimed = (json["data"] as? [String: Any])?["reclaimed"] as? UInt64 ?? 0
        return .success(reclaimed)
    }

    // Large Files
    public func scanLargeFiles(paths: [String], minSize: UInt64, olderThanDays: UInt64, token: OpaquePointer?) -> [LargeOldFileModel] {
        let pathsJson = (try? String(data: jsonEncoder.encode(paths), encoding: .utf8)) ?? "[]"
        let cPaths = pathsJson.cString(using: .utf8)!
        guard let cStr = macmaid_large_files(cPaths, minSize, olderThanDays, token) else { return [] }
        defer { macmaid_free_string(cStr) }
        let str = String(cString: cStr)
        guard let data = str.data(using: .utf8) else { return [] }
        return (try? jsonDecoder.decode([LargeOldFileModel].self, from: data)) ?? []
    }

    public func trashLargeFiles(paths: [String], estimatedBytes: UInt64, reviewToken: String) -> Result<UInt64, MacMaidError> {
        let pathsJson = (try? String(data: jsonEncoder.encode(paths), encoding: .utf8)) ?? "[]"
        let cPaths = pathsJson.cString(using: .utf8)!
        let cToken = reviewToken.cString(using: .utf8)!
        guard let cResult = macmaid_trash_large_files(cPaths, estimatedBytes, cToken) else {
            return .failure(MacMaidError("Null response from FFI"))
        }
        defer { macmaid_free_string(cResult) }
        let str = String(cString: cResult)
        guard let data = str.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return .failure(MacMaidError("Invalid response JSON"))
        }
        if let err = json["error"] as? String {
            return .failure(MacMaidError(err))
        }
        let reclaimed = (json["data"] as? [String: Any])?["reclaimed"] as? UInt64 ?? 0
        return .success(reclaimed)
    }

    // Smart Downloads
    public func scanSmartDownloads(olderThanDays: UInt64, token: OpaquePointer?) -> SmartDownloadsReportModel? {
        guard let cStr = macmaid_smart_downloads(olderThanDays, token) else { return nil }
        defer { macmaid_free_string(cStr) }
        let str = String(cString: cStr)
        guard let data = str.data(using: .utf8) else { return nil }
        return try? jsonDecoder.decode(SmartDownloadsReportModel.self, from: data)
    }

    public func trashDownloadItems(paths: [String], estimatedBytes: UInt64, reviewToken: String) -> Result<UInt64, MacMaidError> {
        let pathsJson = (try? String(data: jsonEncoder.encode(paths), encoding: .utf8)) ?? "[]"
        let cPaths = pathsJson.cString(using: .utf8)!
        let cToken = reviewToken.cString(using: .utf8)!
        guard let cResult = macmaid_trash_download_items(cPaths, estimatedBytes, cToken) else {
            return .failure(MacMaidError("Null response from FFI"))
        }
        defer { macmaid_free_string(cResult) }
        let str = String(cString: cResult)
        guard let data = str.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return .failure(MacMaidError("Invalid response JSON"))
        }
        if let err = json["error"] as? String {
            return .failure(MacMaidError(err))
        }
        let reclaimed = (json["data"] as? [String: Any])?["reclaimed"] as? UInt64 ?? 0
        return .success(reclaimed)
    }

    // Time Machine Snapshots
    public func listSnapshots() -> [SnapshotInfoModel] {
        guard let cStr = macmaid_list_snapshots() else { return [] }
        defer { macmaid_free_string(cStr) }
        let str = String(cString: cStr)
        guard let data = str.data(using: .utf8) else { return [] }
        return (try? jsonDecoder.decode([SnapshotInfoModel].self, from: data)) ?? []
    }

    public func thinSnapshots(targetGb: UInt64, reviewToken: String) -> Result<SnapshotThinResultModel, MacMaidError> {
        let cToken = reviewToken.cString(using: .utf8)!
        guard let cResult = macmaid_thin_snapshots(targetGb, cToken) else {
            return .failure(MacMaidError("Null response from FFI"))
        }
        defer { macmaid_free_string(cResult) }
        let str = String(cString: cResult)
        guard let data = str.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return .failure(MacMaidError("Invalid response JSON"))
        }
        if let err = json["error"] as? String {
            return .failure(MacMaidError(err))
        }
        if let res = try? jsonDecoder.decode(SnapshotThinResultModel.self, from: data) {
            return .success(res)
        }
        return .failure(MacMaidError("Failed to parse snapshot thinning result"))
    }

    // Project Purge
    public func scanProjectPurge(paths: [String], token: OpaquePointer?) -> [ProjectArtifactModel] {
        let pathsJson = (try? String(data: jsonEncoder.encode(paths), encoding: .utf8)) ?? "[]"
        let cPaths = pathsJson.cString(using: .utf8)!
        guard let cStr = macmaid_purge_scan(cPaths, token) else { return [] }
        defer { macmaid_free_string(cStr) }
        let str = String(cString: cStr)
        guard let data = str.data(using: .utf8) else { return [] }
        return (try? jsonDecoder.decode([ProjectArtifactModel].self, from: data)) ?? []
    }

    public func purgeArtifact(artifact: ProjectArtifactModel, reviewToken: String) -> Result<UInt64, MacMaidError> {
        guard let artData = try? jsonEncoder.encode(artifact),
              let artStr = String(data: artData, encoding: .utf8) else {
            return .failure(MacMaidError("Failed to encode artifact"))
        }
        let cArt = artStr.cString(using: .utf8)!
        let cToken = reviewToken.cString(using: .utf8)!
        guard let cResult = macmaid_purge_item(cArt, cToken) else {
            return .failure(MacMaidError("Null response from FFI"))
        }
        defer { macmaid_free_string(cResult) }
        let str = String(cString: cResult)
        guard let data = str.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return .failure(MacMaidError("Invalid response JSON"))
        }
        if let err = json["error"] as? String {
            return .failure(MacMaidError(err))
        }
        if let reclaimed = (json["data"] as? [String: Any])?["reclaimed"] as? UInt64 {
            return .success(reclaimed)
        }
        return .failure(MacMaidError("Unknown response"))
    }

    // History & Recovery
    public func readHistory(limit: Int) -> [OperationRecordModel] {
        guard let cStr = macmaid_read_history(limit) else { return [] }
        defer { macmaid_free_string(cStr) }
        let str = String(cString: cStr)
        guard let data = str.data(using: .utf8) else { return [] }
        return (try? jsonDecoder.decode([OperationRecordModel].self, from: data)) ?? []
    }

    public func listRestorable(limit: Int) -> [RestorableItemModel] {
        guard let cStr = macmaid_list_restorable(limit) else { return [] }
        defer { macmaid_free_string(cStr) }
        let str = String(cString: cStr)
        guard let data = str.data(using: .utf8) else { return [] }
        return (try? jsonDecoder.decode([RestorableItemModel].self, from: data)) ?? []
    }

    public func restoreTrashItem(trashPath: String, origPath: String, allowCopy: Bool) -> Result<String, MacMaidError> {
        let cTrash = trashPath.cString(using: .utf8)!
        let cOrig = origPath.cString(using: .utf8)!
        guard let cResult = macmaid_restore_trash_item(cTrash, cOrig, allowCopy) else {
            return .failure(MacMaidError("Null response from FFI"))
        }
        defer { macmaid_free_string(cResult) }
        let str = String(cString: cResult)
        guard let data = str.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return .failure(MacMaidError("Invalid response JSON"))
        }
        if let err = json["error"] as? String {
            return .failure(MacMaidError(err))
        }
        if let restored = (json["data"] as? [String: Any])?["restoredPath"] as? String {
            return .success(restored)
        }
        return .failure(MacMaidError("Unknown response"))
    }

    // Whitelist
    public func loadWhitelist() -> [String] {
        guard let cStr = macmaid_load_whitelist() else { return [] }
        defer { macmaid_free_string(cStr) }
        let str = String(cString: cStr)
        guard let data = str.data(using: .utf8) else { return [] }
        return (try? jsonDecoder.decode([String].self, from: data)) ?? []
    }

    public func addWhitelistRule(_ rule: String) -> Bool {
        let cRule = rule.cString(using: .utf8)!
        guard let cResult = macmaid_add_whitelist_rule(cRule) else { return false }
        defer { macmaid_free_string(cResult) }
        let str = String(cString: cResult)
        return str.contains("\"success\":true")
    }

    public func removeWhitelistRule(_ rule: String) -> Bool {
        let cRule = rule.cString(using: .utf8)!
        guard let cResult = macmaid_remove_whitelist_rule(cRule) else { return false }
        defer { macmaid_free_string(cResult) }
        let str = String(cString: cResult)
        return str.contains("\"success\":true")
    }

    // Settings & Localization
    public func loadSettings() -> AppSettingsModel {
        guard let cStr = macmaid_load_settings() else { return AppSettingsModel(language: "en") }
        defer { macmaid_free_string(cStr) }
        let str = String(cString: cStr)
        guard let data = str.data(using: .utf8) else { return AppSettingsModel(language: "en") }
        return (try? jsonDecoder.decode(AppSettingsModel.self, from: data)) ?? AppSettingsModel(language: "en")
    }

    public func saveSettings(_ settings: AppSettingsModel) -> Bool {
        guard let data = try? jsonEncoder.encode(settings),
              let str = String(data: data, encoding: .utf8) else { return false }
        let cStr = str.cString(using: .utf8)!
        guard let cResult = macmaid_save_settings(cStr) else { return false }
        defer { macmaid_free_string(cResult) }
        return String(cString: cResult).contains("\"success\":true")
    }

    public func translate(_ key: String, lang: String) -> String {
        let cKey = key.cString(using: .utf8)!
        let cLang = lang.cString(using: .utf8)!
        guard let cResult = macmaid_translate(cKey, cLang) else { return key }
        defer { macmaid_free_string(cResult) }
        let str = String(cString: cResult)
        return str.isEmpty ? key : str
    }

    public func checkUpdates() -> UpdateStatusModel? {
        guard let cStr = macmaid_check_updates() else { return nil }
        defer { macmaid_free_string(cStr) }
        let str = String(cString: cStr)
        guard let data = str.data(using: .utf8) else { return nil }
        return try? jsonDecoder.decode(UpdateStatusModel.self, from: data)
    }
}
