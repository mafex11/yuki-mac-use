import AppKit
import Carbon

final class HotKey {
    private var hotKeyRef: EventHotKeyRef?
    private var onTap: (() -> Void)?
    private var onLongPress: (() -> Void)?
    private var keyDownAt: Date?

    func register(
        onTap: @escaping () -> Void,
        onLongPress: (() -> Void)? = nil
    ) {
        self.onTap = onTap
        self.onLongPress = onLongPress

        let signature: OSType = OSType("YUKI".fourCharCode)
        let hotKeyID = EventHotKeyID(signature: signature, id: 1)
        let modifiers: UInt32 = UInt32(cmdKey | shiftKey)
        let keycode: UInt32 = 0 // 'A'
        RegisterEventHotKey(keycode, modifiers, hotKeyID,
                            GetApplicationEventTarget(), 0, &hotKeyRef)

        let handler: EventHandlerUPP = { _, eventRef, userData in
            let me = Unmanaged<HotKey>.fromOpaque(userData!).takeUnretainedValue()
            let kind = GetEventKind(eventRef)
            if kind == UInt32(kEventHotKeyPressed) {
                me.keyDownAt = Date()
            } else if kind == UInt32(kEventHotKeyReleased) {
                if let down = me.keyDownAt {
                    let dt = Date().timeIntervalSince(down)
                    if dt > 0.5 { me.onLongPress?() } else { me.onTap?() }
                }
                me.keyDownAt = nil
            }
            return noErr
        }
        var spec = [
            EventTypeSpec(eventClass: OSType(kEventClassKeyboard),
                          eventKind: UInt32(kEventHotKeyPressed)),
            EventTypeSpec(eventClass: OSType(kEventClassKeyboard),
                          eventKind: UInt32(kEventHotKeyReleased)),
        ]
        InstallEventHandler(GetApplicationEventTarget(), handler,
                            spec.count, &spec,
                            Unmanaged.passUnretained(self).toOpaque(), nil)
    }

    func unregister() {
        if let ref = hotKeyRef { UnregisterEventHotKey(ref) }
        hotKeyRef = nil
    }
}

private extension String {
    var fourCharCode: UInt32 {
        var code: UInt32 = 0
        for ch in self.utf8.prefix(4) {
            code = (code << 8) + UInt32(ch)
        }
        return code
    }
}
