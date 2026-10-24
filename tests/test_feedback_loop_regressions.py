import asyncio
from unittest.mock import AsyncMock, patch

from app import services


def test_content_runtime_binds_worker_to_persisted_brief():
    runtime = services.ContentRuntime()
    runtime._run = AsyncMock()
    persisted = "当前主题\n"

    async def exercise():
        with (
            patch.object(services.storage, "get_brief", return_value=persisted),
            patch.object(services.storage, "write_json"),
            patch.object(services.storage, "project_file"),
        ):
            state = await runtime.start(
                {"id": 7, "topic_name": "测试"},
                {"mode": "video"},
                "当前主题\n\n",
                "general",
            )
            await asyncio.sleep(0)
            return state

    state = asyncio.run(exercise())
    assert state["brief_hash"] == __import__("hashlib").sha256(persisted.encode("utf-8")).hexdigest()
    assert runtime._run.await_args.args[2] == persisted


def test_numeric_extractor_ignores_ordinals_and_physical_blocks():
    text = "第一次先看原图，第二次只处理一小块，AI在遮罩里重新画一块背景。"
    assert services.extract_numeric_fact_tokens(text) == []


def test_numeric_repair_keeps_hypothetical_operation_duration_natural():
    line = "【主播】你花30秒把照片里的路人抹掉。"
    repaired, hits = services.soften_unsupported_numeric_claim_line(line, ["30秒"])
    assert repaired == line
    assert hits == []
    assert "花短时间" not in repaired


def test_numeric_repair_rejects_broken_money_collocation():
    line = "【主播】AI在遮罩里重新画一块背景。"
    repaired, hits = services.soften_unsupported_numeric_claim_line(line, ["一块"])
    assert repaired == line
    assert hits == []
    assert "画不少钱" not in repaired


def test_sales_channel_words_do_not_become_topic_entity():
    profile = services.topic_entity_profile(
        "官网涨了 800，店里降了 1300",
        "一句话选题：苹果官网调价，同一款 iPhone 17 在线下授权店价格更低。",
    )

    assert profile["primary_entity"] in {"苹果", "iPhone", "iPhone 17"}
    assert profile["primary_entity"] not in {"官网", "店里", "渠道", "授权店"}


def test_researched_story_does_not_treat_brief_or_generated_summary_as_evidence():
    content = """# 苹果手机价格

## 原始材料简述
- 新机 9999 元起售，官网涨了 800 元。

## 口播脚本
【主播】新机 9999 元起售，官网涨了 800 元。
"""
    references = [{
        "title": "iPhone 17 官网涨价",
        "snippet": "苹果官网对 iPhone 17 调价，价格上涨 800 元。",
        "url": "https://example.com/apple-price",
        "source": "News",
    }]
    with patch.object(
        services.storage,
        "get_project",
        return_value={"id": 7, "template_mode": "video"},
    ):
        report = services.numeric_source_consistency_report(
            7,
            content,
            brief="用户希望写新机 9999 元起售。",
            references=references,
        )

    assert "800元" in report["verified_facts"]
    assert "9999元" in [item["fact"] for item in report["unsupported_facts"]]


def test_spoken_price_without_yuan_unit_still_requires_evidence():
    claims = services.strong_numeric_claims_in_line(
        "【主播】官网 6799，授权店报 5499；新机 9999 起售，电商挂出 9099。"
    )

    assert {item["normalized"] for item in claims} == {
        "6799元",
        "5499元",
        "9999元",
        "9099元",
    }


def test_unsupported_prices_are_blurred_as_a_natural_comparison():
    content = """# 价格对比

## 口播脚本
【主播】官网 6799，授权店报 5499，中间差 1300 元。
"""
    references = [{
        "title": "渠道价格变化",
        "snippet": "官网涨价 800 元，授权店报出 5499 元，和官网相差 1300 元。",
        "url": "https://example.com/price",
        "source": "News",
    }]
    with patch.object(
        services.storage,
        "get_project",
        return_value={"id": 7, "template_mode": "video"},
    ):
        blurred, hits = services.blur_unsupported_numeric_facts_text(
            7,
            content,
            brief="",
            references=references,
        )

    assert "官网和授权店出现明显价差" in blurred
    assert "6799" not in blurred
    assert "5499" not in blurred
    assert "1300" not in blurred
    assert hits


