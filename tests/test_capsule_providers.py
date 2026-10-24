from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app import capsule_providers, services


class CapsuleProviderContractTests(unittest.TestCase):
    def test_seedance_i2v_payload_is_silent_and_uses_first_frame(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "scene.png"
            image_path.write_bytes(b"png-fixture")
            payload = capsule_providers.build_seedance_i2v_payload(
                prompt="人物轻微抬头，屏幕反光自然变化",
                image_path=image_path,
                duration=5,
            )
        self.assertFalse(payload["generate_audio"])
        self.assertEqual(payload["ratio"], "16:9")
        self.assertEqual(payload["content"][1]["role"], "first_frame")
        self.assertTrue(payload["content"][1]["image_url"]["url"].startswith("data:image/png;base64,"))

    def test_agnes_image_payload_matches_public_contract(self) -> None:
        payload = capsule_providers.build_agnes_image_payload(
            prompt="真实办公室，证据物件特写",
            ratio="16:9",
        )
        self.assertEqual(payload["model"], "agnes-image-2.1-flash")
        self.assertEqual(payload["extra_body"], {"response_format": "url"})

    def test_agnes_i2v_payload_uses_free_video_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "scene.png"
            image_path.write_bytes(b"png-fixture")
            payload = capsule_providers.build_agnes_i2v_payload(
                prompt="Only the orange modules light up in sequence; keep the composition stable.",
                image_path=image_path,
                num_frames=121,
                frame_rate=24,
            )
        self.assertEqual(payload["model"], "agnes-video-v2.0")
        self.assertEqual(payload["num_frames"], 121)
        self.assertEqual(payload["frame_rate"], 24)
        self.assertTrue(payload["image"].startswith("data:image/png;base64,"))

    def test_video_clip_filter_does_not_add_zoompan(self) -> None:
        expression = services.build_video_clip_filter(0, 8.0, source_duration=5.0, output_label="clip")
        self.assertIn("tpad=stop_mode=clone", expression)
        self.assertNotIn("zoompan", expression)
        self.assertIn("[clip]", expression)


if __name__ == "__main__":
    unittest.main()
