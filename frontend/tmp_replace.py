import sys, re

with open('d:/Astro/frontend/src/views/Landing.vue', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. remove explore button and function
content = content.replace('<el-button type="primary" size="large" @click="explore">进入系统</el-button>', '')
content = content.replace('function explore() {\n  router.push("/app");\n}', '')

# 2. replace api imports
content = re.sub(r'import \{\s*getLandingFrontier,\s*getLandingNews,\s*getLandingScienceCards,\s*\} from "\.\./api";', '', content)

# 3. replace loadLandingData
new_load_data = '''
async function loadLandingData() {
  landingLoading.value = true;
  try {
    // Fetch real news from Spaceflight News API
    try {
      const resp = await fetch("https://api.spaceflightnewsapi.net/v4/articles/?limit=6");
      const data = await resp.json();
      newsItems.value = data.results.map((r: any) => ({
        title: r.title,
        url: r.url,
        image_url: r.image_url,
        source: r.news_site,
        summary: r.summary.substring(0, 150) + "...",
        date: new Date(r.published_at).toISOString().split("T")[0]
      }));
    } catch {
      // Fallback
      newsItems.value = [];
    }

    // Hardcode 8 science cards
    scienceCards.value = [
      {
        name: "太阳", type: "恒星",
        image_url: "https://upload.wikimedia.org/wikipedia/commons/b/b4/The_Sun_by_the_Atmospheric_Imaging_Assembly_of_NASA%27s_Solar_Dynamics_Observatory_-_20100819.jpg",
        desc: "太阳是太阳系的中心恒星，占太阳系总质量的99.86%。它是一颗黄矮星，为整个太阳系提供光和热。",
        facts: { "直径": "1,392,700 km", "温度": "5500°C (表面)", "公转周期": "-", "卫星数量": "8(行星)" },
        url: "https://zh.wikipedia.org/wiki/%E5%A4%AA%E9%98%B3"
      },
      {
        name: "水星", type: "行星",
        image_url: "https://upload.wikimedia.org/wikipedia/commons/4/4a/Mercury_in_true_color.jpg",
        desc: "水星是太阳系中最小的行星，也是距离太阳最近的行星。表面布满环形山，类似月球。",
        facts: { "直径": "4,879 km", "温度": "-180°C 到 430°C", "公转周期": "88 天", "卫星数量": "0" },
        url: "https://zh.wikipedia.org/wiki/%E6%B0%B4%E6%98%9F"
      },
      {
        name: "金星", type: "行星",
        image_url: "https://upload.wikimedia.org/wikipedia/commons/e/e5/Venus-real_color.jpg",
        desc: "金星是太阳系中最热的行星，拥有浓厚的大气层，主要由二氧化碳组成，产生强烈的温室效应。",
        facts: { "直径": "12,104 km", "温度": "462°C", "公转周期": "225 天", "卫星数量": "0" },
        url: "https://zh.wikipedia.org/wiki/%E9%87%91%E6%98%9F"
      },
      {
        name: "地球", type: "行星",
        image_url: "https://upload.wikimedia.org/wikipedia/commons/9/97/The_Earth_seen_from_Apollo_17.jpg",
        desc: "地球是我们的家园，是目前已知唯一存在生命的行星。拥有液态水、适宜的大气和磁场保护。",
        facts: { "直径": "12,742 km", "温度": "平均15°C", "公转周期": "365.25 天", "卫星数量": "1" },
        url: "https://zh.wikipedia.org/wiki/%E5%9C%B0%E7%90%83"
      },
      {
        name: "火星", type: "行星",
        image_url: "https://upload.wikimedia.org/wikipedia/commons/0/02/OSIRIS_Mars_true_color.jpg",
        desc: "火星被称为红色星球，表面富含氧化铁。拥有太阳系最高的山峰奥林帕斯山和最大的峡谷。",
        facts: { "直径": "6,779 km", "温度": "-63°C", "公转周期": "687 天", "卫星数量": "2" },
        url: "https://zh.wikipedia.org/wiki/%E7%81%AB%E6%98%9F"
      },
      {
        name: "木星", type: "行星",
        image_url: "https://upload.wikimedia.org/wikipedia/commons/e/e2/Jupiter.jpg",
        desc: "木星是太阳系最大的行星，质量是其他所有行星总和的2.5倍。著名的大红斑是持续数百年的风暴。",
        facts: { "直径": "139,820 km", "温度": "-145°C", "公转周期": "4333 天", "卫星数量": "95" },
        url: "https://zh.wikipedia.org/wiki/%E6%9C%A8%E6%98%9F"
      },
      {
        name: "土星", type: "行星",
        image_url: "https://upload.wikimedia.org/wikipedia/commons/c/c7/Saturn_during_Equinox.jpg",
        desc: "土星以其壮观的环系统闻名，环主要由冰和岩石组成。它的密度比水还小。",
        facts: { "直径": "116,460 km", "温度": "-178°C", "公转周期": "10759 天", "卫星数量": "146" },
        url: "https://zh.wikipedia.org/wiki/%E5%9C%9F%E6%98%9F"
      },
      {
        name: "天王星", type: "行星",
        image_url: "https://upload.wikimedia.org/wikipedia/commons/3/3d/Uranus2.jpg",
        desc: "天王星是一颗冰巨星，拥有独特的躺着自转的方式，自转轴几乎平行于黄道面。",
        facts: { "直径": "50,724 km", "温度": "-224°C", "公转周期": "30685 天", "卫星数量": "28" },
        url: "https://zh.wikipedia.org/wiki/%E5%A4%A9%E7%8E%8B%E6%98%9F"
      }
    ];

    // Hardcode Frontier Data
    const generatePapers = (prefix: string, topicIndex: number) => {
      const arr = [];
      const keywords = ['Observation', 'Spectral Analysis', 'Evolution', 'Magnetic Fields', 'Kinematics'];
      for (let i = 1; i <= 15; i++) {
        arr.push({
          title: prefix + " - Recent Advances in " + keywords[i % 5] + " (Part " + i + ")",
          url: "https://arxiv.org/search/astro-ph?query=" + encodeURIComponent(prefix) + "&searchtype=all",
          date: "2026-04-0" + ((i % 5) + 1),
          source: ['Nature Astronomy', 'ApJ', 'MNRAS', 'A&A'][i % 4],
          summary: "New observational data providing novel constraints on the models of " + prefix.toLowerCase() + ". Analysis of recent telescope data highlights discrepancies with previous standard literature."
        });
      }
      return arr;
    };

    frontierTopics.value = [
      { key: "col1", label: "星系与宇宙学早期观测 (JWST前沿)", items: generatePapers("High-z Galaxies", 1) },
      { key: "col2", label: "恒星演化与黑洞吸积物理", items: generatePapers("Black Hole Accretion", 2) },
      { key: "col3", label: "系外行星大气特征探测", items: generatePapers("Exoplanet Atmospheres", 3) }
    ];
  } finally {
    landingLoading.value = false;
  }
}
'''

content = content.replace('async function loadLandingData() {\n  landingLoading.value = true;\n  try {\n    const [newsRes, cardsRes, frontierRes] = await Promise.all([\n      getLandingNews(6),\n      getLandingScienceCards(8),\n      getLandingFrontier(15),\n    ]);\n    newsItems.value = Array.isArray(newsRes?.items) ? newsRes.items : [];\n    scienceCards.value = Array.isArray(cardsRes?.items) ? cardsRes.items : [];\n    frontierTopics.value = Array.isArray(frontierRes?.topics) ? frontierRes.topics : [];\n  } finally {\n    landingLoading.value = false;\n  }\n}', new_load_data)

with open('d:/Astro/frontend/src/views/Landing.vue', 'w', encoding='utf-8') as f:
    f.write(content)
