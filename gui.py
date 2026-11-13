#!/usr/bin/env python3
"""
Local web GUI for niz68. Serves a single page on 127.0.0.1 and talks to the
keyboard through the same code paths as the CLI (niz68.py).

Security: binds to loopback only, and every API call must carry a random
per-launch token, so other web pages open in the browser cannot reach it.
"""
import argparse
import glob
import json
import os
import secrets
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import niz68 as core  # noqa: E402

TOKEN = secrets.token_urlsafe(16)
DEV_LOCK = threading.Lock()

CATEGORIES = [
    ("字母", list(range(29, 39)) + list(range(43, 52)) + list(range(56, 63))),
    ("數字與符號", list(range(14, 27)) + [39, 40, 41, 52, 53, 63, 64, 65, 204]),
    ("F 鍵", list(range(2, 14))),
    ("修飾鍵", [55, 66, 67, 68, 69, 71, 72, 74, 73]),
    ("編輯與導航", [1, 27, 28, 42, 54, 70, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90]),
    ("數字鍵盤", list(range(91, 108))),
    ("多媒體", list(range(108, 126))),
    ("滑鼠", list(range(126, 135)) + [157, 158, 173, 199]),
    ("Fn 與鍵盤功能", [156, 166, 155, 152, 153, 150, 151, 154, 167, 168, 169, 170, 171, 172,
                    149, 159, 174, 175, 176, 177, 75, 76, 77]),
    ("背光", list(range(135, 149)) + list(range(160, 166))),
]


def slot_json(s):
    return {"type": s.type, "codes": s.normal_codes() if s.type == 0 else [],
            "desc": s.describe(), "typeName": core.TYPE_NAMES.get(s.type, str(s.type))}


def device_call(fn):
    with DEV_LOCK:
        k = core.NiZ()
        k.open()
        try:
            return fn(k)
        finally:
            k.close()


def api_status(_):
    try:
        cfg, macmode = core.find_devices()
    except core.DeviceError as e:
        return {"ok": False, "state": "nohid", "message": str(e)}
    if core.pick_config_interface(cfg):
        try:
            ver = device_call(lambda k: k.version())
            return {"ok": True, "state": "ready", "version": ver}
        except core.DeviceError as e:
            return {"ok": False, "state": "error", "message": str(e)}
    if macmode:
        return {"ok": False, "state": "macmode"}
    return {"ok": False, "state": "none"}


def api_read(_):
    def go(k):
        ver = k.version()
        slots = k.read_all()
        counts = None
        try:
            counts = k.read_counter()
        except core.DeviceError:
            pass
        return ver, slots, counts
    ver, slots, counts = device_call(go)
    # Only keep a new backup when the keymap differs from the latest one.
    latest = sorted(glob.glob(os.path.join(core.BACKUP_DIR, "keymap-*.json")))
    same = False
    if latest:
        try:
            _, prev = core.load_backup(latest[-1])
            same = {k: s.packets for k, s in prev.items()} == {k: s.packets for k, s in slots.items()}
        except (OSError, ValueError, SystemExit):
            pass
    path = latest[-1] if same else core.save_backup(slots, ver)
    return {"ok": True, "version": ver, "backup": os.path.basename(path),
            "slots": {f"{l}:{kk}": slot_json(s) for (l, kk), s in slots.items()},
            "counts": counts}


def api_write(body):
    changes = body.get("changes") or []
    if not changes:
        return {"ok": False, "message": "沒有要寫入的修改"}
    parsed = []
    for c in changes:
        l, kk, codes = int(c["layer"]), int(c["key"]), [int(x) for x in c["codes"]]
        if not (1 <= l <= core.LAYERS and 1 <= kk <= core.KEYS_PER_LAYER):
            return {"ok": False, "message": f"鍵位超出範圍: L{l} K{kk}"}
        if len(codes) > 6 or any(not 0 <= x <= 255 for x in codes):
            return {"ok": False, "message": f"按鍵代碼不正確: L{l} K{kk}"}
        parsed.append((l, kk, codes))

    def go(k):
        ver = k.version()
        slots = k.read_all()
        path = core.save_backup(slots, ver)
        for l, kk, codes in parsed:
            slots[(l, kk)] = core.Slot.normal(l, kk, codes)
        k.write_all(slots)
        time.sleep(0.5)
        after = k.read_all()
        bad = [f"L{l}:K{kk}" for (l, kk), s in after.items()
               if (l, kk) not in slots or s.packets != slots[(l, kk)].packets]
        if set(after) != set(slots):
            bad.append("slot-count")
        return path, bad, after
    path, bad, after = device_call(go)
    return {"ok": not bad, "backup": os.path.basename(path), "mismatch": bad[:20],
            "slots": {f"{l}:{kk}": slot_json(s) for (l, kk), s in after.items()}}


