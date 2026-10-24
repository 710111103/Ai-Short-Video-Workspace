from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PublishDataPageTests(unittest.TestCase):
    def test_publish_and_analytics_have_separate_top_level_tabs(self) -> None:
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('data-tab="releases" data-step="4">发布</button>', html)
        self.assertIn('data-tab="analytics" data-step="5">数据</button>', html)
        self.assertIn('id="tab-releases" class="tab-panel"', html)
        self.assertIn('id="tab-analytics" class="tab-panel"', html)

    def test_publishing_controls_are_visible_and_data_dashboard_is_separate(self) -> None:
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        publish_start = html.index('<section id="tab-releases"')
        analytics_start = html.index('<section id="tab-analytics"')
        config_start = html.index('<section id="tab-config"')
        publish_html = html[publish_start:analytics_start]
        analytics_html = html[analytics_start:config_start]

        self.assertIn('class="release-legacy-controls"', publish_html)
        self.assertNotIn('class="release-legacy-controls" hidden', publish_html)
        self.assertIn('id="release-auto-publish-btn"', publish_html)
        self.assertIn('id="release-batch-targets"', publish_html)
        self.assertIn('id="release-queue-list"', publish_html)
        self.assertNotIn('id="release-platform-stats"', publish_html)

        self.assertIn('class="release-data-dashboard"', analytics_html)
        self.assertIn('id="release-platform-stats"', analytics_html)
        self.assertIn('id="sync-release-metrics-btn"', analytics_html)
        self.assertNotIn('id="release-auto-publish-btn"', analytics_html)

    def test_platform_work_rows_show_canonical_three_dimension_diagnosis(self) -> None:
        script = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn('const performance = item.performance || {};', script)
        self.assertIn('<small>播放潜力</small>', script)
        self.assertIn('<small>完播潜力</small>', script)
        self.assertIn('<small>评论潜力</small>', script)
        self.assertIn('performance.diagnosis || "数据仍在积累"', script)

    def test_each_tab_only_loads_its_own_runtime(self) -> None:
        script = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn('if (tab === "releases" && state.currentProject) {\n    refreshReleaseAutomation(true)', script)
        self.assertIn('if (tab === "analytics" && state.currentProject) {\n    refreshReleases({ autoSync: true })', script)
        self.assertNotIn(
            'if (tab === "releases" && state.currentProject) {\n    refreshReleaseAutomation(true).catch((error) => console.warn(error));\n    refreshReleases',
            script,
        )

    def test_data_page_shows_channel_strategy_without_controlling_content_editor(self) -> None:
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="content-learning-explanation"', html)
        self.assertIn('class="channel-strategy-card"', script)
        self.assertIn('function channelStrategyHtml(strategy = {})', script)
        self.assertIn('els.releasePlatformStats.innerHTML = strategyHtml + `', script)
        self.assertIn("当前最大问题", script)
        self.assertIn("已验证能力", script)
        self.assertIn("下一期实验", script)
        self.assertIn("观察指标", script)
        self.assertIn("Release metrics belong to the analytics page", script)
        self.assertNotIn("本期为什么这样写", script)
        self.assertNotIn("generation_reasons", script)


if __name__ == "__main__":
    unittest.main()
