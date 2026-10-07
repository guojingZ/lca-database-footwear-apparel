"""独立合成夹具检验业务规则；测试数值不是 Carbonfact 因子。"""

import copy
import unittest
from decimal import Decimal

from carbonfact_app.catalog import load_catalog
from carbonfact_app.engine import calculate, compare, convert, export_model
from carbonfact_app.templates import templates


def synthetic_model(catalog):
    def factor(fid, value, kind="process", unit="kg"):
        return {"id": fid, "name": "测试用合成因子", "ghg": str(value), "kind": kind, "unit": unit,
                "source": "单元测试手算夹具，不能用于实际核算", "scope": "仅用于程序校验", "status": "reviewed"}
    return {"schema_version": 1, "catalog_digest": catalog["catalog_digest"], "name": "测试夹具",
            "boundary": "测试材料、两段工序、损失处理", "boundary_reviewed": True, "result_basis": "item",
            "weight_g": "1000", "include_materials": True,
            "materials": [{"name": "测试原料", "share_percent": "100", "factor_id": "ext-material"}],
            "chain": [{"id": "a", "name": "前工序", "mode": "factor", "factor_id": "ext-a",
                       "ratio_mode": "ratio", "input_ratio": "1.1", "ratio_note": "测试夹具"},
                      {"id": "b", "name": "后工序", "mode": "factor", "factor_id": "ext-b",
                       "ratio_mode": "ratio", "input_ratio": "1.25", "ratio_note": "测试夹具"}],
            "required_stages": [{"id": "a", "name": "前工序"}, {"id": "b", "name": "后工序"}],
            "external_factors": [factor("ext-a", 2), factor("ext-b", 3), factor("ext-material", 5, "material"), factor("ext-waste", 1)],
            "waste_factor_id": "ext-waste", "additional_items": []}


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog()

    def setUp(self):
        self.model = synthetic_model(self.catalog)

    def test_hand_calculated_chain_and_material_balance(self):
        r = calculate(self.model, self.catalog)
        self.assertTrue(r["complete"])
        self.assertEqual(Decimal(r["total_ghg"]), Decimal("12.75"))
        self.assertEqual(Decimal(r["initial_input_kg"]), Decimal("1.375"))
        self.assertEqual(Decimal(r["total_waste_kg"]), Decimal("0.375"))
        self.assertEqual([Decimal(q["output_kg"]) for q in r["chain_quantities"]], [Decimal("1.25"), Decimal(1)])
        self.assertEqual(sum(Decimal(c["ghg"]) for c in r["contributions"]), Decimal(r["subtotal_ghg"]))

    def test_loss_percent_equals_ratio(self):
        expected = calculate(self.model, self.catalog)
        self.model["chain"][1].update(ratio_mode="loss", loss_percent="20")
        r = calculate(self.model, self.catalog)
        self.assertEqual(r["subtotal_ghg"], expected["subtotal_ghg"])

    def test_unknown_is_partial_and_never_complete_total(self):
        self.model["materials"][0]["factor_id"] = None
        r = calculate(self.model, self.catalog)
        self.assertTrue(r["valid"])
        self.assertFalse(r["complete"])
        self.assertIsNone(r["total_ghg"])
        self.assertEqual(Decimal(r["subtotal_ghg"]), Decimal("5.875"))
        self.assertTrue(any("原料" in m["message"] for m in r["missing"]))

    def test_unknown_ratio_stops_upstream_quantities(self):
        self.model["chain"][1]["ratio_mode"] = "factor"
        r = calculate(self.model, self.catalog)
        self.assertIsNone(r["initial_input_kg"])
        self.assertIsNone(r["chain_quantities"][0]["output_kg"])
        self.assertEqual(Decimal(r["subtotal_ghg"]), Decimal(3))
        self.assertFalse(r["complete"])

    def test_missing_waste_is_a_real_gap(self):
        self.model["waste_factor_id"] = None
        r = calculate(self.model, self.catalog)
        self.assertFalse(r["complete"])
        self.assertTrue(any(m["id"] == "损失材料处理" for m in r["missing"]))

    def test_removed_required_stage_is_not_silently_complete(self):
        self.model["chain"].pop(0)
        r = calculate(self.model, self.catalog)
        self.assertTrue(any(m["id"] == "stage/a" for m in r["missing"]))

    def test_duplicate_factor_requires_repeat_reason(self):
        self.model["chain"][1]["factor_id"] = "ext-a"
        self.assertFalse(calculate(self.model, self.catalog)["valid"])
        self.model["chain"][1]["repeat_reason"] = "第二次加工，独立活动量"
        self.assertTrue(calculate(self.model, self.catalog)["valid"])

    def test_wrong_unit_blocks_published_subtotal(self):
        self.model["external_factors"][0]["unit"] = "m2"
        r = calculate(self.model, self.catalog)
        self.assertFalse(r["valid"])
        self.assertIsNone(r["subtotal_ghg"])

    def test_zero_is_allowed_only_as_an_explicit_factor_value(self):
        for f in self.model["external_factors"]:
            f["ghg"] = "0"
        r = calculate(self.model, self.catalog)
        self.assertTrue(r["complete"])
        self.assertEqual(Decimal(r["total_ghg"]), Decimal(0))

    def test_bad_shares_bad_loss_nan_and_missing_source(self):
        cases = [lambda m: m["materials"][0].update(share_percent="99"),
                 lambda m: m["chain"][1].update(ratio_mode="loss", loss_percent="100"),
                 lambda m: m.update(weight_g="NaN"),
                 lambda m: m["external_factors"][0].update(source="")]
        for change in cases:
            with self.subTest(change=change):
                m = copy.deepcopy(self.model)
                change(m)
                self.assertFalse(calculate(m, self.catalog)["valid"])

    def test_pending_and_hypothetical_factor_keep_partial_status(self):
        for status in ("pending", "hypothetical"):
            self.model["external_factors"][0]["status"] = status
            self.assertFalse(calculate(self.model, self.catalog)["complete"])

    def test_inventory_and_factor_paths_are_mutually_exclusive(self):
        m = templates(self.catalog)["inventory"]
        m["boundary_reviewed"] = True
        m["chain"][0].update(inventory_complete=True, ratio_note="实测不损失质量")
        m["external_factors"] = [{"id": "ext-power", "name": "测试电", "ghg": "0.5", "unit": "kWh",
                                  "kind": "process", "scope": "仅测试", "source": "合成夹具", "status": "reviewed"}]
        m["weight_g"] = "2000"
        m["chain"][0]["inventory"] = [{"name": "电", "quantity": "3", "unit": "kWh", "factor_id": "ext-power"}]
        r = calculate(m, self.catalog)
        self.assertEqual(Decimal(r["total_ghg"]), Decimal(3))
        self.assertEqual(Decimal(r["contributions"][0]["quantity"]), Decimal(6))
        m["chain"][0]["factor_id"] = self.catalog["factors"][0]["id"]
        self.assertFalse(calculate(m, self.catalog)["valid"])

    def test_empty_inventory_has_no_false_zero_subtotal(self):
        r = calculate(templates(self.catalog)["inventory"], self.catalog)
        self.assertTrue(r["valid"])
        self.assertIsNone(r["subtotal_ghg"])
        self.assertFalse(r["complete"])

    def test_compare_coverage_and_boundary(self):
        new = copy.deepcopy(self.model)
        new["weight_g"] = "2000"
        r = compare(new, self.model, self.catalog)
        self.assertTrue(r["comparable"])
        self.assertEqual(Decimal(r["delta_ghg"]), Decimal("12.75"))
        new["boundary"] = "另一边界"
        self.assertFalse(compare(new, self.model, self.catalog)["comparable"])
        new = copy.deepcopy(self.model)
        new["materials"][0]["factor_id"] = None
        self.assertFalse(compare(new, self.model, self.catalog)["comparable"])

    def test_save_reload_and_catalog_change(self):
        packet = export_model(self.model, self.catalog)
        self.assertEqual(calculate(packet["model"], self.catalog), packet["result"])
        self.assertEqual(calculate(self.model, self.catalog), calculate(self.model, self.catalog))
        self.model["catalog_digest"] = "older"
        self.assertFalse(calculate(self.model, self.catalog)["valid"])

    def test_only_explicit_supported_unit_conversion(self):
        self.assertEqual(convert(Decimal(1000), "g", "kg"), Decimal(1))
        self.assertEqual(convert(Decimal(1000), "L", "m3"), Decimal(1))
        with self.assertRaises(ValueError):
            convert(Decimal(1), "m2", "kg")

    def test_real_templates_and_mixed_unit_catalog(self):
        for name, m in templates(self.catalog).items():
            with self.subTest(name=name):
                r = calculate(m, self.catalog)
                self.assertTrue(r["valid"], r["errors"])
                self.assertFalse(r["complete"])
        shoe = next(f for f in self.catalog["factors"] if f["unit"] == "pair")
        self.model["additional_items"] = [{"id": "shoe", "name": "测试每双计量", "quantity": "2", "unit": "pair", "factor_id": shoe["id"]}]
        r = calculate(self.model, self.catalog)
        c = next(c for c in r["contributions"] if c["id"] == "shoe")
        self.assertEqual(Decimal(c["ghg"]), Decimal(shoe["impacts"]["GHG"]) * 2)

    def test_malformed_lists_return_a_clear_validation_error(self):
        self.model["chain"] = [1]
        with self.assertRaisesRegex(ValueError, "chain"):
            calculate(self.model, self.catalog)

    def test_real_assembly_and_drying_need_overlap_evidence(self):
        m = templates(self.catalog)["tshirt"]
        self.assertTrue(any(v["id"] == "assembly/overlap" for v in calculate(m, self.catalog)["missing"]))
        m["chain"][-1]["overlap_review"] = "测试已查证内含项；本说明不批准实际产品"
        self.assertFalse(any(v["id"] == "assembly/overlap" for v in calculate(m, self.catalog)["missing"]))
        m = templates(self.catalog)["factory"]
        drying = next(f for f in self.catalog["factors"] if "/CAN_DRY" in f["descriptor"])
        m["chain"].append({"id": "dry", "name": "额外干燥", "mode": "factor", "factor_id": drying["id"], "ratio_mode": "factor"})
        self.assertTrue(any(v["id"] == "dry/overlap" for v in calculate(m, self.catalog)["missing"]))


if __name__ == "__main__":
    unittest.main()
