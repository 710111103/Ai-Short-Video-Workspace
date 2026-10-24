from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import services, storage


class ProductModeTests(unittest.TestCase):
    def test_project_settings_default_to_editorial_and_keep_product_fields(self) -> None:
        normalized = storage.normalize_project_settings(
            {
                "content_type": "product",
                "product_name": "  65W 充电器  ",
                "product_selling_points": "双口\n体积小",
                "product_asset_files": ["front.png", "front.png", "detail.jpg"],
            }
        )
        self.assertEqual(normalized["content_type"], "product")
        self.assertEqual(normalized["product_name"], "65W 充电器")
        self.assertEqual(normalized["product_asset_files"], ["front.png", "detail.jpg"])
        self.assertEqual(storage.normalize_project_settings({})["content_type"], "editorial")

    def test_product_rules_use_facts_as_whitelist(self) -> None:
        project = {"id": 7, "topic_name": "充电器值不值得买", "content_type": "product"}
        settings = {
            "content_type": "product",
            "product_name": "轻行 65W 充电器",
            "product_category": "氮化镓充电器",
            "product_target_customer": "经常出差的人",
            "product_usage_scenarios": "机场与酒店",
            "product_selling_points": "双口同时充电",
            "product_evidence": "标称单口最高 65W",
            "product_offer": "",
            "product_compliance_notes": "不承诺所有手机达到 65W",
            "product_asset_files": ["front.png"],
        }
        with patch.object(services, "project_product_settings", return_value=settings):
            rules = services.build_product_content_rules(project)
            visual = services.product_visual_prompt_block(project, purpose="scene", index=2, total=5)
        self.assertIn("轻行 65W 充电器", rules)
        self.assertIn("事实白名单", rules)
        self.assertIn("严禁自行补齐", rules)
        self.assertIn("保持外形、结构、颜色", visual)
        self.assertIn("手部操作", visual)

    def test_product_reference_images_are_resolved_from_project_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            projects_root = Path(temp_dir) / "projects"
            product_dir = projects_root / "12" / "uploads" / "products"
            product_dir.mkdir(parents=True)
            (product_dir / "front.png").write_bytes(b"png")
            (product_dir / "notes.txt").write_text("not an image", encoding="utf-8")
            output = projects_root / "12" / "scenes" / ".s_01.gen-1.png"
            with (
                patch.object(storage, "PROJECTS_ROOT", projects_root),
                patch.object(
                    storage,
                    "get_project_settings",
                    return_value={
                        "content_type": "product",
                        "product_asset_files": ["front.png", "notes.txt", "missing.jpg"],
                    },
                ),
            ):
                references = services.product_reference_images_for_output(output)
        self.assertEqual([item.name for item in references], ["front.png"])

    def test_editorial_project_does_not_attach_product_images(self) -> None:
        project = {"id": 8, "topic_name": "知识主题", "content_type": "editorial"}
        with patch.object(services, "project_product_settings", return_value={"content_type": "editorial"}):
            self.assertFalse(services.project_is_product_mode(project))
            self.assertEqual(services.build_product_content_rules(project), "")
            self.assertEqual(services.product_visual_prompt_block(project, purpose="cover"), "")


if __name__ == "__main__":
    unittest.main()
