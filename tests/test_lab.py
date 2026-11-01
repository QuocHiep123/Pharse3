"""Test WebRTC Lab: file tĩnh, hợp đồng xuất file (events.jsonl / qos.csv), server, lệnh CLI. Không cần trình duyệt."""

from __future__ import annotations

import csv
import io
import json
import re
import shutil
import subprocess
import threading
import urllib.request
from datetime import datetime, timedelta, timezone

import pytest

from callops.cli import main
from callops.lab import lab_dir, make_server
from callops.qos import compute_mos
from callops.ui.loaders import QOS_CSV_COLUMNS, load_jsonl, load_qos_csv
from callops.ui.runner import reanalyze

HTML = lab_dir() / "index.html"
CALL = "lab-ab12cd34"
T0 = datetime(2026, 10, 31, 9, 0, 0, tzinfo=timezone.utc)


def _iso(ms: int) -> str:
    return (T0 + timedelta(milliseconds=ms)).isoformat(timespec="milliseconds")


def _ev(ms: int, event: str, state: str, msg: str, level: str = "INFO", code: str | None = None, **detail):
    return {"ts": _iso(ms), "call_id": CALL, "level": level, "event": event, "state": state,
            "error_code": code, "message": msg, "detail": detail}


def _lab_events() -> list[dict]:
    """Bộ event đúng định dạng JS xuất (cuộc gọi loopback host<->host)."""
    return [
        _ev(30, "INVITE", "SETUP", "alice gửi INVITE", caller="alice"),
        _ev(250, "RINGING_ACCEPTED", "SETUP", "bob chấp nhận", callee="bob"),
        _ev(270, "SDP_OFFER", "OFFER_SENT", "alice createOffer", sdp_lines=40),
        _ev(300, "SDP_ANSWER", "ANSWER_RECEIVED", "bob createAnswer", sdp_lines=38),
        _ev(320, "ICE_GATHERING_COMPLETE", "ANSWER_RECEIVED", "alice gather", participant="alice",
            candidate_types="host"),
        _ev(330, "ICE_GATHERING_COMPLETE", "ANSWER_RECEIVED", "bob gather", participant="bob",
            candidate_types="host"),
        _ev(340, "ICE_CANDIDATES_EXCHANGED", "ICE_CHECKING", "trickle", local=2, remote=2),
        _ev(500, "ICE_SELECTED_PAIR", "ICE_CHECKING", "pair", media_path="P2P_HOST", local_type="host",
            remote_type="host"),
        _ev(700, "MEDIA_ESTABLISHED", "CONNECTED", "DTLS xong", media_path="P2P_HOST"),
        _ev(10700, "BYE", "TERMINATED", "BYE", duration_s=10),
    ]


def _lab_qos_csv(rtt: float = 1.0, jitter: float = 2.0, loss: float = 0.0) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["ts", "call_id", "participant_id", "t_s", "rtt_ms", "jitter_ms", "packet_loss_pct", "mos",
                "video_freeze_count", "concealment_pct"])
    for t in range(10):
        for pid in ("alice", "bob"):
            w.writerow([_iso(700 + 1000 * t), CALL, pid, t, rtt, jitter, loss,
                        compute_mos(rtt, jitter, loss), 0, 0])
    return buf.getvalue()


# ---------------------------------------------------------------- (a) file tĩnh
def test_lab_dir_and_markers() -> None:
    assert lab_dir().is_dir() and HTML.is_file()
    text = HTML.read_text(encoding="utf-8")
    for marker in ("RTCPeerConnection", "getStats", "createOffer", "ice-candidate", "events.jsonl", "qos.csv",
                   "BroadcastChannel", "window.__lab", "captureStream", "textContent"):
        assert marker in text, marker
    assert "alert(" not in text and "confirm(" not in text
    assert "innerHTML" not in text
    assert not re.search(r"(src|href)\s*=\s*[\"']https?://", text)  # không CDN


def test_no_network_egress_and_real_media() -> None:
    text = HTML.read_text(encoding="utf-8")
    for banned in ("fetch(", "XMLHttpRequest", "new WebSocket", "sendBeacon"):
        assert banned not in text, banned
    for needed in ("getUserMedia", "NotAllowedError", "NotReadableError", "isSecureContext", "pagehide",
                   "echoCancellation", "setMedia", "chkListen"):
        assert needed in text, needed


def test_qos_header_matches_model() -> None:
    text = HTML.read_text(encoding="utf-8")
    header = ",".join(QOS_CSV_COLUMNS)
    assert header == "ts,call_id,participant_id,t_s,rtt_ms,jitter_ms,packet_loss_pct,mos,video_freeze_count,concealment_pct"
    assert header in text


def test_event_names_present_in_html() -> None:
    text = HTML.read_text(encoding="utf-8")
    for name in ("INVITE", "RINGING_ACCEPTED", "SDP_OFFER", "SDP_ANSWER", "ICE_GATHERING_COMPLETE",
                 "ICE_CANDIDATES_EXCHANGED", "ICE_SELECTED_PAIR", "TURN_FALLBACK", "ICE_FAILED",
                 "MEDIA_ESTABLISHED", "BYE"):
        assert name in text, name


