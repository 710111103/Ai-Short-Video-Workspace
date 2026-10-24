from app import services


def test_evidence_ledger_deduplicates_claims_and_keeps_source_identity():
    refs = [
        {
            "title": "同款电视官方售价上涨 800 元",
            "snippet": "同款电视官方售价上涨 800 元。授权店同期优惠 1300 元。",
            "source": "示例新闻",
            "url": "https://example.com/a",
        },
        {
            "title": "渠道价格出现变化",
            "snippet": "授权店同期优惠 1300 元。消费者应核对具体型号。",
            "source": "示例周刊",
            "url": "https://example.com/b",
        },
    ]
    ledger = services.build_evidence_ledger(refs)
    assert [item["id"] for item in ledger] == [f"F{i}" for i in range(1, len(ledger) + 1)]
    assert sum("授权店同期优惠 1300 元" in item["claim"] for item in ledger) == 1
    assert all(item["source_id"].startswith("S") for item in ledger)
    assert all(item["url"].startswith("https://") for item in ledger)


def test_narrative_blueprint_consumes_each_fact_once():
    ledger = [{"id": f"F{i}"} for i in range(1, 13)]
    blueprint = services.build_narrative_blueprint(ledger)
    consumed = [fact_id for slot in blueprint for fact_id in slot["fact_ids"]]
    assert len(consumed) == len(set(consumed))
    assert consumed == [f"F{i}" for i in range(1, 13)]
    assert [slot["slot"] for slot in blueprint] == [
        "hook", "what_happened", "why", "impact", "boundary", "takeaway"
    ]


def test_writing_contract_forbids_unassigned_precision_and_repetition():
    block = services.writing_contract_block([
        {
            "title": "产品价格下降 12%",
            "snippet": "报告发布于 2026 年。",
            "source": "报告",
            "url": "https://example.com/report",
        }
    ])
    assert '"evidence_ledger"' in block
    assert '"narrative_blueprint"' in block
    assert "每个 F 编号最多在正文完整使用一次" in block
    assert "没有 F 编号支持的精确事实不得补写" in block


def test_narrative_tension_rejects_flat_news_digest():
    content = """# 科技新闻

## 口播脚本
【主播】多家公司近日发布了一项新的合作声明。
【主播】声明介绍了参与企业和相关产品。
【主播】随后，多家媒体对此进行了报道。
【主播】行业也对这项消息给予了关注。
【主播】这项合作还在持续推进。
【主播】后续进展值得关注。
"""

    report = services.narrative_tension_report(content, "video")

    assert report["passed"] is False
    assert "flat_news_summary" in report["hard_failures"]
    assert report["signals"]["mechanism"] is False
    assert report["signals"]["audience_stake"] is False


def test_narrative_tension_rejects_polished_but_generic_news_summary():
    content = """# 科技新闻

## 口播脚本
【主播】近日，多家主流应用宣布限制豆包手机助手访问。
【主播】有关方面表示，这是出于安全和隐私考虑。
【主播】豆包手机助手也回应称将持续优化产品。
【主播】该事件引发了用户和行业关注。
【主播】未来各方还需要进一步沟通。
"""

    report = services.narrative_tension_report(content, "video")

    assert report["passed"] is False
    assert "flat_news_summary" in report["hard_failures"]
    assert report["signals"]["audience_stake"] is False
    assert report["signals"]["judgment"] is False


def test_narrative_tension_accepts_conflict_cost_mechanism_and_judgment():
    content = """# 155款App为什么拒绝同一个助手

## 口播脚本
【主播】155款主流App同时拒绝豆包助手，真正被争夺的是你手机上的操作权。
【主播】平台担心它绕过页面和广告直接替用户操作，助手则想把多个步骤压成一句话。
【主播】对普通用户来说，代价很现实：功能更省时间，但账号、隐私和售后责任可能变得更难判断。
【主播】因为双方依赖的规则不同，一边要守住应用内权限，另一边要获得跨应用执行能力。
【主播】这不代表所有自动化都危险，也不代表所有封禁都合理，关键要看权限是否透明、操作是否可撤销。
【主播】真正该判断的不是谁赢，而是谁能把操作权交还给用户。
"""

    report = services.narrative_tension_report(content, "video")

    assert report["passed"] is True
    assert report["hard_failures"] == []
    assert all(report["signals"].values())


def test_writing_contract_carries_current_topic_and_user_intent():
    block = services.writing_contract_block(
        [{"title": "155款App拒绝自动化助手", "snippet": "多家平台限制跨应用操作。"}],
        topic="手机助手遭到平台集体限制",
        brief="重点讲清平台和助手争夺的操作权，以及普通用户会受到什么影响。",
    )

    assert '"topic_label":"手机助手遭到平台集体限制"' in block
    assert "普通用户会受到什么影响" in block
    assert "explanation_model" in block
    assert "narrative_blueprint" in block


def test_transition_topic_uses_continuity_contract_without_consumer_pollution():
    topic = "华为27年老将彭博卸任：关键岗位如何交接"
    brief = "彭博办理退休，公开信息显示其长期负责全球采购认证管理。"
    model = services.classify_content_explanation_mode(topic, brief, [])
    strategy = services.content_strategy_report(
        {"topic_name": topic, "template_mode": "video", "template": "科技情报站"},
        {"mode": "video", "name": "科技情报站"},
        brief,
        references=[],
    )

    assert model["content_type"] == "transition"
    assert "业务连续性" in model["explanation_target"]
    assert "花出去的钱" not in str(strategy)
    assert "营销" not in str(strategy["audience_resonance_contract"])
    assert strategy["explanation_model"]["content_type"] == "transition"


def test_mechanism_completeness_requires_process_and_boundary():
    model = services.classify_content_explanation_mode(
        "认证机制如何运转",
        "重点解释触发条件、中间环节、结果和失效边界。",
        [],
    )
    incomplete = """# 测试

## 口播脚本
【主播】这套认证机制决定供应商能不能进入名单。
【主播】因为它会检查供应商，所以最后能够降低风险。
"""
    complete = """# 测试

## 口播脚本
【主播】这套认证机制决定供应商能不能进入名单。
【主播】当前提是企业提交资料和样品，审核才会被触发。
【主播】第一步核对资质，接着验证样品，再经过小批量测试。
【主播】测试结果形成准入或拒绝的结果，所以风险被提前拦住。
【主播】但样品通过不代表长期稳定，量产数据不足时仍不能推出可靠结论。
【主播】回到这次事件，真正检验的是记录和标准能否继续被执行。
"""

    assert services.explanation_completeness_report(incomplete, "video", model)["passed"] is False
    assert services.explanation_completeness_report(complete, "video", model)["passed"] is True
