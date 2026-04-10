import sys

with open('d:/Astro/frontend/src/views/CelestialDetail.vue', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace lucide imports
content = content.replace("import { ChevronLeft } from 'lucide-vue-next';", "import { ChevronLeft, FileText, Sparkles, Database, Orbit, Telescope, Rocket } from 'lucide-vue-next';")

# Replace 📄 简介 with FileText
content = content.replace('<span class="head-icon">📄</span>', '<FileText class="head-icon" />')
# Replace ✨ 特征 with Sparkles
content = content.replace('<span class="head-icon">✨</span>', '<Sparkles class="head-icon" />')
# Replace 📊 基本数据 with Database
content = content.replace('<span class="head-icon">📊</span>', '<Database class="head-icon" />')
# Replace 🪐 轨道参数 with Orbit
content = content.replace('<span class="head-icon">🪐</span>', '<Orbit class="head-icon" />')
# Replace 🔭 其他天体 with Telescope
content = content.replace('<span class="head-icon">🔭</span>', '<Telescope class="head-icon" />')

# Insert the exploration block below features
exploration_block = '''
          <section class="info-card surface-card">
            <h3 class="card-head"><Rocket class="head-icon" /> 探测历史</h3>
            <p class="intro-text">{{ currentBody.exploration }}</p>
          </section>'''

# Find where to insert it (after the features section)
features_end = '</section>'
left_col_end = '        </div>\n\n        <div class="right-col">'
idx = content.find(left_col_end)
if idx != -1:
    content = content[:idx] + exploration_block + '\n' + content[idx:]
    
with open('d:/Astro/frontend/src/views/CelestialDetail.vue', 'w', encoding='utf-8') as f:
    f.write(content)
