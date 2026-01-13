import streamlit as st
from yt_dlp import YoutubeDL

st.set_page_config(page_title="YouTube Scraper", layout="wide")
st.title("🎬 YouTube Keyword Research Tool")
st.write("Recherche des vidéos YouTube avec commentaires")

# SIDEBAR - PARAMÈTRES
st.sidebar.header("⚙️ Paramètres")

keyword = st.sidebar.text_input("🔍 Mot-clé:", placeholder="guerre en Irak")
max_videos = st.sidebar.slider("📊 Nombre de vidéos:", 1, 20, 5)
min_views = st.sidebar.number_input("👁️ Vues minimum:", min_value=0, value=0, step=10000)

# BOUTON RECHERCHE
if st.sidebar.button("🚀 Lancer la recherche", use_container_width=True):
    if not keyword:
        st.error("❌ Rentre un mot-clé!")
    else:
        st.info(f"⏳ Recherche en cours pour: **{keyword}**...")
        
        try:
            # RECHERCHE VIDÉOS
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': 'in_playlist',
            }
            
            with YoutubeDL(ydl_opts) as ydl:
                search_query = f"ytsearch{max_videos}:{keyword}"
                results = ydl.extract_info(search_query, download=False)
                videos = results.get('entries', [])
            
            # FILTRER PAR VUES
            videos_filtered = []
            for video in videos:
                views = video.get('view_count', 0) or 0
                if views >= min_views:
                    videos_filtered.append(video)
            
            st.success(f"✅ {len(videos_filtered)} vidéo(s) trouvée(s)!")
            st.divider()
            
            # AFFICHER LES VIDÉOS
            for idx, video in enumerate(videos_filtered, 1):
                st.write(f"## 📹 Vidéo {idx}: {video['title']}")
                st.write(f"**Canal:** {video.get('uploader', 'Inconnu')}")
                st.write(f"👁️ **Vues:** {video.get('view_count', 0):,}")
                st.write(f"🔗 [Regarder sur YouTube](https://www.youtube.com/watch?v={video['id']})")
                
                # SECTION COMMENTAIRES
                st.write("### 💬 Top 20 Commentaires")
                
                try:
                    ydl_comments = YoutubeDL({
                        'quiet': True,
                        'no_warnings': True,
                        'skip_download': True,
                    })
                    
                    video_info = ydl_comments.extract_info(f"https://www.youtube.com/watch?v={video['id']}", download=False)
                    comments = video_info.get('comments', [])
                    
                    if comments:
                        comments_sorted = sorted(comments, key=lambda x: x.get('likes', 0), reverse=True)[:20]
                        
                        for i, comment in enumerate(comments_sorted, 1):
                            author = comment.get('author', 'Anonyme')
                            text = comment.get('text', '')
                            likes = comment.get('likes', 0)
                            
                            st.write(f"**{i}. {author}** (👍 {likes})")
                            st.write(f"> {text}")
                            st.write("")
                    else:
                        st.info("⚠️ Aucun commentaire disponible")
                
                except Exception as e:
                    st.warning(f"⚠️ Commentaires non disponibles")
                
                st.divider()
        
        except Exception as e:
            st.error(f"❌ Erreur: {str(e)}")
