import sys, re

with open('d:/Astro/frontend/src/views/Landing.vue', 'r', encoding='utf-8') as f:
    content = f.read()

# Remove '前往登录' button
content = content.replace('<el-button size="large" @click="goToLogin">前往登录</el-button>', '')


# Import celestialBodies
if 'import { celestialBodies } from "../data/celestials";' not in content:
    content = content.replace('import { useRouter } from "vue-router";', 'import { useRouter } from "vue-router";\nimport { celestialBodies } from "../data/celestials";')

# Replace hardcoded scienceCards logic
# It starts around `// Hardcode 8 science cards` up to `];`
replacement = '''    // Load from data repository
    scienceCards.value = celestialBodies.map(body => ({
      name: body.name,
      type: body.type,
      image_url: body.gridImage,
      desc: body.desc,
      facts: body.basicData,
      url: `/celestial/${body.id}` // Use route path
    }));'''

# We find the start and end of the block to replace
start_idx = content.find('// Hardcode 8 science cards')
end_idx = content.find('    // Hardcode Frontier Data')
if start_idx != -1 and end_idx != -1:
    content = content[:start_idx] + replacement + '\n\n' + content[end_idx:]

# Replace <a> with <router-link> or click handlers for the science cards wrapper
# It currently has:
# <a :href="card.url" target="_blank" rel="noopener noreferrer" class="card-image-wrap">
# and <a :href="card.url" target="_blank" rel="noopener noreferrer" class="card-link">查看详情</a>

# To easily switch from <a> to Vue Router programmatic nav, 
# we can just change the <a> to use the router properly.
# But <a :href="..."> with target="_blank" opens a new tab. For a webapp detail page, it shouldn't open a new tab.
content = content.replace(
  '<a :href="card.url" target="_blank" rel="noopener noreferrer" class="card-image-wrap">',
  '<router-link :to="card.url" class="card-image-wrap">'
)
content = content.replace(
  '</a>\n            <div class="card-body">',
  '</router-link>\n            <div class="card-body">'
)

content = content.replace(
  '<a :href="card.url" target="_blank" rel="noopener noreferrer" class="card-link">查看详情</a>',
  '<router-link :to="card.url" class="card-link">查看详情</router-link>'
)

with open('d:/Astro/frontend/src/views/Landing.vue', 'w', encoding='utf-8') as f:
    f.write(content)
