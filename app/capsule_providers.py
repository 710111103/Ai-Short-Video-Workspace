"""Provider adapters adopted from Capsule Cinema's API contracts.

This module keeps network I/O behind a small, testable boundary.  It supports
official Volcengine Seedance image-to-video tasks plus Agnes image/video APIs.
Generated motion clips are always downloaded into the project and are treated
as silent visual assets by the final compositor.

Reference: https://github.com/JuneYaooo/capsule-cinema (Apache-2.0)
"""

from __future__ import annotations

import base64
import json
import mimetypes
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable


DEFAULT_ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_SEEDANCE_MODEL = "doubao-seedance-2-0-260128"
DEFAULT_AGNES_BASE_URL = "https://apihub.agnes-ai.com"
DEFAULT_AGNES_IMAGE_MODEL = "agnes-image-2.1-flash"
DEFAULT_AGNES_VIDEO_MODEL = "agnes-video-v2.0"


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _request_json(
    method: str,
    url: str,
    *,
    api_key: str,
    payload: dict[str, Any] | None = None,
    timeout: int = 300,
) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "short-video-studio/capsule-provider-v1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=max(1, int(timeout))) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:600]
        raise RuntimeError(f"API HTTP {exc.code}: {body}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"API 网络请求失败：{exc.__class__.__name__}") from exc
    try:
        result = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("API 返回内容不是有效 JSON") from exc
    if not isinstance(result, dict):
        raise RuntimeError("API 返回结构异常")
    return result


def _download(url: str, destination: Path, *, timeout: int = 600) -> Path:
    request = urllib.request.Request(url, headers={"User-Agent": "short-video-studio/capsule-provider-v1"})
    try:
        with urllib.request.urlopen(request, timeout=max(1, int(timeout))) as response:
            content = response.read()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"生成结果下载失败：{exc.__class__.__name__}") from exc
    if not content:
        raise RuntimeError("生成结果为空")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.downloading")
    temporary.write_bytes(content)
    temporary.replace(destination)
    return destination


def _data_url(path: Path) -> str:
    if not path.exists() or not path.is_file():
        raise RuntimeError(f"参考图片不存在：{path.name}")
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def _find_first(payload: Any, keys: tuple[str, ...]) -> str:
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, (str, int)) and str(value).strip():
                return str(value)
        for value in payload.values():
            found = _find_first(value, keys)
            if found:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = _find_first(value, keys)
            if found:
                return found
    return ""


def _find_media_url(payload: Any, suffixes: tuple[str, ...]) -> str:
    if isinstance(payload, dict):
        for key in ("video_url", "image_url", "output_url", "download_url", "url"):
            value = payload.get(key)
            if not isinstance(value, str) or not value.startswith(("https://", "http://")):
                continue
            path = urllib.parse.urlparse(value).path.lower()
            if key != "url" or not suffixes or path.endswith(suffixes):
                return value
        for value in payload.values():
            found = _find_media_url(value, suffixes)
            if found:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = _find_media_url(value, suffixes)
            if found:
                return found
    return ""


def build_seedance_i2v_payload(
    *,
    prompt: str,
    image_path: Path,
    model: str = DEFAULT_SEEDANCE_MODEL,
    ratio: str = "16:9",
    resolution: str = "720p",
    duration: int = 5,
) -> dict[str, Any]:
    prompt = _clean(prompt)
    if not prompt:
        raise RuntimeError("视频运动提示词为空")
    if ratio not in {"16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"}:
        raise RuntimeError(f"Seedance 不支持画幅 {ratio}")
    if resolution not in {"480p", "720p", "1080p", "4k"}:
        raise RuntimeError(f"Seedance 不支持分辨率 {resolution}")
    duration = max(4, min(int(duration), 15))
    return {
        "model": model or DEFAULT_SEEDANCE_MODEL,
        "content": [
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {"url": _data_url(image_path)},
                "role": "first_frame",
            },
        ],
        "resolution": resolution,
        "ratio": ratio,
        "duration": duration,
        "generate_audio": False,
        "watermark": False,
        "return_last_frame": False,
        "execution_expires_after": 172800,
        "priority": 0,
    }


