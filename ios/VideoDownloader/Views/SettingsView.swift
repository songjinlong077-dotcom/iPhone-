import SwiftUI

struct SettingsView: View {
    @EnvironmentObject private var settings: SettingsStore
    @EnvironmentObject private var model: AppModel
    @State private var showKey = false

    var body: some View {
        Form {
            Section("云端服务器") {
                TextField("https://api.example.com", text: $settings.serverURLString)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .keyboardType(.URL)
                HStack {
                    Group {
                        if showKey { TextField("API Key", text: $settings.apiKey) }
                        else { SecureField("API Key", text: $settings.apiKey) }
                    }
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    Button { showKey.toggle() } label: { Image(systemName: showKey ? "eye.slash" : "eye") }
                }
                Button("保存设置") {
                    do {
                        try settings.save()
                        model.noticeMessage = settings.savedMessage
                    } catch { model.errorMessage = error.localizedDescription }
                }
            }
            Section("安全") {
                Label("API Key 保存于 iPhone Keychain", systemImage: "key.fill")
                Label("服务器地址必须使用 HTTPS", systemImage: "lock.shield")
                Text("不要把 API Key 发给其他人，也不要在截图中展示。")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            Section("安装说明") {
                Text("使用免费 Apple 账号安装时，签名通常在 7 天后失效，需要在 Windows 上通过 Sideloadly 重新签名安装。")
                    .font(.footnote).foregroundStyle(.secondary)
            }
        }
        .navigationTitle("设置")
    }
}