def test_traditional_numeric_units_verify_simplified_script_facts():
    content = """# 折叠屏备货

## 口播脚本
【主播】量产良率约30%到65%，三季度备货约50万到100万部，年底预计700万到800万部。
"""
    references = [{
        "title": "折叠屏供货预测",
        "snippet": "量產良率約30％至65％，第3季備貨量約50萬至100萬部，年底出貨量約700萬至800萬部。",
        "url": "https://example.com/supply",
        "source": "News",
    }]
    with patch.object(
        services.storage,
        "get_project",
        return_value={"id": 7, "template_mode": "video"},
    ):
        report = services.numeric_source_consistency_report(
            7,
            content,
            brief="",
            references=references,
        )
        blurred, hits = services.blur_unsupported_numeric_facts_text(
            7,
            content,
            brief="",
            references=references,
        )

    assert report["passed"] is True
    assert report["unsupported_facts"] == []
    assert blurred == content
    assert hits == []


def test_project_numeric_gate_repair_uses_sentence_blur(monkeypatch):
    content = """# 价格对比

## 口播脚本
【主播】官网 6799，授权店报 5499，中间差 1300 元。
"""
    references = [{
        "title": "渠道价格变化",
        "snippet": "官网涨价 800 元，授权店报出 5499 元，和官网相差 1300 元。",
        "url": "https://example.com/price",
        "source": "News",
    }]
    monkeypatch.setattr(services.storage, "get_content", lambda _pid: content)
    monkeypatch.setattr(services.storage, "get_brief", lambda _pid: "")
    monkeypatch.setattr(
        services.storage,
        "get_project",
        lambda _pid: {"id": 7, "template_mode": "video", "template": ""},
    )
    monkeypatch.setattr(services, "effective_project_references", lambda _pid, brief=None: references)
    monkeypatch.setattr(services, "save_project_content_bundle", lambda *_args, **_kwargs: {})

    result = services.repair_project_unsupported_numeric_facts(7)

    assert result["changed"] is True
    assert "官网和授权店出现明显价差" in result["content"]
    assert all(token not in result["content"] for token in ("6799", "5499", "1300"))
    assert result["ok"] is True
    assert any("模糊表述" in hit for hit in result["hits"])


def test_locked_topic_keeps_same_entity_source_with_shared_numeric_anchor():
    source = {
        "title": "苹果发布新机后 iPhone 17 也涨价，消费者需多花 1300 元",
        "snippet": "苹果客服回应，第三方渠道仍有自己的定价权。",
        "url": "https://example.com/apple-price",
        "source": "News",
    }
    profile = services.topic_research_query(
        "官网涨了 800，店里降了 1300",
        "一句话选题：苹果官网调价，线下授权店价格更低。",
    )[1]

    filtered = services.filter_references_for_locked_topic(
        [source],
        "官网涨了 800，店里降了 1300",
        limit=12,
        entity_profile=profile,
    )

    assert filtered
    assert filtered[0]["topic_score"] >= 2


def test_narrative_counts_do_not_enter_numeric_fact_gate():
    claims = services.strong_numeric_claims_in_line(
        '苹果客服的回应只有六个字；“定价权”这三个字要讲清；这两条路都成立。'
    )

    assert claims == []


def test_structural_clause_counts_do_not_enter_numeric_fact_gate():
    lines = (
        "报道只说，三条里得满足至少一条，申请才会被考虑。",
        "拿报道里的三条去对。",
        "不是三条全中，而是三条中至少一条。",
    )

    for line in lines:
        claims = services.strong_numeric_claims_in_line(line)
        assert not any(item.get("normalized") == "三条" for item in claims), line


