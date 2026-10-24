from __future__ import annotations

import re
from typing import Any, Sequence


AUDIENCE_VISUAL_POLICY_VERSION = "audience-first-visual-director-v2"

_NUMBER_RE = re.compile(
    r"(?P<prefix>超过|超|约|近|至少|不足|接近)?"
    r"(?P<value>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>%|％|倍|万|亿|元|秒|分钟|小时|天|部|个|GB|TB|W|V|A)?",
    flags=re.IGNORECASE,
)
_YEAR_RE = re.compile(r"(?P<year>20\d{2}年)(?P<context>还没过完|尚未过完|上半年|下半年|至今|截至目前)?")
_GENERIC_METRIC_LABELS = {
    "数据",
    "数量",
    "记录",
    "总量",
    "结果",
    "问题",
    "情况",
}


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _spoken(value: Any) -> str:
    text = _clean(value)
    text = re.sub(r"^[【\[]?(?:主播|旁白|画外音|角色[^】\]]*)[】\]]?\s*[:：]?\s*", "", text)
    text = re.sub(r"^[【\[]画面[】\]]\s*", "", text)
    return text.strip()


def _metric_label_after(text: str, match: re.Match[str]) -> str:
    tail = text[match.end() : match.end() + 24]
    tail = re.sub(r"^[多余左右上下约近超个条项次份台部名家例宗起]+", "", tail)
    candidates = (
        r"(?P<label>软件漏洞|安全漏洞|漏洞记录|聊天记录|攻击脚本|用户数据|个人信息)",
        r"(?P<label>[\u4e00-\u9fff]{2,8})(?:数量|记录|总量|订单|用户|设备|文件|病例|样本|漏洞)",
        r"(?P<label>[\u4e00-\u9fff]{2,8})",
    )
    for pattern in candidates:
        label_match = re.match(pattern, tail)
        if not label_match:
            continue
        label = _clean(label_match.group("label")).strip("的了已在和与，。！？")
        if label and label not in _GENERIC_METRIC_LABELS:
            return label
    return ""


def _metric_label_before(text: str, match: re.Match[str]) -> str:
    head = text[max(0, match.start() - 20) : match.start()]
    patterns = (
        r"(软件漏洞|安全漏洞|漏洞记录|聊天记录|攻击脚本|用户数据|个人信息)[^\u4e00-\u9fff]*$",
        r"([\u4e00-\u9fff]{2,8})(?:达到|已达|超过|接近|约|为|有)\s*$",
    )
    for pattern in patterns:
        label_match = re.search(pattern, head)
        if label_match:
            label = _clean(label_match.group(1)).strip("的了已在和与，。！？")
            if label and label not in _GENERIC_METRIC_LABELS:
                return label
    return ""


def extract_metric_items(narration: str) -> list[dict[str, str]]:
    spoken = _spoken(narration)
    items: list[dict[str, str]] = []
    for match in _NUMBER_RE.finditer(spoken):
        value = _clean(match.group("value"))
        unit = _clean(match.group("unit"))
        prefix = _clean(match.group("prefix"))
        if not value:
            continue
        if not unit and len(value) <= 1:
            continue
        if unit == "年" or (not unit and re.fullmatch(r"20\d{2}", value)):
            continue
        display_value = f"{value}{unit}"
        if prefix in {"超过", "超", "至少"} and unit in {"万", "亿", "%", "％", "倍"}:
            display_value += "+"
        label = _metric_label_after(spoken, match) or _metric_label_before(spoken, match)
        item = {
            "value": display_value,
            "raw_value": f"{prefix}{value}{unit}",
            "label": label,
        }
        if item not in items:
            items.append(item)
    return items[:4]


def _year_context(spoken: str) -> str:
    match = _YEAR_RE.search(spoken)
    if not match:
        return ""
    year = _clean(match.group("year"))
    context = _clean(match.group("context"))
    return f"{year}{context}" if context else year


def _benchmark_relation(spoken: str) -> str:
    patterns = (
        r"(?:已经|已)?(接近|逼近|达到|超过)(去年|上年|此前)[^，。！？]{0,8}(全年|同期|总量|总和)",
        r"(接近|逼近|达到|超过)[^，。！？]{0,10}(全年|同期|总量|总和)",
    )
    for pattern in patterns:
        match = re.search(pattern, spoken)
        if match:
            phrase = _clean(match.group(0)).strip("，。！？；： ")
            return phrase[:14]
    return ""


