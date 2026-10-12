"""
Skill层：路线业务调用MCP层工具

"""

from pydantic import ValidationError

from mymcp.amap_mcp import RoutePlanMCP,GeomMCP
from mymcp.schemas import RoutePlanParms
from mymcp.routeSchemas import SimplifyDriveRoute

#下面这个RouteSkill类提供的方法会给route_agent调用
class RouteSkill:
    def __init__(self):
        self.geom_mcp =GeomMCP()
    @staticmethod
    async def plan_city_route(params:RoutePlanParms)->SimplifyDriveRoute:
        """根据城市，出行方式、天数、偏好查询路线"""
        
        return await RoutePlanMCP().execute(params)