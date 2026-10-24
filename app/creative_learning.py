from __future__ import annotations

import hashlib
import json
import math
import re
import time
from pathlib import Path
from typing import Any, Iterable

from . import storage


SCHEMA_VERSION = "creative-intelligence-v1"
RECIPE_VERSION = "channel-capsule-v1"
RESEARCH_VERSION = "multi-source-research-v2-grok-primary"
DATASET_VERSION = "short-video-learning-v1"
CHANNEL_MEMORY_VERSION = "channel-performance-memory-v5"

LEARNING_ROOT = storage.DATA_ROOT / "learning"
LEARNING_EVENTS_FILE = LEARNING_ROOT / "events.jsonl"
LEARNING_DATASET_FILE = LEARNING_ROOT / "training_dataset.jsonl"
LEARNING_SUMMARY_FILE = LEARNING_ROOT / "summary.json"
CHANNEL_MEMORY_ROOT = LEARNING_ROOT / "channel_memory"


PROVIDER_CATALOG: dict[str, dict[str, Any]] = {
    "tavily": {
        "label": "Tavily",
        "strengths": ["公开网页", "新闻发现", "来源链接"],
        "ecosystems": ["global_web", "news", "official"],
        "mode": "api",
    },
    "gemini": {
        "label": "Gemini",
        "strengths": ["全球网页", "知识站点", "技术资料"],
        "ecosystems": ["global_web", "technology", "official"],
        "mode": "browser_or_api",
    },
    "grok": {
        "label": "Grok",
        "strengths": ["实时动态", "海外社交", "热点讨论"],
        "ecosystems": ["realtime", "social", "global_web"],
        "mode": "browser_or_api",
    },
    "doubao": {
        "label": "豆包",
        "strengths": ["中文热点", "抖音生态", "中文内容归纳"],
        "ecosystems": ["china_trend", "douyin", "consumer"],
        "mode": "browser_or_api",
    },
    "yuanbao": {
        "label": "元宝",
        "strengths": ["公众号", "微信生态", "中文信源补充"],
        "ecosystems": ["wechat", "china_web", "official"],
        "mode": "browser_or_api",
    },
    "qwen": {
        "label": "通义千问",
        "strengths": ["中文网页", "行业信息", "电商生态"],
        "ecosystems": ["china_web", "commerce", "industry"],
        "mode": "browser_or_api",
    },
    "kimi": {
        "label": "Kimi",
        "strengths": ["长文阅读", "文档理解", "研究资料整理"],
        "ecosystems": ["long_context", "reports", "global_web"],
        "mode": "browser_or_api",
    },
    "minimax": {
        "label": "MiniMax",
        "strengths": ["B站内容", "中文消费话题", "生活类信息"],
        "ecosystems": ["bilibili", "consumer", "china_trend"],
        "mode": "browser_or_api",
    },
}


