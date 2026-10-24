import re
import unittest
from pathlib import Path
from unittest.mock import patch

from app import services


def complete_content(label: str) -> str:
    return f"""# {label}

## Meta
- 核心观点: 这是本期明确结论

## 口播脚本
【主播】{label}，这件事会直接改变普通人的选择。这里有具体事实、原因解释和实际行动，不是空泛写作方法。

## 重点字幕
1. {label}

## 图片提示词
1. 围绕本期事实生成对应画面

## 参考资料
- [资料](https://example.com) - 本期事实来源
"""


class ContentGenerationWarningTests(unittest.TestCase):
    def test_best_current_run_candidate_uses_quality_not_last_attempt(self):
        candidates = [complete_content("首稿"), complete_content("高分稿"), complete_content("末稿")]
        scores = {"首稿": 55, "高分稿": 91, "末稿": 72}

        def assessment(content, _mode):
            label = next(name for name in scores if name in content)
            return {
                "engagement": {},
                "quality_passed": label == "高分稿",
                "rank_score": scores[label],
                "opening_score": 4.5,
                "retention_score": 4.2,
                "overall_score": 4.3,
                "viewer_value_score": 80,
                "warning": "" if label == "高分稿" else "开头吸引力偏弱",
            }

        with patch.object(services, "generated_content_quality_assessment", side_effect=assessment):
            selected = services.select_best_generated_content_candidate(candidates, "video")

        self.assertIsNotNone(selected)
        self.assertEqual(selected["attempt"], 2)
        self.assertIn("高分稿", selected["content"])

    def test_low_editorial_score_is_saved_with_diagnostics_without_rewrite(self):
        draft = complete_content("首稿")
        report = {
            "overall_score": 3.8,
            "opening_score": 3.6,
            "retention_score": 3.7,
            "interaction_score": 4.0,
            "opening_has_stake": False,
            "issues": [{"where": "开头", "issue": "偏弱"}],
            "needs_rewrite": True,
            "viewer_value": {"value_score": 58, "needs_rewrite": True},
        }
        meta = {}
        with (
            patch.object(services, "runtime_env", return_value={
                "DEEPSEEK_API_KEY": "TOKEN",
                "DEEPSEEK_BASE_URL": "https://api.deepseek.com/v1",
                "DEEPSEEK_MODEL": "deepseek-chat",
            }),
            patch.object(services, "compose_deepseek_messages", return_value=[{"role": "system", "content": "规则"}]),
            patch.object(services, "compose_deepseek_rewrite_messages", return_value=[]) as rewrite_prompt,
            patch.object(services, "request_deepseek_chat_completion", return_value=(draft, "stop")) as request,
            patch.object(services, "content_engagement_report", return_value=report),
            patch.object(services, "retention_duration_profile", return_value={"minimum_sec": 0, "target_sec": 0, "maximum_sec": 0}),
        ):
            result = services.render_deepseek_content(
                {"id": 0, "topic_name": "测试主题", "template_mode": "video"},
                {"name": "科技情报站", "mode": "video"},
                "测试 brief",
                "general",
                {"references": []},
                meta,
            )

        self.assertIn("首稿", result)
        self.assertEqual(request.call_count, 1)
        rewrite_prompt.assert_not_called()
        self.assertFalse(meta["quality_passed"])
        self.assertTrue(meta["duration_passed"])
        self.assertTrue(meta["issues"])

    def test_empty_or_broken_draft_is_not_a_valid_candidate(self):
        self.assertIsNone(services.select_best_generated_content_candidate(["", "只有一句话"], "video"))

    def test_gateway_http_500_eof_retries_same_writer_request(self):
        response = {"choices": [{"message": {"content": "# 正常稿"}, "finish_reason": "stop"}]}
        with (
            patch.object(services, "_request_provider_json", side_effect=[RuntimeError('HTTP 500: {"type":"server_error","message":"EOF"}'), response]) as request,
            patch.object(services.time, "sleep"),
        ):
            content, finish_reason = services.request_deepseek_chat_completion(
                api_key="TOKEN",
                base_url="https://gateway.example/v1",
                model="deepseek-v4-flash-0731",
                messages=[],
                temperature=0.6,
                max_tokens=1000,
                timeout=60,
            )
        self.assertEqual(request.call_count, 2)
        self.assertEqual(content, "# 正常稿")
        self.assertEqual(finish_reason, "stop")

    def test_frontend_has_warning_success_label(self):
        app_js = Path("app.js").read_text(encoding="utf-8")
        self.assertIn('succeeded_with_warnings: "已生成 · 建议优化"', app_js)




