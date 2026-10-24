import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ProductionCockpitContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.js = (ROOT / "app.js").read_text(encoding="utf-8")
        self.css = (ROOT / "styles.css").read_text(encoding="utf-8")

    def test_cockpit_has_one_copy_of_each_live_field(self) -> None:
        field_ids = [
            "production-cockpit-status",
            "production-cockpit-kind",
            "production-cockpit-action-title",
            "production-cockpit-action-detail",
            "production-cockpit-elapsed",
            "production-cockpit-eta",
            "production-cockpit-progress",
            "production-cockpit-human",
            "production-cockpit-budget-title",
            "production-cockpit-budget-detail",
            "production-cockpit-scenes",
            "production-cockpit-candidates",
            "production-cockpit-covers",
            "production-cockpit-image-calls",
            "production-cockpit-next",
            "production-cockpit-action",
        ]
        for field_id in field_ids:
            with self.subTest(field_id=field_id):
                self.assertEqual(self.html.count(f'id="{field_id}"'), 1)
                self.assertIn(f'getElementById("{field_id}")', self.js)

    def test_cockpit_reuses_runtime_state_and_exposes_budget_formula(self) -> None:
        self.assertIn("function productionRuntimeSnapshot(job)", self.js)
        self.assertIn("function productionBudgetSnapshot(job)", self.js)
        for runtime_kind in ("retrying", "external", "human", "stalled", "failed", "done"):
            self.assertIn(f'kind = "{runtime_kind}"', self.js)
        for budget_term in ("场景", "首镜备选 1", "封面"):
            self.assertIn(budget_term, self.js)
        self.assertNotIn('formula.push("主封面备选 1")', self.js)
        self.assertIn('formula.push("主封面 1（其它比例本地适配）")', self.js)

    def test_cockpit_is_full_width_and_cache_keys_are_updated(self) -> None:
        self.assertRegex(self.css, r"\.production-cockpit\s*\{[^}]*grid-column:\s*1\s*/\s*-1")
        self.assertIn("styles.css?v=20260910-model-dropdown-v2", self.html)
        self.assertIn("app.js?v=20261009-cpa-image-v3", self.html)

    def test_busy_chatgpt_account_uses_inline_status_instead_of_blocking_alert(self) -> None:
        self.assertIn('${account.busy ? "disabled" : ""}', self.js)
        self.assertIn('account.busy ? "生图结束后可打开"', self.js)
        self.assertIn('const statusEl = els.chatgptAccountPool.querySelector("[data-chatgpt-pool-status]");', self.js)

    def test_ant_browser_detection_saves_current_fields_and_updates_new_status_node(self) -> None:
        self.assertIn('data-test-ant-browser>保存、检测并刷新</button>', self.js)
        self.assertIn('CHATGPT_ACCOUNT_PROVIDER: "ant_browser"', self.js)
        self.assertIn('ANT_BROWSER_API_URL: apiUrl', self.js)
        self.assertIn('ANT_BROWSER_LAUNCH_CODES: codes', self.js)
        self.assertIn('const latestStatusEl = els.chatgptAccountPool.querySelector("[data-chatgpt-pool-status]");', self.js)
        self.assertIn('当前参与轮询 ${accountCount} 个。刷新时间 ${refreshedAt}', self.js)
        self.assertIn('method === "GET" ? { cache: "no-store" }', self.js)

    def test_live_job_log_is_visible_in_focus_mode_and_directly_reachable(self) -> None:
        self.assertIn('id="production-log-jump-btn"', self.html)
        self.assertIn('id="production-live-log-panel" class="card production-live-log-panel"', self.html)
        self.assertNotIn('id="production-live-log-panel" class="card production-live-log-panel advanced-only"', self.html)
        self.assertIn('productionLiveLogPanel?.scrollIntoView', self.js)
        self.assertIn('.production-live-log-panel .log-view', self.css)

    def test_step_launcher_is_visible_and_reuses_the_existing_job_action(self) -> None:
        self.assertEqual(self.html.count('id="run-job-btn"'), 1)
        self.assertEqual(self.html.count('id="selected-step-summary"'), 1)
        launcher_position = self.html.index('class="production-step-launch"')
        advanced_details_end = self.html.index('</details>', self.html.index('class="production-details advanced-only"'))
        self.assertGreater(launcher_position, advanced_details_end)
        self.assertIn('selectedStepSummary: document.getElementById("selected-step-summary")', self.js)
        self.assertIn('`开始执行 ${selectedStepCount} 个步骤`', self.js)
        self.assertIn('selectedStepCount === 0', self.js)
        self.assertIn('els.stepList?.addEventListener("change"', self.js)
        self.assertIn('await withBusyButton(els.runJobBtn, "正在启动..."', self.js)
        self.assertIn('.production-step-launch {', self.css)

    def test_common_advanced_actions_are_visible_before_account_menu(self) -> None:
        menu_position = self.html.index('<details class="production-more-menu">')
        for button_id in ("sample-image-btn", "resume-plan-btn", "next-to-files-btn"):
            with self.subTest(button_id=button_id):
                self.assertLess(self.html.index(f'id="{button_id}"'), menu_position)

    def test_focus_mode_is_default_and_advanced_tools_remain_reachable(self) -> None:
        self.assertIn('id="workspace-mode-toggle"', self.html)
        self.assertIn('data-enable-advanced-mode', self.html)
        self.assertIn('.studio-shell:not(.is-advanced-mode) .advanced-only', self.css)
        self.assertIn('advancedMode: storedAdvancedMode()', self.js)
        self.assertIn('function setAdvancedMode(enabled', self.js)
        self.assertIn('localStorage.setItem(UI_MODE_KEY', self.js)

    def test_topic_mining_shows_evidence_and_reuses_the_visible_best_candidate(self) -> None:
        self.assertIn("系统先检索近 7 天真实事件", self.js)
        self.assertIn("independent_source_count", self.js)
        self.assertIn("readiness_label", self.js)
        self.assertIn("AI 选最佳并成片", self.js)
        self.assertIn("selectedTopics: [best]", self.js)
        self.assertIn("topicPayload: draft.topicPayload || null", self.js)


if __name__ == "__main__":
    unittest.main()


