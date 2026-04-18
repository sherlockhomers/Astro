# 真的拿天文库去算的一组小工具。QA 那边 RAG 答不好、也不擅长回答的具体天文问题
# （比如"今晚木星在北京能看到吗""2026-4-18 的月相是什么"）都可以丢到这里算出来。
#
# 这里刻意不依赖 astropy —— astropy 装起来太重（>100MB），一个比赛项目带不动。
# 用的办法是：尽量用公式自己算 + 极简的星历数据。精度够一般科普展示用，差个几度不影响理解。
# 如果以后想上精度，可以把 skyfield / astropy 装进来，然后把 _PlanetEphemeris 换掉即可。

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

# 黄赤交角（度）。J2000 历元附近基本就是这个值，短期没必要算得更精
_OBLIQUITY_DEG = 23.4393

# 行星的"可见性"计算用的轨道要素（J2000 历元），都是平均值
# 顺序: a (AU), e, i, Ω, ω, M0 (deg), n (deg/day)
_PLANET_ELEMENTS: dict[str, dict[str, float]] = {
    "mercury": {"a": 0.38709927, "e": 0.20563593, "i": 7.00497902, "om": 48.33076593, "w": 77.45779628, "l": 252.25032350, "n": 4.09233445},
    "venus":   {"a": 0.72333566, "e": 0.00677672, "i": 3.39467605, "om": 76.67984255, "w": 131.60246718, "l": 181.97909950, "n": 1.60213034},
    "earth":   {"a": 1.00000261, "e": 0.01671123, "i": -0.00001531, "om": 0.0, "w": 102.93768193, "l": 100.46457166, "n": 0.98560912},
    "mars":    {"a": 1.52371034, "e": 0.09339410, "i": 1.84969142, "om": 49.55953891, "w": -23.94362959, "l": -4.55343205, "n": 0.52402068},
    "jupiter": {"a": 5.20288700, "e": 0.04838624, "i": 1.30439695, "om": 100.47390909, "w": 14.72847983, "l": 34.39644051, "n": 0.08308529},
    "saturn":  {"a": 9.53667594, "e": 0.05386179, "i": 2.48599187, "om": 113.66242448, "w": 92.59887831, "l": 49.95424423, "n": 0.03344414},
    "uranus":  {"a": 19.18916464, "e": 0.04725744, "i": 0.77263783, "om": 74.01692503, "w": 170.95427630, "l": 313.23810451, "n": 0.01172834},
    "neptune": {"a": 30.06992276, "e": 0.00859048, "i": 1.77004347, "om": 131.78422574, "w": 44.96476227, "l": -55.12002969, "n": 0.00597196},
}

# 中英文行星名的规整
_PLANET_ALIASES: dict[str, str] = {
    "水星": "mercury", "mercury": "mercury",
    "金星": "venus", "venus": "venus",
    "地球": "earth", "earth": "earth",
    "火星": "mars", "mars": "mars",
    "木星": "jupiter", "jupiter": "jupiter",
    "土星": "saturn", "saturn": "saturn",
    "天王星": "uranus", "uranus": "uranus",
    "海王星": "neptune", "neptune": "neptune",
}

# 主要城市简易坐标表，给"默认位置"用；前端传真实经纬度会覆盖
_CITY_COORDS: dict[str, tuple[float, float]] = {
    "北京": (39.9042, 116.4074),
    "上海": (31.2304, 121.4737),
    "广州": (23.1291, 113.2644),
    "深圳": (22.5429, 114.0596),
    "成都": (30.5728, 104.0668),
    "杭州": (30.2741, 120.1551),
    "西安": (34.3416, 108.9398),
    "南京": (32.0603, 118.7969),
    "重庆": (29.4316, 106.9123),
    "武汉": (30.5928, 114.3055),
    "天津": (39.0842, 117.2010),
    "哈尔滨": (45.8038, 126.5349),
    "香港": (22.3193, 114.1694),
    "台北": (25.0330, 121.5654),
}


# ────────────────────────────────────────────────────────────────────────────
# 通用数学 / 时间工具


def _deg_to_rad(x: float) -> float:
    return x * math.pi / 180.0


def _rad_to_deg(x: float) -> float:
    return x * 180.0 / math.pi


def _normalize_angle(deg: float) -> float:
    return deg % 360.0


