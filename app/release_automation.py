from __future__ import annotations

import asyncio
import contextlib
import csv
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from . import services, storage


SOCIAL_AUTO_UPLOAD_PLATFORM_REGISTRY = [
    {
        "key": "douyin",
        "label": "抖音",
        "provider": "omnipost",
        "adapter": "sau_cli",
        "status": "ready",
        "capabilities": ["video", "note", "schedule", "login", "check", "content_stats", "metrics_backfill"],
        "note": "CLI/Skill 最完整，支持发布后自动回填作品链接与部分数据。",
    },
    {
        "key": "kuaishou",
        "label": "快手",
        "provider": "omnipost",
        "adapter": "sau_cli",
        "status": "ready",
        "capabilities": ["video", "note", "schedule", "login", "check", "content_stats"],
        "note": "支持视频/图文发布与账号作品数据同步；发布链接按作品 ID 或标题归因。",
    },
    {
        "key": "xiaohongshu",
        "label": "小红书",
        "provider": "omnipost",
        "adapter": "sau_cli",
        "status": "ready",
        "capabilities": ["video", "note", "schedule", "login", "check", "content_stats"],
        "note": "支持视频/图文发布与账号作品数据同步；发布链接按作品 ID 或标题归因。",
    },
    {
        "key": "bilibili",
        "label": "Bilibili",
        "provider": "omnipost",
        "adapter": "sau_cli",
        "status": "ready",
        "capabilities": ["video", "schedule", "login", "check", "content_stats"],
        "note": "通过 biliup 上传视频，支持账号作品数据同步；默认使用知识区分区 249。",
    },
    {
        "key": "tencent",
        "label": "视频号",
        "provider": "omnipost",
        "adapter": "sau_cli",
        "status": "ready",
        "capabilities": ["video", "schedule", "login", "check"],
        "note": "通过 OmniPost tencent uploader 上传视频；暂不自动回填作品链接。",
    },
    {
        "key": "baijiahao",
        "label": "百家号",
        "provider": "omnipost",
        "adapter": "omnipost_bridge",
        "status": "ready",
        "capabilities": ["video", "article", "schedule", "login"],
        "note": "通过 OmniPost 上传成片视频。",
    },
    {
        "key": "toutiao",
        "label": "今日头条",
        "provider": "omnipost",
        "adapter": "omnipost_bridge",
        "status": "ready",
        "capabilities": ["video", "article", "schedule", "login"],
        "note": "通过 OmniPost 上传成片视频。",
    },
    {
        "key": "sohu",
        "label": "搜狐号",
        "provider": "omnipost",
        "adapter": "omnipost_bridge",
        "status": "ready",
        "capabilities": ["article", "schedule", "login"],
        "note": "自动从项目口播稿提取正文并发布文章。",
    },
    {
        "key": "zhihu",
        "label": "知乎",
        "provider": "omnipost",
        "adapter": "omnipost_bridge",
        "status": "ready",
        "capabilities": ["article", "schedule", "login"],
        "note": "自动从项目口播稿提取正文并发布文章。",
    },
    {
        "key": "tiktok",
        "label": "TikTok",
        "provider": "omnipost",
        "adapter": "omnipost_bridge",
        "status": "ready",
        "capabilities": ["video", "schedule", "login"],
        "note": "通过 OmniPost 上传成片视频。",
    },
]
SOCIAL_AUTO_UPLOAD_PLATFORMS = SOCIAL_AUTO_UPLOAD_PLATFORM_REGISTRY
SOCIAL_AUTO_UPLOAD_STATE_NAME = "releases/social_auto_upload.json"
SOCIAL_AUTO_UPLOAD_DRAFT_NAME = "releases/social_auto_upload_draft.json"
SOCIAL_AUTO_UPLOAD_QUEUE_NAME = "release_queue.json"
SOCIAL_AUTO_UPLOAD_BINDINGS_NAME = "release_channel_accounts.json"
SOCIAL_AUTO_UPLOAD_ZIP_URL = "https://codeload.github.com/rehatRobot/omnipost/zip/refs/heads/main"
BROKEN_PATCHRIGHT_HOSTS = {
    "https://npmmirror.com/mirrors/playwright",
}
RELEASE_ACTION_TIMEOUT_SECONDS = {
    "check": 90,
    "login": 8 * 60,
    "publish": 20 * 60,
    "prepare": 10 * 60,
}
RELEASE_HEARTBEAT_INTERVAL_SECONDS = 5
RELEASE_STALE_GRACE_SECONDS = 90
RELEASE_ACTION_LABELS = {
    "check": "账号检测",
    "login": "账号登录",
    "publish": "视频发布",
    "prepare": "环境准备",
}


ANSI_ESCAPE_RE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
RELEASE_LOG_NOISE_PREFIXES = (
    "Traceback (most recent call last)",
    "During handling of the above exception",
    "The above exception was the direct cause",
)


def _release_log_error_detail(log_text: str) -> str:
    """Return the last useful platform/traceback error without flattening all logs."""
    text = ANSI_ESCAPE_RE.sub("", str(log_text or "")).replace("\r", "")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    preferred: list[str] = []
    fallback: list[str] = []
    for line in lines:
        if line.startswith(RELEASE_LOG_NOISE_PREFIXES):
            continue
        if line.startswith("[release] step ") or line.startswith("[release] publish payload"):
            continue
        if re.search(r"(?:RuntimeError|TimeoutError|ValueError|TypeError|AssertionError|PlaywrightTimeoutError|Error):", line):
            preferred.append(line)
            continue
        if re.search(r"(?:ERROR|失败|异常|超时|失效|验证码|风控|未找到|不可用|not found|timed out)", line, re.I):
            fallback.append(line)
    # Browser cleanup may print an unhandled TargetClosedError after the real
    # uploader exception. Prefer the uploader's explicit root-cause line so the
    # UI does not replace a DOM/navigation bug with a misleading close error.
    root_causes = [line for line in lines if "视频号发布流程失败:" in line]
    detail = (root_causes or preferred or fallback or [""])[-1]
    detail = re.sub(r"^(?:ERROR\s*[:：-]?|\[release\]\s*)", "", detail, flags=re.I).strip()
    return detail[-500:]


def _release_command_failure_message(action: str, platform: str, log_text: str, return_code: int) -> str:
    log_text = ANSI_ESCAPE_RE.sub("", str(log_text or ""))
    if platform == "douyin" and "账号检测未发现真实上传界面" in log_text:
        return "抖音发布页为空白或上传控件未加载，账号检测未通过。"
    if platform == "douyin" and (
        "发布页为空白或上传控件未加载" in log_text or "Locator.set_input_files" in log_text
    ):
        return "抖音发布页没有加载出上传控件，视频尚未上传。"
    if (
        "cookie文件不存在或已失效" in log_text
        or "cookie 已失效" in log_text
        or "cookie is missing or expired" in log_text.lower()
    ):
        return f"{_platform_label(platform)}账号登录已失效，请重新登录。"
    detail = _release_log_error_detail(log_text)
    if detail:
        return f"{RELEASE_ACTION_LABELS.get(action, '发布任务')}失败：{detail}"
    return f"{RELEASE_ACTION_LABELS.get(action, '发布任务')}执行失败（退出码 {return_code}，没有返回具体异常）。"


def _hidden_subprocess_kwargs() -> dict[str, int]:
    if os.name == "nt":
        return {"creationflags": int(getattr(subprocess, "CREATE_NO_WINDOW", 0))}
    return {}
LOCAL_CHROME_CANDIDATES = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
]
ACCOUNT_PROBE_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
)
AUTO_RELEASE_ENTRY_URLS = {
    "douyin": "https://creator.douyin.com/creator-micro/content/manage",
}
DOUYIN_WORK_LIST_ENDPOINT = "https://creator.douyin.com/janus/douyin/creator/pc/work_list"
DOUYIN_WORK_LIST_PARAMS = {
    "status": 0,
    "count": 20,
    "max_cursor": 0,
    "scene": "star_atlas",
    "device_platform": "android",
    "aid": 1128,
}


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def clean_multiline_text(value: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", str(line)).strip() for line in str(value or "").splitlines()]
    return "\n".join([line for line in lines if line]).strip()


def _looks_lost_text(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if re.search(r"[\u4e00-\u9fffA-Za-z0-9]", text):
        return False
    reduced = re.sub(r"[\s\?\uff1f\ufffd\.,，。!！:：;；、'\"“”‘’#\-_/|()\[\]{}<>]+", "", text)
    return reduced == ""


def _with_text_fallback(value: Any, fallback: Any, *, multiline: bool = False) -> str:
    normalizer = clean_multiline_text if multiline else clean_text
    cleaned = normalizer(str(value or ""))
    if cleaned and not _looks_lost_text(cleaned):
        return cleaned
    backup = normalizer(str(fallback or ""))
    return backup or cleaned


def _debug_text(value: Any, limit: int = 120) -> str:
    text = str(value or "")
    if len(text) > limit:
        text = text[:limit] + "..."
    return text.encode("unicode_escape", errors="backslashreplace").decode("ascii")


def runtime_env() -> dict[str, str]:
    env = dict(storage.DEFAULT_ENV)
    env.update(storage.parse_env())
    return env


def _normalized_patchright_host(value: str) -> str:
    host = clean_text(value).rstrip("/")
    if not host or host in BROKEN_PATCHRIGHT_HOSTS:
        return ""
    return host


def _detect_local_chrome() -> str:
    for candidate in LOCAL_CHROME_CANDIDATES:
        if candidate.exists():
            return str(candidate).replace("\\", "/")
    return ""


def workspace_root() -> Path:
    return storage.APP_ROOT.parent


def repo_candidates(env: dict[str, str] | None = None) -> list[Path]:
    env = env or runtime_env()
    configured = clean_text(env.get("SAU_REPO_PATH", ""))
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured))
    roots = [
        workspace_root(),
        workspace_root() / "_refs",
        workspace_root().parent,
        storage.APP_ROOT.parent,
    ]
    for root in roots:
        candidates.extend(
            [
                root / "omnipost",
                root / "omnipost-src",
                root / "_refs" / "omnipost",
                root / "_refs" / "omnipost-src",
                root / "social-auto-upload",
                root / "social-auto-upload-src",
                root / "_refs" / "social-auto-upload",
                root / "_refs" / "social-auto-upload-src",
            ]
        )
    deduped: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(path)
    return deduped


def detect_repo(env: dict[str, str] | None = None) -> tuple[Path, bool]:
    env = env or runtime_env()
    configured = clean_text(env.get("SAU_REPO_PATH", ""))
    if configured:
        return Path(configured), False
    for candidate in repo_candidates(env):
        if (candidate / "pyproject.toml").exists():
            return candidate, True
    return repo_candidates(env)[0], True


def _repo_cli_platforms(repo_path: Path) -> set[str]:
    script_path = repo_path / "sau_cli.py"
    if not script_path.exists():
        return set()
    try:
        text = script_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return set()
    platforms: set[str] = set()
    for item in SOCIAL_AUTO_UPLOAD_PLATFORM_REGISTRY:
        key = clean_text(str(item.get("key") or "")).lower()
        if key and re.search(rf'add_parser\(\s*["\']{re.escape(key)}["\']', text):
            platforms.add(key)
    return platforms


def release_platforms(env: dict[str, str] | None = None) -> list[dict[str, Any]]:
    env = env or runtime_env()
    repo_path, _ = detect_repo(env)
    repo_ready = repo_path.exists() and (repo_path / "pyproject.toml").exists()
    cli_platforms = _repo_cli_platforms(repo_path) if repo_ready else set()
    platforms: list[dict[str, Any]] = []
    for item in SOCIAL_AUTO_UPLOAD_PLATFORM_REGISTRY:
        entry = dict(item)
        key = clean_text(str(entry.get("key") or "")).lower()
        adapter = clean_text(str(entry.get("adapter") or ""))
        base_status = clean_text(str(entry.get("status") or "planned"))
        if adapter == "sau_cli":
            if not repo_ready:
                entry["status"] = "ready"
                entry["available"] = True
            elif key in cli_platforms:
                entry["status"] = "ready"
                entry["available"] = True
            else:
                entry["status"] = "needs_update"
                entry["available"] = False
                entry["note"] = "当前本地发布仓库没有这个平台的 CLI，请准备/更新 OmniPost 后再用。"
        elif adapter == "omnipost_bridge":
            module_dir = repo_path / "uploader" / f"{key}_uploader"
            if key == "tiktok":
                module_dir = repo_path / "uploader" / "tk_uploader"
            bridge_ready = (storage.APP_ROOT / "app" / "omnipost_bridge.py").exists()
            if repo_ready and module_dir.exists() and bridge_ready:
                entry["status"] = "ready"
                entry["available"] = True
            else:
                entry["status"] = "needs_update"
                entry["available"] = False
                entry["note"] = "当前 OmniPost 缺少这个平台的上传器，请先点击准备环境。"
        else:
            entry["status"] = base_status or "planned"
            entry["available"] = False
        platforms.append(entry)
    return platforms


def release_platform(platform: str, env: dict[str, str] | None = None) -> dict[str, Any] | None:
    normalized = clean_text(platform).lower()
    for item in release_platforms(env):
        if clean_text(str(item.get("key") or "")).lower() == normalized:
            return item
    return None


def probe(env: dict[str, str] | None = None) -> dict[str, Any]:
    env = env or runtime_env()
    repo_path, auto_detected = detect_repo(env)
    uv_bin = clean_text(env.get("SAU_UV_BIN", "")) or "uv"
    uv_available = bool(shutil.which(uv_bin) or Path(uv_bin).exists())
    repo_exists = repo_path.exists()
    pyproject_exists = (repo_path / "pyproject.toml").exists()
    script_exists = (repo_path / "sau_cli.py").exists()
    status = "unconfigured"
    message = "还没有找到 OmniPost 发布仓库；点击“准备环境”会自动下载并安装。"
    if repo_exists and pyproject_exists and uv_available:
        status = "success"
        message = "已找到 OmniPost/social-auto-upload 仓库与 uv，可以在投放页直接准备环境、登录和发布。"
    elif repo_exists and pyproject_exists and not uv_available:
        status = "error"
        message = "已找到仓库，但本机没有可用的 uv 命令。请先安装 uv 或在配置里填写 uv 的绝对路径。"
    elif repo_exists and not pyproject_exists and not script_exists:
        status = "error"
        message = "当前路径不是 social-auto-upload 仓库根目录，请重新填写到包含 pyproject.toml 的目录。"
    elif repo_exists and not pyproject_exists and script_exists:
        status = "warning"
        message = "仓库目录已找到，但缺少 pyproject.toml；建议更新为官方完整仓库后再使用。"
    elif clean_text(env.get("SAU_REPO_PATH", "")):
        status = "error"
        message = "配置中的发布仓库路径不存在；你可以改成正确路径，或清空后用“准备环境”自动下载。"
    return {
        "status": status,
        "message": message,
        "repo_path": str(repo_path),
        "repo_auto_detected": auto_detected,
        "repo_exists": repo_exists,
        "pyproject_exists": pyproject_exists,
        "script_exists": script_exists,
        "uv_bin": uv_bin,
        "uv_available": uv_available,
        "browser_mode": clean_text(env.get("SAU_BROWSER_MODE", "")) or "headless",
        "xhs_base_url": clean_text(env.get("SAU_XHS_CREATOR_BASE_URL", "")) or "https://creator.xiaohongshu.com",
        "patchright_download_host": _normalized_patchright_host(str(env.get("SAU_PATCHRIGHT_DOWNLOAD_HOST", ""))),
        "local_chrome_path": _detect_local_chrome(),
    }