def _now() -> float:
    return time.time()


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    storage.write_json(path, payload)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _hash_payload(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _number(value: Any) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def _rate(value: Any) -> float:
    number = _number(value)
    if 0 < number <= 1:
        number *= 100
    return round(max(0.0, min(100.0, number)), 2)


def _channel_memory_path(template_key: str) -> Path:
    return CHANNEL_MEMORY_ROOT / f"{storage.safe_name(_clean(template_key) or 'default')}.json"


def _performance_sample_diagnosis(sample: dict[str, Any]) -> dict[str, Any]:
    metrics = sample.get("metrics") if isinstance(sample.get("metrics"), dict) else {}
    impressions = max(0, int(_number(metrics.get("impressions"))))
    views = max(0, int(_number(metrics.get("views"))))
    ctr = _rate(metrics.get("click_through_rate"))
    if not ctr and impressions and views:
        ctr = round(min(100.0, views / impressions * 100), 2)
    completion = _rate(metrics.get("completion_rate"))
    average_watch = round(_number(metrics.get("average_watch_seconds")), 2)
    duration = round(_number(sample.get("duration_seconds")), 2)
    if duration <= 0 and average_watch > 0 and completion > 0:
        duration = round(average_watch / completion * 100, 2)
    watch_ratio = round(average_watch / duration * 100, 2) if duration > 0 else completion
    likes = max(0, int(_number(metrics.get("likes"))))
    comments = max(0, int(_number(metrics.get("comments"))))
    shares = max(0, int(_number(metrics.get("shares"))))
    favorites = max(0, int(_number(metrics.get("favorites"))))
    follows = max(0, int(_number(metrics.get("follows"))))
    interactions = likes + comments + shares + favorites + follows
    interaction_rate = round(interactions / views * 100, 2) if views else 0.0
    comment_rate = round(comments / views * 100, 2) if views else 0.0
    like_rate = round(likes / views * 100, 2) if views else 0.0
    share_save_rate = round((shares + favorites) / views * 100, 2) if views else 0.0
    view_score = min(100.0, math.log10(views + 1) / 5 * 100) if views else 0.0
    play_potential = round(view_score, 1)
    completion_potential = round(completion, 1)
    comment_potential = round(
        min(100.0, comment_rate / 3 * 100) * 0.70
        + min(100.0, share_save_rate / 2 * 100) * 0.20
        + min(100.0, like_rate / 5 * 100) * 0.10,
        1,
    ) if views else 0.0
    dimension_scores = {
        "play_potential": play_potential,
        "completion_potential": completion_potential,
        "comment_potential": comment_potential,
    }
    confidence = round(min(1.0, math.log10(max(10, views)) / 4.0), 3) if views else 0.15
    age_days = max(0.0, (_now() - _number(sample.get("observed_at") or sample.get("created_at") or _now())) / 86400)
    recency = max(0.35, math.exp(-age_days / 180.0))
    weight = round(confidence * recency, 3)

    strengths: list[dict[str, Any]] = []
    weaknesses: list[dict[str, Any]] = []

    def add(target: list[dict[str, Any]], rule_id: str, rule: str, reason: str, severity: float) -> None:
        target.append({"id": rule_id, "rule": rule, "reason": reason, "weight": round(weight * severity, 3)})

    if ctr >= 8:
        add(strengths, "retain_packaging", "保留能在封面和标题中立即看懂的冲突对象与明确问题。", f"点击率 {ctr}% 表明包装具备吸引力。", 1.0)
    elif ctr and ctr < 5:
        add(weaknesses, "repair_packaging", "标题和封面必须呈现具体对象、明确冲突和观众收益，避免泛概念。", f"点击率仅 {ctr}%。", 1.0)

    if completion and completion < 22:
        add(weaknesses, "repair_retention", "删除重复解释；围绕核心结论补足缺失的证据、原因、现实后果或可执行判断。不要按固定句距插入反问、转折或动作。", f"完播率 {completion}% 显示中后段流失。", 1.2)
    elif completion >= 30:
        add(strengths, "retain_pacing", "保留当前信息推进速度和段落长度。", f"完播率 {completion}% 较健康。", 0.8)

    if duration >= 90 and completion and completion < 25:
        add(weaknesses, "one_answer_per_episode", "一期只解决一个核心问题；时长由证据量决定，长内容拆成连续单结论选题。", f"推算片长约 {int(duration)} 秒且完播率 {completion}%。", 1.0)

    if views and interaction_rate < 1:
        add(weaknesses, "repair_interaction", "先检查选题价值和正文是否交付完整；只有正文自然留下分歧或经历时才加一个承接结论的问题，禁止固定 CTA。", f"每百次播放互动仅 {interaction_rate} 次。", 0.9)
    if views and comment_rate >= 1.5:
        add(strengths, "retain_real_disagreement", "保留由事实自然产生的立场分歧：把双方各自最强理由讲清，再给出创作者判断；不制造虚假争吵。", f"评论率 {comment_rate}% 表明话题具有真实讨论空间。", 1.0)
    if views and comments == 0:
        add(weaknesses, "low_friction_cta", "禁止让观众替创作者找资料、交作业或补证据。评论为零不能单独证明缺少 CTA，优先提升内容的新鲜事实、明确判断和现实用途。", "评论为 0。", 1.15)
    if views and follows == 0:
        add(weaknesses, "follow_payoff", "本期先完整解决当前问题；只有确有后续调查时才说明下一期内容，不用关注口号或悬空预告。", "关注转化为 0。", 0.75)
    if shares > 0 and comments == 0:
        add(strengths, "retain_share_value", "保留可转发的核查价值和实用判断标准。", f"产生 {shares} 次分享，说明信息具有转发价值。", 0.75)

    hook_text = _clean(sample.get("hook_text"))
    authority_patterns = ("没找到", "翻了一晚上", "你们手上", "评论区甩出来", "我们查一下")
    hits = [item for item in authority_patterns if item in hook_text]
    if hits:
        add(
            weaknesses,
            "authority_first",
            "开头先交付已核实的结论和证据边界；禁止用“我没找到、你们帮我找、评论区补资料”代替调查结果。",
            "开头包含削弱可信度的表达：" + "、".join(hits) + "。",
            1.3,
        )

    return {
        "metrics": {
            "impressions": impressions,
            "views": views,
            "click_through_rate": ctr,
            "average_watch_seconds": average_watch,
            "completion_rate": completion,
            "duration_seconds": duration,
            "watch_ratio": watch_ratio,
            "interaction_rate": interaction_rate,
            "comment_rate": comment_rate,
            "like_rate": like_rate,
            "share_save_rate": share_save_rate,
            "likes": likes,
            "comments": comments,
            "shares": shares,
            "favorites": favorites,
            "follows": follows,
        },
        "confidence": confidence,
        "recency_weight": round(recency, 3),
        "sample_weight": weight,
        "dimension_scores": dimension_scores,
        "strengths": strengths,
        "weaknesses": weaknesses,
    }


def _channel_production_guidance_from_memory(memory: dict[str, Any]) -> dict[str, Any]:
    samples = memory.get("samples") if isinstance(memory.get("samples"), list) else []
    rules = memory.get("active_rules") if isinstance(memory.get("active_rules"), list) else []
    rule_ids = {_clean(row.get("id")) for row in rules if isinstance(row, dict)}
    diagnosed = [item for item in samples if isinstance(item, dict)]
    completions = sorted(
        _number((item.get("diagnosis") or {}).get("metrics", {}).get("completion_rate"))
        for item in diagnosed
        if _number((item.get("diagnosis") or {}).get("metrics", {}).get("completion_rate")) > 0
    )
    durations = sorted(
        _number((item.get("diagnosis") or {}).get("metrics", {}).get("duration_seconds"))
        for item in diagnosed
        if _number((item.get("diagnosis") or {}).get("metrics", {}).get("duration_seconds")) > 0
    )

    def median(values: list[float]) -> float:
        if not values:
            return 0.0
        middle = len(values) // 2
        return round(values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2, 1)

    low_completion_count = sum(1 for value in completions if value < 22)
    completion_problem = "repair_retention" in rule_ids or bool(completions and low_completion_count >= max(2, math.ceil(len(completions) * 0.5)))
    one_answer_problem = "one_answer_per_episode" in rule_ids
    interaction_problem = bool({"repair_interaction", "low_friction_cta"} & rule_ids)

    if completion_problem:
        current_problem = "标题或选题能把人带进来，但正文没有持续交付新信息，观众在中后段离开。"
    elif "repair_packaging" in rule_ids:
        current_problem = "标题和封面还没有把具体对象、冲突和观众收益说清。"
    elif interaction_problem:
        current_problem = "内容有观看，但缺少值得表态、转发或带走的明确判断。"
    else:
        current_problem = "真实样本仍在积累，当前先验证开头兑现、信息推进和结论交付。"

    strengths: list[str] = []
    if "retain_packaging" in rule_ids:
        strengths.append("标题与封面能让观众迅速看懂冲突")
    if "retain_real_disagreement" in rule_ids:
        strengths.append("真实观点分歧能带来评论")
    if "retain_share_value" in rule_ids:
        strengths.append("核查价值和实用判断具备转发空间")
    if "retain_pacing" in rule_ids:
        strengths.append("部分样本的信息推进速度有效")
    proven_strength = "；".join(strengths[:3]) or "选题方向已有真实播放样本，下一步重点验证正文兑现。"

    constraints = [
        "开头 2 秒直接兑现标题中的对象、结果或冲突，不先讲背景。",
        "8 秒内交付第一条事实、数字、动作或可观察结果。",
        "一期围绕一个主结论展开，但允许用事实、原因、影响和行动建议把结论讲完整；只有无关支线才另立选题。",
        "每一段至少新增证据、原因、后果或判断中的一种，禁止换句话重复。",
        "术语后立刻用生活场景或动作解释，始终使用大白话。",
        "只有资料存在真实分歧时，才讲清双方最强理由并给出本期判断。",
        "先完整交付结论，再决定是否提一个承接结论的问题。",
        "不使用固定 CTA，不让观众替创作者找资料或补证据。",
        "时长由有效证据量决定，不凑时长，也不为压时长删掉必要证据。",
    ]
    if completion_problem or one_answer_problem:
        constraints.append("当前完播实验优先控制在 60–100 秒；超过该范围必须说明新增了哪些不可删除的证据节点。")

    if completion_problem:
        experiment = "主结论完整交付：开头先给结果，随后按“证据→原因→影响→怎么做”推进；时长由必要信息决定，不为追求短而删掉关键解释。"
        metrics = ["2 秒留存", "5 秒留存", "完播率"]
    elif "repair_packaging" in rule_ids:
        experiment = "同一正文测试两组具体标题与封面，正文结构保持不变，单独验证包装。"
        metrics = ["点击率", "2 秒留存", "播放潜力"]
    elif interaction_problem:
        experiment = "保留完整结论，只在确有真实分歧时加入一个具体选择，验证评论质量。"
        metrics = ["评论率", "分享收藏率", "完播率"]
    else:
        experiment = "先做一条单问题、强证据短片，建立可比较的频道基线。"
        metrics = ["2 秒留存", "5 秒留存", "完播率"]

    evidence: list[str] = []
    if completions:
        evidence.append(f"{low_completion_count}/{len(completions)} 个有效样本完播低于 22%，中位完播 {median(completions)}%。")
    if durations:
        evidence.append(f"有效样本中位时长约 {int(round(median(durations)))} 秒。")
    for row in rules[:3]:
        if not isinstance(row, dict):
            continue
        examples = row.get("evidence") if isinstance(row.get("evidence"), list) else []
        if examples:
            evidence.append(_clean(examples[0]))

    reasons = [
        {
            "title": "本期开头直接给结果",
            "reason": "历史数据表明包装或选题能带来播放，但低完播说明正文兑现太慢。" if completion_problem else "先建立开头是否兑现标题的可比较基线。",
        },
        {
            "title": "本期围绕一个主结论展开",
            "reason": "过去的问题不是信息太多，而是信息没有围绕同一主结论形成推进；本期保留完整证据链，删除无关支线。" if one_answer_problem else "主结论结构能让观众知道这期要得到什么，同时允许原因、影响和做法把价值讲完整。",
        },
        {
            "title": "每段必须推进新信息",
            "reason": "下一期重点删除同义复述，用证据、原因、后果和判断持续兑现标题。",
        },
    ]
    if "retain_real_disagreement" in rule_ids:
        reasons.append({"title": "保留真实双方观点", "reason": "历史评论数据说明真实分歧有讨论价值，但双方理由必须由资料支撑。"})
    elif "retain_share_value" in rule_ids:
        reasons.append({"title": "保留可转发判断", "reason": "历史分享信号说明实用核查标准值得继续保留。"})

    return {
        "sample_count": len(diagnosed),
        "current_problem": current_problem,
        "proven_strength": proven_strength,
        "next_experiment": experiment,
        "observation_metrics": metrics,
        "script_constraints": constraints,
        "evidence": evidence[:5],
        "generation_reasons": reasons,
        "median_completion_rate": median(completions),
        "median_duration_seconds": median(durations),
        "low_completion_count": low_completion_count,
    }


def channel_production_guidance(template_key: str) -> dict[str, Any]:
    memory = rebuild_channel_performance_memory(template_key)
    guidance = memory.get("production_guidance")
    return guidance if isinstance(guidance, dict) else _channel_production_guidance_from_memory(memory)


def rebuild_channel_performance_memory(template_key: str) -> dict[str, Any]:
    path = _channel_memory_path(template_key)
    stored = _read_json(path, {})
    samples = stored.get("samples") if isinstance(stored.get("samples"), list) else []
    aggregates: dict[str, dict[str, Any]] = {}
    diagnosed_samples: list[dict[str, Any]] = []
    for raw in samples[-100:]:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        diagnosis = _performance_sample_diagnosis(item)
        item["diagnosis"] = diagnosis
        diagnosed_samples.append(item)
        for kind in ("strengths", "weaknesses"):
            for rule in diagnosis.get(kind, []):
                rule_id = _clean(rule.get("id"))
                if not rule_id:
                    continue
                row = aggregates.setdefault(rule_id, {"id": rule_id, "kind": kind, "rule": rule.get("rule", ""), "weight": 0.0, "evidence": [], "sample_count": 0})
                row["weight"] = round(_number(row.get("weight")) + _number(rule.get("weight")), 3)
                row["sample_count"] = int(row.get("sample_count", 0) or 0) + 1
                reason = _clean(rule.get("reason"))
                if reason and reason not in row["evidence"]:
                    row["evidence"].append(reason)
    ranked = sorted(aggregates.values(), key=lambda row: (_number(row.get("weight")), int(row.get("sample_count", 0))), reverse=True)
    active = [row for row in ranked if _number(row.get("weight")) >= 0.25][:10]
    dimension_labels = {
        "play_potential": "播放潜力",
        "completion_potential": "完播潜力",
        "comment_potential": "评论潜力",
    }
    dimension_leaders: dict[str, list[dict[str, Any]]] = {}
    for dimension, label in dimension_labels.items():
        ordered = sorted(
            diagnosed_samples,
            key=lambda item: (
                _number((item.get("diagnosis") or {}).get("dimension_scores", {}).get(dimension))
                * _number((item.get("diagnosis") or {}).get("sample_weight")),
                _number((item.get("diagnosis") or {}).get("metrics", {}).get("views")),
            ),
            reverse=True,
        )
        dimension_leaders[dimension] = [
            {
                "sample_id": item.get("sample_id"),
                "project_id": item.get("project_id"),
                "topic": _clean(item.get("topic") or item.get("title")),
                "hook_text": _clean(item.get("hook_text")),
                "score": _number((item.get("diagnosis") or {}).get("dimension_scores", {}).get(dimension)),
                "label": label,
                "metrics": (item.get("diagnosis") or {}).get("metrics", {}),
            }
            for item in ordered[:3]
            if _number((item.get("diagnosis") or {}).get("dimension_scores", {}).get(dimension)) > 0
        ]
    memory = {
        "version": CHANNEL_MEMORY_VERSION,
        "template_key": template_key,
        "sample_count": len(diagnosed_samples),
        "samples": diagnosed_samples,
        "active_rules": active,
        "positive_rules": [row for row in active if row.get("kind") == "strengths"],
        "repair_rules": [row for row in active if row.get("kind") == "weaknesses"],
        "dimension_leaders": dimension_leaders,
        "policy": {
            "method": "带样本置信度与时间衰减的增量频道记忆",
            "rule_activation_threshold": 0.25,
            "max_prompt_rules": 8,
            "note": "单期表现只形成带权证据，不会永久写死频道；后续样本会继续增强、削弱或替换规则。",
        },
        "updated_at": _now(),
    }
    memory["production_guidance"] = _channel_production_guidance_from_memory(memory)
    memory["fingerprint"] = _hash_payload({"samples": diagnosed_samples, "active_rules": active, "dimension_leaders": dimension_leaders, "production_guidance": memory["production_guidance"]})
    _write_json(path, memory)
    return memory


def record_channel_performance(template_key: str, sample: dict[str, Any], *, emit_event: bool = True) -> dict[str, Any]:
    template_key = _clean(template_key)
    if not template_key:
        raise ValueError("template_key is required")
    path = _channel_memory_path(template_key)
    stored = _read_json(path, {})
    samples = stored.get("samples") if isinstance(stored.get("samples"), list) else []
    normalized = dict(sample if isinstance(sample, dict) else {})
    normalized["sample_id"] = _clean(normalized.get("sample_id")) or _hash_payload({"template": template_key, "sample": normalized})
    normalized["observed_at"] = _number(normalized.get("observed_at")) or _now()
    metrics = normalized.get("metrics") if isinstance(normalized.get("metrics"), dict) else {}
    normalized["metrics"] = {
        "impressions": max(0, int(_number(metrics.get("impressions")))),
        "views": max(0, int(_number(metrics.get("views")))),
        "click_through_rate": _rate(metrics.get("click_through_rate")),
        "two_second_retention_rate": _rate(metrics.get("two_second_retention_rate")),
        "five_second_retention_rate": _rate(metrics.get("five_second_retention_rate")),
        "average_watch_seconds": round(_number(metrics.get("average_watch_seconds")), 2),
        "completion_rate": _rate(metrics.get("completion_rate")),
        "likes": max(0, int(_number(metrics.get("likes")))),
        "comments": max(0, int(_number(metrics.get("comments")))),
        "shares": max(0, int(_number(metrics.get("shares")))),
        "favorites": max(0, int(_number(metrics.get("favorites")))),
        "follows": max(0, int(_number(metrics.get("follows")))),
    }
    samples = [item for item in samples if isinstance(item, dict) and _clean(item.get("sample_id")) != normalized["sample_id"]]
    samples.append(normalized)
    _write_json(path, {"version": CHANNEL_MEMORY_VERSION, "template_key": template_key, "samples": samples[-100:]})
    memory = rebuild_channel_performance_memory(template_key)
    if emit_event:
        append_learning_event("channel_performance_recorded", int(normalized.get("project_id", 0) or 0), {"sample_id": normalized["sample_id"], "template_key": template_key, "memory_fingerprint": memory.get("fingerprint")})
    return memory


def record_project_release_performance(project_id: int, release: dict[str, Any]) -> dict[str, Any]:
    project = storage.get_project(project_id)
    content = storage.get_content(project_id)
    hook = ""
    for raw_line in content.splitlines():
        line = _clean(raw_line)
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        if "】" in line:
            line = line.split("】", 1)[1].strip()
        if line:
            hook = line
            break
    release_id = int(release.get("id", 0) or 0)
    metrics = release.get("metrics") if isinstance(release.get("metrics"), dict) else {}
    return record_channel_performance(
        _clean(project.get("template")),
        {
            "sample_id": f"project-{project_id}-release-{release_id}",
            "project_id": project_id,
            "release_id": release_id,
            "platform": _clean(release.get("platform")),
            "topic": _clean(project.get("topic_name")),
            "title": _clean(release.get("title") or project.get("topic_name")),
            "hook_text": hook,
            "metrics": metrics,
            "observed_at": _number(metrics.get("updated_at")) or _number(release.get("created_at")) or _now(),
            "source": _clean(metrics.get("source")) or "release_metrics",
        },
    )


def sync_project_release_memory(project_id: int) -> dict[str, Any]:
    project = storage.get_project(project_id)
    template_key = _clean(project.get("template"))
    memory = rebuild_channel_performance_memory(template_key)
    for release in storage.get_release_links(project_id):
        if not isinstance(release, dict) or not isinstance(release.get("metrics"), dict):
            continue
        content = storage.get_content(project_id)
        hook = next((_clean(line.split("】", 1)[-1]) for line in content.splitlines() if _clean(line) and not _clean(line).startswith(("#", "-"))), "")
        memory = record_channel_performance(
            template_key,
            {
                "sample_id": f"project-{project_id}-release-{int(release.get('id', 0) or 0)}",
                "project_id": project_id,
                "release_id": int(release.get("id", 0) or 0),
                "platform": _clean(release.get("platform")),
                "topic": _clean(project.get("topic_name")),
                "title": _clean(release.get("title") or project.get("topic_name")),
                "hook_text": hook,
                "metrics": release.get("metrics"),
                "observed_at": _number((release.get("metrics") or {}).get("updated_at")) or _number(release.get("created_at")) or _now(),
                "source": _clean((release.get("metrics") or {}).get("source")) or "release_metrics",
            },
            emit_event=False,
        )
    return memory


def channel_performance_prompt_block(template_key: str, max_rules: int = 8) -> str:
    memory = rebuild_channel_performance_memory(template_key)
    rules = memory.get("active_rules") if isinstance(memory.get("active_rules"), list) else []
    if not rules:
        return "频道表现学习：暂无真实发布样本，本期仅服从频道设定与当前资料。"
    lines = [
        f"频道表现分析（{memory.get('sample_count', 0)} 个真实发布样本；仅供生成后复盘，不参与自动写稿）：",
        "- 播放潜力、完播潜力、评论潜力分别判断；评论高不代表留存好，播放高也不代表正文合格。",
        "- 以下规则由播放数据按样本量、置信度和时间衰减得出；当前 brief 和可靠事实始终优先。",
    ]
    guidance = memory.get("production_guidance") if isinstance(memory.get("production_guidance"), dict) else _channel_production_guidance_from_memory(memory)
    lines.extend(
        [
            f"- 当前频道最大问题：{guidance.get('current_problem', '')}",
            f"- 当前已验证能力：{guidance.get('proven_strength', '')}",
            f"- 建议观察方向：{guidance.get('next_experiment', '')}",
            "复盘建议（不作为生成硬约束）：",
            *[f"- {item}" for item in guidance.get("script_constraints", [])],
        ]
    )
    dimension_leaders = memory.get("dimension_leaders") if isinstance(memory.get("dimension_leaders"), dict) else {}
    for dimension, label in (("play_potential", "播放潜力"), ("completion_potential", "完播潜力"), ("comment_potential", "评论潜力")):
        leaders = dimension_leaders.get(dimension) if isinstance(dimension_leaders.get(dimension), list) else []
        if not leaders:
            continue
        leader = leaders[0]
        metrics = leader.get("metrics") if isinstance(leader.get("metrics"), dict) else {}
        lines.append(
            f"- {label}样本：{leader.get('topic') or '未命名'}（{leader.get('score', 0)} 分；"
            f"播放 {metrics.get('views', 0)}，完播 {metrics.get('completion_rate', 0)}%，评论率 {metrics.get('comment_rate', 0)}%）。"
            "只学习其结构信号，不照搬主题与句子。"
        )
    for row in rules[: max(1, int(max_rules or 8))]:
        prefix = "保留" if row.get("kind") == "strengths" else "修正"
        evidence = "；".join(str(item) for item in (row.get("evidence") or [])[:2])
        lines.append(f"- {prefix}：{row.get('rule', '')} 依据：{evidence}")
    return "\n".join(lines)


def _srt_time_to_ms(value: str) -> int:
    match = re.fullmatch(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})", _clean(value))
    if not match:
        return 0
    hours, minutes, seconds, millis = (int(part) for part in match.groups())
    return (((hours * 60) + minutes) * 60 + seconds) * 1000 + millis


