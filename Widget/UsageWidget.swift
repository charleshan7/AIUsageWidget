import WidgetKit
import SwiftUI
import AppIntents

// 手动刷新按钮：重新取数并重载小组件。
struct RefreshUsageIntent: AppIntent {
    static var title: LocalizedStringResource = "刷新用量"
    func perform() async throws -> some IntentResult {
        _ = await UsageAPI.fetch()
        WidgetCenter.shared.reloadAllTimelines()
        return .result()
    }
}

struct UsageEntry: TimelineEntry {
    let date: Date
    let snapshot: UsageSnapshot
}

struct UsageProvider: TimelineProvider {
    func placeholder(in context: Context) -> UsageEntry {
        UsageEntry(date: Date(), snapshot: .sample)
    }

    func getSnapshot(in context: Context, completion: @escaping (UsageEntry) -> Void) {
        if context.isPreview {
            completion(UsageEntry(date: Date(), snapshot: .sample))
            return
        }
        Task {
            let snapshot = await UsageAPI.fetch()
            completion(UsageEntry(date: Date(), snapshot: snapshot))
        }
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<UsageEntry>) -> Void) {
        Task {
            let snapshot = await UsageAPI.fetch()
            let now = Date()
            // 用量变化不快：每 10 分钟刷新一次（菜单/按钮也会主动重载）。
            //
            // 但系统「冻」住小组件时（重载预算耗尽、宿主 App 换过路径导致注册失效等）
            // 不会有任何代码被执行——只排一条时间线的话，几天前的数字会一直冒充实时，
            // 而且倒计时文案是渲染那一刻算好的，看上去完全合理。这里预排几条「已过期」
            // 条目兜底：重载即使没发生，卡片也会自己降级，不会继续骗人。
            var entries = [UsageEntry(date: now, snapshot: snapshot)]
            let staled = snapshot.markedStale()
            for minutes in [20.0, 45.0, 90.0, 240.0, 720.0] {
                entries.append(UsageEntry(date: now.addingTimeInterval(minutes * 60), snapshot: staled))
            }
            completion(Timeline(entries: entries, policy: .after(now.addingTimeInterval(10 * 60))))
        }
    }
}

struct UsageWidgetEntryView: View {
    @Environment(\.widgetFamily) private var family
    @Environment(\.colorScheme) private var systemScheme
    @Environment(\.widgetRenderingMode) private var renderingMode
    let entry: UsageEntry

    private var palette: Palette {
        Palette.of(AppTheme.scheme(entry.snapshot.theme) ?? systemScheme)
    }

    var body: some View {
        ZStack(alignment: .topTrailing) {
            Group {
                switch family {
                case .systemSmall:
                    SmallView(snapshot: entry.snapshot)
                case .systemLarge, .systemExtraLarge:
                    LargeView(snapshot: entry.snapshot)
                default:
                    MediumView(snapshot: entry.snapshot)
                }
            }
            Button(intent: RefreshUsageIntent()) {
                Image(systemName: "arrow.clockwise")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(renderingMode == .fullColor ? palette.secondary : .primary)
                    .frame(width: 22, height: 22)
                    .background {
                        if renderingMode == .fullColor {
                            Circle().fill(palette.track)
                        }
                    }
                    .contentShape(Circle())
            }
            .buttonStyle(.plain)
            .padding(7)
        }
        .environment(\.palette, palette)
    }
}

// 容器背景跟随外观偏好（containerBackground 在配置层，需自行算 palette）。
struct ContainerBG: View {
    @Environment(\.colorScheme) private var systemScheme
    let theme: String?
    var body: some View {
        Palette.of(AppTheme.scheme(theme) ?? systemScheme).cardBackground
    }
}

struct AIUsageWidget: Widget {
    let kind = "AIUsageWidget"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: UsageProvider()) { entry in
            UsageWidgetEntryView(entry: entry)
                .containerBackground(for: .widget) { ContainerBG(theme: entry.snapshot.theme) }
        }
        .configurationDisplayName("AI 用量")
        .description("查看 Claude Code 与 Codex 的 5 小时 / 一周用量。")
        .supportedFamilies([.systemSmall, .systemMedium, .systemLarge])
    }
}
