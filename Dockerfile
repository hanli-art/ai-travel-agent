# AI 旅游小助手 —— 生产镜像（Docker 本地部署 / Hugging Face Spaces 通用）
# HF Spaces 要求：以 UID 1000 运行，监听 app_port（默认 7860）
FROM python:3.10-slim

WORKDIR /app

# 先装依赖（利用层缓存）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制全部代码（含 .env 由运行环境注入，勿打进镜像）
COPY . .

# HF Spaces：以 user 1000 运行并赋予 /app 写权限（路线 SVG 输出需要）
RUN useradd -m -u 1000 user && chown -R user:user /app
USER user

EXPOSE 7860

# 生产环境：关闭 reload，单进程即可支撑 SSE 流式（如需更高并发可换 gunicorn）
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
