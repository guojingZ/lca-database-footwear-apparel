"""覆盖前盘点旧快照；--apply 备份原字节一致或仅 CRLF/LF 不同的旧文件。"""

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".md", ".csv", ".json", ".py", ".yml", ".yaml", ".cff",
                 ".txt", ".js", ".cjs", ".html", ".css"}
TEXT_NAMES = {"LICENSE", "CODEOWNERS", ".gitignore", ".gitattributes"}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare_bytes(content, reference, expected_hash):
    """只接受原哈希或 UTF-8 文本的 CRLF/LF 差异；参考文件也必须符合清单。"""
    actual_hash = hashlib.sha256(content).hexdigest()
    if actual_hash == expected_hash:
        return "exact", actual_hash
    reference = Path(reference)
    if reference.suffix.lower() not in TEXT_SUFFIXES and reference.name not in TEXT_NAMES:
        return None, actual_hash
    if reference.is_symlink() or not reference.is_file():
        return None, actual_hash
    baseline = reference.read_bytes()
    if hashlib.sha256(baseline).hexdigest() != expected_hash:
        return None, actual_hash
    if b"\x00" in content or b"\x00" in baseline:
        return None, actual_hash
    try:
        content.decode("utf-8")
        baseline.decode("utf-8")
    except UnicodeDecodeError:
        return None, actual_hash
    if content.replace(b"\r\n", b"\n") == baseline.replace(b"\r\n", b"\n"):
        return "line_endings", actual_hash
    return None, actual_hash


def has_symlink_parent(file, target):
    return any(p.is_symlink() for p in file.parents if p != target and p.is_relative_to(target))


def public_plan(plan):
    return {key: value for key, value in plan.items() if not key.startswith("_")}


def plan_upgrade(target, manifest=None):
    target = Path(target).resolve()
    if not target.is_dir():
        raise ValueError("目标项目目录不存在")
    manifest = manifest or json.loads((ROOT / "data/source_manifest.json").read_text(encoding="utf-8"))
    replacement_path = ROOT / "data/upgrade_manifest.json"
    replacements = json.loads(replacement_path.read_text(encoding="utf-8")) if replacement_path.exists() else {}
    target_release_marker = target / "data/upgrade_manifest.json"
    new_application_present = False
    if (replacement_path.is_file() and target_release_marker.is_file() and
            not target_release_marker.is_symlink() and not has_symlink_parent(target_release_marker, target)):
        new_application_present = bool(compare_bytes(target_release_marker.read_bytes(), replacement_path,
                                                     digest(replacement_path))[0])
    matching, modified, absent, already_new, line_endings = [], [], [], [], []
    raw_hashes = {}
    for item in manifest["files"]:
        file = target / item["path"]
        if has_symlink_parent(file, target):
            modified.append(item["path"])
        elif not file.exists() and not file.is_symlink():
            absent.append(item["path"])
        elif file.is_symlink() or not file.is_file():
            modified.append(item["path"])
        else:
            content = file.read_bytes()
            replacement_match = (compare_bytes(content, ROOT / item["path"], replacements[item["path"]])[0]
                                 if item["path"] in replacements else None)
            source_match, actual_hash = compare_bytes(content, ROOT / "upstream/carbonfact" / item["path"],
                                                      item["sha256"])
            if new_application_present and replacement_match:
                already_new.append(item["path"])
            elif source_match:
                matching.append(item["path"])
                raw_hashes[item["path"]] = actual_hash
                if source_match == "line_endings":
                    line_endings.append(item["path"])
            elif replacement_match:
                already_new.append(item["path"])
            else:
                modified.append(item["path"])
    known = {i["path"] for i in manifest["files"]}
    application_conflicts = []
    if (target_release_marker.exists() or target_release_marker.is_symlink()) and not new_application_present:
        application_conflicts.append("data/upgrade_manifest.json")
    for rel, expected_hash in replacements.items():
        if rel in known:
            continue
        file = target / rel
        if file.is_symlink() or has_symlink_parent(file, target):
            application_conflicts.append(rel)
        elif file.exists() and (not file.is_file() or not compare_bytes(file.read_bytes(), ROOT / rel, expected_hash)[0]):
            application_conflicts.append(rel)
    extras = []
    # 只检查旧来源目录和旧根文件；Git、环境、个人资料从不进入备份范围。
    old_dirs = {Path(p).parts[0] for p in known if len(Path(p).parts) > 1}
    for name in sorted(old_dirs):
        base = target / name
        if base.is_symlink():
            modified.append(name + "/（符号链接）")
            continue
        if base.is_dir():
            extras.extend(p.relative_to(target).as_posix() for p in base.rglob("*")
                          if p.is_file() and p.relative_to(target).as_posix() not in known)
    return {"target": str(target), "matching_old_files": matching, "line_ending_only_files": line_endings,
            "modified_source_files": sorted(set(modified)),
            "extra_files_in_old_dirs": sorted(extras), "already_new_root_files": already_new,
            "absent_old_files": absent, "new_application_path_conflicts": application_conflicts,
            "can_apply": not modified and not application_conflicts,
            "preserved": [".git/", ".venv/", "venv/", ".env", "所有未知/自建文件"],
            "_matching_raw_hashes": raw_hashes}