def _load_caption_blocks(project_root: Path, cover_duration_ms: int) -> list[dict[str, Any]]:
    subtitle_path = project_root / "subtitles.srt"
    if not subtitle_path.exists():
        subtitle_path = project_root / "audio" / "subtitles.srt"
    blocks: list[dict[str, Any]] = []
    for chunk in re.split(r"\r?\n\r?\n+", _read_text(subtitle_path).strip()):
        lines = [line.strip("\ufeff") for line in chunk.splitlines() if line.strip()]
        time_index = next((index for index, line in enumerate(lines) if "-->" in line), -1)
        if time_index < 0:
            continue
        start_raw, end_raw = [part.strip() for part in lines[time_index].split("-->", 1)]
        body = _clean(" ".join(lines[time_index + 1 :]))
        if not body:
            continue
        blocks.append(
            {
                "index": len(blocks) + 1,
                "start_ms": cover_duration_ms + _srt_time_to_ms(start_raw),
                "end_ms": cover_duration_ms + _srt_time_to_ms(end_raw),
                "text": body,
            }
        )
    return blocks


def _parse_brief_references(project_root: Path) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    for raw_line in _read_text(project_root / "brief.md").splitlines():
        line = raw_line.strip()
        if not line.startswith("- "):
            continue
        url_match = re.search(r"https?://\S+", line)
        if not url_match:
            continue
        url = url_match.group(0).rstrip("，。；;)")
        prefix = line[2 : url_match.start()].strip(" ：:")
        date_match = re.match(r"\[([^\]]+)\]\s*", prefix)
        published_at = date_match.group(1).strip() if date_match else ""
        title = (prefix[date_match.end() :] if date_match else prefix).strip(" ：:")
        domain_match = re.match(r"https?://(?:www\.)?([^/]+)", url, flags=re.IGNORECASE)
        provider = domain_match.group(1) if domain_match else "brief"
        references.append(
            {
                "title": title[:500],
                "url": url,
                "source": provider,
                "published_date": published_at,
                "freshness_status": "brief_reference",
                "score": 0.0,
                "snippet": title[:600],
            }
        )
    return references