def _release_description(project: dict[str, Any], template: dict[str, Any], strategy: dict[str, Any], summary: dict[str, Any]) -> str:
    """Build platform copy around the episode hook, payoff and discussion point.

    The publishing title is already rendered by every platform, so repeating it as
    the first description line wastes the strongest visible area. Prefer the
    episode-specific description authored in Meta; older projects are upgraded
    from their verified opening hook and core viewpoint.
    """
    topic = clean_text(project.get("topic_name") or "")
    publish_title = clean_text(summary.get("publish_title") or summary.get("video_title") or topic)
    authored = clean_multiline_text(str(summary.get("publish_description") or ""))

    insights = strategy.get("insights") if isinstance(strategy.get("insights"), dict) else {}
    opening_hook = clean_text(str(insights.get("opening_hook") or ""))
    core = clean_text(str(insights.get("core_viewpoint") or ""))
    interaction = clean_text(str(insights.get("interaction_hook") or ""))

    # Meta 中已经有当期发布描述时，它就是唯一文案来源。继续拼接早期
    # strategy insights 会把旧钩子/旧观点重新塞回描述，正是历史上“改了
    # 文案，发布时还是旧话术”的根因。只有旧项目缺少发布描述时才组合
    # opening/core/interaction。
    candidates = [*authored.splitlines()] if authored else [opening_hook, core, interaction]
    lines: list[str] = []
    fingerprints: list[str] = []
    title_fingerprint = re.sub(r"[^\w\u4e00-\u9fff]+", "", publish_title).lower()
    exact_title_prefix = re.compile(
        r"^\s*" + re.escape(publish_title) + r"(?:\s|[，,。；;：:！!？?—|·])*",
        flags=re.IGNORECASE,
    ) if publish_title else None
    for candidate in candidates:
        line = candidate.strip(" ，,。；;：:")
        if exact_title_prefix:
            previous = None
            while line and line != previous:
                previous = line
                line = exact_title_prefix.sub("", line, count=1).strip(" ，,。；;：:")
        if not line:
            continue
        fingerprint = re.sub(r"[^\w\u4e00-\u9fff]+", "", line).lower()
        if not fingerprint:
            continue
        if title_fingerprint and (fingerprint == title_fingerprint or fingerprint in title_fingerprint):
            continue
        if any(fingerprint == saved or fingerprint in saved or saved in fingerprint for saved in fingerprints):
            continue
        lines.append(line + ("" if line.endswith(("。", "！", "？", "!", "?")) else "。"))
        fingerprints.append(fingerprint)

    if not lines:
        fallback = topic or publish_title or clean_text(template.get("name") or template.get("key") or "短片工坊")
        lines = [f"{fallback}到底和普通人有什么关系？这期把事实、原因和实际影响一次讲清。"]
    return "\n\n".join(lines[:3]).strip()


def _release_tags_csv(raw: str) -> str:
    tokens = re.findall(r"#?([\u4e00-\u9fffA-Za-z0-9_]{2,})", raw or "")
    seen: set[str] = set()
    tags: list[str] = []
    for item in tokens:
        cleaned = clean_text(item).lstrip("#")
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        tags.append(cleaned)
    return ",".join(tags[:12])


def _english_release_tags_csv(raw: str, topic: str) -> str:
    configured = [
        item
        for item in _release_tags_csv(raw).split(",")
        if item and re.fullmatch(r"[A-Za-z0-9_]+", item)
    ]
    topic_words = [
        item.lower()
        for item in re.findall(r"\b[A-Za-z][A-Za-z0-9]{2,}\b", clean_text(topic))
        if item.lower() not in {"the", "and", "for", "with", "that", "this", "why", "how"}
    ]
    return ",".join(list(dict.fromkeys([*configured, *topic_words[:4], "shortvideo", "explainer"]))[:12])


def _file_info(project_id: int, relative_path: str) -> dict[str, Any] | None:
    path = storage.project_file(project_id, relative_path)
    if not path.exists() or not path.is_file():
        return None
    stat = path.stat()
    return {
        "relative_path": relative_path,
        "name": path.name,
        "size": stat.st_size,
        "modified_at": stat.st_mtime,
        "url": f"/data/projects/{project_id}/{relative_path}",
        "absolute_path": str(path.resolve()),
    }


def clear_login_qrcodes(platform: str, account_name: str, env: dict[str, str] | None = None) -> int:
    """Remove an expired login QR before starting a new platform login.

    QR files are only a transient UI hand-off.  Keeping a previous QR lets the
    UI present a code that no longer belongs to the current browser session.
    """
    env = env or runtime_env()
    repo_path, _ = detect_repo(env)
    cookie_dir = repo_path / "cookies"
    if not cookie_dir.exists():
        return 0
    normalized_platform = clean_text(platform).lower() or "douyin"
    normalized_alias = clean_text(account_name) or "default"
    removed = 0
    patterns = (
        f"{normalized_platform}_{normalized_alias}_login_qrcode_*.png",
        f"{normalized_platform}_{normalized_alias}_{normalized_platform}_login_qrcode_*.png",
    )
    for pattern in patterns:
        for path in cookie_dir.glob(pattern):
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
    return removed


