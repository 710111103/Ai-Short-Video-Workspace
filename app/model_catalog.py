from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


def models_endpoint(base_url: str) -> str:
    base = str(base_url or "").strip().rstrip("/")
    if not base:
        base = "https://api.deepseek.com"
    return f"{base}/models"


def _model_ids(payload: Any) -> list[str]:
    candidates: Any = []
    if isinstance(payload, dict):
        candidates = payload.get("data")
        if not isinstance(candidates, list):
            candidates = payload.get("models")
    elif isinstance(payload, list):
        candidates = payload
    if not isinstance(candidates, list):
        return []

    ids: list[str] = []
    for item in candidates:
        if isinstance(item, str):
            model_id = item.strip()
        elif isinstance(item, dict):
            model_id = str(item.get("id") or item.get("name") or item.get("model") or "").strip()
        else:
            model_id = ""
        if model_id and model_id not in ids:
            ids.append(model_id)
    return sorted(ids, key=lambda value: value.lower())


def fetch_compatible_models(base_url: str, api_key: str, timeout: float = 20.0) -> dict[str, Any]:
    endpoint = models_endpoint(base_url)
    headers = {"Accept": "application/json", "User-Agent": "ShortVideoStudio/1.0"}
    key = str(api_key or "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(endpoint, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            payload = json.loads(raw)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"模型接口返回 HTTP {exc.code}: {detail or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"连接模型接口失败: {exc.reason}") from exc
    except (TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"读取模型列表失败: {exc}") from exc

    models = _model_ids(payload)
    if not models:
        raise RuntimeError("模型接口响应成功，但没有返回可选择的模型 ID")
    return {"endpoint": endpoint, "models": models, "count": len(models)}
