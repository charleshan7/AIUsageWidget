import SwiftUI

// ---- 配色（浅/深两套，可被「外观」偏好强制覆盖）----

struct Palette {
    let claude: Color
    let codex: Color
    let textPrimary: Color
    let secondary: Color
    let tertiary: Color
    let track: Color
    let cardBackground: Color

    static let light = Palette(
        claude: Color(red: 0.78, green: 0.52, blue: 0.44),
        codex: Color(red: 0.42, green: 0.64, blue: 0.57),
        textPrimary: Color(red: 0.15, green: 0.15, blue: 0.17),
        secondary: Color(red: 0.46, green: 0.47, blue: 0.51),
        tertiary: Color(red: 0.64, green: 0.65, blue: 0.69),
        track: Color(red: 0.90, green: 0.90, blue: 0.92),
        cardBackground: Color(red: 0.99, green: 0.99, blue: 0.985))

    static let dark = Palette(
        claude: Color(red: 0.82, green: 0.56, blue: 0.48),
        codex: Color(red: 0.46, green: 0.68, blue: 0.60),
        textPrimary: Color(red: 0.95, green: 0.95, blue: 0.96),
        secondary: Color(red: 0.62, green: 0.63, blue: 0.68),
        tertiary: Color(red: 0.45, green: 0.46, blue: 0.50),
        track: Color(red: 0.22, green: 0.22, blue: 0.26),
        cardBackground: Color(red: 0.08, green: 0.085, blue: 0.11))

    static func of(_ scheme: ColorScheme) -> Palette { scheme == .dark ? .dark : .light }
}

private struct PaletteKey: EnvironmentKey { static let defaultValue: Palette = .light }
extension EnvironmentValues {
    var palette: Palette {
        get { self[PaletteKey.self] }
        set { self[PaletteKey.self] = newValue }
    }
}

/// 外观偏好（"system"/"light"/"dark"）→ 强制配色；nil 表示跟随系统。
enum AppTheme {
    static func scheme(_ raw: String?) -> ColorScheme? {
        switch raw {
        case "light": return .light
        case "dark": return .dark
        default: return nil
        }
    }
}

func severityColor(_ percent: Int) -> Color {
    if percent >= 80 { return Color(red: 0.80, green: 0.45, blue: 0.42) }   // 柔红
    if percent >= 50 { return Color(red: 0.85, green: 0.66, blue: 0.36) }   // 柔黄
    return Color(red: 0.46, green: 0.66, blue: 0.49)                        // 柔绿
}

func resetCountdown(_ unix: Int?) -> String {
    guard let unix = unix else { return "" }
    let remaining = Double(unix) - Date().timeIntervalSince1970
    if remaining <= 0 { return "即将重置" }
    let hours = remaining / 3600
    if hours < 1 { return "\(Int((remaining / 60).rounded())) 分钟后重置" }
    if hours < 24 { return "约 \(Int(hours.rounded())) 小时后重置" }
    return "\(Int((hours / 24).rounded())) 天后重置"
}

func resetAbsolute(_ unix: Int?) -> String {
    guard let unix = unix else { return "" }
    let date = Date(timeIntervalSince1970: Double(unix))
    let fmt = DateFormatter()
    fmt.locale = Locale(identifier: "zh_CN")
    if Calendar.current.isDateInToday(date) {
        fmt.dateFormat = "HH:mm"
        return "今天 " + fmt.string(from: date)
    }
    fmt.dateFormat = "M/d HH:mm"
    return fmt.string(from: date)
}

// 重置说明行。窗口已重置（resets_at 为空）时显示「已重置」。
func resetLine(_ w: UsageWindow, absolute: Bool) -> String {
    guard w.resetsAt != nil else { return "已重置" }
    return absolute ? "\(resetCountdown(w.resetsAt)) · \(resetAbsolute(w.resetsAt))"
                    : resetCountdown(w.resetsAt)
}

// ---- Token 统计格式化 ----

func fmtTokens(_ n: Int) -> String {
    let d = Double(n)
    if d >= 1e9 { return String(format: "%.2fB", d / 1e9) }
    if d >= 1e6 { return String(format: "%.1fM", d / 1e6) }
    if d >= 1e3 { return String(format: "%.1fK", d / 1e3) }
    return "\(n)"
}

