import unittest
from pathlib import Path

from app import storage


class PromptPreviewTests(unittest.TestCase):
    def test_preview_ends_at_sentence_boundary(self) -> None:
        prompt = ("第一段" * 15) + "。" + ("中间内容" * 30) + "；第二段也很长" + ("继续" * 30)

        preview = storage.prompt_preview_text(prompt, 80)

        self.assertTrue(preview.endswith("。…") or preview.endswith("；…"))

    def test_frontend_does_not_slice_full_prompt(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "app.js").read_text(encoding="utf-8")

        self.assertNotIn("text.slice(0, 160)", source)
        self.assertIn("item.prompt || item.prompt_preview", source)


if __name__ == "__main__":
    unittest.main()
