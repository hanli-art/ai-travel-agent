"""
高德地图 MCP ，所有天气查询，路线规划、酒店查询、地理编码、实时天气、景点查询
"""
import json
import math
import os
import re
import httpx
from typing import Dict, Any, List, Optional
from config import AMAP_KEY
from dotenv import load_dotenv
from mymcp.base_mcp import BaseMCP
from mymcp.schemas import (
    LiveWeather,
    HotleSearchParms,
    SigleHotelItem,
    RoutePlanParms,
    AmapWeatherResponse,
    HotelSearchOutput,
    FoodSearchParms,
    FoodSearchOutput,
    SingleFoodItem,
    BudgetSearchParms,
    BudgetOutput,
    BudgetItem
)
from mymcp.routeSchemas import RouteSpot, SimplifyDriveRoute,RouteDaySegment, SpotPhoto
from mymcp import map_events
# 风景名胜大类编码（注：060000实测返回购物服务，110000才是风景名胜）
SCENIC_TYPE = "110000"
# 住宿服务大类编码（酒店检索用）
HOTEL_TYPE = "100000"
# 餐饮服务大类编码（美食检索用）
FOOD_TYPE = "050000"
# 过路费估算单价（高德v3接口tolls字段恒为0，按高速收费里程估算，约0.45元/公里）
TOLL_FEE_PER_KM = 0.45
# 高德接口请求超时（秒）与失败重试次数：偶发超时是工具调用报错的主因
REQUEST_TIMEOUT = 10
RETRY_TIMES = 1


# 复用同一个异步客户端，避免每次请求新建连接的开销
_amap_client: Optional[httpx.AsyncClient] = None


async def amap_get(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """带超时与重试的高德接口异步 GET 请求（不阻塞事件循环），失败时抛出带原因的异常。
    改用 httpx.AsyncClient 替代同步 requests：原同步写法在 asyncio 事件循环里会阻塞整个循环，
    并发请求时（部署到云端后更明显）会卡死服务。"""
    global _amap_client
    if _amap_client is None or _amap_client.is_closed:
        _amap_client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT)
    last_err = None
    for attempt in range(RETRY_TIMES + 1):
        try:
            resp = await _amap_client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            last_err = e
            print(f"高德接口请求失败（第{attempt + 1}次）：{url} -> {str(e)}")
    raise ValueError(f"高德接口请求超时/失败：{str(last_err)}")

class GeomMCP(BaseMCP):
    """地理编码：获取经纬度"""
    name: str = "geo_mcp"
    description: str = "输入城市+地址，返回经纬度"
        
    async def execute(self, city: str, address: str = ""):
        url = "https://restapi.amap.com/v3/geocode/geo"
        # 注意：高德地理编码 address 为必填参数，只传city会报 MISSING_REQUIRED_PARAMS
        # 未提供详细地址时用城市名兜底，保证"只说城市"的调用也能成功
        req_params = {
            "key": AMAP_KEY,
            "city": city,
            "address": address or city,
            "output": "json",
        }
        res = await amap_get(url, req_params)
        if res.get("status") == "1":
            return res["geocodes"][0]["location"]
        else:
            raise ValueError(f"高德地理编码返回错误：{res.get('info', res)}")


class WeatherMCP(BaseMCP):
    """实时天气：获取城市实时天气"""
    name: str = "weather_mcp"
    description: str = "输入城市，返回实时天气"

    async def execute(self, city: str, address: str = "", extensions: str = "base") -> AmapWeatherResponse:
        """查询天气：extensions=base 返回实时天气，extensions=all 返回未来几天预报"""
        # 1. 地理编码拿到城市 adcode（天气接口只认 adcode，不认经纬度）
        #    address 为高德必填参数，未提供详细地址时用城市名兜底
        geo_url = "https://restapi.amap.com/v3/geocode/geo"
        geo_res = await amap_get(geo_url, {
            "key": AMAP_KEY, "city": city, "address": address or city, "output": "json"
        })
        city_location = ""
        if geo_res.get("status") == "1" and geo_res.get("geocodes"):
            adcode = geo_res["geocodes"][0].get("adcode", "")
            city_location = geo_res["geocodes"][0].get("location", "")  # 城市中心坐标，供地图定位
        else:
            raise ValueError(f"高德地理编码返回错误：{geo_res.get('info', geo_res)}")

        # 2. 根据 adcode 查询天气（base=实时 / all=预报）
        weather_url = "https://restapi.amap.com/v3/weather/weatherInfo"
        params = {
            "key": AMAP_KEY,
            "city": adcode,
            "extensions": extensions,
            "output": "json",
        }
        res = await amap_get(weather_url, params)
        if res.get("status") == "1" and (res.get("lives") or res.get("forecasts")):
            # 地图联动：天气查询后视角飞到该城市（带地理编码得到的城市中心坐标）
            try:
                map_events.push_focus(city, city_location)
            except Exception:
                pass
            return AmapWeatherResponse.model_validate(res)
        else:
            raise ValueError(f"高德天气接口返回错误：{res.get('info', res)}")

        
