from ctypes import addressof

from pydantic import BaseModel,Field
from typing import List,Optional

# ====================== 1. 实时天气子模型（lives 字段） ======================
class LiveWeather(BaseModel):
    """高德实时天气数据模型"""
    province: str = Field(..., description="省份名")
    city: str = Field(..., description="城市名")
    adcode: str = Field(..., description="城市编码")
    weather: str = Field(..., description="天气状况（晴/阴/雨等）")
    temperature: str = Field(..., description="气温（摄氏度）")
    winddirection: str = Field(..., description="风向")
    windpower: str = Field(..., description="风力等级")
    humidity: str = Field(..., description="相对湿度（%）")
    reporttime: str = Field(..., description="数据发布时间")

# ====================== 2. 逐日预报子模型（forecasts → casts 字段） ======================
class ForecastDayDetail(BaseModel):
    """单日天气预报详情"""
    date: str = Field(..., description="日期")
    week: str = Field(..., description="星期几")
    dayweather: str = Field(..., description="白天天气")
    nightweather: str = Field(..., description="夜间天气")
    daytemp: str = Field(..., description="白天温度")
    nighttemp: str = Field(..., description="夜间温度")
    daywind: str = Field(..., description="白天风向")
    nightwind: str = Field(..., description="夜间风向")
    daypower: str = Field(..., description="白天风力")
    nightpower: str = Field(..., description="夜间风力")


# ====================== 3. 城市预报父模型（forecasts 字段） ======================
class CityForecast(BaseModel):
    """
    城市预报天气模型
    """
    city: str = Field(..., description="城市名")
    adcode: str = Field(..., description="城市编码")
    province: str = Field(..., description="省份")
    reporttime: str = Field(..., description="发布时间")
    casts: List[ForecastDayDetail] = Field(..., description="未来多天预报列表")    

#天气查询
class WeatherInputParms(BaseModel):
    city: str = Field(description="目标城市编码")
    extensions: Optional[str] = Field(default=None, description="扩展参数,如：base,all")
    output: Optional[str] = Field(default="json", description="输出格式,如：json,xml")

class AmapWeatherResponse(BaseModel):
    """
    高德地图天气API 统一响应模型
    支持：实时天气接口 + 预报天气接口
    """
    status: str = Field(..., description="返回状态：1=成功，0=失败")
    count: str = Field(..., description="返回结果总数")
    info: str = Field(..., description="返回信息说明")
    infocode: str = Field(..., description="返回状态码（10000=成功）")

    # 实时天气（基础天气接口返回）
    lives: Optional[List[LiveWeather]] = Field(None, description="实时天气数据")
    
    # 预报天气（预报接口返回）
    forecasts: Optional[List[CityForecast]] = Field(None, description="预报天气数据")  


  #景点查询
class AttractionsSearch(BaseModel):
    city: str = Field(description="目标城市")
    tags: Optional[List[str]] = Field(default=None, description="景点标签,多个标签用逗号隔开,如：上海 亲子游")
    crowd: Optional[str] = Field(default=None, description="人群类型,如：学生、教师、学生等")


#酒店查询
class  HotleSearchParms(BaseModel):
    city: str = Field(description="目标城市")
    price_min: Optional[int] = Field(default=None, description="最低价格,单位：元/人")
    price_max: Optional[int] = Field(default=None, description="最高价格,单位：元/人")
    crowd: Optional[str] = Field(default=None, description="入住人群类型,如：学生、教师、学生等")
    stay_days: Optional[int] = Field(default=None, description="入住天数")
    address: Optional[str] = Field(default=None, description="酒店地址")
    
  
#美食查询
class FoodSearchParms(BaseModel):
    city: str = Field(description="目标城市")
    cuisine: Optional[str] = Field(default=None, description="美食类型,菜系如：中餐、西餐、日餐、杭帮菜、川菜等")
    budget: Optional[int] = Field(default=None, description="人均预算,单位：元")
    address: Optional[str] = Field(default=None, description="觅食位置,如景区/商圈/街道名称,默认市中心")



class WeatherOutputParms(BaseModel):
    status: str = Field(description="接口状态: 1成功 0失败")
    info: str = Field(description="接口返回信息")
    count: Optional[str] = Field(default="", description="返回路径条数")
    weather: Optional[dict] = Field(default=None, description="天气数据")


#预算计算
class BudgetSearchParms(BaseModel):
    traffic_cost:int=Field(description="交通成本,单位：元")
    hotel_cost:int=Field(description="酒店成本,单位：元")
    food_cost:int=Field(description="美食成本,单位：元")
    tick_cost:int=Field(description="景点门票成本,单位：元")
    travel_days: Optional[int] = Field(default=None, description="旅行总天数,用于计算日均花费")

