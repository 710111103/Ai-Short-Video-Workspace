import unittest
from pathlib import Path
from unittest.mock import patch

from app import services, storage


class ProductionResumeGuardTests(unittest.TestCase):
    def test_running_content_generation_blocks_downstream_resume(self) -> None:
        with (
            patch.object(storage, "project_file", return_value=Path("content_generate.json")),
            patch.object(
                storage,
                "read_json",
                return_value={"status": "running", "stage": "write", "started_at": 1},
            ),
            patch.object(storage, "get_content", return_value=""),
        ):
            plan = services.production_resume_plan(86)

        self.assertFalse(plan["can_resume"])
        self.assertEqual(plan["blocked_stage"], "content_generation")
        self.assertEqual(plan["recommended_steps"], [])
        self.assertIn("全自动任务会直接进入", plan["reasons"][0])

    def test_empty_content_blocks_asset_generation(self) -> None:
        with (
            patch.object(storage, "project_file", return_value=Path("content_generate.json")),
            patch.object(storage, "read_json", return_value={"status": "failed"}),
            patch.object(storage, "get_content", return_value="\n"),
        ):
            plan = services.production_resume_plan(86)

        self.assertFalse(plan["can_resume"])
        self.assertEqual(plan["blocked_stage"], "content_missing")
        self.assertEqual(plan["recommended_steps"], [])


if __name__ == "__main__":
    unittest.main()
