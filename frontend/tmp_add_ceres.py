import sys
import codecs

with codecs.open('d:/Astro/frontend/src/data/celestials.ts', 'r', 'utf-8') as f:
    content = f.read()

# I will inject Ceres right after Pluto (at the end of the array)
ceres_data = '''  {
    id: "ceres",
    name: "谷神星",
    subtitle: "Ceres",
    icon: "⚳",
    gridImage: "https://upload.wikimedia.org/wikipedia/commons/7/76/Ceres_-_RC3_-_Haulani_Crater_39.jpg",
    heroImage: "https://upload.wikimedia.org/wikipedia/commons/7/76/Ceres_-_RC3_-_Haulani_Crater_39.jpg",
    type: "矮行星",
    desc: "谷神星是小行星带中最大的天体，也是唯一的矮行星。被认为是保存有早期内部水的原始天体。",
    intro: "谷神星位于火星和木星之间的小行星带，是该区域内唯一通过自身重力达到静力平衡（呈球形）的天体。它不仅含有大量的冰水物质，还被认为是太阳系演化早期的重要时间胶囊。",
    features: [
      "小行星带中体积最大、引力最大的单一星体",
      "地壳之下可能存在着广阔的冰冻层甚至液态大洋",
      "表面存在几处极其明亮的神秘反光盐斑（如奥卡托撞击坑）",
      "是一颗仍在演化的类地天体过渡形态"
    ],
    exploration: "NASA的黎明号（Dawn）探测器在2015年成功进入了谷神星轨道，不仅传回了前所未见的地表高清图，更成为人类首个深入环绕矮行星探测的航天英雄。",
    basicData: {
      "类型": "矮行星",
      "直径": "939 km",
      "质量": "9.39 × 10²⁰ kg",
      "表面温度": "约 -105 °C",
      "距太阳": "2.77 AU",
      "公转周期": "4.6 年",
      "自转周期": "9.1 小时",
      "卫星数": "0"
    },
    orbitData: {
      "轨道偏心率": "0.0758",
      "轨道倾角": "10.59°"
    }
  }'''

# Find the end of the array
idx = content.rfind(']')
if idx != -1:
    # insert before the bracket, append a comma to the last item
    content = content[:idx-1] + ',\n' + ceres_data + '\n' + content[idx:]

with codecs.open('d:/Astro/frontend/src/data/celestials.ts', 'w', 'utf-8') as f:
    f.write(content)
