import streamlit as st
from yt_dlp import YoutubeDL
import json
from datetime import datetime, timedelta
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

st.set_page_config(page_title="YouTube Scraper Pro", layout="wide")
st.title("🚀 YouTube Keyword Research Tool PRO")

# ============ SIDEBAR ============
st.sidebar.header("⚙️ Paramètres")

# MOTS-CLÉS
keywords_input = st.sidebar.text_area(
    "🔍 Mot-clé :",
    placeholder="starlink",
    help="Entre un mot-clé"
)
keywords_list = [k.strip() for k in keywords_input.split('\n') if k.strip()]

# VUES
st.sidebar.write("### 👁️ Vues minimum")
selected_views = []
if st.sidebar.checkbox("10K-50K"):
    selected_views.append((10000, 50000))
if st.sidebar.checkbox("50K-100K"):
    selected_views.append((50000, 100000))
if st.sidebar.checkbox("100K+"):
    selected_views.append((100000, 10000000))
if st.sidebar.checkbox("1M+"):
    selected_views.append((1000000, float('inf')))

# BOUTON
if st.sidebar.button("🚀 Lancer"):
    if not keywords_list:
        st.error("❌ Mot-clé requis!")
    elif not selected_views:
        st.error("❌ Sélectionne une gamme de vues!")
    else:
        progress = st.progress(0)
        status = st.empty()
        
        keyword = keywords_list[0]
        
        try:
            # RECHERCHE
            status.text(f"🔍 Recherche: {keyword}")
            
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': 'in_playlist',
                'socket_timeout': 5,
                'ignoreerrors': True,
            }
            
            search_query = f"ytsearch50:{keyword}"
            
            with YoutubeDL(ydl_opts) as ydl:
                results = ydl.extract_info(search_query, download=False)
                video_ids = results.get('entries', [])
            
            video_ids = [v for v in video_ids if v is not None]
            st.info(f"✅ {len(video_ids)} vidéos trouvées sur YouTube")
            
            progress.progress(20)
            
            # RÉCUPÉRER MÉTADONNÉES
            status.text("📊 Récupération métadonnées...")
            
            def fetch_metadata(vid):
                try:
                    video_id = vid.get('id')
                    if not video_id:
                        return None
                    
                    ydl = YoutubeDL({
                        'quiet': True,
                        'no_warnings': True,
                        'socket_timeout': 5,
                        'ignoreerrors': True,
                        'skip_download': True,
                    })
                    
                    info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
                    return info
                except:
                    return None
            
            videos = []
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(fetch_metadata, vid) for vid in video_ids]
                for future in as_completed(futures):
                    result = future.result()
                    if result:
                        videos.append(result)
            
            st.info(f"✅ {len(videos)} vidéos avec métadonnées")
            progress.progress(40)
            
            # FILTRER PAR VUES
            status.text("🎯 Filtrage par vues...")
            
            videos_filtered = []
            for video in videos:
                views = video.get('view_count', 0) or 0
                
                for min_v, max_v in selected_views:
                    if min_v <= views <= max_v:
                        videos_filtered.append(video)
                        break
            
            st.success(f"✅ {len(videos_filtered)} vidéos après filtrage!")
            
            if len(videos_filtered) == 0:
                st.error("❌ Aucune vidéo avec ces filtres de vues")
                
                # DEBUG : Afficher les vues des vidéos
                st.write("### 🔍 Debug : Vues des vidéos trouvées")
                for v in videos[:10]:
                    st.write(f"- {v.get('title', '')[:50]}... : {v.get('view_count', 0):,} vues")
                st.stop()
            
            progress.progress(60)
            
            # AFFICHER RÉSULTATS
            st.header(f"📹 {len(videos_filtered)} vidéos trouvées")
            
            for idx, video in enumerate(videos_filtered, 1):
                title = video.get('title', '')
                views = video.get('view_count', 0)
                likes = video.get('like_count', 0)
                video_id = video.get('id', '')
                thumbnail = video.get('thumbnail', '')
                
                with st.expander(f"{idx}. {title} | 👁️ {views:,}"):
                    if thumbnail:
                        st.image(thumbnail, width=300)
                    st.write(f"**👁️ Vues:** {views:,}")
                    st.write(f"**👍 Likes:** {likes:,}")
                    st.write(f"**🔗** [Regarder](https://www.youtube.com/watch?v={video_id})")
            
            progress.progress(100)
            status.text("✅ Terminé!")
            
        except Exception as e:
            st.error(f"❌ Erreur: {str(e)}")
            st.exception(e)
