// pickfit's text finder for a screenshot (the host's own Vision framework; nothing runs in the box).
// Usage: pickfit-ocr <png>  ->  one JSON array of {"text", "x", "y", "w", "h", "conf"} in image pixels, top-left origin.
import AppKit
import Foundation
import Vision

let args = CommandLine.arguments
guard args.count == 2, let image = NSImage(contentsOfFile: args[1]),
      let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    FileHandle.standardError.write("usage: pickfit-ocr <png>\n".data(using: .utf8)!)
    exit(2)
}
let width = Double(cg.width), height = Double(cg.height)
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = false
do {
    try VNImageRequestHandler(cgImage: cg, options: [:]).perform([request])
} catch {
    FileHandle.standardError.write("vision failed: \(error)\n".data(using: .utf8)!)
    exit(1)
}
var out: [[String: Any]] = []
for observation in request.results ?? [] {
    guard let best = observation.topCandidates(1).first else { continue }
    let b = observation.boundingBox  // normalized, bottom-left origin
    out.append(["text": best.string, "conf": Double(best.confidence),
                "x": Int((b.minX * width).rounded()), "y": Int(((1 - b.maxY) * height).rounded()),
                "w": Int((b.width * width).rounded()), "h": Int((b.height * height).rounded())])
}
let data = try JSONSerialization.data(withJSONObject: out, options: [])
FileHandle.standardOutput.write(data)
FileHandle.standardOutput.write("\n".data(using: .utf8)!)
