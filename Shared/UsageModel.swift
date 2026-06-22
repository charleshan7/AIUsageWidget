import Foundation

// 与 usage-agent.py 输出的 JSON 一一对应。

struct UsageWindow: Codable, Hashable {
    let percent: Int
    let resetsAt: Int?

    enum CodingKeys: String, CodingKey {
        case percent
        case resetsAt = "resets_at"
    }
}

struct ProductUsage: Codable, Hashable {
    let ok: Bool
    let plan: String?
    let fiveHour: UsageWindow?
    let sevenDay: UsageWindow?
    let stale: Bool?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case ok, plan, stale, error
        case fiveHour = "five_hour"
        case sevenDay = "seven_day"
    }
}

struct UsageSnapshot: Codable, Hashable {
    let updated: Int
    let claude: ProductUsage
    let codex: ProductUsage
    var theme: String? = nil   // "system" | "light" | "dark"
}

extension ProductUsage {
    static func failed(_ message: String) -> ProductUsage {
        ProductUsage(ok: false, plan: nil, fiveHour: nil, sevenDay: nil, stale: nil, error: message)
    }
    static func demo(_ five: Int, _ seven: Int, plan: String? = nil) -> ProductUsage {
        let now = Int(Date().timeIntervalSince1970)
        return ProductUsage(ok: true, plan: plan,
                            fiveHour: UsageWindow(percent: five, resetsAt: now + 3600 * 4),
                            sevenDay: UsageWindow(percent: seven, resetsAt: now + 3600 * 24 * 6),
                            stale: nil, error: nil)
    }
}

extension UsageSnapshot {
    /// 预览 / 占位用的假数据。
    static let sample = UsageSnapshot(
        updated: Int(Date().timeIntervalSince1970),
        claude: .demo(26, 20, plan: "pro"),
        codex: .demo(35, 23))

    /// Agent 不可达时的兜底快照。
    static let disconnected = UsageSnapshot(
        updated: Int(Date().timeIntervalSince1970),
        claude: .failed("未连接"),
        codex: .failed("未连接"))
}
