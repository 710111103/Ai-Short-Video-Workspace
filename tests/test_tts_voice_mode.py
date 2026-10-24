import tempfile
import subprocess
import unittest
import array
import base64
import json
import math
from pathlib import Path
from unittest.mock import patch

from app import original_runtime_bridge, services


class TtsVoiceModeTests(unittest.TestCase):
    def test_single_voice_chunks_never_exceed_podcast_round_limit(self):
        chunks = original_runtime_bridge.split_single_voice_chunks(
            ["这是一个很长的完整句子。" * 80]
        )

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 280 for chunk in chunks))
        self.assertEqual("".join(chunks), "这是一个很长的完整句子。" * 80)

    def test_explicit_dual_template_adds_a_balanced_second_voice(self) -> None:
        dialogue = [
            {"speaker": "主播", "text": "第一句。"},
            {"speaker": "主播", "text": "第二句。"},
        ]

        self.assertEqual(services.resolve_tts_voice_mode("dual", dialogue), "dual")
        normalized = services.normalize_tts_dialogue_for_voice_mode(dialogue, "dual")
        self.assertEqual({item["speaker"] for item in normalized}, {"主播A", "主播B"})
        self.assertTrue(services.dialogue_voice_balance_report(normalized)["balanced"])

    def test_auto_mode_keeps_a_single_role_script_single(self) -> None:
        dialogue = [
            {"speaker": "主播", "text": "第一句。"},
            {"speaker": "主播", "text": "第二句。"},
        ]

        self.assertEqual(services.resolve_tts_voice_mode("", dialogue), "single")

    def test_two_roles_can_use_dual_voice(self) -> None:
        dialogue = [
            {"speaker": "女", "text": "问题。"},
            {"speaker": "男", "text": "回答。"},
        ]

        self.assertEqual(services.resolve_tts_voice_mode("dual", dialogue), "dual")

    def test_single_configuration_stays_single_with_multiple_labels(self) -> None:
        dialogue = [
            {"speaker": "主播", "text": "正文。"},
            {"speaker": "旁白", "text": "补充。"},
        ]

        self.assertEqual(services.resolve_tts_voice_mode("single", dialogue), "single")

    def test_single_mode_normalizes_every_line_to_one_role(self) -> None:
        dialogue = [
            {"speaker": "主播", "text": "正文。"},
            {"speaker": "女", "text": "突然插入的一句。"},
        ]

        normalized = services.normalize_tts_dialogue_for_voice_mode(dialogue, "single")

        self.assertEqual({item["speaker"] for item in normalized}, {"主播"})

    def test_dual_mode_keeps_distinct_roles(self) -> None:
        dialogue = [
            {"speaker": "女", "text": "问题。"},
            {"speaker": "男", "text": "回答。"},
        ]

        normalized = services.normalize_tts_dialogue_for_voice_mode(dialogue, "dual")

        self.assertEqual([item["speaker"] for item in normalized], ["女", "男"])

    def test_highly_imbalanced_dual_roles_are_redistributed(self) -> None:
        dialogue = [
            *[{"speaker": "主播", "text": f"这是第 {index} 句正文，长度保持接近。"} for index in range(1, 9)],
            {"speaker": "提问", "text": "最后一句。"},
        ]

        normalized = services.normalize_tts_dialogue_for_voice_mode(dialogue, "dual")
        report = services.dialogue_voice_balance_report(normalized)

        self.assertEqual({item["speaker"] for item in normalized}, {"主播A", "主播B"})
        self.assertTrue(report["balanced"])
        self.assertGreaterEqual(report["minor_character_ratio"], 0.40)

    def test_narrative_bracket_label_is_not_spoken_and_not_a_second_role(self) -> None:
        payload = services.sanitized_dialogue_payload_for_tts(
            [
                "【主播】前面都是同一个人讲。",
                "【问你们一个问题】你最常用哪一家产品？",
            ],
            "",
            "科技巨头",
        )

        self.assertEqual({item["speaker"] for item in payload}, {"主播"})
        self.assertTrue(any(item["text"] == "你最常用哪一家产品？" for item in payload))
        self.assertFalse(any("问你们一个问题" in item["text"] for item in payload))

    def test_unlabelled_lines_inherit_current_speaker_instead_of_alternating(self) -> None:
        payload = services.bridge_dialogue_payload(
            ["【主播】第一句。", "没有重复角色标签的第二句。", "没有重复角色标签的第三句。"]
        )

        self.assertEqual({item["speaker"] for item in payload}, {"主播"})

    def test_single_voice_request_locks_both_slots_and_every_dialogue_role(self) -> None:
        dialogue, overrides, speakers = original_runtime_bridge.enforce_single_voice_request(
            [
                {"speaker": "主播", "text": "第一句。"},
                {"speaker": "speaker_b", "text": "不应切换音色。"},
            ],
            {
                "voice_mode": "single",
                "speaker_1": "voice-a",
                "speaker_2": "voice-b",
                "random_order": True,
            },
            {},
        )

        self.assertEqual({item["speaker"] for item in dialogue}, {"主播"})
        self.assertEqual(len(dialogue), 2)
        self.assertEqual(" ".join(item["text"] for item in dialogue), "第一句。 不应切换音色。")
        self.assertTrue(all("\n" not in item["text"] for item in dialogue))
        self.assertEqual(overrides["speaker_1"], "voice-a")
        self.assertEqual(overrides["speaker_2"], "voice-a")
        self.assertFalse(overrides["random_order"])
        self.assertEqual(speakers, ["voice-a"])

    def test_single_voice_api_payload_matches_action_3_schema(self) -> None:
        params = {
            "action": 3,
            "speaker_info": {
                "random_order": True,
                "speakers": ["voice-a", "voice-a"],
            },
            "nlp_texts": [
                {"speaker": "voice-a", "text": "第一段。"},
                {"speaker": "voice-a", "text": "第二段。"},
            ],
        }

        result = original_runtime_bridge.collapse_single_voice_request_params(
            params,
            "voice-a",
            "voice-b",
        )

        self.assertNotIn("speaker_info", result)
        self.assertEqual({item["speaker"] for item in result["nlp_texts"]}, {"voice-a"})

    def test_tts_v3_stream_decoder_joins_all_audio_chunks(self) -> None:
        first = b"first-audio"
        second = b"second-audio"
        response = "\n".join(
            [
                json.dumps({"code": 0, "data": base64.b64encode(first).decode("ascii")}),
                json.dumps({"code": 0, "data": base64.b64encode(second).decode("ascii")}),
                json.dumps({"code": 20000000, "message": "done"}),
            ]
        ).encode("utf-8")

        audio, final = original_runtime_bridge.decode_tts_v3_stream(response)

        self.assertEqual(audio, first + second)
        self.assertEqual(final["code"], 20000000)

    def test_saturn_voice_uses_tts_v2_resource(self) -> None:
        self.assertEqual(
            original_runtime_bridge.single_voice_resource_id(
                "zh_male_dayixiansheng_v2_saturn_bigtts",
                {},
            ),
            "seed-tts-2.0",
        )

    def test_single_voice_resource_can_be_overridden(self) -> None:
        self.assertEqual(
            original_runtime_bridge.single_voice_resource_id(
                "voice-a",
                {"VOLC_TTS_SINGLE_RESOURCE_ID": "custom-resource"},
            ),
            "custom-resource",
        )


