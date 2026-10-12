"""
Skill层：预算计算业务调用MCP层工具
"""

from mymcp.amap_mcp import BudgetMCP
from mymcp.schemas import BudgetSearchParms, BudgetOutput


# 下面这个BudgetSkill类提供的方法会给budget_agent调用
class BudgetSkill:

    @staticmethod
    async def estimate_trip_budget(params: BudgetSearchParms) -> BudgetOutput:
        """根据交通/住宿/餐饮/门票分项费用与旅行天数估算总预算"""
        return await BudgetMCP().execute(params)