def _true_comparison(spoken: str, metrics: Sequence[dict[str, str]]) -> bool:
    if len(metrics) < 2:
        return False
    comparison_signal = bool(re.search(r"对比|相比|从.+到|分别|前者|后者|高于|低于|增长|下降|→", spoken))
    percentage_pair = sum(1 for item in metrics if re.search(r"%|％", item.get("value", ""))) >= 2
    return comparison_signal or percentage_pair


def _semantic_mode(spoken: str, metrics: Sequence[dict[str, str]], benchmark: str) -> str:
    if _true_comparison(spoken, metrics):
        return "true_comparison"
    if metrics and benchmark:
        return "benchmark_metric"
    if metrics:
        return "single_metric"
    if re.search(r"报告|文件|新闻|调查|研究|数据显示|官方|来源|公告|发布|搜索结果", spoken):
        return "evidence"
    if re.search(r"第一|第二|第三|步骤|打开|关闭|设置|检查|删除|操作", spoken):
        return "process"
    if re.search(r"不是|而是|真正|结论|别再|问题在于|你以为|其实", spoken):
        return "verdict"
    return "scene"


def _visual_role(mode: str, spoken: str, index: int) -> str:
    if int(index or 1) == 1:
        return "hook"
    if mode in {"true_comparison", "benchmark_metric", "single_metric", "evidence"}:
        return "evidence"
    if mode == "process":
        return "process"
    if mode == "verdict":
        return "verdict"
    return "context"


def _image_priority(role: str, mode: str) -> int:
    if role == "hook":
        return 100
    if role == "evidence":
        return 90 if mode in {"true_comparison", "benchmark_metric"} else 82
    if role == "verdict":
        return 78
    if role == "process":
        return 68
    return 42


def _primary_metric(metrics: Sequence[dict[str, str]]) -> dict[str, str]:
    if not metrics:
        return {}
    ranked = sorted(
        metrics,
        key=lambda item: (
            bool(item.get("label")),
            bool(re.search(r"万|亿|%|％|倍", item.get("value", ""))),
            len(item.get("value", "")),
        ),
        reverse=True,
    )
    return dict(ranked[0])


def _metric_kicker(label: str, mode: str) -> str:
    if mode == "true_comparison":
        return "数据对比"
    if label:
        compact = label[:6]
        if compact.endswith(("规模", "数量", "记录", "总量")):
            return compact
        return f"{compact}规模" if len(compact) <= 4 else compact
    return "关键数据"


def _audience_takeaway(
    context: str,
    metric: dict[str, str],
    relation: str,
    spoken: str,
) -> str:
    value = _clean(metric.get("value"))
    label = _clean(metric.get("label")) or "关键对象"
    if value:
        parts = [item for item in (context, f"{value}{label}", relation) if item]
        return "，".join(parts)
    clauses = [item.strip(" ，。！？；：") for item in re.split(r"[。！？；]+", spoken) if item.strip()]
    return min(clauses, key=lambda item: abs(len(item) - 18))[:36] if clauses else ""


