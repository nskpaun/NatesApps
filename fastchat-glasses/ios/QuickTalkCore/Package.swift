// swift-tools-version: 6.0
// The conversation, reply prompt and gesture logic shared by the iPhone app. It has no UIKit or
// Meta toolkit dependencies, so `swift test` runs it on macOS or Linux.
import PackageDescription

let package = Package(
    name: "QuickTalkCore",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [
        .library(name: "QuickTalkCore", targets: ["QuickTalkCore"]),
    ],
    targets: [
        .target(name: "QuickTalkCore"),
        .testTarget(name: "QuickTalkCoreTests", dependencies: ["QuickTalkCore"]),
    ]
)
