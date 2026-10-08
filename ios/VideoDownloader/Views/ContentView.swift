import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        TabView {
            NavigationStack { HomeView() }
                .tabItem { Label("下载", systemImage: "arrow.down.circle") }
            NavigationStack { TaskListView() }
                .tabItem { Label("任务", systemImage: "list.bullet.rectangle") }
            NavigationStack { SettingsView() }
                .tabItem { Label("设置", systemImage: "gearshape") }
        }
        .task {
            await model.refreshTasks(showErrors: false)
            model.startPolling()
        }
        .onDisappear { model.stopPolling() }
        .alert("操作失败", isPresented: Binding(
            get: { model.errorMessage != nil },
            set: { if !$0 { model.errorMessage = nil } }
        )) {
            Button("知道了", role: .cancel) { model.errorMessage = nil }
        } message: { Text(model.errorMessage ?? "未知错误") }
        .alert("提示", isPresented: Binding(
            get: { model.noticeMessage != nil },
            set: { if !$0 { model.noticeMessage = nil } }
        )) {
            Button("好", role: .cancel) { model.noticeMessage = nil }
        } message: { Text(model.noticeMessage ?? "") }
        .sheet(item: $model.exportFile) { file in
            DocumentExporter(fileURL: file.url)
        }
    }
}
