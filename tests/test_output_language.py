from __future__ import annotations

import unittest

from app import services, storage


class OutputLanguageTests(unittest.TestCase):
    def test_project_settings_normalize_supported_languages(self) -> None:
        self.assertEqual(
            storage.normalize_project_settings({"output_language": "en-GB"})["output_language"],
            "en-US",
        )
        self.assertEqual(
            storage.normalize_project_settings({"output_language": "zh-TW"})["output_language"],
            "zh-CN",
        )

    def test_english_language_rule_covers_all_audience_assets(self) -> None:
        project = {"id": 0, "output_language": "en-US"}

        rule = services.build_output_language_rules(project)

        self.assertIn("narration", rule)
        self.assertIn("subtitles", rule)
        self.assertIn("release description", rule)
        self.assertIn("readable text requested inside images", rule)
        self.assertIn("## 口播脚本", rule)

    def test_cover_directive_uses_selected_language(self) -> None:
        prompt = services.ensure_cover_text_directives(
            "A high-contrast editorial cover.",
            "The Hidden Cost",
            "What the headline missed",
            "en-US",
        )

        self.assertIn("The Hidden Cost", prompt)
        self.assertIn("拼写正确的英文", prompt)
        self.assertNotIn("简体中文完整可读", prompt)

    def test_english_fallback_keeps_parser_markers_and_english_audience_copy(self) -> None:
        project = {
            "id": 0,
            "topic_name": "Why AI search changes research",
            "output_language": "en-US",
            "content_type": "editorial",
        }
        template = {"mode": "video", "voice_mode": "single"}

        content = services.render_fallback_content(
            project,
            template,
            "Explain the practical tradeoff using verified sources.",
            "general",
            {"references": []},
        )

        self.assertIn("## 口播脚本", content)
        self.assertIn("【主播】", content)
        self.assertIn("Why AI search changes research", content)
        self.assertIn("correctly spelled English", content)
        self.assertNotIn("今天我们来聊聊", content)

    def test_english_engagement_uses_word_based_hook_rules(self) -> None:
        content = """# The hidden cost

## 口播脚本

【主播】The cheapest option can cost you twice.
【主播】At first, the lower price looks like the obvious win.
【主播】But the first replacement changes the math.
【主播】Now compare the warranty, repair time, and actual failure rate.
【主播】For example, one delayed repair can erase the entire saving.
【主播】The catch is simple: purchase price is only the first number.
【主播】So check the full cost before accepting the easy headline.
【主播】Which hidden cost would change your decision first?
"""

        report = services.content_engagement_report(content, "video")

        self.assertEqual(report["detected_language"], "en-US")
        self.assertFalse(report["first_line_chars"] > 120)
        self.assertTrue(report["has_interaction"])
        self.assertGreaterEqual(report["opening_score"], 3.5)
        self.assertGreaterEqual(report["retention_score"], 3.5)

    def test_english_captions_wrap_only_on_word_boundaries(self) -> None:
        source = "The cheapest option can cost you twice when the first repair wipes out the saving."

        segments = services.split_caption_sentence(source, limit=16)

        self.assertGreater(len(segments), 1)
        self.assertEqual(" ".join(segments), source)
        self.assertTrue(all(not segment.startswith(" ") and not segment.endswith(" ") for segment in segments))

    def test_chinese_caption_wrap_balances_long_tail(self) -> None:
        source = "5499元起，比小米17的4499元直接多出一张千元大钞。"

        segments = services.split_caption_sentence(source, limit=20)

        self.assertEqual("".join(segments), source)
        self.assertGreaterEqual(len(segments[-1]), 6)

    def test_caption_wrap_keeps_model_names_numbers_and_units_intact(self) -> None:
        sources = [
            "是台积电2nm工艺的骁龙8至尊版Gen 6。",
            "新一代旗舰平台骁龙8E6系列就会正式揭面。",
            "5499元起，比上一代直接多出一千元。",
        ]

        rendered = [services.split_caption_sentence(source, limit=12) for source in sources]

        self.assertTrue(all("".join(parts) == source for parts, source in zip(rendered, sources)))
        self.assertTrue(all(not any(part.endswith("骁") for part in parts) for parts in rendered))
        for protected in ("2nm", "Gen 6", "8E6", "5499元"):
            matching_parts = next(parts for parts, source in zip(rendered, sources) if protected in source)
            self.assertTrue(any(protected in part for part in matching_parts), protected)

    def test_english_tts_does_not_append_a_chinese_cta(self) -> None:
        lines = [
            "【主播】The cheaper option can cost you twice.",
            "【主播】Which hidden cost would change your decision first?",
        ]

        payload = services.sanitized_dialogue_payload_for_tts(
            lines,
            "\n".join(lines),
            "The hidden cost of cheap products",
        )

        self.assertEqual(len(payload), 2)
        self.assertTrue(payload[-1]["text"].endswith("?"))
        self.assertNotRegex(payload[-1]["text"], r"[\u4e00-\u9fff]")


if __name__ == "__main__":
    unittest.main()
