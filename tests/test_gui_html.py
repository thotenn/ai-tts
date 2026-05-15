import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from typing import Iterator

import pytest

from piper_sandbox.api import INDEX_HTML, PiperRequestHandler


@pytest.fixture
def server(monkeypatch) -> Iterator[str]:
    monkeypatch.setattr(PiperRequestHandler, "service_mode", "both")
    monkeypatch.setattr(PiperRequestHandler, "engine_url", "")
    monkeypatch.setattr(PiperRequestHandler, "cors_origin", "*")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), PiperRequestHandler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{srv.server_port}"
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=2)


def test_index_html_template_has_chunked_path():
    assert "/speak/chunks" in INDEX_HTML
    assert "audio_base64" in INDEX_HTML
    assert "sayChunked" in INDEX_HTML
    assert "sayWhole" in INDEX_HTML
    assert "chunks_enabled" in INDEX_HTML
    assert "__ENGINE_URL_JSON__" in INDEX_HTML


def test_index_html_template_has_fallback_path():
    assert "/speak" in INDEX_HTML


def test_get_root_injects_engine_url(server, monkeypatch):
    monkeypatch.setattr(PiperRequestHandler, "engine_url", "https://remote.example")
    response = urllib.request.urlopen(f"{server}/", timeout=5)
    body = response.read().decode("utf-8")
    assert "https://remote.example" in body
    assert "__ENGINE_URL_JSON__" not in body


def test_get_root_xss_safe_when_engine_url_has_closing_script(server, monkeypatch):
    monkeypatch.setattr(PiperRequestHandler, "engine_url", "https://x.example/</script><script>alert(1)")
    response = urllib.request.urlopen(f"{server}/", timeout=5)
    body = response.read().decode("utf-8")
    script_start = body.index("<script>")
    script_end = body.index("</script>", script_start + len("<script>"))
    inside = body[script_start:script_end]
    assert "</script>" not in inside[len("<script>"):]
    assert "\\u003c/script\\u003e" in inside


def test_get_root_returns_404_in_engine_only_mode(server, monkeypatch):
    monkeypatch.setattr(PiperRequestHandler, "service_mode", "engine")
    import urllib.error
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(f"{server}/", timeout=5)
    assert exc.value.code == 404
