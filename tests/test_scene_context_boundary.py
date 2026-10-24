from app import services


def test_memory_contains_layout_not_previous_story():
    result = services.scene_layout_memory("选定视觉概念：主体：手机；景别：近景；构图：左右；冲突：收到涉黄短链")
    assert "近景" in result and "左右" in result
    assert "手机" not in result and "短链" not in result


def test_memory_without_layout_does_not_copy_story():
    assert services.scene_layout_memory("选定视觉概念：主体：产品；动作：开箱使用；冲突：另一个事件") == ""


def test_inherited_copy_requires_current_sentence():
    speech = "通常会把消息群发和自动回复权限接入管理系统统一调度"
    assert services.scene_local_copy_supported("自动回复", speech)
    assert not services.scene_local_copy_supported("成百上千个客户群", speech)


def test_brief_drops_other_scene_evidence_and_replaces_stale_headline():
    speech = "通常会把消息群发和自动回复权限接入管理系统统一调度"
    result = services.balanced_scene_generation_brief(
        "频道固定视觉签名：纸张线稿", topic="客服系统", speech=speech,
        concept="管理系统连接群发与自动回复模块",
        source_information={"supporting_evidence": ["不要点击恶意短链"],
                            "visual_copy": {"headline": "成百上千个客户群", "fact_chips": ["其他镜头事实"]}})
    assert "不要点击恶意短链" not in result
    assert "成百上千个客户群" not in result
    assert "其他镜头事实" not in result
    assert speech in result


def test_stale_unboxing_is_not_carried_to_system_scene():
    speech = "消息群发和自动回复权限接入管理系统统一调度"
    result = services.balanced_scene_generation_brief(
        "", speech=speech, concept="主体：产品本体；动作：开箱使用")
    assert "开箱使用" not in result
    assert speech in result


def test_mismatched_source_binding_drops_old_payload():
    result = services.balanced_scene_generation_brief(
        "", speech="自动回复权限接入管理系统", source_information={
            "bound_speech": "客户群收到异常链接",
            "supporting_evidence": ["自动回复权限出现旧事件"],
            "visual_copy": {"headline": "旧事件标题"}})
    assert "旧事件" not in result
