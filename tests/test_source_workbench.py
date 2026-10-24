from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import services, storage


class SourceWorkbenchTests(unittest.TestCase):
    def test_manual_source_is_persisted_and_enters_reference_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            projects_root = Path(temp_dir) / "projects"
            (projects_root / "7").mkdir(parents=True)
            (projects_root / "7" / "project.json").write_text("{}", encoding="utf-8")
            with patch.object(storage, "PROJECTS_ROOT", projects_root):
                item = services.add_project_source(
                    7,
                    {
                        "type": "url",
                        "title": "官方公告",
                        "url": "https://example.com/report",
                        "note": "确认产品在2026年7月发布",
                        "must_use": True,
                    },
                )
                references = services.project_source_references(7)

        self.assertTrue(item["must_use"])
        self.assertEqual(references[0]["title"], "官方公告")
        self.assertEqual(references[0]["score"], 1.0)
        self.assertEqual(references[0]["source_material_id"], item["id"])

    def test_multi_source_search_merges_providers_and_can_adopt_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            projects_root = Path(temp_dir) / "projects"
            (projects_root / "8").mkdir(parents=True)
            (projects_root / "8" / "project.json").write_text("{}", encoding="utf-8")
            with (
                patch.object(storage, "PROJECTS_ROOT", projects_root),
                patch.object(
                    services,
                    "search_deepseek_web",
                    return_value=[
                        {
                            "title": "DeepSeek来源",
                            "url": "https://deepseek.example/report",
                            "source": "DeepSeek 检索",
                            "provider": "deepseek",
                            "snippet": "实时事实",
                        }
                    ],
                ),
                patch.object(
                    services,
                    "search_tavily",
                    return_value=[
                        {
                            "title": "来源A",
                            "url": "https://a.example/report",
                            "source": "Tavily",
                            "snippet": "事实A",
                        }
                    ],
                ),
                patch.object(
                    services,
                    "search_duckduckgo",
                    return_value=[
                        {
                            "title": "来源B",
                            "url": "https://b.example/report",
                            "source": "DuckDuckGo",
                            "snippet": "事实B",
                        }
                    ],
                ),
            ):
                result = services.search_project_sources(8, "最新 AI 手机", limit=8)
                adopted = services.adopt_project_source_candidate(8, result["results"][0]["id"])

        self.assertEqual(result["providers"], {"DeepSeek": 1, "辅助检索": 1, "DuckDuckGo": 1})
        self.assertEqual(result["primary_provider"], "DeepSeek")
        self.assertEqual(result["results"][0]["source"], "DeepSeek 检索")
        self.assertEqual(len(result["results"]), 3)
        self.assertTrue(adopted["item"]["must_use"])

    def test_current_news_source_search_does_not_call_grok_twice(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            projects_root = Path(temp_dir) / "projects"
            (projects_root / "10").mkdir(parents=True)
            (projects_root / "10" / "project.json").write_text("{}", encoding="utf-8")
            with (
                patch.object(storage, "PROJECTS_ROOT", projects_root),
                patch.object(
                    services,
                    "search_current_news",
                    return_value=[
                        {
                            "title": "DeepSeek实时来源",
                            "url": "https://deepseek.example/live",
                            "source": "DeepSeek 检索",
                            "provider": "deepseek",
                            "snippet": "实时事实",
                        },
                        {
                            "title": "辅助核验",
                            "url": "https://tavily.example/live",
                            "source": "Tavily",
                            "snippet": "核验事实",
                        },
                    ],
                ) as current_search,
                patch.object(services, "search_deepseek_web", side_effect=AssertionError("duplicate DeepSeek call")),
                patch.object(services, "search_duckduckgo", return_value=[]),
            ):
                result = services.search_project_sources(10, "最新 AI 手机", current_news=True, limit=8)

        current_search.assert_called_once_with("最新 AI 手机", 8)
        self.assertEqual(result["providers"]["DeepSeek"], 1)
        self.assertEqual(result["results"][0]["source"], "DeepSeek 检索")

    def test_must_use_source_image_is_attached_to_image_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            projects_root = Path(temp_dir) / "projects"
            source_dir = projects_root / "9" / "uploads" / "sources"
            source_dir.mkdir(parents=True)
            (projects_root / "9" / "project.json").write_text("{}", encoding="utf-8")
            (source_dir / "reference.png").write_bytes(b"png")
            output = projects_root / "9" / "scenes" / ".s_01.gen-1.png"
            with (
                patch.object(storage, "PROJECTS_ROOT", projects_root),
                patch.object(storage, "get_project_settings", return_value={"content_type": "editorial"}),
            ):
                item = services.add_project_source(
                    9,
                    {
                        "type": "image",
                        "title": "产品实拍",
                        "must_use": True,
                    },
                )
                items = services.list_project_sources(9)
                items[0]["relative_path"] = "uploads/sources/reference.png"
                services.save_project_sources(9, items)
                references = services.product_reference_images_for_output(output)

        self.assertEqual(item["type"], "image")
        self.assertEqual([path.name for path in references], ["reference.png"])


if __name__ == "__main__":
    unittest.main()
