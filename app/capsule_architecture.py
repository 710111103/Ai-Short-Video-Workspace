"""Capsule Cinema inspired production contracts for the local studio.

The implementation keeps the studio's existing assets and providers, while
adopting the useful run architecture from JuneYaooo/capsule-cinema:
production promise -> storyboard/continuity contract -> ordered execution ->
QA -> delivery.  It intentionally does not include an editable layer canvas.

Reference project: https://github.com/JuneYaooo/capsule-cinema
License: Apache-2.0
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import storage


ARCHITECTURE_VERSION = "capsule-production-architecture-v1"
STAGE_ORDER = ("routing", "planning", "generation", "assembly", "qa", "delivery")
STEP_STAGE = {
    "content_sync": "planning",
    "audio": "generation",
    "subtitles": "generation",
    "images": "generation",
    "images_missing": "generation",
    "images_sample": "generation",
    "covers": "generation",
    "covers_missing": "generation",
    "motion_clips": "generation",
    "article": "assembly",
    "video": "assembly",
}


def _snapshot_release_file(source: Path, target: Path) -> str:
    """Snapshot a large immutable release without storing a second copy.

    Run folders are audit history, while the canonical deliverable remains in
    ``releases``. On the same Windows volume a hard link preserves both paths
    and consumes no additional payload space. Filesystems without hard-link
    support keep the previous copy behavior.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    try:
        os.link(source, target)
        return "hardlink"
    except OSError:
        shutil.copy2(source, target)
        return "copy"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\u3000", " ").split()).strip()


