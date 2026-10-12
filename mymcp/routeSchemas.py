from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional


class SpotPhoto(BaseModel):
    """景点照片"""
    photo_url: str = Field(default="", description="照片URL")
    photo_description: str = Field(default="", description="照片描述")
class RouteSpot(BaseModel):
    """景点"""
    spot_name: str = Field(description="景点名称")
    spot_type: str = Field(description="景点类型")
    short_intro_tags: List[str] = Field(description="景点简介标签")
    score:float = Field(description="景点评分")
    ticket_price:str = Field(description="门票价格")
    open_hour:str = Field(description="开放时间")
    spot_images: List[SpotPhoto] = Field( description="景点照片集合")



# ====================== Pydantic 轻量化输出模型（供给LLM） ======================
class RouteDaySegment(BaseModel):
    """单日/单段行驶分段，聚合后简化路段"""
    section_name: str = Field(description="区间名称，如：福州鼓楼区 -> 南昌红谷滩")
    distance_km: int = Field(description="本段里程，单位km")
    drive_hours: float = Field(description="本段纯驾驶时长，小时")
    road_type: str = Field(description="道路类型：高速/国道/城区道路/山路")
    service_info: List[str] = Field(description="服务区、收费站、隧道等配套")
    scenic_spots: List[RouteSpot] = Field(description="沿途景点信息，包含图片，价格短标签、门票评分")
    road_tips: str = Field(description="本段路况、弯道、限行、风险提示")


class SimplifyDriveRoute(BaseModel):
    """清洗后给到大模型的极简路线结构，无任何地图技术冗余字段"""
    origin: str = Field(description="出发地名称+地址")
    destination: str = Field(description="目的地名称+地址")
    pass_cities: List[str] = Field(description="全程途经主要城市")
    total_distance_km: int = Field(description="全程总里程")
    total_drive_hours: float = Field(description="全程纯驾驶总时长")
    total_toll_fee: int = Field(description="全程预估过路费（元）")
    route_strategy: str = Field(description="路线策略：高速优先/不走高速/最少收费等")
    has_mountain_road: bool = Field(description="是否包含山区弯道路段")
    daily_segments: List[RouteDaySegment] = Field(description="聚合后的分段行程")
    global_tips: List[str] = Field(description="全局出行提示：限行、隧道、天气驾驶建议等")
    route_map_url: str = Field(default="", description="自驾路线示意图URL，回复开头用 ![自驾路线图](该URL) 内联展示")



