import SwiftUI
import Foundation

struct TaskListView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        Group {
            if model.tasks.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "tray").font(.system(size: 42)).foregroundStyle(.secondary)
                    Text("暂无任务").font(.headline)
                    Text("完成解析后创建第一个下载任务。")
                        .font(.subheadline).foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List {
                    ForEach(model.tasks) { task in
                        TaskRow(task: task)
                    }
                }
                .refreshable { await model.refreshTasks() }
            }
        }
        .navigationTitle("下载任务")
        .toolbar {
            Button { Task { await model.refreshTasks() } } label: { Image(systemName: "arrow.clockwise") }
        }
    }
}

private struct TaskRow: View {
    @EnvironmentObject private var model: AppModel
    let task: DownloadTaskInfo

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            Text(task.title.isEmpty ? task.url : task.title).font(.headline).lineLimit(2)
            HStack {
                Text(task.statusText)
                if !task.platform.isEmpty { Text("· \(task.platform)") }
                Spacer()
                Text("第 \(task.attempt) 次")
            }
            .font(.caption).foregroundStyle(.secondary)

            if task.isActive {
                ProgressView(value: max(0, min(100, task.progress)), total: 100)
                HStack {
                    Text(String(format: "%.1f%%", task.progress))
                    Spacer()
                    if let speed = task.speedBytes { Text(ByteCountFormatter.string(fromByteCount: Int64(speed), countStyle: .file) + "/s") }
                    if let eta = task.etaSeconds { Text("剩余 \(eta)s") }
                }
                .font(.caption.monospacedDigit()).foregroundStyle(.secondary)
            }

            if let error = task.error, !error.isEmpty {
                Text(error).font(.caption).foregroundStyle(.red)
            }

            HStack {
                if task.isActive {
                    Button("取消", role: .destructive) { Task { await model.cancel(task) } }
                }
                if task.canRetry {
                    Button("重试") { Task { await model.retry(task) } }
                }
                if task.status == "completed" && task.hasFile {
                    Button("存到文件") { Task { await model.prepareFile(task) } }
                    Button("存到相册") { Task { await model.saveToPhotos(task) } }
                }
                Spacer()
                if !task.isActive {
                    Button(role: .destructive) { Task { await model.delete(task) } } label: { Image(systemName: "trash") }
                }
            }
            .buttonStyle(.borderless)
        }
        .padding(.vertical, 5)
    }
}
