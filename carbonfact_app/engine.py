"""确定性质量链与独立投入清单核算；仅计算 GHG，保留证据和缺项。"""

import hashlib
import json
from decimal import Decimal, InvalidOperation, localcontext

from .catalog import ATTRIBUTION

UNITS = {"kg", "g", "m2", "pair", "min", "kWh", "MJ", "m3", "L", "item", "km", "tkm"}


def number(value, label, minimum=Decimal(0), positive=False):
    if isinstance(value, bool) or value is None or str(value).strip() == "":
        raise ValueError(label + " 必须是数值")
    try:
        n = Decimal(str(value))
    except InvalidOperation:
        raise ValueError(label + " 必须是数值") from None
    if not n.is_finite() or n < minimum or (positive and n == 0) or abs(n) > Decimal("1e15"):
        raise ValueError(label + " 数值超出范围")
    return n


def ds(value):
    if value is None:
        return None
    return format(value, "f")


def convert(quantity, unit, target):
    if unit == target:
        return quantity
    conversions = {("g", "kg"): Decimal("0.001"), ("kg", "g"): Decimal(1000),
                   ("L", "m3"): Decimal("0.001"), ("m3", "L"): Decimal(1000)}
    if (unit, target) not in conversions:
        raise ValueError("无法自动转换单位：" + unit + " → " + target)
    return quantity * conversions[(unit, target)]


def calculate(model, catalog):
    """相同模型及目录生成相同结果；无时间戳参与哈希或计算。"""
    with localcontext() as context:
        context.prec = 40
        return _calculate(model, catalog)


