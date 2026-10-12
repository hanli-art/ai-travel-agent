import json
import os

from fastapi import FastAPI
from agents import Runner
from openai.types.responses import ResponseTextDeltaEvent
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from Agent_com.main_agent import main_agent
from hook.monitor_hook import MonitorHook
from config import AMAP_KEY
from mymcp.map_events import drain_events, merge_events


class ChatRequest(BaseModel):
    message: str
    user_id: str = 'user'


app = FastAPI(title="AI旅游智能助手")


@app.get("/api/map_config")
def map_config():
    """前端地图配置：JS API key 与安全密钥（若配置）。
    AMAP_JS_KEY 默认复用 AMAP_KEY（实测本 key 可加载 JS API 2.0）；
    若为 2021-12 后申请的新 key，请在 .env 配置 AMAP_JS_KEY 与 AMAP_SECURITY_CODE。"""
    return {
        "jsKey": os.getenv("AMAP_JS_KEY") or AMAP_KEY,
        "securityCode": os.getenv("AMAP_SECURITY_CODE") or "",
    }


@app.get("/")
def home():
    return FileResponse("index.html")


@app.post("/chat")
async def chat(req: ChatRequest):
    """非流式接口：等待智能体完整运行后一次性返回"""
    print(f"后台收到数据 req.message={req.message}")
    hook = MonitorHook()
    result = await Runner.run(main_agent, req.message, hooks=hook)
    return {"code": 200, "data": result.final_output}


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """流式接口：SSE 实时推送智能体思考过程与回复内容"""
    print(f"后台收到流式请求 req.message={req.message}")

    async def event_generator():
        hook = MonitorHook()
        current_agent_name = main_agent.name  # 用于过滤初始Agent的重复提示
        try:
            result = Runner.run_streamed(main_agent, req.message, hooks=hook)
            async for event in result.stream_events():
                # 1. 模型文本增量 → 前端实时渲染
                if event.type == "raw_response_event" and isinstance(event.data, ResponseTextDeltaEvent):
                    if event.data.delta:
                        yield _sse({"type": "delta", "content": event.data.delta})
                # 2. Agent 切换（handoff 发生，初始Agent不提示）
                elif event.type == "agent_updated_stream_event":
                    if event.new_agent.name != current_agent_name:
                        current_agent_name = event.new_agent.name
                        yield _sse({"type": "status", "content": f"🔀 任务转交：{current_agent_name}"})
                # 3. 工具调用过程提示（工具输出时顺带推送地图联动数据）
                elif event.type == "run_item_stream_event":
                    item = event.item
                    if item.type == "tool_call_item":
                        tool_name = getattr(item.raw_item, "name", "未知工具")
                        yield _sse({"type": "status", "content": f"🔧 正在调用工具：{tool_name}"})
                    elif item.type == "tool_call_output_item":
                        yield _sse({"type": "status", "content": f"✅ 工具执行完成，正在整理结果"})
                        # 地图联动：工具执行完可能有新的地图数据，合并成一帧推送
                        map_frame = merge_events(drain_events())
                        if map_frame:
                            yield _sse({"type": "map_update", "map": map_frame})
        except Exception as e:
            yield _sse({"type": "error", "content": f"服务器处理异常：{str(e)}"})
        yield _sse({"type": "done"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(payload: dict) -> str:
    """把 dict 打包成一条 SSE 数据帧"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# 服务器要挂载当前目录
app.mount("/", StaticFiles(directory=".", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
