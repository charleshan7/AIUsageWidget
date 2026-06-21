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
            let entry = UsageEntry(date: now, snapshot: snapshot)
            completion(Timeline(entries: [entry], policy: .after(now.addingTimeInterval(10 * 60))))
        }
    }
}

struct UsageWidgetEntryView: View {
    @Environment(\.widgetFamily) private var family
    let entry: UsageEntry

    var body: some View {
        ZStack(alignment: .topTrailing) {
            switch family {
            case .systemSmall:
                SmallView(snapshot: entry.snapshot)
            case .systemLarge, .systemExtraLarge:
                LargeView(snapshot: entry.snapshot)
            default:
                MediumView(snapshot: entry.snapshot)
            }
            Button(intent: RefreshUsageIntent()) {
                Image(systemName: "arrow.clockwise")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundColor(Palette.secondary)
                    .padding(5)
            }
            .buttonStyle(.plain)
            .padding(6)
        }
    }
}

struct AIUsageWidget: Widget {
    let kind = "AIUsageWidget"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: UsageProvider()) { entry in
            UsageWidgetEntryView(entry: entry)
                .containerBackground(Palette.cardBackground, for: .widget)
        }
        .configurationDisplayName("AI 用量")
        .description("查看 Claude Code 与 Codex 的 5 小时 / 一周用量。")
        .supportedFamilies([.systemSmall, .systemMedium, .systemLarge])
    }
}
