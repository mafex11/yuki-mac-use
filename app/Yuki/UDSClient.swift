import Foundation
import Network

/// Minimal HTTP/1.1 client over a Unix Domain Socket using NWConnection.
/// Supports buffered request/response (postJSON, getJSON) and a
/// line-streaming SSE request (streamSSE).
final class UDSClient {
    private let socketPath: String

    init(socketPath: String) { self.socketPath = socketPath }

    private func makeConnection() -> NWConnection {
        let endpoint = NWEndpoint.unix(path: socketPath)
        let params = NWParameters.tcp
        return NWConnection(to: endpoint, using: params)
    }

    /// Buffered POST returning the full response body as Data.
    func postJSON(path: String, body: Data) async throws -> Data {
        try await sendBuffered(method: "POST", path: path, body: body)
    }

    /// Buffered GET returning the full response body as Data.
    func getJSON(path: String) async throws -> Data {
        try await sendBuffered(method: "GET", path: path, body: Data())
    }

    private func sendBuffered(method: String, path: String, body: Data) async throws -> Data {
        try await withCheckedThrowingContinuation { cont in
            let conn = makeConnection()
            var received = Data()
            var resumed = false
            func finish(_ result: Result<Data, Error>) {
                if resumed { return }
                resumed = true
                conn.cancel()
                cont.resume(with: result)
            }
            conn.stateUpdateHandler = { state in
                if case .failed(let err) = state { finish(.failure(err)) }
            }
            conn.start(queue: .global())
            let req = Self.httpRequest(method: method, path: path, body: body)
            conn.send(content: req, completion: .contentProcessed { err in
                if let err = err { finish(.failure(err)) }
            })
            func readMore() {
                conn.receive(minimumIncompleteLength: 1, maximumLength: 65536) {
                    data, _, isComplete, err in
                    if let data = data { received.append(data) }
                    if let err = err { finish(.failure(err)); return }
                    if isComplete {
                        finish(.success(Self.stripHeaders(received)))
                    } else {
                        readMore()
                    }
                }
            }
            readMore()
        }
    }

    /// Streaming POST: calls onEvent for each SSE "data:" line as it arrives.
    func streamSSE(path: String, body: Data,
                   onEvent: @escaping (String) -> Void,
                   onDone: @escaping () -> Void) {
        let conn = makeConnection()
        var buffer = Data()
        var headersDone = false
        var finished = false
        func done() {
            if finished { return }
            finished = true
            conn.cancel()
            onDone()
        }
        conn.stateUpdateHandler = { state in
            switch state {
            case .failed, .cancelled: done()
            default: break
            }
        }
        conn.start(queue: .global())
        let req = Self.httpRequest(method: "POST", path: path, body: body)
        conn.send(content: req, completion: .contentProcessed { _ in })
        func readMore() {
            conn.receive(minimumIncompleteLength: 1, maximumLength: 65536) {
                data, _, isComplete, err in
                if let data = data {
                    buffer.append(data)
                    if !headersDone,
                       let range = buffer.range(of: Data("\r\n\r\n".utf8)) {
                        buffer.removeSubrange(buffer.startIndex..<range.upperBound)
                        headersDone = true
                    }
                    if headersDone {
                        while let nl = buffer.firstIndex(of: 0x0A) {
                            let lineData = buffer[buffer.startIndex..<nl]
                            buffer.removeSubrange(buffer.startIndex...nl)
                            if let line = String(data: lineData, encoding: .utf8) {
                                let trimmed = line.trimmingCharacters(
                                    in: .whitespacesAndNewlines)
                                if trimmed.hasPrefix("data:") {
                                    let payload = String(trimmed.dropFirst(5))
                                        .trimmingCharacters(in: .whitespaces)
                                    onEvent(payload)
                                }
                            }
                        }
                    }
                }
                if let _ = err { done(); return }
                if isComplete { done() } else { readMore() }
            }
        }
        readMore()
    }

    private static func httpRequest(method: String, path: String, body: Data) -> Data {
        var head = "\(method) \(path) HTTP/1.1\r\n"
        head += "Host: yuki\r\n"
        head += "Content-Type: application/json\r\n"
        head += "Content-Length: \(body.count)\r\n"
        head += "Connection: close\r\n\r\n"
        var data = Data(head.utf8)
        data.append(body)
        return data
    }

    private static func stripHeaders(_ data: Data) -> Data {
        if let range = data.range(of: Data("\r\n\r\n".utf8)) {
            return data.subdata(in: range.upperBound..<data.endIndex)
        }
        return data
    }
}
