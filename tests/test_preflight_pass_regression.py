from unittest.mock import patch
from app import services


def test_current_pass_does_not_require_historical_gate():
    with patch.object(services, "cached_stage_gate_result", side_effect=AssertionError("must not read stale gate")):
        assert services.visual_prompt_preflight_may_continue(151, {
            "passed": True, "issues": [], "final_prompts": {"s_01.png": "current prompt"}})


def test_hard_blocker_wins_over_inconsistent_safe_flag():
    assert not services.visual_prompt_preflight_may_continue(151, {
        "passed": True, "generation_safe": True, "hard_blockers": ["wrong topic"],
        "final_prompts": {"s_01.png": "prompt"}})


def test_safe_flag_does_not_replace_missing_prompts():
    assert not services.visual_prompt_preflight_may_continue(151, {"generation_safe": True})


def test_explicit_phone_subject_is_not_banned_by_generic_prop_rule():
    result = services.enforce_scene_prop_contract(
        "本期核心对象必须是：iPhone。\n本镜任务：比较购买条件。", "比较两套购买条件")
    assert "本镜禁用手机" not in result
    assert "iPhone" in result


def test_phone_mentioned_only_in_title_does_not_enable_generic_phone_props():
    result = services.enforce_scene_prop_contract(
        "本期主题：手机行业\n本镜任务：工厂生产线", "工厂提高产量")
    assert "本镜禁用手机" in result
