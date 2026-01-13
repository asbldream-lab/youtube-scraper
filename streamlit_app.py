import streamlit as st
from yt_dlp import YoutubeDL

st.set_page_config(page_title="YouTube Scraper", layout="wide")
st.title("🎬 YouTube Keyword Research Tool")

if 'selected_views' not in st.session_state:
    st.session_state.selected_views = []

# SIDEBAR
st.sidebar.header("⚙️ Paramètres")
keyword = st.sidebar.text_input("🔍 Mot-clé:", placeholder="guerre en Irak")

st.sidebar.write("### 👁️ Vues minimum")
col1, col2, col3, col4 = st.sidebar.columns(4)

selected_views = []

with col1:
    if st.sidebar.checkbox("10K-50K"):
        selected_views.append((10000, 50000, "10K-50K"))

with col2:
    if st.sidebar.checkbox("50K-100K"):
        selected_views.append((50000, 100000, "50K-100K"))

with col3:
    if st.sidebar.checkbox("100K+"):
        selected_views.append((100000, 10000000, "100K+"))

with col4:
    if st.sidebar.checkbox("1M+"):
        selected_views.append((1000000, float('inf'), "1M+"))

if selected_views:
    st.sidebar.success(f"✅ OK")

# BOUTON RECHERCHE
if st.sidebar.button("🚀 Lancer", use_container_width=True):
    if not keyword:
        st.error("❌ Mot-clé requis!")
    elif not selected_views:
        st.error("❌ Sélectionne une gamme!")
    else:
        progress_bar = st.progress(0)
        status = st.empty()
        
        status.text("🔍 Recherche vidéos...")
        
        try:
            # RECHERCHE
            ydl_opts = {'quiet': True, 'no_warnings': True, 'extract_flat': 'in_playlist'}
            
            with YoutubeDL(ydl_opts) as ydl:
                results = ydl.extract_info(f"ytsearch15:{keyword}", download=False)
                videos = results.get('entries', [])
            
            # FILTRER
            videos_filtered = []
            for video in videos:
                views = video.get('view_count', 0) or 0
                for min_v, max_v, _ in selected_views:
                    if min_v <= views <= max_v:
                        videos_filtered.append(video)
                        break
            
            st.success(f"✅ {len(videos_filtered)} vidéo(s)!")
            st.divider()
            
            # RÉCUPÉRER TOUS LES COMMENTAIRES
            status.text("💬 Récupération commentaires...")
            progress_bar.progress(40)
            
            all_comments_list = []
            
            for idx, video in enumerate(videos_filtered):
                progress_bar.progress(40 + int((idx / len(videos_filtered)) * 40))
                status.text(f"💬 Vidéo {idx+1}/{len(videos_filtered)}...")
                
                video_id = video['id']
                video_title = video['title']
                
                try:
                    ydl = YoutubeDL({
                        'quiet': True,
                        'no_warnings': True,
                        'socket_timeout': 10,
                    })
                    
                    info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
                    comments = info.get('comments', [])
                    
                    if comments:
                        comments_sorted = sorted(comments, key=lambda x: x.get('likes', 0), reverse=True)[:20]
                        
                        for comment in comments_sorted:
                            all_comments_list.append({
                                'video': video_title,
                                'author': comment.get('author', 'Anonyme'),
                                'text': comment.get('text', ''),
                                'likes': comment.get('likes', 0)
                            })
                except:
                    pass
            
            progress_bar.progress(90)
            
            # LAYOUT
            left_col, right_col = st.columns([1, 2])
            
            # === GAUCHE: SECTION COPIE ===
            with left_col:
                st.header("📋 Copie")
                
                prompt = """*"Agis comme un Consultant en Stratégie YouTube Senior. Je te donne des données brutes (commentaires). Ignore les compliments simples. Cherche les problèmes.

Livrable attendu :
1. Le Top des Sujets : De quoi parle la majorité ?
2. Le Mur des Lamentations : De quoi se plaignent-ils ? (Frustrations).
3. Le "Gap" : Qu'est-ce qu'ils ont cherché dans la vidéo sans le trouver ? (Ce qui manque).
4. Le Plan d'Attaque : 3 Angles de vidéos qui comblent ces trous."*"""
                
                # CONSTRUIRE LE TEXTE À COPIER
                copy_text = prompt + "\n\n" + "="*50 + "\n"
                
                if all_comments_list:
                    for i, comment in enumerate(all_comments_list, 1):
                        copy_text += f"\n{i}. {comment['author']} ({comment['likes']} likes):\n{comment['text']}\n"
                else:
                    copy_text += "\n[Aucun commentaire trouvé]"
                
                # AFFICHER LA ZONE DE COPIE
                st.text_area("Copie-colle ceci dans ChatGPT:", value=copy_text, height=600)
                
                # BOUTON TÉLÉCHARGER
                st.download_button(
                    label="📥 Télécharger",
                    data=copy_text,
                    file_name="prompt_commentaires.txt"
                )
            
            # === DROITE: VIDÉOS ===
            with right_col:
                st.header("📹 Vidéos")
                
                for idx, video in enumerate(videos_filtered, 1):
                    title = video['title']
                    views = video.get('view_count', 0)
                    channel = video.get('uploader', 'Inconnu')
                    video_id = video['id']
                    
                    with st.expander(f"Vidéo {idx}: {title} | 👁️ {views:,}"):
                        st.write(f"**Canal:** {channel}")
                        st.write(f"👁️ **Vues:** {views:,}")
                        st.write(f"🔗 [Regarder](https://www.youtube.com/watch?v={video_id})")
                        st.divider()
                        st.write("### 💬 Top 20 Commentaires")
                        
                        # AFFICHER LES COMMENTAIRES DE CETTE VIDÉO
                        video_comments = [c for c in all_comments_list if c['video'] == title]
                        
                        if video_comments:
                            for i, comment in enumerate(video_comments, 1):
                                st.write(f"**{i}. {comment['author']}** 👍 {comment['likes']}")
                                st.write(f"> {comment['text']}")
                        else:
                            st.info("⚠️ Aucun commentaire")
            
            progress_bar.progress(100)
            status.text("✅ Terminé!")
        
        except Exception as e:
            st.error(f"❌ Erreur: {str(e)}")
