import SwiftUI
#if DEBUG
import MWDATMockDevice
#endif

struct QuickTalkSettings: View {
    @ObservedObject var app: QuickTalkModel
    @ObservedObject var glasses: GlassesLink
    @Environment(\.dismiss) private var dismiss
    @State private var changingMock = false

    var body: some View {
        NavigationStack {
            Form {
                Section("About you") {
                    TextField("Name", text: $app.name)
                        .textContentType(.givenName)
                    TextField("Facts to use in your replies", text: $app.about, axis: .vertical)
                        .lineLimit(3...8)
                }
                Section("Voice") {
                    Picker("Voice", selection: $app.voice) {
                        ForEach(0..<app.voiceCount, id: \.self) { index in Text("Voice \(index + 1)").tag(index) }
                    }
                    Slider(value: $app.speed, in: 0.75...1.25, step: 0.05) { Text("Speaking speed") }
                    LabeledContent("Speaking speed", value: app.speed.formatted(.percent))
                    Slider(value: $app.volume) { Text("Voice volume") }
                    LabeledContent("Voice volume", value: app.volume.formatted(.percent))
                    Button(app.loading ? "Loading voice…" : "Preview voice", systemImage: "speaker.wave.2") {
                        app.previewVoice()
                    }
                    .disabled(!app.modelsReady || app.loading)
                    if let issue = app.issue { Text(issue).foregroundStyle(.red) }
                }
                Section("Glasses") {
                    if glasses.registered {
                        if glasses.devices.isEmpty { Text("No display glasses found").foregroundStyle(.secondary) }
                        ForEach(Array(glasses.devices.enumerated()), id: \.offset) { _, status in Text(status) }
                        Button("Disconnect from Meta AI", role: .destructive) { Task { await glasses.unregister() } }
                    } else {
                        Button("Connect through Meta AI") { Task { await glasses.register() } }
                    }
                    Toggle("Click when highlight moves", isOn: $app.tick)
                    #if DEBUG
                    Toggle("Simulated glasses", isOn: Binding(
                        get: { glasses.mock != nil },
                        set: { enabled in
                            changingMock = true
                            Task {
                                await glasses.setMockEnabled(enabled)
                                changingMock = false
                            }
                        }
                    ))
                    .disabled(changingMock)
                    #endif
                    if let issue = glasses.issue { Text(issue).foregroundStyle(.red) }
                }
            }
            .navigationTitle("Settings")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
            }
        }
    }
}

#if DEBUG
struct MockGlassesPreview: UIViewRepresentable {
    let glasses: any MockGlasses

    func makeUIView(context: Context) -> UIView { glasses.services.display.createPreviewView() }
    func updateUIView(_ uiView: UIView, context: Context) {}
}
#endif
