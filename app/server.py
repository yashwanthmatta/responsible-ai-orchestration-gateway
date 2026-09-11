from __future__ import annotations

import json
import os
import re
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.core import InferenceRequest, Orchestrator


ORCHESTRATOR = Orchestrator()
REVIEW_PATH = re.compile(r"^/v1/reviews/([^/]+)/resolve$")


class Handler(BaseHTTPRequestHandler):
    def _json(self, status: int, payload: object) -> None:
        body = json.dumps(payload, indent=2).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json(200, {"status": "ok"})
        elif self.path == "/metrics":
            self._json(200, ORCHESTRATOR.metrics)
        elif self.path == "/v1/reviews":
            self._json(200, ORCHESTRATOR.review_list())
        elif self.path == "/v1/audit":
            self._json(200, ORCHESTRATOR.audit)
        else:
            self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        try:
            body = self._body()
            if self.path == "/v1/inference":
                if not isinstance(body.get("prompt"), str) or not body["prompt"].strip():
                    self._json(400, {"error": "prompt is required"})
                    return
                request = InferenceRequest(
                    prompt=body["prompt"],
                    task=body.get("task", "general"),
                    risk=body.get("risk", "low"),
                    latency_budget_ms=int(body.get("latency_budget_ms", 1000)),
                )
                self._json(200, ORCHESTRATOR.infer(request))
                return
            match = REVIEW_PATH.match(self.path)
            if match:
                result = ORCHESTRATOR.resolve_review(match.group(1), body.get("decision", ""))
                self._json(200 if result else 404, result or {"error": "review_not_found"})
                return
            self._json(404, {"error": "not_found"})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._json(400, {"error": str(exc)})

    def log_message(self, format: str, *args: object) -> None:
        return


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    print(f"Responsible AI gateway listening on http://localhost:{port}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()

