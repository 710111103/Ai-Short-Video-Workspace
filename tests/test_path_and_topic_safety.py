from __future__ import annotations

import unittest

from app import original_runtime_bridge, services


class PathAndTopicSafetyTests(unittest.TestCase):
    def test_runtime_path_component_removes_windows_invalid_characters(self) -> None:
        raw = "手机排行：华为第一|三星反超?苹果*承压/新浪新闻"
        result = original_runtime_bridge.safe_path_name(raw, "topic")

        self.assertLessEqual(len(result), 72)
        self.assertFalse(any(char in result for char in '<>:"/\\|?*'))
        self.assertEqual(result, original_runtime_bridge.safe_path_name(raw, "topic"))
        self.assertRegex(result, r"_[0-9a-f]{10}$")

    def test_runtime_path_component_handles_windows_reserved_names(self) -> None:
        result = original_runtime_bridge.safe_path_name("CON", "topic")

        self.assertNotEqual(result.upper(), "CON")
        self.assertFalse(result.endswith("."))

    def test_pipe_metadata_is_not_shown_as_the_project_title(self) -> None:
        raw = (
            "手机品牌排行大洗牌：华为稳居中国第一，三星满意度反超，苹果双线承压+FAQ"
            "|手机品牌排行|华为第一|三星满意度|苹果|手机市场份额|新浪新闻"
        )
        candidates = services._clean_selected_topic_queue([{"title": raw}])

        self.assertEqual(
            candidates[0]["title"],
            "手机品牌排行大洗牌：华为稳居中国第一，三星满意度反超，苹果双线承压+FAQ",
        )
        self.assertNotIn("|", candidates[0]["title"])
        self.assertIn("手机市场份额", candidates[0]["search_query"])


if __name__ == "__main__":
    unittest.main()