def generate_seedance_i2v(
    *,
    prompt: str,
    image_path: Path,
    output_path: Path,
    api_key: str,
    model: str = DEFAULT_SEEDANCE_MODEL,
    base_url: str = DEFAULT_ARK_BASE_URL,
    ratio: str = "16:9",
    resolution: str = "720p",
    duration: int = 5,
    timeout: int = 1200,
    poll_interval: int = 8,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    if not _clean(api_key):
        raise RuntimeError("Seedance 视频 API Key 未配置")
    tasks_url = f"{base_url.rstrip('/')}/contents/generations/tasks"
    request_payload = build_seedance_i2v_payload(
        prompt=prompt,
        image_path=image_path,
        model=model,
        ratio=ratio,
        resolution=resolution,
        duration=duration,
    )
    created = _request_json("POST", tasks_url, api_key=api_key, payload=request_payload, timeout=min(timeout, 300))
    task_id = _find_first(created, ("id", "task_id"))
    video_url = _find_media_url(created, (".mp4", ".mov", ".webm"))
    started = time.monotonic()
    status = _find_first(created, ("status", "state")) or "submitted"
    while not video_url and task_id and time.monotonic() - started < timeout:
        elapsed = int(time.monotonic() - started)
        if progress:
            progress(f"Seedance 正在生成动态镜头，已等待 {elapsed} 秒")
        time.sleep(max(1, int(poll_interval)))
        result = _request_json("GET", f"{tasks_url}/{task_id}", api_key=api_key, timeout=90)
        status = _find_first(result, ("status", "state")) or status
        if status.lower() in {"failed", "error", "cancelled", "canceled", "expired", "rejected"}:
            message = _find_first(result, ("message", "error_message", "code"))
            raise RuntimeError(f"Seedance 任务状态 {status}{f'：{message}' if message else ''}")
        video_url = _find_media_url(result, (".mp4", ".mov", ".webm"))
    if not video_url:
        raise RuntimeError(f"Seedance 任务等待超时，最后状态 {status}")
    _download(video_url, output_path, timeout=min(max(timeout, 300), 1800))
    return {
        "provider": "volcengine_seedance",
        "model": model,
        "task_id": task_id,
        "output_path": str(output_path),
        "generation_type": "image_to_video",
        "duration": int(request_payload["duration"]),
        "ratio": ratio,
        "resolution": resolution,
    }


def build_agnes_i2v_payload(
    *,
    prompt: str,
    image_path: Path,
    model: str = DEFAULT_AGNES_VIDEO_MODEL,
    width: int = 1152,
    height: int = 648,
    num_frames: int = 121,
    frame_rate: int = 24,
    negative_prompt: str = "",
) -> dict[str, Any]:
    clean_prompt = _clean(prompt)
    if not clean_prompt:
        raise RuntimeError("Agnes 视频运动提示词为空")
    normalized_frames = int(num_frames)
    if normalized_frames < 1 or normalized_frames > 441 or (normalized_frames - 1) % 8 != 0:
        raise RuntimeError("Agnes 视频帧数必须小于等于 441，并满足 8n+1")
    payload: dict[str, Any] = {
        "model": model or DEFAULT_AGNES_VIDEO_MODEL,
        "prompt": clean_prompt,
        "image": _data_url(image_path),
        "width": int(width),
        "height": int(height),
        "num_frames": normalized_frames,
        "frame_rate": max(1, min(int(frame_rate), 60)),
    }
    if _clean(negative_prompt):
        payload["negative_prompt"] = _clean(negative_prompt)
    return payload


def generate_agnes_i2v(
    *,
    prompt: str,
    image_path: Path,
    output_path: Path,
    api_key: str,
    model: str = DEFAULT_AGNES_VIDEO_MODEL,
    base_url: str = DEFAULT_AGNES_BASE_URL,
    width: int = 1152,
    height: int = 648,
    num_frames: int = 121,
    frame_rate: int = 24,
    negative_prompt: str = "",
    timeout: int = 1200,
    poll_interval: int = 10,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    if not _clean(api_key):
        raise RuntimeError("Agnes 视频 API Key 未配置")
    tasks_url = f"{base_url.rstrip('/')}/v1/videos"
    request_payload = build_agnes_i2v_payload(
        prompt=prompt,
        image_path=image_path,
        model=model,
        width=width,
        height=height,
        num_frames=num_frames,
        frame_rate=frame_rate,
        negative_prompt=negative_prompt,
    )
    created = _request_json("POST", tasks_url, api_key=api_key, payload=request_payload, timeout=min(timeout, 300))
    task_id = _find_first(created, ("id", "task_id"))
    video_url = _find_media_url(created, (".mp4", ".mov", ".webm"))
    status = _find_first(created, ("status", "state")) or "submitted"
    started = time.monotonic()
    while not video_url and task_id and time.monotonic() - started < timeout:
        elapsed = int(time.monotonic() - started)
        if progress:
            progress(f"Agnes 正在生成动态镜头，已等待 {elapsed} 秒")
        time.sleep(max(1, int(poll_interval)))
        result = _request_json(
            "GET",
            f"{tasks_url}/{urllib.parse.quote(task_id)}",
            api_key=api_key,
            timeout=90,
        )
        status = _find_first(result, ("status", "state")) or status
        if status.lower() in {"failed", "error", "cancelled", "canceled", "expired", "rejected"}:
            message = _find_first(result, ("message", "error_message", "code"))
            raise RuntimeError(f"Agnes 任务状态 {status}{f'：{message}' if message else ''}")
        video_url = _find_media_url(result, (".mp4", ".mov", ".webm"))
    if not video_url:
        raise RuntimeError(f"Agnes 任务等待超时，最后状态 {status}")
    _download(video_url, output_path, timeout=min(max(timeout, 300), 1800))
    return {
        "provider": "agnes_video",
        "model": model,
        "task_id": task_id,
        "output_path": str(output_path),
        "generation_type": "image_to_video",
        "num_frames": int(request_payload["num_frames"]),
        "frame_rate": int(request_payload["frame_rate"]),
        "width": int(request_payload["width"]),
        "height": int(request_payload["height"]),
    }


def build_agnes_image_payload(
    *, prompt: str, model: str = DEFAULT_AGNES_IMAGE_MODEL, ratio: str = "16:9", size: str = "1K"
) -> dict[str, Any]:
    if ratio not in {"9:16", "16:9", "1:1"}:
        raise RuntimeError(f"Agnes 不支持图片画幅 {ratio}")
    normalized_size = size.upper()
    if normalized_size not in {"1K", "2K", "3K", "4K"}:
        raise RuntimeError(f"Agnes 不支持图片尺寸 {size}")
    return {
        "model": model or DEFAULT_AGNES_IMAGE_MODEL,
        "prompt": _clean(prompt),
        "size": normalized_size,
        "ratio": ratio,
        "extra_body": {"response_format": "url"},
    }


def generate_agnes_image(
    *,
    prompt: str,
    output_path: Path,
    api_key: str,
    model: str = DEFAULT_AGNES_IMAGE_MODEL,
    base_url: str = DEFAULT_AGNES_BASE_URL,
    ratio: str = "16:9",
    size: str = "1K",
    timeout: int = 600,
) -> dict[str, Any]:
    if not _clean(api_key):
        raise RuntimeError("Agnes 图片 API Key 未配置")
    payload = build_agnes_image_payload(prompt=prompt, model=model, ratio=ratio, size=size)
    result = _request_json(
        "POST",
        f"{base_url.rstrip('/')}/v1/images/generations",
        api_key=api_key,
        payload=payload,
        timeout=timeout,
    )
    encoded = _find_first(result, ("b64_json", "base64"))
    if encoded:
        try:
            content = base64.b64decode(encoded)
        except ValueError as exc:
            raise RuntimeError("Agnes 图片 Base64 返回损坏") from exc
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(content)
    else:
        image_url = _find_media_url(result, (".png", ".jpg", ".jpeg", ".webp"))
        if not image_url:
            raise RuntimeError("Agnes 响应中没有图片结果")
        _download(image_url, output_path, timeout=timeout)
    return {
        "provider": "agnes_image",
        "model": model,
        "output_path": str(output_path),
        "ratio": ratio,
        "size": size,
    }
