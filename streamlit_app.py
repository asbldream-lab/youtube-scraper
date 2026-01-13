import streamlit as st
from yt_dlp import YoutubeDL

st.set_page_config(page_title="YouTube Scraper", layout="wide")
st.title("🎬 YouTube Keyword Research Tool")
st.write("Recherche des vidéos YouTube")

col1, col2 = st.columns(2)

with col1:
    keyword = st.text_input("🔍 Mot-clé:", placeholder="guerre en Irak")

with col2:
    max_videos = st.slider("📊 Nombre de vidéos:", 1, 10, 3)

if st.button("🚀 Lancer la recherche", use_container_width=True):
    if not keyword:
        st.error("❌ Rentre un mot-clé!")
    else:
        st.info(f"⏳ Recherche en cours pour: **{keyword}**...")
        
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': 'in_playlist',
            }
            
            with YoutubeDL(ydl_opts) as ydl:
                search_query = f"ytsearch{max_videos}:{keyword}"
                results = ydl.extract_info(search_query, download=False)
                
                videos = results.get('entries', [])
                st.success(f"✅ {len(videos)} vidéo(s) trouvée(s)!")
                
                for idx, video in enumerate(videos, 1):
                    st.write(f"### Vidéo {idx}: {video['title']}")
                    st.write(f"**Canal:** {video.get('uploader', 'Inconnu')}")
                    st.write(f"🔗 https://www.youtube.com/watch?v={video['id']}")
                    st.divider()
        
        except Exception as e:
            st.error(f"❌ Erreur: {str(e)}")
