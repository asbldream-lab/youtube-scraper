import streamlit as st
from yt_dlp import YoutubeDL

st.set_page_config(page_title="YouTube Scraper", layout="wide")
st.title("🎬 YouTube Keyword Research Tool")

if 'selected_views' not in st.session_state:
    st.session_state.selected_views = []

# SIDEBAR
st.sidebar.header("⚙️ Paramètres")
keyword = st.sidebar.text_input("🔍 Mot-clé:", placeholder="guerre en Irak")

# Option de langue
language = st.sidebar.selectbox(
    "🌍 Langue de recherche:",
    ["Auto (toutes langues)", "Français", "Anglais"],
    help="Choisir la langue des vidéos à rechercher"
)

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
            # RECHERCHE YouTube
            ydl_opts = {
                'quiet': True, 
                'no_warnings': True, 
                'socket_timeout': 20,
                'ignoreerrors': True,  # IMPORTANT : ignorer les vidéos avec restrictions
                'age_limit': None,  # Essayer quand même les vidéos avec restrictions d'âge
            }
            
            # Nombre de résultats selon la langue
            search_limit = 50  # Réduit pour la rapidité
            
            # Configuration de la langue pour YouTube
            if language == "Français":
                ydl_opts['extractor_args'] = {'youtube': {'lang': ['fr']}}
                search_query = f"ytsearch{search_limit}:{keyword}"
            elif language == "Anglais":
                ydl_opts['extractor_args'] = {'youtube': {'lang': ['en']}}
                search_query = f"ytsearch{search_limit}:{keyword}"
            else:  # Auto
                search_query = f"ytsearch{search_limit}:{keyword}"
            
            status.text("🔍 Recherche et extraction des métadonnées...")
            
            with YoutubeDL(ydl_opts) as ydl:
                results = ydl.extract_info(search_query, download=False)
                videos = results.get('entries', [])
            
            # Filtrer les vidéos None (celles qui ont échoué)
            videos = [v for v in videos if v is not None]
            
            st.info(f"🔍 {len(videos)} vidéos trouvées sur YouTube")
            
            # Debug : afficher combien ont des vues
            videos_with_views = [v for v in videos if v.get('view_count', 0)]
            st.info(f"📊 {len(videos_with_views)} vidéos avec info de vues")
            
            # Pour le français ou Auto, on garde TOUTES les vidéos
            # Pour l'anglais, on filtre légèrement
            if language == "Anglais":
                videos_temp = []
                for video in videos:
                    video_lang = video.get('language', '').lower()
                    if video_lang != 'fr':
                        videos_temp.append(video)
                
                if len(videos_temp) >= 5:
                    videos = videos_temp
                    st.info(f"🌍 {len(videos)} vidéos après filtre langue")
            
            progress_bar.progress(20)
            
            # FILTRER PAR VUES - Strict!
            videos_filtered = []
            debug_info = []  # Pour voir ce qui se passe
            
            for video in videos:
                views = video.get('view_count', 0) or 0
                debug_info.append(f"{video.get('title', 'Sans titre')[:50]}... = {views:,} vues")
                
                for min_v, max_v, label in selected_views:
                    if min_v <= views <= max_v:
                        videos_filtered.append(video)
                        break
            
            # Afficher quelques exemples pour debug
            with st.expander("🔍 Debug : Vues des premières vidéos trouvées"):
                for info in debug_info[:10]:
                    st.text(info)
            
            if len(videos_filtered) == 0:
                st.error(f"❌ Aucune vidéo trouvée avec les filtres de vues sélectionnés.")
                st.warning("💡 Essaye de sélectionner d'autres gammes de vues ou change le mot-clé")
                st.stop()
            
            st.success(f"✅ {len(videos_filtered)} vidéo(s) trouvée(s)!")
            st.divider()
            
            # RÉCUPÉRER TOUS LES COMMENTAIRES
            status.text("💬 Récupération commentaires...")
            progress_bar.progress(40)
            
            all_comments_list = []
            failed_videos = []
            
            for idx, video in enumerate(videos_filtered):
                progress_bar.progress(40 + int((idx / len(videos_filtered)) * 40))
                status.text(f"💬 Vidéo {idx+1}/{len(videos_filtered)}...")
                
                video_id = video['id']
                video_title = video['title']
                
                try:
                    ydl_comments = YoutubeDL({
                        'quiet': True,
                        'no_warnings': True,
                        'socket_timeout': 20,
                        'getcomments': True,
                        'extractor_args': {'youtube': {'max_comments': ['100']}}
                    })
                    
                    info = ydl_comments.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
                    comments = info.get('comments', [])
                    
                    if comments:
                        # Trier par likes et prendre le top 20
                        comments_sorted = sorted(comments, key=lambda x: x.get('like_count', 0) or 0, reverse=True)[:20]
                        
                        for comment in comments_sorted:
                            all_comments_list.append({
                                'video': video_title,
                                'video_id': video_id,
                                'author': comment.get('author', 'Anonyme'),
                                'text': comment.get('text', ''),
                                'likes': comment.get('like_count', 0) or 0
                            })
                    else:
                        failed_videos.append(video_title)
                        
                except Exception as e:
                    failed_videos.append(f"{video_title} (Erreur: {str(e)})")
                    continue
            
            progress_bar.progress(90)
            
            # Afficher les vidéos sans commentaires
            if failed_videos:
                with st.expander(f"⚠️ {len(failed_videos)} vidéo(s) sans commentaires"):
                    for video_name in failed_videos:
                        st.write(f"- {video_name}")
            
            # LAYOUT
            left_col, right_col = st.columns([1, 2])
            
            # === GAUCHE: SECTION COPIE ===
            with left_col:
                st.header("📋 Copie en bas")
                
                prompt = """*"Agis comme un Consultant en Stratégie YouTube Senior. Je te donne des données brutes (commentaires). Ignore les compliments simples. Cherche les problèmes.

Livrable attendu :
1. Le Top des Sujets : De quoi parle la majorité ?
2. Le Mur des Lamentations : De quoi se plaignent-ils ? (Frustrations).
3. Le "Gap" : Qu'est-ce qu'ils ont cherché dans la vidéo sans le trouver ? (Ce qui manque).
4. Le Plan d'Attaque : 3 Angles de vidéos qui comblent ces trous."*"""
                
                # CONSTRUIRE LE TEXTE À COPIER
                copy_text = prompt + "\n\n" + "="*50 + "\n"
                
                if all_comments_list:
                    copy_text += f"\nMot-clé recherché: {keyword}\n"
                    copy_text += f"Nombre de vidéos analysées: {len(videos_filtered)}\n"
                    copy_text += f"Nombre total de commentaires: {len(all_comments_list)}\n\n"
                    copy_text += "="*50 + "\n\n"
                    
                    for i, comment in enumerate(all_comments_list, 1):
                        copy_text += f"{i}. {comment['author']} ({comment['likes']} likes):\n{comment['text']}\n\n"
                else:
                    copy_text += "\n[Aucun commentaire trouvé]"
                
                # AFFICHER LA ZONE DE COPIE
                st.text_area("Copie-colle ceci dans ChatGPT:", value=copy_text, height=600, key="copy_area")
            
            # === DROITE: VIDÉOS ===
            with right_col:
                st.header(f"📹 Vidéos ({len(videos_filtered)} trouvées)")
                
                for idx, video in enumerate(videos_filtered, 1):
                    title = video['title']
                    views = video.get('view_count', 0) or 0
                    channel = video.get('uploader', 'Inconnu')
                    video_id = video['id']
                    
                    # Compter les commentaires pour cette vidéo
                    video_comments = [c for c in all_comments_list if c['video_id'] == video_id]
                    
                    with st.expander(f"Vidéo {idx}: {title} | 👁️ {views:,} | 💬 {len(video_comments)} commentaires"):
                        st.write(f"**Canal:** {channel}")
                        st.write(f"👁️ **Vues:** {views:,}")
                        st.write(f"🔗 [Regarder](https://www.youtube.com/watch?v={video_id})")
                        st.divider()
                        st.write("### 💬 Top 20 Commentaires (par likes)")
                        
                        if video_comments:
                            for i, comment in enumerate(video_comments, 1):
                                st.write(f"**{i}. {comment['author']}** 👍 {comment['likes']}")
                                st.write(f"> {comment['text']}")
                                st.write("")  # Espacement
                        else:
                            st.info("⚠️ Aucun commentaire disponible pour cette vidéo")
            
            progress_bar.progress(100)
            status.text("✅ Terminé!")
        
        except Exception as e:
            st.error(f"❌ Erreur: {str(e)}")
            st.exception(e)  # Afficher la trace complète de l'erreur
