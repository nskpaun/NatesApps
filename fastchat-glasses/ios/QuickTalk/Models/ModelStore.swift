import CryptoKit
import Foundation

struct ModelStore: Sendable {
    struct ModelFile: Sendable {
        let path: String
        let url: String
        let bytes: Int64
        var sha256: String?
    }

    let directory: URL

    init() {
        directory = URL.applicationSupportDirectory.appending(path: "QuickTalk/Models", directoryHint: .isDirectory)
    }

    static let totalBytes = catalog.reduce(Int64(0)) { $0 + $1.bytes }

    func path(_ name: String) -> String {
        directory.appending(path: name).path(percentEncoded: false)
    }

    func presentBytes() -> Int64 {
        Self.catalog.reduce(0) { $0 + (contains($1) ? $1.bytes : 0) }
    }

    func prepareDirectory() throws {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        var modelDirectory = directory
        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        try modelDirectory.setResourceValues(values)
    }

    func download(progress: @escaping @Sendable (Int64) -> Void) async throws {
        try prepareDirectory()
        let files = FileManager.default
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 60
        let session = URLSession(configuration: configuration)
        defer { session.invalidateAndCancel() }

        var completed = presentBytes()
        progress(completed)
        for model in Self.catalog where !contains(model) {
            try Task.checkCancellation()
            guard let url = URL(string: model.url) else { throw DownloadError.invalidURL }
            let baseline = completed
            let delegate = DownloadProgress { progress(baseline + min(model.bytes, $0)) }
            let (temporary, response) = try await session.download(for: URLRequest(url: url), delegate: delegate)
            defer { try? files.removeItem(at: temporary) }
            guard let response = response as? HTTPURLResponse, response.statusCode == 200 else {
                throw DownloadError.server(model.path, (response as? HTTPURLResponse)?.statusCode)
            }
            try validate(temporary, model: model)
            try Task.checkCancellation()

            let destination = directory.appending(path: model.path)
            try files.createDirectory(at: destination.deletingLastPathComponent(), withIntermediateDirectories: true)
            if files.fileExists(atPath: destination.path) {
                _ = try files.replaceItemAt(destination, withItemAt: temporary)
            } else {
                try files.moveItem(at: temporary, to: destination)
            }
            completed += model.bytes
            progress(completed)
        }
    }

    private func contains(_ model: ModelFile) -> Bool {
        let file = directory.appending(path: model.path)
        let values = try? file.resourceValues(forKeys: [.isRegularFileKey, .fileSizeKey])
        return values?.isRegularFile == true && values?.fileSize == Int(model.bytes)
    }

    private func validate(_ file: URL, model: ModelFile) throws {
        let size = try file.resourceValues(forKeys: [.fileSizeKey]).fileSize
        guard size == Int(model.bytes) else { throw DownloadError.corrupt(model.path) }
        guard let expected = model.sha256 else { return }

        let input = try FileHandle(forReadingFrom: file)
        defer { try? input.close() }
        var sha = SHA256()
        while let chunk = try input.read(upToCount: 1 << 20), !chunk.isEmpty {
            try Task.checkCancellation()
            sha.update(data: chunk)
        }
        let actual = sha.finalize().map { String(format: "%02x", $0) }.joined()
        guard actual == expected else { throw DownloadError.corrupt(model.path) }
    }
}

private final class DownloadProgress: NSObject, URLSessionDownloadDelegate, Sendable {
    private let progress: @Sendable (Int64) -> Void

    init(_ progress: @escaping @Sendable (Int64) -> Void) {
        self.progress = progress
    }

    func urlSession(
        _ session: URLSession, downloadTask: URLSessionDownloadTask,
        didWriteData bytesWritten: Int64, totalBytesWritten: Int64, totalBytesExpectedToWrite: Int64
    ) {
        progress(totalBytesWritten)
    }

    func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask, didFinishDownloadingTo location: URL) {}
}

private enum DownloadError: LocalizedError {
    case invalidURL
    case server(String, Int?)
    case corrupt(String)

    var errorDescription: String? {
        switch self {
        case .invalidURL: "A model download URL is invalid."
        case let .server(path, status): "Could not download \(path) (HTTP \(status ?? 0))."
        case let .corrupt(path): "The download for \(path) did not pass verification. Try again."
        }
    }
}
