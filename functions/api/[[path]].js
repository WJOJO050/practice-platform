// Cloudflare Pages Functions · /api/*
// 所有接口集中在这一个文件，路由用 path 尾段判断。
//
// 需要的绑定：
//   KV  命名空间  PF         （账号、密钥、会话）
//   环境变量      PF_SECRET  （32 位以上随机字符串，用于加密 API Key）

const SID_RE = /^\d{10}$/;
const SESSION_DAYS = 14;
const PBKDF2_ITER = 100000;

const PROVIDERS = {
  zhipu: {
    label: "智谱 GLM",
    base: "https://open.bigmodel.cn/api/paas/v4",
    img: "cogview-3-flash",
    vis: "glm-4v-flash",
    hint: "cogview-3-flash 免费；glm-4v-flash 免费",
  },
  siliconflow: {
    label: "硅基流动 SiliconFlow",
    base: "https://api.siliconflow.cn/v1",
    img: "Kwai-Kolors/Kolors",
    vis: "Qwen/Qwen2-VL-72B-Instruct",
    hint: "注册送额度；图像可用 Kolors/FLUX",
  },
  dashscope: {
    label: "阿里云百炼 · 通义万相",
    base: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    img: "wanx2.1-t2i-turbo",
    vis: "qwen-vl-max",
    hint: "需开通百炼",
  },
  openai: {
    label: "OpenAI",
    base: "https://api.openai.com/v1",
    img: "gpt-image-1",
    vis: "gpt-4o-mini",
    hint: "国内需代理",
  },
  custom: { label: "自定义（OpenAI 兼容）", base: "", img: "", vis: "", hint: "填 /v1 结尾的 baseUrl" },
};

// ---------------------------------------------------------------- 工具
function json(obj, status = 200, extra = {}) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store", ...extra },
  });
}

function getCookie(req, name) {
  const raw = req.headers.get("Cookie") || "";
  for (const part of raw.split(";")) {
    const [k, ...v] = part.trim().split("=");
    if (k === name) return v.join("=");
  }
  return null;
}

function sessionCookie(token, maxAge) {
  return `pf_session=${token}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${maxAge}`;
}

