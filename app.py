"""本地中文页面；仅监听 127.0.0.1。Python 3.10+，无第三方依赖。"""

import argparse
import json
import mimetypes
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse, parse_qs
import hashlib

from carbonfact_app.catalog import ROOT, load_catalog, validate_catalog
from carbonfact_app.engine import calculate, compare, export_model
from carbonfact_app.templates import templates
from carbonfact_app import __version__
from carbonfact_app.learning import learning_content, demo_snapshot, demo_export


def make_handler(catalog):
    class Handler(BaseHTTPRequestHandler):
        server_version = "CarbonfactZH/0.2"

        def reply(self, status, data, mime="application/json; charset=utf-8"):
            content = json.dumps(data, ensure_ascii=False).encode() if isinstance(data, (dict, list)) else data
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self):
            path = unquote(urlparse(self.path).path)
            if path == "/api/catalog":
                return self.reply(200, catalog)
            if path == "/api/templates":
                return self.reply(200, templates(catalog))
            if path == "/api/health":
                return self.reply(200, {"ok": True, "version": __version__, "catalog_digest": catalog["catalog_digest"]})
            if path == "/api/learning":
                return self.reply(200, learning_content(catalog))
            if path == "/api/document":
                rel = parse_qs(urlparse(self.path).query).get("path", [""])[0]
                file = (ROOT / rel).resolve()
                permitted = [ROOT / "upstream/carbonfact", ROOT / "docs", ROOT / "data/processed"]
                if (not any(file.is_relative_to(p.resolve()) for p in permitted) or
                        file.suffix.lower() != ".md" or not file.is_file()):
                    return self.reply(404, {"error": "此资料不可在阅读页打开"})
                content = file.read_bytes()
                return self.reply(200, {"path": file.relative_to(ROOT).as_posix(),
                                        "text": content.decode("utf-8-sig"), "sha256": hashlib.sha256(content).hexdigest()})
            if path == "/":
                file = ROOT / "web/index.html"
            elif path in {"/demo", "/demo/"}:
                file = ROOT / "web/demo.html"
            elif path == "/reader":
                file = ROOT / "web/reader.html"
            elif path in {"/app.js", "/styles.css", "/learning.js", "/demo.js", "/reader.js", "/learning.css"}:
                file = ROOT / "web" / path[1:]
            elif path.startswith("/evidence/"):
                rel = path.removeprefix("/evidence/")
                file = (ROOT / rel).resolve()
                permitted = [ROOT / "upstream/carbonfact", ROOT / "docs", ROOT / "data/processed"]
                if not any(file.is_relative_to(p.resolve()) for p in permitted) or file.suffix.lower() not in {".md", ".pdf", ".csv", ".json", ".cff"}:
                    return self.reply(404, {"error": "证据路径不可读取"})
            else:
                return self.reply(404, {"error": "路径不存在"})
            if not file.is_file():
                return self.reply(404, {"error": "文件不存在"})
            mime = mimetypes.guess_type(file.name)[0] or "text/plain"
            if mime.startswith("text/") or file.suffix in {".md", ".cff", ".json"}:
                mime += "; charset=utf-8"
            return self.reply(200, file.read_bytes(), mime)

        def do_POST(self):
            path = urlparse(self.path).path
            origin = self.headers.get("Origin")
            if origin and origin != "http://" + self.headers.get("Host", ""):
                return self.reply(403, {"error": "请求来源不匹配"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 2_000_000:
                    raise ValueError("请求为空或超过 2 MB")
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("请求应为 JSON 对象")
                if path == "/api/calculate":
                    result = calculate(payload["model"], catalog)
                elif path == "/api/compare":
                    result = compare(payload["model"], payload["baseline"], catalog)
                elif path == "/api/export":
                    result = export_model(payload["model"], catalog)
                elif path == "/api/demo/calculate":
                    result = demo_snapshot(payload.get("state", {}), catalog)
                elif path == "/api/demo/export":
                    result = demo_export(payload.get("state", {}), catalog)
                else:
                    return self.reply(404, {"error": "接口不存在"})
                return self.reply(200, result)
            except (ValueError, KeyError, TypeError, AttributeError) as exc:
                return self.reply(400, {"error": "请求格式有误：" + str(exc)})

        def log_message(self, fmt, *args):
            print("本地请求：" + (fmt % args))

    return Handler


def main():
    parser = argparse.ArgumentParser(description="启动 Carbonfact 中文本地应用")
    parser.add_argument("--port", type=int, default=8768, help="默认 8768")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()
    catalog = load_catalog()
    errors = validate_catalog(catalog)
    if errors:
        raise SystemExit("数据校验未通过：\n" + "\n".join(errors))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(catalog))
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"Carbonfact 中文应用 v{__version__}：{url}\n独立演示：{url}/demo\n按 Ctrl+C 停止。")
    if not args.no_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止。")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