class RoutePlanMCP(BaseMCP):
    """路线规划：根据城市、出行方式、天数、偏好查询路线"""
    name: str = "route_plan_mcp"
    description: str = "输入城市+出行方式+天数+偏好，返回路线规划"
    # 需要直接删除的冗余字段（匹配需求：坐标串、编码、埋点、polyline等）
    DEL_FIELDS = {
        "polyline", "citycode", "adcode", "tollId", "linkId", "routeId",
        "tmcs", "taxi_cost", "districts", "orientation", "action", "assistant_action"
    }
    # 用户偏好 → 高德驾车策略编码
    PREFERENCE_STRATEGY = {
        "高速": "0", "速度": "0", "最快": "0", "时间": "0",
        "费用": "1", "收费": "1", "省钱": "1", "经济": "1",
        "距离": "2", "短": "2",
        "不走高速": "6", "国道": "6", "风景": "0",
    }
    # 高德策略编码 → 中文名称
    STRATEGY_NAMES = {
        "0": "速度优先（高速最快）", "1": "费用优先（少收费）", "2": "距离优先",
        "3": "不走快速路", "4": "常规最快", "5": "多策略", "6": "不走高速",
        "7": "不走高速且避免收费", "8": "避免收费", "9": "不走高速且避免收费",
        "10": "高快结合", "11": "多备选方案", "12": "避免左转", "13": "避免右转",
        "32": "速度最快（时间最短）", "33": "速度最快且避免收费",
    }

    @classmethod
    def resolve_strategy(cls, preference: str = "") -> str:
        """把用户的中文偏好转换为高德数字策略编码，默认速度优先"""
        if not preference:
            return "0"
        for keyword, code in cls.PREFERENCE_STRATEGY.items():
            if keyword in preference:
                return code
        # 用户直接传了数字编码
        if str(preference).isdigit():
            return str(preference)
        return "0"

    @staticmethod
    def clean_poi_to_spot(poi_raw:dict,max_img=3)->Optional[RouteSpot]:
        """
        将高德原始POI数据清洗为轻量化RouteSpot模型
        限制图片数量，拆分tag为简介数组
        """
        name=poi_raw.get("name", "")
        if not name:
            return None
        #拆分标签做为简短介绍
        tag_raw=poi_raw.get("tag", "")
        if isinstance(tag_raw, list):
            tag_list=[t.strip() for t in tag_raw if t.strip()]
        elif isinstance(tag_raw, str) and tag_raw.strip():
            tag_list=[t.strip() for t in tag_raw.split(",") if t.strip()]
        else:
            tag_list=[]
        #景点类
        type_full=poi_raw.get("type", "")
        #基础业务信息
        biz_ext=poi_raw.get("biz_ext", {})
        score=float(biz_ext.get("rating",0.0)) if biz_ext.get("rating") else 0.0
        # 高德门票字段为 biz_ext.cost（注意不是 const），为空时视为免费/未知
        ticket = biz_ext.get("cost") or "免费/以现场为准"
        open_time = biz_ext.get("open_time") or "全天开放"

        #清洗图片，最多保留max_img张图片
        photo_list=[]
        raw_photos=poi_raw.get("photos",[])
        for p in raw_photos[:max_img]:
            p_url = p.get("url")
            p_title = p.get("title")
            photo=SpotPhoto(
                photo_url=(p_url if isinstance(p_url, str) else ""),
                photo_description=(p_title if isinstance(p_title, str) else "景点实拍")
            )
            photo_list.append(photo)

        spot =RouteSpot(
            spot_name=name,
            spot_type=type_full,
            short_intro_tags=tag_list,
            score=score,
            ticket_price=ticket,
            open_hour=open_time,
            spot_images=photo_list
        )
        return spot

    # 景点类型白名单：POI 的 type 字段包含这些词才认定为真实景点，
    # 防止把商场、宾馆等非景点数据混入"沿途景点"（实测 060000/关键词检索会混入购物中心）
    SPOT_TYPE_WORDS = (
        "风景名胜", "公园", "动物园", "植物园", "游乐场", "博物馆", "纪念馆",
        "寺庙", "道观", "教堂", "清真寺", "古迹", "遗址", "景区", "湖泊", "湖;",
        "海滩", "海滨", "岛屿", "森林公园", "湿地", "瀑布", "溶洞", "山峰", "峡谷", "草原",
    )

    @staticmethod
    def is_real_scenic(poi_raw: Dict[str, Any]) -> bool:
        """按 type 名称白名单判断 POI 是否为真实景点"""
        type_full = poi_raw.get("type", "") or ""
        return any(word in type_full for word in RoutePlanMCP.SPOT_TYPE_WORDS)

    @staticmethod
    async def search_amap_scenic(city:str,keyword:str="",limit:int=5)->str:
        """
        高德POI关键词搜索景区，返回轻量化景点JSON数组
        Args:
            city: 城市名称，如大理、南昌、福州
            keyword: 可选景点关键词，为空则只搜风景名胜大类
            limit: 返回景点数量上限
    Returns:
        压缩JSON字符串，元素为RouteSpot轻量化景点数据
        """
        url="https://restapi.amap.com/v3/place/text"
        base_params={
            "key":AMAP_KEY,
            "city":city,
            "types":SCENIC_TYPE,
            "extensions":"all",
            "offset":25,   # 每页拉满，多翻几页才能捞到高评分知名景点
            "output":"json",
        }
        if keyword:
            base_params["keywords"]=keyword
        try:
            spot_result=[]
            raw_scenic_pois = []   # 供地图撒点的原始POI（含location坐标）
            # 翻前3页收集候选：高德默认排序靠前的不一定是知名景点（小广场/小庙居多），
            # 必须收满3页候选池再统一按评分排序，才能捞出高分知名景点
            for page in (1, 2, 3):
                params=dict(base_params, page=page)
                res=await amap_get(url,params)
                if res.get("status")!="1":
                    print(res.get("info",res))
                    break
                pois = res.get("pois", [])
                if not pois:
                    break
                for p in pois:
                    if not RoutePlanMCP.is_real_scenic(p):
                        continue
                    raw_scenic_pois.append({"name": p.get("name",""), "location": p.get("location","")})
                    spot=RoutePlanMCP.clean_poi_to_spot(p)
                    if spot:
                        spot_result.append(spot.model_dump())
            # 按评分降序，优先推荐高分知名景点
            spot_result.sort(key=lambda s: s.get("score", 0) or 0, reverse=True)
            spot_result = spot_result[:limit]
            # 地图联动：景点撒点 + 视角聚焦到目标城市
            try:
                map_events.push_markers("scenic", raw_scenic_pois[:8], focus_name=city)
            except Exception:
                pass
            return json.dumps(spot_result,separators=(",",":"))
        except Exception as e:
            print(f"高德地图Poi景点检索异常：{str(e)}")
            err={"error":f"高德地图返回错误：{str(e)}"}
            return json.dumps(err,separators=(",",":"))
    




    @staticmethod
    def meter_to_km(meter: int) -> int:
        """米转公里，四舍五入"""
        return math.ceil(meter / 1000) if meter % 1000 != 0 else meter // 1000
    @staticmethod
    def second_to_hour(second: int) -> float:
        """秒转小时，保留1位小数"""
        return round(second / 3600, 1)

    

