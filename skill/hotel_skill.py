"""
Skill层：酒店业务调用MCP层工具
"""
from mymcp.amap_mcp import HotelSearchMCP
from mymcp.schemas import HotleSearchParms, HotelSearchOutput


# 下面这个HotelSkill类提供的方法会给hotel_agent调用
class HotelSkill:

    @staticmethod
    async def search_city_hotels(params: HotleSearchParms) -> HotelSearchOutput:
        """根据城市、地址、价格范围、入住人群、入住天数查询周边酒店"""
        return await HotelSearchMCP().execute(params)
