import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app import omnipost_account_profile, omnipost_bridge, release_automation, storage


class ReleaseQueueRecordTests(unittest.TestCase):
    def test_release_subprocesses_are_hidden_on_windows(self) -> None:
        with patch.object(release_automation.os, "name", "nt"):
            options = release_automation._hidden_subprocess_kwargs()

        self.assertIn("creationflags", options)
        self.assertEqual(options["creationflags"], getattr(release_automation.subprocess, "CREATE_NO_WINDOW", 0))

    def test_account_without_cookie_is_reported_as_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "omnipost"
            repo.mkdir()
            with patch.object(release_automation, "detect_repo", return_value=(repo, False)):
                account = release_automation.inspect_account_profile("toutiao", "default")

        self.assertEqual(account["status"], "missing")
        self.assertFalse(account["cookie_exists"])
        self.assertIn("登录", account["message"])

    def test_profile_sidecar_exposes_name_without_claiming_live_login(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "omnipost"
            cookies = repo / "cookies"
            cookies.mkdir(parents=True)
            (cookies / "toutiao_default.json").write_text("{}", encoding="utf-8")
            (cookies / "toutiao_default.profile.json").write_text(
                '{"display_name":"科技情报站","source":"toutiao_creator_page"}',
                encoding="utf-8",
            )
            with patch.object(release_automation, "detect_repo", return_value=(repo, False)):
                account = release_automation.inspect_account_profile("toutiao", "default")

        self.assertEqual(account["status"], "saved_session")
        self.assertEqual(account["display_name"], "科技情报站")
        self.assertIn("实时检测", account["message"])

    def test_xiaohongshu_name_is_read_from_creator_storage(self) -> None:
        storage_state = {
            "origins": [
                {
                    "origin": "https://creator.xiaohongshu.com",
                    "localStorage": [
                        {
                            "name": "USER_INFO_FOR_BIZ",
                            "value": json.dumps(
                                {"userId": "USER_ID", "userName": "橙子酱酱酱o76"},
                                ensure_ascii=False,
                            ),
                        }
                    ],
                }
            ]
        }

        self.assertEqual(
            omnipost_account_profile.name_from_storage_state(storage_state),
            "橙子酱酱酱o76",
        )

    def test_release_action_check_timeout_is_bounded(self) -> None:
        runtime = release_automation.SocialAutoUploadRuntime()
        self.assertEqual(runtime._command_timeout_seconds("check"), 90)

    def test_stale_queue_job_is_closed_after_worker_heartbeat_expires(self) -> None:
        payload = {
            "jobs": [{
                "id": "stale",
                "status": "publishing",
                "platform": "tencent",
                "updated_at": 1,
                "created_at": 1,
            }]
        }

        changed = release_automation._reconcile_stale_release_jobs(
            payload, now=release_automation.RELEASE_ACTION_TIMEOUT_SECONDS["publish"] + 200,
        )

        self.assertTrue(changed)
        job = payload["jobs"][0]
        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["stalled_reason"], "worker_heartbeat_timeout")
        self.assertTrue(job["recoverable"])

    def test_release_log_maps_platform_progress_to_current_stage(self) -> None:
        self.assertEqual(
            release_automation._release_stage_from_log("✅ 3:4 个人主页卡片真实编辑入口已就绪"),
            "设置 3:4 封面",
        )
        self.assertEqual(
            release_automation._release_stage_from_log("🚀 已点击发表，正在等待平台确认"),
            "等待平台确认",
        )

    def test_release_log_strips_ansi_from_new_and_existing_lines(self) -> None:
        runtime = release_automation.SocialAutoUploadRuntime()
        runtime.state = {
            "project_id": 0,
            "log": "\x1b[38;2;112;172;222m旧日志\x1b[0m",
        }

        runtime._log("\x1b[38;2;156;191;221mINFO\x1b[0m: 设置封面")

        self.assertEqual(runtime.state["log"], "旧日志\nINFO: 设置封面")
        self.assertNotIn("\x1b", runtime.state["log"])

    def test_douyin_blank_page_error_is_user_visible(self) -> None:
        message = release_automation._release_command_failure_message(
            "check",
            "douyin",
            "抖音账号检测未发现真实上传界面: file_inputs=0, body_length=0",
            1,
        )
        self.assertIn("空白", message)
        self.assertIn("账号检测未通过", message)

    def test_failure_message_uses_last_traceback_error(self) -> None:
        message = release_automation._release_command_failure_message(
            "publish",
            "xiaohongshu",
            "Traceback (most recent call last):\n  File \"main.py\", line 10\nRuntimeError: 预约发布时间必须晚于当前时间",
            1,
        )
        self.assertIn("预约发布时间必须晚于当前时间", message)
        self.assertNotIn("退出码 1）。", message)

    def test_past_schedule_becomes_immediate(self) -> None:
        from datetime import datetime

        schedule, notice = release_automation._schedule_for_execution(
            "2026-09-09T06:00",
            now=datetime(2026, 9, 9, 8, 22),
        )

        self.assertEqual(schedule, "")
        self.assertIn("按立即发布", notice)

    def test_future_schedule_is_preserved(self) -> None:
        from datetime import datetime

        schedule, notice = release_automation._schedule_for_execution(
            "2026-09-09T10:00",
            now=datetime(2026, 9, 9, 8, 22),
        )

        self.assertEqual(schedule, "2026-09-09 10:00")
        self.assertEqual(notice, "")

    def test_failed_account_check_invalidates_fresh_profile_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "omnipost"
            cookies = repo / "cookies"
            cookies.mkdir(parents=True)
            profile = cookies / "douyin_default.profile.json"
            profile.write_text(
                json.dumps({"status": "connected", "synced_at": "2099-01-01T00:00:00+08:00"}),
                encoding="utf-8",
            )
            with patch.object(release_automation, "detect_repo", return_value=(repo, False)):
                release_automation.mark_account_profile_invalid("douyin", "default", "检测失败")
                self.assertFalse(release_automation.account_profile_is_fresh("douyin", "default"))

            saved = json.loads(profile.read_text(encoding="utf-8"))
            self.assertEqual(saved["status"], "invalid")
            self.assertEqual(saved["message"], "检测失败")

    def test_failed_publish_without_discovered_work_does_not_backfill_success(self) -> None:
        with (
            patch.object(release_automation, "_discover_douyin_release", return_value=None),
            patch.object(release_automation, "inspect_account_profile", return_value={}),
        ):
            result = release_automation.backfill_release_link(
                112,
                {"id": "failed-task", "platform": "douyin", "status": "failed"},
                {"platform": "douyin", "title": "测试标题"},
            )

        self.assertIsNone(result)

    def test_douyin_discovery_rejects_recent_work_with_different_title(self) -> None:
        work = {
            "aweme_id": "OLD_ID",
            "create_time": 2000,
            "description": "华为小米同一天开发布会，把炮口对准了下周的苹果",
            "status": {"allow_share": True},
            "share_url": "https://www.douyin.com/video/OLD_ID",
        }
        with (
            patch.object(release_automation, "detect_repo", return_value=(Path("repo"), False)),
            patch.object(release_automation, "_load_douyin_recent_works", return_value=[work]),
            patch.object(release_automation.storage, "get_project", return_value={"topic_name": "红果屠城"}),
            patch.object(release_automation.storage, "get_summary", return_value={}),
        ):
            result = release_automation._discover_douyin_release(
                114,
                {"account_name": "default", "started_at": 1900, "finished_at": 2100},
                {"platform": "douyin", "title": "红果屠城：免费短剧改写互联网"},
            )

        self.assertIsNone(result)

    def test_douyin_discovery_rejects_work_present_before_upload(self) -> None:
        work = {
            "aweme_id": "OLD_ID",
            "create_time": 2000,
            "description": "红果屠城：免费短剧改写互联网",
            "status": {"allow_share": True},
            "share_url": "https://www.douyin.com/video/OLD_ID",
        }
        with (
            patch.object(release_automation, "detect_repo", return_value=(Path("repo"), False)),
            patch.object(release_automation, "_load_douyin_recent_works", return_value=[work]),
            patch.object(release_automation.storage, "get_project", return_value={"topic_name": "红果屠城"}),
            patch.object(release_automation.storage, "get_summary", return_value={}),
        ):
            result = release_automation._discover_douyin_release(
                114,
                {"account_name": "default", "started_at": 1900, "finished_at": 2100},
                {
                    "platform": "douyin",
                    "title": "红果屠城：免费短剧改写互联网",
                    "_douyin_before_ids": ["OLD_ID"],
                },
            )

        self.assertIsNone(result)

    def test_release_ui_uses_multi_account_batch_queue(self) -> None:
        root = Path(__file__).resolve().parents[1]
        html = (root / "index.html").read_text(encoding="utf-8")
        javascript = (root / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="release-batch-targets"', html)
        self.assertIn("data-release-target", javascript)
        self.assertIn("/release-queue/batch", javascript)

    def test_account_profile_sidecars_label_multiple_accounts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "omnipost"
            cookies = repo / "cookies"
            cookies.mkdir(parents=True)
            for alias, name in (("default", "科技情报站"), ("second", "数码观察室")):
                (cookies / f"toutiao_{alias}.json").write_text("{}", encoding="utf-8")
                (cookies / f"toutiao_{alias}.profile.json").write_text(
                    json.dumps({"display_name": name}, ensure_ascii=False), encoding="utf-8"
                )
            with patch.object(release_automation, "detect_repo", return_value=(repo, False)):
                profiles = release_automation.list_account_profiles("toutiao")

        self.assertEqual([item["alias"] for item in profiles], ["default", "second"])
        self.assertEqual(profiles[1]["label"], "数码观察室（second）")

    def test_omnipost_registry_lists_ready_and_planned_platforms(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with (
                patch.object(storage, "DATA_ROOT", root / "data"),
                patch.object(storage, "CONFIG_ROOT", root / "config"),
                patch.object(release_automation, "detect_repo", return_value=(root / "missing-omnipost", True)),
            ):
                platforms = release_automation.release_platforms()

        by_key = {item["key"]: item for item in platforms}
        self.assertTrue(by_key["douyin"]["available"])
        self.assertTrue(by_key["bilibili"]["available"])
        self.assertTrue(by_key["tencent"]["available"])
        self.assertFalse(by_key["toutiao"]["available"])
        self.assertEqual(by_key["toutiao"]["status"], "needs_update")

    def test_article_body_uses_voiceover_section_and_removes_speaker_labels(self) -> None:
        content = """# 标题

## 口播脚本
【女】第一句。
【男】第二句。

## 重点字幕
- 不应进入正文
"""
        self.assertEqual(omnipost_bridge.extract_article_body(content), "第一句。\n\n第二句。")

    def test_tencent_login_qrcode_accepts_platform_specific_filename(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "omnipost"
            cookie_dir = repo / "cookies"
            cookie_dir.mkdir(parents=True)
            qrcode = cookie_dir / "tencent_default_tencent_login_qrcode_20260819_231448.png"
            qrcode.write_bytes(b"png")
            with patch.object(release_automation, "detect_repo", return_value=(repo, False)):
                result = release_automation.latest_login_qrcode(51, "tencent", "default")

        self.assertIsNotNone(result)
        self.assertEqual(result["name"], qrcode.name)

    def test_existing_old_repo_marks_missing_cli_platform_as_needs_update(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "social-auto-upload"
            repo.mkdir()
            (repo / "pyproject.toml").write_text("[project]\nname='old-sau'\n", encoding="utf-8")
            (repo / "sau_cli.py").write_text('platform_parsers.add_parser("douyin")\n', encoding="utf-8")
            with patch.object(release_automation, "detect_repo", return_value=(repo, False)):
                platforms = release_automation.release_platforms()

        by_key = {item["key"]: item for item in platforms}
        self.assertTrue(by_key["douyin"]["available"])
        self.assertFalse(by_key["tencent"]["available"])
        self.assertEqual(by_key["tencent"]["status"], "needs_update")

    def test_enqueue_persists_channel_account_binding_and_deduplicates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = {"id": 51, "topic_name": "测试主题", "template": "科技情报站"}
            draft = {
                "platform": "douyin",
                "account_name": "tech-account",
                "title": "测试标题",
                "description": "",
                "tags": "",
                "schedule": "",
                "headed": False,
                "debug": False,
            }
            with (
                patch.object(storage, "DATA_ROOT", root / "data"),
                patch.object(storage, "CONFIG_ROOT", root / "config"),
                patch.object(storage, "get_project", return_value=project),
                patch.object(release_automation, "_release_draft_defaults", return_value=draft),
            ):
                first = release_automation.enqueue_release_job_record(51, draft)
                second = release_automation.enqueue_release_job_record(51, draft)
                bindings = release_automation.load_release_bindings()
                queue = release_automation.load_release_queue()

            self.assertEqual(first["id"], second["id"])
            self.assertEqual(len(queue["jobs"]), 1)
            self.assertEqual(first["channel"], "科技情报站")
            self.assertEqual(bindings["科技情报站:douyin"], "tech-account")


    def test_successful_release_reuses_same_artifact_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_root = root / "data"
            projects_root = data_root / "projects"
            video_path = projects_root / "51" / "releases" / "final-video.mp4"
            video_path.parent.mkdir(parents=True)
            video_path.write_bytes(b"first-render")
            project = {"id": 51, "topic_name": "测试主题", "template": "科技情报站"}
            draft = {
                "platform": "douyin",
                "account_name": "tech-account",
                "title": "测试标题",
                "description": "",
                "tags": "",
                "schedule": "",
                "headed": False,
                "debug": False,
            }
            with (
                patch.object(storage, "DATA_ROOT", data_root),
                patch.object(storage, "PROJECTS_ROOT", projects_root),
                patch.object(storage, "CONFIG_ROOT", data_root / "config"),
                patch.object(storage, "get_project", return_value=project),
                patch.object(release_automation, "_release_draft_defaults", return_value=draft),
            ):
                first = release_automation.enqueue_release_job_record(51, draft)
                queue = release_automation.load_release_queue()
                queue["jobs"][0].update({
                    "status": "succeeded",
                    "stage": "发布完成",
                    "finished_at": storage.now_ts(),
                    "result": {"published_release": {"url": "https://example.test/work/1"}},
                })
                release_automation.save_release_queue(queue)

                second = release_automation.enqueue_release_job_record(51, draft)
                saved = release_automation.load_release_queue()

            self.assertEqual(second["id"], first["id"])
            self.assertEqual(len(saved["jobs"]), 1)
            self.assertEqual(second["stage"], "已发布，复用成功记录")
            self.assertTrue(second["release_key"])
            self.assertEqual(second["result"]["published_release"]["url"], "https://example.test/work/1")

    def test_changed_final_video_creates_new_release_job(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_root = root / "data"
            projects_root = data_root / "projects"
            video_path = projects_root / "51" / "releases" / "final-video.mp4"
            video_path.parent.mkdir(parents=True)
            video_path.write_bytes(b"first-render")
            project = {"id": 51, "topic_name": "测试主题", "template": "科技情报站"}
            draft = {
                "platform": "douyin",
                "account_name": "tech-account",
                "title": "测试标题",
                "description": "",
                "tags": "",
                "schedule": "",
                "headed": False,
                "debug": False,
            }
            with (
                patch.object(storage, "DATA_ROOT", data_root),
                patch.object(storage, "PROJECTS_ROOT", projects_root),
                patch.object(storage, "CONFIG_ROOT", data_root / "config"),
                patch.object(storage, "get_project", return_value=project),
                patch.object(release_automation, "_release_draft_defaults", return_value=draft),
            ):
                first = release_automation.enqueue_release_job_record(51, draft)
                queue = release_automation.load_release_queue()
                queue["jobs"][0].update({"status": "succeeded", "stage": "发布完成"})
                release_automation.save_release_queue(queue)

                video_path.write_bytes(b"second-render-with-different-content")
                second = release_automation.enqueue_release_job_record(51, draft)
                saved = release_automation.load_release_queue()

            self.assertNotEqual(second["id"], first["id"])
            self.assertNotEqual(second["file_sha256"], first["file_sha256"])
            self.assertEqual(len(saved["jobs"]), 2)
            self.assertEqual(second["status"], "queued")
    def test_release_description_prefers_authored_episode_copy(self) -> None:
        description = release_automation._release_description(
            {"topic_name": "手机 App 在偷听你聊天？"},
            {"name": "科技情报站"},
            {"insights": {"opening_hook": "旧钩子", "core_viewpoint": "旧观点"}},
            {
                "publish_title": "手机 App 真在偷听吗",
                "publish_description": "刚聊完旅行，广告立刻出现，真的是麦克风在偷听？\n\n这期用权限、数据链路和广告画像把原因讲清。",
            },
        )

        self.assertIn("刚聊完旅行", description)
        self.assertIn("权限、数据链路", description)
        self.assertNotIn("旧钩子", description)

    def test_release_description_uses_hook_payoff_and_topic_question(self) -> None:
        description = release_automation._release_description(
            {"topic_name": "苹果最高涨 2300，把用户逼去了二手市场"},
            {"name": "科技情报站"},
            {
                "insights": {
                    "opening_hook": "下单 4268 元，第二天同一款变成 6268 元",
                    "core_viewpoint": "AI 数据中心抢走高端存储产能，老款、新款和二手一起涨",
                    "interaction_hook": "如果锁单后商家让你取消，你会怎么处理？",
                }
            },
            {"publish_title": "苹果最高涨2300，用户被逼去了二手市场"},
        )

        self.assertIn("4268", description)
        self.assertIn("AI 数据中心", description)
        self.assertIn("你会怎么处理", description)
        self.assertNotEqual(description.splitlines()[0], "苹果最高涨2300，用户被逼去了二手市场")

    def test_release_description_removes_repeated_title_prefix_but_keeps_new_information(self) -> None:
        title = "华为小米同一天开发布会，把炮口对准了下周的苹果"
        description = release_automation._release_description(
            {"topic_name": title},
            {"name": "科技情报站"},
            {"insights": {}},
            {
                "publish_title": title,
                "publish_description": f"{title}\n{title} 真正关键是价格差",
            },
        )

        self.assertNotIn(title, description)
        self.assertIn("真正关键是价格差", description)

    def test_release_description_keeps_only_one_semantically_identical_line(self) -> None:
        description = release_automation._release_description(
            {"topic_name": "手机涨价"},
            {"name": "科技情报站"},
            {"insights": {}},
            {
                "publish_title": "手机为什么又涨价了",
                "publish_description": "存储成本上涨推高了手机价格。\n存储成本上涨，推高了手机价格！",
            },
        )

        self.assertEqual(description.count("存储成本上涨"), 1)

    def test_content_summary_extracts_publish_description(self) -> None:
        content = """# 测试主题

## Meta
- 推荐发布标题: 测试发布标题
- 发布描述: 一个具体反差，让观众想知道原因。
- 时长: 60 秒

## 口播脚本
【主播】这里是正文。
"""

        summary = release_automation.services.summarize_content(content, "video")

        self.assertEqual(summary["publish_description"], "一个具体反差，让观众想知道原因。")

    def test_xiaohongshu_draft_normalizes_to_headed(self) -> None:
        normalized = release_automation._normalize_release_draft(
            {"platform": "xiaohongshu", "headed": False},
        )

        self.assertTrue(normalized["headed"])


class ReleaseQueueRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_xiaohongshu_check_syncs_profile_after_cookie_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "omnipost"
            repo.mkdir()
            (repo / "pyproject.toml").write_text("[project]\nname='omnipost'\n", encoding="utf-8")
            (repo / "sau_cli.py").write_text('platform_parsers.add_parser("xiaohongshu")\n', encoding="utf-8")
            runtime = release_automation.SocialAutoUploadRuntime()
            with (
                patch.object(release_automation, "probe", return_value={"repo_path": str(repo), "uv_bin": "uv"}),
                patch.object(release_automation, "release_platform", return_value={"adapter": "sau_cli", "available": True}),
                patch.object(release_automation.shutil, "which", return_value="uv"),
            ):
                _, commands = runtime._resolve_commands(
                    51,
                    "check",
                    {"platform": "xiaohongshu", "account_name": "default"},
                )

        self.assertEqual(len(commands), 2)
        self.assertIn("sau_cli.py", commands[0])
        self.assertIn("omnipost_account_profile.py", " ".join(commands[1]))
        self.assertIn("xiaohongshu", commands[1])

    async def test_xiaohongshu_publish_is_always_headed_even_when_requested_headless(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo = root / "omnipost"
            repo.mkdir()
            (repo / "pyproject.toml").write_text("[project]\nname='omnipost'\n", encoding="utf-8")
            (repo / "sau_cli.py").write_text('platform_parsers.add_parser("xiaohongshu")\n', encoding="utf-8")
            video = root / "final-video.mp4"
            video.write_bytes(b"video")
            runtime = release_automation.SocialAutoUploadRuntime()
            with (
                patch.object(release_automation, "probe", return_value={"repo_path": str(repo), "uv_bin": "uv"}),
                patch.object(release_automation, "release_platform", return_value={"adapter": "sau_cli", "available": True}),
                patch.object(release_automation.shutil, "which", return_value="uv"),
                patch.object(release_automation, "_project_files_or_error", return_value={"final_video": {"absolute_path": str(video)}}),
                patch.object(storage, "get_project", return_value={"topic_name": "测试主题"}),
            ):
                _, commands = runtime._resolve_commands(
                    51,
                    "publish",
                    {"platform": "xiaohongshu", "account_name": "default", "title": "标题", "headed": False},
                )

        command = commands[0]
        self.assertIn("--headed", command)
        self.assertNotIn("--headless", command)

    async def test_tencent_login_uses_visible_headed_qrcode_flow(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "omnipost"
            repo.mkdir()
            (repo / "pyproject.toml").write_text("[project]\nname='omnipost'\n", encoding="utf-8")
            (repo / "sau_cli.py").write_text('platform_parsers.add_parser("tencent")\n', encoding="utf-8")
            runtime = release_automation.SocialAutoUploadRuntime()
            with (
                patch.object(release_automation, "probe", return_value={"repo_path": str(repo), "uv_bin": "uv"}),
                patch.object(release_automation.shutil, "which", return_value="uv"),
            ):
                _, commands = runtime._resolve_commands(51, "login", {"platform": "tencent", "account_name": "wx"})

        self.assertIn("--headed", commands[0])
        self.assertNotIn("--headless", commands[0])

    async def test_toutiao_bridge_publish_uses_final_video(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo = root / "omnipost"
            repo.mkdir()
            (repo / "pyproject.toml").write_text("[project]\nname='omnipost'\n", encoding="utf-8")
            video = root / "final-video.mp4"
            video.write_bytes(b"video")
            runtime = release_automation.SocialAutoUploadRuntime()
            with (
                patch.object(release_automation, "probe", return_value={"repo_path": str(repo), "uv_bin": "uv"}),
                patch.object(release_automation, "release_platform", return_value={"adapter": "omnipost_bridge", "available": True}),
                patch.object(release_automation.shutil, "which", return_value="uv"),
                patch.object(release_automation, "_project_files_or_error", return_value={"final_video": {"absolute_path": str(video)}}),
                patch.object(storage, "get_project", return_value={"topic_name": "测试主题"}),
            ):
                _, commands = runtime._resolve_commands(51, "publish", {"platform": "toutiao", "title": "标题"})

        command = commands[0]
        self.assertIn("omnipost_bridge.py", " ".join(command))
        self.assertIn("--file", command)
        self.assertIn(str(video), command)
        self.assertNotIn("--headed", command)

    async def test_zhihu_bridge_publish_uses_project_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo = root / "omnipost"
            repo.mkdir()
            (repo / "pyproject.toml").write_text("[project]\nname='omnipost'\n", encoding="utf-8")
            video = root / "final-video.mp4"
            content = root / "content.md"
            video.write_bytes(b"video")
            content.write_text("## 口播脚本\n【主播】正文", encoding="utf-8")
            runtime = release_automation.SocialAutoUploadRuntime()
            with (
                patch.object(release_automation, "probe", return_value={"repo_path": str(repo), "uv_bin": "uv"}),
                patch.object(release_automation, "release_platform", return_value={"adapter": "omnipost_bridge", "available": True}),
                patch.object(release_automation.shutil, "which", return_value="uv"),
                patch.object(release_automation, "_project_files_or_error", return_value={"final_video": {"absolute_path": str(video)}}),
                patch.object(storage, "get_project", return_value={"topic_name": "测试主题"}),
                patch.object(storage, "project_file", return_value=content),
            ):
                _, commands = runtime._resolve_commands(51, "publish", {"platform": "zhihu", "title": "标题"})

        command = commands[0]
        self.assertIn("--content-file", command)
        self.assertIn(str(content), command)
        self.assertNotIn("--file", command)

    async def test_bilibili_publish_command_uses_cli_defaults_without_browser_flags(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo = root / "omnipost"
            repo.mkdir()
            (repo / "pyproject.toml").write_text("[project]\nname='omnipost'\n", encoding="utf-8")
            (repo / "sau_cli.py").write_text('platform_parsers.add_parser("bilibili")\n', encoding="utf-8")
            video = root / "final-video.mp4"
            video.write_bytes(b"video")
            runtime = release_automation.SocialAutoUploadRuntime()
            with (
                patch.object(release_automation, "probe", return_value={"repo_path": str(repo), "uv_bin": "uv"}),
                patch.object(release_automation.shutil, "which", return_value="uv"),
                patch.object(release_automation, "_project_files_or_error", return_value={"final_video": {"absolute_path": str(video)}}),
                patch.object(storage, "get_project", return_value={"topic_name": "测试主题"}),
            ):
                _, commands = runtime._resolve_commands(
                    51,
                    "publish",
                    {"platform": "bilibili", "account_name": "bili", "title": "标题", "description": "简介", "tags": "科技"},
                )

        command = commands[0]
        self.assertIn("bilibili", command)
        self.assertIn("--tid", command)
        self.assertIn("249", command)
        self.assertNotIn("--headless", command)

    async def test_tencent_publish_command_uses_both_thumbnails_and_browser_flags(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo = root / "omnipost"
            repo.mkdir()
            (repo / "pyproject.toml").write_text("[project]\nname='omnipost'\n", encoding="utf-8")
            (repo / "sau_cli.py").write_text('platform_parsers.add_parser("tencent")\n', encoding="utf-8")
            video = root / "final-video.mp4"
            landscape = root / "cover-16x9.png"
            story = root / "cover-4x3.png"
            portrait = root / "cover-3x4.png"
            video.write_bytes(b"video")
            landscape.write_bytes(b"png")
            story.write_bytes(b"png")
            portrait.write_bytes(b"png")
            runtime = release_automation.SocialAutoUploadRuntime()
            with (
                patch.object(release_automation, "probe", return_value={"repo_path": str(repo), "uv_bin": "uv"}),
                patch.object(release_automation.shutil, "which", return_value="uv"),
                patch.object(
                    release_automation,
                    "_project_files_or_error",
                    return_value={
                        "final_video": {"absolute_path": str(video)},
                        "thumbnail_landscape": {"absolute_path": str(landscape)},
                        "thumbnail_story": {"absolute_path": str(story)},
                        "thumbnail_portrait": {"absolute_path": str(portrait)},
                    },
                ),
                patch.object(storage, "get_project", return_value={"topic_name": "测试主题"}),
            ):
                _, commands = runtime._resolve_commands(
                    51,
                    "publish",
                    {"platform": "tencent", "account_name": "wx", "title": "标题", "description": "简介", "headed": True},
                )

        command = commands[0]
        self.assertIn("tencent", command)
        self.assertIn("--headed", command)
        self.assertIn("--thumbnail-landscape", command)
        self.assertIn(str(story), command)
        self.assertNotIn(str(landscape), command)
        self.assertIn("--thumbnail-portrait", command)
        self.assertIn(str(portrait), command)

    async def test_queue_job_checks_account_then_publishes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video = root / "data" / "projects" / "51" / "releases" / "final-video.mp4"
            video.parent.mkdir(parents=True)
            video.write_bytes(b"video")
            job = {
                "id": "job-1",
                "project_id": 51,
                "project_title": "测试主题",
                "channel": "科技情报站",
                "platform": "douyin",
                "account_name": "tech-account",
                "payload": {"platform": "douyin", "account_name": "tech-account", "title": "测试标题"},
                "status": "queued",
                "stage": "等待发布",
                "attempts": 0,
                "max_attempts": 2,
                "created_at": 1,
                "updated_at": 1,
            }
            with (
                patch.object(storage, "DATA_ROOT", root / "data"),
                patch.object(storage, "CONFIG_ROOT", root / "config"),
            ):
                release_automation.save_release_queue({"jobs": [job]})
                runtime = release_automation.SocialAutoUploadRuntime()
                runtime._run_queue_action = AsyncMock(
                    side_effect=[
                        {"status": "succeeded"},
                        {"status": "succeeded", "result": {"published_release": {"url": "https://example.test/work"}}},
                    ]
                )

                await runtime._process_queue_job(job)
                saved = release_automation.load_release_queue()["jobs"][0]

            self.assertEqual(saved["status"], "succeeded")
            self.assertEqual(saved["attempts"], 1)
            self.assertEqual(saved["result"]["published_release"]["url"], "https://example.test/work")
            self.assertEqual(
                [call.args[1] for call in runtime._run_queue_action.await_args_list],
                ["check", "publish"],
            )

    async def test_enqueue_without_final_video_waits_for_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with (
                patch.object(storage, "DATA_ROOT", root / "data"),
                patch.object(storage, "CONFIG_ROOT", root / "config"),
                patch.object(storage, "get_project", return_value={"id": 51, "topic_name": "测试", "template": "科技情报站"}),
            ):
                runtime = release_automation.SocialAutoUploadRuntime()
                runtime._ensure_queue_worker = AsyncMock()
                result = await runtime.enqueue(51, {"platform": "douyin", "title": "测试标题"})
                queued = release_automation.load_release_queue()["jobs"]

        self.assertEqual(len(queued), 1)
        self.assertEqual(queued[0]["status"], "waiting_assets")
        self.assertEqual(queued[0]["stage"], "等待成片")
        self.assertEqual(queued[0]["attempts"], 0)
        self.assertEqual(result["job"]["status"], "waiting_assets")
        runtime._ensure_queue_worker.assert_awaited_once()

    async def test_batch_enqueue_without_final_video_waits_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with (
                patch.object(storage, "DATA_ROOT", root / "data"),
                patch.object(storage, "CONFIG_ROOT", root / "config"),
                patch.object(storage, "get_project", return_value={"id": 51, "topic_name": "测试", "template": "科技情报站"}),
                patch.object(
                    release_automation,
                    "release_platforms",
                    return_value=[
                        {"key": "douyin", "available": True, "status": "ready"},
                        {"key": "tencent", "available": True, "status": "ready"},
                    ],
                ),
            ):
                runtime = release_automation.SocialAutoUploadRuntime()
                runtime._ensure_queue_worker = AsyncMock()
                result = await runtime.enqueue_many(51, {
                    "targets": [
                        {"platform": "douyin", "account_name": "default"},
                        {"platform": "tencent", "account_name": "default"},
                    ],
                    "title": "测试标题",
                })
                queued = release_automation.load_release_queue()["jobs"]

        self.assertEqual(result["count"], 2)
        self.assertEqual([job["status"] for job in queued], ["waiting_assets", "waiting_assets"])
        self.assertTrue(all(job["attempts"] == 0 for job in queued))
        runtime._ensure_queue_worker.assert_awaited_once()

    async def test_finished_video_waits_for_future_schedule(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video = root / "data" / "projects" / "51" / "releases" / "final-video.mp4"
            video.parent.mkdir(parents=True)
            video.write_bytes(b"video")
            with (
                patch.object(storage, "DATA_ROOT", root / "data"),
                patch.object(storage, "CONFIG_ROOT", root / "config"),
                patch.object(storage, "get_project", return_value={"id": 51, "topic_name": "测试", "template": "科技情报站"}),
            ):
                runtime = release_automation.SocialAutoUploadRuntime()
                runtime._ensure_queue_worker = AsyncMock()
                result = await runtime.enqueue(51, {
                    "platform": "douyin",
                    "title": "测试标题",
                    "schedule": "2099-12-31T23:59",
                })

        self.assertEqual(result["job"]["status"], "waiting_schedule")
        self.assertEqual(result["job"]["stage"], "等待预约时间")
        self.assertEqual(result["job"]["attempts"], 0)

    async def test_batch_enqueue_creates_douyin_and_tencent_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video = root / "data" / "projects" / "51" / "releases" / "final-video.mp4"
            video.parent.mkdir(parents=True)
            video.write_bytes(b"video")
            with (
                patch.object(storage, "DATA_ROOT", root / "data"),
                patch.object(storage, "CONFIG_ROOT", root / "config"),
                patch.object(
                    storage,
                    "get_project",
                    return_value={"id": 51, "topic_name": "测试主题", "template": "科技情报站"},
                ),
                patch.object(
                    release_automation,
                    "release_platforms",
                    return_value=[
                        {"key": "douyin", "available": True, "status": "ready"},
                        {"key": "tencent", "available": True, "status": "ready"},
                    ],
                ),
                patch.object(release_automation, "list_account_profiles", return_value=[]),
            ):
                runtime = release_automation.SocialAutoUploadRuntime()
                runtime._ensure_queue_worker = AsyncMock()
                result = await runtime.enqueue_many(
                    51,
                    {
                        "targets": [
                            {"platform": "douyin", "account_name": "default"},
                            {"platform": "tencent", "account_name": "default"},
                        ],
                        "title": "测试标题",
                    },
                )
                queued = release_automation.load_release_queue()["jobs"]

        self.assertEqual(result["count"], 2)
        self.assertEqual([job["platform"] for job in queued], ["douyin", "tencent"])
        runtime._ensure_queue_worker.assert_awaited_once()

    async def test_tencent_queue_job_uses_single_publish_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video = root / "data" / "projects" / "51" / "releases" / "final-video.mp4"
            video.parent.mkdir(parents=True)
            video.write_bytes(b"video")
            job = {
                "id": "tencent-job-1",
                "project_id": 51,
                "project_title": "测试主题",
                "channel": "科技情报站",
                "platform": "tencent",
                "account_name": "default",
                "payload": {"platform": "tencent", "account_name": "default", "title": "测试标题"},
                "status": "queued",
                "stage": "等待发布",
                "attempts": 0,
                "max_attempts": 2,
                "created_at": 1,
                "updated_at": 1,
            }
            with (
                patch.object(storage, "DATA_ROOT", root / "data"),
                patch.object(storage, "CONFIG_ROOT", root / "config"),
            ):
                release_automation.save_release_queue({"jobs": [job]})
                runtime = release_automation.SocialAutoUploadRuntime()
                runtime._run_queue_action = AsyncMock(
                    return_value={"status": "succeeded", "result": {"published_release": {"url": "https://example.test/work"}}}
                )

                await runtime._process_queue_job(job)
                saved = release_automation.load_release_queue()["jobs"][0]

            self.assertEqual(saved["status"], "succeeded")
            self.assertEqual(
                [call.args[1] for call in runtime._run_queue_action.await_args_list],
                ["publish"],
            )


    async def test_failed_publish_persists_platform_log_and_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video = root / "data" / "projects" / "114" / "releases" / "final-video.mp4"
            video.parent.mkdir(parents=True)
            video.write_bytes(b"video")
            job = {
                "id": "xhs-failed-job",
                "project_id": 114,
                "project_title": "测试主题",
                "channel": "科技情报站",
                "platform": "xiaohongshu",
                "account_name": "default",
                "payload": {"platform": "xiaohongshu", "account_name": "default", "title": "测试标题"},
                "status": "queued",
                "stage": "等待发布",
                "attempts": 0,
                "max_attempts": 1,
                "created_at": 1,
                "updated_at": 1,
                "attempt_history": [],
            }
            failed_state = {
                "status": "failed",
                "error": "视频发布失败：RuntimeError: 发布按钮未找到",
                "log": "Traceback\nRuntimeError: 发布按钮未找到",
                "command": "uv run python sau_cli.py xiaohongshu upload-video",
                "cwd": str(root / "omnipost"),
                "result": {},
                "started_at": 2,
                "finished_at": 3,
            }
            with (
                patch.object(storage, "DATA_ROOT", root / "data"),
                patch.object(storage, "CONFIG_ROOT", root / "config"),
                patch.object(release_automation, "account_profile_is_fresh", return_value=True),
                patch.object(release_automation, "backfill_release_link", return_value=None),
                patch.object(release_automation, "submission_may_have_started", return_value=False),
                patch.object(release_automation.asyncio, "sleep", new=AsyncMock()),
            ):
                release_automation.save_release_queue({"jobs": [job]})
                runtime = release_automation.SocialAutoUploadRuntime()
                runtime._run_queue_action = AsyncMock(return_value=failed_state)

                await runtime._process_queue_job(job)
                saved = release_automation.load_release_queue()["jobs"][0]

        self.assertEqual(saved["status"], "failed")
        self.assertIn("发布按钮未找到", saved["log"])
        self.assertIn("sau_cli.py", saved["command"])
        self.assertEqual(saved["last_action"], "publish")
        self.assertEqual(len(saved["attempt_history"]), 1)

    async def test_submitted_but_unconfirmed_publish_waits_for_attention_without_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video = root / "data" / "projects" / "119" / "releases" / "final-video.mp4"
            video.parent.mkdir(parents=True)
            video.write_bytes(b"video")
            job = {
                "id": "douyin-unconfirmed-job",
                "project_id": 119,
                "project_title": "测试主题",
                "channel": "科技情报站",
                "platform": "douyin",
                "account_name": "default",
                "payload": {"platform": "douyin", "account_name": "default", "title": "测试标题"},
                "status": "queued",
                "stage": "等待发布",
                "attempts": 0,
                "max_attempts": 2,
                "created_at": 1,
                "updated_at": 1,
                "attempt_history": [],
            }
            failed_state = {
                "status": "failed",
                "error": "发布按钮已点击，平台没有返回明确结果",
                "log": "已点击发布按钮（本次提交第1次）",
                "command": "uv run python sau_cli.py douyin upload-video",
                "cwd": str(root / "omnipost"),
                "result": {},
                "started_at": 2,
                "finished_at": 3,
            }
            with (
                patch.object(storage, "DATA_ROOT", root / "data"),
                patch.object(storage, "CONFIG_ROOT", root / "config"),
                patch.object(release_automation, "account_profile_is_fresh", return_value=True),
                patch.object(release_automation, "_load_douyin_recent_works", return_value=[]),
                patch.object(release_automation, "backfill_release_link", return_value=None),
                patch.object(release_automation.asyncio, "sleep", new=AsyncMock()),
            ):
                release_automation.save_release_queue({"jobs": [job]})
                runtime = release_automation.SocialAutoUploadRuntime()
                runtime._run_queue_action = AsyncMock(return_value=failed_state)

                await runtime._process_queue_job(job)
                saved = release_automation.load_release_queue()["jobs"][0]

        self.assertEqual(saved["status"], "needs_attention")
        self.assertEqual(saved["stage"], "等待发布结果确认")
        self.assertIn("避免重复发布", saved["error"])
        self.assertEqual(runtime._run_queue_action.await_count, 1)

    async def test_release_metrics_runtime_returns_immediately_and_reuses_active_task(self) -> None:
        import asyncio
        import threading

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "data" / "projects" / "112").mkdir(parents=True, exist_ok=True)
            (root / "data" / "projects" / "112" / "project.json").write_text('{"id":112}', encoding="utf-8")
            entered = threading.Event()
            release = threading.Event()

            def slow_sync(project_id, **kwargs):
                callback = kwargs["progress_callback"]
                callback(
                    {
                        "stage": "syncing_account",
                        "message": "正在同步抖音 · 科技小地瓜",
                        "current_platform": "douyin",
                        "current_account": "default",
                        "current_account_display_name": "科技小地瓜",
                        "completed_accounts": 0,
                        "total_accounts": 1,
                        "succeeded_accounts": 0,
                        "failed_accounts": 0,
                        "accounts": [
                            {
                                "platform": "douyin",
                                "platform_label": "抖音",
                                "account_name": "default",
                                "account_display_name": "科技小地瓜",
                                "status": "running",
                                "message": "正在读取作品数据",
                            }
                        ],
                    }
                )
                entered.set()
                release.wait(timeout=2)
                return {"project_id": project_id, "message": "同步完成", "accounts": [], "errors": []}

            with (
                patch.object(storage, "DATA_ROOT", root / "data"),
                patch.object(storage, "PROJECTS_ROOT", root / "data" / "projects"),
                patch.object(storage, "CONFIG_ROOT", root / "config"),
                patch.object(release_automation, "sync_release_metrics", side_effect=slow_sync) as sync_mock,
                patch("app.creative_learning.sync_project_release_memory", return_value={}),
            ):
                runtime = release_automation.ReleaseMetricsSyncRuntime()
                first = await runtime.start(112)
                await asyncio.to_thread(entered.wait, 1)
                second = await runtime.start(112)
                active = runtime.status(112)
                release.set()
                for _ in range(50):
                    final = runtime.status(112)
                    if final and not final.get("running"):
                        break
                    await asyncio.sleep(0.01)

            self.assertTrue(first["running"])
            self.assertEqual(second["task_id"], first["task_id"])
            self.assertEqual(sync_mock.call_count, 1)
            self.assertEqual(active["current_account_display_name"], "科技小地瓜")
            self.assertEqual(final["status"], "succeeded")
            self.assertEqual(final["percent"], 100)

    async def test_release_metrics_runtime_exposes_failed_account_progress(self) -> None:
        import asyncio

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "data" / "projects" / "113").mkdir(parents=True, exist_ok=True)
            (root / "data" / "projects" / "113" / "project.json").write_text('{"id":113}', encoding="utf-8")

            def sync_with_account_failure(project_id, **kwargs):
                kwargs["progress_callback"](
                    {
                        "stage": "account_failed",
                        "message": "小红书 · account-b 读取失败：登录失效",
                        "current_platform": "xiaohongshu",
                        "current_account": "account-b",
                        "current_account_display_name": "橙子酱酱酱o76",
                        "completed_accounts": 2,
                        "total_accounts": 2,
                        "succeeded_accounts": 1,
                        "failed_accounts": 1,
                        "accounts": [
                            {"platform": "douyin", "account_name": "account-a", "status": "succeeded"},
                            {"platform": "xiaohongshu", "account_name": "account-b", "status": "failed", "message": "登录失效"},
                        ],
                    }
                )
                return {"project_id": project_id, "message": "读取 2 个账号，失败 1 个。", "accounts": [], "errors": [{}]}

            with (
                patch.object(storage, "DATA_ROOT", root / "data"),
                patch.object(storage, "PROJECTS_ROOT", root / "data" / "projects"),
                patch.object(storage, "CONFIG_ROOT", root / "config"),
                patch.object(release_automation, "sync_release_metrics", side_effect=sync_with_account_failure),
                patch("app.creative_learning.sync_project_release_memory", return_value={}),
            ):
                runtime = release_automation.ReleaseMetricsSyncRuntime()
                await runtime.start(113)
                for _ in range(50):
                    final = runtime.status(113)
                    if final and not final.get("running"):
                        break
                    await asyncio.sleep(0.01)

            self.assertEqual(final["status"], "succeeded")
            self.assertEqual(final["failed_accounts"], 1)
            self.assertEqual(final["accounts"][1]["status"], "failed")


class ReleaseRootCauseTests(unittest.TestCase):
    def test_tencent_root_cause_beats_cleanup_target_closed_error(self):
        log = """视频号发布流程失败: Locator.inner_text: strict mode violation: resolved to 2 elements
Future exception was never retrieved
patchright._impl._errors.TargetClosedError: Target page, context or browser has been closed
"""
        message = release_automation._release_command_failure_message("publish", "tencent", log, 1)
        self.assertIn("strict mode violation", message)
        self.assertNotIn("TargetClosedError", message)


if __name__ == "__main__":
    unittest.main()
