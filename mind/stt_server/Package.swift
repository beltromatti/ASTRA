// swift-tools-version: 6.0
// astra-stt: speech recognition for the ASTRA mind on the Apple Neural Engine (Parakeet TDT 0.6B v3 / Ultra, via
// FluidAudio, Apache-2.0). A tiny child process of the mind: PCM in on stdin, JSON lines out on stdout.
import PackageDescription

let package = Package(
    name: "astra-stt",
    platforms: [.macOS(.v14)],
    dependencies: [
        .package(url: "https://github.com/FluidInference/FluidAudio.git", from: "0.12.4"),
    ],
    targets: [
        .executableTarget(
            name: "astra-stt",
            dependencies: [.product(name: "FluidAudio", package: "FluidAudio")],
            path: "Sources/astra-stt",
            swiftSettings: [.swiftLanguageMode(.v5)]
        ),
    ]
)