# ====================== 高德原始JSON清洗核心工具函数 ======================
    @staticmethod
    def get_road_type_from_road_name(road_name: str, instruction: str = "") -> str:
        """根据道路名称+导航指令判断道路类型（step.road经常为空，需结合instruction）"""
        text = f"{road_name or ''} {instruction or ''}"
        if "高速" in text:
            return "高速"
        elif "国道" in text:
            return "国道"
        elif "山" in (road_name or "") or "盘山" in text:
            return "山路"
        else:
            return "城区道路"

    @staticmethod
    def extract_road_name(step: Dict[str, Any]) -> str:
        """优先取step.road字段，为空时从导航指令中提取道路名（如'沿G1505福州绕城高速行驶'）"""
        road = step.get("road") or ""
        if road:
            return road
        instruction = step.get("instruction") or ""
        m = re.search(r"沿(.+?)(高速|国道|省道|隧道|大桥|大道|大街|枢纽|互通|匝道|路)", instruction)
        if m:
            return m.group(1) + m.group(2)
        return ""
    @staticmethod
    def extract_pass_cities(steps: List[Dict[str, Any]]) -> List[str]:
        """提取途经城市名称（v3接口cities在step级，按顺序去重），过滤citycode/adcode编码"""
        city_names = []
        for step in steps or []:
            for city_item in step.get("cities", []):
                city_name = city_item.get("name")
                if city_name and city_name not in city_names:
                    city_names.append(city_name)
        return city_names


    @staticmethod
    async def aggregate_steps(steps: List[Dict[str, Any]], city: str = None) -> List[RouteDaySegment]:
        """
        核心路段聚合逻辑：合并连续同类型道路
        输入：原始高德step小段列表, city为目的地城市用于搜索沿线景点
        输出：聚合后的大分段RouteDaySegment数组（含景点信息）
        """
        if not steps:
            return []

        agg_segments = []
        # 初始化第一段
        current_road_name = RoutePlanMCP.extract_road_name(steps[0]) or "起点路段"
        current_road_type = RoutePlanMCP.get_road_type_from_road_name(
            steps[0].get("road") or "", steps[0].get("instruction") or "")
        start_point = current_road_name
        total_meter = int(steps[0].get("distance", 0) or 0)
        total_second = int(steps[0].get("duration", 0) or 0)
        toll_count = 1 if int(steps[0].get("tolls", 0) or 0) > 0 else 0
        tunnel_count = 0
        road_tip_list = []
        if "隧道" in (steps[0].get("instruction") or ""):
            tunnel_count += 1

        for step in steps[1:]:
            instruction = step.get("instruction") or ""
            road_type = RoutePlanMCP.get_road_type_from_road_name(step.get("road") or "", instruction)

            # 同类型道路，合并
            if road_type == current_road_type:
                total_meter += int(step.get("distance", 0) or 0)
                total_second += int(step.get("duration", 0) or 0)
                toll_count += 1 if int(step.get("tolls", 0) or 0) > 0 else 0
                # 路况提示收集 + 隧道计数
                if instruction:
                    if any(keyword in instruction for keyword in ["弯道", "长下坡", "隧道"]):
                        road_tip_list.append(instruction)
                    if "隧道" in instruction:
                        tunnel_count += 1
                # 更新当前路段终点名
                current_road_name = RoutePlanMCP.extract_road_name(step) or current_road_name
            # 不同类型道路，保存上一段，开启新分段
            else:
                # 生成配套设施描述
                service_info = []
                if toll_count > 0:
                    service_info.append(f"收费站{toll_count}个")
                if tunnel_count > 0:
                    service_info.append(f"隧道{tunnel_count}处")
                # 路况提示合并
                road_tip = "，".join(list(set(road_tip_list))) if road_tip_list else "路况平稳，正常驾驶"
                # 区间名称
                section_name = f"{start_point} → {current_road_name}"
                seg = RouteDaySegment(
                    section_name=section_name,
                    distance_km=RoutePlanMCP.meter_to_km(total_meter),
                    drive_hours=RoutePlanMCP.second_to_hour(total_second),
                    road_type=current_road_type,
                    service_info=service_info,
                    scenic_spots=[],
                    road_tips=road_tip
                )
                agg_segments.append(seg)
                # 重置当前分段
                current_road_type = road_type
                start_point = current_road_name
                current_road_name = RoutePlanMCP.extract_road_name(step) or "路段"
                total_meter = int(step.get("distance", 0) or 0)
                total_second = int(step.get("duration", 0) or 0)
                toll_count = 1 if int(step.get("tolls", 0) or 0) > 0 else 0
                tunnel_count = 0
                road_tip_list = []
                if "隧道" in (step.get("instruction") or ""):
                    tunnel_count += 1

        # 循环结束，处理最后一段
        service_info = []
        if toll_count > 0:
            service_info.append(f"收费站{toll_count}个")
        if tunnel_count > 0:
            service_info.append(f"隧道{tunnel_count}处")
        road_tip = "，".join(list(set(road_tip_list))) if road_tip_list else "路况平稳，正常驾驶"
        last_section = RouteDaySegment(
            section_name=f"{start_point} → {current_road_name}",
            distance_km=RoutePlanMCP.meter_to_km(total_meter),
            drive_hours=RoutePlanMCP.second_to_hour(total_second),
            road_type=current_road_type,
            service_info=service_info,
            scenic_spots=[],
            road_tips=road_tip
        )
        agg_segments.append(last_section)

        # ===== 聚合完成后，补充景点信息 =====
        if city and agg_segments:
            spot_json = await RoutePlanMCP.search_amap_scenic(city)
            try:
                spot_dicts = json.loads(spot_json)
                if isinstance(spot_dicts, list):
                    # 筛除非景点数据（如错误信息）
                    valid_spots = [s for s in spot_dicts if isinstance(s, dict) and "spot_name" in s]
                    if valid_spots:
                        # 只分配到非高速路段
                        stoppable = [s for s in agg_segments if s.road_type != "高速"] or agg_segments
                        for i, s in enumerate(valid_spots):
                            stoppable[i % len(stoppable)].scenic_spots.append(RouteSpot(**s))
            except Exception as e:
                print(f"高德地图Poi景点分配异常：{str(e)}")

        return agg_segments

    @staticmethod
    def generate_global_tips(path_data: Dict[str, Any]) -> List[str]:
        """生成全局出行提示：限行、高速、山路通用提醒"""
        tips = []
        # 限行判断：restriction=1代表有无法规避限行
        if path_data.get("restriction", 0) == 1:
            tips.append("本路线包含限行路段，出行前确认外地车辆限行规则")
        # 高速提示（step.road常为空，结合instruction判断）
        def _has_keyword(key: str) -> bool:
            for step in path_data.get("steps", []):
                if key in (step.get("road") or "") or key in (step.get("instruction") or ""):
                    return True
            return False
        if _has_keyword("高速"):
            tips.append("高速路段多隧道，进出隧道注意切换车灯，保持安全车距")
        # 山路提示
        if _has_keyword("山"):
            tips.append("山区弯道路段较多，雨天路面易打滑，尽量避免夜间行驶")
        # 过路费估算说明
        toll_distance_km = int(int(path_data.get("toll_distance", 0) or 0) / 1000)
        if toll_distance_km > 0:
            tips.append(f"全程收费里程约{toll_distance_km}公里，过路费按约{TOLL_FEE_PER_KM}元/公里估算，实际以高速出口计费为准")
        return tips

    @staticmethod
    async def clean_amap_raw_data(raw_resp:Dict[str,Any], dest_city:str="", origin_label:str="", dest_label:str="")->SimplifyDriveRoute:
        """
        入口主函数：原始高德API响应 → 清洗聚合 → SimplifyDriveRoute模型
        :param raw_resp: 高德驾车规划完整返回json字典
        :param dest_city: 目的地城市，用于搜索沿线景点
        :param origin_label: 出发地名称（用于展示，如：福州飞霞路86号）
        :param dest_label: 目的地名称（用于展示，如：雷峰塔）
        :return: SimplifyDriveRoute 实例（可直接model_dump_json发给LLM）
        """
        # 1. 基础状态校验
        if raw_resp.get("status") != "1":
            raise ValueError(f"高德接口请求失败，错误信息：{raw_resp.get('info')}")
        route_root = raw_resp.get("route", {})
        if not route_root:
            raise ValueError("未获取到驾车路线数据")
        path_list = route_root.get("paths", [])
        if not path_list:
            raise ValueError("无驾车方案paths数据")
        path_data = path_list[0]

        # 2. 提取顶层基础数值
        total_meter = int(path_data.get("distance", 0) or 0)
        total_second = int(path_data.get("duration", 0) or 0)
        total_toll = int(path_data.get("tolls", 0) or 0)
        # 高德v3接口tolls字段恒为0，用收费里程估算过路费（约0.45元/公里）
        toll_distance_m = int(path_data.get("toll_distance", 0) or 0)
        if total_toll <= 0 and toll_distance_m > 0:
            total_toll = math.ceil(toll_distance_m / 1000 * TOLL_FEE_PER_KM)
        strategy_code = str(path_data.get("strategy", ""))
        # 新版高德v3的strategy可能直接返回中文名称（如"速度最快"），编码则查表翻译
        if strategy_code in RoutePlanMCP.STRATEGY_NAMES:
            strategy = RoutePlanMCP.STRATEGY_NAMES[strategy_code]
        elif strategy_code:
            strategy = strategy_code
        else:
            strategy = "未知路线策略"
        origin_coord = route_root.get("origin", "")
        dest_coord = route_root.get("destination", "")
        # 用用户提供的地址名称展示（附带坐标），比纯坐标可读性更好
        origin_name = f"{origin_label}（{origin_coord}）" if origin_label else f"起点坐标{origin_coord}"
        dest_name = f"{dest_label}（{dest_coord}）" if dest_label else f"终点坐标{dest_coord}"

        # 3. 途经城市提取（cities位于step级）
        raw_steps = path_data.get("steps", [])
        pass_cities = RoutePlanMCP.extract_pass_cities(raw_steps)

        # 使用目的地城市搜索景点，若未传入则取途经城市最后一个
        scenic_city = dest_city or (pass_cities[-1] if pass_cities else "")

        # 4. 路段聚合（传入城市以搜索沿线景点）
        daily_segments = await RoutePlanMCP.aggregate_steps(raw_steps, city=scenic_city)
        # 5. 判断是否存在山路
        has_mountain_road = any(seg.road_type == "山路" for seg in daily_segments)
        # 6. 全局出行提示
        global_tips = RoutePlanMCP.generate_global_tips(path_data)

        # 7. 生成自驾路线示意图SVG（存static目录，前端内联显示；失败不阻断主流程）
        route_map_url = ""
        try:
            from mymcp.route_map import generate_route_svg
            route_map_url = generate_route_svg(
                origin_coord=origin_coord, dest_coord=dest_coord,
                origin_label=origin_label or "起点", dest_label=dest_label or "终点",
                steps=raw_steps, pass_cities=pass_cities,
                total_km=RoutePlanMCP.meter_to_km(total_meter),
                total_hours=RoutePlanMCP.second_to_hour(total_second),
                strategy=strategy,
            )
        except Exception as map_err:
            print(f"路线示意图生成失败（不影响规划）：{map_err}")

        # 地图联动：把真实驾车路径（抽稀）推给前端地图绘制
        try:
            def _c(cstr):
                try:
                    a, b = str(cstr).split(",")[:2]
                    return {"lng": float(a), "lat": float(b)}
                except (ValueError, TypeError, IndexError):
                    return None
            start_pt = _c(origin_coord)
            end_pt = _c(dest_coord)
            if start_pt and end_pt:
                from mymcp.route_map import _parse_polyline, _dedup_points
                line_pts, _city_segs = _parse_polyline(raw_steps)
                start_pt["name"] = origin_label or "起点"
                end_pt["name"] = dest_label or "终点"
                map_events.push_route(
                    route_points=_dedup_points(line_pts, min_gap=0.004),
                    start=start_pt, end=end_pt,
                    via_cities=pass_cities,
                )
        except Exception as map_ev_err:
            print(f"地图路线事件推送失败（不影响规划）：{map_ev_err}")

        # 8. 组装输出模型
        clean_model = SimplifyDriveRoute(
            origin=origin_name,
            destination=dest_name,
            pass_cities=pass_cities,
            total_distance_km=RoutePlanMCP.meter_to_km(total_meter),
            total_drive_hours=RoutePlanMCP.second_to_hour(total_second),
            total_toll_fee=total_toll,
            route_strategy=strategy,
            has_mountain_road=has_mountain_road,
            daily_segments=daily_segments,
            global_tips=global_tips,
            route_map_url=route_map_url
        )
        return clean_model


    async def execute(self, params: RoutePlanParms) -> SimplifyDriveRoute:
        city = params.endCity
        preference = params.preference
        geo = GeomMCP()
        origin = await geo.execute(params.startCity, params.origin_address or "")
        dest = await geo.execute(params.endCity, params.dest_address or "")
        url = "https://restapi.amap.com/v3/direction/driving"
        req_params = {
            "key": AMAP_KEY,
            "origin": origin,
            "destination": dest,
            "strategy": RoutePlanMCP.resolve_strategy(preference),
            "extensions": "all",
            "output": "json",
        }
        res = await amap_get(url, req_params)

        cleaned_res = await RoutePlanMCP.clean_amap_raw_data(
            res,
            dest_city=params.endCity,
            origin_label=params.origin_address or params.startCity,
            dest_label=params.dest_address or params.endCity,
        )
        return cleaned_res
        
    # 新增：获取原始JSON数据（不做Pydantic校验）

