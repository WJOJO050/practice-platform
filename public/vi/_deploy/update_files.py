# -*- coding: utf-8 -*-
"""更新仓库中的若干文件（一次提交）。"""

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

TOKEN = os.environ["GH_TOKEN"].strip()
OWNER = os.environ.get("GH_OWNER", "WJOJO050")
REPO = os.environ.get("REPO_NAME", "vi")
API = "https://api.github.com"
UA = "vi-deployer"


def call(method, path, payload=None, ok=(200, 201)):
    url = API + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + TOKEN)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", UA)
    if data:
        req.add_header("Content-Type", "application/json")
    last = (0, {})
    for a in range(4):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                body = r.read().decode("utf-8")
                return r.status, (json.loads(body) if body else {})
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            try:
                last = (e.code, json.loads(body))
            except Exception:
                last = (e.code, {"raw": body})
            if e.code in (401, 429, 500, 502, 503, 504):
                time.sleep(2 + a * 2)
                continue
            return last
        except Exception as e:
            last = (0, {"message": str(e)})
            time.sleep(2 + a * 2)
    return last


def main(pairs):
    st, ref = call("GET", "/repos/%s/%s/git/refs/heads/main" % (OWNER, REPO))
    base_commit = ref["object"]["sha"]
    st, commit = call("GET", "/repos/%s/%s/git/commits/%s" % (OWNER, REPO, base_commit))
    base_tree = commit["tree"]["sha"]

    entries = []
    for rel, full in pairs:
        with open(full, "rb") as f:
            blob = base64.b64encode(f.read()).decode("ascii")
        st, res = call("POST", "/repos/%s/%s/git/blobs" % (OWNER, REPO),
                       {"content": blob, "encoding": "base64"})
        if st not in (200, 201):
            print("BLOB_ERR", rel, st, res.get("message"))
            return 1
        entries.append({"path": rel, "mode": "100644", "type": "blob", "sha": res["sha"]})
        print("blob ok:", rel)

    st, tree = call("POST", "/repos/%s/%s/git/trees" % (OWNER, REPO),
                    {"base_tree": base_tree, "tree": entries})
    if st not in (200, 201):
        print("TREE_ERR", st, tree.get("message"))
        return 1
    st, nc = call("POST", "/repos/%s/%s/git/commits" % (OWNER, REPO),
                  {"message": "更新：网盘下载链接与维护方声明", "tree": tree["sha"], "parents": [base_commit]})
    if st not in (200, 201):
        print("COMMIT_ERR", st, nc.get("message"))
        return 1
    st, upd = call("PATCH", "/repos/%s/%s/git/refs/heads/main" % (OWNER, REPO),
                   {"sha": nc["sha"], "force": False})
    if st not in (200, 201):
        print("REF_ERR", st, upd.get("message"))
        return 1
    print("new commit:", nc["sha"][:10])
    return 0


if __name__ == "__main__":
    site = r"D:\文档\BaiduSyncdisk\工作\学生会工作\科技部工作材料\平面设计\人工智能学院视觉形象系统\网站"
    pairs = [
        ("assets/js/data.js", os.path.join(site, "assets", "js", "data.js")),
        ("index.html", os.path.join(site, "index.html")),
        ("assets/css/style.css", os.path.join(site, "assets", "css", "style.css")),
    ]
    sys.exit(main(pairs))
