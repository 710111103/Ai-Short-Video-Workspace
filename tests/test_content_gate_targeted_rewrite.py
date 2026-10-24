import unittest
from unittest.mock import patch

from app import services


class ContentGateTargetedRewriteTests(unittest.TestCase):
    def semantic_result(self, *, action="DeepSeek 总编改稿并复检"):
        return {
            "key": "content_gate",
            "score": 87,
            "passed": False,
            "status": "failed",
            "cache_hit": True,
            "reassessment_completed": True,
            "actions": [action],
            "issues": [
                {
                    "level": "risk",
                    "where": "语义事实依据",
                    "issue": "具体断言缺少当前来源支持：刷新越快，曝光越多，收入越多。",
                    "fix": "来源没有收入因果",
                }
            ],
            "details": {
                "supervisors": {
                    "semantic_review": {
                        "available": True,
                        "unsupported_claims": [
                            {
                                "claim": "刷新越快，曝光越多，收入越多。",
                                "reason": "来源只说明支持自定义刷新频率，没有说明收入因果",
                            }
                        ],
                    }
                }
            },
        }

    def test_extracts_semantic_claim_as_targeted_rewrite(self):
        targets = services.content_gate_semantic_rewrite_targets(self.semantic_result())
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0]["claim"], "刷新越快，曝光越多，收入越多。")
        self.assertIn("收窄", targets[0]["instruction"])
        self.assertTrue(services.content_gate_has_rewriteable_issues(self.semantic_result()))

    def test_rewrite_prompt_requires_each_unsupported_claim_to_change_or_be_deleted(self):
        targets = services.content_gate_semantic_rewrite_targets(self.semantic_result())
        messages = services.compose_deepseek_rewrite_messages(
            {"template": "科技情报站"},
            {"name": "科技情报站"},
            "# 测试\n\n【主播】刷新越快，曝光越多，收入越多。",
            {"issues": []},
            rewrite_targets=targets,
        )
        prompt = messages[-1]["content"]
        self.assertIn("来源边界定向修订", prompt)
        self.assertIn("都必须在最终稿中被实质修改或删除", prompt)
        self.assertIn("刷新越快，曝光越多，收入越多", prompt)
        self.assertIn("不得新增法律结论", prompt)

    def test_old_generic_failure_gets_one_targeted_rewrite_instead_of_early_stop(self):
        before = self.semantic_result()
        passed = {
            **before,
            "cache_hit": False,
            "score": 90,
            "passed": True,
            "status": "passed",
            "issues": [],
            "details": {"supervisors": {"semantic_review": {"unsupported_claims": []}}},
        }
        with (
            patch.object(services, "cached_stage_gate_result", return_value=before),
            patch.object(services, "evaluate_production_stage_gate", side_effect=[before, passed]),
            patch.object(services, "repair_project_platform_risk", return_value={"changed": False}),
            patch.object(services, "repair_project_fact_compliance", return_value={"changed": False}),
            patch.object(services, "repair_project_unsupported_numeric_facts", return_value={"changed": False}),
            patch.object(services, "runtime_env", return_value={"DEEPSEEK_API_KEY": "TOKEN"}),
            patch.object(services, "optimize_project_content", return_value={"provider": "deepseek", "changed": True}) as optimize,
            patch.object(services, "compress_content_to_retention_budget", return_value={"changed": False}),
            patch.object(services, "save_stage_gate_result"),
        ):
            result = services.run_production_stage_gate(118, "content_gate", auto_fix=True)
        self.assertTrue(result["passed"])
        optimize.assert_called_once()
        targets = optimize.call_args.kwargs["rewrite_targets"]
        self.assertEqual(targets[0]["claim"], "刷新越快，曝光越多，收入越多。")
        self.assertTrue(any("定向事实修订 1 条" in item for item in result["actions"]))

    def test_targeted_failure_is_not_retried_on_unchanged_input(self):
        before = self.semantic_result(action="DeepSeek 总编定向事实修订 1 条并复检")
        with (
            patch.object(services, "cached_stage_gate_result", return_value=before),
            patch.object(services, "repair_project_unsupported_semantic_claims", return_value={"changed": False}),
            patch.object(services, "optimize_project_content") as optimize,
            patch.object(services, "save_stage_gate_result"),
        ):
            result = services.run_production_stage_gate(118, "content_gate", auto_fix=True)
        self.assertTrue(result["retry_skipped"])
        optimize.assert_not_called()

    def test_removes_unsupported_claim_and_dependent_explanation(self):
        content = """# 测试

## 口播脚本
【主播】还有一条最容易被忽略的——退货。
【主播】《消费者权益保护法》第二十五条规定，网络购物通常可以无理由退货。
【主播】根据商品性质，并经消费者在购买时确认不宜退货的商品，可以不适用。
【主播】注意，在购买时确认这几个字。
【主播】也就是说，能不能退，可以提前约定。
【主播】价格和国补才是本期主线。

## 重点字幕
- 网购无理由退货有前提：购买时确认
- 官网和渠道价格不同
"""
        targets = [{
            "claim": "《消费者权益保护法》第二十五条规定，网络购物通常可以无理由退货。根据商品性质，并经消费者在购买时确认不宜退货的商品，可以不适用。"
        }]

        repaired, hits = services.remove_unsupported_semantic_claims_text(content, targets)

        self.assertNotIn("消费者权益保护法", repaired)
        self.assertNotIn("购买时确认", repaired)
        self.assertNotIn("能不能退", repaired)
        self.assertIn("价格和国补才是本期主线", repaired)
        self.assertIn("官网和渠道价格不同", repaired)
        self.assertTrue(hits)


if __name__ == "__main__":
    unittest.main()


