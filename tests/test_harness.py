from clipping.eval import harness


def test_regression_gate_rejects_worse_and_missed_bar(monkeypatch):
    monkeypatch.setattr(
        harness,
        "thresholds",
        lambda: {"zz": {"recall": {"bar": 0.7}, "lat": {"bar": 10, "direction": "lower"}}},
    )
    base = {"metrics": {"recall": 0.9, "lat": 2.0}}
    good = harness.evaluate("zz", harness.StageResult({"recall": 0.89, "lat": 2.03}), base)
    assert all(c.passed for c in good)  # within 2% tolerance
    worse = harness.evaluate("zz", harness.StageResult({"recall": 0.85, "lat": 2.0}), base)
    assert not worse[0].passed and "baseline" in worse[0].reason
    miss = harness.evaluate("zz", harness.StageResult({"recall": 0.6, "lat": 11}), None)
    assert not any(c.passed for c in miss)
    missing = harness.evaluate("zz", harness.StageResult({"recall": 0.9}), None)
    assert any(c.reason == "metric missing" for c in missing)


def test_accept_refuses_failing_run():
    import pytest

    rep = harness.RunReport("zz", False, [], harness.StageResult({}), 0.0)
    with pytest.raises(ValueError):
        harness.accept(rep)
