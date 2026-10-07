"""离线读取、无损整理及来源校验。数值保留原始字符串。"""

import csv
import hashlib
import json
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / "upstream" / "carbonfact"
IMPACTS = ("ACD", "ETF", "FRU", "FWE", "GHG", "HTC", "HTN", "IOR",
           "LDU", "MRU", "OZD", "PCO", "PMA", "SWE", "TRE", "WTU")
DQR = ("P_dqr", "TiR_dqr", "TeR_dqr", "GR_dqr")
ATTRIBUTION = {
    "name": "Carbonfact — LCA Database for Footwear & Apparel",
    "repository": "https://github.com/carbonfact/lca-database-footwear-apparel",
    "website": "https://www.carbonfact.com/database",
    "license": "CC BY-SA 4.0",
    "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
    "citation": "upstream/carbonfact/CITATION.cff",
    "authors": ["Vincent Carrières", "Gustavo Vieira", "Laurent Vandepaer"],
    "doi": "10.5281/zenodo.21102755",
    "snapshot": "用户上传快照：引用文件 1.1.0，含 Unreleased；提交号未知",
    "modification": "v0.1.0：新增中文展示、字段归一与核算；原始影响数值未修改。",
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def factor_id(descriptor):
    return "cf-" + hashlib.sha256(descriptor.encode("utf-8")).hexdigest()[:16]


def raw_records(root=UPSTREAM):
    """csv_record 为包含表头的逻辑记录号；并非有换行引号时的物理行号。"""
    for path in sorted(Path(root).glob("datasets/**/impact-scores.csv")):
        with path.open(encoding="utf-8-sig", newline="") as stream:
            for number, row in enumerate(csv.DictReader(stream), 2):
                yield path, number, row


def verify_snapshot(root=UPSTREAM):
    manifest = read_json(ROOT / "data/source_manifest.json")
    errors = []
    expected = {f["path"]: f for f in manifest["files"]}
    actual = {p.relative_to(root).as_posix(): p for p in Path(root).rglob("*") if p.is_file()}
    for rel, item in expected.items():
        if rel not in actual:
            errors.append("来源文件缺失：" + rel)
        elif sha(actual[rel]) != item["sha256"]:
            errors.append("来源文件已改变：" + rel)
    for rel in actual.keys() - expected.keys():
        errors.append("上游快照中出现未登记文件：" + rel)
    return errors


def build_catalog():
    categories = read_json(ROOT / "data/categories.json")
    by_category = {c["id"]: c for c in categories}
    with (ROOT / "data/activity_names_zh.csv").open(encoding="utf-8-sig", newline="") as stream:
        names = {r["descriptor"]: r for r in csv.DictReader(stream)}
    factors, empty = [], []
    csv_counts = Counter()
    for path, number, raw in raw_records():
        rel = path.relative_to(UPSTREAM).as_posix()
        if not any((v or "").strip() for v in raw.values()):
            empty.append({"path": rel, "csv_record": number})
            continue
        descriptor = raw["descriptor"]
        if descriptor not in names:
            raise ValueError("缺中文名称：" + descriptor)
        category = path.relative_to(UPSTREAM / "datasets").parts[0]
        meta = by_category[category]
        unit = meta["unit"]
        fu = raw.get("Functional unit", "")
        if category == "shoe-assembly":
            unit = "pair" if "sneaker" in rel else "kg"
        if category == "use-phase":
            unit = "min" if "min" in fu else "kg"
        ratio = raw.get("Input_required_kg", raw.get("Input required (kg)"))
        ratio = ratio if ratio and ratio.strip() else None
        # 鞋类装配的总投入字段不作为单一纺织质量链转换依据。
        chain_allowed = category not in {"shoe-assembly", "synthetic-pu-leather", "natural-rubber", "use-phase"}
        method_files = sorted(p.relative_to(UPSTREAM).as_posix()
                              for p in (path.parent / "methodology").rglob("*")
                              if p.suffix.lower() in {".md", ".pdf"})
        factor = {
            "id": factor_id(descriptor), "descriptor": descriptor,
            "activity_zh": names[descriptor]["activity_zh"], "activity_en": raw["Activity"],
            "translation_status": names[descriptor]["status"],
            "category": category, "category_zh": meta["name"],
            "unit": unit, "functional_unit_original": fu or None,
            "unit_label": {"kg": "kg", "m2": "m²", "pair": "双", "min": "分钟"}[unit],
            "input_ratio": ratio, "mass_chain_allowed": chain_allowed,
            "impacts": {i: raw[i] for i in IMPACTS},
            "dqr": {i: raw.get(i) or None for i in DQR},
            "geography_tag": descriptor.rsplit("@", 1)[-1],
            "data_year": None, "boundary": meta["boundary"],
            "limitations": meta["limitations"],
            "kind": "material" if category == "natural-rubber" or descriptor.startswith("MATERIAL:") else "process",
            "source": {"csv": "upstream/carbonfact/" + rel, "csv_record": number,
                       "sha256": sha(path), "unit_evidence": "upstream/carbonfact/" + path.parent.relative_to(UPSTREAM).as_posix() + "/README.md",
                       "methods": ["upstream/carbonfact/" + p for p in method_files]},
            "raw": raw,
        }
        factors.append(factor)
        csv_counts[rel] += 1
    manifest = read_json(ROOT / "data/source_manifest.json")
    payload = {"schema_version": 1, "app_version": "0.1.0", "attribution": ATTRIBUTION,
               "snapshot_zip_sha256": manifest["original_zip_sha256"],
               "categories": categories, "factors": factors}
    payload["catalog_digest"] = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                                        separators=(",", ":")).encode()).hexdigest()
    audit = {"valid_records": len(factors), "empty_records_removed": empty,
             "records_per_csv": dict(csv_counts), "records_per_category": dict(Counter(f["category"] for f in factors)),
             "missing_dqr_records": sum(all(v is None for v in f["dqr"].values()) for f in factors),
             "missing_input_ratio_records": sum(f["input_ratio"] is None for f in factors),
             "numeric_source": "CSV 原始字符串，不以文档的舍入结果替换。",
             "known_differences": read_json(ROOT / "data/known_differences.json")}
    return payload, audit