def _semantic_tokens(value: str) -> set[str]:
    text = _clean(value).lower()
    tokens = {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9._+-]{1,}|[\u4e00-\u9fff]{2,}", text)
        if len(token) >= 2
    }
    compact_cjk = "".join(re.findall(r"[\u4e00-\u9fff]", text))
    tokens.update(compact_cjk[index : index + 2] for index in range(max(0, len(compact_cjk) - 1)))
    compact_latin = "".join(re.findall(r"[a-z0-9]", text))
    tokens.update(
        compact_latin[index : index + 4]
        for index in range(max(0, len(compact_latin) - 3))
    )
    return tokens


def _source_relevance(source: dict[str, Any], narration: str, topic: str = "") -> float:
    query_tokens = _semantic_tokens(f"{topic} {narration}")
    source_tokens = _semantic_tokens(
        f"{source.get('title', '')} {source.get('snippet', '')} {source.get('provider', '')}"
    )
    if not query_tokens or not source_tokens:
        return 0.0
    lexical = len(query_tokens & source_tokens) / max(1, min(len(query_tokens), 24))
    number_tokens = {token for token in query_tokens if re.search(r"\d", token)}
    number_match = len(number_tokens & source_tokens) / max(1, len(number_tokens))
    freshness = 0.08 if _clean(source.get("freshness_status")) in {"live", "fresh", "brief_reference"} else 0.0
    url = _clean(source.get("url")).lower()
    local_history_penalty = 0.3 if not url.startswith(("http://", "https://")) else 0.0
    return round(max(0.0, min(1.0, lexical + number_match * 0.35 + freshness - local_history_penalty)), 4)


def _project_template(project: dict[str, Any]) -> dict[str, Any]:
    key = _clean(project.get("template"))
    return storage.get_template(key) if key else {}


