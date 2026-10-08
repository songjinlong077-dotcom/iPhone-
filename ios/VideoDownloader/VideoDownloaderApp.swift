import SwiftUI

@main
struct VideoDownloaderApp: App {
    @StateObject private var settings: SettingsStore
    @StateObject private var model: AppModel

    init() {
        let settings = SettingsStore()
        _settings = StateObject(wrappedValue: settings)
        _model = StateObject(wrappedValue: AppModel(settings: settings))
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(settings)
                .environmentObject(model)
        }
    }
}
