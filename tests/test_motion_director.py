from __future__ import annotations

import unittest

from app import motion_director


class MotionDirectorTests(unittest.TestCase):
    def test_information_scene_locks_text_and_uses_evidence_camera(self) -> None:
        plan = motion_director.build_motion_plan(
            topic="AI 客服是否省钱",
            index=3,
            duration=5,
            scene={
                "narrative_state": "机制拆解/证据",
                "visual_type": "comparison",
                "audio_anchor": "免费试用两个月，按转化结账",
                "motion": "slow_pull_out",
                "visual_director": {
                    "primary_subjects": ["月账单", "客服后台"],
                    "action_peak": "核对节省金额",
                },
            },
        )
        self.assertEqual(plan["narrative_role"], "evidence")
        self.assertEqual(plan["content_family"], "information")
        self.assertIn("文字、数字、图表", plan["environment_motion"])
        self.assertIn("缓慢后拉", plan["camera"])
        self.assertIn("输出静音视频", plan["prompt"])

    def test_prompts_change_with_narrative_function(self) -> None:
        hook = motion_director.build_motion_plan(
            topic="智能门锁",
            index=1,
            scene={
                "narrative_state": "前三秒钩子/痛点",
                "audio_anchor": "门锁突然自己打开",
                "visual_director": {"action_peak": "手停在门把手前"},
            },
        )
        conclusion = motion_director.build_motion_plan(
            topic="智能门锁",
            index=4,
            scene={
                "narrative_state": "结论回扣/互动",
                "audio_anchor": "检查这三个设置",
                "visual_director": {"action_peak": "完成最后一次核验"},
            },
        )
        self.assertNotEqual(hook["camera"], conclusion["camera"])
        self.assertNotEqual(hook["prompt"], conclusion["prompt"])
        self.assertIn("快速靠近", hook["camera"])
        self.assertIn("最后1秒稳定停留", conclusion["camera"])


if __name__ == "__main__":
    unittest.main()

