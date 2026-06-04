"""Regression: ApplicationControl.Windows must not recurse on apps (e.g. Arc)
whose window elements report role AXApplication.

Bug: Windows used CreateControl, which dispatches on role. Arc reports its
windows as AXApplication, so CreateControl built ApplicationControl objects
whose Status/IsMinimized re-read .Windows → infinite recursion → the whole
desktop-state capture (and thus every control task) crashed. The fix force-
wraps as WindowControl, which has the safe window-level IsMinimized.
"""

from __future__ import annotations

from yuki.ax import controls as C


class _FakeElement:
    """Stands in for an AXUIElementRef whose Role is AXApplication (Arc-like)."""

    def __init__(self, n_child_windows: int) -> None:
        self._n = n_child_windows


def test_application_windows_wrap_as_windowcontrol(monkeypatch) -> None:
    # GetAttribute(elem, Windows) returns child window elements; GetAttribute(
    # elem, Role) returns AXApplication for ALL of them (the Arc quirk).
    child_windows = [_FakeElement(0), _FakeElement(0)]

    def fake_get_attribute(element, attr):
        if attr == C.Attribute.Windows:
            # the app has child "windows"; a window element has none
            return child_windows if isinstance(element, _FakeElement) and element._n else []
        if attr == C.Attribute.Role:
            return "AXApplication"  # the bug trigger
        return None

    monkeypatch.setattr(C, "GetAttribute", fake_get_attribute)

    app = C.ApplicationControl(element=_FakeElement(2))
    windows = app.Windows

    # Each window must be a WindowControl, NOT an ApplicationControl — otherwise
    # IsMinimized/Status recurse back into .Windows.
    assert len(windows) == 2
    assert all(isinstance(w, C.WindowControl) for w in windows)
    assert not any(isinstance(w, C.ApplicationControl) for w in windows)


def test_status_does_not_recurse_with_application_role_windows(monkeypatch) -> None:
    """The end-to-end symptom: app.Status must return (not RecursionError) even
    when every window element reports role AXApplication."""
    child_windows = [_FakeElement(0), _FakeElement(0)]

    def fake_get_attribute(element, attr):
        if attr == C.Attribute.Windows:
            return child_windows if isinstance(element, _FakeElement) and element._n else []
        if attr == C.Attribute.Role:
            return "AXApplication"
        if attr == C.Attribute.Minimized:
            return False
        if attr == C.Attribute.Hidden:
            return False
        return None

    monkeypatch.setattr(C, "GetAttribute", fake_get_attribute)
    # IsActive reads other attrs; stub to a simple value to avoid unrelated calls.
    monkeypatch.setattr(C.ApplicationControl, "IsActive", property(lambda self: False))
    monkeypatch.setattr(C.ApplicationControl, "IsHidden", property(lambda self: False))

    app = C.ApplicationControl(element=_FakeElement(2))
    # Should complete without RecursionError. Windows present + not all minimized
    # + not active → "Visible".
    assert app.Status == "Visible"
