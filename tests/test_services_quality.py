import asyncio
import base64
import inspect
import json
import http.client
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app import release_automation, services, storage, validators


class SceneQualityTests(unittest.TestCase):
    def test_entity_profile_uses_declared_research_subject_over_short_title(self) -> None:
        profile = services.topic_entity_profile(
            "10 月 1 日，和还要五年",
            "核心检索对象：Nebius H100 黄仁勋 英伟达 倪军 宁德时代 全固态电池\n"
            "核心材料：Nebius 将上调 H100 算力价格。",
        )

        self.assertNotEqual(profile["primary_entity"], "会造")
        self.assertIn(profile["primary_entity"], {"Nebius", "H100", "黄仁勋", "英伟达", "倪军", "宁德时代", "全固态电池"})

    def test_structured_brief_searches_each_material_separately(self) -> None:
        brief = """核心检索对象：Nebius H100 黄仁勋 英伟达 倪军 宁德时代 全固态电池

核心材料：
- Nebius 从 10 月 1 日上调 H100 按需租赁价格 17%。
- 黄仁勋公开预测英伟达芯片销量将在 2027 年翻倍。
- 宁德时代倪军表示全固态电池规模化至少还要五年。

主线：比较承诺的时间责任。
"""
        queries = services.evidence_search_queries(brief, "fallback")
        contract = services.evidence_contract(
            "时间差",
            brief,
            {"primary_entity": "Nebius"},
        )

        self.assertEqual(len(queries), 3)
        self.assertTrue(any("nebius" in item.lower() and "h100" in item.lower() for item in queries))
        self.assertTrue(any("黄仁勋" in item and "2027" in item for item in queries))
        self.assertEqual(len(set(queries)), 3)
        self.assertEqual(len(contract["claims"]), 3)
        self.assertFalse(any("核心材料" in item["text"] for item in contract["claims"]))

    def test_unstructured_transcript_opening_builds_event_queries(self) -> None:
        brief = """国产摩托车在摩博会上集体冲高，张雪机车五车齐发，最贵 13.8 万，配置对标 150 万。
        同一场论坛上，隆鑫通用董事长李耀表示，年轻人更关注声浪和社交表达。

        目标受众
        对摩托车感兴趣的城市用户。

        完整口播逐字稿
        后续长稿不应污染开头两条事实的检索对象。
        """

        queries = services.evidence_search_queries(brief, "fallback")

        self.assertEqual(len(queries), 2)
        self.assertTrue(any("张雪" in item and "13.8" in item for item in queries))
        self.assertTrue(any("隆鑫" in item and "李耀" in item for item in queries))
        self.assertFalse(any("fallback" == item for item in queries))

    def test_compound_product_search_ignores_speculative_numbers(self) -> None:
        brief = "小米申请 SU9 LUX 商标，网传 5.3 米与百万级定位尚未证实。"
        queries = services.evidence_search_queries(brief, "小米SU9 LUX曝光")
        self.assertEqual(queries, ['"SU9 LUX" 小米 商标'])

    def test_contextual_price_does_not_split_spaced_ten_thousand_unit(self) -> None:
        claims = services.strong_numeric_claims_in_line("一场比赛要花 2000 万到 3000 万元。")
        facts = {item["normalized"] for item in claims}

        self.assertNotIn("2000元", facts)
        self.assertNotIn("3000元", facts)

    def test_deepseek_request_retries_remote_disconnect(self) -> None:
        response = {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}
        with (
            patch.object(
                services,
                "_request_provider_json",
                side_effect=[http.client.RemoteDisconnected("closed"), response],
            ) as request,
            patch.object(services.time, "sleep"),
        ):
            content, finish_reason = services.request_deepseek_chat_completion(
                api_key="key",
                base_url="http://127.0.0.1:8317/v1",
                model="deepseek-flash",
                messages=[{"role": "user", "content": "test"}],
                temperature=0.1,
                max_tokens=100,
            )

        self.assertEqual(content, "ok")
        self.assertEqual(finish_reason, "stop")
        self.assertEqual(request.call_count, 2)

    def test_volc_api_key_headers_do_not_mix_legacy_credentials(self) -> None:
        headers = services.volc_asr_api_key_headers(
            "speech-api-key",
            "volc.seedasr.auc",
            "request-id",
            submit=True,
        )

        self.assertEqual(headers["X-Api-Key"], "speech-api-key")
        self.assertEqual(headers["X-Api-Resource-Id"], "volc.seedasr.auc")
        self.assertEqual(headers["X-Api-Sequence"], "-1")
        self.assertNotIn("X-Api-App-Key", headers)
        self.assertNotIn("X-Api-Access-Key", headers)

    def test_volc_api_key_utterances_parse_official_millisecond_fields(self) -> None:
        entries = services.parse_volc_asr_api_key_utterances(
            {
                "result": {
                    "text": "第一句。第二句。",
                    "utterances": [
                        {"text": "第一句。", "start_time": 120, "end_time": 960},
                        {"text": "第二句。", "start_time": 1100, "end_time": 2300},
                    ],
                }
            }
        )

        self.assertEqual(
            entries,
            [
                {"text": "第一句。", "start_ms": 120, "end_ms": 960},
                {"text": "第二句。", "start_ms": 1100, "end_ms": 2300},
            ],
        )

    def test_volc_api_key_submit_uploads_local_audio_and_queries_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir_name:
            audio_path = Path(temp_dir_name) / "podcast.mp3"
            audio_path.write_bytes(b"local-audio-bytes")
            responses = [
                (
                    {"task_id": "task-123"},
                    {"X-Api-Status-Code": "20000000", "X-Api-Message": "OK"},
                    200,
                ),
                (
                    {
                        "result": {
                            "utterances": [
                                {"text": "测试字幕。", "start_time": 80, "end_time": 1280}
                            ]
                        }
                    },
                    {"X-Api-Status-Code": "20000000", "X-Api-Message": "OK"},
                    200,
                ),
            ]
            with (
                patch.object(services, "_volc_asr_request_json", side_effect=responses) as request_mock,
                patch.object(services.time, "sleep"),
            ):
                result = services.transcribe_volc_asr_api_key(
                    audio_path,
                    {
                        "VOLC_SPEECH_API_KEY": "speech-api-key",
                        "VOLC_ASR_API_KEY_MODE": "submit",
                        "VOLC_ASR_API_KEY_RESOURCE_ID": "volc.seedasr.auc",
                    },
                    timeout=60,
                )

        submit_call, query_call = request_mock.call_args_list
        submit_body = submit_call.args[2]
        self.assertEqual(base64.b64decode(submit_body["audio"]["data"]), b"local-audio-bytes")
        self.assertEqual(submit_body["audio"]["format"], "mp3")
        self.assertEqual(query_call.args[1]["X-Api-Request-Id"], "task-123")
        self.assertNotIn("X-Api-Sequence", query_call.args[1])
        self.assertEqual(result["utterances"][0]["start_ms"], 80)

    def test_volc_validator_prefers_api_key_over_legacy_bridge(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temp_dir_name,
            patch.object(
                validators,
                "_prepare_asr_sample",
                return_value=(Path(temp_dir_name) / "sample.wav", "wave"),
            ),
            patch.object(
                services,
                "transcribe_volc_asr_api_key",
                return_value={"utterances": [{"text": "测试", "start_ms": 0, "end_ms": 500}]},
            ) as api_key_mock,
            patch.object(services, "run_original_bridge") as legacy_mock,
        ):
            result = validators.validate_volc_asr(
                {
                    "VOLC_SPEECH_API_KEY": "speech-api-key",
                    "VOLC_ASR_APP_KEY": "legacy-app",
                    "VOLC_ASR_ACCESS_KEY": "legacy-token",
                }
            )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["detail"]["provider"], "volc_api_key")
        api_key_mock.assert_called_once()
        legacy_mock.assert_not_called()

    def test_volc_api_key_is_masked_in_settings_payload(self) -> None:
        self.assertIn("VOLC_SPEECH_API_KEY", storage.SECRET_KEYS)
        self.assertNotIn("speech-api-key", storage.mask_secret("speech-api-key"))

    def test_placeholder_heading_is_not_used_as_episode_title(self) -> None:
        content = "# 短标题\n\n## 口播脚本\n【主播】真正的主题内容"

        self.assertEqual(services.first_heading(content), "")
        self.assertEqual(services.summarize_content(content, "video")["cover_title"], "")
        self.assertEqual(services.first_heading("# 真正的主题\n\n正文"), "真正的主题")

    def test_placeholder_heading_uses_following_plain_text_title(self) -> None:
        content = "# 短标题\n超导材料减到一层，反而看清了本质\n\n## 口播脚本\n【主播】先看实验结果。"

        self.assertEqual(services.first_heading(content), "超导材料减到一层，反而看清了本质")
        self.assertEqual(
            services.summarize_content(content, "video")["video_title"],
            "超导材料减到一层，反而看清了本质",
        )

    def test_highlights_accept_markdown_bullets_and_numbered_items(self) -> None:
        content = """# 测试

## 重点字幕
- 第一条事实
* 第二条结论
3. 第三条行动
"""

        self.assertEqual(
            services.parse_highlights(content),
            ["第一条事实", "第二条结论", "第三条行动"],
        )

    def test_effective_references_filters_noise_and_keeps_selected_primary_source(self) -> None:
        auto_topic = {
            "payload": {
                "references": [
                    {
                        "title": "Single-layer cuprate superconductivity",
                        "url": "https://nature.example/paper",
                        "source": "nature.example",
                        "score": 0.8,
                    }
                ]
            }
        }

        def read_json(path: Path, default: object) -> object:
            return auto_topic if str(path).endswith("auto_topic.json") else default

        with (
            patch.object(services.storage, "get_project", return_value={"topic_name": "单铜氧层高温超导体"}),
            patch.object(services.storage, "get_brief", return_value=""),
            patch.object(
                services.storage,
                "get_references",
                return_value=[{"title": "楼盘价格", "url": "https://house.example/item", "source": "house.example"}],
            ),
            patch.object(services, "project_source_references", return_value=[]),
            patch.object(services.storage, "read_json", side_effect=read_json),
        ):
            references = services.effective_project_references(51)

        urls = [item.get("url") for item in references]
        self.assertIn("https://nature.example/paper", urls)
        self.assertNotIn("https://house.example/item", urls)

    def test_scene_audit_rejects_exact_duplicate_from_hidden_temp_path(self) -> None:
        if services.Image is None or services.np is None:
            self.skipTest("image audit dependencies unavailable")
        with tempfile.TemporaryDirectory() as temp_dir:
            scene_dir = Path(temp_dir) / "scenes"
            scene_dir.mkdir()
            pixels = services.np.zeros((72, 128, 3), dtype=services.np.uint8)
            pixels[:, :, 0] = services.np.arange(128, dtype=services.np.uint8)
            pixels[:, :, 1] = services.np.arange(72, dtype=services.np.uint8)[:, None] * 3
            pixels[12:60, 25:105, 2] = 240
            existing_path = scene_dir / "s_01.png"
            temp_path = scene_dir / ".s_04.gen-123456.png"
            services.Image.fromarray(pixels).save(existing_path)
            temp_path.write_bytes(existing_path.read_bytes())

            with patch.object(
                services,
                "run_local_image_ocr",
                return_value={"status": "unavailable", "text": "", "lines": []},
            ):
                report = services.audit_generated_image(temp_path, "128x72", "scene", "")

            self.assertEqual(services.scene_image_index_from_path(temp_path), 4)
            self.assertTrue(report["project_similarity"]["checked"])
            self.assertTrue(report["project_similarity"]["exact_duplicate"])
            self.assertIn("exact_duplicate_scene", report["reasons"])
            self.assertEqual(report["severity"], "hard")

    def test_scene_audit_rejects_large_flat_icon_placeholder(self) -> None:
        if services.Image is None or services.np is None:
            self.skipTest("image audit dependencies unavailable")
        with tempfile.TemporaryDirectory() as temp_dir:
            scene_dir = Path(temp_dir) / "scenes"
            scene_dir.mkdir()
            pixels = services.np.zeros((72, 128, 3), dtype=services.np.uint8)
            pixels[:, :] = (22, 116, 232)
            pixels[18:54, 50:78] = (248, 248, 248)
            image_path = scene_dir / ".s_02.gen-123.png"
            services.Image.fromarray(pixels).save(image_path)

            with patch.object(
                services,
                "run_local_image_ocr",
                return_value={"status": "unavailable", "text": "", "lines": []},
            ):
                report = services.audit_generated_image(image_path, "128x72", "scene", "")

            self.assertIn("flat_graphic_placeholder", report["reasons"])
            self.assertEqual(report["severity"], "hard")

    def test_chatgpt_image_snapshot_uses_stable_src_not_dom_index(self) -> None:
        before = [
            {
                "index": 7,
                "key": "https://example.test/old.png|1024x1024",
                "src": "https://example.test/old.png",
                "width": 1024,
                "height": 1024,
            }
        ]

        keys = services.chatgpt_image_snapshot_keys(before)

        self.assertEqual(keys, {"https://example.test/old.png|1024x1024"})
        self.assertNotIn(7, keys)

    def test_chatgpt_image_dom_probe_accepts_new_data_turn_role(self) -> None:
        script = services._large_chatgpt_images_script()

        self.assertIn('[data-turn]', script)
        self.assertIn('getAttribute("data-turn")', script)
        self.assertIn('generated-image-preview', script)
        self.assertIn('generated-image-gallery', script)
        self.assertIn('imagegen-image', script)
        self.assertIn('generated: generatedImage', script)
        self.assertIn('after_latest_user', script)

    def test_chatgpt_image_candidate_recovers_generated_image_after_latest_user(self) -> None:
        image = {
            "index": 4,
            "key": "https://chatgpt.com/backend-api/estuary/content?id=current|1672x941",
            "src": "https://chatgpt.com/backend-api/estuary/content?id=current",
            "width": 1672,
            "height": 941,
            "in_main": True,
            "assistant": True,
            "generated": True,
            "after_latest_user": True,
            "conversation_turn_index": 1,
            "turn_index": 2,
        }

        selected = services.select_chatgpt_image_candidate([image], {image["key"]})

        self.assertEqual(selected, image)

    def test_chatgpt_image_candidate_does_not_recover_old_generated_image(self) -> None:
        image = {
            "index": 4,
            "key": "https://chatgpt.com/backend-api/estuary/content?id=old|1672x941",
            "src": "https://chatgpt.com/backend-api/estuary/content?id=old",
            "width": 1672,
            "height": 941,
            "in_main": True,
            "assistant": True,
            "generated": True,
            "after_latest_user": False,
        }

        selected = services.select_chatgpt_image_candidate([image], {image["key"]})

        self.assertIsNone(selected)

    def test_stale_scene_check_rejects_images_without_actual_prompt_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scene_dir = root / "scenes"
            scene_dir.mkdir()
            paths = [scene_dir / "s_01.png", scene_dir / "s_02.png"]
            for path in paths:
                path.write_bytes(b"I" * 5000)
            records = [
                {
                    "filename": path.name,
                    "source_prompt": f"主题：测试。口播原文：第 {index} 镜。",
                    "topic_hash": "topic-hash",
                    "content_hash": "content-hash",
                    "prompt_policy_version": "older-policy",
                }
                for index, path in enumerate(paths, start=1)
            ]
            prompts = [record["source_prompt"] for record in records]

            def fake_read_json(path, default=None):
                name = Path(path).name
                if name == "scene_prompts.json":
                    return records
                if name == "content_change.json":
                    return {"generated_at": 1.0, "invalidate": {"scene_images": ["all"]}}
                return default if default is not None else {}

            with (
                patch.object(services.storage, "get_project", return_value={"template_mode": "video", "topic_name": "测试"}),
                patch.object(services.storage, "get_content", return_value="# 测试"),
                patch.object(services.storage, "project_file", side_effect=lambda _project_id, relative: root / relative),
                patch.object(services.storage, "read_json", side_effect=fake_read_json),
                patch.object(services.storage, "scene_status", return_value={"expected_count": 2, "existing": []}),
                patch.object(services, "current_scene_prompts", return_value=prompts),
                patch.object(
                    services,
                    "project_image_context_hashes",
                    return_value={"topic_hash": "topic-hash", "content_hash": "content-hash"},
                ),
                patch.object(services, "find_scene_image_paths", return_value=paths),
            ):
                stale = services.stale_scene_image_indexes(1)

            self.assertEqual(stale, [1, 2])

    def test_stale_scene_check_accepts_current_topic_after_prompt_rewrite(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scene_dir = root / "scenes"
            scene_dir.mkdir()
            image_path = scene_dir / "s_01.png"
            image_path.write_bytes(b"I" * 5000)
            image_path.with_suffix(".md").write_text(
                "本期主题：问界渠道变化\n当前完整口播：问界门店渠道正在调整。\n本镜画面：门店与汽车",
                encoding="utf-8",
            )
            record = {
                "filename": "s_01.png",
                "source_prompt": "完全不同措辞的本轮视觉方案",
                "topic_hash": "topic-hash",
                "content_hash": "content-hash",
            }

            def fake_read_json(path, default=None):
                name = Path(path).name
                if name == "scene_prompts.json":
                    return [record]
                if name == "scene_plan.json":
                    return {"scenes": [{"index": 1, "speech_text": "问界门店渠道正在调整。"}]}
                return default if default is not None else {}

            with (
                patch.object(services.storage, "get_project", return_value={"template_mode": "video", "topic_name": "问界渠道变化"}),
                patch.object(services.storage, "get_content", return_value="# 问界渠道变化"),
                patch.object(services.storage, "project_file", side_effect=lambda _project_id, relative: root / relative),
                patch.object(services.storage, "read_json", side_effect=fake_read_json),
                patch.object(services.storage, "scene_status", return_value={"expected_count": 1, "existing": []}),
                patch.object(services, "current_scene_prompts", return_value=["另一版当前场景提示词"]),
                patch.object(services, "project_image_context_hashes", return_value={"topic_hash": "topic-hash", "content_hash": "content-hash"}),
                patch.object(services, "find_scene_image_paths", return_value=[image_path]),
            ):
                stale = services.stale_scene_image_indexes(1)

            self.assertEqual(stale, [])

    def test_stale_scene_check_accepts_compacted_prompt_with_current_lineage(self) -> None:
        topic = "\u95ee\u754c\u6e20\u9053\u53d8\u5316"
        narration = "\u95ee\u754c\u95e8\u5e97\u6e20\u9053\u6b63\u5728\u8c03\u6574\u3002"
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scene_dir = root / "scenes"
            scene_dir.mkdir()
            image_path = scene_dir / "s_01.png"
            image_path.write_bytes(b"I" * 5000)
            image_path.with_suffix(".md").write_text(
                f"\u5f53\u524d\u5b8c\u6574\u53e3\u64ad\uff1a{narration}\n\u672c\u955c\u753b\u9762\uff1a\u95e8\u5e97\u4e0e\u6c7d\u8f66",
                encoding="utf-8",
            )
            record = {
                "filename": "s_01.png",
                "source_prompt": "compacted provider prompt",
                "topic_hash": "topic-hash",
                "content_hash": "content-hash",
            }

            def fake_read_json(path, default=None):
                name = Path(path).name
                if name == "scene_prompts.json":
                    return [record]
                if name == "scene_plan.json":
                    return {"scenes": [{"index": 1, "speech_text": narration}]}
                return default if default is not None else {}

            with (
                patch.object(services.storage, "get_project", return_value={"template_mode": "video", "topic_name": topic}),
                patch.object(services.storage, "get_content", return_value=f"# {topic}"),
                patch.object(services.storage, "project_file", side_effect=lambda _project_id, relative: root / relative),
                patch.object(services.storage, "read_json", side_effect=fake_read_json),
                patch.object(services.storage, "scene_status", return_value={"expected_count": 1, "existing": []}),
                patch.object(services, "current_scene_prompts", return_value=["current planning prompt"]),
                patch.object(services, "project_image_context_hashes", return_value={"topic_hash": "topic-hash", "content_hash": "content-hash"}),
                patch.object(services, "find_scene_image_paths", return_value=[image_path]),
            ):
                stale = services.stale_scene_image_indexes(1)

            self.assertEqual(stale, [])

    def test_compact_outbound_prompt_has_topic_lineage(self) -> None:
        prompt = "本期主题：问界渠道变化\n当前完整口播：问界门店渠道正在调整。\n本镜画面：门店与汽车"
        self.assertTrue(services.image_prompt_has_topic_anchor(prompt))

    def test_actual_provider_prompt_survives_planning_record_hash_loss(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scene_dir = root / "scenes"
            scene_dir.mkdir()
            image_path = scene_dir / "s_01.png"
            image_path.write_bytes(b"I" * 5000)
            image_path.with_suffix(".md").write_text(
                "本期主题：问界渠道变化\n当前完整口播：问界门店渠道正在调整。\n本镜画面：门店与汽车",
                encoding="utf-8",
            )

            def fake_read_json(path, default=None):
                name = Path(path).name
                if name == "scene_prompts.json":
                    return [{"filename": "s_01.png", "prompt": "闸门重建后的规划提示词"}]
                if name == "scene_plan.json":
                    return {"scenes": [{"index": 1, "speech_text": "问界门店渠道正在调整。"}]}
                return default if default is not None else {}

            with (
                patch.object(services.storage, "get_project", return_value={"template_mode": "video", "topic_name": "问界渠道变化"}),
                patch.object(services.storage, "get_content", return_value="# 问界渠道变化"),
                patch.object(services.storage, "project_file", side_effect=lambda _project_id, relative: root / relative),
                patch.object(services.storage, "read_json", side_effect=fake_read_json),
                patch.object(services.storage, "scene_status", return_value={"expected_count": 1, "existing": []}),
                patch.object(services, "current_scene_prompts", return_value=["当前规划提示词"]),
                patch.object(services, "project_image_context_hashes", return_value={"topic_hash": "new-topic", "content_hash": "new-content"}),
                patch.object(services, "find_scene_image_paths", return_value=[image_path]),
            ):
                stale = services.stale_scene_image_indexes(1)

            self.assertEqual(stale, [])

    def test_project_visual_memory_uses_other_accepted_scene_concepts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scene_dir = Path(temp_dir) / "scenes"
            scene_dir.mkdir()
            (scene_dir / "s_01.png").write_bytes(b"image")
            (scene_dir / "s_01.md").write_text(
                "选定视觉概念：人物在桌前摊开双手，左右摆放两件产品。\n",
                encoding="utf-8",
            )
            output_path = scene_dir / ".s_03.gen-123.png"

            clause = services.project_scene_visual_memory_clause(output_path)

            self.assertIn("镜头1", clause)
            self.assertIn("左右", clause)
            self.assertNotIn("人物在桌前摊开双手", clause)
            self.assertIn("不能复刻", clause)

    def test_visual_concept_rejects_generic_presenter_question_mark_pose(self) -> None:
        issues = services.visual_concept_quality_issues(
            "主播面对镜头摊开双手，桌面摆着两件产品，身后屏幕显示一个巨大问号。"
        )

        self.assertIn("通用人物摊手摆拍，缺少当前口播的证据动作", issues)
        self.assertIn("用问号或红叉代替具体冲突证据", issues)

    def test_visual_concept_keeps_concrete_test_action(self) -> None:
        issues = services.visual_concept_quality_issues(
            "测试员按下耳机降噪键，测量仪同步记录频谱变化，人物回头看向镜头旁的结果屏。"
        )

        self.assertNotIn("通用人物摊手摆拍，缺少当前口播的证据动作", issues)

    def test_generation_repairs_legacy_generic_concept_without_losing_speech(self) -> None:
        prompt = (
            "本期主题：降噪耳机。当前完整口播：谁才是真正的降噪神器？ "
            "选定视觉概念：主播面对镜头摊开双手，身后是巨大问号。 "
            "本镜任务：呈现真假降噪的冲突。数字边界：不虚构数字。"
        )

        repaired, issues = services.repair_generic_scene_visual_concept(prompt)

        self.assertTrue(issues)
        self.assertIn("当前完整口播：谁才是真正的降噪神器", repaired)
        self.assertIn("本镜任务：呈现真假降噪的冲突", repaired)
        self.assertIn("视觉方案重选", repaired)
        self.assertNotIn("主播面对镜头摊开双手", repaired)

    def test_balanced_brief_preserves_topic_and_speech_from_manifest_prompt(self) -> None:
        source = (
            "主题：蓝牙降噪耳机：你买的是降噪，还是噪音？。"
            "口播原文：「你猜，谁才是真正的降噪神器？」。"
            "主主体：当前口播中的关键人物和核心物件。"
            "动作：人物正在操作、比较或检查核心物件。"
        )

        balanced = services.balanced_scene_generation_brief(source)
        integrity = services.semantic_scene_brief_integrity(balanced, balanced)

        self.assertIn("本期主题：蓝牙降噪耳机", balanced)
        self.assertIn("当前完整口播：你猜，谁才是真正的降噪神器", balanced)
        self.assertIn("不要用人物正对镜头摆拍", balanced)
        self.assertTrue(integrity["required"])
        self.assertTrue(integrity["ok"])

    def test_balanced_brief_extracts_specific_evidence_from_comma_joined_prompt(self) -> None:
        source = (
            "这张图先抓住这个瞬间：库存数字可能是障眼法，"
            "主题：存储芯片见顶争议，"
            "口播原文：花旗直接甩数据反驳大摩拿13周库存吓人，"
            "画面任务：把库存表象与真实需求做成正面对照，"
            "主主体：存储芯片晶圆与仓库货架，"
            "证据信息：一侧库存堆高，另一侧服务器订单持续流入，"
            "可视化关系：库存表象被订单流向穿透"
        )

        balanced = services.balanced_scene_generation_brief(source)

        self.assertIn("本镜任务：把库存表象与真实需求做成正面对照", balanced)
        self.assertIn("来源支撑信息：一侧库存堆高，另一侧服务器订单持续流入", balanced)
        self.assertIn("建议的信息结构：库存表象被订单流向穿透", balanced)

    def test_visual_director_concept_uses_episode_specific_beat_and_action(self) -> None:
        concept = services.visual_director_scene_concept(
            {
                "beat": "花旗用真实需求反驳大摩的库存见顶判断",
                "primary_subjects": ["芯片晶圆与仓库货架", "被截断的旧字段..."],
                "action_peak": "分析师把库存曲线与服务器订单并排核对",
                "tension": "短期库存表象与持续需求形成相反结论",
            }
        )

        self.assertIn("花旗用真实需求反驳大摩", concept)
        self.assertIn("芯片晶圆与仓库货架", concept)
        self.assertIn("库存曲线与服务器订单并排核对", concept)
        self.assertNotIn("被截断的旧字段", concept)

    def test_scene_spoken_text_removes_visual_stage_direction(self) -> None:
        text = "人物手指划过屏幕圈出几个错误 最坑的是AI汇编，你让它写2024年深圳房价分析"

        cleaned = services.clean_scene_spoken_text(text)

        self.assertTrue(cleaned.startswith("最坑的是AI汇编"))
        self.assertNotIn("人物手指划过屏幕", cleaned)

    def test_scene_spoken_text_removes_whiteboard_direction_before_dialogue(self) -> None:
        text = "左边写自己两小时右边写AI半小时然后打红叉 那我是不是就不该用AI了"

        cleaned = services.clean_scene_spoken_text(text)

        self.assertEqual(cleaned, "那我是不是就不该用AI了")

    def test_tts_rejects_visual_marker_variants(self) -> None:
        self.assertEqual(services.strip_spoken_line_for_tts("【（画面】电脑屏幕出现红色弹窗"), "")
        self.assertEqual(services.strip_spoken_line_for_tts("【画面切换】人物点击删除按钮"), "")
        self.assertEqual(services.strip_spoken_line_for_tts("【镜头】手指特写"), "")
        self.assertEqual(services.strip_spoken_line_for_tts("【（屏幕上叠加字幕】93%可关闭）"), "")

    def test_tts_rejects_unlabelled_image_generation_instructions(self) -> None:
        self.assertEqual(
            services.strip_spoken_line_for_tts(
                "短视频画面，真实摄影质感，横向画面，主体与字幕区分开，留出标题空间。"
            ),
            "",
        )
        self.assertEqual(
            services.strip_spoken_line_for_tts("请直接调用生成图片功能，只返回图片，不要回复文字。"),
            "",
        )

    def test_tts_keeps_spoken_question_after_visual_lead_in(self) -> None:
        cleaned = services.strip_spoken_line_for_tts("【主播】65W标在盒子上，你以为插上就能跑满？")

        self.assertEqual(cleaned, "你以为插上就能跑满？")

    def test_dialogue_parser_exposes_only_spoken_lane(self) -> None:
        content = """# 快充测试

## 口播脚本
【主播】65W标在盒子上，你以为插上就能跑满？
【主播】画面方向：横向构图，留出字幕区，只保留一个信息牌。
【画面】充电器包装盒特写，屏幕上显示功率变化。
【主播】真正决定速度的，是手机和充电器支持的协议能不能对上。
"""

        lines = services.parse_dialogue_lines(content, "video")

        self.assertEqual(
            lines,
            [
                "【主播】你以为插上就能跑满？",
                "【主播】真正决定速度的，是手机和充电器支持的协议能不能对上。",
            ],
        )

    def test_source_locked_subtitles_keep_tts_words_instead_of_asr_errors(self) -> None:
        entries = services.build_source_locked_subtitles(
            ["百分之九十三的电视可以关闭广告", "操作入口在设置页面"],
            [
                {"start_ms": 200, "end_ms": 2400, "text": "9×3的电视可以关闭广告"},
                {"start_ms": 2500, "end_ms": 4800, "text": "操作入口在设置页面"},
            ],
            5000,
        )

        joined = "".join(item["text"] for item in entries)
        self.assertIn("百分之九十三", joined)
        self.assertNotIn("9×3", joined)
        self.assertNotIn("广告操作", "|".join(item["text"] for item in entries))
        self.assertEqual([item["text"] for item in entries], ["百分之九十三的电视可以关闭广告", "操作入口在设置页面"])
        self.assertGreaterEqual(entries[0]["start_ms"], 200)
        merged = services.merge_subtitle_display_entries(entries)
        self.assertEqual([item["text"] for item in merged], ["百分之九十三的电视可以关闭广告", "操作入口在设置页面"])
        self.assertTrue(all(left["end_ms"] <= right["start_ms"] for left, right in zip(entries, entries[1:])))

    def test_source_locked_subtitles_use_asr_sentence_boundaries_not_character_share(self) -> None:
        long_sentence = "第一句虽然字很多但是主播说得很快而且一口气说完"
        short_sentence = "结论别买"
        entries = services.build_source_locked_subtitles(
            [long_sentence, short_sentence],
            [
                {"start_ms": 120, "end_ms": 1250, "text": long_sentence},
                {"start_ms": 1300, "end_ms": 9000, "text": short_sentence},
            ],
            9200,
        )

        first_sentence_end = max(item["end_ms"] for item in entries if item["utterance_index"] == 0)
        second_sentence_start = min(item["start_ms"] for item in entries if item["utterance_index"] == 1)
        self.assertLess(first_sentence_end, 1800)
        self.assertGreaterEqual(second_sentence_start, first_sentence_end)
        self.assertEqual("".join(item["text"] for item in entries), long_sentence + short_sentence)

    def test_audio_activity_subtitles_skip_real_silence(self) -> None:
        entries = services.build_audio_activity_locked_subtitles(
            ["第一句话", "第二句话"],
            [(200, 2200), (5200, 7200)],
            7500,
        )

        self.assertEqual([item["text"] for item in entries], ["第一句话", "第二句话"])
        self.assertEqual(entries[0]["start_ms"], 200)
        self.assertLessEqual(entries[0]["end_ms"], 2200)
        self.assertGreaterEqual(entries[1]["start_ms"], 5200)
        self.assertEqual(entries[1]["end_ms"], 7200)

    def test_audio_activity_subtitle_segment_switches_after_nearby_silence(self) -> None:
        entries = services.build_audio_activity_locked_subtitles(
            ["前半句先把大家容易误解的问题说明白，后半句再给出真正结论"],
            [(100, 1600), (2050, 3650)],
            3800,
        )

        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["end_ms"], 1600)
        self.assertEqual(entries[1]["start_ms"], 2050)

    def test_audio_activity_subtitles_reset_drift_at_real_tts_round_boundaries(self) -> None:
        entries = services.build_round_anchored_audio_activity_subtitles(
            ["第一段说得快", "第一段继续", "第二段重新开始", "第二段结束"],
            [(100, 1800), (5000, 6900)],
            7000,
            [
                {"round": 1, "start_ms": 0, "end_ms": 2000, "text": "第一段说得快。第一段继续。"},
                {"round": 2, "start_ms": 4800, "end_ms": 7000, "text": "第二段重新开始。第二段结束。"},
            ],
        )

        second_round = [item for item in entries if item["utterance_index"] >= 2]
        self.assertEqual(len(entries), 4)
        self.assertGreaterEqual(second_round[0]["start_ms"], 5000)
        self.assertEqual(second_round[-1]["end_ms"], 6900)
        self.assertEqual({item["tts_round"] for item in second_round}, {2})

    def test_subtitle_fidelity_flags_asr_created_math_expression(self) -> None:
        report = services.subtitle_text_fidelity(
            "百分之九十三的电视可以关闭广告",
            [{"text": "9×3的电视可以关闭广告"}],
        )

        self.assertFalse(report["passed"])
        self.assertEqual(report["suspicious_math"], ["9×3"])

    def test_mass_visual_marker_contamination_recovers_only_spoken_lines(self) -> None:
        content = """# 测试

## 口播脚本
【（画面】电脑屏幕出现扩展管理页面，鼠标划过权限提示
【（画面】60万用户的密码被一个插件偷光了，是你亲手点的“允许”。
【画面切换】主角点击允许按钮，手指特写
【（画面】真正的问题是插件拥有读取所有网站数据的权限。
【（画面】现在打开扩展列表，把不用的插件彻底删除。

## 重点字幕
1. 检查插件权限
"""

        repaired, hits = services.repair_visual_prompt_contamination_text(content, "video")

        script = services.extract_section(repaired, "口播脚本", level=2)
        self.assertNotIn("电脑屏幕", script)
        self.assertNotIn("手指特写", script)
        self.assertIn("【主播】60万用户的密码被一个插件偷光了，是你亲手点的“允许”。", script)
        self.assertIn("【主播】真正的问题是插件拥有读取所有网站数据的权限。", script)
        self.assertIn("【主播】现在打开扩展列表，把不用的插件彻底删除。", script)
        self.assertTrue(any("移除口播区画面提示词" in item for item in hits))

    def test_canonical_repair_removes_prompt_lane_and_trims_visual_lead_in(self) -> None:
        content = """# 快充测试

## 口播脚本
【主播】65W标在盒子上，你以为插上就能跑满？
【主播】短视频画面，真实摄影质感，横向构图，留出字幕区。
【主播】真正决定速度的，是协议能不能对上。

## 重点字幕
1. 先看协议
"""

        repaired, hits = services.repair_visual_prompt_contamination_text(content, "video")
        script = services.extract_section(repaired, "口播脚本", level=2)

        self.assertIn("【主播】你以为插上就能跑满？", script)
        self.assertIn("【主播】真正决定速度的，是协议能不能对上。", script)
        self.assertNotIn("真实摄影质感", script)
        self.assertTrue(any("剥离台词前置画面描述" in item for item in hits))

    def test_asr_subtitle_normalizes_mixed_chinese_tens(self) -> None:
        self.assertEqual(services.normalize_asr_subtitle_text("6十万用户受到影响"), "60万用户受到影响")
        self.assertEqual(services.normalize_asr_subtitle_text("3十6个插件"), "36个插件")

    def test_audio_anchor_uses_complete_subtitle_window(self) -> None:
        group = [
            {"text": "所以现在你去检查一下", "start_ms": 0},
            {"text": "你最近用 AI 写的稿子", "start_ms": 2000},
            {"text": "看看最终到底省没省时间", "start_ms": 4000},
        ]

        anchor = services.select_key_audio_anchor(group, "口播原文：检查AI稿子的真实耗时")

        self.assertGreaterEqual(len(anchor), 18)
        self.assertFalse(anchor.endswith("AI"))
        self.assertIn("省没省时间", anchor)

    def test_semantic_key_image_count_never_exceeds_requested_count(self) -> None:
        utterances = [
            {"text": "先别急", "start_ms": 0},
            {"text": "它用30秒生成1000字", "start_ms": 12_000},
            {"text": "结果人工改稿花了3小时", "start_ms": 35_000},
            {"text": "真正的问题是事实错误", "start_ms": 62_000},
            {"text": "评论区告诉我", "start_ms": 92_000},
        ]

        result = services.suggest_semantic_key_image_count(utterances, 7, 100_000)

        self.assertLessEqual(result["final"], 7)
        self.assertGreaterEqual(result["final"], 3)
        self.assertGreaterEqual(result["semantic_count"], 2)

    def test_three_minute_audio_uses_fewer_more_meaningful_scenes(self) -> None:
        suggestion = services.suggest_scene_count(186_913, 5)
        self.assertEqual(suggestion["final"], 5)
        self.assertEqual(suggestion["candidate_count"], 5)
        self.assertGreaterEqual(suggestion["minimum"], 5)
        self.assertLessEqual(suggestion["final"], suggestion["maximum"])

    def test_eighty_seven_second_video_uses_adaptive_visual_density(self) -> None:
        suggestion = services.suggest_scene_count(86_808, 3)

        self.assertEqual(suggestion["duration_target"], 9)
        self.assertEqual(suggestion["final"], 3)

    def test_ninety_nine_second_video_is_not_collapsed_to_four_scenes(self) -> None:
        suggestion = services.suggest_scene_count(99_000, 4)

        self.assertEqual(suggestion["duration_target"], 10)
        self.assertEqual(suggestion["final"], 4)

    def test_same_duration_uses_script_information_density_for_scene_count(self) -> None:
        sparse = """## 口播脚本
【主播】同一台手机，官网在涨，授权店在降。
【主播】这件事的核心就是渠道价格不同。
【主播】换句话说，官网价不等于市场成交价。
【主播】所以买之前多问一家店。
"""
        dense = """## 口播脚本
【主播】同一台手机，官网涨了八百，授权店却降了一千三百。
【主播】官网执行统一挂牌价，但是授权店需要自己承担库存。
【主播】库存压久了会占用现金，所以经销商愿意降价回款。
【主播】这意味着官网价只是参考，不是市场成交价。
【主播】第一要确认是不是国行，第二要确认能不能开票。
【主播】第三还要确认官方保修是否一致。
【主播】低价商品可能限制七天无理由退货，拆封条件也不同。
【主播】最终省下多少钱，取决于报价和售后条件是否同时成立。
"""

        sparse_result = services.resolve_project_scene_count(
            {"id": 0}, sparse, "video", candidate_count=4, audio_ms=100_000
        )
        dense_result = services.resolve_project_scene_count(
            {"id": 0}, dense, "video", candidate_count=4, audio_ms=100_000
        )

        self.assertEqual(sparse_result["count_source"], "script_information")
        self.assertGreater(dense_result["information_count"], sparse_result["information_count"])
        self.assertGreater(dense_result["final"], sparse_result["final"])

    def test_semantic_filter_does_not_collapse_normal_video_below_pacing_floor(self) -> None:
        utterances = [
            {"text": "先给出反常识结论", "start_ms": 0, "end_ms": 8000},
            {"text": "库存数字只是一次性抢货形成的假象", "start_ms": 16_000, "end_ms": 24_000},
            {"text": "真正增长来自企业级存储需求", "start_ms": 38_000, "end_ms": 46_000},
            {"text": "关键比例从18%升到41%", "start_ms": 58_000, "end_ms": 66_000},
            {"text": "最后回到该看库存还是看增量", "start_ms": 78_000, "end_ms": 86_000},
        ]

        result = services.suggest_semantic_key_image_count(utterances, 5, 86_808)

        self.assertGreaterEqual(result["final"], 4)
        self.assertLessEqual(result["final"], 5)

    def test_excessive_candidate_scene_count_returns_to_duration_target(self) -> None:
        suggestion = services.suggest_scene_count(182_357, 15)
        self.assertEqual(suggestion["duration_target"], 12)
        self.assertEqual(suggestion["final"], 15)

    def test_information_density_cannot_bypass_duration_band_upper_bound(self) -> None:
        suggestion = services.suggest_scene_count(123_884, 19, information_count=19)

        self.assertEqual(suggestion["minimum"], 7)
        self.assertEqual(suggestion["maximum"], 13)
        self.assertEqual(suggestion["final"], 13)

    def test_auto_scene_count_uses_audio_target_even_when_candidate_is_in_range(self) -> None:
        suggestion = services.suggest_scene_count(155_960, 9)
        self.assertEqual(suggestion["duration_target"], 10)
        self.assertEqual(suggestion["final"], 9)

    def test_audio_only_job_preserves_existing_scene_count(self) -> None:
        count, preserved = services.stable_scene_count_for_job(
            13,
            12,
            ["audio", "subtitles", "video"],
        )
        self.assertEqual(count, 12)
        self.assertTrue(preserved)

    def test_visual_job_can_recalculate_scene_count(self) -> None:
        count, preserved = services.stable_scene_count_for_job(
            13,
            12,
            ["audio", "subtitles", "images", "video"],
        )
        self.assertEqual(count, 13)
        self.assertFalse(preserved)

    def test_content_audit_respects_authoritative_timeline_scene_count(self) -> None:
        content = """# 测试

## 口播脚本
【主播】你以为一个数字就能说明问题吗？
【主播】先看真实测量。
【主播】再看重复实验。
【主播】接着解释误差来源。
【主播】然后看连续趋势。
【主播】最后给出判断方法。
【主播】现在复测一次。
【主播】评论区说说你的经历。

## 重点字幕
1. 单次别信
2. 连续复测
3. 看趋势
4. 再核对

## 图片提示词
镜头优先保证信息关系一眼可懂。
"""
        with (
            patch.object(services, "resolved_scene_prompt_plan", return_value=[f"场景 {index}" for index in range(1, 6)]),
            patch.object(services, "effective_visual_scene_count", return_value=5),
        ):
            report = services.content_audit_report(
                {"id": 51, "template_mode": "video", "topic_name": "测试"},
                {"mode": "video"},
                "",
                content,
                references=[{"title": "资料", "url": "https://example.com"}],
            )

        self.assertFalse(any(item.get("where") == "场景图" for item in report["issues"]))
        self.assertFalse(any(item.get("where") == "平台风险" for item in report["issues"]))

    def test_scene_prompt_reduction_keeps_coverage_and_skips_filler(self) -> None:
        prompts = [
            "口播原文：开场损失3000块，主体：手机",
            "口播原文：先别急，真正的点在后面，主体：人物",
            "口播原文：至少20家厂商关停，主体：灯泡",
            "口播原文：这里换个角度看，问题就清楚了，主体：人物",
            "口播原文：认准Matter认证标志，主体：包装盒",
            "口播原文：设备最长寿命等于公司余额，主体：设备",
        ]
        selected = services.normalize_scene_prompt_count(prompts, 3, "智能家居", "video")
        self.assertEqual(len(selected), 3)
        self.assertIn("3000块", selected[0])
        self.assertIn("20家", selected[1])
        self.assertIn("最长寿命", selected[2])

    def test_scene_prompt_reduction_can_drop_weak_final_cta(self) -> None:
        prompts = [
            "口播原文：30秒生成1000字，3小时改稿",
            "口播原文：你以为只改错别字",
            "口播原文：AI最擅长说正确的废话",
            "口播原文：AI会编数据，事实错误",
            "口播原文：逻辑跳跃，只能重搭骨架",
            "口播原文：AI只出草稿，自己写关键段落",
            "口播原文：不要直接粘贴",
            "口播原文：评论区告诉我，下期再见",
        ]
        selected = services.normalize_scene_prompt_count(prompts, 6, "AI写作", "video")
        self.assertFalse(any("下期再见" in item for item in selected))
        self.assertTrue(any("只出草稿" in item for item in selected))

    def test_timeline_cuts_on_meaningful_audio_instead_of_equal_windows(self) -> None:
        utterances = [
            {"start_ms": 0, "end_ms": 2000, "text": "3000块买的灯两年后失效"},
            {"start_ms": 2000, "end_ms": 4000, "text": "先别急真正的点在后面"},
            {"start_ms": 4000, "end_ms": 6000, "text": "2024年至少20家小厂关停"},
            {"start_ms": 6000, "end_ms": 8000, "text": "这里换个角度看"},
            {"start_ms": 8000, "end_ms": 10000, "text": "认准Matter认证标志"},
        ]
        prompts = [
            "口播原文：3000块买的灯两年后失效，主体：手机",
            "口播原文：2024年至少20家小厂关停，主体：灯泡",
            "口播原文：认准Matter认证标志，主体：包装盒",
        ]
        timeline = services.build_scene_timeline_for_scene_count(utterances, prompts, 3, 10_000)
        starts = [scene["start_ms"] for scene in timeline["scenes"]]
        self.assertEqual(starts, [5_000, 9_000, 13_000])
        self.assertIn("先别急", timeline["scenes"][0]["text"])
        self.assertEqual(timeline["scenes"][0]["audio_anchor"], "3000块买的灯两年后失效")

    def test_semantic_timeline_keeps_scenes_temporally_balanced(self) -> None:
        utterances = [
            {
                "start_ms": index * 8_000,
                "end_ms": min(86_000, index * 8_000 + 7_500),
                "text": f"Evidence step {index + 1} changes the conclusion by {index + 11} percent",
            }
            for index in range(11)
        ]
        prompts = [f"Scene {index + 1} evidence" for index in range(5)]

        timeline = services.build_scene_timeline_for_scene_count(utterances, prompts, 5, 86_000)
        durations = [scene["end_ms"] - scene["start_ms"] for scene in timeline["scenes"]]

        self.assertEqual(len(durations), 5)
        self.assertLessEqual(max(durations), 24_000)
        self.assertGreaterEqual(min(durations), 8_000)
        self.assertEqual(timeline["repair"]["selection_policy"], "temporal_semantic_balance_v2")

    def test_semantic_scene_beats_do_not_spend_two_images_on_callbacks(self) -> None:
        utterances = [
            {"start_ms": 0, "end_ms": 3000, "text": "每年等待开机广告的时间够看完55部繁花"},
            {"start_ms": 18_000, "end_ms": 22_000, "text": "93%的智能电视可以彻底关闭开机广告"},
            {"start_ms": 38_000, "end_ms": 43_000, "text": "广告和会员占总利润将近四成"},
            {"start_ms": 66_000, "end_ms": 71_000, "text": "打400客服报MAC地址后台直接关掉"},
            {"start_ms": 98_000, "end_ms": 103_000, "text": "第一步打品牌400要求永久关闭开机广告"},
            {"start_ms": 132_000, "end_ms": 137_000, "text": "买新电视优先选择全系无广告品牌"},
            {"start_ms": 158_000, "end_ms": 163_000, "text": "55部繁花终于从你手上省下来"},
        ]

        selected = services.select_semantic_scene_beats(utterances, 6, 165_000)
        anchors = [item["text"] for item in selected]

        self.assertEqual(sum("55部繁花" in item for item in anchors), 1)
        self.assertEqual(sum("400" in item for item in anchors), 1)
        self.assertTrue(any("利润" in item for item in anchors))
        self.assertTrue(any("无广告品牌" in item for item in anchors))

    def test_timeline_audio_anchor_never_uses_cached_prompt_rules(self) -> None:
        utterances = [
            {"start_ms": 0, "end_ms": 2000, "text": "开场说智能灯失效"},
            {"start_ms": 2000, "end_ms": 4000, "text": "至少20家厂商关停"},
        ]
        prompts = [
            "口播原文：开场说智能灯失效，主体：手机",
            "口播原文：对应概念。关键节点最多加入一个视觉钩子，主体：灯泡",
        ]
        timeline = services.build_scene_timeline_for_scene_count(utterances, prompts, 2, 4_000)
        self.assertEqual(timeline["scenes"][1]["audio_anchor"], "至少20家厂商关停")
        self.assertNotIn("视觉钩子", timeline["scenes"][1]["audio_anchor"])

    def test_clean_authored_audio_anchor_can_restore_complete_sentence(self) -> None:
        utterances = [
            {"start_ms": 0, "end_ms": 2000, "text": "开场损失3000块"},
            {"start_ms": 2000, "end_ms": 4000, "text": "产品最多倒闭风险最低"},
            {"start_ms": 4000, "end_ms": 6000, "text": "第二不确定买哪家"},
        ]
        prompts = [
            "口播原文：开场损失3000块，主体：手机",
            "口播原文：产品最多、倒闭风险最低，主体：认证设备",
        ]
        timeline = services.build_scene_timeline_for_scene_count(utterances, prompts, 2, 6_000)
        self.assertEqual(timeline["scenes"][1]["audio_anchor"], "产品最多、倒闭风险最低")

    def test_workwear_does_not_trigger_ai_callouts(self) -> None:
        entry = {
            "semantic_context": {
                "speech": "一个穿工作服的人提着清洁桶，说免费上门清洗油烟机。",
            },
            "visual_decision": {
                "hook_words": ["免费=最贵"],
                "must_show": ["工作服", "清洁桶", "猫眼"],
            },
            "final_prompt": "老人从猫眼看见穿工作服的陌生人。",
        }
        candidates = services.scene_callout_candidates_for_entry(entry, "免费上门清洗油烟机骗局")
        ai_labels = {"AI代办", "效率翻倍", "岗位变化", "人机协作", "省下时间", "别被替代"}
        self.assertFalse(ai_labels.intersection(candidates))
        self.assertIn("免费=最贵", candidates)

    def test_foreign_callouts_lower_semantic_score(self) -> None:
        score = services.image_semantic_score(
            "老人从猫眼看见上门推销员，画面短字：AI抢工作、效率翻倍、岗位变化。",
            {
                "topic": "免费上门清洗油烟机骗局",
                "speech": "穿工作服的人敲门，老人先别开门。",
                "visual_director": "猫眼、清洁桶、老人手停在门把手上。",
            },
        )
        self.assertIn("AI抢工作", score["foreign_callouts"])
        self.assertLess(score["overall"], 65)

    def test_cover_semantic_score_uses_key_facts_not_full_script_copy(self) -> None:
        score = services.image_semantic_score(
            "智能手表显示93%，同一只手上的指夹式血氧仪显示98%，手指停在120拨号键上。",
            {
                "topic": "智能手表测血氧？别信",
                "speech": "血氧数据别信，电子安慰剂别当真。我差点被一块手表送进ICU，它说我血氧93%，拿医用血氧仪一测98%，手指停在120拨号键上。",
                "visual_director": "真实测量现场，手腕、智能手表、指夹式血氧仪和紧张动作。",
            },
            is_cover=True,
        )

        self.assertGreaterEqual(score["cover_key"], 70)
        self.assertGreaterEqual(score["overall"], 72)

    def test_cover_semantic_score_blocks_invented_number(self) -> None:
        score = services.image_semantic_score(
            "智能手表显示93%，血氧仪显示98%，中间写5%误差。",
            {
                "topic": "智能手表测血氧？别信",
                "speech": "手表显示93%，血氧仪显示98%。",
                "visual_director": "智能手表与指夹式血氧仪同框。",
            },
            is_cover=True,
        )

        self.assertIn("5%", score["foreign_numeric_facts"])

    def test_semantic_issues_cannot_be_ignored(self) -> None:
        semantic_issue = {
            "level": "warn",
            "where": "scenes/s_01.png",
            "issue": "图片与主题/口播贴合偏弱。",
            "fix": "按本段口播重绘。",
        }
        visual_issue = {
            "level": "warn",
            "where": "scenes/s_01.png",
            "issue": "画面对比度偏低，显得太素。",
            "fix": "提高对比度。",
        }
        self.assertFalse(services.is_ignorable_image_quality_issue(semantic_issue))
        self.assertTrue(services.is_ignorable_image_quality_issue(visual_issue))

    def test_scene_prompt_can_use_multiple_audio_bound_information_elements(self) -> None:
        prompt = services.apply_unique_scene_callouts_to_prompt(
            "真实家庭门口，老人手停在门把手上，陌生人站在门外。",
            ["免费=最贵", "先别开门", "官方核实"],
        )
        self.assertIn("免费=最贵", prompt)
        self.assertIn("先别开门", prompt)
        self.assertIn("官方核实", prompt)
        self.assertIn("不以此为数量或文字边界", prompt)
        self.assertIn("本期主题与本镜口播原文", prompt)

    def test_only_key_scenes_use_information_anchors(self) -> None:
        anchors = [index for index in range(1, 11) if services.scene_should_use_information_anchor(index, 10)]
        self.assertEqual(anchors, [1, 3, 7, 10])

    def test_scene_information_anchor_prefers_current_audio_wording(self) -> None:
        entry = {
            "semantic_context": {
                "speech": "你花3000块搞个智能灯光秀，两年后它可能集体失效。",
            },
            "visual_decision": {
                "hook_words": ["智能家居真相"],
                "must_show": ["智能灯", "手机"],
            },
            "final_prompt": "年轻人看着失效的智能灯。",
        }
        selected = services.select_unique_scene_callouts(
            entry,
            topic="智能家居避坑",
            used=services.Counter(),
            index=1,
            total=10,
            count=1,
        )
        self.assertEqual(selected, ["3000块"])

    def test_audio_blueprint_changes_with_the_current_spoken_point(self) -> None:
        offline = services.audio_bound_visual_blueprint("App下线，灯和插座全部失去响应", "智能家居避坑")
        matter = services.audio_bound_visual_blueprint("通过Matter认证的产品超过3500款", "智能家居避坑")
        self.assertIn("服务离线", " ".join(offline["subjects"]))
        self.assertIn("认证", " ".join(matter["subjects"]))
        self.assertNotEqual(offline["action"], matter["action"])

    def test_ai_writing_does_not_receive_job_replacement_callouts(self) -> None:
        entry = {
            "semantic_context": {"speech": "AI写稿只用30秒，最后却花3小时改稿。"},
            "visual_decision": {"hook_words": []},
            "final_prompt": "职场人修改AI草稿。",
        }
        candidates = services.scene_callout_candidates_for_entry(entry, "AI写作效率陷阱")
        self.assertIn("3小时改稿", candidates)
        self.assertNotIn("AI抢工作", candidates)
        self.assertNotIn("效率翻倍", candidates)

    def test_ai_writing_blueprints_follow_the_specific_problem(self) -> None:
        facts = services.audio_bound_visual_blueprint("AI会编，把2023年浦东数据套到2024年深圳房价", "AI写作效率陷阱")
        logic = services.audio_bound_visual_blueprint("每句话都通顺，但逻辑跳到别处，只能重搭骨架", "AI写作效率陷阱")
        self.assertIn("冲突数据", " ".join(facts["subjects"]))
        self.assertIn("段落卡片", " ".join(logic["subjects"]))
        self.assertNotEqual(facts["evidence"], logic["evidence"])

    def test_topic_numbers_do_not_override_current_ai_writing_scene(self) -> None:
        blueprint = services.audio_bound_visual_blueprint(
            "AI最擅长说一堆正确的废话，产品卖点一个都没有",
            "AI省1小时，改稿花3小时",
        )
        self.assertIn("华丽空话", " ".join(blueprint["subjects"]))
        self.assertNotIn("计时器", " ".join(blueprint["subjects"]))

    def test_tts_removes_leading_stage_direction_but_keeps_spoken_text(self) -> None:
        spoken = services.strip_spoken_line_for_tts("（皱眉盯着屏幕，手指敲键盘）我让AI写了个总结。")
        self.assertEqual(spoken, "我让AI写了个总结。")

    def test_tts_keeps_sound_hook_but_removes_its_acting_note(self) -> None:
        spoken = services.strip_spoken_line_for_tts(
            "听——嘶——嘶——（模仿）这不是背景噪音，是耳机自己发出的电子噪音。"
        )
        self.assertEqual(spoken, "听——嘶——嘶——这不是背景噪音，是耳机自己发出的电子噪音。")

    def test_tts_removes_inline_performance_cue_without_dropping_speech(self) -> None:
        spoken = services.strip_spoken_line_for_tts("先看结果（停顿）再解释原因。")
        self.assertEqual(spoken, "先看结果再解释原因。")

    def test_scene_anchor_skips_standalone_visual_direction(self) -> None:
        group = [
            {"text": "皱眉盯着电脑屏幕，手指在键盘上狂敲"},
            {"text": "AI用30秒生成1000字，我却花3小时改稿"},
        ]
        anchor = services.select_key_audio_anchor(group, "口播原文：AI用30秒生成1000字，我却花3小时改稿")
        self.assertIn("3小时改稿", anchor)
        self.assertNotIn("皱眉", anchor)

    def test_scene_anchor_strips_malformed_visual_prefix(self) -> None:
        anchor = services.strip_leading_stage_direction("人物在白板画时间对比图）AI不是不能用，关键是只让它出草稿")
        self.assertEqual(anchor, "AI不是不能用，关键是只让它出草稿")

    def test_late_scene_prefers_actionable_spoken_advice(self) -> None:
        text = "那我是不是不该用AI了 不是 AI最好的用法不是交作业而是帮你出草稿 关键段落自己动手"
        anchor = services.actionable_audio_anchor(text)
        self.assertIn("最好的用法", anchor)
        self.assertIn("出草稿", anchor)

    def test_scene_without_short_text_still_binds_visual_information_to_audio(self) -> None:
        prompt = services.apply_unique_scene_callouts_to_prompt("真实客厅，灯光突然熄灭。", [])
        self.assertIn("当前主题与口播", prompt)
        self.assertIn("不借用其它镜头", prompt)

    def test_quality_uses_prompt_that_actually_generated_asset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scene_dir = root / "scenes"
            scene_dir.mkdir(parents=True)
            scene_path = scene_dir / "s_01.png"
            scene_path.write_bytes(b"image-placeholder")
            (scene_dir / "scene_prompts.json").write_text(
                json.dumps([{"prompt": "计划提示词"}], ensure_ascii=False),
                encoding="utf-8",
            )
            (scene_dir / "s_01.audit.json").write_text(
                json.dumps({"prompt": "真正发送给生图模型的提示词"}, ensure_ascii=False),
                encoding="utf-8",
            )

            def project_file(_project_id: int, relative: str) -> Path:
                return root / relative

            with (
                patch.object(services.storage, "project_dir", return_value=root),
                patch.object(services.storage, "project_file", side_effect=project_file),
                patch.object(services, "find_scene_image_paths", return_value=[scene_path]),
                patch.object(services, "_cover_output_paths", return_value=[]),
            ):
                prompt_map = services.image_prompt_context_map(1, "", "video")

            self.assertEqual(prompt_map["scenes/s_01.png"], "真正发送给生图模型的提示词")


class ContentAndLogTests(unittest.TestCase):
    def test_locked_topic_brief_removes_visual_and_production_notes(self) -> None:
        brief = """一句话选题：官网涨价，授权店降价。
【画面/分镜建议】
黑底白字，停三秒。
【口播正文】
同一时间，两个渠道价格方向相反。
【钩子】
这里要停顿。
制作批注
这一段不应进入写稿提示。
"""
        cleaned = services.sanitize_locked_topic_brief(brief, "官网涨价")
        self.assertIn("一句话选题", cleaned)
        self.assertIn("同一时间", cleaned)
        self.assertNotIn("黑底白字", cleaned)
        self.assertIn("这里要停顿", cleaned)
        self.assertNotIn("制作批注", cleaned)

    def test_locked_topic_brief_does_not_feed_embedded_full_draft_back_to_writer(self) -> None:
        brief = """一句话选题：官网涨价，授权店降价。
目标受众：准备换手机的人。
口播逐字稿（约 9 分钟）
【第 1 段】这是旧草稿，不应再次作为事实材料。
"""
        cleaned = services.sanitize_locked_topic_brief(brief, "官网涨价")
        self.assertIn("目标受众", cleaned)
        self.assertNotIn("旧草稿", cleaned)

    def test_complete_user_transcript_is_promoted_without_visual_notes(self) -> None:
        brief = """一句话选题
两个行业使用不同的时钟。

完整口播逐字稿（约 9 分钟）
【第 1 段】两张纸
【画面/分镜建议】
黑底放两张纸，停三秒。
【口播】
今天我想给你看两张纸。

左边有日期，右边没有。
【段末钩子】
镜头推近。
【第 2 段】时钟
【口播】
这两句话不矛盾，但付钱的人站在今天。

这里补足足够长度，用来确认完整逐字稿会被直接采用，而不是重新压缩成一句选题或混入画面说明。这里继续补足正文长度。
制作批注
这部分不进入口播。
"""

        content = services.extract_user_authored_script(brief, "两个时钟")

        self.assertIn("## 口播脚本", content)
        self.assertIn("【主播】今天我想给你看两张纸", content)
        self.assertIn("【主播】左边有日期，右边没有", content)
        self.assertIn("付钱的人站在今天", content)
        self.assertNotIn("黑底放两张纸", content)
        self.assertNotIn("制作批注", content)

    def test_complete_transcript_drives_concrete_research_subject(self) -> None:
        transcript = "Nebius 上调 H100 租金。黄仁勋谈英伟达芯片，倪军谈宁德时代全固态电池。"

        subject = services.transcript_research_subject(transcript)
        query, profile = services.topic_research_query(
            "10 月 1 日，和还要五年",
            f"核心检索对象：{subject}\n用户提供的完整素材稿：{transcript}",
        )

        self.assertIn("Nebius", query)
        self.assertIn("H100", query)
        self.assertNotEqual(profile.get("primary_entity"), "规则")

    def test_reference_url_is_required_when_research_sources_exist(self) -> None:
        content = """# 标题
## Meta
- 时长：60秒
## 口播脚本
【主播】这是完整口播。
## 重点字幕
- 重点
## 参考资料
- 标题写了一半
"""
        self.assertTrue(services.has_complete_production_content_structure(content, "video"))
        self.assertFalse(
            services.has_complete_production_content_structure(
                content,
                "video",
                require_reference_url=True,
            )
        )

    def test_rhythm_split_never_breaks_number_from_unit(self) -> None:
        line = "这款芯片采用2nm制程而且需要结合整条产业链成本变化才能解释清楚"
        parts = services.split_spoken_text_for_rhythm(line, limit=12)
        self.assertEqual(parts, [line])

    def test_unknown_bracket_label_is_editorial_marker(self) -> None:
        self.assertTrue(services.is_narrative_speaker_label("我把话说准一点"))
        self.assertTrue(services.is_narrative_speaker_label("常见的几种"))
        self.assertFalse(services.is_narrative_speaker_label("主播"))

    def test_visual_prompt_gate_does_not_invalidate_images_when_prompts_are_unchanged(self) -> None:
        before = {"passed": False, "score": 70, "issues": [{"issue": "weak"}]}
        after = {"passed": True, "score": 92, "issues": []}
        with (
            patch.object(services, "cached_stage_gate_result", return_value=None),
            patch.object(services, "evaluate_production_stage_gate", side_effect=[before, after]),
            patch.object(
                services,
                "repair_image_prompt_section",
                return_value={"changed": False, "content": "existing content"},
            ),
            patch.object(services, "save_stage_gate_result"),
        ):
            result = services.run_production_stage_gate(103, "visual_prompt_gate", auto_fix=True)

        self.assertTrue(result["passed"])
        self.assertFalse(result["content_changed"])

    def test_visual_prompt_change_keeps_existing_images_in_missing_only_job(self) -> None:
        self.assertFalse(
            services.stage_gate_change_requires_full_refresh("visual_prompt_gate", "images_missing", True)
        )
        self.assertFalse(
            services.stage_gate_change_requires_full_refresh("visual_prompt_gate", "covers_missing", True)
        )
        self.assertTrue(
            services.stage_gate_change_requires_full_refresh("content_gate", "images_missing", True)
        )
        self.assertTrue(services.stage_gate_change_requires_full_refresh("visual_prompt_gate", "images", True))

    def test_chatgpt_prompt_explicitly_requests_an_image(self) -> None:
        prompt = services.build_chatgpt_handoff_prompt("智能灯失效的真实家庭场景", "1920x1080", "scene")
        self.assertTrue(prompt.startswith("请直接调用 ChatGPT 的“生成图片”功能"))
        self.assertIn("不要整理或改写 Prompt", prompt)
        self.assertTrue(prompt.rstrip().endswith("请现在直接生成图片，只返回图片，不要输出任何文字或新的 Prompt。"))

    def test_chatgpt_scene_prompt_keeps_facts_but_drops_stale_layout_rules(self) -> None:
        source = (
            "本期主题：AI写作真的省时间吗。"
            "本镜口播原文：「它用30秒写了1000字，但我改稿花了3小时」。"
            "普通场景不生成文字；关键节点最多保留 1 个 2-8 字信息牌，固定放在上半区。"
            "电影级科技纪录片空间，冷蓝与暖金对比照明。"
        )

        prompt = services.build_chatgpt_handoff_prompt(source, "1920x1080", "scene")

        self.assertIn("它用30秒写了1000字，但我改稿花了3小时", prompt)
        self.assertIn("30秒", prompt)
        self.assertIn("1000字", prompt)
        self.assertIn("3小时", prompt)
        self.assertIn("文字策略：模型一次完成画面和文字", prompt)
        self.assertIn("字数和数量不设统一上限", prompt)
        self.assertIn("不要留下大片空白", prompt)
        self.assertIn("禁止乱码、截断", prompt)
        self.assertNotIn("由后期写入", prompt)
        self.assertNotIn("最多保留 1 个", prompt)
        self.assertNotIn("2-8 字", prompt)
        self.assertNotIn("固定放在上半区", prompt)
        self.assertNotIn("冷蓝与暖金", prompt)

    def test_balanced_scene_brief_separates_audio_segment_from_focus(self) -> None:
        prompt = services.balanced_scene_generation_brief(
            "旧场景规则：最多一个信息牌，固定上半区。",
            topic="AI写作是否真的省时间",
            speech="AI先生成草稿，随后进入反复改稿，最后总耗时反而更长。",
            anchor="30秒生成1000字，人工改稿3小时",
        )

        self.assertIn("当前完整口播：AI先生成草稿", prompt)
        self.assertIn("当前口播重点：30秒生成1000字，人工改稿3小时", prompt)
        self.assertNotIn("最多一个信息牌", prompt)
        self.assertNotIn("固定上半区", prompt)

    def test_balanced_scene_brief_preserves_selected_visual_concept(self) -> None:
        prompt = services.balanced_scene_generation_brief(
            "旧构图：统一办公室人物。",
            topic="AI写作耗时",
            speech="生成只要30秒，人工改稿却用了3小时。",
            anchor="30秒生成，3小时改稿",
            concept="一张被密集红色修订痕迹吞没的打印稿，与仍在计时的秒表形成真实物件证据",
        )

        self.assertIn("选定视觉概念：一张被密集红色修订痕迹吞没的打印稿", prompt)
        self.assertNotIn("统一办公室人物", prompt)

    def test_source_information_extracts_scene_relevant_evidence(self) -> None:
        references = [
            {
                "title": "折叠屏长期体验",
                "source": "测试资料",
                "url": "https://example.com/fold",
                "snippet": "过去几年，厂商持续让机身薄一毫米、折痕浅一丝，但很多升级仍停留在改善物理体感。",
            },
            {
                "title": "厨房家电选购",
                "source": "无关资料",
                "url": "https://example.com/kitchen",
                "snippet": "空气炸锅的加热效率与清洁方式。",
            },
        ]
        content = "# 折叠屏半年后悔\n\n- 核心观点: 屏幕折痕会影响长期体验。\n"

        candidates = services.source_information_candidates(
            51,
            topic="折叠屏手机，用半年就后悔？",
            content=content,
            references=references,
        )
        payload = services.scene_source_information_payload(
            51,
            topic="折叠屏手机，用半年就后悔？",
            speech="用上一个月，屏幕中间的凹槽越来越明显。",
            content=content,
            candidates=candidates,
        )

        self.assertTrue(payload["supporting_evidence"])
        self.assertIn("折痕", payload["supporting_evidence"][0])
        self.assertNotIn("一毫米", payload["supporting_evidence"][0])
        self.assertNotIn("空气炸锅", " ".join(payload["supporting_evidence"]))
        self.assertEqual(payload["grounding"], "references")

    def test_source_information_does_not_borrow_following_shot_evidence(self) -> None:
        content = """# 存储芯片多空交锋

## 口播脚本

【主播】花旗直接甩数据反驳，那些库存数字可能只是表象。
【主播】大摩拿13周库存吓人？你细算过三星停掉MLC NAND模组厂的事吗？
【主播】客户集中抢货，这批库存随后会快速回落。
【主播】这一轮库存，是停产前集中采购挤出来的假象。
【主播】下一段开始讨论企业级固态需求。
"""

        payload = services.scene_source_information_payload(
            83,
            topic="花旗驳斥大摩存储芯片见顶论",
            speech="花旗直接甩数据反驳，那些库存数字可能只是表象。大摩拿13周库存吓人？",
            content=content,
            candidates=[],
        )

        evidence = " ".join(payload["supporting_evidence"])
        self.assertEqual(payload["grounding"], "speech")
        self.assertEqual(evidence, "")
        self.assertIn("花旗直接甩数据反驳", payload["bound_speech"])

    def test_scene_information_copy_turns_speech_into_visible_conclusion(self) -> None:
        cases = {
            "倒车影像黑屏，你脖子都快拧断了结果它又亮了": "倒车影像黑屏",
            "你花三十万买的新车，车机芯片可能是好几年前": "新车配旧芯",
            "8155这颗被吹上天的芯片": "8155被吹上天",
            "降频之后别说3D动画，切换菜单都掉帧": "切换菜单都掉帧",
            "车机一个月至少重启一次，清理偷偷自启动的App": "一个月重启一次",
            "开车半年只用来导航、听歌、调空调": "只剩导航、听歌、调空调",
            "在屏幕里疯狂塞功能：3D地图、动态壁纸、应用商店": "功能越塞越多",
            "买车前别只看芯片型号，问清楚系统更新策略": "买车别只看芯片型号",
        }

        for speech, expected in cases.items():
            with self.subTest(speech=speech):
                self.assertEqual(services.scene_information_headline(speech), expected)

    def test_scene_information_fact_chips_extracts_visual_list_items(self) -> None:
        chips = services.scene_information_fact_chips(
            "在屏幕里疯狂塞功能：3D地图、动态壁纸、应用商店、点外卖、看视频、KTV。",
            headline="功能越塞越多",
        )

        self.assertEqual(chips, ["3D地图", "动态壁纸", "应用商店", "点外卖", "看视频", "KTV"])

    def test_dialogue_scene_anchors_skip_terminal_comment_prompt(self) -> None:
        content = """## 口播脚本
【主播】倒车影像黑屏，结果过了路口才亮。
【主播】三十万新车，装的可能是几年前的旧芯片。
【主播】功能越塞越多，后台进程先爆了。
【主播】夏天高温以后，切换菜单都掉帧。
【主播】买车前别只看芯片型号，还要问更新策略。
【主播】一个月至少重启一次，清理自启动应用。
【主播】花哨功能最后只剩导航、听歌、调空调。
【主播】评论区说说，你的车机最后怎么解决的？
"""

        indexes = services.select_dialogue_scene_anchor_indexes(content, "video", 6)
        lines = [
            services.strip_dialogue_speaker(item)
            for item in services.parse_dialogue_lines(content, "video")
            if services.clean_text(item)
        ]

        self.assertEqual(len(indexes), 6)
        self.assertFalse(any("评论区说说" in lines[index] for index in indexes))

    def test_source_information_does_not_match_unrelated_single_digit(self) -> None:
        score = services.source_information_match_score(
            "问界 M9 Ultimate 采用全新 6C3B 黑金涂装工艺",
            "降频之后别说3D动画，切换菜单都掉帧",
        )

        self.assertLess(score, 18)

    def test_reference_freshness_rejects_recent_repost_of_old_event(self) -> None:
        now = services.datetime(2026, 7, 24, tzinfo=services.timezone.utc)
        report = services.reference_freshness(
            {
                "title": "回顾2022年的旧发布会",
                "snippet": "这条内容再次整理当年的产品发布。",
                "published_date": "2026-07-23",
            },
            now=now,
        )

        self.assertEqual(report["age_days"], 1)
        self.assertEqual(report["status"], "historical")
        self.assertTrue(report["resurfaced_old_event"])
        rfc_report = services.reference_freshness(
            {"title": "当天新进展", "published_date": "Thu, 23 Jul 2026 23:37:05 GMT"},
            now=now,
        )
        self.assertEqual(rfc_report["age_days"], 0)
        self.assertEqual(rfc_report["status"], "live")

    def test_current_news_ranking_keeps_recent_dated_sources(self) -> None:
        today = services.datetime.now(services.timezone.utc)
        fresh_date = (today - services.timedelta(days=2)).date().isoformat()
        stale_date = (today - services.timedelta(days=90)).date().isoformat()

        ranked = services.prioritize_current_news_references(
            [
                {"title": "最新进展", "url": "https://example.test/fresh", "published_date": fresh_date, "score": 0.7},
                {"title": "三个月前的报道", "url": "https://example.test/stale", "published_date": stale_date, "score": 0.9},
                {"title": "没有日期", "url": "https://example.test/unknown", "score": 1.0},
            ]
        )

        self.assertEqual([item["url"] for item in ranked], ["https://example.test/fresh"])
        self.assertEqual(ranked[0]["freshness_status"], "live")

    def test_search_current_news_expands_from_week_to_month(self) -> None:
        today = services.datetime.now(services.timezone.utc)
        weekly = [
            {
                "title": "本周更新",
                "url": "https://example.test/week",
                "published_date": (today - services.timedelta(days=2)).date().isoformat(),
                "score": 0.9,
            }
        ]
        monthly = [
            {
                "title": "本月进展",
                "url": "https://example.test/month",
                "published_date": (today - services.timedelta(days=12)).date().isoformat(),
                "score": 0.8,
            }
        ]

        with patch.object(services, "search_deepseek_web", return_value=[]), patch.object(
            services, "search_grok2api_web", return_value=[]
        ), patch.object(
            services, "search_tavily", side_effect=[weekly, monthly]
        ) as search, patch.object(services, "search_google_news_rss", return_value=[]):
            result = services.search_current_news("AI 最新进展", 8)

        self.assertEqual([item["url"] for item in result], ["https://example.test/week", "https://example.test/month"])
        self.assertEqual(search.call_args_list[0].kwargs["time_range"], "week")
        self.assertEqual(search.call_args_list[1].kwargs["time_range"], "month")

    def test_search_current_news_prioritizes_deepseek_results(self) -> None:
        today = services.datetime.now(services.timezone.utc).date().isoformat()
        deepseek = [{"title": "DeepSeek发现", "url": "https://deepseek.test/a", "published_date": today, "source": "官方站点", "provider": "deepseek"}]
        grok = [{"title": "Grok发现", "url": "https://grok.test/a", "published_date": today, "source": "官方站点", "provider": "grok"}]
        tavily = [{"title": "辅助核验", "url": "https://tavily.test/a", "published_date": today, "source": "Tavily"}]

        with patch.object(services, "search_deepseek_web", return_value=deepseek) as deepseek_search, patch.object(
            services, "search_grok2api_web", return_value=grok
        ) as grok_search, patch.object(
            services, "search_tavily", return_value=tavily
        ), patch.object(services, "search_google_news_rss", return_value=[]):
            result = services.search_current_news("AI 最新进展", 8)

        self.assertEqual(result[0]["provider"], "deepseek")
        deepseek_search.assert_called_once_with("AI 最新进展", 8)
        grok_search.assert_not_called()

    def test_current_news_candidates_without_two_sources_are_capped(self) -> None:
        candidates = [
            {
                "title": "Kimi新模型开放",
                "brief": "新模型上线后的真实变化",
                "score": 4.8,
                "duplicate_penalty": 0.0,
            },
            {
                "title": "没有来源的旧话题",
                "brief": "泛泛讨论长期问题",
                "score": 4.9,
                "duplicate_penalty": 0.0,
            },
        ]
        references = [
            {
                "title": "Kimi新模型开放测试",
                "snippet": "Kimi新模型本周开放。",
                "url": "https://example.test/a",
                "published_date": "2026-07-23",
                "freshness_status": "live",
            },
            {
                "title": "Kimi新模型上线后用户增加",
                "snippet": "新模型上线引发关注。",
                "url": "https://example.test/b",
                "published_date": "2026-07-22",
                "freshness_status": "live",
            },
        ]

        scored = services.apply_current_news_candidate_scores(candidates, references)

        self.assertEqual(scored[0]["title"], "Kimi新模型开放")
        self.assertGreaterEqual(scored[0]["news_evidence_count"], 2)
        unsupported = next(item for item in scored if item["title"] == "没有来源的旧话题")
        self.assertLessEqual(unsupported["score"], 3.0)

    def test_grok_evidence_controls_topic_readiness_and_order(self) -> None:
        today = services.datetime.now(services.timezone.utc).date().isoformat()
        candidates = [
            {"title": "DeepSeek V4 Pro正式上线", "brief": "新模型正式上线后的功能变化", "score": 4.5},
            {"title": "某手机系统更新", "brief": "手机系统更新后的功能变化", "score": 4.8},
        ]
        references = [
            {
                "title": "DeepSeek V4 Pro正式上线",
                "snippet": "新模型正式上线并公布功能变化。",
                "url": "https://grok-source.test/deepseek",
                "source": "官方文档",
                "provider": "deepseek",
                "published_date": today,
                "age_days": 0,
            },
            {
                "title": "DeepSeek V4 Pro发布说明",
                "snippet": "发布说明确认模型功能变化。",
                "url": "https://verify.test/deepseek",
                "source": "Tavily",
                "provider": "tavily",
                "published_date": today,
                "age_days": 0,
            },
            {
                "title": "某手机系统更新",
                "snippet": "手机系统更新带来功能变化。",
                "url": "https://verify.test/phone",
                "source": "Tavily",
                "provider": "tavily",
                "published_date": today,
                "age_days": 0,
            },
        ]

        scored = services.apply_current_news_candidate_scores(candidates, references)

        self.assertEqual(scored[0]["title"], "DeepSeek V4 Pro正式上线")
        self.assertEqual(scored[0]["deepseek_evidence_count"], 1)
        phone = next(item for item in scored if item["title"] == "某手机系统更新")
        self.assertIn("未命中DeepSeek主检索", phone["quality_issues"])
        self.assertNotEqual(phone["readiness"], "strong")

    def test_channel_news_filter_does_not_match_ai_inside_english_words(self) -> None:
        filtered = services.filter_current_news_references_for_channel(
            [
                {"title": "AI model launches this week", "snippet": "A new AI assistant is available."},
                {"title": "Manufacturing quarterly earnings", "snippet": "A factory reported quarterly results."},
            ],
            ["AI", "人工智能"],
        )

        self.assertEqual([item["title"] for item in filtered], ["AI model launches this week"])

    def test_topic_candidate_quality_exposes_sources_freshness_and_readiness(self) -> None:
        today = services.datetime.now(services.timezone.utc)
        published = (today - services.timedelta(days=1)).date().isoformat()
        candidates = [{
            "title": "Kimi新版本本周开放测试",
            "brief": "对比新版本上线前后的手机使用成本和功能变化",
            "score": 4.4,
            "duplicate_penalty": 0.0,
        }]
        references = [
            {
                "title": "Kimi新版本本周开放测试",
                "snippet": "新版本已经上线并开放测试。",
                "url": "https://source-a.test/news",
                "published_date": published,
                "age_days": 1,
            },
            {
                "title": "Kimi更新带来新的手机功能",
                "snippet": "报告对比更新前后的用户体验。",
                "url": "https://source-b.test/report",
                "published_date": published,
                "age_days": 1,
            },
        ]

        result = services.apply_current_news_candidate_scores(candidates, references)[0]

        self.assertEqual(result["independent_source_count"], 2)
        self.assertEqual(result["latest_age_days"], 1)
        self.assertEqual(result["readiness"], "strong")
        self.assertIn("visual_potential", result["quality_dimensions"])

    def test_topic_mining_focuses_split_channel_hint_into_focused_queries(self) -> None:
        focuses = services._topic_mining_focuses(
            {"topic_mining_hint": "AI工具、智能硬件、手机数码、效率工具、消费电子"},
            "",
            "news",
        )

        self.assertEqual(focuses[:3], ["AI工具", "智能硬件", "手机数码"])
        self.assertLessEqual(len(focuses), 8)

    def test_topic_mining_focuses_shorten_natural_language_direction(self) -> None:
        focuses = services._topic_mining_focuses(
            {"topic_mining_hint": "AI工具、智能硬件"},
            "最近一周普通人能直接感知的AI产品变化，优先价格、功能或使用成本",
            "news",
        )

        self.assertEqual(focuses, ["AI产品 价格", "AI产品 功能", "AI产品 使用成本"])

    def test_prompted_topic_mining_does_not_fill_missing_news_with_generic_topics(self) -> None:
        with patch.object(services, "_mine_topic_reference_pool", return_value=([], ["AI产品 最新进展"])), patch.object(
            services, "runtime_env", return_value={}
        ):
            result = services.mine_channel_topic(
                {"key": "", "name": "科技情报站", "topic_mining_hint": "AI工具、智能硬件"},
                "news",
                "AI产品最近一周的新变化",
                6,
            )

        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["quality_summary"]["returned_count"], 0)
        self.assertIn("资料不足", result["quality_summary"]["message"])

    def test_google_news_rss_keeps_publisher_and_date(self) -> None:
        xml = b"""<?xml version='1.0' encoding='UTF-8'?>
        <rss><channel><item><title>AI product update - Example News</title>
        <link>https://news.google.com/rss/articles/example</link>
        <pubDate>Sat, 01 Aug 2026 08:00:00 GMT</pubDate>
        <source>Example News</source></item></channel></rss>"""
        response = MagicMock()
        response.__enter__.return_value.read.return_value = xml
        response.__exit__.return_value = False
        with patch.object(services.urllib.request, "urlopen", return_value=response):
            result = services.search_google_news_rss("AI update", 3)

        self.assertEqual(result[0]["source"], "Example News")
        self.assertEqual(result[0]["published_date"], "Sat, 01 Aug 2026 08:00:00 GMT")

    def test_diverse_topic_selection_avoids_near_duplicate_titles(self) -> None:
        candidates = [
            {"title": "手机AI助手本周上线新功能", "rank_score": 4.8},
            {"title": "手机AI助手新功能本周上线", "rank_score": 4.7},
            {"title": "智能汽车召回规则发生变化", "rank_score": 4.5},
        ]

        selected = services._select_diverse_topic_candidates(candidates, 2)

        self.assertEqual(selected[0]["title"], "手机AI助手本周上线新功能")
        self.assertEqual(selected[1]["title"], "智能汽车召回规则发生变化")

    def test_scene_information_ocr_requires_the_main_conclusion(self) -> None:
        prompt = (
            "画面主信息：必须把「切换菜单都掉帧」作为画面中的最大信息层，原样、清晰、醒目呈现。"
            "必须呈现的事实词：降频。"
        )

        missing = services.scene_information_ocr_report("降频中 23.0°", prompt)
        passed = services.scene_information_ocr_report("降频之后，切换菜单都掉帧", prompt)

        self.assertFalse(missing["passed"])
        self.assertTrue(passed["passed"])

    def test_scene_short_hook_is_a_required_ocr_target(self) -> None:
        prompt = (
            "当前完整口播：配置看着很高，真正拖后腿的却是刹车。"
            "画面短钩子：必须逐字、完整、清晰写入「高配置，低刹车」；"
            "与主体分区，不得删减、改写、截断或乱码。"
        )

        self.assertEqual(services.required_scene_information_text(prompt), ["高配置，低刹车"])
        self.assertFalse(services.scene_information_ocr_report("豪华配置", prompt)["passed"])
        self.assertTrue(services.scene_information_ocr_report("高配置，低刹车", prompt)["passed"])

    def test_scene_text_policy_uses_project132_native_text_contract(self) -> None:
        policy = services.scene_text_overlay_policy(
            "同一台车，配置堆满了，最后却卡在刹车上。",
            "evidence",
            [],
        )

        self.assertIn("根据当前口播自行选择", policy)
        self.assertIn("不限制为固定短钩子", policy)
        self.assertNotIn("8至16字", policy)

    def test_compacted_scene_prompt_keeps_exact_short_hook(self) -> None:
        prompt = (
            "本期主题：豪华车的最后一道安全题。\n"
            "当前完整口播：同一台车，配置堆满了，最后却卡在刹车上。\n"
            "本镜画面：测试台上的刹车卡钳与制动盘正在接受压力测试。\n"
            "画面短钩子：必须逐字、完整、清晰写入「配置堆满，刹车卡住」；"
            "短钩子与主体分区，不得删减、改写、截断或乱码。"
        )

        outbound = services.lightweight_scene_model_prompt(prompt, max_chars=680)
        handoff = services.build_chatgpt_handoff_prompt(prompt, "2560x1440", "scene")

        self.assertIn("同一台车，配置堆满了，最后却卡在刹车上", outbound)
        self.assertIn("同一台车，配置堆满了，最后却卡在刹车上", handoff)
        self.assertIn("原生画面文字", handoff)
        self.assertNotIn("画面短钩子", handoff)

    def test_scene_information_ocr_rejects_truncated_headline(self) -> None:
        prompt = "画面主信息：必须把「手机App正在偷听聊天」作为画面中的最大信息层，原样、清晰、醒目呈现。"

        result = services.scene_information_ocr_report("手机App正在偷听", prompt)

        self.assertFalse(result["passed"])
        self.assertLess(result["headline_completeness"]["coverage"], 0.90)
        self.assertTrue(result["headline_completeness"]["missing_fragments"])

    def test_visual_text_completeness_accepts_spacing_but_rejects_missing_suffix(self) -> None:
        complete = services.visual_text_completeness_report("30秒写完1000字", "30 秒 写完 1000 字")
        truncated = services.visual_text_completeness_report("30秒写完1000字", "30秒写完")

        self.assertTrue(complete["passed"])
        self.assertFalse(truncated["passed"])
        self.assertLess(truncated["coverage"], 0.90)

    def test_scene_typography_is_sent_to_image_model_instead_of_reserved_for_post(self) -> None:
        prompt = (
            "本期主题：手机App在偷听你聊天。当前完整口播：它会利用权限和广告画像。"
            "画面主信息：必须把「不是偷听，是画像」作为画面中的最大信息层，原样、清晰、醒目呈现。"
            "必须呈现的事实词：麦克风权限、广告画像。"
        )
        payload = services.scene_exact_typography_payload(prompt)
        reserved = services.reserve_exact_typography_area(prompt, "scene", payload)

        self.assertEqual(payload["headline"], "不是偷听，是画像")
        self.assertEqual(payload["fact_chips"], ["麦克风权限", "广告画像"])
        self.assertIn("AI原生画面文字", reserved)
        self.assertIn("不是偷听，是画像", reserved)
        self.assertIn("麦克风权限", reserved)
        self.assertIn("广告画像", reserved)
        self.assertIn("不设统一字数上限", reserved)
        self.assertNotIn("由后期准确写入", reserved)

    def test_scene_prompt_requests_native_text_without_a_headline_payload(self) -> None:
        prompt = (
            "本期主题：无线充电为什么发热。"
            "当前完整口播：线圈没有对准时，更多能量会变成热。"
            "选定视觉概念：透明拆解台上，两组错位线圈与温度变化形成对照。"
        )

        reserved = services.reserve_exact_typography_area(prompt, "scene", {})
        handoff = services.build_chatgpt_handoff_prompt(prompt, "2560x1440", "scene")

        self.assertIn("AI原生画面文字", reserved)
        self.assertIn("根据当前完整口播自行提炼", reserved)
        self.assertIn("原生画面文字", handoff)
        self.assertIn("模型一次完成画面和文字", handoff)
        self.assertNotIn("AI底图不画字", handoff)

    def test_scene_outbound_prompt_keeps_native_text_and_full_fact_relationship(self) -> None:
        prompt = services.balanced_scene_generation_brief(
            "",
            topic="AI 改稿时间",
            speech="它用30秒写完1000字，但人工改稿花了3小时。",
            source_information={
                "bound_speech": "它用30秒写完1000字，但人工改稿花了3小时。",
                "visual_copy": {
                    "headline": "到底省没省",
                    "fact_chips": ["30秒", "1000字", "3小时"],
                },
                "visual_relation": "写作时间与改稿时间形成强烈反差",
            },
        )
        payload = services.image_exact_typography_payload(prompt, "scene")
        reserved = services.reserve_exact_typography_area(prompt, "scene", payload)
        outbound = services.lightweight_scene_model_prompt(reserved, max_chars=680)

        self.assertEqual(payload["headline"], "到底省没省")
        self.assertEqual(payload["fact_chips"], ["30秒", "1000字", "3小时"])
        self.assertIn("原生画面文字", outbound)
        self.assertIn("到底省没省", outbound)
        self.assertIn("30秒", outbound)
        self.assertIn("1000字", outbound)
        self.assertIn("3小时", outbound)
        self.assertIn("模型一次完成画面和文字", outbound)
        self.assertNotIn("由后期写入", outbound)

    def test_cover_model_prompt_keeps_title_for_native_image_generation(self) -> None:
        source = (
            "封面主标题必须原样清晰写成「中国AI杀进美国，比GPT便宜10倍」，不得省略、改写或缩成角落小字。"
            "封面短副标题必须原样清晰写成「成本只有美国模型的1/10，性能还接近」，与主标题形成结论反转。"
            "主题：中国AI杀进美国，比GPT便宜10倍？。真实科技办公室摄影。"
        )
        payload = services.image_exact_typography_payload(source, "cover")

        reserved = services.reserve_exact_typography_area(source, "cover", payload)

        self.assertEqual(payload["headline"], "中国AI杀进美国，比GPT便宜10倍")
        self.assertIn("封面主标题必须原样", reserved)
        self.assertIn("封面短副标题必须原样", reserved)
        self.assertIn("真实科技办公室摄影", reserved)
        self.assertIn("AI原生封面文字", reserved)
        self.assertIn("主标题必须是缩略图状态下仍清晰可读的最大视觉块", reserved)
        self.assertNotIn("由后期准确写入", reserved)
        self.assertNotIn("AI 底图不得生成任何可读", reserved)

    def test_balanced_scene_brief_preserves_source_information_structure(self) -> None:
        source = (
            "主题：折叠屏长期体验。口播原文：屏幕中间的凹槽越来越明显。"
            "本镜信息任务：以折痕变化作为主信息。"
            "来源支撑信息：厂商持续改善折痕，但升级仍停留在物理体感。"
            "可视化关系：用新机与长期使用后的屏幕反光做前后对比。"
        )

        prompt = services.balanced_scene_generation_brief(source)

        self.assertIn("来源支撑信息：", prompt)
        self.assertIn("厂商持续改善折痕", prompt)
        self.assertIn("建议的信息结构：", prompt)
        self.assertIn("前后对比", prompt)
        self.assertIn("关键证据、反转和结论镜头优先采用信息主导构图", prompt)

    def test_scene_prompt_speech_anchor_stops_before_visual_rules(self) -> None:
        source = (
            "主题：折叠屏手机，用半年就后悔？，口播原文：你以为是“有一点线”，屏幕中间的凹槽越来越明显，"
            "主体：折叠屏手机与侧光，动作：手指划过折痕，冲突：息屏仍可见。"
        )

        speech = services.scene_prompt_speech_anchor(source)
        balanced = services.balanced_scene_generation_brief(source)

        self.assertEqual(speech, "你以为是“有一点线”，屏幕中间的凹槽越来越明显")
        self.assertNotIn("主体", speech)
        self.assertIn("本期主题：折叠屏手机，用半年就后悔？", balanced)
        self.assertIn("当前完整口播：你以为是“有一点线”", balanced)

    def test_authoritative_scene_speech_replaces_stale_prompt_narration_once(self) -> None:
        stale_prompt = (
            "本期主题：旧主题\n"
            "当前完整口播：旧项目里的人物拿着手机查看智能家居。\n"
            "本镜禁用手机：旧规则。\n"
            "主体：手机、智能灯和控制屏。"
        )
        current_speech = "制动踏板支架在紧急刹车测试中断裂，驾驶员正在检查机械断点。"

        compiled = services.balanced_scene_generation_brief(
            stale_prompt,
            topic="车辆制动安全测试",
            speech=current_speech,
        )
        compiled_again = services.enforce_scene_prop_contract(
            compiled,
            current_speech,
            "vehicle_mobility",
        )

        self.assertEqual(compiled_again.count("当前完整口播："), 1)
        self.assertIn(f"当前完整口播：{current_speech}", compiled_again)
        self.assertNotIn("旧项目里的人物", compiled_again)
        self.assertNotIn("智能家居", compiled_again)
        self.assertEqual(compiled_again.count("本镜禁用手机："), 1)
        self.assertEqual(compiled_again.count("车辆题材主体约束："), 1)

    def test_vehicle_brake_event_contract_keeps_episode_subject(self) -> None:
        content = (
            "尊界V800豪华MPV在连续紧急制动测试中，刹车踏板支架断裂，"
            "踏板脱落，制动距离明显增加。"
        )
        prompt = services.enforce_episode_event_visual_contract(
            "机械剖面展示结构受力设计缺陷。画面原生文字：软件可以每周OTA修复。",
            topic="断裂的尊界",
            content=content,
            speech="排除装配疏忽，指向结构受力设计和材料强度问题。",
            topic_type="vehicle_mobility",
        )

        self.assertIn("尊界V800豪华MPV", prompt)
        self.assertIn("刹车踏板支架", prompt)
        self.assertIn("驾驶舱脚部", prompt)
        self.assertIn("变速箱", prompt)
        self.assertIn("禁止复制成多个近似分格", prompt)
        self.assertNotIn("软件可以每周OTA修复", prompt)

    def test_vehicle_brake_event_contract_is_not_applied_to_other_topics(self) -> None:
        with patch.object(
            services,
            "topic_entity_profile",
            return_value={"primary_entity": "电视", "secondary_entities": ["开机广告"]},
        ):
            prompt = services.enforce_episode_event_visual_contract(
                "真实客厅里的电视正在播放开机广告。",
                topic="电视开机广告",
                content="电视开机后出现广告。",
                speech="用户等待广告结束。",
                topic_type="consumer_product",
            )

        self.assertNotIn("刹车踏板支架", prompt)
        self.assertIn("整期事件锁定", prompt)
        self.assertIn("核心实体是电视", prompt)
        self.assertIn("同一事件", prompt)

    def test_episode_event_contract_survives_final_provider_compaction(self) -> None:
        source = (
            "主体：检测现场。动作：分析结构受力。\n"
            "整期事件锁定：本期讲的是尊界V800豪华MPV紧急制动时刹车踏板支架断裂；"
            "后续镜头不得用变速箱、齿轮箱或通用机械替代刹车踏板支架。"
        )

        outbound = services.build_chatgpt_handoff_prompt(source, "2560x1440", "scene")

        self.assertIn("整期事件锁定", outbound)
        self.assertIn("尊界V800", outbound)
        self.assertIn("刹车踏板支架", outbound)
        self.assertIn("变速箱", outbound)

    def test_scene_semantic_context_uses_audio_anchor_instead_of_stale_timeline_text(self) -> None:
        context = services.normalize_scene_semantic_context(
            {
                "topic": "智能冰箱让你多花钱",
                "audio_anchor": "一段时间电费多出300多",
                "speech": "你以为省菜钱，最后评论区晒出来",
            }
        )

        self.assertEqual(context["speech"], "一段时间电费多出300多")
        self.assertEqual(context["timeline_speech"], "你以为省菜钱，最后评论区晒出来")
        self.assertTrue(context["speech_rebound_to_audio_anchor"])

    def test_current_audio_number_is_allowed_even_when_fact_registry_missed_it(self) -> None:
        context = {
            "audio_anchor": "一段时间电费多出300多",
            "speech": "一段时间电费多出300多",
            "fact_registry_enforced": True,
            "allowed_numeric_facts": [],
        }

        foreign = services.foreign_scene_numeric_facts("电费单上圈出300+", context)

        self.assertEqual(foreign, [])

    def test_prompt_scaffolding_one_second_is_not_treated_as_scene_fact(self) -> None:
        context = {
            "audio_anchor": "月薪一万请客服",
            "speech": "月薪一万请客服",
            "fact_registry_enforced": True,
            "allowed_numeric_facts": ["10000"],
        }

        foreign = services.foreign_scene_numeric_facts(
            "观众1秒必须看懂：月薪一万请客服；一秒抓人的真实办公场景。",
            context,
        )

        self.assertEqual(foreign, [])

    def test_foreign_scene_number_is_generalized_before_generation(self) -> None:
        context = {
            "audio_anchor": "月薪一万请客服",
            "speech": "月薪一万请客服",
            "fact_registry_enforced": True,
            "allowed_numeric_facts": ["10000"],
        }

        repaired, removed = services.repair_foreign_scene_numeric_facts(
            "观众1秒必须看懂：月薪一万请客服。选定视觉概念：三年AI定制合同。",
            context,
        )

        self.assertEqual(removed, ["3年"])
        self.assertIn("观众必须立即看懂", repaired)
        self.assertIn("长期AI定制合同", repaired)
        self.assertEqual(services.foreign_scene_numeric_facts(repaired, context), [])

    def test_channel_hex_colors_are_not_treated_as_scene_facts(self) -> None:
        context = {
            "audio_anchor": "这次涨价到底值不值",
            "speech": "这次涨价到底值不值",
            "fact_registry_enforced": True,
            "allowed_numeric_facts": ["1000元"],
        }

        foreign = services.foreign_scene_numeric_facts(
            "本期主题：手机涨1000元。炭黑 #24211D，靛蓝 #405A93。",
            context,
        )

        self.assertEqual(foreign, [])

    def test_numeric_repair_never_replaces_suffix_of_larger_number(self) -> None:
        with (
            patch.object(services, "foreign_scene_numeric_facts", return_value=["0元"]),
            patch.object(services, "extract_numeric_fact_tokens", return_value=["0元"]),
        ):
            repaired, removed = services.repair_foreign_scene_numeric_facts(
                "小米18涨1000元",
                {},
            )

        self.assertEqual(removed, ["0元"])
        self.assertEqual(repaired, "小米18涨1000元")

    def test_ai_teacher_concrete_scene_is_kept_as_the_visual_concept(self) -> None:
        context = {
            "topic": "智能冰箱让你多花钱",
            "audio_anchor": "一段时间电费多出300多",
            "speech": "一段时间电费多出300多",
        }
        concrete = (
            "特写，一只手拿着电费单，手指圈出300+，旁边智能冰箱屏幕显示电费条形图，"
            "背景为真实厨房台面，自然光，浅景深，焦点在电费单，真实生活摄影质感"
        )

        grounding = services.ai_teacher_scene_grounding_report(
            concrete,
            concept="电费单与冰箱屏幕形成费用对比",
            semantic_context=context,
            active_topic_type="general_editorial",
        )
        prompt = services.grounded_ai_teacher_scene_prompt(
            concrete,
            topic=context["topic"],
            semantic_context=context,
        )

        self.assertTrue(grounding["accepted"])
        self.assertIn("选定视觉概念：特写，一只手拿着电费单", prompt)
        self.assertIn("当前完整口播：一段时间电费多出300多", prompt)
        self.assertNotIn("牛肝菌", prompt)

    def test_balanced_scene_brief_locks_chinese_percentages_and_emergency_number(self) -> None:
        prompt = services.balanced_scene_generation_brief(
            "旧构图规则。",
            topic="智能手表测血氧？别信",
            speech="手表说我血氧百分之九十三，120就差按下去，医用血氧仪一测百分之九十八。",
            anchor="手表93%，医用仪器98%，手指停在120拨号键上",
        )

        self.assertIn("不可改错的数字事实", prompt)
        self.assertIn("93%", prompt)
        self.assertIn("98%", prompt)
        self.assertIn("120", prompt)
        self.assertIn("具体数字必须来自当前口播", prompt)

    def test_wearable_blueprint_prefers_specific_experiment_over_emergency_number(self) -> None:
        blueprint = services.audio_bound_visual_blueprint(
            "我都差点打120了，说明书却写仅供参考；随后用三块不同品牌手表各测10次。",
            "智能手表测血氧？别信",
        )

        self.assertIn("三块不同外观的无品牌手表", blueprint["subjects"])
        self.assertIn("重复测量", blueprint["evidence"])
        self.assertNotIn("拨号键", " ".join(blueprint["subjects"]))

    def test_audio_bound_semantic_prompt_keeps_concept_open_but_evidence_specific(self) -> None:
        prompt = services.audio_bound_semantic_scene_prompt(
            "智能手表测血氧？别信",
            "晚上睡觉连续监测时，血氧趋势曲线在某个时段持续下降。",
            "连续趋势比单个数字更有参考价值",
        )

        self.assertIn("睡眠中的佩戴者手腕", prompt)
        self.assertIn("完整夜间时间轴", prompt)
        self.assertIn("创作自由：画面风格、人物或物件、场景、构图", prompt)
        self.assertNotIn("扁平信息图", prompt)

    def test_wearable_advice_prompt_does_not_invite_invented_readings(self) -> None:
        prompt = services.audio_bound_semantic_scene_prompt(
            "智能手表测血氧？别信",
            "单次数值不要信，静息时复测，运动出汗时直接无视，再用医用指夹式血氧仪核对。",
            "单次数值不要信，连续趋势可以看",
        )

        self.assertIn("不补造具体血氧百分比", prompt)
        self.assertIn("未在口播出现的读数不写进任何设备屏幕", prompt)

    def test_numeric_fact_alignment_ignores_incidental_keypad_digits(self) -> None:
        alignment = services.numeric_fact_alignment(
            ["93%", "98%", "120"],
            ["93%", "98%", "120", "2", "3", "4", "5", "8"],
        )

        self.assertEqual(alignment["coverage_score"], 100)
        self.assertEqual(alignment["matched"], ["120", "93%", "98%"])
        self.assertEqual(alignment["missing"], [])

    def test_image_audit_ignores_lexical_once_but_keeps_explicit_measurement_count(self) -> None:
        lexical = services.image_audit_expected_numeric_facts(
            "曲线中一次持续下降的时段，完整夜间趋势共同支撑判断。"
        )
        explicit = services.image_audit_expected_numeric_facts(
            "当前口播：同一姿势各测三次。不可改错的数字事实：3次 创作边界：只服务当前口播。"
        )

        self.assertNotIn("1次", lexical)
        self.assertIn("3次", explicit)

    def test_numeric_fact_extraction_preserves_approximate_chinese_amounts(self) -> None:
        facts = {
            services.normalized_numeric_fact(item)
            for item in services.extract_numeric_fact_tokens("几十块的血氧仪，比几千块的手表更可靠，各测三次。")
        }

        self.assertIn("几十块", facts)
        self.assertIn("几千块", facts)
        self.assertIn("3次", facts)
        self.assertNotIn("10块", facts)
        self.assertNotIn("1000块", facts)

    def test_numeric_fact_extraction_recognizes_technical_parameters(self) -> None:
        facts = {
            services.normalized_numeric_fact(item)
            for item in services.extract_numeric_fact_tokens(
                "20000mAh容量在3.7V下储能，升压到5V后额定容量约12000毫安。"
            )
        }

        self.assertIn("20000mAh", facts)
        self.assertIn("3.7V", facts)
        self.assertIn("5V", facts)
        self.assertIn("12000毫安", facts)

    def test_verified_technical_fact_allows_equivalent_unitless_scene_number(self) -> None:
        context = {
            "speech": "看清楚，20000只是标称容量。",
            "fact_registry_enforced": True,
            "allowed_numeric_facts": ["20000mAh"],
        }

        foreign = services.foreign_scene_numeric_facts(
            "充电宝背面突出20000并指向容量参数。",
            context,
        )

        self.assertEqual(foreign, [])

    def test_scaled_numeric_fact_matches_full_number(self) -> None:
        context = {
            "speech": "这款标称2万毫安。",
            "fact_registry_enforced": True,
            "allowed_numeric_facts": ["2万毫安"],
        }

        foreign = services.foreign_scene_numeric_facts("参数牌写20000mAh。", context)

        self.assertEqual(foreign, [])

    def test_visual_fragment_truncation_does_not_split_technical_number(self) -> None:
        source = "人物翻转充电宝并指向额定容量，商家为什么标20000mAh而不是额定容量"
        cut_inside_number = source.index("20000mAh") + 3

        truncated = services.truncate_visual_fragment(source, cut_inside_number)

        self.assertNotIn("标200", truncated)
        self.assertNotRegex(truncated, r"\d+$")

    def test_numeric_fact_extraction_does_not_treat_piece_classifier_as_money(self) -> None:
        facts = [
            services.normalized_numeric_fact(item)
            for item in services.extract_numeric_fact_tokens("没有一块表能做到，但测试费用只要一块钱。")
        ]

        self.assertIn("1块", facts)
        self.assertEqual(facts.count("1块"), 1)

    def test_ocr_prompt_overlap_matches_short_chinese_semantic_fragments(self) -> None:
        score = services.ocr_prompt_text_overlap_score(
            "血氧饱和度 整夜趋势 23:00 05:00",
            "晚上睡觉连续监测，整夜血氧趋势曲线出现持续下降。",
        )

        self.assertGreaterEqual(score, 22)

    def test_scene_facts_do_not_inherit_unspoken_numbers_from_topic(self) -> None:
        prompt = services.balanced_scene_generation_brief(
            "画面任务：展示逻辑断裂。",
            topic="AI生成30秒，改稿3小时",
            speech="每句话单独看都通顺，但连起来没有逻辑。",
            anchor="句子通顺，逻辑断裂",
        )

        self.assertNotIn("不可改错的数字事实", prompt)

    def test_foreign_scene_numbers_reject_next_scene_contamination(self) -> None:
        foreign = services.foreign_scene_numeric_facts(
            "白板显示自己写2小时，AI生成0.5小时加改稿2.5小时",
            {"speech": "搭骨架比从零开始写更累", "audio_anchor": "重新搭建文章骨架"},
        )

        self.assertIn("2小时", foreign)
        self.assertIn("0.5小时", foreign)

    def test_visual_object_counts_are_not_treated_as_foreign_facts(self) -> None:
        foreign = services.foreign_scene_numeric_facts(
            "四张段落卡片分成三块拼图，每张只写四字短句",
            {"speech": "把文章骨架全部推翻后重新排列", "audio_anchor": "重新搭文章骨架"},
        )

        self.assertEqual(foreign, [])

    def test_visual_concept_carriers_detect_only_dominant_repeated_media(self) -> None:
        phone = services.visual_concept_carriers("手机屏幕特写，手指圈出错误数据")
        paper = services.visual_concept_carriers("打印稿旁边放着三张段落纸卡")

        self.assertEqual(phone, {"phone"})
        self.assertEqual(paper, set())

    def test_ai_visual_director_requests_two_distinct_concepts_without_old_text_cap(self) -> None:
        messages = services.compose_image_prompt_teacher_messages(
            {"id": 0, "topic_name": "AI写作耗时", "template": "科技情报站"},
            {"name": "科技情报站"},
            "scene",
            [{"target": "s_01.png", "semantic_context": {"speech": "30秒生成，3小时改稿"}}],
        )
        system = messages[0]["content"]
        payload = json.loads(messages[1]["content"])

        self.assertIn("A、B 两个", system)
        self.assertIn("concepts", payload["output_schema"]["prompts"][0])
        self.assertNotIn("最多一个", system)
        self.assertNotIn("上半区信息牌", system)

    def test_chatgpt_image_mode_is_selected_before_prompt(self) -> None:
        class FakeLocator:
            def __init__(self, count: int = 0) -> None:
                self._count = count
                self.clicked = False

            def count(self) -> int:
                return self._count

            def nth(self, _index: int):
                return self

            def is_visible(self, timeout: int = 0) -> bool:
                return bool(self._count)

            def is_enabled(self, timeout: int = 0) -> bool:
                return bool(self._count)

            def click(self, timeout: int = 0) -> None:
                self.clicked = True

            def filter(self, **_kwargs):
                return self

        class FakePage:
            def __init__(self) -> None:
                self.image_button = FakeLocator(1)
                self.empty = FakeLocator(0)

            def get_by_role(self, role: str, **_kwargs):
                return self.image_button if role == "button" else self.empty

            def locator(self, _selector: str):
                return self.empty

            def wait_for_timeout(self, _timeout: int) -> None:
                return None

        page = FakePage()
        logs: list[str] = []
        activated = services._activate_chatgpt_image_mode(page, log=logs.append)

        self.assertTrue(activated)
        self.assertTrue(page.image_button.clicked)
        self.assertIn("先选择", logs[0])

    def test_old_job_cannot_overwrite_new_job_log(self) -> None:
        runtime = services.JobRuntime()
        old_snapshot = {"id": "job-old"}
        with (
            patch.object(services.storage, "load_latest_job", return_value={"id": "job-new"}),
            patch.object(services.storage, "save_latest_job") as save_latest,
        ):
            runtime._flush(1, old_snapshot, ["old log"], [], "images")

        save_latest.assert_not_called()

    def test_late_progress_callback_cannot_revive_cancelled_job(self) -> None:
        runtime = services.JobRuntime()
        snapshot = {"id": "job-current", "status": "cancelled", "running": False}
        cancelled = {
            "id": "job-current",
            "status": "cancelled",
            "running": False,
            "finished_at": 123.0,
        }
        with (
            patch.object(services.storage, "load_latest_job", return_value=cancelled),
            patch.object(services.storage, "save_latest_job") as save_latest,
        ):
            runtime._flush(1, snapshot, ["late callback"], [], "motion_clips")

        save_latest.assert_not_called()
        self.assertEqual(snapshot["status"], "cancelled")
        self.assertFalse(snapshot["running"])

    def test_job_runtime_instances_share_active_task_registry(self) -> None:
        owner = services.JobRuntime()
        observer = services.JobRuntime()
        job_id = "job-shared-registry-test"
        owner.tasks[job_id] = {"task": MagicMock(), "project_id": 901}
        stored = {
            "id": job_id,
            "project_id": 901,
            "status": "running",
            "running": True,
            "started_at": 100.0,
            "updated_at": 110.0,
            "heartbeat_at": 110.0,
            "last_progress_at": 109.0,
            "progress": [],
            "log": "",
        }
        try:
            with (
                patch.object(services.storage, "load_latest_job", return_value=stored),
                patch.object(services.storage, "save_latest_job") as save_latest,
                patch.object(services.storage, "now_ts", return_value=111.0),
            ):
                result = observer.latest(901)
        finally:
            owner.tasks.pop(job_id, None)

        self.assertTrue(result["running"])
        self.assertEqual(result["status"], "running")
        self.assertEqual(result["runtime_health"]["state"], "active")
        save_latest.assert_not_called()

    def test_fresh_unregistered_job_is_not_misclassified_as_interrupted(self) -> None:
        runtime = services.JobRuntime()
        stored = {
            "id": "job-owned-by-another-runtime",
            "project_id": 902,
            "status": "running",
            "running": True,
            "started_at": 100.0,
            "updated_at": 198.0,
            "heartbeat_at": 198.0,
            "last_progress_at": 190.0,
            "progress": [],
            "log": "",
        }
        with (
            patch.object(services.storage, "load_latest_job", return_value=stored),
            patch.object(services.storage, "save_latest_job") as save_latest,
            patch.object(services.storage, "now_ts", return_value=200.0),
        ):
            result = runtime.latest(902)

        self.assertTrue(result["running"])
        self.assertEqual(result["status"], "running")
        self.assertEqual(result["runtime_health"]["state"], "active")
        save_latest.assert_not_called()

    def test_startup_recovery_can_force_recent_orphan_to_interrupted(self) -> None:
        runtime = services.JobRuntime()
        stored = {
            "id": "job-left-by-old-process",
            "project_id": 903,
            "status": "running",
            "running": True,
            "started_at": 100.0,
            "updated_at": 198.0,
            "heartbeat_at": 198.0,
            "last_progress_at": 190.0,
            "progress": [],
            "log": "",
        }
        with (
            patch.object(services.storage, "load_latest_job", return_value=stored),
            patch.object(services.storage, "save_latest_job") as save_latest,
            patch.object(services.storage, "now_ts", return_value=200.0),
        ):
            result = runtime.latest(903, force_recover_orphan=True)

        self.assertFalse(result["running"])
        self.assertEqual(result["status"], "interrupted")
        save_latest.assert_called_once()

    def test_chatgpt_image_wait_keeps_active_generation_alive(self) -> None:
        failure = services.chatgpt_image_wait_failure(
            {"active": True, "send_ready": False, "error": ""},
            elapsed_seconds=120,
            silent_seconds=120,
            ready_seconds=0,
            stall_seconds=240,
        )

        self.assertEqual(failure, "")

    def test_chatgpt_page_state_treats_generation_error_as_failure(self) -> None:
        page = MagicMock()
        page.locator.return_value.inner_text.return_value = (
            "Creating image\nWe experienced an error when generating images."
        )

        state = services._chatgpt_generation_page_state(page)
        failure = services.chatgpt_image_wait_failure(
            state,
            elapsed_seconds=20,
            silent_seconds=0,
            ready_seconds=0,
            stall_seconds=240,
        )

        self.assertEqual(state["error"], "ChatGPT 图片生成服务返回错误")
        self.assertIn("已停止等待", failure)

    def test_chatgpt_page_state_detects_free_image_quota_card(self) -> None:
        page = MagicMock()
        page.locator.return_value.inner_text.return_value = (
            "Previous activity\nYou're out of images\n"
            "You've used all your free images for now.\nThis response couldn't load."
        )

        state = services._chatgpt_generation_page_state(page)
        failure = services.chatgpt_image_wait_failure(
            state,
            elapsed_seconds=2,
            silent_seconds=0,
            ready_seconds=0,
            stall_seconds=240,
        )

        self.assertEqual(state["error"], "ChatGPT 图片生成额度已用完")
        self.assertIn("已停止等待", failure)

    def test_chatgpt_page_state_parses_japanese_quota_reset_time(self) -> None:
        page = MagicMock()
        page.locator.return_value.inner_text.return_value = (
            "画像を使い切りました\n現在、無料の画像生成枠を使い切っています。"
            "または、明日の 1:37に無料枠が回復するまでお待ちください。"
        )
        page.evaluate.return_value = {"now": 1791540000.0, "offset": -540}

        state = services._chatgpt_generation_page_state(page)
        failure = services.chatgpt_image_wait_failure(
            state,
            elapsed_seconds=2,
            silent_seconds=0,
            ready_seconds=0,
            stall_seconds=240,
        )

        reset = services.datetime.fromtimestamp(state["retry_at"], tz=services.timezone(services.timedelta(hours=9)))
        self.assertEqual(state["error"], "ChatGPT 图片生成额度已用完")
        self.assertEqual((reset.hour, reset.minute), (1, 37))
        self.assertIn("自动解冻", failure)
        self.assertIn("[retry_at=", failure)

    def test_chatgpt_page_state_parses_japanese_relative_quota_reset(self) -> None:
        page = MagicMock()
        page.locator.return_value.inner_text.return_value = (
            "画像生成リクエストの上限に達しました。"
            "上限は 5 時間後にリセットされ、その後はさらに画像を作成できます。"
        )
        page.evaluate.return_value = {"now": 1791540000.0, "offset": -540}

        state = services._chatgpt_generation_page_state(page)

        self.assertEqual(state["error"], "ChatGPT 图片生成额度已用完")
        self.assertAlmostEqual(state["retry_at"], 1791540000.0 + 5 * 3600, delta=2)

    def test_chatgpt_page_state_detects_japanese_scheduled_image_card_and_freezes_five_hours(self) -> None:
        page = MagicMock()
        page.locator.return_value.inner_text.return_value = (
            "この画像の生成が予定されています。"
            "画像は後ほど生成されます。今すぐ作成するには、プランをアップグレードしてください。"
        )
        page.evaluate.return_value = {"now": 1791540000.0, "offset": -540}

        with patch.object(services.storage, "now_ts", return_value=1791540000.0):
            state = services._chatgpt_generation_page_state(page)

        self.assertIn("额度受限", state["error"])
        self.assertAlmostEqual(state["retry_at"], 1791540000.0 + 5 * 3600, delta=2)

    def test_chatgpt_quota_cooldown_defaults_to_five_hours(self) -> None:
        account = {"id": "five-hour-quota-account"}
        before = services.storage.now_ts()
        try:
            with patch.object(services.storage, "write_json"):
                services.record_chatgpt_account_result(
                    account,
                    error="ChatGPT 图片生成额度受限，当前请求已排队",
                    env={},
                )

            health = services._CHATGPT_ACCOUNT_HEALTH[account["id"]]
            self.assertGreaterEqual(health["cooldown_until"], before + 5 * 3600 - 2)
        finally:
            services._CHATGPT_ACCOUNT_HEALTH.pop(account["id"], None)

    def test_final_redraw_preview_replaces_previous_requirement_once(self) -> None:
        prompt_payload = {
            "prompt": "本期主题：刹车测试\n当前完整口播：最后一脚刹车决定结果\n追加要求（最高优先级，必须落实）：旧要求",
            "anchor_options": [{"key": "scene-1", "text": "最后一脚刹车决定结果"}],
            "anchor_key": "scene-1",
        }
        with patch.object(services, "image_prompt", return_value=prompt_payload):
            result = services.compile_final_chatgpt_image_prompt(
                137,
                "scene",
                "s_01.png",
                anchor_key="scene-1",
                additional_requirement="车型必须是 MPV",
            )

        outbound = result["final_outbound_prompt"]
        self.assertNotIn("旧要求", outbound)
        self.assertEqual(outbound.count("车型必须是 MPV"), 1)
        self.assertEqual(result["anchor_text"], "最后一脚刹车决定结果")

    def test_final_redraw_preview_uses_ai_rewritten_prompt(self) -> None:
        prompt_payload = {
            "target": "s_01.png",
            "prompt": "旧提示词：轿车驾驶员戴着头盔。",
            "anchor_options": [],
            "semantic_context": {"speech": "MPV 的刹车测试"},
        }
        rewritten = {
            "s_01.png": {
                "prompt": "横向画面，MPV 刹车测试台，清楚展示制动卡钳，不出现头盔。",
                "provider": "deepseek-image-prompt-teachers:test",
            }
        }
        with (
            patch.object(services, "image_prompt", return_value=prompt_payload),
            patch.object(services.storage, "get_project", return_value={"id": 137, "template": "科技情报站"}),
            patch.object(services.storage, "get_template", return_value={"name": "科技情报站"}),
            patch.object(services, "rewrite_image_prompts_with_ai_teachers", return_value=rewritten) as rewrite,
        ):
            result = services.compile_final_chatgpt_image_prompt(
                137,
                "scene",
                "s_01.png",
                additional_requirement="车型必须是 MPV，不要头盔",
                rewrite_prompt=True,
            )

        self.assertIn("MPV 刹车测试台", result["base_prompt"])
        self.assertNotIn("轿车驾驶员戴着头盔", result["base_prompt"])
        self.assertEqual(result["rewrite_provider"], "deepseek-image-prompt-teachers:test")
        self.assertEqual(rewrite.call_args.args[3][0]["rewrite_scope"], "partial")

    def test_final_visual_rewrite_bypasses_generic_scene_recompiler(self) -> None:
        rewritten = "高端豪华MPV驾驶席侧透视剖面，聚焦刹车踏板总成、转轴和机械推杆。"

        outbound = services.build_chatgpt_handoff_prompt(
            rewritten,
            "2560x1440",
            "scene",
            required_user_instruction="车型为MPV",
            preserve_visual_prompt=True,
        )

        self.assertIn("高端豪华MPV驾驶席侧透视剖面", outbound)
        self.assertIn("刹车踏板总成", outbound)
        self.assertNotIn("当前对象", outbound)
        self.assertNotIn("把当前口播最重要的冲突", outbound)

    def test_chatgpt_quota_failure_persists_exact_cooldown_until(self) -> None:
        account = {"id": "quota-test-account"}
        retry_at = services.storage.now_ts() + 4321
        try:
            with patch.object(services.storage, "write_json") as write_json:
                services.record_chatgpt_account_result(
                    account,
                    error=f"ChatGPT 图片生成额度已用完 [retry_at={retry_at:.3f}]",
                    env={},
                )

            health = services._CHATGPT_ACCOUNT_HEALTH[account["id"]]
            self.assertAlmostEqual(health["cooldown_until"], retry_at, places=2)
            self.assertAlmostEqual(health["quota_retry_at"], retry_at, places=2)
            write_json.assert_called_once()
        finally:
            services._CHATGPT_ACCOUNT_HEALTH.pop(account["id"], None)

    def test_chatgpt_image_wait_stops_frozen_generation_indicator(self) -> None:
        failure = services.chatgpt_image_wait_failure(
            {"active": True, "send_ready": False, "error": ""},
            elapsed_seconds=300,
            silent_seconds=241,
            ready_seconds=0,
            stall_seconds=240,
        )

        self.assertIn("判定为停滞", failure)

    def test_chatgpt_image_wait_rotates_account_after_active_hard_limit(self) -> None:
        failure = services.chatgpt_image_wait_failure(
            {"active": True, "send_ready": False, "error": ""},
            elapsed_seconds=421,
            silent_seconds=2,
            ready_seconds=0,
            stall_seconds=900,
            active_limit_seconds=420,
        )

        self.assertIn("自动轮换下一个账号", failure)

    def test_chatgpt_account_pool_assigns_independent_ports_and_profiles(self) -> None:
        env = {
            "CHATGPT_IMAGE_ACCOUNT_COUNT": "3",
            "CHATGPT_IMAGE_CDP_BASE_PORT": "9330",
            "CHATGPT_IMAGE_USER_DATA_DIR": "C:/studio/chatgpt-profile",
            "CHATGPT_IMAGE_ACCOUNT_LABELS": "主账号,备用账号,团队账号",
        }

        accounts = services.chatgpt_image_accounts(env)

        self.assertEqual([item["port"] for item in accounts], [9330, 9331, 9332])
        self.assertEqual([item["label"] for item in accounts], ["主账号", "备用账号", "团队账号"])
        self.assertEqual(str(accounts[0]["profile_dir"]).replace("\\", "/"), "C:/studio/chatgpt-profile")
        self.assertTrue(str(accounts[1]["profile_dir"]).replace("\\", "/").endswith("chatgpt-profile-account-02"))

    def test_chatgpt_generation_browser_uses_background_cdp_window(self) -> None:
        account = {
            "id": "account-01",
            "label": "ChatGPT 账号 1",
            "port": 9550,
            "cdp_url": "http://127.0.0.1:9550",
            "profile_dir": Path("C:/studio/chatgpt-profile"),
        }
        env = {"CHATGPT_IMAGE_HEADLESS": "true"}

        with (
            patch.object(services, "resolve_chatgpt_browser_path", return_value="C:/Chrome/chrome.exe"),
            patch.object(
                services,
                "chatgpt_cdp_metadata",
                side_effect=[{}, {"Browser": "Chrome"}],
            ),
            patch.object(services.storage, "ensure_dir", return_value=account["profile_dir"]),
            patch.object(services.subprocess, "Popen") as popen,
        ):
            services.ensure_chatgpt_cdp_browser(account, env)

        launch_args = popen.call_args.args[0]
        self.assertNotIn("--headless=new", launch_args)
        self.assertIn("--start-minimized", launch_args)
        self.assertIn("--window-position=-32000,-32000", launch_args)
        self.assertIn("--disable-session-crashed-bubble", launch_args)
        self.assertIn("--hide-crash-restore-bubble", launch_args)
        self.assertNotIn("--new-window", launch_args)

    def test_ant_browser_preserves_other_instances_when_starting_selected_account(self) -> None:
        account = {
            "id": "ant-new",
            "label": "账号二",
            "provider": "ant_browser",
            "code": "NEW222",
            "cdp_url": "",
            "port": 0,
        }
        client = MagicMock()
        client.runtime_status.return_value = {"running": False, "debugReady": False}
        client.list_profiles.return_value = [
            {"launchCode": "OLD111", "running": True, "debugReady": True},
            {"launchCode": "NEW222", "running": False, "debugReady": False},
        ]
        client.start_session.return_value = {
            "directDebugUrl": "http://127.0.0.1:9333",
            "debugPort": 9333,
            "profileId": "profile-new",
            "lastStartAt": "2026-09-18T22:41:05+08:00",
        }

        with (
            patch.object(services.ant_browser, "client_from_env", return_value=client),
            patch.object(services, "chatgpt_cdp_metadata", return_value={"Browser": "Chrome"}),
        ):
            result = services.ensure_chatgpt_cdp_browser(account, {})

        self.assertEqual(result, {"Browser": "Chrome"})
        client.list_profiles.assert_not_called()
        client.stop_and_wait.assert_not_called()
        client.runtime_status.assert_called_once_with("NEW222")
        client.start_session.assert_called_once_with(
            "NEW222", start_url="https://chatgpt.com/", timeout_ms=120000
        )

    def test_ant_browser_reuses_running_instance_without_opening_launch_page(self) -> None:
        account = {
            "id": "ant-existing",
            "label": "已有账号",
            "provider": "ant_browser",
            "code": "OLD111",
            "cdp_url": "",
            "port": 0,
        }
        client = MagicMock()
        client.runtime_status.return_value = {
            "running": True,
            "debugReady": True,
            "directDebugUrl": "http://127.0.0.1:9222",
            "debugPort": 9222,
            "profileId": "profile-old",
        }

        with (
            patch.object(services.ant_browser, "client_from_env", return_value=client),
            patch.object(services, "chatgpt_cdp_metadata", return_value={"Browser": "Chrome"}),
        ):
            result = services.ensure_chatgpt_cdp_browser(account, {})

        self.assertEqual(result, {"Browser": "Chrome"})
        client.start_session.assert_not_called()
        self.assertFalse(account["ant_started_by_task"])
        self.assertEqual(account["cdp_url"], "http://127.0.0.1:9222")

    def test_ant_browser_delayed_takeover_keeps_polling_same_instance(self) -> None:
        client = services.ant_browser.AntBrowserClient(timeout=1.0)
        delayed = RuntimeError(
            "浏览器窗口已启动，但在 15 秒 内尚未完成接管；系统会继续在后台连接。"
        )
        with (
            patch.object(services.ant_browser.AntBrowserClient, "request", side_effect=delayed) as request,
            patch.object(
                services.ant_browser.AntBrowserClient,
                "runtime_status",
                side_effect=[
                    {"running": True, "debugReady": False},
                    {
                        "running": True,
                        "debugReady": True,
                        "directDebugUrl": "http://127.0.0.1:9333",
                        "debugPort": 9333,
                    },
                ],
            ) as runtime_status,
            patch.object(services.ant_browser.time, "sleep"),
        ):
            result = client.start_session("ABC123", timeout_ms=3000)

        self.assertTrue(result["ready"])
        self.assertEqual(result["debugPort"], 9333)
        request.assert_called_once()
        self.assertEqual(runtime_status.call_count, 2)

    def test_chatgpt_true_headless_requires_explicit_opt_in(self) -> None:
        account = {
            "id": "account-01",
            "label": "ChatGPT 账号 1",
            "port": 9550,
            "cdp_url": "http://127.0.0.1:9550",
            "profile_dir": Path("C:/studio/chatgpt-profile"),
        }
        env = {
            "CHATGPT_IMAGE_HEADLESS": "true",
            "CHATGPT_IMAGE_TRUE_HEADLESS": "true",
        }
        with (
            patch.object(services, "resolve_chatgpt_browser_path", return_value="C:/Chrome/chrome.exe"),
            patch.object(services, "chatgpt_cdp_metadata", side_effect=[{}, {"Browser": "Chrome"}]),
            patch.object(services.storage, "ensure_dir", return_value=account["profile_dir"]),
            patch.object(services.subprocess, "Popen") as popen,
        ):
            services.ensure_chatgpt_cdp_browser(account, env)

        self.assertIn("--headless=new", popen.call_args.args[0])

    def test_chatgpt_challenge_page_is_detected_without_waiting_for_composer(self) -> None:
        reason = services.chatgpt_access_challenge_reason(
            "请稍候…",
            "https://chatgpt.com/",
            "正在验证您是否是真人 Cloudflare",
        )

        self.assertTrue(reason)

    def test_chatgpt_composer_does_not_rewrite_existing_prompt(self) -> None:
        composer = MagicMock()
        composer.inner_text.return_value = "first line\nsecond line"
        page = SimpleNamespace(add_style_tag=MagicMock(), keyboard=MagicMock())

        with patch.object(
            services,
            "_find_chatgpt_composer",
            return_value=(composer, "form div#prompt-textarea[contenteditable='true']"),
        ):
            services._fill_chatgpt_composer(page, "first line second line")

        composer.fill.assert_not_called()
        page.keyboard.insert_text.assert_not_called()

    def test_chatgpt_composer_accepts_contenteditable_layout_whitespace(self) -> None:
        composer = MagicMock()
        composer.inner_text.side_effect = ["", "first line\n\nsecond line"]
        page = SimpleNamespace(add_style_tag=MagicMock(), keyboard=MagicMock())

        with patch.object(
            services,
            "_find_chatgpt_composer",
            return_value=(composer, "form div#prompt-textarea[contenteditable='true']"),
        ):
            services._fill_chatgpt_composer(page, "first line second line")

        composer.fill.assert_called_once_with("first line second line", timeout=10000)
        page.keyboard.insert_text.assert_not_called()

    def test_chatgpt_composer_stops_after_second_failed_write(self) -> None:
        composer = MagicMock()
        composer.inner_text.side_effect = ["", "partial", "still partial"]
        page = SimpleNamespace(add_style_tag=MagicMock(), keyboard=MagicMock())

        with (
            patch.object(
                services,
                "_find_chatgpt_composer",
                return_value=(composer, "form div#prompt-textarea[contenteditable='true']"),
            ),
            self.assertRaisesRegex(RuntimeError, "stopped rewriting|已停止重写"),
        ):
            services._fill_chatgpt_composer(page, "target prompt")

        composer.fill.assert_called_once()
        page.keyboard.insert_text.assert_called_once_with("target prompt")

    def test_chatgpt_email_verification_page_is_reported_as_challenge(self) -> None:
        reason = services.chatgpt_access_challenge_reason(
            "检查你的收件箱 - OpenAI",
            "https://auth.openai.com/",
            "",
        )

        self.assertTrue(reason)

    def test_chatgpt_login_window_forces_visible_browser(self) -> None:
        env = {"CHATGPT_IMAGE_ACCOUNT_COUNT": "1"}
        with (
            patch.object(services, "chatgpt_cdp_metadata", return_value={}),
            patch.object(services, "ensure_chatgpt_cdp_browser") as ensure_browser,
        ):
            services.open_chatgpt_login_window(env, account_id="account-01")

        self.assertFalse(ensure_browser.call_args.kwargs["headless"])

    def test_chatgpt_generation_rotates_to_next_account_after_failure(self) -> None:
        first = {"id": "account-01", "label": "账号一"}
        second = {"id": "account-02", "label": "账号二"}
        first_lock = MagicMock()
        second_lock = MagicMock()
        manager = MagicMock()
        playwright = MagicMock()
        manager.__enter__.return_value = playwright
        expected = Path("C:/studio/scenes/s_01.png")
        env = {"CHATGPT_IMAGE_ACCOUNT_COUNT": "2"}

        with (
            patch.object(
                services,
                "acquire_chatgpt_image_account",
                side_effect=[(first, first_lock), (second, second_lock)],
            ),
            patch.object(
                services,
                "_generate_chatgpt_web_auto_image_for_account",
                side_effect=[RuntimeError("验证页"), expected],
            ) as generate_for_account,
            patch.object(services, "record_chatgpt_account_result"),
        ):
            result = services._run_chatgpt_web_auto_image_account_pool(
                lambda: manager,
                "提示词",
                expected,
                "https://chatgpt.com/",
                900,
                env,
            )

        self.assertEqual(result, expected)
        self.assertEqual(generate_for_account.call_count, 2)
        first_lock.release.assert_called_once()
        second_lock.release.assert_called_once()

    def test_chatgpt_generation_closes_browser_after_image_is_saved(self) -> None:
        account = {
            "id": "account-01",
            "label": "账号一",
            "cdp_url": "http://127.0.0.1:9222",
            "port": 9222,
            "profile_dir": Path("C:/studio/profile"),
        }
        output_path = Path("C:/studio/scenes/s_01.png")
        playwright = MagicMock()
        browser = MagicMock()
        context = MagicMock()
        page = MagicMock()
        browser.contexts = [context]
        context.pages = [page]
        context.new_page.return_value = page
        playwright.chromium.connect_over_cdp.return_value = browser
        page.evaluate.return_value = []
        env = {
            "CHATGPT_IMAGE_HEADLESS": "false",
            "CHATGPT_IMAGE_CLOSE_BROWSER_AFTER_SAVE": "true",
        }

        with (
            patch.object(services, "ensure_chatgpt_cdp_browser"),
            patch.object(services, "_open_fresh_chatgpt_image_chat", return_value=page),
            patch.object(services, "_wait_for_visible_chatgpt_challenge"),
            patch.object(services, "_dismiss_chatgpt_blocking_overlays") as dismiss_overlays,
            patch.object(services, "_activate_chatgpt_image_mode"),
            patch.object(services, "_fill_chatgpt_composer"),
            patch.object(services, "_click_chatgpt_send"),
            patch.object(services, "_save_latest_chatgpt_image", return_value=output_path),
            patch.object(services, "cleanup_chatgpt_conversation_after_save"),
            patch.object(services, "close_connected_chatgpt_browser", return_value=True) as close_browser,
        ):
            result = services._generate_chatgpt_web_auto_image_for_account(
                playwright,
                account,
                "提示词",
                output_path,
                "https://chatgpt.com/",
                900,
                env,
            )

        self.assertEqual(result, output_path)
        context.new_page.assert_not_called()
        dismiss_overlays.assert_called_once_with(page, log=None)
        close_browser.assert_called_once_with(browser, account, log=None)

    def test_chatgpt_generation_closes_browser_after_failure(self) -> None:
        account = {
            "id": "account-01",
            "label": "账号一",
            "cdp_url": "http://127.0.0.1:9222",
            "port": 9222,
            "profile_dir": Path("C:/studio/profile"),
        }
        playwright = MagicMock()
        browser = MagicMock()
        context = MagicMock()
        page = MagicMock()
        browser.contexts = [context]
        context.pages = [page]
        context.new_page.return_value = page
        playwright.chromium.connect_over_cdp.return_value = browser
        page.evaluate.return_value = []
        env = {"CHATGPT_IMAGE_HEADLESS": "false"}

        with (
            patch.object(services, "ensure_chatgpt_cdp_browser"),
            patch.object(services, "_open_fresh_chatgpt_image_chat", return_value=page),
            patch.object(services, "_wait_for_visible_chatgpt_challenge"),
            patch.object(services, "_activate_chatgpt_image_mode"),
            patch.object(services, "_fill_chatgpt_composer"),
            patch.object(services, "_click_chatgpt_send"),
            patch.object(services, "_save_latest_chatgpt_image", side_effect=RuntimeError("生成失败")),
            patch.object(services, "close_connected_chatgpt_browser", return_value=True) as close_browser,
        ):
            with self.assertRaisesRegex(RuntimeError, "生成失败"):
                services._generate_chatgpt_web_auto_image_for_account(
                    playwright,
                    account,
                    "提示词",
                    Path("C:/studio/scenes/s_01.png"),
                    "https://chatgpt.com/",
                    900,
                    env,
                )

        close_browser.assert_called_once_with(
            browser,
            account,
            timeout_seconds=8.0,
            log=None,
            image_saved=False,
        )

    def test_ant_generation_closes_only_task_page_after_success(self) -> None:
        account = {
            "id": "ant-01",
            "label": "Ant 账号一",
            "provider": "ant_browser",
            "code": "ABC123",
            "cdp_url": "http://127.0.0.1:9222",
        }
        output_path = Path("C:/studio/scenes/s_01.png")
        playwright = MagicMock()
        browser = MagicMock()
        context = MagicMock()
        preexisting_page = MagicMock()
        task_page = MagicMock()
        context.pages = [preexisting_page]
        context.new_page.return_value = task_page
        browser.contexts = [context]
        playwright.chromium.connect_over_cdp.return_value = browser
        env = {"CHATGPT_IMAGE_CLOSE_BROWSER_AFTER_SAVE": "true"}

        with (
            patch.object(services, "ensure_chatgpt_cdp_browser"),
            patch.object(services, "_open_fresh_chatgpt_image_chat", return_value=task_page),
            patch.object(services, "chatgpt_image_account_count", return_value=1),
            patch.object(services, "_wait_for_visible_chatgpt_challenge"),
            patch.object(services, "_dismiss_chatgpt_blocking_overlays"),
            patch.object(services, "_attach_chatgpt_reference_images"),
            patch.object(services, "_fill_chatgpt_composer"),
            patch.object(services, "_click_chatgpt_send"),
            patch.object(services, "_save_latest_chatgpt_image", return_value=output_path),
            patch.object(services, "cleanup_chatgpt_conversation_after_save"),
            patch.object(services, "close_connected_chatgpt_browser") as close_browser,
        ):
            result = services._generate_chatgpt_web_auto_image_for_account(
                playwright, account, "提示词", output_path, "https://chatgpt.com/", 900, env
            )

        self.assertEqual(result, output_path)
        task_page.close.assert_called_once()
        preexisting_page.close.assert_not_called()
        close_browser.assert_called_once_with(
            browser,
            account,
            timeout_seconds=8.0,
            log=None,
            image_saved=True,
        )
        browser.close.assert_not_called()

    def test_ant_generation_closes_only_task_page_after_failure(self) -> None:
        account = {
            "id": "ant-01",
            "label": "Ant 账号一",
            "provider": "ant_browser",
            "code": "ABC123",
            "cdp_url": "http://127.0.0.1:9222",
        }
        playwright = MagicMock()
        browser = MagicMock()
        context = MagicMock()
        preexisting_page = MagicMock()
        task_page = MagicMock()
        context.pages = [preexisting_page]
        context.new_page.return_value = task_page
        browser.contexts = [context]
        playwright.chromium.connect_over_cdp.return_value = browser

        with (
            patch.object(services, "ensure_chatgpt_cdp_browser"),
            patch.object(services, "_open_fresh_chatgpt_image_chat", return_value=task_page),
            patch.object(services, "chatgpt_image_account_count", return_value=1),
            patch.object(services, "_wait_for_visible_chatgpt_challenge"),
            patch.object(services, "_dismiss_chatgpt_blocking_overlays"),
            patch.object(services, "_attach_chatgpt_reference_images"),
            patch.object(services, "_fill_chatgpt_composer", side_effect=RuntimeError("输入失败")),
            patch.object(services, "close_connected_chatgpt_browser") as close_browser,
            patch.object(services, "close_chatgpt_cdp_browser") as close_account,
        ):
            with self.assertRaisesRegex(RuntimeError, "输入失败"):
                services._generate_chatgpt_web_auto_image_for_account(
                    playwright,
                    account,
                    "提示词",
                    Path("C:/studio/scenes/s_01.png"),
                    "https://chatgpt.com/",
                    900,
                    {},
                )

        task_page.close.assert_called_once()
        preexisting_page.close.assert_not_called()
        close_browser.assert_called_once_with(
            browser,
            account,
            timeout_seconds=8.0,
            log=None,
            image_saved=False,
        )
        close_account.assert_not_called()
        browser.close.assert_not_called()

    def test_ant_browser_cleanup_never_stops_shared_instance(self) -> None:
        account = {
            "id": "ant-01",
            "label": "Ant 账号一",
            "provider": "ant_browser",
            "code": "ABC123",
            "cdp_url": "http://127.0.0.1:9222",
        }
        browser = MagicMock()

        with patch.object(services.ant_browser, "client_from_env") as client_factory:
            self.assertTrue(services.close_connected_chatgpt_browser(browser, account))
            self.assertTrue(services.close_chatgpt_cdp_browser(account))

        client_factory.assert_not_called()
        browser.close.assert_not_called()

    def test_ant_browser_cleanup_stops_instance_started_by_task(self) -> None:
        account = {
            "id": "ant-01",
            "label": "Ant 账号一",
            "provider": "ant_browser",
            "code": "ABC123",
            "ant_started_by_task": True,
        }
        browser = MagicMock()
        client = MagicMock()
        client.stop_and_wait.return_value = True

        with (
            patch.object(services, "runtime_env", return_value={}),
            patch.object(services.ant_browser, "client_from_env", return_value=client),
        ):
            closed = services.close_connected_chatgpt_browser(browser, account)

        self.assertTrue(closed)
        client.stop_and_wait.assert_called_once_with("ABC123", timeout_seconds=10.0)
        browser.close.assert_not_called()
        self.assertNotIn("ant_started_by_task", account)

    def test_ant_browser_multi_account_challenge_rotates_without_waiting(self) -> None:
        account = {
            "id": "ant-01",
            "label": "账号一",
            "provider": "ant_browser",
            "code": "ABC123",
            "cdp_url": "http://127.0.0.1:9222",
        }
        output_path = Path("C:/studio/scenes/s_01.png")
        playwright = MagicMock()
        browser = MagicMock()
        context = MagicMock()
        page = MagicMock()
        browser.contexts = [context]
        playwright.chromium.connect_over_cdp.return_value = browser
        env = {"CHATGPT_IMAGE_HEADLESS": "false"}

        with (
            patch.object(services, "ensure_chatgpt_cdp_browser"),
            patch.object(services, "_reuse_chatgpt_automation_page", return_value=page),
            patch.object(services, "_open_fresh_chatgpt_image_chat", return_value=page),
            patch.object(services, "chatgpt_image_account_count", return_value=4),
            patch.object(
                services,
                "_raise_chatgpt_access_challenge",
                side_effect=services.ChatgptAccessChallengeError("需要验证"),
            ) as raise_challenge,
            patch.object(services, "_wait_for_visible_chatgpt_challenge") as wait_challenge,
            patch.object(services, "close_connected_chatgpt_browser", return_value=True),
        ):
            with self.assertRaises(services.ChatgptAccessChallengeError):
                services._generate_chatgpt_web_auto_image_for_account(
                    playwright,
                    account,
                    "提示词",
                    output_path,
                    "https://chatgpt.com/",
                    900,
                    env,
                )

        raise_challenge.assert_called_once_with(page)
        wait_challenge.assert_not_called()

    def test_chatgpt_automation_reuses_launch_tab_and_closes_duplicates(self) -> None:
        context = MagicMock()
        launch_page = MagicMock()
        duplicate_page = MagicMock()
        launch_page.is_closed.return_value = False
        duplicate_page.is_closed.return_value = False
        launch_page.url = "https://chatgpt.com/"
        duplicate_page.url = "https://chatgpt.com/c/old-chat"
        context.pages = [launch_page, duplicate_page]
        logs: list[str] = []

        selected = services._reuse_chatgpt_automation_page(
            context,
            "https://chatgpt.com/",
            log=logs.append,
        )

        self.assertIs(selected, launch_page)
        context.new_page.assert_not_called()
        duplicate_page.close.assert_called_once()
        self.assertIn("关闭 1 个重复标签", logs[-1])

    def test_chatgpt_generation_closes_account_port_when_cdp_connection_fails(self) -> None:
        account = {
            "id": "account-01",
            "label": "账号一",
            "cdp_url": "http://127.0.0.1:9222",
            "port": 9222,
            "profile_dir": Path("C:/studio/profile"),
        }
        playwright = MagicMock()
        playwright.chromium.connect_over_cdp.side_effect = RuntimeError("端口连接失败")

        with (
            patch.object(services, "ensure_chatgpt_cdp_browser"),
            patch.object(services, "close_chatgpt_cdp_browser", return_value=True) as close_port,
        ):
            with self.assertRaisesRegex(RuntimeError, "端口连接失败"):
                services._generate_chatgpt_web_auto_image_for_account(
                    playwright,
                    account,
                    "提示词",
                    Path("C:/studio/scenes/s_01.png"),
                    "https://chatgpt.com/",
                    900,
                    {},
                )

        close_port.assert_called_once_with(account, timeout_seconds=8.0)

    def test_chatgpt_browser_shutdown_uses_browser_level_cdp_command(self) -> None:
        browser = MagicMock()
        session = MagicMock()
        browser.new_browser_cdp_session.return_value = session

        services._request_chatgpt_browser_shutdown(browser)

        session.send.assert_called_once_with("Browser.close")
        session.detach.assert_called_once()
        browser.close.assert_not_called()

    def test_chatgpt_browser_close_only_reports_success_after_port_disappears(self) -> None:
        browser = MagicMock()
        account = {"id": "account-01", "label": "账号一", "cdp_url": "http://127.0.0.1:9222"}
        messages: list[str] = []

        with (
            patch.object(services, "_request_chatgpt_browser_shutdown") as request_shutdown,
            patch.object(services, "_wait_for_chatgpt_cdp_shutdown", return_value=True) as wait_shutdown,
            patch.object(services, "_wait_for_managed_chatgpt_process_exit", return_value=True) as wait_process,
            patch.object(services, "_terminate_managed_chatgpt_process", return_value=False) as terminate_process,
        ):
            closed = services.close_connected_chatgpt_browser(browser, account, log=messages.append)

        self.assertTrue(closed)
        request_shutdown.assert_called_once_with(browser)
        wait_shutdown.assert_called_once_with(account, 10.0)
        wait_process.assert_called_once_with(account, timeout_seconds=10.0)
        terminate_process.assert_not_called()
        self.assertIn("Chrome 已确认关闭", messages[-1])

    def test_chatgpt_browser_force_closes_only_after_graceful_exit_timeout(self) -> None:
        browser = MagicMock()
        account = {"id": "account-01", "label": "账号一", "cdp_url": "http://127.0.0.1:9222"}
        with (
            patch.object(services, "_request_chatgpt_browser_shutdown"),
            patch.object(services, "_wait_for_chatgpt_cdp_shutdown", return_value=True),
            patch.object(services, "_wait_for_managed_chatgpt_process_exit", return_value=False),
            patch.object(services, "_terminate_managed_chatgpt_process", return_value=True) as terminate_process,
        ):
            closed = services.close_connected_chatgpt_browser(browser, account)

        self.assertTrue(closed)
        terminate_process.assert_called_once_with(account)

    def test_chatgpt_account_pool_reports_saved_session_when_browser_is_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_root = Path(temp_dir)
            profile_dir = config_root / "chatgpt-browser-profile"
            cookie_file = profile_dir / "Default" / "Network" / "Cookies"
            cookie_file.parent.mkdir(parents=True)
            connection = sqlite3.connect(cookie_file)
            connection.execute("CREATE TABLE cookies (host_key TEXT, name TEXT)")
            connection.execute(
                "INSERT INTO cookies (host_key, name) VALUES (?, ?)",
                (".chatgpt.com", "__Secure-next-auth.session-token"),
            )
            connection.commit()
            connection.close()
            env = {
                "CHATGPT_IMAGE_ACCOUNT_COUNT": "1",
                "CHATGPT_IMAGE_USER_DATA_DIR": str(profile_dir),
            }

            with (
                patch.object(storage, "CONFIG_ROOT", config_root),
                patch.object(services, "chatgpt_cdp_metadata", return_value={}),
            ):
                payload = services.chatgpt_account_pool_status(env)

            self.assertFalse(payload["accounts"][0]["connected"])
            self.assertTrue(payload["accounts"][0]["saved_session"])

    def test_chatgpt_account_pool_releases_stale_stopping_lease(self) -> None:
        env = {"CHATGPT_IMAGE_ACCOUNT_COUNT": "1"}
        account = services.chatgpt_image_accounts(env)[0]
        account_lock = threading.Lock()
        account_lock.acquire()
        abort_event = threading.Event()
        abort_event.set()
        with services._CHATGPT_ACCOUNT_POOL_LOCK:
            services._CHATGPT_ACCOUNT_USE_LOCKS[account["id"]] = account_lock
            services._CHATGPT_ACCOUNT_LEASES[account["id"]] = {
                "lock": account_lock,
                "abort_event": abort_event,
                "started_at": services.storage.now_ts() - 30,
                "abort_requested_at": services.storage.now_ts() - 20,
            }
        try:
            with (
                patch.object(services, "chatgpt_cdp_metadata", return_value={}),
                patch.object(services, "chatgpt_profile_has_saved_session", return_value=True),
            ):
                payload = services.chatgpt_account_pool_status(env)
        finally:
            with services._CHATGPT_ACCOUNT_POOL_LOCK:
                services._CHATGPT_ACCOUNT_USE_LOCKS.clear()
                services._CHATGPT_ACCOUNT_LEASES.clear()

        self.assertFalse(account_lock.locked())
        self.assertFalse(payload["accounts"][0]["busy"])
        self.assertFalse(payload["accounts"][0]["stopping"])

    def test_chatgpt_account_pool_releases_legacy_orphan_busy_lease(self) -> None:
        env = {"CHATGPT_IMAGE_ACCOUNT_COUNT": "1"}
        account = services.chatgpt_image_accounts(env)[0]
        account_lock = threading.Lock()
        account_lock.acquire()
        with services._CHATGPT_ACCOUNT_POOL_LOCK:
            services._CHATGPT_ACCOUNT_USE_LOCKS[account["id"]] = account_lock
            services._CHATGPT_ACCOUNT_LEASES[account["id"]] = {
                "lock": account_lock,
                "abort_event": threading.Event(),
                "started_at": services.storage.now_ts() - 1800,
            }
        try:
            with (
                patch.object(services, "chatgpt_cdp_metadata", return_value={}),
                patch.object(services, "chatgpt_profile_has_saved_session", return_value=True),
            ):
                payload = services.chatgpt_account_pool_status(env)
        finally:
            with services._CHATGPT_ACCOUNT_POOL_LOCK:
                services._CHATGPT_ACCOUNT_USE_LOCKS.clear()
                services._CHATGPT_ACCOUNT_LEASES.clear()

        self.assertFalse(account_lock.locked())
        self.assertFalse(payload["accounts"][0]["busy"])
        self.assertFalse(payload["accounts"][0]["stopping"])

    def test_clear_chatgpt_account_login_state_removes_slot_and_shifts_later_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_root = Path(temp_dir)
            primary = config_root / "chatgpt-browser-profile"
            secondary = config_root / "chatgpt-browser-profile-account-02"
            tertiary = config_root / "chatgpt-browser-profile-account-03"
            (primary / "Default").mkdir(parents=True)
            (secondary / "Default").mkdir(parents=True)
            (tertiary / "Default").mkdir(parents=True)
            (primary / "Default" / "keep.txt").write_text("keep", encoding="utf-8")
            (secondary / "Default" / "remove.txt").write_text("remove", encoding="utf-8")
            (tertiary / "Default" / "shift.txt").write_text("shift", encoding="utf-8")
            env = {
                "CHATGPT_IMAGE_ACCOUNT_COUNT": "3",
                "CHATGPT_IMAGE_USER_DATA_DIR": str(primary),
            }

            with (
                patch.object(storage, "CONFIG_ROOT", config_root),
                patch.object(services, "chatgpt_cdp_metadata", return_value={}),
                patch.object(storage, "save_env_patch") as save_env_patch,
            ):
                result = services.clear_chatgpt_account_login_state(env, "account-02")

            self.assertTrue(result["ok"])
            self.assertEqual(result["count"], 2)
            self.assertTrue((primary / "Default" / "keep.txt").exists())
            self.assertFalse((secondary / "Default" / "remove.txt").exists())
            self.assertTrue((secondary / "Default" / "shift.txt").exists())
            self.assertFalse(tertiary.exists())
            save_env_patch.assert_called_once_with({"CHATGPT_IMAGE_ACCOUNT_COUNT": "2"})

    def test_chatgpt_account_pool_skips_cooled_account(self) -> None:
        env = {
            "CHATGPT_IMAGE_ACCOUNT_COUNT": "2",
            "CHATGPT_IMAGE_CDP_BASE_PORT": "9440",
            "CHATGPT_IMAGE_USER_DATA_DIR": "C:/studio/chatgpt-pool",
            "CHATGPT_IMAGE_ACCOUNT_COOLDOWN_SECONDS": "180",
        }
        with services._CHATGPT_ACCOUNT_POOL_LOCK:
            services._CHATGPT_ACCOUNT_HEALTH.clear()
            services._CHATGPT_ACCOUNT_USE_LOCKS.clear()
            services._CHATGPT_ACCOUNT_POOL_CURSOR = 0

        first, first_lock = services.acquire_chatgpt_image_account(env)
        first_lock.release()
        services.record_chatgpt_account_result(first, error="生成图片停滞", env=env)
        second, second_lock = services.acquire_chatgpt_image_account(env)
        second_lock.release()

        self.assertEqual(first["id"], "account-01")
        self.assertEqual(second["id"], "account-02")

    def test_chatgpt_abort_closes_browser_and_releases_account_lease(self) -> None:
        env = {"CHATGPT_IMAGE_ACCOUNT_COUNT": "1"}
        account = services.chatgpt_image_accounts(env)[0]
        account_lock = threading.Lock()
        account_lock.acquire()
        abort_event = threading.Event()
        with services._CHATGPT_ACCOUNT_POOL_LOCK:
            services._CHATGPT_ACCOUNT_USE_LOCKS[account["id"]] = account_lock
            services._CHATGPT_ACCOUNT_LEASES[account["id"]] = {
                "lock": account_lock,
                "abort_event": abort_event,
                "started_at": services.storage.now_ts(),
            }

        def release_after_abort() -> None:
            abort_event.wait(1)
            services.release_chatgpt_image_account(account, account_lock)

        worker = threading.Thread(target=release_after_abort)
        worker.start()
        try:
            with patch.object(services, "close_chatgpt_cdp_browser", return_value=True) as close_browser:
                result = services.abort_active_chatgpt_image_generations(env, timeout_seconds=1)
        finally:
            worker.join(timeout=1)
            with services._CHATGPT_ACCOUNT_POOL_LOCK:
                services._CHATGPT_ACCOUNT_USE_LOCKS.clear()
                services._CHATGPT_ACCOUNT_LEASES.clear()

        self.assertTrue(abort_event.is_set())
        self.assertEqual(result["released"], ["account-01"])
        self.assertEqual(result["pending"], [])
        close_browser.assert_called_once()

    def test_job_cancel_requests_chatgpt_browser_abort(self) -> None:
        async def scenario() -> dict[str, object]:
            runtime = services.JobRuntime()
            job_id = "job-cancel-chatgpt"
            task = asyncio.create_task(asyncio.sleep(30))
            runtime.tasks[job_id] = {"task": task, "project_id": 99}
            try:
                with (
                    patch.object(services, "runtime_env", return_value={"CHATGPT_IMAGE_ACCOUNT_COUNT": "1"}),
                    patch.object(
                        services,
                        "abort_active_chatgpt_image_generations",
                        return_value={"requested": 1, "released": ["account-01"], "pending": []},
                    ) as abort_generation,
                ):
                    result = await runtime.cancel(job_id)
                abort_generation.assert_called_once()
                return result
            finally:
                runtime.tasks.pop(job_id, None)

        result = asyncio.run(scenario())

        self.assertFalse(result["already_done"])
        self.assertEqual(result["chatgpt_abort"]["pending"], [])

    def test_job_cancel_survives_browser_cleanup_failure(self) -> None:
        async def scenario() -> dict[str, object]:
            runtime = services.JobRuntime()
            job_id = "job-cancel-cleanup-failure"
            task = asyncio.create_task(asyncio.sleep(30))
            runtime.tasks[job_id] = {"task": task, "project_id": 99}
            try:
                with patch.object(
                    services,
                    "abort_active_chatgpt_image_generations",
                    side_effect=RuntimeError("Ant Browser API timed out"),
                ):
                    return await runtime.cancel(job_id)
            finally:
                runtime.tasks.pop(job_id, None)

        result = asyncio.run(scenario())

        self.assertFalse(result["already_done"])
        self.assertIn("cleanup_error", result["chatgpt_abort"])

    def test_abort_active_generation_does_not_discover_browser_accounts(self) -> None:
        account_lock = threading.Lock()
        account_lock.acquire()
        abort_event = threading.Event()
        with services._CHATGPT_ACCOUNT_POOL_LOCK:
            services._CHATGPT_ACCOUNT_LEASES["ant-01"] = {
                "lock": account_lock,
                "abort_event": abort_event,
                "account": {"id": "ant-01", "provider": "ant_browser", "code": "ABC123"},
            }
        try:
            with (
                patch.object(services, "chatgpt_image_accounts", side_effect=RuntimeError("must not discover")),
                patch.object(services, "close_chatgpt_cdp_browser", return_value=True),
            ):
                result = services.abort_active_chatgpt_image_generations({}, timeout_seconds=0)
        finally:
            account_lock.release()
            with services._CHATGPT_ACCOUNT_POOL_LOCK:
                services._CHATGPT_ACCOUNT_LEASES.clear()

        self.assertTrue(abort_event.is_set())
        self.assertEqual(result["requested"], 1)

    def test_chatgpt_image_wait_stops_finished_text_only_response(self) -> None:
        failure = services.chatgpt_image_wait_failure(
            {"active": False, "send_ready": True, "error": ""},
            elapsed_seconds=151,
            silent_seconds=100,
            ready_seconds=91,
            stall_seconds=240,
        )

        self.assertIn("只回复了文字", failure)
        self.assertIn("自动停止", failure)

    def test_chatgpt_key_image_candidates_do_not_redraw_inside_each_variant(self) -> None:
        candidate_attempts = services.image_prompt_generation_attempt_limit(
            "chatgpt_web_auto",
            ".s_01_a.gen-123456.png",
        )
        normal_attempts = services.image_prompt_generation_attempt_limit(
            "chatgpt_web_auto",
            ".s_04.gen-123456.png",
        )

        self.assertEqual(candidate_attempts, 1)
        self.assertEqual(normal_attempts, 1)

    def test_job_flush_persists_heartbeat_and_phase_message(self) -> None:
        runtime = services.JobRuntime()
        snapshot = {"id": "job-current"}
        progress = [
            {
                "key": "images",
                "status": "running",
                "message": "正在等待 ChatGPT 生图",
                "updated_at": 319.0,
            }
        ]
        with (
            patch.object(services.storage, "load_latest_job", return_value={"id": "job-current"}),
            patch.object(services.storage, "save_latest_job") as save_latest,
            patch.object(services.storage, "now_ts", return_value=321.0),
        ):
            runtime._flush(1, snapshot, ["live"], progress, "images")

        saved = save_latest.call_args.args[1]
        self.assertEqual(saved["heartbeat_at"], 321.0)
        self.assertEqual(saved["updated_at"], 321.0)
        self.assertEqual(saved["last_progress_at"], 319.0)
        self.assertEqual(saved["phase_message"], "正在等待 ChatGPT 生图")

    def test_job_runtime_health_distinguishes_waiting_from_stalled(self) -> None:
        base = {
            "status": "running",
            "running": True,
            "started_at": 100.0,
        }

        active = services.job_runtime_health(
            {**base, "heartbeat_at": 198.0, "last_progress_at": 190.0},
            now=200.0,
        )
        waiting = services.job_runtime_health(
            {**base, "heartbeat_at": 198.0, "last_progress_at": 120.0},
            now=200.0,
        )
        stalled = services.job_runtime_health(
            {**base, "heartbeat_at": 180.0, "last_progress_at": 120.0},
            now=200.0,
        )
        terminal = services.job_runtime_health(
            {**base, "status": "failed", "running": False, "heartbeat_at": 180.0},
            now=200.0,
        )

        self.assertEqual(active["state"], "active")
        self.assertTrue(active["worker_alive"])
        self.assertEqual(waiting["state"], "waiting_external")
        self.assertTrue(waiting["worker_alive"])
        self.assertEqual(stalled["state"], "stalled")
        self.assertFalse(stalled["worker_alive"])
        self.assertEqual(terminal["state"], "terminal")

    def test_production_error_recovery_policy_retries_transient_provider_failure(self) -> None:
        policy = services.production_error_recovery_policy(
            "Page.goto: net::ERR_CONNECTION_CLOSED at https://chatgpt.com/"
        )

        self.assertTrue(policy["retryable"])
        self.assertEqual(policy["category"], "external_transient")
        self.assertEqual(policy["max_retries"], 2)

    def test_production_error_recovery_policy_keeps_login_and_gate_failures_visible(self) -> None:
        login = services.production_error_recovery_policy("ChatGPT 需要重新登录，请登录后重试")
        gate = services.production_error_recovery_policy("文案生产前闸门未通过，已停止进入下一步")

        self.assertFalse(login["retryable"])
        self.assertFalse(gate["retryable"])
        self.assertEqual(gate["category"], "configuration_or_quality")

    def test_production_error_recovery_policy_does_not_retry_missing_tts_permission(self) -> None:
        policy = services.production_error_recovery_policy(
            "当前豆包 AppID 未开通单人 TTS 资源 seed-tts-2.0"
        )

        self.assertFalse(policy["retryable"])
        self.assertEqual(policy["category"], "configuration_or_quality")

    def test_production_error_recovery_policy_does_not_retry_doubao_auth_failure(self) -> None:
        policy = services.production_error_recovery_policy(
            "豆包语音播客鉴权失败（HTTP 401）"
        )

        self.assertFalse(policy["retryable"])
        self.assertEqual(policy["category"], "configuration_or_quality")

    def test_remaining_job_steps_preserves_completed_assets(self) -> None:
        job = {
            "steps": ["audio", "subtitles", "images", "covers", "video"],
            "current_step": "images",
            "progress": [
                {"key": "audio", "status": "success"},
                {"key": "subtitles", "status": "success"},
                {"key": "images", "status": "failed"},
            ],
        }

        self.assertEqual(services.remaining_job_steps(job), ["images", "covers", "video"])

    def test_normalize_production_steps_rejects_unknown_step(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "生产步骤不存在"):
            services.normalize_production_steps(["audio", "mystery_step"])

    def test_clear_job_log_preserves_real_task_state(self) -> None:
        current = {
            "id": "job-1",
            "status": "running",
            "running": True,
            "log": "live log",
            "progress": [{"key": "audio", "status": "running"}],
            "error": "",
        }
        with (
            patch.object(storage, "load_latest_job", return_value=current),
            patch.object(storage, "write_json") as write_json,
        ):
            result = storage.clear_latest_job_log(1)

        self.assertEqual(result["status"], "running")
        self.assertTrue(result["running"])
        self.assertEqual(result["progress"], current["progress"])
        self.assertEqual(result["log"], "")
        write_json.assert_called_once()

    def test_restart_reconciliation_marks_manual_job_for_auto_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_root = root / "1"
            jobs_root = project_root / "jobs"
            jobs_root.mkdir(parents=True)
            (project_root / "project.json").write_text(
                json.dumps({"id": 1, "topic_name": "测试", "last_job_status": "running"}),
                encoding="utf-8",
            )
            (jobs_root / "latest.json").write_text(
                json.dumps(
                    {
                        "id": "job-1",
                        "status": "running",
                        "running": True,
                        "auto_recover": True,
                        "origin": "manual",
                        "steps": ["audio", "video"],
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(storage, "PROJECTS_ROOT", root):
                storage.reconcile_interrupted_project_states()
            result = json.loads((jobs_root / "latest.json").read_text(encoding="utf-8"))

        self.assertEqual(result["status"], "interrupted")
        self.assertTrue(result["resume_pending"])
        self.assertEqual(result["interruption_reason"], "service_restart")

    def test_job_runtime_resumes_restart_pending_manual_job(self) -> None:
        runtime = services.JobRuntime()
        stored = {
            "id": "job-old",
            "project_id": 77,
            "status": "interrupted",
            "running": False,
            "auto_recover": True,
            "origin": "manual",
            "resume_pending": True,
            "interruption_reason": "service_restart",
            "steps": ["audio", "subtitles", "video"],
            "current_step": "subtitles",
            "restart_resume_count": 0,
        }
        started = {**stored, "id": "job-new", "status": "running", "running": True}
        with (
            patch.object(storage, "list_projects", return_value=[{"id": 77}]),
            patch.object(storage, "load_latest_job", return_value=stored),
            patch.object(storage, "get_project", return_value={"id": 77}),
            patch.object(storage, "save_latest_job") as save_latest,
            patch.object(runtime, "start", new=AsyncMock(return_value=started)) as start,
        ):
            result = asyncio.run(runtime.resume_on_startup())

        self.assertEqual(len(result), 1)
        self.assertEqual(start.await_args.args[1], ["subtitles", "video"])
        self.assertFalse(save_latest.call_args.args[1]["resume_pending"])

    def test_production_stability_summary_uses_recent_job_history(self) -> None:
        history = [
            {"id": "a", "status": "succeeded", "started_at": 10, "finished_at": 20, "progress": []},
            {"id": "b", "status": "failed", "started_at": 30, "finished_at": 40, "progress": []},
        ]
        with patch.object(storage, "list_job_history", return_value=history):
            result = services.production_stability_summary(1)

        self.assertEqual(result["sample_count"], 2)
        self.assertEqual(result["completion_rate_percent"], 50)

    def test_current_low_quality_gate_blocks_release_readiness(self) -> None:
        report = {"overall_score": 42, "verdict": "建议先返工"}
        with (
            patch.object(storage, "get_report", return_value=report),
            patch.object(services, "quality_gate_non_video_sections_current", return_value=True),
        ):
            result = services.cached_quality_gate_state(1, "brief", "content")

        self.assertTrue(result["current"])
        self.assertEqual(result["score"], 42)
        self.assertFalse(result["release_ready"])

    def test_stale_quality_gate_blocks_release_until_rechecked(self) -> None:
        with (
            patch.object(storage, "get_report", return_value={"overall_score": 90}),
            patch.object(services, "quality_gate_non_video_sections_current", return_value=False),
        ):
            result = services.cached_quality_gate_state(1, "brief", "content")

        self.assertTrue(result["exists"])
        self.assertFalse(result["current"])
        self.assertIsNone(result["score"])
        self.assertFalse(result["release_ready"])

    def test_full_auto_parent_follows_running_project_job(self) -> None:
        runtime = services.AutoVideoRuntime()
        runtime.state = {
            "id": "auto-1",
            "status": "interrupted",
            "running": False,
            "stage": "produce",
            "project_id": 67,
            "auto_confirm_images": True,
            "queue_index": 1,
            "queue_total": 1,
            "log": "",
        }
        child = {
            "id": "job-67",
            "status": "running",
            "running": True,
            "started_at": 100.0,
            "updated_at": 198.0,
            "heartbeat_at": 198.0,
            "last_progress_at": 190.0,
            "phase_message": "正在自动修复场景图",
        }
        with (
            patch.object(services.storage, "load_latest_job", return_value=child),
            patch.object(services.storage, "now_ts", return_value=200.0),
            patch.object(runtime, "_save") as save_state,
        ):
            result = runtime.latest()

        self.assertTrue(result["running"])
        self.assertEqual(result["status"], "running")
        self.assertEqual(result["child_job_id"], "job-67")
        self.assertEqual(result["runtime_health"]["state"], "active")
        self.assertIn("自动修复场景图", result["phase_message"])
        save_state.assert_called()

    def test_full_auto_parent_finishes_when_project_video_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            final_video = root / "releases" / "final-video.mp4"
            final_video.parent.mkdir(parents=True)
            final_video.write_bytes(b"video")
            runtime = services.AutoVideoRuntime()
            runtime.state = {
                "id": "auto-2",
                "status": "interrupted",
                "running": False,
                "stage": "produce",
                "project_id": 68,
                "auto_confirm_images": True,
                "queue_index": 1,
                "queue_total": 1,
                "topic": "测试主题",
                "log": "",
            }
            child = {"id": "job-68", "status": "succeeded", "running": False}
            with (
                patch.object(services.storage, "load_latest_job", return_value=child),
                patch.object(
                    services.storage,
                    "project_file",
                    side_effect=lambda _project_id, relative: root / relative,
                ),
                patch.object(services.storage, "get_project", return_value={"topic_name": "测试主题"}),
                patch.object(
                    services.storage,
                    "list_project_files",
                    return_value=[{"relative_path": "releases/final-video.mp4"}],
                ),
                patch.object(services.storage, "project_dir", return_value=root),
                patch.object(services.storage, "now_ts", return_value=220.0),
                patch.object(runtime, "_save") as save_state,
            ):
                result = runtime.latest()

        self.assertFalse(result["running"])
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["result"]["project_id"], 68)
        self.assertFalse(result["child_job_running"])
        self.assertEqual(result["runtime_health"]["state"], "terminal")
        save_state.assert_called()

    def test_interrupted_job_stops_orphaned_running_progress(self) -> None:
        runtime = services.JobRuntime()
        stored = {
            "id": "job-old",
            "project_id": 1,
            "status": "running",
            "running": True,
            "finished_at": None,
            "log": "[gate] AI 总编改稿",
            "progress": [
                {
                    "key": "gate:content_gate",
                    "status": "running",
                    "phase": "ai_rewrite",
                    "message": "正在调用 AI 总编改稿",
                }
            ],
        }
        with (
            patch.object(services.storage, "load_latest_job", return_value=stored),
            patch.object(services.storage, "save_latest_job") as save_latest,
        ):
            result = runtime.latest(1)

        self.assertEqual(result["status"], "interrupted")
        self.assertFalse(result["running"])
        self.assertEqual(result["progress"][0]["status"], "interrupted")
        self.assertEqual(result["progress"][0]["phase"], "interrupted")
        self.assertIn("已经停止", result["progress"][0]["message"])
        save_latest.assert_called_once()

    def test_failed_job_recovers_specific_error_for_progress_card(self) -> None:
        runtime = services.JobRuntime()
        stored = {
            "id": "job-failed",
            "project_id": 56,
            "status": "failed",
            "running": False,
            "finished_at": 123.0,
            "log": "[images] 已生成 1/7\n[job] 任务失败：[WinError 5] 拒绝访问: '.project.json.tmp' -> 'project.json'",
            "progress": [
                {
                    "key": "images_missing",
                    "status": "failed",
                    "phase": "failed",
                    "message": "任务执行失败，当前步骤已经停止，请查看日志后重试。",
                }
            ],
        }
        with (
            patch.object(services.storage, "load_latest_job", return_value=stored),
            patch.object(services.storage, "save_latest_job") as save_latest,
        ):
            result = runtime.latest(56)

        self.assertIn("Windows 暂时占用", result["error"])
        self.assertEqual(result["progress"][0]["status"], "failed")
        self.assertIn("失败原因", result["progress"][0]["message"])
        save_latest.assert_called_once()

    def test_clipboard_fallback_preserves_unicode_prompt(self) -> None:
        prompt = "真实家庭场景，中文提示词不能乱码。"
        with (
            patch.object(services.os, "name", "nt"),
            patch.object(services, "_copy_text_to_windows_clipboard", return_value=False),
            patch.object(services.subprocess, "run") as run,
        ):
            run.return_value.returncode = 0
            copied = services.copy_text_to_clipboard(prompt)

        self.assertTrue(copied)
        command = run.call_args.args[0]
        self.assertIn("-EncodedCommand", command)
        script = base64.b64decode(command[-1]).decode("utf-16-le")
        encoded_prompt = script.split("FromBase64String('", 1)[1].split("')", 1)[0]
        self.assertEqual(base64.b64decode(encoded_prompt).decode("utf-8"), prompt)

    def test_rhythm_enhancement_does_not_append_topic_callback(self) -> None:
        script = """【主播】智能家居装得越多，家里就一定越聪明吗？
【主播】两年后，有些设备可能连灯都打不开。
【主播】真正的问题不是硬件坏了，而是服务停了。
【主播】第一，设备依赖厂商自己的云端。
【主播】第二，不同品牌各用各的协议。
【主播】比如一个客厅可能要装三个 App。
【主播】第三，小品牌停止维护后功能会逐步失效。
【主播】现在就去检查设备，把截图发评论区。
【主播】你准备买哪款？发出来我帮你看看。
【主播】评论区告诉我你遇到的是哪一种情况。"""

        enhanced, stats = services.enhance_script_section_rhythm(
            script,
            "智能家居变电子垃圾？避坑指南",
            "video",
        )
        self.assertEqual(enhanced.count("评论区"), 1)
        self.assertNotIn("你家哪件智能设备已经吃灰或变砖", enhanced)
        self.assertGreaterEqual(stats["interaction_removed"], 2)
        self.assertFalse(stats["interaction_added"])

    def test_rhythm_enhancement_never_inserts_generic_bridge(self) -> None:
        script = "\n".join(
            [
                "【主播】第一条事实说明市场份额发生变化。",
                "【主播】第二条事实解释变化来自产品节奏。",
                "【主播】第三条事实说明用户换机周期延长。",
                "【主播】第四条事实给出消费者能采用的判断。",
                "【主播】最后用这个判断决定是否换机。",
            ]
        )

        enhanced, stats = services.enhance_script_section_rhythm(script, "手机市场变化", "video")

        self.assertEqual(stats["bridge_count"], 0)
        self.assertNotIn("先别急", enhanced)
        self.assertNotIn("关键还没出现", enhanced)

    def test_tts_sanitizer_does_not_append_missing_cta(self) -> None:
        text = "证据已经说明差距来自换机周期。\n买之前先看真实体验，不要只看品牌。"

        sanitized = services.sanitize_tts_delivery_text(text, "手机市场变化")

        self.assertEqual(sanitized.replace("。", ""), text.replace("。", ""))
        self.assertNotIn("评论区", sanitized)

    def test_script_repair_normalizes_structure_labels_without_new_copy(self) -> None:
        script = """【先给结论】市场份额已经发生变化。
【那问题来了】原因是换机周期拉长。
【最后问你一句】买之前先看真实体验。"""

        repaired, hits = services.rewrite_script_section_bad_phrases(script, "手机市场变化", "video")

        self.assertEqual(repaired.count("【主播】"), 3)
        self.assertNotIn("【先给结论】", repaired)
        self.assertNotIn("【那问题来了】", repaired)
        self.assertNotIn("【最后问你一句】", repaired)
        self.assertIn("结构标签归一为主播", hits)

    def test_opening_cleaner_preserves_normal_sentence_punctuation(self) -> None:
        spoken = "苹果排第二，但身后只差1.3个百分点。"

        repaired, hits = services.strip_weak_opening_prefix(spoken)

        self.assertEqual(repaired, spoken)
        self.assertEqual(hits, [])

    def test_inserted_angle_change_counts_as_retention_push(self) -> None:
        signal = services.rhythm_signal_for_line("这里换个角度看，问题就清楚了。", 10, 20)
        self.assertEqual(signal, "push")

    def test_dashboard_marks_old_content_gate_result_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            content_path = Path(temp_dir) / "content.md"
            content_path.write_text("new content", encoding="utf-8")
            old_report = {
                "gates": {
                    "content_gate": {
                        "key": "content_gate",
                        "label": "文案生产前闸门",
                        "status": "failed",
                        "score": 48,
                        "passed": False,
                        "checked_at": 1,
                        "issues": [],
                        "details": {},
                    }
                }
            }
            with (
                patch.object(services.storage, "get_report", return_value=old_report),
                patch.object(services.storage, "get_project", return_value={"topic_name": "测试"}),
                patch.object(services.storage, "project_file", return_value=content_path),
            ):
                dashboard = services.production_stage_gates_dashboard(1)

        content_gate = dashboard["ordered_gates"][0]
        self.assertEqual(content_gate["status"], "stale")
        self.assertTrue(content_gate["stale"])
        self.assertIn("旧分数", content_gate["issues"][0]["fix"])

    def test_dashboard_blocks_downstream_gates_until_content_passes(self) -> None:
        old_report = {
            "gates": {
                "content_gate": {
                    "key": "content_gate",
                    "label": "文案生产前闸门",
                    "status": "failed",
                    "score": 81,
                    "passed": False,
                    "source_fingerprint": "current",
                    "issues": [],
                    "details": {},
                },
                "visual_prompt_gate": {
                    "key": "visual_prompt_gate",
                    "label": "新图生成前提示词闸门",
                    "status": "passed",
                    "score": 92,
                    "passed": True,
                    "source_fingerprint": "current",
                    "issues": [],
                    "details": {},
                },
            }
        }
        with (
            patch.object(services.storage, "get_report", return_value=old_report),
            patch.object(services.storage, "get_project", return_value={"topic_name": "测试"}),
            patch.object(services, "stage_gate_source_fingerprint", return_value="current"),
        ):
            dashboard = services.production_stage_gates_dashboard(1)

        content_gate, visual_gate, video_gate = dashboard["ordered_gates"]
        self.assertEqual(content_gate["status"], "failed")
        self.assertEqual(visual_gate["status"], "blocked")
        self.assertEqual(visual_gate["blocked_by"], "content_gate")
        self.assertFalse(visual_gate["passed"])
        self.assertEqual(video_gate["status"], "blocked")
        self.assertEqual(video_gate["blocked_by"], "content_gate")

    def test_dashboard_opens_visual_gate_after_content_passes(self) -> None:
        old_report = {
            "gates": {
                "content_gate": {
                    "key": "content_gate",
                    "label": "文案生产前闸门",
                    "status": "passed",
                    "score": 90,
                    "passed": True,
                    "source_fingerprint": "current",
                    "issues": [],
                    "details": {},
                }
            }
        }
        with (
            patch.object(services.storage, "get_report", return_value=old_report),
            patch.object(services.storage, "get_project", return_value={"topic_name": "测试"}),
            patch.object(services, "stage_gate_source_fingerprint", return_value="current"),
        ):
            dashboard = services.production_stage_gates_dashboard(1)

        content_gate, visual_gate, video_gate = dashboard["ordered_gates"]
        self.assertTrue(content_gate["passed"])
        self.assertEqual(visual_gate["status"], "pending")
        self.assertNotIn("blocked_by", visual_gate)
        self.assertEqual(video_gate["status"], "blocked")
        self.assertEqual(video_gate["blocked_by"], "visual_prompt_gate")

    def test_chatgpt_web_and_desktop_handoffs_are_separate(self) -> None:
        legacy_env = {"CHATGPT_IMAGE_OPEN_TARGET": "both"}
        web = services.resolve_image_provider_queue({"IMAGE_PROVIDER": "chatgpt_web_handoff", **legacy_env})[0]
        desktop = services.resolve_image_provider_queue({"IMAGE_PROVIDER": "chatgpt_desktop_handoff", **legacy_env})[0]

        self.assertEqual(web["key"], "chatgpt_web_handoff")
        self.assertEqual(web["label"], "ChatGPT 网页接力")
        self.assertEqual(services.resolve_chatgpt_handoff_target(legacy_env, web["key"]), "web")
        self.assertEqual(desktop["key"], "chatgpt_desktop_handoff")
        self.assertEqual(desktop["label"], "ChatGPT Classic 手动接力")
        self.assertEqual(services.resolve_chatgpt_handoff_target(legacy_env, desktop["key"]), "desktop")

    def test_chatgpt_desktop_handoff_does_not_open_web(self) -> None:
        env = {
            "CHATGPT_IMAGE_AUTO_OPEN": "true",
            "CHATGPT_IMAGE_WEB_URL": "https://chatgpt.com/",
            "CHATGPT_IMAGE_DESKTOP_PATH": "chatgpt://",
        }
        with (
            patch.object(services, "copy_text_to_clipboard"),
            patch.object(services.os, "startfile", create=True) as startfile,
        ):
            services.open_chatgpt_handoff(
                Path("handoff.html"),
                env,
                "prompt",
                open_target="desktop",
            )

        startfile.assert_called_once_with("chatgpt://")

    def test_chatgpt_web_handoff_does_not_open_desktop(self) -> None:
        env = {
            "CHATGPT_IMAGE_AUTO_OPEN": "true",
            "CHATGPT_IMAGE_WEB_URL": "https://chatgpt.com/",
            "CHATGPT_IMAGE_DESKTOP_PATH": "chatgpt://",
        }
        with (
            patch.object(services, "copy_text_to_clipboard"),
            patch.object(services.os, "startfile", create=True) as startfile,
        ):
            services.open_chatgpt_handoff(
                Path("handoff.html"),
                env,
                "prompt",
                open_target="web",
            )

        self.assertEqual(
            [call.args[0] for call in startfile.call_args_list],
            ["handoff.html", "https://chatgpt.com/"],
        )

    def test_chatgpt_handoff_preserves_reviewed_semantic_prompt(self) -> None:
        prompt = """本期主题：智能手表测血氧？别信
当前完整口播：手表显示93%，医用血氧仪显示98%，手指停在120拨号键上。
选定视觉概念：同一只手上的两台设备与拨号动作形成真实测量冲突。
本镜任务：呈现读数反差和动作悬念
创作边界：只服务当前口播。
创作自由：由 AI 选择画面表达。
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "s_01.png"
            with (
                patch.object(services, "optimize_visual_generation_prompt", side_effect=AssertionError("不应二次改写")),
                patch.object(services.storage, "write_text"),
                patch.object(services, "write_chatgpt_handoff_page", return_value=Path(temp_dir) / "handoff.html"),
                patch.object(services, "open_chatgpt_handoff", return_value=True),
            ):
                result = services.prepare_chatgpt_handoff_request(
                    prompt,
                    output_path,
                    "2560x1440",
                    "scene",
                    {},
                    provider_key="chatgpt_web_handoff",
                )

        self.assertEqual(result["prompt"], services.normalize_image_prompt(prompt))
        self.assertIn("选定视觉概念：同一只手上的两台设备", result["prompt"])

    def test_scene_additional_requirement_survives_provider_compaction(self) -> None:
        prompt = """本期主题：百万豪车急刹测试
当前完整口播：三台测试车在急刹时踏板支架断裂。
本镜画面：汽车测试场内的急刹测试与踏板机构特写。
追加要求：车型为MPV
"""

        compacted = services.lightweight_scene_model_prompt(prompt, max_chars=680)
        outbound = services.build_chatgpt_handoff_prompt(compacted, "2560x1440", "scene")

        self.assertIn("追加要求（最高优先级）：车型为MPV", compacted)
        self.assertIn("追加要求（最高优先级）：车型为MPV", outbound)

    def test_long_first_sentence_requires_rewrite(self) -> None:
        content = """# 测试

## 口播脚本

【主播】你一个人在家门铃突然响了外面的人说免费清洗油烟机还说是街道安排的这时候到底应该怎么办你可能觉得开门看看也没关系
【主播】但结果比你想的更危险。
【主播】有人因此损失了5000元。
【主播】比如骗子会先用低价清洁剂演示。
【主播】更狠的还在后面。
【主播】他们还会套取家庭信息。
【主播】你觉得这就结束了吗？
【主播】其实同伙可能正在翻抽屉。
【主播】最后记住先核实身份。
【主播】你家装了可视门铃吗？评论区扣1。
"""
        report = services.content_engagement_report(content, "video")
        self.assertGreater(report["first_line_chars"], 42)
        self.assertTrue(report["needs_rewrite"])
        self.assertLess(report["opening_score"], services.CONTENT_OPENING_MIN_SCORE)

    def test_danger_and_loss_language_counts_as_an_opening_hook(self) -> None:
        content = """# 测试

## 口播脚本

【主播】就这？我差点被手表送进医院，血氧只有93%。
【主播】医用血氧仪一夹却是98%。
【主播】这块表到底是救我还是害我？
【主播】真正的问题藏在检测原理里。
【主播】你踩过这种坑吗？评论区告诉我。
"""

        report = services.content_engagement_report(content, "video")

        self.assertGreaterEqual(report["opening_score"], services.CONTENT_OPENING_MIN_SCORE)

    def test_scene_action_time_collision_counts_as_an_opening_hook(self) -> None:
        content = """# 测试

## 口播脚本

【主播】火锅还没夹起来，广告先弹到脸上。
【主播】手机明明放在桌边，刚聊过的餐厅却出现在推荐页。
【主播】这不是巧合，也不等于手机一直在偷听。
【主播】真正起作用的是广告标识、浏览记录和位置画像。
【主播】关掉个性化广告后，再看推荐发生了什么变化。
【主播】你遇到过最离谱的弹窗是什么？评论区只写一个经历。
"""

        report = services.content_engagement_report(content, "video")

        self.assertGreaterEqual(report["opening_score"], services.CONTENT_OPENING_MIN_SCORE)
        self.assertEqual(
            report["semantic_hook_signals"],
            {"scene_action": True, "temporal_contrast": True, "perspective_contrast": False},
        )
        self.assertNotIn("开头钩子", {item["where"] for item in report["issues"]})
        self.assertEqual(services.rhythm_signal_for_line("火锅还没夹起来，广告先弹到脸上。", 0, 6), "hook")

    def test_opening_scene_without_viewer_stake_requires_rewrite(self) -> None:
        content = """# 测试

## 口播脚本

【主播】一家咖啡店，没有咖啡师，也没有店员。
【主播】负责冲咖啡的是机器人。
【主播】机械臂正在磨豆、萃取和打奶泡。
【主播】这是媒体探访的一家无人咖啡店。
【主播】每个步骤都有固定参数。
【主播】机器可以稳定完成动作。
【主播】店里仍然需要维护设备。
【主播】这就是无人咖啡店。
"""

        report = services.content_engagement_report(content, "video")

        self.assertFalse(report["opening_has_stake"])
        self.assertTrue(report["needs_rewrite"])
        self.assertIn("开头利害关系", {item["where"] for item in report["issues"]})

    def test_opening_scene_with_job_cost_has_viewer_stake(self) -> None:
        content = """# 测试

## 口播脚本

【主播】AI抢工作的第一站，可能不是办公室，而是你楼下的咖啡店。
【主播】吧台后少掉的不是一双手，而是一个原本需要排班发工资的岗位。
【主播】负责出杯的机械臂，正在把咖啡师最标准化的那部分工作接过去。
【主播】公开报道显示，无人咖啡店已经进入真实经营场景。
【主播】老板得到的是稳定出杯和更低排班成本。
【主播】顾客得到的是更快、更便宜的咖啡。
【主播】真正没人替他算账的，是原来站在吧台后的人。
【主播】技术进步没有错，但转型成本由谁承担，才是这件事最值得追问的地方。
"""

        report = services.content_engagement_report(content, "video")

        self.assertTrue(report["opening_has_stake"])
        self.assertIn("工作", report["opening_stake_hits"])
        self.assertNotIn("开头利害关系", {item["where"] for item in report["issues"]})

    def test_attention_capture_opening_counts_as_audience_stake(self) -> None:
        content = """# 测试

## 口播脚本

【主播】你妈最近是不是半夜都在刷手机？别怪她，她很可能被“红果”绑票了。
【主播】那部让她停不下来的剧，你可能看不上，名字又长又土。
【主播】但我跟你说个数：15天，60亿播放。
【主播】真正变化的是内容平台争夺注意力的方式。
【主播】平台用免费短剧换来了更长的使用时间。
【主播】用户以为自己只看一集，结果一集接着一集。
【主播】这套模式正在改变内容行业的流量分配。
【主播】判断一个平台值不值得警惕，先看它怎样占用你的时间。
"""

        report = services.content_engagement_report(content, "video")
        assessment = services.generated_content_quality_assessment(content, "video")

        self.assertTrue(report["opening_has_stake"])
        self.assertTrue(report["opening_stake_signals"]["audience_linked"])
        self.assertTrue(report["opening_stake_signals"]["attention_cost"])
        self.assertTrue(report["opening_stake_signals"]["involuntary_impact"])
        self.assertNotIn("开头利害关系", {item["where"] for item in report["issues"]})
        self.assertNotEqual(assessment["warning"], "开头吸引力偏弱")

    def test_descriptive_scene_without_consequence_keeps_stake_warning_precise(self) -> None:
        content = """# 测试

## 口播脚本

【主播】不是咖啡师，机器人30秒就做完一杯咖啡！
【主播】吧台后面没有店员，这到底是怎么做到的？
【主播】机械臂正在磨豆和打奶泡。
【主播】每一步都有固定参数。
【主播】机器可以稳定完成动作。
【主播】店里仍然需要维护设备。
【主播】这是媒体报道的新门店。
【主播】这就是无人咖啡店。
"""

        assessment = services.generated_content_quality_assessment(content, "video")

        self.assertFalse(assessment["engagement"]["opening_has_stake"])
        self.assertIn("开头与观众的利害关系不明确", assessment["warning"])

    def test_media_reporting_counts_as_viewer_value_evidence(self) -> None:
        content = """# 测试

## 口播脚本

【主播】AI抢工作的第一站，可能是你楼下的咖啡店。
【主播】媒体实地探访发现，机械臂已经能独立完成磨豆、萃取和打奶泡。
【主播】公开报道里的记者看到，店内只保留设备维护和补料人员。
【主播】这说明最先被机器接走的，是重复、标准化、容易量化的动作。
【主播】老板省下排班成本，顾客得到稳定出杯，但咖啡师要承担转型代价。
【主播】判断自己的工作风险，先看核心任务里有多少步骤能被拆成固定参数。
【主播】如果大部分都能标准化，就该提前补上沟通、判断和现场处理能力。
【主播】机器替代的是任务，不一定是整个职业，但准备时间不会等人。
"""

        report = services.viewer_value_report(content, "video")

        self.assertGreater(report["evidence_count"], 0)

    def test_rewrite_prompt_restores_original_brief_and_references(self) -> None:
        project = {"id": 111, "template": "科技情报站", "topic_name": "AI抢走咖啡师工作"}
        template = {"key": "科技情报站", "name": "科技情报站", "mode": "video"}
        content = """# 测试

## 口播脚本

【主播】无人咖啡店里，机器人正在冲咖啡。
"""
        report = {
            "issues": [
                {
                    "where": "开头利害关系",
                    "issue": "没有说明影响谁。",
                    "fix": "把岗位和转型成本提前。",
                }
            ]
        }
        with (
            patch.object(services, "channel_learning_prompt_block", return_value=""),
            patch.object(services.episode_review, "attach_guidance", side_effect=lambda messages, _project: messages),
        ):
            messages = services.compose_deepseek_rewrite_messages(
                project,
                template,
                content,
                report,
                brief="老板省下成本，但被替代的人转型费用由谁承担",
                references=[
                    {
                        "title": "媒体探访无人咖啡店",
                        "snippet": "机械臂完成磨豆、萃取和打奶泡。",
                        "url": "https://example.com/report",
                    }
                ],
            )

        prompt = messages[-1]["content"]
        self.assertIn("本期原始创作意图", prompt)
        self.assertIn("转型费用由谁承担", prompt)
        self.assertIn("本期可追溯事实", prompt)
        self.assertIn("媒体探访无人咖啡店", prompt)
        self.assertIn("可以重排叙事顺序", messages[0]["content"])
        self.assertNotIn("你的任务不是改结构", messages[0]["content"])

    def test_viewer_value_report_rejects_structured_but_empty_narration(self) -> None:
        content = """# 测试

## 对话脚本

【女】很多时候，表面现象已经很明显了。
【男】真正决定结果的，往往是后面那个小动作。
【女】关键其实藏在另一层？
【男】这就有意思了，换个角度来看就会发现不同。
【女】那下一步呢？
【男】从本质上说，要先找那个真正决定结果的点。
【女】所以事情没那么简单。
【男】下次碰到类似情况，先别急着下结论。
"""

        report = services.viewer_value_report(content, "video")

        self.assertTrue(report["needs_rewrite"])
        self.assertLess(report["value_score"], 62)
        self.assertIn("真正决定结果", report["vague_hits"])

    def test_viewer_value_report_accepts_fact_explanation_and_action(self) -> None:
        content = """# 测试

## 口播脚本

【主播】手机刚聊过餐厅，广告就跟过来了，真是麦克风在偷听吗？
【主播】先看一个事实：广告平台会读取位置、搜索记录和广告标识。
【主播】比如你和朋友连过同一个商场网络，系统就可能把你们归进相近人群。
【主播】说白了，它不一定听见聊天，也能根据这些线索猜中你想买什么。
【主播】这意味着，关麦克风权限不等于关掉个性化推荐。
【主播】你可以先关闭个性化广告，再清除广告标识，连续观察几天推荐有没有变化。
【主播】判断重点不是“它猜中了”，而是这个应用到底拿到了哪些权限和记录。
【主播】你遇到过最离谱的一次精准推荐是什么？
"""

        report = services.viewer_value_report(content, "video")

        self.assertFalse(report["needs_rewrite"])
        self.assertGreaterEqual(report["value_score"], 62)
        self.assertGreaterEqual(report["plain_score"], 72)

    def test_audience_resonance_rejects_abstract_explanation_without_real_stakes(self) -> None:
        content = """# 测试

## 口播脚本

【主播】这个现象背后有一套复杂机制。
【主播】表面看是一个问题，实际还有另一层。
【主播】首先要理解系统如何运转。
【主播】然后再分析不同环节。
【主播】这件事值得进一步关注。
【主播】最后要形成自己的认识。
"""

        report = services.audience_resonance_report(content, "video")

        self.assertTrue(report["needs_rewrite"])
        self.assertIn("大众共鸣", {item["where"] for item in report["issues"]})
        self.assertIn("情绪来源", {item["where"] for item in report["issues"]})

    def test_audience_resonance_accepts_shared_stake_and_honest_disagreement(self) -> None:
        content = """# 测试

## 口播脚本

【主播】手机刚聊过餐厅，广告就追过来，你会不会也觉得隐私被偷走了？
【主播】有人觉得授权换方便很正常，另一边担心平台知道得太多。
【主播】先看事实：广告平台会读取位置、搜索记录和广告标识。
【主播】比如一家人连过同一个商场网络，推荐就可能变得很像。
【主播】说白了，它不一定偷听，也能猜中你想买什么。
【主播】判断重点不是广告准不准，而是应用拿到了哪些权限和记录。
【主播】你可以关闭个性化广告，再观察几天推荐变化。
"""

        report = services.audience_resonance_report(content, "video")

        self.assertFalse(report["needs_rewrite"])
        self.assertTrue(report["has_honest_disagreement"])
        self.assertGreaterEqual(report["score"], 70)

    def test_robot_data_does_not_select_privacy_resonance_contract(self) -> None:
        contract = services.audience_resonance_contract(
            "人形机器人离工业应用还有多远",
            "机器人需要积累训练数据，进入陌生环境后独立完成任务。",
        )

        self.assertNotIn("隐私", contract["shared_stake"])
        self.assertIn("结果", contract["shared_stake"])

    def test_callout_from_current_scene_evidence_is_not_cross_scene_pollution(self) -> None:
        context = {
            "topic": "人形机器人离工业应用还有多远",
            "speech": "换个环境，它还能不能自己把事干成",
            "audio_anchor": "换个环境，它还能不能自己把事干成",
            "visual_director": "陌生环境任务测试",
            "source_information_text": "下次看到机器人演示，先问一句：换间屋子，它还行吗",
        }
        report = services.image_semantic_score(
            "机器人进入陌生厨房执行任务，来源支撑信息：先问一句，换间屋子它还行吗",
            context,
        )

        self.assertNotIn("先问一句", report["foreign_callouts"])

    def test_local_supervisor_converts_five_point_engagement_to_percent(self) -> None:
        with (
            patch.object(services.storage, "get_project", return_value={"topic_name": "别信手表血氧", "template": "test", "template_mode": "video"}),
            patch.object(services.storage, "get_template", return_value={"mode": "video", "release_tags": ["科技"]}),
            patch.object(services.storage, "get_brief", return_value="反差测试"),
            patch.object(services.storage, "get_references", return_value=[{}, {}, {}]),
            patch.object(services.storage, "scene_status", return_value={"expected_count": 5, "generated_count": 5}),
            patch.object(services, "summarize_content", return_value={"hook": "差点出事", "publish_title": "别信手表血氧", "interaction": "说说你的经历"}),
            patch.object(services, "content_engagement_report", return_value={"overall_score": 4.1, "opening_score": 4.2, "retention_score": 4.0, "interaction_score": 4.1}),
            patch.object(services, "image_prompt_layer_report", return_value={"metrics": {"avg_layer_score": 82, "weak_prompt_count": 0}}),
            patch.object(services, "visual_director_quality_report", return_value={"score": 84}),
            patch.object(services, "video_quality_report", return_value={"score": 80, "metrics": {"subtitle_coverage": 1.0}}),
        ):
            report = services.local_ai_supervisor_report(51, "# 测试")

        script_teacher = next(item for item in report["teachers"] if item["key"] == "script_teacher")
        self.assertEqual(script_teacher["score"], 82)
        self.assertFalse(script_teacher["blocking"])

    def test_fact_teacher_accepts_traceable_numbers_from_one_source_with_warning(self) -> None:
        references = [{"source": "news.example.com", "url": "https://news.example.com/report"}]
        with (
            patch.object(services.storage, "get_project", return_value={"topic_name": "市场变化", "template": "test", "template_mode": "video"}),
            patch.object(services.storage, "get_template", return_value={"mode": "video", "release_tags": ["科技"]}),
            patch.object(services.storage, "get_brief", return_value="来源中的市场数据"),
            patch.object(services.storage, "get_references", return_value=references),
            patch.object(services.storage, "scene_status", return_value={"expected_count": 5, "generated_count": 5}),
            patch.object(services, "summarize_content", return_value={"hook": "市场变了", "publish_title": "市场变化", "interaction": "你怎么看"}),
            patch.object(services, "content_engagement_report", return_value={"overall_score": 4.1, "opening_score": 4.2, "retention_score": 4.0, "interaction_score": 4.1}),
            patch.object(services, "image_prompt_layer_report", return_value={"metrics": {"avg_layer_score": 82, "weak_prompt_count": 0}}),
            patch.object(services, "visual_director_quality_report", return_value={"score": 84}),
            patch.object(services, "video_quality_report", return_value={"score": 80, "metrics": {"subtitle_coverage": 1.0}}),
            patch.object(services, "numeric_source_consistency_report", return_value={"passed": True, "unsupported_facts": []}),
        ):
            report = services.local_ai_supervisor_report(51, "# 市场变化\n\n## 口播脚本\n【主播】报道显示市场份额发生变化。")

        fact_teacher = next(item for item in report["teachers"] if item["key"] == "fact_teacher")
        self.assertEqual(fact_teacher["score"], 82)
        self.assertFalse(fact_teacher["blocking"])
        self.assertIn("独立来源较少", fact_teacher["suggestions"][0])

    def test_deepseek_balance_error_is_human_readable(self) -> None:
        message = services.user_facing_error("Error code: 402 - {'error': {'message': 'Insufficient Balance'}}")
        self.assertIn("DeepSeek 账户余额不足", message)
        self.assertIn("本地规则", message)

    def test_stage_gate_reports_progress_callback_events(self) -> None:
        evaluation = {
            "key": "content_gate",
            "label": "文案生产前闸门",
            "score": 86,
            "passed": True,
            "status": "passed",
            "issues": [],
            "details": {},
        }
        events = []
        with (
            patch.object(services, "evaluate_production_stage_gate", return_value=evaluation),
            patch.object(services, "save_stage_gate_result"),
        ):
            result = services.run_production_stage_gate(51, "content_gate", progress_callback=events.append)

        self.assertTrue(result["passed"])
        self.assertEqual(events[0]["phase"], "checking")
        self.assertEqual(events[-1]["phase"], "complete")

    def test_check_only_content_gate_refreshes_stale_ai_review(self) -> None:
        refreshed = {
            "key": "content_gate",
            "label": "文案生产前闸门",
            "score": 88,
            "passed": True,
            "status": "passed",
            "issues": [],
            "details": {},
        }
        with (
            patch.object(services, "authoritative_editorial_gate_result", return_value=None),
            patch.object(services, "refresh_authoritative_editorial_gate", return_value=refreshed) as refresh,
            patch.object(services, "save_stage_gate_result"),
        ):
            result = services.run_production_stage_gate(51, "content_gate", auto_fix=False)

        self.assertTrue(result["passed"])
        refresh.assert_called_once()

    def test_editorial_quality_excludes_image_prompts_and_reference_quotes(self) -> None:
        content = """# 标题

## 口播脚本
【主播】这件事可能没有你想得简单。

## 图片提示词
优先保证信息关系一眼可懂。

## 参考资料
原文写着百分百保证。
"""

        editorial = services.content_for_editorial_quality(content)

        self.assertIn("这件事可能没有你想得简单", editorial)
        self.assertNotIn("优先保证", editorial)
        self.assertNotIn("百分百保证", editorial)

    def test_editorial_quality_does_not_treat_generated_reference_section_as_authority(self) -> None:
        full_content = """# 标题

## 口播脚本
【主播】这笔协议金额是500亿美元。

## 参考资料
- [报道](https://example.com/deal) 英伟达签署500亿美元协议。
"""
        editorial = services.content_for_editorial_quality(full_content)
        project = {"id": 51, "template_mode": "video"}
        with (
            patch.object(services, "summarize_content", return_value={}),
            patch.object(services, "resolved_scene_prompt_plan", return_value=[]),
            patch.object(services, "parse_highlights", return_value=[]),
            patch.object(services, "opening_novelty_report", return_value={}),
            patch.object(services, "viral_doctor_report", return_value={}),
            patch.object(services, "title_cover_ab_report", return_value={}),
        ):
            report = services.content_audit_report(
                project,
                {},
                "",
                editorial,
                [],
                source_content=full_content,
            )

        self.assertEqual(report["metrics"]["unsupported_numeric_fact_count"], 1)
        self.assertTrue(any(item.get("where") == "数字事实依据" for item in report["issues"]))

    def test_low_nonblocking_teacher_score_is_warning_not_hard_risk(self) -> None:
        issue = services._stage_gate_teacher_issue(
            {
                "key": "topic_teacher",
                "name": "爆款选题老师",
                "score": 56,
                "blocking": True,
                "suggestions": ["继续优化标题"],
            }
        )

        self.assertIsNotNone(issue)
        self.assertEqual(issue["level"], "warn")
        self.assertTrue(
            services.stage_gate_can_continue_with_warnings(
                "content_gate",
                {"score": 56, "issues": [issue]},
            )
        )
        fact_issue = services._stage_gate_teacher_issue(
            {
                "key": "fact_teacher",
                "name": "事实合规老师",
                "score": 56,
                "blocking": True,
            }
        )
        self.assertIsNotNone(fact_issue)
        self.assertEqual(fact_issue["level"], "risk")

    def test_platform_repair_does_not_rewrite_image_prompt_instructions(self) -> None:
        content = """# 标题

## 口播脚本
【主播】这一定会出问题。

## 图片提示词
镜头优先保证信息关系一眼可懂。
"""
        with (
            patch.object(services.storage, "get_content", return_value=content),
            patch.object(services, "save_project_content_bundle", return_value={}),
        ):
            result = services.repair_project_platform_risk(51)

        self.assertTrue(result["changed"])
        self.assertIn("这很可能会出问题", result["content"])
        self.assertIn("优先保证信息关系", result["content"])
        self.assertEqual(result["hits"], ["一定会"])

    def test_semantic_scene_brief_survives_the_actual_provider_sanitizer(self) -> None:
        prompt = """本期主题：智能手表测血氧？别信
当前完整口播：我差点被一块手表送进医院，手表显示93%，指夹式血氧仪显示98%。
当前口播重点：两种设备读数形成反差
选定视觉概念：同一只手同时佩戴智能手表和指夹式血氧仪，人物正在核对读数。
本镜任务：把测量反差变成真实现场
创作边界：只服务本期主题和当前口播。
创作自由：场景、构图和信息元素由 AI 决定。
文字策略：文字必须与当前口播呼应。
"""

        sanitized = services.sanitize_prompt_for_image_model(prompt, "scene")
        handoff = services.build_chatgpt_handoff_prompt(sanitized, "2560x1440", "scene")
        integrity = services.semantic_scene_brief_integrity(prompt, sanitized)

        self.assertTrue(services.image_prompt_has_topic_anchor(prompt))
        self.assertTrue(integrity["ok"])
        self.assertIn("本期主题：智能手表测血氧？别信", sanitized)
        self.assertIn("当前完整口播：我差点被一块手表送进医院", sanitized)
        self.assertIn("选定视觉概念：同一只手同时佩戴", handoff)
        self.assertNotIn("最多保留 1 个", handoff)

    def test_image_provider_prompt_rewrites_sensitive_editorial_wording_only_at_handoff(self) -> None:
        prompt = """本期主题：红果屠城：一部你妈停不下来的剧
当前完整口播：别怪她，她很可能被红果绑票了。低质AI剧正在反噬行业，5月处置超过两万部违规作品。
本镜画面：一位中年观众深夜看手机，屏幕旁展示15天、60亿播放。
频道硬风格：成熟纸张线稿科技编辑卡通
"""

        outbound = services.build_chatgpt_handoff_prompt(prompt, "2560x1440", "scene")

        self.assertIn("红果席卷全网", outbound)
        self.assertIn("家中长辈", outbound)
        self.assertIn("牢牢吸引", outbound)
        self.assertIn("带来反作用", outbound)
        self.assertIn("5月", outbound)
        self.assertNotIn("屠城", outbound)
        self.assertNotIn("你妈", outbound)
        self.assertNotIn("绑票", outbound)
        self.assertNotIn("反噬", outbound)

    def test_all_direct_image_provider_prompt_builders_apply_the_same_boundary_rewrite(self) -> None:
        prompt = "本期主题：红果屠城；当前口播：家人被短剧绑票，低质内容正在反噬行业；事实：15天、60亿播放。"

        playground = services.build_imageai_playground_prompt(prompt, "2560x1440", "scene")
        compatible = services.make_image_prompt_provider_friendly(
            services.apply_apiyi_prompt_conventions(prompt, "2560x1440", "scene")
        )
        report = services.image_prompt_provider_friendly_report(prompt)

        for outbound in (playground, compatible, str(report["prompt"])):
            self.assertIn("红果席卷全网", outbound)
            self.assertIn("牢牢吸引", outbound)
            self.assertIn("带来反作用", outbound)
            self.assertIn("15天", outbound)
            self.assertIn("60亿播放", outbound)
            self.assertNotIn("屠城", outbound)
            self.assertNotIn("绑票", outbound)
            self.assertNotIn("反噬", outbound)
        self.assertTrue(report["rewritten"])
        self.assertGreaterEqual(int(report["count"]), 3)

    def test_outbound_scene_prompt_is_short_without_losing_topic_speech_or_facts(self) -> None:
        prompt = """本期主题：智能电视广告：你买的不是电视，是广告屏
当前完整口播：国家广电总局2025年文件写得清清楚楚，9×3品牌智能电视可以彻底关闭开机广告，不是跳过；每次15秒等待都在消耗用户时间。
当前口播重点：开机广告可以彻底关闭
选定视觉概念：客厅电视开机倒计时与遥控器操作形成前后对比，旁边放政策文件，关闭后回到干净桌面。
本镜任务：把广告倒计时、政策依据和关闭结果做成信息对比
来源支撑信息：广电总局2025文件；9×3智能电视；厂商后台关闭；用户等待时间
建议的信息结构：左侧广告倒计时，中间操作动作，右侧关闭结果
必须落进成图的信息：彻底关闭开机广告；9×3；2025文件
不可改错的数字事实：9×3、2025、15秒
数字边界：涉及结论、价格、比例、读数、时长和次数的具体数字必须来自当前口播，不虚构示例数值。
创作边界：只服务本期主题和当前口播，不借用上一镜或其它项目的信息，不改错人物、对象、数字和因果关系。
创作自由：画面风格、人物或物件、场景、构图、光线、色彩、信息载体和视觉层级均由你根据本段口播决定，不套固定模板。
视觉取舍：优先呈现当前口播里的真实动作、测试过程、实物证据、因果关系或结果反差。
信息策略：关键证据、反转和结论镜头优先采用信息主导构图。
文字策略：文字必须服务当前口播。
静音验收：只看图也能理解。
"""

        compacted = services.compile_outbound_image_prompt(prompt, "scene")
        integrity = services.semantic_scene_brief_integrity(prompt, compacted)

        self.assertLessEqual(len(compacted), 520)
        self.assertTrue(integrity["ok"])
        self.assertIn("本期主题：智能电视广告", compacted)
        self.assertIn("当前完整口播：国家广电总局2025年文件", compacted)
        self.assertIn("信息证据：", compacted)
        self.assertIn("广电总局2025文件", compacted)
        self.assertIn("2025", compacted)
        self.assertIn("15秒", compacted)
        self.assertEqual(compacted.count("创作边界："), 1)
        self.assertEqual(compacted.count("创作自由："), 1)

    def test_outbound_scene_prompt_keeps_script_evidence_under_tight_limit(self) -> None:
        prompt = """本期主题：存储芯片库存见顶了吗
当前完整口播：大摩拿13周库存吓人？花旗说这些库存数字是障眼法。
当前口播重点：13周库存可能是假象
选定视觉概念：分析师按住下跌报告，仓库与停产工厂形成因果对照。
本镜任务：把库存形成原因和后续断崖做成一个具体现场
来源支撑信息：三星6月底停掉MLC NAND模组厂；客户紧急抢货；这批库存最多撑到明年一季度，之后直接断崖；这一轮库存是挤出来的假象
建议的信息结构：停产导致抢货，抢货制造短期库存高点，随后库存断崖
必须落进成图的信息：13周库存是假象
不可改错的数字事实：13周、6月底、明年一季度
创作边界：只服务本期主题和当前口播，不串入其它镜头。
创作自由：构图和信息层级由模型决定。
排版分工（最高优先级）：后期写入标题和数字。
"""

        compacted = services.compile_outbound_image_prompt(prompt, "scene", max_chars=520)

        self.assertLessEqual(len(compacted), 520)
        self.assertIn("信息证据：", compacted)
        self.assertIn("三星6月底停掉MLC NAND模组厂", compacted)
        self.assertIn("客户紧急抢货", compacted)
        self.assertIn("库存最多撑到明年一季度", compacted)
        self.assertIn("当前完整口播：大摩拿13周库存吓人", compacted)
        self.assertIn("创作边界：", compacted)
        self.assertIn("创作自由：", compacted)

    def test_outbound_scene_prompt_rejects_adjacent_scene_typography(self) -> None:
        prompt = """本期主题：你买的是问界，还是那扇门上的两个字
当前完整口播：现有信息没有时间表，也没有说可能回落。
本镜任务：展示调整传闻存在但没有公开时间表。
主主体：问界汽车、门店日历和空白时间轴。
动作：用户检查没有发布日期的公告。
冲突/悬念：调整传闻存在，但没有公开时间表。
必须落进成图的信息：「你愿意为那两个字多付多少」
创作边界：只服务本期主题和当前口播，不借用相邻镜头的信息。
创作自由：场景和构图由当前口播决定。
"""

        compacted = services.lightweight_scene_model_prompt(prompt, max_chars=680)

        self.assertIn("原生画面文字：也没有说可能回落", compacted)
        self.assertNotIn("原生画面文字：你愿意为那两个字多付多少", compacted)

    def test_scene_composition_duplicate_ignores_different_narration(self) -> None:
        entries = [
            {
                "label": "s_08.png",
                "final_prompt": "本期主题：问界。当前完整口播：没有时间表。\n主体：用户、手机、问界门店。\n动作：用户拿手机抬头思考。\n本镜画面：门店前的人物与汽车。",
            },
            {
                "label": "s_09.png",
                "final_prompt": "本期主题：问界。当前完整口播：愿意多付多少。\n主体：用户、手机、问界门店。\n动作：用户拿手机抬头思考。\n本镜画面：门店前的人物与汽车。",
            },
        ]

        pairs = services.duplicate_scene_composition_pairs(entries)

        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["left"], "s_08.png")
        self.assertEqual(pairs[0]["right"], "s_09.png")

    def test_generic_symbolic_concept_is_rebuilt_from_current_evidence(self) -> None:
        prompt = """本期主题：存储芯片库存见顶了吗
当前完整口播：大摩拿13周库存吓人？花旗说这些库存数字是障眼法。
选定视觉概念：分析师按下暂停手势，旁边出现巨大红叉和放大镜。
本镜任务：呈现库存形成原因
来源支撑信息：三星6月底停掉MLC NAND模组厂；客户紧急抢货；库存随后断崖
创作边界：只服务本期主题和当前口播。
创作自由：构图和信息层级由模型决定。
"""

        repaired, issues = services.repair_generic_scene_visual_concept(prompt)

        self.assertIn("用抽象手势或符号代替具体冲突证据", issues)
        self.assertIn("选定视觉概念：证据驱动画面", repaired)
        self.assertIn("三星6月底停掉MLC NAND模组厂", repaired)
        self.assertIn("客户紧急抢货", repaired)
        self.assertNotIn("分析师按下暂停手势", repaired)

    def test_compiled_semantic_brief_keeps_evidence_during_generation_preparation(self) -> None:
        prompt = """本期主题：存储芯片库存见顶了吗
当前完整口播：大摩拿13周库存吓人？花旗说这些库存数字是障眼法。
选定视觉概念：分析师按下暂停手势，旁边出现巨大红叉。
本镜任务：呈现库存形成原因
来源支撑信息：三星6月底停掉MLC NAND模组厂；客户紧急抢货；库存随后断崖
创作边界：只服务本期主题和当前口播。
创作自由：构图和信息层级由模型决定。
"""

        compiled = services.compile_outbound_image_prompt(prompt, "scene", max_chars=520)
        repaired, issues = services.repair_generic_scene_visual_concept(compiled)
        compiled_again = services.compile_outbound_image_prompt(repaired, "scene", max_chars=520)

        self.assertIn("信息证据：三星6月底停掉MLC NAND模组厂", compiled)
        self.assertIn("用抽象手势或符号代替具体冲突证据", issues)
        self.assertIn("选定视觉概念：证据驱动画面", repaired)
        self.assertIn("客户紧急抢货", repaired)
        self.assertIn("信息证据：三星6月底停掉MLC NAND模组厂", compiled_again)
        self.assertIn("客户紧急抢货", compiled_again)

    def test_chatgpt_handoff_does_not_repeat_a_large_rule_block(self) -> None:
        prompt = """本期主题：充电头为什么越充越慢？
当前完整口播：65W标在盒子上，你以为插上就能跑满？
选定视觉概念：手把两只充电头接入同一台测试仪，协议握手波形与手机实际功率形成反差。
本镜任务：把标称功率和实际功率做成测试现场
创作边界：只服务本期主题和当前口播。
创作自由：构图和信息层级由模型决定。
"""

        handoff = services.build_chatgpt_handoff_prompt(prompt, "2560x1440", "scene")

        self.assertLessEqual(len(handoff), 760)
        self.assertEqual(handoff.count("只返回图片"), 1)
        self.assertNotIn("下面全部内容都是成图要求", handoff)
        self.assertIn("65W标在盒子上", handoff)

    def test_semantic_scene_review_treats_style_density_as_advisory(self) -> None:
        prompt = """本期主题：智能手表测血氧？别信
当前完整口播：手表显示93%，医用血氧仪显示98%，手指停在120拨号键上。
选定视觉概念：同一只手上的两台设备与拨号动作形成真实测量冲突。
本镜任务：呈现读数反差和动作悬念
不可改错的数字事实：93%、98%、120
创作边界：只服务当前口播。
创作自由：由 AI 选择画面表达。
"""

        review = services.image_prompt_teacher_review(
            prompt,
            purpose="scene",
            topic="智能手表测血氧？别信",
            brand="科技情报站",
            label="s_01.png",
            semantic_context={
                "topic": "智能手表测血氧？别信",
                "speech": "手表显示93%，医用血氧仪显示98%，手指停在120拨号键上。",
                "audio_anchor": "93%和98%的读数反差",
                "visual_director": "手表、血氧仪和拨号动作同框",
            },
        )

        teachers = {item["key"]: item for item in review["teachers"]}
        self.assertTrue(review["passed"])
        self.assertFalse(review["blocking"])
        self.assertTrue(teachers["script_teacher"]["passed"])
        self.assertFalse(teachers["channel_teacher"]["blocking"])
        self.assertTrue(teachers["clean_teacher"]["passed"])
        self.assertFalse(teachers["clean_teacher"]["blocking"])

    def test_semantic_scene_review_still_blocks_cross_topic_prompt(self) -> None:
        review = services.image_prompt_teacher_review(
            "当前完整口播：老人先别开门。画面是一台智能手表显示93%。",
            purpose="scene",
            topic="免费上门清洗油烟机骗局",
            brand="生活防骗",
            label="s_01.png",
            semantic_context={
                "topic": "免费上门清洗油烟机骗局",
                "speech": "穿工作服的人敲门，老人先别开门。",
                "audio_anchor": "老人先别开门",
                "visual_director": "猫眼、清洁桶、门把手",
            },
        )

        self.assertFalse(review["passed"])
        self.assertTrue(review["blocking"])

    def test_repair_legacy_mojibake_restores_scene_prompt(self) -> None:
        source = "\u672c\u671f\u4e3b\u9898\uff1a\u522b\u4e3aAI\u53c2\u6570\u591a\u638f\u94b1\n\u5f53\u524d\u5b8c\u6574\u53e3\u64ad\uff1a\u603b\u53c2\u6570284B\uff0c\u53ea\u919213B"
        broken = source.encode("gb18030").decode("latin1")

        repaired = services.repair_legacy_mojibake(broken)

        self.assertEqual(repaired, source)

    def test_repair_legacy_mojibake_restores_utf8_decoded_as_cp1252(self) -> None:
        source = "# 短标题"
        broken = source.encode("utf-8").decode("cp1252")

        repaired = services.repair_legacy_mojibake(broken)

        self.assertEqual(repaired, source)

    def test_locked_topic_references_drop_parallel_tech_news(self) -> None:
        topic = "具身智能，在物理世界中成长（院士讲科普·未来产业） --经济·科技--人民网"
        brief = (
            "## 参考资料\n"
            "- [Sat, 08 Aug 2026 / live] 具身智能，在物理世界中成长："
            "智能进入现实世界并持续学习。 http://gd.people.com.cn/article.html\n"
        )
        references = services.brief_reference_candidates(brief, topic) + [
            {"title": "AI wearable watches you", "snippet": "A blood pressure watch", "url": "https://example.com/watch"},
            {"title": "Is Embodied AI the next computing revolution?", "snippet": "Physical systems", "url": "https://example.com/embodied"},
        ]

        filtered = services.filter_references_for_locked_topic(references, topic, limit=8)
        titles = [item["title"] for item in filtered]

        self.assertTrue(any("具身智能" in title for title in titles))
        self.assertTrue(any("Embodied AI" in title for title in titles))
        self.assertFalse(any("wearable" in title for title in titles))

    def test_locked_brief_removes_aggregator_parallel_story(self) -> None:
        topic = "具身智能，在物理世界中成长（院士讲科普·未来产业） --经济·科技--人民网"
        brief = (
            "## 参考资料\n"
            "- [live] 具身智能，在物理世界中成长：智能进入现实世界。 https://example.com/main\n"
            "- [live] 人民日报图文数据库：具身智能，在物理世界中成长；跑马拉松是对机器人的压力测试。 https://example.com/layout\n"
        )

        sanitized = services.sanitize_locked_topic_brief(brief, topic)

        self.assertIn("https://example.com/main", sanitized)
        self.assertNotIn("https://example.com/layout", sanitized)

    def test_single_interaction_action_drops_follow_and_topic_order(self) -> None:
        spoken = "你最想让机器人做什么？评论区聊聊。关注科技情报站，下期想看啥，点单。"

        repaired, changed = services.trim_to_single_interaction_action(spoken)

        self.assertTrue(changed)
        self.assertEqual(repaired, "你最想让机器人做什么？评论区聊聊。")

    def test_semantic_scene_brief_integrity_rejects_truncated_outbound_prompt(self) -> None:
        source = """本期主题：智能手表测血氧？别信
当前完整口播：手表显示93%，指夹式血氧仪显示98%。
本镜任务：呈现真实测量反差
创作边界：只服务当前口播。
创作自由：由 AI 选择画面表达。
"""

        result = services.semantic_scene_brief_integrity(source, "可读视觉钩子：93%、98%")

        self.assertFalse(result["ok"])
        self.assertIn("本期主题", result["missing"])
        self.assertIn("当前完整口播", result["missing"])

    def test_semantic_scene_brief_integrity_accepts_budgeted_long_topic(self) -> None:
        source = """本期主题：美股科技巨头遭财报杀，公募前七月业绩大洗牌与长期资金调仓
当前完整口播：钱没消失，只是换赛道。
本镜任务：画出资金从旧赛道转向新赛道。
创作边界：只服务本期主题和当前口播。
创作自由：自由设计具体画面。"""
        outbound = """本期主题：美股科技巨头遭财报杀，公募前七月业绩大洗牌
当前完整口播：钱没消失，只是换赛道。
本镜画面：资金从旧赛道转向新赛道。
文字策略：文字完整可读。"""

        result = services.semantic_scene_brief_integrity(source, outbound)

        self.assertTrue(result["ok"])
        self.assertGreaterEqual(result["shared_topic_prefix_length"], 12)

    def test_lightweight_scene_prompt_keeps_valid_outbound_semantic_structure(self) -> None:
        source = """本期主题：中小企业用AI客服，真的能省钱？
当前完整口播：月薪一万请客服，客户还是因为回复慢跑单。
选定视觉概念：空客服工位、月薪账单和聊天等待记录形成对比。
本镜任务：把人工成本和回复延迟放进同一真实办公场景。
创作边界：只服务当前口播。
创作自由：根据证据选择构图。
"""

        outbound = services.lightweight_scene_model_prompt(source, max_chars=420)
        result = services.semantic_scene_brief_integrity(source, outbound)

        self.assertTrue(result["ok"])
        self.assertTrue(services.is_outbound_semantic_scene_brief(outbound))
        self.assertIn("本期主题：中小企业用AI客服", outbound)
        self.assertIn("当前完整口播：月薪一万请客服", outbound)

    def test_wearable_health_is_not_classified_as_smart_home(self) -> None:
        prompt = "智能手表通过光电传感器检测血氧，和指夹式血氧仪现场对比。"

        domain = services.classify_visual_prompt_domain(prompt, "scene")
        topic_type = services.infer_visual_topic_type(prompt, "tech_cinematic", domain)

        self.assertEqual(domain, "wearable_health")
        self.assertEqual(topic_type, "wearable_health")

    def test_tech_style_does_not_force_smart_home_objects_into_wearable_scene(self) -> None:
        source = "智能手表测血氧，和指夹式血氧仪现场复测。旧缓存里曾写过中控主机和家居设备。"

        entities = services.choose_visual_entities(source, "tech_cinematic", "wearable_health", limit=3)

        joined = " ".join(entities)
        self.assertIn("智能手表", joined)
        self.assertIn("血氧仪", joined)
        self.assertNotIn("中控主机", joined)
        self.assertNotIn("家居设备", joined)

    def test_elastic_visual_decision_rejects_stale_scene_subjects(self) -> None:
        project = {"id": 51, "template": "tech", "topic_name": "智能手表测血氧？别信"}
        template = {"name": "科技情报站", "mode": "video"}
        content = "# 智能手表测血氧？别信\n\n## 口播脚本\n手表显示93%，指夹式血氧仪显示98%。\n"
        visual_brief = {
            "topic": project["topic_name"],
            "topic_type": "wearable_health",
            "topic_type_label": "可穿戴健康/测量现场",
            "style": "tech_cinematic",
            "visual_world": "真实测量现场：手腕上的智能手表、指夹式血氧仪和人物反应共同证明当前口播",
            "subject_pool": ["佩戴智能手表的手腕", "指夹式血氧仪", "真实皮肤与手指"],
            "action_pool": ["同时测量对比", "重新佩戴校准"],
            "attention_hooks": ["读数反差", "佩戴误差"],
            "scenes": [
                {
                    "dialogue_anchor": "手表显示93%，指夹式血氧仪显示98%。",
                    "primary_subjects": ["中控主机", "被联动的家居设备", "控制界面与屏幕光"],
                    "action_peak": "空间联动",
                    "tension": "真实家庭里的灯光和窗帘同时触发",
                }
            ],
        }

        decision = services.build_elastic_visual_decision(
            project,
            template,
            content,
            visual_brief,
            purpose="scene",
            target="s_01.png",
            label="场景 1",
            source_prompt="旧提示词：中控主机让家居设备空间联动",
            semantic_context={"speech": "手表显示93%，指夹式血氧仪显示98%。"},
        )

        serialized = str(decision)
        self.assertIn("智能手表", serialized)
        self.assertIn("指夹式血氧仪", serialized)
        self.assertNotIn("中控主机", serialized)
        self.assertNotIn("家居设备", serialized)
        self.assertNotIn("空间联动", serialized)

    def test_ai_visual_brief_topic_guard_replaces_foreign_domain_objects(self) -> None:
        project = {"id": 51, "topic_name": "智能手表测血氧？别信"}
        template = {"name": "科技情报站"}
        content = "# 智能手表测血氧？别信\n\n手表显示93%，指夹式血氧仪显示98%。"
        fallback = {
            "prompt_policy_version": services.IMAGE_PROMPT_POLICY_VERSION,
            "topic_type": "wearable_health",
            "topic_type_label": "可穿戴健康/测量现场",
            "visual_world": "智能手表与指夹式血氧仪的真实测量现场",
            "subject_pool": ["佩戴智能手表的手腕", "指夹式血氧仪"],
            "action_pool": ["同时测量对比"],
            "attention_hooks": ["读数反差"],
            "forbidden": [],
            "scenes": [
                {
                    "index": 1,
                    "narrative_state": "前三秒钩子/痛点",
                    "visual_type": "comparison",
                    "beat": "手表与血氧仪读数反差",
                    "dialogue_anchor": "手表显示93%，指夹式血氧仪显示98%。",
                    "primary_subjects": ["佩戴智能手表的手腕", "指夹式血氧仪"],
                    "action_peak": "同时测量对比",
                    "attention_hooks": ["93%", "98%"],
                    "tension": "同一只手出现不同读数",
                }
            ],
        }
        payload = {
            "topic_type": "smart_home",
            "topic_type_label": "智能家居",
            "visual_world": "中控主机让全屋智能设备空间联动",
            "subject_pool": ["中控主机", "被联动的家居设备"],
            "action_pool": ["空间联动"],
            "scenes": [
                {
                    "primary_subjects": ["中控主机", "被联动的家居设备"],
                    "action_peak": "空间联动",
                    "tension": "网关断开后窗帘联动失败",
                }
            ],
        }

        normalized = services.normalize_ai_visual_brief(payload, fallback, project, template, content, "test-model", 2)

        serialized = str(normalized)
        self.assertEqual(normalized["topic_type"], "wearable_health")
        self.assertIn("智能手表", serialized)
        self.assertIn("指夹式血氧仪", serialized)
        self.assertNotIn("中控主机", " ".join(normalized["subject_pool"]))
        self.assertNotIn("空间联动", " ".join(normalized["action_pool"]))
        self.assertTrue(normalized["topic_guard_rejections"])

    def test_chinese_percentage_matches_arabic_percentage_fact(self) -> None:
        context = {"speech": "手表显示百分之九十三，血氧仪显示百分之九十八。", "audio_anchor": ""}

        foreign = services.foreign_scene_numeric_facts("手表显示93%，血氧仪显示98%。", context)

        self.assertEqual(foreign, [])

    def test_visual_concept_quality_rejects_self_disqualifying_candidate(self) -> None:
        issues = services.visual_concept_quality_issues("创意图解：用玻璃和墨水展示光线受阻，但可能不符合现场质感。")

        self.assertIn("可能不符合", issues)

    def test_visual_concept_compaction_keeps_complete_clauses(self) -> None:
        concept = (
            "主体：智能手表、指夹式血氧仪、真实皮肤；"
            "动作：静息状态复测后再和运动出汗状态对比；"
            "冲突：单次读数和连续趋势给出不同判断；"
            "补充：" + "很长的环境描述" * 30
        )

        compacted = services.compact_visual_concept(concept, 90)

        self.assertIn("主体：智能手表", compacted)
        self.assertIn("动作：静息状态复测", compacted)
        self.assertNotIn("...", compacted)
        self.assertNotIn("…", compacted)

    def test_latin_dominant_prompt_is_detected_for_preservation(self) -> None:
        prompt = "Medium shot of a young man comparing a smartwatch and a medical pulse oximeter in natural window light."

        self.assertTrue(services.prompt_is_latin_dominant(prompt))

    def test_generation_prompt_integrity_rejects_truncated_english_and_empty_clause(self) -> None:
        issues = services.generation_prompt_integrity_issues(
            "人物看着智能手表。Medium shot of a young man showi。画面里有。"
        )

        self.assertIn("英文单词被截断", issues)
        self.assertTrue(any("空壳句" in item for item in issues))

    def test_manifest_prompt_review_preserves_selected_concept_without_old_text_cap(self) -> None:
        prompt = "本期主题：智能手表测血氧？别信\n选定视觉概念：手表93%与血氧仪98%同框，手指停在拨号键上。"
        semantic_context = {"speech": "手表显示93%，血氧仪显示98%。"}

        reviewed, review = services.review_manifest_generation_prompt(
            prompt,
            purpose="scene",
            topic="智能手表测血氧？别信",
            brand="科技情报站",
            label="s_01.png",
            semantic_context=semantic_context,
        )

        self.assertIn("选定视觉概念", reviewed)
        self.assertIn("手表93%与血氧仪98%同框", reviewed)
        self.assertNotIn("最多保留 1 个", reviewed)
        self.assertEqual(review["provider"], "visual-prompt-manifest")

    def test_manifest_prompt_review_adds_canonical_topic_and_scene_speech(self) -> None:
        prompt = (
            "本镜信息任务：以「只能看渠道和平台报价」为主信息。"
            "频道视觉合同：暖米白纸张线稿卡通。"
        )

        reviewed, _ = services.review_manifest_generation_prompt(
            prompt,
            purpose="scene",
            topic="官网涨了800，店里降了1300",
            brand="科技情报站",
            label="s_10.png",
            semantic_context={"speech": "那接下来你只能看渠道和平台报价。"},
        )

        self.assertIn("本期主题：官网涨了800，店里降了1300", reviewed)
        self.assertIn("当前完整口播：那接下来你只能看渠道和平台报价", reviewed)
        self.assertIn("本镜信息任务：以「只能看渠道和平台报价", reviewed)

    def test_manifest_prompt_review_removes_adjacent_scene_information(self) -> None:
        reviewed, _ = services.review_manifest_generation_prompt(
            "本镜信息任务：以「渠道报5499，是授权渠道自己的报价」为主信息。"
            "频道视觉合同：暖米白纸张线稿卡通。",
            purpose="scene",
            topic="官网涨了800，店里降了1300",
            brand="科技情报站",
            label="s_10.png",
            semantic_context={
                "speech": "那接下来你只能看渠道和平台报价。",
                "timeline_speech": "那接下来你只能看渠道和平台报价，别默认它还按以前的老规律走。",
            },
        )

        self.assertIn("当前完整口播：那接下来你只能看渠道和平台报价", reviewed)
        self.assertNotIn("渠道报5499", reviewed)

    def test_manifest_scene_prompt_survives_provider_compaction(self) -> None:
        manifest_prompt = (
            "本镜信息任务：以「如果商品已经下架，就只能看渠道和平台报价」为主信息。"
            "频道视觉合同：暖米白纸张线稿卡通；主体与信息共同占满画面。"
        )
        reviewed, _ = services.review_manifest_generation_prompt(
            manifest_prompt,
            purpose="scene",
            topic="官网涨了800，店里降了1300",
            brand="科技情报站",
            label="s_09.png",
            semantic_context={"speech": "如果它已经下架，就说明官网不再卖它了。"},
        )

        prepared = services.lightweight_scene_model_prompt(
            services.balanced_scene_generation_brief(reviewed),
            max_chars=680,
        )

        self.assertIn("本期主题：官网涨了800", prepared)
        self.assertIn("当前完整口播：如果它已经下架", prepared)
        self.assertTrue("渠道" in prepared or "下架" in prepared)
        self.assertNotEqual(prepared, "主体清楚，信息元素服从当前内容与频道画风，画面留出字幕空间")

    def test_scene_prompt_short_audio_anchor_keeps_valid_image_current(self) -> None:
        actual_prompt = "本期主题：手机价格。当前完整口播：授权渠道报价变化，先核对退货条件。"

        self.assertTrue(
            services.scene_prompt_matches_narration(
                actual_prompt,
                "你比较的从来不是两个价格，而是两套条件，退货规则也可能不同。",
                "先核对退货条件",
            )
        )

    def test_scene_prompt_unrelated_to_speech_and_anchor_is_stale(self) -> None:
        actual_prompt = "项目管理看板，数据分析图表，团队开会讨论进度。"

        self.assertFalse(
            services.scene_prompt_matches_narration(
                actual_prompt,
                "那接下来你只能看渠道和平台报价，别默认还按以前的规律走。",
                "渠道和平台报价",
            )
        )

    def test_lightweight_scene_prompt_locks_product_type_and_allowed_numbers(self) -> None:
        source = """本期主题：官网涨了800，店里降了1300
当前完整口播：你比较的不是两个价格，而是两套条件。
本期核心对象必须是：iPhone。画面主体不得被其它品类替换。
本镜任务：比较官网和门店的购买条件。
"""

        outbound = services.lightweight_scene_model_prompt(
            services.balanced_scene_generation_brief(source),
            max_chars=680,
        )

        self.assertIn("核心对象硬约束：必须清晰画出iPhone实物", outbound)
        self.assertIn("以iPhone为唯一商品主体", outbound)
        self.assertIn("禁止出现其它可售商品", outbound)
        self.assertIn("只允许出现800、1300", outbound)
        self.assertIn("禁止添加任何其它价格", outbound)

    def test_lightweight_scene_prompt_preserves_explicit_scene_composition(self) -> None:
        source = """本期主题：官网涨了800，店里降了1300
当前完整口播：你比较的不是两个价格，而是两套条件。
本期核心对象必须是：苹果iPhone手机。
本镜画面：同一款苹果iPhone手机在左右各出现一台，左侧官网页面，右侧授权门店柜台。
"""

        outbound = services.lightweight_scene_model_prompt(source, max_chars=680)

        self.assertIn("同一款苹果iPhone手机在左右各出现一台", outbound)
        self.assertIn("左侧官网页面", outbound)
        self.assertIn("右侧授权门店柜台", outbound)

    def test_lightweight_scene_prompt_uses_project132_open_composition(self) -> None:
        source = """本期主题：智能手表测血氧？别信
当前完整口播：皮肤不是玻璃，佩戴松一点、出汗、纹身和防晒都会干扰光线。
选定视觉概念：骑手戴着头盔在城市道路上查看手机导航。
"""

        outbound = services.lightweight_scene_model_prompt(source, max_chars=900)

        self.assertIn("骑手戴着头盔在城市道路上查看手机导航", outbound)
        self.assertIn("原生文字要与主体成为同一场景", outbound)
        self.assertIn("主体与证据铺满画面", outbound)
        self.assertNotIn("前景是动作触发点", outbound)
        self.assertNotIn("画面短钩子", outbound)

    def test_generation_prompt_punctuation_removes_duplicate_commas(self) -> None:
        self.assertEqual(services.clean_generation_prompt_punctuation("你说，，手表准吗。。"), "你说，手表准吗")

    def test_wearable_blueprint_follows_skin_interference_speech(self) -> None:
        blueprint = services.audio_bound_visual_blueprint(
            "皮肤不是玻璃，佩戴松一点、出汗、纹身和防晒都会干扰光线。",
            "智能手表测血氧？别信",
        )

        serialized = str(blueprint)
        self.assertIn("汗珠", serialized)
        self.assertIn("纹身", serialized)
        self.assertNotIn("家居设备", serialized)

    def test_visual_caches_expire_when_prompt_policy_changes(self) -> None:
        content = "# 智能手表测血氧？别信\n\n手表显示93%，指夹式血氧仪显示98%。"
        source_hash = services.visual_brief_source_hash(content)
        project = {"topic_name": "智能手表测血氧？别信"}
        brief = {
            "source_hash": source_hash,
            "topic": project["topic_name"],
            "scene_count": 1,
            "scenes": [{"index": 1}],
        }
        director = {
            "source_hash": source_hash,
            "edit_direction": {"scene_count": 1, "scenes": [{"index": 1}]},
            "sound_direction": {"bgm_policy_version": services.BGM_POLICY_VERSION},
        }

        self.assertFalse(services.visual_brief_is_current(brief, project, content, 1))
        self.assertFalse(services.visual_director_is_current(director, content, 1))

        brief["prompt_policy_version"] = services.IMAGE_PROMPT_POLICY_VERSION
        director["prompt_policy_version"] = services.IMAGE_PROMPT_POLICY_VERSION

        self.assertTrue(services.visual_brief_is_current(brief, project, content, 1))
        self.assertTrue(services.visual_director_is_current(director, content, 1))

    def test_visual_prompt_manifest_binds_channel_episode_content_and_scene(self) -> None:
        project = {"id": 51, "template": "tech", "topic_name": "智能手表测血氧？别信"}
        content = "# 血氧数据别信\n\n## 口播脚本\n手表显示93%，指夹式血氧仪显示98%。\n"
        with patch.object(services, "visual_timeline_signature", return_value="timeline-a"):
            identity = services.visual_prompt_manifest_identity(project, content)
            manifest = {
                "manifest_version": services.VISUAL_PROMPT_MANIFEST_VERSION,
                **identity,
                "scene_count": 1,
                "scenes": [
                    {
                        "prompt": "智能手表与指夹式血氧仪同场对比",
                        "lineage": {
                            **identity,
                            "scene_id": "scene-01",
                        },
                    }
                ],
            }

            self.assertTrue(services.visual_prompt_manifest_is_current(manifest, project, content))
            self.assertFalse(
                services.visual_prompt_manifest_is_current(
                    manifest,
                    {**project, "template": "health"},
                    content,
                )
            )
            self.assertFalse(
                services.visual_prompt_manifest_is_current(
                    manifest,
                    project,
                    content.replace("98%", "97%"),
                )
            )

    def test_visual_prompt_manifest_expires_when_channel_image_policy_changes(self) -> None:
        project = {"id": 51, "template": "tech", "topic_name": "智能手表测血氧？别信"}
        content = "# 血氧数据别信\n\n## 口播脚本\n手表显示93%，指夹式血氧仪显示98%。\n"
        first_template = {
            "key": "tech",
            "image_style_prompt": "真实纪实摄影，冷灰与暖黄点色，35mm近景",
            "image_negative_prompt": "机器人、全息屏、廉价红叉",
        }
        second_template = {
            **first_template,
            "image_style_prompt": "真实家庭纪实摄影，自然窗光，50mm近景",
        }
        with (
            patch.object(services, "visual_timeline_signature", return_value="timeline-a"),
            patch.object(services.storage, "get_template", side_effect=[first_template, second_template]),
        ):
            before = services.visual_prompt_manifest_identity(project, content)
            after = services.visual_prompt_manifest_identity(project, content)

        self.assertNotEqual(before["channel_image_policy_hash"], after["channel_image_policy_hash"])

    def test_visual_prompt_manifest_keeps_higher_scoring_prompt(self) -> None:
        manifest = {
            "scenes": [
                {
                    "target": "s_01.png",
                    "prompt": "高分提示词",
                    "prompt_hash": "old-hash",
                    "quality_score": 94,
                    "quality_score_version": services.IMAGE_PROMPT_SCORE_VERSION,
                    "lineage": {"prompt_hash": "old-hash"},
                }
            ],
            "covers": {},
        }
        with (
            patch.object(services, "load_visual_prompt_manifest", return_value=manifest),
            patch.object(services.storage, "write_json") as write_json,
            patch.object(services, "sync_scene_prompt_records_from_manifest"),
        ):
            updated = services.update_visual_prompt_manifest_prompts(
                51,
                "scene",
                {"s_01.png": "较低分的新提示词"},
                "# 内容",
                prompt_scores={"s_01.png": 72},
            )

        item = updated["scenes"][0]
        self.assertEqual(item["prompt"], "高分提示词")
        self.assertEqual(item["quality_score"], 94)
        self.assertEqual(item["last_rejected_candidate"]["quality_score"], 72)
        self.assertEqual(updated["last_prompt_update"]["preserved_targets"], ["s_01.png"])
        write_json.assert_called_once()

    def test_visual_prompt_manifest_regrades_score_from_old_rubric(self) -> None:
        manifest = {
            "scenes": [
                {
                    "target": "s_01.png",
                    "prompt": "旧量尺高分提示词",
                    "prompt_hash": "old-hash",
                    "quality_score": 98,
                    "quality_score_version": "old-rubric",
                    "lineage": {"prompt_hash": "old-hash"},
                }
            ],
            "covers": {},
        }
        with (
            patch.object(services, "load_visual_prompt_manifest", return_value=manifest),
            patch.object(services.storage, "write_json"),
            patch.object(services, "sync_scene_prompt_records_from_manifest"),
        ):
            updated = services.update_visual_prompt_manifest_prompts(
                51,
                "scene",
                {"s_01.png": "新版量尺提示词"},
                "# 内容",
                prompt_scores={"s_01.png": 88},
            )

        item = updated["scenes"][0]
        self.assertEqual(item["prompt"], "新版量尺提示词")
        self.assertEqual(item["quality_score"], 88)
        self.assertEqual(item["quality_score_version"], services.IMAGE_PROMPT_SCORE_VERSION)

    def test_manifest_scene_rewrite_must_match_its_own_narration(self) -> None:
        item = {
            "audience_visual": {"spoken": "把材料剥到只剩一层铜氧面"},
            "source_information": {"primary_message": "把材料剥到只剩一层铜氧面"},
        }

        self.assertTrue(
            services.prompt_matches_manifest_scene(
                "当前完整口播：把材料剥到只剩一层铜氧面。画面表现实验剥离过程。",
                item,
            )
        )
        self.assertFalse(
            services.prompt_matches_manifest_scene(
                "当前完整口播：石墨烯迫使人们重新思考维度。画面表现石墨烯晶格。",
                item,
            )
        )

    def test_channel_policy_keeps_scene_content_before_style_contract(self) -> None:
        template = {
            "image_style_prompt": "暖米白纸张线稿卡通，炭黑轮廓",
            "image_negative_prompt": "写实摄影、3D渲染",
        }
        prompt = "当前完整口播：超导材料被剥到只剩一层铜氧面。主体是实验镊子和单层材料。"

        result = services.apply_channel_image_policy(prompt, template, "scene")

        self.assertLess(result.index("当前完整口播"), result.index("频道固定视觉签名"))

    def test_manifest_prompt_sync_does_not_relabel_an_existing_old_image(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            records_path = root / "scenes" / "scene_prompts.json"
            records_path.parent.mkdir(parents=True, exist_ok=True)
            (records_path.parent / "s_02.png").write_bytes(b"old-image")
            records_path.write_text(
                json.dumps(
                    [
                        {
                            "filename": "s_02.png",
                            "prompt": "旧提示词",
                            "prompt_policy_version": "semantic-concepts-v4",
                            "audit": {"ok": True, "attempt": 1},
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            manifest = {
                "manifest_version": 1,
                "prompt_policy_version": services.IMAGE_PROMPT_POLICY_VERSION,
                "content_hash": "content-new",
                "topic_hash": "topic-new",
                "channel_id": "tech",
                "episode_id": "51",
                "scenes": [
                    {
                        "target": "s_02.png",
                        "prompt": "当前口播绑定的新提示词",
                        "lineage": {"content_hash": "content-new", "topic_hash": "topic-new"},
                    }
                ],
            }

            with patch.object(services.storage, "project_file", side_effect=lambda _pid, rel: root / rel):
                services.sync_scene_prompt_records_from_manifest(51, manifest, ["s_02.png"])

            synced = json.loads(records_path.read_text(encoding="utf-8"))[0]
            self.assertEqual(synced["prompt"], "旧提示词")
            self.assertEqual(synced["prompt_policy_version"], "semantic-concepts-v4")
            self.assertEqual(synced["audit"], {"ok": True, "attempt": 1})
            self.assertEqual(synced["planned_prompt"], "当前口播绑定的新提示词")
            self.assertEqual(synced["planned_content_hash"], "content-new")
            self.assertEqual(synced["planned_topic_hash"], "topic-new")

    def test_saving_visual_manifest_also_syncs_scene_prompt_records(self) -> None:
        manifest = {
            "scenes": [
                {"target": "s_01.png", "prompt": "第一镜独立提示词"},
                {"target": "s_02.png", "prompt": "第二镜独立提示词"},
            ],
            "covers": {},
        }
        with (
            patch.object(services.storage, "get_content", return_value="# 文案"),
            patch.object(services, "visual_prompt_manifest_path", return_value=Path("visual_prompt_manifest.json")),
            patch.object(services.storage, "read_json", return_value={}),
            patch.object(services, "build_visual_prompt_manifest", return_value=manifest),
            patch.object(services.storage, "write_json"),
            patch.object(services, "sync_scene_prompt_records_from_manifest") as sync_records,
        ):
            saved = services.save_visual_prompt_manifest(51, force=True)

        self.assertIs(saved, manifest)
        sync_records.assert_called_once_with(51, manifest, ["s_01.png", "s_02.png"])

    def test_cover_numeric_facts_can_use_verified_episode_source(self) -> None:
        context = {
            "speech": "手表显示93%，血氧仪显示98%。",
            "fact_source": "手指停在120拨号键上，但最终没有拨出。",
        }

        foreign = services.foreign_scene_numeric_facts("画面出现120拨号键。", context)

        self.assertEqual(foreign, [])

    def test_cover_numeric_facts_accept_current_script_difference(self) -> None:
        context = {
            "speech": "折叠屏起步1999美元，直板机起步1199美元。",
            "fact_registry_enforced": True,
            "allowed_numeric_facts": ["1999", "1199", "八百美元"],
        }

        foreign = services.foreign_scene_numeric_facts("封面写差价 $800。", context)

        self.assertEqual(foreign, [])

    def test_numeric_fact_extractor_keeps_dollar_unit_and_equivalent_value(self) -> None:
        facts = services.extract_numeric_fact_tokens("两边差了八百美元，折叠屏起步1999美元。")
        normalized = {services.normalized_numeric_fact(item) for item in facts}

        self.assertIn("800美元", normalized)
        self.assertTrue(
            services.numeric_fact_equivalence_keys("800美元")
            & services.numeric_fact_equivalence_keys("800")
        )

    def test_content_prompt_refresh_no_longer_writes_image_prompts_into_content(self) -> None:
        content = """# 标题

## 口播脚本
这是本期口播。

## 图片提示词
1. 旧智能家居中控屏提示词

## 参考资料
- 资料 A
"""

        refreshed = services.refresh_content_image_prompts({}, {}, content)

        self.assertIn("这是本期口播", refreshed)
        self.assertIn("资料 A", refreshed)
        self.assertNotIn("图片提示词", refreshed)
        self.assertNotIn("智能家居中控屏", refreshed)

    def test_ocr_rejects_production_metadata_not_present_in_speech_prompt(self) -> None:
        prompt = "智能手表与指夹式血氧仪现场对比，读数93%和98%。"
        ocr_text = "93% 98% AI生成内容 人设 受众 结构 节奏 转化"

        hits = services.ocr_prompt_contamination(ocr_text, prompt)

        self.assertIn("AI生成", hits)
        self.assertIn("人设", hits)
        self.assertIn("转化", hits)
        self.assertEqual(
            services.image_audit_reason_label("ocr_production_meta"),
            "检测到人设、受众、AI生成等制作过程文字",
        )

    def test_playwright_noise_is_removed_from_user_log(self) -> None:
        raw = """[images] 开始生成
[job] 任务失败：BrowserType.launch_persistent_context: Target page, context or browser has been closed
Browser logs:
<launching> chrome --enable-features=LotsOfFlags
- <launched> pid=14216
- [pid=14216] taskkill stderr: ����� u����
- [pid=14216] <gracefully close end>
"""
        cleaned = services.sanitize_user_log_text(raw)
        self.assertIn("[images] 开始生成", cleaned)
        self.assertIn("浏览器窗口已关闭", cleaned)
        self.assertNotIn("<launching>", cleaned)
        self.assertNotIn("taskkill", cleaned)
        self.assertNotIn("�", cleaned)

    def test_script_repair_does_not_append_interaction_when_valid_cta_survives(self) -> None:
        script = """【主播】智能门锁不是装上就安全。
【主播】你家的智能锁，坑过你吗？评论区只写一个经历。
【主播】感谢收听，下期再见。"""

        repaired, hits = services.rewrite_script_section_bad_phrases(script, "智能门锁真安全", "video")

        self.assertIn("你家的智能锁，坑过你吗？评论区只写一个经历", repaired)
        self.assertEqual(repaired.count("评论区"), 1)
        self.assertNotIn("说到智能门锁真安全", repaired)
        self.assertNotIn("感谢收听", repaired)
        self.assertNotIn("补具体互动结尾", hits)

    def test_tts_sanitizer_keeps_only_one_terminal_comment_action(self) -> None:
        text = """你家的智能锁，坑过你吗？评论区只写一个经历。
说到智能门锁真安全，你踩过哪个坑？评论区只写一个经历。"""

        sanitized = services.sanitize_tts_delivery_text(text, "智能门锁真安全")

        self.assertEqual(sanitized.count("评论区"), 1)
        self.assertIn("你家的智能锁，坑过你吗？", sanitized)
        self.assertNotIn("说到智能门锁真安全", sanitized)

    def test_dialogue_payload_keeps_only_one_terminal_comment_action(self) -> None:
        lines = [
            "主播：先看锁体和应急供电。",
            "主播：你家的智能锁，坑过你吗？评论区只写一个经历。",
            "主播：说到智能门锁真安全，你踩过哪个坑？评论区只写一个经历。",
        ]

        payload = services.sanitized_dialogue_payload_for_tts(lines, "", "智能门锁真安全")

        self.assertEqual(sum("评论区" in item["text"] for item in payload), 1)
        self.assertIn("你家的智能锁，坑过你吗？", payload[-1]["text"])

    def test_spoken_script_manifest_is_a_one_way_content_artifact(self) -> None:
        content = """# 快充协议

## 口播脚本
【主播】盒子写着65W，不等于手机真能吃满65W。

## 图片提示词
1. 充电器包装盒特写，画面显示65W。
"""
        manifest = services.build_spoken_script_manifest(content, "video", "快充协议")

        self.assertEqual(manifest["schema_version"], services.SPOKEN_SCRIPT_SCHEMA_VERSION)
        self.assertFalse(manifest["visual_writeback_allowed"])
        self.assertTrue(manifest["utterances"])
        self.assertTrue(all(item["source_type"] == "spoken_text" for item in manifest["utterances"]))
        self.assertNotIn("包装盒特写", manifest["tts_text"])

    def test_tts_payload_rejects_non_spoken_manifest_entries(self) -> None:
        content = "# 主题\n\n## 口播脚本\n【主播】这是最终口播。\n"
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_path = Path(temp_dir) / "spoken_script.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema_version": services.SPOKEN_SCRIPT_SCHEMA_VERSION,
                        "source_hash": services.spoken_script_source_hash(content),
                        "visual_writeback_allowed": False,
                        "utterances": [
                            {"speaker": "主播", "text": "这是最终口播。", "source_type": "spoken_text"},
                            {"speaker": "视觉", "text": "镜头切到包装盒。", "source_type": "visual_brief"},
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with patch.object(services, "spoken_script_manifest_path", return_value=manifest_path):
                payload = services.current_spoken_dialogue_payload(59, content, "video", "主题")

        self.assertEqual(payload, [{"speaker": "主播", "text": "这是最终口播。"}])

    def test_content_generation_rules_use_a_separate_visual_stage(self) -> None:
        rules = services.build_common_content_system_rules()
        self.assertIn("当前调用只负责文案", rules)
        self.assertIn("后续视觉阶段", rules)
        self.assertIn("不要输出图片提示词", rules)

    def test_windows_background_subprocesses_use_no_window_flag(self) -> None:
        kwargs = services.background_subprocess_kwargs()
        if services.os.name == "nt":
            self.assertEqual(kwargs["creationflags"], services.subprocess.CREATE_NO_WINDOW)
        else:
            self.assertEqual(kwargs, {})

    def test_ffprobe_inherits_background_subprocess_policy(self) -> None:
        completed = type("Completed", (), {"stdout": "12.5\n"})()
        with patch.object(services.subprocess, "run", return_value=completed) as mocked_run:
            duration = services.probe_media_duration(Path("video.mp4"))

        self.assertEqual(duration, 12.5)
        if services.os.name == "nt":
            self.assertEqual(
                mocked_run.call_args.kwargs.get("creationflags"),
                services.subprocess.CREATE_NO_WINDOW,
            )

    def test_terminal_cta_dedupe_catches_question_without_comment_keyword(self) -> None:
        lines = [
            "【主播】你手机上弹过最离谱的广告是什么？是刚想买电脑就弹电脑，还是刚查过病历就弹药？",
            "【主播】说到弹窗广告比你会撩妹，你踩过哪个坑？",
            "【主播】说到弹窗广告比你会撩妹，你踩过哪个坑？评论区只写一个经历。",
        ]

        cleaned, removed = services.dedupe_terminal_interaction_lines(lines)

        self.assertEqual(removed, 2)
        self.assertEqual(len(cleaned), 1)
        self.assertNotIn("评论区只写一个经历", cleaned[0])
        self.assertIn("你手机上弹过最离谱的广告是什么", cleaned[0])
        self.assertNotIn("说到弹窗广告比你会撩妹", cleaned[0])

    def test_structural_direct_conclusion_label_is_normalized(self) -> None:
        script = """【直接说结论】同一台手机，系统版本不同，实测帧率会拉开差距。
【直接说结论】因为更新里包含 GPU 驱动和调度优化。
【直接说结论】先别急，真正容易忽略的点在后面。
【直接说结论】老机型先看同型号更新反馈，再决定要不要升。"""

        repaired, hits = services.rewrite_script_section_bad_phrases(script, "手机系统更新", "video")

        self.assertNotIn("【直接说结论】", repaired)
        self.assertEqual(repaired.count("【主播】"), 3)
        self.assertNotIn("先别急，真正容易忽略的点在后面", repaired)
        self.assertIn("结构标签归一为主播", hits)
        self.assertIn("移除无信息转场", hits)

    def test_compact_meta_does_not_invent_interaction_hook_from_last_line(self) -> None:
        content = """# 系统更新

## Meta
- 核心观点: 系统更新可能包含驱动优化。
- 钩子: 同一台手机，帧率为什么不一样？

## 口播脚本
【主播】同一台手机，系统版本不同，实测帧率会拉开差距。
【主播】老机型先看同型号反馈，再决定要不要升？
"""

        compacted = services.compact_content_meta(content)

        meta = services.extract_section(compacted, "Meta", level=2)
        self.assertNotIn("互动钩子", meta)

    def test_review_rules_do_not_require_fixed_cta_or_timed_turns(self) -> None:
        prompt = services.build_viral_content_rules(
            {"id": 0, "template": "科技情报站", "template_mode": "video", "topic_name": "系统更新"},
            {"key": "科技情报站", "name": "科技情报站", "mode": "video", "voice_mode": "single"},
        )

        self.assertNotIn("每 2-4 句", prompt)
        self.assertNotIn("每 2—3 句", prompt)
        self.assertNotIn("具体互动问题", prompt)
        self.assertIn("互动不是必选", prompt)

    def test_json_write_replaces_old_content_without_trailing_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "project.json"
            path.write_text('{"old": "value"}} trailing bytes', encoding="utf-8")

            services.storage.write_json(path, {"id": 53, "topic_name": "测试项目"})

            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["id"], 53)
            self.assertEqual(list(path.parent.glob(".project.json.*.tmp")), [])

    def test_json_write_retries_transient_windows_file_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "project.json"
            path.write_text('{"id": 52}', encoding="utf-8")
            real_replace = services.storage.os.replace
            attempts = 0

            def flaky_replace(source: Path, target: Path) -> None:
                nonlocal attempts
                attempts += 1
                if attempts < 3:
                    raise PermissionError(13, "file is temporarily locked", str(target))
                real_replace(source, target)

            with (
                patch.object(services.storage.os, "replace", side_effect=flaky_replace),
                patch.object(services.storage.time, "sleep"),
            ):
                services.storage.write_json(path, {"id": 56, "last_job_status": "running"})

            self.assertEqual(attempts, 3)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["id"], 56)
            self.assertEqual(list(path.parent.glob(".project.json.*.tmp")), [])

    def test_json_read_recovers_valid_object_before_trailing_junk(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "project.json"
            path.write_text('{"id": 53, "topic_name": "手机App在偷听你聊天？"}\n}', encoding="utf-8")

            recovered = services.storage.read_json(path, {})

            self.assertEqual(recovered["id"], 53)
            self.assertEqual(recovered["topic_name"], "手机App在偷听你聊天？")

    def test_text_write_replaces_longer_old_content_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "content.md"
            path.write_text("旧内容" * 200, encoding="utf-8")

            services.storage.write_text(path, "新文案")

            self.assertEqual(path.read_text(encoding="utf-8"), "新文案")
            self.assertEqual(list(path.parent.glob(".content.md.*.tmp")), [])

    def test_semantic_duplicate_dialogue_pairs_finds_nearby_paraphrase(self) -> None:
        lines = [
            "【主播】智能门锁真正的风险不是没电，而是应急开锁方式暴露。",
            "【主播】先检查机械钥匙和应急供电口放在哪里。",
            "【主播】所以智能门锁真正的风险不是断电，而是应急开锁方式被暴露。",
        ]

        pairs = services.semantic_duplicate_dialogue_pairs(lines)

        self.assertEqual(len(pairs), 1)
        self.assertEqual((pairs[0]["left_index"], pairs[0]["right_index"]), (0, 2))

    def test_semantic_duplicate_dialogue_pairs_keeps_distinct_progression(self) -> None:
        lines = [
            "【主播】先关闭不必要的麦克风权限。",
            "【主播】广告画像还会读取搜索、位置和停留时长。",
            "【主播】最后用系统隐私面板检查最近调用记录。",
        ]

        self.assertEqual(services.semantic_duplicate_dialogue_pairs(lines), [])

    def test_content_information_repetition_finds_repeated_numeric_fact(self) -> None:
        report = services.content_information_repetition([
            "五款新车里，顶配卖到13.8万元，国产摩托第一次越过十万元。",
            "消费者还要计算后续保养成本。",
            "能确认的还是五款新车、13.8万元和首次越过十万元。",
        ])
        self.assertGreaterEqual(report["repeat_count"], 1)
        self.assertTrue(report["repeated_facts"])

    def test_content_information_repetition_keeps_fact_reason_action_progression(self) -> None:
        report = services.content_information_repetition([
            "顶配车型卖到13.8万元。",
            "价格抬高，是因为车架和刹车配置发生变化。",
            "下单前分别核对配置、保养周期和售后价格。",
        ])
        self.assertEqual(report["repeat_count"], 0)

    def test_cover_title_and_subtitle_survive_prompt_optimization(self) -> None:
        prompt = "主标题：APP真在偷听？\n反转章：其实是画像\n封面具体画面：手机隐私实验现场。"

        optimized = services.optimize_visual_generation_prompt(prompt, {}, "cover")

        self.assertEqual(services.extract_cover_title_hint(prompt), "APP真在偷听？")
        self.assertEqual(services.extract_cover_subtitle_hint(prompt), "其实是画像")
        self.assertIn("APP真在偷听？", optimized)
        self.assertIn("其实是画像", optimized)

    def test_channel_image_style_and_negative_terms_survive_prompt_optimization(self) -> None:
        template = {
            "image_style_prompt": "真实纪实摄影，生活化自然光，冷灰与暖黄点色，35mm近景",
            "image_negative_prompt": "赛博蓝光、机器人、全息屏、廉价红叉、同一男模",
        }
        prompt = "当前口播：老人正在比较腕表93%与指夹血氧仪98%的读数，手部动作清楚。"

        optimized = services.optimize_visual_generation_prompt(prompt, template, "scene")

        self.assertIn("老人", optimized)
        self.assertIn("频道固定视觉签名", optimized)
        self.assertIn("真实纪实摄影", optimized)
        self.assertIn("频道禁止元素", optimized)
        self.assertIn("赛博蓝光", optimized)
        self.assertIn("同一男模", optimized)

    def test_numeric_or_conclusion_scene_uses_text_led_sparse_object_layout(self) -> None:
        prompt = "本镜口播原文：「AI用30秒生成1000字，我却花3小时改稿。」。真实办公桌上的改稿现场。"

        clauses = services.image_text_policy_clauses(prompt, "scene")
        optimized = services.optimize_visual_generation_prompt(prompt, {}, "scene")

        self.assertEqual(services.image_layout_mode(prompt, "scene"), "text_led")
        self.assertIn("信息主导的满幅构图", " ".join(clauses))
        self.assertIn("一到三个", " ".join(clauses))
        self.assertIn("信息主导的满幅构图", optimized)

    def test_plain_action_scene_uses_object_led_layout_without_forced_large_text(self) -> None:
        prompt = "本镜口播原文：「老人把药盒放到桌上，伸手拿起血压计。」。真实家庭餐桌近景。"

        clauses = services.image_text_policy_clauses(prompt, "scene")

        self.assertEqual(services.image_layout_mode(prompt, "scene"), "object_led")
        self.assertIn("物体主导的满幅构图", " ".join(clauses))
        self.assertIn("不强行加大字", " ".join(clauses))

    def test_cover_text_directives_are_explicit_and_survive_long_prompt(self) -> None:
        prompt = services.ensure_cover_text_directives(
            "真实餐桌上的药盒、西柚和血压计形成强冲突。" * 30,
            "吃药忌口的事",
            "吃错一口，药都白费",
        )

        self.assertEqual(services.extract_cover_title_hint(prompt), "吃药忌口的事")
        self.assertEqual(services.extract_cover_subtitle_hint(prompt), "吃错一口，药都白费")
        self.assertLess(prompt.index("吃药忌口的事"), prompt.index("真实餐桌"))

    def test_cover_text_directives_never_truncate_exact_title_or_subtitle(self) -> None:
        title = "中国AI杀进美国，比GPT便宜10倍？"
        subtitle = "成本只有美国模型的1/10，性能还接近"

        prompt = services.ensure_cover_text_directives("科技办公室真实摄影。", title, subtitle)

        self.assertEqual(services.extract_cover_title_hint(prompt), "中国AI杀进美国，比GPT便宜10倍")
        self.assertEqual(services.extract_cover_subtitle_hint(prompt), subtitle)
        self.assertNotIn("比GP」", prompt)
        self.assertNotIn("模型的1/...", prompt)

    def test_cover_typography_overlay_preserves_ai_source(self) -> None:
        if services.Image is None:
            self.skipTest("Pillow is unavailable")
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "cover_landscape.png"
            services.Image.new("RGB", (1280, 720), (22, 38, 54)).save(image_path)
            before = image_path.read_bytes()

            result = services.apply_cover_typography_overlay(image_path, "APP真在偷听？", "其实是画像")

            self.assertTrue(result["applied"])
            self.assertNotEqual(before, image_path.read_bytes())
            self.assertTrue(services.cover_typography_source_path(image_path).exists())
            payload = json.loads(image_path.with_suffix(".typography.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["title"], "APP真在偷听？")
            self.assertEqual(payload["subtitle"], "其实是画像")

    def test_cover_typography_overlay_wraps_without_dropping_characters(self) -> None:
        if services.Image is None:
            self.skipTest("Pillow is unavailable")
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "cover_landscape.png"
            services.Image.new("RGB", (1536, 1024), (24, 40, 58)).save(image_path)
            title = "中国AI杀进美国，比GPT便宜10倍"
            subtitle = "成本只有美国模型的1/10，性能还接近"

            result = services.apply_cover_typography_overlay(image_path, title, subtitle)

            self.assertTrue(result["applied"])
            self.assertEqual("".join(result["title_lines"]), title)
            self.assertEqual("".join(result["subtitle_lines"]), subtitle)
            self.assertGreaterEqual(len(result["title_lines"]), 2)
            self.assertTrue(
                all(
                    not line.startswith(tuple("，。！？；：、,.!?;:)]】》”’"))
                    for line in result["title_lines"]
                )
            )
            self.assertGreater(len(result["title_lines"][-1]), 1)

    def test_applied_cover_typography_resolves_ocr_false_negative(self) -> None:
        audit = {
            "ok": False,
            "severity": "soft",
            "reasons": ["cover_title_missing", "cover_subtitle_missing"],
            "ocr": {"missing_cover_text": ["APP真在偷听？", "其实是画像"]},
        }

        result = services.accept_applied_cover_typography(
            audit,
            {"applied": True, "title": "APP真在偷听？", "subtitle": "其实是画像"},
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["severity"], "ok")
        self.assertEqual(result["ocr"]["missing_cover_text"], [])

    def test_quality_sample_selects_highest_value_scene(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            plan_path = Path(temp_dir) / "scene_plan.json"
            plan_path.write_text(
                json.dumps(
                    {
                        "scenes": [
                            {"index": 1, "importance_score": 61, "alignment_score": 80},
                            {"index": 2, "importance_score": 92, "alignment_score": 94},
                            {"index": 3, "importance_score": 70, "alignment_score": 88},
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with patch.object(services.storage, "project_file", return_value=plan_path):
                selected = services.quality_sample_scene_index(53, 3)

            self.assertEqual(selected, 2)

    def test_video_lineage_records_cover_dependency(self) -> None:
        lineage = {"artifacts": {}}
        snapshots = {"video": {"exists": True, "hash": "video-v1"}}
        hashes = {
            "content_hash": "content-v1",
            "audio_hash": "audio-v1",
            "subtitles_hash": "subtitles-v1",
            "scene_plan_hash": "plan-v1",
            "scene_images_hash": "images-v1",
            "covers_hash": "covers-v2",
            "bgm_hash": "bgm-v3",
            "bgm_mix_hash": "bgm-mix-v4",
        }
        with (
            patch.object(services, "ensure_production_lineage", return_value=lineage),
            patch.object(services, "production_artifact_snapshots", return_value=snapshots),
            patch.object(services, "production_source_hashes", return_value=hashes),
            patch.object(services, "production_lineage_path", return_value=Path("production_lineage.json")),
            patch.object(services.storage, "write_json"),
            patch.object(services, "refresh_production_manifest", return_value={"ok": True}),
        ):
            services.record_production_step(53, "video")

        self.assertEqual(lineage["artifacts"]["video"]["sources"]["covers_hash"], "covers-v2")
        self.assertEqual(lineage["artifacts"]["video"]["sources"]["bgm_hash"], "bgm-v3")
        self.assertEqual(lineage["artifacts"]["video"]["sources"]["bgm_mix_hash"], "bgm-mix-v4")
        self.assertEqual(lineage["artifacts"]["video"]["sources"]["mix_policy"], services.BGM_MIX_POLICY_VERSION)
        self.assertEqual(
            lineage["artifacts"]["video"]["sources"]["visual_master_policy"],
            services.VISUAL_MASTER_POLICY_VERSION,
        )

    def test_sound_mood_uses_privacy_investigation_for_app_listening_topic(self) -> None:
        decision = services.sound_mood_decision(
            "科技调查",
            "真实实验",
            "手机应用",
            "手机 App 在偷听你聊天吗？关闭麦克风权限后，精准广告更多来自用户画像与跨应用追踪。",
        )

        self.assertEqual(decision["mood"], "privacy_investigation")
        self.assertIn("偷听", decision["matched_signals"])
        self.assertIn("隐私调查", decision["reason"])

    def test_sound_mood_separates_fraud_health_and_business_topics(self) -> None:
        fraud = services.sound_mood_decision("", "", "", "冒充客服诱导转账，这是最近常见的诈骗骗局。")
        health = services.sound_mood_decision("", "", "", "智能手表血氧读数只能作为健康提醒，不能替代医疗判断。")
        business = services.sound_mood_decision("", "", "", "房价、市场销量和公司成本正在发生变化。")

        self.assertEqual(fraud["mood"], "urgent_warning")
        self.assertEqual(health["mood"], "warm_warning")
        self.assertEqual(business["mood"], "business_pulse")

    def test_sound_mood_does_not_match_ai_inside_health_claim(self) -> None:
        decision = services.sound_mood_decision(
            "health_claim",
            "family_documentary",
            "daily_life",
            "高血压患者不能擅自停用降压药，应记录血压并听医生指导。",
        )

        self.assertEqual(decision["mood"], "warm_warning")
        self.assertNotIn("ai", decision["matched_signals"])
        self.assertIn("高血压", decision["matched_signals"])

    def test_sound_mood_still_matches_standalone_ai_topic(self) -> None:
        decision = services.sound_mood_decision(
            "technology",
            "documentary",
            "office",
            "AI 写作工具和大模型到底能不能提高效率？",
        )

        self.assertEqual(decision["mood"], "tech_suspense")
        self.assertIn("ai", decision["matched_signals"])

    def test_old_auto_bgm_is_stale_after_theme_policy_upgrade(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "bgm.mp3").write_bytes(b"old bgm")
            (root / "bgm_meta.json").write_text(
                json.dumps({"source": "procedural_local", "mood": "warm_warning", "label": "温暖提醒"}, ensure_ascii=False),
                encoding="utf-8",
            )
            project = {"id": 53, "topic_name": "手机App在偷听你聊天？", "template": "科技情报站"}
            content = "手机 App 偷听、麦克风权限和用户画像到底是什么关系？"
            with (
                patch.object(services.storage, "project_file", side_effect=lambda _project_id, relative: root / relative),
                patch.object(services.storage, "TEMPLATES_ROOT", root / "templates"),
                patch.object(services.storage, "get_project", return_value=project),
                patch.object(services.storage, "get_template", return_value={"name": "科技情报站"}),
                patch.object(services.storage, "get_content", return_value=content),
                patch.object(services, "runtime_env", return_value={"BGM_AUTO_MODE": "auto"}),
                patch.object(services, "BGM_FEATURE_ENABLED", True),
            ):
                status = services.project_bgm_status(53)

            self.assertEqual(status["status"], "stale")
            self.assertTrue(status["needs_rematch"])
            self.assertEqual(status["desired_mood"], "privacy_investigation")

    def test_local_bgm_fallback_does_not_loop_when_online_provider_is_unconfigured(self) -> None:
        self.assertFalse(services.auto_bgm_provider_changed("procedural_local", "loudly", False))
        self.assertTrue(services.auto_bgm_provider_changed("procedural_local", "loudly", True))
        self.assertTrue(services.auto_bgm_provider_changed("freesound", "loudly", False))
        self.assertFalse(services.auto_bgm_provider_changed("loudly", "loudly", True))

    def test_bgm_uses_another_configured_catalog_when_preferred_is_unavailable(self) -> None:
        provider, ready = services.resolve_online_bgm_provider(
            {
                "LOUDLY_API_KEY": "",
                "JAMENDO_CLIENT_ID": "",
                "FREESOUND_API_KEY": "configured-token",
            },
            "loudly",
        )

        self.assertEqual(provider, "freesound")
        self.assertTrue(ready)

    def test_project_bgm_without_auto_metadata_is_manual_locked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "bgm.mp3").write_bytes(b"manual bgm")
            project = {"id": 8, "topic_name": "人物故事", "template": "故事频道"}
            with (
                patch.object(services.storage, "project_file", side_effect=lambda _project_id, relative: root / relative),
                patch.object(services.storage, "TEMPLATES_ROOT", root / "templates"),
                patch.object(services.storage, "get_project", return_value=project),
                patch.object(services.storage, "get_template", return_value={"name": "故事频道"}),
                patch.object(services.storage, "get_content", return_value="这是一个真实人物经历。"),
                patch.object(services, "runtime_env", return_value={"BGM_AUTO_MODE": "auto"}),
                patch.object(services, "BGM_FEATURE_ENABLED", True),
            ):
                status = services.project_bgm_status(8)

            self.assertEqual(status["status"], "current")
            self.assertTrue(status["manual_locked"])
            self.assertFalse(status["needs_rematch"])

    def test_current_theme_bgm_is_reused_without_regeneration(self) -> None:
        current = {
            "status": "current",
            "current": True,
            "path": "C:/tmp/bgm.mp3",
            "source": "procedural_local",
            "label": "隐私调查",
        }
        with (
            patch.object(services, "runtime_env", return_value={"BGM_AUTO_MODE": "auto"}),
            patch.object(services, "project_bgm_status", return_value=current),
            patch.object(services, "write_procedural_bgm_wav") as write_bgm,
        ):
            result = services.ensure_project_bgm(53)

        self.assertTrue(result["reused"])
        write_bgm.assert_not_called()

    def test_bgm_rotation_pool_includes_current_history_and_recent_channel_tracks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            def project_file(project_id: int, relative: str) -> Path:
                return root / str(project_id) / relative

            def write_meta(project_id: int, relative: str, track_id: str) -> None:
                path = project_file(project_id, relative)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    json.dumps({"source": "loudly", "track": {"id": track_id}}, ensure_ascii=False),
                    encoding="utf-8",
                )

            write_meta(53, "bgm_meta.json", "current-track")
            write_meta(53, "bgm_history/bgm_meta-100.json", "archived-track")
            write_meta(54, "bgm_meta.json", "same-channel-track")
            write_meta(55, "bgm_meta.json", "other-channel-track")
            with (
                patch.object(services.storage, "project_file", side_effect=project_file),
                patch.object(services.storage, "get_project", return_value={"id": 53, "template": "科技情报站"}),
                patch.object(
                    services.storage,
                    "list_projects",
                    return_value=[
                        {"id": 54, "template": "科技情报站"},
                        {"id": 55, "template": "其它频道"},
                    ],
                ),
            ):
                recent = services.recent_bgm_track_ids(53, "loudly")

        self.assertEqual(recent, {"current-track", "archived-track", "same-channel-track"})
        self.assertNotIn("other-channel-track", recent)

    def test_bgm_rotation_always_prefers_an_acceptable_fresh_track(self) -> None:
        ranked = services.prioritize_fresh_bgm_candidates(
            [
                {"id": "recent-best", "selection_score": 0.95, "recent_repeat_penalty": 0.42},
                {"id": "fresh-good", "selection_score": 0.61, "recent_repeat_penalty": 0.0},
                {"id": "fresh-ok", "selection_score": 0.55, "recent_repeat_penalty": 0.0},
            ]
        )

        self.assertEqual([item["id"] for item in ranked], ["fresh-good", "fresh-ok", "recent-best"])

    def test_bgm_arrangement_rotates_away_from_recent_channel_sound(self) -> None:
        with (
            patch.object(
                services.storage,
                "get_project",
                return_value={"id": 81, "topic_name": "手机芯片为什么越来越贵", "template": "科技情报站"},
            ),
            patch.object(
                services,
                "recent_bgm_arrangement_ids",
                return_value=["glass_clockwork", "minimal_pulse", "dry_piano"],
            ),
        ):
            arrangement = services.choose_bgm_arrangement(81, "tech_suspense")

        self.assertEqual(arrangement["arrangement_id"], "restrained_strings")
        self.assertEqual(arrangement["arrangement_label"], "克制弦乐")

    def test_bgm_track_family_groups_numbered_loop_variants(self) -> None:
        first = services.bgm_track_family_signature(
            {"name": "Orchestral Suspense Loop 1.wav", "username": "composer"}
        )
        second = services.bgm_track_family_signature(
            {"name": "Orchestral Suspense Loop 3.mp3", "username": "composer"}
        )
        mix_variant = services.bgm_track_family_signature(
            {"name": "Orchestral Suspense Loop (no drums).mp3", "username": "composer"}
        )

        self.assertEqual(first, second)
        self.assertEqual(first, mix_variant)

    def test_freesound_music_quality_rejects_short_sfx_and_keeps_full_instrumental(self) -> None:
        self.assertEqual(
            services.bgm_candidate_music_quality(
                {
                    "name": "Cinematic Impact Climax Intro SFX",
                    "duration": 90,
                    "tags": ["cinematic", "music"],
                }
            ),
            0.0,
        )
        self.assertGreater(
            services.bgm_candidate_music_quality(
                {
                    "name": "Restrained Documentary Piano",
                    "duration": 120,
                    "tags": ["instrumental", "piano", "documentary"],
                }
            ),
            0.8,
        )

    def test_bgm_selector_prompt_exposes_theme_aware_profiles_and_reason(self) -> None:
        messages = services.compose_bgm_selector_messages(
            {"id": 53, "topic_name": "手机App在偷听你聊天？", "template": "科技情报站"},
            {"name": "科技情报站"},
            "关闭麦克风权限后，广告仍可能来自用户画像。",
            {"mood": "privacy_investigation"},
        )

        self.assertIn("privacy_investigation", messages[0]["content"])
        self.assertIn('"reason"', messages[0]["content"])
        self.assertIn("主题与本期口播优先", messages[0]["content"])

    def test_freesound_ranking_balances_theme_popularity_and_recent_repetition(self) -> None:
        preview = {"preview-hq-mp3": "https://example.com/a.mp3"}
        results = [
            {
                "id": 1,
                "name": "privacy investigation pulse",
                "tags": ["privacy", "investigation", "documentary"],
                "license": "Creative Commons 0",
                "previews": preview,
                "score": 10,
                "num_downloads": 1200,
                "avg_rating": 4.8,
                "num_ratings": 12,
            },
            {
                "id": 2,
                "name": "happy ukulele party",
                "tags": ["happy", "party"],
                "license": "Creative Commons 0",
                "previews": preview,
                "score": 2,
                "num_downloads": 900000,
                "avg_rating": 5,
                "num_ratings": 100,
            },
            {
                "id": 3,
                "name": "privacy documentary tension",
                "tags": ["privacy", "documentary", "tension"],
                "license": "Creative Commons 0",
                "previews": preview,
                "score": 9,
                "num_downloads": 900,
                "avg_rating": 4.6,
                "num_ratings": 8,
            },
        ]
        brief = {"query": "privacy investigation documentary", "tags": ["privacy", "documentary"]}

        ranked = services.rank_freesound_bgm_candidates(results, brief, {"1"})

        self.assertEqual(ranked[0]["id"], 3)
        ranked_by_id = {item["id"]: item for item in ranked}
        self.assertGreater(ranked_by_id[3]["theme_overlap"], ranked_by_id[2]["theme_overlap"])
        self.assertGreater(ranked_by_id[2]["popularity_score"], ranked_by_id[3]["popularity_score"])
        self.assertLess(ranked_by_id[1]["selection_score"], ranked_by_id[3]["selection_score"])
        self.assertGreater(ranked_by_id[1]["recent_repeat_penalty"], 0)

    def test_freesound_accepts_official_cc0_license_url(self) -> None:
        self.assertTrue(services.allowed_bgm_license("http://creativecommons.org/publicdomain/zero/1.0/"))
        self.assertFalse(services.allowed_bgm_license("http://creativecommons.org/licenses/by-nc/4.0/"))

    def test_freesound_ranking_drops_non_music_ambience(self) -> None:
        preview = {"preview-hq-mp3": "https://example.com/a.mp3"}
        ranked = services.rank_freesound_bgm_candidates(
            [
                {
                    "id": 1,
                    "name": "Ambient Industrial Factory Fans",
                    "tags": ["Buzz", "Fans", "Machinery", "Noise"],
                    "license": "Creative Commons 0",
                    "previews": preview,
                    "score": 100,
                },
                {
                    "id": 2,
                    "name": "Cinematic technology pulse",
                    "tags": ["instrumental", "music", "synth", "loop"],
                    "license": "Creative Commons 0",
                    "previews": preview,
                    "score": 5,
                },
            ],
            {"query": "technology instrumental music", "tags": ["technology"]},
        )

        self.assertEqual([item["id"] for item in ranked], [2])

    def test_freesound_search_uses_text_endpoint_and_cc0_filter(self) -> None:
        requested_urls: list[str] = []

        class FakeResponse:
            def __init__(self, payload: bytes) -> None:
                self.payload = payload

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def read(self, *_args: object) -> bytes:
                return self.payload

        def fake_urlopen(request: object, timeout: int = 0) -> FakeResponse:
            del timeout
            url = str(getattr(request, "full_url", request))
            requested_urls.append(url)
            if "/apiv2/search/text/" in url:
                payload = {
                    "results": [
                        {
                            "id": 42,
                            "name": "privacy investigation pulse",
                            "url": "https://freesound.org/s/42/",
                            "username": "studio",
                            "license": "Creative Commons 0",
                            "duration": 60,
                            "tags": ["privacy", "investigation", "documentary"],
                            "previews": {"preview-hq-mp3": "https://example.com/preview.mp3"},
                            "score": 10,
                            "avg_rating": 4.8,
                            "num_ratings": 12,
                            "num_downloads": 1200,
                        }
                    ]
                }
                return FakeResponse(json.dumps(payload).encode("utf-8"))
            return FakeResponse(b"fake mp3")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with (
                patch.object(services.urllib.request, "urlopen", side_effect=fake_urlopen),
                patch.object(services.storage, "project_file", side_effect=lambda _project_id, relative: root / relative),
                patch.object(services, "recent_freesound_track_ids", return_value=set()),
                patch.object(services, "safe_probe_duration", return_value=60.0),
                patch.object(
                    services,
                    "audit_bgm_audio_for_vocals",
                    return_value={"status": "passed", "checked": True, "has_vocals": False},
                ),
            ):
                result = services.freesound_search_bgm(
                    53,
                    {"query": "privacy investigation documentary", "tags": ["privacy", "documentary"]},
                    "test-token",
                    60.0,
                )

        self.assertEqual(result["track"]["id"], 42)
        self.assertIn("/apiv2/search/text/", requested_urls[0])
        self.assertIn("license%3A%22Creative+Commons+0%22", requested_urls[0])

    def test_freesound_search_skips_vocal_candidate_and_uses_next_track(self) -> None:
        class FakeResponse:
            def __init__(self, payload: bytes) -> None:
                self.payload = payload

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def read(self, *_args: object) -> bytes:
                return self.payload

        def fake_urlopen(request: object, timeout: int = 0) -> FakeResponse:
            del timeout
            url = str(getattr(request, "full_url", request))
            if "/apiv2/search/text/" in url:
                return FakeResponse(json.dumps({"results": []}).encode("utf-8"))
            return FakeResponse(b"candidate audio")

        candidates = [
            {"id": 1, "name": "spoken intro", "preview_url": "https://example.com/a.mp3"},
            {"id": 2, "name": "instrumental pulse", "preview_url": "https://example.com/b.mp3"},
        ]
        audit_results = [
            {"status": "rejected", "checked": True, "has_vocals": True, "reason": "检测到可辨人声"},
            {"status": "passed", "checked": True, "has_vocals": False, "reason": "未识别到人声"},
        ]
        logs: list[str] = []
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with (
                patch.object(services.urllib.request, "urlopen", side_effect=fake_urlopen),
                patch.object(services.storage, "project_file", side_effect=lambda _project_id, relative: root / relative),
                patch.object(services, "freesound_query_candidates", return_value=["documentary"]),
                patch.object(services, "recent_freesound_track_ids", return_value=set()),
                patch.object(services, "rank_freesound_bgm_candidates", return_value=candidates),
                patch.object(services, "safe_probe_duration", return_value=60.0),
                patch.object(services, "runtime_env", return_value={"BGM_VOCAL_AUDIT_MAX_CANDIDATES": "5"}),
                patch.object(services, "audit_bgm_audio_for_vocals", side_effect=audit_results),
            ):
                result = services.freesound_search_bgm(
                    53,
                    {"query": "documentary"},
                    "test-token",
                    60.0,
                    status_callback=logs.append,
                )

        self.assertEqual(result["track"]["id"], 2)
        self.assertEqual(result["track"]["rejected_candidate_count"], 1)
        self.assertEqual(result["audio_vocal_audit"]["status"], "passed")
        self.assertTrue(any("自动换下一首" in item for item in logs))

    def test_loudly_ranking_prefers_theme_fit_and_rejects_vocals_and_recent_tracks(self) -> None:
        def track(
            track_id: str,
            *,
            title: str,
            moods: list[str],
            genres: list[str],
            has_vocal: bool = False,
            bpm: int = 90,
        ) -> dict[str, object]:
            return {
                "id": track_id,
                "title": title,
                "duration": 180000,
                "music_file_path": f"https://example.com/{track_id}.mp3",
                "moods": [{"name": value} for value in moods],
                "genres": [{"name": value} for value in genres],
                "secondary_genres": [],
                "energies": [{"name": "Medium"}],
                "has_vocal": has_vocal,
                "tempo_bpm": bpm,
            }

        ranked = services.rank_loudly_bgm_candidates(
            [
                track("recent", title="Dark Investigation", moods=["Dark", "Mysterious"], genres=["Ambient"]),
                track("fresh", title="Privacy Tension", moods=["Dark", "Tense"], genres=["Ambient"], bpm=88),
                track("vocal", title="Privacy Song", moods=["Dark"], genres=["Ambient"], has_vocal=True),
                track("wrong", title="Happy Party", moods=["Happy"], genres=["House"], bpm=140),
            ],
            {"mood": "privacy_investigation", "bpm": [76, 102]},
            {"recent"},
            170.0,
        )

        self.assertEqual(ranked[0]["id"], "fresh")
        self.assertNotIn("vocal", [item["id"] for item in ranked])
        self.assertEqual(ranked[0]["duration_sec"], 180.0)
        self.assertGreater(ranked[-1]["recent_repeat_penalty"], 0.0)

    def test_loudly_search_uses_catalog_tags_and_downloads_instrumental_track(self) -> None:
        requested_urls: list[str] = []
        requested_api_keys: list[str] = []

        class FakeResponse:
            def __init__(self, payload: bytes) -> None:
                self.payload = payload

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def read(self, *_args: object) -> bytes:
                return self.payload

        def fake_urlopen(request: object, timeout: int = 0) -> FakeResponse:
            del timeout
            url = str(getattr(request, "full_url", request))
            requested_urls.append(url)
            requested_api_keys.append(str(getattr(request, "get_header", lambda _name: "")("Api-key") or ""))
            if url.endswith("/api/songs/tags"):
                return FakeResponse(json.dumps({"mood": ["Dark", "Dreamy"], "genre": ["Ambient", "Lo Fi"]}).encode("utf-8"))
            if "/api/songs?" in url:
                payload = {
                    "items": [
                        {
                            "id": "loudly-42",
                            "title": "Dark Documentary Pulse",
                            "duration": 190000,
                            "music_file_path": "https://example.com/loudly-42.mp3",
                            "genres": [{"name": "Ambient"}],
                            "secondary_genres": [],
                            "moods": [{"name": "Dark"}, {"name": "Mysterious"}],
                            "instruments": [{"name": "Synth"}],
                            "energies": [{"name": "Medium"}],
                            "has_vocal": False,
                            "tempo_bpm": 90,
                        }
                    ],
                    "pagination_data": {"total_items": 1},
                }
                return FakeResponse(json.dumps(payload).encode("utf-8"))
            return FakeResponse(b"fake mp3")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with (
                patch.object(services.urllib.request, "urlopen", side_effect=fake_urlopen),
                patch.object(services.storage, "project_file", side_effect=lambda _project_id, relative: root / relative),
                patch.object(services, "recent_loudly_track_ids", return_value=set()),
                patch.object(services, "safe_probe_duration", return_value=190.0),
            ):
                result = services.loudly_search_bgm(
                    53,
                    {"mood": "privacy_investigation", "bpm": [76, 102]},
                    "loudly-key",
                    170.0,
                )

        search_url = next(url for url in requested_urls if "/api/songs?" in url)
        self.assertEqual(result["track"]["id"], "loudly-42")
        self.assertEqual(result["track"]["provider"], "loudly")
        self.assertEqual(result["track"]["duration"], 190.0)
        self.assertIn("mood=Dark", search_url)
        self.assertIn("genre=Ambient", search_url)
        self.assertTrue(all(value == "loudly-key" for value in requested_api_keys))

    def test_jamendo_ranking_rejects_vocals_restricted_licenses_and_recent_tracks(self) -> None:
        def track(
            track_id: str,
            *,
            name: str,
            license_url: str = "https://creativecommons.org/licenses/by/4.0/",
            instrumental: str = "instrumental",
            popularity: int = 100,
            rank: int = 1,
        ) -> dict[str, object]:
            return {
                "id": track_id,
                "name": name,
                "album_name": "Documentary Soundtrack",
                "duration": 180,
                "license_ccurl": license_url,
                "audiodownload_allowed": True,
                "audiodownload": f"https://example.com/{track_id}.mp3",
                "content_id_free": True,
                "musicinfo": {
                    "vocalinstrumental": instrumental,
                    "tags": {"genres": ["electronic"], "instruments": ["piano"], "vartags": ["suspense"]},
                },
                "stats": {"listened": popularity, "downloaded": popularity // 10, "likes": popularity // 20},
                "_catalog_rank": rank,
            }

        ranked = services.rank_jamendo_bgm_candidates(
            [
                track("recent", name="Electronic Privacy Suspense", popularity=10000),
                track("fresh", name="Electronic Privacy Suspense", popularity=800, rank=2),
                track("vocal", name="Electronic Privacy Song", instrumental="vocal", popularity=50000),
                track(
                    "non-commercial",
                    name="Electronic Privacy Suspense",
                    license_url="https://creativecommons.org/licenses/by-nc/4.0/",
                    popularity=50000,
                ),
                track("sfx", name="Privacy Sound Effect", popularity=50000),
            ],
            {"query": "electronic privacy suspense", "tags": ["electronic", "privacy", "suspense"]},
            {"recent"},
            170.0,
        )

        self.assertEqual([item["id"] for item in ranked], ["fresh", "recent"])
        self.assertEqual(ranked[0]["recent_repeat_penalty"], 0.0)
        self.assertGreater(ranked[1]["recent_repeat_penalty"], 0.0)

    def test_jamendo_search_requests_full_instrumental_commercial_tracks(self) -> None:
        requested_urls: list[str] = []

        class FakeResponse:
            def __init__(self, payload: bytes) -> None:
                self.payload = payload

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def read(self, *_args: object) -> bytes:
                return self.payload

        def fake_urlopen(request: object, timeout: int = 0) -> FakeResponse:
            del timeout
            url = str(getattr(request, "full_url", request))
            requested_urls.append(url)
            if "api.jamendo.com/v3.0/tracks/" in url:
                payload = {
                    "headers": {"code": 0, "status": "success"},
                    "results": [
                        {
                            "id": "7042",
                            "name": "Privacy Pulse",
                            "artist_id": "77",
                            "artist_name": "Studio Artist",
                            "album_name": "Documentary",
                            "duration": 190,
                            "license_ccurl": "https://creativecommons.org/licenses/by/4.0/",
                            "audiodownload_allowed": True,
                            "audiodownload": "https://example.com/7042.mp3",
                            "shareurl": "https://www.jamendo.com/track/7042",
                            "content_id_free": True,
                            "musicinfo": {
                                "vocalinstrumental": "instrumental",
                                "tags": {"genres": ["electronic"], "instruments": [], "vartags": ["suspense"]},
                            },
                            "stats": {"listened": 5000, "downloaded": 200, "likes": 50},
                        }
                    ],
                }
                return FakeResponse(json.dumps(payload).encode("utf-8"))
            return FakeResponse(b"fake mp3")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with (
                patch.object(services.urllib.request, "urlopen", side_effect=fake_urlopen),
                patch.object(services.storage, "project_file", side_effect=lambda _project_id, relative: root / relative),
                patch.object(services, "recent_jamendo_track_ids", return_value=set()),
                patch.object(services, "safe_probe_duration", return_value=190.0),
            ):
                result = services.jamendo_search_bgm(
                    53,
                    {"mood": "privacy_investigation", "query": "privacy suspense", "tags": ["privacy", "suspense"]},
                    "client-id",
                    170.0,
                )

        search_url = next(url for url in requested_urls if "api.jamendo.com/v3.0/tracks/" in url)
        self.assertEqual(result["track"]["id"], "7042")
        self.assertEqual(result["track"]["provider"], "jamendo")
        self.assertIn("vocalinstrumental=instrumental", search_url)
        self.assertIn("durationbetween=75_600", search_url)
        self.assertIn("boost=popularity_total", search_url)
        self.assertIn("ccnc=false", search_url)
        self.assertIn("ccnd=false", search_url)
        self.assertIn("ccsa=false", search_url)

    def test_high_confidence_theme_rejects_ai_mood_drift(self) -> None:
        fallback = {
            "mood": "privacy_investigation",
            "mood_locked": True,
            "confidence_score": 88.6,
            "query": "digital privacy investigation minimal pulse documentary underscore",
            "tags": ["privacy", "investigation"],
            "bpm": [76, 102],
            "reason": "偷听、麦克风和隐私是本期主冲突。",
        }
        ai_payload = {
            "mood": "warm_warning",
            "query": "warm piano family background",
            "tags": ["warm", "piano"],
            "bpm": [60, 80],
            "reason": "结尾比较温暖。",
            "provider": "deepseek-bgm-selector:test",
        }

        normalized = services.normalize_bgm_brief(ai_payload, fallback)

        self.assertEqual(normalized["mood"], "privacy_investigation")
        self.assertEqual(normalized["rejected_mood"], "warm_warning")
        self.assertEqual(normalized["bpm"], [76, 102])
        self.assertIn("privacy", normalized["query"])

    def test_bgm_brief_does_not_literalize_the_problem_noise(self) -> None:
        normalized = services.normalize_bgm_brief(
            {
                "mood": "tech_suspense",
                "query": "subtle digital static investigative ambient texture",
                "tags": ["electronic", "static", "noise texture"],
                "instrumentation": ["low frequency hum", "pulsing synth", "fan noise"],
                "reason": "用底噪和嗡鸣呼应耳机问题。",
            },
            {
                "mood": "tech_suspense",
                "query": "cinematic suspense technology pulse instrumental music",
                "tags": ["cinematic", "technology", "instrumental"],
                "instrumentation": ["restrained synth pulse"],
                "reason": "用科技悬疑纯音乐承接口播情绪。",
                "bpm": [78, 108],
            },
        )

        self.assertEqual(
            normalized["query"],
            "cinematic suspense technology pulse instrumental music",
        )
        self.assertNotIn("static", normalized["tags"])
        self.assertNotIn("noise texture", normalized["tags"])
        self.assertEqual(normalized["instrumentation"], ["pulsing synth"])
        self.assertNotIn("底噪", normalized["reason"])
        self.assertIn("hiss static buzzing", normalized["avoid"])

    def test_bgm_mix_uses_voice_sidechain_and_edge_fades(self) -> None:
        filters, audio_map = services.build_bgm_mix_filters(5, 6, 120.0, 0.17)
        serialized = ";".join(filters)

        self.assertEqual(audio_map, "[aout]")
        self.assertIn("asplit=2[a_voice_mix][a_voice_key]", serialized)
        self.assertIn("sidechaincompress=", serialized)
        self.assertIn("afade=t=in", serialized)
        self.assertIn("afade=t=out:st=118.200:d=1.800", serialized)
        self.assertIn("volume=0.170", serialized)
        self.assertIn("normalize=0", serialized)

    def test_bgm_mix_clamps_excessive_background_volume(self) -> None:
        filters, _audio_map = services.build_bgm_mix_filters(1, 2, 30.0, 0.9)
        self.assertIn("volume=0.350", ";".join(filters))

    def test_project_bgm_settings_clamp_volume_and_invalidate_mix_preview(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            preview = root / "audio/bgm_mix_preview.mp3"
            preview_meta = root / "audio/bgm_mix_preview.json"
            preview.parent.mkdir(parents=True, exist_ok=True)
            preview.write_bytes(b"old preview")
            preview_meta.write_text("{}", encoding="utf-8")
            with patch.object(
                services.storage,
                "project_file",
                side_effect=lambda _project_id, relative: root / relative,
            ):
                result = services.update_project_bgm_settings(53, volume=0.9, track_locked=True)

            self.assertEqual(result["volume"], 0.35)
            self.assertTrue(result["track_locked"])
            self.assertFalse(preview.exists())
            self.assertFalse(preview_meta.exists())

    def test_bgm_mix_preview_uses_voice_sidechain_and_saved_volume(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            voice = root / "audio/podcast.mp3"
            bgm = root / "bgm.mp3"
            voice.parent.mkdir(parents=True, exist_ok=True)
            voice.write_bytes(b"voice")
            bgm.write_bytes(b"bgm")
            captured: list[str] = []

            def fake_run(command: list[str], **_kwargs: object) -> SimpleNamespace:
                captured.extend(command)
                Path(command[-1]).write_bytes(b"preview" * 400)
                return SimpleNamespace(returncode=0, stderr="", stdout="")

            with (
                patch.object(services.storage, "project_file", side_effect=lambda _project_id, relative: root / relative),
                patch.object(services, "project_bgm_status", return_value={"path": bgm.as_posix(), "volume": 0.22}),
                patch.object(services, "safe_probe_duration", return_value=60.0),
                patch.object(services.subprocess, "run", side_effect=fake_run),
            ):
                result = services.ensure_project_bgm_mix_preview(53)

            serialized = " ".join(captured)
            self.assertTrue(Path(result["path"]).exists())
            self.assertIn("sidechaincompress=", serialized)
            self.assertIn("volume=0.220", serialized)
            self.assertTrue(result["voice_sidechain"])

    def test_visual_master_fingerprint_tracks_visual_inputs_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cover = root / "cover.png"
            scene = root / "scene.png"
            subtitles = root / "subtitles.srt"
            cover.write_bytes(b"cover-v1")
            scene.write_bytes(b"scene-v1")
            subtitles.write_text("1\n00:00:00,000 --> 00:00:02,000\n第一版字幕\n", encoding="utf-8")
            segments = [
                {"path": cover, "source_duration": 5.0, "motion": "quick_push_in"},
                {"path": scene, "source_duration": 25.0, "motion": "slow_push_in"},
            ]
            with patch.object(services.storage, "project_dir", return_value=root):
                first = services.visual_master_context(53, segments, subtitles, 30.0)
                unchanged = services.visual_master_context(53, segments, subtitles, 30.0)
                subtitles.write_text("1\n00:00:00,000 --> 00:00:02,000\n字幕已经发生变化\n", encoding="utf-8")
                changed = services.visual_master_context(53, segments, subtitles, 30.0)

        self.assertEqual(first["fingerprint"], unchanged["fingerprint"])
        self.assertNotEqual(first["fingerprint"], changed["fingerprint"])
        self.assertNotIn("bgm", first)

    def test_ffmpeg_progress_maps_encoder_time_to_job_percent(self) -> None:
        class FakeProcess:
            def __init__(self) -> None:
                self.stdout = iter(
                    [
                        "out_time_us=5000000\n",
                        "progress=continue\n",
                        "out_time_us=10000000\n",
                        "progress=end\n",
                    ]
                )

            def wait(self) -> int:
                return 0

            def poll(self) -> int:
                return 0

            def kill(self) -> None:
                return None

        events: list[dict[str, object]] = []
        with patch.object(services.subprocess, "Popen", return_value=FakeProcess()) as popen:
            services.run_ffmpeg_with_progress(
                ["ffmpeg", "-y", "output.mp4"],
                10.0,
                phase="visual_master",
                message="正在构建画面母版",
                progress_callback=events.append,
                percent_start=10.0,
                percent_end=90.0,
            )

        command = popen.call_args.args[0]
        self.assertIn("-progress", command)
        self.assertEqual(events[0]["percent"], 10.0)
        self.assertTrue(any(event.get("percent") == 50.0 for event in events))
        self.assertEqual(events[-1]["percent"], 90.0)
        self.assertEqual(events[-1]["eta_seconds"], 0)

    def test_bgm_only_quality_refresh_reuses_non_video_sections(self) -> None:
        source_hashes = {"policy_version": "quality-sections-v1", "content_hash": "same"}
        cached = {
            "source_hashes": source_hashes,
            "sections": {
                "content": {"score": 96, "issues": []},
                "director": {"score": 95, "issues": []},
                "images": {"score": 94, "issues": []},
                "video": {"score": 80, "issues": []},
                "supervisors": {"score": 93, "issues": [], "next_actions": []},
            },
        }
        with (
            patch.object(services, "quality_gate_source_hashes", return_value=source_hashes),
            patch.object(services, "video_quality_report", return_value={"score": 99, "issues": []}),
            patch.object(services.storage, "get_project", return_value={"topic_name": "测试主题"}),
        ):
            self.assertTrue(services.quality_gate_non_video_sections_current(53, cached, "brief", "content"))
            refreshed = services.refresh_quality_gate_video_section(53, cached, "brief", "content")

        self.assertEqual(refreshed["sections"]["video"]["score"], 99)
        self.assertEqual(refreshed["sections"]["images"]["score"], 94)
        self.assertEqual(refreshed["overall_score"], 93)
        self.assertEqual(refreshed["reused_sections"], ["content", "director", "images", "supervisors"])

    def test_key_image_hold_time_is_visual_note_not_script_penalty(self) -> None:
        lines = [
            "但是第一处反差已经出现",
            "其实第二处证据更关键",
            "结果第三处结论完全相反",
            "真正的问题现在才出现",
            "评论区只写一个经历",
        ]
        with (
            patch.object(services.storage, "get_project", return_value={"id": 1, "topic_name": "测试", "template": "", "template_mode": "video"}),
            patch.object(services.storage, "get_content", return_value="测试内容"),
            patch.object(services, "content_body_lines", return_value=lines),
            patch.object(services, "parse_dialogue_lines", return_value=lines),
            patch.object(services, "content_engagement_report", return_value={"overall_score": 5, "opening_score": 5, "retention_score": 5, "interaction_score": 5}),
            patch.object(services, "script_bad_phrase_hits", return_value=[]),
            patch.object(services, "hollow_script_report", return_value={"hollow": False, "hits": []}),
            patch.object(services, "resolved_scene_prompt_plan", return_value=[{}] * 5),
            patch.object(services, "safe_probe_duration", return_value=150.0),
            patch.object(services, "estimate_spoken_duration_sec", return_value=(240, 50.0)),
        ):
            report = services.script_rhythm_report(1)

        # Other script-quality checks may lower the score; this test only
        # verifies that long visual hold time stays informational.
        self.assertGreaterEqual(report["score"], 70)
        self.assertEqual(report["metrics"]["avg_scene_hold_sec"], 30.0)
        self.assertEqual(report["visual_notes"][0]["where"], "画面停留")
        self.assertFalse(any(item.get("where") == "画面停留" for item in report["issues"]))

    def test_informative_long_tech_script_has_no_duration_only_blocker(self) -> None:
        lines = [
            "发布五天，模型就暂停订阅。",
            "但是第一处反差已经出现。",
            "其实第二处证据更关键。",
            "结果第三处结论完全相反。",
            "评论区只写一个经历。",
        ]
        with (
            patch.object(services.storage, "get_project", return_value={"id": 1, "topic_name": "测试", "template": "科技情报站", "template_mode": "video"}),
            patch.object(services.storage, "get_template", return_value={"name": "科技情报站", "mode": "video"}),
            patch.object(services.storage, "get_content", return_value="测试内容"),
            patch.object(services, "content_body_lines", return_value=lines),
            patch.object(services, "parse_dialogue_lines", return_value=lines),
            patch.object(services, "content_engagement_report", return_value={"overall_score": 5, "opening_score": 5, "retention_score": 5, "interaction_score": 5}),
            patch.object(services, "script_bad_phrase_hits", return_value=[]),
            patch.object(services, "resolved_scene_prompt_plan", return_value=[{}] * 5),
            patch.object(services, "safe_probe_duration", return_value=150.0),
            patch.object(services, "estimate_spoken_duration_sec", return_value=(760, 158.0)),
        ):
            report = services.script_rhythm_report(1)

        self.assertFalse(any(item.get("where") == "留存时长" for item in report["issues"]))
        self.assertEqual(report["metrics"]["retention_maximum_sec"], 0)
        self.assertGreaterEqual(report["metrics"]["retention_soft_maximum_sec"], report["metrics"]["retention_target_sec"])

    def test_retention_compression_does_not_delete_evidence_to_hit_a_stopwatch(self) -> None:
        dialogue = "\n".join(
            [
                "【主播】这个结果会直接改变你的判断，先看证据。",
                "【主播】第一组调查给出了完全相反的答案。",
                "【主播】很多人认可人工智能带来的效率。",
                "【主播】但是他们同时担心工作和隐私。",
                "【主播】这句话只是重复解释前面的矛盾。",
                "【主播】先别急，真正容易忽略的点在后面。",
                "【主播】企业已经开始把模型放进真实工作流。",
                "【主播】一边担心被替代，一边又每天使用它。",
                "【主播】有人用它整理资料，有人用它检查代码，还有人让它先做方案。",
                "【主播】这些使用场景不是概念，它们已经进入每天的工作流程。",
                "【主播】另一边，隐私、岗位变化和错误回答仍然让很多人犹豫。",
                "【主播】同一批人会在效率和风险之间来回摇摆，这正是矛盾来源。",
                "【主播】只重复讨论态度没有意义，真正重要的是建立可验证的使用边界。",
                "【主播】把低风险任务先交出去，重要结果仍由人复核，判断会更具体。",
                *[
                    f"【主播】第{index}个补充说明继续解释同一个背景，用来模拟需要压缩的重复论证内容。"
                    for index in range(1, 9)
                ],
                "【主播】所以不要只问信不信，先做一次可控测试。",
                "【主播】对比质量、时间和风险，再决定交出多少工作。",
                "【主播】评论区写下你最不敢交给人工智能的一件事。",
                "【主播】这才是这份调查真正提醒你的地方。",
            ]
        )
        content = f"# 测试\n\n## 口播脚本\n\n{dialogue}\n\n## 重点字幕\n\n1. 测试"
        with (
            patch.object(services.storage, "get_project", return_value={"id": 1, "topic_name": "测试", "template": "科技情报站", "template_mode": "video"}),
            patch.object(services.storage, "get_template", return_value={"name": "科技情报站", "mode": "video"}),
            patch.object(services, "refresh_content_image_prompts", side_effect=lambda _p, _t, value: value),
            patch.object(services, "repair_script_bad_phrases_text", side_effect=lambda value, _topic, _mode: (value, [])),
            patch.object(services.storage, "save_report"),
        ):
            result = services.compress_content_to_retention_budget(1, content, save=False)

        self.assertFalse(result["changed"])
        self.assertEqual(result["after_duration_sec"], result["before_duration_sec"])
        self.assertIn("这个结果会直接改变你的判断", result["content"])
        self.assertIn("评论区写下你最不敢交给人工智能的一件事", result["content"])

    def test_short_tech_script_reports_missing_content_depth(self) -> None:
        lines = [
            "这台设备正在悄悄多收你的钱。",
            "参数看起来很强。",
            "实际体验却不是这样。",
            "评论区说说你的经历。",
        ]
        with (
            patch.object(services.storage, "get_project", return_value={"id": 1, "topic_name": "测试", "template": "科技情报站", "template_mode": "video"}),
            patch.object(services.storage, "get_template", return_value={"name": "科技情报站", "mode": "video"}),
            patch.object(services.storage, "get_brief", return_value=""),
            patch.object(services.storage, "get_content", return_value="测试内容"),
            patch.object(services, "content_body_lines", return_value=lines),
            patch.object(services, "parse_dialogue_lines", return_value=lines),
            patch.object(services, "content_engagement_report", return_value={"overall_score": 5, "opening_score": 5, "retention_score": 5, "interaction_score": 5}),
            patch.object(services, "script_bad_phrase_hits", return_value=[]),
            patch.object(services, "resolved_scene_prompt_plan", return_value=[{}] * 3),
            patch.object(services, "safe_probe_duration", return_value=40.0),
            patch.object(services, "estimate_spoken_duration_sec", return_value=(170, 35.0)),
        ):
            report = services.script_rhythm_report(1)

        issue = next(item for item in report["issues"] if item.get("where") == "内容深度")
        self.assertEqual(issue["level"], "risk")
        self.assertEqual(report["metrics"]["retention_minimum_sec"], 75)

    def test_hollow_fallback_script_is_rejected_as_editorial_scaffolding(self) -> None:
        content = """# 测试

## 对话脚本

【女】别上来背概念，先说那个最容易让人误判的瞬间。
【男】这种题最容易写成解释文，真正决定结果的往往是被忽略的小动作。
【女】表面看是一个问题，真正关键其实藏在另一层？
【男】最有效的讲法，就是把它放进一个真实场景里。
【男】下次你再碰到这个题，先找那个真正决定结果的点。
"""

        report = services.hollow_script_report(content, "video")

        self.assertTrue(report["hollow"])
        self.assertGreaterEqual(len(report["hits"]), 3)

    def test_direct_deepseek_request_does_not_depend_on_openai_sdk(self) -> None:
        response = {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": "# 完整文案"},
                }
            ]
        }
        with patch.object(services, "_request_provider_json", return_value=response) as request:
            content, finish_reason = services.request_deepseek_chat_completion(
                api_key="key",
                base_url="https://api.deepseek.com",
                model="deepseek-chat",
                messages=[{"role": "user", "content": "写稿"}],
                temperature=0.5,
                max_tokens=1000,
            )

        self.assertEqual(content, "# 完整文案")
        self.assertEqual(finish_reason, "stop")
        self.assertEqual(request.call_args.args[1], "https://api.deepseek.com/chat/completions")
        self.assertEqual(request.call_args.args[2]["User-Agent"], "short-video-studio/1.0")

    def test_gateway_preserves_requested_completion_budget(self) -> None:
        response = {"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]}
        with patch.object(services, "_request_provider_json", return_value=response) as request:
            services.request_deepseek_chat_completion(
                api_key="key",
                base_url="https://gateway.example/v1",
                model="deepseek-chat",
                messages=[],
                temperature=0.1,
                max_tokens=7000,
            )

        self.assertEqual(request.call_args.args[3]["max_tokens"], 7000)

    def test_model_name_in_price_context_is_not_parsed_as_yuan(self) -> None:
        claims = services.extract_contextual_price_claims(
            "隆鑫是谁？就是给张雪最便宜那辆 600V 提供发动机的公司。"
        )

        self.assertEqual(claims, [])

    def test_auto_video_failure_reason_exposes_child_gate_blocker(self) -> None:
        reason = services.production_job_failure_reason(
            {
                "error": "文案生产前闸门未通过，已停止进入下一步。",
                "log": "[gate] 阻止：留存时长 - 口播约 100 秒，超过频道上限。",
            }
        )

        self.assertIn("文案生产前闸门未通过", reason)
        self.assertIn("留存时长", reason)
        self.assertNotIn("images_missing", reason)

    def test_incomplete_video_mode_treats_rhythm_as_advisory(self) -> None:
        report = {
            "passed": False,
            "blockers": [
                services.quality_issue("risk", "文案节奏", "节奏体检只有 46 分。", "建议优化文案。"),
            ],
        }
        gate = {
            "passed": False,
            "issues": [
                services.quality_issue("risk", "文案节奏", "节奏体检只有 46 分。", "建议优化文案。"),
                services.quality_issue("risk", "图片确认", "当前图片尚未人工确认。", "确认图片。"),
            ],
            "details": {"preflight": report, "image_hard_risk": False},
        }

        self.assertEqual(services.pre_video_technical_blockers(report), [])
        self.assertTrue(services.pre_video_gate_can_continue_incomplete(gate))

    def test_incomplete_video_mode_still_blocks_missing_subtitles(self) -> None:
        subtitle_issue = services.quality_issue("risk", "字幕", "缺少 subtitles.srt。", "重新生成字幕。")
        report = {"passed": False, "blockers": [subtitle_issue]}
        gate = {
            "passed": False,
            "issues": [subtitle_issue],
            "details": {"preflight": report, "image_hard_risk": False},
        }

        self.assertEqual(services.pre_video_technical_blockers(report), [subtitle_issue])
        self.assertFalse(services.pre_video_gate_can_continue_incomplete(gate))

    def test_video_step_continues_past_editorial_score_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scene_path = root / "scenes" / "s_01.png"
            scene_path.parent.mkdir(parents=True)
            scene_path.write_bytes(b"image")

            def fake_compose(_project_id, _title, _scenes, _audio, _subtitle, output, _progress):
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b"video")
                return output

            runtime = services.JobRuntime()
            logs: list[str] = []
            with (
                patch.object(
                    services,
                    "video_preflight_report",
                    return_value={
                        "passed": False,
                        "blockers": [services.quality_issue("risk", "文案节奏", "节奏体检只有 46 分。", "建议优化文案。")],
                        "warnings": [],
                    },
                ),
                patch.object(services.storage, "project_file", side_effect=lambda _project_id, relative: root / relative),
                patch.object(services.storage, "get_template", return_value={}),
                patch.object(services.storage, "read_json", return_value={}),
                patch.object(services.storage, "load_latest_job", return_value={"id": "test-job"}),
                patch.object(services.storage, "save_latest_job"),
                patch.object(services.storage, "save_report"),
                patch.object(services, "find_scene_image_paths", return_value=[scene_path]),
                patch.object(services, "compose_final_video", side_effect=fake_compose),
                patch.object(services, "quality_gate_report", return_value={"overall_score": 46, "verdict": "提醒"}),
            ):
                handled, _ = asyncio.run(
                    runtime._handle_real_step(
                        1,
                        {"id": 1, "template": "test", "template_mode": "video", "topic_name": "测试"},
                        "测试",
                        "video",
                        "# 测试",
                        ["测试镜头"],
                        logs,
                        "test-job",
                        allow_incomplete_video=True,
                    )
                )

            self.assertTrue(handled)
            self.assertTrue((root / "releases" / "final-video.mp4").exists())
            self.assertTrue(any("带质量提醒进入合成" in line for line in logs))

    def test_pre_video_auto_fix_routes_rhythm_blocker_to_content_repair(self) -> None:
        before = {
            "key": "pre_video_gate",
            "score": 70,
            "passed": False,
            "status": "failed",
            "issues": [{"level": "risk", "where": "文案节奏", "issue": "节奏体检只有 70 分。"}],
            "details": {},
        }
        after = {
            "key": "pre_video_gate",
            "score": 90,
            "passed": True,
            "status": "passed",
            "issues": [],
            "details": {},
        }
        with (
            patch.object(services, "evaluate_production_stage_gate", side_effect=[before, after]),
            patch.object(services, "enhance_content_rhythm", return_value={"result": {"changed": True}}) as enhance,
            patch.object(services, "pre_video_gate_repair_targets", return_value=[]),
            patch.object(services, "runtime_env", return_value={}),
            patch.object(services, "save_stage_gate_result"),
        ):
            result = services.run_production_stage_gate(54, "pre_video_gate", auto_fix=True)

        enhance.assert_called_once_with(54, save=True)
        self.assertTrue(result["passed"])
        self.assertTrue(result["content_changed"])
        self.assertIn("文案节奏阻断已修复", result["actions"])

    def test_pre_video_manual_review_creates_one_candidate_without_overwriting_official(self) -> None:
        before = {
            "key": "pre_video_gate",
            "score": 55,
            "passed": False,
            "status": "failed",
            "issues": [{"level": "risk", "where": "scenes/s_01.png", "issue": "图片与口播贴合偏弱。"}],
            "details": {},
        }
        after = {**before, "score": 60}
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scene_dir = root / "scenes"
            scene_dir.mkdir(parents=True)
            official = scene_dir / "s_01.png"
            official.write_bytes(b"OLD" * 2000)

            def fake_generate(_prompt, output_path, *_args, **_kwargs):
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"NEW" * 2000)
                output_path.with_suffix(".md").write_text("当前主题和口播提示词", encoding="utf-8")
                output_path.with_suffix(".audit.json").write_text(
                    json.dumps({"ok": True, "severity": "ok"}),
                    encoding="utf-8",
                )
                return output_path

            with (
                patch.object(services, "cached_stage_gate_result", return_value=None),
                patch.object(services, "evaluate_production_stage_gate", side_effect=[before, after]),
                patch.object(services, "pre_video_gate_repair_targets", return_value=[("scene", "s_01.png")]),
                patch.object(services, "current_scene_prompts", return_value=["本期主题：测试。当前完整口播：测试口播。"]),
                patch.object(services, "preflight_generation_prompt_batch", return_value={"passed": True}),
                patch.object(services, "project_image_repair_prompt", return_value="本期主题：测试。当前完整口播：测试口播。"),
                patch.object(services, "image_review_status", return_value={"required": True, "scene_candidate_pending_indexes": []}),
                patch.object(services, "generate_configured_image_safely", side_effect=fake_generate),
                patch.object(services, "_save_scene_repair_candidate", return_value={}) as save_candidate,
                patch.object(services, "regenerate_project_image") as direct_redraw,
                patch.object(services, "runtime_env", return_value={}),
                patch.object(services, "stage_gate_source_fingerprint", return_value="fingerprint"),
                patch.object(services, "save_stage_gate_result"),
                patch.object(services.storage, "project_file", side_effect=lambda _project_id, relative: root / relative),
                patch.object(services.storage, "get_project", return_value={"template": "", "template_mode": "video", "topic_name": "测试"}),
                patch.object(services.storage, "get_content", return_value="测试口播"),
            ):
                result = services.run_production_stage_gate(54, "pre_video_gate", auto_fix=True)

            self.assertTrue(result["waiting_for_human"])
            self.assertEqual(result["manual_candidates_created"], 1)
            self.assertEqual(official.read_bytes(), b"OLD" * 2000)
            self.assertTrue((scene_dir / "candidates" / "s_01_r.png").exists())
            save_candidate.assert_called_once()
            direct_redraw.assert_not_called()

    def test_stage_gate_closed_loop_stops_when_candidate_waits_for_human(self) -> None:
        waiting = {
            "key": "pre_video_gate",
            "score": 60,
            "passed": False,
            "status": "waiting_human",
            "waiting_for_human": True,
            "issues": [{"where": "图片确认", "issue": "等待采用候选"}],
            "actions": ["已生成待审替换图"],
        }
        with (
            patch.object(services, "run_production_stage_gate", return_value=waiting) as run_gate,
            patch.object(services, "save_stage_gate_result"),
        ):
            result = services.run_production_stage_gate_closed_loop(54, "pre_video_gate", max_rounds=3)

        run_gate.assert_called_once()
        self.assertEqual(result["closed_loop_rounds"], 1)
        self.assertTrue(result["waiting_for_human"])

    def test_audio_specific_callout_is_ranked_before_generic_ai_labels(self) -> None:
        entry = {
            "semantic_context": {
                "speech": "AI最擅长说一堆正确的废话，听起来没错，但没有任何有效信息。",
            },
            "final_prompt": "年轻人在电脑前修改 AI 文案",
        }
        candidates = services.scene_callout_candidates_for_entry(entry, "AI写作改稿花了3小时")
        self.assertEqual(candidates[0], "正确废话")

    def test_ignore_weak_images_accepts_low_score_but_not_cross_topic_pollution(self) -> None:
        weak = {
            "level": "risk",
            "where": "scenes/s_01.png",
            "issue": "图片与主题/口播贴合偏弱：55 分，主题关键词贴合偏弱。",
            "fix": "把本期主题里的核心名词放进画面。",
        }
        polluted = {
            "level": "risk",
            "where": "scenes/s_01.png",
            "issue": "提示词混入跨题材短词：自动扣费。",
            "fix": "删除旧项目词。",
        }
        self.assertTrue(services.is_ignorable_image_quality_issue(weak))
        self.assertFalse(services.is_ignorable_image_quality_issue(polluted))

    def test_pre_video_auto_fix_targets_the_reported_scene_image(self) -> None:
        result = {
            "issues": [
                {
                    "level": "risk",
                    "where": "scenes/s_06.png",
                    "issue": "图片与主题/口播贴合偏弱：58 分。",
                },
                {
                    "level": "risk",
                    "where": "音频",
                    "issue": "缺少 podcast.mp3。",
                },
            ]
        }
        self.assertEqual(services.pre_video_gate_repair_targets(result), [("scene", "s_06.png")])

    def test_pre_video_auto_fix_targets_old_prompt_policy_image(self) -> None:
        result = {
            "issues": [
                {
                    "level": "risk",
                    "where": "scenes/s_03.png",
                    "issue": "s_03.png 仍由旧提示词策略生成，尚未按 semantic-concepts-v3 重绘。",
                }
            ]
        }

        self.assertEqual(services.pre_video_gate_repair_targets(result), [("scene", "s_03.png")])

    def test_pre_video_auto_mode_keeps_good_legacy_image_without_redraw(self) -> None:
        before = {
            "key": "pre_video_gate",
            "score": 20,
            "passed": False,
            "status": "failed",
            "issues": [
                {
                    "level": "risk",
                    "where": "scenes/s_03.png",
                    "issue": "s_03.png 仍由旧提示词策略生成。",
                }
            ],
            "details": {},
        }
        after = {**before, "score": 100, "passed": True, "status": "passed", "issues": []}
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scene_path = root / "scenes" / "s_03.png"
            scene_path.parent.mkdir(parents=True)
            scene_path.write_bytes(b"OLD" * 2000)
            with (
                patch.object(services, "evaluate_production_stage_gate", side_effect=[before, after]),
                patch.object(services, "current_scene_prompts", return_value=["提示词"] * 3),
                patch.object(services, "preflight_generation_prompt_batch", return_value={"passed": True}),
                patch.object(services, "image_review_status", return_value={"required": False, "scene_candidate_pending_indexes": []}),
                patch.object(services, "read_image_audit", return_value={"severity": "ok"}),
                patch.object(services, "keep_current_scene_image") as keep_current,
                patch.object(services, "generate_configured_image_safely") as generate,
                patch.object(services, "runtime_env", return_value={}),
                patch.object(services, "stage_gate_source_fingerprint", return_value="fingerprint"),
                patch.object(services, "save_stage_gate_result"),
                patch.object(services.storage, "project_file", side_effect=lambda _project_id, relative: root / relative),
                patch.object(services.storage, "get_project", return_value={"template": "", "template_mode": "video", "topic_name": "测试"}),
                patch.object(services.storage, "get_content", return_value="测试口播"),
            ):
                result = services.run_production_stage_gate(54, "pre_video_gate", auto_fix=True)

        keep_current.assert_called_once_with(54, 3)
        generate.assert_not_called()
        self.assertTrue(result["passed"])
        self.assertTrue(any("保留旧图" in action for action in result["actions"]))

    def test_pending_scene_prompt_redraw_indexes_only_include_expected_scenes(self) -> None:
        payload = {
            "expected_count": 2,
            "existing": [
                {"index": 1, "prompt_pending_redraw": True},
                {"index": 2, "prompt_pending_redraw": False},
                {"index": 3, "prompt_pending_redraw": True},
                {"index": "bad", "prompt_pending_redraw": True},
            ],
        }

        self.assertEqual(services.pending_scene_prompt_redraw_indexes(payload), [1])

    def test_old_prompt_policy_does_not_block_video_in_full_auto_mode(self) -> None:
        scene_status = {
            "complete": True,
            "expected_count": 1,
            "generated_count": 1,
            "existing": [{"index": 1, "prompt_pending_redraw": True}],
        }
        with (
            patch.object(services.storage, "read_json", return_value={"required": False}),
            patch.object(services.storage, "scene_status", return_value=scene_status),
            patch.object(services, "_cover_output_paths", return_value=[]),
            patch.object(services, "_scene_output_paths", return_value=[]),
        ):
            status = services.image_review_status(50)

        self.assertTrue(status["can_generate_video"])
        self.assertEqual(status["scene_pending_redraw_indexes"], [1])

    def test_old_prompt_policy_still_requires_confirmation_in_manual_mode(self) -> None:
        scene_status = {
            "complete": True,
            "expected_count": 1,
            "generated_count": 1,
            "existing": [{"index": 1, "prompt_pending_redraw": True}],
        }
        with (
            patch.object(services.storage, "read_json", return_value={"required": True}),
            patch.object(services.storage, "scene_status", return_value=scene_status),
            patch.object(services, "_cover_output_paths", return_value=[]),
            patch.object(services, "_scene_output_paths", return_value=[]),
        ):
            status = services.image_review_status(50)

        self.assertFalse(status["can_generate_video"])

    def test_pre_video_old_policy_and_soft_scores_are_not_hard_risks(self) -> None:
        old_policy = {
            "level": "risk",
            "where": "scenes/s_01.png",
            "issue": "仍由旧提示词策略生成。",
        }
        weak = {
            "level": "risk",
            "where": "scenes/s_02.png",
            "issue": "图片与当前口播贴合偏弱：58 分。",
        }
        polluted = {
            "level": "risk",
            "where": "scenes/s_03.png",
            "issue": "提示词混入跨题材短词。",
        }

        self.assertFalse(services.pre_video_image_issue_is_hard(old_policy))
        self.assertFalse(services.pre_video_image_issue_is_hard(weak))
        self.assertTrue(services.pre_video_image_issue_is_hard(polluted))

    def test_pre_video_repeated_legacy_policy_warnings_share_one_penalty(self) -> None:
        warnings = [
            {"where": f"scenes/s_{index:02d}.png", "issue": "仍由旧提示词策略生成。"}
            for index in range(1, 8)
        ]
        warnings.append({"where": "封面", "issue": "封面建议优化。"})

        self.assertEqual(services.pre_video_warning_penalty_count(warnings), 2)

    def test_new_project_image_review_defaults_to_full_auto(self) -> None:
        with (
            patch.object(services.storage, "read_json", return_value={}),
            patch.object(
                services.storage,
                "scene_status",
                return_value={"complete": False, "expected_count": 0, "generated_count": 0, "existing": []},
            ),
            patch.object(services, "_cover_output_paths", return_value=[]),
            patch.object(services, "_scene_output_paths", return_value=[]),
        ):
            status = services.image_review_status(50)

        self.assertFalse(status["required"])
        self.assertTrue(status["can_generate_video"])

    def test_image_review_treats_cover_as_optional_when_project_skips_it(self) -> None:
        scene_status = {
            "complete": True,
            "expected_count": 1,
            "generated_count": 1,
            "existing": [{"index": 1, "prompt_pending_redraw": False}],
        }
        with (
            patch.object(services.storage, "read_json", return_value={"required": True}),
            patch.object(services.storage, "scene_status", return_value=scene_status),
            patch.object(services.storage, "get_project_settings", return_value={"cover_enabled": False}),
            patch.object(services, "_cover_output_paths", return_value=[Path("missing-cover.png")]),
            patch.object(services, "_scene_output_paths", return_value=[]),
        ):
            status = services.image_review_status(50)

        self.assertTrue(status["ready_to_confirm"])
        self.assertTrue(status["covers_ready"])
        self.assertFalse(status["cover_enabled"])
        self.assertEqual(status["cover_expected"], 0)

    def test_automatic_image_review_does_not_keep_stale_candidate_reason(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            review_path = Path(temp_dir) / "image_review.json"
            review_path.write_text(
                json.dumps({"required": False, "dirty_reason": "旧候选说明"}, ensure_ascii=False),
                encoding="utf-8",
            )
            with (
                patch.object(services.storage, "project_file", return_value=review_path),
                patch.object(services, "image_review_status", return_value={"required": False}),
            ):
                services.mark_image_review_dirty(61, "场景 5 已由 AI 自动采用候选 R")

            payload = json.loads(review_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["dirty_reason"], "")

    def test_scene_information_overlay_preserves_a_source_copy(self) -> None:
        if services.Image is None:
            self.skipTest("Pillow is unavailable")
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "s_01.png"
            services.Image.new("RGB", (1280, 720), (35, 45, 55)).save(image_path)
            before = image_path.read_bytes()
            result = services.apply_scene_information_overlay(image_path, "正确废话")
            self.assertTrue(result["applied"])
            self.assertNotEqual(before, image_path.read_bytes())
            sidecar = services.scene_information_overlay_path(image_path)
            self.assertTrue(sidecar.exists())
            self.assertTrue(services.scene_information_source_path(image_path).exists())
            self.assertEqual(before, services.scene_information_source_path(image_path).read_bytes())

    def test_scene_information_overlay_renders_anchor_and_fact_chips(self) -> None:
        if services.Image is None:
            self.skipTest("Pillow is unavailable")
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "s_02.png"
            services.Image.new("RGB", (1280, 720), (188, 174, 152)).save(image_path)
            headline = "手机App不是偷听而是在建立广告画像"

            result = services.apply_scene_information_overlay(
                image_path,
                headline,
                ["麦克风权限", "广告画像"],
            )

            self.assertTrue(result["applied"])
            self.assertEqual(result["text"], headline)
            self.assertEqual(result["fact_chips"], ["麦克风权限", "广告画像"])
            self.assertEqual(result["all_text"], [headline, "麦克风权限", "广告画像"])

    def test_scene_information_headline_prefers_numeric_contrast(self) -> None:
        speech = "总参数284B，干一次活，只醒13B，推理贴着旗舰Pro走"
        self.assertEqual(services.scene_information_headline(speech), "284B总参数，只醒13B")

    def test_scene_generation_pipeline_has_no_post_typography_call(self) -> None:
        self.assertNotIn(
            "apply_scene_information_overlay",
            services.generate_configured_image_safely.__code__.co_names,
        )

    def test_cover_generation_pipeline_has_no_post_typography_call(self) -> None:
        self.assertNotIn(
            "apply_cover_typography_overlay",
            services.generate_configured_image_safely.__code__.co_names,
        )

    def test_cover_pipeline_does_not_generate_second_image_by_default(self) -> None:
        source = inspect.getsource(services.JobRuntime._handle_real_step)
        self.assertIn('get("cover_candidate_auto_enabled", False)', source)
        self.assertIn('and cover_candidate_auto_enabled', source)
        self.assertIn("单封面模式：AI 只生成一张主封面", source)
        self.assertIn("图文与竖屏比例由本地自动适配", source)
        self.assertIn("不追加生图", source)

    def test_missing_native_cover_title_is_a_hard_failure(self) -> None:
        report = services.audit_generated_image.__code__.co_consts
        self.assertIn("cover_title_missing", report)

    def test_motion_keyframe_reuses_ai_native_scene_without_overlay(self) -> None:
        source = Path("scene-with-native-text.png")

        result_path, typography = services.prepare_motion_information_keyframe(
            1,
            1,
            {"speech_text": "生成快，不等于交付快"},
            source,
        )

        self.assertEqual(result_path, source)
        self.assertFalse(typography["applied"])
        self.assertEqual(typography["mode"], "ai_native")
        self.assertEqual(typography["reason"], "scene_text_already_in_image")

    def test_motion_clips_checkpoint_each_completed_clip_and_show_prompt(self) -> None:
        source = inspect.getsource(services.generate_project_motion_clips)
        self.assertIn("save_motion_checkpoint", source)
        self.assertIn('status="generating"', source)
        self.assertIn("本次视频提示词", source)
        self.assertIn("recovered_from_disk", source)
        self.assertIn("跳过重复生成", source)

    def test_motion_clip_failure_preserves_completed_checkpoint(self) -> None:
        source = inspect.getsource(services.JobRuntime._handle_real_step)
        self.assertIn('"status": "ready" if preserved_clips else "fallback"', source)
        self.assertIn('"partial": bool(preserved_clips)', source)
        self.assertIn('"clips": preserved_clips', source)

    def test_applied_scene_typography_resolves_only_information_ocr_reason(self) -> None:
        audit = {
            "ok": False,
            "severity": "soft",
            "reasons": ["ocr_information_missing"],
            "ocr": {"information": {"passed": False, "missing": ["不是偷听，是画像"]}},
        }

        result = services.accept_applied_scene_typography(
            audit,
            {
                "applied": True,
                "text": "不是偷听，是画像",
                "all_text": ["不是偷听，是画像", "广告画像"],
            },
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["ocr"]["information"]["source"], "deterministic_typography")
        self.assertEqual(result["ocr"]["information"]["missing"], [])

    def test_scene_information_anchor_is_extracted_from_final_prompt(self) -> None:
        prompt = "人物盯着屏幕。本镜只突出一个可读信息锚点：重搭骨架；放在画面上半区。"
        self.assertEqual(services.scene_information_anchor_from_prompt(prompt), "重搭骨架")

    def test_extract_opening_hook_removes_timing_artifact(self) -> None:
        content = """# 测试

## 口播脚本

【主播】00-00:22）火锅还没夹起来，广告先弹到脸上。
【主播】第二句继续解释原因。
"""

        self.assertEqual(services.extract_opening_hook(content, "video"), "火锅还没夹起来，广告先弹到脸上。")

    def test_opening_similarity_detects_reused_surface_formula(self) -> None:
        left = "就这？火锅还没夹起来，广告先弹到脸上。"
        right = "就这？手表显示血氧93%，手指已经停在拨号键上。"

        self.assertEqual(services.opening_surface_signature(left), "就这式反问")
        self.assertEqual(services.opening_family(left), "open_loop")
        self.assertGreaterEqual(services.opening_similarity(left, right), 0.84)

    def test_opening_plan_avoids_recently_dominant_family(self) -> None:
        history = [
            {"project_id": index, "family": "open_loop", "surface": "就这式反问", "hook": f"就这？样本{index}"}
            for index in range(1, 6)
        ]
        history.append({"project_id": 9, "family": "result_first", "surface": "", "hook": "结论先说"})
        with patch.object(services, "channel_opening_history", return_value=history):
            plan = services.channel_opening_diversity_plan(
                {"id": 0, "topic_name": "手机App在偷听你聊天", "template": "tech"},
                {"key": "tech", "mode": "video"},
                brief="手机弹出刚搜索过的广告，讨论隐私风险。",
            )

        self.assertNotEqual(plan["selected_family"], "open_loop")
        self.assertIn("open_loop", plan["avoid_families"])
        self.assertIn("就这式反问", plan["forbidden_surfaces"])

    def test_repetitive_opening_repair_keeps_existing_scene_fact(self) -> None:
        content = """# 广告

## Meta
- 钩子: 就这？火锅还没夹起来，广告先弹到脸上。

## 口播脚本

【主播】就这？火锅还没夹起来，广告先弹到脸上。你是不是也以为手机在偷听？
【主播】真正原因是搜索、定位和广告画像。
"""
        before = {
            "hook": "就这？火锅还没夹起来，广告先弹到脸上。你是不是也以为手机在偷听？",
            "score": 39,
            "repetitive": True,
        }
        after = {
            "hook": "火锅还没夹起来，广告先弹到脸上。",
            "score": 100,
            "repetitive": False,
        }
        history = [
            {
                "project_id": 51,
                "topic": "智能手表",
                "hook": "就这？手表说我血氧93%。",
                "family": "open_loop",
                "surface": "就这式反问",
            }
        ]
        with (
            patch.object(services, "opening_novelty_report", side_effect=[before, after]),
            patch.object(services.storage, "get_project", return_value={"id": 54, "template": "tech", "template_mode": "video"}),
            patch.object(services.storage, "get_template", return_value={"key": "tech", "mode": "video"}),
            patch.object(services, "channel_opening_history", return_value=history),
            patch.object(
                services,
                "channel_opening_diversity_plan",
                return_value={"preferred_families": ["scene_action", "consequence"]},
            ),
        ):
            result = services.repair_channel_opening_repetition(54, content)

        self.assertTrue(result["changed"])
        self.assertEqual(result["replacement"], "火锅还没夹起来，广告先弹到脸上。")
        self.assertIn("【主播】火锅还没夹起来，广告先弹到脸上。", result["content"])
        self.assertIn("- 钩子: 火锅还没夹起来，广告先弹到脸上。", result["content"])

    def test_cta_only_change_does_not_invalidate_images_covers_or_bgm(self) -> None:
        before = """# 广告真相

## Meta
- 核心观点: 精准广告主要依赖用户画像。

## 口播脚本
【主播】火锅还没夹起来，广告先弹到脸上。
【主播】搜索、定位和浏览记录会共同形成广告画像。
【主播】你遇到过哪种广告？评论区写一个经历。
"""
        after = before.replace("你遇到过哪种广告？评论区写一个经历。", "你被哪种广告追过？评论区只写一个经历。")
        with (
            patch.object(services.storage, "get_project", return_value={"id": 54, "template": "tech", "template_mode": "video", "topic_name": "广告真相"}),
            patch.object(services.storage, "get_template", return_value={"key": "tech", "mode": "video"}),
        ):
            impact = services.content_change_impact(54, before, after)

        self.assertEqual(impact["scope"], "cta_only")
        self.assertEqual(impact["invalidate"]["scene_images"], [])
        self.assertFalse(impact["invalidate"]["covers"])
        self.assertFalse(impact["invalidate"]["bgm"])
        self.assertTrue(impact["invalidate"]["audio"])

    def test_cta_only_change_keeps_visual_manifest_identity(self) -> None:
        project = {"id": 54, "template": "tech", "template_mode": "video", "topic_name": "广告真相"}
        template = {"key": "tech", "mode": "video"}
        before = """# 广告真相

## Meta
- 核心观点: 精准广告主要依赖用户画像。

## 口播脚本
【主播】火锅还没入口，广告已经弹到脸上。
【主播】搜索、定位和浏览记录会形成广告画像。
【主播】你遇到过哪种广告？评论区写一个经历。
"""
        after = before.replace("你遇到过哪种广告？评论区写一个经历。", "你被哪种广告追过？评论区只写一个经历。")
        with (
            patch.object(services.storage, "get_template", return_value=template),
            patch.object(services, "visual_timeline_signature", return_value="same-timeline"),
        ):
            before_identity = services.visual_prompt_manifest_identity(project, before)
            after_identity = services.visual_prompt_manifest_identity(project, after)

        self.assertEqual(before_identity["content_hash"], after_identity["content_hash"])

    def test_opening_only_change_targets_first_scene(self) -> None:
        before = """# 广告真相

## Meta
- 核心观点: 精准广告主要依赖用户画像。

## 口播脚本
【主播】就这？广告又弹到脸上了。
【主播】搜索、定位和浏览记录会共同形成广告画像。
【主播】你被哪种广告追过？评论区只写一个经历。
"""
        after = before.replace("就这？广告又弹到脸上了。", "火锅还没入口，广告已经弹到脸上。")
        with (
            patch.object(services.storage, "get_project", return_value={"id": 54, "template": "tech", "template_mode": "video", "topic_name": "广告真相"}),
            patch.object(services.storage, "get_template", return_value={"key": "tech", "mode": "video"}),
        ):
            impact = services.content_change_impact(54, before, after)

        self.assertEqual(impact["scope"], "opening_only")
        self.assertEqual(impact["invalidate"]["scene_images"], ["s_01.png"])
        self.assertFalse(impact["invalidate"]["covers"])
        self.assertFalse(impact["invalidate"]["bgm"])

    def test_pre_video_gate_reuses_matching_asset_fingerprint(self) -> None:
        old_report = {
            "gates": {
                "content_gate": {
                    "key": "content_gate",
                    "label": "文案生产前闸门",
                    "status": "passed",
                    "score": 92,
                    "passed": True,
                    "source_fingerprint": "same-assets",
                    "issues": [],
                    "details": {},
                },
                "visual_prompt_gate": {
                    "key": "visual_prompt_gate",
                    "label": "新图生成前提示词闸门",
                    "status": "passed",
                    "score": 92,
                    "passed": True,
                    "source_fingerprint": "same-assets",
                    "issues": [],
                    "details": {},
                },
                "pre_video_gate": {
                    "key": "pre_video_gate",
                    "label": "成片资产闸门",
                    "status": "passed",
                    "score": 92,
                    "passed": True,
                    "source_fingerprint": "same-assets",
                    "issues": [],
                    "details": {},
                }
            }
        }
        with (
            patch.object(services.storage, "get_report", return_value=old_report),
            patch.object(services.storage, "get_project", return_value={"topic_name": "测试"}),
            patch.object(services, "stage_gate_source_fingerprint", return_value="same-assets"),
        ):
            dashboard = services.production_stage_gates_dashboard(1)

        pre_video = next(item for item in dashboard["ordered_gates"] if item["key"] == "pre_video_gate")
        self.assertTrue(pre_video["passed"])
        self.assertNotEqual(pre_video["status"], "stale")

    def test_visual_brief_default_path_does_not_call_ai(self) -> None:
        project = {"id": 9, "template": "tech", "template_mode": "video", "topic_name": "测试"}
        template = {"key": "tech", "mode": "video"}
        fallback = {"scene_count": 1, "scenes": [{"index": 1}], "source_hash": "new"}
        with (
            patch.object(services.storage, "read_json", return_value={"scene_count": 1, "scenes": [{"index": 1}], "source_hash": "old"}),
            patch.object(services, "visual_brief_is_current", return_value=False),
            patch.object(services, "save_visual_brief", side_effect=AssertionError("AI should not run")),
            patch.object(services, "build_visual_brief", return_value=fallback),
            patch.object(services.storage, "write_json") as write_json,
        ):
            result = services.get_or_create_visual_brief(project, template, "# 新文案", scene_count=1)

        self.assertEqual(result, fallback)
        write_json.assert_called_once_with(services.visual_brief_path(9), fallback)

    def test_visual_manifest_accessor_rebuilds_and_persists_stale_policy(self) -> None:
        rebuilt = {
            "covers": {
                "landscape": {"prompt": "新策略封面提示词"},
            },
            "scenes": [],
        }
        with (
            patch.object(services, "load_visual_prompt_manifest", return_value={}),
            patch.object(services, "save_visual_prompt_manifest", return_value=rebuilt) as save_manifest,
        ):
            prompt = services.visual_prompt_manifest_cover_prompt(112, "landscape", "# 新文案")

        self.assertEqual(prompt, "新策略封面提示词")
        save_manifest.assert_called_once_with(112, "# 新文案", force=True)

    def test_explicit_single_image_candidate_preserves_official_in_full_auto_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            official = root / "scenes" / "s_01.png"
            official.parent.mkdir(parents=True)
            official.write_bytes(b"O" * 5000)
            saved_reports = []

            def fake_generate(prompt, output_path, *_args, **_kwargs):
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"N" * 5000)
                output_path.with_suffix(".md").write_text(prompt, encoding="utf-8")
                output_path.with_suffix(".audit.json").write_text(
                    json.dumps({"ok": True, "severity": "ok", "attempt": 1}),
                    encoding="utf-8",
                )
                return output_path

            with (
                patch.object(services.storage, "project_file", side_effect=lambda _project_id, relative: root / relative),
                patch.object(services.storage, "get_project", return_value={"template": ""}),
                patch.object(services.storage, "get_report", return_value={}),
                patch.object(services.storage, "save_report", side_effect=lambda *args: saved_reports.append(args[2])),
                patch.object(services.storage, "scene_status", return_value={"candidate_count": 1}),
                patch.object(services, "runtime_env", return_value={}),
                patch.object(services, "save_image_prompt_control", return_value={}),
                patch.object(services, "image_review_status", return_value={"required": False}),
                patch.object(services, "resolve_image_provider_queue", return_value=[{"key": "test", "label": "测试"}]),
                patch.object(services, "generate_configured_image", side_effect=fake_generate),
                patch.object(services, "key_image_candidate_score", return_value={"score": 88, "prompt": "备选提示词"}),
                patch.object(services, "mark_image_review_dirty", return_value={}),
            ):
                result = services.regenerate_project_image(
                    1,
                    "scene",
                    "s_01.png",
                    "主题：广告真相。口播原文：广告先弹到脸上。",
                    as_candidate=True,
                )

            self.assertTrue(result["candidate"])
            self.assertEqual(official.read_bytes(), b"O" * 5000)
            self.assertTrue((root / "scenes" / "candidates" / "s_01_r.png").exists())
            self.assertEqual(saved_reports[-1]["competitions"][0]["candidate_limit"], 1)

    def test_repair_candidate_keeps_current_when_new_score_is_not_better(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            official = root / "scenes" / "s_02.png"
            candidate = root / "scenes" / "candidates" / "s_02_r.png"
            candidate.parent.mkdir(parents=True)
            official.write_bytes(b"O" * 5000)
            candidate.write_bytes(b"N" * 5000)
            saved_reports = []

            def fake_score(_project_id, path, prompt, _scene_index):
                return {"path": str(path), "score": 84 if path == official else 73, "prompt": prompt}

            with (
                patch.object(services.storage, "project_file", side_effect=lambda _project_id, relative: root / relative),
                patch.object(services.storage, "get_report", return_value={}),
                patch.object(services.storage, "save_report", side_effect=lambda *args: saved_reports.append(args[2])),
                patch.object(services, "read_generated_prompt", side_effect=lambda _path, fallback: fallback),
                patch.object(services, "key_image_candidate_score", side_effect=fake_score),
                patch.object(services, "mark_image_review_dirty", return_value={}),
            ):
                result = services._save_scene_repair_candidate(1, 2, candidate, "当前口播提示")

            competition = saved_reports[-1]["competitions"][0]
            self.assertEqual(result["score"], 73)
            self.assertEqual(competition["ai_recommended_variant"], "CURRENT")
            self.assertEqual(competition["current"]["score"], 84)

    def test_repair_candidate_does_not_auto_replace_current_without_visual_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            official = root / "scenes" / "s_02.png"
            candidate = root / "scenes" / "candidates" / "s_02_r.png"
            candidate.parent.mkdir(parents=True)
            official.write_bytes(b"O" * 5000)
            candidate.write_bytes(b"N" * 5000)
            saved_reports = []

            def fake_score(_project_id, path, prompt, _scene_index):
                return {"path": str(path), "score": 99 if path == candidate else 70, "prompt": prompt}

            with (
                patch.object(services.storage, "project_file", side_effect=lambda _project_id, relative: root / relative),
                patch.object(services.storage, "get_report", return_value={}),
                patch.object(services.storage, "save_report", side_effect=lambda *args: saved_reports.append(args[2])),
                patch.object(services, "read_generated_prompt", side_effect=lambda _path, fallback: fallback),
                patch.object(services, "key_image_candidate_score", side_effect=fake_score),
                patch.object(services, "mark_image_review_dirty", return_value={}),
            ):
                services._save_scene_repair_candidate(1, 2, candidate, "当前口播提示")

            competition = saved_reports[-1]["competitions"][0]
            self.assertEqual(competition["ai_recommended_variant"], "CURRENT")
            self.assertFalse(competition["visual_review_available"])
            self.assertEqual(official.read_bytes(), b"O" * 5000)

    def test_batch_scene_generation_adds_one_competitor_only_for_opening_scene(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            generated_paths = []

            def fake_generate(prompt, output_path, *_args, **_kwargs):
                generated_paths.append(output_path)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"I" * 5000)
                output_path.with_suffix(".md").write_text(prompt, encoding="utf-8")
                output_path.with_suffix(".audit.json").write_text(
                    json.dumps({"ok": True, "severity": "ok", "attempt": 1}),
                    encoding="utf-8",
                )
                return output_path

            prompts = [
                "本期主题：测试\n当前完整口播：第一镜",
                "本期主题：测试\n当前完整口播：第二镜",
            ]
            preflight = {
                "passed": True,
                "score": 100,
                "changed_count": 0,
                "issues": [],
                "final_prompts": {"s_01.png": prompts[0], "s_02.png": prompts[1]},
                "callout_plan": [],
            }
            runtime = services.JobRuntime()
            with (
                patch.object(services.storage, "project_file", side_effect=lambda _project_id, relative: root / relative),
                patch.object(services.storage, "get_template", return_value={}),
                patch.object(services.storage, "cleanup_extra_scene_outputs", return_value=0),
                patch.object(services.storage, "read_json", return_value=[]),
                patch.object(services.storage, "load_latest_job", return_value={}),
                patch.object(services, "runtime_env", return_value={}),
                patch.object(services, "resolve_image_provider_queue", return_value=[{"key": "test", "label": "测试"}]),
                patch.object(services, "describe_image_provider_queue", return_value="测试图片通道"),
                patch.object(services, "project_image_context_hashes", return_value={}),
                patch.object(services, "reusable_scene_image_record", return_value=None),
                patch.object(services, "preflight_generation_prompt_batch", return_value=preflight),
                patch.object(services, "generate_configured_image_safely", side_effect=fake_generate),
                patch.object(services, "build_opening_scene_candidate_prompt", return_value="首镜第二构思"),
                patch.object(
                    services,
                    "save_opening_scene_competition",
                    return_value={
                        "ai_recommended_variant": "B",
                        "current": {"score": 82},
                        "candidates": [{"variant": "B", "score": 91}],
                    },
                ),
                patch.object(services, "image_review_status", return_value={"required": True}),
                patch.object(services, "discard_scene_image_candidates") as discard_candidates,
                patch.object(services, "mark_image_review_dirty", return_value={}),
            ):
                ok, _ = asyncio.run(
                    runtime._handle_real_step(
                        1,
                        {"id": 1, "template": "test", "template_mode": "video", "topic_name": "测试"},
                        "生成场景图",
                        "images",
                        "# 测试",
                        prompts,
                        [],
                        "test-job",
                    )
                )

            self.assertTrue(ok)
            self.assertEqual(len(generated_paths), len(prompts) + 1)
            self.assertEqual([path.name for path in generated_paths], ["s_01.png", "s_01_b.png", "s_02.png"])
            self.assertEqual(sum("candidates" in path.parts for path in generated_paths), 1)
            self.assertEqual(discard_candidates.call_count, len(prompts))

    def test_images_missing_regenerates_semantically_stale_existing_scene(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            generated_paths = []
            prompts = [
                "本期主题：测试\n当前完整口播：新版第一镜",
                "本期主题：测试\n当前完整口播：第二镜",
            ]
            existing_records = [
                {"filename": "s_01.png", "prompt": "旧版第一镜"},
                {"filename": "s_02.png", "prompt": prompts[1]},
            ]

            def fake_read_json(path, default=None):
                return existing_records if Path(path).name == "scene_prompts.json" else (default if default is not None else {})

            def fake_generate(prompt, output_path, *_args, **_kwargs):
                generated_paths.append(output_path)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"I" * 5000)
                output_path.with_suffix(".md").write_text(prompt, encoding="utf-8")
                output_path.with_suffix(".audit.json").write_text(
                    json.dumps({"ok": True, "severity": "ok", "attempt": 1}),
                    encoding="utf-8",
                )
                return output_path

            preflight = {
                "passed": True,
                "score": 100,
                "changed_count": 0,
                "issues": [],
                "final_prompts": {"s_01.png": prompts[0]},
                "callout_plan": [],
            }
            runtime = services.JobRuntime()
            with (
                patch.object(services.storage, "project_file", side_effect=lambda _project_id, relative: root / relative),
                patch.object(services.storage, "get_template", return_value={}),
                patch.object(services.storage, "cleanup_extra_scene_outputs", return_value=0),
                patch.object(services.storage, "read_json", side_effect=fake_read_json),
                patch.object(services.storage, "load_latest_job", return_value={}),
                patch.object(services.storage, "scene_status", return_value={"missing_items": []}),
                patch.object(services, "stale_scene_image_indexes", return_value=[1]),
                patch.object(services, "runtime_env", return_value={}),
                patch.object(services, "resolve_image_provider_queue", return_value=[{"key": "test", "label": "测试"}]),
                patch.object(services, "describe_image_provider_queue", return_value="测试图片通道"),
                patch.object(services, "project_image_context_hashes", return_value={}),
                patch.object(services, "preflight_generation_prompt_batch", return_value=preflight),
                patch.object(services, "generate_configured_image_safely", side_effect=fake_generate),
                patch.object(services, "discard_scene_image_candidates"),
                patch.object(services, "mark_image_review_dirty", return_value={}),
            ):
                ok, _ = asyncio.run(
                    runtime._handle_real_step(
                        1,
                        {"id": 1, "template": "test", "template_mode": "video", "topic_name": "测试"},
                        "增量补图",
                        "images_missing",
                        "# 测试",
                        prompts,
                        [],
                        "test-job",
                    )
                )

            self.assertTrue(ok)
            self.assertEqual([path.name for path in generated_paths], ["s_01.png"])

    def test_scene_status_allows_ai_enhanced_prompt_when_integrity_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scene_dir = root / "scenes"
            scene_dir.mkdir(parents=True)
            image_path = scene_dir / "s_01.png"
            image_path.write_bytes(b"I" * 5000)
            (scene_dir / "scene_prompts.json").write_text(
                json.dumps(
                    [
                        {
                            "filename": "s_01.png",
                            "prompt": "主题：测试。口播原文：基础提示词。",
                            "source_prompt": "主题：测试。口播原文：基础提示词。",
                            "prompt_policy_version": "semantic-test",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            image_path.with_suffix(".audit.json").write_text(
                json.dumps(
                    {
                        "prompt": "本期主题：测试。当前完整口播：基础提示词。增强视觉概念：现场证据特写。",
                        "prompt_policy_version": "semantic-test",
                        "prompt_integrity": {"required": True, "ok": True, "missing": []},
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch.object(storage, "project_file", side_effect=lambda _project_id, relative: root / relative),
                patch.object(storage, "get_summary", return_value={"scene_count": 1}),
                patch.object(storage, "get_project_settings", return_value={"scene_count_mode": "auto", "scene_count_fixed": 6}),
            ):
                status = storage.scene_status(1)

            self.assertFalse(status["existing"][0]["prompt_pending_redraw"])

    def test_scene_status_exposes_candidate_images_instead_of_hiding_them(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scene_dir = root / "scenes"
            candidate_dir = scene_dir / "candidates"
            report_dir = root / "reports"
            candidate_dir.mkdir(parents=True)
            report_dir.mkdir(parents=True)
            (scene_dir / "s_01.png").write_bytes(b"official")
            for variant in ("a", "b"):
                path = candidate_dir / f"s_01_{variant}.png"
                path.write_bytes((variant.encode("ascii") * 5000))
                path.with_suffix(".md").write_text(f"candidate {variant}", encoding="utf-8")
                path.with_suffix(".audit.json").write_text(
                    json.dumps({"ok": True, "severity": "ok"}),
                    encoding="utf-8",
                )
            (root / "image_review.json").write_text(
                json.dumps({"required": True}),
                encoding="utf-8",
            )
            (report_dir / "key_image_candidates.json").write_text(
                json.dumps(
                    {
                        "competitions": [
                            {
                                "scene_index": 1,
                                "target": "s_01.png",
                                "selected_variant": "A",
                                "ai_recommended_variant": "A",
                                "selection_mode": "ai_recommended_pending_human",
                                "candidates": [
                                    {"variant": "A", "score": 91},
                                    {"variant": "B", "score": 86},
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch.object(storage, "project_file", side_effect=lambda _project_id, relative: root / relative),
                patch.object(storage, "get_summary", return_value={"scene_count": 1}),
                patch.object(storage, "get_project_settings", return_value={"scene_count_mode": "auto", "scene_count_fixed": 6}),
            ):
                status = storage.scene_status(1)

        self.assertEqual(status["candidate_review_mode"], "manual")
        self.assertEqual(status["candidate_count"], 2)
        self.assertEqual(len(status["candidate_groups"]), 1)
        group = status["candidate_groups"][0]
        self.assertEqual(group["selected_variant"], "A")
        self.assertTrue(group["selection_pending"])
        self.assertEqual([item["variant"] for item in group["candidates"]], ["A", "B"])
        self.assertEqual(group["candidates"][0]["score"], 91)

    def test_manual_candidate_selection_promotes_only_the_requested_variant(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            candidate_dir = root / "scenes" / "candidates"
            candidate_dir.mkdir(parents=True)
            candidate = candidate_dir / "s_02_b.png"
            candidate.write_bytes(b"B" * 5000)
            candidate.with_suffix(".md").write_text("主题：高血压药。口播原文：突然停药会反跳。", encoding="utf-8")
            candidate.with_suffix(".audit.json").write_text(
                json.dumps({"ok": True, "severity": "ok", "attempt": 1}),
                encoding="utf-8",
            )
            report = {
                "competitions": [
                    {
                        "scene_index": 2,
                        "target": "s_02.png",
                        "selected_variant": "A",
                        "ai_recommended_variant": "A",
                        "candidates": [
                            {"variant": "A", "score": 92},
                            {"variant": "B", "score": 88},
                        ],
                    }
                ]
            }
            saved_reports = []
            with (
                patch.object(services.storage, "project_file", side_effect=lambda _project_id, relative: root / relative),
                patch.object(services.storage, "get_report", return_value=report),
                patch.object(services.storage, "save_report", side_effect=lambda *args: saved_reports.append(args[2])),
                patch.object(services.storage, "scene_status", return_value={"candidate_count": 2}),
                patch.object(services, "project_image_context_hashes", return_value={}),
                patch.object(services, "mark_image_review_dirty", return_value={"required": True, "confirmed": False}),
                patch.object(services, "record_production_step", return_value={}),
            ):
                result = services.select_scene_image_candidate(1, 2, "B")

            promoted = root / "scenes" / "s_02.png"
            self.assertEqual(promoted.read_bytes(), b"B" * 5000)
            self.assertEqual(result["variant"], "B")
            self.assertEqual(saved_reports[-1]["competitions"], [])
            self.assertEqual(saved_reports[-1]["selection_history"][-1]["selection_mode"], "manual")
            self.assertEqual(saved_reports[-1]["selection_history"][-1]["variant"], "B")
            self.assertFalse(candidate.exists())

    def test_automatic_review_promotes_ai_recommendation_and_cleans_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            candidate_dir = root / "scenes" / "candidates"
            candidate_dir.mkdir(parents=True)
            candidate_a = candidate_dir / "s_02_a.png"
            candidate_b = candidate_dir / "s_02_b.png"
            candidate_a.write_bytes(b"A" * 5000)
            candidate_b.write_bytes(b"B" * 5000)
            candidate_b.with_suffix(".md").write_text("主题：高血压药。口播原文：突然停药会反跳。", encoding="utf-8")
            candidate_b.with_suffix(".audit.json").write_text(
                json.dumps({"ok": True, "severity": "ok", "attempt": 1}),
                encoding="utf-8",
            )
            report = {
                "competitions": [
                    {
                        "scene_index": 2,
                        "target": "s_02.png",
                        "selected_variant": "A",
                        "ai_recommended_variant": "B",
                        "selection_mode": "ai_recommended_pending_human",
                        "candidates": [
                            {"variant": "A", "score": 85},
                            {"variant": "B", "score": 94},
                        ],
                    }
                ]
            }
            saved_reports = []
            with (
                patch.object(services.storage, "project_file", side_effect=lambda _project_id, relative: root / relative),
                patch.object(services.storage, "get_report", return_value=report),
                patch.object(services.storage, "save_report", side_effect=lambda *args: saved_reports.append(args[2])),
                patch.object(services.storage, "scene_status", return_value={"candidate_count": 0}),
                patch.object(services, "project_image_context_hashes", return_value={}),
                patch.object(services, "mark_image_review_dirty", return_value={"required": False, "confirmed": False}),
                patch.object(services, "record_production_step", return_value={}),
            ):
                result = services.resolve_scene_candidates_automatically(1)

            official = root / "scenes" / "s_02.png"
            self.assertEqual(result["resolved_count"], 1)
            self.assertEqual(result["resolved"][0]["variant"], "B")
            self.assertEqual(official.read_bytes(), b"B" * 5000)
            self.assertFalse(candidate_a.exists())
            self.assertFalse(candidate_b.exists())
            self.assertEqual(saved_reports[-1]["competitions"], [])
            self.assertEqual(saved_reports[-1]["selection_history"][-1]["selection_mode"], "ai_auto")
            records = json.loads((root / "scenes" / "scene_prompts.json").read_text(encoding="utf-8"))
            self.assertFalse(records[0].get("manual_image_accepted", False))

    def test_opening_candidate_score_includes_title_hook_contract(self) -> None:
        with (
            patch.object(
                services,
                "image_asset_metrics",
                return_value={"contrast": 30, "edge_score": 8},
            ),
            patch.object(services, "image_semantic_context_map", return_value={"scenes/s_01.png": {}}),
            patch.object(
                services,
                "image_appeal_score",
                return_value={"score": 80, "semantic": {"speech": 74, "audio_anchor": 82}},
            ),
            patch.object(
                services,
                "read_image_audit",
                return_value={"severity": "ok", "ocr": {"fact_coverage_score": 90, "text": "关键事实"}},
            ),
            patch.object(
                services,
                "opening_visual_contract",
                return_value={"title": "手机偷听", "opening_line": "刚聊完就收到广告"},
            ),
            patch.object(
                services,
                "opening_visual_alignment_score",
                return_value={"score": 92, "title_alignment": 96, "opening_line_alignment": 88},
            ),
        ):
            result = services.key_image_candidate_score(1, Path("opening.png"), "首镜提示词", 1)

        self.assertEqual(result["dimensions"]["opening_contract"], 92)
        self.assertEqual(result["dimensions"]["title_alignment"], 96)
        self.assertIn("title-opening-first-frame-contract", result["judge"])

    def test_automatic_review_can_keep_current_opening_option(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            official = root / "scenes" / "s_01.png"
            candidate = root / "scenes" / "candidates" / "s_01_b.png"
            candidate.parent.mkdir(parents=True)
            official.write_bytes(b"A" * 5000)
            candidate.write_bytes(b"B" * 5000)
            report = {
                "competitions": [
                    {
                        "scene_index": 1,
                        "target": "s_01.png",
                        "role": "opening_hook_competition",
                        "selected_score": 93,
                        "ai_recommended_variant": "CURRENT",
                        "selection_mode": "ai_recommended_pending_human",
                        "candidates": [{"variant": "B", "score": 88}],
                    }
                ]
            }
            saved_reports = []
            with (
                patch.object(services.storage, "project_file", side_effect=lambda _project_id, relative: root / relative),
                patch.object(services.storage, "get_report", return_value=report),
                patch.object(services.storage, "save_report", side_effect=lambda *args: saved_reports.append(args[2])),
            ):
                result = services.resolve_scene_candidates_automatically(1)

            self.assertEqual(result["resolved_count"], 1)
            self.assertEqual(result["resolved"][0]["variant"], "CURRENT")
            self.assertEqual(official.read_bytes(), b"A" * 5000)
            self.assertFalse(candidate.exists())
            self.assertEqual(saved_reports[-1]["competitions"], [])
            self.assertEqual(saved_reports[-1]["selection_history"][-1]["selection_mode"], "ai_auto_current")

    def test_cover_candidate_b_can_be_promoted_and_cleaned(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            official = root / "covers" / "cover_landscape.png"
            candidate = root / "covers" / "candidates" / "cover_landscape_b.png"
            candidate.parent.mkdir(parents=True)
            official.write_bytes(b"A" * 5000)
            candidate.write_bytes(b"B" * 5000)
            candidate.with_suffix(".md").write_text("封面候选 B", encoding="utf-8")
            report = {
                "competition": {"target": "cover_landscape.png", "ai_recommended_variant": "B"}
            }
            saved_reports = []
            with (
                patch.object(services.storage, "project_file", side_effect=lambda _project_id, relative: root / relative),
                patch.object(services.storage, "get_report", return_value=report),
                patch.object(services.storage, "save_report", side_effect=lambda *args: saved_reports.append(args[2])),
                patch.object(services, "mark_image_review_dirty", return_value={"required": True}),
            ):
                result = services.select_cover_candidate(1, "B")

            self.assertEqual(result["variant"], "B")
            self.assertEqual(official.read_bytes(), b"B" * 5000)
            self.assertFalse(candidate.exists())
            self.assertEqual(saved_reports[-1]["competition"], {})
            self.assertEqual(saved_reports[-1]["selection_history"][-1]["selection_mode"], "manual")

    def test_keep_current_scene_clears_candidates_and_accepts_old_prompt_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scene_dir = root / "scenes"
            candidate_dir = scene_dir / "candidates"
            candidate_dir.mkdir(parents=True)
            official = scene_dir / "s_02.png"
            official.write_bytes(b"OLD" * 2000)
            official.with_suffix(".md").write_text("旧图提示词", encoding="utf-8")
            official.with_suffix(".audit.json").write_text(
                json.dumps({"ok": True, "severity": "ok", "prompt_policy_version": "old"}),
                encoding="utf-8",
            )
            for variant in ("a", "b"):
                (candidate_dir / f"s_02_{variant}.png").write_bytes(variant.encode("ascii") * 5000)
            (scene_dir / "scene_prompts.json").write_text(
                json.dumps([{"filename": "s_02.png", "prompt_policy_version": services.IMAGE_PROMPT_POLICY_VERSION}]),
                encoding="utf-8",
            )
            report = {
                "competitions": [
                    {
                        "scene_index": 2,
                        "target": "s_02.png",
                        "ai_recommended_variant": "A",
                        "selection_mode": "ai_recommended_pending_human",
                        "candidates": [{"variant": "A", "score": 90}, {"variant": "B", "score": 85}],
                    }
                ]
            }
            saved_reports = []
            with (
                patch.object(services.storage, "project_file", side_effect=lambda _project_id, relative: root / relative),
                patch.object(services.storage, "get_report", return_value=report),
                patch.object(services.storage, "save_report", side_effect=lambda *args: saved_reports.append(args[2])),
                patch.object(services.storage, "scene_status", return_value={"candidate_count": 0}),
                patch.object(services, "project_image_context_hashes", return_value={}),
                patch.object(services, "mark_image_review_dirty", return_value={"required": True, "confirmed": False}),
                patch.object(services, "record_production_step", return_value={}),
            ):
                result = services.keep_current_scene_image(1, 2)

            self.assertEqual(result["variant"], "CURRENT")
            self.assertEqual(official.read_bytes(), b"OLD" * 2000)
            self.assertFalse((candidate_dir / "s_02_a.png").exists())
            self.assertFalse((candidate_dir / "s_02_b.png").exists())
            records = json.loads((scene_dir / "scene_prompts.json").read_text(encoding="utf-8"))
            self.assertTrue(records[0]["manual_image_accepted"])
            self.assertEqual(saved_reports[-1]["competitions"], [])
            self.assertEqual(saved_reports[-1]["selection_history"][-1]["selection_mode"], "keep_current")

    def test_interrupted_candidate_download_is_recovered_for_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            candidate_dir = root / "scenes" / "candidates"
            candidate_dir.mkdir(parents=True)
            temp_image = candidate_dir / ".s_03_a.gen-123456.png"
            temp_image.write_bytes(b"A" * 5000)
            temp_image.with_suffix(".md").write_text("候选提示词", encoding="utf-8")
            with (
                patch.object(services.storage, "project_file", side_effect=lambda _project_id, relative: root / relative),
                patch.object(services, "Image", None),
            ):
                recovered = services.recover_orphaned_scene_candidates(1, minimum_age_seconds=0)

            final_image = candidate_dir / "s_03_a.png"
            self.assertTrue(final_image.exists())
            self.assertFalse(temp_image.exists())
            self.assertEqual(recovered[0]["filename"], "s_03_a.png")
            audit = json.loads(final_image.with_suffix(".audit.json").read_text(encoding="utf-8"))
            self.assertEqual(audit["severity"], "pending")

    def test_interrupted_official_download_becomes_one_visible_repair_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scene_dir = root / "scenes"
            scene_dir.mkdir(parents=True)
            temp_image = scene_dir / ".s_06.gen-123456.png"
            temp_image.write_bytes(b"R" * 5000)
            temp_image.with_suffix(".md").write_text("中断前已完成的提示词", encoding="utf-8")
            saved_reports = []
            with (
                patch.object(services.storage, "project_file", side_effect=lambda _project_id, relative: root / relative),
                patch.object(services.storage, "get_report", return_value={}),
                patch.object(services.storage, "save_report", side_effect=lambda *args: saved_reports.append(args[2])),
                patch.object(services, "mark_image_review_dirty", return_value={}),
                patch.object(services, "Image", None),
            ):
                recovered = services.recover_orphaned_scene_candidates(1, minimum_age_seconds=0)

            candidate = scene_dir / "candidates" / "s_06_r.png"
            self.assertTrue(candidate.exists())
            self.assertFalse(temp_image.exists())
            self.assertEqual(recovered[0]["filename"], "s_06_r.png")
            competition = saved_reports[-1]["competitions"][0]
            self.assertEqual(competition["candidate_limit"], 1)
            self.assertEqual(competition["selection_mode"], "recovered_pending_human")

    def test_recovery_skips_image_that_is_still_being_generated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scene_dir = root / "scenes"
            scene_dir.mkdir(parents=True)
            temp_image = scene_dir / ".s_05.gen-123456.png"
            temp_image.write_bytes(b"G" * 5000)
            with (
                patch.object(services.storage, "project_file", side_effect=lambda _project_id, relative: root / relative),
                services._track_active_generated_tmp(temp_image),
            ):
                recovered = services.recover_orphaned_scene_candidates(1, minimum_age_seconds=0)

            self.assertEqual(recovered, [])
            self.assertTrue(temp_image.exists())

    def test_safe_generation_accepts_output_already_promoted_by_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "s_05.png"

            def generate(_prompt, temp_path, *_args, **_kwargs):
                temp_path.write_bytes(b"P" * 5000)
                services._replace_generated_image(temp_path, output_path)
                return temp_path

            with (
                patch.object(
                    services,
                    "resolve_image_provider_queue",
                    return_value=[{"key": "chatgpt_web_auto", "label": "ChatGPT", "model": ""}],
                ),
                patch.object(services, "generate_configured_image", side_effect=generate),
            ):
                result = services.generate_configured_image_safely(
                    "主题与当前口播",
                    output_path,
                    "2560x1440",
                    "scene",
                    {},
                    None,
                )

            self.assertEqual(result, output_path)
            self.assertEqual(output_path.read_bytes(), b"P" * 5000)

    def test_chatgpt_navigation_retries_transient_connection_close(self) -> None:
        class FakePage:
            def __init__(self) -> None:
                self.attempts = 0
                self.context = self

            def is_closed(self) -> bool:
                return False

            def new_page(self):
                return self

            def goto(self, url, **_kwargs):
                if url == "about:blank":
                    return None
                self.attempts += 1
                if self.attempts < 3:
                    raise RuntimeError("Page.goto: net::ERR_CONNECTION_CLOSED")
                return None

        page = FakePage()
        logs = []
        with patch.object(services.time, "sleep"):
            result = services._goto_chatgpt_with_retry(page, "https://chatgpt.com/", log=logs.append, attempts=3)

        self.assertIs(result, page)
        self.assertEqual(page.attempts, 3)
        self.assertEqual(len(logs), 2)
        self.assertTrue(all("自动重连" in line for line in logs))

    def test_chatgpt_hard_audit_does_not_trigger_duplicate_browser_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "cover_story.png"
            calls = []

            def generate(_prompt, path, *_args, **_kwargs):
                calls.append(path)
                if len(calls) == 1:
                    path.write_bytes(b"first-image")
                    return path
                raise RuntimeError(
                    "所有 ChatGPT 生图账号均不可用，本张图片未生成。"
                    "详情：ChatGPT 账号 1：浏览器窗口已关闭或启动后意外退出。"
                )

            with (
                patch.object(
                    services,
                    "resolve_image_provider_queue",
                    return_value=[{"key": "chatgpt_web_auto", "label": "ChatGPT 网页自动化", "model": ""}],
                ),
                patch.object(services, "image_prompt_has_topic_anchor", return_value=True),
                patch.object(services, "sanitize_prompt_for_image_model", side_effect=lambda prompt, _purpose: prompt),
                patch.object(services, "prompt_visual_score", return_value={"score": 90, "length": 20}),
                patch.object(services, "generate_chatgpt_web_auto_image", side_effect=generate),
                patch.object(services, "normalize_generated_image_size"),
                patch.object(
                    services,
                    "audit_generated_image",
                    return_value={
                        "ok": False,
                        "severity": "hard",
                        "reasons": ["ocr_semantic_mismatch"],
                        "warnings": [],
                    },
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "ocr_semantic_mismatch"):
                    services.generate_configured_image(
                    "主题：高血压药。封面标题：不要突然停药。",
                    output_path,
                    "2304x1728",
                    "cover",
                    {},
                )

            self.assertEqual(output_path.read_bytes(), b"first-image")
            audit = json.loads(output_path.with_suffix(".audit.json").read_text(encoding="utf-8"))
            self.assertEqual(audit["severity"], "hard")
            self.assertEqual(len(calls), 1)

    def test_safe_incremental_generation_does_not_mask_failed_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "s_05.png"
            output_path.write_bytes(b"existing-image" * 400)

            with (
                patch.object(
                    services,
                    "resolve_image_provider_queue",
                    return_value=[{"key": "chatgpt_web_auto", "label": "ChatGPT 网页自动化", "model": ""}],
                ),
                patch.object(
                    services,
                    "generate_configured_image",
                    side_effect=RuntimeError("ChatGPT 尚未返回图片，页面已静止超时。"),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "尚未返回图片"):
                    services.generate_configured_image_safely(
                        "本期主题：测试。当前完整口播：测试口播。",
                        output_path,
                        "2560x1440",
                        "scene",
                        {},
                        None,
                    )

            self.assertTrue(output_path.exists())
            self.assertFalse(output_path.with_suffix(".audit.json").exists())

    def test_scene_task_quote_survives_prompt_compaction_without_palette_numbers(self) -> None:
        prompt = (
            "本镜信息任务：以「准备上市的机器人公司要证明收入、亏损变化或技术」为主信息，"
            "把对象、动作和证据组织成画面。频道视觉合同：暖白 #F4E9D4、炭黑 #24211D。"
            "本期核心对象必须是：交易日。"
        )

        balanced = services.balanced_scene_generation_brief(prompt)
        outbound = services.lightweight_scene_model_prompt(balanced, 680)

        self.assertIn("准备上市的机器人公司", outbound)
        self.assertNotIn("24211", outbound)
        self.assertNotIn("F4E9", outbound)

    def test_local_fact_change_maps_to_exact_scene(self) -> None:
        before = """# 广告真相

## Meta
- 核心观点: 广告画像来自多类行为信号。

## 口播脚本
【主播】火锅还没入口，广告已经弹到脸上。
【主播】搜索记录会形成一类兴趣标签。
【主播】定位记录会补充你常去的区域。
【主播】你被哪种广告追过？评论区只写一个经历。
"""
        after = before.replace("定位记录会补充你常去的区域。", "定位记录会补充你常去的商圈和通勤区域。")
        scene_plan = {
            "scenes": [
                {"index": 1, "speech_text": "火锅还没入口，广告已经弹到脸上。"},
                {"index": 2, "speech_text": "搜索记录会形成一类兴趣标签。"},
                {"index": 3, "speech_text": "定位记录会补充你常去的区域。", "audio_anchor": "定位记录"},
                {"index": 4, "speech_text": "评论区只写一个经历。"},
            ]
        }
        with (
            patch.object(services.storage, "get_project", return_value={"id": 54, "template": "tech", "template_mode": "video", "topic_name": "广告真相"}),
            patch.object(services.storage, "get_template", return_value={"key": "tech", "mode": "video"}),
            patch.object(services.storage, "read_json", return_value=scene_plan),
            patch.object(services.storage, "get_summary", return_value={"scene_count": 4}),
        ):
            impact = services.content_change_impact(54, before, after)

        self.assertEqual(impact["scope"], "scene_local")
        self.assertEqual(impact["invalidate"]["scene_images"], ["s_03.png"])
        self.assertFalse(impact["invalidate"]["covers"])
        self.assertFalse(impact["invalidate"]["bgm"])

    def test_script_standardizer_removes_duplicate_lines_and_empty_bridges(self) -> None:
        lines = [
            "【主播】先别急，真正关键的点还在后面。",
            "【主播】等等，更狠的还在后面。",
            "【主播】搜索记录会形成兴趣标签。",
            "【主播】搜索记录会形成兴趣标签。",
        ]

        output, metrics = services.dedupe_script_semantic_lines(lines)

        self.assertEqual(output, ["【主播】搜索记录会形成兴趣标签。"])
        self.assertEqual(metrics["transition_count"], 2)
        self.assertEqual(metrics["duplicate_count"], 1)

    def test_numeric_consistency_requires_source_for_exact_claims(self) -> None:
        content = """# 测试

## 口播脚本
【主播】这次测试只用了30秒。
【主播】全球92%的网站都会这样做。
【主播】你遇到过吗？评论区只写一个经历。
"""
        with (
            patch.object(services.storage, "get_project", return_value={"id": 7, "template_mode": "video"}),
            patch.object(services.storage, "get_brief", return_value="实测耗时30秒。"),
            patch.object(services.storage, "get_references", return_value=[]),
        ):
            report = services.numeric_source_consistency_report(7, content)

        self.assertFalse(report["passed"])
        self.assertEqual([item["fact"] for item in report["unsupported_facts"]], ["92%"])

    def test_numeric_consistency_checks_meta_and_highlights_but_ignores_planned_duration(self) -> None:
        content = """# 停药提醒

## Meta
- 时长: 3-4分钟
- 钩子: 停药三天后住院。
- 核心观点: 2024年指南提醒不要自行停药。

## 原始材料简述
- 2024年指南提醒不要自行停药。

## 口播脚本
【主播】血压稳定也不要自行停药。

## 重点字幕
1. 停药24小时，血压冲180+
"""
        with (
            patch.object(services.storage, "get_project", return_value={"id": 7, "template_mode": "video"}),
            patch.object(services.storage, "get_brief", return_value=""),
            patch.object(services.storage, "get_references", return_value=[]),
        ):
            report = services.numeric_source_consistency_report(7, content)

        facts = [item["fact"] for item in report["unsupported_facts"]]
        self.assertEqual(facts, ["3天", "2024年", "24小时", "血压180"])
        self.assertNotIn("3分钟", facts)
        self.assertNotIn("4分钟", facts)
        self.assertEqual(
            {item["section"] for item in report["unsupported_facts"]},
            {"Meta", "重点字幕"},
        )

    def test_fact_registry_records_sources_and_cross_section_usages(self) -> None:
        content = """# 测试

## Meta
- 钩子: 实测只用了30秒。

## 口播脚本
【主播】这次测试只用了30秒。
【主播】全球92%的网站都会这样做。
"""
        with (
            patch.object(services.storage, "get_project", return_value={"id": 7, "template_mode": "video"}),
            patch.object(services.storage, "get_brief", return_value="实测耗时30秒。"),
            patch.object(services.storage, "get_references", return_value=[]),
        ):
            registry = services.build_episode_fact_registry(7, content)

        facts = {item["fact"]: item for item in registry["facts"]}
        self.assertEqual(facts["30秒"]["status"], "verified")
        self.assertEqual(
            {item["section"] for item in facts["30秒"]["usages"]},
            {"Meta", "口播脚本"},
        )
        self.assertEqual(facts["92%"]["status"], "unsupported")
        self.assertEqual(registry["counts"]["verified"], 1)
        self.assertEqual(registry["counts"]["unsupported"], 1)

    def test_fact_registry_verifies_technical_parameters_from_episode_sources(self) -> None:
        content = """# 充电宝20000mAh

## 口播脚本
【主播】电芯容量是20000mAh，工作电压是3.7V。
"""
        with (
            patch.object(services.storage, "get_project", return_value={"id": 7, "template_mode": "video"}),
            patch.object(services.storage, "get_brief", return_value="标称容量20000mAh，电芯电压3.7V。"),
            patch.object(services.storage, "get_references", return_value=[]),
        ):
            registry = services.build_episode_fact_registry(7, content)

        self.assertEqual(set(registry["verified_facts"]), {"20000mAh", "3.7V"})
        self.assertEqual(registry["unsupported_facts"], [])

    def test_historical_draft_numbers_cannot_verify_current_episode_facts(self) -> None:
        content = """# 当前健康主题

## 口播脚本
【主播】设备显示98%。
"""
        historical = [
            {
                "title": "上一期智能手表稿",
                "snippet": "指夹设备显示98%。",
                "source": "历史稿",
                "url": "C:/studio/data/projects/50/content.md",
            }
        ]
        with (
            patch.object(services.storage, "get_project", return_value={"id": 7, "template_mode": "video"}),
            patch.object(services.storage, "get_brief", return_value=""),
            patch.object(services.storage, "get_references", return_value=historical),
        ):
            report = services.numeric_source_consistency_report(7, content)

        self.assertFalse(report["passed"])
        self.assertEqual([item["fact"] for item in report["unsupported_facts"]], ["98%"])

    def test_canonicalizer_reports_unsupported_facts_without_damaging_copy(self) -> None:
        content = """# 停药提醒

## Meta
- 时长: 3-4分钟
- 钩子: 停药三天后住院。

## 口播脚本
【主播】血压稳定也不要自行停药。

## 重点字幕
1. 停药24小时，血压冲180+
"""
        with (
            patch.object(services.storage, "get_project", return_value={"id": 7, "template": "health", "template_mode": "video", "topic_name": "停药提醒"}),
            patch.object(services.storage, "get_template", return_value={"mode": "video"}),
            patch.object(services.storage, "get_brief", return_value=""),
            patch.object(services.storage, "get_references", return_value=[]),
            patch.object(services, "repair_channel_opening_repetition", side_effect=lambda _project_id, value: {"changed": False, "content": value, "replacement": ""}),
            patch.object(services, "opening_novelty_report", return_value={"score": 100, "repetitive": False}),
        ):
            canonical = services.canonicalize_project_content(7, content)

        repaired = canonical["content"]
        self.assertIn("Meta时长同步实际口播", canonical["actions"])
        self.assertIn("停药三天", repaired)
        self.assertIn("24小时", repaired)
        self.assertIn("180+", repaired)
        self.assertFalse(canonical["numeric_consistency"]["passed"])
        self.assertGreater(canonical["fact_registry"]["counts"]["source_only"], -1)

    def test_fact_registry_limits_image_numbers_even_when_speech_contains_more(self) -> None:
        context = {
            "speech": "手表显示93%，血氧仪显示98%。",
            "fact_registry_enforced": True,
            "allowed_numeric_facts": ["93%"],
        }

        foreign = services.foreign_scene_numeric_facts("画面同时出现93%和98%。", context)

        self.assertEqual(foreign, ["98%"])

    def test_save_content_bundle_passes_references_to_fact_registry(self) -> None:
        content = "# 测试\n\n## 口播脚本\n【主播】不要自行停药。\n"
        references = [{"title": "指南", "snippet": "不要自行停药", "source": "医院"}]
        canonical = {
            "content": content,
            "bad_phrase_repair": [],
            "opening_repair": {},
            "opening_novelty": {},
            "numeric_consistency": {"passed": True, "unsupported_facts": []},
            "fact_registry": {"version": services.FACT_REGISTRY_VERSION, "counts": {"verified": 0}},
        }
        artifacts = {
            "strategy": {"topic_score": {}},
            "audit": {"viral_doctor": {}, "title_cover_ab": {}},
        }
        with (
            patch.object(services.storage, "get_project", return_value={"id": 7, "template": "health", "template_mode": "video"}),
            patch.object(services.storage, "get_content", return_value=content),
            patch.object(services.storage, "get_template", return_value={"mode": "video"}),
            patch.object(services.storage, "get_brief", return_value="brief"),
            patch.object(services.storage, "get_references", return_value=references),
            patch.object(services.storage, "get_project_settings", return_value={"tavily_topic": "general"}),
            patch.object(services.storage, "save_content"),
            patch.object(services.storage, "save_summary"),
            patch.object(services.storage, "write_json"),
            patch.object(services.storage, "save_report"),
            patch.object(services.storage, "project_file", return_value=Path("project-file")),
            patch.object(services, "canonicalize_project_content", return_value=canonical) as canonicalize,
            patch.object(services, "content_change_impact", return_value={"scope": "none", "invalidate": {}}),
            patch.object(services, "save_episode_fact_registry", return_value=canonical["fact_registry"]) as save_registry,
            patch.object(services, "save_visual_prompt_manifest", return_value={"scene_count": 1}),
            patch.object(services, "visual_prompt_manifest_path", return_value=Path("visual_prompt_manifest.json")),
            patch.object(services, "summarize_content", return_value={"video_title": "测试"}),
            patch.object(services, "build_content_artifacts", return_value=artifacts),
            patch.object(services, "save_video_spec"),
        ):
            result = services.save_project_content_bundle(7, content, refresh_quality_report=False)

        self.assertEqual(canonicalize.call_args.kwargs["references"], references)
        self.assertEqual(save_registry.call_args.kwargs["references"], references)
        self.assertEqual(result["fact_registry"], canonical["fact_registry"])

    def test_numeric_consistency_ignores_approximate_ordinal_and_family_phrases(self) -> None:
        content = """# 测试

## 口播脚本
【主播】省下的只是几块钱，第二次提醒也别忽略。
【主播】你的身体是一家人的牵挂。
"""
        with (
            patch.object(services.storage, "get_project", return_value={"id": 7, "template_mode": "video"}),
            patch.object(services.storage, "get_brief", return_value=""),
            patch.object(services.storage, "get_references", return_value=[]),
        ):
            report = services.numeric_source_consistency_report(7, content)

        self.assertTrue(report["passed"])

    def test_unsupported_numeric_claims_are_softened_without_new_numbers(self) -> None:
        content = """# 测试

## 口播脚本
【主播】他偷偷停了两天降压药，最后进了医院。
【主播】你一停药，24小时内风险就可能上升。
【主播】十个人里至少五个中招。
【主播】身体已经扛了两年、三年的代价。
"""
        with (
            patch.object(services.storage, "get_project", return_value={"id": 7, "template_mode": "video"}),
            patch.object(services.storage, "get_brief", return_value=""),
            patch.object(services.storage, "get_references", return_value=[]),
        ):
            repaired, hits = services.soften_unsupported_numeric_facts_text(7, content)
            after = services.numeric_source_consistency_report(7, repaired)

        self.assertIn("擅自停用降压药后", repaired)
        self.assertIn("短时间内", repaired)
        self.assertIn("不少人都会中招", repaired)
        self.assertIn("很长一段时间", repaired)
        self.assertNotIn("两天", repaired)
        self.assertNotIn("24小时", repaired)
        self.assertTrue(hits)
        self.assertTrue(after["passed"])

    def test_fact_compliance_repair_does_not_mutate_numeric_prose(self) -> None:
        content = """# 测试

## 口播脚本
【主播】你每多等一次，厂商就多赚一笔。
【主播】设置只要三分钟，但不要自行停药。
"""
        with (
            patch.object(services.storage, "get_content", return_value=content),
            patch.object(services, "rewrite_fact_compliance_text", return_value=(content, [])),
            patch.object(services, "save_project_content_bundle") as save_bundle,
        ):
            result = services.repair_project_fact_compliance(7)

        self.assertFalse(result["changed"])
        self.assertEqual(result["content"], content)
        save_bundle.assert_not_called()

    def test_unsupported_blood_pressure_values_are_checked_and_softened(self) -> None:
        content = """# 测试

## 口播脚本
【主播】医生一看，血压190，情况很危险。
【主播】擅自停药后，血压可能冲到180、200。
"""
        with (
            patch.object(services.storage, "get_project", return_value={"id": 7, "template_mode": "video"}),
            patch.object(services.storage, "get_brief", return_value="不要自行停药。"),
            patch.object(services.storage, "get_references", return_value=[]),
        ):
            before = services.numeric_source_consistency_report(7, content)
            repaired, _hits = services.soften_unsupported_numeric_facts_text(7, content)
            after = services.numeric_source_consistency_report(7, repaired)

        self.assertEqual(
            [item["fact"] for item in before["unsupported_facts"]],
            ["血压190", "血压180", "血压200"],
        )
        self.assertNotIn("190", repaired)
        self.assertNotIn("180", repaired)
        self.assertNotIn("200", repaired)
        self.assertIn("血压突然飙高", repaired)
        self.assertTrue(after["passed"])

    def test_unsupported_numeric_claims_are_rewritten_as_complete_natural_phrases(self) -> None:
        content = """# 无线充电

## Meta
- 钩子: 你一千块买的无线充，电池健康度只剩88%？真凶是38℃。

## 口播脚本
【主播】你一千块买的无线充，电池健康度只剩88%？真凶是38℃。
【主播】充了半小时，电量才涨了15%。
【主播】国外实测多衰减2%到3%。
【主播】我自己的电池健康度还剩92%。
"""
        brief = "可靠资料显示，持续达到38℃值得关注；实测差异约为2%到3%。"
        with (
            patch.object(services.storage, "get_project", return_value={"id": 7, "template_mode": "video"}),
            patch.object(services.storage, "get_brief", return_value=brief),
            patch.object(services.storage, "get_references", return_value=[]),
        ):
            before = services.numeric_source_consistency_report(7, content)
            repaired, hits = services.soften_unsupported_numeric_facts_text(7, content)
            after = services.numeric_source_consistency_report(7, repaired)

        self.assertIn("1000块", [item["fact"] for item in before["unsupported_facts"]])
        self.assertIn("花大价钱买的无线充", repaired)
        self.assertIn("电池健康度明显下降", repaired)
        self.assertIn("电量却只涨了一点", repaired)
        self.assertNotIn("一笔买的", repaired)
        self.assertNotIn("88%", repaired)
        self.assertNotIn("15%", repaired)
        self.assertNotIn("92%", repaired)
        self.assertIn("38℃", repaired)
        self.assertIn("2%到3%", repaired)
        self.assertTrue(hits)
        self.assertTrue(after["passed"])

    def test_evaluate_all_stage_gates_reuses_unchanged_fingerprints(self) -> None:
        cached = {"key": "content_gate", "passed": True, "status": "passed", "score": 90}
        with (
            patch.object(services, "cached_stage_gate_result", return_value=cached),
            patch.object(services, "evaluate_production_stage_gate", side_effect=AssertionError("unchanged gate should not rerun")),
            patch.object(services, "production_stage_gates_dashboard", return_value={"ordered_gates": []}),
        ):
            report = services.evaluate_all_production_stage_gates(7)

        self.assertEqual(report["cache"]["hit_count"], len(services.STAGE_GATE_DEFS))
        self.assertEqual(report["cache"]["miss_count"], 0)

    def test_stage_gate_rule_version_invalidates_cached_fingerprint(self) -> None:
        with (
            patch.object(services.storage, "get_content", return_value="# 测试"),
            patch.object(services.storage, "get_brief", return_value="brief"),
            patch.object(services.storage, "get_references", return_value=[]),
        ):
            before = services.stage_gate_source_fingerprint(7, "content_gate")
            with patch.dict(services.STAGE_GATE_RULE_VERSIONS, {"content_gate": "next-version"}):
                after = services.stage_gate_source_fingerprint(7, "content_gate")

        self.assertNotEqual(before, after)

    def test_fact_source_blocker_does_not_trigger_ai_rewrite(self) -> None:
        fact_only = {
            "issues": [
                {
                    "level": "risk",
                    "where": "数字事实依据",
                    "issue": "精确数字没有出现在 brief 或参考资料中。",
                }
            ]
        }
        rhythm = {
            "issues": [
                {
                    "level": "warn",
                    "where": "中段留存",
                    "issue": "中段推进偏平。",
                }
            ]
        }

        self.assertFalse(services.content_gate_has_rewriteable_issues(fact_only))
        self.assertTrue(services.content_gate_has_rewriteable_issues(rhythm))

    def test_pre_video_blockers_map_to_real_asset_repairs(self) -> None:
        result = {
            "issues": [
                {"where": "音频版本", "issue": "podcast.mp3 早于最新 content.md"},
                {"where": "字幕版本", "issue": "subtitles.srt 已过期"},
                {"where": "scenes/s_03.png", "issue": "旧提示词策略"},
                {"where": "scenes/s_04.png", "issue": "场景图缺失"},
                {"where": "BGM", "issue": "背景音乐需要重新匹配"},
            ]
        }

        steps = services.stage_gate_repair_steps("pre_video_gate", result)

        self.assertEqual(steps, ["audio", "subtitles", "images_missing", "bgm"])


    def test_zoompan_filter_uses_requested_motion_instead_of_static_zoom(self) -> None:
        push_filter = services.build_zoompan_filter(0, "gentle_push_in", 6.0)
        pan_filter = services.build_zoompan_filter(1, "slow_pan_left_to_right", 6.0)

        self.assertNotIn("zoompan=z='1':", push_filter)
        self.assertIn("1+0.12*", push_filter)
        self.assertIn("(iw-iw/zoom)*(on/", pan_filter)
        self.assertIn("d=180", pan_filter)
        focus_filter = services.build_zoompan_filter(2, "micro_focus_right", 6.0)
        self.assertIn("0.50+0.22", focus_filter)
        self.assertNotIn("1+0.18*", focus_filter)

    def test_pre_video_soft_image_issue_does_not_schedule_hidden_redraw(self) -> None:
        result = {
            "issues": [
                {"where": "scenes/s_01.png", "issue": "图片与主题/口播贴合偏弱：58 分。"},
                {"where": "scenes/s_02.png", "issue": "旧提示词策略"},
                {"where": "covers/cover_story.png", "issue": "封面吸引力不足"},
            ]
        }

        self.assertEqual(services.stage_gate_repair_steps("pre_video_gate", result), [])

    def test_implicit_pre_video_gate_is_check_only(self) -> None:
        self.assertFalse(services.production_stage_gate_auto_fix_mode("", "pre_video_gate"))
        self.assertFalse(services.production_stage_gate_auto_fix_mode("check", "pre_video_gate"))
        self.assertTrue(services.production_stage_gate_auto_fix_mode("fix", "pre_video_gate"))
        self.assertFalse(services.production_stage_gate_auto_fix_mode("", "content_gate"))
        self.assertFalse(services.production_stage_gate_auto_fix_mode("check", "content_gate"))

    def test_project_109_production_contract_is_active(self) -> None:
        self.assertEqual(services.PRODUCTION_LOGIC_VERSION, "project-109")
        self.assertEqual(
            services.IMAGE_PROMPT_POLICY_VERSION,
            "semantic-concepts-v24-grounded-resonance",
        )
        self.assertEqual(
            services.suggest_scene_count(270_500, 12),
            {"minimum": 7, "maximum": 10, "target": 10, "final": 10},
        )

    def test_content_review_runs_before_asset_production(self) -> None:
        self.assertEqual(services.production_stage_gate_keys_for_step("audio"), ["content_gate"])
        self.assertEqual(
            services.production_stage_gate_keys_for_step("images"),
            ["content_gate", "visual_prompt_gate"],
        )
        self.assertEqual(
            services.production_stage_gate_keys_for_step("video"),
            ["content_gate", "pre_video_gate"],
        )

    def test_doubao_voice_options_are_loaded_from_preview_manifest(self) -> None:
        options = storage.doubao_tts_voice_options()

        self.assertGreaterEqual(len(options), 30)
        self.assertIn("zh_female_cancan_uranus_bigtts", {item["value"] for item in options})

    def test_voice_settings_do_not_invalidate_existing_production_assets(self) -> None:
        snapshots = {
            "audio": {"hash": "audio-hash"},
            "subtitles": {"hash": "subtitles-hash"},
            "scene_plan": {"hash": "scene-plan-hash"},
            "visual_prompts": {"hash": "visual-prompts-hash"},
            "scene_images": {"hash": "scene-images-hash"},
            "covers": {"hash": "covers-hash"},
            "bgm": {"hash": "bgm-hash"},
            "video": {"hash": "video-hash"},
        }
        project = {"id": 81, "topic_name": "声音只影响下一次配音", "template": "voice-channel"}
        base_template = {"name": "voice-channel", "tts_speaker_1": "voice-a", "tts_speech_rate": 1.0}
        changed_voice_template = {**base_template, "tts_speaker_1": "voice-b", "tts_speech_rate": 1.2}
        semantics = {"speech_hash": "same-script", "bgm_semantic_hash": "same-bgm"}

        def source_hashes_for(template: dict[str, object]) -> dict[str, str]:
            with (
                patch.object(services.storage, "get_content", return_value="same spoken script"),
                patch.object(services.storage, "get_project", return_value=project),
                patch.object(services.storage, "get_template", return_value=template),
                patch.object(services.storage, "read_json", return_value={}),
                patch.object(services, "content_semantic_fingerprints", return_value=semantics),
                patch.object(services, "project_bgm_status", return_value={"volume": 0.18}),
            ):
                return services.production_source_hashes(81, snapshots)

        before = source_hashes_for(base_template)
        after = source_hashes_for(changed_voice_template)

        self.assertEqual(before, after)
        self.assertNotIn("voice_config_hash", before)

    def test_builtin_template_voice_settings_can_be_updated_without_unlocking_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            templates_root = Path(temp_dir) / "templates"
            template_root = templates_root / "story"
            template_root.mkdir(parents=True)
            storage.write_json(
                template_root / "manifest.json",
                {"name": "story", "builtin_locked": True, "voice_mode": "single"},
            )
            storage.write_text(template_root / "prompt.md", "locked prompt")
            with patch.object(storage, "TEMPLATES_ROOT", templates_root):
                result = storage.save_template_voice_settings(
                    "story",
                    {
                        "voice_mode": "dual",
                        "tts_speaker_1": "voice-a",
                        "tts_speaker_2": "voice-b",
                        "tts_random_order": False,
                        "tts_speech_rate": 1.1,
                    },
                )

            self.assertEqual(result["voice_mode"], "dual")
            self.assertEqual(result["tts_speaker_1"], "voice-a")
            self.assertEqual(result["tts_speaker_2"], "voice-b")
            self.assertFalse(result["tts_random_order"])
            self.assertEqual(result["tts_action"], 3)
            self.assertEqual(storage.read_text(template_root / "prompt.md"), "locked prompt")

    def test_auto_voice_mode_keeps_second_voice_available_without_forcing_dual(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            templates_root = Path(temp_dir) / "templates"
            template_root = templates_root / "news"
            template_root.mkdir(parents=True)
            storage.write_json(template_root / "manifest.json", {"name": "news"})
            storage.write_text(template_root / "prompt.md", "prompt")
            with patch.object(storage, "TEMPLATES_ROOT", templates_root):
                result = storage.save_template_voice_settings(
                    "news",
                    {
                        "voice_mode": "auto",
                        "tts_speaker_1": "voice-a",
                        "tts_speaker_2": "voice-b",
                        "tts_random_order": False,
                        "tts_speech_rate": 1.0,
                    },
                )

            self.assertEqual(result["voice_mode"], "")
            self.assertEqual(result["tts_speaker_1"], "voice-a")
            self.assertEqual(result["tts_speaker_2"], "voice-b")

    def test_release_metrics_normalize_retention_and_growth_fields(self) -> None:
        metrics = services.normalize_release_metrics(
            {
                "impressions": "30000",
                "views": "12000",
                "follows": "36",
                "two_second_retention_rate": 0.68,
                "five_second_retention_rate": 42.5,
                "average_watch_seconds": "18.4",
                "completion_rate": 0.31,
            }
        )

        self.assertEqual(metrics["views"], 12000)
        self.assertEqual(metrics["impressions"], 30000)
        self.assertEqual(metrics["click_through_rate"], 40.0)
        self.assertEqual(metrics["follows"], 36)
        self.assertEqual(metrics["two_second_retention_rate"], 68.0)
        self.assertEqual(metrics["five_second_retention_rate"], 42.5)
        self.assertEqual(metrics["average_watch_seconds"], 18.4)
        self.assertEqual(metrics["completion_rate"], 31.0)

    def test_release_performance_signal_finds_real_retention_bottleneck(self) -> None:
        signal = services.release_performance_signal(
            {
                "id": 9,
                "platform": "douyin",
                "metrics": {
                    "views": 10000,
                    "likes": 240,
                    "comments": 30,
                    "shares": 18,
                    "favorites": 40,
                    "follows": 12,
                    "two_second_retention_rate": 48,
                    "five_second_retention_rate": 31,
                    "completion_rate": 18,
                },
            }
        )

        self.assertTrue(signal["has_metrics"])
        self.assertEqual(signal["growth_stage"], "开场流失")
        self.assertGreater(signal["performance_score"], 0)
        self.assertLessEqual(signal["performance_score"], 100)
        self.assertGreater(signal["raw_performance_score"], 10000)
        self.assertEqual(
            set(signal["dimension_scores"]),
            {"play_potential", "completion_potential", "comment_potential"},
        )
        for key in ("play_potential_score", "completion_potential_score", "comment_potential_score"):
            self.assertGreaterEqual(signal[key], 0)
            self.assertLessEqual(signal[key], 100)

    def test_release_performance_dimensions_do_not_confuse_comments_with_retention(self) -> None:
        launch_event = services.release_performance_signal(
            {
                "metrics": {
                    "views": 33000,
                    "likes": 172,
                    "comments": 226,
                    "shares": 0,
                    "favorites": 0,
                    "completion_rate": 8.4,
                }
            }
        )
        cybercab = services.release_performance_signal(
            {
                "metrics": {
                    "views": 2508,
                    "likes": 12,
                    "comments": 90,
                    "shares": 0,
                    "favorites": 0,
                    "completion_rate": 2.5,
                }
            }
        )

        self.assertGreater(launch_event["play_potential_score"], cybercab["play_potential_score"])
        self.assertGreater(cybercab["comment_potential_score"], launch_event["comment_potential_score"])
        self.assertLess(launch_event["completion_potential_score"], 10)
        self.assertLess(cybercab["completion_potential_score"], 10)
        self.assertEqual(launch_event["diagnosis"], "选题有效，正文未兑现")
        self.assertEqual(cybercab["diagnosis"], "有争议，留存不足")

    def test_channel_growth_experiment_uses_long_low_completion_as_a_short_episode_trial(self) -> None:
        signals = [
            services.release_performance_signal(
                {
                    "metrics": {
                        "impressions": 375,
                        "views": 77,
                        "average_watch_seconds": 75,
                        "completion_rate": 18.8,
                    }
                }
            ),
            services.release_performance_signal(
                {
                    "metrics": {
                        "impressions": 98,
                        "views": 28,
                        "average_watch_seconds": 79,
                        "completion_rate": 10.3,
                    }
                }
            ),
        ]

        experiment = services.channel_growth_experiment(signals)

        self.assertEqual(experiment["kind"], "short_episode_recovery")
        self.assertEqual(experiment["duration_target"], "60-100 秒")
        self.assertGreater(experiment["average_click_through_rate"], 0)
        self.assertGreater(experiment["median_estimated_duration_seconds"], 180)

    def test_douyin_metric_sync_matches_release_by_work_id(self) -> None:
        links = [
            {
                "id": 5,
                "platform": "抖音",
                "url": "https://www.douyin.com/video/123456",
                "aweme_id": "123456",
                "account_name": "default",
                "metrics": {"completion_rate": 31},
            }
        ]
        work = {
            "item_id": "123456",
            "title": "智能门锁真安全吗",
            "play_count": 12000,
            "like_count": 520,
            "comment_count": 42,
            "share_count": 33,
            "collect_count": 88,
        }
        with (
            patch.object(release_automation.storage, "get_release_links", return_value=links),
            patch.object(release_automation.storage, "save_release_links") as save_links,
            patch.object(release_automation.storage, "save_report"),
            patch.object(release_automation, "detect_repo", return_value=(Path("C:/repo"), False)),
            patch.object(release_automation, "list_account_profiles", return_value=[]),
            patch.object(release_automation, "_load_platform_recent_stats", return_value=[work]),
        ):
            result = release_automation.sync_release_metrics(7)

        self.assertEqual(result["updated"], 1)
        self.assertEqual(links[0]["metrics"]["views"], 12000)
        self.assertEqual(links[0]["metrics"]["completion_rate"], 31)
        self.assertEqual(links[0]["metrics"]["source"], "omnipost_douyin_content_stats")
        self.assertTrue(save_links.called)

    def test_multi_platform_metric_sync_updates_kuaishou_xiaohongshu_and_bilibili(self) -> None:
        links = [
            {"id": 21, "platform": "快手", "item_id": "ks-1", "account_name": "a", "title": "快手作品"},
            {"id": 22, "platform": "小红书", "item_id": "xhs-1", "account_name": "b", "title": "小红书作品"},
            {"id": 23, "platform": "B站", "item_id": "BV1TEST", "account_name": "c", "title": "B站作品"},
        ]
        works = {
            "kuaishou": [{"item_id": "ks-1", "title": "快手作品", "play_count": 800, "like_count": 30}],
            "xiaohongshu": [{"item_id": "xhs-1", "title": "小红书作品", "play_count": 900, "like_count": 40}],
            "bilibili": [{"item_id": "BV1TEST", "title": "B站作品", "play_count": 1000, "like_count": 50}],
        }
        with (
            patch.object(release_automation.storage, "get_release_links", return_value=links),
            patch.object(release_automation.storage, "save_release_links"),
            patch.object(release_automation.storage, "save_report") as save_report,
            patch.object(release_automation, "detect_repo", return_value=(Path("C:/repo"), False)),
            patch.object(release_automation, "list_account_profiles", return_value=[]),
            patch.object(
                release_automation,
                "_load_platform_recent_stats",
                side_effect=lambda _repo, platform, _alias, limit=10: works[platform],
            ),
        ):
            result = release_automation.sync_release_metrics(7)

        self.assertEqual(result["updated"], 3)
        self.assertEqual([item["metrics"]["views"] for item in links], [800, 900, 1000])
        self.assertEqual(len(result["accounts"]), 3)
        self.assertTrue(save_report.called)

    def test_platform_stats_syncs_saved_accounts_without_project_release_links(self) -> None:
        work = {
            "item_id": "posted-1",
            "title": "账号最近作品",
            "play_count": 321,
            "like_count": 12,
            "raw_json": "x" * 20000,
        }
        profiles = {
            "douyin": [{"alias": "default", "display_name": "科技小地瓜", "cookie_exists": True}],
            "xiaohongshu": [{"alias": "default", "display_name": "小红书账号", "cookie_exists": True}],
        }
        calls = []
        with (
            patch.object(release_automation.storage, "get_release_links", return_value=[]),
            patch.object(release_automation.storage, "save_release_links"),
            patch.object(release_automation.storage, "save_report") as save_report,
            patch.object(release_automation, "detect_repo", return_value=(Path("C:/repo"), False)),
            patch.object(
                release_automation,
                "list_account_profiles",
                side_effect=lambda platform: profiles.get(platform, []),
            ),
            patch.object(
                release_automation,
                "_load_platform_recent_stats",
                side_effect=lambda _repo, platform, alias, limit=10: calls.append((platform, alias)) or [work],
            ),
        ):
            result = release_automation.sync_release_metrics(112)

        self.assertEqual(calls, [("douyin", "default"), ("xiaohongshu", "default")])
        self.assertEqual(len(result["accounts"]), 2)
        self.assertEqual(result["accounts"][0]["account_display_name"], "科技小地瓜")
        self.assertNotIn("raw_json", result["accounts"][0]["items"][0])
        performance = result["accounts"][0]["items"][0]["performance"]
        self.assertEqual(
            set(performance["dimension_scores"]),
            {"play_potential", "completion_potential", "comment_potential"},
        )
        self.assertTrue(performance["diagnosis"])
        self.assertTrue(save_report.called)

    def test_platform_csv_import_attributes_retention_to_existing_release(self) -> None:
        links = [
            {
                "id": 8,
                "platform": "抖音",
                "url": "https://www.douyin.com/video/778899",
                "aweme_id": "778899",
                "title": "智能门锁真安全吗",
            }
        ]
        csv_data = (
            "作品ID,作品标题,展现量,点击率,播放量,点赞量,2秒跳出率,5秒留存率,平均观看时长,完播率,新增关注\n"
            "778899,智能门锁真安全吗,80000,31.25%,25000,900,24%,58%,21.4,36%,75\n"
        ).encode("utf-8-sig")
        with (
            patch.object(release_automation.storage, "get_release_links", return_value=links),
            patch.object(release_automation.storage, "save_release_links") as save_links,
        ):
            result = release_automation.import_release_metrics_csv(7, csv_data, "douyin.csv")

        self.assertEqual(result["updated"], 1)
        self.assertEqual(links[0]["metrics"]["views"], 25000)
        self.assertEqual(links[0]["metrics"]["impressions"], 80000)
        self.assertEqual(links[0]["metrics"]["click_through_rate"], 31.25)
        self.assertEqual(links[0]["metrics"]["two_second_retention_rate"], 76)
        self.assertEqual(links[0]["metrics"]["five_second_retention_rate"], 58)
        self.assertEqual(links[0]["metrics"]["completion_rate"], 36)
        self.assertEqual(links[0]["metrics"]["follows"], 75)
        self.assertTrue(save_links.called)

    def test_key_visual_planner_builds_three_distinct_concepts_and_renders_top_two(self) -> None:
        saved = []
        contract = {
            "title": "手机 App 在偷听你聊天？",
            "cover_title": "手机在偷听？",
            "opening_line": "刚聊完火锅，广告就追过来了。",
            "first_scene_speech": "你刚说完想吃火锅，手机里立刻出现了同类广告。",
        }
        with (
            patch.object(services.storage, "get_project", return_value={"id": 1, "template": "tech", "topic_name": contract["title"]}),
            patch.object(services.storage, "get_template", return_value={"name": "科技情报站"}),
            patch.object(services.storage, "get_report", return_value={}),
            patch.object(services.storage, "save_report", side_effect=lambda *args: saved.append(args[2])),
            patch.object(services, "opening_visual_contract", return_value=contract),
            patch.object(services, "runtime_env", return_value={}),
        ):
            result = services.generate_key_visual_concepts(
                1,
                "opening",
                "真实家庭餐桌，手机刚出现火锅广告，当前口播必须与画面事实呼应。",
            )

        self.assertEqual(result["concept_count"], 3)
        self.assertEqual(result["render_count"], 2)
        self.assertEqual(len(result["selected_concepts"]), 2)
        bodies = [services._key_visual_concept_text(item) for item in result["concepts"]]
        self.assertTrue(all(bodies))
        self.assertEqual(len(set(item["name"] for item in result["concepts"])), 3)
        self.assertEqual(saved[-1]["plans"]["opening"]["selected_ids"], result["selected_ids"])

    def test_actual_image_judge_blends_vision_with_local_score(self) -> None:
        local = {"score": 70, "judge": "local", "dimensions": {"appeal": 70}}
        vision = {"available": True, "score": 90, "provider": "vision-test"}

        result = services.apply_actual_image_judge(local, vision)

        self.assertEqual(result["local_score"], 70)
        self.assertEqual(result["score"], 82)
        self.assertEqual(result["judge_mode"], "multimodal_actual_image_review")
        self.assertIn("actual-image", result["judge"])

    def test_opening_competition_keeps_concept_pool_and_actual_image_scores(self) -> None:
        plan = {
            "provider": "director-test",
            "concept_count": 3,
            "concepts": [{"id": "A", "name": "证据"}, {"id": "B", "name": "后果"}, {"id": "C", "name": "选择"}],
            "selected_concepts": [{"id": "A", "name": "证据"}, {"id": "B", "name": "后果"}],
        }
        saved = []
        score_side_effect = [
            {"score": 78, "judge": "local-a", "opening_contract": {}},
            {"score": 80, "judge": "local-b", "opening_contract": {}},
        ]
        vision_side_effect = [
            {"available": True, "score": 88},
            {"available": True, "score": 72},
        ]
        with (
            patch.object(services, "key_image_candidate_score", side_effect=score_side_effect),
            patch.object(services, "vision_key_image_judge", side_effect=vision_side_effect),
            patch.object(services.storage, "get_report", return_value={}),
            patch.object(services.storage, "save_report", side_effect=lambda *args: saved.append(args[2])),
            patch.object(services, "opening_visual_contract", return_value={}),
            patch.object(services, "image_review_status", return_value={"required": True}),
            patch.object(services, "mark_image_review_dirty", return_value={}),
        ):
            result = services.save_opening_scene_competition(
                1,
                Path("a.png"),
                Path("b.png"),
                "A prompt",
                "B prompt",
                plan,
            )

        self.assertEqual(result["concept_count"], 3)
        self.assertEqual(result["generated_count"], 2)
        self.assertEqual(result["current"]["concept"]["name"], "证据")
        self.assertEqual(result["candidates"][0]["concept"]["name"], "后果")
        self.assertEqual(result["current"]["judge_mode"], "multimodal_actual_image_review")
        self.assertEqual(saved[-1]["policy"], "three text concepts, render top two for opening hook, keep one; every other scene stays single-output")


class ReferenceResearchRegressionTests(unittest.TestCase):
    def test_opening_stake_recognizes_viewer_money_and_paid_product_cost(self) -> None:
        signals = services.opening_semantic_stake_signals(
            "你花钱买回来的那台电视，开机第一件事是放广告。"
        )
        self.assertTrue(signals["audience_linked"])
        self.assertTrue(signals["financial_cost"])
        self.assertTrue(signals["has_stake"])

    def test_opening_stake_recognizes_purchase_decision_for_family(self) -> None:
        opening = "给爸妈挑电视，你比的是尺寸和价格，厂商算的是另一笔账。"
        signals = services.opening_semantic_stake_signals(opening)
        hooks = services.opening_semantic_hook_signals(opening)
        self.assertTrue(signals["audience_linked"])
        self.assertTrue(signals["purchase_decision"])
        self.assertTrue(signals["has_stake"])
        self.assertTrue(hooks["perspective_contrast"])

    def test_purchase_decision_contrast_passes_opening_gate(self) -> None:
        content = """# 测试

## 口播脚本

【主播】给爸妈挑电视，你比的是尺寸和价格，厂商算的是另一笔账。
【主播】今年上半年，中国电视出货量同比下滑10.1%。
【主播】机构预计全年会创下17年来的新低。
【主播】但同期电视平均尺寸已经突破65英寸。
【主播】台数在跌，英寸在涨。
【主播】硬件利润越来越薄，厂商只能把剩下的需求推向大屏。
【主播】买之前先问开机有没有广告，再让销售当场演示怎么关。
【主播】老人能不能自己打开，比参数表更能说明它好不好用。
"""
        report = services.content_engagement_report(content, "video")
        self.assertTrue(report["opening_has_stake"])
        self.assertGreaterEqual(report["opening_score"], services.CONTENT_OPENING_MIN_SCORE)
        self.assertNotIn("开头利害关系", {item["where"] for item in report["issues"]})
        self.assertNotIn("开头钩子", {item["where"] for item in report["issues"]})

    def test_topic_entity_profile_uses_explicit_brief_when_title_is_elliptical(self) -> None:
        profile = services.topic_entity_profile(
            "越卖不动，越大",
            "今年上半年，中国电视销量在跌，但电视平均尺寸突破65英寸。面板和MiniLED继续增长。",
        )
        self.assertEqual(profile["primary_entity"], "电视")
        query, _ = services.topic_research_query("越卖不动，越大", "中国电视销量下降，平均尺寸突破65英寸。")
        self.assertIn("电视", query)

    def test_tv_topic_rejects_phone_market_source(self) -> None:
        profile = services.topic_entity_profile(
            "越卖不动，越大",
            "中国电视销量下降，电视平均尺寸突破65英寸。",
        )
        phone_source = {
            "title": "AI越火，廉价手机越卖不动",
            "snippet": "智能手机BOM中存储成本占比上升",
        }
        self.assertFalse(services.reference_matches_primary_entity(phone_source, profile))

    def test_tv_topic_accepts_tv_market_source(self) -> None:
        profile = services.topic_entity_profile(
            "越卖不动，越大",
            "中国电视销量下降，电视平均尺寸突破65英寸。",
        )
        tv_source = {
            "title": "中国电视销量下滑，大屏化继续",
            "snippet": "电视平均尺寸突破65英寸，MiniLED增长",
        }
        self.assertTrue(services.reference_matches_primary_entity(tv_source, profile))

    def test_concrete_product_rejects_unrelated_parent_brand_source(self) -> None:
        topic = "你买的是问界，还是那扇门上的两个字"
        brief = "一条撤店传闻和一句系误读的否认同时出现。"
        profile = services.topic_entity_profile(topic, brief)
        source = {
            "title": "Huawei showcases AI smartphone-driven car at MWC",
            "snippet": "Huawei uses a smartphone to drive a vehicle.",
        }
        self.assertEqual(profile["primary_entity"], "问界")
        self.assertFalse(services.reference_matches_primary_entity(source, profile))

    def test_evidence_contract_blocks_same_brand_unrelated_research(self) -> None:
        topic = "你买的是问界，还是那扇门上的两个字"
        brief = "一条撤店传闻和一句系误读的否认在 24 小时内同时出现。"
        profile = services.topic_entity_profile(topic, brief)
        contract = services.evidence_contract(topic, brief, profile)
        unrelated = [{
            "title": "华为在世界移动通信大会展示智能汽车",
            "snippet": "手机驱动车辆完成演示",
            "url": "https://example.com/mwc",
        }]
        blocked = services.evaluate_evidence_contract(contract, unrelated)
        self.assertFalse(blocked["can_draft"])

        relevant = [{
            "title": "传问界撤出华为专卖店，相关方回应系误读",
            "snippet": "问界门店渠道归属变化引发讨论",
            "url": "https://example.com/wenjie",
        }]
        covered = services.evaluate_evidence_contract(contract, relevant)
        self.assertTrue(covered["can_draft"])
        self.assertGreater(covered["coverage_score"], 0)

    def test_content_gate_rejects_cross_category_script(self) -> None:
        report = services.topic_entity_alignment_report(
            "越卖不动，越大",
            "中国电视销量下降，平均尺寸突破65英寸。",
            "# 越卖不动，越大\n\n## 口播脚本\n\n【主播】AI越火，最便宜的手机越没人买。",
        )
        self.assertTrue(report["mismatch"])
        self.assertEqual(report["primary_entity"], "电视")

    def test_reference_context_queries_brief_entity_and_filters_phone_results(self) -> None:
        project = {"id": 122, "topic_name": "越卖不动，越大"}
        found = [
            {
                "title": "AI越火，廉价手机越卖不动",
                "url": "https://example.com/phone",
                "source": "News",
                "snippet": "智能手机BOM中存储成本占比上升",
                "score": 0.9,
            },
            {
                "title": "中国电视销量下降，大屏化趋势延续",
                "url": "https://example.com/tv",
                "source": "News",
                "snippet": "电视平均尺寸突破65英寸",
                "score": 0.8,
            },
        ]
        brief = "中国电视销量下降，但电视平均尺寸突破65英寸。"
        with (
            patch.object(services, "runtime_env", return_value={"TAVILY_MAX_REFERENCES": "8"}),
            patch.object(services, "local_article_references", return_value=[]),
            patch.object(services, "project_source_references", return_value=[]),
            patch.object(services, "brief_reference_candidates", return_value=[]),
            patch.object(services.storage, "get_project_settings", return_value={"current_news_mode": True}),
            patch.object(services, "search_current_news", return_value=found) as search,
        ):
            context = services.build_reference_context(project, {}, brief, "general")
        query = search.call_args.args[0]
        self.assertIn("电视", query)
        self.assertEqual([item["url"] for item in context["web_refs"]], ["https://example.com/tv"])
        self.assertEqual(context["research_diagnostics"]["primary_entity"], "电视")

    def test_locked_topic_terms_split_chinese_brands_and_bridge_english_titles(self) -> None:
        topic = "华为小米同一天开发布会，把炮口对准了下周的苹果"
        terms = services.locked_topic_terms(topic)
        self.assertIn("华为", terms)
        self.assertIn("小米", terms)
        self.assertIn("苹果", terms)
        self.assertIn("huawei", terms)
        self.assertIn("xiaomi", terms)
        self.assertIn("apple", terms)
        reference = {
            "title": "Huawei launches foldable smartphone as competition with Xiaomi and Apple heats up",
            "snippet": "",
        }
        self.assertGreaterEqual(services.reference_topic_score(reference, topic), 4)

    def test_reference_context_searches_locked_topic_without_speculative_brief(self) -> None:
        project = {"id": 112, "topic_name": "华为小米同日发布新品"}
        found = [{
            "title": "华为小米同日发布新品",
            "url": "https://example.com/news",
            "source": "News",
            "provider": "tavily",
            "snippet": "发布会信息",
            "score": 0.9,
        }]
        with (
            patch.object(services, "runtime_env", return_value={"TAVILY_MAX_REFERENCES": "8"}),
            patch.object(services, "local_article_references", return_value=[]),
            patch.object(services, "project_source_references", return_value=[]),
            patch.object(services, "brief_reference_candidates", return_value=[]),
            patch.object(services.storage, "get_project_settings", return_value={"current_news_mode": True}),
            patch.object(services, "search_current_news", return_value=found) as search,
        ):
            context = services.build_reference_context(project, {}, "虚构型号 99999 元，性能提升 88%", "general")
        search.assert_any_call("华为小米同日发布新品", 8)
        self.assertEqual(context["query"], "华为小米同日发布新品")
        self.assertEqual(context["research_diagnostics"]["effective_count"], 1)

    def test_content_gate_reference_refresh_persists_sources_and_rebuilds_evidence(self) -> None:
        references = [{
            "title": "华为小米发布会信息",
            "url": "https://example.com/source",
            "source": "News",
            "snippet": "同日发布",
        }]
        context = {
            "references": references,
            "research_diagnostics": {"raw_web_count": 3, "filtered_web_count": 1},
        }
        with (
            patch.object(services, "effective_project_references", return_value=[]),
            patch.object(services.storage, "get_project", return_value={"id": 112, "template": "tech", "tavily_topic": "news"}),
            patch.object(services.storage, "get_template", return_value={"key": "tech"}),
            patch.object(services.storage, "get_brief", return_value="brief"),
            patch.object(services.storage, "get_content", return_value="# 文案"),
            patch.object(services.storage, "project_file", return_value=Path("reference_research.json")),
            patch.object(services.storage, "write_json") as write_json,
            patch.object(services.storage, "save_references") as save_references,
            patch.object(services, "build_reference_context", return_value=context),
            patch.object(services, "save_episode_fact_registry") as save_registry,
            patch.object(services, "sync_production_intelligence") as sync_intelligence,
        ):
            result = services.refresh_content_gate_references(112)
        save_references.assert_called_once_with(112, references)
        save_registry.assert_called_once()
        sync_intelligence.assert_called_once_with(112, "content_gate_source_refresh")
        self.assertEqual(result["effective_count"], 1)
        self.assertIn("重新检索得到 3 条结果", result["message"])
        self.assertTrue(write_json.called)

    def test_plain_aspect_ratios_are_not_prompt_metadata_pollution(self) -> None:
        self.assertNotIn("16:9", services.IMAGE_PROMPT_META_POLLUTION_TERMS)
        self.assertNotIn("4:3", services.IMAGE_PROMPT_META_POLLUTION_TERMS)
        self.assertNotIn("3:4", services.IMAGE_PROMPT_META_POLLUTION_TERMS)

    def test_mp3_header_detection_ignores_random_id3_payload_bytes(self) -> None:
        valid_header = b"ID3\x04\x00\x00\x00\x00\x00\x03abc\xff\xf3"
        random_payload = b"audio-ID3\x04\x00\x00\x00\x00\x00\x03abc-no-frame"
        data = valid_header + (b"\x11" * 64) + random_payload
        self.assertEqual(services.mp3_id3_header_offsets(data), [0])

    def test_mp3_header_detection_finds_concatenated_streams(self) -> None:
        stream = b"ID3\x04\x00\x00\x00\x00\x00\x03abc\xff\xf3" + (b"\x22" * 64)
        self.assertEqual(services.mp3_id3_header_offsets(stream + stream), [0, len(stream)])

    def test_image_quality_score_caps_repeated_root_causes(self) -> None:
        issues = [
            services.quality_issue("warn", f"scenes/s_{index:02d}.png", "图片提示词含生产元信息：画幅要求。")
            for index in range(1, 8)
        ]
        issues.extend(
            services.quality_issue("warn", f"scenes/s_{index:02d}.png", "图片与主题/口播贴合偏弱：30 分。")
            for index in range(1, 4)
        )
        issues.extend([
            services.quality_issue("warn", "场景差异度", "多张场景图提示词过于相似。"),
            services.quality_issue("warn", "口播绑定", "部分场景图没有明确绑定对应口播。"),
            services.quality_issue("info", "cover_landscape.png", "图片自检提示：cover_title_missing"),
            services.quality_issue("info", "cover_story.png", "图片自检提示：cover_title_missing"),
            services.quality_issue("info", "cover_portrait.png", "图片自检提示：cover_title_missing"),
        ])

        score = services.image_quality_score_from_issues(issues)

        self.assertGreaterEqual(score, 60)
        self.assertLess(score, 100)

    def test_cover_ocr_unavailable_is_not_reported_as_missing_title(self) -> None:
        if services.Image is None or services.np is None:
            self.skipTest("image audit dependencies unavailable")
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "cover.png"
            services.Image.new("RGB", (128, 72), (240, 230, 210)).save(image_path)
            with patch.object(
                services,
                "run_local_image_ocr",
                return_value={"status": "unavailable", "engine": "rapidocr", "text": "", "lines": []},
            ):
                report = services.audit_generated_image(
                    image_path,
                    "128x72",
                    "cover",
                    "封面主标题必须原样清晰写成「华为小米围剿苹果」",
                )

            self.assertIn("cover_text_ocr_unavailable", report["reasons"])
            self.assertNotIn("cover_title_missing", report["reasons"])
            self.assertNotIn("cover_subtitle_missing", report["reasons"])

    def test_generic_device_word_does_not_force_smart_home_scene(self) -> None:
        prompt = services.concrete_visual_hint_from_anchor(
            "华为小米发布会设备正面对撞苹果",
            "手机厂商同一天发布新品",
            "cover",
        )
        self.assertNotIn("真实家居空间", prompt)
        self.assertNotIn("墙体", prompt)
        self.assertNotIn("插座", prompt)

    def test_distilled_prompt_does_not_override_cartoon_with_photography(self) -> None:
        prompt = services.distill_content_authored_image_prompt(
            "频道质感：成熟纸张线稿卡通。封面主主体：华为、小米、苹果发布会舞台对峙。封面具体画面：三方新品同台竞争。",
            "cover",
        )
        self.assertIn("纸张线稿卡通", prompt)
        self.assertNotIn("真实摄影质感", prompt)

    def test_manual_landscape_redraw_derives_two_variants_without_extra_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            calls = []

            def fake_generate(prompt, output_path, *_args, **_kwargs):
                calls.append((prompt, output_path))
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"N" * 5000)
                output_path.with_suffix(".md").write_text(prompt, encoding="utf-8")
                output_path.with_suffix(".audit.json").write_text(
                    json.dumps({"ok": True, "severity": "ok", "reasons": []}),
                    encoding="utf-8",
                )
                return output_path

            with (
                patch.object(services.storage, "project_file", side_effect=lambda _project_id, relative: root / relative),
                patch.object(services.storage, "get_project", return_value={"template": ""}),
                patch.object(services.storage, "get_template", return_value={}),
                patch.object(services, "runtime_env", return_value={}),
                patch.object(services, "save_image_prompt_control", return_value={}),
                patch.object(services, "resolve_image_provider_queue", return_value=[{"key": "test", "label": "测试"}]),
                patch.object(services, "generate_configured_image", side_effect=fake_generate),
                patch.object(services, "derive_cover_variants_from_master", return_value=2) as derive,
                patch.object(services, "mark_image_review_dirty", return_value={}),
                patch.object(services, "record_production_step", return_value={}),
            ):
                result = services.regenerate_project_image(
                    1,
                    "cover",
                    "landscape",
                    "主题：手机发布会。封面主标题：三强正面对撞。",
                )

            self.assertEqual(len(calls), 1)
            derive.assert_called_once()
            self.assertEqual(result["derived_count"], 2)

    def test_chatgpt_cover_missing_title_retries_once_with_exact_title(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "cover_landscape.png"
            generated_prompts = []
            audits = [
                {"ok": False, "severity": "hard", "reasons": ["cover_title_missing"], "warnings": []},
                {"ok": True, "severity": "ok", "reasons": [], "warnings": []},
            ]

            def generate(prompt, path, *_args, **_kwargs):
                generated_prompts.append(prompt)
                path.write_bytes((f"image-{len(generated_prompts)}" * 100).encode("utf-8"))
                return path

            with (
                patch.object(
                    services,
                    "resolve_image_provider_queue",
                    return_value=[{"key": "chatgpt_web_auto", "label": "ChatGPT 网页自动化", "model": ""}],
                ),
                patch.object(services, "image_prompt_has_topic_anchor", return_value=True),
                patch.object(services, "sanitize_prompt_for_image_model", side_effect=lambda prompt, _purpose: prompt),
                patch.object(services, "prompt_visual_score", return_value={"score": 90, "length": 40}),
                patch.object(services, "generate_chatgpt_web_auto_image", side_effect=generate),
                patch.object(services, "normalize_generated_image_size"),
                patch.object(services, "audit_generated_image", side_effect=audits),
            ):
                result = services.generate_configured_image(
                    "主题：手机隐私。主标题：APP真在偷听？。封面具体画面：手机权限冲突现场。",
                    output_path,
                    "2560x1440",
                    "cover",
                    {},
                )

            self.assertEqual(result, output_path)
            self.assertEqual(len(generated_prompts), 2)
            self.assertIn("APP真在偷听？", generated_prompts[1])
            self.assertIn("逐字保留原语言", generated_prompts[1])
            self.assertEqual(output_path.read_bytes(), ("image-2" * 100).encode("utf-8"))

    def test_scene_user_redraw_requirement_survives_final_prompt_compilation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "s_04.png"
            outbound_prompts = []

            def generate(prompt, path, *_args, **_kwargs):
                outbound_prompts.append(prompt)
                path.write_bytes(b"image" * 1000)
                return path

            with (
                patch.object(
                    services,
                    "resolve_image_provider_queue",
                    return_value=[{"key": "chatgpt_web_auto", "label": "ChatGPT Web", "model": ""}],
                ),
                patch.object(services, "image_prompt_has_topic_anchor", return_value=True),
                patch.object(services, "sanitize_prompt_for_image_model", side_effect=lambda prompt, _purpose: prompt),
                patch.object(services, "prompt_visual_score", return_value={"score": 90, "length": 40}),
                patch.object(services, "generate_chatgpt_web_auto_image", side_effect=generate),
                patch.object(services, "normalize_generated_image_size"),
                patch.object(
                    services,
                    "audit_generated_image",
                    return_value={"ok": True, "severity": "ok", "reasons": [], "warnings": []},
                ),
            ):
                services.generate_configured_image(
                    "Topic: vehicle braking\nCurrent speech: braking support failed\n"
                    "Additional requirement: ignored label\n"
                    "追加要求（最高优先级，必须落实）：车型为MPV",
                    output_path,
                    "2560x1440",
                    "scene",
                    {},
                )

            self.assertEqual(len(outbound_prompts), 1)
            self.assertIn("车型为MPV", outbound_prompts[0])

    def test_chatgpt_web_prompt_keeps_requirement_after_second_compilation(self) -> None:
        marker = "\u7528\u6237\u91cd\u7ed8\u786c\u8981\u6c42\uff08\u5fc5\u987b\u843d\u5b9e\u5230\u6210\u56fe\uff09\uff1a"
        requirement = "vehicle must be MPV, not sedan or SUV"

        outbound = services.build_chatgpt_handoff_prompt(
            f"Topic: brake test\nCurrent speech: support failed\n{marker}{requirement}",
            "2560x1440",
            "scene",
            required_user_instruction=requirement,
        )

        self.assertIn(requirement, outbound)

    def test_chatgpt_prompt_does_not_restore_unrelated_rule_number(self) -> None:
        source = (
            "本期主题：刹车测试\n当前完整口播：MPV 制动测试\n"
            "数字硬约束：只允许出现1000000、800、1秒，禁止添加其它数字\n"
            "规则版本：3"
        )

        outbound = services.build_chatgpt_handoff_prompt(source, "2560x1440", "scene")

        self.assertNotIn("必须保持的语义与事实：3", outbound)

    def test_ai_editorial_fact_failure_blocks_even_with_high_total(self) -> None:
        dimensions = []
        for key, _name, _weight, _threshold in services.AI_EDITORIAL_DIMENSIONS:
            dimensions.append(
                {
                    "key": key,
                    "score": 60 if key == "fact_topic_alignment" else 100,
                    "evidence_quotes": ["稿件原句"],
                    "failed_sentences": ["未经来源支持的原句"] if key == "fact_topic_alignment" else [],
                    "reason": "逐句核验结果",
                    "repair_instruction": "只修改被引用的失败句",
                }
            )

        report = services.normalize_ai_editorial_score(
            {"summary": "事实不合格", "hard_vetoes": [], "dimensions": dimensions},
            content="# 主题\n\n## 口播脚本\n【主播】稿件原句。",
            evidence_hash="evidence-hash",
            model="review-model",
            review_round=1,
        )

        self.assertGreaterEqual(report["weighted_total"], 80)
        self.assertFalse(report["passed"])
        self.assertIn("fact_topic_alignment", report["failed_dimension_keys"])

    def test_editorial_evidence_snapshot_excludes_historical_scripts(self) -> None:
        snapshot = services.editorial_evidence_snapshot(
            {"id": 9, "topic_name": "本期机器人", "template": "tech"},
            {"key": "tech", "mode": "video"},
            "只讨论本期机器人",
            [
                {"title": "当前报道", "url": "https://news.example/current", "snippet": "当前事实"},
                {"title": "旧稿", "url": "data/projects/8/content.md", "snippet": "苹果降价"},
            ],
        )

        self.assertEqual(len(snapshot["references"]), 1)
        self.assertEqual(snapshot["references"][0]["title"], "当前报道")
        self.assertNotIn("苹果降价", json.dumps(snapshot, ensure_ascii=False))

    def test_targeted_revision_prompt_contains_only_failed_dimension_evidence(self) -> None:
        review = {
            "dimensions": [
                {
                    "key": "opening_attraction",
                    "name": "开头吸引力",
                    "passed": False,
                    "failed_sentences": ["今天我们来聊一个话题。"],
                    "repair_instruction": "换成具体异常和观众利害",
                },
                {
                    "key": "viewer_value",
                    "name": "观众获得感",
                    "passed": True,
                    "failed_sentences": [],
                    "repair_instruction": "保持不变",
                },
            ],
            "hard_vetoes": [],
        }

        messages = services.compose_targeted_revision_messages(
            {"topic": "机器人", "references": []},
            "# 机器人\n\n## 口播脚本\n【主播】今天我们来聊一个话题。",
            review,
        )
        request = json.loads(messages[1]["content"])

        self.assertEqual(len(request["failed_dimensions"]), 1)
        self.assertEqual(request["failed_dimensions"][0]["key"], "opening_attraction")
        self.assertIn("今天我们来聊一个话题", request["failed_dimensions"][0]["failed_sentences"][0])
        self.assertIn("replacements", request["output_schema"])

    def test_targeted_revision_applies_json_replacements_without_rebuilding_document(self) -> None:
        original = "# 机器人\n\n## Meta\n时长：60秒\n\n## 口播脚本\n【主播】今天我们来聊一个话题。\n【主播】第二句保持不变。\n\n## 重点字幕\n- 第二句\n\n## 图片提示词\n### 场景1\n机器人测试\n\n## 参考资料\n- https://example.com"
        response = json.dumps({"replacements": [{"old": "今天我们来聊一个话题。", "new": "机器人已经开始替人搬运重物。"}]}, ensure_ascii=False)
        with (
            patch.object(services, "runtime_env", return_value={"DEEPSEEK_API_KEY": "key", "DEEPSEEK_BASE_URL": "https://gateway.example/v1", "DEEPSEEK_MODEL": "deepseek-chat"}),
            patch.object(services, "request_deepseek_chat_completion", return_value=(response, "stop")) as request,
        ):
            revised = services.targeted_ai_editorial_revision(
                {"channel": {"mode": "video"}},
                original,
                {"dimensions": [], "hard_vetoes": []},
            )

        self.assertIn("机器人已经开始替人搬运重物", revised)
        self.assertIn("第二句保持不变", revised)
        self.assertIn("## 图片提示词", revised)
        self.assertEqual(request.call_args.kwargs["extra_body"]["response_format"], {"type": "json_object"})

    def test_editorial_snapshot_includes_explicit_user_evidence(self) -> None:
        brief = """主题说明\n\n事实汇总\n张雪机车 2026 年 4 月 WSBK 夺冠，多家媒体报道。\n2025 年中国摩托车产销均突破 2000 万辆。\n\n成稿要求\n说清楚事实。"""
        with patch.object(services, "numeric_fact_authority_records", return_value=[
            {"kind": "brief_evidence", "label": "brief.md / 事实汇总", "text": "张雪机车 2026 年 4 月 WSBK 夺冠，多家媒体报道。"},
            {"kind": "brief_evidence", "label": "brief.md / 事实汇总", "text": "2025 年中国摩托车产销均突破 2000 万辆。"},
            {"kind": "content", "label": "生成稿", "text": "不应进入证据。"},
        ]):
            snapshot = services.editorial_evidence_snapshot(
                {"id": 127, "topic_name": "摩托车", "template": "tech"},
                {"key": "tech", "mode": "video"},
                brief,
                [],
            )

        self.assertEqual(len(snapshot["user_evidence"]), 2)
        self.assertNotIn("不应进入证据", json.dumps(snapshot, ensure_ascii=False))

    def test_ai_editorial_pipeline_does_not_save_content_when_review_fails(self) -> None:
        with (
            patch.object(services, "ai_editorial_score_report", side_effect=services.ContentGenerationError("review offline")),
            patch.object(services.storage, "save_content") as save_content,
            patch.object(services.storage, "write_json"),
        ):
            with self.assertRaises(services.ContentGenerationError):
                services.run_ai_editorial_pipeline(
                    {"id": 9, "topic_name": "机器人", "template": "tech"},
                    {"key": "tech", "mode": "video"},
                    "本期机器人",
                    [],
                    "# 机器人\n\n## 口播脚本\n【主播】当前正式稿。",
                )

        save_content.assert_not_called()

    def test_ai_editorial_rereview_uses_same_rubric_and_hashes_revised_content(self) -> None:
        failed = {"passed": False, "dimensions": [], "hard_vetoes": [], "rubric_version": services.AI_EDITORIAL_RUBRIC_VERSION}
        revised = "# 机器人\n\n## Meta\n时长：60秒\n\n## 口播脚本\n【主播】新的具体事实。\n\n## 重点字幕\n- 新事实\n\n## 图片提示词\n### 场景1\n机器人测试\n\n## 参考资料\n- https://example.com"

        def score(_evidence, candidate, *, review_round=1):
            if review_round == 1:
                return failed
            return {
                "passed": True,
                "dimensions": [],
                "hard_vetoes": [],
                "rubric_version": services.AI_EDITORIAL_RUBRIC_VERSION,
                "review_round": 2,
                "content_hash": __import__("hashlib").sha256(candidate.encode("utf-8")).hexdigest(),
            }

        with (
            patch.object(services, "ai_editorial_score_report", side_effect=score) as reviewer,
            patch.object(services, "targeted_ai_editorial_revision", return_value=revised),
            patch.object(services, "canonicalize_project_content", return_value={"content": revised}),
            patch.object(services, "refresh_content_image_prompts", side_effect=lambda _p, _t, text: text),
            patch.object(services.storage, "write_json"),
        ):
            final_content, artifact = services.run_ai_editorial_pipeline(
                {"id": 9, "topic_name": "机器人", "template": "tech"},
                {"key": "tech", "mode": "video"},
                "本期机器人",
                [],
                "# 初稿",
            )

        self.assertEqual(reviewer.call_args_list[0].kwargs["review_round"], 1)
        self.assertEqual(reviewer.call_args_list[1].kwargs["review_round"], 2)
        self.assertEqual(artifact["final_review"]["rubric_version"], services.AI_EDITORIAL_RUBRIC_VERSION)
        self.assertEqual(
            artifact["final_review"]["content_hash"],
            __import__("hashlib").sha256(final_content.encode("utf-8")).hexdigest(),
        )

    def test_ai_editorial_review_retries_compact_json_after_truncated_response(self) -> None:
        dimensions = [
            {
                "key": key,
                "score": 90,
                "evidence_quotes": ["具体原句"],
                "failed_sentences": [],
                "reason": "符合标准",
                "repair_instruction": "保持当前事实密度",
            }
            for key, _name, _weight, _threshold in services.AI_EDITORIAL_DIMENSIONS
        ]
        valid = json.dumps(
            {"summary": "可进入生产", "hard_vetoes": [], "dimensions": dimensions},
            ensure_ascii=False,
        )
        with (
            patch.object(
                services,
                "runtime_env",
                return_value={
                    "DEEPSEEK_API_KEY": "test-key",
                    "DEEPSEEK_BASE_URL": "http://127.0.0.1:8317/v1",
                    "DEEPSEEK_MODEL": "deepseek-flash",
                },
            ),
            patch.object(
                services,
                "request_deepseek_chat_completion",
                side_effect=[('{"summary":"truncated"', "length"), (valid, "stop")],
            ) as request,
        ):
            report = services.ai_editorial_score_report(
                {"project_id": 0, "evidence_hash": "evidence"},
                "# 主题\n\n## 口播脚本\n【主播】具体原句。",
            )

        self.assertTrue(report["passed"])
        self.assertEqual(request.call_count, 2)
        self.assertTrue(request.call_args_list[1].kwargs["extra_body"]["response_format"])
        self.assertEqual(request.call_args_list[1].kwargs["extra_body"]["thinking"], {"type": "disabled"})
        second_messages = request.call_args_list[1].kwargs["messages"]
        self.assertIn("上一次响应格式无效或被截断", second_messages[0]["content"])

    def test_long_editorial_review_prompt_requires_bounded_json(self) -> None:
        messages = services.compose_ai_editorial_score_messages(
            {"project_id": 127, "evidence_hash": "evidence", "references": []},
            "# 主题\n\n## 口播脚本\n" + "【主播】这是完整长稿。\n" * 800,
            compact=True,
        )

        self.assertIn("总长度控制在 1800 个汉字以内", messages[0]["content"])
        self.assertIn("reason 不超过 45 字", messages[0]["content"])
        self.assertIn("上一次响应格式无效或被截断", messages[0]["content"])

    def test_production_content_gate_never_rewrites_existing_content(self) -> None:
        failed_review = {
            "rubric_version": services.AI_EDITORIAL_RUBRIC_VERSION,
            "weighted_total": 70,
            "passed": False,
            "review_round": 1,
            "content_hash": "hash",
            "evidence_hash": "evidence",
            "dimensions": [],
            "hard_vetoes": [],
        }
        with (
            patch.object(services, "authoritative_editorial_gate_result", return_value=None),
            patch.object(services, "editorial_evidence_snapshot", return_value={"project_id": 51, "evidence_hash": "evidence"}),
            patch.object(services, "ai_editorial_score_report", return_value=failed_review),
            patch.object(services.storage, "get_project", return_value={"id": 51, "template": "tech"}),
            patch.object(services.storage, "get_template", return_value={"key": "tech", "mode": "video"}),
            patch.object(services.storage, "get_brief", return_value="brief"),
            patch.object(services.storage, "get_content", return_value="# current"),
            patch.object(services, "effective_project_references", return_value=[]),
            patch.object(services.storage, "write_json"),
            patch.object(services.storage, "save_content") as save_content,
        ):
            result = services.refresh_authoritative_editorial_gate(51)

        self.assertFalse(result["passed"])
        save_content.assert_not_called()

if __name__ == "__main__":
    unittest.main()