def audience_visual_plan(
    *,
    topic: str,
    narration: str,
    evidence_facts: Sequence[str] = (),
    index: int = 1,
) -> dict[str, Any]:
    del evidence_facts  # Episode-wide facts must never leak into another scene.
    spoken = _spoken(narration)
    metrics = extract_metric_items(spoken)
    primary = _primary_metric(metrics)
    context = _year_context(spoken)
    benchmark = _benchmark_relation(spoken)
    mode = _semantic_mode(spoken, metrics, benchmark)
    role = _visual_role(mode, spoken, index)
    priority = _image_priority(role, mode)
    label = _clean(primary.get("label"))
    takeaway = _audience_takeaway(context, primary, benchmark, spoken)
    true_comparison = mode == "true_comparison"
    image_required = priority >= 65
    avoid_generic_emotion = not bool(re.search(r"哭|笑|害怕|焦虑|震惊|愤怒|崩溃|绝望|情绪", spoken))
    proof_target = (
        f"让“{label or '当前对象'}”在现实中的原生工作界面、记录载体或检测结果成为主体，并证明“{takeaway}”"
        if takeaway
        else "用当前口播中的真实对象、动作和结果证明观点"
    )
    banned = [
        "与当前事实无关的通用人物摆拍",
        "把数字抽象成与对象无关的纸堆、金币、方块或装饰物",
        "只用气氛、表情或空背景代替证据",
        "没有对象说明的孤立数字",
        "把单个年份和单个数值伪装成数据对比",
    ]
    if avoid_generic_emotion:
        banned.append("抱头、皱眉、摊手等通用焦虑人物")
    return {
        "version": AUDIENCE_VISUAL_POLICY_VERSION,
        "image_required": image_required,
        "visual_role": role,
        "image_priority": priority,
        "asset_strategy": (
            "generate_distinct_key_visual"
            if priority >= 78
            else ("generate_supporting_visual" if image_required else "reuse_or_hold_previous_visual")
        ),
        "mode": mode,
        "true_comparison": true_comparison,
        "topic": _clean(topic),
        "spoken": spoken,
        "audience_takeaway": takeaway,
        "audience_question": "观众在1秒内能否说出：对象是什么、发生了什么、哪条证据证明它",
        "primary_metric": primary,
        "metric_items": metrics,
        "context_label": context,
        "relation_label": benchmark,
        "kicker": _metric_kicker(label, mode),
        "proof_target": proof_target,
        "must_show": [
            item
            for item in (
                label or "",
                _clean(primary.get("value")),
                context,
                benchmark,
            )
            if item
        ],
        "banned_visuals": banned,
        "typography": {
            "hierarchy": ["对象/结论", "主数字", "时间条件", "关系结论"],
            "primary_value_weight": 800,
            "label_weight": 650,
            "context_weight": 500,
            "max_reading_layers": 4,
            "avoid_subject_overlap": True,
        },
        "motion": {
            "background": "static_hold",
            "sequence": [
                {"role": "context", "delay": 0.08, "duration": 0.24, "motion": "fade_rise"},
                {"role": "primary_metric", "delay": 0.28, "duration": 0.30, "motion": "fade_rise"},
                {"role": "relation", "delay": 0.58, "duration": 0.28, "motion": "line_reveal"},
            ],
            "settle_after_seconds": 0.9,
            "continuous_zoom": False,
        },
    }


def audience_prompt_block(plan: dict[str, Any]) -> str:
    if not isinstance(plan, dict):
        return ""
    must_show = "、".join(_clean(item) for item in plan.get("must_show", []) if _clean(item))
    banned = "、".join(_clean(item) for item in plan.get("banned_visuals", []) if _clean(item))
    lines = [
        f"观众1秒必须看懂：{_clean(plan.get('audience_takeaway'))}",
        f"证据画面：{_clean(plan.get('proof_target'))}",
        f"必须可对应：{must_show}" if must_show else "",
        f"排除：{banned}",
        "成图由模型一次完成真实对象、动作、证据关系与口播所需文字；文字自然融入画面，不追加模板黑框。",
    ]
    return "\n".join(item for item in lines if item)