class HotelSearchMCP(BaseMCP):
    """酒店查询：根据城市、地址位置、价格范围、入住人群、入住天数查询周边酒店"""
    name: str = "hotel_m_mcp"
    description: str = "输入城市+价格范围+入住人群类型+入住天数，返回酒店列表"

    @staticmethod
    def parse_price(biz_ext: Dict[str, Any]) -> int:
        """从POI的biz_ext里解析参考价格（高德字段为cost，单位元）"""
        cost = biz_ext.get("cost") if isinstance(biz_ext, dict) else None
        if cost:
            try:
                return int(float(cost))
            except (TypeError, ValueError):
                pass
        return 0

    async def execute(self, params: HotleSearchParms) -> HotelSearchOutput:
        city = params.city
        stay_days = params.stay_days or 1

        # 1. 地理编码拿到市中心/指定位置的经纬度
        location = await GeomMCP().execute(city, params.address or "")

        # 2. 根据位置周边搜索酒店
        search_url = "https://restapi.amap.com/v3/place/around"
        search_params = {
            "key": AMAP_KEY,
            "location": location,
            "keywords": "酒店",
            "types": HOTEL_TYPE,  # 住宿服务大类
            "radius": 5000,
            "sortrule": "distance",
            "offset": 10,
            "page": 1,
            "extensions": "all",
            "output": "json",
        }
        res = await amap_get(search_url, search_params)
        if res.get("status") != "1":
            raise ValueError(f"高德酒店搜索失败：{res.get('info', res)}")

        # 地图联动：酒店POI撒点 + 视角聚焦到搜索城市（location为'lng,lat'）
        try:
            map_events.push_markers("hotel", [
                {"name": p.get("name", ""), "location": p.get("location", "")}
                for p in res.get("pois", [])[:8]
            ], focus_name=city)
        except Exception:
            pass

        # 3. 原始POI → 结构化输出模型（先按价格区间过滤）
        hotel_list = []
        for poi in res.get("pois", []):
            biz_ext = poi.get("biz_ext", {}) or {}
            price = HotelSearchMCP.parse_price(biz_ext)
            # 有价格区间要求且能解析出价格时做过滤；解析不出价格的保留（后续标注参考价）
            if (params.price_min or params.price_max) and price:
                if params.price_min and price < params.price_min:
                    continue
                if params.price_max and price > params.price_max:
                    continue
            avg_estimate = ((params.price_min or 0) + (params.price_max or 0)) // 2 if (params.price_min and params.price_max) else price
            # 评分与图片（extensions=all 时高德会返回）
            rating_raw = biz_ext.get("rating")
            photos = poi.get("photos", []) or []
            photo_url = photos[0].get("url") if photos and isinstance(photos[0], dict) else ""
            hotel_item = SigleHotelItem(
                hotel_name=poi.get("name", "未知酒店"),
                # 真实参考价优先；高德未收录价格时才用价格区间中值兜底
                price=price or avg_estimate or 0,
                crowd=params.crowd,
                address=str(poi.get("address", "") or poi.get("pname", "")),
                rating=float(rating_raw) if rating_raw else None,
                photo_url=photo_url if isinstance(photo_url, str) and photo_url else None,
            )
            hotel_list.append(hotel_item)
            if len(hotel_list) >= 5:
                break

        if not hotel_list:
            raise ValueError(f"未在{city}找到符合条件的酒店，请放宽价格或地址条件后重试")

        # 4. 生成总体入住建议（预算估算）
        prices = [h.price for h in hotel_list if h.price > 0]
        avg_price = int(sum(prices) / len(prices)) if prices else 0
        budget = avg_price * stay_days
        total_suggest = (
            f"共推荐{len(hotel_list)}家酒店；按均价{avg_price}元/晚、入住{stay_days}晚估算，"
            f"住宿总预算约{budget}元。建议提前1-3天在预订平台确认房价与房态，"
            "自驾出行优先选择带免费停车场、临近主干道出入口的酒店。"
        )
        return HotelSearchOutput(
            recommend_hotels=hotel_list,
            city=city,
            total_suggest=total_suggest,
        )


