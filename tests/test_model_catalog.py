from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from app.model_catalog import _model_ids, fetch_compatible_models, models_endpoint


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_models_endpoint_preserves_v1_prefix():
    assert models_endpoint("http://127.0.0.1:8317/v1") == "http://127.0.0.1:8317/v1/models"


def test_models_endpoint_for_official_deepseek_url():
    assert models_endpoint("https://api.deepseek.com/") == "https://api.deepseek.com/models"


def test_parses_openai_data_ids_and_deduplicates():
    assert _model_ids({"data": [{"id": "deepseek-chat"}, {"id": "deepseek-chat"}, {"id": "deepseek-reasoner"}]}) == [
        "deepseek-chat",
        "deepseek-reasoner",
    ]


def test_parses_models_array_and_supported_fields():
    assert _model_ids({"models": ["model-c", {"name": "model-a"}, {"model": "model-b"}]}) == [
        "model-a",
        "model-b",
        "model-c",
    ]


def test_fetch_sends_bearer_key_and_returns_catalog():
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["authorization"] = request.get_header("Authorization")
        captured["timeout"] = timeout
        return FakeResponse({"data": [{"id": "deepseek-v4-flash-0731"}]})

    with patch("app.model_catalog.urllib.request.urlopen", side_effect=fake_urlopen):
        result = fetch_compatible_models("https://zero.cat/v1", "secret-key", timeout=7)

    assert captured == {
        "url": "https://zero.cat/v1/models",
        "authorization": "Bearer secret-key",
        "timeout": 7,
    }
    assert result["models"] == ["deepseek-v4-flash-0731"]
    assert result["count"] == 1


def test_empty_model_list_is_reported():
    with patch("app.model_catalog.urllib.request.urlopen", return_value=FakeResponse({"data": []})):
        with pytest.raises(RuntimeError, match="没有返回可选择的模型 ID"):
            fetch_compatible_models("https://api.deepseek.com", "secret-key")