def test_factual_item_count_still_enters_numeric_fact_gate():
    claims = services.strong_numeric_claims_in_line("文件新增了三条政策。")

    assert any(item.get("normalized") == "三条" for item in claims)


def test_explicit_user_brief_evidence_remains_authoritative_with_web_references(monkeypatch):
    brief = """一句话选题
一家公司在 15 天里变化明显，创业者称能规模化造本体的不超过 5 家。

制作批注
一、事实分级
✅ 可以直接说（多源可交叉）
⚠️ 不超过 5 家来自单一媒体标题，引用时必须保留限定词。
🚫 不能说行业只剩 3 家。
二、画面红线与版权提示
"""
    references = [{"title": "另一条有效报道", "snippet": "上市首日上涨 460%。", "url": "https://example.com/a"}]
    monkeypatch.setattr(services.storage, "get_project", lambda _project_id: {"template_mode": "video"})

    records = services.numeric_fact_authority_records(7, "", brief=brief, references=references)
    source_map = services.numeric_fact_source_map(records)

    assert "15天" in source_map
    assert "5家" in source_map
    assert "3家" not in source_map


def test_legacy_numeric_softening_artifacts_are_repaired_naturally():
    content = """## 口播脚本
涨到 这个价格，比之前贵了 800。
官网 256GB，从 5999 价格上调，涨 800。
是“定价权”这具体数字，到底落在谁手上。
网络购物这段时间内可以无理由退货。
这不少路都成立。

## 重点字幕
- 官网这个价格｜线下 5499
"""

    repaired, hits = services.repair_legacy_numeric_softening_artifacts_text(content)

    assert "价格上调，比之前贵了 800" in repaired
    assert "官网 256GB，原价 5999，之后价格上调，涨 800" in repaired
    assert '“定价权”这几个字' in repaired
    assert "网络购物通常可以无理由退货" in repaired
    assert "这些选择都成立" in repaired
    assert "官网价格上调｜线下 5499" in repaired
    assert hits


def test_channel_performance_experiment_does_not_override_topic_duration_budget():
    guidance = {
        "next_experiment": "60–100 秒单结论短片",
        "script_constraints": ["当前完播实验优先控制在 60–100 秒。"],
    }
    with patch("app.creative_learning.channel_production_guidance", return_value=guidance):
        profile = services.retention_duration_profile(
            {"id": 0, "template": "科技情报站", "template_mode": "video"},
            {"key": "科技情报站", "name": "科技情报站", "mode": "video"},
        )
    assert profile["experiment_active"] is False
    assert profile["minimum_sec"] < profile["target_sec"]
    assert profile["target_sec"] != 105
    assert profile["maximum_sec"] == 0
    assert profile["max_chars"] == 0


def test_viral_rules_treat_active_experiment_as_production_budget():
    profile = {
        "enabled": True,
        "experiment_active": True,
        "minimum_sec": 60,
        "target_sec": 80,
        "maximum_sec": 100,
        "information_beats": 4,
    }
    with (
        patch.object(services, "retention_duration_profile", return_value=profile),
        patch.object(services, "channel_profile_text", return_value="频道规则"),
        patch.object(services, "channel_learning_prompt_block", return_value="学习规则"),
    ):
        rules = services.build_viral_content_rules(
            {"template": "科技情报站"},
            {"key": "科技情报站", "name": "科技情报站", "mode": "video"},
        )
    assert "60–100 秒" in rules
    assert "不得以‘资料丰富’为由扩写成长解释文" in rules
    assert "这不是硬性时长上限" not in rules


