import QuickTalkCore
import SwiftUI

struct QuickTalkView: View {
    @ObservedObject var app: QuickTalkModel
    @ObservedObject var glasses: GlassesLink
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var settings = false
    @State private var arrowRaised = false

    private let cream = Color(red: 0.99, green: 0.96, blue: 0.91)
    private let cocoa = Color(red: 0.23, green: 0.15, blue: 0.11)
    private let terracotta = Color(red: 0.66, green: 0.28, blue: 0.19)

    var body: some View {
        ZStack {
            cream.ignoresSafeArea()
            if app.active {
                conversation
            } else {
                setup
            }
        }
        .foregroundStyle(cocoa)
        .tint(terracotta)
        .environment(\.colorScheme, .light)
        .sheet(isPresented: $settings) {
            QuickTalkSettings(app: app, glasses: glasses)
                .tint(terracotta)
        }
    }

    private var setup: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 25) {
                VStack(alignment: .leading, spacing: 9) {
                    Image(systemName: "bubble.left.and.bubble.right.fill")
                        .font(.title)
                        .foregroundStyle(terracotta)
                        .accessibilityHidden(true)
                    Text("QuickTalk").font(.system(.largeTitle, design: .serif).weight(.semibold))
                        .accessibilityAddTraits(.isHeader)
                    Text("Speak with help from your Meta Ray-Ban Display glasses.")
                        .foregroundStyle(cocoa.opacity(0.76))
                }
                if app.modelsReady {
                    if !glasses.registered {
                        Text("Connect your glasses through the Meta AI app to show replies.")
                        Button("Connect through Meta AI", systemImage: "eyeglasses") {
                            Task { await glasses.register() }
                        }
                        .buttonStyle(.bordered)
                    }
                    if glasses.registered && !glasses.available {
                        Text("Put on your connected Ray-Ban Display glasses to start.")
                            .foregroundStyle(cocoa.opacity(0.76))
                    }
                    Button {
                        app.start()
                    } label: {
                        Label(app.loading ? "Loading models…" : "Start conversation", systemImage: "play.fill")
                            .foregroundStyle(cream)
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .disabled(app.loading || !glasses.registered || !glasses.available)
                    volume
                } else {
                    Text("Download the speech and reply models once (1.9 GB). Conversations run on this iPhone.")
                    if app.downloading {
                        ProgressView(value: Double(app.downloaded), total: Double(ModelStore.totalBytes))
                            .accessibilityLabel("Model download")
                        Button("Cancel download") { app.cancelDownload() }
                    } else {
                        Button { app.download() } label: {
                            Label("Download models", systemImage: "arrow.down.circle").foregroundStyle(cream)
                        }
                            .buttonStyle(.borderedProminent)
                            .controlSize(.large)
                    }
                }
                if let issue = app.issue ?? app.state.problem ?? glasses.issue {
                    Text(issue).font(.callout).foregroundStyle(terracotta)
                }
                Button("Settings", systemImage: "gearshape") { settings = true }
                    .buttonStyle(.bordered)
                    .disabled(app.loading)
            }
            .frame(maxWidth: 490, alignment: .leading)
            .padding(30)
            .frame(maxWidth: .infinity)
        }
        .defaultScrollAnchor(.center)
    }

    private var conversation: some View {
        VStack(spacing: 14) {
            HStack {
                Spacer()
                Button("Pause", systemImage: "pause.fill") { app.pause() }
                    .buttonStyle(.bordered)
                    .controlSize(.large)
            }
            Spacer()
            let turn = partnerTurn(app.state.phase, glassesReady: glasses.ready)
            if turn == .wearersTurn {
                Image(systemName: "arrow.up")
                    .font(.system(size: 70, weight: .light))
                    .foregroundStyle(terracotta)
                    .offset(y: arrowRaised && !reduceMotion ? -10 : 0)
                    .accessibilityHidden(true)
                    .onAppear {
                        arrowRaised = false
                        if !reduceMotion {
                            withAnimation(.easeInOut(duration: 1.25).repeatForever(autoreverses: true)) { arrowRaised = true }
                        }
                    }
            }
            Text(turnTitle(turn))
                .font(.system(.largeTitle, design: .serif).weight(.semibold))
                .multilineTextAlignment(.center)
                .accessibilityAddTraits(.isHeader)
            if turn == .reconnecting {
                Text("Reconnecting to the glasses")
                    .foregroundStyle(cocoa.opacity(0.72))
            }
            Spacer()
            #if DEBUG
            if let mock = glasses.mock {
                MockGlassesPreview(glasses: mock)
                    .frame(maxWidth: 300)
                    .aspectRatio(1.5, contentMode: .fit)
                    .accessibilityLabel("Simulated glasses display")
                simulatedControls
            }
            #endif
        }
        .padding(24)
    }

    private func turnTitle(_ turn: PartnerTurn) -> String {
        switch turn {
        case .yourTurn: "Your turn"
        case .wearersTurn:
            app.name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "Please wait" : "\(app.name)’s turn"
        case .reconnecting: "One moment"
        case .paused: "Paused"
        }
    }

    private var volume: some View {
        VStack(alignment: .leading) {
            Text("Voice volume").font(.subheadline.weight(.medium))
            Slider(value: $app.volume) { Text("Voice volume") }
        }
    }

    #if DEBUG
    private var simulatedControls: some View {
        VStack(spacing: 8) {
            HStack {
                control("Turn counterclockwise", "arrow.counterclockwise", .turn(clockwise: false))
                control("Swipe up", "arrow.up", .highlight(.up))
                control("Turn clockwise", "arrow.clockwise", .turn(clockwise: true))
            }
            HStack {
                control("Swipe left", "arrow.left", .highlight(.left))
                control("Pinch", "hand.pinch", .confirm)
                control("Swipe right", "arrow.right", .highlight(.right))
            }
            HStack {
                control("Back", "arrow.uturn.backward", .back)
                control("Swipe down", "arrow.down", .highlight(.down))
            }
        }
        .buttonStyle(.bordered)
    }

    private func control(_ name: String, _ icon: String, _ input: GlassesInput) -> some View {
        Button(name, systemImage: icon) { glasses.simulate(input) }
            .labelStyle(.iconOnly)
            .accessibilityLabel(name)
    }
    #endif
}