class BgmInstrumentalPolicyTests(unittest.TestCase):
    def test_vocal_catalog_result_is_rejected(self) -> None:
        self.assertTrue(
            services.bgm_candidate_has_vocals(
                {"name": "Warm documentary", "tags": ["ambient", "female voice", "speech"]}
            )
        )

    def test_instrumental_catalog_result_is_allowed(self) -> None:
        self.assertFalse(
            services.bgm_candidate_has_vocals(
                {"name": "Documentary pulse", "tags": ["instrumental", "ambient", "background"]}
            )
        )

    def test_whisper_or_human_sample_is_rejected_as_background_music(self) -> None:
        self.assertTrue(
            services.bgm_candidate_has_vocals(
                {"name": "Atmospheric element", "tags": ["ambient", "whisper", "human"]}
            )
        )

    def test_factory_fan_ambience_is_rejected_as_background_music(self) -> None:
        self.assertTrue(
            services.bgm_candidate_is_non_music_noise(
                {
                    "name": "Ambient Industrial/Factory/Fans",
                    "tags": ["Ambience", "Buzz", "Buzzing", "Factory", "Fans", "Machinery", "Noise"],
                }
            )
        )

    def test_instrumental_electronic_track_is_not_rejected_as_noise(self) -> None:
        self.assertFalse(
            services.bgm_candidate_is_non_music_noise(
                {
                    "name": "Industrial pulse soundtrack",
                    "tags": ["instrumental", "electronic", "music", "synth", "loop"],
                }
            )
        )

    def test_asr_vocal_evidence_rejects_spoken_phrase(self) -> None:
        evidence = services.bgm_asr_vocal_evidence(
            [{"start_ms": 100, "end_ms": 1800, "text": "欢迎关注这个频道"}]
        )

        self.assertTrue(evidence["has_vocals"])
        self.assertEqual(evidence["utterance_count"], 1)

    def test_asr_vocal_evidence_ignores_music_marker(self) -> None:
        evidence = services.bgm_asr_vocal_evidence(
            [{"start_ms": 0, "end_ms": 5000, "text": "纯音乐"}]
        )

        self.assertFalse(evidence["has_vocals"])


