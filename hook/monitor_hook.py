"""
工具调用追踪 Hook
监控 Agent 生命周期：工具调用、handoff、Agent 切换等
"""
import logging
from typing import Any

from agents import RunHooks, RunContextWrapper, Agent, Tool
from agents.run_context import AgentHookContext

logger = logging.getLogger("agent_monitor")




class MonitorHook(RunHooks):
    """追踪工具调用和 Agent 生命周期"""

    async def on_agent_start(
        self,
        context: AgentHookContext[Any],
        agent: Agent[Any],
    ) -> None:
        logger.info(f"[Agent 启动] {agent.name}")
        print(f"[Agent 启动] {agent.name}")

    async def on_agent_end(
        self,
        context: AgentHookContext[Any],
        agent: Agent[Any],
        output: Any,
    ) -> None:
        logger.info(f"[Agent 结束] {agent.name} | 输出类型: {type(output).__name__}")
        print(f"[Agent 结束] {agent.name}")

    async def on_tool_start(
        self,
        context: RunContextWrapper[Any],
        agent: Agent[Any],
        tool: Tool,
    ) -> None:
        logger.info(f"[工具调用开始] Agent={agent.name} | Tool={tool.name}")
        print(f"🔧 [工具调用] {agent.name} → {tool.name}")

    async def on_tool_end(
        self,
        context: RunContextWrapper[Any],
        agent: Agent[Any],
        tool: Tool,
        result: str,
    ) -> None:
        result_str = str(result)
        preview = result_str[:200] + "..." if len(result_str) > 200 else result_str
        logger.info(f"[工具调用结束] Agent={agent.name} | Tool={tool.name}")
        print(f"✅ [工具返回] {tool.name} → {preview}")

    async def on_handoff(
        self,
        context: RunContextWrapper[Any],
        from_agent: Agent[Any],
        to_agent: Agent[Any],
    ) -> None:
        logger.info(f"[Handoff] {from_agent.name} → {to_agent.name}")
        print(f"🔀 [Handoff] {from_agent.name} → {to_agent.name}")