def test_opening_stake_accepts_visible_photo_damage_without_forced_audience_pronoun():
    opening = "\u624b\u673a AI \u6d88\u9664\u662f\u5728\u731c\u80cc\u666f\u8865\u4e01\u3002\u5730\u7816\u7eb9\u7406\u91cd\u590d\uff0c\u680f\u6746\u53d8\u5f2f\uff0c\u4eba\u6d88\u5931\u4e86\u5f71\u5b50\u8fd8\u7559\u7740\u3002"
    signals = services.opening_semantic_stake_signals(opening)
    assert signals["affected_result"] is True
    assert signals["visible_quality_damage"] is True
    assert signals["has_stake"] is True


def test_generated_delivery_rhythm_splits_long_opening_without_changing_words():
    spoken = (
        "\u624b\u673a AI \u6d88\u9664\uff0c\u4e0d\u662f\u628a\u88ab\u6321\u4f4f\u7684\u771f\u5b9e\u80cc\u666f\u627e\u56de\u6765\uff0c"
        "\u5b83\u662f\u6839\u636e\u5468\u56f4\u50cf\u7d20\u731c\u4e00\u5757\u8865\u4e01\u8d34\u4e0a\u53bb\u3002"
        "\u6240\u4ee5\u5730\u7816\u7eb9\u7406\u53ef\u80fd\u91cd\u590d\uff0c\u680f\u6746\u4f1a\u5f2f\uff0c\u4eba\u6d88\u5931\u4e86\u5f71\u5b50\u8fd8\u7559\u7740\u3002"
    )
    script = "\u3010\u7ed3\u8bba\u3011\n" + spoken
    enhanced, stats = services.enhance_script_section_rhythm_with_limit(
        script, "\u624b\u673aAI\u6d88\u9664\u4e3a\u4ec0\u4e48\u8d8a\u4fee\u8d8a\u5047\uff1f", "video", limit=32
    )
    enhanced_lines = services.parse_dialogue_lines("## \u53e3\u64ad\u811a\u672c\n" + enhanced, "video")
    enhanced_spoken = "".join(services.strip_dialogue_speaker(item) for item in enhanced_lines)
    normalize = lambda value: re.sub(r"[\\s，,。！？!?；;：:]", "", value)
    assert stats["split_count"] >= 1
    assert normalize(spoken) == normalize(enhanced_spoken)
    first_line = services.content_body_lines("## \u53e3\u64ad\u811a\u672c\n" + enhanced, "video")[0]
    assert len(first_line) <= 32

if __name__ == "__main__":
    unittest.main()


def test_rewrite_prompt_preserves_every_production_section():
    messages = services.compose_deepseek_rewrite_messages(
        {"id": 121, "template": "科技情报站"},
        {"name": "科技情报站", "mode": "video"},
        complete_content("原稿"),
        {"issues": [{"where": "开头", "issue": "偏弱", "fix": "直接给结论"}]},
        brief="只回答手机 AI 消除为什么越修越假",
        references=[],
    )
    system_prompt = messages[0]["content"]
    assert "生产章节必须完整保留" in system_prompt
    assert "禁止只返回口播片段" in system_prompt
    assert "不输出图片提示词" not in system_prompt


def test_compact_retry_uses_feedback_duration_and_original_brief():
    calls = []
    recovered = """# 消除为何变假

## Meta
- 时长：80秒
- 核心观点：AI是在猜补丁

## 原始材料简述
- 主体：手机 AI 消除

## 口播脚本
【主播】地砖突然复制了一块，栏杆也被掰弯了，人物没了，影子却还留着。先说结论：手机 AI 消除不是把原来的背景找回来，而是在看周围像素后猜一块补丁。背景纹理简单、遮挡面积小，它通常猜得像；碰到重复地砖、栏杆、墙线、玻璃倒影，线条关系一多，它就容易把附近花纹抄错。判断照片有没有修假，别只看人消失没有。先放大看纹理有没有重复，再看直线有没有弯，接着检查影子和倒影是否还在。重要照片先保留原图，复杂背景少量多次处理，每次消掉一小部分，比一次抹掉大区域更自然。这样检查一遍，你就知道问题不是手机有没有这个按钮，而是这块背景有没有足够线索让它猜对。

## 重点字幕
1. 它不是找回背景，是在猜补丁

## 图片提示词
1. 地砖重复、栏杆弯曲和残留影子的对比画面

## 参考资料
- 本期只解释可观察的软件工作现象
"""

    def request(**kwargs):
        calls.append(kwargs["messages"])
        return (("模型分析，没有 Markdown", "stop") if len(calls) == 1 else (recovered, "stop"))

    passed = {
        "engagement": {"opening_has_stake": True},
        "quality_passed": True,
        "rank_score": 90,
        "opening_score": 5,
        "retention_score": 5,
        "overall_score": 5,
        "viewer_value_score": 90,
        "warning": "",
    }
    profile = {"minimum_sec": 60, "target_sec": 80, "maximum_sec": 100}
    with (
        patch.object(services, "runtime_env", return_value={
            "DEEPSEEK_API_KEY": "TOKEN",
            "DEEPSEEK_BASE_URL": "https://gateway.example/v1",
            "DEEPSEEK_MODEL": "deepseek-v4-flash-0731",
        }),
        patch.object(services, "compose_deepseek_messages", return_value=[{"role": "system", "content": "规则"}]),
        patch.object(services, "request_deepseek_chat_completion", side_effect=request),
        patch.object(services, "retention_duration_profile", return_value=profile),
        patch.object(services, "content_engagement_report", return_value={"needs_rewrite": False, "issues": []}),
        patch.object(services, "generated_content_quality_assessment", return_value=passed),
        patch.object(services, "hollow_script_report", return_value={"hollow": False}),
        patch.object(services, "estimate_spoken_duration_sec", return_value=(336, 70.0)),
    ):
        result = services.render_deepseek_content(
            {"id": 121, "topic_name": "手机AI消除为什么越修越假？", "template_mode": "video"},
            {"name": "科技情报站", "mode": "video", "channel_voice": "像懂技术的朋友聊天"},
            "第一口给结论，解释它是在猜一块补丁",
            "technology",
            {"references": []},
            {},
        )

    compact_prompt = "\n".join(item["content"] for item in calls[1])
    assert "300至650个有效中文字" in compact_prompt
    assert "第一口给结论，解释它是在猜一块补丁" in compact_prompt
    assert "所有二级标题必须逐字保留" in compact_prompt
    assert "## 图片提示词" in result