class TtsAudioProcessingTests(unittest.TestCase):
    def test_boundary_pause_varies_by_punctuation_and_speaker(self) -> None:
        same_speaker = {"speaker": "主播", "text": "说完了。"}
        question = {"speaker": "主播", "text": "真的吗？"}
        continuation = {"speaker": "主播", "text": "比如心率"}
        next_line = {"speaker": "主播", "text": "下一句。"}
        other_speaker = {"speaker": "嘉宾", "text": "我来回答。"}

        self.assertEqual(services.tts_boundary_pause_ms(same_speaker, next_line), 360)
        self.assertEqual(services.tts_boundary_pause_ms(question, next_line), 440)
        self.assertEqual(services.tts_boundary_pause_ms(continuation, next_line), 260)
        self.assertEqual(services.tts_boundary_pause_ms(same_speaker, other_speaker), 520)

    def test_multiple_doubao_mp3_round_headers_are_detected(self) -> None:
        header = b"ID3\x04\x00\x00\x00\x00\x00\x00"
        payload = header + b"a" * 1024 + header + b"b" * 1024 + header + b"c" * 1024

        self.assertEqual(
            services.mp3_id3_header_offsets(payload),
            [0, 1034, 2068],
        )

    def test_incidental_id3_text_without_a_valid_version_is_ignored(self) -> None:
        payload = b"prefix-ID3-text" + b"ID3\x04\x00\x00\x00\x00\x00\x00"

        self.assertEqual(services.mp3_id3_header_offsets(payload), [15])

    def test_pcm_quality_rejects_sustained_high_frequency_corruption(self) -> None:
        clean = array.array("h", [int(12000 * math.sin(2 * math.pi * 440 * i / 24000)) for i in range(24000)])
        corrupt = array.array("h", [14000 if i % 2 == 0 else -14000 for i in range(24000)])

        self.assertFalse(services.pcm16_voice_quality(clean.tobytes())["suspicious"])
        self.assertTrue(services.pcm16_voice_quality(corrupt.tobytes())["suspicious"])

    def test_rounds_with_different_sample_rates_are_decoded_independently(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "first.mp3"
            second = root / "second.mp3"
            combined = root / "podcast.mp3"
            for path, rate, frequency in ((first, 16000, 440), (second, 48000, 880)):
                subprocess.run(
                    [
                        str(services.ffmpeg_binary()),
                        "-y",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-f",
                        "lavfi",
                        "-i",
                        f"sine=frequency={frequency}:duration=1",
                        "-ar",
                        str(rate),
                        "-ac",
                        "1",
                        str(path),
                    ],
                    check=True,
                    **services.background_subprocess_kwargs(),
                )
            combined.write_bytes(first.read_bytes() + second.read_bytes())

            metadata = services.normalize_tts_audio_asset(
                combined,
                [
                    {"speaker": "主播", "text": "第一句。"},
                    {"speaker": "主播", "text": "第二句。"},
                ],
            )

            self.assertEqual(metadata["decode_strategy"], "per_round_pcm")
            self.assertEqual(metadata["round_count"], 2)
            self.assertEqual(metadata["id3_headers_after"], 1)
            self.assertAlmostEqual(metadata["output_duration"], 2.36, delta=0.15)
            self.assertGreaterEqual(metadata["inserted_pause_seconds"], 0.30)
            self.assertEqual(len(metadata["boundary_pacing"]), 1)
            self.assertEqual(metadata["repaired_rounds"], [])
            self.assertFalse(metadata["final_quality"]["suspicious"])


class VoiceAssetStatusTests(unittest.TestCase):
    def test_current_single_voice_manifest_is_reported_as_locked(self) -> None:
        dialogue = [{"speaker": "主播", "text": "第一句。"}, {"speaker": "主播", "text": "第二句。"}]
        speech_hash = services.semantic_text_hash([item["text"] for item in dialogue])
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audio = root / "audio" / "podcast.mp3"
            audio.parent.mkdir(parents=True)
            audio.write_bytes(b"audio")
            services.storage.write_json(
                root / "audio" / "voice_manifest.json",
                {
                    "version": services.TTS_VOICE_MANIFEST_VERSION,
                    "generated_at": 1,
                    "voice_mode": "single",
                    "selected_voice": "voice-a",
                    "effective_speakers": ["voice-a"],
                    "single_voice_enforced": True,
                    "single_round_enforced": True,
                    "utterance_count": 2,
                    "speech_hash": speech_hash,
                },
            )
            with (
                patch.object(services.storage, "get_project", return_value={"id": 7, "template": "频道", "template_mode": "video", "topic_name": "主题"}),
                patch.object(services.storage, "get_template", return_value={"mode": "video", "voice_mode": "single", "tts_speaker_1": "voice-a"}),
                patch.object(services.storage, "get_content", return_value="正文"),
                patch.object(services.storage, "project_file", side_effect=lambda _project_id, relative: root / relative),
                patch.object(services, "current_spoken_dialogue_payload", return_value=dialogue),
                patch.object(services, "runtime_env", return_value={}),
                patch.object(services, "tts_voice_label", side_effect=lambda value: {"voice-a": "声音 A"}.get(value, value)),
            ):
                status = services.project_tts_voice_status(7)

        self.assertEqual(status["status"], "current")
        self.assertTrue(status["single_voice_enforced"])
        self.assertIn("2/2", status["reason"])

    def test_changed_speech_rate_marks_existing_audio_stale(self) -> None:
        dialogue = [{"speaker": "主播", "text": "这是一段用于测试语速版本的口播。"}]
        speech_hash = services.semantic_text_hash([item["text"] for item in dialogue])
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audio = root / "audio" / "podcast.mp3"
            audio.parent.mkdir(parents=True)
            audio.write_bytes(b"audio")
            services.storage.write_json(
                root / "audio" / "voice_manifest.json",
                {
                    "version": services.TTS_VOICE_MANIFEST_VERSION,
                    "generated_at": 1,
                    "voice_mode": "single",
                    "selected_voice": "voice-a",
                    "effective_speakers": ["voice-a"],
                    "single_voice_enforced": True,
                    "utterance_count": 1,
                    "speech_hash": speech_hash,
                    "speech_rate": 1.0,
                    "audio_processing": {"output_duration": 30.0},
                },
            )
            with (
                patch.object(services.storage, "get_project", return_value={"id": 7, "template": "频道", "template_mode": "video", "topic_name": "主题"}),
                patch.object(services.storage, "get_template", return_value={"mode": "video", "voice_mode": "single", "tts_speaker_1": "voice-a", "tts_speech_rate": 0.9}),
                patch.object(services.storage, "get_content", return_value="正文"),
                patch.object(services.storage, "project_file", side_effect=lambda _project_id, relative: root / relative),
                patch.object(services, "current_spoken_dialogue_payload", return_value=dialogue),
                patch.object(services, "runtime_env", return_value={}),
                patch.object(services, "tts_voice_label", side_effect=lambda value: value),
            ):
                status = services.project_tts_voice_status(7)

        self.assertEqual(status["status"], "stale")
        self.assertEqual(status["generated_speech_rate"], 1.0)
        self.assertEqual(status["configured_speech_rate"], 0.9)
        self.assertEqual(status["audio_duration_seconds"], 30.0)
        self.assertIn("0.90x", status["reason"])


class TaskTimeoutTests(unittest.TestCase):
    def test_rewrite_timeout_default_is_patient(self) -> None:
        self.assertEqual(services.deepseek_rewrite_timeout_seconds({}), 180)

    def test_configured_timeout_is_bounded(self) -> None:
        self.assertEqual(services.configured_timeout_seconds({"WAIT": "12"}, "WAIT", 300, 30, 600), 30)
        self.assertEqual(services.configured_timeout_seconds({"WAIT": "999"}, "WAIT", 300, 30, 600), 600)


if __name__ == "__main__":
    unittest.main()