# ---------------------------------------------------------------- (b) hợp đồng xuất file
def test_export_contract_healthy(tmp_path) -> None:
    ev_p = tmp_path / "events.jsonl"
    ev_p.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in _lab_events()), encoding="utf-8")
    q_p = tmp_path / "qos.csv"
    q_p.write_text(_lab_qos_csv(), encoding="utf-8")
    events, samples = load_jsonl(ev_p), load_qos_csv(q_p)
    res = reanalyze(events, samples, scenario_name="lab")
    assert res.report is not None and res.report.call_id == CALL
    tags = " ".join(" ".join(f.tags) for f in res.report.facts)
    stmts = " ".join(f.evidence for f in res.report.facts)
    for ev in ("ICE_GATHERING_COMPLETE", "ICE_SELECTED_PAIR", "MEDIA_ESTABLISHED"):
        assert ev in stmts or ev.lower() in tags, ev
    assert res.report.media_path is not None and res.report.media_path.value == "P2P_HOST"
    assert any(r.rule == "healthy_call" and r.matched for r in res.rule_traces)


def test_export_contract_degraded_not_healthy(tmp_path) -> None:
    ev_p = tmp_path / "e.jsonl"
    ev_p.write_text("".join(json.dumps(e) + "\n" for e in _lab_events()), encoding="utf-8")
    q_p = tmp_path / "q.csv"
    q_p.write_text(_lab_qos_csv(rtt=420, jitter=45, loss=6.0), encoding="utf-8")
    res = reanalyze(load_jsonl(ev_p), load_qos_csv(q_p), scenario_name="lab")
    assert not any(r.rule == "healthy_call" and r.matched for r in res.rule_traces)


# ---------------------------------------------------------------- MOS: JS == Python
def _extract_js_mos() -> str:
    text = HTML.read_text(encoding="utf-8")
    m = re.search(r"// MOS-BEGIN(.*?)// MOS-END", text, re.S)
    assert m, "thiếu marker MOS-BEGIN/MOS-END"
    return m.group(1)


@pytest.mark.skipif(shutil.which("node") is None, reason="cần node để chạy công thức JS")
def test_js_compute_mos_matches_python() -> None:
    cases = [(1, 2, 0), (60, 5, 0.2), (150, 20, 1), (300, 35, 3), (420, 45, 6), (900, 80, 20), (5000, 300, 60)]
    js = _extract_js_mos() + "\nconsole.log(JSON.stringify(" + json.dumps(cases) + ".map(c=>computeMos(c[0],c[1],c[2]))));"
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout
    got = json.loads(out)
    for (r, j, l), g in zip(cases, got):
        assert g == pytest.approx(compute_mos(r, j, l), abs=0.005), (r, j, l)


@pytest.mark.skipif(shutil.which("node") is None, reason="cần node để kiểm cú pháp JS")
def test_inline_script_parses() -> None:
    text = HTML.read_text(encoding="utf-8")
    scripts = re.findall(r"<script>(.*?)</script>", text, re.S)
    assert scripts
    for s in scripts:
        r = subprocess.run(["node", "--check", "-"], input=s.encode("utf-8"), capture_output=True)
        assert r.returncode == 0, r.stderr.decode("utf-8", "replace")


# ---------------------------------------------------------------- (c) serve
def test_server_serves_index() -> None:
    srv = make_server("127.0.0.1", 0)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        port = srv.server_address[1]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as r:
            assert r.status == 200
            assert b"RTCPeerConnection" in r.read()
    finally:
        srv.shutdown()
        srv.server_close()
        t.join(timeout=5)


# ---------------------------------------------------------------- (d) CLI
def test_cli_lab_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as ei:
        main(["lab", "--help"])
    assert ei.value.code == 0
    out = capsys.readouterr().out
    assert "--host" in out and "--port" in out


def test_cli_lab_calls_serve(monkeypatch: pytest.MonkeyPatch) -> None:
    got: dict = {}
    monkeypatch.setattr("callops.lab.serve", lambda **kw: got.update(kw))
    assert main(["lab", "--port", "8799"]) == 0
    assert got == {"host": "127.0.0.1", "port": 8799}


def test_serve_does_not_crash_on_cp1252_console(monkeypatch) -> None:
    """Hồi quy: console Windows cp1252 không in được tiếng Việt -> serve() từng văng UnicodeEncodeError."""
    import io
    import sys

    from callops import lab

    class _FakeServer:
        server_address = ("127.0.0.1", 1234)

        def serve_forever(self) -> None:
            raise KeyboardInterrupt

        def server_close(self) -> None:
            pass

    monkeypatch.setattr(lab, "make_server", lambda host, port: _FakeServer())
    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="cp1252", errors="strict"))
    lab.serve("127.0.0.1", 1234)
    sys.stdout.flush()
    assert b"WebRTC Lab" in raw.getvalue()