class FoodSearchMCP(BaseMCP):
    """美食查询：根据城市、菜系、人均预算查询周边推荐餐厅"""
    name: str = "food_search_mcp"
    description: str = "输入城市+菜系/美食关键词+人均预算，返回餐厅推荐列表"

    @staticmethod
    def parse_price(biz_ext: Dict[str, Any]) -> int:
        """从POI的biz_ext里解析人均消费（高德字段为cost，单位元）"""
        cost = biz_ext.get("cost") if isinstance(biz_ext, dict) else None
        if cost:
            try:
                return int(float(cost))
            except (TypeError, ValueError):
                pass
        return 0

    async def execute(self, params: FoodSearchParms) -> FoodSearchOutput:
        city = params.city

        # 1. 地理编码拿到市中心/指定位置的经纬度（address为必填，城市名兜底）
        location = await GeomMCP().execute(city, params.address or "")

        # 2. 按位置周边搜索餐厅（place/around 支持半径控制，比 place/text 更贴近"周边觅食"）
        search_params = {
            "key": AMAP_KEY,
            "location": location,
            "types": FOOD_TYPE,  # 餐饮服务大类
            "radius": 5000,
            "sortrule": "weight",
            "offset": 20,
            "page": 1,
            "extensions": "all",
            "output": "json",
        }
        if params.cuisine:
            search_params["keywords"] = params.cuisine
        res = await amap_get("https://restapi.amap.com/v3/place/around", search_params)
        if res.get("status") != "1":
            raise ValueError(f"高德美食搜索失败：{res.get('info', res)}")

        # 地图联动：餐厅POI撒点 + 视角聚焦到搜索城市
        try:
            map_events.push_markers("food", [
                {"name": p.get("name", ""), "location": p.get("location", "")}
                for p in res.get("pois", [])[:8]
            ], focus_name=city)
        except Exception:
            pass

        # 3. 原始POI → 结构化输出（过滤混合业态如宾馆餐饮；按预算过滤）
        food_list = []
        for poi in res.get("pois", []):
            type_full = poi.get("type", "") or ""
            # 只保留主业为餐饮服务的POI，过滤"住宿服务|餐饮服务"混合的宾馆
            if "餐饮服务" not in type_full:
                continue
            biz_ext = poi.get("biz_ext", {}) or {}
            price = FoodSearchMCP.parse_price(biz_ext)
            # 有预算要求且能解析出人均时做过滤；解析不出人均的保留并标注
            if params.budget and price and price > params.budget:
                continue
            rating_raw = biz_ext.get("rating")
            photos = poi.get("photos", []) or []
            photo_url = photos[0].get("url") if photos and isinstance(photos[0], dict) else ""
            open_hours = biz_ext.get("opentime") or biz_ext.get("open_time") or ""
            # 菜系取类型末段（如"餐饮服务;中餐厅;浙江菜"→浙江菜），无关键词时留空由LLM概括
            cuisine_label = params.cuisine or (type_full.split(";")[-1] if ";" in type_full else "")
            food_item = SingleFoodItem(
                food_name=poi.get("name", "未知餐厅"),
                price=price,
                cuisine=cuisine_label or None,
                rating=float(rating_raw) if rating_raw else None,
                address=str(poi.get("address", "") or poi.get("pname", "")),
                open_hours=open_hours if isinstance(open_hours, str) and open_hours else None,
                photo_url=photo_url if isinstance(photo_url, str) and photo_url else None,
            )
            food_list.append(food_item)
            if len(food_list) >= 8:
                break

        if not food_list:
            raise ValueError(f"未在{city}找到符合条件的餐厅，请更换菜系关键词或放宽预算后重试")

        # 4. 按评分降序取前5，生成总体建议
        food_list.sort(key=lambda f: f.rating or 0, reverse=True)
        food_list = food_list[:5]
        prices = [f.price for f in food_list if f.price > 0]
        avg_price = int(sum(prices) / len(prices)) if prices else 0
        total_suggest = (
            f"共推荐{len(food_list)}家{params.cuisine or ''}餐厅"
            + (f"，人均约{avg_price}元" if avg_price else "")
            + "；人均与评分为高德参考数据，实际以到店为准，"
            "热门餐厅建议错峰就餐或提前排号。"
        )
        return FoodSearchOutput(
            recommend_foods=food_list,
            city=city,
            total_suggest=total_suggest,
        )


