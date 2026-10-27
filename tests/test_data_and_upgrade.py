"""无损数据和本地升级的关键保护行为。"""

import shutil
import copy
import csv
import hashlib
import io
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

    def test_line_endings_are_backed_up_without_rewriting(self):
        paths = ["README.md", "LICENSE", "datasets/natural-rubber/impact-scores.csv"]
        local_bytes = {}
        for rel in paths:
            self.copy_old(rel)
            local_bytes[rel] = (UPSTREAM / rel).read_bytes().replace(b"\r\n", b"\n")
            (self.target / rel).write_bytes(local_bytes[rel])
        plan = plan_upgrade(self.target)
        self.assertTrue(plan["can_apply"])
        self.assertEqual(set(plan["line_ending_only_files"]), set(paths))
        self.assertEqual(set(plan["matching_old_files"]), set(paths))
        backup = Path(apply_upgrade(plan))
        audit = json.loads((backup / "备份说明.json").read_text(encoding="utf-8"))
        for rel in paths:
            self.assertEqual((backup / rel).read_bytes(), local_bytes[rel])
            self.assertEqual(audit["backup_file_sha256"][rel], hashlib.sha256(local_bytes[rel]).hexdigest())
        self.assertEqual(verify_snapshot(), [])

    def test_crlf_checkout_of_lf_source_is_allowed(self):
        with tempfile.TemporaryDirectory() as folder:
            release = Path(folder)
            (release / "upstream/carbonfact").mkdir(parents=True)
            baseline = "原始内容\n第二行\n".encode("utf-8")
            (release / "upstream/carbonfact/README.md").write_bytes(baseline)
            manifest = {"files": [{"path": "README.md", "sha256": hashlib.sha256(baseline).hexdigest()}]}
            (release / "data").mkdir()
            (release / "data/source_manifest.json").write_text(json.dumps(manifest))
            local = baseline.replace(b"\n", b"\r\n")
            (self.target / "README.md").write_bytes(local)
            with patch("tools.prepare_upgrade.ROOT", release):
                plan = plan_upgrade(self.target)
                self.assertTrue(plan["can_apply"])
                self.assertEqual(plan["line_ending_only_files"], ["README.md"])
                backup = Path(apply_upgrade(plan))
            self.assertEqual((backup / "README.md").read_bytes(), local)

    def test_changed_csv_value_is_blocked_even_with_line_ending_change(self):
        rel = "datasets/natural-rubber/impact-scores.csv"
        self.copy_old(rel)
        local = (self.target / rel).read_bytes().replace(b"\r\n", b"\n")
        first = next(csv.DictReader(io.StringIO(local.decode("utf-8"))))
        value = first["GHG"].encode("utf-8")
        self.assertIn(value, local)
        (self.target / rel).write_bytes(local.replace(value, b"999999.123", 1))
        plan = plan_upgrade(self.target)
        self.assertFalse(plan["can_apply"])
        self.assertEqual(plan["modified_source_files"], [rel])
        with self.assertRaises(ValueError):
            apply_upgrade(plan)
        self.assertTrue((self.target / rel).is_file())

    def test_other_text_differences_are_not_ignored(self):
        rel = "README.md"
        self.copy_old(rel)
        baseline = (UPSTREAM / rel).read_bytes().replace(b"\r\n", b"\n")
        variants = {"行尾空格": baseline.replace(b"\n", b" \n", 1),
                    "BOM": b"\xef\xbb\xbf" + baseline,
                    "多一个换行": baseline + b"\n",
                    "单独CR": baseline.replace(b"\n", b"\r")}
        for label, content in variants.items():
            with self.subTest(label=label):
                (self.target / rel).write_bytes(content)
                plan = plan_upgrade(self.target)
                self.assertFalse(plan["can_apply"])
                self.assertEqual(plan["modified_source_files"], [rel])

    def test_pdf_line_ending_change_is_not_accepted(self):
        rel = "methodology/building-infrastructure.pdf"
        self.copy_old(rel)
        baseline = (UPSTREAM / rel).read_bytes()
        self.assertIn(b"\n", baseline)
        (self.target / rel).write_bytes(baseline.replace(b"\n", b"\r\n", 1))
        plan = plan_upgrade(self.target)
        self.assertFalse(plan["can_apply"])
        self.assertEqual(plan["modified_source_files"], [rel])

    def test_tampered_reference_cannot_approve_changed_content(self):
        manifest = json.loads((ROOT / "data/source_manifest.json").read_text())
        (self.target / "README.md").write_bytes(b"local change\n")
        with tempfile.TemporaryDirectory() as folder:
            release = Path(folder)
            (release / "upstream/carbonfact").mkdir(parents=True)
            (release / "upstream/carbonfact/README.md").write_bytes(b"local change\r\n")
            with patch("tools.prepare_upgrade.ROOT", release):
                plan = plan_upgrade(self.target, manifest)
        self.assertFalse(plan["can_apply"])
        self.assertEqual(plan["modified_source_files"], ["README.md"])

    def test_line_ending_change_after_scan_is_not_moved(self):
        self.copy_old("README.md")
        plan = plan_upgrade(self.target)
        local = (self.target / "README.md").read_bytes().replace(b"\r\n", b"\n")
        (self.target / "README.md").write_bytes(local)
        self.assertTrue(plan_upgrade(self.target)["can_apply"])
        with self.assertRaisesRegex(ValueError, "盘点后文件状态改变"):
            apply_upgrade(plan)
        self.assertEqual((self.target / "README.md").read_bytes(), local)
        self.assertFalse((self.target / "_upgrade_backup").exists())

    def test_new_application_with_crlf_is_not_backed_up_as_old(self):
        with tempfile.TemporaryDirectory() as folder:
            release = Path(folder)
            (release / "data").mkdir()
            (release / "upstream/carbonfact").mkdir(parents=True)
            shutil.copy2(UPSTREAM / "README.md", release / "upstream/carbonfact/README.md")
            old = {"files": [{"path": "README.md", "sha256": hashlib.sha256((UPSTREAM / "README.md").read_bytes()).hexdigest()}]}
            (release / "data/source_manifest.json").write_text(json.dumps(old))
            content = "新版中文入口\n".encode("utf-8")
            (release / "README.md").write_bytes(content)
            replacements = {"README.md": hashlib.sha256(content).hexdigest()}
            marker = (json.dumps(replacements, indent=2) + "\n").encode("utf-8")
            (release / "data/upgrade_manifest.json").write_bytes(marker)
            (self.target / "README.md").write_bytes(content.replace(b"\n", b"\r\n"))
            (self.target / "data").mkdir()
            (self.target / "data/upgrade_manifest.json").write_bytes(marker.replace(b"\n", b"\r\n"))
            with patch("tools.prepare_upgrade.ROOT", release):
                plan = plan_upgrade(self.target)
                self.assertTrue(plan["can_apply"])
                self.assertEqual(plan["already_new_root_files"], ["README.md"])
                self.assertEqual(plan["matching_old_files"], [])
                self.assertIsNone(apply_upgrade(plan))
            self.assertFalse((self.target / "_upgrade_backup").exists())
            self.assertEqual((self.target / "README.md").read_bytes(), content.replace(b"\n", b"\r\n"))

    def test_backup_directory_symlink_is_rejected(self):
        self.copy_old("README.md")
        outside = self.target / "个人目录"
        outside.mkdir()
        try:
            (self.target / "_upgrade_backup").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("当前系统无符号链接权限")
        with self.assertRaisesRegex(ValueError, "本地普通目录"):
            apply_upgrade(plan_upgrade(self.target))
        self.assertTrue((self.target / "README.md").is_file())
        self.assertEqual(list(outside.iterdir()), [])

    def test_move_failure_rolls_back_and_retry_succeeds(self):
        for rel in ["README.md", "CHANGELOG.md"]:
            self.copy_old(rel)
        original = {rel: (self.target / rel).read_bytes() for rel in ["README.md", "CHANGELOG.md"]}
        real_move = shutil.move
        calls = 0

        def fail_on_second_move(source, destination):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("模拟文件被占用")
            return real_move(source, destination)

        with patch("tools.prepare_upgrade.shutil.move", side_effect=fail_on_second_move):
            with self.assertRaisesRegex(OSError, "模拟文件被占用"):
                apply_upgrade(plan_upgrade(self.target))
        for rel, content in original.items():
            self.assertEqual((self.target / rel).read_bytes(), content)
        backup = Path(apply_upgrade(plan_upgrade(self.target)))
        for rel, content in original.items():
            self.assertEqual((backup / rel).read_bytes(), content)
        self.assertTrue((self.target / ".git/keep").is_file())

    def test_backup_metadata_failure_rolls_back_files(self):
        self.copy_old("README.md")
        baseline = (self.target / "README.md").read_bytes()
        real_write = Path.write_text

        def fail_metadata(path, *args, **kwargs):
            if path.name == "备份说明.json":
                raise OSError("模拟备份说明无法写入")
            return real_write(path, *args, **kwargs)

        with patch("pathlib.Path.write_text", autospec=True, side_effect=fail_metadata):
            with self.assertRaisesRegex(OSError, "模拟备份说明无法写入"):
                apply_upgrade(plan_upgrade(self.target))
        self.assertEqual((self.target / "README.md").read_bytes(), baseline)


if __name__ == "__main__":
    unittest.main()
