from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def parse_launch_codes(raw: str) -> list[str]:
    """Parse comma/newline separated Ant Browser quick launch codes."""
    result: list[str] = []
    seen: set[str] = set()
    for item in str(raw or "").replace("，", ",").replace("\n", ",").split(","):
        code = _clean(item).upper()
        if not code or code in seen:
            continue
        seen.add(code)
        result.append(code)
    return result


@dataclass(slots=True)
class AntBrowserClient:
    base_url: str = "http://127.0.0.1:19876"
    api_key: str = ""
    api_key_header: str = "X-Ant-Api-Key"
    timeout: float = 30.0

    def __post_init__(self) -> None:
        self.base_url = str(self.base_url or "http://127.0.0.1:19876").strip().rstrip("/")
        self.api_key = str(self.api_key or "").strip()
        self.api_key_header = str(self.api_key_header or "X-Ant-Api-Key").strip() or "X-Ant-Api-Key"

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.api_key:
            headers[self.api_key_header] = self.api_key
        request = urllib.request.Request(
            f"{self.base_url}/{path.lstrip('/')}",
            data=body,
            headers=headers,
            method=method.upper(),
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8", errors="replace") or "{}")
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                error_payload = json.loads(exc.read().decode("utf-8", errors="replace") or "{}")
                detail = _clean(error_payload.get("error"))
            except Exception:
                detail = ""
            raise RuntimeError(detail or f"Ant Browser API HTTP {exc.code}") from exc
        except (OSError, urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"Ant Browser API 连接异常：{exc}") from exc
        if not isinstance(data, dict):
            raise RuntimeError("Ant Browser API 返回格式异常")
        if data.get("ok") is False:
            raise RuntimeError(_clean(data.get("error")) or "Ant Browser API 请求失败")
        return data

    def health(self) -> dict[str, Any]:
        return self.request("GET", "/api/health")

    def list_profiles(self) -> list[dict[str, Any]]:
        payload = self.request("GET", "/api/profiles")
        return [item for item in payload.get("items", []) if isinstance(item, dict)]

    def runtime_status(self, code: str) -> dict[str, Any]:
        return self.request("POST", "/api/runtime/status", {"code": _clean(code).upper()})

    def start_session(self, code: str, *, start_url: str = "", timeout_ms: int = 120000) -> dict[str, Any]:
        request: dict[str, Any] = {
            "code": _clean(code).upper(),
            "timeoutMs": max(1000, min(int(timeout_ms or 120000), 120000)),
        }
        if _clean(start_url):
            request.update({"startUrls": [_clean(start_url)], "skipDefaultStartUrls": True})
        try:
            payload = self.request("POST", "/api/runtime/session", request)
        except RuntimeError as exc:
            # Ant Browser may launch Chrome successfully but return an error when
            # its short internal takeover window expires. The debug port often
            # becomes ready shortly afterwards, so keep polling this instance
            # instead of rotating accounts and opening another browser window.
            message = _clean(exc)
            delayed_takeover = any(
                marker in message
                for marker in (
                    "尚未完成接管",
                    "连接完成前",
                    "调试端口准备中",
                    "debug port is not ready",
                )
            )
            if not delayed_takeover:
                raise
            payload = {"ready": False, "runtimeWarning": message}
        if payload.get("ready") and (payload.get("directDebugUrl") or payload.get("cdpUrl")):
            return payload
        deadline = time.monotonic() + max(3.0, request["timeoutMs"] / 1000.0)
        last_warning = _clean(payload.get("runtimeWarning") or payload.get("error"))
        while time.monotonic() < deadline:
            try:
                status = self.runtime_status(code)
                last_warning = _clean(status.get("runtimeWarning") or status.get("lastError")) or last_warning
                if status.get("debugReady") and (status.get("directDebugUrl") or status.get("cdpUrl")):
                    status["ready"] = True
                    return status
            except RuntimeError as exc:
                last_warning = _clean(exc) or last_warning
            time.sleep(0.75)
        detail = f"：{last_warning}" if last_warning else ""
        raise RuntimeError(f"Ant Browser 实例 {code} 的调试端口在 {request['timeoutMs'] // 1000} 秒内未就绪{detail}")

    def stop(self, code: str) -> dict[str, Any]:
        return self.request("POST", "/api/runtime/stop", {"code": _clean(code).upper()})

    def stop_and_wait(self, code: str, *, timeout_seconds: float = 20.0) -> bool:
        """Stop one instance and confirm it is down before another is started."""
        normalized = _clean(code).upper()
        if not normalized:
            return True
        last_error: Exception | None = None
        for _ in range(2):
            try:
                self.stop(normalized)
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                time.sleep(1.0)
        deadline = time.monotonic() + max(3.0, float(timeout_seconds or 0))
        while time.monotonic() < deadline:
            try:
                status = self.runtime_status(normalized)
                if not status.get("running") and not status.get("debugReady"):
                    return True
            except Exception as exc:
                last_error = exc
            time.sleep(0.5)
        if last_error is not None:
            raise RuntimeError(f"Ant Browser 实例 {normalized} 停止确认失败：{last_error}") from last_error
        return False


def client_from_env(env: dict[str, str], *, timeout: float = 30.0) -> AntBrowserClient:
    return AntBrowserClient(
        base_url=env.get("ANT_BROWSER_API_URL") or "http://127.0.0.1:19876",
        api_key=env.get("ANT_BROWSER_API_KEY") or "",
        api_key_header=env.get("ANT_BROWSER_API_KEY_HEADER") or "X-Ant-Api-Key",
        timeout=timeout,
    )


def discover_accounts(env: dict[str, str]) -> list[dict[str, Any]]:
    """Return rotation entries while Ant Browser remains the session owner."""
    client = client_from_env(env)
    configured_codes = parse_launch_codes(env.get("ANT_BROWSER_LAUNCH_CODES") or "")
    profiles = client.list_profiles()
    by_code = {
        _clean(profile.get("launchCode")).upper(): profile
        for profile in profiles
        if _clean(profile.get("launchCode"))
    }
    # Rotation depends on a stable list. Runtime state must never reorder the
    # pool, otherwise the persisted cursor points at a different account on
    # every refresh and appears to launch profiles randomly.
    if configured_codes:
        # The configured list is a stable rotation preference, not a source of
        # truth. An instance removed from Ant Browser must disappear from the
        # pool instead of becoming a permanent ``found=false`` placeholder.
        codes = [code for code in configured_codes if code in by_code]
    else:
        codes = sorted(by_code)
    accounts: list[dict[str, Any]] = []
    for index, code in enumerate(codes, start=1):
        profile = by_code.get(code, {})
        profile_name = _clean(profile.get("profileName"))
        debug_port = int(profile.get("debugPort") or 0)
        debug_ready = bool(profile.get("debugReady"))
        direct_url = f"http://127.0.0.1:{debug_port}" if debug_ready and debug_port else ""
        accounts.append(
            {
                "id": f"ant-{code.lower()}",
                "index": index,
                "label": profile_name or f"Ant 实例 {index}",
                "code": code,
                "profile_id": _clean(profile.get("profileId")),
                "provider": "ant_browser",
                "port": debug_port,
                "cdp_url": direct_url,
                "profile_dir": None,
                "running": bool(profile.get("running")),
                "debug_ready": debug_ready,
                "runtime_warning": _clean(profile.get("runtimeWarning")),
                "last_error": _clean(profile.get("lastError")),
                "last_start_at": _clean(profile.get("lastStartAt")),
                "last_stop_at": _clean(profile.get("lastStopAt")),
                "found": bool(profile),
            }
        )
    return accounts

