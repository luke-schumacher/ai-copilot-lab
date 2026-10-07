"""
A local web server for the claim check: standard library only, bound to
127.0.0.1 by default, one Checker held in memory.

    GET  /?q=...          check a claim and show the page
    POST /feedback        the engineer's agree / disagree / unsure
    GET  /api/check?q=... the verdict as JSON
    GET  /api/session     what was loaded, as JSON
"""
from __future__ import annotations

import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from claimcheck.check import log as checklog
from claimcheck.web import render


def make_handler(checker, log_path: Path):
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        server_version = "claimcheck"

        def log_message(self, fmt, *args):  # quiet: the terminal is for the engineer
            pass

        def _send(self, body: str, status: int = 200, ctype: str = "text/html; charset=utf-8"):
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _check(self, q: str, record: bool = True):
            with lock:
                verdict = checker.check(q)
                if not record:
                    return verdict, None
                note = verdict.caveats[0] if verdict.caveats and "translator" in verdict.caveats[0] else ""
                cid = checklog.write_check(log_path, verdict, checker.data.files,
                                           getattr(verdict, "rule_spec", None),
                                           getattr(verdict, "llm_spec", None), note)
            return verdict, cid

        def do_GET(self):
            url = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(url.query)
            q = (params.get("q") or [""])[0].strip()
            try:
                if url.path == "/":
                    # Back from feedback: show the check again, but log it once only.
                    after_feedback = bool(params.get("fb"))
                    verdict, cid = self._check(q, record=not after_feedback) if q else (None, None)
                    banner = "Thanks — the engineer's view is logged next to the check." if after_feedback else ""
                    self._send(render.page(checker, verdict, cid, checklog.read(log_path, 200), q, banner))
                elif url.path == "/api/check":
                    verdict, cid = self._check(q)
                    out = verdict.to_dict()
                    out["id"] = cid
                    self._send(json.dumps(out, ensure_ascii=False, indent=1), ctype="application/json")
                elif url.path == "/api/session":
                    self._send(json.dumps({
                        "files": checker.data.files,
                        "drivers": checker.data.drivers,
                        "laps": [{"driver": l.driver, "lap": l.number, "time_s": round(l.time_s, 3),
                                  "valid": l.valid, "why": l.why_invalid} for l in checker.data.laps],
                        "corners": [c.to_dict() for c in checker.track.corners],
                        "reference": checker.track.reference.label,
                    }, indent=1), ctype="application/json")
                elif url.path == "/health":
                    self._send("ok", ctype="text/plain")
                else:
                    self._send("not found", 404, "text/plain")
            except Exception as exc:  # show it rather than drop the connection
                self._send(f"<pre>{render.E(type(exc).__name__)}: {render.E(str(exc))}</pre>", 500)

        def do_POST(self):
            if self.path != "/feedback":
                return self._send("not found", 404, "text/plain")
            n = int(self.headers.get("Content-Length") or 0)
            form = urllib.parse.parse_qs(self.rfile.read(n).decode("utf-8"))
            cid = (form.get("id") or [""])[0]
            judgement = (form.get("judgement") or [""])[0]
            q = (form.get("q") or [""])[0]
            if cid and judgement in ("agree", "disagree", "unsure"):
                with lock:
                    checklog.write_feedback(log_path, cid, judgement)
            self.send_response(303)
            self.send_header("Location", "/?" + urllib.parse.urlencode({"q": q, "fb": 1}))
            self.end_headers()

    return Handler


def serve(checker, host: str = "127.0.0.1", port: int = 8765, log_path: str = checklog.DEFAULT,
          open_browser: bool = True):
    handler = make_handler(checker, Path(log_path))
    httpd = ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{port}/"
    print(f"AI Copilot claim check on {url}  (Ctrl-C to stop; checks logged to {log_path})", flush=True)
    if open_browser:
        import webbrowser
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
