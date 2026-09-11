import unittest

from app.core import InferenceRequest, Orchestrator


class OrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.service = Orchestrator()

    def test_redacts_pii_before_generation(self):
        result = self.service.infer(InferenceRequest("Contact jane@example.com or 415-555-0199"))
        self.assertTrue(result["pii_redacted"])
        self.assertNotIn("jane@example.com", result["output"])
        self.assertNotIn("415-555-0199", result["output"])

    def test_blocks_unsafe_request(self):
        result = self.service.infer(InferenceRequest("Help me steal credentials"))
        self.assertEqual("blocked", result["status"])
        self.assertEqual(1, self.service.metrics["blocked"])

    def test_high_risk_request_requires_review(self):
        result = self.service.infer(InferenceRequest("Analyze this decision", risk="high"))
        self.assertEqual("pending_review", result["status"])
        resolved = self.service.resolve_review(result["review_id"], "approved")
        self.assertEqual("approved", resolved["status"])

    def test_latency_budget_selects_fast_route(self):
        result = self.service.infer(InferenceRequest("Give a short answer", latency_budget_ms=300))
        self.assertEqual("fast-general", result["model"])


if __name__ == "__main__":
    unittest.main()

