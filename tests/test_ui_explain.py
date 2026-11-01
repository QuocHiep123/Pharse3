"""Test glossary + giải thích rule/verdict/metric tiếng Việt (callops.ui.explain)."""
from __future__ import annotations

import pytest

from callops.diagnosis import InferenceEngine
from callops.models import MediaPath, Severity
from callops.qos import THRESHOLDS
from callops.ui.explain import (
    GLOSSARY,
    MEDIA_PATH_EXPLAIN_VI,
    NO_MEDIA_PATH_EXPLAIN_VI,
    RULE_EXPLAIN,
    VERDICT_EXPLAIN_VI,
    find_terms,
    glossary_markdown,
    metric_explain_vi,
    rule_explain,
)

REQUIRED_KEYS = {
    "ICE", "STUN", "TURN", "SFU", "NAT", "SYMMETRIC_NAT", "SDP", "SIGNALING", "CANDIDATE",
    "HOST", "SRFLX", "RELAY", "DTLS_SRTP", "RTT", "JITTER", "PACKET_LOSS", "MOS",
    "CONCEALMENT", "BUFFERBLOAT", "FEC", "SIMULCAST", "FACT", "INFERENCE",
}


def test_glossary_has_required_keys() -> None:
    assert REQUIRED_KEYS <= set(GLOSSARY)
    assert all(k == t.key for k, t in GLOSSARY.items())


def test_rule_explain_covers_engine_rules() -> None:
    assert set(RULE_EXPLAIN) == {n for n, _ in InferenceEngine().rules}


def test_enum_coverage() -> None:
    assert set(MEDIA_PATH_EXPLAIN_VI) == set(MediaPath)
    assert set(VERDICT_EXPLAIN_VI) == set(Severity)
    assert NO_MEDIA_PATH_EXPLAIN_VI.strip()


def test_find_terms_longest_match_and_order() -> None:
    keys = [t.key for t in find_terms("Fallback TURN vì NAT đối xứng, ICE failed")]
    assert keys == ["TURN", "SYMMETRIC_NAT", "ICE"]


def test_find_terms_word_boundary_and_dedup() -> None:
    assert find_terms("returned value") == []
    assert find_terms("") == []
    assert len(find_terms("turn turn")) == 1


def test_find_terms_alias_and_plain_nat() -> None:
    assert [t.key for t in find_terms("mất gói và PLC")] == ["PACKET_LOSS", "CONCEALMENT"]
    assert [t.key for t in find_terms("sau NAT")] == ["NAT"]


@pytest.mark.parametrize("metric", sorted(THRESHOLDS))
def test_metric_explain_contains_thresholds(metric: str) -> None:
    th = THRESHOLDS[metric]
    text = metric_explain_vi(metric)
    assert f"{th.warning:g}" in text and f"{th.critical:g}" in text


def test_metric_explain_mos_and_unknown() -> None:
    assert "hệ quả" in metric_explain_vi("mos")
    with pytest.raises(ValueError):
        metric_explain_vi("cpu")


def test_glossary_markdown() -> None:
    md = glossary_markdown()
    assert all(t.name in md for t in GLOSSARY.values())
    sfu = glossary_markdown(["SFU"])
    assert "SFU" in sfu and "STUN" not in sfu


def test_rule_explain_fallback_and_nonempty() -> None:
    assert rule_explain("unknown_rule").title_vi == "unknown_rule"
    assert rule_explain("healthy_call") is RULE_EXPLAIN["healthy_call"]
    assert all(t.short_vi.strip() and t.long_vi.strip() for t in GLOSSARY.values())
    assert all(r.when_vi.strip() and r.title_vi.strip() for r in RULE_EXPLAIN.values())
