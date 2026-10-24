from __future__ import annotations

import asyncio
import copy
import contextlib
import importlib
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import storage, validators


storage.bootstrap()

app = FastAPI(title="Short Video Studio Clone", version="0.1.0")
_SCENE_STATUS_CACHE_TTL_SECONDS = 0.75
_SCENE_STATUS_CACHE_LOCK = threading.Lock()
_SCENE_STATUS_CACHE: dict[int, tuple[float, dict[str, Any]]] = {}
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def disable_studio_asset_cache(request, call_next):
    response = await call_next(request)
    if request.url.path == "/studio" or request.url.path.startswith("/studio/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.get("/api/runtime/version")
def api_runtime_version() -> dict[str, str]:
    return {"version": "20260815-open-file-permissions-v1"}


class LazyModule:
    def __init__(self, module_name: str):
        self.module_name = module_name
        self._module: Any | None = None

    def get(self) -> Any:
        if self._module is None:
            self._module = importlib.import_module(f".{self.module_name}", __package__)
        return self._module

    def __getattr__(self, name: str) -> Any:
        return getattr(self.get(), name)


class LazyRuntime:
    def __init__(self, module_name: str, class_name: str):
        self.module_name = module_name
        self.class_name = class_name
        self._instance: Any | None = None

    def get(self) -> Any:
        if self._instance is None:
            module = importlib.import_module(f".{self.module_name}", __package__)
            self._instance = getattr(module, self.class_name)()
        return self._instance

    def __getattr__(self, name: str) -> Any:
        return getattr(self.get(), name)

    @property
    def loaded(self) -> bool:
        return self._instance is not None


services = LazyModule("services")
creative_learning = LazyModule("creative_learning")
capsule_architecture = LazyModule("capsule_architecture")
release_automation = LazyModule("release_automation")
package_builder = LazyModule("package_builder")
content_runtime = LazyRuntime("services", "ContentRuntime")
content_sync_runtime = LazyRuntime("services", "ContentSyncRuntime")
job_runtime = LazyRuntime("services", "JobRuntime")
auto_video_runtime = LazyRuntime("services", "AutoVideoRuntime")
release_runtime = LazyRuntime("release_automation", "SocialAutoUploadRuntime")
release_metrics_runtime = LazyRuntime("release_automation", "ReleaseMetricsSyncRuntime")
packaging_runtime = LazyRuntime("package_builder", "PackagingRuntime")
startup_recovery_task: asyncio.Task[None] | None = None


def install_windows_socket_exception_filter() -> None:
    if os.name != "nt":
        return
    loop = asyncio.get_running_loop()
    previous_handler = loop.get_exception_handler()

    def handle_loop_exception(current_loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
        error = context.get("exception")
        message = str(context.get("message") or "")
        winerror = getattr(error, "winerror", None)
        transient_accept_error = isinstance(error, OSError) and winerror in {64, 995, 10053, 10054}
        if transient_accept_error and ("accept" in message.lower() or "socket" in message.lower()):
            return
        if previous_handler:
            previous_handler(current_loop, context)
        else:
            current_loop.default_exception_handler(context)

    loop.set_exception_handler(handle_loop_exception)


async def resume_background_runtimes() -> None:
    await asyncio.to_thread(services.recover_orphaned_ant_task_instance)
    await release_runtime.resume_queue()
    await auto_video_runtime.resume_on_startup()
    await job_runtime.resume_on_startup()


@app.on_event("startup")
async def resume_release_queue_on_startup() -> None:
    global startup_recovery_task
    install_windows_socket_exception_filter()
    startup_recovery_task = asyncio.create_task(resume_background_runtimes())


@app.on_event("shutdown")
async def stop_background_runtime_recovery() -> None:
    global startup_recovery_task
    if startup_recovery_task and not startup_recovery_task.done():
        startup_recovery_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await startup_recovery_task
    startup_recovery_task = None


def tts_previews_static_root() -> Path:
    original = storage.APP_ROOT.parent / "_analysis" / "awesome_app_install" / "_internal" / "web" / "static" / "tts-previews"
    if original.exists():
        return original
    fallback = storage.DATA_ROOT / "tts-previews"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


class ModelSyncPayload(BaseModel):
    base_url: str = ""
    api_key: str = ""


class TemplatePayload(BaseModel):
    key: str
    name: str | None = None
    brand_name: str | None = None
    mode: str = "video"
    target_audience: str = ""
    channel_voice: str = ""
    visual_strategy: str = ""
    # A channel-level material/palette contract.  It is deliberately separate
    # from the long visual strategy so every image prompt can carry the same
    # visual language without repeating a full channel brief.
    visual_palette: dict[str, Any] | str = Field(default_factory=dict)
    forbidden_rules: str = ""
    image_style_prompt: str = ""
    image_negative_prompt: str = ""
    interaction_goal: str = ""
    topic_mining_hint: str = ""
    default_disclaimer: str = ""
    release_tags: str = ""
    cover_footnote_line_1: str = ""
    cover_footnote_line_2: str = ""
    cover_style: str = "default"
    voice_mode: str = ""
    tts_speaker_1: str = ""
    tts_speaker_2: str = ""
    tts_random_order: str | bool = ""
    tts_action: str | int = ""
    tts_speech_rate: float = 1.0
    generate_cover_landscape: bool = True
    generate_cover_portrait: bool = True
    prompt: str = ""
    version: str = ""


class TemplateVoiceSettingsPayload(BaseModel):
    voice_mode: str = "auto"
    tts_speaker_1: str = ""
    tts_speaker_2: str = ""
    tts_random_order: bool = False
    tts_speech_rate: float = 1.0


class ProjectCreatePayload(BaseModel):
    topic_name: str
    template: str
    content_type: str = "editorial"
    output_language: str = "zh-CN"


class TextPayload(BaseModel):
    brief: str | None = None
    content: str | None = None


class ProjectSettingsPayload(BaseModel):
    tavily_topic: str | None = None
    output_language: str | None = None
    scene_count_mode: str | None = None
    scene_count_fixed: int | None = None
    cover_enabled: bool | None = None
    content_type: str | None = None
    product_name: str | None = None
    product_category: str | None = None
    product_target_customer: str | None = None
    product_usage_scenarios: str | None = None
    product_selling_points: str | None = None
    product_evidence: str | None = None
    product_offer: str | None = None
    product_compliance_notes: str | None = None
    product_asset_files: list[str] | None = None


class ContentGeneratePayload(BaseModel):
    brief: str
    tavily_topic: str = "general"


class ToolPayload(BaseModel):
    brief: str | None = None
    content: str | None = None
    platform: str | None = None
    count: int = 6


class ProjectSourcePayload(BaseModel):
    type: str = "url"
    title: str = ""
    url: str = ""
    note: str = ""
    source: str = "用户资料"
    must_use: bool = True


class ProjectSourceSearchPayload(BaseModel):
    query: str
    current_news: bool = False
    limit: int = 8


class ProjectSourceUpdatePayload(BaseModel):
    must_use: bool | None = None
    title: str | None = None
    note: str | None = None




class JobPayload(BaseModel):
    steps: list[str]
    allow_incomplete_video: bool = False
    auto_recover: bool = True


class AutoVideoPayload(BaseModel):
    count: int = 1
    tavily_topic: str = "general"
    mining_prompt: str = ""
    steps: list[str] | None = None
    auto_confirm_images: bool = True
    selected_topics: list[dict[str, Any]] | None = None


class AutoTopicMinePayload(BaseModel):
    count: int = 6
    tavily_topic: str = "general"
    mining_prompt: str = ""


class ImageReviewPayload(BaseModel):
    required: bool | None = None
    confirmed: bool | None = None


class ImageRegeneratePayload(BaseModel):
    kind: str
    target: str
    prompt: str = ""
    anchor_key: str = ""
    abstraction_level: str = "balanced"
    additional_requirement: str = ""
    rewrite_prompt: bool = False
    rewrite_scope: str = "partial"
    as_candidate: bool = False


class ImageCandidateSelectPayload(BaseModel):
    scene_index: int
    variant: str


class ImageCandidateKeepPayload(BaseModel):
    scene_index: int


class CoverCandidateSelectPayload(BaseModel):
    variant: str = "B"


class BgmSettingsPayload(BaseModel):
    volume: float | None = None
    track_locked: bool | None = None


class MotionProfilePayload(BaseModel):
    selected: str


class ReleasePayload(BaseModel):
    platform: str
    url: str
    note: str = ""
    impressions: int | None = None
    click_through_rate: float | None = None
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    shares: int | None = None
    favorites: int | None = None
    follows: int | None = None
    two_second_retention_rate: float | None = None
    five_second_retention_rate: float | None = None
    average_watch_seconds: float | None = None
    completion_rate: float | None = None
    metrics_notes: str = ""


class ReleaseUpdatePayload(BaseModel):
    platform: str | None = None
    url: str | None = None
    note: str | None = None


class ReleaseMetricsPayload(BaseModel):
    impressions: int | None = None
    click_through_rate: float | None = None
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    shares: int | None = None
    favorites: int | None = None
    follows: int | None = None
    two_second_retention_rate: float | None = None
    five_second_retention_rate: float | None = None
    average_watch_seconds: float | None = None
    completion_rate: float | None = None
    notes: str = ""


class ReleaseMetricsSyncPayload(BaseModel):
    release_id: int | None = None
    account_name: str = ""
    platform: str = ""
    limit: int = Field(default=10, ge=1, le=20)


class ChannelPerformancePayload(BaseModel):
    sample_id: str = ""
    project_id: int | None = None
    release_id: int | None = None
    platform: str = ""
    topic: str = ""
    title: str = ""
    hook_text: str = ""
    duration_seconds: float | None = None
    observed_at: float | None = None
    source: str = "manual"
    metrics: ReleaseMetricsPayload


class ReleaseAutomationPayload(BaseModel):
    platform: str = "douyin"
    account_name: str = "default"
    title: str = ""
    description: str = ""
    tags: str = ""
    schedule: str = ""
    headed: bool = False
    debug: bool = False


class ReleaseBatchTarget(BaseModel):
    platform: str
    account_name: str = "default"


class ReleaseBatchPayload(BaseModel):
    targets: list[ReleaseBatchTarget] = Field(default_factory=list)
    title: str = ""
    description: str = ""
    tags: str = ""
    schedule: str = ""
    headed: bool = False
    debug: bool = False


class SecretsPayload(BaseModel):
    values: dict[str, str]


class SecretsValidatePayload(BaseModel):
    targets: list[str] | None = None


class ChatGPTLoginPayload(BaseModel):
    account_id: str | None = None


class PackagingBuildPayload(BaseModel):
    include_zip: bool = False


class ProjectFileOpenPayload(BaseModel):
    path: str


def ensure_project(project_id: int) -> dict[str, Any]:
    try:
        return storage.get_project(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def open_in_explorer(path: Path) -> dict[str, Any]:
    try:
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        return {"ok": True, "path": str(path)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"无法打开目录：{exc}") from exc


def open_path(path: Path) -> dict[str, Any]:
    try:
        if not path.exists():
            raise FileNotFoundError(path)
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        return {"ok": True, "path": str(path)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"路径不存在：{exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"无法打开路径：{exc}") from exc


def ensure_windows_file_read_access(path: Path) -> None:
    """Allow the interactive Windows player to read files created by the worker account."""
    if os.name != "nt":
        return
    result = subprocess.run(
        ["icacls", str(path), "/grant", "*S-1-5-32-545:(R)"],
        capture_output=True,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "未知权限错误").strip()
        raise PermissionError(detail)


@app.get("/api/templates")
def api_templates() -> list[dict[str, Any]]:
    return storage.list_templates()


@app.post("/api/templates")
def api_create_template(payload: TemplatePayload) -> dict[str, Any]:
    try:
        return storage.save_template(payload.key, payload.model_dump())
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/templates/{key}")
def api_get_template(key: str) -> dict[str, Any]:
    return storage.get_template(key)


@app.put("/api/templates/{key}")
def api_update_template(key: str, payload: TemplatePayload) -> dict[str, Any]:
    try:
        return storage.save_template(key, payload.model_dump())
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/templates/{key}/voice-settings")
def api_update_template_voice_settings(key: str, payload: TemplateVoiceSettingsPayload) -> dict[str, Any]:
    try:
        previous = storage.get_template(key)
        previous_settings = {
            "voice_mode": previous.get("voice_mode"),
            "tts_speaker_1": previous.get("tts_speaker_1"),
            "tts_speaker_2": previous.get("tts_speaker_2"),
            "tts_random_order": previous.get("tts_random_order"),
            "tts_speech_rate": previous.get("tts_speech_rate"),
        }
        template = storage.save_template_voice_settings(key, payload.model_dump())
        current_settings = {
            "voice_mode": template.get("voice_mode"),
            "tts_speaker_1": template.get("tts_speaker_1"),
            "tts_speaker_2": template.get("tts_speaker_2"),
            "tts_random_order": template.get("tts_random_order"),
            "tts_speech_rate": template.get("tts_speech_rate"),
        }
        return {
            **template,
            "voice_update": {
                "changed": previous_settings != current_settings,
                "affected_projects": 0,
                "invalidated_assets": [],
            },
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/templates/{key}")
def api_delete_template(key: str, delete_projects: bool = False) -> dict[str, Any]:
    try:
        return storage.delete_template(key, delete_projects=delete_projects)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/templates/open-root")
def api_open_templates_root() -> dict[str, Any]:
    return open_in_explorer(storage.TEMPLATES_ROOT)


@app.post("/api/templates/{key}/open-folder")
def api_open_template_folder(key: str) -> dict[str, Any]:
    return open_in_explorer(storage.TEMPLATES_ROOT / key)


@app.post("/api/templates/{key}/open-products-folder")
def api_open_template_products_folder(key: str) -> dict[str, Any]:
    return open_in_explorer(storage.build_template_products_dir(key))


@app.post("/api/templates/{key}/auto-topics/mine")
async def api_mine_template_auto_topics(key: str, payload: AutoTopicMinePayload | None = None) -> dict[str, Any]:
    payload = payload or AutoTopicMinePayload()
    try:
        template = storage.get_template(key)
        result = await asyncio.to_thread(
            services.mine_channel_topic,
            template,
            payload.tavily_topic,
            payload.mining_prompt,
            payload.count,
        )
        limit = max(1, min(int(payload.count or 6), 12))
        candidates = result.get("candidates") if isinstance(result.get("candidates"), list) else []
        result["candidates"] = candidates[:limit]
        result["template_key"] = key
        result["count"] = len(result["candidates"])
        return result
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/templates/{key}/auto-video")
async def api_start_template_auto_video(key: str, payload: AutoVideoPayload | None = None) -> dict[str, Any]:
    payload = payload or AutoVideoPayload()
    try:
        storage.get_template(key)
        return await auto_video_runtime.start(
            key,
            count=payload.count,
            tavily_topic=payload.tavily_topic,
            mining_prompt=payload.mining_prompt,
            steps=payload.steps,
            auto_confirm_images=payload.auto_confirm_images,
            selected_topics=payload.selected_topics,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/auto-video/latest")
def api_latest_auto_video() -> dict[str, Any]:
    task = auto_video_runtime.latest()
    return {"task": task, "running": bool(task and task.get("running"))}


@app.post("/api/auto-video/cancel")
async def api_cancel_auto_video() -> dict[str, Any]:
    return await auto_video_runtime.cancel()


@app.post("/api/auto-video/continue/{project_id}")
async def api_continue_auto_video(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    try:
        return await auto_video_runtime.continue_project(project_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.delete("/api/orphan-templates/{key}")
def api_delete_orphan_template(key: str) -> dict[str, Any]:
    try:
        return storage.delete_orphan_template(key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/projects")
def api_projects(template: str | None = None) -> list[dict[str, Any]]:
    if template:
        return storage.projects_for_template(template)
    return storage.list_projects()


@app.post("/api/projects")
def api_create_project(payload: ProjectCreatePayload) -> dict[str, Any]:
    if not payload.topic_name.strip():
        raise HTTPException(status_code=400, detail="topic_name 不能为空")
    return storage.create_project(
        payload.topic_name,
        payload.template,
        payload.content_type,
        payload.output_language,
    )


@app.get("/api/projects/{project_id}")
def api_get_project(project_id: int) -> dict[str, Any]:
    return ensure_project(project_id)


@app.delete("/api/projects/{project_id}")
def api_delete_project(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    storage.delete_project(project_id)
    return {"ok": True}


@app.get("/api/projects/{project_id}/content")
def api_project_content(project_id: int) -> dict[str, Any]:
    project = ensure_project(project_id)
    bundle = storage.content_bundle(project_id)
    content = str(bundle.get("content") or "")
    if content.strip():
        bundle["fact_registry"] = services.save_episode_fact_registry(project_id, content)
        summary = services.summarize_content(content, project.get("template_mode", "video"))
        current_summary = bundle.get("summary") if isinstance(bundle.get("summary"), dict) else {}
        for key in ("scene_count", "scene_count_aligned", "scene_count_script"):
            if key in current_summary:
                summary[key] = current_summary[key]
        if "scene_count" in current_summary and "scene_count_script" not in summary:
            summary["scene_count_script"] = current_summary["scene_count"]
        persisted_summary = storage.read_json(storage.project_file(project_id, "summary.json"), {})
        if summary != persisted_summary:
            storage.save_summary(project_id, summary)
        bundle["summary"] = summary
    bundle["content_generate"] = content_runtime.status(project_id)
    bundle["content_sync"] = content_sync_runtime.status(project_id)
    bundle["source_materials"] = services.list_project_sources(project_id)
    bundle["source_candidates"] = services.get_project_source_candidates(project_id)
    bundle["learning_explanation"] = storage.read_json(
        storage.project_file(project_id, "content_learning_explanation.json"), {}
    )
    return bundle


@app.get("/api/projects/{project_id}/content/references/{index}")
def api_project_reference(project_id: int, index: int) -> dict[str, Any]:
    ensure_project(project_id)
    try:
        return services.read_reference_preview(project_id, index)
    except IndexError as exc:
        raise HTTPException(status_code=404, detail="reference not found") from exc


@app.get("/api/projects/{project_id}/sources")
def api_project_sources(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    return {
        "items": services.list_project_sources(project_id),
        "candidates": services.get_project_source_candidates(project_id),
    }


@app.post("/api/projects/{project_id}/sources")
def api_add_project_source(project_id: int, payload: ProjectSourcePayload) -> dict[str, Any]:
    ensure_project(project_id)
    if not payload.url.strip() and not payload.note.strip():
        raise HTTPException(status_code=400, detail="链接或资料摘要至少填写一项")
    item = services.add_project_source(project_id, payload.model_dump())
    return {"ok": True, "item": item, "items": services.list_project_sources(project_id)}


@app.patch("/api/projects/{project_id}/sources/{source_id}")
def api_update_project_source(
    project_id: int,
    source_id: str,
    payload: ProjectSourceUpdatePayload,
) -> dict[str, Any]:
    ensure_project(project_id)
    items = services.list_project_sources(project_id)
    target = next((item for item in items if str(item.get("id") or "") == source_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="资料不存在")
    patch = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "must_use" in patch:
        target["must_use"] = bool(patch["must_use"])
    if "title" in patch:
        target["title"] = str(patch["title"] or "").strip()
    if "note" in patch:
        target["snippet"] = str(patch["note"] or "").strip()
    saved = services.save_project_sources(project_id, items)
    return {"ok": True, "item": target, "items": saved}


@app.delete("/api/projects/{project_id}/sources/{source_id}")
def api_delete_project_source(project_id: int, source_id: str) -> dict[str, Any]:
    ensure_project(project_id)
    return services.delete_project_source(project_id, source_id)


@app.post("/api/projects/{project_id}/sources/search")
async def api_search_project_sources(
    project_id: int,
    payload: ProjectSourceSearchPayload,
) -> dict[str, Any]:
    ensure_project(project_id)
    try:
        return await asyncio.to_thread(
            services.search_project_sources,
            project_id,
            payload.query,
            current_news=payload.current_news,
            limit=payload.limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/sources/candidates/{candidate_id}/adopt")
def api_adopt_project_source_candidate(project_id: int, candidate_id: str) -> dict[str, Any]:
    ensure_project(project_id)
    try:
        return services.adopt_project_source_candidate(project_id, candidate_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/sources/upload")
async def api_upload_project_source_image(
    project_id: int,
    file: UploadFile = File(...),
    title: str = "",
    note: str = "",
    must_use: bool = True,
) -> dict[str, Any]:
    ensure_project(project_id)
    original = storage.safe_name(file.filename or "source.png")
    suffix = Path(original).suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(status_code=400, detail=f"{original} 不是支持的图片格式")
    payload = await file.read()
    if len(payload) > 12 * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"{original} 超过 12MB")
    filename = original
    target = storage.project_file(project_id, f"uploads/sources/{filename}")
    if target.exists():
        filename = f"{Path(original).stem}-{storage.now_ms()}{suffix}"
        target = storage.project_file(project_id, f"uploads/sources/{filename}")
    storage.ensure_dir(target.parent)
    target.write_bytes(payload)
    item = services.add_project_source(
        project_id,
        {
            "type": "image",
            "title": title.strip() or Path(original).stem,
            "url": "",
            "note": note,
            "source": "用户图片",
            "must_use": must_use,
        },
    )
    items = services.list_project_sources(project_id)
    for current in items:
        if current.get("id") == item.get("id"):
            current["relative_path"] = f"uploads/sources/{filename}"
            current["filename"] = filename
            item = current
            break
    services.save_project_sources(project_id, items)
    services.mark_image_review_dirty(project_id, "参考图片已更新，后续场景图将使用新的图生图素材")
    return {"ok": True, "item": item, "items": items}


@app.post("/api/projects/{project_id}/brief")
def api_save_brief(project_id: int, payload: TextPayload) -> dict[str, Any]:
    ensure_project(project_id)
    storage.save_brief(project_id, payload.brief or "")
    content = storage.get_content(project_id)
    fact_registry = services.save_episode_fact_registry(project_id, content) if content.strip() else {}
    return {"ok": True, "fact_registry": fact_registry}


@app.post("/api/projects/{project_id}/content")
async def api_save_content(project_id: int, payload: TextPayload) -> dict[str, Any]:
    ensure_project(project_id)
    saved = services.save_project_content_bundle(
        project_id,
        payload.content or "",
        image_dirty_reason="文案语义已变化，受影响的场景图或封面需要重新确认",
        refresh_quality_report=False,
    )
    content = str(saved.get("content") or "")
    sync_state = await content_sync_runtime.start(project_id)
    manifest = services.refresh_production_manifest(project_id)
    return {
        "ok": True,
        "accepted": True,
        "content": content,
        "canonicalization": saved.get("canonicalization") or {},
        "fact_registry": saved.get("fact_registry") or {},
        "spoken_script": saved.get("spoken_script") or {},
        "visual_prompt_manifest": saved.get("visual_prompt_manifest") or {},
        "change_impact": saved.get("change_impact") or {},
        "sync": sync_state,
        "manifest": manifest,
        "summary": saved.get("summary") or {},
    }


@app.get("/api/projects/{project_id}/content/sync/status")
def api_content_sync_status(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    return content_sync_runtime.status(project_id) or {"status": "idle", "running": False}


@app.post("/api/projects/{project_id}/project-settings")
def api_save_project_settings(project_id: int, payload: ProjectSettingsPayload) -> dict[str, Any]:
    ensure_project(project_id)
    before_settings = storage.get_project_settings(project_id)
    patch = payload.model_dump(exclude_unset=True, exclude_none=True)
    storage.save_project_settings(project_id, patch)
    project_settings = storage.get_project_settings(project_id)
    language_changed = (
        "output_language" in patch
        and str(before_settings.get("output_language") or "zh-CN")
        != str(project_settings.get("output_language") or "zh-CN")
    )
    cover_only_changed = set(patch) == {"cover_enabled"}
    result: dict[str, Any] | None = None
    if language_changed:
        services.mark_image_review_dirty(
            project_id,
            "成片语言已切换；重新生成文案后，配音、字幕、图片文字和发布文案会使用新语言",
        )
        storage.write_json(
            storage.project_file(project_id, "output_language_change.json"),
            {
                "changed_at": storage.now_ts(),
                "from": before_settings.get("output_language") or "zh-CN",
                "to": project_settings.get("output_language") or "zh-CN",
                "requires_content_regeneration": True,
            },
        )
    elif storage.get_content(project_id).strip() and not cover_only_changed:
        with contextlib.suppress(Exception):
            result = services.repair_image_prompt_section(project_id)
        with contextlib.suppress(Exception):
            expected = int(storage.scene_status(project_id).get("expected_count", 0) or 0)
            if expected > 0:
                storage.cleanup_extra_scene_outputs(project_id, expected)
    return {
        "ok": True,
        "project_settings": project_settings,
        "project": storage.get_project(project_id),
        "repair": result,
        "language_changed": language_changed,
        "requires_content_regeneration": language_changed,
    }


@app.post("/api/projects/{project_id}/content/generate")
async def api_generate_content(project_id: int, payload: ContentGeneratePayload) -> dict[str, Any]:
    project = ensure_project(project_id)
    template = storage.get_template(project["template"])
    incoming_brief = payload.brief
    complete_brief = storage.latest_complete_brief(project_id)
    if complete_brief and len(incoming_brief) < len(complete_brief) * 0.45:
        storage.write_text(storage.project_file(project_id, "generation_request.md"), incoming_brief)
        incoming_brief = complete_brief
    storage.save_brief(project_id, incoming_brief)
    storage.save_project_settings(project_id, {"tavily_topic": payload.tavily_topic})
    creative_learning.prepare_project_research_plan(project_id, incoming_brief)
    services.mark_image_review_dirty(project_id, "正在重新生成 content.md，图片需要重新确认")
    state = await content_runtime.start(project, template, incoming_brief, payload.tavily_topic)
    return state


@app.get("/api/projects/{project_id}/content/generate/status")
def api_content_generate_status(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    return content_runtime.status(project_id) or {"status": "idle"}


@app.post("/api/projects/{project_id}/content/generate/cancel")
async def api_cancel_content_generate(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    return await content_runtime.cancel(project_id)


@app.post("/api/projects/{project_id}/content/tools/topic-score")
def api_topic_score(project_id: int, payload: ToolPayload) -> dict[str, Any]:
    project = ensure_project(project_id)
    result = services.topic_score_report(project, payload.brief or storage.get_brief(project_id))
    path = storage.save_report(project_id, "topic_score", result)
    return {"report_path": str(path), "result": result}


@app.get("/api/projects/{project_id}/content/tools/topic-score")
def api_get_topic_score(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    report = storage.get_report(project_id, "topic_score")
    if not report:
        raise HTTPException(status_code=404, detail="暂无选题评分")
    return {"report_path": str(storage.report_path(project_id, "topic_score")), "result": report}


@app.post("/api/projects/{project_id}/content/tools/viral-doctor")
def api_viral_doctor(project_id: int, payload: ToolPayload) -> dict[str, Any]:
    project = ensure_project(project_id)
    result = services.viral_doctor_report(project, payload.content or storage.get_content(project_id))
    path = storage.save_report(project_id, "viral_doctor", result)
    return {"report_path": str(path), "result": result}


@app.get("/api/projects/{project_id}/content/tools/viral-doctor")
def api_get_viral_doctor(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    report = storage.get_report(project_id, "viral_doctor")
    if not report:
        raise HTTPException(status_code=404, detail="暂无脚本体检报告")
    return {"report_path": str(storage.report_path(project_id, "viral_doctor")), "result": report}


@app.post("/api/projects/{project_id}/content/tools/viral-rewrite")
def api_viral_rewrite(project_id: int, payload: ToolPayload) -> dict[str, Any]:
    ensure_project(project_id)
    try:
        return services.optimize_project_content(project_id, payload.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/content/tools/channel-history")
def api_channel_history(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    result = services.channel_history_report(project_id)
    path = storage.save_report(project_id, "channel_history", result)
    return {"report_path": str(path), "result": result}


@app.get("/api/projects/{project_id}/creative-intelligence")
def api_project_creative_intelligence(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    return creative_learning.project_creative_intelligence(project_id, refresh=False)


@app.post("/api/projects/{project_id}/creative-intelligence/refresh")
def api_refresh_project_creative_intelligence(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    result = creative_learning.project_creative_intelligence(project_id, refresh=True)
    creative_learning.append_learning_event(
        "creative_intelligence_refreshed",
        project_id,
        {
            "recipe_fingerprint": result.get("recipe", {}).get("fingerprint"),
            "evidence_fingerprint": result.get("evidence", {}).get("fingerprint"),
        },
    )
    return result






@app.get("/api/learning/recipes")
def api_learning_recipes() -> list[dict[str, Any]]:
    return creative_learning.list_channel_recipes(refresh=False)


@app.post("/api/learning/recipes/refresh")
def api_refresh_learning_recipes() -> list[dict[str, Any]]:
    return creative_learning.list_channel_recipes(refresh=True)


@app.post("/api/learning/dataset/rebuild")
def api_rebuild_learning_dataset() -> dict[str, Any]:
    return creative_learning.rebuild_training_dataset()


@app.get("/api/learning/channels/{template_key}/performance-memory")
def api_channel_performance_memory(template_key: str) -> dict[str, Any]:
    storage.get_template(template_key)
    return creative_learning.rebuild_channel_performance_memory(template_key)


@app.post("/api/learning/channels/{template_key}/performance-memory")
def api_record_channel_performance(template_key: str, payload: ChannelPerformancePayload) -> dict[str, Any]:
    storage.get_template(template_key)
    sample = payload.model_dump()
    metrics = sample.get("metrics")
    sample["metrics"] = metrics if isinstance(metrics, dict) else {}
    return creative_learning.record_channel_performance(template_key, sample)


@app.get("/api/learning/providers")
def api_learning_providers() -> list[dict[str, Any]]:
    return creative_learning.provider_catalog()


@app.post("/api/projects/{project_id}/content/tools/optimization-plan")
def api_creative_optimization_plan(project_id: int, payload: ToolPayload) -> dict[str, Any]:
    ensure_project(project_id)
    result = services.creative_optimization_plan(project_id, payload.content)
    path = storage.save_report(project_id, "creative_optimization_plan", result)
    return {"report_path": str(path), "result": result}


@app.post("/api/projects/{project_id}/content/tools/image-prompt-layers")
def api_image_prompt_layers(project_id: int, payload: ToolPayload) -> dict[str, Any]:
    ensure_project(project_id)
    result = services.image_prompt_layer_report(project_id, payload.content)
    path = storage.save_report(project_id, "image_prompt_layers", result)
    return {"report_path": str(path), "result": result}


@app.post("/api/projects/{project_id}/content/tools/ai-supervisors")
def api_ai_supervisors(project_id: int, payload: ToolPayload) -> dict[str, Any]:
    ensure_project(project_id)
    try:
        result = services.ai_editorial_review_for_project(project_id, payload.content)
    except services.ContentGenerationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    path = storage.save_report(project_id, "editorial_ai_score", result)
    return {"report_path": str(path), "result": result}


@app.post("/api/projects/{project_id}/content/tools/visual-brief")
def api_visual_brief(project_id: int, payload: ToolPayload) -> dict[str, Any]:
    ensure_project(project_id)
    result = services.save_visual_brief(project_id, payload.content)
    return {"report_path": str(services.visual_brief_path(project_id)), "result": result}


@app.post("/api/projects/{project_id}/content/tools/visual-director")
def api_visual_director(project_id: int, payload: ToolPayload) -> dict[str, Any]:
    ensure_project(project_id)
    visual_brief = services.save_visual_brief(project_id, payload.content)
    result = services.save_visual_director(project_id, payload.content, visual_brief=visual_brief)
    return {"report_path": str(services.visual_director_path(project_id)), "result": result}


@app.post("/api/projects/{project_id}/content/tools/video-spec")
def api_video_spec(project_id: int, payload: ToolPayload) -> dict[str, Any]:
    ensure_project(project_id)
    try:
        result = services.save_video_spec(project_id, payload.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    path = storage.project_file(project_id, "video_spec.json")
    return {"report_path": str(path), "result": result}


@app.post("/api/projects/{project_id}/content/tools/rhythm")
def api_script_rhythm(project_id: int, payload: ToolPayload) -> dict[str, Any]:
    ensure_project(project_id)
    result = services.script_rhythm_report(project_id, payload.content)
    path = storage.save_report(project_id, "script_rhythm", result)
    return {"report_path": str(path), "result": result}


@app.post("/api/projects/{project_id}/content/tools/rhythm-enhance")
def api_script_rhythm_enhance(project_id: int, payload: ToolPayload) -> dict[str, Any]:
    ensure_project(project_id)
    try:
        return services.enhance_content_rhythm(project_id, payload.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/content/tools/title-cover-ab")
def api_title_cover_ab(project_id: int, payload: ToolPayload) -> dict[str, Any]:
    project = ensure_project(project_id)
    result = services.title_cover_ab_report(project, payload.content or storage.get_content(project_id), payload.count)
    path = storage.save_report(project_id, "title_cover_ab", result)
    return {"report_path": str(path), "result": result}


@app.get("/api/projects/{project_id}/content/tools/title-cover-ab")
def api_get_title_cover_ab(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    report = storage.get_report(project_id, "title_cover_ab")
    if not report:
        raise HTTPException(status_code=404, detail="暂无标题封面方案")
    return {"report_path": str(storage.report_path(project_id, "title_cover_ab")), "result": report}


@app.post("/api/projects/{project_id}/quality-gate")
def api_quality_gate(project_id: int, payload: TextPayload | None = None) -> dict[str, Any]:
    ensure_project(project_id)
    payload = payload or TextPayload()
    result = services.quality_gate_report(project_id, brief=payload.brief, content=payload.content)
    path = storage.save_report(project_id, "quality_gate", result)
    return {"report_path": str(path), "result": result}


@app.get("/api/projects/{project_id}/quality-gate")
def api_get_quality_gate(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    report = storage.get_report(project_id, "quality_gate")
    if not report:
        raise HTTPException(status_code=404, detail="暂无质量总检报告")
    return {"report_path": str(storage.report_path(project_id, "quality_gate")), "result": report}


@app.get("/api/projects/{project_id}/stage-gates")
def api_stage_gates(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    result = services.production_stage_gates_dashboard(project_id)
    return {"report_path": str(storage.report_path(project_id, "stage_gates")), "result": result}


@app.post("/api/projects/{project_id}/stage-gates/evaluate")
async def api_evaluate_stage_gates(project_id: int) -> dict[str, Any]:
    project = ensure_project(project_id)
    try:
        job = await job_runtime.start(
            project,
            [f"gate-check:{gate_key}" for gate_key in services.STAGE_GATE_DEFS],
            False,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "accepted": True,
        "job": job,
        "report_path": str(storage.report_path(project_id, "stage_gates")),
        "dashboard": services.production_stage_gates_dashboard(project_id),
    }


@app.post("/api/projects/{project_id}/stage-gates/{gate_key}/run")
async def api_run_stage_gate(project_id: int, gate_key: str) -> dict[str, Any]:
    project = ensure_project(project_id)
    if gate_key not in services.STAGE_GATE_DEFS:
        raise HTTPException(status_code=404, detail=f"未知生产闸门：{gate_key}")
    try:
        job = await job_runtime.start(project, [f"gate-fix:{gate_key}"], False)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "accepted": True,
        "job": job,
        "report_path": str(storage.report_path(project_id, "stage_gates")),
        "dashboard": services.production_stage_gates_dashboard(project_id),
    }


@app.post("/api/projects/{project_id}/stage-gates/{gate_key}/accept")
def api_accept_stage_gate(project_id: int, gate_key: str) -> dict[str, Any]:
    ensure_project(project_id)
    try:
        result = services.accept_production_stage_gate(project_id, gate_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "accepted": True,
        "result": result,
        "report_path": str(storage.report_path(project_id, "stage_gates")),
        "dashboard": services.production_stage_gates_dashboard(project_id),
    }


@app.post("/api/projects/{project_id}/quality-gate/repair-image-prompts")
def api_repair_quality_image_prompts(project_id: int, payload: TextPayload | None = None) -> dict[str, Any]:
    ensure_project(project_id)
    payload = payload or TextPayload()
    result = services.repair_image_prompt_section(project_id, content=payload.content)
    return result


@app.get("/api/projects/{project_id}/scene-prompt")
def api_scene_prompt(project_id: int, filename: str) -> dict[str, Any]:
    ensure_project(project_id)
    return services.scene_prompt(project_id, filename)


@app.get("/api/projects/{project_id}/image-prompt")
def api_image_prompt(
    project_id: int,
    kind: str,
    target: str,
    anchor_key: str = "",
    abstraction_level: str = "",
) -> dict[str, Any]:
    ensure_project(project_id)
    try:
        return services.image_prompt(project_id, kind, target, anchor_key=anchor_key, abstraction_level=abstraction_level)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/image-prompt/preview")
def api_image_prompt_preview(project_id: int, payload: ImageRegeneratePayload) -> dict[str, Any]:
    ensure_project(project_id)
    try:
        return services.compile_final_chatgpt_image_prompt(
            project_id,
            payload.kind,
            payload.target,
            anchor_key=payload.anchor_key,
            abstraction_level=payload.abstraction_level,
            additional_requirement=payload.additional_requirement,
            rewrite_prompt=payload.rewrite_prompt,
            rewrite_scope=payload.rewrite_scope,
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}/image-review")
def api_image_review(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    return services.image_review_status(project_id)


@app.get("/api/projects/{project_id}/status")
def api_project_status(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    return services.project_status_report(project_id)


@app.get("/api/projects/{project_id}/production-manifest")
def api_production_manifest(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    return services.refresh_production_manifest(project_id)


@app.get("/api/projects/{project_id}/bgm/status")
def api_project_bgm_status(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    return services.project_bgm_status(project_id)


@app.get("/api/projects/{project_id}/voice/status")
def api_project_voice_status(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    return services.project_tts_voice_status(project_id)


@app.get("/api/projects/{project_id}/bgm/audio")
def api_project_bgm_audio(project_id: int) -> FileResponse:
    ensure_project(project_id)
    status = services.project_bgm_status(project_id)
    path_value = str(status.get("path") or "").strip()
    path = Path(path_value) if path_value else None
    if not path or not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="当前项目还没有可试听的背景音乐。")
    media_types = {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".m4a": "audio/mp4",
        ".aac": "audio/aac",
    }
    return FileResponse(
        path,
        media_type=media_types.get(path.suffix.lower(), "application/octet-stream"),
        filename=path.name,
        content_disposition_type="inline",
    )


@app.post("/api/projects/{project_id}/bgm/settings")
def api_project_bgm_settings(project_id: int, payload: BgmSettingsPayload) -> dict[str, Any]:
    ensure_project(project_id)
    services.update_project_bgm_settings(
        project_id,
        volume=payload.volume,
        track_locked=payload.track_locked,
    )
    return services.project_bgm_status(project_id)


@app.get("/api/projects/{project_id}/bgm/mix-preview")
def api_project_bgm_mix_preview(project_id: int) -> FileResponse:
    ensure_project(project_id)
    try:
        result = services.ensure_project_bgm_mix_preview(project_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    path = Path(str(result.get("path") or ""))
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="混音试听文件尚未生成。")
    return FileResponse(
        path,
        media_type="audio/mpeg",
        filename=path.name,
        content_disposition_type="inline",
    )


@app.get("/api/projects/{project_id}/video-preflight")
def api_video_preflight(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    result = services.video_preflight_report(project_id)
    path = storage.save_report(project_id, "video_preflight", result)
    return {"report_path": str(path), "result": result}


@app.get("/api/projects/{project_id}/motion-samples")
def api_motion_samples(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    manifest = storage.read_json(services.motion_samples_manifest_path(project_id), {})
    manifest = manifest if isinstance(manifest, dict) else {}
    manifest["selected"] = services.project_motion_profile(project_id)["selected"]
    return manifest


@app.post("/api/projects/{project_id}/motion-samples")
async def api_generate_motion_samples(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    try:
        return await asyncio.to_thread(services.generate_motion_sample_variants, project_id)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/motion-profile")
def api_select_motion_profile(project_id: int, payload: MotionProfilePayload) -> dict[str, Any]:
    ensure_project(project_id)
    try:
        profile = services.save_project_motion_profile(project_id, payload.selected)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"profile": profile}


@app.get("/api/projects/{project_id}/resume-plan")
def api_resume_plan(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    return services.production_resume_plan(project_id)


@app.post("/api/projects/{project_id}/video-preflight/repair-timeline")
def api_repair_video_preflight_timeline(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    try:
        result = services.repair_scene_timeline(project_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    path = storage.save_report(project_id, "video_preflight", result["after"])
    return {"report_path": str(path), **result}


@app.post("/api/projects/{project_id}/video-preflight/reuse-images")
def api_reuse_video_preflight_images(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    try:
        result = services.reuse_current_images_for_content(project_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    after = services.video_preflight_report(project_id)
    path = storage.save_report(project_id, "video_preflight", after)
    return {"report_path": str(path), "after": after, **result}


@app.post("/api/projects/{project_id}/video-preflight/ignore-image-quality")
def api_ignore_video_preflight_image_quality(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    try:
        result = services.ignore_soft_image_quality_for_video(project_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    quality = services.quality_gate_report(project_id)
    storage.save_report(project_id, "quality_gate", quality)
    after = services.video_preflight_report(project_id)
    path = storage.save_report(project_id, "video_preflight", after)
    return {"report_path": str(path), "after": after, "quality_gate": quality, **result}


@app.post("/api/projects/{project_id}/video-self-check")
def api_video_self_check(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    result = services.run_video_self_check(project_id)
    return {"report_path": str(storage.report_path(project_id, "video_self_check")), "result": result}


@app.post("/api/projects/{project_id}/image-review")
async def api_save_image_review(project_id: int, payload: ImageReviewPayload) -> dict[str, Any]:
    ensure_project(project_id)
    latest = job_runtime.latest(project_id)
    if payload.required is False and latest and latest.get("running"):
        raise HTTPException(status_code=409, detail="图片任务仍在运行，请等待候选生成完成后再切换全自动模式。")
    try:
        auto_resolution: dict[str, Any] | None = None
        cover_auto_resolution: dict[str, Any] | None = None
        if payload.required is False:
            auto_resolution = await asyncio.to_thread(services.resolve_scene_candidates_automatically, project_id)
            if auto_resolution.get("skipped_count"):
                skipped = auto_resolution.get("skipped") or []
                scene_labels = "、".join(str(item.get("scene_index")) for item in skipped if isinstance(item, dict))
                raise ValueError(f"场景 {scene_labels or '未知'} 的候选图尚未完整保存，暂时不能切换全自动。请刷新后重试。")
            cover_auto_resolution = await asyncio.to_thread(services.resolve_cover_candidates_automatically, project_id)
        status = services.save_image_review_status(
            project_id,
            required=payload.required,
            confirmed=payload.confirmed,
        )
        if auto_resolution is not None:
            status["auto_resolution"] = auto_resolution
        if cover_auto_resolution is not None:
            status["cover_auto_resolution"] = cover_auto_resolution
        return status
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/images/regenerate")
async def api_regenerate_project_image(project_id: int, payload: ImageRegeneratePayload) -> dict[str, Any]:
    ensure_project(project_id)
    if not payload.additional_requirement.strip():
        raise HTTPException(status_code=400, detail="请先填写这次要增加、删除或改变的内容，并重做提示词。")
    if not payload.prompt.strip():
        raise HTTPException(status_code=400, detail="AI 重写提示词尚未完成，本次重绘未启动。")
    latest = job_runtime.latest(project_id)
    if latest and latest.get("running"):
        raise HTTPException(status_code=409, detail="当前项目有生产任务正在运行，请先停止或等待完成后再重绘图片。")
    try:
        return await asyncio.to_thread(
            services.regenerate_project_image,
            project_id,
            payload.kind,
            payload.target,
            payload.prompt,
            payload.anchor_key,
            payload.abstraction_level,
            payload.additional_requirement,
            payload.as_candidate,
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=services.user_facing_error(exc)) from exc

@app.get("/api/projects/{project_id}/scene-images/status")
def api_scene_images_status(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    now = time.monotonic()
    with _SCENE_STATUS_CACHE_LOCK:
        cached = _SCENE_STATUS_CACHE.get(project_id)
        if cached and now - cached[0] < _SCENE_STATUS_CACHE_TTL_SECONDS:
            return copy.deepcopy(cached[1])
    latest = job_runtime.latest(project_id)
    recovered: list[dict[str, Any]] = []
    pruned: list[dict[str, Any]] = []
    auto_resolution: dict[str, Any] | None = None
    if not latest or not latest.get("running"):
        pruned = services.prune_finished_scene_candidates(project_id)
        recovered = services.recover_orphaned_scene_candidates(project_id)
        review_status = services.image_review_status(project_id)
        if review_status.get("required") is False:
            auto_resolution = services.resolve_scene_candidates_automatically(project_id)
    result = storage.scene_status(project_id)
    stale_indexes = set(services.stale_scene_image_indexes(project_id))
    if stale_indexes:
        stale_existing = []
        current_existing = []
        for item in result.get("existing", []):
            if int(item.get("index", 0) or 0) in stale_indexes:
                stale_existing.append(
                    {
                        **item,
                        "lineage_stale": True,
                        "prompt_pending_redraw": True,
                        "status_label": "旧主题已隔离",
                    }
                )
            else:
                current_existing.append(item)
        result["existing"] = current_existing
        result["stale_existing"] = stale_existing
        result["stale_indexes"] = sorted(stale_indexes)
        result["stale_count"] = len(stale_existing)
        result["generated_count"] = len(current_existing)
        missing_indexes = {
            int(item.get("index", 0) or 0)
            for item in result.get("missing_items", [])
            if int(item.get("index", 0) or 0) > 0
        }
        missing_indexes.update(
            index
            for index in stale_indexes
            if 0 < index <= int(result.get("expected_count", 0) or 0)
        )
        result["missing"] = [f"s_{index:02d}" for index in sorted(missing_indexes)]
        result["missing_items"] = [
            {
                "filename": f"s_{index:02d}.png",
                "stem": f"s_{index:02d}",
                "index": index,
                "expected_path": f"scenes/s_{index:02d}.png",
                "reason": "lineage_stale" if index in stale_indexes else "missing",
            }
            for index in sorted(missing_indexes)
        ]
        result["complete"] = False
    if recovered:
        result["recovered_candidates"] = recovered
    if pruned:
        result["pruned_candidates"] = pruned
    if auto_resolution and auto_resolution.get("resolved_count"):
        result["auto_resolved_candidates"] = auto_resolution.get("resolved", [])
    with _SCENE_STATUS_CACHE_LOCK:
        _SCENE_STATUS_CACHE[project_id] = (time.monotonic(), copy.deepcopy(result))
    return result


@app.get("/api/projects/{project_id}/production-architecture")
def api_project_production_architecture(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    latest = storage.load_latest_job(project_id) or {}
    steps = latest.get("steps") if isinstance(latest.get("steps"), list) else []
    if not steps:
        steps = ["audio", "subtitles", "images", "covers", "motion_clips", "video"]
    return {
        "version": capsule_architecture.ARCHITECTURE_VERSION,
        "delivery_promise": capsule_architecture.build_delivery_promise(project_id),
        "storyboard": capsule_architecture.build_storyboard_contract(project_id),
        "production_plan": capsule_architecture.build_production_plan(project_id, steps),
        "latest_run": latest.get("architecture") if isinstance(latest.get("architecture"), dict) else {},
    }


@app.post("/api/projects/{project_id}/scene-images/candidates/select")
async def api_select_scene_image_candidate(
    project_id: int,
    payload: ImageCandidateSelectPayload,
) -> dict[str, Any]:
    ensure_project(project_id)
    latest = job_runtime.latest(project_id)
    if latest and latest.get("running"):
        raise HTTPException(status_code=409, detail="图片任务仍在运行，请等待当前候选生成完成后再选择。")
    try:
        result = await asyncio.to_thread(
            services.select_scene_image_candidate,
            project_id,
            payload.scene_index,
            payload.variant,
        )
        creative_learning.append_learning_event(
            "visual_candidate_selected",
            project_id,
            {
                "scene_index": payload.scene_index,
                "selected_variant": payload.variant,
                "result": result,
            },
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/cover-images/candidates/select")
async def api_select_cover_candidate(
    project_id: int,
    payload: CoverCandidateSelectPayload,
) -> dict[str, Any]:
    ensure_project(project_id)
    latest = job_runtime.latest(project_id)
    if latest and latest.get("running"):
        raise HTTPException(status_code=409, detail="封面任务仍在运行，请等待当前候选生成完成后再选择。")
    try:
        result = await asyncio.to_thread(services.select_cover_candidate, project_id, payload.variant)
        creative_learning.append_learning_event(
            "cover_candidate_selected",
            project_id,
            {"selected_variant": payload.variant, "result": result},
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/cover-images/candidates/keep-current")
async def api_keep_current_cover(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    latest = job_runtime.latest(project_id)
    if latest and latest.get("running"):
        raise HTTPException(status_code=409, detail="封面任务仍在运行，请等待当前候选生成完成后再选择。")
    try:
        result = await asyncio.to_thread(services.keep_current_cover, project_id)
        creative_learning.append_learning_event(
            "cover_candidate_selected",
            project_id,
            {"selected_variant": "CURRENT", "result": result},
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/scene-images/candidates/keep-current")
async def api_keep_current_scene_image(
    project_id: int,
    payload: ImageCandidateKeepPayload,
) -> dict[str, Any]:
    ensure_project(project_id)
    latest = job_runtime.latest(project_id)
    if latest and latest.get("running"):
        raise HTTPException(status_code=409, detail="图片任务仍在运行，请等待当前候选生成完成后再选择。")
    try:
        result = await asyncio.to_thread(
            services.keep_current_scene_image,
            project_id,
            payload.scene_index,
        )
        creative_learning.append_learning_event(
            "visual_candidate_selected",
            project_id,
            {
                "scene_index": payload.scene_index,
                "selected_variant": "CURRENT",
                "result": result,
            },
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/jobs")
async def api_start_job(project_id: int, payload: JobPayload) -> dict[str, Any]:
    project = ensure_project(project_id)
    content_state = storage.read_json(storage.project_file(project_id, "content_generate.json"), {})
    content_state = content_state if isinstance(content_state, dict) else {}
    if str(content_state.get("status") or "").strip().lower() == "running":
        stage = str(content_state.get("stage") or "write").strip() or "write"
        raise HTTPException(
            status_code=409,
            detail=f"文案正在生成（{stage}），完成后全自动任务会继续后续流程；本次重复启动已忽略。",
        )
    if not storage.get_content(project_id).strip():
        raise HTTPException(
            status_code=409,
            detail="当前文案为空，请先完成文案生成；正文写入后再启动配音、字幕、图片和成片。",
        )
    try:
        return await job_runtime.start(
            project,
            payload.steps,
            payload.allow_incomplete_video,
            auto_recover=payload.auto_recover,
            origin="manual",
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}/jobs/latest")
def api_latest_job(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    job = job_runtime.latest(project_id)
    return {"job": job, "running": bool(job and job.get("running")), "log_available": bool(job)}


@app.delete("/api/projects/{project_id}/jobs/latest/log")
def api_clear_latest_job_log(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    job = storage.clear_latest_job_log(project_id)
    return {"job": job, "running": bool(job.get("running")), "log_available": False}


@app.post("/api/jobs/{job_id}/cancel")
async def api_cancel_job(job_id: str) -> dict[str, Any]:
    return await job_runtime.cancel(job_id)


@app.get("/api/projects/{project_id}/files")
def api_project_files(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    files = storage.list_project_files(project_id)
    topics = [
        item
        for item in files
        if item["relative_path"]
        in {
            "brief.md",
            "content.md",
            "summary.json",
            "references.json",
            "content_strategy.json",
            "content_audit.json",
            "auto_topic.json",
            "auto_video.json",
            "video_spec.json",
            "reports/quality_gate.json",
            "audio/scene_plan.json",
        }
    ]
    outputs = [item for item in files if item not in topics]
    lookup = {item["relative_path"]: item for item in files}
    return {
        "project_root": str(storage.project_dir(project_id)),
        "releases_root": str(storage.project_file(project_id, "releases")),
        "topics": topics,
        "outputs": outputs,
        "artifacts": {
            "final_video": lookup.get("releases/final-video.mp4"),
            "final_preview": lookup.get("releases/final-preview.html"),
            "release_note": lookup.get("releases/final-video.txt"),
            "video_spec": lookup.get("video_spec.json"),
            "scene_plan": lookup.get("audio/scene_plan.json"),
        },
    }


@app.delete("/api/projects/{project_id}/files")
def api_delete_file(project_id: int, relative_path: str) -> dict[str, Any]:
    ensure_project(project_id)
    path = storage.project_file(project_id, relative_path)
    if path.exists():
        path.unlink()
    return {"ok": True}


@app.post("/api/projects/{project_id}/files/batch-delete")
def api_batch_delete(project_id: int, payload: dict[str, list[str]]) -> dict[str, Any]:
    ensure_project(project_id)
    for relative in payload.get("relative_paths", []):
        path = storage.project_file(project_id, relative)
        if path.exists() and path.is_file():
            path.unlink()
    return {"ok": True}


@app.post("/api/projects/{project_id}/uploads")
async def api_upload_files(project_id: int, files: list[UploadFile] = File(...), slot: str = "uploads") -> dict[str, Any]:
    ensure_project(project_id)
    saved = []
    for item in files:
        filename = storage.safe_name(item.filename or "upload.bin")
        path = storage.project_file(project_id, f"{slot}/{filename}")
        storage.ensure_dir(path.parent)
        path.write_bytes(await item.read())
        saved.append(filename)
    return {"saved": saved}


def product_assets_payload(project_id: int) -> dict[str, Any]:
    settings = storage.get_project_settings(project_id)
    allowed = set(settings.get("product_asset_files") or [])
    assets = [
        item
        for item in storage.list_project_files(project_id)
        if item.get("relative_path", "").startswith("uploads/products/") and item.get("name") in allowed
    ]
    return {"assets": assets, "project_settings": settings}


@app.get("/api/projects/{project_id}/product-assets")
def api_product_assets(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    return product_assets_payload(project_id)


@app.post("/api/projects/{project_id}/product-assets")
async def api_upload_product_assets(project_id: int, files: list[UploadFile] = File(...)) -> dict[str, Any]:
    ensure_project(project_id)
    settings = storage.get_project_settings(project_id)
    existing = list(settings.get("product_asset_files") or [])
    allowed_suffixes = {".png", ".jpg", ".jpeg", ".webp"}
    for item in files[:10]:
        original = storage.safe_name(item.filename or "product.png")
        suffix = Path(original).suffix.lower()
        if suffix not in allowed_suffixes:
            raise HTTPException(status_code=400, detail=f"{original} 不是支持的商品图片格式")
        payload = await item.read()
        if len(payload) > 12 * 1024 * 1024:
            raise HTTPException(status_code=400, detail=f"{original} 超过 12MB")
        stem = Path(original).stem or "product"
        filename = original
        target = storage.project_file(project_id, f"uploads/products/{filename}")
        if target.exists() or filename in existing:
            filename = f"{stem}-{storage.now_ms()}{suffix}"
            target = storage.project_file(project_id, f"uploads/products/{filename}")
        storage.ensure_dir(target.parent)
        target.write_bytes(payload)
        existing.append(filename)
    settings["content_type"] = "product"
    retained = existing[-10:]
    discarded = set(existing) - set(retained)
    for filename in discarded:
        stale_path = storage.project_file(project_id, f"uploads/products/{storage.safe_name(filename)}")
        if stale_path.exists() and stale_path.is_file():
            stale_path.unlink()
    settings["product_asset_files"] = retained
    storage.save_project_settings(project_id, settings)
    services.mark_image_review_dirty(project_id, "商品参考图已更新，后续生图将按新参考图生成")
    return product_assets_payload(project_id)


@app.delete("/api/projects/{project_id}/product-assets/{filename}")
def api_delete_product_asset(project_id: int, filename: str) -> dict[str, Any]:
    ensure_project(project_id)
    safe_filename = storage.safe_name(filename)
    path = storage.project_file(project_id, f"uploads/products/{safe_filename}")
    if path.exists() and path.is_file():
        path.unlink()
    settings = storage.get_project_settings(project_id)
    settings["product_asset_files"] = [
        item for item in settings.get("product_asset_files", []) if item != safe_filename
    ]
    storage.save_project_settings(project_id, settings)
    services.mark_image_review_dirty(project_id, "商品参考图已调整，图片需要重新确认")
    return product_assets_payload(project_id)


@app.post("/api/projects/{project_id}/open-folder")
def api_open_project_folder(project_id: int, subpath: str | None = None) -> dict[str, Any]:
    ensure_project(project_id)
    target = storage.project_dir(project_id)
    if subpath:
        target = target / subpath
    return open_in_explorer(target)


@app.post("/api/projects/{project_id}/open-file")
def api_open_project_file(project_id: int, payload: ProjectFileOpenPayload) -> dict[str, Any]:
    ensure_project(project_id)
    root = storage.project_dir(project_id).resolve()
    relative = Path(payload.path)
    if relative.is_absolute():
        raise HTTPException(status_code=400, detail="只能打开当前项目内的文件")
    target = (root / relative).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="只能打开当前项目内的文件") from exc
    if not target.is_file():
        raise HTTPException(status_code=404, detail=f"文件不存在：{payload.path}")
    try:
        ensure_windows_file_read_access(target)
        return open_path(target)
    except PermissionError as exc:
        raise HTTPException(status_code=500, detail=f"无法为播放器授予文件读取权限：{exc}") from exc


@app.get("/api/projects/{project_id}/releases")
def api_release_links(project_id: int) -> list[dict[str, Any]]:
    ensure_project(project_id)
    result: list[dict[str, Any]] = []
    for raw in storage.get_release_links(project_id):
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        item["performance"] = services.release_performance_signal(item)
        result.append(item)
    return result


@app.post("/api/projects/{project_id}/releases")
def api_create_release_link(project_id: int, payload: ReleasePayload) -> dict[str, Any]:
    ensure_project(project_id)
    links = storage.get_release_links(project_id)
    metrics_payload = {
        "impressions": payload.impressions,
        "click_through_rate": payload.click_through_rate,
        "views": payload.views,
        "likes": payload.likes,
        "comments": payload.comments,
        "shares": payload.shares,
        "favorites": payload.favorites,
        "follows": payload.follows,
        "two_second_retention_rate": payload.two_second_retention_rate,
        "five_second_retention_rate": payload.five_second_retention_rate,
        "average_watch_seconds": payload.average_watch_seconds,
        "completion_rate": payload.completion_rate,
        "notes": payload.metrics_notes,
    }
    item = {
        "id": storage.next_release_id(),
        "platform": payload.platform,
        "url": payload.url,
        "note": payload.note,
        "created_at": storage.now_ts(),
    }
    if any(value not in (None, "", 0) for value in metrics_payload.values()):
        item["metrics"] = services.normalize_release_metrics(metrics_payload)
    links.append(item)
    storage.save_release_links(project_id, links)
    creative_learning.append_learning_event(
        "release_created",
        project_id,
        {
            "release_id": item.get("id"),
            "platform": item.get("platform"),
            "metrics": item.get("metrics") or {},
        },
    )
    if isinstance(item.get("metrics"), dict):
        creative_learning.record_project_release_performance(project_id, item)
    return item


@app.patch("/api/projects/{project_id}/releases/{release_id}")
def api_update_release_link(project_id: int, release_id: int, payload: ReleaseUpdatePayload) -> dict[str, Any]:
    ensure_project(project_id)
    links = storage.get_release_links(project_id)
    for item in links:
        if item["id"] == release_id:
            if payload.platform is not None:
                item["platform"] = payload.platform
            if payload.url is not None:
                item["url"] = payload.url
            if payload.note is not None:
                item["note"] = payload.note
            storage.save_release_links(project_id, links)
            return item
    raise HTTPException(status_code=404, detail="release not found")


@app.put("/api/projects/{project_id}/releases/{release_id}/metrics")
def api_update_release_metrics(project_id: int, release_id: int, payload: ReleaseMetricsPayload) -> dict[str, Any]:
    ensure_project(project_id)
    try:
        result = services.update_release_metrics(project_id, release_id, payload.model_dump())
        creative_learning.append_learning_event(
            "release_metrics_updated",
            project_id,
            {
                "release_id": release_id,
                "metrics": result.get("metrics") if isinstance(result, dict) else payload.model_dump(),
            },
        )
        if isinstance(result, dict):
            creative_learning.record_project_release_performance(project_id, result)
        creative_learning.rebuild_training_dataset()
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}/releases/platform-stats")
def api_release_platform_stats(project_id: int) -> dict[str, Any]:
    project = ensure_project(project_id)
    cached = storage.get_report(project_id, "release_platform_stats")
    report = release_automation.enrich_platform_stats_report(cached) if isinstance(cached, dict) else {
        "project_id": project_id,
        "accounts": [],
        "items": [],
        "supported_platforms": ["douyin", "kuaishou", "xiaohongshu", "bilibili"],
        "message": "尚未同步平台运营数据。",
    }
    report["channel_strategy"] = creative_learning.channel_production_guidance(
        str(project.get("template") or "")
    )
    return report


@app.post("/api/projects/{project_id}/releases/sync-metrics")
async def api_sync_release_metrics(project_id: int, payload: ReleaseMetricsSyncPayload | None = None) -> dict[str, Any]:
    ensure_project(project_id)
    request = payload or ReleaseMetricsSyncPayload()
    return await release_metrics_runtime.start(
        project_id,
        release_id=request.release_id,
        account_name=request.account_name,
        platform=request.platform,
        limit=request.limit,
    )


@app.get("/api/projects/{project_id}/releases/sync-metrics/status")
def api_release_metrics_sync_status(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    return release_metrics_runtime.status(project_id) or {
        "project_id": project_id,
        "status": "idle",
        "running": False,
        "stage": "idle",
        "message": "尚未启动平台数据同步。",
        "accounts": [],
        "completed_accounts": 0,
        "total_accounts": 0,
        "succeeded_accounts": 0,
        "failed_accounts": 0,
    }


@app.post("/api/projects/{project_id}/releases/import-metrics")
async def api_import_release_metrics(project_id: int, file: UploadFile = File(...)) -> dict[str, Any]:
    ensure_project(project_id)
    filename = storage.safe_name(file.filename or "platform-metrics.csv")
    if Path(filename).suffix.lower() not in {".csv", ".txt"}:
        raise HTTPException(status_code=400, detail="请选择平台导出的 CSV 数据文件。")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="数据文件为空。")
    try:
        result = release_automation.import_release_metrics_csv(project_id, data, filename)
        result["channel_memory"] = creative_learning.sync_project_release_memory(project_id)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/projects/{project_id}/releases/{release_id}")
def api_delete_release_link(project_id: int, release_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    links = [item for item in storage.get_release_links(project_id) if item["id"] != release_id]
    storage.save_release_links(project_id, links)
    return {"ok": True}


@app.post("/api/projects/{project_id}/releases/replay")
def api_release_replay(project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    ensure_project(project_id)
    return {"ok": True, "saved": payload}


@app.get("/api/projects/{project_id}/release-automation")
def api_release_automation(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    payload = release_automation.snapshot(project_id)
    payload["task"] = release_runtime.latest(project_id)
    payload["queue"] = release_runtime.queue_snapshot(project_id)
    return payload


@app.post("/api/projects/{project_id}/release-automation/draft")
def api_release_automation_draft(project_id: int, payload: ReleaseAutomationPayload) -> dict[str, Any]:
    ensure_project(project_id)
    return {"draft": release_automation.save_draft(project_id, payload.model_dump())}


@app.get("/api/projects/{project_id}/release-automation/qrcode")
def api_release_automation_qrcode(project_id: int, platform: str = "douyin", account_name: str = "default") -> FileResponse:
    ensure_project(project_id)
    qrcode = release_automation.latest_login_qrcode(project_id, platform, account_name)
    if not qrcode:
        raise HTTPException(status_code=404, detail="二维码文件不存在")
    path = Path(str(qrcode.get("absolute_path") or ""))
    if not path.exists():
        raise HTTPException(status_code=404, detail="二维码文件不存在")
    return FileResponse(path, media_type="image/png", filename=path.name)


@app.post("/api/projects/{project_id}/release-automation/prepare")
async def api_release_prepare(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    try:
        return await release_runtime.start(project_id, "prepare", {})
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/release-checklist")
def api_release_checklist(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    result = services.release_checklist_report(project_id)
    path = storage.save_report(project_id, "release_checklist", result)
    return {"report_path": str(path), "result": result}


@app.post("/api/projects/{project_id}/release-automation/login")
async def api_release_login(project_id: int, payload: ReleaseAutomationPayload) -> dict[str, Any]:
    ensure_project(project_id)
    try:
        return await release_runtime.start(project_id, "login", payload.model_dump())
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/release-automation/check")
async def api_release_check(project_id: int, payload: ReleaseAutomationPayload) -> dict[str, Any]:
    ensure_project(project_id)
    try:
        return await release_runtime.start(project_id, "check", payload.model_dump())
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/release-automation/publish")
async def api_release_publish(project_id: int, payload: ReleaseAutomationPayload) -> dict[str, Any]:
    ensure_project(project_id)
    try:
        return await release_runtime.start(project_id, "publish", payload.model_dump())
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/release-queue")
async def api_enqueue_release(project_id: int, payload: ReleaseAutomationPayload) -> dict[str, Any]:
    ensure_project(project_id)
    try:
        return await release_runtime.enqueue(project_id, payload.model_dump())
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/release-automation/accounts")
def api_release_account_catalog() -> dict[str, Any]:
    platforms = release_automation.release_platforms()
    return {
        "platforms": platforms,
        "accounts": {
            item["key"]: release_automation.list_account_profiles(item["key"])
            for item in platforms
            if item.get("available") is not False and item.get("status") == "ready"
        },
    }


@app.post("/api/projects/{project_id}/release-queue/batch")
async def api_enqueue_release_batch(project_id: int, payload: ReleaseBatchPayload) -> dict[str, Any]:
    ensure_project(project_id)
    try:
        return await release_runtime.enqueue_many(project_id, payload.model_dump())
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/release-queue/{job_id}/retry")
async def api_retry_release_queue_job(job_id: str) -> dict[str, Any]:
    try:
        return await release_runtime.retry_queue_job(job_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/release-queue/{job_id}/cancel")
async def api_cancel_release_queue_job(job_id: str) -> dict[str, Any]:
    try:
        return await release_runtime.cancel_queue_job(job_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/release-automation/cancel")
async def api_release_cancel(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    return await release_runtime.cancel()


@app.get("/api/settings/open-data-folder")
def api_open_data_folder() -> dict[str, Any]:
    return open_in_explorer(storage.DATA_ROOT)


@app.get("/api/settings/data-location")
def api_data_location() -> dict[str, Any]:
    return {"path": str(storage.DATA_ROOT)}


@app.get("/api/settings/data-location/status")
def api_data_location_status() -> dict[str, Any]:
    return {"path": str(storage.DATA_ROOT), "migrating": False}


@app.post("/api/settings/data-location/migrate")
def api_migrate_data_location(payload: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "target": payload.get("target"), "note": "本地演示版固定使用 data 目录。"}


@app.get("/api/settings/secrets")
def api_secrets() -> dict[str, Any]:
    return storage.secrets_payload()


@app.post("/api/settings/secrets")
def api_save_secrets(payload: SecretsPayload) -> dict[str, Any]:
    storage.save_env_patch(payload.values)
    return storage.secrets_payload()


@app.post("/api/settings/secrets/validate")
def api_validate_secrets(payload: SecretsValidatePayload) -> dict[str, Any]:
    values = storage.parse_env()
    return validators.validate_sections(values, payload.targets)


@app.post("/api/settings/deepseek/models")
def api_sync_deepseek_models(payload: ModelSyncPayload) -> dict[str, Any]:
    from .model_catalog import fetch_compatible_models

    values = storage.parse_env()
    base_url = payload.base_url.strip() or values.get("DEEPSEEK_BASE_URL", "")
    api_key = payload.api_key.strip() or values.get("DEEPSEEK_API_KEY", "")
    try:
        return fetch_compatible_models(base_url, api_key)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/settings/chatgpt-accounts")
def api_chatgpt_accounts() -> dict[str, Any]:
    return services.chatgpt_account_pool_status(services.runtime_env())


@app.post("/api/settings/ant-browser/test")
def api_test_ant_browser() -> dict[str, Any]:
    try:
        return services.test_ant_browser_connection(services.runtime_env())
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/settings/chatgpt-login")
def api_open_chatgpt_login(payload: ChatGPTLoginPayload | None = None) -> dict[str, Any]:
    try:
        return services.open_chatgpt_login_window(
            services.runtime_env(),
            account_id=payload.account_id if payload else None,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/settings/chatgpt-accounts/{account_id}/login")
def api_open_chatgpt_account_login(account_id: str) -> dict[str, Any]:
    try:
        return services.open_chatgpt_login_window(services.runtime_env(), account_id=account_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/settings/chatgpt-accounts/{account_id}")
def api_delete_chatgpt_account_login(account_id: str) -> dict[str, Any]:
    try:
        return services.clear_chatgpt_account_login_state(services.runtime_env(), account_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/settings/chatgpt-logout")
def api_clear_chatgpt_login() -> dict[str, Any]:
    try:
        return services.clear_chatgpt_login_state(services.runtime_env())
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/settings/tts-previews")
def api_tts_previews() -> dict[str, Any]:
    return services.tts_preview_manifest()


@app.get("/api/settings/packaging")
def api_packaging_status() -> dict[str, Any]:
    return packaging_runtime.latest()


@app.post("/api/settings/packaging/build")
def api_packaging_build(payload: PackagingBuildPayload | None = None) -> dict[str, Any]:
    payload = payload or PackagingBuildPayload()
    try:
        return packaging_runtime.start(include_zip=payload.include_zip)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/settings/packaging/cancel")
def api_packaging_cancel() -> dict[str, Any]:
    return packaging_runtime.cancel()


@app.post("/api/settings/packaging/open")
def api_packaging_open(target: str = "output") -> dict[str, Any]:
    try:
        path = packaging_runtime.open_target(target)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"打包产物不存在：{exc}") from exc
    return open_path(path)


@app.post("/api/transcribe-audio")
async def api_transcribe_audio(file: UploadFile = File(...)) -> dict[str, Any]:
    suffix = Path(file.filename or "upload.wav").suffix or ".wav"
    temp_path = storage.CONFIG_ROOT / f"transcribe-upload-{storage.now_ms()}{suffix}"
    temp_path.write_bytes(await file.read())
    try:
        text = await asyncio.to_thread(services.transcribe_audio_to_text, temp_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"音频转写失败：{exc}") from exc
    finally:
        temp_path.unlink(missing_ok=True)

    if not text.strip():
        raise HTTPException(status_code=400, detail="没有识别到有效语音内容，请换一段更清晰的音频再试。")
    return {"text": text}


@app.get("/")
def api_root() -> JSONResponse:
    return JSONResponse(
        {
            "name": "Short Video Studio Clone",
            "message": "前端页面可直接打开 http://127.0.0.1:8765/studio/ ，后端运行在 http://127.0.0.1:8765",
            "data_root": str(storage.DATA_ROOT),
        }
    )


app.mount("/data", StaticFiles(directory=storage.DATA_ROOT), name="data")
app.mount("/static/tts-previews", StaticFiles(directory=tts_previews_static_root()), name="tts-previews")
app.mount("/studio", StaticFiles(directory=storage.APP_ROOT, html=True), name="studio")


@app.on_event("shutdown")
async def _cleanup() -> None:
    if content_runtime.loaded:
        for project_id in list(content_runtime.tasks):
            with contextlib.suppress(Exception):
                await content_runtime.cancel(project_id, silent=True)
    if job_runtime.loaded:
        for job_id, item in list(job_runtime.tasks.items()):
            task = item["task"]
            task.cancel()
            with contextlib.suppress(Exception):
                await task
    if release_runtime.loaded:
        with contextlib.suppress(Exception):
            await release_runtime.cancel()


class EpisodeReviewPayload(BaseModel):
    audience_question: str = Field(default="", max_length=4000)
    viewer_takeaway: str = Field(default="", max_length=4000)
    evidence_notes: str = Field(default="", max_length=8000)
    visual_purpose: str = Field(default="", max_length=4000)
    audience_feedback: str = Field(default="", max_length=8000)
    next_experiment: str = Field(default="", max_length=4000)


@app.get("/api/projects/{project_id}/episode-review")
def api_episode_review(project_id: int) -> dict[str, Any]:
    ensure_project(project_id)
    card = storage.read_json(storage.project_file(project_id, "episode_review.json"), {})
    releases = storage.read_json(storage.project_file(project_id, "release_links.json"), [])
    return {"card": card, "releases": releases if isinstance(releases, list) else []}


@app.put("/api/projects/{project_id}/episode-review")
def api_save_episode_review(project_id: int, payload: EpisodeReviewPayload) -> dict[str, Any]:
    ensure_project(project_id)
    from datetime import datetime, timezone
    card = {key: value.strip() for key, value in payload.model_dump().items()}
    card["updated_at"] = datetime.now(timezone.utc).isoformat()
    storage.write_json(storage.project_file(project_id, "episode_review.json"), card)
    return {"ok": True, "card": card}