def _read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return fallback


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _fingerprint(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def run_root(project_id: int, run_id: str) -> Path:
    return storage.project_dir(project_id) / "runs" / storage.safe_name(run_id)


def _recipe(project: dict[str, Any]) -> dict[str, Any]:
    template_key = _clean(project.get("template"))
    payload = _read_json(storage.TEMPLATES_ROOT / template_key / "recipe.json", {})
    return payload if isinstance(payload, dict) else {}


def build_delivery_promise(project_id: int) -> dict[str, Any]:
    project = storage.get_project(project_id)
    mode = _clean(project.get("template_mode") or project.get("content_type") or "video")
    promise_type = "source_led" if mode == "article" else "tts_led_explainer"
    return {
        "schema": "studio.delivery-promise/v1",
        "architecture": ARCHITECTURE_VERSION,
        "created_at": _now(),
        "promise_type": promise_type,
        "route": "article" if mode == "article" else "short_video",
        "viewer_result": "口播、字幕、画面和时轴保持同一语义来源并输出可发布成片",
        "fallback_policy": "preserve_finished_assets_and_retry_only_failed_step",
        "qa_requirements": [
            "配音时长是视频时轴主基准",
            "字幕文本必须来自最终口播稿",
            "场景只使用当前镜头事实和画面提示词",
            "静态场景图只做轻量镜头运动，动态镜头必须来自真实视频模型输出",
            "发布前检查画幅、黑帧、静音、字幕覆盖与资产版本",
        ],
    }


def build_storyboard_contract(project_id: int) -> dict[str, Any]:
    root = storage.project_dir(project_id)
    project = storage.get_project(project_id)
    recipe = _recipe(project)
    visual_recipe = recipe.get("visual_recipe") if isinstance(recipe.get("visual_recipe"), dict) else {}
    plan = _read_json(root / "audio" / "scene_plan.json", {})
    scenes = plan.get("scenes") if isinstance(plan, dict) and isinstance(plan.get("scenes"), list) else []
    style_anchor = {
        "id": "channel_style",
        "description": _clean(visual_recipe.get("style_prompt") or visual_recipe.get("strategy")),
        "negative_prompt": _clean(visual_recipe.get("negative_prompt")),
        "fixed_traits": [
            _clean(item)
            for item in visual_recipe.get("rules", [])
            if _clean(item)
        ],
    }
    rows: list[dict[str, Any]] = []
    for fallback_index, raw in enumerate(scenes, start=1):
        if not isinstance(raw, dict):
            continue
        index = int(raw.get("index", fallback_index) or fallback_index)
        start_ms = max(0, int(raw.get("start_ms", 0) or 0))
        end_ms = max(start_ms + 1, int(raw.get("end_ms", start_ms + 1) or start_ms + 1))
        rows.append(
            {
                "scene_id": index,
                "chapter_id": "main",
                "continuity_group": f"scene_{index:02d}",
                "start_ms": start_ms,
                "end_ms": end_ms,
                "duration_ms": end_ms - start_ms,
                "narration": _clean(raw.get("speech_text") or raw.get("audio_anchor")),
                "image_prompt": _clean(raw.get("image_prompt") or raw.get("source_prompt")),
                "motion_prompt": _clean(raw.get("motion_prompt") or raw.get("motion")),
                "generation_type": "image_to_video",
                "source_image": f"scenes/s_{index:02d}.png",
                "motion_clip": f"video_clips/s_{index:02d}.mp4",
                "style_anchor": "channel_style",
                "continuity_notes": _clean(raw.get("visual_anchor") or raw.get("narrative_state")),
                "transition": _clean(raw.get("transition") or "crossfade_8_frames"),
                "evidence_refs": [
                    _clean(item)
                    for item in raw.get("evidence_refs", [])
                    if _clean(item)
                ],
            }
        )
    contract = {
        "schema": "studio.storyboard-contract/v1",
        "architecture": ARCHITECTURE_VERSION,
        "project_id": project_id,
        "topic": _clean(project.get("topic_name")),
        "style_contract": style_anchor,
        "continuity_contract": {
            "long_chain_ready": True,
            "style_anchor_id": "channel_style",
            "scene_order_locked": True,
            "cross_scene_fact_leakage_forbidden": True,
        },
        "storyboard": rows,
        "created_at": _now(),
    }
    contract["fingerprint"] = _fingerprint({key: value for key, value in contract.items() if key != "created_at"})
    return contract


def build_production_plan(project_id: int, steps: Iterable[str]) -> dict[str, Any]:
    project = storage.get_project(project_id)
    normalized = [_clean(item) for item in steps if _clean(item)]
    storyboard = build_storyboard_contract(project_id)
    delivery = build_delivery_promise(project_id)
    plan_steps: list[dict[str, Any]] = []
    previous_stage_index = 0
    for index, step in enumerate(normalized, start=1):
        stage = STEP_STAGE.get(step, "qa" if step.startswith("gate") else "generation")
        stage_index = STAGE_ORDER.index(stage)
        if stage_index < previous_stage_index:
            stage = STAGE_ORDER[previous_stage_index]
            stage_index = previous_stage_index
        previous_stage_index = stage_index
        plan_steps.append(
            {
                "id": f"step-{index:02d}-{step.replace(':', '-')}",
                "key": step,
                "stage": stage,
                "input_refs": ["content.md", "audio/scene_plan.json"],
                "output_refs": {
                    "audio": ["audio/podcast.mp3"],
                    "subtitles": ["subtitles.srt", "audio/scene_plan.json"],
                    "images": ["scenes/"],
                    "images_missing": ["scenes/"],
                    "images_sample": ["scenes/"],
                    "covers": ["covers/"],
                    "covers_missing": ["covers/"],
                    "motion_clips": ["video_clips/"],
                    "article": ["releases/article.md"],
                    "video": ["releases/final-video.mp4"],
                }.get(step, ["reports/"]),
                "quality_refs": ["asset_current", "semantic_alignment"],
            }
        )
    payload = {
        "schema": "studio.production-plan/v1",
        "architecture": ARCHITECTURE_VERSION,
        "project_id": project_id,
        "channel": _clean(project.get("template")),
        "topic": _clean(project.get("topic_name")),
        "delivery_promise": delivery,
        "storyboard_fingerprint": storyboard.get("fingerprint"),
        "objectives": [
            {"id": "publishable", "statement": "输出可发布且可追溯的短视频"},
            {"id": "coherent", "statement": "口播、字幕、画面和镜头运动保持一致"},
        ],
        "quality_requirements": [
            {"id": "asset_current", "blocker": True, "description": "所有使用资产均为当前版本"},
            {"id": "semantic_alignment", "blocker": True, "description": "镜头与对应口播语义一致"},
            {"id": "media_integrity", "blocker": True, "description": "成片无黑帧、静音或时长断裂"},
        ],
        "steps": plan_steps,
        "created_at": _now(),
    }
    payload["digest"] = _fingerprint({key: value for key, value in payload.items() if key != "created_at"})
    return payload


def initialize_run(project_id: int, run_id: str, steps: Iterable[str]) -> dict[str, Any]:
    root = run_root(project_id, run_id)
    for name in ("work", "qa", "release"):
        (root / name).mkdir(parents=True, exist_ok=True)
    storyboard = build_storyboard_contract(project_id)
    plan = build_production_plan(project_id, steps)
    _write_json(root / "work" / "storyboard_contract.json", storyboard)
    _write_json(root / "work" / "production_plan.json", plan)
    state = {
        "schema": "studio.run-state/v1",
        "architecture": ARCHITECTURE_VERSION,
        "run_id": run_id,
        "project_id": project_id,
        "status": "running",
        "current_step": "",
        "plan_digest": plan["digest"],
        "steps": [
            {"key": item["key"], "stage": item["stage"], "status": "queued"}
            for item in plan["steps"]
        ],
        "created_at": _now(),
        "updated_at": _now(),
    }
    _write_json(root / "run_state.json", state)
    return {
        "version": ARCHITECTURE_VERSION,
        "run_id": run_id,
        "root": str(root),
        "plan": f"runs/{root.name}/work/production_plan.json",
        "storyboard": f"runs/{root.name}/work/storyboard_contract.json",
        "state": f"runs/{root.name}/run_state.json",
        "plan_digest": plan["digest"],
    }


def record_step(project_id: int, run_id: str, step: str, status: str, message: str = "") -> dict[str, Any]:
    root = run_root(project_id, run_id)
    state_path = root / "run_state.json"
    state = _read_json(state_path, {})
    if not isinstance(state, dict):
        state = {}
    rows = state.get("steps") if isinstance(state.get("steps"), list) else []
    for row in rows:
        if isinstance(row, dict) and _clean(row.get("key")) == _clean(step):
            row["status"] = _clean(status) or "running"
            row["message"] = _clean(message)
            row["updated_at"] = _now()
            break
    state["current_step"] = _clean(step)
    state["updated_at"] = _now()
    if _clean(status) in {"success", "passed", "succeeded"} and _clean(step) in {
        "subtitles",
        "images",
        "images_missing",
        "images_sample",
        "motion_clips",
    }:
        storyboard = build_storyboard_contract(project_id)
        _write_json(root / "work" / "storyboard_contract.json", storyboard)
        state["storyboard_fingerprint"] = storyboard.get("fingerprint")
    _write_json(state_path, state)
    return state


def finalize_run(project_id: int, run_id: str, status: str, error: str = "") -> dict[str, Any]:
    root = run_root(project_id, run_id)
    state_path = root / "run_state.json"
    state = _read_json(state_path, {})
    state = state if isinstance(state, dict) else {}
    state["status"] = _clean(status) or "completed"
    state["error"] = _clean(error)
    state["finished_at"] = _now()
    state["updated_at"] = state["finished_at"]
    project_root = storage.project_dir(project_id)
    release_map = {
        "final-video.mp4": project_root / "releases" / "final-video.mp4",
        "article.md": project_root / "releases" / "article.md",
    }
    delivered: list[dict[str, Any]] = []
    if state["status"] == "succeeded":
        for name, source in release_map.items():
            if source.exists() and source.is_file():
                target = root / "release" / name
                storage_mode = _snapshot_release_file(source, target) if source.suffix.lower() == ".mp4" else "copy"
                if storage_mode == "copy" and source.suffix.lower() != ".mp4":
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                delivered.append(
                    {
                        "name": name,
                        "path": str(target),
                        "size": target.stat().st_size,
                        "storage_mode": storage_mode,
                    }
                )
    qa = {
        "schema": "studio.run-qa/v1",
        "run_id": run_id,
        "status": state["status"],
        "error": state.get("error", ""),
        "delivery": delivered,
        "checked_at": _now(),
    }
    _write_json(root / "qa" / "run_qa.json", qa)
    _write_json(state_path, state)
    return {"state": state, "qa": qa}


__all__ = [
    "ARCHITECTURE_VERSION",
    "build_delivery_promise",
    "build_storyboard_contract",
    "build_production_plan",
    "initialize_run",
    "record_step",
    "finalize_run",
]
