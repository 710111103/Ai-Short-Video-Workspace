from __future__ import annotations

import re
from typing import Any


MOTION_DIRECTOR_VERSION = "motion-director-v2"


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _short(value: Any, limit: int = 72) -> str:
    text = _text(value)
    return text if len(text) <= limit else text[: limit - 1].rstrip("，。；：、 ") + "…"


def _director_data(scene: dict[str, Any]) -> dict[str, Any]:
    value = scene.get("visual_director")
    return value if isinstance(value, dict) else {}


def _narrative_role(scene: dict[str, Any], index: int) -> str:
    raw = _text(
        scene.get("narrative_state")
        or scene.get("narrative_role")
        or scene.get("beat_type")
    ).lower()
    if index == 1 or any(word in raw for word in ("钩子", "开场", "hook")):
        return "hook"
    if any(word in raw for word in ("反转", "转折", "reversal")):
        return "reversal"
    if any(word in raw for word in ("证据", "机制", "数据", "拆解", "evidence")):
        return "evidence"
    if any(word in raw for word in ("结论", "回扣", "互动", "cta", "conclusion")):
        return "conclusion"
    if any(word in raw for word in ("冲突", "误区", "痛点", "conflict")):
        return "conflict"
    return "explain"


def _content_family(scene: dict[str, Any]) -> str:
    visual_type = _text(scene.get("visual_type")).lower()
    anchor = _text(
        " ".join(
            str(scene.get(key) or "")
            for key in ("audio_anchor", "visual_anchor", "image_prompt")
        )
    ).lower()
    if visual_type in {"timeline", "comparison", "data", "chart", "infographic"}:
        return "information"
    if any(word in anchor for word in ("屏幕", "界面", "账单", "图表", "数据", "字幕", "信息牌")):
        return "information"
    if any(word in anchor for word in ("手机", "电脑", "产品", "包装", "设备", "机器", "芯片")):
        return "object"
    if any(word in anchor for word in ("人物", "男人", "女人", "老人", "顾客", "员工", "表情", "手指")):
        return "person"
    return "environment"


def _camera_instruction(role: str, family: str, explicit_motion: str, index: int) -> str:
    explicit = _text(explicit_motion).lower()
    explicit_map = {
        "quick_push_in": "前1.2秒快速但平稳地推进到核心证据，随后减速停稳",
        "slow_push_in": "全程缓慢推进约4%，始终锁定核心物件",
        "micro_zoom_then_hold": "前1秒极轻微推进，随后固定构图等待信息被看清",
        "slow_pull_out": "从细节缓慢后拉，逐步揭示细节与结果之间的关系",
        "lateral_slide": "镜头沿信息关系方向缓慢横移，先原因后结果",
        "locked": "固定机位，只允许真实主体和环境发生局部运动",
    }
    if explicit in explicit_map:
        return explicit_map[explicit]
    if family == "information":
        return "固定机位或不超过3%的微推进，所有文字、数字和线条全程保持清晰稳定"
    by_role = {
        "hook": "前1秒快速靠近动作峰值，随后短暂停住形成悬念",
        "conflict": "沿主体动作方向短距离侧移，让原因与异常结果依次进入注意中心",
        "evidence": "从证据细节开始，缓慢后拉到能看懂对象与结果关系的中景",
        "reversal": "先锁定原状态，约2秒时平稳后拉揭示反转信息",
        "conclusion": "缓慢推进到最终结果，最后1秒稳定停留",
        "explain": "平稳微推进或轻微侧移，运动幅度克制并服务当前信息",
    }
    instruction = by_role.get(role, by_role["explain"])
    if index % 3 == 0 and role == "explain":
        instruction = "镜头从前景物件轻微横移到核心证据，最后稳定停留"
    return instruction


def build_motion_plan(
    *,
    topic: str,
    index: int,
    scene: dict[str, Any],
    duration: int = 5,
) -> dict[str, Any]:
    """Create an I2V director plan, deliberately separate from the image prompt.

    The source image owns composition and information. This plan only specifies
    temporal change, camera grammar, continuity and anti-artifact constraints.
    """

    director = _director_data(scene)
    role = _narrative_role(scene, index)
    family = _content_family(scene)
    anchor = _short(scene.get("audio_anchor") or scene.get("speech_text"), 78)
    action_peak = _short(
        director.get("action_peak")
        or scene.get("action_peak")
        or scene.get("motion_prompt")
        or "核心物件发生与口播一致的细微真实变化",
        52,
    )
    subjects = director.get("primary_subjects")
    if isinstance(subjects, list):
        subject_text = "、".join(_short(item, 16) for item in subjects[:3] if _text(item))
    else:
        subject_text = _short(subjects or "当前主体", 42)
    camera = _camera_instruction(role, family, scene.get("motion") or scene.get("motion_prompt"), index)

    if family == "information":
        subject_motion = f"信息载体和构图保持不动；只执行一次明确变化：{action_peak}。原图没有人物或手时，严禁新增人物、手指或操作动作"
        environment_motion = "背景景深和环境光轻微变化，文字、数字、图表、屏幕和标签不变形、不位移"
    elif family == "object":
        subject_motion = f"{subject_text}围绕“{action_peak}”完成一个连续动作，物体结构与位置关系保持真实"
        environment_motion = "只加入与现场一致的屏幕微光、反射、机械细节或景深变化"
    elif family == "person":
        subject_motion = f"{subject_text}完成“{action_peak}”，动作克制自然，眼神、手部和身体运动方向一致"
        environment_motion = "衣物、头发和背景光影仅有轻微自然变化，不抢主体"
    else:
        subject_motion = f"围绕“{action_peak}”产生一次明确、连续、符合物理规律的现场变化"
        environment_motion = "环境中只保留一种辅助运动，例如灯光掠过、蒸汽、车辆或人群远景移动"

    prompt_parts = [
        f"图生视频导演指令，第{index}镜，{duration}秒，叙事功能：{role}",
        f"语义锚点：{anchor}" if anchor else f"主题锚点：{_short(topic, 64)}",
        f"主体运动：{subject_motion}",
        f"摄影机：{camera}",
        f"环境运动：{environment_motion}",
        "时间节奏：起始0.5秒承接第一帧，中段完成唯一动作变化，最后0.8秒稳定落点，不在片段内部切镜",
        "第一帧锁定：保持原图人物身份、产品外形、物体数量、空间关系、构图、色彩及全部可读信息完全一致",
        "不新增或改写人物、物件、文字、数字、图表、标志和界面；避免肢体变形、物体融化、文字闪烁、边缘漂移、镜头抖动和无关运动",
        "输出静音视频，不含对白、旁白、环境音或音乐",
    ]
    return {
        "version": MOTION_DIRECTOR_VERSION,
        "scene_index": index,
        "narrative_role": role,
        "content_family": family,
        "semantic_anchor": anchor,
        "subjects": subject_text,
        "action_peak": action_peak,
        "camera": camera,
        "subject_motion": subject_motion,
        "environment_motion": environment_motion,
        "duration_seconds": duration,
        "prompt": "。".join(part for part in prompt_parts if part),
    }
