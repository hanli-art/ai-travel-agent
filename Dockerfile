# AI 旅游小助手 —— 后端生产镜像
# 部署说明见 APK部署说明.md
FROM python:3.10-slim

WORKDIR /app

# 先装依赖（利用层缓存）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制全部代码（含 .env 由运行环境注入，勿打进镜像）
COPY . .

EXPOSE 8000

# 生产环境：关闭 reload，单进程即可支撑 SSE 流式（如需更高并发可换 gunicorn）
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