def validate_catalog(catalog):
    errors = verify_snapshot()
    factors = catalog["factors"]
    for key in ("id", "descriptor"):
        if len({f[key] for f in factors}) != len(factors):
            errors.append(key + " 重复")
    if len(factors) != 304:
        errors.append("当前快照应有 304 条有效记录")
    for f in factors:
        if not f["activity_zh"] or f["unit"] not in {"kg", "m2", "pair", "min"}:
            errors.append("中文名或单位无效：" + f["id"])
        for code in IMPACTS:
            try:
                value = Decimal(f["impacts"][code])
                if not value.is_finite():
                    raise InvalidOperation
                if f["raw"][code] != f["impacts"][code]:
                    errors.append("原值改变：" + f["id"] + " / " + code)
            except (InvalidOperation, KeyError):
                errors.append("指标无效：" + f["id"] + " / " + code)
        for code, value in f["dqr"].items():
            if value is not None:
                try:
                    n = Decimal(value)
                    if not n.is_finite() or not Decimal(1) <= n <= Decimal(5):
                        raise InvalidOperation
                except (InvalidOperation, TypeError):
                    errors.append("DQR 无效或超范围：" + f["id"] + " / " + code)
        if f["input_ratio"] is not None:
            try:
                n = Decimal(f["input_ratio"])
                if not n.is_finite() or n <= 0:
                    raise InvalidOperation
            except (InvalidOperation, TypeError):
                errors.append("投入产出比无效：" + f["id"])
    rebuilt, _ = build_catalog()
    if rebuilt != catalog:
        errors.append("整理结果与当前上游、中文映射或类别元数据不一致，请重新 build")
    return errors


def load_catalog():
    return read_json(ROOT / "data/processed/factors.json")
