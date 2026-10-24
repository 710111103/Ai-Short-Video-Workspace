from unittest.mock import patch
from app import services


def test_production_checks_do_not_rewrite_script():
    assert not services.production_stage_gate_auto_fix_mode("", "content_gate")
    assert not services.production_stage_gate_auto_fix_mode("", "pre_video_gate")
    assert services.production_stage_gate_auto_fix_mode("fix", "content_gate")
    assert not services.production_stage_gate_auto_fix_mode("check", "visual_prompt_gate")


def test_passed_unchanged_gate_does_not_research_again():
    before = {"key": "content_gate", "passed": True, "score": 90,
              "status": "passed", "issues": [], "cache_hit": True}
    with patch.object(services, "cached_stage_gate_result", return_value=before), \
         patch.object(services, "refresh_content_gate_references", side_effect=AssertionError("duplicate research")), \
         patch.object(services, "save_stage_gate_result"):
        result = services.run_production_stage_gate(151, "content_gate", auto_fix=True)
    assert result["passed"]
    assert result["content_changed"] is False
    assert result["source_refresh"] == {}


def test_check_only_uses_review_without_source_refresh_or_rewrite():
    before = {"key": "content_gate", "passed": False, "score": 60, "issues": []}
    with patch.object(services, "authoritative_editorial_gate_result", return_value=before), \
         patch.object(services, "refresh_content_gate_references", side_effect=AssertionError("unexpected research")), \
         patch.object(services, "optimize_project_content", side_effect=AssertionError("unexpected rewrite")), \
         patch.object(services, "save_stage_gate_result"):
        result = services.run_production_stage_gate(151, "content_gate", auto_fix=False)
    assert not result["passed"]
    assert result["content_changed"] is False
