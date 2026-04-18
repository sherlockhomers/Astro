# 重新生成 RAG 七阶段流程图的 PNG，用 Pillow 手绘。
# 原图是 PPT 里的 STAGE 1-7，用户说文字有乱的地方，这里按他图的结构重画一份，
# 所有中文都走 Windows 微软雅黑字体，不会乱码。
#
# 运行:  cd d:\Astro  &&  python scripts/make_rag_flowchart.py
# 产出:  d:\Astro\assets\rag_flowchart_clean.png

from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "rag_flowchart_clean.png"

# ── 中文字体：Windows 常见路径，按优先级试 ──
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyhbd.ttc",   # 微软雅黑 Bold
    r"C:\Windows\Fonts\msyh.ttc",     # 微软雅黑 Regular
    r"C:\Windows\Fonts\simhei.ttf",   # 黑体
    r"C:\Windows\Fonts\simsun.ttc",   # 宋体
]


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    # 先找粗体
    for path in (FONT_CANDIDATES if bold else FONT_CANDIDATES[1:]):
        p = Path(path)
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


# ── 画布 ──
W, H = 2400, 1400         # 2 倍像素，导出后缩一半清晰
BG = (255, 255, 255, 0)   # 完全透明
img = Image.new("RGBA", (W, H), BG)
draw = ImageDraw.Draw(img)

# 字体
F_STAGE_NUM = load_font(36, bold=True)   # "1"/"2"... 圆圈数字
F_STAGE_LABEL = load_font(32, bold=True) # "STAGE 1"
F_STAGE_TITLE = load_font(36, bold=True) # "输入预处理"
F_ITEM = load_font(24)                   # 子项
F_ITEM_BOLD = load_font(24, bold=True)   # 关键项
F_FOOTER = load_font(32, bold=True)      # 底部标签

# 每个阶段的主题色（边框 + 标题条 + 圆圈）
STAGES = [
    {
        "num": "1", "label": "STAGE 1", "title": "输入预处理",
        "color": (19, 210, 184),
        "items": [
            "用户提问",
            "会话历史融合",
            "缓存检查",
            "[ 命中判定 ]",
            "→ 命中：直接返回",
            "→ 未命中：继续",
        ],
    },
    {
        "num": "2", "label": "STAGE 2", "title": "查询理解",
        "color": (96, 165, 250),
        "items": [
            "意图识别",
            "（一般/事实/科普/",
            "  比较/关系）",
            "实体抽取与归一化",
            "复杂度分级",
            "（简单/中等/复杂）",
        ],
    },
    {
        "num": "3", "label": "STAGE 3", "title": "策略决策",
        "color": (167, 139, 250),
        "items": [
            "启发式策略引擎",
            "＋ LLM Planner（可选）",
            "critical flags:",
            "need_retrieval",
            "need_graph",
            "need_dynamic",
            "need_web / need_mcp",
            "领域事实护栏",
        ],
    },
    {
        "num": "4", "label": "STAGE 4", "title": "多源检索",
        "color": (251, 146, 60),
        "items": [
            "知识库（向量+BM25）",
            "实体直出",
            "知识图谱（Neo4j）",
            "动态数据（系外行星）",
            "MCP 工具 · Web 搜索",
            "检索结果融合与重排",
            "第 2 轮扩展检索（可选）",
        ],
    },
    {
        "num": "5", "label": "STAGE 5", "title": "答案合成",
        "color": (74, 222, 128),
        "items": [
            "最新资讯摘要",
            "结构化对比",
            "本地 LLM（AstroSage-8B）",
            "RAG 拼接",
            "Agent 兜底",
            "Web 兜底",
        ],
    },
    {
        "num": "6", "label": "STAGE 6", "title": "后处理",
        "color": (244, 114, 182),
        "items": [
            "领域护栏校验",
            "相关性验证",
            "云端增强",
            "（GPT-4o-mini）",
            "反思自评",
            "重试",
        ],
    },
    {
        "num": "7", "label": "STAGE 7", "title": "输出",
        "color": (250, 204, 21),
        "items": [
            "记忆写入",
            "SSE 流式推送",
            "（分析 / 策略 /",
            "  检索 / 预览 /",
            "  增量 / 完成）",
            "最终答案",
        ],
    },
]

