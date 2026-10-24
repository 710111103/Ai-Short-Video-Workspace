from __future__ import annotations

import unittest

from app import services
from app.audience_visual_director import (
    audience_visual_failure_reasons,
    audience_visual_plan,
    audience_visual_repair_actions,
    validate_audience_visual_plan,
)


class AudienceVisualDirectorTests(unittest.TestCase):
    def test_year_and_one_metric_are_not_a_fake_comparison(self) -> None:
        narration = (
            "2026年还没过完，美国国家漏洞数据库已经记录了超过4.5万个软件漏洞，"
            "接近去年全年总和。"
        )
        plan = audience_visual_plan(topic="AI安全", narration=narration)

        self.assertEqual(plan["mode"], "benchmark_metric")
        self.assertFalse(plan["true_comparison"])
        self.assertEqual(plan["primary_metric"]["value"], "4.5万+")
        self.assertEqual(plan["primary_metric"]["label"], "软件漏洞")
        self.assertEqual(plan["kicker"], "软件漏洞规模")
        self.assertEqual(validate_audience_visual_plan(plan), [])



    def test_lightweight_prompt_starts_from_audience_comprehension(self) -> None:
        prompt = (
            "本期主题：AI用越多，漏洞越多？\n"
            "当前完整口播：2026年还没过完，美国国家漏洞数据库已经记录了超过4.5万个软件漏洞，"
            "接近去年全年总和。\n"
            "本镜任务：呈现漏洞规模。\n"
            "选定视觉概念：一个人抱头坐在文件堆中。"
        )
        result = services.lightweight_scene_model_prompt(prompt, max_chars=520)

        self.assertIn("观众1秒必须看懂", result)
        self.assertIn("4.5万+软件漏洞", result)
        self.assertIn("原生工作界面", result)
        self.assertIn("纸堆", result)


    def test_generic_emotion_is_rejected_in_favor_of_native_evidence(self) -> None:
        plan = audience_visual_plan(
            topic="软件漏洞",
            narration="2026年还没过完，已经记录超过4.5万个软件漏洞。",
            index=2,
        )
        issues = audience_visual_failure_reasons(
            plan,
            visual_concept="一个男人抱头坐在巨大文件堆旁边，冷蓝灯光。",
        )
        actions = audience_visual_repair_actions(plan, issues)

        self.assertIn("generic_emotion_substitute", issues)
        self.assertIn("irrelevant_symbolic_object", issues)
        self.assertTrue(any("原生界面" in item for item in actions))

    def test_negative_policy_words_are_not_mistaken_for_chosen_concept(self) -> None:
        plan = audience_visual_plan(
            topic="软件漏洞",
            narration="2026年还没过完，已经记录超过4.5万个软件漏洞。",
            index=2,
        )
        issues = audience_visual_failure_reasons(
            plan,
            visual_concept="使用漏洞检测结果作为主体。排除抱头人物、纸堆、金币和盾牌。",
        )

        self.assertNotIn("generic_emotion_substitute", issues)
        self.assertNotIn("irrelevant_symbolic_object", issues)

    def test_ordinary_context_shot_can_hold_previous_visual(self) -> None:
        plan = audience_visual_plan(
            topic="通勤观察",
            narration="镜头沿着清晨的街道缓慢向前。",
            index=4,
        )

        self.assertFalse(plan["image_required"])
        self.assertEqual(plan["asset_strategy"], "reuse_or_hold_previous_visual")

    def test_short_benchmark_line_is_joined_to_metric_sentence(self) -> None:
        content = """
## 口播脚本
【主播】2026年还没过完，已经记录超过4.5万个软件漏洞
【主播】接近去年全年总和。
【主播】下一段内容。
"""
        expanded = services.expand_scene_speech_anchor(
            content,
            "video",
            "2026年还没过完，已经记录超过4.5万个软件漏洞",
        )

        self.assertIn("4.5万个软件漏洞", expanded)
        self.assertIn("接近去年全年总和", expanded)

    def test_source_match_cannot_pass_on_shared_year_only(self) -> None:
        speech = "2026年还没过完，已经记录超过4.5万个软件漏洞。"
        unrelated = (
            "2026年1月涉事平台向公安局报案，警方通过大数据监测退款订单，"
            "在住所查获75部用于作案的设备。"
        )

        self.assertFalse(
            services.source_information_has_scene_subject_overlap(unrelated, speech)
        )
        self.assertTrue(
            services.source_information_has_scene_subject_overlap(
                "国家漏洞数据库公布软件漏洞检测记录。",
                speech,
            )
        )

    def test_visual_brief_assigns_emotional_jobs_from_the_current_narration(self) -> None:
        project = {"id": 1, "topic_name": "手机App在偷听你聊天？", "template_mode": "video"}
        template = {"mode": "video", "name": "科技情报站"}
        content = """# 手机App在偷听你聊天？

## 口播脚本
【主播】手机刚聊过餐厅，广告就追过来了。
【主播】广告平台会读取位置、搜索记录和广告标识。
【主播】判断重点不是它猜中了，而是应用拿到了哪些权限。
【主播】关掉个性化广告，再观察推荐有没有变化。
"""

        brief = services.build_visual_brief(project, template, content, scene_count=4)

        self.assertIn("audience_resonance_contract", brief)
        self.assertIn("代入", brief["scenes"][0]["emotional_target"])
        self.assertIn("行动", brief["scenes"][-1]["emotional_target"])
        prompt = services.visual_director_scene_seed(brief, 1)
        self.assertIn("情绪任务", prompt)
        self.assertIn("观众代入", prompt)


if __name__ == "__main__":
    unittest.main()
