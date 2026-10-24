from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import creative_learning, services


class CreativeLearningTests(unittest.TestCase):

    def test_performance_memory_separates_packaging_from_retention(self) -> None:
        diagnosis = creative_learning._performance_sample_diagnosis(
            {
                "duration_seconds": 83,
                "hook_text": "我翻了一晚上没找到榜单，你们手上可能有，评论区甩出来我们查一下。",
                "metrics": {
                    "impressions": 926,
                    "views": 100,
                    "click_through_rate": 10.8,
                    "average_watch_seconds": 45,
                    "completion_rate": 15.69,
                    "comments": 0,
                    "follows": 0,
                },
            }
        )

        strength_ids = {item["id"] for item in diagnosis["strengths"]}
        weakness_ids = {item["id"] for item in diagnosis["weaknesses"]}
        self.assertIn("retain_packaging", strength_ids)
        self.assertIn("repair_retention", weakness_ids)
        self.assertIn("authority_first", weakness_ids)
        self.assertIn("low_friction_cta", weakness_ids)

    def test_channel_memory_is_weighted_and_injected_as_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with (
                patch.object(creative_learning, "CHANNEL_MEMORY_ROOT", root / "channel_memory"),
                patch.object(creative_learning, "LEARNING_ROOT", root),
                patch.object(creative_learning, "LEARNING_EVENTS_FILE", root / "events.jsonl"),
                patch.object(creative_learning.storage, "get_project", side_effect=FileNotFoundError),
            ):
                memory = creative_learning.record_channel_performance(
                    "科技情报站",
                    {
                        "sample_id": "episode-1",
                        "hook_text": "我没找到原始资料，你们帮我找一下。",
                        "metrics": {"views": 993, "completion_rate": 15.69, "comments": 0, "follows": 0},
                    },
                )
                prompt = creative_learning.channel_performance_prompt_block("科技情报站")

            self.assertEqual(memory["sample_count"], 1)
            self.assertIn("样本置信度与时间衰减", memory["policy"]["method"])
            self.assertIn("先交付已核实的结论", prompt)
            self.assertIn("不会永久写死频道", memory["policy"]["note"])

    def test_channel_memory_keeps_separate_dimension_leaders_and_retention_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with (
                patch.object(creative_learning, "CHANNEL_MEMORY_ROOT", root / "channel_memory"),
                patch.object(creative_learning, "LEARNING_ROOT", root),
                patch.object(creative_learning, "LEARNING_EVENTS_FILE", root / "events.jsonl"),
            ):
                creative_learning.record_channel_performance(
                    "科技情报站",
                    {
                        "sample_id": "high-play",
                        "topic": "发布会价格战",
                        "metrics": {
                            "views": 33000,
                            "likes": 172,
                            "comments": 226,
                            "two_second_retention_rate": 52,
                            "five_second_retention_rate": 30,
                            "completion_rate": 8.4,
                        },
                    },
                    emit_event=False,
                )
                memory = creative_learning.record_channel_performance(
                    "科技情报站",
                    {
                        "sample_id": "high-comment",
                        "topic": "Cybercab 争议",
                        "metrics": {
                            "views": 2508,
                            "likes": 12,
                            "comments": 90,
                            "two_second_retention_rate": 35,
                            "five_second_retention_rate": 15,
                            "completion_rate": 2.5,
                        },
                    },
                    emit_event=False,
                )
                prompt = creative_learning.channel_performance_prompt_block("科技情报站")

            leaders = memory["dimension_leaders"]
            self.assertEqual(
                set(leaders),
                {"play_potential", "completion_potential", "comment_potential"},
            )
            self.assertEqual(leaders["play_potential"][0]["sample_id"], "high-play")
            self.assertEqual(leaders["comment_potential"][0]["sample_id"], "high-comment")
            saved = {item["sample_id"]: item for item in memory["samples"]}
            self.assertEqual(saved["high-play"]["metrics"]["two_second_retention_rate"], 52.0)
            self.assertEqual(saved["high-play"]["metrics"]["five_second_retention_rate"], 30.0)
            self.assertIn("播放潜力", prompt)
            self.assertIn("完播潜力", prompt)
            self.assertIn("评论潜力", prompt)
            self.assertIn("评论高不代表留存好", prompt)
            strength_ids = {
                item["id"]
                for item in saved["high-comment"]["diagnosis"]["strengths"]
            }
            self.assertIn("retain_real_disagreement", strength_ids)


    def test_research_router_combines_realtime_chinese_and_global_tech_sources(self) -> None:
        result = creative_learning.research_routing_plan(
            "刚刚发布的中国 AI 手机模型为什么引发海外争议",
            {"topic_mining_hint": "AI工具、手机数码、科技公司"},
            {"current_news_mode": True},
        )

        providers = [item["provider"] for item in result["routes"]]
        self.assertEqual(providers[0], "grok")
        self.assertEqual(providers[1], "tavily")
        self.assertIn("grok", providers)
        self.assertIn("doubao", providers)
        self.assertIn("gemini", providers)
        self.assertTrue(result["current_news_mode"])

    def test_channel_recipe_reuses_method_but_isolates_episode_content(self) -> None:
        template = {
            "key": "科技情报站",
            "name": "科技情报站",
            "brand_name": "科技情报站",
            "mode": "video",
            "target_audience": "科技用户",
            "channel_voice": "先讲结论",
            "visual_strategy": "真实科技纪实",
            "forbidden_rules": "不伪造数据",
            "topic_mining_hint": "AI、手机、互联网",
            "prompt": "频道结构、开场、证据、结论与互动规则",
            "voice_mode": "single",
            "tts_speech_rate": 0.9,
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with (
                patch.object(creative_learning.storage, "get_template", return_value=template),
                patch.object(creative_learning.storage, "TEMPLATES_ROOT", root),
            ):
                recipe = creative_learning.build_channel_recipe("科技情报站", persist=True)

            self.assertTrue(recipe["content_recipe"]["episode_content_isolation"])
            self.assertIn("当期事实", recipe["content_recipe"]["never_reuse"])
            self.assertIn("失败镜头", "；".join(recipe["visual_recipe"]["rules"]))
            self.assertTrue((root / "科技情报站" / "recipe.json").exists())

    def test_evidence_graph_links_verified_fact_to_scene_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "references.json").write_text(
                json.dumps(
                    [
                        {
                            "title": "官方报告",
                            "url": "https://example.com/report",
                            "source": "Tavily",
                            "published_date": "2026-07-27",
                            "freshness_status": "live",
                            "score": 0.9,
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (root / "fact_registry.json").write_text(
                json.dumps(
                    {
                        "facts": [
                            {
                                "fact": "15%",
                                "status": "verified",
                                "sources": [{"label": "官方报告"}],
                                "usages": [],
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (root / "visual_prompt_manifest.json").write_text(
                json.dumps(
                    {
                        "scenes": [
                            {
                                "index": 1,
                                "scene_id": "scene-01",
                                "target": "s_01.png",
                                "prompt": "核心证据是成本只有15%",
                                "quality_score": 92,
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with patch.object(creative_learning.storage, "project_dir", return_value=root):
                graph = creative_learning.build_evidence_graph(9, persist=True)

            self.assertEqual(graph["coverage"]["source_count"], 1)
            self.assertEqual(graph["coverage"]["verified_fact_count"], 1)
            self.assertEqual(graph["coverage"]["scenes_with_fact_links"], 1)
            self.assertEqual(graph["scenes"][0]["linked_facts"], ["15%"])
            self.assertTrue((root / "evidence_graph.json").exists())









    def test_channel_guidance_reports_low_completion_without_hard_duration_constraint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with (
                patch.object(creative_learning, "CHANNEL_MEMORY_ROOT", root / "channel_memory"),
                patch.object(creative_learning, "LEARNING_ROOT", root),
                patch.object(creative_learning, "LEARNING_EVENTS_FILE", root / "events.jsonl"),
            ):
                creative_learning.record_channel_performance(
                    "科技情报站",
                    {
                        "sample_id": "low-completion-long-video",
                        "topic": "测试主题",
                        "metrics": {
                            "views": 12000,
                            "completion_rate": 8.4,
                            "duration_seconds": 460,
                            "comments": 120,
                        },
                    },
                    emit_event=False,
                )
                guidance = creative_learning.channel_production_guidance("科技情报站")
                prompt = creative_learning.channel_performance_prompt_block("科技情报站")

            self.assertIn("正文没有持续交付新信息", guidance["current_problem"])
            self.assertNotIn("60–100 秒", guidance["next_experiment"])
            self.assertIn("时长由必要信息决定", guidance["next_experiment"])
            self.assertIn("开头 2 秒", prompt)
            self.assertIn("8 秒内", prompt)
            self.assertIn("一期围绕一个主结论展开", prompt)
            self.assertIn("不使用固定 CTA", prompt)
            self.assertIn("不参与自动写稿", prompt)
            self.assertIn("不作为生成硬约束", prompt)
            self.assertEqual(guidance["observation_metrics"], ["2 秒留存", "5 秒留存", "完播率"])
            self.assertTrue(guidance["generation_reasons"])


if __name__ == "__main__":
    unittest.main()