class BudgetMCP(BaseMCP):
    """预算计算：根据交通/住宿/餐饮/门票分项成本估算旅行总预算"""
    name: str = "budget_mcp"
    description: str = "输入交通/住宿/餐饮/门票分项费用与旅行天数，返回预算明细"

    # 分项名称与口径说明（顺序固定，便于前端/LLM渲染）
    BUDGET_ITEMS = [
        ("交通费", "往返大交通+当地用车，自驾含油费与过路费"),
        ("住宿费", "按入住晚数累计"),
        ("餐饮费", "按天数×人均餐标估算"),
        ("门票费", "沿途景点门票合计"),
    ]

    async def execute(self, params: BudgetSearchParms) -> BudgetOutput:
        costs = [params.traffic_cost, params.hotel_cost, params.food_cost, params.tick_cost]
        budget_items = [
            BudgetItem(item_name=name, cost=max(0, cost), note=note)
            for (name, note), cost in zip(BudgetMCP.BUDGET_ITEMS, costs)
        ]
        total_cost = sum(item.cost for item in budget_items)
        # 日均：给了旅行天数才计算
        daily_avg = math.ceil(total_cost / params.travel_days) if params.travel_days and params.travel_days > 0 else None

        # 费用分析：找出占比最高的分项给针对性建议
        suggest_parts = [f"本次旅行总预算约{total_cost}元"]
        if daily_avg:
            suggest_parts.append(f"日均约{daily_avg}元")
        positive = [i for i in budget_items if i.cost > 0]
        if positive:
            biggest = max(positive, key=lambda i: i.cost)
            pct = round(biggest.cost / total_cost * 100) if total_cost else 0
            suggest_parts.append(f"{biggest.item_name}占比最高（约{pct}%），可优先在该项上优化")
            if biggest.item_name == "住宿费":
                suggest_parts.append("建议提前1-2周预订、错峰出行或选择景区外围性价比酒店")
            elif biggest.item_name == "交通费":
                suggest_parts.append("可对比高铁/机票折扣、提前购票或拼车分摊油费")
            elif biggest.item_name == "餐饮费":
                suggest_parts.append("可选本地家常菜馆替代景区内餐厅，人均可降30%左右")
            else:
                suggest_parts.append("可关注景点联票、免预约开放日或替代免费景点")
        else:
            suggest_parts.append("各分项费用均为0，请提供实际的分项费用后再计算")
        suggest_parts.append("以上为参考估算，实际以预订平台与现场价格为准")

        return BudgetOutput(
            budget_items=budget_items,
            total_cost=total_cost,
            daily_avg=daily_avg,
            total_suggest="；".join(suggest_parts) + "。",
        )



        
       

        