from __future__ import annotations

import hashlib
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any


EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE = re.compile(r"(?<!\d)(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]?\d{3}[-. ]?\d{4}(?!\d)")
SSN = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
BLOCKED_TERMS = {"build malware", "steal credentials", "bypass authentication"}


@dataclass(frozen=True)
class InferenceRequest:
    prompt: str
    task: str = "general"
    risk: str = "low"
    latency_budget_ms: int = 1000


@dataclass
class ReviewItem:
    id: str
    request_id: str
    redacted_prompt: str
    candidate: str
    reason: str
    status: str = "pending"


class Orchestrator:
    def __init__(self) -> None:
        self.audit: list[dict[str, Any]] = []
        self.reviews: dict[str, ReviewItem] = {}
        self.metrics = {"requests": 0, "blocked": 0, "redacted": 0, "reviews": 0}
        self._lock = threading.Lock()

    def infer(self, request: InferenceRequest) -> dict[str, Any]:
        request_id = str(uuid.uuid4())
        with self._lock:
            self.metrics["requests"] += 1

        if any(term in request.prompt.lower() for term in BLOCKED_TERMS):
            self._event(request_id, "blocked", {"reason": "safety_policy"})
            with self._lock:
                self.metrics["blocked"] += 1
            return {"request_id": request_id, "status": "blocked", "reason": "safety_policy"}

        redacted, pii_types = self._redact(request.prompt)
        if pii_types:
            with self._lock:
                self.metrics["redacted"] += 1
            self._event(request_id, "pii_redacted", {"types": pii_types})

        model = self._route(request)
        self._event(request_id, "model_routed", {"model": model, "task": request.task})
        candidate, confidence = self._generate(redacted, model)

        reason = None
        if request.risk == "high":
            reason = "high_risk_request"
        elif confidence < 0.72:
            reason = "low_confidence"

        response: dict[str, Any] = {
            "request_id": request_id,
            "status": "completed",
            "model": model,
            "output": candidate,
            "confidence": confidence,
            "pii_redacted": bool(pii_types),
        }
        if reason:
            item = ReviewItem(str(uuid.uuid4()), request_id, redacted, candidate, reason)
            with self._lock:
                self.reviews[item.id] = item
                self.metrics["reviews"] += 1
            response.update({"status": "pending_review", "review_id": item.id, "review_reason": reason})
            self._event(request_id, "review_queued", {"review_id": item.id, "reason": reason})
        else:
            self._event(request_id, "response_accepted", {"confidence": confidence})
        return response

    def resolve_review(self, review_id: str, decision: str) -> dict[str, Any] | None:
        if decision not in {"approved", "rejected"}:
            raise ValueError("decision must be approved or rejected")
        with self._lock:
            item = self.reviews.get(review_id)
            if not item:
                return None
            item.status = decision
        self._event(item.request_id, "review_resolved", {"review_id": review_id, "decision": decision})
        return asdict(item)

    def review_list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [asdict(item) for item in self.reviews.values()]

    def _route(self, request: InferenceRequest) -> str:
        if request.risk == "high":
            return "quality-guarded"
        if request.latency_budget_ms <= 400:
            return "fast-general"
        if request.task in {"reasoning", "analysis"}:
            return "deep-reasoning"
        return "balanced-general"

    @staticmethod
    def _redact(prompt: str) -> tuple[str, list[str]]:
        found: list[str] = []
        result = prompt
        for label, pattern in (("email", EMAIL), ("phone", PHONE), ("ssn", SSN)):
            if pattern.search(result):
                found.append(label)
                result = pattern.sub(f"[REDACTED_{label.upper()}]", result)
        return result, found

    @staticmethod
    def _generate(prompt: str, model: str) -> tuple[str, float]:
        digest = int(hashlib.sha256(prompt.encode()).hexdigest()[:4], 16)
        confidence = round(0.62 + (digest % 33) / 100, 2)
        output = f"[{model}] Processed request safely: {prompt[:180]}"
        return output, confidence

    def _event(self, request_id: str, kind: str, details: dict[str, Any]) -> None:
        event = {"timestamp": round(time.time(), 3), "request_id": request_id, "event": kind, "details": details}
        with self._lock:
            self.audit.append(event)