function hex(buf) {
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function unhex(s) {
  const out = new Uint8Array(s.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(s.substr(i * 2, 2), 16);
  return out;
}

function b64(buf) {
  let s = "";
  const bytes = new Uint8Array(buf);
  for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
  return btoa(s);
}

function unb64(s) {
  const bin = atob(s);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

async function sha256(str) {
  return await crypto.subtle.digest("SHA-256", new TextEncoder().encode(str));
}

// ---------------------------------------------------------------- 加密
async function aesKey(env) {
  const material = await sha256("pf:" + (env.PF_SECRET || "dev-secret"));
  return crypto.subtle.importKey("raw", material, { name: "AES-GCM" }, false, ["encrypt", "decrypt"]);
}

async function encryptKey(env, plain, sid) {
  if (!plain) return null;
  const key = await aesKey(env);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const data = new TextEncoder().encode(sid + "|" + plain);
  const enc = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, data);
  return { iv: b64(iv), data: b64(enc) };
}

async function decryptKey(env, box, sid) {
  if (!box || !box.data) return "";
  try {
    const key = await aesKey(env);
    const dec = await crypto.subtle.decrypt({ name: "AES-GCM", iv: unb64(box.iv) }, key, unb64(box.data));
    const text = new TextDecoder().decode(dec);
    const i = text.indexOf("|");
    return i >= 0 ? text.slice(i + 1) : text;
  } catch {
    return "";
  }
}

// ---------------------------------------------------------------- 密码
async function hashPassword(pwd, saltHex) {
  const salt = saltHex ? unhex(saltHex) : crypto.getRandomValues(new Uint8Array(16));
  const material = await crypto.subtle.importKey("raw", new TextEncoder().encode(pwd), "PBKDF2", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits(
    { name: "PBKDF2", salt, iterations: PBKDF2_ITER, hash: "SHA-256" },
    material,
    256
  );
  return `pbkdf2$${hex(salt)}$${hex(bits)}`;
}

async function verifyPassword(pwd, stored) {
  try {
    const [kind, salt] = stored.split("$");
    if (kind !== "pbkdf2") return false;
    const again = await hashPassword(pwd, salt);
    if (again.length !== stored.length) return false;
    let diff = 0;
    for (let i = 0; i < again.length; i++) diff |= again.charCodeAt(i) ^ stored.charCodeAt(i);
    return diff === 0;
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------- 存储
async function getUser(env, sid) {
  return await env.PF.get("user:" + sid, "json");
}

async function putUser(env, user) {
  await env.PF.put("user:" + user.sid, JSON.stringify(user));
}

async function getUserKey(env, sid) {
  return (await env.PF.get("key:" + sid, "json")) || {};
}

async function putUserKey(env, sid, obj) {
  await env.PF.put("key:" + sid, JSON.stringify(obj));
}

async function currentUser(req, env) {
  const token = getCookie(req, "pf_session");
  if (!token) return null;
  const sess = await env.PF.get("sess:" + token, "json");
  if (!sess || (sess.exp && sess.exp < Date.now())) return null;
  return await getUser(env, sess.sid);
}

async function startSession(env, sid) {
  const token = [...crypto.getRandomValues(new Uint8Array(24))].map((b) => b.toString(16).padStart(2, "0")).join("");
  await env.PF.put("sess:" + token, JSON.stringify({ sid, exp: Date.now() + SESSION_DAYS * 86400 * 1000 }), {
    expirationTtl: SESSION_DAYS * 86400,
  });
  return token;
}

function userConfig(env, user, stored) {
  const p = PROVIDERS[stored.provider] || PROVIDERS.zhipu;
  return {
    provider: stored.provider || "zhipu",
    base: (stored.baseUrl || p.base || "").replace(/\/$/, ""),
    imageModel: stored.imageModel || p.img,
    visionModel: stored.visionModel || p.vis,
    box: stored.enc || null,
  };
}

// ---------------------------------------------------------------- 上游请求
async function callJSON(url, payload, apiKey, timeoutMs = 120000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: "Bearer " + apiKey },
      body: JSON.stringify(payload),
      signal: ctrl.signal,
    });
    const text = await res.text();
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${text.slice(0, 400)}`);
    return JSON.parse(text);
  } finally {
    clearTimeout(timer);
  }
}

async function fetchB64(url) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 90000);
  try {
    const res = await fetch(url, { signal: ctrl.signal });
    const buf = await res.arrayBuffer();
    return b64(buf);
  } finally {
    clearTimeout(timer);
  }
}

function cleanThink(t) {
  return (t || "")
    .replace(/<think>[\s\S]*?<\/think>/gi, "")
    .replace(/<\/?think>/gi, "")
    .trim();
}

// ---------------------------------------------------------------- 主入口
export async function onRequest(context) {
  const { request, env } = context;
  const url = new URL(request.url);
  const action = url.pathname.replace(/^\/api\/?/, "").replace(/\/$/, "");
  const method = request.method;

  if (!env.PF) return json({ error: "缺少 KV 绑定 PF（请在 Pages 设置里绑定命名空间）" }, 500);

  if (method === "GET" && action === "ping") {
    return json({ ok: true, app: "人工智能学院科技部实践平台" });
  }

  try {
    if (method === "POST" && action === "register") return await apiRegister(request, env);
    if (method === "POST" && action === "login") return await apiLogin(request, env);
    if (method === "POST" && action === "logout") return await apiLogout(request, env);

    const user = await currentUser(request, env);
    if (!user) return json({ error: "未登录" }, 401);

    if (method === "GET" && action === "me") {
      return json({ sid: user.sid, name: user.name || "", role: user.role || "member" });
    }
    if (method === "GET" && action === "roster") return await apiRoster(env, user);
    if (method === "GET" && action === "config") return await apiGetConfig(env, user);
    if (method === "POST" && (action === "key" || action === "config")) return await apiSetKey(request, env, user);
    if (method === "POST" && action === "generate") return await apiGenerate(request, env, user);
    if (method === "POST" && action === "vision") return await apiVision(request, env, user);
    if (method === "POST" && action === "roster/delete") return await apiDeleteUser(request, env, user);

    return json({ error: "未知接口" }, 404);
  } catch (e) {
    return json({ error: "服务端异常：" + (e && e.message ? e.message : String(e)) }, 500);
  }
}

// ---------------------------------------------------------------- 账号
async function apiRegister(request, env) {
  const b = await request.json().catch(() => ({}));
  const sid = String(b.sid || "").trim();
  const pwd = String(b.password || "");
  const name = String(b.name || "").trim().slice(0, 20);

  if (!SID_RE.test(sid)) return json({ error: "学号必须是 10 位数字" }, 400);
  if (pwd.length < 6) return json({ error: "密码至少 6 位" }, 400);
  if (await getUser(env, sid)) return json({ error: "该学号已注册，请直接登录" }, 409);

  const list = await env.PF.list({ prefix: "user:", limit: 1 });
  const role = list.keys.length === 0 ? "admin" : "member";

  const user = { sid, name: name || sid, pwd: await hashPassword(pwd), role, created: Date.now() };
  await putUser(env, user);
  const token = await startSession(env, sid);
  return json({ ok: true, sid }, 200, { "Set-Cookie": sessionCookie(token, SESSION_DAYS * 86400) });
}

async function apiLogin(request, env) {
  const b = await request.json().catch(() => ({}));
  const sid = String(b.sid || "").trim();
  const pwd = String(b.password || "");
  const user = await getUser(env, sid);
  if (!user || !(await verifyPassword(pwd, user.pwd))) {
    return json({ error: "学号或密码不正确" }, 401);
  }
  const token = await startSession(env, sid);
  return json({ ok: true, sid }, 200, { "Set-Cookie": sessionCookie(token, SESSION_DAYS * 86400) });
}

async function apiLogout(request, env) {
  const token = getCookie(request, "pf_session");
  if (token) await env.PF.delete("sess:" + token);
  return json({ ok: true }, 200, { "Set-Cookie": sessionCookie("", 0) });
}

async function apiRoster(env, me) {
  const list = await env.PF.list({ prefix: "user:" });
  const users = [];
  for (const k of list.keys) {
    const u = await env.PF.get(k.name, "json");
    if (!u) continue;
    const key = await getUserKey(env, u.sid);
    users.push({
      sid: u.sid,
      name: u.name,
      role: u.role,
      created: Math.floor((u.created || 0) / 1000),
      hasKey: !!(key && key.enc),
    });
  }
  users.sort((a, b) => a.created - b.created);
  return json({ users, me: me.sid, isAdmin: me.role === "admin" });
}

async function apiDeleteUser(request, env, me) {
  if (me.role !== "admin") return json({ error: "只有管理员可以移除成员" }, 403);
  const b = await request.json().catch(() => ({}));
  const sid = String(b.sid || "").trim();
  if (sid === me.sid) return json({ error: "不能移除自己" }, 400);
  await env.PF.delete("user:" + sid);
  await env.PF.delete("key:" + sid);
  return json({ ok: true });
}

// ---------------------------------------------------------------- AI 配置
async function apiGetConfig(env, user) {
  const cfg = userConfig(env, user, await getUserKey(env, user.sid));
  const plain = await decryptKey(env, cfg.box, user.sid);
  return json({
    provider: cfg.provider,
    hasKey: !!plain,
    keyMask: plain ? "*".repeat(Math.max(0, plain.length - 4)) + plain.slice(-4) : "",
    imageModel: cfg.imageModel,
    visionModel: cfg.visionModel,
    baseUrl: cfg.base,
    providers: Object.fromEntries(
      Object.entries(PROVIDERS).map(([k, v]) => [k, { label: v.label, img: v.img, vis: v.vis, hint: v.hint }])
    ),
  });
}

async function apiSetKey(request, env, user) {
  const b = await request.json().catch(() => ({}));
  const cur = await getUserKey(env, user.sid);
  const provider = b.provider || cur.provider || "zhipu";

  let box = cur.enc || null;
  if (b.apiKey) box = await encryptKey(env, b.apiKey, user.sid);
  if (b.apiKey === "") box = null;

  await putUserKey(env, user.sid, {
    provider,
    enc: box,
    baseUrl: b.baseUrl !== undefined ? b.baseUrl : cur.baseUrl || "",
    imageModel: b.imageModel !== undefined ? b.imageModel : cur.imageModel || "",
    visionModel: b.visionModel !== undefined ? b.visionModel : cur.visionModel || "",
  });
  return json({ ok: true });
}

// ---------------------------------------------------------------- 生图 / 评审
async function apiGenerate(request, env, user) {
  const b = await request.json().catch(() => ({}));
  const prompt = String(b.prompt || "").trim();
  const size = b.size || "1024x1024";
  if (!prompt) return json({ error: "提示词为空" }, 400);

  const cfg = userConfig(env, user, await getUserKey(env, user.sid));
  const apiKey = await decryptKey(env, cfg.box, user.sid);
  if (!apiKey) return json({ error: "还没有配置 API Key，请到「AI 设置」填写" }, 400);

  const payload = { model: cfg.imageModel, prompt, size };
  if (cfg.provider === "openai") payload.response_format = "b64_json";

  let data;
  try {
    data = await callJSON(cfg.base + "/images/generations", payload, apiKey);
  } catch (e) {
    return json({ error: e.message }, 502);
  }

  const out = [];
  for (const it of (data.data || []).slice(0, 2)) {
    if (it.b64_json) out.push("data:image/png;base64," + it.b64_json);
    else if (it.url) {
      try {
        out.push("data:image/png;base64," + (await fetchB64(it.url)));
      } catch (e) {
        return json({ error: "下载生成结果失败：" + e.message }, 502);
      }
    }
  }
  if (!out.length) return json({ error: "接口没有返回图片" }, 502);
  return json({ images: out });
}

async function apiVision(request, env, user) {
  const b = await request.json().catch(() => ({}));
  const image = b.image || "";
  const prompt = b.prompt || "";
  if (!image) return json({ error: "缺少图片" }, 400);

  const cfg = userConfig(env, user, await getUserKey(env, user.sid));
  const apiKey = await decryptKey(env, cfg.box, user.sid);
  if (!apiKey) return json({ error: "还没有配置 API Key" }, 400);

  const models = [cfg.visionModel];
  if (cfg.provider === "zhipu") {
    for (const m of ["glm-4v-flash", "glm-4.6v-flash", "glm-4.1v-thinking-flash"]) {
      if (!models.includes(m)) models.push(m);
    }
  }

  let last = "";
  for (const model of models) {
    const payload = {
      model,
      messages: [
        {
          role: "user",
          content: [
            { type: "text", text: prompt },
            { type: "image_url", image_url: { url: image } },
          ],
        },
      ],
      temperature: 0.4,
    };
    try {
      const data = await callJSON(cfg.base + "/chat/completions", payload, apiKey);
      let text = data?.choices?.[0]?.message?.content ?? "";
      if (Array.isArray(text)) text = text.map((c) => c.text || "").join("");
      return json({ text: cleanThink(text), model });
    } catch (e) {
      last = e.message;
      if (/1113|1305|429/.test(last)) continue;
      return json({ error: last }, 502);
    }
  }
  return json({ error: "视觉模型暂时不可用：" + last }, 502);
}
