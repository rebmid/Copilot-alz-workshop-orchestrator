"""Quick tests for enterprise-scale merge functions."""
from signals.registry import (
    _merge_raw_dicts, _merge_signal_results,
    _merge_defender_pricings, _merge_defender_scores,
    _merge_workspace_topology,
)
from signals.types import SignalResult, SignalStatus


def test_raw_merge():
    r1 = {"budget_count": 3, "has_reservations": True,
           "coverage": {"applicable": 4, "compliant": 2, "ratio": 0.5}}
    r2 = {"budget_count": 5, "has_reservations": False,
           "coverage": {"applicable": 6, "compliant": 4, "ratio": 0.667}}
    m = _merge_raw_dicts([r1, r2])
    assert m["budget_count"] == 8
    assert m["has_reservations"] is True
    assert m["coverage"]["applicable"] == 10
    assert m["coverage"]["compliant"] == 6
    assert abs(m["coverage"]["ratio"] - 0.6) < 0.01
    print("  raw merge OK")


def test_signal_merge():
    s1 = SignalResult(signal_name="test", status=SignalStatus.OK,
                      items=[{"a": 1}], raw={"count": 5}, duration_ms=100)
    s2 = SignalResult(signal_name="test", status=SignalStatus.OK,
                      items=[{"b": 2}], raw={"count": 3}, duration_ms=50)
    m = _merge_signal_results([s1, s2])
    assert len(m.items) == 2
    assert m.raw is not None
    assert m.raw["count"] == 8
    assert m.raw["_subscriptions_assessed"] == 2
    print("  signal merge OK")


def test_defender_pricing():
    d1 = SignalResult(signal_name="defender:pricings", status=SignalStatus.OK,
                      items=[{"name": "CloudPosture", "tier": "Standard"},
                             {"name": "Servers", "tier": "Standard"}],
                      raw={}, duration_ms=50)
    d2 = SignalResult(signal_name="defender:pricings", status=SignalStatus.OK,
                      items=[{"name": "CloudPosture", "tier": "Free"},
                             {"name": "Servers", "tier": "Standard"}],
                      raw={}, duration_ms=50)
    dm = _merge_defender_pricings([d1, d2])
    plans = {p["name"]: p["tier"] for p in dm.items}
    assert plans["cloudposture"] == "Free", f"Expected Free, got {plans['cloudposture']}"
    assert plans["servers"] == "Standard"
    print("  defender pricing merge OK")


def test_defender_score():
    sc1 = SignalResult(signal_name="defender:secure_score", status=SignalStatus.OK,
                       items=[{"name": "default", "percentage": 80,
                               "current": 40, "max": 50}],
                       raw={}, duration_ms=50)
    sc2 = SignalResult(signal_name="defender:secure_score", status=SignalStatus.OK,
                       items=[{"name": "default", "percentage": 60,
                               "current": 30, "max": 50}],
                       raw={}, duration_ms=50)
    scm = _merge_defender_scores([sc1, sc2])
    assert scm.items[0]["percentage"] == 70.0
    print("  defender score merge OK")


def test_workspace_topology():
    w1 = SignalResult(signal_name="monitor:workspace_topology", status=SignalStatus.OK,
                      items=[], raw={"is_centralized": True, "sentinel_enabled": True,
                                     "max_retention_days": 365},
                      duration_ms=50)
    w2 = SignalResult(signal_name="monitor:workspace_topology", status=SignalStatus.OK,
                      items=[], raw={"is_centralized": False, "sentinel_enabled": True,
                                     "max_retention_days": 90},
                      duration_ms=50)
    wm = _merge_workspace_topology([w1, w2])
    assert wm.raw is not None
    assert wm.raw["is_centralized"] is False
    assert wm.raw["sentinel_enabled"] is True
    assert wm.raw["max_retention_days"] == 90
    print("  workspace topology merge OK")


if __name__ == "__main__":
    print("Running merge tests...")
    test_raw_merge()
    test_signal_merge()
    test_defender_pricing()
    test_defender_score()
    test_workspace_topology()
    print("\nAll merge tests passed!")
