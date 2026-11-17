"""Local development server: standard library only, loopback binding, SQLite persistence."""
import argparse
import csv
import io
import json
import mimetypes
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from backend.service import Store
from backend.scenario import research_demo

ROOT = Path(__file__).resolve().parent


def handler(store):
    class Handler(BaseHTTPRequestHandler):
        def origin_allowed(self):
            origin = self.headers.get("Origin")
            port = self.server.server_port
            return origin in (None, "", f"http://127.0.0.1:{port}", f"http://localhost:{port}")

        def send(self, data, status=200, content_type="application/json; charset=utf-8"):
            body = json.dumps(data,ensure_ascii=False,allow_nan=False).encode() if isinstance(data,(dict,list)) else data
            self.send_response(status)
            self.send_header("Content-Type",content_type)
            self.send_header("Content-Length",str(len(body)))
            self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("X-Frame-Options","DENY")
            self.send_header("Content-Security-Policy","default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers(); self.wfile.write(body)

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/api/state":
                with store.lock:
                    return self.send(store.read())
            if path == "/api/health":
                return self.send({"ok":True,"version":"0.2.0"})
            if path.startswith('/public-benchmarks/'):
                name=path.removeprefix('/public-benchmarks/')
                allowed={'report.html','runs.csv','instances.csv','summary.json','protocol.json','feasibility.png','feasibility.svg','feasibility.pdf','hardware.json','integrity-audit.json','tdsp-consistency-witness.json'}
                if name not in allowed:
                    return self.send({'error':'实验文件不存在'},404)
                f=ROOT/'data/public-benchmarks/results/native-v1'/name
                if not f.is_file():
                    return self.send({'error':'公开基准报告尚未生成'},404)
                return self.send(f.read_bytes(),content_type=(mimetypes.guess_type(str(f))[0] or 'application/octet-stream')+'; charset=utf-8')
            if path == "/api/template":
                return self.send(research_demo())
            if path == '/api/history-template':
                from backend.prediction import synthetic_history
                return self.send({'source':'synthetic','rows':synthetic_history(300)})
            if path == "/api/export":
                with store.lock:
                    return self.send(store.read())
            files = {"/":"index.html","/style.css":"style.css","/app.js":"app.js","/research.js":"research.js"}
            if path not in files:
                return self.send({"error":"页面不存在"},404)
            f = ROOT / "web" / files[path]
            return self.send(f.read_bytes(),content_type=(mimetypes.guess_type(str(f))[0] or "application/octet-stream")+"; charset=utf-8")

        def do_POST(self):
            if not self.origin_allowed():
                return self.send({"error":"不接受跨站请求"},403)
            if self.headers.get("Content-Type","").split(";")[0] != "application/json":
                return self.send({"error":"必须使用 application/json"},415)
            try:
                length = int(self.headers.get("Content-Length","0"))
                if not 0 < length <= 2_000_000:
                    return self.send({"error":"请求大小须小于2MB"},413)
                body = json.loads(self.rfile.read(length))
                if not isinstance(body,dict):
                    raise ValueError("请求必须为对象")
                if not self.path.startswith("/api/") or "/" in self.path[5:]:
                    return self.send({"error":"接口不存在"},404)
                return self.send(store.action(self.path[5:],body))
            except (ValueError, KeyError, TypeError) as e:
                return self.send({"error":str(e)},400)
            except Exception:
                traceback.print_exc()
                return self.send({"error":"服务内部异常，详见服务器终端日志"},500)

        def log_message(self, format, *args):
            if len(args)>1 and str(args[1]) not in ("200","304"):
                super().log_message(format,*args)
    return Handler


if __name__ == "__main__":
    # Fail before opening the page if compiled solver dependencies do not match Python.
    try:
        import numpy  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "调度依赖与当前 Python 不兼容。请双击 start.cmd，"
            "使用项目配套的 Python 3.12 启动服务。"
        ) from exc
    parser = argparse.ArgumentParser(description="环卫智枢本地开发服务")
    parser.add_argument("--port",type=int,default=8766)
    parser.add_argument("--db",default=str(ROOT/"data"/"dispatch.sqlite3"))
    args = parser.parse_args()
    app = ThreadingHTTPServer(("127.0.0.1",args.port),handler(Store(args.db)))
    print(f"环卫智枢已启动：http://127.0.0.1:{args.port}  | Ctrl+C 停止",flush=True)
    try:
        app.serve_forever()
    except KeyboardInterrupt:
        app.server_close()
