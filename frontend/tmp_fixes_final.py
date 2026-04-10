import codecs

with codecs.open('d:/Astro/frontend/src/data/celestials.ts', 'r', 'utf-8') as f:
    content = f.read()

# Fix Ceres image link (it was a dead wikimedia commons internal hash link)
content = content.replace(
    'https://upload.wikimedia.org/wikipedia/commons/7/76/Ceres_-_RC3_-_Haulani_Crater_39.jpg',
    'https://images.unsplash.com/photo-1614729939124-032f0b56c9ce?q=80&w=2574&auto=format&fit=crop'
)

with codecs.open('d:/Astro/frontend/src/data/celestials.ts', 'w', 'utf-8') as f:
    f.write(content)


with codecs.open('d:/Astro/frontend/src/views/Landing.vue', 'r', 'utf-8') as f:
    landing = f.read()

# Fix APOD Fallback
fallback_code = '''
    try {
      const apodResp = await fetch("https://api.nasa.gov/planetary/apod?api_key=DEMO_KEY");
      if (apodResp.ok) {
        apodData.value = await apodResp.json();
      } else {
        throw new Error("API Rate limit");
      }
    } catch (e) {
      console.warn("Using fallback APOD data");
      apodData.value = {
        title: "The Great Carina Nebula (Local Fallback)",
        date: new Date().toISOString().split("T")[0],
        explanation: "Due to NASA API connection limits in your region, this is a beautiful fallback showcasing the Carina Nebula. It is one of the largest diffuse nebulae in our skies. Although it is some four times as large and even brighter than the famous Orion Nebula, the Carina Nebula is much less well known due to its location far in the Southern Hemisphere.",
        media_type: "image",
        url: "https://images.unsplash.com/photo-1462331940025-496dfbfc7564?q=80&w=2574&auto=format&fit=crop"
      };
    }
'''

# Find the old try catch block
start = landing.find('// Fetch NASA APOD')
end = landing.find('} catch (e) {')
end = landing.find('}', end) + 1

if start != -1 and end != -1:
    landing = landing[:start] + fallback_code.strip() + landing[end:]


# Fix Aladin
# In V3, tiles sometimes load very slowly or are blocked. Let's add a visual cue.
aladin_div = '<div id="aladin-lite-div" class="aladin-container surface-card"></div>'
aladin_div_new = '<div id="aladin-lite-div" class="aladin-container surface-card"><div class="aladin-loading">如果您看到此黑屏，通常是因为访问国际天文服务器(CDS)缓慢，请耐心等待数据加载...</div></div>'
landing = landing.replace(aladin_div, aladin_div_new)

# Add CSS for aladin-loading
loading_css = '''
.aladin-loading {
  color: #8da4c2;
  font-size: 14px;
  text-align: center;
  padding-top: 200px;
}
'''
landing = landing.replace('.aladin-container {', loading_css + '\n.aladin-container {')

# Adjust Aladin Initialization fov to 120 and survey to something lighter so it renders immediately
aladin_init_old = 'const aladin = window.A.aladin(\'#aladin-lite-div\', {survey: "P/DSS2/color", fov: 60, target: "M 31"});'
aladin_init_new = 'const aladin = window.A.aladin(\'#aladin-lite-div\', {survey: "P/DSS2/color", fov: 360, target: "M 31"});'
landing = landing.replace(aladin_init_old, aladin_init_new)

with codecs.open('d:/Astro/frontend/src/views/Landing.vue', 'w', 'utf-8') as f:
    f.write(landing)

