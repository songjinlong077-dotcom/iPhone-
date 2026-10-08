import SwiftUI

struct HomeView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        Form {
            Section("视频网址") {
                TextField("粘贴 YouTube、Instagram、TikTok 等网址", text: $model.inputURL, axis: .vertical)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .keyboardType(.URL)
                Button {
                    Task { await model.analyze() }
                } label: {
                    if model.isAnalyzing { ProgressView() } else { Label("解析视频", systemImage: "magnifyingglass") }
                }
                .disabled(model.isAnalyzing)
            }

            if let media = model.media {
                Section("视频信息") {
                    HStack(alignment: .top, spacing: 12) {
                        AsyncImage(url: URL(string: media.thumbnailURL)) { image in
                            image.resizable().scaledToFill()
                        } placeholder: {
                            Rectangle().fill(.secondary.opacity(0.15)).overlay { Image(systemName: "video") }
                        }
                        .frame(width: 112, height: 72).clipShape(RoundedRectangle(cornerRadius: 8))
                        VStack(alignment: .leading, spacing: 5) {
                            Text(media.title).font(.headline).lineLimit(3)
                            Text("\(media.platform) · \(media.uploader)").font(.caption).foregroundStyle(.secondary)
                            Text(media.durationText).font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                        }
                    }
                    Picker("画质", selection: $model.selectedResolution) {
                        Text("自动最高").tag(Optional<Int>.none)
                        ForEach(media.formats) { format in
                            Text("\(format.height)p · \(format.label)").tag(Optional(format.height))
                        }
                    }
                    Picker("模式", selection: $model.selectedMode) {
                        ForEach(DownloadMode.allCases) { mode in Text(mode.title).tag(mode) }
                    }
                    Button {
                        Task { await model.createDownload() }
                    } label: {
                        if model.isCreatingTask { ProgressView() } else { Label("开始云端下载", systemImage: "icloud.and.arrow.down") }
                    }
                    .disabled(model.isCreatingTask)
                }
            }

            Section {
                Text("只下载您有权保存且平台允许访问的内容。本 App 不绕过 DRM、付费、会员或私密访问限制。")
                    .font(.footnote).foregroundStyle(.secondary)
            }
        }
        .navigationTitle("视频下载")
    }
}