func fmtCost(_ c: Double) -> String {
    if c >= 100 { return String(format: "$%.0f", c) }
    if c >= 1 { return String(format: "$%.1f", c) }
    return String(format: "$%.2f", c)
}

// ---- Token 统计区块（菜单栏面板用）----

struct StatCell: View {
    @Environment(\.palette) private var palette
    let bucket: StatBucket?
    var body: some View {
        VStack(alignment: .trailing, spacing: 1) {
            Text(bucket.map { fmtTokens($0.tokens) } ?? "—")
                .font(.system(size: 11, weight: .medium)).foregroundColor(palette.textPrimary)
            Text(bucket.map { fmtCost($0.cost) } ?? "")
                .font(.system(size: 9)).foregroundColor(palette.tertiary)
        }
        .frame(maxWidth: .infinity, alignment: .trailing)
    }
}

struct StatsSection: View {
    @Environment(\.palette) private var palette
    let stats: UsageStats

    private func woolText(_ name: String, _ s: ProductStats?) -> String? {
        guard let cost = s?.monthCost else { return nil }
        if let sub = s?.subPrice, sub > 0 {
            return "\(name) \(fmtCost(cost))（\(String(format: "%.1f", cost / sub))× 订阅）"
        }
        return "\(name) \(fmtCost(cost))"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Token 消耗（API 等值估算）")
                .font(.system(size: 11, weight: .medium)).foregroundColor(palette.secondary)
            HStack {
                Spacer()
                Text("今日").font(.system(size: 10)).foregroundColor(palette.tertiary)
                    .frame(width: 62, alignment: .trailing)
                Text("7 天").font(.system(size: 10)).foregroundColor(palette.tertiary)
                    .frame(width: 62, alignment: .trailing)
                Text("累计").font(.system(size: 10)).foregroundColor(palette.tertiary)
                    .frame(width: 62, alignment: .trailing)
            }
            statRow(name: "Claude", color: palette.claude, s: stats.claude)
            statRow(name: "Codex", color: palette.codex, s: stats.codex)
            let wools = [woolText("Claude", stats.claude),
                         woolText("Codex", stats.codex)].compactMap { $0 }
            if !wools.isEmpty {
                Rectangle().fill(palette.track).frame(height: 0.5).padding(.vertical, 2)
                HStack(alignment: .top, spacing: 8) {
                    Text("本月羊毛").font(.system(size: 10)).foregroundColor(palette.tertiary)
                    VStack(alignment: .leading, spacing: 2) {
                        ForEach(wools, id: \.self) { w in
                            Text(w).font(.system(size: 10)).foregroundColor(palette.secondary)
                        }
                    }
                    Spacer(minLength: 0)
                }
            }
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 10).fill(palette.cardBackground))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(palette.track, lineWidth: 0.5))
    }

    private func statRow(name: String, color: Color, s: ProductStats?) -> some View {
        HStack {
            HStack(spacing: 5) {
                Circle().fill(color).frame(width: 6, height: 6)
                Text(name).font(.system(size: 11, weight: .medium)).foregroundColor(palette.textPrimary)
            }
            Spacer()
            StatCell(bucket: s?.today).frame(width: 62)
            StatCell(bucket: s?.week).frame(width: 62)
            StatCell(bucket: s?.total).frame(width: 62)
        }
    }
}

// ---- 基础组件 ----

struct UsageBar: View {
    @Environment(\.palette) private var palette
    let percent: Int
    var height: CGFloat = 6
    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Capsule().fill(palette.track)
                Capsule().fill(severityColor(percent))
                    .frame(width: max(geo.size.width * CGFloat(min(max(percent, 0), 100)) / 100.0,
                                      percent > 0 ? 3 : 0))
            }
        }
        .frame(height: height)
    }
}

struct ProductHeader: View {
    @Environment(\.palette) private var palette
    let name: String
    let color: Color
    var plan: String? = nil
    var body: some View {
        HStack(spacing: 6) {
            Circle().fill(color).frame(width: 7, height: 7)
            Text(name).font(.system(size: 12, weight: .medium)).foregroundColor(palette.textPrimary)
            if let plan = plan {
                Text(plan.capitalized)
                    .font(.system(size: 9, weight: .medium))
                    .foregroundColor(palette.secondary)
                    .padding(.horizontal, 5).padding(.vertical, 1)
                    .background(Capsule().fill(palette.track))
            }
            Spacer(minLength: 0)
        }
    }
}