def test_low_similarity_history_is_not_retrieved(monkeypatch):
    projects = [
        {"id": 1, "template": "科技情报站", "topic_name": "手机存储越用越小"},
    ]
    monkeypatch.setattr(services.storage, "list_projects", lambda: projects)
    monkeypatch.setattr(services.storage, "get_content", lambda _pid: "手机存储空间和预装软件说明")
    monkeypatch.setattr(services.storage, "get_summary", lambda _pid: {})
    monkeypatch.setattr(services, "overlap_score", lambda _tokens, _text: 0.086)
    refs = services.local_article_references(
        {"id": 120, "template": "科技情报站", "topic_name": "手机AI消除为什么越修越假"},
        {"key": "科技情报站"},
        "AI消除重复纹理和错误阴影",
    )
    assert refs == []


def test_video_structure_does_not_require_legacy_image_prompt_section():
    content = """# 主题

## Meta
- 钩子: 直接说结果

## 原始材料简述
已核实一条事实。

## 口播脚本
【主播】这是完整口播。

## 重点字幕
- 一条重点。

## 参考资料
- https://example.com/source
"""
    assert services.has_complete_production_content_structure(content, "video") is True


def test_passing_candidate_wins_over_higher_scored_warning():
    candidates = ["# pass", "# warning"]
    assessments = {
        "# pass": {"quality_passed": True, "rank_score": 70},
        "# warning": {"quality_passed": False, "rank_score": 95},
    }
    with (
        patch.object(services, "has_complete_production_content_structure", return_value=True),
        patch.object(services, "hollow_script_report", return_value={"hollow": False}),
        patch.object(services, "generated_content_quality_assessment", side_effect=lambda text, _mode: assessments[text]),
    ):
        selected = services.select_best_generated_content_candidate(candidates, "video")
    assert selected["content"] == "# pass"

def test_numeric_extractor_treats_block_classifier_as_physical_not_money():
    assert services.extract_numeric_fact_tokens("AI复制同一块纹理，再贴上一块补丁。") == []
    assert services.extract_numeric_fact_tokens("这个功能卖一块钱。") == ["一块"]


def test_semantic_section_label_is_not_kept_as_a_speaker():
    script = "【所以检查很简单】消除后先放大。\n【所以检查很简单】重要照片保留原图。"
    repaired, hits = services.rewrite_script_section_bad_phrases(script, "AI消除", "video")
    assert "所以检查很简单" not in repaired
    assert "【主播】消除后先放大。" in repaired
    assert "【主播】重要照片保留原图。" in repaired
    assert "结构标签归一为主播" in hits


def test_viewer_directive_label_is_not_kept_as_a_speaker():
    script = "【你放大看更明显】砖缝对不上。\n原因不复杂，它拿到的是照片。"
    repaired, hits = services.rewrite_script_section_bad_phrases(script, "AI消除", "video")
    assert "你放大看更明显" not in repaired
    assert "【主播】砖缝对不上。" in repaired
    manifest = services.build_spoken_script_manifest(
        f"# AI消除\n\n## 口播脚本\n{repaired}",
        "video",
        "AI消除",
    )
    assert {item["speaker"] for item in manifest["utterances"]} == {"主播"}
    assert "结构标签归一为主播" in hits


def test_language_pollution_gate_rejects_money_fragment_inside_image_action():
    content = """# AI消除

## Meta
- 时长: 60秒

## 口播脚本
【主播】地砖纹理很容易复制同不少钱，于是出现盖章感。
"""
    assessment = services.generated_content_quality_assessment(content, "video")
    assert assessment["quality_passed"] is False
    assert assessment["language_pollution"]
    assert "语义拼接污染" in assessment["warning"]
    assert services.script_language_pollution_hits("这个修图软件需要花不少钱购买。") == []


def test_meta_duration_is_inserted_when_model_omits_it():
    content = """# 主题

## Meta
- 钩子: 先说结果

## 口播脚本
【主播】这段口播用于计算实际时长。
"""
    updated, actions = services.synchronize_content_meta_duration(content, "video")
    chars, duration = services.estimate_spoken_duration_sec(updated, "video")
    assert f"- 时长: 约{int(round(duration))}秒（{chars}个有效中文字）" in updated
    assert actions == ["Meta时长同步实际口播"]


