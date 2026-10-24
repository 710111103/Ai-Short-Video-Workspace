from __future__ import annotations

import argparse
import asyncio
import re
import sys
from datetime import datetime
from pathlib import Path


PLATFORM_MODULES = {
    "baijiahao": "uploader.baijiahao_uploader.main",
    "toutiao": "uploader.toutiao_uploader.main",
    "sohu": "uploader.sohu_uploader.main",
    "zhihu": "uploader.zhihu_uploader.main",
    "tiktok": "uploader.tk_uploader.main_chrome",
}


def extract_article_body(content: str) -> str:
    match = re.search(r"^##\s*口播脚本\s*$([\s\S]*?)(?=^##\s|\Z)", content, flags=re.MULTILINE)
    source = match.group(1) if match else content
    lines: list[str] = []
    for raw_line in source.splitlines():
        line = re.sub(r"^\s*【[^】]+】\s*", "", raw_line).strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return "\n\n".join(lines).strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Short Video Studio OmniPost adapter")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--platform", choices=sorted(PLATFORM_MODULES), required=True)
    parser.add_argument("--action", choices=["login", "check", "publish"], required=True)
    parser.add_argument("--account", default="default")
    parser.add_argument("--file")
    parser.add_argument("--content-file")
    parser.add_argument("--thumbnail")
    parser.add_argument("--title", default="")
    parser.add_argument("--desc", default="")
    parser.add_argument("--tags", default="")
    parser.add_argument("--schedule", default="")
    parser.add_argument("--headed", action="store_true")
    return parser.parse_args()


def account_path(repo: Path, platform: str, account: str) -> Path:
    path = repo / "cookies" / f"{platform}_{account}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def parse_schedule(value: str) -> datetime | int:
    return datetime.strptime(value, "%Y-%m-%d %H:%M") if value else 0


async def run(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    if not (repo / "pyproject.toml").exists():
        raise RuntimeError(f"OmniPost 仓库不可用: {repo}")
    sys.path.insert(0, str(repo))

    import conf

    conf.LOCAL_CHROME_HEADLESS = not args.headed
    account_file = account_path(repo, args.platform, args.account)

    if args.platform == "baijiahao":
        from uploader.baijiahao_uploader.main import BaiJiaHaoVideo, baijiahao_setup, cookie_auth

        setup, auth = baijiahao_setup, cookie_auth
    elif args.platform == "toutiao":
        from uploader.toutiao_uploader.main import TouTiaoVideo, cookie_auth, toutiao_setup

        setup, auth = toutiao_setup, cookie_auth
    elif args.platform == "sohu":
        from uploader.sohu_uploader.main import SoHuArticle, cookie_auth, sohu_setup

        setup, auth = sohu_setup, cookie_auth
    elif args.platform == "zhihu":
        from uploader.zhihu_uploader.main import ZhiHuArticle, cookie_auth, zhihu_setup

        setup, auth = zhihu_setup, cookie_auth
    else:
        from uploader.tk_uploader.main_chrome import TiktokVideo, cookie_auth, tiktok_setup

        setup, auth = tiktok_setup, cookie_auth

    if args.action == "login":
        result = await setup(str(account_file), handle=True)
        if not result:
            raise RuntimeError(f"{args.platform} 登录未完成")
        print(f"login saved: {account_file}")
        return 0

    if args.action == "check":
        valid = account_file.exists() and await auth(str(account_file))
        print("valid" if valid else "invalid")
        return 0 if valid else 1

    valid = account_file.exists() and await setup(str(account_file), handle=False)
    if not valid:
        raise RuntimeError(f"账号未登录或 cookie 已失效: {account_file}")

    tags = [item.strip().lstrip("#") for item in args.tags.split(",") if item.strip()]
    publish_date = parse_schedule(args.schedule)
    thumbnail = Path(args.thumbnail) if args.thumbnail else None
    if args.platform == "baijiahao":
        app = BaiJiaHaoVideo(args.title, args.file, tags, publish_date, str(account_file))
    elif args.platform == "toutiao":
        app = TouTiaoVideo(args.title, args.file, tags, publish_date, str(account_file), description=args.desc)
    elif args.platform == "tiktok":
        app = TiktokVideo(args.title, args.file, tags, publish_date, str(account_file), thumbnail_path=thumbnail)
    else:
        if not args.content_file:
            raise RuntimeError("图文平台缺少项目文稿")
        body = extract_article_body(Path(args.content_file).read_text(encoding="utf-8", errors="replace"))
        if not body:
            raise RuntimeError("项目文稿没有可发布的正文")
        if args.platform == "sohu":
            app = SoHuArticle(
                args.title,
                body,
                tags,
                publish_date,
                str(account_file),
                cover_path=thumbnail,
                info_source="包含AI创作内容",
            )
        else:
            app = ZhiHuArticle(
                args.title,
                body,
                tags,
                publish_date,
                str(account_file),
                cover_path=thumbnail,
                creation_statement="包含 AI 辅助创作 作者对内容负责",
            )
    app.headless = not args.headed
    await app.main()
    print(f"publish completed: {args.platform}")
    return 0


def main() -> int:
    return asyncio.run(run(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