def apply_upgrade(plan):
    if not plan["can_apply"]:
        raise ValueError("存在修改过的来源文件或新版同名路径冲突；先自行保存并对比，工具未移动任何文件")
    target = Path(plan["target"])
    files = plan["matching_old_files"]
    if not files:
        return None
    # 立即二次检查，避免盘点后文件改变时移动。
    fresh = plan_upgrade(target)
    if (not fresh["can_apply"] or fresh["matching_old_files"] != files or
            fresh["_matching_raw_hashes"] != plan["_matching_raw_hashes"]):
        raise ValueError("盘点后文件状态改变；请重新执行")
    backup_root = target / "_upgrade_backup"
    if backup_root.is_symlink() or (backup_root.exists() and not backup_root.is_dir()):
        raise ValueError("_upgrade_backup 必须是本地普通目录；工具未移动任何文件")
    folder = target / "_upgrade_backup" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    moved = []
    try:
        folder.mkdir(parents=True, exist_ok=False)
        for rel in files:
            source = target / rel
            if (source.is_symlink() or has_symlink_parent(source, target) or
                    not source.is_file() or digest(source) != plan["_matching_raw_hashes"][rel]):
                raise ValueError("移动前文件状态改变：" + rel + "；请重新执行")
            destination = folder / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            moved.append(rel)
        audit = public_plan(plan)
        audit["backup_folder"] = str(folder)
        audit["backup_file_sha256"] = plan["_matching_raw_hashes"]
        (folder / "备份说明.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception as exc:
        rollback_errors = []
        for rel in reversed(moved):
            try:
                (target / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(folder / rel), str(target / rel))
            except OSError as rollback_exc:
                rollback_errors.append(rel + ": " + str(rollback_exc))
        if rollback_errors:
            raise OSError("备份失败且回滚未完成；请保留 " + str(folder) + "；" + "; ".join(rollback_errors)) from exc
        raise
    # 只清理已经空的旧来源目录；未知文件所在目录保留。
    old_dirs = {Path(p).parts[0] for p in files if len(Path(p).parts) > 1}
    for name in old_dirs:
        base = target / name
        if base.is_dir():
            for p in sorted((p for p in base.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)):
                if not any(p.iterdir()):
                    p.rmdir()
            if not any(base.iterdir()):
                base.rmdir()
    return str(folder)


def main():
    parser = argparse.ArgumentParser(description="旧 Carbonfact 快照安全迁移")
    parser.add_argument("--target", required=True, type=Path, help="已有 Git 项目的根目录")
    parser.add_argument("--apply", action="store_true", help="移动匹配的旧文件到备份；默认只盘点")
    args = parser.parse_args()
    try:
        plan = plan_upgrade(args.target)
        if args.apply:
            if not plan["can_apply"]:
                print(json.dumps(public_plan(plan), ensure_ascii=False, indent=2))
            plan["backup_folder"] = apply_upgrade(plan)
        print(json.dumps(public_plan(plan), ensure_ascii=False, indent=2))
        return int(not plan["can_apply"])
    except (ValueError, OSError) as exc:
        print("迁移停止：" + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
