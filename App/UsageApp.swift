import SwiftUI
import WidgetKit
import AppKit
import Combine
import ServiceManagement

@main
struct AIUsageApp: App {
    var body: some Scene {
        MenuBarExtra {
            ContentView()
        } label: {
            Image("MenuBarIcon")
        }
        .menuBarExtraStyle(.window)
    }
}

struct ContentView: View {
    @Environment(\.colorScheme) private var systemScheme
    @State private var snapshot: UsageSnapshot = .sample
    @State private var refreshing = false
    @State private var loadedOnce = false
    @State private var theme: String = "system"
    @State private var launchAtLogin = false

    private let timer = Timer.publish(every: 30, on: .main, in: .common).autoconnect()

    private var connected: Bool { snapshot.claude.ok || snapshot.codex.ok }
    private var palette: Palette { Palette.of(AppTheme.scheme(theme) ?? systemScheme) }

    private var updatedText: String {
        let fmt = DateFormatter()
        fmt.dateFormat = "HH:mm"
        return fmt.string(from: Date(timeIntervalSince1970: Double(snapshot.updated)))
    }

    var body: some View {
        VStack(spacing: 12) {
            ZStack {
                palette.cardBackground
                LargeView(snapshot: snapshot)
            }
            .frame(width: 320, height: 290)
            .clipShape(RoundedRectangle(cornerRadius: 16))
            .overlay(RoundedRectangle(cornerRadius: 16).stroke(palette.track, lineWidth: 0.5))
            .environment(\.palette, palette)

            VStack(spacing: 10) {
                HStack {
                    Text("小组件外观").font(.system(size: 12))
                    Spacer()
                    Picker("", selection: $theme) {
                        Text("跟随系统").tag("system")
                        Text("白").tag("light")
                        Text("黑").tag("dark")
                    }
                    .pickerStyle(.segmented).labelsHidden().frame(width: 200)
                }
                HStack {
                    Text("开机自启动").font(.system(size: 12))
                    Spacer()
                    Toggle("", isOn: $launchAtLogin).labelsHidden()
                }
                HStack {
                    Text(connected ? "运行时每 30 秒刷新 · \(updatedText)" : "未连接到本地 Agent")
                        .font(.system(size: 11)).foregroundColor(.secondary)
                    Spacer()
                    Button("退出") { NSApplication.shared.terminate(nil) }
                }
            }

            if loadedOnce && !connected {
                VStack(alignment: .leading, spacing: 6) {
                    Text("后台取数服务未运行。在项目目录执行一次安装脚本：")
                        .font(.system(size: 12)).foregroundColor(.secondary)
                    HStack {
                        Text("bash agent/install.sh")
                            .font(.system(size: 12, design: .monospaced))
                            .textSelection(.enabled)
                        Spacer()
                        Button("复制") {
                            NSPasteboard.general.clearContents()
                            NSPasteboard.general.setString("bash agent/install.sh", forType: .string)
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
        .preferredColorScheme(AppTheme.scheme(theme))
        .task {
            theme = await UsageAPI.currentTheme()
            launchAtLogin = (SMAppService.mainApp.status == .enabled)
            await refresh()
        }
        .onChange(of: theme) { _, newValue in
            Task {
                await UsageAPI.setTheme(newValue)
                await refresh()
                WidgetCenter.shared.reloadAllTimelines()
            }
        }
        .onChange(of: launchAtLogin) { _, on in
            do {
                if on { try SMAppService.mainApp.register() }
                else { try SMAppService.mainApp.unregister() }
            } catch {
                launchAtLogin = (SMAppService.mainApp.status == .enabled)
            }
        }
        .onReceive(timer) { _ in
            Task { await refresh() }
        }
    }

    private func refresh() async {
        refreshing = true
        snapshot = await UsageAPI.fetch()
        loadedOnce = true
        refreshing = false
        WidgetCenter.shared.reloadAllTimelines()
    }
}
