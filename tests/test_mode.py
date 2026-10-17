from __future__ import annotations

from skillgate_ai.mode import CLOUD, LOCAL, current_mode, is_local, slots_for


def test_default_mode_is_local(monkeypatch) -> None:
    monkeypatch.delenv("SKILLGATE_MODE", raising=False)
    assert current_mode() == LOCAL
    assert is_local()
    slots = slots_for()
    assert slots["signIn"] is False
    assert slots["billing"] is False
    assert slots["generateChecks"] is False
    assert slots["gitPublish"] is False
    assert slots["analyticsHome"] is True
    assert slots["hostedJudge"] is False


def test_cloud_mode_shows_slots(monkeypatch) -> None:
    monkeypatch.setenv("SKILLGATE_MODE", "cloud")
    assert current_mode() == CLOUD
    assert not is_local()
    assert all(slots_for().values())