def _calculate(model, catalog):
    if not isinstance(model, dict):
        raise ValueError("模型应为 JSON 对象")
    for key in ("chain", "materials", "external_factors", "additional_items", "required_stages"):
        items = model.get(key, [])
        if not isinstance(items, list) or len(items) > 1000 or any(not isinstance(item, dict) for item in items):
            raise ValueError(key + " 应为不超过 1000 项的对象数组")
    for stage in model.get("chain", []):
        items = stage.get("inventory", [])
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise ValueError("inventory 应为对象数组")
    errors, missing, warnings, contributions, quantities = [], [], [], [], []
    if model.get("schema_version") != 1:
        errors.append("模型 schema_version 必须为 1")
    if model.get("catalog_digest") != catalog["catalog_digest"]:
        errors.append("模型目录版本不匹配；请重新选用当前目录因子，不能静默更新旧结果")
    if not str(model.get("name", "")).strip() or not str(model.get("boundary", "")).strip():
        errors.append("需填写产品/批次名称及核算边界")
    if model.get("result_basis") not in {"item", "batch"}:
        errors.append("结果口径须为 item（每件）或 batch（本批次）")
    if model.get("boundary_reviewed") is not True:
        missing.append({"id": "boundary", "message": "尚未确认目标边界、必需环节及所选因子的适用性"})
    factors = {f["id"]: f for f in catalog["factors"]}
    custom_seen = set()
    for custom in model.get("external_factors", []):
        cid = custom.get("id", "")
        try:
            if not cid.startswith("ext-") or cid in factors or cid in custom_seen:
                raise ValueError("外部因子 id 必须为唯一 ext- 标识")
            if not all(str(custom.get(k, "")).strip() for k in ("name", "source", "scope")):
                raise ValueError("外部因子需名称、来源和适用范围")
            if custom.get("unit") not in UNITS:
                raise ValueError("外部因子单位不受支持")
            if custom.get("status") not in {"reviewed", "pending", "hypothetical"}:
                raise ValueError("外部因子状态需为 reviewed、pending 或 hypothetical")
            value = number(custom.get("ghg"), "外部因子 GHG")
            factors[cid] = {"id": cid, "activity_zh": custom["name"], "unit": custom["unit"],
                            "kind": custom.get("kind", "process"), "mass_chain_allowed": True,
                            "impacts": {"GHG": ds(value)}, "input_ratio": None,
                            "source": {"reference": custom["source"], "scope": custom["scope"]},
                            "status": custom["status"], "category": "external"}
            custom_seen.add(cid)
        except ValueError as exc:
            errors.append(str(exc) + "：" + str(cid))

    def resolve(fid, label, kind=None):
        if not fid:
            missing.append({"id": label, "message": label + " 缺因子"})
            return None
        factor = factors.get(fid)
        if factor is None:
            errors.append(label + " 引用未知因子 " + str(fid))
            return None
        if kind and factor.get("kind") != kind:
            errors.append(label + " 因子类型不符：需要 " + kind)
            return None
        if factor.get("status") in {"pending", "hypothetical"}:
            missing.append({"id": label + "/review", "message": label + " 使用待审阅或假设因子"})
        return factor

    def contribute(cid, name, quantity, unit, factor, extra=None):
        if factor is None:
            return
        if quantity is None:
            missing.append({"id": cid + "/quantity", "message": name + " 的上游数量尚不能确定"})
            return
        try:
            activity = convert(quantity, unit, factor["unit"])
        except ValueError as exc:
            errors.append(name + "：" + str(exc))
            return
        value = Decimal(factor["impacts"]["GHG"])
        contributions.append({"id": cid, "name": name, "quantity": ds(activity), "unit": factor["unit"],
                              "factor_id": factor["id"], "factor_name": factor["activity_zh"],
                              "factor_ghg": ds(value), "ghg": ds(activity * value),
                              "formula": f"{ds(activity)} × {ds(value)}",
                              "source": factor["source"], "status": factor.get("status", "published"),
                              **(extra or {})})

    try:
        final_mass = number(model.get("weight_g"), "最终质量（g）", positive=True) / 1000
    except ValueError as exc:
        errors.append(str(exc))
        final_mass = None
    chain = model.get("chain", [])
    if not isinstance(chain, list) or not chain:
        errors.append("质量链至少需要一个工序")
        chain = []
    ids = [s.get("id") for s in chain]
    if any(not i for i in ids) or len(set(ids)) != len(ids):
        errors.append("工序实例 id 缺失或重复")
    for requirement in model.get("required_stages", []):
        if requirement.get("id") not in ids:
            missing.append({"id": "stage/" + str(requirement.get("id")),
                            "message": "必需工序缺失：" + requirement.get("name", "未命名")})
    used_factors = {}
    for stage in chain:
        fid = stage.get("factor_id")
        if stage.get("mode", "factor") == "factor" and fid:
            if fid in used_factors and not str(stage.get("repeat_reason", "")).strip():
                errors.append(stage.get("name", "工序") + " 与 " + used_factors[fid] + " 重复因子；真实重复加工需填写 repeat_reason")
            used_factors[fid] = stage.get("name", "工序")
    dye_present = any(factors.get(s.get("factor_id"), {}).get("category") == "dyeing" for s in chain)
    weave_present = any(factors.get(s.get("factor_id"), {}).get("category") == "weaving" for s in chain)
    downstream = final_mass
    stages_reversed = []
    for stage in reversed(chain):
        sid, name = stage.get("id", ""), stage.get("name", "未命名工序")
        mode = stage.get("mode", "factor")
        factor = None
        if mode == "factor":
            if stage.get("inventory"):
                errors.append(name + " 不能同时叠加整项因子与投入清单")
            factor = resolve(stage.get("factor_id"), name, "process")
            if factor:
                if factor["unit"] != "kg" or not factor.get("mass_chain_allowed"):
                    errors.append(name + " 不能进入单一纺织质量链；请用独立定量项目")
                descriptor = factor.get("descriptor", "")
                overlap = (dye_present and "/CAN_DRY" in descriptor) or (weave_present and "/SIZING/" in descriptor)
                if overlap:
                    warnings.append(name + " 可能与染色内含干燥或机织准备环节重叠")
                    if not str(stage.get("overlap_review", "")).strip():
                        missing.append({"id": sid + "/overlap", "message": name + " 需填写边界复核依据（overlap_review）"})
                if "INDIGO" in descriptor:
                    warnings.append(name + " 使用还原染料背景代理，不能视为专属靛蓝清单")
                if factor.get("category") == "textile-assembly":
                    warnings.append(name + " 专属说明包含缝纫线、包装及裁剪损失；与通用损耗说明存在差异，须核对外置处理及补充项目是否重复")
                    if not str(stage.get("overlap_review", "")).strip():
                        missing.append({"id": sid + "/overlap", "message": name + " 需复核内含包装/缝线/裁剪损失与外置项目的边界，并填写 overlap_review"})
                contribute(sid, name, downstream, "kg", factor, {"type": "process"})
        elif mode == "inventory":
            if stage.get("factor_id"):
                errors.append(name + " 投入清单模式不能同时选择整项工序因子")
            inventory = stage.get("inventory", [])
            if not inventory or stage.get("inventory_complete") is not True:
                missing.append({"id": sid + "/inventory", "message": name + " 投入清单尚未确认完整"})
            for index, item in enumerate(inventory):
                label = name + " / " + item.get("name", "投入 " + str(index + 1))
                inv_factor = resolve(item.get("factor_id"), label)
                try:
                    if item.get("quantity") in {None, ""}:
                        missing.append({"id": sid + "/input/" + str(index) + "/quantity", "message": label + " 缺每 kg 产出活动量"})
                        continue
                    per_kg = number(item.get("quantity"), label + " 每 kg 产出活动量")
                    q = None if downstream is None else per_kg * downstream
                    contribute(sid + "/input/" + str(index), label, q, item.get("unit", ""), inv_factor,
                               {"type": "inventory", "per_kg_output": ds(per_kg), "stage": sid})
                except ValueError as exc:
                    errors.append(str(exc))
        else:
            errors.append(name + " 核算模式不受支持")
        ratio = None
        rule = stage.get("ratio_mode", "factor")
        try:
            if rule == "factor":
                ratio_raw = factor.get("input_ratio") if factor else None
                if ratio_raw is not None:
                    ratio = number(ratio_raw, name + " 投入产出比", minimum=Decimal(1))
                else:
                    missing.append({"id": sid + "/ratio", "message": name + " 缺投入产出比，不能反推更上游用量"})
            elif rule in {"ratio", "loss"}:
                if not str(stage.get("ratio_note", "")).strip():
                    errors.append(name + " 手动投入比/损耗率需填写依据或假设")
                if rule == "ratio":
                    ratio = number(stage.get("input_ratio"), name + " 投入产出比", minimum=Decimal(1))
                else:
                    loss = number(stage.get("loss_percent"), name + " 损耗率") / 100
                    if loss >= 1:
                        raise ValueError(name + " 损耗率必须小于 100%")
                    ratio = Decimal(1) / (Decimal(1) - loss)
            else:
                errors.append(name + " 投入比模式不受支持")
        except ValueError as exc:
            errors.append(str(exc))
        input_mass = downstream * ratio if downstream is not None and ratio is not None else None
        waste = input_mass - downstream if input_mass is not None else None
        stages_reversed.append({"id": sid, "name": name, "output_kg": ds(downstream), "input_kg": ds(input_mass),
                                "input_ratio": ds(ratio), "loss_fraction_of_input": ds(1 - 1 / ratio) if ratio else None,
                                "waste_kg": ds(waste), "ratio_rule": rule,
                                "ratio_note": stage.get("ratio_note"), "mode": mode})
        downstream = input_mass
    quantities = list(reversed(stages_reversed))
    if model.get("include_materials") is True:
        materials = model.get("materials", [])
        if not materials:
            errors.append("含原料边界需要材料配比")
        shares = Decimal(0)
        for index, material in enumerate(materials):
            label = "原料 / " + material.get("name", "材料 " + str(index + 1))
            try:
                share = number(material.get("share_percent"), label + " 占比")
                shares += share
                factor = resolve(material.get("factor_id"), label, "material")
                contribute("material/" + str(index), label, None if downstream is None else downstream * share / 100,
                           "kg", factor, {"type": "material"})
            except ValueError as exc:
                errors.append(str(exc))
        if shares != 100:
            errors.append("材料占比之和必须等于 100%")
    waste_masses = [Decimal(q["waste_kg"]) for q in quantities if q["waste_kg"] is not None]
    total_waste = sum(waste_masses, Decimal(0))
    if any(q["waste_kg"] is None for q in quantities):
        missing.append({"id": "waste/quantity", "message": "部分损失材料数量未知"})
    if total_waste > 0:
        waste_factor = resolve(model.get("waste_factor_id"), "损失材料处理")
        contribute("waste", "损失材料处理（统一路线）", total_waste, "kg", waste_factor, {"type": "waste"})
        warnings.append("各环节损失材料采用同一处理路线；不同废料需拆到独立项目并调整边界，避免重复。")
    for index, item in enumerate(model.get("additional_items", [])):
        name = item.get("name", "独立项目 " + str(index + 1))
        if str(item.get("excluded_reason", "")).strip():
            warnings.append(name + " 明确排除：" + item["excluded_reason"])
            continue
        factor = resolve(item.get("factor_id"), name)
        try:
            q = number(item.get("quantity"), name + " 数量")
            contribute(item.get("id", "extra/" + str(index)), name, q, item.get("unit", ""), factor, {"type": "additional"})
        except ValueError as exc:
            if item.get("quantity") in {None, ""}:
                missing.append({"id": "extra/" + str(index) + "/quantity", "message": name + " 缺活动量"})
            else:
                errors.append(str(exc))
    if not contributions:
        missing.append({"id": "no-contribution", "message": "尚无可计算项目"})
    subtotal = sum((Decimal(c["ghg"]) for c in contributions), Decimal(0))
    complete = not errors and not missing
    return {"schema_version": 1, "app_version": "0.1.0", "valid": not errors, "complete": complete,
            "status": "invalid" if errors else "complete" if complete else "partial",
            "label": "输入需要修正" if errors else "所声明边界的完整估算" if complete else "已覆盖部分排放",
            "name": model.get("name"), "boundary": model.get("boundary"),
            "unit": "kg CO₂e/件" if model.get("result_basis") == "item" else "kg CO₂e/批次",
            "subtotal_ghg": None if errors or not contributions else ds(subtotal), "total_ghg": ds(subtotal) if complete else None,
            "contributions": contributions, "chain_quantities": quantities,
            "initial_input_kg": ds(downstream), "total_waste_kg": ds(total_waste),
            "missing": missing, "errors": errors, "warnings": sorted(set(warnings)),
            "catalog_digest": catalog["catalog_digest"], "attribution": ATTRIBUTION,
            "model_sha256": hashlib.sha256(json.dumps(model, sort_keys=True, ensure_ascii=False,
                                                     separators=(",", ":")).encode()).hexdigest()}


