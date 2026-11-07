# -*- coding: utf-8 -*-
"""用 GitHub REST API 部署静态站（不依赖 git，走 HTTPS/代理）。

用法（环境变量）：
  GH_TOKEN   必填
  REPO_NAME  默认 vi
"""

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

SITE = r"D:\文档\BaiduSyncdisk\工作\学生会工作\科技部工作材料\平面设计\人工智能学院视觉形象系统\网站"
TOKEN = os.environ.get("GH_TOKEN", "").strip()
REPO = os.environ.get("REPO_NAME", "vi").strip()
API = "https://api.github.com"
UA = "vi-site-deployer"


def _once(method, path, payload):
    url = API + path if path.startswith("/") else path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + TOKEN)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", UA)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            body = r.read().decode("utf-8")
            return r.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"raw": body}
    except Exception as e:
        return 0, {"message": "NET: %s" % e}


def call(method, path, payload=None, ok=(200, 201, 204)):
    last = (0, {})
    for attempt in range(5):
        st, body = _once(method, path, payload)
        if st in ok:
            return st, body
        last = (st, body)
        if st in (0, 401, 429, 500, 502, 503, 504):
            time.sleep(2 + attempt * 3)
            continue
        return last
    return last


def _old_call(method, path, payload=None, ok=(200, 201, 204)):
    url = API + path if path.startswith("/") else path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + TOKEN)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", UA)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read().decode("utf-8")
            return r.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = {"raw": body}
        return e.code, parsed


def main():
    if not TOKEN:
        print("NO_TOKEN")
        return 1

    st, me = call("GET", "/user")
    if st != 200:
        print("AUTH_FAIL", st, me.get("message"))
        return 1
    owner = me["login"]
    print("login:", owner)

    # 1) 建仓库
    st, repo = call("POST", "/user/repos", {
        "name": REPO,
        "description": "中国矿业大学（北京）人工智能学院 · 视觉形象识别系统",
        "homepage": "https://%s.github.io/%s/" % (owner.lower(), REPO),
        "private": False,
        "has_issues": False,
        "has_wiki": False,
        "has_projects": False,
        "auto_init": False,
    })
    if st == 201:
        print("repo created:", repo["full_name"])
    elif st in (403, 422):
        print("repo exists, reuse")
        st2, repo = call("GET", "/repos/%s/%s" % (owner, REPO))
        if st2 != 200:
            print("REPO_ERR", st2, repo.get("message"))
            return 1
    else:
        print("REPO_ERR", st, repo.get("message"))
        return 1

    # 1.5) 空仓库需要先有一个提交，Git Data API 才能建 blob
    st, chk = call("GET", "/repos/%s/%s/contents/" % (owner, REPO), ok=(200, 404))
    if st == 404:
        call("PUT", "/repos/%s/%s/contents/.init" % (owner, REPO), {
            "message": "init",
            "content": base64.b64encode(b"init").decode("ascii"),
        })
        print("initial commit created")

    # 2) 逐个文件建 blob
    files = []
    for root, _, names in os.walk(SITE):
        for n in names:
            if n.startswith("."):
                continue
            full = os.path.join(root, n)
            rel = os.path.relpath(full, SITE).replace("\\", "/")
            if rel.startswith("_") or "/_" in rel:
                continue
            files.append((rel, full))
    files.sort()
    print("files:", len(files))

    entries = []
    for i, (rel, full) in enumerate(files, 1):
        with open(full, "rb") as f:
            blob = base64.b64encode(f.read()).decode("ascii")
        st, res = call("POST", "/repos/%s/%s/git/blobs" % (owner, REPO),
                       {"content": blob, "encoding": "base64"})
        if st not in (200, 201):
            print("BLOB_ERR", rel, st, res.get("message"))
            return 1
        entries.append({"path": rel, "mode": "100644", "type": "blob", "sha": res["sha"]})
        if i % 20 == 0:
            print("  uploaded", i)

    # 3) 建 tree / commit / ref
    st, tree = call("POST", "/repos/%s/%s/git/trees" % (owner, REPO), {"tree": entries})
    if st not in (200, 201):
        print("TREE_ERR", st, tree.get("message"))
        return 1
    st, commit = call("POST", "/repos/%s/%s/git/commits" % (owner, REPO), {
        "message": "初始化：视觉形象识别系统网站",
        "tree": tree["sha"],
    })
    if st not in (200, 201):
        print("COMMIT_ERR", st, commit.get("message"))
        return 1
    st, ref = call("POST", "/repos/%s/%s/git/refs" % (owner, REPO),
                   {"ref": "refs/heads/main", "sha": commit["sha"]})
    if st not in (200, 201):
        if st == 422:
            st, ref = call("PATCH", "/repos/%s/%s/git/refs/heads/main" % (owner, REPO),
                           {"sha": commit["sha"], "force": True})
        if st not in (200, 201):
            print("REF_ERR", st, ref.get("message"))
            return 1
    print("commit:", commit["sha"][:10])

    # 4) 开 Pages
    st, pages = call("POST", "/repos/%s/%s/pages" % (owner, REPO),
                     {"source": {"branch": "main", "path": "/"}})
    if st in (201, 204):
        print("pages enabled")
    elif st == 409:
        print("pages already enabled")
    else:
        st2, pages = call("PUT", "/repos/%s/%s/pages" % (owner, REPO),
                          {"source": {"branch": "main", "path": "/"}})
        print("pages:", st, st2, pages.get("message", ""))

    print("URL: https://%s.github.io/%s/" % (owner.lower(), REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
