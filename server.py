#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
人工智能学院科技部 · 实践平台

一个文件搞定：账号（学号+密码）、名单、每人独立 API Key、
规范手册在线阅读、海报工厂、生图/评审代理。

启动：  python server.py            （默认 7788）
        python server.py 8000
"""

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

ROOT = os.path.dirname(os.path.abspath(__file__))
PUBLIC = os.path.join(ROOT, "public")
DATA = os.path.join(ROOT, "data")
USERS_FILE = os.path.join(DATA, "users.json")
KEYS_FILE = os.path.join(DATA, "keys.json")
SESS_FILE = os.path.join(DATA, "sessions.json")
SECRET_FILE = os.path.join(DATA, "secret.key")

APP_NAME = "人工智能学院科技部实践平台"
SESSION_DAYS = 14
SID_RE = re.compile(r"^\d{10}$")          # 学号：10 位数字

PROVIDERS = {
    "zhipu": {"label": "智谱 GLM", "base": "https://open.bigmodel.cn/api/paas/v4",
              "img": "cogview-3-flash", "vis": "glm-4v-flash",
              "hint": "cogview-3-flash 免费；glm-4v-flash 免费"},
    "siliconflow": {"label": "硅基流动 SiliconFlow", "base": "https://api.siliconflow.cn/v1",
                    "img": "Kwai-Kolors/Kolors", "vis": "Qwen/Qwen2-VL-72B-Instruct",
                    "hint": "注册送额度；图像可用 Kolors/FLUX"},
    "dashscope": {"label": "阿里云百炼 · 通义万相", "base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                  "img": "wanx2.1-t2i-turbo", "vis": "qwen-vl-max",
                  "hint": "需开通百炼"},
    "openai": {"label": "OpenAI", "base": "https://api.openai.com/v1",
               "img": "gpt-image-1", "vis": "gpt-4o-mini",
               "hint": "国内需代理"},
    "custom": {"label": "自定义（OpenAI 兼容）", "base": "", "img": "", "vis": "",
               "hint": "填 /v1 结尾的 baseUrl"},
}

_lock = threading.Lock()


def say(*a):
    """pythonw 无控制台时静默，避免 print 抛异常。"""
    try:
        if sys.stdout:
            print(*a)
    except Exception:
        pass


# ---------------------------------------------------------------- 存储
def ensure_data():
    os.makedirs(DATA, exist_ok=True)
    if not os.path.exists(SECRET_FILE):
        with open(SECRET_FILE, "w", encoding="utf-8") as f:
            f.write(secrets.token_hex(32))
    for p, default in ((USERS_FILE, {"users": []}), (KEYS_FILE, {}), (SESS_FILE, {})):
        if not os.path.exists(p):
            write_json(p, default)


def read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def secret_bytes():
    with open(SECRET_FILE, "r", encoding="utf-8") as f:
        return bytes.fromhex(f.read().strip())


def xor_bytes(data, key):
    out = bytearray(len(data))
    k = key
    i = 0
    while i < len(data):
        block = hashlib.sha256(k + i.to_bytes(4, "big")).digest()
        for b in block:
            if i >= len(data):
                break
            out[i] = data[i] ^ b
            i += 1
    return bytes(out)


def enc_key(plain, sid):
    if not plain:
        return ""
    raw = xor_bytes(plain.encode("utf-8"), secret_bytes() + sid.encode("utf-8"))
    return base64.b64encode(raw).decode("ascii")


def dec_key(cipher, sid):
    if not cipher:
        return ""
    raw = base64.b64decode(cipher.encode("ascii"))
    return xor_bytes(raw, secret_bytes() + sid.encode("utf-8")).decode("utf-8", "replace")


# ---------------------------------------------------------------- 密码
def hash_pwd(pwd, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pwd.encode("utf-8"), salt.encode("utf-8"), 150_000)
    return "pbkdf2$%s$%s" % (salt, h.hex())


def check_pwd(pwd, stored):
    try:
        _, salt, _ = stored.split("$")
        return hmac.compare_digest(hash_pwd(pwd, salt), stored)
    except Exception:
        return False


# ---------------------------------------------------------------- HTTP 工具
def http_json(url, payload=None, headers=None, timeout=180, method=None):
    data = None
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=hdrs,
                                 method=method or ("POST" if data else "GET"))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            if "application/json" in r.headers.get("Content-Type", ""):
                return json.loads(body.decode("utf-8"))
            return {"_raw": body}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:600]
        raise RuntimeError("HTTP %s: %s" % (e.code, detail))
    except Exception as e:
        raise RuntimeError(str(e))


def fetch_b64(url, timeout=120):
    req = urllib.request.Request(url, headers={"User-Agent": "cumtb-practice/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return base64.b64encode(r.read()).decode("ascii")


def clean_think(t):
    t = re.sub(r"<think>.*?</think>", "", t or "", flags=re.S | re.I)
    return re.sub(r"</?think>", "", t, flags=re.I).strip()


class Handler(SimpleHTTPRequestHandler):
    server_version = "PracticePlatform/1.0"

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=PUBLIC, **kw)

    # ------------------------------------------------ 基础
    def log_message(self, fmt, *args):
        try:
            if sys.stdout and "/api/" in (self.path or ""):
                sys.stdout.write("  · %s\n" % (fmt % args))
        except Exception:
            pass

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def json_out(self, obj, code=200, cookie=None):
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(raw)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return {}

    # ------------------------------------------------ 会话
    def current_user(self):
        raw = self.headers.get("Cookie") or ""
        for part in raw.split(";"):
            if part.strip().startswith("pf_session="):
                token = part.strip().split("=", 1)[1]
                sess = read_json(SESS_FILE, {})
                info = sess.get(token)
                if info and info.get("exp", 0) > time.time():
                    users = read_json(USERS_FILE, {"users": []})["users"]
                    for u in users:
                        if u["sid"] == info["sid"]:
                            return u
                break
        return None

    def start_session(self, sid):
        token = secrets.token_urlsafe(32)
        with _lock:
            sess = read_json(SESS_FILE, {})
            now = time.time()
            sess = {k: v for k, v in sess.items() if v.get("exp", 0) > now}
            sess[token] = {"sid": sid, "exp": now + SESSION_DAYS * 86400}
            write_json(SESS_FILE, sess)
        return "pf_session=%s; Path=/; HttpOnly; SameSite=Lax; Max-Age=%d" % (token, SESSION_DAYS * 86400)

    # ------------------------------------------------ 路由
    def do_GET(self):
        u = urlparse(self.path)
        path = unquote(u.path)   # 中文文件名需要解码

        if path == "/api/ping":
            return self.json_out({"ok": True, "app": APP_NAME})

        if path.startswith("/api/"):
            user = self.current_user()
            if not user:
                return self.json_out({"error": "未登录"}, 401)
            if path == "/api/me":
                return self.json_out({"sid": user["sid"], "name": user.get("name", ""),
                                      "role": user.get("role", "member")})
            if path == "/api/roster":
                return self.api_roster(user)
            if path == "/api/config":
                return self.api_get_config(user)
            return self.json_out({"error": "未知接口"}, 404)

        # 静态资源：未登录只能看登录页
        if path in ("/", "/index.html"):
            return self.serve_file(os.path.join(PUBLIC, "index.html"))
        # 登录页需要的最小资源，放行
        if path in ("/logo.png", "/favicon.png"):
            return self.serve_public(path.lstrip("/"))
        if path in ("/favicon.ico",):
            return self.send_error(404)

        if not self.current_user():
            return self.redirect("/")

        if path.startswith("/vi"):
            rel = path[len("/vi"):] or "/index.html"
            return self.serve_public(os.path.join("vi", rel.lstrip("/")))
        if path.startswith("/poster"):
            rel = path[len("/poster"):] or "/workbench/index.html"
            if rel in ("/", ""):
                rel = "/workbench/index.html"
            return self.serve_public(os.path.join("poster", rel.lstrip("/")))

        self.send_error(404)

    def do_POST(self):
        path = unquote(urlparse(self.path).path)
        if path == "/api/register":
            return self.api_register()
        if path == "/api/login":
            return self.api_login()
        if path == "/api/logout":
            return self.api_logout()

        user = self.current_user()
        if not user:
            return self.json_out({"error": "未登录"}, 401)

        if path == "/api/key" or path == "/api/config":
            return self.api_set_key(user)
        if path == "/api/generate":
            return self.api_generate(user)
        if path == "/api/vision":
            return self.api_vision(user)
        if path == "/api/roster/delete":
            return self.api_delete_user(user)
        return self.json_out({"error": "未知接口"}, 404)

    # ------------------------------------------------ 静态
    def serve_public(self, rel):
        target = os.path.normpath(os.path.join(PUBLIC, rel))
        if not target.startswith(PUBLIC):
            return self.send_error(403)
        if os.path.isdir(target):
            target = os.path.join(target, "index.html")
        if not os.path.exists(target):
            return self.send_error(404)
        self.serve_file(target)

    def serve_file(self, target):
        ext = os.path.splitext(target)[1].lower()
        ctype = {".webp": "image/webp", ".woff2": "font/woff2", ".woff": "font/woff",
                 ".ttf": "font/ttf", ".otf": "font/otf", ".svg": "image/svg+xml",
                 ".json": "application/json; charset=utf-8"}.get(ext) or self.guess_type(target)
        try:
            with open(target, "rb") as f:
                raw = f.read()
        except OSError:
            return self.send_error(404)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(raw)

    def redirect(self, to):
        self.send_response(302)
        self.send_header("Location", to)
        self.end_headers()

    # ------------------------------------------------ 账号
    def api_register(self):
        b = self.body()
        sid = (b.get("sid") or "").strip()
        pwd = b.get("password") or ""
        name = (b.get("name") or "").strip()[:20]

        if not SID_RE.match(sid):
            return self.json_out({"error": "学号必须是 10 位数字"}, 400)
        if len(pwd) < 6:
            return self.json_out({"error": "密码至少 6 位"}, 400)

        with _lock:
            data = read_json(USERS_FILE, {"users": []})
            if any(u["sid"] == sid for u in data["users"]):
                return self.json_out({"error": "该学号已注册，请直接登录"}, 409)
            role = "admin" if not data["users"] else "member"
            data["users"].append({
                "sid": sid, "name": name or sid,
                "pwd": hash_pwd(pwd),
                "role": role,
                "created": int(time.time()),
            })
            write_json(USERS_FILE, data)

        return self.json_out({"ok": True, "sid": sid}, cookie=self.start_session(sid))

    def api_login(self):
        b = self.body()
        sid = (b.get("sid") or "").strip()
        pwd = b.get("password") or ""
        data = read_json(USERS_FILE, {"users": []})
        for u in data["users"]:
            if u["sid"] == sid and check_pwd(pwd, u["pwd"]):
                return self.json_out({"ok": True, "sid": sid}, cookie=self.start_session(sid))
        return self.json_out({"error": "学号或密码不正确"}, 401)

    def api_logout(self):
        cookie = self.headers.get("Cookie") or ""
        for part in cookie.split(";"):
            if part.strip().startswith("pf_session="):
                token = part.strip().split("=", 1)[1]
                with _lock:
                    sess = read_json(SESS_FILE, {})
                    sess.pop(token, None)
                    write_json(SESS_FILE, sess)
        return self.json_out({"ok": True}, cookie="pf_session=; Path=/; Max-Age=0")

    def api_roster(self, user):
        data = read_json(USERS_FILE, {"users": []})
        keys = read_json(KEYS_FILE, {})
        rows = []
        for u in data["users"]:
            k = keys.get(u["sid"]) or {}
            rows.append({
                "sid": u["sid"],
                "name": u.get("name", ""),
                "role": u.get("role", "member"),
                "created": u.get("created", 0),
                "hasKey": bool(k.get("enc")),
                "provider": k.get("provider", ""),
            })
        rows.sort(key=lambda r: r["created"])
        return self.json_out({"users": rows, "me": user["sid"],
                              "isAdmin": user.get("role") == "admin"})

    def api_delete_user(self, user):
        if user.get("role") != "admin":
            return self.json_out({"error": "只有管理员可以移除成员"}, 403)
        sid = (self.body().get("sid") or "").strip()
        if sid == user["sid"]:
            return self.json_out({"error": "不能移除自己"}, 400)
        with _lock:
            data = read_json(USERS_FILE, {"users": []})
            data["users"] = [u for u in data["users"] if u["sid"] != sid]
            write_json(USERS_FILE, data)
            keys = read_json(KEYS_FILE, {})
            keys.pop(sid, None)
            write_json(KEYS_FILE, keys)
        return self.json_out({"ok": True})

    # ------------------------------------------------ 每用户 AI 配置
    def user_cfg(self, sid):
        k = (read_json(KEYS_FILE, {}).get(sid)) or {}
        p = PROVIDERS.get(k.get("provider") or "zhipu", PROVIDERS["zhipu"])
        return {
            "provider": k.get("provider") or "zhipu",
            "apiKey": dec_key(k.get("enc", ""), sid),
            "base": (k.get("baseUrl") or p["base"]).rstrip("/"),
            "imageModel": k.get("imageModel") or p["img"],
            "visionModel": k.get("visionModel") or p["vis"],
        }

    def api_get_config(self, user):
        cfg = self.user_cfg(user["sid"])
        key = cfg["apiKey"]
        return self.json_out({
            "provider": cfg["provider"],
            "hasKey": bool(key),
            "keyMask": ("*" * max(0, len(key) - 4) + key[-4:]) if key else "",
            "imageModel": cfg["imageModel"],
            "visionModel": cfg["visionModel"],
            "baseUrl": cfg["base"],
            "providers": {k: {"label": v["label"], "img": v["img"], "vis": v["vis"], "hint": v["hint"]}
                          for k, v in PROVIDERS.items()},
        })

    def api_set_key(self, user):
        b = self.body()
        with _lock:
            keys = read_json(KEYS_FILE, {})
            cur = keys.get(user["sid"]) or {}
            provider = b.get("provider") or cur.get("provider") or "zhipu"
            api_key = b.get("apiKey")
            if api_key is None:
                api_key = cur.get("apiKey_plain", "")
            keys[user["sid"]] = {
                "provider": provider,
                "enc": enc_key(api_key, user["sid"]) if api_key else "",
                "baseUrl": b.get("baseUrl", cur.get("baseUrl", "")),
                "imageModel": b.get("imageModel", cur.get("imageModel", "")),
                "visionModel": b.get("visionModel", cur.get("visionModel", "")),
            }
            write_json(KEYS_FILE, keys)
        return self.json_out({"ok": True})

    # ------------------------------------------------ AI
    def api_generate(self, user):
        cfg = self.user_cfg(user["sid"])
        b = self.body()
        prompt = (b.get("prompt") or "").strip()
        kind = b.get("kind") or "icon"
        size = b.get("size") or "1024x1024"
        if not prompt:
            return self.json_out({"error": "提示词为空"}, 400)
        if not cfg["apiKey"]:
            return self.json_out({"error": "还没有配置 API Key，请到「设置」填写"}, 400)

        payload = {"model": cfg["imageModel"], "prompt": prompt, "size": size}
        if cfg["provider"] == "openai":
            payload["response_format"] = "b64_json"
        try:
            data = http_json(cfg["base"] + "/images/generations", payload,
                             headers={"Authorization": "Bearer " + cfg["apiKey"]})
        except RuntimeError as e:
            return self.json_out({"error": str(e)}, 502)

        items = data.get("data") or []
        out = []
        for it in items[:2]:
            if it.get("b64_json"):
                out.append("data:image/png;base64," + it["b64_json"])
            elif it.get("url"):
                try:
                    out.append("data:image/png;base64," + fetch_b64(it["url"]))
                except Exception as e:
                    return self.json_out({"error": "下载生成结果失败：%s" % e}, 502)
        if not out:
            return self.json_out({"error": "接口没有返回图片"}, 502)
        return self.json_out({"images": out})

    def api_vision(self, user):
        cfg = self.user_cfg(user["sid"])
        b = self.body()
        image = b.get("image") or ""
        prompt = b.get("prompt") or ""
        if not image:
            return self.json_out({"error": "缺少图片"}, 400)
        if not cfg["apiKey"]:
            return self.json_out({"error": "还没有配置 API Key"}, 400)

        models = [cfg["visionModel"]]
        if cfg["provider"] == "zhipu":
            for m in ("glm-4v-flash", "glm-4.6v-flash", "glm-4.1v-thinking-flash"):
                if m not in models:
                    models.append(m)

        last = None
        for m in models:
            payload = {
                "model": m,
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image}},
                ]}],
                "temperature": 0.4,
            }
            try:
                data = http_json(cfg["base"] + "/chat/completions", payload,
                                 headers={"Authorization": "Bearer " + cfg["apiKey"]})
            except RuntimeError as e:
                last = e
                msg = str(e)
                if "1113" in msg or "1305" in msg or "429" in msg:
                    continue
                return self.json_out({"error": msg}, 502)
            text = data["choices"][0]["message"]["content"]
            if isinstance(text, list):
                text = "".join(c.get("text", "") for c in text if isinstance(c, dict))
            return self.json_out({"text": clean_think(text), "model": m})
        return self.json_out({"error": "视觉模型暂时不可用：%s" % last}, 502)


def free_port(start):
    for p in range(start, start + 30):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    return start


def already_running(port):
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/api/ping" % port, timeout=1.5) as r:
            return r.status == 200
    except Exception:
        return False


def main():
    ensure_data()
    args = [a for a in sys.argv[1:]]
    silent = "--silent" in args
    args = [a for a in args if not a.startswith("--")]
    base_port = int(args[0]) if args else 7788

    # 已经在跑：直接打开浏览器，不再起第二个实例
    if already_running(base_port):
        if not silent and not os.environ.get("PF_NO_BROWSER"):
            webbrowser.open("http://127.0.0.1:%d/" % base_port)
        say("服务已在运行： http://127.0.0.1:%d/" % base_port)
        return

    port = free_port(base_port)
    with open(os.path.join(ROOT, "port.txt"), "w", encoding="utf-8") as f:
        f.write(str(port))

    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = "http://127.0.0.1:%d/" % port
    if not silent:
        say("")
        say("  %s" % APP_NAME)
        say("  →  %s" % url)
        say("  按 Ctrl+C 停止")
        say("")
        if not os.environ.get("PF_NO_BROWSER"):
            threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        say("\n已停止")


if __name__ == "__main__":
    main()
