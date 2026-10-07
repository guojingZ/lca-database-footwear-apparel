"""覆盖前盘点旧快照；--apply 仅备份哈希一致的旧路径，不删除用户文件。"""

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def plan_upgrade(target, manifest=None):
    target = Path(target).resolve()
    if not target.is_dir():
        raise ValueError("目标项目目录不存在")
    manifest = manifest or json.loads((ROOT / "data/source_manifest.json").read_text(encoding="utf-8"))
    replacement_path = ROOT / "data/upgrade_manifest.json"
    replacements = json.loads(replacement_path.read_text(encoding="utf-8")) if replacement_path.exists() else {}
    target_release_marker = target / "data/upgrade_manifest.json"
    new_application_present = (replacement_path.exists() and target_release_marker.is_file() and
                               not target_release_marker.is_symlink() and
                               target_release_marker.read_bytes() == replacement_path.read_bytes())
    matching, modified, absent, already_new = [], [], [], []
    for item in manifest["files"]:
        file = target / item["path"]
        ancestors = [p for p in file.parents if p != target and p.is_relative_to(target)]
        if any(p.is_symlink() for p in ancestors):
            modified.append(item["path"])
        elif not file.exists() and not file.is_symlink():
            absent.append(item["path"])
        elif file.is_symlink() or not file.is_file():
            modified.append(item["path"])
        elif new_application_present and item["path"] in replacements and digest(file) == replacements[item["path"]]:
            already_new.append(item["path"])
        elif digest(file) == item["sha256"]:
            matching.append(item["path"])
        elif item["path"] in replacements and digest(file) == replacements[item["path"]]:
            already_new.append(item["path"])
        else:
            modified.append(item["path"])
    known = {i["path"] for i in manifest["files"]}
    application_conflicts = []
    if (target_release_marker.exists() or target_release_marker.is_symlink()) and (target_release_marker.is_symlink() or
                                         not target_release_marker.is_file() or
                                         target_release_marker.read_bytes() != replacement_path.read_bytes()):
        application_conflicts.append("data/upgrade_manifest.json")
    for rel, expected_hash in replacements.items():
        if rel in known:
            continue
        file = target / rel
        ancestors = [p for p in file.parents if p != target and p.is_relative_to(target)]
        if file.is_symlink() or any(p.is_symlink() for p in ancestors):
            application_conflicts.append(rel)
        elif file.exists() and (not file.is_file() or digest(file) != expected_hash):
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
    return {"target": str(target), "matching_old_files": matching, "modified_source_files": sorted(set(modified)),
            "extra_files_in_old_dirs": sorted(extras), "already_new_root_files": already_new,
            "absent_old_files": absent, "new_application_path_conflicts": application_conflicts,
            "can_apply": not modified and not application_conflicts,
            "preserved": [".git/", ".venv/", "venv/", ".env", "所有未知/自建文件"]}


def apply_upgrade(plan):
    if not plan["can_apply"]:
        raise ValueError("存在修改过的来源文件或新版同名路径冲突；先自行保存并对比，工具未移动任何文件")
    target = Path(plan["target"])
    files = plan["matching_old_files"]
    if not files:
        return None
    # 立即二次检查，避免盘点后文件改变时移动。
    fresh = plan_upgrade(target)
    if not fresh["can_apply"] or fresh["matching_old_files"] != files:
        raise ValueError("盘点后文件状态改变；请重新执行")
    folder = target / "_upgrade_backup" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    moved = []
    try:
        for rel in files:
            destination = folder / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target / rel), str(destination))
            moved.append(rel)
    except Exception:
        for rel in reversed(moved):
            (target / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(folder / rel), str(target / rel))
        raise
    (folder / "备份说明.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
            plan["backup_folder"] = apply_upgrade(plan)
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return int(not plan["can_apply"])
    except (ValueError, OSError) as exc:
        print("迁移停止：" + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
