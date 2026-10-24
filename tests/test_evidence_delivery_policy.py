from app import services


def test_brief_only_is_not_verified_and_has_no_minimum():
    result = services.evidence_delivery_policy([], "某公司负责人退休。")
    assert result["mode"] == "brief_only"
    assert not result["independently_verified"]
    assert result["minimum_words"] == 0


def test_title_only_reference_does_not_count_as_source_text():
    result = services.evidence_delivery_policy([{"title": "新闻", "url": "https://example.com"}], "")
    assert result["mode"] == "brief_only"


def test_source_text_is_not_automatically_verified():
    result = services.evidence_delivery_policy([{"snippet": "报道正文", "url": "https://example.com"}], "")
    assert result["mode"] == "source_backed"
    assert not result["independently_verified"]


def test_bypassed_review_cannot_override_weak_editorial_quality():
    result = services.editorial_delivery_verdict({"passed": True, "weighted_total": 0, "review_round": 0}, {"quality_passed": False})
    assert not result["quality_passed"]
    assert result["review_passed"]
    assert result["ai_score"] is None
    assert result["quality_status"] == "needs_review"


def test_both_checks_required():
    assert services.editorial_delivery_verdict({"passed": True}, {"quality_passed": True})["quality_passed"]
    assert not services.editorial_delivery_verdict({"passed": False}, {"quality_passed": True})["quality_passed"]


def test_brief_clauses_keep_their_subject():
    block = services.writing_contract_block([], brief="某公司负责人任职多年，近日退休。")
    assert "某公司负责人任职多年，近日退休" in block
    assert '"evidence_policy"' in block


def test_automatic_editor_receives_current_topic_material():
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(services.optimize_project_content))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == "compose_deepseek_rewrite_messages"]
    assert len(calls) == 1
    keywords = {k.arg: k.value for k in calls[0].keywords}
    assert isinstance(keywords["brief"], ast.Name) and keywords["brief"].id == "brief"
    assert "references" in keywords


def test_editor_prompt_has_evidence_delivery_policy():
    from unittest.mock import patch
    with patch.object(services, "channel_learning_prompt_block", return_value=""):
        messages = services.compose_deepseek_rewrite_messages({}, {}, "# 原稿", {}, brief="本期独有材料")
    combined = "\n".join(m["content"] for m in messages)
    assert "本期独有材料" in combined
    assert "brief_only" in combined
    assert "不用补资料清单替换口播" in combined
