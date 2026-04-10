import sys

with open('d:/Astro/frontend/src/views/Landing.vue', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the news fetching and merging logic:
replacement = '''
      const resp = await fetch("https://api.spaceflightnewsapi.net/v4/articles/?limit=20");
      const data = await resp.json();
      
      // We will completely lock the backgrounds to curated ultra-high-res NASA stock
      // to avoid identical/duplicate news API covers
      const fallbackImages = [
        "https://images.unsplash.com/photo-1614729939124-032f0b56c9ce?q=80&w=2574&auto=format&fit=crop", // Galaxy
        "https://images.unsplash.com/photo-1462331940025-496dfbfc7564?q=80&w=2000&auto=format&fit=crop", // Nebula
        "https://images.unsplash.com/photo-1451187580459-43490279c0fa?q=80&w=2000&auto=format&fit=crop", // Earth Orbit
        "https://images.unsplash.com/photo-1444703686981-a3abbc4d4fe3?q=80&w=2000&auto=format&fit=crop", // ISS/Spacecraft
        "https://images.unsplash.com/photo-1541185933-ef5d8ed016c2?q=80&w=2000&auto=format&fit=crop", // Telescope launch
        "https://images.unsplash.com/photo-1614730321146-b6fa6a46bcb4?q=80&w=2000&auto=format&fit=crop"  // Deep space
      ];
      
      const uniqueNews = [];
      const seenTitles = new Set();
      
      for (const r of data.results) {
        // filter out literal same articles since the API occasionally blasts duplicates
        if (!seenTitles.has(r.title.substring(0, 20))) {
          seenTitles.add(r.title.substring(0, 20));
          uniqueNews.push({
            title: r.title,
            url: r.url,
            // FORCE beautiful unique background by overriding API data:
            image_url: fallbackImages[uniqueNews.length],
            source: r.news_site,
            summary: r.summary.substring(0, 150) + "...",
            date: new Date(r.published_at).toISOString().split("T")[0]
          });
        }
        if (uniqueNews.length >= 6) break;
      }
      
      newsItems.value = uniqueNews;
'''

import re
# We need to find the old loadLandingData fetch block and replace it
# The block starts with `const resp = await fetch(` and ends with `newsItems.value = uniqueNews;`

start_idx = content.find('const resp = await fetch("https://api.spaceflightnewsapi.net/v4/articles/?limit=20");')
end_idx = content.find('newsItems.value = uniqueNews;') + len('newsItems.value = uniqueNews;')

if start_idx != -1 and end_idx != -1:
    content = content[:start_idx] + replacement.strip() + content[end_idx:]
    
with open('d:/Astro/frontend/src/views/Landing.vue', 'w', encoding='utf-8') as f:
    f.write(content)
