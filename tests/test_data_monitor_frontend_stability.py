from __future__ import annotations

import unittest
from pathlib import Path

import app as app_module


class DataMonitorFrontendStabilityTest(unittest.TestCase):
    def test_data_monitor_uses_central_asset_version(self) -> None:
        original = app_module.WEB_ACCESS_PASSWORD_SIGNATURE
        app_module.WEB_ACCESS_PASSWORD_SIGNATURE = ""
        try:
            response = app_module.app.test_client().get("/data-monitor?tab=stablecoins")
        finally:
            app_module.WEB_ACCESS_PASSWORD_SIGNATURE = original
        self.assertEqual(response.status_code, 200)
        self.assertIn("data-monitor-page.js?v=20260813-pollingfix1", response.get_data(as_text=True))

    def test_idle_pages_do_not_poll_and_pagehide_aborts_dynamic_request(self) -> None:
        source = (Path(app_module.__file__).parent / "static" / "data-monitor-page.js").read_text(encoding="utf-8")
        self.assertIn('panel.getAttribute("data-stablecoin-running") === "true"', source)
        self.assertIn('panel.getAttribute("data-cdn-running") === "true"', source)
        self.assertIn('window.addEventListener("pagehide"', source)
        self.assertIn("applovinRequestController.abort()", source)
