from __future__ import annotations

import unittest
from unittest.mock import patch

from app import ant_browser, services


class AntBrowserIntegrationTests(unittest.TestCase):
    def test_parse_launch_codes_preserves_order_and_removes_duplicates(self) -> None:
        self.assertEqual(
            ant_browser.parse_launch_codes("60osqx, IXG652\n60OSQX，SQ3OU5"),
            ["60OSQX", "IXG652", "SQ3OU5"],
        )

    def test_discover_accounts_uses_configured_code_order(self) -> None:
        profiles = [
            {"launchCode": "BBB222", "profileId": "p2", "profileName": "备用", "running": False},
            {"launchCode": "AAA111", "profileId": "p1", "profileName": "主号", "running": True,
             "debugReady": True, "debugPort": 30123},
        ]
        with patch.object(ant_browser.AntBrowserClient, "list_profiles", return_value=profiles):
            accounts = ant_browser.discover_accounts(
                {"ANT_BROWSER_LAUNCH_CODES": "AAA111,BBB222", "ANT_BROWSER_API_URL": "http://127.0.0.1:19876"}
            )
        self.assertEqual([item["code"] for item in accounts], ["AAA111", "BBB222"])
        self.assertEqual(accounts[0]["cdp_url"], "http://127.0.0.1:30123")
        self.assertEqual(accounts[1]["id"], "ant-bbb222")

    def test_discover_accounts_drops_configured_profiles_deleted_from_ant(self) -> None:
        profiles = [
            {"launchCode": "BBB222", "profileId": "p2", "profileName": "备用"},
            {"launchCode": "AAA111", "profileId": "p1", "profileName": "主号"},
        ]
        with patch.object(ant_browser.AntBrowserClient, "list_profiles", return_value=profiles):
            accounts = ant_browser.discover_accounts(
                {"ANT_BROWSER_LAUNCH_CODES": "AAA111,DELETED,BBB222"}
            )

        self.assertEqual([item["code"] for item in accounts], ["AAA111", "BBB222"])
        self.assertTrue(all(item["found"] for item in accounts))

    def test_discover_accounts_uses_all_current_profiles_when_config_is_empty(self) -> None:
        profiles = [
            {"launchCode": "BBB222", "profileName": "备用"},
            {"launchCode": "AAA111", "profileName": "主号"},
        ]
        with patch.object(ant_browser.AntBrowserClient, "list_profiles", return_value=profiles):
            accounts = ant_browser.discover_accounts({"ANT_BROWSER_LAUNCH_CODES": ""})

        self.assertEqual([item["code"] for item in accounts], ["AAA111", "BBB222"])

    def test_discover_accounts_does_not_promote_running_profiles(self) -> None:
        profiles = [
            {"launchCode": "SECOND", "profileName": "账号二", "running": True, "debugReady": True},
            {"launchCode": "FIRST", "profileName": "账号一", "running": False, "debugReady": False},
            {"launchCode": "THIRD", "profileName": "账号三", "running": True, "debugReady": True},
        ]
        with patch.object(ant_browser.AntBrowserClient, "list_profiles", return_value=profiles):
            accounts = ant_browser.discover_accounts({"ANT_BROWSER_LAUNCH_CODES": "FIRST,SECOND"})

        self.assertEqual([item["code"] for item in accounts], ["FIRST", "SECOND"])

    def test_service_uses_ant_accounts_without_local_profile_dirs(self) -> None:
        expected = [{"id": "ant-code01", "index": 1, "code": "CODE01", "provider": "ant_browser"}]
        with patch.object(ant_browser, "discover_accounts", return_value=expected):
            accounts = services.chatgpt_image_accounts({"CHATGPT_ACCOUNT_PROVIDER": "ant_browser"})
        self.assertEqual(accounts, expected)

    def test_pool_status_removes_deleted_codes_and_persists_configuration(self) -> None:
        env = {
            "CHATGPT_ACCOUNT_PROVIDER": "ant_browser",
            "ANT_BROWSER_LAUNCH_CODES": "AAA111,DELETED,BBB222",
        }
        accounts = [
            {
                "id": "ant-aaa111", "index": 1, "label": "主号", "port": 0,
                "profile_dir": None, "provider": "ant_browser", "code": "AAA111",
                "profile_id": "p1", "found": True,
            },
            {
                "id": "ant-bbb222", "index": 2, "label": "备用", "port": 0,
                "profile_dir": None, "provider": "ant_browser", "code": "BBB222",
                "profile_id": "p2", "found": True,
            },
        ]
        with (
            patch.object(services, "chatgpt_image_accounts", return_value=accounts),
            patch.object(services, "chatgpt_cdp_metadata", return_value={}),
            patch.object(services.storage, "save_env_patch") as save_env_patch,
            patch.object(services.storage, "write_json"),
        ):
            payload = services.chatgpt_account_pool_status(env)

        self.assertEqual(payload["configured_codes"], ["AAA111", "BBB222"])
        self.assertEqual([item["code"] for item in payload["accounts"]], ["AAA111", "BBB222"])
        save_env_patch.assert_called_once_with({"ANT_BROWSER_LAUNCH_CODES": "AAA111,BBB222"})

    def test_deleted_ant_health_is_cleaned_but_active_lease_is_retained(self) -> None:
        idle_id = "ant-deleted"
        active_id = "ant-active"
        active_lock = services.threading.Lock()
        active_lock.acquire()
        try:
            with services._CHATGPT_ACCOUNT_POOL_LOCK:
                services._CHATGPT_ACCOUNT_HEALTH[idle_id] = {"last_error": "profile not found"}
                services._CHATGPT_ACCOUNT_USE_LOCKS[idle_id] = services.threading.Lock()
                services._CHATGPT_ACCOUNT_HEALTH[active_id] = {"last_error": "running"}
                services._CHATGPT_ACCOUNT_USE_LOCKS[active_id] = active_lock
                services._CHATGPT_ACCOUNT_LEASES[active_id] = {"lock": active_lock}
            with patch.object(services.storage, "write_json") as write_json:
                services._reconcile_deleted_ant_account_state(set())
            self.assertNotIn(idle_id, services._CHATGPT_ACCOUNT_HEALTH)
            self.assertIn(active_id, services._CHATGPT_ACCOUNT_HEALTH)
            write_json.assert_called_once()
        finally:
            active_lock.release()
            with services._CHATGPT_ACCOUNT_POOL_LOCK:
                services._CHATGPT_ACCOUNT_HEALTH.pop(idle_id, None)
                services._CHATGPT_ACCOUNT_USE_LOCKS.pop(idle_id, None)
                services._CHATGPT_ACCOUNT_HEALTH.pop(active_id, None)
                services._CHATGPT_ACCOUNT_USE_LOCKS.pop(active_id, None)
                services._CHATGPT_ACCOUNT_LEASES.pop(active_id, None)

    def test_stop_and_wait_confirms_runtime_is_down(self) -> None:
        client = ant_browser.AntBrowserClient()
        with (
            patch.object(ant_browser.AntBrowserClient, "stop", return_value={"ok": True}) as stop,
            patch.object(
                ant_browser.AntBrowserClient,
                "runtime_status",
                side_effect=[
                    {"running": True, "debugReady": True},
                    {"running": False, "debugReady": False},
                ],
            ),
            patch.object(ant_browser.time, "sleep"),
        ):
            self.assertTrue(client.stop_and_wait("abc123", timeout_seconds=3))
        stop.assert_called_once_with("ABC123")


if __name__ == "__main__":
    unittest.main()
