"""
The page renders for every kind of verdict, and the server answers.

Rendering is plain string building, so the failure mode is an exception on
an edge case (no corner, no plot, a single-lap comparison) rather than a
wrong pixel. Every claim below goes through the full page.
"""
from __future__ import annotations

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from claimcheck import synth
from claimcheck.check.checker import Checker
from claimcheck.web import render
from claimcheck.web.server import make_handler


@pytest.fixture(scope="module")
def checker(tmp_path_factory):
    return Checker(synth.demo(tmp_path_factory.mktemp("web")), ["AA", "BB"])


@pytest.mark.parametrize("claim", [
    "BB loses time in T2 because he brakes early",
    "BB loses time in T5 because he brakes early",
    "BB loses time in T1",
    "BB brakes early in T4",
    "BB loses time in T9",
    "XY loses time",
    "BB oversteers in T3",
    "BB loses time in T2 against his own best",
    "",
])
def test_page_renders(checker, claim):
    v = checker.check(claim) if claim else None
    html = render.page(checker, v, "abc123" if v else None, [], claim)
    assert html.startswith("<!doctype html>") and "</html>" in html
    if v is not None:
        assert render.E(v.label) in html


def test_server_round_trip(checker, tmp_path):
    log = tmp_path / "checks.jsonl"
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(checker, log))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        q = "BB+loses+time+in+T2+because+he+brakes+early"
        page = urllib.request.urlopen(f"{base}/?q={q}").read().decode()
        assert "Supported" in page
        out = json.loads(urllib.request.urlopen(f"{base}/api/check?q={q}").read())
        assert out["stamp"] == "supported" and out["id"]
        data = f"id={out['id']}&judgement=agree&q={q}".encode()
        urllib.request.urlopen(urllib.request.Request(f"{base}/feedback", data=data))
        rows = [json.loads(line) for line in log.read_text().splitlines()]
        assert [r["type"] for r in rows].count("check") == 2
        assert rows[-1] == {**rows[-1], "type": "feedback", "check_id": out["id"], "engineer": "agree"}
        assert rows[0]["files"][0]["sha256"] and rows[0]["thresholds"]
    finally:
        httpd.shutdown()
