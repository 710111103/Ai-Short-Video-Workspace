from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app import services


class AutoVideoContentResumeTests(unittest.TestCase):
    def test_all_production_buttons_use_content_recovery_and_cache_is_busted(self) -> None:
        root = Path(__file__).resolve().parents[1]
        script = (root / "app.js").read_text(encoding="utf-8")
        html = (root / "index.html").read_text(encoding="utf-8")

        self.assertGreaterEqual(script.count("resumeContentGenerationWhenMissing(project,"), 4)
        self.assertIn("20260910-model-dropdown-v2", html)
        self.assertIn("editorIsEmpty", script)
        self.assertIn("文案为空|content\\.md", script)

    def test_empty_content_is_regenerated_before_downstream_production(self) -> None:
        runtime = services.AutoVideoRuntime()
        runtime.state = {
            "project_id": 96,
            "template_key": "tech",
            "tavily_topic": "news",
            "log": "",
        }
        content_runtime = MagicMock()
        content_runtime.start = AsyncMock(return_value={"status": "running"})
        content_runtime.tasks = {}
        content_reads = ["", "generated content"]

        with (
            patch.object(services.storage, "get_content", side_effect=lambda _project_id: content_reads.pop(0)),
            patch.object(services.storage, "get_project", return_value={"id": 96, "template": "tech"}),
            patch.object(services.storage, "get_template", return_value={"key": "tech"}),
            patch.object(services.storage, "get_brief", return_value="topic evidence"),
            patch.object(services.storage, "project_file", return_value=Path("content_generate.json")),
            patch.object(services.storage, "read_json", return_value={"status": "succeeded"}),
            patch.object(services, "ContentRuntime", return_value=content_runtime),
            patch.object(runtime, "_save"),
        ):
            asyncio.run(runtime._ensure_content_before_production(96))

        content_runtime.start.assert_awaited_once()
        self.assertEqual(runtime.state["stage"], "content")
        self.assertIn("文案已恢复", runtime.state["log"])

    def test_existing_content_does_not_regenerate(self) -> None:
        runtime = services.AutoVideoRuntime()
        runtime.state = {"project_id": 96, "log": ""}
        with (
            patch.object(services.storage, "get_content", return_value="ready"),
            patch.object(services, "ContentRuntime") as content_runtime,
        ):
            asyncio.run(runtime._ensure_content_before_production(96))

        content_runtime.assert_not_called()


if __name__ == "__main__":
    unittest.main()