FOOTER_TAGS = [
    ("自适应策略", (19, 210, 184)),
    ("多源融合检索", (96, 165, 250)),
    ("多轮渐进检索", (167, 139, 250)),
    ("优先级瀑布生成", (251, 146, 60)),
    ("反思与重试", (244, 114, 182)),
    ("云端增强", (250, 204, 21)),
]


# ── 布局常量 ──
MARGIN_X = 60
MARGIN_TOP = 120
GAP = 24
NUM_COL = 7
COL_W = (W - MARGIN_X * 2 - GAP * (NUM_COL - 1)) // NUM_COL
STAGE_H = 960
FOOTER_Y = MARGIN_TOP + STAGE_H + 80
FOOTER_H = 100


def rounded_rect(draw, xy, radius, fill=None, outline=None, width=2):
    # Pillow 9+ 自带 rounded_rectangle
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def text_anchor_center(draw, pos, text, font, fill):
    # PIL 的 anchor="mm" 要求 font 是 truetype。我们用先算宽高再居中的方式更稳
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    draw.text((pos[0] - w // 2, pos[1] - h // 2), text, font=font, fill=fill)


# ── 画每个阶段 ──
for idx, stage in enumerate(STAGES):
    x0 = MARGIN_X + idx * (COL_W + GAP)
    y0 = MARGIN_TOP
    x1 = x0 + COL_W
    y1 = y0 + STAGE_H

    color = stage["color"]
    color_soft = (*color, 38)         # 半透明背景
    color_border = (*color, 255)

    # 外框
    rounded_rect(draw, (x0, y0, x1, y1), radius=18, fill=color_soft, outline=color_border, width=4)

    # 圆圈数字（贴在左上角）
    cx = x0 + 45
    cy = y0 - 30
    draw.ellipse((cx - 36, cy - 36, cx + 36, cy + 36), fill=color_border, outline=(255, 255, 255, 255), width=3)
    text_anchor_center(draw, (cx, cy), stage["num"], F_STAGE_NUM, fill=(255, 255, 255, 255))

    # STAGE N 标签（圆圈右边）
    draw.text((cx + 50, cy - 22), stage["label"], font=F_STAGE_LABEL, fill=(60, 60, 60, 255))

    # 标题栏（顶部色条）
    title_y = y0 + 30
    title_band_h = 80
    rounded_rect(
        draw,
        (x0 + 14, title_y, x1 - 14, title_y + title_band_h),
        radius=10,
        fill=(*color, 230),
    )
    text_anchor_center(
        draw,
        ((x0 + x1) // 2, title_y + title_band_h // 2),
        stage["title"],
        F_STAGE_TITLE,
        fill=(255, 255, 255, 255),
    )

    # 子项列表
    item_y = title_y + title_band_h + 28
    line_height = 40
    for line in stage["items"]:
        font = F_ITEM_BOLD if line.startswith("[") else F_ITEM
        if line.startswith("→"):
            color_text = (60, 60, 60, 255)
        elif line.startswith("["):
            color_text = color_border
        else:
            color_text = (30, 30, 30, 255)
        draw.text((x0 + 30, item_y), line, font=font, fill=color_text)
        item_y += line_height


# ── 底部标签条 ──
footer_count = len(FOOTER_TAGS)
footer_col_w = (W - MARGIN_X * 2 - 16 * (footer_count - 1)) // footer_count

for i, (tag, color) in enumerate(FOOTER_TAGS):
    fx0 = MARGIN_X + i * (footer_col_w + 16)
    fx1 = fx0 + footer_col_w
    rounded_rect(
        draw,
        (fx0, FOOTER_Y, fx1, FOOTER_Y + FOOTER_H),
        radius=14,
        fill=(*color, 200),
        outline=color + (255,),
        width=3,
    )
    text_anchor_center(
        draw,
        ((fx0 + fx1) // 2, FOOTER_Y + FOOTER_H // 2),
        tag,
        F_FOOTER,
        fill=(255, 255, 255, 255),
    )


# ── 输出 ──
OUT.parent.mkdir(parents=True, exist_ok=True)
img.save(OUT)
print(f"Saved: {OUT} ({OUT.stat().st_size / 1024:.1f} KB)")
