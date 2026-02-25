import json
import random

from engine.delta import compute_delta, compute_trend


def _run_with_results(results):
    return {"meta": {"run_id": "run-1"}, "results": results}


def test_compute_delta_is_repeatable_for_identical_inputs():
    prev = _run_with_results(
        [{"control_id": "A01.01", "status": "Fail"}, {"control_id": "B01.01", "status": "Pass"}]
    )
    curr = _run_with_results(
        [{"control_id": "A01.01", "status": "Pass"}, {"control_id": "B01.01", "status": "Pass"}]
    )

    first = compute_delta(prev, curr)
    second = compute_delta(prev, curr)

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_compute_delta_ignores_input_order():
    prev = _run_with_results(
        [{"control_id": "A01.01", "status": "Fail"}, {"control_id": "B01.01", "status": "Pass"}]
    )
    curr_one = _run_with_results(
        [{"control_id": "A01.01", "status": "Pass"}, {"control_id": "B01.01", "status": "Fail"}]
    )
    curr_two = _run_with_results(
        [{"control_id": "B01.01", "status": "Fail"}, {"control_id": "A01.01", "status": "Pass"}]
    )

    assert compute_delta(prev, curr_one) == compute_delta(prev, curr_two)


def test_compute_delta_empty_inputs():
    result = compute_delta(_run_with_results([]), _run_with_results([]))
    assert result == {"has_previous": True, "changed_controls": [], "count": 0}


def test_compute_delta_large_input_is_stable():
    controls = [{"control_id": f"C{i:05d}", "status": "Fail"} for i in range(1000)]
    prev = _run_with_results(controls)
    curr_controls = [{"control_id": f"C{i:05d}", "status": "Pass" if i % 10 == 0 else "Fail"} for i in range(1000)]
    shuffled = curr_controls[:]
    random.Random(42).shuffle(shuffled)
    curr = _run_with_results(shuffled)

    delta = compute_delta(prev, curr)

    assert delta["count"] == 100
    assert delta["changed_controls"][0]["control_id"] == "C00000"
    assert delta["changed_controls"][-1]["control_id"] == "C00990"


def test_compute_trend_is_order_independent_for_sections():
    prev = {
        "meta": {"run_id": "run-prev"},
        "scoring": {
            "overall_maturity_percent": 55.0,
            "section_scores": [
                {"section": "Security", "maturity_percent": 60.0},
                {"section": "Governance", "maturity_percent": 50.0},
            ],
        },
    }
    curr_one = {
        "scoring": {
            "overall_maturity_percent": 60.0,
            "section_scores": [
                {"section": "Governance", "maturity_percent": 55.0},
                {"section": "Security", "maturity_percent": 62.0},
            ],
        }
    }
    curr_two = {
        "scoring": {
            "overall_maturity_percent": 60.0,
            "section_scores": [
                {"section": "Security", "maturity_percent": 62.0},
                {"section": "Governance", "maturity_percent": 55.0},
            ],
        }
    }

    assert compute_trend(prev, curr_one) == compute_trend(prev, curr_two)
