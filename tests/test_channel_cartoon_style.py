from __future__ import annotations

import unittest

from app import services, storage


class ChannelCartoonStyleTests(unittest.TestCase):
    def test_scene_without_phone_intent_explicitly_forbids_phone(self):
        prompt = services.balanced_scene_generation_brief(
            "人物拿着手机站在摩托车旁",
            topic="复古摩托车价格变化",
            speech="这台摩托的发动机和车架，决定了它为什么越来越贵。",
        )
        self.assertIn("本镜禁用手机", prompt)
        self.assertNotIn("人物拿着手机", prompt)
        self.assertIn("车辆题材主体约束", prompt)

    def test_scene_with_phone_intent_keeps_phone_available(self):
        prompt = services.balanced_scene_generation_brief(
            "用户拿着手机查看应用界面",
            topic="手机应用更新",
            speech="打开手机 App 的设置界面，关闭这个开关。",
        )
        self.assertNotIn("本镜禁用手机", prompt)

    def test_explicit_doodle_channel_overrides_technology_keywords(self) -> None:
        template = {
            "name": "科技情报站",
            "cover_style": "doodle",
        }
        style = services.classify_material_style(
            "AI 手机 芯片 智能设备",
            template,
            "scene",
        )
        self.assertEqual(style, "storyboard_comic")

    def test_technology_channel_template_uses_cartoon_identity(self) -> None:
        template = storage.get_template("科技情报站")
        self.assertEqual(template["cover_style"], "doodle")
        self.assertIn("成熟编辑线稿卡通", template["visual_strategy"])
        self.assertIn("不同主题必须更换题材配色", template["image_style_prompt"])
        self.assertNotIn("卡通风", template["image_negative_prompt"])

    def test_technology_channel_duration_is_content_adaptive(self) -> None:
        template = storage.get_template("科技情报站")
        prompt = str(template.get("prompt") or "")

        self.assertIn("按本期信息量自适应", prompt)
        self.assertIn("最终时长以实际配音为准", prompt)
        self.assertNotIn("55—85 秒", prompt)
        self.assertNotIn("280—430", prompt)
        self.assertNotIn("60—85s", prompt)

    def test_cartoon_channel_identity_survives_final_chatgpt_handoff(self) -> None:
        template = storage.get_template("科技情报站")
        source = """本期主题：DeepSeek V4-Flash
当前完整口播：总参数284B，每次只激活13B。
选定视觉概念：真实科技纪录片现场里，一台电脑展示参数变化。
本镜任务：把总参数和激活参数的反差做成一眼可懂的画面。
创作边界：只服务当前口播。
创作自由：由模型选择构图。
"""
        with_policy = services.apply_channel_image_policy(source, template, "scene")
        with_policy += "。同集视觉连续性：保持同一模块阵列、砖红激活节点和手绘靛蓝箭头"
        balanced = services.balanced_scene_generation_brief(with_policy)
        handoff = services.build_chatgpt_handoff_prompt(balanced, "2560x1440", "scene")

        self.assertIn("频道固定视觉签名", balanced)
        self.assertIn("编辑线稿卡通", handoff)
        self.assertIn("同集视觉连续性", handoff)
        self.assertIn("编辑线稿卡通", handoff)
        self.assertNotIn("真实科技纪录片现场", handoff)

    def test_channel_visual_strategy_is_a_final_generation_constraint(self) -> None:
        template = storage.get_template("科技情报站")
        source = "本期主题：AI模型。当前完整口播：只激活少数参数。本镜任务：画出激活与休眠的反差。"
        governed = services.apply_channel_image_policy(source, template, "scene")
        handoff = services.build_chatgpt_handoff_prompt(governed, "2560x1440", "scene")

        self.assertIn("频道画面策略", governed)
        self.assertIn("频道画面规则", handoff)
        self.assertIn("当前口播", governed)
        self.assertIn("编辑线稿卡通", handoff)

    def test_directed_subject_and_action_survive_provider_handoff(self) -> None:
        template = storage.get_template("科技情报站")
        source = """主题：别为AI参数多掏钱。
口播原文：「总参数284B，干一次活，只醒13B」。
主主体：284个参数模块组成的整齐阵列、其中13个被点亮的橙色模块。
动作：少数橙色模块从大阵列中依次点亮。
冲突/悬念：庞大总阵列与极少数实际激活模块形成数量反差。
"""
        governed = services.apply_channel_image_policy(source, template, "scene")
        handoff = services.build_chatgpt_handoff_prompt(governed, "2560x1440", "scene")

        self.assertIn("284个参数模块", handoff)
        self.assertIn("13个被点亮", handoff)
        self.assertIn("依次点亮", handoff)
        self.assertIn("编辑线稿卡通", handoff)

    def test_ai_cartoon_brief_changes_visual_recipe_with_the_narration(self) -> None:
        template = storage.get_template("科技情报站")
        project = {"id": 0, "template_mode": "video", "topic_name": "模型测试", "template": "科技情报站"}
        content = "# 别为AI参数多掏钱\n\n## 口播脚本\n总参数284B，只醒13B。\n1M上下文，一整本书也接得住。"
        brief = services.build_visual_brief(
            project,
            template,
            content,
            scene_count=2,
            beats=["总参数284B，只醒13B", "1M上下文，一整本书也接得住"],
            dialogue_anchors=["总参数284B，只醒13B", "1M上下文，一整本书也接得住"],
        )

        first, second = brief["scenes"]
        self.assertIn("284B", first["dialogue_anchor"])
        self.assertIn("1M", second["dialogue_anchor"])
        serialized = str(brief)
        self.assertNotIn("AI账单", serialized)
        self.assertNotIn("轻量通道", serialized)

    def test_cartoon_channel_does_not_inject_ai_recipe_into_finance_episode(self) -> None:
        template = storage.get_template("科技情报站")
        project = {"id": 0, "template_mode": "video", "topic_name": "美股财报杀", "template": "科技情报站"}
        content = "# 美股财报杀\n\n## 口播脚本\n美股巨头财报爆雷，资金正在换仓。\n外资集中买入中国AI龙头。"
        brief = services.build_visual_brief(
            project,
            template,
            content,
            scene_count=2,
            beats=["美股巨头财报爆雷", "外资集中买入中国AI龙头"],
            dialogue_anchors=["美股巨头财报爆雷", "外资集中买入中国AI龙头"],
        )

        serialized = str(brief)
        for stale in ("284B", "13B", "1M上下文", "AI账单", "全勤参数", "轻量通道"):
            self.assertNotIn(stale, serialized)

    def test_channel_keywords_do_not_turn_motorcycle_episode_into_ai_tech(self) -> None:
        template = storage.get_template("科技情报站")
        project = {"id": 0, "template_mode": "video", "topic_name": "你的热爱正在被重新定价", "template": "科技情报站"}
        content = "# 机车定价\n\n## 口播脚本\n13万8买一辆摩托车，发动机和车架是一笔账，朋友圈的关注是另一笔账。"
        brief = services.build_visual_brief(
            project,
            template,
            content,
            scene_count=1,
            beats=["发动机和车架是一笔账"],
            dialogue_anchors=["13万8买一辆摩托车，发动机和车架是一笔账"],
        )

        self.assertEqual(brief["topic_type"], "vehicle_mobility")
        self.assertIn("发动机", str(brief["subject_pool"]))
        scene_payload = str(brief["scenes"])
        self.assertNotIn("真实用户、智能设备、屏幕光", scene_payload)
        self.assertNotIn("办公室屏幕光", brief["visual_world"])
        self.assertIn("暖米白纸张", brief["visual_world"])
        self.assertNotIn("制动踏板", str(brief["action_pool"]))
        self.assertNotIn("踏板支架", str(brief["action_pool"]))


if __name__ == "__main__":
    unittest.main()
