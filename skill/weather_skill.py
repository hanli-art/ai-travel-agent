"""
Skill层：天气业务调用MCP层工具
"""

from mymcp.amap_mcp import WeatherMCP
from mymcp.schemas import WeatherQueryParms, WeatherReport


# 下面这个WeatherSkill类提供的方法会给weather_agent调用
class WeatherSkill:

    @staticmethod
    async def query_city_weather(params: WeatherQueryParms) -> WeatherReport:
        """查询城市实时天气与未来几天预报，合并为一份天气报告"""
        mcp = WeatherMCP()
        # 实时天气（base）+ 逐日预报（all）各查一次
        live_resp = await mcp.execute(params.city, params.address or "", extensions="base")
        forecast_resp = await mcp.execute(params.city, params.address or "", extensions="all")
        return WeatherReport(
            city=params.city,
            live=live_resp.lives[0] if live_resp.lives else None,
            forecast=forecast_resp.forecasts or None,
        )