#=======结构化输出模型（强制大模型返回标准JSON)
class SigleHotelItem(BaseModel):
    hotel_name: str = Field(description="酒店名称")
    price: int = Field(description="酒店价格,单位：元/人")
    crowd: Optional[str] = Field(default=None, description="入住人群类型,如：学生、教师、学生等")
    address: Optional[str] = Field(default=None, description="酒店地址")
    rating: Optional[float] = Field(default=None, description="平台评分,如4.5")
    photo_url: Optional[str] = Field(default=None, description="酒店图片URL")

class HotelSearchOutput(BaseModel):
    recommend_hotels: List[SigleHotelItem] = Field(description="酒店列表")
    city: str = Field(description="目标城市")
    total_suggest: Optional[str] = Field(default=None, description="入住的总体建议")



class SingleFoodItem(BaseModel):
    food_name: str = Field(description="餐厅/美食名称")
    price: int = Field(description="人均消费,单位：元,未知为0")
    cuisine: Optional[str] = Field(default=None, description="美食类型,菜系如：中餐、西餐、日餐等")
    rating: Optional[float] = Field(default=None, description="平台评分,如4.7")
    address: Optional[str] = Field(default=None, description="餐厅地址")
    open_hours: Optional[str] = Field(default=None, description="营业时间")
    photo_url: Optional[str] = Field(default=None, description="餐厅图片URL")

class FoodSearchOutput(BaseModel):
    recommend_foods: List[SingleFoodItem] = Field(description="美食列表")
    city: str = Field(description="目标城市")
    total_suggest: Optional[str] = Field(default=None, description="美食的总体建议")


#=========天气查询 参数+输出模型（LLM用）
class WeatherQueryParms(BaseModel):
    city: str = Field(description="目标城市名称,如：杭州")
    address: Optional[str] = Field(default=None, description="城市内详细地址,可选,如：西湖区")

class WeatherReport(BaseModel):
    """天气查询统一输出：实时天气 + 未来几天预报"""
    city: str = Field(description="查询城市")
    live: Optional[LiveWeather] = Field(default=None, description="实时天气数据")
    forecast: Optional[List[CityForecast]] = Field(default=None, description="未来几天预报数据")


#=========预算计算 输出模型
class BudgetItem(BaseModel):
    item_name: str = Field(description="费用项目名称,如：交通费")
    cost: int = Field(description="该项费用,单位：元")
    note: Optional[str] = Field(default=None, description="费用口径说明")

class BudgetOutput(BaseModel):
    """预算计算输出：分项明细+总预算+日均"""
    budget_items: List[BudgetItem] = Field(description="分项费用明细")
    total_cost: int = Field(description="总预算,单位：元")
    daily_avg: Optional[int] = Field(default=None, description="日均花费,单位：元/天")
    total_suggest: Optional[str] = Field(default=None, description="预算分析与优化建议")


#=========路线规划  数据 +输出模型
class RoutePlanParms(BaseModel):
    startCity: str = Field(description="出发所在城市")
    origin_address: Optional[str] = Field(default=None, description="出发地址")
    endCity: str = Field(description="目的地所在城市")
    dest_address: Optional[str] = Field(default=None, description="目的地地址")
    travel_mode: Optional[str] = Field(default=None, description="出行方式,如：驾车、步行、骑行等")
    travel_days: Optional[int] = Field(default=None, description="出行天数")
    preference: Optional[str] = Field(default=None, description="偏好,如：高速、国道、风景优先等")

class RouteDayItem(BaseModel):
    """"单日行程明细"""
    day_num: int = Field(description="第几天行程")
    spot_name:str=Field(description="景点名称")
    play_duration: Optional[str]=Field(description="建议游玩时间")
    traffic_between_spots:str=Field(description="景点之间的交通方式")
    lunch_recommend: Optional[str] = Field(default=None, description="附近午餐推荐")


'''路线规划输出模型
{
  "status": "1",
  "route": {               // dict
    "origin": "119.28xxx,26.11xxx",
    "destination": "100.22xxx,25.60xxx",
    "paths": [             // list 多条路线方案
      {
        "distance": "2680000", // 总米数
        "duration": "300000",  // 总秒数
        "highway_distance": "2500000",
        "tolls": "1200",
        "steps": [           // list 分段导航步骤
          {
            "instruction": "沿福飞南路向南行驶2公里...",
            "distance": "2000"
          }
        ]
      }
    ]
  }
}
'''

class RoutePlanOutput(BaseModel):
    """路线规划输出模型"""
    city: str
    total_days: int
    travel_mode: str
    full_route: List[RouteDayItem]
    total_distance_km: float
    total_time_hour: float
    route_tips: str = Field(description="路线避坑、出行小贴士")

    
