from __future__ import annotations

import re

_NORMALIZATION_RULES: list[tuple[tuple[str, ...], str]] = [
    (("supermassive black hole", "supermassive black holes"), "超大质量黑洞"),
    (("stellar black hole", "stellar black holes"), "恒星级黑洞"),
    (("intermediate black hole", "intermediate black holes"), "中等质量黑洞"),
    (("black hole", "black holes"), "黑洞"),
    (("spiral galaxy", "spiral galaxies"), "旋涡星系"),
    (("elliptical galaxy", "elliptical galaxies"), "椭圆星系"),
    (("irregular galaxy", "irregular galaxies"), "不规则星系"),
    (("planetary nebula", "planetary nebulae", "planetay nebulae"), "行星状星云"),
    (("emission nebula", "emission nebulae"), "发射星云"),
    (("reflection nebula", "reflection nebulae"), "反射星云"),
    (("nebula", "nebulae"), "星云"),
    (("comet", "comets"), "彗星"),
    (("asteroid belt",), "小行星带"),
    (("asteroid", "asteroids"), "小行星"),
    (("kuiper belt",), "柯伊伯带"),
    (("galaxy", "galaxies"), "星系"),
    (("moon",), "月球"),
    (("sun",), "太阳"),
    (("mercury",), "水星"),
    (("venus",), "金星"),
    (("earth",), "地球"),
    (("mars",), "火星"),
    (("jupiter",), "木星"),
    (("saturn",), "土星"),
    (("uranus",), "天王星"),
    (("neptune",), "海王星"),
    (("pluto",), "冥王星"),
    (("callisto",), "木卫四"),
    (("europa",), "木卫二"),
    (("ganymede",), "木卫三"),
    ((" io ",), "木卫一"),
    (("titan",), "土卫六"),
    (("white dwarf", "white dwarfs"), "白矮星"),
    (("neutron star", "neutron stars", "pulsar", "pulsars"), "中子星"),
    (("giant star", "giant stars", "supergiant", "supergiants"), "巨星"),
    (("constellation", "constellations"), "星座"),
    (("dwarf planet", "dwarf planets"), "矮行星"),
    (("exoplanet", "exoplanets"), "系外行星"),
    (("space station",), "空间站"),
]

_FAMILY_RULES: list[tuple[tuple[str, ...], str]] = [
    (
        (
            "太阳",
            "月球",
            "水星",
            "金星",
            "地球",
            "火星",
            "木星",
            "土星",
            "天王星",
            "海王星",
            "冥王星",
            "木卫一",
            "木卫二",
            "木卫三",
            "木卫四",
            "土卫六",
            "矮行星",
        ),
        "solar_system",
    ),
    (("黑洞", "超大质量黑洞", "恒星级黑洞", "中等质量黑洞"), "black_hole"),
    (("旋涡星系", "椭圆星系", "不规则星系", "星系"), "galaxy"),
    (("行星状星云", "发射星云", "反射星云", "星云"), "nebula"),
    (("彗星", "小行星", "小行星带", "柯伊伯带"), "small_body"),
    (("白矮星", "中子星", "巨星"), "star"),
    (("星座",), "constellation"),
    (("空间站",), "spacecraft"),
]


def normalize_astronomy_label(raw_name: str) -> str:
    raw = str(raw_name or "").strip()
    if not raw:
        return ""

    lowered = " " + raw.lower().replace("_", " ").strip() + " "
    lowered = re.sub(r"\s+\d+\s*$", " ", lowered)
    lowered = re.sub(r"\s{2,}", " ", lowered)
    if any(token in lowered.strip() for token in {"unknown", "n/a", "none"}):
        return ""

    for aliases, canonical in _NORMALIZATION_RULES:
        for alias in aliases:
            if alias == " io ":
                if " io " in lowered:
                    return canonical
                continue
            if alias in lowered:
                return canonical
    return raw.strip()


def astronomy_label_family(name: str) -> str:
    normalized = normalize_astronomy_label(name)
    for aliases, family in _FAMILY_RULES:
        if normalized in aliases:
            return family
    return ""


def is_catalog_like_title(raw_name: str) -> bool:
    raw = str(raw_name or "").strip().lower().replace("_", " ")
    return bool(re.search(r"\b\d+\b", raw))
