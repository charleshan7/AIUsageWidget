import SwiftUI
import WidgetKit
import AppKit

@main
struct AIUsageApp: App {
    var body: some Scene {
        WindowGroup("AI 用量") {
            ContentView()
        }
        .windowResizability(.contentSize)
    }
}

struct ContentView: View {
    @State private var snapshot: UsageSnapshot = .sample
    @State private var refreshing = false
    @State private var loadedOnce = false

    private var connected: Bool { snapshot.claude.ok || snapshot.codex.ok }

    private var updatedText: String {
        let fmt = DateFormatter()
        fmt.dateFormat = "HH:mm"
        return fmt.string(from: Date(timeIntervalSince1970: Double(snapshot.updated)))
    }

    var body: some View {
        VStack(spacing: 14) {
            ZStack {
                Palette.cardBackground
                LargeView(snapshot: snapshot)
            }
            .frame(width: 320, height: 290)
            .clipShape(RoundedRectangle(cornerRadius: 16))
            .overlay(RoundedRectangle(cornerRadius: 16).stroke(Palette.track, lineWidth: 0.5))

            HStack(spacing: 10) {
                Circle().fill(connected ? Color.green : Color.gray).frame(width: 7, height: 7)
                Text(connected ? "已连接 · 更新于 \(updatedText)" : "未连接到本地 Agent")
                    .font(.system(size: 12)).foregroundColor(.secondary)
                Spacer()
                Button {
                    Task { await refresh() }
                } label: {
                    Label("刷新", systemImage: "arrow.clockwise")
                }
                .disabled(refreshing)
            }

            if loadedOnce && !connected {
                VStack(alignment: .leading, spacing: 6) {
                    Text("后台取数服务未运行。在终端执行一次安装脚本：")
                        .font(.system(size: 12)).foregroundColor(.secondary)
                    HStack {
                        Text("bash ~/AIUsageWidget/agent/install.sh")
                            .font(.system(size: 12, design: .monospaced))
                            .textSelection(.enabled)
                        Spacer()
                        Button("复制") {
                            NSPasteboard.general.clearContents()
                            NSPasteboard.general.setString("bash ~/AIUsageWidget/agent/install.sh", forType: .string)
                        }
                    }
                    .padding(8)
                    .background(Color.primary.opacity(0.06))
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                }
            }
        }
        .padding(16)
        .frame(width: 360)
        .task { await refresh() }
    }

    private func refresh() async {
        refreshing = true
        snapshot = await UsageAPI.fetch()
        loadedOnce = true
        refreshing = false
        WidgetCenter.shared.reloadAllTimelines()
    }
}
