from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

MODULES = {
    "douyin": "uploader.douyin_uploader.content_stats",
    "kuaishou": "uploader.ks_uploader.content_stats",
    "xiaohongshu": "uploader.xiaohongshu_uploader.content_stats",
    "bilibili": "uploader.bilibili_uploader.content_stats",
}
RESULT_PREFIX = "__OMNIPOST_STATS_JSON__="


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OmniPost content statistics bridge")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--platform", choices=sorted(MODULES), required=True)
    parser.add_argument("--account", default="default")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--headed", action="store_true")
    return parser.parse_args()


def run(args: argparse.Namespace) -> dict:
    repo = Path(args.repo).resolve()
    if not (repo / "pyproject.toml").exists():
        raise RuntimeError(f"OmniPost 仓库不存在: {repo}")
    sys.path.insert(0, str(repo))

    import importlib
    import conf

    conf.LOCAL_CHROME_HEADLESS = not args.headed
    module = importlib.import_module(MODULES[args.platform])
    account_file = repo / "cookies" / f"{args.platform}_{args.account}.json"
    items = module.sync_recent_items_sync(
        account_file,
        limit=max(1, min(int(args.limit), 20)),
        headless=not args.headed,
    )
    return {
        "platform": args.platform,
        "account_name": args.account,
        "items": items if isinstance(items, list) else [],
    }


def main() -> int:
    payload = run(parse_args())
    print(RESULT_PREFIX + json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
