import unittest
from pathlib import Path
from unittest.mock import patch

from app import services


class VisualPromptGateAcceptTests(unittest.TestCase):
    def test_low_score_warning_only_report_can_continue_automatically(self) -> None:
        report = {
            "score": 66,
            "passed": False,
            "issues": [
                {"level": "warn", "where": f"镜头 {index}", "issue": "质量提醒"}
                for index in range(1, 11)
            ],
            "details": {"weak_prompt_count": 10},
        }

        self.assertTrue(services.stage_gate_can_continue_with_warnings("visual_prompt_gate", report))

    def test_visual_prompt_risk_still_blocks_automatic_continue(self) -> None:
        report = {
            "score": 66,
            "passed": False,
            "issues": [
                {"level": "warn", "where": "镜头 1", "issue": "质量提醒"},
                {"level": "risk", "where": "镜头 2", "issue": "主题错位"},
            ],
            "details": {"weak_prompt_count": 2},
        }

        self.assertFalse(services.stage_gate_can_continue_with_warnings("visual_prompt_gate", report))

    def test_visual_prompt_error_still_blocks_automatic_continue(self) -> None:
        report = {
            "score": 66,
            "passed": False,
            "issues": [{"level": "error", "where": "镜头 1", "issue": "提示词结构损坏"}],
            "details": {"weak_prompt_count": 1},
        }

        self.assertFalse(services.stage_gate_can_continue_with_warnings("visual_prompt_gate", report))

    def test_accept_keeps_warnings_and_passes_current_fingerprint(self) -> None:
        current = {
            "key": "visual_prompt_gate",
            "label": "新图生成前提示词闸门",
            "score": 80,
            "passed": False,
            "status": "needs_fix",
            "issues": [{"level": "warn", "where": "镜头 1", "issue": "信息表达偏弱"}],
            "details": {"weak_prompt_count": 2},
            "source_fingerprint": "current-fingerprint",
        }
        with (
            patch.object(services, "cached_stage_gate_result", return_value=current),
            patch.object(services, "stage_gate_source_fingerprint", return_value="current-fingerprint"),
            patch.object(services.storage, "now_ts", return_value=123.0),
            patch.object(services, "save_stage_gate_result") as save_result,
        ):
            accepted = services.accept_production_stage_gate(111, "visual_prompt_gate")

        self.assertTrue(accepted["passed"])
        self.assertEqual(accepted["status"], "accepted_with_warnings")
        self.assertTrue(accepted["accepted_by_user"])
        self.assertEqual(accepted["accepted_at"], 123.0)
        self.assertEqual(accepted["source_fingerprint"], "current-fingerprint")
        self.assertEqual(accepted["issues"], current["issues"])
        save_result.assert_called_once_with(111, accepted)

    def test_accept_rejects_unknown_stage_gate(self) -> None:
        with self.assertRaisesRegex(ValueError, "未知生产闸门"):
            services.accept_production_stage_gate(111, "unknown_gate")

    def test_accept_supports_content_gate_and_pre_video_gate(self) -> None:
        content_gate_mock = {
            "key": "content_gate",
            "score": 0,
            "passed": False,
            "status": "needs_fix",
            "issues": [{"level": "warn", "where": "文案", "issue": "测试提醒"}],
            "source_fingerprint": "cg-fp",
        }
        with (
            patch.object(services, "cached_stage_gate_result", return_value=content_gate_mock),
            patch.object(services, "stage_gate_source_fingerprint", return_value="cg-fp"),
            patch.object(services.storage, "now_ts", return_value=124.0),
            patch.object(services, "save_stage_gate_result"),
        ):
            accepted = services.accept_production_stage_gate(111, "content_gate")
        self.assertTrue(accepted["passed"])
        self.assertEqual(accepted["status"], "accepted_with_warnings")
        self.assertTrue(accepted["accepted_by_user"])

    def test_acceptance_cache_expires_when_prompt_fingerprint_changes(self) -> None:
        report = {
            "gates": {
                "visual_prompt_gate": {
                    "key": "visual_prompt_gate",
                    "score": 80,
                    "passed": True,
                    "status": "accepted_with_warnings",
                    "issues": [{"issue": "提醒仍保留"}],
                    "source_fingerprint": "accepted-version",
                }
            }
        }
        with patch.object(services, "_stage_gates_report_base", return_value=report):
            with patch.object(services, "stage_gate_source_fingerprint", return_value="accepted-version"):
                self.assertIsNotNone(services.cached_stage_gate_result(111, "visual_prompt_gate"))
            with patch.object(services, "stage_gate_source_fingerprint", return_value="new-version"):
                self.assertIsNone(services.cached_stage_gate_result(111, "visual_prompt_gate"))

    def test_accepted_visual_gate_allows_soft_inline_preflight_warnings(self) -> None:
        preflight = {
            "generation_safe": False,
            "hard_blockers": [],
            "issues": [{"level": "warn", "where": "场景 1", "issue": "质量提醒"}],
            "final_prompts": {"s_01.png": "prompt"},
        }
        accepted = {
            "passed": True,
            "status": "accepted_with_warnings",
            "accepted_by_user": True,
        }
        with patch.object(services, "cached_stage_gate_result", return_value=accepted):
            self.assertTrue(services.visual_prompt_preflight_may_continue(111, preflight))

    def test_accepted_visual_gate_does_not_bypass_hard_prompt_risk(self) -> None:
        preflight = {
            "generation_safe": False,
            "hard_blockers": [{"target": "s_01.png", "reasons": ["主题污染"]}],
            "issues": [{"level": "risk", "where": "场景 1", "issue": "主题污染"}],
            "final_prompts": {"s_01.png": "prompt"},
        }
        accepted = {
            "passed": True,
            "status": "accepted_with_warnings",
            "accepted_by_user": True,
        }
        with patch.object(services, "cached_stage_gate_result", return_value=accepted):
            self.assertFalse(services.visual_prompt_preflight_may_continue(111, preflight))

    def test_stale_visual_gate_does_not_bypass_soft_preflight_warning(self) -> None:
        preflight = {
            "generation_safe": False,
            "hard_blockers": [],
            "issues": [{"level": "warn", "where": "场景 1", "issue": "质量提醒"}],
            "final_prompts": {"s_01.png": "prompt"},
        }
        with patch.object(services, "cached_stage_gate_result", return_value=None):
            self.assertFalse(services.visual_prompt_preflight_may_continue(111, preflight))

    def test_skip_all_listener_is_registered_independently_and_keeps_manual_skips(self) -> None:
        source = Path("app.js").read_text(encoding="utf-8")
        refresh_start = source.index('els.stageGatesRefreshBtn?.addEventListener("click"')
        skip_start = source.index('els.stageGatesSkipAllBtn?.addEventListener("click"')
        between = source[refresh_start:skip_start]
        self.assertIn('创建闸门检查任务失败', between)
        self.assertTrue(between.rstrip().endswith('});'))
        self.assertIn('"accepted_with_warnings", "skipped_manual"', source)
        self.assertNotIn('const targets = unpassed.length ? unpassed : gates.filter', source)
        self.assertIn('以下闸门未能跳过', source)
        self.assertIn('已跳过（提醒保留）', source)

    def test_frontend_exposes_ignore_and_continue_action(self) -> None:
        source = Path("app.js").read_text(encoding="utf-8")
        self.assertIn('data-stage-gate-accept=', source)
        self.assertIn('忽略本次并继续', source)
        self.assertIn('/accept`', source)
        self.assertIn('action = canAcceptCurrentPrompt ? "gate-accept" : "gate"', source)


if __name__ == "__main__":
    unittest.main()
