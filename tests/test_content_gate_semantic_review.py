import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app import services


class ContentGateSemanticReviewTests(unittest.TestCase):
    def _semantic_supervisor(self, unsupported=None):
        teachers = [
            {"key": "topic_teacher", "name": "爆款选题老师", "score": 85, "blocking": False, "findings": [], "suggestions": []},
            {"key": "script_teacher", "name": "脚本结构老师", "score": 85, "blocking": False, "findings": [], "suggestions": []},
            {"key": "fact_teacher", "name": "事实合规老师", "score": 85, "blocking": False, "findings": [], "suggestions": []},
        ]
        return {
            "provider": "deepseek-ai-supervisors",
            "overall_score": 88,
            "score": 88,
            "teachers": teachers,
            "semantic_review": {
                "available": True,
                "evidence_present": True,
                "explanation_present": True,
                "concrete_example_present": True,
                "viewer_action_present": True,
                "opening_hook_present": True,
                "retention_progression_present": True,
                "unsupported_claims": unsupported or [],
            },
        }

    def _evaluate(self, supervisor):
        viewer_issue = services.quality_issue(
            "risk",
            "观众收获",
            "关键词启发式待核验：证据标记 0。",
            "补充事实、解释、例子和动作。",
        )
        content_report = {
            "issues": [viewer_issue],
            "engagement": {"overall_score": 4.0, "opening_score": 4.5, "retention_score": 3.6},
        }
        with (
            patch.object(services.storage, "get_project", return_value={"id": 111, "template": "科技情报站"}),
            patch.object(services.storage, "get_template", return_value={"mode": "video"}),
            patch.object(services.storage, "get_brief", return_value="brief"),
            patch.object(services, "effective_project_references", return_value=[]),
            patch.object(services, "ai_supervisor_report", return_value=supervisor),
            patch.object(services, "script_rhythm_report", return_value={"score": 68, "issues": []}),
            patch.object(services, "content_quality_report", return_value=content_report),
            patch.object(services, "stage_gate_source_fingerprint", return_value="fingerprint"),
        ):
            return services.evaluate_production_stage_gate(111, "content_gate", "# 稿子", prefer_ai=True)

    def test_semantic_review_turns_keyword_viewer_value_into_diagnostic(self):
        result = self._evaluate(self._semantic_supervisor())
        self.assertTrue(result["passed"])
        self.assertGreaterEqual(result["score"], services.CONTENT_GATE_MIN_SCORE)
        viewer = next(item for item in result["issues"] if item["where"] == "观众收获")
        self.assertEqual(viewer["level"], "info")
        self.assertTrue(result["details"]["supervisors"]["semantic_review"]["available"])

    def test_semantic_unsupported_claim_remains_hard_blocker(self):
        result = self._evaluate(
            self._semantic_supervisor([{"claim": "咖啡店最大开销一定是排班人员", "reason": "来源摘要没有成本构成"}])
        )
        self.assertFalse(result["passed"])
        self.assertIn("语义事实依据", {item["where"] for item in result["issues"] if item["level"] == "risk"})

    def test_supervisor_prompt_contains_source_material_and_semantic_schema(self):
        messages = services.compose_ai_supervisor_messages(
            {"id": 111, "topic_name": "机器人咖啡师", "template": "科技情报站"},
            {"name": "科技情报站"},
            "# 稿子",
            {"teachers": []},
            [{"title": "媒体探访", "url": "https://example.com", "snippet": "机器人负责冲煮咖啡"}],
        )
        payload = json.loads(messages[1]["content"])
        self.assertEqual(payload["source_material"][0]["title"], "媒体探访")
        self.assertIn("semantic_review", payload["output_schema"])
        self.assertIn("unsupported_claims", payload["output_schema"]["semantic_review"])

    def test_local_cpa_supervisor_sends_direct_review_controls(self):
        response_payload = {
            "overall_score": 86,
            "teachers": [],
            "semantic_review": {
                "evidence_present": True,
                "explanation_present": True,
                "concrete_example_present": True,
                "viewer_action_present": True,
                "opening_hook_present": True,
                "retention_progression_present": True,
                "unsupported_claims": [],
            },
        }
        completion = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(response_payload, ensure_ascii=False)))]
        )
        client = MagicMock()
        client.chat.completions.create.return_value = completion
        with (
            patch.object(services.storage, "get_project", return_value={"id": 111, "template": "科技情报站"}),
            patch.object(services.storage, "get_template", return_value={}),
            patch.object(services.storage, "get_brief", return_value="brief"),
            patch.object(services, "local_ai_supervisor_report", return_value={"teachers": [], "next_actions": []}),
            patch.object(services, "effective_project_references", return_value=[]),
            patch.object(services, "runtime_env", return_value={
                "DEEPSEEK_API_KEY": "TOKEN",
                "DEEPSEEK_BASE_URL": "http://127.0.0.1:8317/v1",
                "DEEPSEEK_MODEL": "deepseek-v4-flash-0731",
            }),
            patch.object(services, "OpenAI", return_value=client),
        ):
            report = services.ai_supervisor_report(111, "# 稿子", prefer_ai=True)
        kwargs = client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs["extra_body"]["reasoning_effort"], "low")
        self.assertEqual(kwargs["extra_body"]["thinking"], {"type": "disabled"})
        self.assertTrue(report["semantic_review"]["available"])

    def test_duration_deviation_is_rewritten_as_natural_clause(self):
        repaired, hits = services.soften_unsupported_numeric_claim_line(
            "【主播】昨晚没睡好，萃取时间偏了2秒，这杯就是苦的。",
            ["2秒"],
        )
        self.assertIn("萃取时间一偏，这杯就是苦的", repaired)
        self.assertNotIn("偏了短时间", repaired)
        self.assertTrue(hits)


if __name__ == "__main__":
    unittest.main()


class ResearchChecklistGateTests(unittest.TestCase):
    def test_checklist_not_script(self):
        self.assertTrue(services.content_is_research_request(
            "# 新闻标题\n## 需要补充的资料\n1. 来源\n## 建议检索方向\n1. 核实"))
        self.assertFalse(services.content_is_research_request(
            "# 新闻标题\n## 口播脚本\n这是一段口播。\n## 需要补充的资料\n## 建议检索方向"))

    def test_gate_does_not_rewrite_research_checklist(self):
        checklist = "# 标题\n## 需要补充的资料\n1. 来源\n## 建议检索方向\n1. 核实"
        before = {"key": "content_gate", "score": 50, "passed": False, "issues": [], "actions": []}
        with patch.object(services.storage, "get_content", return_value=checklist), \
             patch.object(services, "cached_stage_gate_result", return_value=before), \
             patch.object(services, "save_stage_gate_result") as save, \
             patch.object(services, "optimize_project_content") as rewrite:
            result = services.run_production_stage_gate(148, "content_gate")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["score"], 0)
        self.assertIn("待补资料清单", result["error"])
        rewrite.assert_not_called()
        save.assert_called_once()
