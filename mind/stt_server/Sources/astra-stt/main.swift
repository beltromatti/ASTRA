// astra-stt — speech recognition for the ASTRA mind, on the Neural Engine (Parakeet TDT 0.6B v3 family via FluidAudio).
//
// A child process of the mind: it reads requests on stdin and answers with one JSON line per request on stdout (logs go
// to stderr). Requests are a JSON line, optionally followed by a binary payload:
//
//   {"op":"transcribe","id":7,"n":48000,"lang":"it"}\n  + n little-endian int16 samples, 16 kHz mono
//   {"op":"ping","id":8}\n
//   {"op":"quit"}\n
//
// Answers:
//   {"ready":true,"model":"ultra","units":"ane","load_ms":812,"warm_ms":95}
//   {"id":7,"ok":true,"text":"…","conf":0.94,"ms":41,"dur":3.0,"words":[{"w":"Timoniere,","s":0.12,"e":0.7}]}
//   {"id":7,"ok":false,"error":"…"}
//
// The Neural Engine keeps the GPU free for the game; the preprocessor runs on the CPU (FluidAudio's choice).
import CoreML
import Foundation
import FluidAudio

setvbuf(stderr, nil, _IOLBF, 0)

func log(_ s: String) {
    FileHandle.standardError.write(Data(("[astra-stt] " + s + "\n").utf8))
}

func emit(_ obj: [String: Any]) {
    guard var data = try? JSONSerialization.data(withJSONObject: obj, options: [.withoutEscapingSlashes]) else { return }
    data.append(0x0A)
    FileHandle.standardOutput.write(data)
}

// ------------------------------------------------------------------------------------------------ arguments
var modelName = "ultra"
var modelsRoot: URL? = nil
var unitsName = "ane"
var argv = Array(CommandLine.arguments.dropFirst())
while !argv.isEmpty {
    let a = argv.removeFirst()
    switch a {
    case "--model": modelName = argv.isEmpty ? modelName : argv.removeFirst()
    case "--models-dir": if !argv.isEmpty { modelsRoot = URL(fileURLWithPath: argv.removeFirst(), isDirectory: true) }
    case "--compute": unitsName = argv.isEmpty ? unitsName : argv.removeFirst()
    default: log("ignoring argument \(a)")
    }
}

let version: AsrModelVersion
switch modelName {
case "v3": version = .v3
case "redux": version = .redux
case "v2": version = .v2
default: version = .ultra
}
// where the models live: <root>/<repo folder> (FluidAudio's own layout); no root: its default cache in Application Support
let repoFolder: String
switch version {
case .ultra: repoFolder = "parakeet-ultra-coreml"
case .redux: repoFolder = "parakeet-redux-coreml"
case .v2: repoFolder = "parakeet-tdt-0.6b-v2-coreml"
default: repoFolder = "parakeet-tdt-0.6b-v3-coreml"
}
let modelsDir: URL? = modelsRoot?.appendingPathComponent(repoFolder, isDirectory: true)
let units: MLComputeUnits
switch unitsName {
case "gpu": units = .cpuAndGPU
case "cpu": units = .cpuOnly
case "all": units = .all
default: units = .cpuAndNeuralEngine
}

// ------------------------------------------------------------------------------------------------ stdin reader
final class StdinReader {
    private var buf = [UInt8]()
    private var pos = 0
    private var eof = false

    private func fill() -> Bool {
        if eof { return false }
        var tmp = [UInt8](repeating: 0, count: 1 << 16)
        let n = read(0, &tmp, tmp.count)
        if n <= 0 {
            eof = true
            return false
        }
        if pos > 0 && pos == buf.count {
            buf.removeAll(keepingCapacity: true)
            pos = 0
        }
        buf.append(contentsOf: tmp[0..<n])
        return true
    }

    func readLine() -> String? {
        while true {
            if let nl = buf[pos...].firstIndex(of: 0x0A) {
                let line = String(decoding: buf[pos..<nl], as: UTF8.self)
                pos = nl + 1
                return line
            }
            if !fill() { return nil }
        }
    }

    func readBytes(_ n: Int) -> [UInt8]? {
        while buf.count - pos < n {
            if !fill() { return nil }
        }
        let out = Array(buf[pos..<(pos + n)])
        pos += n
        return out
    }
}

