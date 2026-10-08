import Foundation

struct MediaFormat: Codable, Identifiable, Hashable {
    let height: Int
    let label: String

    var id: Int { height }
}

struct MediaInfo: Codable, Equatable {
    let url: String
    let title: String
    let uploader: String
    let platform: String
    let duration: Double?
    let thumbnailURL: String
    let formats: [MediaFormat]

    var durationText: String {
        guard let duration else { return "未知时长" }
        let seconds = max(0, Int(duration))
        return String(format: "%02d:%02d", seconds / 60, seconds % 60)
    }
}

enum DownloadMode: String, Codable, CaseIterable, Identifiable {
    case best
    case compatibleMP4 = "compatible_mp4"

    var id: String { rawValue }
    var title: String { self == .best ? "最高画质" : "兼容 MP4" }
}

struct DownloadTaskInfo: Codable, Identifiable, Equatable {
    let id: String
    let url: String
    let title: String
    let platform: String
    let status: String
    let progress: Double
    let downloadedBytes: Int64
    let totalBytes: Int64?
    let speedBytes: Double?
    let etaSeconds: Int?
    let resolution: Int?
    let mode: String
    let error: String?
    let hasFile: Bool
    let createdAt: Date
    let updatedAt: Date
    let expiresAt: Date?
    let attempt: Int

    var isActive: Bool { ["queued", "analyzing", "downloading", "merging"].contains(status) }
    var canRetry: Bool { ["failed", "cancelled", "expired"].contains(status) }
    var statusText: String {
        [
            "queued": "排队中", "analyzing": "解析中", "downloading": "下载中",
            "merging": "合并中", "completed": "已完成", "failed": "失败",
            "cancelled": "已取消", "expired": "已过期"
        ][status] ?? status
    }
}

struct AnalyzeBody: Encodable { let url: String }
struct TaskCreateBody: Encodable { let url: String; let resolution: Int?; let mode: DownloadMode }

struct LocalVideoFile: Identifiable {
    let url: URL
    var id: String { url.path }
}
