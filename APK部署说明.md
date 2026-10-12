# AI 旅游小助手 · 打包成 APK 部署说明

## 方案概览

本项目是「FastAPI 后端 + 网页前端」形态。打包 APK 采用 **WebView 壳 + 云端后端**：

```
[ Android APK ]
    └─ Capacitor WebView  ──打开──▶  https://你的域名/   （云端 FastAPI 服务）
                                          ├─ /               前端 index.html（同源托管）
                                          ├─ /chat/stream    SSE 流式对话
                                          └─ /api/map_config 前端地图 key
```

- 前端（`index.html` / `static/`）已经全部使用**相对路径**，后端本来就同源托管前端与 API，
  所以 APK 只是一个打开网址的浏览器壳，**前端几乎零改动**。
- 高德 key、DashScope key 都留在后端，不会写进 APK，**不会被反编译泄露**。

---

## 第一步：部署后端（必须，APK 依赖它）

APK 本身不含后端，必须有一个**公网可访问的 HTTPS 地址**常驻运行。

### 方式 A：Docker 部署（推荐，最省心）

```bash
# 1. 把整个项目目录放到服务器（含 .env）
# 2. 构建镜像
docker build -t ai-travel-agent .
# 3. 运行（把 .env 变量注入容器；端口映射 8000）
docker run -d --name travel-agent -p 8000:8000 \
  -e DASHSCOPE_API_KEY=xxx -e DASHSCOPE_BASE_URL=xxx \
  -e MODEL_NAME=xxx -e AMAP_KEY=xxx \
  ai-travel-agent
```

> 注意：`.env` 已写进 `.dockerignore`，不会打进镜像，运行时用 `-e` 注入或挂卷。

### 方式 B：云服务器 / 校园服务器直接跑

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
# 生产建议用反向代理（nginx / Caddy）做 HTTPS + 域名
```

### 方式 C：Render / 类似 PaaS 免费托管

- 连 GitHub 仓库，启动命令填 `uvicorn main:app --host 0.0.0.0 --port 8000`
- 在平台的环境变量里配置 4 个 key
- 平台会分配一个 `https://xxx.onrender.com` 域名（免费，但会休眠，演示够用）

### ⚠️ 关键：高德 key 域名白名单

高德「Web端(JS API)」类型的 key 默认**只认登记过的域名**。
到 [高德开放平台控制台](https://console.amap.com/) → 应用 → 对应 key → 设置「域名白名单」，
把你部署的域名（如 `yourdomain.com`，**不要带 http/https，也不要带端口**）加进去；
如果图省事可留空（允许所有域名，安全性略低）。

---

## 第二步：改 APK 壳指向你的域名

编辑 `mobile_app/capacitor.config.json`：

```json
{
  "appId": "com.travelagent.app",
  "appName": "AI旅游小助手",
  "server": {
    "url": "https://你的域名或Render地址",   // ← 改成第一步拿到的地址
    "androidScheme": "https",
    "cleartext": false
  }
}
```

`mobile_app/www/index.html` 是**离线兜底页**：后端挂掉时 WebView 会显示“服务暂时连不上”，避免白屏，一般不用改。

---

## 第三步：本地编译出 APK（需 Android SDK）

> 本机当前**没有 Android SDK / Gradle**，所以下面的 `assembleRelease` 这一步要你在装好 SDK 的机器上跑。
> 工程已经用 `npx cap add android` 生成好了 `mobile_app/android/` 原生项目。

1. 安装 **Android Studio**（含 SDK）或单独装 command-line tools；
   首次需接受 license：`sdkmanager --licenses`。
2. 装好 **Java 17+**（Capacitor 6 需要 JDK 17；本机是 Java 21，满足）。
3. 进入工程同步并构建：

```bash
cd mobile_app
npm install            # 若还没装
npx cap sync android  # 把配置同步进 android 工程
cd android
./gradlew assembleRelease   # 生成  app/build/outputs/apk/release/app-release-unsigned.apk
```

4. **签名**（发布必须）：用自己的 keystore 签名后才能安装到手机

```bash
# 生成签名（仅一次）
keytool -genkey -v -keystore my-release-key.keystore -alias travel -keyalg RSA -keysize 2048 -validity 10000
# 用 apksigner 签名
apksigner sign --ks my-release-key.keystore --out app-release.apk app/build/outputs/apk/release/app-release-unsigned.apk
```

装到手机：`adb install app-release.apk`（需开发者模式 + USB 调试）。

---

## 安全与注意事项

- ✅ key 不进 APK：所有密钥都在后端，前端只拿地图 JS key（本来就是公开给浏览器用的）。
- ✅ 必须 HTTPS：高德 JS API 在纯 http 下会受限；自签/无证书无法加载地图。
- ✅ `.env` / `*.keystore` 不要提交到公开仓库（已加进 `.gitignore` / `.dockerignore`）。
- ⚠️ 需要常驻后端：APK 是壳，后端停了 APP 就不能用（兜底页会提示）。
- ⚠️ 静态地图未实装：路线图仍是 SVG 自绘图；`static/` 下的 `route_map_*.svg` 同一天会堆积（清理只删 7 天前的），可在服务端加定时清理。

---

## 已知可优化（非阻塞）

- ✅ **已修复（2026-10-09）**：`mymcp/amap_mcp.py` 的 `amap_get()` 已由同步 `requests` 改为异步 `httpx.AsyncClient`，并发不再阻塞事件循环（部署到云后更稳）。
- 会话仅存 localStorage，换设备丢失，可加后端持久化。
- 无鉴权 / 限流，正式上线建议加一层简单校验。
