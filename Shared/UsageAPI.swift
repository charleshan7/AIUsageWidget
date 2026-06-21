import Foundation

enum UsageAPI {
    static var endpoint: String {
        (Bundle.main.object(forInfoDictionaryKey: "AIUsageEndpoint") as? String)
            .flatMap { $0.isEmpty ? nil : $0 } ?? "http://127.0.0.1:47615/usage"
    }

    /// 从本地 Agent 取数。失败时回退上次缓存，再不行返回「未连接」兜底，保证总有内容渲染。
    static func fetch() async -> UsageSnapshot {
        guard let url = URL(string: endpoint) else { return SharedStore.read() ?? .disconnected }
        var req = URLRequest(url: url)
        req.timeoutInterval = 8
        req.cachePolicy = .reloadIgnoringLocalCacheData
        do {
            let (data, _) = try await URLSession.shared.data(for: req)
            let snapshot = try JSONDecoder().decode(UsageSnapshot.self, from: data)
            SharedStore.write(snapshot)
            return snapshot
        } catch {
            return SharedStore.read() ?? .disconnected
        }
    }
}
