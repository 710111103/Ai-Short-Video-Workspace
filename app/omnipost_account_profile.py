from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PLATFORM_URLS = {
    "douyin": "https://creator.douyin.com/",
    "kuaishou": "https://cp.kuaishou.com/",
    "xiaohongshu": "https://creator.xiaohongshu.com/",
    "bilibili": "https://member.bilibili.com/platform/home",
    "tencent": "https://channels.weixin.qq.com/platform",
    "baijiahao": "https://baijiahao.baidu.com/",
    "toutiao": "https://mp.toutiao.com/",
    "sohu": "https://mp.sohu.com/",
    "zhihu": "https://www.zhihu.com/creator",
    "tiktok": "https://www.tiktok.com/tiktokstudio",
}

NAME_KEYS = {
    "nickname",
    "nick_name",
    "display_name",
    "displayname",
    "screen_name",
    "screenname",
    "author_name",
    "authorname",
    "creator_name",
    "creatorname",
    "account_name",
    "accountname",
    "user_name",
    "username",
}

REJECTED_NAMES = {
    "创作中心",
    "创作者中心",
    "创作服务平台",
    "作品管理",
    "账号管理",
    "个人中心",
    "首页",
    "登录",
    "退出登录",
    "消息",
}


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def valid_name(value: Any) -> str:
    text = clean(value)
    if not text or text in REJECTED_NAMES or len(text) > 40 or text.startswith("http"):
        return ""
    if not re.search(r"[A-Za-z0-9\u4e00-\u9fff]", text):
        return ""
    return text


def deep_find_name(node: Any) -> str:
    queue = [node]
    while queue:
        current = queue.pop(0)
        if isinstance(current, dict):
            for key, value in current.items():
                normalized = re.sub(r"[^a-z]", "", str(key).lower())
                if normalized in {re.sub(r"[^a-z]", "", item) for item in NAME_KEYS}:
                    candidate = valid_name(value)
                    if candidate:
                        return candidate
                queue.append(value)
        elif isinstance(current, list):
            queue.extend(current[:100])
    return ""


def decode_structured(value: str) -> list[Any]:
    candidates = [value]
    with_decoded = urllib.parse.unquote(value)
    if with_decoded != value:
        candidates.append(with_decoded)
    payloads: list[Any] = []
    for candidate in candidates:
        try:
            payloads.append(json.loads(candidate))
        except Exception:
            continue
    return payloads


def name_from_storage_state(payload: dict[str, Any]) -> str:
    for origin in payload.get("origins", []):
        for item in origin.get("localStorage", []):
            for decoded in decode_structured(str(item.get("value") or "")):
                candidate = deep_find_name(decoded)
                if candidate:
                    return candidate
    return ""


async def name_from_page(page, platform: str) -> str:
    body = await page.locator("body").first.inner_text()
    lines = [clean(item) for item in body.splitlines() if clean(item)]
    if platform == "toutiao":
        for index, line in enumerate(lines[:-1]):
            if re.search(r"在头条创作的第\s*\d+\s*天", line):
                candidate = valid_name(lines[index + 1])
                if candidate:
                    return candidate

    for frame in list(getattr(page, "frames", []) or [page]):
        try:
            candidates = await frame.locator(
                '[class*="nickname" i], [class*="user-name" i], [class*="username" i], '
                '[class*="account-name" i], [class*="profile-name" i], [class*="author-name" i], '
                '[id*="nickname" i], [id*="user-name" i], [id*="account-name" i]'
            ).all_inner_texts()
        except Exception:
            continue
        for item in candidates:
            candidate = valid_name(item)
            if candidate:
                return candidate
    return ""


async def run(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    account_file = repo / "cookies" / f"{args.platform}_{args.account}.json"
    profile_file = account_file.with_suffix(".profile.json")
    if not account_file.exists():
        print(f"profile skipped: cookie missing {account_file}")
        return 0

    storage_state = json.loads(account_file.read_text(encoding="utf-8"))
    display_name = name_from_storage_state(storage_state)
    source = "browser_storage"
    page_url = ""

    if not display_name:
        try:
            sys.path.insert(0, str(repo))
            import conf
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                launch_options: dict[str, Any] = {"headless": True}
                if conf.LOCAL_CHROME_PATH:
                    launch_options["executable_path"] = conf.LOCAL_CHROME_PATH
                browser = await playwright.chromium.launch(**launch_options)
                try:
                    context = await browser.new_context(storage_state=str(account_file), locale="zh-CN")
                    page = await context.new_page()
                    await page.goto(PLATFORM_URLS[args.platform], wait_until="domcontentloaded", timeout=60000)
                    await page.wait_for_timeout(2500)
                    page_url = page.url
                    display_name = await name_from_page(page, args.platform)
                    source = "creator_page"
                finally:
                    await browser.close()
        except Exception as exc:
            source = f"profile_probe_error:{type(exc).__name__}"

    profile = {
        "platform": args.platform,
        "alias": args.account,
        "display_name": display_name,
        "status": "connected" if display_name else "nickname_unavailable",
        "source": source,
        "page_url": page_url,
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }
    profile_file.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    if display_name:
        print(f"account profile synced: {display_name} ({args.account})")
    else:
        print(f"account profile nickname unavailable: {args.platform} ({args.account})")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--platform", choices=sorted(PLATFORM_URLS), required=True)
    parser.add_argument("--account", default="default")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(parse_args())))
