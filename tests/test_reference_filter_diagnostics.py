from app import services


def test_attribution_does_not_dominate_query():
    brief = "新浪科技、驱动之家与凤凰网科技10月23日独家获悉，在华为效力超过27年的彭博近日正式办理离职退休手续。"
    queries = services.evidence_search_queries(brief, "彭博 华为 退休")
    assert any("彭博" in q and "退休" in q for q in queries)
    assert all("新浪" not in q and "凤凰" not in q for q in queries)


def test_rejection_is_explained_without_exposing_url_secrets():
    refs = [{"title": "苹果发布产品", "snippet": "新产品", "url": "https://example.com/a?token=SECRET"}]
    rows = services.reference_filter_diagnostics(refs, [], "华为 彭博 退休", {"primary_entity": "彭博"})
    assert rows[0]["reason"] == "primary_entity_mismatch"
    assert "SECRET" not in str(rows)


def test_accepted_reference_is_not_reported_rejected():
    refs = [{"title": "华为彭博退休", "url": "https://example.com/a"}]
    assert services.reference_filter_diagnostics(refs, refs, "华为 彭博", {"primary_entity": "彭博"})[0]["reason"] == "retained"
