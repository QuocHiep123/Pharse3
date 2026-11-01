"""S3: ICE failure before media can be established."""

from calldiag.models import CallTelemetry
from calldiag.scenarios import data
from calldiag.scenarios.builder import Profile
from calldiag.scenarios.common import (
    add_background_logs, add_ice, add_offer_answer_ok, add_setup, add_standard_metrics, new_builder,
)

TURN_CPU = (40.0, 3.0)


def build() -> CallTelemetry:
    b = new_builder("S3")
    add_setup(b)
    add_offer_answer_ok(b)
    add_ice(b, "fail")
    add_background_logs(b, media_from=None, media_to=None, relay=False, end_t=data.ICE_FAILURE_END_T)
    add_standard_metrics(b, qos=None, turn_cpu=Profile(*TURN_CPU),
                         client_cpu=Profile(*data.CLIENT_CPU), end_t=data.ICE_FAILURE_END_T)
    return b.build(end_t=data.ICE_FAILURE_END_T, expected_metrics=list(data.EXPECTED_METRICS_RESOURCE),
                   missing_sources=list(data.MISSING_SOURCES))
