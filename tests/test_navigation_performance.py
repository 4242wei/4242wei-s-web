from __future__ import annotations

import re
import unittest
from pathlib import Path

import app as app_module


class NavigationPerformanceTests(unittest.TestCase):
    def test_incremental_summary_matches_previous_contract(self) -> None:
        source = "  第一段\n\n第二段\t" + ("很长的专家访谈内容 " * 2000)
        limit = 180
        previous = re.sub(r"\s+", " ", source).strip()
        previous = previous if len(previous) <= limit else previous[: limit - 3].rstrip() + "..."
        self.assertEqual(app_module.summarize_text_block(source, limit=limit), previous)

    def test_empty_excerpt_uses_fallback(self) -> None:
        self.assertEqual(app_module.build_match_excerpt(" \n\t ", [], "暂无摘要"), "暂无摘要")

    def test_navigation_prefetch_does_not_intercept_clicks(self) -> None:
        app_root = Path(app_module.__file__).resolve().parent
        script = (app_root / "static" / "instant-navigation.js").read_text(encoding="utf-8")
        self.assertIn('HTMLScriptElement.supports("speculationrules")', script)
        self.assertIn('hint.rel = "prefetch"', script)
        self.assertNotIn("preventDefault", script)

    def test_cloud_breathing_is_slow_and_scoped(self) -> None:
        app_root = Path(app_module.__file__).resolve().parent
        style = (app_root / "static" / "style.css").read_text(encoding="utf-8")
        self.assertIn('@keyframes cloudStageSweepA', style)
        self.assertIn('@keyframes cloudStageSweepB', style)
        self.assertIn('@keyframes cloudStageSweepC', style)
        self.assertIn('@keyframes cloudStageSweepD', style)
        self.assertIn('@keyframes cloudStageSweepE', style)
        self.assertIn('@keyframes cloudCorePulseA', style)
        self.assertIn('@keyframes cloudCorePulseB', style)
        self.assertIn('@keyframes cloudCorePulseC', style)
        self.assertIn('animation: cloudStageSweepA 18s', style)
        self.assertIn('animation: cloudStageSweepD 23s', style)
        self.assertIn('animation: cloudStageSweepB 27s', style)
        self.assertIn('animation: cloudStageSweepE 33s', style)
        self.assertIn('animation: cloudStageSweepC 39s', style)
        self.assertIn('--page-stars: none', style)
        self.assertGreater(
            style.rfind('Final precedence for the dedicated cloud stage'),
            style.rfind('Three favorite themes use independent cloud sheets'),
        )
        for name in "ABCDE":
            keyframe_start = style.index(f'@keyframes cloudStageSweep{name}')
            keyframe_end = style.find('\n}', keyframe_start) + 2
            keyframe = style[keyframe_start:keyframe_end]
            self.assertNotIn('filter:', keyframe)
            self.assertNotIn('background:', keyframe)
        for name in "ABC":
            keyframe_start = style.index(f'@keyframes cloudCorePulse{name}')
            keyframe_end = style.find('\n}', keyframe_start) + 2
            keyframe = style[keyframe_start:keyframe_end]
            self.assertNotIn('filter:', keyframe)
            self.assertNotIn('background:', keyframe)
        for theme in ("citrus-bloom", "sky-confetti", "aurora-glass"):
            self.assertIn(f'html[data-theme="{theme}"] .page-shell::before', style)
        for theme in ("cherry-picnic", "tidal-spark", "lavender-soda"):
            self.assertNotIn(f'html[data-theme="{theme}"] .page-shell::before', style)

    def test_theme_motion_toggle_is_persistent_and_non_destructive(self) -> None:
        app_root = Path(app_module.__file__).resolve().parent
        script = (app_root / "static" / "theme-switcher.js").read_text(encoding="utf-8")
        self.assertIn('const MOTION_STORAGE_KEY = "workspace-theme-motion"', script)
        self.assertIn('setAttribute("data-theme-motion", resolvedMotion)', script)
        self.assertIn('motionState.textContent = isEnabled ? "开" : "关"', script)
        self.assertIn('stage.className = "theme-cloud-stage"', script)
        self.assertIn('["a", "b", "c", "d", "e"]', script)
        self.assertIn('["a", "b", "c"].forEach(function (coreName)', script)
        self.assertNotIn("setInterval", script)


if __name__ == "__main__":
    unittest.main()
