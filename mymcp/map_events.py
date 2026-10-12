"""
地图联动事件通道（进程内队列）：
MCP 工具执行时把"要在前端地图上展示的数据"push 进队列，
main.py 的 SSE 循环在工具调用结束后 drain 并以 map_update 帧推给前端。

事件结构（与前端 travel_map.js 约定）：
  {"action": "focus",   "focus": {"name": str, "lng": float|None, "lat": float|None}}
  {"action": "markers", "markers": [{"name": str, "lng": float, "lat": float, "kind": str}], "focus": {...}|None}
  {"action": "route",   "route": {"points": [[lng,lat],...],
                                  "start": {"name": str, "lng": float, "lat": float},
                                  "end":   {"name": str, "lng": float, "lat": float}},
                         "markers": [...], "via_cities": [str]}

kind 取值：start / end / via / hotel / food / scenic
"""
import threading
from typing import Any, Dict, List, Optional

_lock = threading.Lock()
_events: List[Dict[str, Any]] = []


def _parse_coord(location: Any) -> Optional[List[float]]:
    """'lng,lat' 字符串 → [lng, lat]，失败返回 None"""
    try:
        parts = str(location).split(",")
        lng, lat = float(parts[0]), float(parts[1])
        # 简单合法性：中国范围大致经度73-136、纬度3-54
        if 70 <= lng <= 140 and 0 <= lat <= 60:
            return [lng, lat]
    except (ValueError, TypeError, IndexError):
        pass
    return None


def push_event(event: Dict[str, Any]) -> None:
    """原始事件入队（推过头的脏数据由前端容错）"""
    with _lock:
        _events.append(event)


def push_focus(name: str, location: Any = None) -> None:
    """地图视角聚焦到某城市/地点（name 必给；坐标可缺省由前端地理编码）"""
    coord = _parse_coord(location)
    push_event({
        "action": "focus",
        "focus": {"name": name, "lng": coord[0] if coord else None, "lat": coord[1] if coord else None},
    })


def push_markers(kind: str, pois: List[Dict[str, Any]], focus_name: str = "") -> None:
    """
    POI 撒点。pois 元素需含 name 与 location（'lng,lat'），缺坐标的自动丢弃。
    focus_name 非空时附带视角聚焦（无坐标，由前端按名称定位）。
    """
    markers = []
    for p in pois or []:
        if not isinstance(p, dict):
            continue
        name = str(p.get("name") or "").strip()
        coord = _parse_coord(p.get("location"))
        if not name or not coord:
            continue
        markers.append({"name": name, "lng": coord[0], "lat": coord[1], "kind": kind})
    if markers:
        push_event({
            "action": "markers",
            "markers": markers,
            "focus": {"name": focus_name, "lng": None, "lat": None} if focus_name else None,
        })


def push_route(route_points: List[List[float]],
               start: Optional[Dict[str, Any]],
               end: Optional[Dict[str, Any]],
               via_cities: Optional[List[str]] = None,
               extra_markers: Optional[List[Dict[str, Any]]] = None) -> None:
    """
    驾车路线绘制。
    route_points 为抽稀后的路径点（GCJ-02），start/end 形如 {"name": str, "lng": x, "lat": y}。
    """
    pts = []
    for p in route_points or []:
        try:
            lng, lat = float(p[0]), float(p[1])
            if 70 <= lng <= 140 and 0 <= lat <= 60:
                pts.append([round(lng, 5), round(lat, 5)])
        except (ValueError, TypeError, IndexError):
            continue
    if len(pts) < 2:
        return
    push_event({
        "action": "route",
        "route": {"points": pts, "start": start, "end": end},
        "via_cities": via_cities or [],
        "markers": extra_markers or [],
    })


def drain_events() -> List[Dict[str, Any]]:
    """取走并清空当前队列（SSE 循环每次消费）"""
    with _lock:
        out = _events[:]
        _events.clear()
    return out


def merge_events(events: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    把一次工具调用产生的多条事件合并为一帧 map_update：
    有 route 用 route（携带全部 markers），否则有 markers 用 markers，否则仅 focus。
    """
    if not events:
        return None
    route_ev = next((e for e in events if e.get("action") == "route"), None)
    markers, seen, focus = [], set(), None
    for e in events:
        f = e.get("focus")
        if f and focus is None and (f.get("lng") is not None or f.get("name")):
            focus = f
        for m in e.get("markers") or []:
            key = (m.get("name"), m.get("lng"), m.get("lat"))
            if key not in seen:
                seen.add(key)
                markers.append(m)
    if route_ev:
        return {
            "action": "route",
            "route": route_ev.get("route"),
            "via_cities": route_ev.get("via_cities") or [],
            "markers": markers,
            "focus": focus,
        }
    if markers:
        return {"action": "markers", "markers": markers, "focus": focus}
    if focus:
        return {"action": "focus", "focus": focus, "markers": []}
    return None
