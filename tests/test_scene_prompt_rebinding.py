import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from app import services


class ScenePromptRebindingTests(unittest.TestCase):
    def test_stale_scene_timeline_is_not_used_for_new_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            content_path = root / "content.md"
            timeline_path = root / "audio" / "scene_timeline.json"
            timeline_path.parent.mkdir(parents=True)
            content_path.write_text("# 新主题\n\n## 口播脚本\n【主播】资金正在换仓。", encoding="utf-8")
            timeline_path.write_text(
                json.dumps({"scenes": [{"prompt": "充电桩3C认证强制实施"}]}, ensure_ascii=False),
                encoding="utf-8",
            )
            now = time.time()
            os.utime(timeline_path, (now - 20, now - 20))
            os.utime(content_path, (now, now))

            def project_file(_project_id: int, relative: str) -> Path:
                return root / relative

            with patch.object(services.storage, "project_file", side_effect=project_file):
                prompts = services.timeline_scene_prompts(89)

        self.assertEqual(prompts, [])

    def test_stale_visual_concept_is_rebuilt_from_final_audio_anchor(self) -> None:
        source = (
            "本期主题：智能电视广告。当前完整口播：55部电视剧被开机广告偷走。"
            "选定视觉概念：时间轴和55个剧集封面。"
        )
        anchor = "第一步，打品牌400客服，直接说我要永久关闭开机广告。"

        rebound, alignment, changed = services.rebind_scene_prompt_to_audio(
            "智能电视广告",
            source,
            anchor,
            anchor,
        )

        self.assertTrue(changed)
        self.assertLess(alignment, 24)
        self.assertIn("400", rebound)
        self.assertIn("永久关闭", rebound)

    def test_aligned_visual_concept_is_preserved(self) -> None:
        source = "口播原文：55部电视剧被开机广告偷走。画面表现等待时间损失。"
        anchor = "55部电视剧被开机广告偷走。"

        rebound, alignment, changed = services.rebind_scene_prompt_to_audio(
            "智能电视广告",
            source,
            anchor,
            anchor,
        )

        self.assertFalse(changed)
        self.assertGreaterEqual(alignment, 24)
        self.assertEqual(rebound, source)

    def test_detailed_but_unrelated_visual_director_is_discarded(self) -> None:
        content = "# 美股财报杀\n\n## 口播脚本\n【主播】美股巨头财报爆雷，资金正在换仓。"
        timeline = {
            "scenes": [
                {
                    "index": 1,
                    "start_ms": 0,
                    "end_ms": 5000,
                    "text": "美股巨头财报爆雷，资金正在换仓。",
                    "audio_anchor": "美股巨头财报爆雷，资金正在换仓。",
                    "prompt": "旧提示：AI账单要求为全部参数付费。",
                }
            ]
        }
        stale_brief = {
            "scene_count": 1,
            "visual_world": "纸张线稿卡通",
            "scenes": [
                {
                    "dialogue_anchor": "总参数284B，每次只激活13B。",
                    "primary_subjects": ["AI账单", "参数阵列"],
                    "action_peak": "账单选择杆停在全量参数旁",
                    "tension": "全勤参数仍在休眠",
                }
            ],
        }
        director = {"edit_direction": {"scenes": [{}]}, "sound_direction": {}}

        with patch.object(services.storage, "get_template", return_value={"mode": "video"}):
            plan = services.build_scene_plan(
                {"id": 0, "template_mode": "video", "topic_name": "美股财报杀"},
                content,
                timeline,
                [],
                visual_brief=stale_brief,
                visual_director=director,
            )

        scene = plan["scenes"][0]
        self.assertTrue(scene["visual_rebound_to_audio"])
        self.assertNotIn("AI账单", scene["image_prompt"])
        self.assertNotIn("参数阵列", scene["image_prompt"])
        self.assertIn("资金正在换仓", scene["image_prompt"])

    def test_outbound_lineage_binding_overrides_stale_rewrite_anchors(self) -> None:
        stale = (
            "本期主题：旧项目主题。当前完整口播：旧镜头让人物拿手机。"
            "主体：保留这一段可用构图和证据关系。"
        )
        topic = "国行 Apple Intelligence 接入千问"
        speech = "海外演示中的跨软件操作，国行目前一个都用不上"

        bound = services.bind_scene_prompt_lineage(stale, topic, speech)

        self.assertTrue(bound.startswith(f"本期主题：{topic}。本镜绑定口播：{speech}"))
        self.assertEqual(services.scene_prompt_speech_anchor(bound), speech)
        self.assertGreaterEqual(services.token_overlap_score(bound, topic, limit=64), 30)
        self.assertGreaterEqual(
            services.token_overlap_score(services.scene_prompt_speech_anchor(bound), speech, limit=96),
            32,
        )

    def test_outbound_lineage_binding_handles_project_145_failed_scenes(self) -> None:
        project_id = 145
        project = services.storage.get_project(project_id)
        content = services.storage.get_content(project_id)
        report = services.storage.read_json(
            services.storage.project_file(project_id, "reports/scene_prompt_preflight.json"),
            {},
        )
        active_topic = services.clean_text(str(project.get("topic_name") or services.first_heading(content) or ""))
        checked = []
        for entry in report.get("entries", []):
            if entry.get("target") not in {"s_03.png", "s_04.png", "s_09.png"}:
                continue
            context = entry.get("semantic_context") if isinstance(entry.get("semantic_context"), dict) else {}
            speech = services.clean_text(str(context.get("speech") or ""))
            bound = services.bind_scene_prompt_lineage(str(entry.get("final_prompt") or ""), active_topic, speech)
            topic_match = __import__("re").search(r"(?:^|\n)本期主题\s*[:：]\s*([^\n。]+(?:。[^本]*?)?)", bound)
            self.assertIsNotNone(topic_match)
            self.assertGreaterEqual(services.token_overlap_score(topic_match.group(1), active_topic, limit=64), 30)
            self.assertGreaterEqual(
                services.token_overlap_score(services.scene_prompt_speech_anchor(bound), speech, limit=96),
                32,
            )
            checked.append(entry.get("target"))
        self.assertEqual(set(checked), {"s_03.png", "s_04.png", "s_09.png"})


if __name__ == "__main__":
    unittest.main()
