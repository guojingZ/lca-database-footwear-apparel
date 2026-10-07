"""命令行复用网页后台计算：python tools/calculate.py examples/tshirt.json。"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from carbonfact_app.catalog import load_catalog, validate_catalog
from carbonfact_app.engine import calculate, compare, export_model


def main():
    parser = argparse.ArgumentParser(description="确定性核算/比较/模型导出")
    parser.add_argument("model", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--export", action="store_true")
    args = parser.parse_args()
    model = json.loads(args.model.read_text(encoding="utf-8-sig"))
    model = model.get("model", model)
    catalog = load_catalog()
    errors = validate_catalog(catalog)
    if errors:
        print(json.dumps({"valid": False, "errors": errors}, ensure_ascii=False, indent=2))
        return 1
    if args.baseline:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8-sig"))
        result = compare(model, baseline.get("model", baseline), catalog)
    else:
        result = export_model(model, catalog) if args.export else calculate(model, catalog)
    content = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
    else:
        print(content, end="")
    return int(not result.get("valid", result.get("current", result.get("result", {})).get("valid", False)))


if __name__ == "__main__":
    raise SystemExit(main())