def compare(model, baseline, catalog):
    current, original = calculate(model, catalog), calculate(baseline, catalog)
    # 因子变化可作为比较对象；边界、数量基准、必需范围及缺项集合需一致。
    signature_keys = ("boundary", "result_basis", "include_materials", "required_stages")
    exclusions = lambda m: [(i.get("id"), i.get("excluded_reason", "")) for i in m.get("additional_items", [])]
    comparable = (current["valid"] and original["valid"] and current["subtotal_ghg"] is not None and original["subtotal_ghg"] is not None and
                  all(model.get(k) == baseline.get(k) for k in signature_keys) and
                  exclusions(model) == exclusions(baseline) and
                  {i["id"] for i in current["missing"]} == {i["id"] for i in original["missing"]})
    delta = (Decimal(current["subtotal_ghg"]) - Decimal(original["subtotal_ghg"])) if comparable else None
    return {"current": current, "baseline": original, "comparable": comparable,
            "delta_ghg": ds(delta), "note": "同边界、同结果口径及同缺项集合的已覆盖小计比较；负值表示下降。"
            if comparable else "边界、必需范围、结果口径、缺项或排除项不同，不能给出同口径减排结论。"}


def export_model(model, catalog):
    result = calculate(model, catalog)
    selected = {c["factor_id"] for c in result["contributions"]}
    for stage in model.get("chain", []):
        if stage.get("factor_id"):
            selected.add(stage["factor_id"])
    return {"format": "carbonfact-zh-model", "schema_version": 1, "model": model, "result": result,
            "selected_source_records": [f for f in catalog["factors"] if f["id"] in selected],
            "attribution": ATTRIBUTION}