// ------------------------------------------------------------------------------------------------ load
let t0 = Date()
log("loading Parakeet \(modelName) on \(unitsName)")
let models: AsrModels
do {
    models = try await AsrModels.downloadAndLoad(to: modelsDir, version: version, encoderComputeUnits: units)
} catch {
    emit(["ready": false, "error": "model load failed: \(error)"])
    log("model load failed: \(error)")
    exit(2)
}
let asr = AsrManager(config: .default)
do {
    try await asr.loadModels(models)
} catch {
    emit(["ready": false, "error": "loadModels failed: \(error)"])
    exit(2)
}
let loadMs = Int(Date().timeIntervalSince(t0) * 1000)

// One warm-up decode compiles/loads the Neural Engine program: the first real request must not pay for it.
func decode(_ samples: [Float], lang: String?) async throws -> ASRResult {
    var state = TdtDecoderState.make(decoderLayers: await asr.decoderLayerCount)
    let language = lang.flatMap { Language(rawValue: $0) }
    return try await asr.transcribe(samples, decoderState: &state, language: language)
}

let tw = Date()
do {
    var noise = [Float](repeating: 0, count: 16000 * 2)
    var seed: UInt32 = 12345
    for i in 0..<noise.count {
        seed = seed &* 1664525 &+ 1013904223
        noise[i] = (Float(seed >> 8) / Float(1 << 24) - 0.5) * 0.02
    }
    _ = try await decode(noise, lang: nil)
} catch {
    log("warm-up decode failed (not fatal): \(error)")
}
emit(["ready": true, "model": modelName, "units": unitsName, "load_ms": loadMs,
      "warm_ms": Int(Date().timeIntervalSince(tw) * 1000)])
log("ready in \(loadMs) ms")

// ------------------------------------------------------------------------------------------------ serve
let reader = StdinReader()
while let line = reader.readLine() {
    guard let data = line.data(using: .utf8),
          let req = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] else {
        continue
    }
    let id = req["id"] ?? 0
    switch (req["op"] as? String) ?? "" {
    case "quit":
        exit(0)
    case "ping":
        emit(["id": id, "ok": true, "pong": true])
    case "transcribe":
        let n = (req["n"] as? Int) ?? 0
        guard n > 0, let raw = reader.readBytes(n * 2) else {
            emit(["id": id, "ok": false, "error": "bad payload"])
            continue
        }
        var samples = [Float](repeating: 0, count: n)
        raw.withUnsafeBytes { p in
            let s = p.bindMemory(to: Int16.self)
            for i in 0..<n { samples[i] = Float(Int16(littleEndian: s[i])) / 32768.0 }
        }
        // the model wants at least a second of audio: shorter phrases are padded with silence
        if samples.count < 16000 {
            samples.append(contentsOf: [Float](repeating: 0, count: 16000 - samples.count))
        }
        let t1 = Date()
        do {
            let r = try await decode(samples, lang: req["lang"] as? String)
            var words: [[String: Any]] = []
            if let timings = r.tokenTimings {
                // sub-word tokens grouped into words on the SentencePiece boundary (a leading space)
                var cur = ""
                var s = 0.0
                var e = 0.0
                for t in timings {
                    let piece = t.token.replacingOccurrences(of: "\u{2581}", with: " ")
                    if piece.hasPrefix(" ") && !cur.isEmpty {
                        words.append(["w": cur.trimmingCharacters(in: .whitespaces), "s": (s * 100).rounded() / 100, "e": (e * 100).rounded() / 100])
                        cur = ""
                    }
                    if cur.isEmpty { s = t.startTime }
                    cur += piece
                    e = t.endTime
                }
                if !cur.isEmpty {
                    words.append(["w": cur.trimmingCharacters(in: .whitespaces), "s": (s * 100).rounded() / 100, "e": (e * 100).rounded() / 100])
                }
            }
            emit(["id": id, "ok": true, "text": r.text, "conf": Double(r.confidence),
                  "ms": Int(Date().timeIntervalSince(t1) * 1000), "dur": Double(n) / 16000.0, "words": words])
        } catch {
            emit(["id": id, "ok": false, "error": "\(error)"])
        }
    default:
        emit(["id": id, "ok": false, "error": "unknown op"])
    }
}
