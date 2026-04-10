import codecs
import re

with codecs.open('d:/Astro/frontend/src/data/celestials.ts', 'r', 'utf-8') as f:
    content = f.read()

# Fix Ceres image link to guaranteed NASA JPL Photojournal link
content = content.replace(
    'https://images.unsplash.com/photo-1614729939124-032f0b56c9ce?q=80&w=2574&auto=format&fit=crop',
    'https://photojournal.jpl.nasa.gov/jpeg/PIA20348.jpg'
)
with codecs.open('d:/Astro/frontend/src/data/celestials.ts', 'w', 'utf-8') as f:
    f.write(content)


with codecs.open('d:/Astro/frontend/src/views/Landing.vue', 'r', 'utf-8') as f:
    landing = f.read()

# 1. Remove Aladin JS injection
landing = re.sub(r'const aladinCss = document\.createElement.*?document\.head\.appendChild\(aladinJs\);\s*', '', landing, flags=re.DOTALL)

# 2. Remove Aladin HTML section
landing = re.sub(r'<section class="aladin-section">.*?</section>\s+', '', landing, flags=re.DOTALL)

# 3. Remove Aladin CSS
landing = re.sub(r'\.aladin-section\s*\{.*?\.aladin-container\s*\{.*?\}\s*', '', landing, flags=re.DOTALL)

# 4. Inject APOD fetching code into loadLandingData if it's missing or fix it
apod_fetch_code = '''
    // Fetch NASA APOD (Astronomy Picture of the Day)
    try {
      const apodResp = await fetch("https://api.nasa.gov/planetary/apod?api_key=DEMO_KEY");
      if (apodResp.ok) {
        apodData.value = await apodResp.json();
      } else {
        throw new Error("Rate limit");
      }
    } catch (e) {
      console.warn("Using fallback APOD data", e);
      apodData.value = {
        title: "大麦哲伦星云中的恒星形成区 (Local Fallback)",
        date: new Date().toISOString().split("T")[0],
        explanation: "由于 NASA 的开放接口在您当前的网络环境下触发了防刷访问限制，我们为您展示这张极具代表性的天文后备图：大麦哲伦星云（LMC）边缘一个极其活跃的恒星形成区，充满了星际气体和尘埃。",
        media_type: "image",
        url: "https://images.unsplash.com/photo-1462331940025-496dfbfc7564?q=80&w=2574&auto=format&fit=crop"
      };
    }
'''

# Check if APOD logic exists
if 'api.nasa.gov/planetary/apod' not in landing:
    # Safely inject inside loadLandingData right after `landingLoading.value = true;`
    # Replace the exact line
    target_line = 'landingLoading.value = true;'
    landing = landing.replace(target_line, target_line + '\n' + apod_fetch_code)


with codecs.open('d:/Astro/frontend/src/views/Landing.vue', 'w', 'utf-8') as f:
    f.write(landing)
