"""数据盘点、整理、校验。运行：python tools/data_workbench.py audit|build|validate。"""

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from carbonfact_app.catalog import ROOT, IMPACTS, build_catalog, load_catalog, validate_catalog, verify_snapshot, write_json


def main():
    parser = argparse.ArgumentParser(description="Carbonfact 离线数据工具")
    parser.add_argument("command", choices=["audit", "build", "validate"])
    args = parser.parse_args()
    if args.command == "validate":
        errors = validate_catalog(load_catalog())
        print(json.dumps({"ok": not errors, "errors": errors}, ensure_ascii=False, indent=2))
        return int(bool(errors))
    errors = verify_snapshot()
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, ensure_ascii=False, indent=2))
        return 1
    catalog, audit = build_catalog()
    if args.command == "build":
        folder = ROOT / "data/processed"
        write_json(folder / "factors.json", catalog)
        write_json(folder / "audit.json", audit)
        fields = ["id", "descriptor", "activity_zh", "activity_en", "category", "unit", "input_ratio", *IMPACTS, "source_csv", "csv_record"]
        with (folder / "factors.csv").open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fields)
            writer.writeheader()
            for f in catalog["factors"]:
                writer.writerow({**{k: f[k] for k in fields if k in f}, **f["impacts"],
                                 "source_csv": f["source"]["csv"], "csv_record": f["source"]["csv_record"]})
    print(json.dumps({"ok": True, "command": args.command, "audit": audit}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
