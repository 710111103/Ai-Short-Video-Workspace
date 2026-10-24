from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import os
import re
import shutil
import ssl
import sys
import traceback
import urllib.error
import urllib.request
import uuid
import warnings
from pathlib import Path
from typing import Any


APP_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = APP_ROOT.parent
EXTRACT_ROOT = WORKSPACE_ROOT / "AwesomeShortVideoMaker.exe_extracted"
PYZ_ROOT = EXTRACT_ROOT / "PYZ.pyz_extracted"
INTERNAL_ROOT = WORKSPACE_ROOT / "_analysis" / "awesome_app_install" / "_internal"
FFMPEG_BIN_ROOT = WORKSPACE_ROOT / "_analysis" / "awesome_app_install" / "ffmpeg" / "bin"
SOURCE_TEMPLATES = INTERNAL_ROOT / "模板文件"
TARGET_TEMPLATES = EXTRACT_ROOT / "模板文件"
PYDANTIC_CORE_SOURCE = INTERNAL_ROOT / "pydantic_core" / "_pydantic_core.cp311-win_amd64.pyd"
PYDANTIC_CORE_TARGET = PYZ_ROOT / "pydantic_core" / "_pydantic_core.cp311-win_amd64.pyd"
JITER_SOURCE = INTERNAL_ROOT / "jiter" / "jiter.cp311-win_amd64.pyd"
JITER_TARGET = PYZ_ROOT / "jiter" / "jiter.cp311-win_amd64.pyd"
CURRENT_DATA_ROOT = APP_ROOT / "data"
CURRENT_PROJECTS_ROOT = CURRENT_DATA_ROOT / "projects"
CURRENT_TEMPLATES_ROOT = CURRENT_DATA_ROOT / "templates"
ORIGINAL_PRODUCTS_MIRROR_ROOT = CURRENT_DATA_ROOT / "_original_runtime" / "products"
INVALID_PATH_CHARS_RE = re.compile(r'[<>:"/\\|?*]+')
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def ensure_original_assets() -> None:
    if SOURCE_TEMPLATES.exists() and not TARGET_TEMPLATES.exists():
        shutil.copytree(SOURCE_TEMPLATES, TARGET_TEMPLATES)
    if not PYZ_ROOT.exists():
        raise RuntimeError(f"Original runtime not found: {PYZ_ROOT}")
    if not INTERNAL_ROOT.exists():
        raise RuntimeError(f"Original dependency root not found: {INTERNAL_ROOT}")
    if PYDANTIC_CORE_SOURCE.exists() and not PYDANTIC_CORE_TARGET.exists():
        PYDANTIC_CORE_TARGET.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PYDANTIC_CORE_SOURCE, PYDANTIC_CORE_TARGET)
    if JITER_SOURCE.exists() and not JITER_TARGET.exists():
        JITER_TARGET.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(JITER_SOURCE, JITER_TARGET)


def apply_env(values: dict[str, str]) -> None:
    for key, value in values.items():
        if value is None:
            continue
        os.environ[str(key)] = str(value)
    if FFMPEG_BIN_ROOT.exists():
        path_parts = [str(FFMPEG_BIN_ROOT)]
        current_path = os.environ.get("PATH", "")
        if current_path:
            path_parts.append(current_path)
        os.environ["PATH"] = os.pathsep.join(path_parts)
    if not os.environ.get("VOLC_ASR_APP_KEY"):
        os.environ["VOLC_ASR_APP_KEY"] = os.environ.get("VOLC_TTS_APP_KEY", "")
    if not os.environ.get("VOLC_ASR_ACCESS_KEY"):
        os.environ["VOLC_ASR_ACCESS_KEY"] = os.environ.get("VOLC_TTS_ACCESS_KEY", "")


def bootstrap_imports() -> None:
    sys.path.insert(0, str(PYZ_ROOT))
    sys.path.insert(0, str(INTERNAL_ROOT))


