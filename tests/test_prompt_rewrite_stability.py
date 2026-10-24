import ast
from pathlib import Path

from app import services


def test_authoritative_speech_match_reads_bound_and_full_fields():
    speech = "但微信作为国民级超级应用，适配折叠屏绝不是把手机界面简单拉宽。"
    prompt = (
        "本期主题：iPhone Duo微信不适配。"
        "本镜绑定口播：但微信作为国民级超级应用，适配折叠屏绝不是把手机界面简单拉宽。"
        "当前完整口播：但微信作为国民级超级应用，适配折叠屏绝不是把手机界面简单拉宽。"
        "画面任务：展示折叠屏界面适配差异。"
    )
    assert services.scene_prompt_matches_authoritative_speech(prompt, speech)


def test_authoritative_speech_match_rejects_foreign_scene():
    assert not services.scene_prompt_matches_authoritative_speech(
        "本期主题：折叠屏。当前完整口播：支付应用授权管理列表。",
        "微信适配折叠屏不是简单拉宽。",
    )


def test_preflight_reports_unique_changed_targets_not_internal_events():
    source = Path("app/services.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "preflight_generation_prompt_batch")
    fn_source = ast.get_source_segment(source, fn) or ""
    assert '"changed_count": len(changed_targets)' in fn_source
    assert '"rewrite_event_count": rewrite_event_count' in fn_source
    assert "changed_count +=" not in fn_source


def test_visual_gate_is_limited_to_one_auto_fix_pass():
    source = Path("app/services.py").read_text(encoding="utf-8")
    assert 'gate_key in {"content_gate", "visual_prompt_gate"}' in source
    assert "max_rounds=1" in source