// 一条带标签的指标行（中/大卡用）。
struct MetricRow: View {
    @Environment(\.palette) private var palette
    let label: String
    let window: UsageWindow?
    var showReset: Bool = true
    var showAbsolute: Bool = false
    var barHeight: CGFloat = 6

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(label).font(.system(size: 11)).foregroundColor(palette.secondary)
                Spacer()
                Text(window.map { "\($0.percent)%" } ?? "—")
                    .font(.system(size: 11, weight: .medium)).foregroundColor(palette.textPrimary)
            }
            UsageBar(percent: window?.percent ?? 0, height: barHeight)
            if showReset, let w = window {
                Text(resetLine(w, absolute: showAbsolute))
                    .font(.system(size: 10)).foregroundColor(palette.tertiary)
            }
        }
    }
}

// 失败态占位。
struct ProductError: View {
    @Environment(\.palette) private var palette
    let message: String
    var body: some View {
        Text(message).font(.system(size: 11)).foregroundColor(palette.tertiary)
    }
}

// ---- 小卡 ----

struct SmallMetric: View {
    @Environment(\.palette) private var palette
    let label: String
    let window: UsageWindow?
    var body: some View {
        HStack(spacing: 6) {
            Text(label).font(.system(size: 11)).foregroundColor(palette.secondary).frame(width: 16, alignment: .leading)
            UsageBar(percent: window?.percent ?? 0, height: 5)
            Text(window.map { "\($0.percent)%" } ?? "—")
                .font(.system(size: 11, weight: .medium)).foregroundColor(palette.textPrimary)
                .lineLimit(1).minimumScaleFactor(0.8)
                .frame(width: 40, alignment: .trailing)
        }
    }
}

struct SmallProduct: View {
    let name: String
    let color: Color
    let product: ProductUsage
    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            ProductHeader(name: name, color: color, plan: product.plan)
            if product.ok {
                SmallMetric(label: "5h", window: product.fiveHour)
                SmallMetric(label: "周", window: product.sevenDay)
            } else {
                ProductError(message: product.error ?? "无数据")
            }
        }
    }
}

struct SmallView: View {
    @Environment(\.palette) private var palette
    let snapshot: UsageSnapshot
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            SmallProduct(name: "Claude", color: palette.claude, product: snapshot.claude)
            SmallProduct(name: "Codex", color: palette.codex, product: snapshot.codex)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .padding(12)
    }
}

// ---- 中卡 ----

struct MediumColumn: View {
    let name: String
    let color: Color
    let product: ProductUsage
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ProductHeader(name: name, color: color, plan: product.plan)
            if product.ok {
                MetricRow(label: "5 小时", window: product.fiveHour)
                MetricRow(label: "一周", window: product.sevenDay)
            } else {
                ProductError(message: product.error ?? "无数据")
                Spacer(minLength: 0)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }
}

struct MediumView: View {
    @Environment(\.palette) private var palette
    let snapshot: UsageSnapshot
    var body: some View {
        HStack(spacing: 16) {
            MediumColumn(name: "Claude Code", color: palette.claude, product: snapshot.claude)
            Rectangle().fill(palette.track).frame(width: 0.5)
            MediumColumn(name: "Codex", color: palette.codex, product: snapshot.codex)
        }
        .padding(14)
    }
}

// ---- 大卡 ----

struct LargeSection: View {
    let name: String
    let color: Color
    let product: ProductUsage
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ProductHeader(name: name, color: color, plan: product.plan)
            if product.ok {
                MetricRow(label: "5 小时窗口", window: product.fiveHour, showAbsolute: true, barHeight: 8)
                MetricRow(label: "一周窗口", window: product.sevenDay, showAbsolute: true, barHeight: 8)
            } else {
                ProductError(message: product.error ?? "无数据")
            }
        }
    }
}

struct LargeView: View {
    @Environment(\.palette) private var palette
    let snapshot: UsageSnapshot
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            LargeSection(name: "Claude Code", color: palette.claude, product: snapshot.claude)
            Rectangle().fill(palette.track).frame(height: 0.5)
            LargeSection(name: "Codex", color: palette.codex, product: snapshot.codex)
            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .padding(16)
    }
}
