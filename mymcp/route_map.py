"""
路线示意图生成：把高德驾车规划的 polyline 路径点渲染成 SVG 路线图卡片。
纯前端可显示的静态图（存入 static 目录），不依赖任何地图服务与 key，规避静态地图 API 账号权限问题。
合规说明：仅绘制路线形状与城市文字标注，不含任何行政区划边界图。
"""
import os
import time
from typing import List, Dict, Any


def _parse_polyline(steps: List[Dict[str, Any]]):
    """
    从驾车规划 steps 中收集坐标点（GCJ-02，lng,lat）
    :return: (全部点列表, 城市归属段列表 [(城市名, 该城市覆盖的点)])
    """
    pts = []
    city_segs: Dict[str, List[List[float]]] = {}
    for step in steps:
        raw = step.get("polyline", "") or ""
        step_pts = []
        for pair in raw.split(";"):
            pair = pair.strip()
            if not pair or "," not in pair:
                continue
            try:
                lng, lat = pair.split(",")[:2]
                step_pts.append([float(lng), float(lat)])
            except (ValueError, TypeError):
                continue
        if not step_pts:
            continue
        pts.extend(step_pts)
        cities = step.get("cities") or []
        city_name = cities[0].get("name", "") if cities else ""
        if city_name:
            city_segs.setdefault(city_name, []).extend(step_pts)
    return pts, city_segs


def _dedup_points(pts: List[List[float]], min_gap: float = 0.005) -> List[List[float]]:
    """按最小间距抽稀，控制点数且保留路线形状"""
    if not pts:
        return pts
    result = [pts[0]]
    for p in pts[1:]:
        q = result[-1]
        if abs(p[0] - q[0]) + abs(p[1] - q[1]) >= min_gap:
            result.append(p)
    if result[-1] != pts[-1]:
        result.append(pts[-1])
    return result


