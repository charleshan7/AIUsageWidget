import SwiftUI

// ---- 配色与格式化 ----

enum Palette {
    // 低饱和品牌点
    static let claude = Color(red: 0.78, green: 0.52, blue: 0.44)
    static let codex = Color(red: 0.42, green: 0.64, blue: 0.57)
    // 浅色主题：文字 / 轨道 / 卡片底
    static let textPrimary = Color(red: 0.15, green: 0.15, blue: 0.17)
    static let secondary = Color(red: 0.46, green: 0.47, blue: 0.51)
    static let tertiary = Color(red: 0.64, green: 0.65, blue: 0.69)
    static let track = Color(red: 0.90, green: 0.90, blue: 0.92)
    static let cardBackground = Color(red: 0.99, green: 0.99, blue: 0.985)
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

// ---- 基础组件 ----

struct UsageBar: View {
    let percent: Int
    var height: CGFloat = 6
    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Capsule().fill(Palette.track)
                Capsule().fill(severityColor(percent))
                    .frame(width: max(geo.size.width * CGFloat(min(max(percent, 0), 100)) / 100.0,
                                      percent > 0 ? 3 : 0))
            }
        }
        .frame(height: height)
    }
}

struct ProductHeader: View {
    let name: String
    let color: Color
    var plan: String? = nil
    var body: some View {
        HStack(spacing: 6) {
            Circle().fill(color).frame(width: 7, height: 7)
            Text(name).font(.system(size: 12, weight: .medium)).foregroundColor(Palette.textPrimary)
            if let plan = plan {
                Text(plan.capitalized)
                    .font(.system(size: 9, weight: .medium))
                    .foregroundColor(Palette.secondary)
                    .padding(.horizontal, 5).padding(.vertical, 1)
                    .background(Capsule().fill(Palette.track))
            }
            Spacer(minLength: 0)
        }
    }
}

// 一条带标签的指标行（中/大卡用）。
struct MetricRow: View {
    let label: String
    let window: UsageWindow?
    var showReset: Bool = true
    var showAbsolute: Bool = false
    var barHeight: CGFloat = 6

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(label).font(.system(size: 11)).foregroundColor(Palette.secondary)
                Spacer()
                Text(window.map { "\($0.percent)%" } ?? "—")
                    .font(.system(size: 11, weight: .medium)).foregroundColor(Palette.textPrimary)
            }
            UsageBar(percent: window?.percent ?? 0, height: barHeight)
            if showReset, let w = window {
                Text(showAbsolute
                     ? "\(resetCountdown(w.resetsAt)) · \(resetAbsolute(w.resetsAt))"
                     : resetCountdown(w.resetsAt))
                    .font(.system(size: 10)).foregroundColor(Palette.tertiary)
            }
        }
    }
}

// 失败态占位。
struct ProductError: View {
    let message: String
    var body: some View {
        Text(message).font(.system(size: 11)).foregroundColor(Palette.tertiary)
    }
}

// ---- 小卡 ----

struct SmallMetric: View {
    let label: String
    let window: UsageWindow?
    var body: some View {
        HStack(spacing: 6) {
            Text(label).font(.system(size: 11)).foregroundColor(Palette.secondary).frame(width: 16, alignment: .leading)
            UsageBar(percent: window?.percent ?? 0, height: 5)
            Text(window.map { "\($0.percent)%" } ?? "—")
                .font(.system(size: 11, weight: .medium)).foregroundColor(Palette.textPrimary)
                .frame(width: 30, alignment: .trailing)
        }
    }
}

struct SmallProduct: View {
    let name: String
    let color: Color
    let product: ProductUsage
    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            ProductHeader(name: name, color: color)
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
    let snapshot: UsageSnapshot
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            SmallProduct(name: "Claude", color: Palette.claude, product: snapshot.claude)
            SmallProduct(name: "Codex", color: Palette.codex, product: snapshot.codex)
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
            ProductHeader(name: name, color: color)
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
    let snapshot: UsageSnapshot
    var body: some View {
        HStack(spacing: 16) {
            MediumColumn(name: "Claude Code", color: Palette.claude, product: snapshot.claude)
            Rectangle().fill(Palette.track).frame(width: 0.5)
            MediumColumn(name: "Codex", color: Palette.codex, product: snapshot.codex)
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
    let snapshot: UsageSnapshot
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            LargeSection(name: "Claude Code", color: Palette.claude, product: snapshot.claude)
            Rectangle().fill(Palette.track).frame(height: 0.5)
            LargeSection(name: "Codex", color: Palette.codex, product: snapshot.codex)
            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .padding(16)
    }
}
