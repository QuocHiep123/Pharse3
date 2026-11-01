"""WebRTC Lab: trang HTML tĩnh dùng RTCPeerConnection thật, xuất events.jsonl + qos.csv cho tab Upload của UI."""

from __future__ import annotations

import functools
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

__all__ = ["lab_dir", "make_server", "serve"]


def lab_dir() -> Path:
    """Thư mục chứa index.html của Lab."""
    return Path(__file__).resolve().parent


class _QuietHandler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        # Trang lab thay đổi thường xuyên khi phát triển: cấm cache để không chạy nhầm bản cũ.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - giữ chữ ký chuẩn
        pass


def make_server(host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    """Tạo server chỉ phục vụ thư mục lab (port=0 -> cổng tự chọn)."""
    handler = functools.partial(_QuietHandler, directory=str(lab_dir()))
    return ThreadingHTTPServer((host, port), handler)


def _safe_print(text: str) -> None:
    """In tiếng Việt kể cả khi console Windows dùng cp1252 (ký tự lạ thành '?', không crash)."""
    try:
        sys.stdout.reconfigure(errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass
    print(text, flush=True)


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    srv = make_server(host, port)
    url = f"http://{host}:{srv.server_address[1]}/"
    _safe_print(f"WebRTC Lab: {url}   (Ctrl+C để dừng)")
    _safe_print(f"Hai tab: {url}?role=alice  và  {url}?role=bob")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