def validate_audience_visual_plan(plan: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    mode = _clean(plan.get("mode"))
    metric = plan.get("primary_metric") if isinstance(plan.get("primary_metric"), dict) else {}
    if mode == "true_comparison" and not bool(plan.get("true_comparison")):
        issues.append("comparison_without_two_comparable_values")
    if mode in {"single_metric", "benchmark_metric"}:
        if not _clean(metric.get("value")):
            issues.append("metric_value_missing")
        if not _clean(metric.get("label")):
            issues.append("metric_subject_missing")
    if bool(plan.get("image_required")) and not _clean(plan.get("proof_target")):
        issues.append("visual_proof_missing")
    if not _clean(plan.get("audience_takeaway")):
        issues.append("audience_takeaway_missing")
    return issues


def _positive_visual_text(value: Any) -> str:
    """Keep affirmative concept clauses and drop negative-policy clauses.

    This prevents a prompt saying “禁止抱头人物” from being mistaken for a
    chosen “抱头人物” concept.
    """

    clauses = re.split(r"[\n。；]+", _clean(value))
    negative_markers = (
        "排除",
        "禁止",
        "不得",
        "不要",
        "避免",
        "不能",
        "拒绝",
        "负面",
        "不使用",
        "不出现",
    )
    return "。".join(
        clause for clause in clauses if clause and not any(marker in clause for marker in negative_markers)
    )


def audience_visual_failure_reasons(
    plan: dict[str, Any],
    *,
    visual_concept: str = "",
    audit_reasons: Sequence[str] = (),
) -> list[str]:
    """Return semantic failure codes that can drive a precise redraw.

    The output is intentionally code-like so UI, prompt repair and reports can
    all use the same diagnosis instead of maintaining separate rule sets.
    """

    issues = list(validate_audience_visual_plan(plan))
    positive = _positive_visual_text(visual_concept)
    spoken = _clean(plan.get("spoken"))
    mode = _clean(plan.get("mode"))
    generic_emotion = bool(re.search(r"抱头|摊手|耸肩|皱眉|捂脸|焦虑的人|震惊的人|崩溃的人", positive))
    native_evidence = bool(
        re.search(r"原生界面|工作界面|检测结果|检测报告|记录载体|日志|报告|公告|数据库|实测|账单|原始文件", positive)
    )
    if generic_emotion and not native_evidence:
        issues.append("generic_emotion_substitute")

    symbolic_props = (
        ("纸堆|文件堆|一摞纸", "纸|文件|报告|档案"),
        ("金币|金砖|钞票雨", "钱|金额|价格|成本|收入|利润|元|块"),
        ("盾牌|红叉|问号|悬浮芯片|全息脑图", "盾牌|红叉|问号|芯片|脑图"),
    )
    for visual_pattern, spoken_pattern in symbolic_props:
        if re.search(visual_pattern, positive) and not re.search(spoken_pattern, spoken):
            issues.append("irrelevant_symbolic_object")
            break

    if mode not in {"true_comparison", "benchmark_metric"} and re.search(r"左右对比|前后对比|VS|vs|对比柱", positive):
        issues.append("fake_comparison")

    motion = plan.get("motion") if isinstance(plan.get("motion"), dict) else {}
    sequence = motion.get("sequence") if isinstance(motion.get("sequence"), list) else []
    if bool(motion.get("continuous_zoom")) or len(sequence) > 4:
        issues.append("motion_too_busy")

    typography = plan.get("typography") if isinstance(plan.get("typography"), dict) else {}
    if typography and not bool(typography.get("avoid_subject_overlap", False)):
        issues.append("subject_overlap")

    normalized_audit = {_clean(item) for item in audit_reasons if _clean(item)}
    if {"ocr_semantic_mismatch", "ocr_fact_mismatch"} & normalized_audit:
        issues.append("speech_visual_mismatch")
    if "ocr_information_missing" in normalized_audit:
        issues.append("visual_proof_missing")
    if {"near_duplicate_scene", "exact_duplicate_scene"} & normalized_audit:
        issues.append("duplicate_visual_concept")

    return list(dict.fromkeys(issues))


def audience_visual_repair_actions(plan: dict[str, Any], issues: Sequence[str]) -> list[str]:
    metric = plan.get("primary_metric") if isinstance(plan.get("primary_metric"), dict) else {}
    label = _clean(metric.get("label")) or "当前对象"
    value = _clean(metric.get("value"))
    relation = _clean(plan.get("relation_label"))
    actions: list[str] = []
    mapping = {
        "metric_subject_missing": "从当前口播重新提取数值对应的具体对象，数字旁必须写清对象名称。",
        "metric_value_missing": "保留当前口播中的核心数值，禁止用抽象气氛代替。",
        "comparison_without_two_comparable_values": "取消双栏对比，只呈现一个真实指标及其时间或基准关系。",
        "fake_comparison": "取消伪造的左右两栏、箭头或柱状对比，改成单指标证据画面。",
        "generic_emotion_substitute": f"去掉抱头、皱眉等通用人物，用{label}的原生界面、记录或检测结果作为主体。",
        "irrelevant_symbolic_object": f"删除纸堆、金币、盾牌等借喻，只保留能直接证明{label}的真实对象。",
        "visual_proof_missing": f"补足能证明“{_clean(plan.get('audience_takeaway'))}”的原生记录、状态变化或检测结果。",
        "audience_takeaway_missing": "先重写本镜的一秒结论，再决定对象、证据和信息层级。",
        "speech_visual_mismatch": "清除其它镜头的文字和事实，只使用当前完整口播中的对象、数字和关系。",
        "subject_overlap": "重新测量主体占位，文字放入独立安全区，不遮挡脸、手、设备和证据。",
        "motion_too_busy": "背景保持静止，只让上下文、主数字和关系结论依次淡入并在0.9秒内稳定。",
        "duplicate_visual_concept": "保留当前事实，彻底更换证据载体、景别和主体摆位，不只换颜色或人物。",
    }
    for issue in issues:
        action = mapping.get(_clean(issue))
        if action and action not in actions:
            actions.append(action)
    if mode := _clean(plan.get("mode")):
        if mode == "benchmark_metric" and value:
            action = f"信息结构锁定为：时间条件 → {value}{label} → {relation or '当前口播中的基准关系'}。"
            if action not in actions:
                actions.append(action)
    return actions
