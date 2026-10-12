---
title: AI 旅游小助手
emoji: ✈️
colorFrom: green
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# AI 旅游小助手

FastAPI 后端 + 多智能体（路线 / 酒店 / 美食 / 天气 / 预算 / 交通），同源托管网页前端。

- 公网地址：`https://<你的用户名>-ai-travel-agent.hf.space`
- 接口：`POST /chat/stream`（SSE）、`GET /api/map_config`
- 密钥通过 Space Secrets 注入（DASHSCOPE_API_KEY / DASHSCOPE_BASE_URL / MODEL_NAME / AMAP_KEY）