def provider_catalog() -> list[dict[str, Any]]:
    return [{"id": provider_id, **profile} for provider_id, profile in PROVIDER_CATALOG.items()]


def research_routing_plan(
    topic: str,
    template: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    template = template or {}
    settings = settings or {}
    source = " ".join(
        value
        for value in (
            _clean(topic),
            _clean(template.get("topic_mining_hint")),
            _clean(template.get("target_audience")),
            _clean(template.get("channel_voice")),
        )
        if value
    ).lower()
    current_tokens = (
        "最新",
        "刚刚",
        "今天",
        "昨日",
        "本周",
        "实时",
        "新闻",
        "发布",
        "更新",
        "热搜",
        "热点",
        "政策",
        "涨价",
        "降价",
    )
    social_tokens = ("舆情", "网友", "评论区", "微博", "推特", "x ", "争议", "讨论")
    tech_tokens = ("ai", "模型", "芯片", "手机", "电脑", "软件", "科技", "互联网", "机器人")
    commerce_tokens = ("商品", "价格", "品牌", "购买", "电商", "淘宝", "消费", "测评")
    health_tokens = ("健康", "医生", "疾病", "药", "血压", "血糖", "医学")
    current = bool(settings.get("current_news_mode")) or any(token in source for token in current_tokens)
    social = any(token in source for token in social_tokens)
    technology = any(token in source for token in tech_tokens)
    commerce = any(token in source for token in commerce_tokens)
    health = any(token in source for token in health_tokens)

    priorities: list[tuple[str, str]] = []

    def add(provider_id: str, reason: str) -> None:
        if provider_id not in {item[0] for item in priorities}:
            priorities.append((provider_id, reason))

    add("grok", "主检索：发现实时动态、事件进展和海外讨论")
    add("tavily", "辅助核验：补充公开网页、发布日期和可追溯链接")
    if current:
        add("doubao", "补充中文热点与抖音内容信号")
    if technology:
        add("gemini", "补充全球技术资料、产品文档和官方来源")
        add("kimi", "整理长文、报告和复杂技术背景")
    if commerce:
        add("qwen", "补充中文消费、电商和产品生态信息")
        add("minimax", "补充中文消费体验与视频平台内容信号")
    if health:
        add("gemini", "优先查找权威机构、论文与医学资料")
        add("yuanbao", "补充中文权威来源与公众号信息")
    add("yuanbao", "补充微信生态和中文来源交叉验证")
    if not current and not technology:
        add("kimi", "负责长文整理、来源归纳和冲突信息比对")

    routes = [
        {
            "priority": index + 1,
            "provider": provider_id,
            "label": PROVIDER_CATALOG[provider_id]["label"],
            "reason": reason,
            "strengths": PROVIDER_CATALOG[provider_id]["strengths"],
            "mode": PROVIDER_CATALOG[provider_id]["mode"],
        }
        for index, (provider_id, reason) in enumerate(priorities[:5])
    ]
    query = _clean(topic)
    query_variants = [
        query,
        f"{query} 最新进展 事件发生时间 官方来源",
        f"{query} 核心数据 原始报告 反方证据",
        f"{query} 普通用户真实影响 使用场景",
    ]
    return {
        "version": RESEARCH_VERSION,
        "topic": query,
        "current_news_mode": current,
        "routes": routes,
        "query_variants": [item for item in query_variants if item],
        "evidence_contract": {
            "required_fields": [
                "claim",
                "source_title",
                "source_url",
                "published_at",
                "event_at",
                "source_type",
                "confidence",
                "scene_usage",
            ],
            "rules": [
                "区分网页发布时间和事件发生时间",
                "数字进入口播或图片前至少绑定一个来源",
                "重大结论保留支持证据与反方证据",
                "来源图片只作为证据素材，不把无关网图当装饰",
            ],
        },
        "generated_at": _now(),
    }


def _release_learning_score(metrics: dict[str, Any]) -> float:
    impressions = max(1.0, _number(metrics.get("impressions")))
    views = _number(metrics.get("views"))
    click_rate = _number(metrics.get("click_through_rate"))
    if not click_rate and impressions > 0 and views > 0:
        click_rate = min(100.0, views / impressions * 100.0)
    completion = _number(metrics.get("completion_rate"))
    two_second = _number(metrics.get("two_second_retention_rate"))
    five_second = _number(metrics.get("five_second_retention_rate"))
    engagement = (
        _number(metrics.get("likes"))
        + _number(metrics.get("comments")) * 2.0
        + _number(metrics.get("shares")) * 3.0
        + _number(metrics.get("favorites")) * 2.0
        + _number(metrics.get("follows")) * 4.0
    ) / max(1.0, views) * 100.0
    available = [
        (click_rate, 0.2),
        (two_second, 0.2),
        (five_second, 0.18),
        (completion, 0.27),
        (min(100.0, engagement * 5.0), 0.15),
    ]
    present = [(value, weight) for value, weight in available if value > 0]
    if not present:
        return 0.0
    total_weight = sum(weight for _, weight in present)
    return round(sum(value * weight for value, weight in present) / total_weight, 2)


def channel_experience_memory(template_key: str, limit: int = 5) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for project in storage.list_projects():
        if not isinstance(project, dict) or _clean(project.get("template")) != template_key:
            continue
        project_id = int(project.get("id", 0) or 0)
        best: dict[str, Any] | None = None
        for release in storage.get_release_links(project_id):
            if not isinstance(release, dict):
                continue
            metrics = release.get("metrics") if isinstance(release.get("metrics"), dict) else {}
            score = _release_learning_score(metrics)
            if score <= 0:
                continue
            if best is None or score > _number(best.get("score")):
                best = {
                    "release_id": release.get("id"),
                    "platform": _clean(release.get("platform")),
                    "metrics": metrics,
                    "score": score,
                }
        if best is None:
            continue
        root = storage.project_dir(project_id)
        content_strategy = _read_json(root / "content_strategy.json", {})
        visual_director = _read_json(root / "visual_director.json", {})
        rows.append(
            {
                "project_id": project_id,
                "topic": _clean(project.get("topic_name")),
                "score": best["score"],
                "platform": best["platform"],
                "metrics": best["metrics"],
                "content_strategy": content_strategy,
                "visual_director": visual_director,
            }
        )
    rows.sort(key=lambda item: _number(item.get("score")), reverse=True)
    selected = rows[: max(1, int(limit or 5))]
    return {
        "sample_count": len(rows),
        "top_projects": selected,
        "learned_rules": [
            "只从真实发布表现较好的项目提炼方法",
            "保留结构、节奏和视觉策略，不复制当期事实与素材",
            "每次新增表现数据后重新排序，旧经验保留版本指纹",
        ],
        "memory_fingerprint": _hash_payload(selected),
    }


def build_channel_recipe(template_key: str, persist: bool = True) -> dict[str, Any]:
    template = storage.get_template(template_key)
    experience_memory = channel_experience_memory(template_key)
    performance_memory = rebuild_channel_performance_memory(template_key)
    recipe = {
        "version": RECIPE_VERSION,
        "key": template_key,
        "name": template.get("name") or template_key,
        "identity": {
            "brand_name": template.get("brand_name") or template_key,
            "mode": template.get("mode") or "video",
            "target_audience": template.get("target_audience") or "",
            "channel_voice": template.get("channel_voice") or "",
            "interaction_goal": template.get("interaction_goal") or "",
            "release_tags": template.get("release_tags") or "",
        },
        "content_recipe": {
            "topic_mining_hint": template.get("topic_mining_hint") or "",
            "prompt": template.get("prompt") or "",
            "episode_content_isolation": True,
            "reuse": ["人设", "叙事结构", "节奏方法", "质量规则", "视觉语法", "声音策略"],
            "never_reuse": ["当期事实", "当期数字", "当期案例", "临时素材", "上一期图片提示词"],
        },
        "visual_recipe": {
            "strategy": template.get("visual_strategy") or "",
            "style_prompt": template.get("image_style_prompt") or "",
            "negative_prompt": template.get("image_negative_prompt") or "",
            "cover_style": template.get("cover_style") or "default",
            "generate_cover_landscape": bool(template.get("generate_cover_landscape", True)),
            "generate_cover_portrait": bool(template.get("generate_cover_portrait", True)),
            "rules": [
                "先审分镜，再生成代表镜头",
                "关键镜头允许候选竞争，普通镜头保持单图",
                "只返工失败镜头，不覆盖已确认素材",
                "图片信息必须来自当前口播与来源证据",
            ],
        },
        "voice_recipe": {
            "mode": template.get("voice_mode") or "single",
            "speaker_1": template.get("tts_speaker_1") or "",
            "speaker_2": template.get("tts_speaker_2") or "",
            "random_order": bool(template.get("tts_random_order", False)),
            "speech_rate": _number(template.get("tts_speech_rate") or 1.0),
        },
        "quality_contract": {
            "forbidden_rules": template.get("forbidden_rules") or "",
            "required_gates": [
                "来源时效与事实一致",
                "文案无重复且画面提示不进入口播",
                "配音角色与字幕逐句一致",
                "图片与当前口播语义一致",
                "封面标题完整可读",
                "成片画幅、黑帧、静帧、响度、字幕安全区通过",
            ],
            "repair_scope": {
                "cta_change": ["voice", "subtitles", "video"],
                "fact_change": ["affected_scenes", "voice", "subtitles", "video"],
                "topic_change": ["all"],
                "single_visual_issue": ["affected_scene", "video"],
            },
        },
        "research_policy": research_routing_plan(
            template.get("topic_mining_hint") or template.get("name") or template_key,
            template,
            {},
        ),
        "learning_policy": {
            "capture_candidate_pairs": True,
            "capture_manual_edits": True,
            "capture_release_metrics": True,
            "ranking_targets": ["topic", "hook", "visual", "pacing"],
            "minimum_samples": {
                "recipe_retrieval": 1,
                "heuristic_ranking": 20,
                "statistical_ranking": 200,
                "preference_model": 1000,
            },
        },
        "validated_experience": experience_memory,
        "performance_memory": performance_memory,
        "generated_at": _now(),
    }
    recipe["fingerprint"] = _hash_payload({key: value for key, value in recipe.items() if key != "generated_at"})
    if persist:
        _write_json(storage.TEMPLATES_ROOT / template_key / "recipe.json", recipe)
    return recipe


def list_channel_recipes(refresh: bool = False) -> list[dict[str, Any]]:
    recipes: list[dict[str, Any]] = []
    for template in storage.list_templates():
        key = _clean(template.get("key"))
        path = storage.TEMPLATES_ROOT / key / "recipe.json"
        recipe = _read_json(path, {})
        if refresh or not recipe or recipe.get("version") != RECIPE_VERSION:
            recipe = build_channel_recipe(key, persist=True)
        recipes.append(recipe)
    return recipes


def build_evidence_graph(project_id: int, persist: bool = True) -> dict[str, Any]:
    project_root = storage.project_dir(project_id)
    references = _read_json(project_root / "references.json", [])
    if not isinstance(references, list):
        references = []
    merged_references: list[dict[str, Any]] = []
    seen_references: set[str] = set()
    for item in [*_parse_brief_references(project_root), *references]:
        if not isinstance(item, dict):
            continue
        key = (_clean(item.get("url")) or _clean(item.get("title"))).lower()
        if not key or key in seen_references:
            continue
        seen_references.add(key)
        merged_references.append(item)
    references = merged_references
    fact_registry = _read_json(project_root / "fact_registry.json", {})
    visual_manifest = _read_json(project_root / "visual_prompt_manifest.json", {})
    timeline = _read_json(project_root / "audio" / "scene_timeline.json", {})
    facts = fact_registry.get("facts") if isinstance(fact_registry, dict) else []
    facts = facts if isinstance(facts, list) else []
    scenes = visual_manifest.get("scenes") if isinstance(visual_manifest, dict) else []
    scenes = scenes if isinstance(scenes, list) else []
    timeline_scenes = timeline.get("scenes") if isinstance(timeline, dict) else []
    timeline_by_index = {
        int(item.get("index", 0) or 0): item
        for item in (timeline_scenes if isinstance(timeline_scenes, list) else [])
        if isinstance(item, dict)
    }

    source_nodes = []
    for index, item in enumerate(references):
        if not isinstance(item, dict):
            continue
        source_nodes.append(
            {
                "id": f"source-{index + 1}",
                "title": _clean(item.get("title")) or f"来源 {index + 1}",
                "url": _clean(item.get("url")),
                "provider": _clean(item.get("source")) or "unknown",
                "published_at": _clean(item.get("published_date")),
                "freshness_status": _clean(item.get("freshness_status")),
                "score": _number(item.get("score")),
                "snippet": _clean(item.get("snippet"))[:600],
            }
        )

    fact_nodes = []
    for index, item in enumerate(facts):
        if not isinstance(item, dict):
            continue
        fact_nodes.append(
            {
                "id": f"fact-{index + 1}",
                "claim": _clean(item.get("fact")),
                "status": _clean(item.get("status")),
                "sources": item.get("sources") if isinstance(item.get("sources"), list) else [],
                "usages": item.get("usages") if isinstance(item.get("usages"), list) else [],
            }
        )

    scene_nodes = []
    topic = _clean(visual_manifest.get("topic"))
    for item in scenes:
        if not isinstance(item, dict):
            continue
        prompt = _clean(item.get("prompt"))
        scene_index = int(item.get("index", 0) or 0)
        timeline_item = timeline_by_index.get(scene_index, {})
        narration = _clean(
            timeline_item.get("narration")
            or timeline_item.get("text")
            or timeline_item.get("spoken_text")
            or item.get("narration")
            or item.get("text")
            or item.get("audio_anchor")
            or prompt
        )
        linked_facts = [fact["claim"] for fact in fact_nodes if fact["claim"] and fact["claim"] in prompt]
        ranked_sources = sorted(
            (
                {
                    "source_id": source["id"],
                    "title": source["title"],
                    "provider": source["provider"],
                    "published_at": source["published_at"],
                    "url": source["url"],
                    "relevance": _source_relevance(source, narration, topic),
                }
                for source in source_nodes
                if _clean(source.get("url")).lower().startswith(("http://", "https://"))
            ),
            key=lambda source: source["relevance"],
            reverse=True,
        )
        linked_sources = [source for source in ranked_sources[:2] if source["relevance"] >= 0.15]
        scene_nodes.append(
            {
                "id": _clean(item.get("scene_id")) or f"scene-{int(item.get('index', 0) or 0):02d}",
                "index": scene_index,
                "target": _clean(item.get("target")),
                "quality_score": _number(item.get("quality_score")),
                "linked_facts": linked_facts,
                "linked_sources": linked_sources,
                "prompt_hash": _clean(item.get("prompt_hash")),
            }
        )

    graph = {
        "version": SCHEMA_VERSION,
        "project_id": project_id,
        "sources": source_nodes,
        "facts": fact_nodes,
        "scenes": scene_nodes,
        "coverage": {
            "source_count": len(source_nodes),
            "fact_count": len(fact_nodes),
            "verified_fact_count": sum(1 for item in fact_nodes if item.get("status") == "verified"),
            "unsupported_fact_count": sum(1 for item in fact_nodes if item.get("status") == "unsupported"),
            "scene_count": len(scene_nodes),
            "scenes_with_fact_links": sum(1 for item in scene_nodes if item.get("linked_facts")),
            "scenes_with_source_links": sum(1 for item in scene_nodes if item.get("linked_sources")),
        },
        "generated_at": _now(),
    }
    graph["fingerprint"] = _hash_payload({key: value for key, value in graph.items() if key != "generated_at"})
    if persist:
        _write_json(project_root / "evidence_graph.json", graph)
    return graph


def prepare_project_research_plan(project_id: int, topic_context: str = "") -> dict[str, Any]:
    project = storage.get_project(project_id)
    template_key = _clean(project.get("template"))
    template = storage.get_template(template_key)
    settings = storage.get_project_settings(project_id)
    topic = " ".join(
        item
        for item in (_clean(project.get("topic_name")), _clean(topic_context))
        if item
    )
    plan = research_routing_plan(topic, template, settings)
    _write_json(storage.project_dir(project_id) / "research_plan.json", plan)
    append_learning_event(
        "research_plan_prepared",
        project_id,
        {
            "providers": [item.get("provider") for item in plan.get("routes", [])],
            "current_news_mode": plan.get("current_news_mode"),
        },
    )
    return plan










def sync_production_intelligence(
    project_id: int,
    step: str,
    *,
    rebuild_dataset: bool = False,
) -> dict[str, Any]:
    """Keep the three reference-project capabilities inside the production chain."""
    project = storage.get_project(project_id)
    template_key = _clean(project.get("template"))
    recipe = build_channel_recipe(template_key, persist=True)
    root = storage.project_dir(project_id)
    research_path = root / "research_plan.json"
    research = _read_json(research_path, {})
    if not research or research.get("version") != RESEARCH_VERSION:
        research = prepare_project_research_plan(project_id, _clean(project.get("topic_name")))
    evidence = build_evidence_graph(project_id, persist=True)
    normalized_step = _clean(step)
    checkpoint = workflow_checkpoint_snapshot(project_id)
    learning = rebuild_training_dataset() if rebuild_dataset else _read_json(LEARNING_SUMMARY_FILE, {})
    payload = {
        "version": SCHEMA_VERSION,
        "project_id": project_id,
        "step": normalized_step,
        "recipe_fingerprint": recipe.get("fingerprint"),
        "research_fingerprint": research.get("fingerprint"),
        "evidence_fingerprint": evidence.get("fingerprint"),
        "checkpoint_completion": checkpoint.get("completion_ratio", 0),
        "updated_at": _now(),
    }
    _write_json(root / "production_intelligence.json", payload)
    append_learning_event("production_intelligence_synced", project_id, payload)
    return {
        "recipe": recipe,
        "research": research,
        "evidence": evidence,
        "checkpoint": checkpoint,
        "learning": learning,
        "status": payload,
    }


def workflow_checkpoint_snapshot(project_id: int) -> dict[str, Any]:
    root = storage.project_dir(project_id)
    manifest = _read_json(root / "production_manifest.json", {})
    lineage = _read_json(root / "production_lineage.json", {})
    auto_video = _read_json(root / "auto_video.json", {})
    files = {
        "content": root / "content.md",
        "voice": root / "audio" / "podcast.mp3",
        "subtitles": root / "subtitles.srt",
        "visual_manifest": root / "visual_prompt_manifest.json",
        "cover_landscape": root / "covers" / "cover_landscape.png",
        "final_video": root / "releases" / "final-video.mp4",
    }
    artifacts = {
        key: {
            "exists": path.exists(),
            "size": path.stat().st_size if path.exists() and path.is_file() else 0,
            "updated_at": path.stat().st_mtime if path.exists() else None,
        }
        for key, path in files.items()
    }
    completed = [key for key, value in artifacts.items() if value["exists"] and value["size"] > 0]
    missing = [key for key, value in artifacts.items() if not value["exists"] or value["size"] <= 0]
    return {
        "version": SCHEMA_VERSION,
        "project_id": project_id,
        "artifacts": artifacts,
        "completed": completed,
        "missing": missing,
        "completion_ratio": round(len(completed) / max(1, len(artifacts)), 3),
        "production_manifest": manifest,
        "production_lineage": lineage,
        "automation": {
            "status": auto_video.get("status") if isinstance(auto_video, dict) else "",
            "current_step": auto_video.get("current_step") if isinstance(auto_video, dict) else "",
            "updated_at": auto_video.get("updated_at") if isinstance(auto_video, dict) else None,
        },
        "generated_at": _now(),
    }


def append_learning_event(
    event_type: str,
    project_id: int | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    LEARNING_ROOT.mkdir(parents=True, exist_ok=True)
    project: dict[str, Any] = {}
    if project_id is not None:
        try:
            project = storage.get_project(project_id)
        except FileNotFoundError:
            project = {}
    event = {
        "version": DATASET_VERSION,
        "event_id": f"{int(_now() * 1000)}-{hashlib.sha1((_clean(event_type) + str(project_id)).encode()).hexdigest()[:8]}",
        "event_type": _clean(event_type),
        "project_id": project_id,
        "channel": _clean(project.get("template")),
        "topic": _clean(project.get("topic_name")),
        "payload": payload or {},
        "created_at": _now(),
    }
    with LEARNING_EVENTS_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
    return event


def _release_rows(project_id: int) -> Iterable[dict[str, Any]]:
    for release in storage.get_release_links(project_id):
        if not isinstance(release, dict):
            continue
        metrics = release.get("metrics") if isinstance(release.get("metrics"), dict) else {}
        if not metrics:
            continue
        yield {
            "release_id": release.get("id"),
            "platform": _clean(release.get("platform")),
            "created_at": release.get("created_at"),
            "metrics": {
                "impressions": int(_number(metrics.get("impressions"))),
                "views": int(_number(metrics.get("views"))),
                "click_through_rate": _number(metrics.get("click_through_rate")),
                "two_second_retention_rate": _number(metrics.get("two_second_retention_rate")),
                "five_second_retention_rate": _number(metrics.get("five_second_retention_rate")),
                "average_watch_seconds": _number(metrics.get("average_watch_seconds")),
                "completion_rate": _number(metrics.get("completion_rate")),
                "likes": int(_number(metrics.get("likes"))),
                "comments": int(_number(metrics.get("comments"))),
                "shares": int(_number(metrics.get("shares"))),
                "favorites": int(_number(metrics.get("favorites"))),
                "follows": int(_number(metrics.get("follows"))),
            },
        }


def _project_learning_record(project: dict[str, Any]) -> dict[str, Any]:
    project_id = int(project.get("id", 0) or 0)
    root = storage.project_dir(project_id)
    template = _project_template(project)
    content = _read_text(root / "content.md")
    content_strategy = _read_json(root / "content_strategy.json", {})
    visual_director = _read_json(root / "visual_director.json", {})
    visual_manifest = _read_json(root / "visual_prompt_manifest.json", {})
    opening_novelty = _read_json(root / "opening_novelty.json", {})
    evidence = build_evidence_graph(project_id, persist=True)
    checkpoint = workflow_checkpoint_snapshot(project_id)
    releases = list(_release_rows(project_id))
    scene_rows = visual_manifest.get("scenes") if isinstance(visual_manifest, dict) else []
    scene_rows = scene_rows if isinstance(scene_rows, list) else []
    scores = [_number(item.get("quality_score")) for item in scene_rows if isinstance(item, dict)]
    return {
        "version": DATASET_VERSION,
        "sample_type": "episode",
        "project_id": project_id,
        "channel": _clean(project.get("template")),
        "topic": _clean(project.get("topic_name")),
        "created_at": project.get("created_at"),
        "features": {
            "mode": _clean(project.get("template_mode")) or _clean(template.get("mode")),
            "content_type": _clean(project.get("content_type")),
            "content_chars": len(re.sub(r"\s+", "", content)),
            "target_audience": _clean(template.get("target_audience")),
            "cover_style": _clean(template.get("cover_style")),
            "scene_count": len(scene_rows),
            "average_scene_quality": round(sum(scores) / len(scores), 2) if scores else 0,
            "source_count": evidence["coverage"]["source_count"],
            "verified_fact_count": evidence["coverage"]["verified_fact_count"],
            "unsupported_fact_count": evidence["coverage"]["unsupported_fact_count"],
            "evidence_scene_coverage": round(
                evidence["coverage"]["scenes_with_fact_links"] / max(1, evidence["coverage"]["scene_count"]),
                3,
            ),
            "checkpoint_completion": checkpoint["completion_ratio"],
            "opening_novelty": opening_novelty,
            "content_strategy": content_strategy,
            "visual_director": visual_director,
        },
        "labels": {
            "releases": releases,
            "has_performance_metrics": bool(releases),
        },
        "lineage": {
            "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest()[:16] if content else "",
            "visual_manifest_hash": _hash_payload(visual_manifest) if visual_manifest else "",
            "evidence_graph_hash": evidence.get("fingerprint"),
        },
    }


def rebuild_training_dataset() -> dict[str, Any]:
    LEARNING_ROOT.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    channels: dict[str, int] = {}
    metric_count = 0
    for project in storage.list_projects():
        if not isinstance(project, dict) or not project.get("id"):
            continue
        try:
            record = _project_learning_record(project)
        except (FileNotFoundError, OSError, ValueError, TypeError):
            continue
        records.append(record)
        channel = record.get("channel") or "未分类"
        channels[channel] = channels.get(channel, 0) + 1
        if record["labels"]["has_performance_metrics"]:
            metric_count += 1
    with LEARNING_DATASET_FILE.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")

    event_count = 0
    if LEARNING_EVENTS_FILE.exists():
        with LEARNING_EVENTS_FILE.open("r", encoding="utf-8") as handle:
            event_count = sum(1 for line in handle if line.strip())
    visual_pair_count = 0
    if LEARNING_EVENTS_FILE.exists():
        with LEARNING_EVENTS_FILE.open("r", encoding="utf-8") as handle:
            visual_pair_count = sum(
                1
                for line in handle
                if '"event_type":"visual_candidate_selected"' in line
                or '"event_type":"cover_candidate_selected"' in line
            )

    sample_count = len(records)
    quality_baselines: dict[str, dict[str, Any]] = {}
    regression_alerts: list[dict[str, Any]] = []
    records_by_channel: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        records_by_channel.setdefault(_clean(record.get("channel")) or "未分类", []).append(record)
    for channel, channel_records in records_by_channel.items():
        scene_scores = [
            _number(item.get("features", {}).get("average_scene_quality"))
            for item in channel_records
            if _number(item.get("features", {}).get("average_scene_quality")) > 0
        ]
        evidence_scores = [
            _number(item.get("features", {}).get("evidence_scene_coverage"))
            for item in channel_records
        ]
        completion_scores = [
            _number(item.get("features", {}).get("checkpoint_completion"))
            for item in channel_records
        ]
        quality_baselines[channel] = {
            "sample_count": len(channel_records),
            "average_scene_quality": round(sum(scene_scores) / len(scene_scores), 2) if scene_scores else 0,
            "average_evidence_coverage": round(sum(evidence_scores) / max(1, len(evidence_scores)), 3),
            "average_checkpoint_completion": round(sum(completion_scores) / max(1, len(completion_scores)), 3),
        }
        ordered = sorted(channel_records, key=lambda item: _number(item.get("created_at")))
        if len(ordered) >= 4:
            recent = ordered[-2:]
            previous = ordered[:-2]
            recent_scene_scores = [
                _number(item.get("features", {}).get("average_scene_quality"))
                for item in recent
                if _number(item.get("features", {}).get("average_scene_quality")) > 0
            ]
            previous_scene_scores = [
                _number(item.get("features", {}).get("average_scene_quality"))
                for item in previous
                if _number(item.get("features", {}).get("average_scene_quality")) > 0
            ]
            if recent_scene_scores and previous_scene_scores:
                recent_average = sum(recent_scene_scores) / len(recent_scene_scores)
                previous_average = sum(previous_scene_scores) / len(previous_scene_scores)
                if recent_average + 6 < previous_average:
                    regression_alerts.append(
                        {
                            "channel": channel,
                            "metric": "average_scene_quality",
                            "previous": round(previous_average, 2),
                            "recent": round(recent_average, 2),
                            "message": "最近两期场景图质量明显低于频道历史基线",
                        }
                    )
    recommended_stage = "规则与配方学习"
    next_threshold = 20
    if sample_count >= 1000 and visual_pair_count >= 300:
        recommended_stage = "视觉偏好模型训练"
        next_threshold = 3000
    elif metric_count >= 200:
        recommended_stage = "统计排序模型训练"
        next_threshold = 1000
    elif metric_count >= 20:
        recommended_stage = "轻量排序与A/B实验"
        next_threshold = 200
    summary = {
        "version": DATASET_VERSION,
        "dataset_path": str(LEARNING_DATASET_FILE),
        "event_path": str(LEARNING_EVENTS_FILE),
        "sample_count": sample_count,
        "performance_sample_count": metric_count,
        "event_count": event_count,
        "visual_pair_count": visual_pair_count,
        "channels": channels,
        "quality_baselines": quality_baselines,
        "regression_alerts": regression_alerts,
        "recommended_stage": recommended_stage,
        "next_threshold": next_threshold,
        "targets": [
            {
                "name": "选题潜力排序",
                "ready": metric_count >= 20,
                "samples": metric_count,
                "minimum": 20,
            },
            {
                "name": "开场留存预测",
                "ready": metric_count >= 50,
                "samples": metric_count,
                "minimum": 50,
            },
            {
                "name": "图片偏好排序",
                "ready": visual_pair_count >= 100,
                "samples": visual_pair_count,
                "minimum": 100,
            },
            {
                "name": "成片表现预测",
                "ready": metric_count >= 200,
                "samples": metric_count,
                "minimum": 200,
            },
        ],
        "generated_at": _now(),
    }
    _write_json(LEARNING_SUMMARY_FILE, summary)
    return summary


def project_creative_intelligence(project_id: int, refresh: bool = False) -> dict[str, Any]:
    project = storage.get_project(project_id)
    template_key = _clean(project.get("template"))
    recipe_path = storage.TEMPLATES_ROOT / template_key / "recipe.json"
    recipe = _read_json(recipe_path, {})
    if refresh or not recipe or recipe.get("version") != RECIPE_VERSION:
        recipe = build_channel_recipe(template_key, persist=True)

    root = storage.project_dir(project_id)
    settings = storage.get_project_settings(project_id)
    evidence_path = root / "evidence_graph.json"
    evidence = _read_json(evidence_path, {})
    if refresh or not evidence or evidence.get("version") != SCHEMA_VERSION:
        evidence = build_evidence_graph(project_id, persist=True)

    research_path = root / "research_plan.json"
    research = _read_json(research_path, {})
    if refresh or not research or research.get("version") != RESEARCH_VERSION:
        research = research_routing_plan(
            _clean(project.get("topic_name")),
            storage.get_template(template_key),
            settings,
        )
        _write_json(research_path, research)

    summary = _read_json(LEARNING_SUMMARY_FILE, {})
    if refresh or not summary or summary.get("version") != DATASET_VERSION:
        summary = rebuild_training_dataset()

    checkpoint = workflow_checkpoint_snapshot(project_id)
    payload = {
        "version": SCHEMA_VERSION,
        "project": {
            "id": project_id,
            "topic": _clean(project.get("topic_name")),
            "channel": template_key,
        },
        "recipe": recipe,
        "research": research,
        "evidence": evidence,
        "checkpoint": checkpoint,
        "learning": summary,
        "generated_at": _now(),
    }
    _write_json(root / "creative_intelligence.json", payload)
    return payload