def _esc(text: str) -> str:
    """XML 转义"""
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def generate_route_svg(origin_coord: str,
                       dest_coord: str,
                       origin_label: str,
                       dest_label: str,
                       steps: List[Dict[str, Any]],
                       pass_cities: List[str],
                       total_km: int,
                       total_hours: float,
                       strategy: str,
                       static_dir: str = "static") -> str:
    """
    生成 SVG 路线示意图并写入 static 目录
    :return: 可供前端 <img> 直接加载的URL，如 /static/route_map_20261008_013000.svg
    """
    line_pts, city_segs = _parse_polyline(steps)
    line_pts = _dedup_points(line_pts)

    def _coord(c: str):
        try:
            lng, lat = c.split(",")[:2]
            return [float(lng), float(lat)]
        except (ValueError, AttributeError, TypeError):
            return None

    origin_pt = _coord(origin_coord)
    dest_pt = _coord(dest_coord)

    # 途经城市标注点在投影后过滤计算（见下）

    if not line_pts:
        # 无 polyline 数据时用起终点直线兜底
        line_pts = [p for p in (origin_pt, dest_pt) if p]

    # ---- 投影计算（等距圆柱近似，纬度用 cos 修正形状） ----
    # 城市标注点均派生自路线点，边界只需 路线点+起终点
    all_pts = list(line_pts) + [p for p in (origin_pt, dest_pt) if p]
    if len(all_pts) < 2:
        return ""
    lngs = [p[0] for p in all_pts]
    lats = [p[1] for p in all_pts]
    min_lng, max_lng = min(lngs), max(lngs)
    min_lat, max_lat = min(lats), max(lats)
    mid_lat = (min_lat + max_lat) / 2 or 1.0
    kx = max((max_lng - min_lng) * 0.0175 * (111.32 * mid_lat / 90), 1e-6)  # 修正后横向跨度
    ky = max((max_lat - min_lat) * 110.57 / 90 * 1.8, 1e-6)                 # 纵向跨度

    W, H = 960, 520
    PAD_L, PAD_R, PAD_T, PAD_B = 70, 70, 84, 96
    dx = max(max_lng - min_lng, 1e-6)
    dy = max(max_lat - min_lat, 1e-6)

    def px(lng: float) -> float:
        return PAD_L + (lng - min_lng) / dx * (W - PAD_L - PAD_R)

    def py(lat: float) -> float:
        return H - PAD_B - (lat - min_lat) / dy * (H - PAD_T - PAD_B)

    # 途经城市过滤：起/终点所在城市不标注（其标签已单独展示），最多标5个
    def _near(a, b, thr=0.035):
        return a is not None and b is not None and abs(a[0] - b[0]) + abs(a[1] - b[1]) < thr

    labeled_cities = []
    for n, cpoints in city_segs.items():
        if len(labeled_cities) >= 5:
            break
        covers_endpoint = any(
            _near(cp, ep) for cp in cpoints for ep in (origin_pt, dest_pt)
        )
        if covers_endpoint:
            continue
        if len(cpoints) >= 2:
            a, b = cpoints[0], cpoints[-1]
            labeled_cities.append((n, [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]))

    # ---- SVG 组装 ----
    path_d = "M " + " L ".join(f"{px(p[0]):.1f},{py(p[1]):.1f}" for p in line_pts)

    def label_anchor(x: float) -> str:
        return "start" if x < W / 2 else "end"

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" font-family="Microsoft YaHei, PingFang SC, sans-serif">',
        # 背景卡片 + 淡网格
        f'<rect x="0" y="0" width="{W}" height="{H}" rx="16" fill="#f8fafc"/>',
        f'<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="15" fill="none" stroke="#e2e8f0"/>',
    ]
    for gx in range(W // 80 + 1):
        parts.append(f'<line x1="{gx * 80}" y1="0" x2="{gx * 80}" y2="{H}" stroke="#eef2f7" stroke-width="1"/>')
    for gy in range(H // 80 + 1):
        parts.append(f'<line x1="0" y1="{gy * 80}" x2="{W}" y2="{gy * 80}" stroke="#eef2f7" stroke-width="1"/>')

    # 标题与信息
    parts.append(f'<text x="{W / 2}" y="40" text-anchor="middle" font-size="21" font-weight="700" fill="#1f2d3d">'
                 f'自驾路线示意图</text>')
    parts.append(f'<text x="{W / 2}" y="64" text-anchor="middle" font-size="14" fill="#64748b">'
                 f'{_esc(strategy)} · 全程约 {total_km} km · 驾驶约 {total_hours} 小时</text>')

    # 路线：底层光晕 + 主线
    if len(line_pts) >= 2:
        parts.append(f'<path d="{path_d}" fill="none" stroke="#2f7eff22" stroke-width="13" '
                     f'stroke-linecap="round" stroke-linejoin="round"/>')
        parts.append(f'<path d="{path_d}" fill="none" stroke="#2f7eff" stroke-width="5.5" '
                     f'stroke-linecap="round" stroke-linejoin="round"/>')

    # 途经城市标注
    for name, p in labeled_cities:
        x, y = px(p[0]), py(p[1])
        ax = label_anchor(x)
        tx = x + 10 if ax == "start" else x - 10
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#fff" stroke="#64748b" stroke-width="2"/>')
        parts.append(f'<text x="{tx:.1f}" y="{y + 5:.1f}" text-anchor="{ax}" font-size="14.5" fill="#475569">'
                     f'{_esc(name)}</text>')

    # 起点 / 终点
    if origin_pt:
        x, y = px(origin_pt[0]), py(origin_pt[1])
        ax = label_anchor(x)
        tx = x + 12 if ax == "start" else x - 12
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="8" fill="#00b34a" stroke="#fff" stroke-width="3"/>')
        parts.append(f'<text x="{tx:.1f}" y="{y - 14:.1f}" text-anchor="{ax}" font-size="16" '
                     f'font-weight="700" fill="#0b7a37">{_esc(origin_label)}</text>')
    if dest_pt:
        x, y = px(dest_pt[0]), py(dest_pt[1])
        ax = label_anchor(x)
        tx = x + 12 if ax == "start" else x - 12
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="8" fill="#ff4444" stroke="#fff" stroke-width="3"/>')
        parts.append(f'<text x="{tx:.1f}" y="{y - 14:.1f}" text-anchor="{ax}" font-size="16" '
                     f'font-weight="700" fill="#c11d1d">{_esc(dest_label)}</text>')

    # 底部图例
    legend_y = H - 34
    parts.append(f'<circle cx="{W / 2 - 190}" cy="{legend_y - 4}" r="6" fill="#00b34a"/>'
                 f'<text x="{W / 2 - 178}" y="{legend_y}" font-size="13.5" fill="#475569">起点</text>')
    parts.append(f'<circle cx="{W / 2 - 110}" cy="{legend_y - 4}" r="6" fill="#ff4444"/>'
                 f'<text x="{W / 2 - 98}" y="{legend_y}" font-size="13.5" fill="#475569">终点</text>')
    parts.append(f'<line x1="{W / 2 - 46}" y1="{legend_y - 4}" x2="{W / 2 - 10}" y2="{legend_y - 4}" '
                 f'stroke="#2f7eff" stroke-width="5" stroke-linecap="round"/>'
                 f'<text x="{W / 2}" y="{legend_y}" font-size="13.5" fill="#475569">驾车路线</text>')

    parts.append('</svg>')
    svg = "".join(parts)

    os.makedirs(static_dir, exist_ok=True)
    fname = f"route_map_{time.strftime('%Y%m%d_%H%M%S')}.svg"
    with open(os.path.join(static_dir, fname), "w", encoding="utf-8") as f:
        f.write(svg)
    # 清理7天前的旧图，避免 static 目录堆积
    cutoff = time.time() - 7 * 86400
    try:
        for f_ in os.listdir(static_dir):
            if f_.startswith("route_map_") and f_.endswith(".svg"):
                fp = os.path.join(static_dir, f_)
                if os.path.getmtime(fp) < cutoff:
                    os.remove(fp)
    except OSError:
        pass
    return f"/static/{fname}"
