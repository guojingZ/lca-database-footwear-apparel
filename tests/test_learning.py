"""教学流程的数值、隔离、导出、资料路径与错误恢复检查。"""

import json
from copy import deepcopy
from decimal import Decimal
import unittest
from urllib.error import HTTPError

from carbonfact_app.catalog import load_catalog, ROOT
from carbonfact_app.engine import calculate
from carbonfact_app.learning import learning_content, demo_snapshot, demo_export
from carbonfact_app.templates import templates
import test_api as api_fixture


class LearningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog()

    def test_learning_links_and_actual_baseline(self):
        content = learning_content(self.catalog)
        self.assertEqual(len(content["concepts"]), 12)
        for item in content["concepts"] + content["lessons"]:
            self.assertTrue((ROOT / item["document"]).is_file())
        self.assertEqual(content["case"]["result"], calculate(content["case"]["model"], self.catalog))
        self.assertEqual(content["case"]["result"]["status"], "partial")

    def test_four_scenarios_match_existing_engine(self):
        expected = {"baseline": "1.7587612014455535026925731984", "weight_double": "3.5175224028911070053851463968",
                    "shares_80_20": "1.7587612014455535026925731984", "loss_20": "1.91089435340002603315667000"}
        for scenario, value in expected.items():
            with self.subTest(scenario=scenario):
                s = demo_snapshot({"scenario": scenario}, self.catalog)
                self.assertEqual(Decimal(s["result"]["subtotal_ghg"]), Decimal(value))
                self.assertEqual(s["result"], calculate(s["model"], self.catalog))
                self.assertFalse(s["result"]["complete"])
        q = demo_snapshot({"scenario": "loss_20"}, self.catalog)["result"]["chain_quantities"][-1]
        self.assertEqual(q["input_kg"], "0.1750")
        self.assertEqual(q["input_ratio"], "1.25")

    def test_changes_are_isolated_from_templates_and_catalog(self):
        previous = deepcopy(self.catalog)
        model = templates(self.catalog)["tshirt"]
        for _ in range(2):
            demo_snapshot({"weight_g": "280", "organic_share": "80", "recycled_share": "20", "scenario": "loss_20"}, self.catalog)
        self.assertEqual(templates(self.catalog)["tshirt"], model)
        self.assertEqual(self.catalog, previous)

    def test_invalid_share_can_be_corrected_and_not_exported(self):
        bad = {"organic_share": "70", "recycled_share": "40"}
        self.assertFalse(demo_snapshot(bad, self.catalog)["result"]["valid"])
        with self.assertRaisesRegex(ValueError, "输入需要修正"):
            demo_export(bad, self.catalog)
        self.assertTrue(demo_snapshot({"organic_share": "70", "recycled_share": "30"}, self.catalog)["result"]["valid"])

    def test_missing_selection_stays_missing_not_zero(self):
        result = demo_snapshot({"dyeing_selected": False}, self.catalog)["result"]
        self.assertTrue(result["valid"])
        self.assertFalse(result["complete"])
        self.assertTrue(any("活性染色" in item["message"] for item in result["missing"]))
        self.assertFalse(any(item["id"] == "dyeing" for item in result["contributions"]))

    def test_unknown_scenario_digest_and_malformed_state_are_rejected(self):
        for state in [[], {"scenario": "not-supported"}, {"catalog_digest": "old"}, {"weight_g": {}},
                      {"dyeing_selected": "yes"}, {"review_status": "approved_public_database"}]:
            with self.subTest(state=state):
                with self.assertRaises(ValueError):
                    demo_snapshot(state, self.catalog)

    def test_export_can_reload_in_existing_engine_and_feedback_does_not_approve(self):
        state = {"scenario": "loss_20", "review_note": "教学意见：需取得企业称重依据", "review_status": "accepted"}
        exported = demo_export(state, self.catalog)
        packet = json.loads(json.dumps(exported["packet"]))
        self.assertEqual(calculate(packet["model"], self.catalog), packet["result"])
        self.assertEqual(packet["format"], "carbonfact-zh-model")
        self.assertEqual(packet["demo_state"]["review_note"], state["review_note"])
        self.assertEqual(packet["result"]["status"], "partial")
        self.assertGreater(len(packet["selected_source_records"]), 0)
        for text in ["仅用于教学", "尚未覆盖", "公开来源", "逻辑记录", "演示采纳"]:
            self.assertIn(text, exported["markdown"])


class LearningApiTests(unittest.TestCase):
    # 复用现有 HTTP fixture，而不重复执行其测试方法。
    setUpClass = classmethod(api_fixture.ApiTests.setUpClass.__func__)
    tearDownClass = classmethod(api_fixture.ApiTests.tearDownClass.__func__)
    request = api_fixture.ApiTests.request

    def test_learning_demo_and_reader_routes(self):
        with self.request("/api/health") as response:
            self.assertEqual(json.load(response)["version"], "0.2.0")
        for path, expected in [("/demo", "独立教学演示"), ("/reader", "资料阅读"), ("/learning.js", "CFLearning"), ("/demo.js", "carbonfact.demo.v1")]:
            with self.request(path) as response:
                self.assertIn(expected, response.read().decode())
        with self.request("/api/learning") as response:
            self.assertEqual(len(json.load(response)["concepts"]), 12)
        with self.request("/api/demo/calculate", {"state": {"scenario": "weight_double"}}) as response:
            self.assertEqual(json.load(response)["model"]["weight_g"], "280")
        with self.request("/api/demo/export", {"state": {}}) as response:
            self.assertEqual(json.load(response)["packet"]["result"]["status"], "partial")

    def test_document_only_exposes_allowed_markdown(self):
        with self.request("/api/document?path=docs/%E4%B8%AD%E6%96%87%E5%85%A5%E9%97%A8.md") as response:
            document = json.load(response)
            self.assertEqual(len(document["sha256"]), 64)
            self.assertIn("工序", document["text"])
        for path in ["app.py", "../app.py", "data/source_manifest.json", "upstream/carbonfact/datasets/dyeing/impact-scores.csv"]:
            with self.subTest(path=path):
                with self.assertRaises(HTTPError) as caught:
                    self.request("/api/document?path=" + path)
                self.assertEqual(caught.exception.code, 404)

    def test_bad_demo_request_and_failure_retry(self):
        with self.assertRaises(HTTPError) as caught:
            self.request("/api/demo/calculate", {"state": {"catalog_digest": "old"}})
        self.assertEqual(caught.exception.code, 400)
        with self.request("/api/demo/calculate", {"state": {"weight_g": "140"}}) as response:
            self.assertTrue(json.load(response)["result"]["valid"])


if __name__ == "__main__":
    unittest.main()
