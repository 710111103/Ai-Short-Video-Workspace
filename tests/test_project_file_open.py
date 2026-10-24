from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from app import main


class ProjectFileOpenTests(unittest.TestCase):
    def test_existing_project_video_is_opened_by_the_os(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "100"
            video = project_root / "releases" / "final-video.mp4"
            video.parent.mkdir(parents=True)
            video.write_bytes(b"video")

            with (
                patch.object(main, "ensure_project", return_value={"id": 100}),
                patch.object(main.storage, "project_dir", return_value=project_root),
                patch.object(main, "ensure_windows_file_read_access") as grant_access,
                patch.object(main, "open_path", return_value={"ok": True, "path": str(video)}) as opener,
            ):
                result = main.api_open_project_file(
                    100,
                    main.ProjectFileOpenPayload(path="releases/final-video.mp4"),
                )

            self.assertTrue(result["ok"])
            grant_access.assert_called_once_with(video.resolve())
            opener.assert_called_once_with(video.resolve())

    def test_project_file_cannot_escape_project_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "100"
            project_root.mkdir()

            with (
                patch.object(main, "ensure_project", return_value={"id": 100}),
                patch.object(main.storage, "project_dir", return_value=project_root),
            ):
                with self.assertRaises(HTTPException) as context:
                    main.api_open_project_file(
                        100,
                        main.ProjectFileOpenPayload(path="../outside.mp4"),
                    )

            self.assertEqual(context.exception.status_code, 400)


class DesktopOpenContractTests(unittest.TestCase):
    def test_mp4_buttons_use_desktop_file_opening(self) -> None:
        root = Path(__file__).resolve().parents[1]
        js = (root / "app.js").read_text(encoding="utf-8")

        self.assertIn('data-open-project-file="releases/final-video.mp4"', js)
        self.assertIn("/open-file`, {", js)
        self.assertNotIn('data-open-file="${escapeHtml(versionedProjectUrl(finalVideo))}">打开 mp4', js)

    def test_launcher_does_not_pause_or_trust_stale_spawn_errorlevel(self) -> None:
        root = Path(__file__).resolve().parents[1]
        launcher = (root / "run.bat").read_text(encoding="utf-8")

        self.assertNotIn("pause", launcher.lower())
        self.assertNotIn("Failed to spawn backend process", launcher)
        self.assertIn("for /l %%i in (1,1,20)", launcher)


if __name__ == "__main__":
    unittest.main()