def _julian_day(dt: datetime) -> float:
    # dt 必须带时区。转 UTC 后按 Meeus 第 7 章公式算 JD。
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    y, m, d = dt.year, dt.month, dt.day + (dt.hour + dt.minute / 60 + dt.second / 3600) / 24
    if m <= 2:
        y -= 1
        m += 12
    a = math.floor(y / 100)
    b = 2 - a + math.floor(a / 4)
    return math.floor(365.25 * (y + 4716)) + math.floor(30.6001 * (m + 1)) + d + b - 1524.5


def _days_since_j2000(dt: datetime) -> float:
    return _julian_day(dt) - 2451545.0


# ────────────────────────────────────────────────────────────────────────────
# 月相


@dataclass
class MoonPhaseResult:
    date: str
    phase_name: str       # 中文相名
    illumination: float   # 0~1 亮度比例
    age_days: float       # 月龄
    synodic_fraction: float  # 0~1 月相周期进度


_PHASE_NAMES = [
    (0.03, "新月"),
    (0.22, "蛾眉月"),
    (0.28, "上弦月"),
    (0.47, "盈凸月"),
    (0.53, "满月"),
    (0.72, "亏凸月"),
    (0.78, "下弦月"),
    (0.97, "残月"),
    (1.00, "新月"),
]


def moon_phase(dt: datetime | None = None) -> MoonPhaseResult:
    # 参考时间：2000-01-06 18:14 UTC 是一个已知新月
    if dt is None:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    known_new_moon_jd = 2451550.1
    jd = _julian_day(dt)
    synodic = 29.53058867  # 朔望月长度（天）
    age = (jd - known_new_moon_jd) % synodic
    fraction = age / synodic

    name = "满月"
    for threshold, label in _PHASE_NAMES:
        if fraction <= threshold:
            name = label
            break

    # 月亮被照亮的比例，用简化公式 (1 - cos(2πf)) / 2
    illumination = (1 - math.cos(2 * math.pi * fraction)) / 2

    return MoonPhaseResult(
        date=dt.strftime("%Y-%m-%d %H:%M %Z") or dt.strftime("%Y-%m-%d"),
        phase_name=name,
        illumination=round(illumination, 3),
        age_days=round(age, 1),
        synodic_fraction=round(fraction, 3),
    )


# ────────────────────────────────────────────────────────────────────────────
# 行星日心直角坐标 -> 地心赤道坐标 -> 地平坐标


def _solve_kepler(m_rad: float, e: float, max_iter: int = 30) -> float:
    # 牛顿法解开普勒方程 M = E - e sin E
    e_rad = m_rad
    for _ in range(max_iter):
        delta = (e_rad - e * math.sin(e_rad) - m_rad) / (1 - e * math.cos(e_rad))
        e_rad -= delta
        if abs(delta) < 1e-9:
            break
    return e_rad


def _planet_heliocentric(key: str, days: float) -> tuple[float, float, float]:
    el = _PLANET_ELEMENTS[key]
    a, e, i = el["a"], el["e"], _deg_to_rad(el["i"])
    om, w, l0, n = _deg_to_rad(el["om"]), _deg_to_rad(el["w"]), _deg_to_rad(el["l"]), _deg_to_rad(el["n"])

    mean_anomaly = l0 - w + n * days
    mean_anomaly = mean_anomaly % (2 * math.pi)

    e_anom = _solve_kepler(mean_anomaly, e)
    x_orb = a * (math.cos(e_anom) - e)
    y_orb = a * math.sqrt(1 - e * e) * math.sin(e_anom)

    # 轨道面转黄道面坐标
    arg_periapsis = w - om
    cos_w = math.cos(arg_periapsis)
    sin_w = math.sin(arg_periapsis)
    cos_om = math.cos(om)
    sin_om = math.sin(om)
    cos_i = math.cos(i)
    sin_i = math.sin(i)

    x = (cos_w * cos_om - sin_w * sin_om * cos_i) * x_orb + (-sin_w * cos_om - cos_w * sin_om * cos_i) * y_orb
    y = (cos_w * sin_om + sin_w * cos_om * cos_i) * x_orb + (-sin_w * sin_om + cos_w * cos_om * cos_i) * y_orb
    z = (sin_w * sin_i) * x_orb + (cos_w * sin_i) * y_orb

    return x, y, z


def _ecliptic_to_equatorial(x: float, y: float, z: float) -> tuple[float, float, float]:
    obl = _deg_to_rad(_OBLIQUITY_DEG)
    xe = x
    ye = y * math.cos(obl) - z * math.sin(obl)
    ze = y * math.sin(obl) + z * math.cos(obl)
    return xe, ye, ze


