"""实际本地 HTTP 接口、导出和证据路径测试。"""

import json
import threading
import unittest
import urllib.error
import urllib.request

from app import ThreadingHTTPServer, make_handler
from carbonfact_app.catalog import load_catalog
from carbonfact_app.engine import calculate
from carbonfact_app.templates import templates


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.catalog))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = "http://127.0.0.1:" + str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def request(self, path, payload=None, origin=None):
        headers = {"Content-Type": "application/json"}
        if origin:
            headers["Origin"] = origin
        request = urllib.request.Request(self.url + path, data=json.dumps(payload).encode() if payload else None, headers=headers)
        return urllib.request.urlopen(request, timeout=10)

    def test_page_and_catalog(self):
        with self.request("/") as response:
            self.assertIn("中文工序工作台", response.read().decode())
        with self.request("/api/catalog") as response:
            self.assertEqual(len(json.load(response)["factors"]), 304)

    def test_web_and_python_calculation_and_export_are_identical(self):
        m = templates(self.catalog)["factory"]
        with self.request("/api/calculate", {"model": m}) as response:
            self.assertEqual(json.load(response), calculate(m, self.catalog))
        with self.request("/api/export", {"model": m}) as response:
            packet = json.load(response)
        self.assertEqual(calculate(packet["model"], self.catalog), packet["result"])
        self.assertGreater(len(packet["selected_source_records"]), 0)
        self.assertEqual(packet["attribution"]["license"], "CC BY-SA 4.0")

    def test_evidence_and_protected_paths(self):
        with self.request("/evidence/upstream/carbonfact/datasets/dyeing/impact-scores.csv") as response:
            self.assertEqual(response.status, 200)
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request("/evidence/../../app.py")
        self.assertEqual(caught.exception.code, 404)

    def test_bad_request_and_origin(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request("/api/calculate", {"model": {"chain": [1]}})
        self.assertEqual(caught.exception.code, 400)
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request("/api/calculate", {"model": templates(self.catalog)["factory"]}, "http://other.example")
        self.assertEqual(caught.exception.code, 403)


if __name__ == "__main__":
    unittest.main()
