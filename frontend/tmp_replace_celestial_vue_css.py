import sys

with open('d:/Astro/frontend/src/views/CelestialDetail.vue', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(
    '.head-icon {\n  font-size: 16px;\n}',
    '.head-icon {\n  width: 18px;\n  height: 18px;\n  stroke-width: 2px;\n}'
)

with open('d:/Astro/frontend/src/views/CelestialDetail.vue', 'w', encoding='utf-8') as f:
    f.write(content)
