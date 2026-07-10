from app.db import compute_summary

RUN = {"id": "run-1", "status": "completed"}


def result(model_id, invoice_stem, status, mistake_count=None, duration_ms=None):
    return {
        "model_id": model_id,
        "invoice_stem": invoice_stem,
        "status": status,
        "mistake_count": mistake_count,
        "duration_ms": duration_ms,
    }


def test_avg_duration_ms_averages_over_attempted_results():
    results = [
        result("model-a", "inv1", "success", mistake_count=0, duration_ms=1000),
        result("model-a", "inv2", "success", mistake_count=2, duration_ms=3000),
    ]
    summary = compute_summary(RUN, results)
    assert summary["per_model"]["model-a"]["avg_duration_ms"] == 2000


def test_avg_duration_ms_includes_errored_attempts():
    results = [
        result("model-a", "inv1", "success", mistake_count=0, duration_ms=1000),
        result("model-a", "inv2", "error", duration_ms=500),
    ]
    summary = compute_summary(RUN, results)
    # error attempts still ran an extraction and recorded a duration — they count
    assert summary["per_model"]["model-a"]["avg_duration_ms"] == 750


def test_avg_duration_ms_null_when_no_durations_recorded():
    results = [result("model-a", "inv1", "no_ground_truth")]
    summary = compute_summary(RUN, results)
    assert summary["per_model"]["model-a"]["avg_duration_ms"] is None


def test_matrix_cell_includes_mistake_count_and_duration():
    results = [result("model-a", "inv1", "success", mistake_count=3, duration_ms=1500)]
    summary = compute_summary(RUN, results)
    assert summary["matrix"]["inv1"]["model-a"] == {"mistake_count": 3, "duration_ms": 1500}


def test_matrix_cell_for_error_has_null_mistake_count_but_keeps_duration():
    results = [result("model-a", "inv1", "error", duration_ms=750)]
    summary = compute_summary(RUN, results)
    assert summary["matrix"]["inv1"]["model-a"] == {"mistake_count": None, "duration_ms": 750}


def test_matrix_cell_for_no_ground_truth_is_none():
    results = [result("model-a", "inv1", "no_ground_truth")]
    summary = compute_summary(RUN, results)
    assert summary["matrix"]["inv1"]["model-a"] is None
