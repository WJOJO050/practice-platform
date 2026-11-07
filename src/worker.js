// Cloudflare Worker 入口
//   /api/*  → 调到 handleApi（账号、名单、生图、评审）
//   其他路径 → 交给静态资源（public/）

import { handleApi } from "./api.js";

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (url.pathname === "/api" || url.pathname.startsWith("/api/")) {
      return handleApi(request, env);
    }

    // 静态资源；找不到时回落到 SPA 入口
    if (env.ASSETS) {
      const res = await env.ASSETS.fetch(request);
      if (res.status !== 404) return res;
      if (!url.pathname.includes(".")) {
        return env.ASSETS.fetch(new Request(new URL("/index.html", url), request));
      }
      return res;
    }

    return new Response("静态资源未绑定（ASSETS）", { status: 500 });
  },
};
