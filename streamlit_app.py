import streamlit as st
from yt_dlp import YoutubeDL

st.set_page_config(page_title="YouTube Scraper", layout="wide")
st.title("🎬 YouTube Keyword Research Tool")
st.write("Recherche des vidéos YouTube avec commentaires")

# INITIALISER SESSION STATE
if 'min_views' not in st.session_state:
    st.session_state.min_views = 0
    st.session_state.max_views = float('inf')
    st.session_state.selected_button = None

# SIDEBAR - PARAMÈTRES
st.sidebar.header("⚙️ Paramètres")

keyword = st.sidebar.text_input("🔍 Mot-clé:", placeholder="guerre en Irak")

st.sidebar.write("### 👁️ Vues minimum")
col1, col2, col3, col4 = st.sidebar.columns(4)

with col1:
    if st.sidebar.button("10K-50K", key="btn1"):
        st.session_state.min_views = 10000
        st.session_state.max_views = 50000
        st.session_state.selected_button = "btn1"

with col2:
    if st.sidebar.button("50K-100K", key="btn2"):
        st.session_state.min_views = 50000
        st.session_state.max_views = 100000
        st.session_state.selected_button = "btn2"

with col3:
    if st.sidebar.button("100K+", key="btn3"):
        st.session_state.min_views = 100000
        st.session_state.max_views = 10000000
        st.session_state.selected_button = "btn3"

with col4:
    if st.sidebar.button("1M+", key="btn4"):
        st.session_state.min_views = 1000000
        st.session_state.max_views = float('inf')
        st.session_state.selected_button = "btn4"

# AFFICHER LES BOUTONS SÉLECTIONNÉS
if st.session_state.selected_button == "btn1":
    st.sidebar.info("✅ 10K-50K sélectionné")
elif st.session_state.selected_button == "btn2":
    st.sidebar.info("✅ 50K-100K sélectionné")
elif st.session_state.selected_button == "btn3":
    st.sidebar.info("✅ 100K+ sélectionné")
elif st.session_state.selected_button == "btn4":
    st.sidebar.info("✅ 1M+ sélectionné")

# BOUTON RECHERCHE
if st.sidebar.button("🚀 Lancer la recherche", use_container_width=True):
    if not keyword:
        st.error("❌ Rentre un mot-clé!")
    else:
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        status_text.text("⏳ Recherche de vidéos...")
        progress_bar.progress(20)
        
        try:
            # RECHERCHE VIDÉOS (entre 10 et 20)
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': 'in_playlist',
            }
            
            with YoutubeDL(ydl_opts) as ydl:
                search_query = f"ytsearch15:{keyword}"
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
            
            st.success(f"✅ {len(videos_filtered)} vidéo(s) trouvée(s)!")
            st.divider()
            
            # LAYOUT PRINCIPAL
            left_col, right_col = st.columns([1, 2])
            
            # COLONNE DE GAUCHE - SECTION COPIE
            with left_col:
                st.header("📋 Section Copie")
                
                all_comments_text = ""
                
                prompt = """*"Agis comme un Consultant en Stratégie YouTube Senior. Je te donne des données brutes (commentaires). Ignore les compliments simples. Cherche les problèmes.

Livrable attendu :
1. Le Top des Sujets : De quoi parle la majorité ?
2. Le Mur des Lamentations : De quoi se plaignent-ils ? (Frustrations).
3. Le "Gap" : Qu'est-ce qu'ils ont cherché dans la vidéo sans le trouver ? (Ce qui manque).
4. Le Plan d'Attaque : 3 Angles de vidéos qui comblent ces trous."*"""
                
                st.write("### Prompt ChatGPT")
                st.text_area("", value=prompt, height=150, disabled=True)
                
                st.write("### 💬 Commentaires")
                
                # Récupérer tous les commentaires
                for idx, video in enumerate(videos_filtered, 1):
                    status_text.text(f"⏳ Récupération... ({idx}/{len(videos_filtered)})")
                    progress_bar.progress(60 + int((idx / len(videos_filtered)) * 30))
                    
                    video_id = video['id']
                    
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
                            
                            for comment in comments_sorted:
                                author = comment.get('author', 'Anonyme')
                                text = comment.get('text', '')
                                likes = comment.get('likes', 0)
                                
                                all_comments_text += f"{author} ({likes} likes): {text}\n"
                    
                    except:
                        pass
                
                # ZONE COPIE
                if all_comments_text:
                    final_text = prompt + "\n\n---\n\n" + all_comments_text
                    st.text_area("Copie-colle dans ChatGPT:", value=final_text, height=400)
                    
                    st.download_button(
                        label="📥 Télécharger",
                        data=final_text,
                        file_name="prompt_commentaires.txt"
                    )
            
            # COLONNE DE DROITE - VIDÉOS
            with right_col:
                st.header("📹 Résultats")
                
                for idx, video in enumerate(videos_filtered, 1):
                    video_title = video['title']
                    video_views = video.get('view_count', 0)
                    video_channel = video.get('uploader', 'Inconnu')
                    video_id = video['id']
                    
                    with st.expander(f"Vidéo {idx}: {video_title} | 👁️ {video_views:,}"):
                        
                        st.write(f"**Canal:** {video_channel}")
                        st.write(f"👁️ **Vues:** {video_views:,}")
                        st.write(f"🔗 [Regarder](https://www.youtube.com/watch?v={video_id})")
                        st.divider()
                        
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
                                    text = comment.get('text', '')
                                    likes = comment.get('likes', 0)
                                    
                                    st.write(f"**{i}. {author}** 👍 {likes}")
                                    st.write(f"> {text}")
                            else:
                                st.info("⚠️ Aucun commentaire")
                        
                        except:
                            st.warning("⚠️ Erreur")
            
            progress_bar.progress(100)
            status_text.text("✅ Terminé!")
        
        except Exception as e:
            st.error(f"❌ Erreur: {str(e)}")
