import sys

with open('d:/Astro/frontend/src/views/Landing.vue', 'r', encoding='utf-8') as f:
    content = f.read()

replacement = '''
      const resp = await fetch("https://api.spaceflightnewsapi.net/v4/articles/?limit=20");
      const data = await resp.json();
      
      const uniqueNews = [];
      const seenImages = new Set();
      
      for (const r of data.results) {
        if (!seenImages.has(r.image_url)) {
          seenImages.add(r.image_url);
          uniqueNews.push({
            title: r.title,
            url: r.url,
            image_url: r.image_url,
            source: r.news_site,
            summary: r.summary.substring(0, 150) + "...",
            date: new Date(r.published_at).toISOString().split("T")[0]
          });
        }
        if (uniqueNews.length >= 6) break;
      }
      
      newsItems.value = uniqueNews;
'''

old = '''
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
'''

content = content.replace(old.strip(), replacement.strip())

with open('d:/Astro/frontend/src/views/Landing.vue', 'w', encoding='utf-8') as f:
    f.write(content)
