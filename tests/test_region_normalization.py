from __future__ import annotations

import unittest

from region_normalization import normalize_region_label


class RegionNormalizationTest(unittest.TestCase):
    def test_us_location_variants_share_one_label(self) -> None:
        for value in ("Boston, USA", "United States", "U.S.A.", "美国"):
            with self.subTest(value=value):
                self.assertEqual(normalize_region_label(value), "美国")

    def test_intentional_hierarchical_region_is_preserved(self) -> None:
        self.assertEqual(normalize_region_label("欧洲-英国"), "欧洲-英国")
        self.assertEqual(normalize_region_label("北美"), "北美")


if __name__ == "__main__":
    unittest.main()
