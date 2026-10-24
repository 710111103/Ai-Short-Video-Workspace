from pathlib import Path
from app import services


def test_authoritative_scene_speech_ignores_cached_generic_prompt(monkeypatch, tmp_path):
    root = tmp_path / "148"
    scenes = root / "scenes"
    scenes.mkdir(parents=True)
    (root / "audio").mkdir()
    (root / "audio" / "scene_plan.json").write_text(
        '{"scenes":[{"index":5,"speech_text":"车企提前注册产品名称，未必量产。"}]}', encoding="utf-8"
    )
    path = scenes / ".s_05.gen-123.png"
    speech = services.authoritative_scene_speech_for_output(path)
    assert speech == "车企提前注册产品名称，未必量产。"
    generic = "情节锚点：一个主结论、两到四个当前口播事实"
    outbound = services.bind_scene_prompt_lineage(generic, "车企商标", speech)
    assert services.scene_prompt_matches_narration(outbound, speech, "")
    assert not services.scene_prompt_matches_narration(generic, speech, "")
