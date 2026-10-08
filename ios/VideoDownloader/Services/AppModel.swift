import Foundation
import Combine
import Photos

@MainActor
final class AppModel: ObservableObject {
    @Published var inputURL = ""
    @Published var media: MediaInfo?
    @Published var selectedResolution: Int?
    @Published var selectedMode: DownloadMode = .best
    @Published var tasks: [DownloadTaskInfo] = []
    @Published var isAnalyzing = false
    @Published var isCreatingTask = false
    @Published var isDownloadingFile = false
    @Published var isSavingPhoto = false
    @Published var errorMessage: String?
    @Published var noticeMessage: String?
    @Published var exportFile: LocalVideoFile?

    private let settings: SettingsStore
    private var pollingTask: _Concurrency.Task<Void, Never>?

    init(settings: SettingsStore) { self.settings = settings }

    private func client() throws -> APIClient {
        APIClient(configuration: try settings.configuration())
    }

    func analyze() async {
        guard !inputURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            errorMessage = "请输入视频网址。"
            return
        }
        isAnalyzing = true
        media = nil
        defer { isAnalyzing = false }
        do {
            let result = try await client().analyze(url: inputURL)
            media = result
            selectedResolution = result.formats.first?.height
        } catch { errorMessage = error.localizedDescription }
    }

    func createDownload() async {
        guard let media else { errorMessage = "请先解析视频信息。"; return }
        isCreatingTask = true
        defer { isCreatingTask = false }
        do {
            let created = try await client().createTask(
                url: media.url, resolution: selectedResolution, mode: selectedMode
            )
            upsert(created)
            noticeMessage = "任务已提交到云端。"
            startPolling()
        } catch { errorMessage = error.localizedDescription }
    }

    func refreshTasks(showErrors: Bool = true) async {
        do { tasks = try await client().tasks() }
        catch { if showErrors { errorMessage = error.localizedDescription } }
    }

    func cancel(_ task: DownloadTaskInfo) async {
        do { upsert(try await client().cancel(id: task.id)) }
        catch { errorMessage = error.localizedDescription }
    }

    func retry(_ task: DownloadTaskInfo) async {
        do { upsert(try await client().retry(id: task.id)); startPolling() }
        catch { errorMessage = error.localizedDescription }
    }

    func delete(_ task: DownloadTaskInfo) async {
        do { try await client().delete(id: task.id); tasks.removeAll { $0.id == task.id } }
        catch { errorMessage = error.localizedDescription }
    }

    func prepareFile(_ task: DownloadTaskInfo) async {
        isDownloadingFile = true
        defer { isDownloadingFile = false }
        do { exportFile = try await client().download(id: task.id) }
        catch { errorMessage = error.localizedDescription }
    }

    func saveToPhotos(_ task: DownloadTaskInfo) async {
        isSavingPhoto = true
        defer { isSavingPhoto = false }
        do {
            let local = try await client().download(id: task.id)
            let status = await PHPhotoLibrary.requestAuthorization(for: .addOnly)
            guard status == .authorized || status == .limited else {
                throw NSError(domain: "Photos", code: 1, userInfo: [NSLocalizedDescriptionKey: "没有相册写入权限。"])
            }
            try await PHPhotoLibrary.shared().performChanges {
                PHAssetChangeRequest.creationRequestForAssetFromVideo(atFileURL: local.url)
            }
            noticeMessage = "视频已保存到相册。"
        } catch { errorMessage = error.localizedDescription }
    }

    func startPolling() {
        pollingTask?.cancel()
        pollingTask = _Concurrency.Task { [weak self] in
            while !Task.isCancelled {
                guard let self else { return }
                await self.refreshTasks(showErrors: false)
                if !self.tasks.contains(where: { $0.isActive }) { return }
                try? await Task.sleep(nanoseconds: 2_000_000_000)
            }
        }
    }

    func stopPolling() {
        pollingTask?.cancel()
        pollingTask = nil
    }

    private func upsert(_ task: DownloadTaskInfo) {
        if let index = tasks.firstIndex(where: { $0.id == task.id }) { tasks[index] = task }
        else { tasks.insert(task, at: 0) }
    }
}
