import Foundation

enum LaunchAgent {
    static let label = "com.yuki.agent"

    static func install() throws {
        let bundle = Bundle.main.bundleURL.path
        let plist: [String: Any] = [
            "Label": label,
            "ProgramArguments": ["\(bundle)/Contents/MacOS/Yuki"],
            "RunAtLoad": true,
            "KeepAlive": true,
        ]
        let dir = FileManager.default
            .urls(for: .libraryDirectory, in: .userDomainMask)
            .first!
            .appendingPathComponent("LaunchAgents")
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let url = dir.appendingPathComponent("\(label).plist")
        let data = try PropertyListSerialization.data(
            fromPropertyList: plist, format: .xml, options: 0
        )
        try data.write(to: url)
    }

    static func uninstall() throws {
        let url = FileManager.default
            .urls(for: .libraryDirectory, in: .userDomainMask)
            .first!
            .appendingPathComponent("LaunchAgents/\(label).plist")
        try? FileManager.default.removeItem(at: url)
    }
}
