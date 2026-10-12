"""
Skill层：美食业务调用MCP层工具
"""

from mymcp.amap_mcp import FoodSearchMCP
from mymcp.schemas import FoodSearchParms, FoodSearchOutput


# 下面这个FoodSkill类提供的方法会给food_agent调用
class FoodSkill:

    @staticmethod
    async def search_city_foods(params: FoodSearchParms) -> FoodSearchOutput:
        """根据城市、菜系、人均预算查询周边推荐餐厅"""
        return await FoodSearchMCP().execute(params)