def _equatorial_to_alt_az(
    ra_rad: float,
    dec_rad: float,
    lat_rad: float,
    lst_rad: float,
) -> tuple[float, float]:
    # local hour angle
    h = lst_rad - ra_rad
    sin_alt = math.sin(dec_rad) * math.sin(lat_rad) + math.cos(dec_rad) * math.cos(lat_rad) * math.cos(h)
    alt = math.asin(sin_alt)
    cos_az = (math.sin(dec_rad) - math.sin(alt) * math.sin(lat_rad)) / (math.cos(alt) * math.cos(lat_rad))
    cos_az = max(-1.0, min(1.0, cos_az))
    az = math.acos(cos_az)
    if math.sin(h) > 0:
        az = 2 * math.pi - az
    return alt, az


def _local_sidereal_time(dt: datetime, lon_deg: float) -> float:
    # 简化 LST 算法（单位：弧度）
    jd = _julian_day(dt)
    t = (jd - 2451545.0) / 36525.0
    gst_deg = 280.46061837 + 360.98564736629 * (jd - 2451545.0) + 0.000387933 * t * t - t * t * t / 38710000.0
    gst_deg = _normalize_angle(gst_deg)
    lst_deg = _normalize_angle(gst_deg + lon_deg)
    return _deg_to_rad(lst_deg)


