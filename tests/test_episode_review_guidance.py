import unittest
from unittest.mock import patch
from app import episode_review

class GuidanceTests(unittest.TestCase):
    def test_empty_unchanged(self):
        messages = [{"role": "user", "content": "task"}]
        self.assertIs(episode_review.attach_guidance(messages, {}), messages)
        with patch.object(episode_review.storage, "read_json", return_value={}):
            self.assertIs(episode_review.attach_guidance(messages, {"id": 1}), messages)

    def test_guidance_is_scoped_and_not_evidence(self):
        messages = [{"role": "system", "content": "style"}, {"role": "user", "content": "format"}]
        card = {"audience_question": "手机为什么发热", "evidence_notes": "待核实数字", "audience_feedback": "OLD_COMMENT", "next_experiment": "NEXT_TEST"}
        with patch.object(episode_review.storage, "read_json", return_value=card):
            result = episode_review.attach_guidance(messages, {"id": 109})
        self.assertEqual(len(messages), 2)
        self.assertEqual(result[-1]["content"], "format")
        self.assertIn("手机为什么发热", result[1]["content"])
        self.assertIn("不是已核实新闻", result[1]["content"])
        self.assertNotIn("OLD_COMMENT", str(result))
        self.assertNotIn("NEXT_TEST", str(result))

    def test_corrupt_card(self):
        with patch.object(episode_review.storage, "read_json", return_value=["bad"]):
            self.assertEqual(episode_review.prompt_block({"id": 1}), "")
