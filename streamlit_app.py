import streamlit as st
from yt_dlp import YoutubeDL

st.set_page_config(page_title="YouTube Scraper", layout="wide")
st.title("🎬 YouTube Keyword Research Tool")
st.write("Recherche des vidéos YouTube avec commentaires")

# SIDEBAR - PARAMÈTRES
st.sidebar.header("⚙️ Paramètres")

keyword = st.sidebar.text_input("🔍 Mot-clé:", placeholder="guerre en Irak")
max_videos = st.sidebar.slider("📊 Nombre de vidéos:", 1, 20, 5)

st.sidebar.write("### 👁️ Vues minimum")
col1, col2, col3 = st.sidebar.columns(3)

with col1:
    if st.button("10K - 50K"):
        st.session_state.min_views = 10000
        st.session_state.max_views = 50000

with col2:
    if st.button("50K - 100K"):
        st.session_state.min_views = 50000
        st.session_state.max_views = 100000

with col3:
    if st.button("+ 100K"):
        st.session_state.min_views = 100000
        st.session_state.max_views = float('inf')

if 'min_views' not in st.session_state:
    st.session_state.min_views = 0
    st.session_state.max_views = float('inf')

# BOUTON RECHERCHE
if st.sidebar.button("🚀 Lancer la recherche", use_container_width=True):
    if not keyword:
        st.error("❌ Rentre un mot-clé!")
    else:
        # BARRE DE CHARGEMENT
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        status_text.text("⏳ Recherche de vidéos...")
        progress_bar.progress(20)
        
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
            
            progress_bar.progress(40)
            
            # FILTRER PAR VUES
            videos_filtered = []
            for video in videos:
                views = video.get('view_count', 0) or 0
                if st.session_state.min_views <= views <= st.session_state.max_views:
                    videos_filtered.append(video)
            
            progress_bar.progress(60)
            status_text.text(f"⏳ Récupération des commentaires... (0/{len(videos_filtered)})")
            
            # AFFICHER LES VIDÉOS AVEC EXPANDERS
            st.success(f"✅ {len(videos_filtered)} vidéo(s) trouvée(s)!")
            st.divider()
            
            for idx, video in enumerate(videos_filtered, 1):
                progress_bar.progress(60 + int((idx / len(videos_filtered)) * 40))
                status_text.text(f"⏳ Récupération des commentaires... ({idx}/{len(videos_filtered)})")
                
                video_title = video['title']
                video_views = video.get('view_count', 0)
                video_channel = video.get('uploader', 'Inconnu')
                video_id = video['id']
                
                with st.expander(f"📹 Vidéo {idx}: {video_title} | 👁️ {video_views:,} vues"):
                    
                    st.write(f"**Canal:** {video_channel}")
                    st.write(f"👁️ **Vues:** {video_views:,}")
                    st.write(f"🔗 [Regarder sur YouTube](https://www.youtube.com/watch?v={video_id})")
                    st.divider()
                    
                    # SECTION COMMENTAIRES
                    st.write("### 💬 Top 20 Commentaires")
                    
                    try:
                        ydl_comments = YoutubeDL({
                            'quiet': True,
                            'no_warnings': True,
                            'skip_download': True,
                            'getcomments': True,
                        })
                        
                        video_info = ydl_comments.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
                        comments = video_info.get('comments', [])
                        
                        if comments and len(comments) > 0:
                            comments_sorted = sorted(comments, key=lambda x: x.get('likes', 0), reverse=True)[:20]
                            
                            for i, comment in enumerate(comments_sorted, 1):
                                author = comment.get('author', 'Anonyme')
                                text = comment.get('text', 'Texte non disponible')
                                likes = comment.get('likes', 0)
                                
                                st.write(f"**{i}. {author}** (👍 {likes})")
                                st.write(f"> {text}")
                                st.write("")
                            
                            all_comments = "\n\n".join([f"{i}. {c.get('author', 'Anonyme')}: {c.get('text', '')}" for i, c in enumerate(comments_sorted, 1)])
                            st.download_button(
                                label="📥 Télécharger commentaires",
                                data=all_comments,
                                file_name=f"commentaires_{video_id}.txt"
                            )
                        else:
                            st.info("⚠️ Aucun commentaire disponible")
                    
                    except Exception as e:
                        st.warning(f"⚠️ Erreur commentaires")
            
            progress_bar.progress(100)
            status_text.text("✅ Recherche terminée!")
        
        except Exception as e:
            st.error(f"❌ Erreur: {str(e)}")
