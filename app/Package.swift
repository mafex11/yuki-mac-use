// swift-tools-version:5.10
import PackageDescription

let package = Package(
    name: "Yuki",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "Yuki", targets: ["Yuki"]),
    ],
    targets: [
        .executableTarget(
            name: "Yuki",
            path: "Yuki",
            linkerSettings: [
                .linkedFramework("AppKit"),
                .linkedFramework("Carbon"),
                .linkedFramework("SwiftUI"),
            ]
        ),
    ]
)
