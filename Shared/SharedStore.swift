import Foundation

// 进程内缓存上次成功取到的快照。Agent 短暂不可达时回退展示，避免卡片闪空。
// 说明：App 与小组件各存各的（ad-hoc 签名无 App Group），但都从同一个本地 Agent 取数，
//       所以两边内容一致。
enum SharedStore {
    private static let key = "lastUsageSnapshot"
    private static let defaults = UserDefaults.standard

    static func write(_ snapshot: UsageSnapshot) {
        guard let data = try? JSONEncoder().encode(snapshot) else { return }
        defaults.set(data, forKey: key)
    }

    static func read() -> UsageSnapshot? {
        guard let data = defaults.data(forKey: key) else { return nil }
        return try? JSONDecoder().decode(UsageSnapshot.self, from: data)
    }
}
