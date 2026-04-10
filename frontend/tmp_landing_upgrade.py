import sys
import re
import codecs

with codecs.open('d:/Astro/frontend/src/views/Landing.vue', 'r', 'utf-8') as f:
    content = f.read()

# 1. Add apodData ref
if 'const apodData = ref<any>(null);' not in content:
    content = content.replace('const newsItems = ref', 'const apodData = ref<any>(null);\nconst newsItems = ref')

# 2. Add APOD fetch logic
if 'api.nasa.gov/planetary/apod' not in content:
    apod_fetch = '''
    // Fetch NASA APOD (Astronomy Picture of the Day)
    try {
      const apodResp = await fetch("https://api.nasa.gov/planetary/apod?api_key=DEMO_KEY");
      if (apodResp.ok) {
        apodData.value = await apodResp.json();
      }
    } catch (e) {
      console.error("Failed to load APOD", e);
    }
'''
    # insert inside loadLandingData
    content = content.replace('landingLoading.value = true;\n  try {', 'landingLoading.value = true;\n  try {\n' + apod_fetch)

# 3. Add Aladin Lite Script inside onMounted
if 'aladin.cds.unistra.fr' not in content:
    aladin_script = '''
  const aladinCss = document.createElement("link");
  aladinCss.rel = "stylesheet";
  aladinCss.href = "https://aladin.cds.unistra.fr/AladinLite/api/v3/latest/aladin.css";
  document.head.appendChild(aladinCss);

  const aladinJs = document.createElement("script");
  aladinJs.src = "https://aladin.cds.unistra.fr/AladinLite/api/v3/latest/aladin.js";
  aladinJs.charset = "utf-8";
  aladinJs.onload = () => {
    // @ts-ignore
    if (window.A && window.A.init) {
      // @ts-ignore
      window.A.init.then(() => {
        // @ts-ignore
        const aladin = window.A.aladin('#aladin-lite-div', {survey: "P/DSS2/color", fov: 60, target: "M 31"});
      });
    }
  };
  document.head.appendChild(aladinJs);
'''
    content = content.replace('loadLandingData();\n  refreshTimer', 'loadLandingData();\n\n' + aladin_script + '\n\n  refreshTimer')

# 4. Insert apod section in template
if 'class="apod-section"' not in content:
    apod_template = '''
      <section class="apod-section" v-if="apodData">
        <div class="apod-card surface-card">
          <div class="apod-img-box">
             <img v-if="apodData.media_type === 'image'" :src="apodData.hdurl || apodData.url" :alt="apodData.title" class="apod-img" />
             <iframe v-else :src="apodData.url" frameborder="0" class="apod-img"></iframe>
          </div>
          <div class="apod-info">
            <div class="apod-tag">NASA 每日星图 <span>(APOD)</span></div>
            <h3 class="apod-title">{{ apodData.title }}</h3>
            <p class="apod-date">{{ apodData.date }}</p>
            <p class="apod-desc">{{ apodData.explanation }}</p>
          </div>
        </div>
      </section>
'''
    # insert before news-section
    content = content.replace('<section class="news-section">', apod_template + '\n      <section class="news-section">')

# 5. Insert aladin section in template
if 'class="aladin-section"' not in content:
    aladin_template = '''
      <section class="aladin-section">
        <div class="section-head center">
          <p class="section-title xl">专业视场观测</p>
          <p class="section-subtitle">拖拽操作以探索全天域光学/红外深空调查数据 (数据源：国际 CDS Aladin Lite)</p>
        </div>
        <div id="aladin-lite-div" class="aladin-container surface-card"></div>
      </section>
'''
    # insert after science-cards-section and before frontier-section
    content = content.replace('<section class="frontier-section">', aladin_template + '\n      <section class="frontier-section">')

# 6. Insert CSS for new sections
if '.apod-section' not in content:
    styles = '''
.apod-section {
  width: 100%;
}
.apod-card {
  display: flex;
  background: rgba(14, 21, 35, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 16px;
  overflow: hidden;
  min-height: 340px;
}
.apod-img-box {
  flex: 0 0 55%;
  position: relative;
  background: #000;
}
.apod-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.apod-info {
  flex: 1;
  padding: 36px 40px;
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.apod-tag {
  color: #dfbea0;
  font-size: 13px;
  letter-spacing: 1px;
  margin-bottom: 8px;
  font-weight: 600;
}
.apod-title {
  font-size: 32px;
  margin: 0 0 6px;
  color: #f7faff;
  line-height: 1.25;
}
.apod-date {
  font-size: 13px;
  color: #8da4c2;
  margin: 0 0 16px;
}
.apod-desc {
  font-size: 14px;
  line-height: 1.6;
  color: #c7d2e4;
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 6;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.aladin-section {
  width: 100%;
}
.section-subtitle {
  color: #8da4c2;
  font-size: 14px;
  margin: 6px 0 0;
}
.aladin-container {
  width: 100%;
  height: 500px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  overflow: hidden;
  background: #000;
}

@media (max-width: 860px) {
  .apod-card {
    flex-direction: column;
  }
  .apod-img-box {
    height: 300px;
  }
}
'''
    content = content.replace('</style>', styles + '\n</style>')


with codecs.open('d:/Astro/frontend/src/views/Landing.vue', 'w', 'utf-8') as f:
    f.write(content)