def api_backups(_):
    files = sorted(glob.glob(os.path.join(core.BACKUP_DIR, "*.json")), reverse=True)
    out = []
    for f in files[:50]:
        try:
            with open(f) as fh:
                d = json.load(fh)
            out.append({"file": os.path.basename(f), "saved_at": d.get("saved_at"),
                        "version": d.get("version")})
        except (OSError, ValueError):
            pass
    return {"ok": True, "backups": out}


def api_restore(body):
    name = os.path.basename(body.get("file", ""))
    path = os.path.join(core.BACKUP_DIR, name)
    if not name.endswith(".json") or not os.path.isfile(path):
        return {"ok": False, "message": "找不到備份檔"}
    _, slots = core.load_backup(path)

    def go(k):
        ver = k.version()
        cur = k.read_all()
        pre = core.save_backup(cur, ver)
        k.write_all(slots)
        time.sleep(0.5)
        after = k.read_all()
        bad = [f"L{l}:K{kk}" for lk in set(slots) | set(after)
               for (l, kk) in [lk]
               if (slots.get(lk) and slots[lk].packets) != (after.get(lk) and after[lk].packets)]
        return pre, bad, after
    pre, bad, after = device_call(go)
    return {"ok": not bad, "backup": os.path.basename(pre), "mismatch": bad[:20],
            "slots": {f"{l}:{kk}": slot_json(s) for (l, kk), s in after.items()}}


def api_codes(_):
    used = set()
    cats = []
    for name, ids in CATEGORIES:
        items = [{"code": c, "name": core.CODES[c]} for c in ids if c in core.CODES and core.CODES[c]]
        used.update(i["code"] for i in items)
        cats.append({"name": name, "items": items})
    rest = [{"code": c, "name": n} for c, n in sorted(core.CODES.items()) if n and c not in used]
    if rest:
        cats.append({"name": "其他", "items": rest})
    return {"ok": True, "categories": cats}


ROUTES = {
    ("GET", "/api/status"): api_status,
    ("GET", "/api/codes"): api_codes,
    ("GET", "/api/backups"): api_backups,
    ("POST", "/api/read"): api_read,
    ("POST", "/api/write"): api_write,
    ("POST", "/api/restore"): api_restore,
}


class Handler(BaseHTTPRequestHandler):
    server_version = "niz68"

    def log_message(self, fmt, *args):
        if os.environ.get("NIZ68_DEBUG"):
            super().log_message(fmt, *args)

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(data)

    def _host_ok(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    def _handle(self, method):
        if not self._host_ok():
            return self._send(403, {"ok": False, "message": "forbidden"})
        url = urlparse(self.path)
        if method == "GET" and url.path == "/":
            if parse_qs(url.query).get("t", [""])[0] != TOKEN:
                return self._send(403, "請用終端機顯示的網址開啟（含 token）".encode(), "text/plain; charset=utf-8")
            with open(os.path.join(HERE, "gui.html"), "rb") as f:
                html = f.read().replace(b"__TOKEN__", TOKEN.encode())
            return self._send(200, html, "text/html; charset=utf-8")
        fn = ROUTES.get((method, url.path))
        if fn is None:
            return self._send(404, {"ok": False, "message": "not found"})
        if self.headers.get("X-Token") != TOKEN:
            return self._send(403, {"ok": False, "message": "bad token"})
        body = {}
        if method == "POST":
            n = int(self.headers.get("Content-Length") or 0)
            if n:
                try:
                    body = json.loads(self.rfile.read(n))
                except ValueError:
                    return self._send(400, {"ok": False, "message": "bad json"})
        try:
            self._send(200, fn(body))
        except core.DeviceError as e:
            self._send(200, {"ok": False, "message": str(e)})
        except Exception as e:  # keep the server alive, surface the error
            self._send(500, {"ok": False, "message": f"{type(e).__name__}: {e}"})

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")


def install_demo():
    """Replace the HID layer with a simulated 68EC (for trying the UI)."""
    import demo
    core.hid = demo.make_fake_hid()
    core.BACKUP_DIR = os.path.join(HERE, "backups-demo")


def main(argv=None):
    p = argparse.ArgumentParser(prog="niz68 gui")
    p.add_argument("--port", type=int, default=0)
    p.add_argument("--no-browser", action="store_true")
    p.add_argument("--demo", action="store_true", help="用模擬鍵盤試用介面，不會碰到真的鍵盤")
    args = p.parse_args(argv)
    if args.demo:
        install_demo()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{srv.server_address[1]}/?t={TOKEN}"
    print("NIZ 68EC 改鍵工具已啟動" + ("（模擬模式）" if args.demo else ""))
    print("瀏覽器網址:", url, flush=True)
    print("用完關掉這個視窗，或按 Ctrl+C 結束。", flush=True)
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
