from app import services


def test_provider_prompt_rewrites_risky_news_words_without_editing_source():
    source = "这场攻击击穿市场，新闻还提到诈骗团伙和暴跌风险。"
    report = services.image_prompt_provider_friendly_report(source)

    assert report["rewritten"] is True
    assert "攻击" not in report["prompt"]
    assert "击穿" not in report["prompt"]
    assert "诈骗" not in report["prompt"]
    assert "暴跌" not in report["prompt"]
    assert "网络安全风险" in report["prompt"]
    assert source == "这场攻击击穿市场，新闻还提到诈骗团伙和暴跌风险。"


def test_provider_prompt_keeps_normal_technology_language():
    prompt = "科技编辑桌面，芯片、服务器和价格曲线，清晰信息图风格。"
    result = services.make_image_prompt_provider_friendly(prompt)
    assert result == prompt
