import Foundation

struct APIConfiguration {
    let baseURL: URL
    let apiKey: String
}

enum APIClientError: LocalizedError {
    case invalidConfiguration
    case invalidResponse
    case server(status: Int, message: String)
    case emptyFile

    var errorDescription: String? {
        switch self {
        case .invalidConfiguration: return "请先填写有效的 HTTPS 服务器地址和 API Key。"
        case .invalidResponse: return "服务器返回了无法识别的响应。"
        case let .server(status, message): return "服务器错误（\(status)）：\(message)"
        case .emptyFile: return "服务器没有返回可保存的文件。"
        }
    }
}

struct APIClient {
    let configuration: APIConfiguration
    var session: URLSession = .shared

    static func makeDecoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }

    private func makeRequest(path: String, method: String = "GET", body: Data? = nil) throws -> URLRequest {
        let cleanPath = path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        let url = cleanPath.split(separator: "/").reduce(configuration.baseURL) { partial, component in
            partial.appendingPathComponent(String(component))
        }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.httpBody = body
        request.timeoutInterval = 60
        request.setValue("Bearer \(configuration.apiKey)", forHTTPHeaderField: "Authorization")
        if body != nil { request.setValue("application/json", forHTTPHeaderField: "Content-Type") }
        return request
    }

    private func validatedData(for request: URLRequest) async throws -> Data {
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw APIClientError.invalidResponse }
        guard 200..<300 ~= http.statusCode else {
            let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
            let detail = object?["detail"] as? String ?? String(data: data, encoding: .utf8) ?? "未知错误"
            throw APIClientError.server(status: http.statusCode, message: detail)
        }
        return data
    }

    private func send<Response: Decodable, Body: Encodable>(
        path: String, method: String = "POST", body: Body
    ) async throws -> Response {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let data = try await validatedData(for: makeRequest(path: path, method: method, body: encoder.encode(body)))
        return try Self.makeDecoder().decode(Response.self, from: data)
    }

    func analyze(url: String) async throws -> MediaInfo {
        try await send(path: "v1/media/analyze", body: AnalyzeBody(url: url))
    }

    func createTask(url: String, resolution: Int?, mode: DownloadMode) async throws -> DownloadTaskInfo {
        try await send(path: "v1/tasks", body: TaskCreateBody(url: url, resolution: resolution, mode: mode))
    }

    func tasks() async throws -> [DownloadTaskInfo] {
        let data = try await validatedData(for: makeRequest(path: "v1/tasks"))
        return try Self.makeDecoder().decode([DownloadTaskInfo].self, from: data)
    }

    func cancel(id: String) async throws -> DownloadTaskInfo {
        let data = try await validatedData(for: makeRequest(path: "v1/tasks/\(id)/cancel", method: "POST"))
        return try Self.makeDecoder().decode(DownloadTaskInfo.self, from: data)
    }

    func retry(id: String) async throws -> DownloadTaskInfo {
        let data = try await validatedData(for: makeRequest(path: "v1/tasks/\(id)/retry", method: "POST"))
        return try Self.makeDecoder().decode(DownloadTaskInfo.self, from: data)
    }

    func delete(id: String) async throws {
        _ = try await validatedData(for: makeRequest(path: "v1/tasks/\(id)", method: "DELETE"))
    }

    func download(id: String) async throws -> LocalVideoFile {
        let request = try makeRequest(path: "v1/tasks/\(id)/file")
        let (temporaryURL, response) = try await session.download(for: request)
        guard let http = response as? HTTPURLResponse else { throw APIClientError.invalidResponse }
        guard 200..<300 ~= http.statusCode else {
            throw APIClientError.server(status: http.statusCode, message: "文件下载失败")
        }
        let suggested = response.suggestedFilename ?? "video.mp4"
        let safeName = suggested.replacingOccurrences(of: "/", with: "_")
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        var destination = documents.appendingPathComponent(safeName)
        if FileManager.default.fileExists(atPath: destination.path) {
            destination = documents.appendingPathComponent("\(UUID().uuidString)-\(safeName)")
        }
        try FileManager.default.moveItem(at: temporaryURL, to: destination)
        let fileSize = try destination.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0
        guard fileSize > 0 else {
            throw APIClientError.emptyFile
        }
        return LocalVideoFile(url: destination)
    }
}