def compact_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def safe_path_name(value: Any, default: str, max_length: int = 72) -> str:
    """Return a readable, collision-resistant Windows path component."""
    original = compact_text(value)
    cleaned = INVALID_PATH_CHARS_RE.sub("_", original)
    cleaned = re.sub(r"[\x00-\x1f]+", "_", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    if not cleaned:
        cleaned = compact_text(default) or "item"
    stem = cleaned.split(".", 1)[0].upper()
    changed = cleaned != original or len(cleaned) > max_length or stem in WINDOWS_RESERVED_NAMES
    if stem in WINDOWS_RESERVED_NAMES:
        cleaned = f"_{cleaned}"
    if changed:
        digest = hashlib.sha1(original.encode("utf-8")).hexdigest()[:10]
        room = max(8, max_length - len(digest) - 1)
        cleaned = f"{cleaned[:room].rstrip(' ._-')}_{digest}"
    return cleaned[:max_length].rstrip(" .") or "item"


def read_json_file(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def sync_current_projects_to_original_products(products_root: Path, template_key: str) -> None:
    template_name = safe_path_name(template_key, "template")
    template_root = products_root / template_name
    if template_root.exists():
        shutil.rmtree(template_root, ignore_errors=True)
    template_root.mkdir(parents=True, exist_ok=True)

    if not CURRENT_PROJECTS_ROOT.exists():
        return

    for project_dir in sorted(CURRENT_PROJECTS_ROOT.iterdir(), key=lambda item: item.name):
        if not project_dir.is_dir():
            continue
        meta = read_json_file(project_dir / "project.json", {})
        if not isinstance(meta, dict):
            continue
        if compact_text(meta.get("template")) != template_key:
            continue
        topic_name = compact_text(meta.get("topic_name"))
        if not topic_name:
            continue
        target_dir = template_root / safe_path_name(topic_name, project_dir.name)
        target_dir.mkdir(parents=True, exist_ok=True)
        for filename in ("brief.md", "content.md", "references.json", "summary.json"):
            source_path = project_dir / filename
            if source_path.exists():
                shutil.copy2(source_path, target_dir / filename)


def normalize_reference_item(item: Any) -> dict[str, Any] | None:
    if isinstance(item, dict):
        title = compact_text(item.get("title"))
        url = compact_text(item.get("url"))
        snippet = compact_text(item.get("snippet") or item.get("summary") or item.get("content"))
        source = compact_text(item.get("source") or item.get("site") or item.get("provider"))
    else:
        title = compact_text(getattr(item, "title", ""))
        url = compact_text(getattr(item, "url", ""))
        snippet = compact_text(getattr(item, "snippet", "") or getattr(item, "summary", ""))
        source = compact_text(getattr(item, "source", "") or getattr(item, "site", ""))
    if not (title or url or snippet):
        return None
    return {
        "title": title or url or "Reference",
        "url": url,
        "snippet": snippet,
        "source": source,
    }


def load_original_references(topic_dir: Path) -> list[dict[str, Any]]:
    raw = read_json_file(topic_dir / "references.json", [])
    if isinstance(raw, dict):
        for key in ("references", "items", "results"):
            value = raw.get(key)
            if isinstance(value, list):
                raw = value
                break
        else:
            raw = []
    if not isinstance(raw, list):
        return []
    refs: list[dict[str, Any]] = []
    for item in raw:
        normalized = normalize_reference_item(item)
        if normalized:
            refs.append(normalized)
    return refs


def optional_path(value: Any) -> Path | None:
    text = compact_text(value)
    return Path(text) if text else None


def optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def normalize_dialogue_payload(items: list[Any] | None) -> list[Any]:
    return list(items or [])


def split_text_at_natural_boundaries(text: str, max_chars: int) -> list[str]:
    """Split text below an API limit without changing the spoken wording."""
    remaining = text.strip()
    parts: list[str] = []
    while len(remaining) > max_chars:
        window = remaining[: max_chars + 1]
        boundaries = [
            match.end()
            for match in re.finditer(r"[。！？!?；;，,、：:]\s*", window)
            if match.end() >= max_chars // 2
        ]
        split_at = boundaries[-1] if boundaries else max_chars
        parts.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        parts.append(remaining)
    return parts


def split_single_voice_chunks(
    segments: list[str],
    max_utf8_bytes: int = 840,
    max_chars: int = 280,
) -> list[str]:
    """Create the fewest API-safe chunks while preserving the original wording."""
    prepared = [
        part
        for segment in segments
        if segment.strip()
        for part in split_text_at_natural_boundaries(segment, max_chars)
    ]
    total_bytes = len(" ".join(prepared).encode("utf-8"))
    desired_count = max(2, (total_bytes + max_utf8_bytes - 1) // max_utf8_bytes)
    chunks: list[str] = []
    current_parts: list[str] = []

    for index, segment in enumerate(prepared):
        remaining_chunks = max(1, desired_count - len(chunks))
        remaining_text = " ".join([*current_parts, *prepared[index:]])
        target_bytes = max(1, (len(remaining_text.encode("utf-8")) + remaining_chunks - 1) // remaining_chunks)
        candidate_parts = [*current_parts, segment]
        candidate = " ".join(candidate_parts)
        should_close = (
            bool(current_parts)
            and len(chunks) < desired_count - 1
            and (
                len(candidate.encode("utf-8")) > target_bytes
                or len(candidate.encode("utf-8")) > max_utf8_bytes
                or len(candidate) > max_chars
            )
        )
        if should_close:
            chunks.append(" ".join(current_parts))
            current_parts = [segment]
        else:
            current_parts = candidate_parts
    if current_parts:
        chunks.append(" ".join(current_parts))

    # The podcast action=3 endpoint emits no audio for a single nlp_text item.
    # Split one short chunk into two pieces without adding or repeating speech.
    if len(chunks) == 1 and chunks[0]:
        source = chunks[0]
        midpoint = len(source) // 2
        boundaries = [
            match.end()
            for match in re.finditer(r"[。！？!?；;，,、：:]\s*", source)
            if 0 < match.end() < len(source)
        ]
        split_at = min(boundaries, key=lambda value: abs(value - midpoint)) if boundaries else midpoint
        if split_at <= 0 or split_at >= len(source):
            split_at = max(1, min(len(source) - 1, midpoint))
        chunks = [source[:split_at].strip(), source[split_at:].strip()]

    # Keep a final hard guard even when a source utterance itself exceeded the
    # service limit. Volcengine documents at most 300 characters per round;
    # 280 leaves room for punctuation and future normalisation.
    return [
        part
        for chunk in chunks
        if chunk
        for part in split_text_at_natural_boundaries(chunk, max_chars)
    ]


def enforce_single_voice_request(
    dialogue_lines: list[Any],
    overrides_payload: dict[str, Any],
    env: dict[str, str] | None = None,
) -> tuple[list[Any], dict[str, Any], list[str]]:
    """Lock every podcast speaker slot and dialogue role to one narrator."""
    overrides = dict(overrides_payload or {})
    if compact_text(overrides.get("voice_mode")).lower() != "single":
        speakers = [
            compact_text(overrides.get("speaker_1")),
            compact_text(overrides.get("speaker_2")),
        ]
        return dialogue_lines, overrides, [item for item in speakers if item]

    runtime_env = env if isinstance(env, dict) else os.environ
    speaker = compact_text(overrides.get("speaker_1") or runtime_env.get("VOLC_TTS_SPEAKER_1"))
    if not speaker:
        raise RuntimeError("单人配音没有选择讲述人音色。")

    spoken_segments: list[str] = []
    for item in dialogue_lines:
        if isinstance(item, dict):
            text = compact_text(item.get("text") or item.get("content"))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            text = compact_text(item[1])
        else:
            text = compact_text(getattr(item, "text", ""))
        if text:
            if not re.search(r"[。！？!?；;…]$", text):
                text += "。"
            spoken_segments.append(text)

    # The podcast action=3 endpoint requires at least two nlp_text items and
    # rejects oversized items. Use the minimum number of API-safe chunks while
    # forcing every chunk to the same voice. The original runtime duplicates a
    # single voice into two speaker slots; the API now rejects that payload as
    # invalid, so run_tts collapses the final request to one speaker below.
    normalized = [
        {"speaker": "主播", "text": chunk}
        for chunk in split_single_voice_chunks(spoken_segments)
    ]

    overrides.update(
        {
            "voice_mode": "single",
            "speaker_1": speaker,
            "speaker_2": speaker,
            "random_order": False,
        }
    )
    runtime_env["VOLC_TTS_SPEAKER_1"] = speaker
    runtime_env["VOLC_TTS_SPEAKER_2"] = speaker
    runtime_env["VOLC_TTS_RANDOM_ORDER"] = "false"
    os.environ["VOLC_TTS_SPEAKER_1"] = speaker
    os.environ["VOLC_TTS_SPEAKER_2"] = speaker
    os.environ["VOLC_TTS_RANDOM_ORDER"] = "false"
    return normalized, overrides, [speaker]


def normalize_direct_script_request_params(
    params: dict[str, Any],
    speaker: str = "",
) -> dict[str, Any]:
    """Normalize a podcast action=3 payload to the official direct-script schema."""
    if not isinstance(params, dict):
        return params
    if int(params.get("action") or 0) != 3:
        return params

    # The official action=3 example accepts a prepared nlp_texts script and
    # does not contain speaker_info or model-writing controls. Older bundled
    # runtimes mixed fields from action=0 into this payload, which the current
    # service rejects as PodcastTTS invalid param.
    allowed = {
        "input_id",
        "action",
        "use_head_music",
        "use_tail_music",
        "audio_config",
        "nlp_texts",
    }
    params = {key: value for key, value in params.items() if key in allowed}
    nlp_texts = params.get("nlp_texts")
    if isinstance(nlp_texts, list):
        for item in nlp_texts:
            if isinstance(item, dict) and speaker:
                item["speaker"] = speaker
    return params


def collapse_single_voice_request_params(
    params: dict[str, Any],
    speaker: str,
    fallback_speaker: str = "",
) -> dict[str, Any]:
    """Backward-compatible wrapper used by focused tests and older callers."""
    return normalize_direct_script_request_params(params, speaker)


def single_voice_resource_id(speaker: str, env: dict[str, str] | None = None) -> str:
    runtime_env = env if isinstance(env, dict) else os.environ
    configured = compact_text(runtime_env.get("VOLC_TTS_SINGLE_RESOURCE_ID"))
    if configured:
        return configured
    normalized = compact_text(speaker).casefold()
    if "uranus" in normalized or "saturn" in normalized or "_v2_" in normalized:
        return "seed-tts-2.0"
    return "volc.service_type.10029"


def decode_tts_v3_stream(raw: bytes) -> tuple[bytes, dict[str, Any]]:
    source = raw.decode("utf-8-sig", errors="replace")
    decoder = json.JSONDecoder()
    cursor = 0
    audio_parts: list[bytes] = []
    final: dict[str, Any] = {}
    while cursor < len(source):
        while cursor < len(source) and source[cursor] in " \r\n\t":
            cursor += 1
        if cursor >= len(source):
            break
        if source.startswith("data:", cursor):
            cursor += len("data:")
            continue
        try:
            item, cursor = decoder.raw_decode(source, cursor)
        except json.JSONDecodeError as exc:
            preview = compact_text(source[cursor:cursor + 240])
            raise RuntimeError(f"豆包单人 TTS 返回无法解析：{preview}") from exc
        if not isinstance(item, dict):
            continue
        code = item.get("code")
        message = compact_text(item.get("message") or item.get("msg"))
        if code not in (None, 0, 20000000, "0", "20000000"):
            raise RuntimeError(f"豆包单人 TTS 失败（{code}）：{message or '未知错误'}")
        encoded = item.get("data")
        if isinstance(encoded, str) and encoded:
            try:
                audio_parts.append(base64.b64decode(encoded))
            except Exception as exc:
                raise RuntimeError("豆包单人 TTS 返回了损坏的音频分片。") from exc
        if str(code) == "20000000":
            final = item
    audio = b"".join(audio_parts)
    if not audio:
        message = compact_text(final.get("message")) if final else ""
        raise RuntimeError(f"豆包单人 TTS 没有返回音频数据。{message}")
    return audio, final


def generate_single_voice_v3(
    dialogue_lines: list[Any],
    output_path: Path,
    speaker: str,
    speech_rate: float,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    runtime_env = env if isinstance(env, dict) else os.environ
    app_id = compact_text(runtime_env.get("VOLC_TTS_APP_KEY"))
    access_key = compact_text(runtime_env.get("VOLC_TTS_ACCESS_KEY"))
    if not app_id or not access_key:
        raise RuntimeError("豆包单人 TTS 缺少 APP ID 或 Access Token。")

    spoken_segments: list[str] = []
    for item in dialogue_lines:
        if isinstance(item, dict):
            text = compact_text(item.get("text") or item.get("content"))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            text = compact_text(item[1])
        else:
            text = compact_text(getattr(item, "text", ""))
        if text:
            spoken_segments.append(text)
    chunks = split_single_voice_chunks(spoken_segments)
    if not chunks:
        raise RuntimeError("豆包单人 TTS 没有可合成的正文。")

    resource_id = single_voice_resource_id(speaker, runtime_env)
    endpoint = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
    audio_rounds: list[bytes] = []
    for index, chunk in enumerate(chunks, start=1):
        request_id = str(uuid.uuid4())
        body = json.dumps(
            {
                "user": {"uid": f"short-video-studio-{request_id}"},
                "req_params": {
                    "text": chunk,
                    "speaker": speaker,
                    "audio_params": {
                        "format": "mp3",
                        "sample_rate": 24000,
                        "speech_rate": int(round((max(0.8, min(speech_rate, 1.2)) - 1.0) * 100)),
                    },
                },
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = urllib.request.Request(
            endpoint,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Api-App-Id": app_id,
                "X-Api-Access-Key": access_key,
                "X-Api-Resource-Id": resource_id,
                "X-Api-Request-Id": request_id,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=180, context=ssl.create_default_context()) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = compact_text(exc.read().decode("utf-8", errors="replace"))
            if exc.code == 403 and "requested resource not granted" in detail.casefold():
                raise RuntimeError(
                    "当前豆包 AppID 未开通单人 TTS 资源 "
                    f"{resource_id}（音色 {speaker}）。双人播客资源不能代替单人 TTS，"
                    "否则会串入第二音色。请在火山引擎豆包语音控制台为当前 AppID "
                    "开通语音合成模型 2.0 后重试配音。"
                ) from exc
            raise RuntimeError(
                f"豆包单人 TTS HTTP {exc.code}（第 {index}/{len(chunks)} 段）：{detail or exc.reason}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"豆包单人 TTS 网络错误（第 {index}/{len(chunks)} 段）：{exc.reason}") from exc
        audio, _ = decode_tts_v3_stream(raw)
        audio_rounds.append(audio)

    output_path.write_bytes(b"".join(audio_rounds))
    return {
        "output_path": str(output_path),
        "size": output_path.stat().st_size,
        "round_count": len(audio_rounds),
        "resource_id": resource_id,
    }


def run_tts(payload: dict[str, Any]) -> dict[str, Any]:
    from video_maker import tts_doubao

    output_path = Path(payload["output_path"])
    if output_path.exists():
        output_path.unlink()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dialogue_lines = normalize_dialogue_payload(payload.get("dialogue_lines"))
    overrides = None
    overrides_payload = payload.get("overrides")
    effective_speakers: list[str] = []
    if isinstance(overrides_payload, dict) and hasattr(tts_doubao, "PodcastOverrides"):
        endpoint_fallback_speaker = compact_text(
            getattr(tts_doubao, "VOLC_TTS_SPEAKER_2", "")
            or os.environ.get("VOLC_TTS_SPEAKER_2")
        )
        dialogue_lines, overrides_payload, effective_speakers = enforce_single_voice_request(
            dialogue_lines,
            overrides_payload,
            os.environ,
        )
        allowed = {
            "voice_mode",
            "speaker_1",
            "speaker_2",
            "random_order",
            "action",
            "speech_rate",
        }
        kwargs = {key: overrides_payload.get(key) for key in allowed if key in overrides_payload}
        if "action" in kwargs and kwargs["action"] not in (None, ""):
            kwargs["action"] = int(kwargs["action"])
        if "speech_rate" in kwargs and kwargs["speech_rate"] not in (None, ""):
            kwargs["speech_rate"] = float(kwargs["speech_rate"])
        overrides = tts_doubao.PodcastOverrides(**kwargs)
    elif dialogue_lines and hasattr(tts_doubao, "PodcastOverrides"):
        # action=3 means "use the supplied dialogue script directly".
        # Without this, Doubao's podcast service may rewrite the script and add
        # generic intro/outro lines that are not present in content.md.
        overrides = tts_doubao.PodcastOverrides(action=3)
    single_speaker = effective_speakers[0] if len(effective_speakers) == 1 else ""
    original_param_builder = getattr(tts_doubao, "_build_request_params", None)
    original_websocket_connect = getattr(tts_doubao.websockets, "connect", None)

    if callable(original_websocket_connect):
        def official_podcast_connect(*args: Any, **kwargs: Any) -> Any:
            header_key = "additional_headers" if "additional_headers" in kwargs else "extra_headers"
            headers = dict(kwargs.get(header_key) or {})
            legacy_request_id = compact_text(headers.pop("X-Api-Connect-Id", ""))
            headers.setdefault("X-Api-Request-Id", legacy_request_id or str(uuid.uuid4()))
            kwargs[header_key] = headers
            return original_websocket_connect(*args, **kwargs)

        tts_doubao.websockets.connect = official_podcast_connect
    if callable(original_param_builder):
        # Every action=3 request must use the official direct-script schema.
        # In single mode all rounds are additionally pinned to one timbre.
        def direct_script_param_builder(*args: Any, **kwargs: Any) -> dict[str, Any]:
            params = original_param_builder(*args, **kwargs)
            return normalize_direct_script_request_params(params, single_speaker)

        tts_doubao._build_request_params = direct_script_param_builder
    try:
        with contextlib.redirect_stdout(sys.stderr):
            result = tts_doubao.generate_podcast(
                str(payload.get("text", "")),
                output_path,
                dialogue_lines=dialogue_lines,
                overrides=overrides,
            )
    finally:
        if callable(original_param_builder):
            tts_doubao._build_request_params = original_param_builder
        if callable(original_websocket_connect):
            tts_doubao.websockets.connect = original_websocket_connect
    return {
        "ok": True,
        "output_path": str(result),
        "size": result.stat().st_size if result.exists() else 0,
        "voice_mode": compact_text((overrides_payload or {}).get("voice_mode")),
        "effective_speakers": effective_speakers,
        "single_voice_enforced": compact_text((overrides_payload or {}).get("voice_mode")).lower() == "single",
        "single_round_enforced": (
            compact_text((overrides_payload or {}).get("voice_mode")).lower() == "single"
            and len(effective_speakers) == 1
        ),
        "single_timbre_enforced": (
            compact_text((overrides_payload or {}).get("voice_mode")).lower() == "single"
            and len(effective_speakers) == 1
        ),
        "single_voice_transport": "podcast",
        "single_voice_rounds": 1 if single_speaker else 0,
        "request_utterance_count": len(dialogue_lines),
        "request_dialogue_lines": [
            {
                "speaker": compact_text(item.get("speaker")) if isinstance(item, dict) else "",
                "text": compact_text(item.get("text") or item.get("content")) if isinstance(item, dict) else compact_text(item),
            }
            for item in dialogue_lines
        ],
    }


def run_asr(payload: dict[str, Any]) -> dict[str, Any]:
    from video_maker import asr_volcengine

    audio_path = Path(payload["audio_path"])
    srt_output = Path(payload["srt_output"])
    srt_output.parent.mkdir(parents=True, exist_ok=True)
    dialogue_lines = payload.get("dialogue_lines") or None
    with contextlib.redirect_stdout(sys.stderr):
        utterances, result_path = asr_volcengine.transcribe_to_srt(
            audio_path,
            srt_output,
            force=True,
            dialogue_lines=dialogue_lines,
        )
    return {
        "ok": True,
        "srt_output": str(result_path),
        "utterances": [
            {
                "start_ms": int(item.start_ms),
                "end_ms": int(item.end_ms),
                "text": str(item.text),
            }
            for item in utterances
        ],
    }


def run_scene_timeline(payload: dict[str, Any]) -> dict[str, Any]:
    from video_maker import scene_timeline

    audio_path = Path(payload["audio_path"])
    srt_path = Path(payload["srt_path"])
    output_path = Path(payload["output_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    scene_prompts = [str(item) for item in (payload.get("scene_prompts") or []) if str(item).strip()]
    if not scene_prompts:
        raise RuntimeError("scene_prompts 为空，无法调用原版 scene_timeline。")
    dialogue_lines = payload.get("dialogue_lines") or None
    cover_duration = float(payload.get("cover_duration", 10.0) or 10.0)
    outro_duration = float(payload.get("outro_duration", 0.0) or 0.0)
    align_mode = str(payload.get("align_mode", "full") or "full")
    force = bool(payload.get("force", True))
    with contextlib.redirect_stdout(sys.stderr):
        result_path = scene_timeline.build_scene_timeline(
            audio_path=audio_path,
            srt_path=srt_path,
            scene_prompts=scene_prompts,
            output_path=output_path,
            cover_duration=cover_duration,
            outro_duration=outro_duration,
            dialogue_lines=dialogue_lines,
            align_mode=align_mode,
            force=force,
        )
    timeline = json.loads(result_path.read_text(encoding="utf-8"))
    scenes = timeline.get("scenes") if isinstance(timeline, dict) else []
    return {
        "ok": True,
        "output_path": str(result_path),
        "scene_count": len(scenes) if isinstance(scenes, list) else 0,
        "timeline": timeline,
    }


def run_content(payload: dict[str, Any]) -> dict[str, Any]:
    from video_maker import config, generate_content, templates

    topic_name = compact_text(payload.get("topic_name"))
    brief = str(payload.get("brief") or "")
    template_key = compact_text(payload.get("template_key"))
    tavily_topic = compact_text(payload.get("tavily_topic")) or "general"
    prompt_path_raw = compact_text(payload.get("prompt_path"))
    prompt_path = Path(prompt_path_raw) if prompt_path_raw else None

    if not topic_name:
        raise RuntimeError("Missing topic_name for content generation.")
    if not template_key:
        raise RuntimeError("Missing template_key for content generation.")
    if not os.environ.get("DEEPSEEK_API_KEY"):
        raise RuntimeError("Missing DEEPSEEK_API_KEY for original content generation.")

    ORIGINAL_PRODUCTS_MIRROR_ROOT.mkdir(parents=True, exist_ok=True)
    sync_current_projects_to_original_products(ORIGINAL_PRODUCTS_MIRROR_ROOT, template_key)

    os.environ["DEFAULT_TEMPLATE"] = template_key
    os.environ["TAVILY_TOPIC"] = tavily_topic

    if CURRENT_TEMPLATES_ROOT.exists():
        templates.TEMPLATES_DIR = CURRENT_TEMPLATES_ROOT
        with contextlib.suppress(Exception):
            templates.reload_templates()

    with contextlib.suppress(Exception):
        config.reload_runtime_config()
    config.PRODUCTS_DIR = ORIGINAL_PRODUCTS_MIRROR_ROOT
    config.DEFAULT_PRODUCTS_DIR = ORIGINAL_PRODUCTS_MIRROR_ROOT
    with contextlib.suppress(Exception):
        config.PROJECT_ROOT = WORKSPACE_ROOT
    with contextlib.suppress(Exception):
        config._ACTIVE_TEMPLATE = templates.get_template(template_key)

    stages: list[str] = []

    def on_stage(stage: str) -> None:
        text = compact_text(stage)
        if text:
            stages.append(text)
            print(f"[content] {text}", file=sys.stderr)

    with contextlib.redirect_stdout(sys.stderr):
        # The extracted runtime uses topic_name as a directory name. Keep the
        # full title in brief/project metadata, but never pass unsafe user or
        # search text to Windows path construction.
        runtime_topic_name = safe_path_name(topic_name, "topic")
        result_path = generate_content.write_content_md(
            runtime_topic_name,
            brief,
            template_key=template_key,
            prompt_path=prompt_path,
            tavily_topic=tavily_topic,
            on_stage=on_stage,
        )

    topic_dir = result_path.parent
    return {
        "ok": True,
        "provider": "deepseek-via-original",
        "content_path": str(result_path),
        "topic_dir": str(topic_dir),
        "content": result_path.read_text(encoding="utf-8"),
        "references": load_original_references(topic_dir),
        "stages": stages,
    }


def run_video(payload: dict[str, Any]) -> dict[str, Any]:
    from video_maker import video_composer

    cover_path = Path(payload["cover_path"])
    scene_paths = [Path(str(item)) for item in (payload.get("scene_paths") or []) if compact_text(item)]
    audio_path = Path(payload["audio_path"])
    output_path = Path(payload["output_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    subtitle_path = optional_path(payload.get("subtitle_path"))
    scene_timeline_path = optional_path(payload.get("scene_timeline_path"))
    bgm_path = optional_path(payload.get("bgm_path"))
    highlights = [compact_text(item) for item in (payload.get("highlights") or []) if compact_text(item)] or None
    dialogue_texts = [compact_text(item) for item in (payload.get("dialogue_texts") or []) if compact_text(item)] or None
    scene_prompts = [compact_text(item) for item in (payload.get("scene_prompts") or []) if compact_text(item)] or None
    disclaimer = str(payload.get("disclaimer") or "")
    outro_duration = optional_float(payload.get("outro_duration"))
    bgm_volume = optional_float(payload.get("bgm_volume"))
    podcast_volume = optional_float(payload.get("podcast_volume"))
    brand_name = compact_text(payload.get("brand_name")) or None
    force = bool(payload.get("force", True))

    with contextlib.redirect_stdout(sys.stderr):
        result_path = video_composer.compose_video(
            cover_path=cover_path,
            scene_paths=scene_paths,
            audio_path=audio_path,
            output_path=output_path,
            highlights=highlights,
            disclaimer=disclaimer,
            outro_duration=outro_duration,
            dialogue_texts=dialogue_texts,
            scene_prompts=scene_prompts,
            subtitle_path=subtitle_path if subtitle_path and subtitle_path.exists() else None,
            scene_timeline_path=scene_timeline_path if scene_timeline_path and scene_timeline_path.exists() else None,
            bgm_path=bgm_path if bgm_path and bgm_path.exists() else None,
            bgm_volume=bgm_volume,
            podcast_volume=podcast_volume,
            brand_name=brand_name,
            force=force,
        )
    return {
        "ok": True,
        "output_path": str(result_path),
        "size": result_path.stat().st_size if result_path.exists() else 0,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(json.dumps({"ok": False, "error": "usage: bridge.py <tts|asr|scene_timeline|content|video> <payload.json>"}, ensure_ascii=False))
        return 2

    command = argv[1].strip().lower()
    payload_path = Path(argv[2])
    try:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        ensure_original_assets()
        apply_env({str(k): str(v) for k, v in (payload.get("env") or {}).items()})
        bootstrap_imports()
        warnings.simplefilter("ignore")
        if command == "tts":
            result = run_tts(payload)
        elif command == "asr":
            result = run_asr(payload)
        elif command == "scene_timeline":
            result = run_scene_timeline(payload)
        elif command == "content":
            result = run_content(payload)
        elif command == "video":
            result = run_video(payload)
        else:
            raise RuntimeError(f"unknown bridge command: {command}")
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        error = {
            "ok": False,
            "error": str(exc),
            "type": type(exc).__name__,
            "traceback": traceback.format_exc(limit=6),
        }
        print(json.dumps(error, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
