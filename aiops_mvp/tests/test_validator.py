import pytest

from calldiag.models import CounterEvidence, PipelineResult, ValidationIssue, ValidationResult
from calldiag.pipeline.validator import apply_validation, validate_report


@pytest.mark.parametrize("sid", [f"S{i}" for i in range(7)])
def test_valid_reports_have_no_issues(sid: str, results: dict[str, PipelineResult]) -> None:
    result = results[sid]
    validation = validate_report(result.report, result.bundle)
    assert validation.passed and validation.issues == []


@pytest.mark.parametrize(("mutation", "code"), [
    ("duplicate", "E_DUP_ID"), ("no_ref", "E_FACT_NO_REF"),
    ("bad_ref", "E_FACT_BAD_REF"), ("banned", "E_FACT_BANNED_WORD"),
    ("no_support", "E_INF_NO_SUPPORT"), ("bad_support", "E_INF_BAD_SUPPORT"),
    ("bad_counter", "E_COUNTER_BAD_REF"), ("bad_condition", "E_INF_BAD_SUPPORT"),
    ("confidence", "E_CONFIDENCE"), ("summary_confidence", "E_CONFIDENCE"),
    ("primary", "E_PRIMARY"), ("primary_rule", "E_PRIMARY"),
])
def test_each_validation_error(mutation: str, code: str, results: dict[str, PipelineResult]) -> None:
    result = results["S1"]
    report = result.report.model_copy(deep=True)
    match mutation:
        case "duplicate":
            report.facts.append(report.facts[0].model_copy(deep=True))
        case "no_ref":
            report.facts[0].refs = []
        case "bad_ref":
            report.facts[0].refs = ["m-alice-rtt_ms-9999"]
        case "banned":
            report.facts[0].statement = "RTT tăng do lỗi TURN"
        case "no_support":
            report.inferences[0].supported_by = []
        case "bad_support":
            report.inferences[0].supported_by = ["F999"]
        case "bad_counter":
            report.inferences[0].counter_evidence = [CounterEvidence(description="Phản chứng", fact_ids=["F999"])]
        case "bad_condition":
            report.inferences[0].conditions[0].fact_ids = ["F999"]
        case "confidence":
            report.inferences[0] = report.inferences[0].model_copy(update={"confidence": "99%"})
        case "summary_confidence":
            report.summary = report.summary.model_copy(update={"confidence": "99%"})
        case "primary":
            report.summary.primary_inference_id = "I999"
        case "primary_rule":
            report.summary.primary_rule_id = "wrong"
    validation = validate_report(report, result.bundle)
    assert not validation.passed
    assert code in {issue.code for issue in validation.issues}


def test_hypothesis_requires_missing_evidence(results: dict[str, PipelineResult]) -> None:
    result = results["S6"]
    report = result.report.model_copy(deep=True)
    report.hypotheses[0].missing_evidence = []
    validation = validate_report(report, result.bundle)
    assert "E_HYP_NO_MISSING" in {issue.code for issue in validation.issues}


@pytest.mark.parametrize("ref", ["ev-999", "log-999", "m-alice-rtt_ms-9999", "an-99", "inc-99", "made-up"])
def test_reference_prefixes_must_resolve_to_real_input(ref: str, results: dict[str, PipelineResult]) -> None:
    result = results["S1"]
    report = result.report.model_copy(deep=True)
    report.facts[0].refs = [ref]
    report.facts[0].data["anomaly_id"] = ref
    validation = validate_report(report, result.bundle)
    assert any(issue.code == "E_FACT_BAD_REF" and issue.ref == report.facts[0].fact_id for issue in validation.issues)


def test_unknown_summary_citations_are_warnings(results: dict[str, PipelineResult]) -> None:
    result = results["S1"]
    report = result.report.model_copy(deep=True)
    report.engineering_summary += " Nội dung [F42, I999]."
    validation = validate_report(report, result.bundle)
    assert validation.passed
    assert any(issue.code == "W_SUMMARY_UNKNOWN_CITE" for issue in validation.issues)


def test_llm_numbers_normalization_small_numbers_and_fallback(results: dict[str, PipelineResult]) -> None:
    result = results["S1"]
    report = result.report.model_copy(deep=True)
    report.summary_source = "llm"
    report.engineering_summary = "Quan sát 9999.99 ms [F999]; 3 bước kiểm tra."
    report.executive_summary = ""
    validation = validate_report(report, result.bundle)
    assert {"W_SUMMARY_UNKNOWN_CITE", "W_SUMMARY_NEW_NUMBER"} <= {issue.code for issue in validation.issues}
    sanitized = apply_validation(report, validation)
    assert sanitized.summary_source == "template"
    assert "9999.99" not in sanitized.engineering_summary
    assert "[F999]" not in sanitized.engineering_summary
    assert report.summary_source == "llm"
    report.engineering_summary = "3 bước; 5 phase. " + result.report.facts[0].statement.replace(".", ",")
    assert not any(issue.code == "W_SUMMARY_NEW_NUMBER" for issue in validate_report(report, result.bundle).issues)


def test_apply_validation_removes_bad_inference_and_promotes_next(results: dict[str, PipelineResult]) -> None:
    result = results["S1"]
    report = result.report.model_copy(deep=True)
    report.inferences[0].supported_by = ["F999"]
    validation = validate_report(report, result.bundle)
    sanitized = apply_validation(report, validation)
    assert [item.inference_id for item in sanitized.inferences] == ["I2"]
    assert sanitized.summary.primary_inference_id == "I2"
    assert sanitized.summary.primary_rule_id == "NETWORK_PATH_DEGRADATION"
    assert "[I1]" not in sanitized.engineering_summary and "[I2]" in sanitized.engineering_summary
    assert not sanitized.validation.passed  # Audit errors remain visible to --strict.
    assert len(report.inferences) == 2


def test_no_valid_inference_keeps_severity_and_reports_uncertainty(results: dict[str, PipelineResult]) -> None:
    result = results["S3"]
    report = result.report.model_copy(deep=True)
    report.inferences[0].supported_by = []
    sanitized = apply_validation(report, validate_report(report, result.bundle))
    assert sanitized.inferences == []
    assert sanitized.summary.primary_inference_id is sanitized.summary.primary_rule_id is sanitized.summary.confidence is None
    assert sanitized.summary.severity == "critical"
    assert sanitized.summary.headline == "Không đủ evidence để kết luận"


def test_existing_issues_preserved_without_duplication(results: dict[str, PipelineResult]) -> None:
    result = results["S1"]
    report = result.report.model_copy(deep=True)
    warning = ValidationIssue(level="warning", code="W_LLM_FAILED", message="Fallback")
    report.validation = ValidationResult(passed=True, issues=[warning])
    validation = validate_report(report, result.bundle)
    assert validation.passed and validation.issues == [warning]
    report.validation = validation
    assert validate_report(report, result.bundle) == validation
