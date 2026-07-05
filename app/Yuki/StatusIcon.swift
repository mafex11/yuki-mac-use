import AppKit

/// Menu-bar icon drawn in code: the snowflake-Y mark as a template image
/// (auto-adapts to light/dark menu bars and tinting). `phase` animates the
/// secondary spokes while a task runs — a quiet shimmer, not a spinner.
enum StatusIcon {
    static func image(running: Bool = false, phase: Double = 0) -> NSImage {
        let size = NSSize(width: 18, height: 18)
        let img = NSImage(size: size, flipped: false) { rect in
            let c = NSGraphicsContext.current!.cgContext
            let cx = rect.midX
            let cy = rect.midY + 0.5   // optical center: stem hangs low
            let arm: CGFloat = 6.4     // heavy Y spokes
            let sec: CGFloat = 5.6     // light snowflake spokes

            func spoke(_ angle: CGFloat, _ len: CGFloat, width: CGFloat, alpha: CGFloat) {
                c.setStrokeColor(NSColor.black.withAlphaComponent(alpha).cgColor)
                c.setLineWidth(width)
                c.setLineCap(.round)
                c.move(to: CGPoint(x: cx, y: cy))
                c.addLine(to: CGPoint(x: cx + len * cos(angle), y: cy + len * sin(angle)))
                c.strokePath()
            }

            // Y spokes: up-left, up-right, down (y-up coordinates).
            let deg = { (d: CGFloat) in d * .pi / 180 }
            for a in [deg(120), deg(60), deg(270)] {
                spoke(a, arm, width: 2.3, alpha: 1.0)
            }
            // Snowflake spokes: up, down-left, down-right. While running,
            // their opacity breathes with `phase` (0..1..0 wave per spoke).
            let base: [CGFloat] = [deg(90), deg(210), deg(330)]
            for (i, a) in base.enumerated() {
                let alpha: CGFloat
                if running {
                    let wave = sin((phase + Double(i) / 3.0) * 2 * .pi)
                    alpha = 0.25 + 0.55 * CGFloat((wave + 1) / 2)
                } else {
                    alpha = 0.45
                }
                spoke(a, sec, width: 1.4, alpha: alpha)
            }
            // center crystal
            c.setFillColor(NSColor.black.cgColor)
            let r: CGFloat = 1.8
            c.fillEllipse(in: CGRect(x: cx - r, y: cy - r, width: 2 * r, height: 2 * r))
            return true
        }
        img.isTemplate = true
        return img
    }
}