# ---------------------------------------------------------------- robustness: ICE thất bại / cấu hình sai / timeout
def test_failure_markers_in_html() -> None:
    text = HTML.read_text(encoding="utf-8")
    for marker in ("ICE_TIMEOUT_MS", "iceTimeoutMs", "no_candidates", "ice_timeout", "ice_failed", "run_timeout",
                   "CALL_FAILED", "validateIce", "unhandledrejection", "InvalidConfig",
                   "Không thu thập được candidate nào: có thể UDP bị chặn/TURN không tới được"):
        assert marker in text, marker
    assert "const ICE_TIMEOUT_MS = 20000" in text


def _failed_events(reason: str = "no_candidates") -> list[dict]:
    return [
        _ev(30, "INVITE", "SETUP", "alice INVITE", caller="alice"),
        _ev(250, "RINGING_ACCEPTED", "SETUP", "bob chấp nhận", callee="bob"),
        _ev(270, "SDP_OFFER", "OFFER_SENT", "offer", sdp_lines=40),
        _ev(300, "SDP_ANSWER", "ANSWER_RECEIVED", "answer", sdp_lines=38),
        _ev(40000, "ICE_GATHERING_COMPLETE", "ANSWER_RECEIVED", "alice thu thập 0 candidate", participant="alice"),
        _ev(40010, "ICE_FAILED", "ANSWER_RECEIVED", "ICE thất bại", level="ERROR", code="ICE_FAILED",
            reason=reason, turn_configured=True, relay_only=True),
        _ev(40020, "CALL_FAILED", "FAILED", "Cuộc gọi thất bại", level="ERROR", code="ICE_FAILED", reason=reason),
    ]


@pytest.mark.parametrize("reason", ["no_candidates", "ice_timeout"])
def test_export_contract_ice_failed(tmp_path, reason: str) -> None:
    ev_p = tmp_path / "events.jsonl"
    ev_p.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in _failed_events(reason)), encoding="utf-8")
    res = reanalyze(load_jsonl(ev_p), [], scenario_name="lab")
    assert res.report is not None and res.report.verdict.value == "CRITICAL"
    assert res.samples == ()
    assert any(r.rule == "ice_failure_root_cause" and r.matched for r in res.rule_traces)
    assert res.report.inferences


def test_permission_wait_markers_and_no_egress() -> None:
    text = HTML.read_text(encoding="utf-8")
    for marker in ("GUM_TIMEOUT_MS", "gumTimeoutMs", "permissions.query", "location.origin",
                   "Đang chờ bạn cho phép camera/mic", "btnCancelWait", "Huỷ", "mediaWait", "THEO ORIGIN",
                   "chuyển sang media giả lập", "ổ khóa"):
        assert marker in text, marker
    assert "const GUM_TIMEOUT_MS = 20000" in text
    for banned in ("fetch(", "XMLHttpRequest", "new WebSocket", "sendBeacon", "alert(", "innerHTML"):
        assert banned not in text, banned


def test_single_mode_opens_camera_once_and_clones() -> None:
    text = HTML.read_text(encoding="utf-8")
    # toàn trang chỉ có một lời gọi getUserMedia thật, nằm trong makeReal
    assert text.count("getUserMedia(") == 1
    m = re.search(r"async function acquireSharedStream\(\) \{(.*?)\n\}", text, re.S)
    assert m, "thiếu acquireSharedStream"
    body = m.group(1)
    assert body.count("makeReal(") == 1 and "clone()" in body
    # chế độ một trang dùng đường chia sẻ stream
    assert "acquireSharedStream()" in text.split("async function prepareAll")[1]
    for marker in ("NotReadableError", "do lỗi camera:", "OBS, Zoom, Teams", "camBusy"):
        assert marker in text, marker


def test_two_tab_follow_and_placeholders() -> None:
    text = HTML.read_text(encoding="utf-8")
    for marker in ("nằm ở tab", "Tab này là BOB — chỉ tab này mở camera của Bob; tab Alice điều khiển các bước.",
                   "followEvent", "showOwnPair", "stepChip", "data-active", "Alice điều khiển các bước",
                   "setRemoteTab"):
        assert marker in text, marker
    for banned in ("fetch(", "XMLHttpRequest", "new WebSocket", "sendBeacon", "alert(", "innerHTML"):
        assert banned not in text, banned


def test_server_disables_browser_cache() -> None:
    """Hồi quy: không có Cache-Control, Chrome dùng lại bản index.html cũ sau khi sửa code."""
    import threading
    import urllib.request

    from callops.lab import make_server

    srv = make_server("127.0.0.1", 0)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{srv.server_address[1]}/") as r:
            assert "no-store" in (r.headers.get("Cache-Control") or "")
    finally:
        srv.shutdown()
        srv.server_close()


def test_hidden_attribute_beats_display_rules() -> None:
    """Hồi quy: `.vids{display:flex}` từng thắng thuộc tính hidden, ô video đen không ẩn được."""
    html = (lab_dir() / "index.html").read_text(encoding="utf-8")
    assert "[hidden]{display:none!important}" in html
