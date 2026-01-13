import streamlit as st
from yt_dlp import YoutubeDL
from concurrent.futures import ThreadPoolExecutor, as_completed

st.set_page_config(page_title="YouTube Scraper", layout="wide")
st.title("🎬 YouTube Keyword Research Tool")
st.write("Recherche rapide avec commentaires")

# INITIALISER SESSION STATE
if 'selected_views' not in st.session_state:
    st.session_state.selected_views = []

# SIDEBAR - PARAMÈTRES
st.sidebar.header("⚙️ Paramètres")

keyword = st.sidebar.text_input("🔍 Mot-clé:", placeholder="guerre en Irak")

st.sidebar.write("### 👁️ Vues minimum (multi-sélection)")
col1, col2, col3, col4 = st.sidebar.columns(4)

selected_views = []

with col1:
    if st.sidebar.checkbox("10K-50K", key="cb1"):
        selected_views.append((10000, 50000, "10K-50K"))

with col2:
    if st.sidebar.checkbox("50K-100K", key="cb2"):
        selected_views.append((50000, 100000, "50K-100K"))

with col3:
    if st.sidebar.checkbox("100K+", key="cb3"):
        selected_views.append((100000, 10000000, "100K+"))

with col4:
    if st.sidebar.checkbox("1M+", key="cb4"):
        selected_views.append((1000000, float('inf'), "1M+"))

if selected_views:
    selected_text = ", ".join([v[2] for v in selected_views])
    st.sidebar.success(f"✅ Sélection: {selected_text}")

# FONCTION COMMENTAIRES RAPIDE
def get_comments_fast(video_id):
    try:
        ydl_comments = YoutubeDL({
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
        })
        
        video_info = ydl_comments.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
        comments = video_info.get('comments', [])
        
        if comments and len(comments) > 0:
            comments_sorted = sorted(comments, key=lambda x: x.get('likes', 0), reverse=True)[:20]
            return comments_sorted
        return []
    except:
        return []

# BOUTON RECHERCHE
if st.sidebar.button("🚀 Lancer la recherche", use_container_width=True):
    if not keyword:
        st.error("❌ Rentre un mot-clé!")
    elif not selected_views:
        st.error("❌ Sélectionne au moins une gamme!")
    else:
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        status_text.text("⏳ Recherche...")
        progress_bar.progress(15)
        
        try:
            # RECHERCHE VIDÉOS
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': 'in_playlist',
            }
            
            with YoutubeDL(ydl_opts) as ydl:
                search_query = f"ytsearch15:{keyword}"
                results = ydl.extract_info(search_query, download=False)
                videos = results.get('entries', [])
            
            progress_bar.progress(30)
            
            # FILTRER PAR VUES (MULTI)
            videos_filtered = []
            for video in videos:
                views = video.get('view_count', 0) or 0
                
                for min_v, max_v, label in selected_views:
                    if min_v <= views <= max_v:
                        videos_filtered.append(video)
                        break
            
            progress_bar.progress(50)
            
            st.success(f"✅ {len(videos_filtered)} vidéo(s)!")
            st.divider()
            
            # LAYOUT
            left_col, right_col = st.columns([1, 2])
            
            # GAUCHE - COPIE
            with left_col:
                st.header("📋 Copie")
                
                all_comments_text = ""
                
                prompt = """*"Agis comme un Consultant en Stratégie YouTube Senior. Je te donne des données brutes (commentaires). Ignore les compliments simples. Cherche les problèmes.

Livrable attendu :
1. Le Top des Sujets : De quoi parle la majorité ?
2. Le Mur des Lamentations : De quoi se plaignent-ils ? (Frustrations).
3. Le "Gap" : Qu'est-ce qu'ils ont cherché dans la vidéo sans le trouver ? (Ce qui manque).
4. Le Plan d'Attaque : 3 Angles de vidéos qui comblent ces trous."*"""
                
                st.text_area("Prompt", value=prompt, height=150, disabled=True)
                st.write("### 💬 Commentaires")
                
                status_text.text("⏳ Récupération commentaires...")
                
                # PARALLÈLE (ultra rapide)
                with ThreadPoolExecutor(max_workers=5) as executor:
                    futures = {executor.submit(get_comments_fast, v['id']): v for v in videos_filtered}
                    
                    for i, future in enumerate(as_completed(futures)):
                        progress_bar.progress(50 + int((i / len(videos_filtered)) * 40))
                        comments = future.result()
                        
                        for comment in comments:
                            author = comment.get('author', 'Anonyme')
                            text = comment.get('text', '')
                            likes = comment.get('likes', 0)
                            
                            all_comments_text += f"{author} ({likes} likes): {text}\n"
                
                # ZONE COPIE
                if all_comments_text:
                    final_text = prompt + "\n\n---\n\n" + all_comments_text
                    st.text_area("Copie-colle:", value=final_text, height=400)
                    
                    st.download_button(
                        label="📥 Télécharger",
                        data=final_text,
                        file_name="prompt_commentaires.txt"
                    )
            
            # DROITE - VIDÉOS
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
                        st.write("### 💬 Top 20")
                        
                        # LAZY LOADING
                        comments = get_comments_fast(video_id)
                        
                        if comments:
                            for i, comment in enumerate(comments, 1):
                                author = comment.get('author', 'Anonyme')
                                text = comment.get('text', '')
                                likes = comment.get('likes', 0)
                                
                                st.write(f"**{i}. {author}** 👍 {likes}")
                                st.write(f"> {text}")
                        else:
                            st.info("⚠️ Aucun commentaire")
            
            progress_bar.progress(100)
            status_text.text("✅ Fini!")
        
        except Exception as e:
            st.error(f"❌ Erreur: {str(e)}")