def latest_login_qrcode(project_id: int, platform: str, account_name: str, env: dict[str, str] | None = None) -> dict[str, Any] | None:
    env = env or runtime_env()
    repo_path, _ = detect_repo(env)
    cookie_dir = repo_path / "cookies"
    if not cookie_dir.exists():
        return None
    normalized_platform = clean_text(platform).lower() or "douyin"
    normalized_alias = clean_text(account_name) or "default"
    patterns = [
        f"{normalized_platform}_{normalized_alias}_login_qrcode_*.png",
        f"{normalized_platform}_{normalized_alias}_{normalized_platform}_login_qrcode_*.png",
    ]
    candidates = sorted(
        {path for pattern in patterns for path in cookie_dir.glob(pattern)},
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return None
    path = candidates[0]
    stat = path.stat()
    return {
        "name": path.name,
        "absolute_path": str(path.resolve()),
        "modified_at": stat.st_mtime,
        "size": stat.st_size,
        "url": (
            f"/api/projects/{project_id}/release-automation/qrcode"
            f"?platform={normalized_platform}&account_name={normalized_alias}&v={int(stat.st_mtime * 1000)}"
        ),
    }


def _release_draft_defaults(project_id: int, task: dict[str, Any] | None = None) -> dict[str, Any]:
    project = storage.get_project(project_id)
    template_key = clean_text(project.get("template") or "")
    template = storage.get_template(template_key) if template_key else {}
    summary = storage.get_summary(project_id)
    strategy = storage.read_json(storage.project_file(project_id, "content_strategy.json"), {})
    status = probe()
    default_platform = clean_text(task.get("platform", "")) if task else ""
    default_alias = clean_text(task.get("account_name", "")) if task else ""
    resolved_platform = default_platform or "douyin"
    bound_alias = load_release_bindings().get(f"{template_key or 'default'}:{resolved_platform}", "")
    settings = storage.get_project_settings(project_id)
    english_output = str(settings.get("output_language") or project.get("output_language") or "").lower().startswith("en")
    release_tags = (
        _english_release_tags_csv(
            str(template.get("release_tags") or ""),
            str(summary.get("publish_title") or project.get("topic_name") or ""),
        )
        if english_output
        else _release_tags_csv(str(template.get("release_tags") or ""))
    )
    return {
        "platform": resolved_platform,
        "account_name": default_alias or bound_alias or "default",
        "title": clean_text(summary.get("publish_title") or summary.get("video_title") or project.get("topic_name") or ""),
        "description": _release_description(project, template, strategy if isinstance(strategy, dict) else {}, summary if isinstance(summary, dict) else {}),
        "tags": release_tags,
        "schedule": "",
        "headed": (status.get("browser_mode") == "headed"),
        "debug": False,
    }


def _platform_requires_headed(platform: str) -> bool:
    """Return whether a platform must run in a visible browser session."""
    return clean_text(platform).lower() == "xiaohongshu"


def _normalize_release_draft(payload: dict[str, Any] | None, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    base = dict(fallback or {})
    incoming = payload or {}
    platform = clean_text(str(incoming.get("platform", base.get("platform", "douyin")) or "")) or "douyin"
    requested_headed = bool(incoming.get("headed", base.get("headed", False)))
    return {
        "platform": platform,
        "account_name": clean_text(str(incoming.get("account_name", base.get("account_name", "default")) or "")) or "default",
        "title": _with_text_fallback(incoming.get("title", ""), base.get("title", "")),
        "description": _with_text_fallback(incoming.get("description", ""), base.get("description", ""), multiline=True),
        "tags": _with_text_fallback(incoming.get("tags", ""), base.get("tags", "")),
        "schedule": clean_text(str(incoming.get("schedule", base.get("schedule", "")) or "")),
        "headed": _platform_requires_headed(platform) or requested_headed,
        "debug": bool(incoming.get("debug", base.get("debug", False))),
    }


def load_draft(project_id: int, task: dict[str, Any] | None = None) -> dict[str, Any]:
    fallback = _release_draft_defaults(project_id, task)
    saved = storage.read_json(storage.project_file(project_id, SOCIAL_AUTO_UPLOAD_DRAFT_NAME), {})
    if not isinstance(saved, dict):
        saved = {}
    return _normalize_release_draft(saved, fallback)


def save_draft(project_id: int, payload: dict[str, Any] | None, task: dict[str, Any] | None = None) -> dict[str, Any]:
    current = load_draft(project_id, task)
    normalized = _normalize_release_draft(payload, current)
    storage.write_json(storage.project_file(project_id, SOCIAL_AUTO_UPLOAD_DRAFT_NAME), normalized)
    return normalized


def release_queue_path() -> Path:
    return storage.DATA_ROOT / SOCIAL_AUTO_UPLOAD_QUEUE_NAME


def release_bindings_path() -> Path:
    return storage.CONFIG_ROOT / SOCIAL_AUTO_UPLOAD_BINDINGS_NAME


def _release_stage_from_log(line: str) -> str:
    text = clean_text(str(line or ""))
    rules = (
        (("检查草稿箱", "草稿列表", "草稿箱没有同标题"), "检查草稿箱"),
        (("加载视频号发表页面", "赶往上传主页"), "打开发布页面"),
        (("搬运视频", "视频文件已交给上传页面", "等待视频上传"), "上传视频"),
        (("填写标题", "填写标题、简介和标签", "发布信息已填写"), "填写发布信息"),
        (("平台正在转码", "提取封面"), "等待平台转码"),
        (("先保存到草稿箱", "已点击保存草稿", "草稿已保存"), "保存草稿"),
        (("返回视频号内容管理页", "内容管理页刷新完成"), "刷新内容管理页"),
        (("进入草稿箱", "点击本次草稿", "打开编辑页"), "从草稿继续"),
        (("4:3 分享卡片",), "设置 4:3 封面"),
        (("3:4 个人主页卡片",), "设置 3:4 封面"),
        (("已点击发表", "等待平台确认"), "等待平台确认"),
        (("已发表列表核验", "平台已返回确认", "视频发布成功"), "验证发布结果"),
    )
    for markers, stage in rules:
        if any(marker in text for marker in markers):
            return stage
    return ""


def _reconcile_stale_release_jobs(
    payload: dict[str, Any],
    active_job_id: str = "",
    now: float | None = None,
) -> bool:
    """Close queue records whose worker disappeared instead of showing forever as running.

    Queue records are durable, while the subprocess is not.  A record in an active
    state is only considered stale when it has missed a full action timeout plus a
    short grace period and is not the job currently owned by this runtime.
    """
    changed = False
    current = float(now if now is not None else storage.now_ts())
    active_statuses = {
        "checking_account", "waiting_login", "publishing", "verifying", "retrying",
    }
    for job in payload.get("jobs", []):
        if str(job.get("id") or "") == str(active_job_id or ""):
            continue
        status = clean_text(str(job.get("status") or ""))
        if status not in active_statuses:
            continue
        platform = clean_text(str(job.get("platform") or "")).lower()
        action = "login" if status == "waiting_login" else "check" if status == "checking_account" else "publish"
        timeout = RELEASE_ACTION_TIMEOUT_SECONDS.get(action, 10 * 60)
        heartbeat = float(job.get("last_heartbeat_at") or job.get("updated_at") or job.get("created_at") or 0)
        if not heartbeat or current - heartbeat <= timeout + RELEASE_STALE_GRACE_SECONDS:
            continue
        job.update({
            "status": "failed",
            "stage": "后台执行已停止",
            "finished_at": current,
            "updated_at": current,
            "error": (
                f"发布任务超过 {timeout // 60} 分钟没有收到后台心跳，执行进程已结束；"
                "未将其标记为成功，请从当前步骤重试。"
            ),
            "stalled_reason": "worker_heartbeat_timeout",
            "stalled_at": current,
            "recoverable": True,
        })
        changed = True
    return changed


def load_release_queue() -> dict[str, Any]:
    payload = storage.read_json(release_queue_path(), {"jobs": []})
    if not isinstance(payload, dict):
        payload = {"jobs": []}
    jobs = payload.get("jobs")
    payload["jobs"] = jobs if isinstance(jobs, list) else []
    # Do not leave a durable "publishing" record forever after a crash.  The
    # runtime-specific active job is protected again by queue_snapshot().
    if _reconcile_stale_release_jobs(payload):
        save_release_queue(payload)
    return payload


def save_release_queue(payload: dict[str, Any]) -> None:
    storage.write_json(release_queue_path(), payload)


def load_release_bindings() -> dict[str, str]:
    payload = storage.read_json(release_bindings_path(), {})
    if not isinstance(payload, dict):
        return {}
    return {
        clean_text(str(key)): clean_text(str(value))
        for key, value in payload.items()
        if clean_text(str(key)) and clean_text(str(value))
    }


def bind_channel_account(project_id: int, platform: str, account_name: str) -> dict[str, str]:
    project = storage.get_project(project_id)
    channel = clean_text(str(project.get("template") or "default")) or "default"
    normalized_platform = clean_text(platform).lower() or "douyin"
    normalized_account = clean_text(account_name) or "default"
    binding_key = f"{channel}:{normalized_platform}"
    bindings = load_release_bindings()
    bindings[binding_key] = normalized_account
    storage.write_json(release_bindings_path(), bindings)
    profile = next(
        (item for item in list_account_profiles(normalized_platform) if item.get("alias") == normalized_account),
        {},
    )
    return {
        "channel": channel,
        "platform": normalized_platform,
        "account_name": normalized_account,
        "account_display_name": clean_text(str(profile.get("display_name") or "")),
        "binding_key": binding_key,
    }


def _release_artifact_identity(project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    video_path = storage.project_file(project_id, "releases/final-video.mp4")
    if not video_path.exists() or not video_path.is_file():
        return {"release_key": "", "file_sha256": "", "file_size": 0, "file_modified_at": 0.0}
    digest = hashlib.sha256()
    with video_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    stat = video_path.stat()
    file_sha256 = digest.hexdigest()
    material = "|".join((
        str(int(project_id)),
        clean_text(str(payload.get("platform") or "")).lower(),
        clean_text(str(payload.get("account_name") or "default")) or "default",
        clean_text(str(payload.get("title") or "")),
        file_sha256,
    ))
    return {
        "release_key": hashlib.sha256(material.encode("utf-8")).hexdigest(),
        "file_sha256": file_sha256,
        "file_size": int(stat.st_size),
        "file_modified_at": float(stat.st_mtime),
    }


def _same_successful_release(job: dict[str, Any], identity: dict[str, Any], title: str) -> bool:
    release_key = clean_text(str(identity.get("release_key") or ""))
    if not release_key or clean_text(str(job.get("status") or "")) != "succeeded":
        return False
    if clean_text(str(job.get("release_key") or "")) == release_key:
        return True
    # Older successful records predate release_key. Match their persisted source
    # file metadata once, then let enqueue migrate the record to the hash key.
    result = dict(job.get("result") or {})
    final_video = dict(result.get("final_video") or {})
    same_title = clean_text(str((job.get("payload") or {}).get("title") or "")) == clean_text(title)
    same_size = int(final_video.get("size") or 0) == int(identity.get("file_size") or -1)
    same_mtime = abs(float(final_video.get("modified_at") or 0) - float(identity.get("file_modified_at") or -1)) < 0.001
    return same_title and same_size and same_mtime


def enqueue_release_job_record(project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_release_draft(payload, _release_draft_defaults(project_id))
    binding = bind_channel_account(
        project_id,
        str(normalized.get("platform") or "douyin"),
        str(normalized.get("account_name") or "default"),
    )
    queue = load_release_queue()
    identity = _release_artifact_identity(project_id, normalized)
    active_statuses = {"waiting_assets", "waiting_schedule", "queued", "checking_account", "waiting_login", "publishing", "verifying", "retrying"}
    for existing in queue["jobs"]:
        same_target = (
            int(existing.get("project_id") or 0) == int(project_id)
            and clean_text(str(existing.get("platform") or "")) == binding["platform"]
            and clean_text(str(existing.get("account_name") or "default")) == binding["account_name"]
        )
        if same_target and _same_successful_release(existing, identity, str(normalized.get("title") or "")):
            existing.update({
                **identity,
                "stage": "已发布，复用成功记录",
                "deduplicated_at": storage.now_ts(),
                "updated_at": storage.now_ts(),
            })
            save_release_queue(queue)
            return existing
        if (
            int(existing.get("project_id") or 0) == int(project_id)
            and clean_text(str(existing.get("platform") or "")) == binding["platform"]
            and clean_text(str(existing.get("account_name") or "default")) == binding["account_name"]
            and clean_text(str(existing.get("status") or "")) in active_statuses
        ):
            if existing.get("status") in {"waiting_assets", "waiting_schedule", "queued"}:
                wait_state = _release_job_wait_state(project_id, normalized)
                existing.update(
                    {
                        "project_title": clean_text(str(storage.get_project(project_id).get("topic_name") or "")),
                        "channel": binding["channel"],
                        "account_name": binding["account_name"],
                        "account_display_name": binding["account_display_name"],
                        "payload": normalized,
                        "status": wait_state["status"],
                        "stage": wait_state["stage"],
                        "waiting_reason": wait_state["waiting_reason"],
                        "next_check_at": wait_state["next_check_at"],
                        "updated_at": storage.now_ts(),
                    }
                )
                save_release_queue(queue)
            return existing
    now = storage.now_ts()
    wait_state = _release_job_wait_state(project_id, normalized)
    job = {
        "id": uuid.uuid4().hex,
        "project_id": int(project_id),
        "project_title": clean_text(str(storage.get_project(project_id).get("topic_name") or "")),
        "channel": binding["channel"],
        "platform": binding["platform"],
        "account_name": binding["account_name"],
        "account_display_name": binding["account_display_name"],
        "payload": normalized,
        "status": wait_state["status"],
        "stage": wait_state["stage"],
        "waiting_reason": wait_state["waiting_reason"],
        "next_check_at": wait_state["next_check_at"],
        "attempts": 0,
        "max_attempts": 2,
        "created_at": now,
        "updated_at": now,
        "started_at": None,
        "finished_at": None,
        "last_heartbeat_at": now,
        "last_action_detail": "等待队列执行",
        "error": "",
        "result": {},
        **identity,
        "last_action": "",
        "command": "",
        "cwd": "",
        "log": "",
        "attempt_history": [],
    }
    queue["jobs"].append(job)
    save_release_queue(queue)
    return job


def update_release_queue_job(job_id: str, **patch: Any) -> dict[str, Any]:
    queue = load_release_queue()
    normalized_job_id = clean_text(job_id)
    for job in queue["jobs"]:
        if clean_text(str(job.get("id") or "")) != normalized_job_id:
            continue
        job.update(patch)
        job["updated_at"] = storage.now_ts()
        save_release_queue(queue)
        return job
    raise KeyError(job_id)


def list_account_aliases(platform: str, env: dict[str, str] | None = None) -> list[str]:
    env = env or runtime_env()
    repo_path, _ = detect_repo(env)
    cookie_dir = repo_path / "cookies"
    normalized_platform = clean_text(platform).lower() or "douyin"
    aliases: set[str] = {"default"}
    if cookie_dir.exists():
        prefix = f"{normalized_platform}_"
        for path in cookie_dir.glob(f"{normalized_platform}_*.json"):
            stem = path.stem
            if not stem.startswith(prefix):
                continue
            alias = clean_text(stem[len(prefix):])
            if alias and not alias.endswith(".profile"):
                aliases.add(alias)
    return sorted(aliases, key=lambda item: (item != "default", item.lower()))


def _account_file_path(repo_path: Path, platform: str, account_name: str) -> Path:
    return repo_path / "cookies" / f"{platform}_{account_name}.json"


def list_account_profiles(platform: str, env: dict[str, str] | None = None) -> list[dict[str, Any]]:
    env = env or runtime_env()
    repo_path, _ = detect_repo(env)
    normalized_platform = clean_text(platform).lower() or "douyin"
    profiles: list[dict[str, Any]] = []
    for alias in list_account_aliases(normalized_platform, env):
        account_file = _account_file_path(repo_path, normalized_platform, alias)
        profile_data = storage.read_json(account_file.with_suffix(".profile.json"), {})
        display_name = clean_text(str(profile_data.get("display_name") or "")) if isinstance(profile_data, dict) else ""
        profiles.append(
            {
                "alias": alias,
                "display_name": display_name,
                "label": f"{display_name}（{alias}）" if display_name else alias,
                "cookie_exists": account_file.exists(),
            }
        )
    return profiles


def account_profile_is_fresh(platform: str, account_name: str, max_age_seconds: int = 3600) -> bool:
    repo_path, _ = detect_repo()
    profile = storage.read_json(
        _account_file_path(repo_path, clean_text(platform).lower(), clean_text(account_name) or "default").with_suffix(".profile.json"),
        {},
    )
    if not isinstance(profile, dict) or profile.get("status") != "connected":
        return False
    synced_at = clean_text(str(profile.get("synced_at") or ""))
    if not synced_at:
        return False
    try:
        synced_ts = datetime.fromisoformat(synced_at.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return False
    return 0 <= storage.now_ts() - synced_ts <= max(30, int(max_age_seconds))


def mark_account_profile_invalid(platform: str, account_name: str, message: str) -> None:
    repo_path, _ = detect_repo()
    platform = clean_text(platform).lower()
    account_name = clean_text(account_name) or "default"
    profile_path = _account_file_path(repo_path, platform, account_name).with_suffix(".profile.json")
    profile = dict(storage.read_json(profile_path, {}) or {})
    profile.update(
        {
            "platform": platform,
            "alias": account_name,
            "status": "invalid",
            "message": clean_text(message),
            "source": "omnipost_cli_check",
            "checked_at": datetime.now().astimezone().isoformat(),
        }
    )
    storage.write_json(profile_path, profile)


def submission_may_have_started(task: dict[str, Any]) -> bool:
    log_text = clean_text(str(task.get("log") or ""))
    markers = (
        "已点击发布",
        "已点击发表",
        "平台已确认接收",
        "publish completed",
    )
    return any(marker in log_text for marker in markers)


def _load_storage_state_cookies(account_file: Path) -> dict[str, str]:
    if not account_file.exists():
        return {}
    try:
        payload = json.loads(account_file.read_text(encoding="utf-8"))
    except Exception:
        return {}
    cookies: dict[str, str] = {}
    for item in payload.get("cookies", []):
        if not isinstance(item, dict):
            continue
        name = clean_text(str(item.get("name", "")))
        if not name:
            continue
        cookies[name] = str(item.get("value", ""))
    return cookies


def _http_json(url: str, cookie_header: str, referer: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": ACCOUNT_PROBE_USER_AGENT,
            "Accept": "application/json,text/plain,*/*",
            "Referer": referer,
            "Cookie": cookie_header,
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        raw = response.read().decode("utf-8", errors="replace")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise RuntimeError("账号接口返回了非对象数据")
    return payload


def _deep_find_string(node: Any, keys: tuple[str, ...]) -> str:
    wanted = {item.lower() for item in keys}
    queue: list[Any] = [node]
    while queue:
        current = queue.pop(0)
        if isinstance(current, dict):
            for key, value in current.items():
                key_text = str(key).lower()
                if key_text in wanted and isinstance(value, str):
                    candidate = clean_text(value)
                    if candidate:
                        return candidate
                queue.append(value)
        elif isinstance(current, list):
            queue.extend(current)
    return ""


def _inspect_douyin_account(repo_path: Path, account_name: str) -> dict[str, Any]:
    account_file = _account_file_path(repo_path, "douyin", account_name)
    profile = {
        "platform": "douyin",
        "alias": account_name,
        "cookie_file": str(account_file),
        "cookie_exists": account_file.exists(),
        "status": "missing",
        "message": "还没有找到这个别名对应的抖音 cookie 文件。",
        "display_name": "",
        "account_id": "",
        "checked_at": storage.now_ts(),
        "source": "douyin_creator_api",
    }
    if not account_file.exists():
        return profile

    cookies = _load_storage_state_cookies(account_file)
    if not cookies:
        profile["status"] = "error"
        profile["message"] = "cookie 文件存在，但内容为空或无法读取。"
        return profile

    cookie_header = "; ".join(f"{name}={value}" for name, value in cookies.items())
    endpoints = [
        "https://creator.douyin.com/web/api/media/user/info/",
        "https://creator.douyin.com/aweme/v1/creator/pc/user/info/",
        "https://creator.douyin.com/aweme/v1/creator/user/info/",
    ]
    last_message = ""
    for url in endpoints:
        try:
            payload = _http_json(url, cookie_header, "https://creator.douyin.com/")
        except Exception as exc:
            last_message = str(exc)
            continue
        status_code = payload.get("status_code")
        status_msg = clean_text(str(payload.get("status_msg", "")))
        if status_code == 0:
            display_name = _deep_find_string(
                payload,
                ("nickname", "nick_name", "display_name", "author_name", "user_name"),
            )
            account_id = _deep_find_string(
                payload,
                ("douyin_id", "unique_id", "short_id", "sec_uid", "uid", "user_id"),
            )
            profile["status"] = "connected"
            profile["display_name"] = display_name
            profile["account_id"] = account_id
            profile["message"] = "已登录抖音创作者后台。"
            if display_name and account_id:
                profile["message"] = f"已登录：{display_name}（{account_id}）"
            elif display_name:
                profile["message"] = f"已登录：{display_name}"
            elif account_id:
                profile["message"] = f"已登录：{account_id}"
            return profile
        if status_code == 8:
            profile["status"] = "not_logged_in"
            profile["message"] = status_msg or "当前 cookie 对应的抖音账号未登录。"
            return profile
        last_message = status_msg or f"账号接口返回状态码 {status_code}"

    profile["status"] = "error"
    profile["message"] = last_message or "读取抖音账号信息失败。"
    return profile


def inspect_account_profile(platform: str, account_name: str, env: dict[str, str] | None = None) -> dict[str, Any]:
    env = env or runtime_env()
    repo_path, _ = detect_repo(env)
    alias = clean_text(account_name) or "default"
    normalized_platform = clean_text(platform).lower() or "douyin"
    account_file = _account_file_path(repo_path, normalized_platform, alias)
    cookie_exists = account_file.exists()
    base = {
        "platform": normalized_platform,
        "alias": alias,
        "cookie_file": str(account_file),
        "cookie_exists": cookie_exists,
        "status": "unsupported" if cookie_exists else "missing",
        "message": (
            "当前平台暂未接入账号昵称识别，将使用 OmniPost CLI 检测登录状态。"
            if cookie_exists
            else "尚未登录这个平台账号，请先点击“登录账号”。"
        ),
        "display_name": "",
        "account_id": "",
        "checked_at": storage.now_ts(),
        "source": "omnipost_cli",
    }
    if normalized_platform == "douyin":
        return _inspect_douyin_account(repo_path, alias)
    if cookie_exists:
        profile_path = account_file.with_suffix(".profile.json")
        profile_data = storage.read_json(profile_path, {})
        display_name = clean_text(str(profile_data.get("display_name") or "")) if isinstance(profile_data, dict) else ""
        if display_name:
            # A profile sidecar only remembers the nickname from a previous
            # successful browser session. It is not proof that today's cookie
            # is still accepted by the platform.
            base["status"] = "saved_session"
            base["display_name"] = display_name
            base["message"] = f"已保存账号：{display_name}；登录状态需要实时检测。"
            base["source"] = clean_text(str(profile_data.get("source") or "creator_page"))
    return base


def snapshot(project_id: int) -> dict[str, Any]:
    project = storage.get_project(project_id)
    status = probe()
    task = storage.read_json(storage.project_file(project_id, SOCIAL_AUTO_UPLOAD_STATE_NAME), None)
    if not isinstance(task, dict):
        task = None
    draft = load_draft(project_id, task)
    files = {
        "final_video": _file_info(project_id, "releases/final-video.mp4"),
        "thumbnail_landscape": _file_info(project_id, "covers/cover_landscape.png"),
        "thumbnail_portrait": _file_info(project_id, "covers/cover_portrait.png"),
        "thumbnail_story": _file_info(project_id, "covers/cover_story.png"),
    }
    account_options = list_account_aliases(draft["platform"])
    if draft["account_name"] not in account_options:
        account_options = [draft["account_name"], *account_options]
    account = inspect_account_profile(draft["platform"], draft["account_name"])
    account_profiles = list_account_profiles(draft["platform"])
    for profile in account_profiles:
        if profile.get("alias") == draft["account_name"] and account.get("display_name"):
            profile["display_name"] = account["display_name"]
            profile["label"] = f"{account['display_name']}（{draft['account_name']}）"
    task_action = clean_text(str((task or {}).get("action", ""))).lower()
    task_running = bool((task or {}).get("running"))
    # A QR is a live credential, not a reusable image.  Expose it only for the
    # active login job; completed/failed jobs must never leave an old code on
    # screen.
    login_qrcode = (
        latest_login_qrcode(project_id, draft["platform"], draft["account_name"])
        if task_action == "login" and task_running and account.get("status") != "connected"
        else None
    )
    published_release = latest_published_release(project_id, task)
    preflight = release_preflight(project_id)
    return {
        "project_id": project_id,
        "project_mode": clean_text(project.get("template_mode") or "video"),
        "supported_platforms": release_platforms(),
        "probe": status,
        "draft": draft,
        "account_options": account_options,
        "account_profiles": account_profiles,
        "account": account,
        "login_qrcode": login_qrcode,
        "last_published_release": published_release,
        "files": files,
        "release_preflight": preflight,
        "task": task,
    }


def _state_seed(project_id: int, action: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"release-{project_id}-{storage.now_ms()}",
        "project_id": project_id,
        "action": action,
        "platform": clean_text(payload.get("platform", "")),
        "account_name": clean_text(payload.get("account_name", "")) or "default",
        "status": "running",
        "running": True,
        "started_at": storage.now_ts(),
        "finished_at": None,
        "last_heartbeat_at": storage.now_ts(),
        "last_action_detail": "任务已受理",
        "command": "",
        "cwd": "",
        "log": "",
        "error": "",
        "result": {},
    }


def _datetime_local_to_cli(value: str) -> str:
    raw = clean_text(value)
    if not raw:
        return ""
    return raw.replace("T", " ")


def _schedule_for_execution(value: str, now: datetime | None = None) -> tuple[str, str]:
    """Resolve a saved local schedule at execution time instead of passing stale dates downstream."""
    cli_value = _datetime_local_to_cli(value)
    if not cli_value:
        return "", ""
    try:
        scheduled_at = datetime.strptime(cli_value, "%Y-%m-%d %H:%M")
    except ValueError:
        return cli_value, ""
    local_now = now or datetime.now()
    if local_now.tzinfo is not None:
        local_now = local_now.astimezone().replace(tzinfo=None)
    if scheduled_at <= local_now:
        return "", f"原预约时间 {cli_value} 已过，已按立即发布执行。"
    return cli_value, ""


def _release_schedule_at(value: str) -> datetime | None:
    cli_value = _datetime_local_to_cli(value)
    if not cli_value:
        return None
    try:
        return datetime.strptime(cli_value, "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def _release_job_wait_state(
    project_id: int,
    payload: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return the queue state without treating an unfinished video as a publish failure."""
    preflight = release_preflight(project_id)
    local_now = now or datetime.now()
    if local_now.tzinfo is not None:
        local_now = local_now.astimezone().replace(tzinfo=None)
    scheduled_at = _release_schedule_at(str(payload.get("schedule") or ""))
    schedule_ready = scheduled_at is None or scheduled_at <= local_now
    asset_ready = bool(preflight.get("ready"))
    next_check_at = storage.now_ts() + 5
    if not asset_ready:
        return {
            "ready": False,
            "status": "waiting_assets",
            "stage": "\u7b49\u5f85\u6210\u7247",
            "waiting_reason": "\u7b49\u5f85 releases/final-video.mp4 \u751f\u6210\u5b8c\u6210",
            "next_check_at": next_check_at,
            "asset_ready": False,
            "schedule_ready": schedule_ready,
        }
    if not schedule_ready:
        return {
            "ready": False,
            "status": "waiting_schedule",
            "stage": "\u7b49\u5f85\u9884\u7ea6\u65f6\u95f4",
            "waiting_reason": f"\u9884\u7ea6\u4e8e {scheduled_at.strftime('%Y-%m-%d %H:%M')} \u53d1\u5e03",
            "next_check_at": min(scheduled_at.timestamp(), storage.now_ts() + 30),
            "asset_ready": True,
            "schedule_ready": False,
        }
    return {
        "ready": True,
        "status": "queued",
        "stage": "\u53ef\u4ee5\u53d1\u5e03",
        "waiting_reason": "",
        "next_check_at": None,
        "asset_ready": True,
        "schedule_ready": True,
    }


def release_preflight(project_id: int) -> dict[str, Any]:
    """Validate immutable publish inputs before a queue record is created."""
    storage.get_project(project_id)
    video_path = storage.DATA_ROOT / "projects" / str(project_id) / "releases" / "final-video.mp4"
    ready = video_path.is_file() and video_path.stat().st_size > 0
    if ready:
        return {
            "ready": True,
            "reason": "",
            "final_video": str(video_path),
            "size": video_path.stat().st_size,
        }

    status_path = storage.DATA_ROOT / "projects" / str(project_id) / "summary.json"
    summary = storage.read_json(status_path, {})
    scene_expected = int(summary.get("scene_expected") or 0) if isinstance(summary, dict) else 0
    scene_generated = int(summary.get("scene_generated") or 0) if isinstance(summary, dict) else 0
    progress = f"（分镜图 {scene_generated}/{scene_expected}）" if scene_expected else ""
    return {
        "ready": False,
        "reason": f"当前项目尚未生成成片{progress}，请先完成 final-video.mp4 合成后再发布。",
        "final_video": str(video_path),
        "size": 0,
    }


def require_release_preflight(project_id: int) -> dict[str, Any]:
    result = release_preflight(project_id)
    if not result["ready"]:
        raise RuntimeError(str(result["reason"]))
    return result


def _project_files_or_error(project_id: int) -> dict[str, Any]:
    files = snapshot(project_id)["files"]
    if not files.get("final_video"):
        raise RuntimeError("当前项目还没有 final-video.mp4，请先完成成片合成。")
    return files


def _platform_label(platform: str) -> str:
    normalized = clean_text(platform).lower()
    for item in SOCIAL_AUTO_UPLOAD_PLATFORM_REGISTRY:
        if clean_text(str(item.get("key", ""))).lower() == normalized:
            return str(item.get("label") or item.get("key") or normalized)
    return normalized or "social-auto-upload"


def _compare_key(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", clean_text(value).lower())


def _usable_title(value: str) -> str:
    cleaned = clean_text(value)
    if not cleaned:
        return ""
    return cleaned if _compare_key(cleaned) else ""


def _douyin_work_list_url() -> str:
    return f"{DOUYIN_WORK_LIST_ENDPOINT}?{urllib.parse.urlencode(DOUYIN_WORK_LIST_PARAMS)}"


def _load_douyin_recent_works(repo_path: Path, account_name: str) -> list[dict[str, Any]]:
    account_file = _account_file_path(repo_path, "douyin", account_name)
    cookies = _load_storage_state_cookies(account_file)
    if not cookies:
        return []
    cookie_header = "; ".join(f"{name}={value}" for name, value in cookies.items())
    payload = _http_json(_douyin_work_list_url(), cookie_header, AUTO_RELEASE_ENTRY_URLS["douyin"])
    status_code = payload.get("status_code")
    if status_code not in (None, 0):
        raise RuntimeError(clean_text(str(payload.get("status_msg") or f"抖音作品列表接口返回状态码 {status_code}")))
    works = payload.get("aweme_list")
    if isinstance(works, list):
        return [item for item in works if isinstance(item, dict)]
    works = payload.get("items")
    if isinstance(works, list):
        return [item for item in works if isinstance(item, dict)]
    return []


def _douyin_work_title(work: dict[str, Any]) -> str:
    share_info = work.get("share_info") if isinstance(work.get("share_info"), dict) else {}
    next_info = work.get("next_info") if isinstance(work.get("next_info"), dict) else {}
    return clean_text(
        str(
            work.get("item_title")
            or next_info.get("item_title")
            or work.get("description")
            or work.get("desc")
            or share_info.get("share_title")
            or ""
        )
    )


def _douyin_title_match_score(work: dict[str, Any], target_title: str) -> int:
    title_key = _compare_key(target_title)
    candidate_keys = [
        _compare_key(_douyin_work_title(work)),
        _compare_key(str(work.get("description") or "")),
        _compare_key(str(work.get("desc") or "")),
    ]
    title_score = 0
    if title_key:
        for candidate in candidate_keys:
            if not candidate:
                continue
            if candidate == title_key:
                title_score = max(title_score, 100)
            elif title_key in candidate or candidate in title_key:
                title_score = max(title_score, 88)
            elif len(title_key) >= 8 and title_key[:8] in candidate:
                title_score = max(title_score, 72)
    return title_score


def _score_douyin_work(work: dict[str, Any], target_title: str, finished_at: float) -> tuple[int, float, float]:
    title_score = _douyin_title_match_score(work, target_title)
    created_at = float(work.get("create_time") or 0)
    delta = abs(finished_at - created_at) if finished_at and created_at else float("inf")
    time_score = 0
    if delta <= 300:
        time_score = 50
    elif delta <= 1800:
        time_score = 42
    elif delta <= 7200:
        time_score = 30
    elif delta <= 86400:
        time_score = 12

    status = work.get("status") if isinstance(work.get("status"), dict) else {}
    public_score = 5 if not status.get("is_private") and status.get("allow_share", True) else 0
    return title_score + time_score + public_score, -delta, created_at


def _discover_douyin_release(project_id: int, task: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
    repo_path, _ = detect_repo()
    account_name = clean_text(task.get("account_name", "") or payload.get("account_name", "")) or "default"
    project = storage.get_project(project_id)
    summary = storage.get_summary(project_id)
    target_title = clean_text(
        payload.get("title", "")
        or summary.get("publish_title", "")
        or summary.get("video_title", "")
        or project.get("topic_name", "")
    )
    finished_at = float(task.get("finished_at") or storage.now_ts())
    works = _load_douyin_recent_works(repo_path, account_name)
    if not works:
        return None
    before_ids = {clean_text(str(item)) for item in payload.get("_douyin_before_ids", []) if clean_text(str(item))}
    if before_ids:
        works = [
            work for work in works
            if clean_text(str(work.get("aweme_id") or work.get("id") or work.get("item_id") or "")) not in before_ids
        ]
        if not works:
            return None
    best = max(works, key=lambda item: _score_douyin_work(item, target_title, finished_at))
    title_score = _douyin_title_match_score(best, target_title)
    created_at = float(best.get("create_time") or 0)
    started_at = float(task.get("started_at") or finished_at)
    recent_enough = bool(created_at and started_at - 600 <= created_at <= finished_at + 1800)
    if title_score < 72 or not recent_enough:
        return None

    author = best.get("author") if isinstance(best.get("author"), dict) else {}
    status = best.get("status") if isinstance(best.get("status"), dict) else {}
    share_url = clean_text(str(best.get("share_url") or ""))
    aweme_id = clean_text(str(best.get("aweme_id") or best.get("id") or best.get("item_id") or ""))
    if not share_url and aweme_id:
        share_url = f"https://www.douyin.com/video/{aweme_id}"
    if not share_url:
        return None

    return {
        "url": share_url,
        "title": _douyin_work_title(best) or target_title,
        "description": clean_text(str(best.get("description") or best.get("desc") or "")),
        "published_at": float(best.get("create_time") or finished_at),
        "aweme_id": aweme_id,
        "account_display_name": clean_text(str(author.get("nickname") or "")),
        "account_id": clean_text(
            str(author.get("unique_id") or author.get("short_id") or author.get("sec_uid") or author.get("uid") or "")
        ),
        "is_private": bool(status.get("is_private")),
        "source": "douyin_creator_work_list",
    }


def _douyin_release_aweme_id(item: dict[str, Any]) -> str:
    direct = clean_text(str(item.get("aweme_id") or item.get("item_id") or ""))
    if direct:
        return direct
    match = re.search(r"/(?:video|note)/(\d+)", clean_text(str(item.get("url") or "")))
    return match.group(1) if match else ""


def _match_douyin_work(release: dict[str, Any], works: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not works:
        return None
    target_id = _douyin_release_aweme_id(release)
    if target_id:
        for work in works:
            work_id = clean_text(str(work.get("aweme_id") or work.get("item_id") or work.get("id") or ""))
            if work_id == target_id:
                return work

    title = clean_text(str(release.get("title") or release.get("note") or ""))
    published_at = float(release.get("published_at") or release.get("created_at") or 0)
    best = max(works, key=lambda item: _score_douyin_work(item, title, published_at))
    score, _, _ = _score_douyin_work(best, title, published_at)
    return best if score >= 60 else None


def _douyin_work_metrics(work: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    statistics = work.get("statistics") if isinstance(work.get("statistics"), dict) else {}
    current = dict(existing or {})
    current.update(
        {
            "views": statistics.get("play_count", current.get("views", 0)),
            "likes": statistics.get("digg_count", current.get("likes", 0)),
            "comments": statistics.get("comment_count", current.get("comments", 0)),
            "shares": statistics.get("share_count", statistics.get("forward_count", current.get("shares", 0))),
            "favorites": statistics.get("collect_count", current.get("favorites", 0)),
            "source": "douyin_creator_work_list",
            "synced_at": storage.now_ts(),
        }
    )
    return services.normalize_release_metrics(current)


STATS_PLATFORM_ALIASES = {
    "douyin": "douyin",
    "抖音": "douyin",
    "kuaishou": "kuaishou",
    "快手": "kuaishou",
    "xiaohongshu": "xiaohongshu",
    "小红书": "xiaohongshu",
    "bilibili": "bilibili",
    "b站": "bilibili",
}
STATS_RESULT_PREFIX = "__OMNIPOST_STATS_JSON__="


def _stats_platform(value: Any) -> str:
    return STATS_PLATFORM_ALIASES.get(clean_text(str(value or "")).lower(), "")


def _stats_command(repo_path: Path, platform: str, account_name: str, limit: int) -> list[str]:
    status = probe()
    uv_bin = str(status.get("uv_bin") or "uv")
    bridge_path = storage.APP_ROOT / "app" / "omnipost_stats_bridge.py"
    if not bridge_path.exists():
        raise RuntimeError(f"运营数据桥接器不存在: {bridge_path}")
    module_path = {
        "douyin": repo_path / "uploader" / "douyin_uploader" / "content_stats.py",
        "kuaishou": repo_path / "uploader" / "ks_uploader" / "content_stats.py",
        "xiaohongshu": repo_path / "uploader" / "xiaohongshu_uploader" / "content_stats.py",
        "bilibili": repo_path / "uploader" / "bilibili_uploader" / "content_stats.py",
    }[platform]
    if not module_path.exists():
        raise RuntimeError(f"OmniPost 缺少{_platform_label(platform)}运营数据采集器: {module_path}")
    return [
        uv_bin,
        "run",
        "python",
        str(bridge_path),
        "--repo",
        str(repo_path),
        "--platform",
        platform,
        "--account",
        account_name,
        "--limit",
        str(max(1, min(int(limit), 20))),
    ]


def _load_platform_recent_stats(repo_path: Path, platform: str, account_name: str, limit: int = 10) -> list[dict[str, Any]]:
    command = _stats_command(repo_path, platform, account_name, limit)
    completed = subprocess.run(
        command,
        cwd=str(repo_path),
        env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=8 * 60,
        **_hidden_subprocess_kwargs(),
    )
    output = completed.stdout or ""
    payload_line = next(
        (line[len(STATS_RESULT_PREFIX):] for line in reversed(output.splitlines()) if line.startswith(STATS_RESULT_PREFIX)),
        "",
    )
    if completed.returncode != 0 or not payload_line:
        detail = clean_text(output[-1600:])
        raise RuntimeError(detail or f"{_platform_label(platform)}作品数据采集失败")
    payload = json.loads(payload_line)
    items = payload.get("items") if isinstance(payload, dict) else []
    return [item for item in items if isinstance(item, dict)]


def _platform_work_summary(work: dict[str, Any], platform: str = "") -> dict[str, Any]:
    """Return compact platform data plus the canonical three-dimensional diagnosis."""
    fields = (
        "item_id", "title", "cover_url", "status", "published_at",
        "play_count", "like_count", "comment_count", "share_count", "collect_count",
        "completion_rate", "avg_play_duration_sec", "bounce_rate_2s",
        "completion_rate_5s", "avg_play_percent", "traffic_sources",
        "audience_gender", "audience_age", "audience_region",
        "boost_play_count", "boost_reason",
    )
    summary = {key: work.get(key) for key in fields if work.get(key) not in (None, "", [])}
    metrics = _platform_work_metrics(summary, _stats_platform(platform))
    summary["performance"] = services.release_performance_signal(
        {
            "platform": _stats_platform(platform),
            "title": summary.get("title", ""),
            "item_id": summary.get("item_id", ""),
            "metrics": metrics,
        }
    )
    return summary


def enrich_platform_stats_report(report: dict[str, Any]) -> dict[str, Any]:
    """Upgrade cached platform reports so old sync results get current diagnostics immediately."""
    result = dict(report or {})
    enriched_accounts: list[dict[str, Any]] = []
    for raw_account in result.get("accounts") if isinstance(result.get("accounts"), list) else []:
        if not isinstance(raw_account, dict):
            continue
        account = dict(raw_account)
        platform = _stats_platform(account.get("platform"))
        account["items"] = [
            _platform_work_summary(item, platform)
            for item in account.get("items") if isinstance(item, dict)
        ] if isinstance(account.get("items"), list) else []
        account["item_count"] = len(account["items"])
        enriched_accounts.append(account)
    result["accounts"] = enriched_accounts
    return result


def _release_content_id(item: dict[str, Any], platform: str) -> str:
    direct = clean_text(str(item.get("item_id") or item.get("aweme_id") or item.get("bvid") or ""))
    if direct:
        return direct
    url = clean_text(str(item.get("url") or ""))
    patterns = {
        "douyin": r"/(?:video|note)/(\d+)",
        "kuaishou": r"/(?:short-video|f)/(\w+)",
        "xiaohongshu": r"/(?:explore|discovery/item)/(\w+)",
        "bilibili": r"/(BV[0-9A-Za-z]+|av\d+)",
    }
    match = re.search(patterns.get(platform, r"$^"), url, flags=re.IGNORECASE)
    return match.group(1) if match else ""


def _match_platform_stat(release: dict[str, Any], works: list[dict[str, Any]], platform: str) -> dict[str, Any] | None:
    target_id = _release_content_id(release, platform)
    if target_id:
        for work in works:
            if clean_text(str(work.get("item_id") or "")).lower() == target_id.lower():
                return work
    target_title = _compare_key(str(release.get("title") or release.get("note") or ""))
    if not target_title:
        return None
    ranked: list[tuple[int, dict[str, Any]]] = []
    for work in works:
        candidate = _compare_key(str(work.get("title") or ""))
        score = 0
        if candidate == target_title:
            score = 100
        elif candidate and (candidate in target_title or target_title in candidate):
            score = 88
        elif len(target_title) >= 6 and target_title[:6] in candidate:
            score = 72
        ranked.append((score, work))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return ranked[0][1] if ranked and ranked[0][0] >= 72 else None


def _platform_work_metrics(work: dict[str, Any], platform: str, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    current = dict(existing or {})
    bounce_2s = work.get("bounce_rate_2s")
    retention_2s = current.get("two_second_retention_rate", 0)
    if bounce_2s not in (None, ""):
        bounce_value = float(bounce_2s)
        if 0 < bounce_value <= 1:
            bounce_value *= 100
        retention_2s = max(0.0, 100.0 - bounce_value)
    current.update(
        {
            "views": work.get("play_count", current.get("views", 0)),
            "likes": work.get("like_count", current.get("likes", 0)),
            "comments": work.get("comment_count", current.get("comments", 0)),
            "shares": work.get("share_count", current.get("shares", 0)),
            "favorites": work.get("collect_count", current.get("favorites", 0)),
            "two_second_retention_rate": retention_2s,
            "five_second_retention_rate": work.get("completion_rate_5s", current.get("five_second_retention_rate", 0)),
            "average_watch_seconds": work.get("avg_play_duration_sec", current.get("average_watch_seconds", 0)),
            "completion_rate": work.get("completion_rate", current.get("completion_rate", 0)),
            "source": f"omnipost_{platform}_content_stats",
            "synced_at": storage.now_ts(),
        }
    )
    return services.normalize_release_metrics(current)


def _stats_snapshot(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "synced_at": metrics.get("synced_at"),
        "views": metrics.get("views", 0),
        "likes": metrics.get("likes", 0),
        "comments": metrics.get("comments", 0),
        "shares": metrics.get("shares", 0),
        "favorites": metrics.get("favorites", 0),
        "completion_rate": metrics.get("completion_rate", 0),
        "average_watch_seconds": metrics.get("average_watch_seconds", 0),
    }


def sync_release_metrics(
    project_id: int,
    *,
    release_id: int | None = None,
    account_name: str = "",
    platform: str = "",
    limit: int = 10,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Synchronize recent work analytics through OmniPost's platform collectors."""
    requested_platform = _stats_platform(platform)
    links = storage.get_release_links(project_id)
    targets = [
        item
        for item in links
        if isinstance(item, dict)
        and (release_id is None or int(item.get("id", 0) or 0) == int(release_id))
        and _stats_platform(item.get("platform"))
        and (not requested_platform or _stats_platform(item.get("platform")) == requested_platform)
    ]
    result: dict[str, Any] = {
        "project_id": project_id,
        "requested": len(targets),
        "updated": 0,
        "skipped": 0,
        "errors": [],
        "items": [],
        "accounts": [],
        "supported_platforms": ["douyin", "kuaishou", "xiaohongshu", "bilibili"],
        "synced_at": storage.now_ts(),
    }
    repo_path, _ = detect_repo()
    works_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}
    account_failures: dict[tuple[str, str], str] = {}

    account_keys: list[tuple[str, str]] = []
    for item in targets:
        current_platform = _stats_platform(item.get("platform"))
        alias = clean_text(str(account_name or item.get("account_name") or "")) or "default"
        if (current_platform, alias) not in account_keys:
            account_keys.append((current_platform, alias))

    # A manual account sync must still show recent works when this project has no
    # release link yet. Only inspect saved accounts, sequentially, so entering the
    # release page never launches several browser collectors at once.
    if release_id is None:
        platforms = [requested_platform] if requested_platform else list(result["supported_platforms"])
        for current_platform in platforms:
            for profile in list_account_profiles(current_platform):
                alias = clean_text(str(profile.get("alias") or "")) or "default"
                if account_name and alias != clean_text(account_name):
                    continue
                if not profile.get("cookie_exists"):
                    continue
                if (current_platform, alias) not in account_keys:
                    account_keys.append((current_platform, alias))

    account_profiles: dict[tuple[str, str], dict[str, Any]] = {}
    account_progress: list[dict[str, Any]] = []
    for current_platform, alias in account_keys:
        profile = next(
            (entry for entry in list_account_profiles(current_platform) if entry.get("alias") == alias),
            {},
        )
        account_profiles[(current_platform, alias)] = profile
        account_progress.append(
            {
                "platform": current_platform,
                "platform_label": _platform_label(current_platform),
                "account_name": alias,
                "account_display_name": profile.get("display_name") or alias,
                "status": "waiting",
                "message": "等待同步",
            }
        )

    def report_progress(stage: str, message: str, **extra: Any) -> None:
        if not progress_callback:
            return
        progress_callback(
            {
                "stage": stage,
                "message": message,
                "total_accounts": len(account_keys),
                "accounts": [dict(item) for item in account_progress],
                **extra,
            }
        )

    report_progress(
        "discovering_accounts",
        f"已发现 {len(account_keys)} 个可同步账号。" if account_keys else "正在检查已保存的平台账号。",
        completed_accounts=0,
        succeeded_accounts=0,
        failed_accounts=0,
    )

    succeeded_accounts = 0
    failed_accounts = 0
    for account_index, (current_platform, alias) in enumerate(account_keys):
        profile = account_profiles.get((current_platform, alias), {})
        progress_item = account_progress[account_index]
        progress_item.update({"status": "running", "message": "正在读取作品数据"})
        display_name = clean_text(str(profile.get("display_name") or alias)) or alias
        report_progress(
            "syncing_account",
            f"正在同步{_platform_label(current_platform)} · {display_name}",
            current_platform=current_platform,
            current_account=alias,
            current_account_display_name=display_name,
            completed_accounts=account_index,
            succeeded_accounts=succeeded_accounts,
            failed_accounts=failed_accounts,
        )
        try:
            works = _load_platform_recent_stats(repo_path, current_platform, alias, limit=limit)
            works_cache[(current_platform, alias)] = works
            result["accounts"].append(
                {
                    "platform": current_platform,
                    "platform_label": _platform_label(current_platform),
                    "account_name": alias,
                    "account_display_name": profile.get("display_name") or alias,
                    "items": [_platform_work_summary(work, current_platform) for work in works],
                    "item_count": len(works),
                    "status": "succeeded",
                }
            )
            succeeded_accounts += 1
            progress_item.update(
                {
                    "status": "succeeded",
                    "message": f"已读取 {len(works)} 条作品",
                    "item_count": len(works),
                }
            )
            report_progress(
                "account_succeeded",
                f"{_platform_label(current_platform)} · {display_name} 已读取 {len(works)} 条作品。",
                current_platform=current_platform,
                current_account=alias,
                current_account_display_name=display_name,
                completed_accounts=account_index + 1,
                succeeded_accounts=succeeded_accounts,
                failed_accounts=failed_accounts,
            )
        except Exception as exc:
            message = clean_text(str(exc))
            account_failures[(current_platform, alias)] = message
            result["accounts"].append(
                {
                    "platform": current_platform,
                    "platform_label": _platform_label(current_platform),
                    "account_name": alias,
                    "account_display_name": profile.get("display_name") or alias,
                    "items": [],
                    "item_count": 0,
                    "status": "failed",
                    "message": message,
                }
            )
            if not any(
                _stats_platform(item.get("platform")) == current_platform
                and (clean_text(str(account_name or item.get("account_name") or "")) or "default") == alias
                for item in targets
            ):
                result["errors"].append(
                    {"release_id": None, "platform": current_platform, "account_name": alias, "message": message}
                )
            failed_accounts += 1
            progress_item.update({"status": "failed", "message": message or "读取失败"})
            report_progress(
                "account_failed",
                f"{_platform_label(current_platform)} · {display_name} 读取失败：{message}",
                current_platform=current_platform,
                current_account=alias,
                current_account_display_name=display_name,
                completed_accounts=account_index + 1,
                succeeded_accounts=succeeded_accounts,
                failed_accounts=failed_accounts,
            )

    if not targets and not account_keys:
        result["message"] = "当前没有已登录的抖音、快手、小红书或 B 站账号。"
        storage.save_report(project_id, "release_platform_stats", result)
        report_progress("completed", result["message"], completed_accounts=0, succeeded_accounts=0, failed_accounts=0)
        return result

    report_progress(
        "matching_releases",
        "账号作品读取完成，正在匹配当前项目的发布记录。",
        completed_accounts=len(account_keys),
        succeeded_accounts=succeeded_accounts,
        failed_accounts=failed_accounts,
    )

    for item in targets:
        current_platform = _stats_platform(item.get("platform"))
        alias = clean_text(str(account_name or item.get("account_name") or "")) or "default"
        cache_key = (current_platform, alias)
        try:
            if cache_key in account_failures:
                raise RuntimeError(account_failures[cache_key])
            work = _match_platform_stat(item, works_cache.get(cache_key, []), current_platform)
            if not work:
                result["skipped"] += 1
                result["items"].append({"release_id": item.get("id"), "platform": current_platform, "status": "not_matched"})
                continue

            previous = services.normalize_release_metrics(item.get("metrics") if isinstance(item.get("metrics"), dict) else {})
            metrics = _platform_work_metrics(work, current_platform, previous)
            history = item.get("metrics_history") if isinstance(item.get("metrics_history"), list) else []
            snapshot = _stats_snapshot(metrics)
            last = history[-1] if history and isinstance(history[-1], dict) else {}
            if any(snapshot.get(key) != last.get(key) for key in snapshot if key != "synced_at"):
                history.append(snapshot)
            item["metrics_history"] = history[-30:]
            item["metrics"] = metrics
            item["item_id"] = clean_text(str(work.get("item_id") or item.get("item_id") or ""))
            if current_platform == "douyin":
                item["aweme_id"] = item["item_id"]
            item["metrics_detail"] = {
                key: work.get(key)
                for key in (
                    "cover_url", "status", "published_at", "avg_play_percent", "traffic_sources",
                    "audience_gender", "audience_age", "audience_region", "boost_play_count", "boost_reason",
                )
                if work.get(key) not in (None, "", [])
            }
            item["metrics_sync"] = {
                "status": "succeeded",
                "source": metrics.get("source"),
                "account_name": alias,
                "synced_at": metrics.get("synced_at"),
            }
            result["updated"] += 1
            result["items"].append(
                {
                    "release_id": item.get("id"),
                    "platform": current_platform,
                    "status": "updated",
                    "metrics": metrics,
                    "metrics_detail": item["metrics_detail"],
                    "performance": services.release_performance_signal(item),
                }
            )
        except Exception as exc:
            message = clean_text(str(exc))
            item["metrics_sync"] = {
                "status": "failed",
                "account_name": alias,
                "synced_at": storage.now_ts(),
                "message": message,
            }
            result["errors"].append(
                {"release_id": item.get("id"), "platform": current_platform, "account_name": alias, "message": message}
            )
            if not any(
                account.get("platform") == current_platform and account.get("account_name") == alias
                for account in result["accounts"]
            ):
                result["accounts"].append(
                    {
                        "platform": current_platform,
                        "platform_label": _platform_label(current_platform),
                        "account_name": alias,
                        "account_display_name": item.get("account_display_name") or alias,
                        "items": [],
                        "item_count": 0,
                        "status": "failed",
                        "message": message,
                    }
                )

    storage.save_release_links(project_id, links)
    result["message"] = (
        f"运营数据同步完成：读取 {len(result['accounts'])} 个账号，"
        f"更新 {result['updated']} 条项目发布记录，未匹配 {result['skipped']} 条，失败 {len(result['errors'])} 条。"
    )
    storage.save_report(project_id, "release_platform_stats", result)
    report_progress(
        "completed",
        result["message"],
        completed_accounts=len(account_keys),
        succeeded_accounts=succeeded_accounts,
        failed_accounts=failed_accounts,
    )
    return result


RELEASE_CSV_ALIASES = {
    "release_id": ("release_id", "发布记录id", "记录id"),
    "aweme_id": ("aweme_id", "item_id", "作品id", "视频id"),
    "url": ("url", "作品链接", "分享链接", "视频链接"),
    "title": ("title", "作品标题", "视频标题", "标题"),
    "platform": ("platform", "平台"),
    "impressions": ("impressions", "impression_count", "展现量", "展现次数", "曝光量", "曝光次数"),
    "click_through_rate": ("click_through_rate", "ctr", "点击率", "播放点击率"),
    "views": ("views", "play_count", "播放量", "播放次数", "播放"),
    "likes": ("likes", "digg_count", "点赞量", "点赞"),
    "comments": ("comments", "comment_count", "评论量", "评论"),
    "shares": ("shares", "share_count", "转发量", "分享量", "转发", "分享"),
    "favorites": ("favorites", "collect_count", "收藏量", "收藏"),
    "follows": ("follows", "follow_count", "涨粉量", "新增关注", "新增粉丝", "涨粉"),
    "two_second_retention_rate": ("two_second_retention_rate", "2秒留存率", "2s留存率", "2秒播放率"),
    "two_second_bounce_rate": ("two_second_bounce_rate", "2秒跳出率", "2s跳出率"),
    "five_second_retention_rate": ("five_second_retention_rate", "5秒留存率", "5s留存率", "5秒播放率", "5秒完播率"),
    "average_watch_seconds": ("average_watch_seconds", "平均观看时长", "平均播放时长", "人均观看时长"),
    "completion_rate": ("completion_rate", "完播率", "播放完成率"),
}


def _normalized_csv_key(value: Any) -> str:
    return re.sub(r"[\s_()（）%％:：/\\-]+", "", clean_text(str(value or "")).lower())


def _csv_row_value(row: dict[str, Any], field: str) -> str:
    wanted = {_normalized_csv_key(item) for item in RELEASE_CSV_ALIASES.get(field, ())}
    for key, value in row.items():
        if _normalized_csv_key(key) in wanted and clean_text(str(value or "")):
            return clean_text(str(value or ""))
    return ""


def _csv_number(value: str) -> float | None:
    text = clean_text(value).replace(",", "").replace("，", "")
    if not text:
        return None
    multiplier = 1.0
    if "万" in text:
        multiplier = 10000.0
    elif "亿" in text:
        multiplier = 100000000.0
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    return max(0.0, float(match.group(0)) * multiplier)


def _decode_release_csv(data: bytes) -> str:
    for encoding in ("utf-8-sig", "gb18030", "utf-16"):
        with contextlib.suppress(UnicodeError):
            return data.decode(encoding)
    return data.decode("utf-8", errors="replace")


def import_release_metrics_csv(project_id: int, data: bytes, filename: str = "metrics.csv") -> dict[str, Any]:
    text = _decode_release_csv(data)
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("数据文件缺少表头。")
    links = storage.get_release_links(project_id)
    result = {
        "project_id": project_id,
        "filename": filename,
        "rows": 0,
        "updated": 0,
        "created": 0,
        "unmatched": [],
        "imported_at": storage.now_ts(),
    }

    for row_index, row in enumerate(reader, start=2):
        result["rows"] += 1
        release_id = int(_csv_number(_csv_row_value(row, "release_id")) or 0)
        aweme_id = _csv_row_value(row, "aweme_id")
        url = _csv_row_value(row, "url")
        title = _csv_row_value(row, "title")
        platform = _csv_row_value(row, "platform") or "抖音"
        if not aweme_id and url:
            aweme_id = _douyin_release_aweme_id({"url": url})

        item = next((entry for entry in links if release_id and int(entry.get("id", 0) or 0) == release_id), None)
        if item is None and aweme_id:
            item = next((entry for entry in links if _douyin_release_aweme_id(entry) == aweme_id), None)
        if item is None and url:
            item = next((entry for entry in links if clean_text(str(entry.get("url") or "")) == url), None)
        if item is None and title:
            title_key = _compare_key(title)
            item = next(
                (
                    entry
                    for entry in links
                    if title_key and title_key == _compare_key(str(entry.get("title") or entry.get("note") or ""))
                ),
                None,
            )
        if item is None and url.startswith(("http://", "https://")):
            item = {
                "id": storage.next_release_id(),
                "platform": platform,
                "url": url,
                "title": title,
                "aweme_id": aweme_id,
                "source": "platform_metrics_csv",
                "created_at": storage.now_ts(),
            }
            links.append(item)
            result["created"] += 1
        if item is None:
            result["unmatched"].append({"row": row_index, "title": title, "aweme_id": aweme_id})
            continue

        incoming = dict(item.get("metrics") if isinstance(item.get("metrics"), dict) else {})
        for field in (
            "impressions",
            "click_through_rate",
            "views",
            "likes",
            "comments",
            "shares",
            "favorites",
            "follows",
            "two_second_retention_rate",
            "five_second_retention_rate",
            "average_watch_seconds",
            "completion_rate",
        ):
            value = _csv_number(_csv_row_value(row, field))
            if value is not None:
                incoming[field] = value
        bounce = _csv_number(_csv_row_value(row, "two_second_bounce_rate"))
        if bounce is not None and not _csv_row_value(row, "two_second_retention_rate"):
            incoming["two_second_retention_rate"] = max(0.0, 100.0 - min(100.0, bounce))
        incoming["source"] = "platform_metrics_csv"
        incoming["synced_at"] = storage.now_ts()
        item["metrics"] = services.normalize_release_metrics(incoming)
        item["metrics_sync"] = {
            "status": "succeeded",
            "source": "platform_metrics_csv",
            "synced_at": item["metrics"].get("synced_at"),
            "filename": filename,
        }
        history = item.get("metrics_history") if isinstance(item.get("metrics_history"), list) else []
        history.append({
            "synced_at": item["metrics"].get("synced_at"),
            "source": "platform_metrics_csv",
            **{key: item["metrics"].get(key, 0) for key in ("impressions", "click_through_rate", "views", "likes", "comments", "shares", "favorites")},
        })
        item["metrics_history"] = history[-30:]
        result["updated"] += 1

    storage.save_release_links(project_id, links)
    result["message"] = f"读取 {result['rows']} 行，更新 {result['updated']} 条，新建 {result['created']} 条。"
    return result


def backfill_release_link(project_id: int, task: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
    platform = clean_text(task.get("platform", "") or payload.get("platform", "")).lower()
    fallback_url = AUTO_RELEASE_ENTRY_URLS.get(platform)
    if not fallback_url:
        return None

    account_name = clean_text(task.get("account_name", "") or payload.get("account_name", "")) or "default"
    account = inspect_account_profile(platform, account_name)
    project = storage.get_project(project_id)
    summary = storage.get_summary(project_id)
    discovered: dict[str, Any] | None = None
    if platform == "douyin":
        with contextlib.suppress(Exception):
            discovered = _discover_douyin_release(project_id, task, payload)

    # A failed command may only be recovered when the platform work list proves
    # that a concrete work was created. The creator management homepage is an
    # entry point, not publication evidence.
    task_status = clean_text(str(task.get("status") or "")).lower()
    if task_status != "succeeded" and not discovered:
        return None

    discovered_title = _usable_title((discovered or {}).get("title", ""))
    title = clean_text(
        discovered_title
        or payload.get("title", "")
        or summary.get("publish_title", "")
        or summary.get("video_title", "")
        or project.get("topic_name", "")
    )
    url = clean_text((discovered or {}).get("url", "") or fallback_url)
    finished_at = float((discovered or {}).get("published_at") or task.get("finished_at") or storage.now_ts())
    account_display_name = clean_text((discovered or {}).get("account_display_name", "") or account.get("display_name", ""))
    account_id = clean_text((discovered or {}).get("account_id", "") or account.get("account_id", ""))
    finished_text = datetime.fromtimestamp(finished_at).strftime("%Y-%m-%d %H:%M")
    note_parts = [f"自动发布成功 {finished_text}"]
    if account_display_name:
        note_parts.append(f"账号 {account_display_name}")
    else:
        note_parts.append(f"别名 {account_name}")
    if title:
        note_parts.append(title)
    note = " · ".join(note_parts)

    links = storage.get_release_links(project_id)
    item = next((entry for entry in links if str(entry.get("task_id") or "") == str(task.get("id") or "")), None)
    link_payload = {
        "platform": _platform_label(platform),
        "url": url,
        "entry_url": fallback_url,
        "note": note,
        "title": title,
        "source": clean_text(str((discovered or {}).get("source") or "social_auto_upload")),
        "task_id": task.get("id"),
        "account_name": account_name,
        "account_display_name": account_display_name,
        "account_id": account_id,
        "aweme_id": clean_text(str((discovered or {}).get("aweme_id") or "")),
        "published_at": finished_at,
        "created_at": finished_at,
    }
    if item is None:
        item = {"id": storage.next_release_id(), **link_payload}
        links.append(item)
    else:
        item.update(link_payload)
    storage.save_release_links(project_id, links)
    return item


def latest_published_release(project_id: int, task: dict[str, Any] | None = None) -> dict[str, Any] | None:
    links = storage.get_release_links(project_id)
    if not isinstance(links, list) or not links:
        return None
    task_id = clean_text(str(task.get("id", ""))) if task else ""
    if task_id:
        for item in links:
            if clean_text(str(item.get("task_id", ""))) == task_id:
                return item
    return max(links, key=lambda item: float(item.get("published_at") or item.get("created_at") or 0))


def _download_repo_archive(target_dir: Path) -> Path:
    if target_dir.exists():
        raise RuntimeError(f"目标路径已存在，无法自动下载仓库：{target_dir}")
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sau-bootstrap-", dir=str(target_dir.parent)) as temp_dir:
        temp_root = Path(temp_dir)
        archive_path = temp_root / "omnipost.zip"
        with urllib.request.urlopen(SOCIAL_AUTO_UPLOAD_ZIP_URL, timeout=120) as response:
            archive_path.write_bytes(response.read())
        extract_root = temp_root / "extract"
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(extract_root)
        repo_root = next(
            (item for item in extract_root.iterdir() if item.is_dir() and (item / "pyproject.toml").exists()),
            None,
        )
        if repo_root is None:
            raise RuntimeError("下载的 OmniPost 压缩包结构异常，缺少 pyproject.toml。")
        shutil.move(str(repo_root), str(target_dir))
    if not (target_dir / "pyproject.toml").exists():
        raise RuntimeError("OmniPost 发布仓库下载完成，但目录内容不完整。")
    return target_dir


def _ensure_repo_conf(repo_path: Path) -> Path:
    conf_path = repo_path / "conf.py"
    if conf_path.exists():
        text = conf_path.read_text(encoding="utf-8")
    else:
        template_path = repo_path / "conf.example.py"
        if not template_path.exists():
            raise RuntimeError("发布仓库缺少 conf.example.py，无法自动初始化 conf.py。")
        shutil.copyfile(template_path, conf_path)
        text = conf_path.read_text(encoding="utf-8")
    chrome_path = _detect_local_chrome()
    if chrome_path:
        updated = re.sub(
            r'LOCAL_CHROME_PATH\s*=\s*".*?"',
            f'LOCAL_CHROME_PATH = "{chrome_path}"',
            text,
            count=1,
        )
        if updated != text:
            conf_path.write_text(updated, encoding="utf-8")
    return conf_path


RELEASE_METRICS_SYNC_STATE_NAME = "release_metrics_sync.json"


class ReleaseMetricsSyncRuntime:
    """Run platform analytics collectors in the background, one account at a time."""

    def __init__(self) -> None:
        self.tasks: dict[int, dict[str, Any]] = {}

    def _path(self, project_id: int) -> Path:
        return storage.project_file(project_id, RELEASE_METRICS_SYNC_STATE_NAME)

    def status(self, project_id: int) -> dict[str, Any] | None:
        active = self.tasks.get(int(project_id))
        if active:
            return dict(active["state"])
        state = storage.read_json(self._path(project_id), None)
        if isinstance(state, dict) and state.get("running"):
            state = {
                **state,
                "status": "interrupted",
                "running": False,
                "stage": "interrupted",
                "message": "上一次平台数据同步随服务重启中断，请重新同步。",
                "finished_at": state.get("finished_at") or storage.now_ts(),
                "updated_at": storage.now_ts(),
            }
            storage.write_json(self._path(project_id), state)
        return state if isinstance(state, dict) else None

    async def start(
        self,
        project_id: int,
        *,
        release_id: int | None = None,
        account_name: str = "",
        platform: str = "",
        limit: int = 10,
    ) -> dict[str, Any]:
        project_id = int(project_id)
        existing = self.tasks.get(project_id)
        if existing and not existing["task"].done():
            return dict(existing["state"])

        now = storage.now_ts()
        state: dict[str, Any] = {
            "task_id": uuid.uuid4().hex,
            "project_id": project_id,
            "status": "queued",
            "running": True,
            "stage": "queued",
            "message": "同步任务已受理，正在准备账号列表。",
            "current_platform": "",
            "current_account": "",
            "current_account_display_name": "",
            "completed_accounts": 0,
            "total_accounts": 0,
            "succeeded_accounts": 0,
            "failed_accounts": 0,
            "accounts": [],
            "started_at": now,
            "updated_at": now,
            "finished_at": None,
            "result": None,
            "error": "",
        }
        storage.write_json(self._path(project_id), state)
        task = asyncio.create_task(
            self._run(
                project_id,
                state,
                release_id=release_id,
                account_name=account_name,
                platform=platform,
                limit=limit,
            )
        )
        self.tasks[project_id] = {"state": state, "task": task}
        return dict(state)

    async def _run(
        self,
        project_id: int,
        state: dict[str, Any],
        *,
        release_id: int | None,
        account_name: str,
        platform: str,
        limit: int,
    ) -> None:
        def update_progress(progress: dict[str, Any]) -> None:
            completed = int(progress.get("completed_accounts") or 0)
            total = int(progress.get("total_accounts") or 0)
            state.update(progress)
            state["status"] = "running"
            state["running"] = True
            state["percent"] = round(completed * 100 / total) if total else 0
            state["updated_at"] = storage.now_ts()
            storage.write_json(self._path(project_id), state)

        try:
            state.update(
                {
                    "status": "running",
                    "running": True,
                    "stage": "discovering_accounts",
                    "message": "正在检查已保存的平台账号。",
                    "updated_at": storage.now_ts(),
                }
            )
            storage.write_json(self._path(project_id), state)
            result = await asyncio.to_thread(
                sync_release_metrics,
                project_id,
                release_id=release_id,
                account_name=account_name,
                platform=platform,
                limit=limit,
                progress_callback=update_progress,
            )
            from . import creative_learning

            result["channel_memory"] = creative_learning.sync_project_release_memory(project_id)
            state.update(
                {
                    "status": "succeeded",
                    "running": False,
                    "stage": "completed",
                    "message": result.get("message") or "平台运营数据同步完成。",
                    "percent": 100,
                    "result": result,
                    "error": "",
                    "finished_at": storage.now_ts(),
                    "updated_at": storage.now_ts(),
                }
            )
            storage.write_json(self._path(project_id), state)
        except Exception as exc:
            message = clean_text(str(exc)) or exc.__class__.__name__
            state.update(
                {
                    "status": "failed",
                    "running": False,
                    "stage": "failed",
                    "message": f"平台数据同步失败：{message}",
                    "error": message,
                    "finished_at": storage.now_ts(),
                    "updated_at": storage.now_ts(),
                }
            )
            storage.write_json(self._path(project_id), state)
        finally:
            self.tasks.pop(project_id, None)


class SocialAutoUploadRuntime:
    def __init__(self) -> None:
        self.task: asyncio.Task[None] | None = None
        self.queue_task: asyncio.Task[None] | None = None
        self.process: asyncio.subprocess.Process | None = None
        self.state: dict[str, Any] | None = None
        self.active_queue_job_id = ""

    def latest(self, project_id: int) -> dict[str, Any] | None:
        if self.state and int(self.state.get("project_id") or 0) == int(project_id):
            return self.state
        payload = storage.read_json(storage.project_file(project_id, SOCIAL_AUTO_UPLOAD_STATE_NAME), None)
        if not isinstance(payload, dict):
            return None
        # Migrate logs written by older runs as soon as the UI reads them.
        raw_log = str(payload.get("log") or "")
        clean_log = ANSI_ESCAPE_RE.sub("", raw_log).replace("\r", "")
        if clean_log != raw_log:
            payload = dict(payload)
            payload["log"] = clean_log
            storage.write_json(storage.project_file(project_id, SOCIAL_AUTO_UPLOAD_STATE_NAME), payload)
        if payload.get("running") and (not self.task or self.task.done()):
            payload = dict(payload)
            payload["running"] = False
            payload["status"] = "interrupted"
            payload["finished_at"] = payload.get("finished_at") or storage.now_ts()
            log_text = str(payload.get("log") or "").rstrip()
            suffix = "[release] 上一次自动发布任务在服务重启前中断，请重新发起。"
            payload["log"] = f"{log_text}\n{suffix}".strip() if log_text else suffix
            storage.write_json(storage.project_file(project_id, SOCIAL_AUTO_UPLOAD_STATE_NAME), payload)
        return payload

    async def start(self, project_id: int, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self.task and not self.task.done():
            raise RuntimeError("已有自动发布任务正在运行，请等待完成或先取消。")
        if self.queue_task and not self.queue_task.done() and self.active_queue_job_id:
            raise RuntimeError("发布队列正在运行，请等待当前队列任务完成或先取消。")
        storage.get_project(project_id)
        saved_draft = load_draft(project_id)
        if action != "prepare":
            saved_draft = save_draft(project_id, payload)
        self.state = _state_seed(project_id, action, payload)
        self.state["draft"] = saved_draft
        if action == "login":
            # A QR code is bound to one browser login attempt.  Never recycle a
            # PNG left by a prior attempt; it causes a successful mobile scan to
            # look as if the page never refreshed.
            platform = clean_text(str(saved_draft.get("platform") or payload.get("platform") or "")).lower()
            account_name = clean_text(str(saved_draft.get("account_name") or payload.get("account_name") or "")) or "default"
            removed = clear_login_qrcodes(platform, account_name)
            if removed:
                self.state["log"] = f"[release] 已清理 {removed} 张过期登录二维码，等待本次登录生成新二维码。"
        self._save()
        self.task = asyncio.create_task(self._run(project_id, action, payload))
        self.task.add_done_callback(lambda _task: asyncio.create_task(self._ensure_queue_worker()))
        return self.state

    def queue_snapshot(self, project_id: int | None = None) -> dict[str, Any]:
        payload = load_release_queue()
        if _reconcile_stale_release_jobs(payload, self.active_queue_job_id):
            save_release_queue(payload)
        jobs = payload["jobs"]
        if project_id is not None:
            jobs = [job for job in jobs if int(job.get("project_id") or 0) == int(project_id)]
        active_statuses = {"waiting_assets", "waiting_schedule", "queued", "checking_account", "waiting_login", "publishing", "verifying", "retrying"}
        return {
            "jobs": sorted(jobs, key=lambda item: float(item.get("created_at") or 0), reverse=True),
            "running": bool(self.queue_task and not self.queue_task.done()),
            "active_job_id": self.active_queue_job_id,
            "pending_count": sum(1 for job in payload["jobs"] if job.get("status") in active_statuses),
            "bindings": load_release_bindings(),
        }

    async def resume_queue(self) -> dict[str, Any]:
        queue = load_release_queue()
        changed = False
        recoverable = {"checking_account", "waiting_login", "publishing", "verifying", "retrying"}
        for job in queue["jobs"]:
            status = clean_text(str(job.get("status") or ""))
            if status not in recoverable:
                continue
            log_text = str(job.get("log") or "")
            if submission_may_have_started({"log": log_text}):
                job.update({
                    "status": "needs_attention",
                    "stage": "等待发布结果确认",
                    "error": "服务重启前平台提交动作已经开始；请先核对平台作品列表，再决定是否重试。",
                    "recoverable": True,
                    "updated_at": storage.now_ts(),
                })
            else:
                job.update({
                    "status": "queued",
                    "stage": "服务恢复后从现有草稿续跑",
                    "updated_at": storage.now_ts(),
                })
            changed = True
        if changed:
            save_release_queue(queue)
        await self._ensure_queue_worker()
        return self.queue_snapshot()

    async def enqueue(self, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        storage.get_project(project_id)
        normalized = save_draft(project_id, payload)
        job = enqueue_release_job_record(project_id, normalized)
        await self._ensure_queue_worker()
        return {"job": job, "queue": self.queue_snapshot(project_id)}

    async def enqueue_many(self, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        storage.get_project(project_id)
        targets = payload.get("targets") or []
        if not isinstance(targets, list) or not targets:
            raise ValueError("请至少勾选一个发布账号。")

        available_platforms = {
            str(item.get("key") or "")
            for item in release_platforms()
            if item.get("available") is not False and item.get("status") == "ready"
        }
        common = {
            "title": clean_text(str(payload.get("title") or "")),
            "description": clean_text(str(payload.get("description") or "")),
            "tags": clean_text(str(payload.get("tags") or "")),
            "schedule": clean_text(str(payload.get("schedule") or "")),
            "headed": bool(payload.get("headed", False)),
            "debug": bool(payload.get("debug", False)),
        }
        if not common["title"]:
            raise ValueError("请先填写发布标题。")

        jobs: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for raw_target in targets:
            if not isinstance(raw_target, dict):
                continue
            platform = clean_text(str(raw_target.get("platform") or "")).lower()
            account_name = clean_text(str(raw_target.get("account_name") or "default")) or "default"
            identity = (platform, account_name)
            if not platform or identity in seen:
                continue
            if platform not in available_platforms:
                raise ValueError(f"平台 {platform or '-'} 尚未完成发布适配。")
            seen.add(identity)
            target_payload = {**common, "platform": platform, "account_name": account_name}
            jobs.append(enqueue_release_job_record(project_id, target_payload))

        if not jobs:
            raise ValueError("没有可入队的发布账号。")
        save_draft(project_id, {**common, **(jobs[0].get("payload") or {})})
        await self._ensure_queue_worker()
        return {"jobs": jobs, "count": len(jobs), "queue": self.queue_snapshot(project_id)}

    async def retry_queue_job(self, job_id: str) -> dict[str, Any]:
        queue = load_release_queue()
        target = next((job for job in queue["jobs"] if clean_text(str(job.get("id") or "")) == clean_text(job_id)), None)
        if target is None:
            raise RuntimeError("没有找到该发布任务。")
        if target.get("status") not in {"failed", "cancelled"}:
            raise RuntimeError("只有失败或已取消的任务可以重试。")
        update_release_queue_job(
            job_id,
            status="queued",
            stage="等待重试",
            error="",
            finished_at=None,
            attempts=0,
        )
        await self._ensure_queue_worker()
        return self.queue_snapshot(int(target.get("project_id") or 0))

    async def cancel_queue_job(self, job_id: str) -> dict[str, Any]:
        queue = load_release_queue()
        target = next((job for job in queue["jobs"] if clean_text(str(job.get("id") or "")) == clean_text(job_id)), None)
        if target is None:
            raise RuntimeError("没有找到该发布任务。")
        if target.get("status") in {"succeeded", "failed", "cancelled"}:
            return self.queue_snapshot(int(target.get("project_id") or 0))
        if self.active_queue_job_id == clean_text(job_id):
            if self.process and self.process.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    self.process.terminate()
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(self.process.wait(), timeout=10)
            if self.queue_task and not self.queue_task.done():
                self.queue_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self.queue_task
            self.queue_task = None
            self.active_queue_job_id = ""
        update_release_queue_job(
            job_id,
            status="cancelled",
            stage="已取消",
            finished_at=storage.now_ts(),
            error="用户取消任务",
        )
        await self._ensure_queue_worker()
        return self.queue_snapshot(int(target.get("project_id") or 0))

    async def _ensure_queue_worker(self) -> None:
        queue = load_release_queue()
        active_statuses = {"waiting_assets", "waiting_schedule", "queued", "retrying"}
        if not any(job.get("status") in active_statuses for job in queue["jobs"]):
            return
        if self.task and not self.task.done():
            return
        if self.queue_task and not self.queue_task.done():
            return
        self.queue_task = asyncio.create_task(self._queue_loop())

    async def _run_queue_action(self, project_id: int, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.state = _state_seed(project_id, action, payload)
        self.state["draft"] = save_draft(project_id, payload)
        self._save()
        await self._run(project_id, action, payload)
        return dict(self.state or {})

    def _queue_action_patch(self, action: str, action_state: dict[str, Any] | None) -> dict[str, Any]:
        state = dict(action_state or {})
        return {
            "last_action": clean_text(action),
            "command": str(state.get("command") or ""),
            "cwd": str(state.get("cwd") or ""),
            "log": str(state.get("log") or ""),
            "result": dict(state.get("result") or {}),
        }

    def _record_queue_action(self, job_id: str, action: str, action_state: dict[str, Any] | None) -> dict[str, Any]:
        queue = load_release_queue()
        current = next((item for item in queue.get("jobs", []) if clean_text(str(item.get("id") or "")) == clean_text(job_id)), {})
        state = dict(action_state or {})
        history = list(current.get("attempt_history") or [])
        history.append({
            "action": clean_text(action),
            "status": clean_text(str(state.get("status") or "")),
            "started_at": state.get("started_at"),
            "finished_at": state.get("finished_at"),
            "command": str(state.get("command") or ""),
            "cwd": str(state.get("cwd") or ""),
            "log": str(state.get("log") or ""),
            "error": str(state.get("error") or ""),
            "result": dict(state.get("result") or {}),
        })
        return update_release_queue_job(job_id, **self._queue_action_patch(action, state), attempt_history=history[-12:])

    async def _queue_loop(self) -> None:
        try:
            while True:
                queue = load_release_queue()
                active = [
                    item for item in queue["jobs"]
                    if item.get("status") in {"waiting_assets", "waiting_schedule", "queued", "retrying"}
                ]
                if not active:
                    return

                runnable: dict[str, Any] | None = None
                for item in active:
                    if item.get("status") in {"waiting_assets", "waiting_schedule"}:
                        wait_state = _release_job_wait_state(
                            int(item.get("project_id") or 0),
                            dict(item.get("payload") or {}),
                        )
                        item = update_release_queue_job(
                            clean_text(str(item.get("id") or "")),
                            status=wait_state["status"],
                            stage=wait_state["stage"],
                            waiting_reason=wait_state["waiting_reason"],
                            next_check_at=wait_state["next_check_at"],
                        )
                    if item.get("status") in {"queued", "retrying"}:
                        runnable = item
                        break

                if runnable is None:
                    self.active_queue_job_id = ""
                    await asyncio.sleep(5)
                    continue

                self.active_queue_job_id = clean_text(str(runnable.get("id") or ""))
                await self._process_queue_job(dict(runnable))
        finally:
            self.active_queue_job_id = ""
            self.queue_task = None

    async def _process_queue_job(self, job: dict[str, Any]) -> None:
        job_id = clean_text(str(job.get("id") or ""))
        project_id = int(job.get("project_id") or 0)
        payload = _normalize_release_draft(
            dict(job.get("payload") or {}),
            {"platform": job.get("platform"), "account_name": job.get("account_name")},
        )
        account_name = clean_text(str(job.get("account_name") or payload.get("account_name") or "default")) or "default"
        payload["account_name"] = account_name
        if payload != dict(job.get("payload") or {}):
            update_release_queue_job(job_id, payload=payload)
        wait_state = _release_job_wait_state(project_id, payload)
        if not wait_state["ready"]:
            update_release_queue_job(
                job_id,
                status=wait_state["status"],
                stage=wait_state["stage"],
                waiting_reason=wait_state["waiting_reason"],
                next_check_at=wait_state["next_check_at"],
            )
            return
        last_action = ""
        last_action_state: dict[str, Any] = {}
        try:
            update_release_queue_job(
                job_id,
                status="checking_account",
                stage="检查发布账号",
                started_at=job.get("started_at") or storage.now_ts(),
                error="",
            )
            platform = clean_text(str(payload.get("platform") or ""))
            if platform == "tencent":
                # The Tencent uploader now owns login, upload, submit and
                # management-list verification in one browser context. A
                # separate check/login process would discard the fresh session.
                update_release_queue_job(job_id, status="publishing", stage="登录并发布")
            else:
                if account_profile_is_fresh(platform, account_name):
                    update_release_queue_job(job_id, status="checking_account", stage="复用最近登录检测")
                    check_state = {"status": "succeeded", "result": {"cached_account_check": True}}
                else:
                    check_state = await self._run_queue_action(project_id, "check", payload)
                    last_action, last_action_state = "check", check_state
                    self._record_queue_action(job_id, last_action, last_action_state)
                if check_state.get("status") != "succeeded":
                    update_release_queue_job(job_id, status="waiting_login", stage="等待账号登录")
                    login_state = await self._run_queue_action(project_id, "login", {**payload, "headed": True})
                    last_action, last_action_state = "login", login_state
                    self._record_queue_action(job_id, last_action, last_action_state)
                    if login_state.get("status") != "succeeded":
                        raise RuntimeError(clean_text(str(login_state.get("error") or "账号登录未完成。")))
                    check_state = await self._run_queue_action(project_id, "check", payload)
                    last_action, last_action_state = "check", check_state
                    self._record_queue_action(job_id, last_action, last_action_state)
                    if check_state.get("status") != "succeeded":
                        raise RuntimeError(clean_text(str(check_state.get("error") or "账号检测未通过。")))

            if platform == "douyin":
                try:
                    repo_path, _ = detect_repo()
                    before_works = await asyncio.to_thread(_load_douyin_recent_works, repo_path, account_name)
                    payload["_douyin_before_ids"] = [
                        clean_text(str(item.get("aweme_id") or item.get("id") or item.get("item_id") or ""))
                        for item in before_works
                        if clean_text(str(item.get("aweme_id") or item.get("id") or item.get("item_id") or ""))
                    ]
                    update_release_queue_job(
                        job_id,
                        result={"douyin_before_ids": payload["_douyin_before_ids"]},
                        stage=f"已记录发布前作品快照（{len(payload['_douyin_before_ids'])} 条）",
                    )
                except Exception as exc:
                    raise RuntimeError(f"抖音发布前作品快照获取失败: {exc}") from exc

            max_attempts = max(1, int(job.get("max_attempts") or 2))
            for attempt in range(int(job.get("attempts") or 0) + 1, max_attempts + 1):
                update_release_queue_job(
                    job_id,
                    status="publishing" if attempt == 1 else "retrying",
                    stage="上传并发布" if attempt == 1 else f"自动重试 {attempt}/{max_attempts}",
                    attempts=attempt,
                    error="",
                )
                publish_state = await self._run_queue_action(project_id, "publish", payload)
                last_action, last_action_state = "publish", publish_state
                self._record_queue_action(job_id, last_action, last_action_state)
                verified_release = (publish_state.get("result") or {}).get("published_release")
                if publish_state.get("status") == "succeeded" and (platform != "douyin" or verified_release):
                    success_patch = self._queue_action_patch("publish", publish_state)
                    success_patch["result"] = (
                        {"published_release": verified_release}
                        if verified_release
                        else dict(publish_state.get("result") or {})
                    )
                    update_release_queue_job(
                        job_id,
                        status="succeeded",
                        stage="平台已确认发布" if verified_release else "发布完成",
                        finished_at=storage.now_ts(),
                        error="",
                        **success_patch,
                    )
                    return
                update_release_queue_job(job_id, status="verifying", stage="核对平台是否已收到作品")
                await asyncio.sleep(8)
                published_link = await asyncio.to_thread(backfill_release_link, project_id, publish_state, payload)
                if published_link:
                    update_release_queue_job(
                        job_id,
                        status="succeeded",
                        stage="平台已确认发布",
                        finished_at=storage.now_ts(),
                        error="",
                        result={"published_release": published_link},
                    )
                    return
                publish_log = clean_text(str(publish_state.get("log") or ""))
                if "未找到可点击的“发表”按钮" in publish_log:
                    raise RuntimeError("视频号封面处理超时，发表按钮始终不可用；本次未点击发表，也不会自动重复上传。")
                if submission_may_have_started(publish_state):
                    raise RuntimeError(
                        "平台可能已经收到视频，但尚未返回可验证结果；为避免重复发布，系统已停止自动重试。"
                    )
                if attempt >= max_attempts:
                    raise RuntimeError(clean_text(str(publish_state.get("error") or "发布命令执行失败。")))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            evidence = self._queue_action_patch(last_action, last_action_state) if last_action_state else {}
            submitted_without_confirmation = bool(
                last_action == "publish"
                and last_action_state
                and submission_may_have_started(last_action_state)
            )
            update_release_queue_job(
                job_id,
                status="needs_attention" if submitted_without_confirmation else "failed",
                stage="等待发布结果确认" if submitted_without_confirmation else "发布失败",
                finished_at=storage.now_ts(),
                error=(
                    "平台提交动作已经发生，但作品列表暂时没有返回可核验结果；已停止自动重试，避免重复发布。"
                    if submitted_without_confirmation
                    else str(exc)
                ),
                recoverable=True,
                **evidence,
            )

    async def cancel(self) -> dict[str, Any]:
        if self.process and self.process.returncode is None:
            await self._terminate_active_process()
        if not self.task or self.task.done():
            if self.state and self.state.get("running"):
                self.state["running"] = False
                self.state["status"] = "cancelled"
                self.state["finished_at"] = storage.now_ts()
                self.state["error"] = "登录或发布进程已结束"
                self._log("[release] 已清理没有后台进程的残留运行状态。")
                self._save()
            return {"already_done": True}
        self.task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self.task
        return {"already_done": False}

    def _save(self) -> None:
        if not self.state:
            return
        project_id = int(self.state.get("project_id") or 0)
        if project_id > 0:
            storage.write_json(storage.project_file(project_id, SOCIAL_AUTO_UPLOAD_STATE_NAME), self.state)

    def _log(self, line: str) -> None:
        if not self.state:
            return
        # Rich/loguru output includes ANSI colour sequences even when stdout is
        # piped. Persist only plain UTF-8 text because the desktop log panel is
        # not a terminal and would otherwise render fragments such as [38;2;...m.
        text = ANSI_ESCAPE_RE.sub("", str(line or "")).replace("\r", "").strip()
        existing = ANSI_ESCAPE_RE.sub("", str(self.state.get("log") or "")).replace("\r", "").rstrip()
        self.state["log"] = f"{existing}\n{text}".strip() if existing else text
        now = storage.now_ts()
        self.state["last_heartbeat_at"] = now
        self.state["last_action_detail"] = text[-240:]
        self._save()
        # Keep the durable queue live while a browser subprocess is producing
        # logs.  Throttling prevents one JSON rewrite per log line.
        job_id = clean_text(self.active_queue_job_id)
        if job_id:
            previous = float(getattr(self, "_last_queue_heartbeat_at", 0) or 0)
            if now - previous >= RELEASE_HEARTBEAT_INTERVAL_SECONDS:
                with contextlib.suppress(Exception):
                    heartbeat_patch = {
                        "last_heartbeat_at": now,
                        "last_action_detail": text[-240:],
                    }
                    detected_stage = _release_stage_from_log(text)
                    if detected_stage:
                        heartbeat_patch["stage"] = detected_stage
                    update_release_queue_job(job_id, **heartbeat_patch)
                self._last_queue_heartbeat_at = now

    def _base_env(self) -> dict[str, str]:
        status = probe()
        env = {
            **os.environ,
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
        }
        host = _normalized_patchright_host(str(status.get("patchright_download_host") or ""))
        if host:
            env["PLAYWRIGHT_DOWNLOAD_HOST"] = host
        if status.get("xhs_base_url"):
            env["XHS_CREATOR_BASE_URL"] = str(status["xhs_base_url"])
        return env

    def _resolve_commands(self, project_id: int, action: str, payload: dict[str, Any]) -> tuple[Path, list[list[str]]]:
        normalized_payload = _normalize_release_draft(payload, _release_draft_defaults(project_id, self.state or None))
        status = probe()
        repo_path = Path(str(status.get("repo_path") or ""))
        if not repo_path.exists() or not (repo_path / "pyproject.toml").exists():
            raise RuntimeError("没有找到可用的 social-auto-upload 仓库，请先在配置页填写正确路径。")
        uv_bin = str(status.get("uv_bin") or "uv")
        if not (shutil.which(uv_bin) or Path(uv_bin).exists()):
            raise RuntimeError("本机没有可用的 uv 命令，请先安装 uv 或在配置页填写 uv 的绝对路径。")

        platform = clean_text(normalized_payload.get("platform", "")).lower()
        account_name = clean_text(normalized_payload.get("account_name", "")) or "default"
        headed = _platform_requires_headed(platform) or bool(normalized_payload.get("headed"))
        debug = bool(normalized_payload.get("debug"))

        def browser_args() -> list[str]:
            args: list[str] = []
            args.append("--headed" if headed else "--headless")
            if debug:
                args.append("--debug")
            return args

        if action == "prepare":
            commands = [[uv_bin, "sync"]]
            if not _detect_local_chrome():
                commands.append([uv_bin, "run", "patchright", "install", "chromium"])
            commands.append([uv_bin, "run", "python", "sau_cli.py", "--help"])
            return repo_path, commands

        platform_info = release_platform(platform)
        supported = {clean_text(str(item.get("key") or "")).lower() for item in SOCIAL_AUTO_UPLOAD_PLATFORM_REGISTRY}
        if platform not in supported:
            raise RuntimeError(f"暂不支持平台：{platform or '未填写'}")
        if not platform_info or not bool(platform_info.get("available")):
            note = clean_text(str((platform_info or {}).get("note") or "这个平台还没有接入可执行发布适配器。"))
            raise RuntimeError(f"{_platform_label(platform)}暂不能自动发布：{note}")

        adapter = clean_text(str(platform_info.get("adapter") or "sau_cli"))
        bridge_path = storage.APP_ROOT / "app" / "omnipost_bridge.py"
        profile_probe_path = storage.APP_ROOT / "app" / "omnipost_account_profile.py"
        profile_command = [
            uv_bin,
            "run",
            "python",
            str(profile_probe_path),
            "--repo",
            str(repo_path),
            "--platform",
            platform,
            "--account",
            account_name,
        ]

        if adapter == "omnipost_bridge":
            base = [
                uv_bin,
                "run",
                "python",
                str(bridge_path),
                "--repo",
                str(repo_path),
                "--platform",
                platform,
                "--action",
                action,
                "--account",
                account_name,
            ]
            # Login may need a visible page, but automatic publishing must stay
            # in the background instead of inheriting the login window mode.
            if action == "login" and headed:
                base.append("--headed")
            if action in {"login", "check"}:
                return repo_path, [base, profile_command]
            if action != "publish":
                raise RuntimeError(f"未知动作：{action}")
            files = _project_files_or_error(project_id)
            final_video = files["final_video"]
            project = storage.get_project(project_id)
            title = clean_text(normalized_payload.get("title", "")) or clean_text(project.get("topic_name") or "")
            description = clean_text(normalized_payload.get("description", ""))
            tags = clean_text(normalized_payload.get("tags", ""))
            schedule, schedule_notice = _schedule_for_execution(str(normalized_payload.get("schedule", "")))
            if schedule_notice:
                self._log(f"[release] {schedule_notice}")
            base.extend(["--title", title, "--desc", description])
            if platform in {"baijiahao", "toutiao", "tiktok"}:
                base.extend(["--file", str(final_video["absolute_path"])])
            else:
                content_file = storage.project_file(project_id, "content.md")
                if not content_file.exists():
                    raise RuntimeError("项目缺少 content.md，无法生成图文发布正文。")
                base.extend(["--content-file", str(content_file)])
            if tags:
                base.extend(["--tags", tags])
            if schedule:
                base.extend(["--schedule", schedule])
            thumbnail = files.get("thumbnail_portrait") or files.get("thumbnail_story") or files.get("thumbnail_landscape")
            if thumbnail:
                base.extend(["--thumbnail", str(thumbnail["absolute_path"])])
            return repo_path, [base]

        if action == "login":
            login_args = ["--headed"]
            if debug:
                login_args.append("--debug")
            # Login and cookie validation establish that the session is valid;
            # the profile command then reads the platform-owned account name
            # from the saved browser storage without opening another window.
            return repo_path, [
                [uv_bin, "run", "python", "sau_cli.py", platform, "login", "--account", account_name, *login_args],
                [uv_bin, "run", "python", "sau_cli.py", platform, "check", "--account", account_name],
                profile_command,
            ]

        if action == "check":
            return repo_path, [
                [uv_bin, "run", "python", "sau_cli.py", platform, "check", "--account", account_name],
                profile_command,
            ]

        if action != "publish":
            raise RuntimeError(f"未知动作：{action}")

        files = _project_files_or_error(project_id)
        final_video = files["final_video"]
        title = clean_text(normalized_payload.get("title", "")) or clean_text(storage.get_project(project_id).get("topic_name") or "")
        description = clean_text(normalized_payload.get("description", ""))
        tags = clean_text(normalized_payload.get("tags", ""))
        schedule, schedule_notice = _schedule_for_execution(str(normalized_payload.get("schedule", "")))
        if schedule_notice:
            self._log(f"[release] {schedule_notice}")
        command = [
            uv_bin,
            "run",
            "python",
            "sau_cli.py",
            platform,
            "upload-video",
            "--account",
            account_name,
            "--file",
            str(final_video["absolute_path"]),
            "--title",
            title,
            "--desc",
            description,
        ]
        if platform != "bilibili":
            command.extend(browser_args())
        if platform == "bilibili":
            command.extend(["--tid", "249"])
        if tags:
            command.extend(["--tags", tags])
        if schedule:
            command.extend(["--schedule", schedule])

        landscape = files.get("thumbnail_landscape")
        story = files.get("thumbnail_story")
        portrait = files.get("thumbnail_portrait")
        if platform == "tencent":
            # Video Channels asks for a 4:3 share card. The Studio's
            # cover_landscape is 16:9, while cover_story is the 4:3 asset.
            share_thumbnail = story or landscape
            if share_thumbnail:
                command.extend(["--thumbnail-landscape", str(share_thumbnail["absolute_path"])])
            portrait_thumbnail = portrait or story
            if portrait_thumbnail:
                command.extend(["--thumbnail-portrait", str(portrait_thumbnail["absolute_path"])])
        elif platform != "bilibili":
            thumbnail = portrait or story or landscape
            if thumbnail:
                command.extend(["--thumbnail", str(thumbnail["absolute_path"])])
        return repo_path, [command]

    def _command_timeout_seconds(self, action: str) -> int:
        env_key = f"RELEASE_{clean_text(action).upper()}_TIMEOUT_SECONDS"
        configured = clean_text(os.environ.get(env_key, ""))
        if configured.isdigit() and int(configured) > 0:
            return int(configured)
        return RELEASE_ACTION_TIMEOUT_SECONDS.get(clean_text(action).lower(), 10 * 60)

    async def _terminate_active_process(self) -> None:
        process = self.process
        if process is None or process.returncode is not None:
            return
        if os.name == "nt":
            killer = None
            with contextlib.suppress(Exception):
                killer = await asyncio.create_subprocess_exec(
                    "taskkill", "/PID", str(process.pid), "/T", "/F",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                    **_hidden_subprocess_kwargs(),
                )
            if killer is not None:
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(killer.wait(), timeout=10)
        else:
            with contextlib.suppress(ProcessLookupError):
                process.terminate()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(process.wait(), timeout=10)
        if process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(process.wait(), timeout=5)

    async def _run_command(self, command: list[str], cwd: Path, action: str) -> int:
        self.process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(cwd),
            env=self._base_env(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            **_hidden_subprocess_kwargs(),
        )
        assert self.process.stdout is not None
        timeout_seconds = self._command_timeout_seconds(action)
        deadline = time.monotonic() + timeout_seconds
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    label = RELEASE_ACTION_LABELS.get(action, action)
                    self._log(f"[release] {label}超过 {timeout_seconds} 秒，正在结束卡住的浏览器进程。")
                    await self._terminate_active_process()
                    raise RuntimeError(f"{label}超过 {timeout_seconds} 秒，已结束卡住的浏览器进程。")
                try:
                    line = await asyncio.wait_for(
                        self.process.stdout.readline(),
                        timeout=min(1.0, remaining),
                    )
                except asyncio.TimeoutError:
                    if self.process.returncode is not None:
                        break
                    continue
                if not line:
                    break
                self._log(line.decode("utf-8", errors="replace").rstrip())
            return await asyncio.wait_for(self.process.wait(), timeout=max(1.0, deadline - time.monotonic()))
        except asyncio.TimeoutError:
            label = RELEASE_ACTION_LABELS.get(action, action)
            self._log(f"[release] {label}超过 {timeout_seconds} 秒，正在结束卡住的浏览器进程。")
            await self._terminate_active_process()
            raise RuntimeError(f"{label}超过 {timeout_seconds} 秒，已结束卡住的浏览器进程。")
        finally:
            if self.process is not None and self.process.returncode is not None:
                self.process = None

    async def _run(self, project_id: int, action: str, payload: dict[str, Any]) -> None:
        assert self.state is not None
        try:
            normalized_payload = _normalize_release_draft(payload, _release_draft_defaults(project_id, self.state))
            self.state["payload"] = normalized_payload
            status = probe()
            repo_path = Path(str(status.get("repo_path") or ""))
            if not repo_path.exists():
                self._log(f"[release] 未找到 social-auto-upload 仓库，正在自动下载到 {repo_path}")
                await asyncio.to_thread(_download_repo_archive, repo_path)
                self._log("[release] social-auto-upload 仓库下载完成")
            if repo_path.exists() and (repo_path / "pyproject.toml").exists() and not (repo_path / "conf.py").exists():
                await asyncio.to_thread(_ensure_repo_conf, repo_path)
                self._log("[release] 已自动创建 social-auto-upload/conf.py")
            elif repo_path.exists() and (repo_path / "pyproject.toml").exists():
                await asyncio.to_thread(_ensure_repo_conf, repo_path)
            if action == "prepare":
                chrome_path = _detect_local_chrome()
                if chrome_path:
                    self._log(f"[release] 已检测到本机 Chrome，准备流程将直接复用：{chrome_path}")
            if action == "login":
                platform = clean_text(normalized_payload.get("platform", "")).lower()
                if platform == "tencent":
                    self._log("[release] 视频号登录将在后台准备二维码，请直接在当前页面扫码。")
                else:
                    self._log("[release] 登录动作将打开可见浏览器，方便完成平台验证。")
            if action == "check":
                platform = clean_text(normalized_payload.get("platform", "")).lower()
                account_name = clean_text(normalized_payload.get("account_name", "")) or "default"
                self.state["cwd"] = str(repo_path)
                self.state["command"] = "inspect_account_profile"
                self._save()
                account = await asyncio.to_thread(inspect_account_profile, platform, account_name)
                self.state["result"] = {"account": account}
                display_name = clean_text(str(account.get("display_name") or account.get("account_id") or ""))
                if account.get("status") == "connected" and platform == "douyin":
                    summary = display_name or clean_text(str(account.get("message") or "已登录"))
                    self._log(f"[release] 账号检测通过: {summary}")
                    self.state["status"] = "succeeded"
                    self.state["running"] = False
                    self.state["finished_at"] = storage.now_ts()
                    self._save()
                    return
                if account.get("cookie_exists"):
                    if display_name:
                        self._log(f"[release] 已保存账号: {display_name}，正在向平台实时验证登录状态。")
                    else:
                        self._log("[release] 已找到账号会话，正在向平台实时验证登录状态。")
                else:
                    message = clean_text(str(account.get("message") or "")) or "账号未登录或 cookie 已失效。"
                    raise RuntimeError(message)
            cwd, commands = self._resolve_commands(project_id, action, normalized_payload)
            if action == "publish":
                self._log(
                    "[release] publish payload"
                    f" title={_debug_text(normalized_payload.get('title', ''))}"
                    f" desc={_debug_text(normalized_payload.get('description', ''))}"
                    f" tags={_debug_text(normalized_payload.get('tags', ''))}"
                )
            self.state["cwd"] = str(cwd)
            self._save()
            for index, command in enumerate(commands, start=1):
                self.state["command"] = subprocess.list2cmdline(command)
                self._save()
                self._log(f"[release] step {index}/{len(commands)} -> {self.state['command']}")
                return_code = await self._run_command(command, cwd, action)
                if return_code != 0:
                    platform = clean_text(normalized_payload.get("platform", "")).lower()
                    failure_message = _release_command_failure_message(
                        action,
                        platform,
                        str(self.state.get("log") or ""),
                        return_code,
                    )
                    if action in {"check", "login"}:
                        mark_account_profile_invalid(
                            platform,
                            clean_text(normalized_payload.get("account_name", "")) or "default",
                            failure_message,
                        )
                    raise RuntimeError(failure_message)
            if action in {"check", "login"}:
                platform = clean_text(normalized_payload.get("platform", "")).lower()
                account_name = clean_text(normalized_payload.get("account_name", "")) or "default"
                previous_account = dict((self.state.get("result") or {}).get("account") or {})
                latest_account = await asyncio.to_thread(inspect_account_profile, platform, account_name)
                display_name = clean_text(
                    str(
                        latest_account.get("display_name")
                        or previous_account.get("display_name")
                        or latest_account.get("account_id")
                        or previous_account.get("account_id")
                        or ""
                    )
                )
                latest_account.update(
                    {
                        "platform": platform,
                        "alias": account_name,
                        "cookie_exists": True,
                        "status": "connected",
                        "message": f"实时检测通过：{display_name or account_name}",
                        "display_name": display_name,
                        "checked_at": storage.now_ts(),
                        "source": "omnipost_cli_check",
                    }
                )
                self.state["result"] = {"account": latest_account}
                repo_path, _ = detect_repo()
                profile_path = _account_file_path(repo_path, platform, account_name).with_suffix(".profile.json")
                profile_payload = dict(storage.read_json(profile_path, {}) or {})
                profile_payload.update(
                    {
                        "platform": platform,
                        "alias": account_name,
                        "display_name": display_name,
                        "status": "connected",
                        "source": "omnipost_cli_check",
                        "synced_at": datetime.now().astimezone().isoformat(),
                    }
                )
                storage.write_json(profile_path, profile_payload)
                if action == "login":
                    self._log(f"[release] 登录已确认：{display_name or account_name}")
                else:
                    self._log(f"[release] 账号实时检测通过：{display_name or account_name}")
            self.state["status"] = "succeeded"
            self.state["running"] = False
            self.state["finished_at"] = storage.now_ts()
            result = dict(self.state.get("result") or {})
            if action in {"prepare", "publish"}:
                result.update(snapshot(project_id)["files"])
            if action == "publish":
                published_link = backfill_release_link(project_id, self.state, payload)
                if published_link:
                    result["published_release"] = published_link
                    self._log(f"[release] 已自动回填投放链接: {published_link['url']}")
            self.state["result"] = result
            self._log("[release] 任务执行完成")
            self._save()
        except asyncio.CancelledError:
            self.state["status"] = "cancelled"
            self.state["running"] = False
            self.state["finished_at"] = storage.now_ts()
            self._log("[release] 用户已取消自动发布任务")
            self._save()
            raise
        except Exception as exc:
            self.state["status"] = "failed"
            self.state["running"] = False
            self.state["finished_at"] = storage.now_ts()
            self.state["error"] = str(exc)
            self._log(f"[release] 任务失败：{exc}")
            self._save()
        finally:
            self.process = None
