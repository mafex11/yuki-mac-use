import Foundation

enum BurstBridge {
    static func engage(token: String, port: Int, duration: Double = 30.0) {
        guard let url = URL(string: "http://127.0.0.1:\(port)/safety/burst") else { return }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONSerialization.data(
            withJSONObject: ["duration": duration]
        )
        URLSession.shared.dataTask(with: req) { _, _, error in
            if let error = error {
                NSLog("BurstBridge engage failed: \(error)")
            }
        }.resume()
    }
}