def test_canonicalizer_derives_meta_duration_and_real_title_from_script(monkeypatch):
    content = """# 一个模型自拟的夸张标题

## Meta
- 时长: 75秒（约430有效中文字）
- 钩子: 先说结果

## 口播脚本
【主播】这是一句用于核对实际时长的口播内容。
【主播】系统应该根据最终口播重新计算，而不是相信模型自报。
"""
    monkeypatch.setattr(services.storage, "get_project", lambda _pid: {
        "id": 121,
        "template": "科技情报站",
        "template_mode": "video",
        "topic_name": "手机AI消除为什么越修越假？",
    })
    monkeypatch.setattr(services.storage, "get_template", lambda _key: {"mode": "video"})
    monkeypatch.setattr(services, "opening_novelty_report", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(services, "repair_channel_opening_repetition", lambda _pid, text: {"content": text, "changed": False})
    monkeypatch.setattr(services, "numeric_source_consistency_report", lambda *_args, **_kwargs: {"passed": True, "unsupported_facts": []})
    monkeypatch.setattr(services, "build_episode_fact_registry", lambda *_args, **_kwargs: {})
    canonical = services.canonicalize_project_content(121, content, brief="", references=[])
    chars, duration = services.estimate_spoken_duration_sec(canonical["content"], "video")
    assert canonical["content"].startswith("# 手机AI消除为什么越修越假？")
    assert f"- 时长: 约{int(round(duration))}秒（{chars}个有效中文字）" in canonical["content"]
    assert "Meta时长同步实际口播" in canonical["actions"]

def test_spoken_manifest_coalesces_same_speaker_continuation_lines() -> None:
    content = """# 测试

## 口播脚本
【主播】这不是没修好
【主播】手机并不知道被挡住的背景，只能根据旁边的信息来猜。
【主播】影子最难。
【主播】光从哪儿来，它没法真的算出来
【主播】只能照着旁边的阴影补一块。

## 重点字幕
1. 它在根据旁边的信息猜

## 参考资料
- 示例资料
"""
    manifest = services.build_spoken_script_manifest(content, "video", "测试")
    texts = [item["text"] for item in manifest["utterances"]]
    assert texts == [
        "这不是没修好，手机并不知道被挡住的背景，只能根据旁边的信息来猜。",
        "影子最难。",
        "光从哪儿来，它没法真的算出来，只能照着旁边的阴影补一块。",
    ]


def test_tts_dialogue_coalescing_keeps_speaker_boundaries() -> None:
    result = services.coalesce_tts_dialogue_units([
        {"speaker": "主播A", "text": "先看结果"},
        {"speaker": "主播B", "text": "我来解释。"},
    ])
    assert result == [
        {"speaker": "主播A", "text": "先看结果"},
        {"speaker": "主播B", "text": "我来解释。"},
    ]



def test_compound_product_entity_rejects_unrelated_suffix_results():
    title = "小米SU9 LUX曝光：雷军的豪车梦"
    profile = services.topic_entity_profile(title, "小米申请SU9 LUX商标")
    assert profile["primary_entity"] == "SU9 LUX"
    assert not services.reference_matches_primary_entity(
        {"title": "Rosalía's LUX album", "snippet": "luxury news"}, profile)
    assert services.reference_matches_primary_entity(
        {"title": "小米 SU9 LUX 商标申请", "snippet": "车型信息"}, profile)


def test_stale_entity_match_metadata_does_not_resurrect_other_topic():
    title = "小米SU9 LUX曝光：雷军的豪车梦"
    profile = services.topic_entity_profile(title, "小米申请SU9 LUX商标")
    stale = {
        "title": "LUX album review", "snippet": "new music", "url": "https://example.org/music",
        "topic_score": 7, "entity_matched": True,
    }
    assert services.filter_references_for_locked_topic(
        [stale], title, limit=5, entity_profile=profile) == []
