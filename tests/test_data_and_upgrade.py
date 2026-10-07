"""无损数据和本地升级的关键保护行为。"""

import shutil
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from carbonfact_app.catalog import ROOT, UPSTREAM, build_catalog, load_catalog, validate_catalog, verify_snapshot
from tools.prepare_upgrade import apply_upgrade, plan_upgrade


class DataTests(unittest.TestCase):
    def test_all_source_files_and_processed_values_match(self):
        self.assertEqual(verify_snapshot(), [])
        self.assertEqual(validate_catalog(load_catalog()), [])

    def test_counts_empty_rows_unknowns_and_units(self):
        c, a = build_catalog()
        self.assertEqual(len(c["factors"]), 304)
        self.assertEqual(len(a["empty_records_removed"]), 17)
        self.assertEqual(a["missing_dqr_records"], 19)
        self.assertEqual(a["missing_input_ratio_records"], 21)
        self.assertEqual(a["records_per_category"]["weaving"], 17)
        self.assertEqual(len(c["categories"]), 12)
        self.assertEqual({f["unit"] for f in c["factors"]}, {"kg", "m2", "pair", "min"})
        self.assertTrue(all(f["data_year"] is None for f in c["factors"]))
        self.assertTrue(all(f["activity_zh"] != f["activity_en"] for f in c["factors"]))

    def test_changed_processed_value_and_invalid_dqr_are_detected(self):
        c = copy.deepcopy(load_catalog())
        c["factors"][0]["impacts"]["GHG"] = "999"
        c["factors"][0]["dqr"]["P_dqr"] = "NaN"
        errors = validate_catalog(c)
        self.assertTrue(any("原值改变" in e for e in errors))
        self.assertTrue(any("DQR" in e for e in errors))


class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.target = Path(self.temp.name)
        (self.target / ".git").mkdir()
        (self.target / ".git/keep").write_text("git marker")
        (self.target / ".venv").mkdir()
        (self.target / ".venv/keep").write_text("environment marker")

    def tearDown(self):
        self.temp.cleanup()

    def copy_old(self, path):
        (self.target / path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(UPSTREAM / path, self.target / path)

    def test_matching_files_backup_unknown_and_git_are_preserved(self):
        self.copy_old("README.md")
        self.copy_old("datasets/dyeing/impact-scores.csv")
        extra = self.target / "datasets/dyeing/企业数据.txt"
        extra.write_text("personal")
        plan = plan_upgrade(self.target)
        self.assertTrue(plan["can_apply"])
        self.assertEqual(plan["extra_files_in_old_dirs"], ["datasets/dyeing/企业数据.txt"])
        backup = Path(apply_upgrade(plan))
        self.assertTrue((backup / "README.md").is_file())
        self.assertFalse((self.target / "README.md").exists())
        self.assertEqual(extra.read_text(), "personal")
        self.assertTrue((self.target / ".git/keep").is_file())
        self.assertTrue((self.target / ".venv/keep").is_file())
        self.assertIsNone(apply_upgrade(plan_upgrade(self.target)))

    def test_any_modified_source_aborts_all_moves(self):
        self.copy_old("README.md")
        self.copy_old("CHANGELOG.md")
        (self.target / "README.md").write_text("local edits")
        plan = plan_upgrade(self.target)
        self.assertFalse(plan["can_apply"])
        with self.assertRaises(ValueError):
            apply_upgrade(plan)
        self.assertTrue((self.target / "CHANGELOG.md").exists())
        self.assertFalse((self.target / "_upgrade_backup").exists())

    def test_changed_after_scan_is_not_moved(self):
        self.copy_old("README.md")
        plan = plan_upgrade(self.target)
        (self.target / "README.md").write_text("changed after scan")
        with self.assertRaises(ValueError):
            apply_upgrade(plan)

    def test_source_directory_symlink_is_not_followed(self):
        outside = self.target / "outside"
        (outside / "dyeing").mkdir(parents=True)
        shutil.copy2(UPSTREAM / "datasets/dyeing/impact-scores.csv", outside / "dyeing/impact-scores.csv")
        try:
            (self.target / "datasets").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("当前系统无符号链接权限")
        self.assertFalse(plan_upgrade(self.target)["can_apply"])
        self.assertTrue((outside / "dyeing/impact-scores.csv").is_file())

    def test_new_application_path_conflict_stops_old_file_moves(self):
        self.copy_old("README.md")
        local = self.target / "docs/中文入门.md"
        local.parent.mkdir()
        local.write_text("个人修改", encoding="utf-8")
        with tempfile.TemporaryDirectory() as folder:
            release = Path(folder)
            (release / "data").mkdir()
            (release / "data/upgrade_manifest.json").write_text(json.dumps({"docs/中文入门.md": hashlib.sha256(b"release").hexdigest()}))
            with patch("tools.prepare_upgrade.ROOT", release):
                manifest = json.loads((ROOT / "data/source_manifest.json").read_text())
                plan = plan_upgrade(self.target, manifest)
                self.assertFalse(plan["can_apply"])
                self.assertIn("docs/中文入门.md", plan["new_application_path_conflicts"])
                with self.assertRaises(ValueError):
                    apply_upgrade(plan)
        self.assertTrue((self.target / "README.md").exists())


if __name__ == "__main__":
    unittest.main()
