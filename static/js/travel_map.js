/* ===== 行程地图模块（高德 JS API 2.0） =====
 * 职责：加载高德地图 → 消费后端 map_update 帧 → 绘制路线/撒点/视角联动
 * 联动数据由后端 MCP 工具执行时产生（mymcp/map_events.py），经 SSE map_update 帧推送
 */
const TravelMap = (function () {
    let map = null;          // AMap.Map 实例
    let AMapRef = null;      // window.AMap 引用
    let overlays = [];       // 当前覆盖物（每次更新前清空）
    let ready = false;

    /* 标记类型配色 */
    const KIND_STYLE = {
        start:  '#00b34a',   // 起点：绿
        end:    '#ff4444',   // 终点：红
        via:    '#64748b',   // 途经：灰蓝
        hotel:  '#2f7eff',   // 酒店：蓝
        food:   '#ff9800',   // 美食：橙
        scenic: '#9c27b0',   // 景点：紫
    };

    function setStatus(text) {
        const el = document.getElementById('mapStatus');
        if (el) el.textContent = text;
    }

    function loadScript(src) {
        return new Promise((resolve, reject) => {
            const s = document.createElement('script');
            s.src = src;
            s.onload = resolve;
            s.onerror = () => reject(new Error('高德 JS API 脚本加载失败'));
            document.head.appendChild(s);
        });
    }

    async function init() {
        const box = document.getElementById('mapContainer');
        try {
            const cfg = await fetch('/api/map_config').then(r => {
                if (!r.ok) throw new Error('map_config HTTP ' + r.status);
                return r.json();
            });
            if (!cfg.jsKey) throw new Error('未配置地图 key');
            // 新 key 需要安全密钥；必须在 SDK 加载前设置
            if (cfg.securityCode) {
                window._AMapSecurityConfig = { securityJsCode: cfg.securityCode };
            }
            await loadScript('https://webapi.amap.com/maps?v=2.0&key=' + encodeURIComponent(cfg.jsKey));
            AMapRef = window.AMap;
            if (!AMapRef) throw new Error('AMap 未定义（key 可能无效）');
            map = new AMapRef.Map('mapContainer', {
                zoom: 7,
                center: [119.3, 26.08],   // 初始视角：福建沿海（与演示主题一致）
                viewMode: '2D',
            });
            // 地图对象创建成功即可接收联动数据；complete 仅用于更新状态文案
            // （实测部分环境 complete 事件可能延迟/不触发，不能作为 ready 依据）
            ready = true;
            map.on('complete', () => {
                setStatus('📍 行程地图已就绪，提问后地图自动联动');
            });
            return true;
        } catch (e) {
            console.error('地图初始化失败：', e);
            box.innerHTML = '<div class="map-fallback">🗺️ 地图加载失败：' + escapeHtml(e.message || '未知错误') +
                '<br><small>请检查 .env 中 AMAP_JS_KEY 是否为"Web端(JS API)"类型 key，' +
                '2021-12后申请的 key 还需配置 AMAP_SECURITY_CODE 安全密钥</small></div>';
            setStatus('地图不可用');
            return false;
        }
    }

    function escapeHtml(text) {
        const d = document.createElement('div');
        d.textContent = text;
        return d.innerHTML;
    }

    function clearOverlays() {
        overlays.forEach(o => { try { map.remove(o); } catch (e) { /* 忽略 */ } });
        overlays = [];
    }

    function makeMarker(m) {
        const color = KIND_STYLE[m.kind] || KIND_STYLE.via;
        const content =
            '<div class="amap-pin" style="--pin:' + color + '">' +
            '<span class="pin-dot"></span>' +
            (m.name ? '<span class="pin-label">' + escapeHtml(m.name) + '</span>' : '') +
            '</div>';
        return new AMapRef.Marker({
            position: [m.lng, m.lat],
            content: content,
            anchor: 'bottom-center',
            zIndex: 120,
        });
    }

    /* 视角聚焦：有坐标直接飞，无坐标用 Geocoder 按名称定位 */
    function focusTo(f) {
        if (!map || !f) return;
        const jump = (lng, lat, zoom) => map.setZoomAndCenter(zoom || 11, [lng, lat]);
        if (f.lng != null && f.lat != null) {
            jump(f.lng, f.lat);
            return;
        }
        const name = (f.name || '').trim();
        if (!name) return;
        AMapRef.plugin('AMap.Geocoder', function () {
            const geo = new AMapRef.Geocoder({ city: '全国' });
            // 短名称（如"漳州"）补"市"提高命中率
            const query = name.length >= 3 ? name : name + '市';
            geo.getLocation(query, function (status, result) {
                if (status === 'complete' && result.geocodes && result.geocodes.length) {
                    const loc = result.geocodes[0].location;
                    jump(loc.lng, loc.lat);
                }
            });
        });
    }

    /* 应用一帧地图更新（后端 map_update 帧的 map 字段） */
    function apply(data) {
        if (!map || !ready || !data) return;
        const action = data.action;

        // focus：只切换视角，不清除已有标注（如天气查询后飞到城市）
        // 注意：focus 帧的 markers 是空数组（truthy），必须判长度
        if (action === 'focus' && !(data.markers && data.markers.length)) {
            if (data.focus) {
                focusTo(data.focus);
                if (data.focus.name) setStatus('📍 已定位到 ' + data.focus.name);
            }
            return;
        }

        clearOverlays();
        const fitTargets = [];
        const statusParts = [];

        // 1. 驾车路线
        if (data.route && Array.isArray(data.route.points) && data.route.points.length >= 2) {
            const line = new AMapRef.Polyline({
                path: data.route.points,
                strokeColor: '#2f7eff',
                strokeWeight: 6,
                strokeOpacity: 0.95,
                lineJoin: 'round',
                showDir: true,
                zIndex: 60,
            });
            map.add(line);
            overlays.push(line);
            fitTargets.push(line);
            const s = data.route.start, e = data.route.end;
            [['start', s], ['end', e]].forEach(([kind, p]) => {
                if (p && p.lng != null && p.lat != null) {
                    const mk = makeMarker({ name: p.name || '', lng: p.lng, lat: p.lat, kind: kind });
                    map.add(mk);
                    overlays.push(mk);
                    fitTargets.push(mk);
                }
            });
            if (s && e) statusParts.push('📍 ' + (s.name || '起点') + ' → ' + (e.name || '终点'));
            if (data.via_cities && data.via_cities.length) {
                statusParts.push('途经 ' + data.via_cities.join('、'));
            }
        }

        // 2. POI 撒点
        const markers = (data.markers || []).filter(m => m.lng != null && m.lat != null);
        markers.forEach(m => {
            const mk = makeMarker(m);
            map.add(mk);
            overlays.push(mk);
            fitTargets.push(mk);
        });
        if (markers.length) {
            const names = markers.map(m => m.name);
            statusParts.push('标注 ' + names.length + ' 个位置：' +
                names.slice(0, 4).join('、') + (names.length > 4 ? '等' : ''));
        }

        // 状态条
        if (statusParts.length) setStatus(statusParts.join('；'));
        else setStatus('📍 地图已更新');

        // 3. 视角：优先适配覆盖物，无覆盖物时按 focus 聚焦
        if (fitTargets.length) {
            map.setFitView(fitTargets, false, [70, 70, 70, 70]);
        } else if (data.focus) {
            focusTo(data.focus);
        }
    }

    const api = { init: init, apply: apply };
    /* 挂到 window：app.js 通过 window.TravelMap 判断与调用（const 声明默认不挂 window） */
    window.TravelMap = api;
    return api;
})();

/* 页面就绪后初始化地图 */
document.addEventListener('DOMContentLoaded', function () {
    TravelMap.init();
});