def test_single_narration_keeps_action_paragraph_with_background_phrase():
    content = """# AI消除为什么越修越假

## 口播脚本
手机AI消除越修越假，它不是还原背景，而是在猜补丁。你放大就会看到纹理重复、栏杆弯曲，人物没了但影子还在。

用的时候记住三点：第一，修完别急着发，放大检查重复纹理。第二，重要照片保留原图，AI只动副本。第三，复杂背景别一次框一大片，少量多次，不行就撤销换小范围。

## 重点字幕
1. 保留原图
"""
    lines = services.parse_dialogue_lines(content, "video")
    spoken = "".join(services.strip_dialogue_speaker(item) for item in lines)
    assert "复杂背景别一次框一大片" in spoken
    assert "保留原图" in spoken
    assert not services.looks_like_visual_generation_instruction(
        "第一，保留原图。第二，复杂背景别一次框一大片，少量多次。"
    )


def test_quality_gate_recognizes_observable_evidence_and_actions():
    content = """# 手机AI消除为什么越修越假？

## 口播脚本
手机AI消除越修越假，最直接的原因：它不是在还原被挡住的真实背景，而是在猜一块补丁。你放大一看就能发现——地砖纹理开始重复，栏杆或墙线在补丁边缘弯了一下，人消失了，影子还留在原地。

这些都是实测里能看到的证据。消除路人之后，两丛灌木中间会突然多出一根柱子；直线边缘被接成锯齿；地面接缝重复得像复制粘贴。不是手机故意骗你，是它只能根据周围像素，推断这一块大概长什么样。周围线条越复杂、遮挡越大，能参考的真实信息越少，它就越容易猜错。而且它只管看起来接得上，不理解透视、光源和立体关系，所以影子、倒影、斜线最容易穿帮。

用的时候记住三点：第一，修完别急着发，放大检查重复纹理、直线有没有弯、影子方向对不对、倒影还在不在。第二，重要照片一定保留原图，AI处理只动副本。第三，复杂背景别一次框一大片，少量多次，一次消一个目标，消完看一眼，不行就撤销换小范围。这样修出来的照片，至少不会第一眼就露馅。

## 重点字幕
1. 保留原图
"""
    report = services.generated_content_quality_assessment(content, "video")
    value = report["engagement"]["viewer_value"]
    assert value["evidence_count"] >= 2
    assert value["action_count"] >= 2
    assert report["engagement"]["opening_has_stake"] is True
    assert report["opening_score"] >= services.CONTENT_OPENING_MIN_SCORE
    assert report["retention_score"] >= services.CONTENT_RETENTION_MIN_SCORE


def test_candidate_selection_prefers_draft_inside_minimum_duration():
    short = complete_content("短稿")
    long = complete_content("达标稿")
    with (
        patch.object(services, "estimate_spoken_duration_sec", side_effect=[(200, 45.0), (320, 70.0)]),
        patch.object(services, "generated_content_quality_assessment", side_effect=[
            {"engagement": {}, "quality_passed": True, "rank_score": 95, "opening_score": 5, "retention_score": 5, "overall_score": 5, "viewer_value_score": 90, "warning": ""},
            {"engagement": {}, "quality_passed": True, "rank_score": 80, "opening_score": 4.5, "retention_score": 4.5, "overall_score": 4.5, "viewer_value_score": 80, "warning": ""},
        ]),
    ):
        selected = services.select_best_generated_content_candidate(
            [short, long], "video", minimum_duration_sec=60, maximum_duration_sec=100
        )
    assert selected is not None
    assert selected["attempt"] == 2
    assert selected["duration_passed"] is True
