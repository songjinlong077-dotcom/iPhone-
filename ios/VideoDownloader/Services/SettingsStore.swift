import Foundation
import Combine

@MainActor
final class SettingsStore: ObservableObject {
    private enum Keys { static let serverURL = "server-url" }

    @Published var serverURLString: String
    @Published var apiKey: String
    @Published var savedMessage = ""

    init() {
        serverURLString = UserDefaults.standard.string(forKey: Keys.serverURL) ?? ""
        apiKey = KeychainStore.load()
    }

    func configuration() throws -> APIConfiguration {
        let raw = serverURLString.trimmingCharacters(in: .whitespacesAndNewlines)
        let key = apiKey.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let url = URL(string: raw), url.scheme?.lowercased() == "https", url.host != nil, key.count >= 16 else {
            throw APIClientError.invalidConfiguration
        }
        return APIConfiguration(baseURL: url, apiKey: key)
    }

    func save() throws {
        _ = try configuration()
        UserDefaults.standard.set(serverURLString.trimmingCharacters(in: .whitespacesAndNewlines), forKey: Keys.serverURL)
        try KeychainStore.save(apiKey.trimmingCharacters(in: .whitespacesAndNewlines))
        savedMessage = "设置已安全保存"
    }
}