def _azimuth_label(az_deg: float) -> str:
    # 方位角 → 中文方位
    dirs = ["北", "东北", "东", "东南", "南", "西南", "西", "西北", "北"]
    idx = int((az_deg + 22.5) % 360 // 45)
    return dirs[idx]


@dataclass
class PlanetVisibility:
    planet_zh: str
    planet_en: str
    date: str
    location_label: str
    latitude: float
    longitude: float
    altitude_deg: float        # 地平高度
    azimuth_deg: float         # 方位角
    azimuth_label: str         # 中文方位（东、西南…）
    distance_au: float         # 与地球距离
    visible_now: bool
    advice: str                # 一句话观测建议


def planet_visibility(
    name: str,
    dt: datetime | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    city: str | None = None,
) -> PlanetVisibility | None:
    key = _PLANET_ALIASES.get((name or "").strip().lower())
    if key is None or key == "earth":
        return None

    if dt is None:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    if latitude is None or longitude is None:
        city_key = (city or "北京").strip()
        lat_lon = _CITY_COORDS.get(city_key, _CITY_COORDS["北京"])
        latitude, longitude = lat_lon
        location_label = city_key
    else:
        location_label = f"{latitude:.2f}°N, {longitude:.2f}°E"

    days = _days_since_j2000(dt)
    earth = _planet_heliocentric("earth", days)
    planet = _planet_heliocentric(key, days)

    # 地心向量
    gx = planet[0] - earth[0]
    gy = planet[1] - earth[1]
    gz = planet[2] - earth[2]
    distance = math.sqrt(gx * gx + gy * gy + gz * gz)

    xe, ye, ze = _ecliptic_to_equatorial(gx, gy, gz)
    ra = math.atan2(ye, xe) % (2 * math.pi)
    dec = math.asin(ze / math.sqrt(xe * xe + ye * ye + ze * ze))

    lst = _local_sidereal_time(dt, longitude)
    alt, az = _equatorial_to_alt_az(ra, dec, _deg_to_rad(latitude), lst)
    alt_deg = _rad_to_deg(alt)
    az_deg = _rad_to_deg(az)

    visible = alt_deg > 5  # 高度低于 5° 基本看不见
    advice = _visibility_advice(alt_deg, az_deg, key)

    planet_zh_map = {v: k for k, v in _PLANET_ALIASES.items() if k not in {"mercury", "venus", "earth", "mars", "jupiter", "saturn", "uranus", "neptune"}}
    zh_name = next((zh for zh, en in _PLANET_ALIASES.items() if en == key and "\u4e00" <= zh[0] <= "\u9fff"), key)

    return PlanetVisibility(
        planet_zh=zh_name,
        planet_en=key.capitalize(),
        date=dt.strftime("%Y-%m-%d %H:%M UTC"),
        location_label=location_label,
        latitude=round(latitude, 4),
        longitude=round(longitude, 4),
        altitude_deg=round(alt_deg, 2),
        azimuth_deg=round(az_deg, 2),
        azimuth_label=_azimuth_label(az_deg),
        distance_au=round(distance, 3),
        visible_now=visible,
        advice=advice,
    )


def _visibility_advice(alt_deg: float, az_deg: float, planet_key: str) -> str:
    if alt_deg <= 0:
        return "此时在地平线以下，看不到。一般需等几个小时后再观察。"
    if alt_deg < 5:
        return f"紧贴地平线（{alt_deg:.1f}°），受大气影响严重，建议换时间再看。"
    if alt_deg < 15:
        return f"角度较低（{alt_deg:.1f}°），朝{_azimuth_label(az_deg)}方找，最好选择视野开阔的地方。"
    if alt_deg < 45:
        return f"角度不错（{alt_deg:.1f}°），朝{_azimuth_label(az_deg)}看就能找到。"
    return f"接近头顶（{alt_deg:.1f}°），今天是观测{planet_key.capitalize()}的好时机。"


# ────────────────────────────────────────────────────────────────────────────
# 坐标转换（简化版：B1950 ↔ J2000 小偏移；支持赤道 ↔ 黄道）


@dataclass
class CoordConvertResult:
    ra_in: float   # 输入赤经 (deg)
    dec_in: float  # 输入赤纬 (deg)
    ra_out: float
    dec_out: float
    from_frame: str
    to_frame: str


def convert_coord(
    ra_deg: float,
    dec_deg: float,
    from_frame: str = "equatorial",
    to_frame: str = "ecliptic",
) -> CoordConvertResult:
    ra = _deg_to_rad(ra_deg % 360)
    dec = _deg_to_rad(dec_deg)
    obl = _deg_to_rad(_OBLIQUITY_DEG)

    # 先把输入转成笛卡尔
    cx = math.cos(dec) * math.cos(ra)
    cy = math.cos(dec) * math.sin(ra)
    cz = math.sin(dec)

    if from_frame == "equatorial" and to_frame == "ecliptic":
        ey = cy * math.cos(obl) + cz * math.sin(obl)
        ez = -cy * math.sin(obl) + cz * math.cos(obl)
        new_lon = math.atan2(ey, cx) % (2 * math.pi)
        new_lat = math.asin(ez)
    elif from_frame == "ecliptic" and to_frame == "equatorial":
        ey = cy * math.cos(obl) - cz * math.sin(obl)
        ez = cy * math.sin(obl) + cz * math.cos(obl)
        new_lon = math.atan2(ey, cx) % (2 * math.pi)
        new_lat = math.asin(ez)
    else:
        # frame 不认识就原样返
        new_lon = ra
        new_lat = dec

    return CoordConvertResult(
        ra_in=round(ra_deg, 4),
        dec_in=round(dec_deg, 4),
        ra_out=round(_rad_to_deg(new_lon), 4),
        dec_out=round(_rad_to_deg(new_lat), 4),
        from_frame=from_frame,
        to_frame=to_frame,
    )


# ────────────────────────────────────────────────────────────────────────────
# 一次性查询接口（给 router 用）


def tool_catalog() -> list[dict[str, Any]]:
    # 给前端做 UI 用；也可以作为 QA Agent 的 tool schema
    return [
        {
            "name": "moon_phase",
            "label": "月相查询",
            "description": "给一个日期，返回当天的月相名称、亮度、月龄",
            "params": [
                {"key": "date", "label": "日期", "type": "date", "required": False, "default": "今天"},
            ],
        },
        {
            "name": "planet_visibility",
            "label": "今晚看什么",
            "description": "查某颗行星此时在某个城市能不能看到、朝哪个方向",
            "params": [
                {"key": "planet", "label": "行星", "type": "select",
                 "options": ["水星", "金星", "火星", "木星", "土星", "天王星", "海王星"], "required": True},
                {"key": "city", "label": "城市", "type": "string", "required": False, "default": "北京"},
                {"key": "date", "label": "日期时间", "type": "datetime", "required": False, "default": "现在"},
            ],
        },
        {
            "name": "coord_convert",
            "label": "坐标系转换",
            "description": "赤道坐标 ↔ 黄道坐标 快速换算",
            "params": [
                {"key": "ra", "label": "RA / 黄经 (°)", "type": "number", "required": True},
                {"key": "dec", "label": "Dec / 黄纬 (°)", "type": "number", "required": True},
                {"key": "from_frame", "label": "源坐标", "type": "select",
                 "options": ["equatorial", "ecliptic"], "required": True, "default": "equatorial"},
                {"key": "to_frame", "label": "目标坐标", "type": "select",
                 "options": ["equatorial", "ecliptic"], "required": True, "default": "ecliptic"},
            ],
        },
    ]
