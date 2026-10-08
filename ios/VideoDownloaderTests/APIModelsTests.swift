import XCTest
@testable import VideoDownloader

final class APIModelsTests: XCTestCase {
    func testTaskResponseDecodesSnakeCaseAndDates() throws {
        let json = """
        {
          "id":"abc", "url":"https://example.com/video", "title":"Demo", "platform":"Example",
          "status":"completed", "progress":100.0, "downloaded_bytes":1024,
          "total_bytes":1024, "speed_bytes":512.0, "eta_seconds":0,
          "resolution":1080, "mode":"best", "error":null, "has_file":true,
          "created_at":"2026-10-08T10:00:00Z", "updated_at":"2026-10-08T10:01:00Z",
          "expires_at":"2026-10-09T10:00:00Z", "attempt":1
        }
        """
        let task = try APIClient.makeDecoder().decode(DownloadTaskInfo.self, from: Data(json.utf8))
        XCTAssertEqual(task.id, "abc")
        XCTAssertEqual(task.statusText, "已完成")
        XCTAssertTrue(task.hasFile)
        XCTAssertFalse(task.isActive)
    }

    func testMediaResponseDecodesFormats() throws {
        let json = """
        {"url":"https://example.com/v","title":"Demo","uploader":"Owner","platform":"Example",
         "duration":65,"thumbnail_url":"https://example.com/i.jpg",
         "formats":[{"height":2160,"label":"4K"},{"height":1080,"label":"1080p"}]}
        """
        let media = try APIClient.makeDecoder().decode(MediaInfo.self, from: Data(json.utf8))
        XCTAssertEqual(media.formats.first?.height, 2160)
        XCTAssertEqual(media.durationText, "01:05")
    }
}
