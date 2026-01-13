import streamlit as st
from yt_dlp import YoutubeDL
import json
from datetime import datetime, timedelta
import requests

st.set_page_config(page_title="YouTube Scraper Pro", layout="wide")
st.title("🚀 YouTube Keyword Research Tool PRO")

# Initialisation session state
if 'search_history' not in st.session_state:
    st.session_state.search_history = []

# ============ SIDEBAR ============
st.sidebar.header("⚙️ Paramètres")

# MULTI-MOTS-CLÉS
keywords_input = st.sidebar.text_area(
    "🔍 Mots-clés (un par ligne):",
    placeholder="guerre irak\nconflit moyen orient\ngéopolitique",
    help="Entre plusieurs mots-clés, un par ligne"
)
keywords_list = [k.strip() for k in keywords_input.split('\n') if k.strip()]

# LANGUE
language = st.sidebar.selectbox(
    "🌍 Langue:",
    ["Auto (toutes langues)", "Français", "Anglais", "Espagnol"]
)

# VUES
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

# RATIO ENGAGEMENT
st.sidebar.write("### 📈 Ratio Engagement")
use_engagement = st.sidebar.checkbox("Filtrer par engagement")
if use_engagement:
    min_engagement = st.sidebar.slider("Like/Vue minimum (%)", 0.0, 10.0, 1.0, 0.1)
else:
    min_engagement = 0.0

# DATE DE PUBLICATION
st.sidebar.write("### 📅 Date de publication")
date_filter = st.sidebar.selectbox(
    "Période:",
    ["Toutes", "7 derniers jours", "30 derniers jours", "6 derniers mois", "1 an"]
)

# DURÉE VIDÉO
st.sidebar.write("### ⏱️ Durée vidéo")
duration_filters = []
col_d1, col_d2, col_d3 = st.sidebar.columns(3)
with col_d1:
    if st.sidebar.checkbox("Court (<5min)"):
        duration_filters.append("short")
with col_d2:
    if st.sidebar.checkbox("Moyen (5-20min)"):
        duration_filters.append("medium")
with col_d3:
    if st.sidebar.checkbox("Long (20+min)"):
        duration_filters.append("long")

if selected_views:
    st.sidebar.success(f"✅ OK")

# ============ BOUTON RECHERCHE ============
if st.sidebar.button("🚀 Lancer", use_container_width=True):
    if not keywords_list:
        st.error("❌ Au moins un mot-clé requis!")
    elif not selected_views:
        st.error("❌ Sélectionne une gamme de vues!")
    else:
        progress_bar = st.progress(0)
        status = st.empty()
        
        # Calculer la date limite
        date_limit = None
        if date_filter == "7 derniers jours":
            date_limit = datetime.now() - timedelta(days=7)
        elif date_filter == "30 derniers jours":
            date_limit = datetime.now() - timedelta(days=30)
        elif date_filter == "6 derniers mois":
            date_limit = datetime.now() - timedelta(days=180)
        elif date_filter == "1 an":
            date_limit = datetime.now() - timedelta(days=365)
        
        all_videos_filtered = []
        all_comments_list = []
        
        try:
            # Boucle sur chaque mot-clé
            for keyword_idx, keyword in enumerate(keywords_list):
                status.text(f"🔍 Recherche: {keyword} ({keyword_idx+1}/{len(keywords_list)})")
                
                # RECHERCHE - ULTRA RAPIDE
                ydl_opts_fast = {
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': 'in_playlist',
                    'socket_timeout': 5,  # RÉDUIT
                    'ignoreerrors': True,
                }
                
                search_limit = 40  # Augmenté pour avoir plus de choix après filtrage langue
                
                if language == "Français":
                    ydl_opts_fast['extractor_args'] = {'youtube': {'lang': ['fr']}}
                    search_query = f"ytsearch{search_limit}:{keyword}"
                elif language == "Anglais":
                    ydl_opts_fast['extractor_args'] = {'youtube': {'lang': ['en']}}
                    search_query = f"ytsearch{search_limit}:{keyword}"
                elif language == "Espagnol":
                    ydl_opts_fast['extractor_args'] = {'youtube': {'lang': ['es']}}
                    search_query = f"ytsearch{search_limit}:{keyword}"
                else:
                    search_query = f"ytsearch{search_limit}:{keyword}"
                
                with YoutubeDL(ydl_opts_fast) as ydl:
                    results = ydl.extract_info(search_query, download=False)
                    video_ids = results.get('entries', [])
                
                video_ids = [v for v in video_ids if v is not None][:search_limit]
                
                progress_bar.progress(10 + int((keyword_idx / len(keywords_list)) * 10))
                
                # Récupérer métadonnées - PARALLÈLE
                status.text(f"📊 Stats: {keyword}")
                
                ydl_opts_views = {
                    'quiet': True,
                    'no_warnings': True,
                    'socket_timeout': 5,  # RÉDUIT
                    'ignoreerrors': True,
                    'skip_download': True,
                }
                
                videos = []
                for vid in video_ids:
                    try:
                        video_id = vid.get('id')
                        if not video_id:
                            continue
                        
                        with YoutubeDL(ydl_opts_views) as ydl:
                            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
                            if info:
                                info['search_keyword'] = keyword
                                videos.append(info)
                    except:
                        continue
                
                # FILTRAGE STRICT PAR LANGUE
                if language != "Auto (toutes langues)":
                    videos_temp = []
                    
                    for video in videos:
                        video_lang = video.get('language', '').lower()
                        title = video.get('title', '').lower()
                        description = video.get('description', '').lower() if video.get('description') else ''
                        uploader = video.get('uploader', '').lower()
                        
                        # Détection stricte par langue
                        if language == "Français":
                            # Indicateurs français
                            french_indicators = ['à', 'é', 'è', 'ê', 'ç', 'où', 'français', 'france']
                            is_french = (
                                video_lang in ['fr', 'fr-fr', 'fr-ca'] or
                                any(ind in title + description + uploader for ind in french_indicators) or
                                'fr' in uploader
                            )
                            # Exclure clairement anglais/espagnol
                            is_english = video_lang in ['en', 'en-us', 'en-gb'] or ' the ' in title or ' and ' in title
                            is_spanish = video_lang in ['es', 'es-es', 'es-mx'] or '¿' in title or '¡' in title
                            
                            if is_french and not is_english and not is_spanish:
                                videos_temp.append(video)
                        
                        elif language == "Anglais":
                            # Indicateurs anglais
                            is_english = (
                                video_lang in ['en', 'en-us', 'en-gb'] or
                                ' the ' in title or ' and ' in title or ' is ' in title
                            )
                            # Exclure français/espagnol
                            is_french = video_lang in ['fr', 'fr-fr'] or 'français' in title
                            is_spanish = video_lang in ['es', 'es-es'] or '¿' in title or '¡' in title
                            
                            if is_english and not is_french and not is_spanish:
                                videos_temp.append(video)
                        
                        elif language == "Espagnol":
                            # Indicateurs espagnol
                            spanish_indicators = ['¿', '¡', 'español', 'méxico', 'latinoamérica']
                            is_spanish = (
                                video_lang in ['es', 'es-es', 'es-mx', 'es-ar', 'es-co', 'es-cl'] or
                                any(ind in title + description + uploader for ind in spanish_indicators) or
                                'ñ' in title or 'ñ' in uploader
                            )
                            # Exclure clairement anglais/français
                            is_english = video_lang in ['en', 'en-us', 'en-gb'] or ' the ' in title
                            is_french = video_lang in ['fr', 'fr-fr'] or 'français' in title
                            
                            if is_spanish and not is_english and not is_french:
                                videos_temp.append(video)
                    
                    videos = videos_temp
                    st.info(f"🌍 {len(videos)} vidéos en {language} après filtrage strict")
                
                progress_bar.progress(20)
                
                # FILTRER PAR VUES
                for video in videos:
                    views = video.get('view_count', 0) or 0
                    likes = video.get('like_count', 0) or 0
                    duration = video.get('duration', 0) or 0
                    upload_date = video.get('upload_date')
                    
                    # Filtre vues
                    match_views = False
                    for min_v, max_v, _ in selected_views:
                        if min_v <= views <= max_v:
                            match_views = True
                            break
                    
                    if not match_views:
                        continue
                    
                    # Filtre engagement
                    if use_engagement and views > 0:
                        engagement_ratio = (likes / views) * 100
                        if engagement_ratio < min_engagement:
                            continue
                    
                    # Filtre date
                    if date_limit and upload_date:
                        try:
                            video_date = datetime.strptime(upload_date, '%Y%m%d')
                            if video_date < date_limit:
                                continue
                        except:
                            pass
                    
                    # Filtre durée
                    if duration_filters:
                        duration_match = False
                        if "short" in duration_filters and duration < 300:  # <5min
                            duration_match = True
                        if "medium" in duration_filters and 300 <= duration <= 1200:  # 5-20min
                            duration_match = True
                        if "long" in duration_filters and duration > 1200:  # 20+min
                            duration_match = True
                        
                        if not duration_match:
                            continue
                    
                    all_videos_filtered.append(video)
            
            if len(all_videos_filtered) == 0:
                st.error(f"❌ Aucune vidéo trouvée avec tous les filtres.")
                st.stop()
            
            st.success(f"✅ {len(all_videos_filtered)} vidéo(s) trouvée(s) pour {len(keywords_list)} mot(s)-clé(s)!")
            st.divider()
            
            # RÉCUPÉRER COMMENTAIRES + SOUS-TITRES
            status.text("💬 Récupération commentaires + sous-titres...")
            progress_bar.progress(40)
            
            failed_videos = []
            
            for idx, video in enumerate(all_videos_filtered):
                progress_bar.progress(40 + int((idx / len(all_videos_filtered)) * 40))
                status.text(f"💬 Vidéo {idx+1}/{len(all_videos_filtered)}...")
                
                video_id = video['id']
                video_title = video['title']
                
                # RÉCUPÉRER SOUS-TITRES (HOOK)
                hook_text = ""
                try:
                    ydl_subs = YoutubeDL({
                        'quiet': True,
                        'no_warnings': True,
                        'socket_timeout': 5,
                        'writesubtitles': True,
                        'writeautomaticsub': True,
                        'subtitleslangs': ['fr', 'en', 'es'],  # Ajout espagnol
                        'skip_download': True,
                        'ignoreerrors': True,
                    })
                    
                    info_subs = ydl_subs.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
                    
                    # Chercher les sous-titres
                    subtitles = info_subs.get('subtitles', {})
                    auto_subs = info_subs.get('automatic_captions', {})
                    
                    # Essayer français, anglais, espagnol
                    subtitle_data = None
                    for lang in ['fr', 'en', 'es', 'fr-FR', 'en-US', 'es-ES']:
                        if lang in subtitles:
                            subtitle_data = subtitles[lang]
                            break
                        elif lang in auto_subs:
                            subtitle_data = auto_subs[lang]
                            break
                    
                    # Extraire le texte des 30 premières secondes (hook)
                    if subtitle_data:
                        # Prendre le premier format (généralement json3)
                        sub_url = subtitle_data[0]['url'] if subtitle_data else None
                        if sub_url:
                            response = requests.get(sub_url, timeout=5)
                            if response.status_code == 200:
                                try:
                                    # Format json3
                                    sub_json = json.loads(response.text)
                                    events = sub_json.get('events', [])
                                    hook_sentences = []
                                    for event in events[:10]:  # ~30 premières secondes
                                        if 'segs' in event:
                                            text = ''.join([seg.get('utf8', '') for seg in event['segs']])
                                            if text.strip():
                                                hook_sentences.append(text.strip())
                                    hook_text = ' '.join(hook_sentences[:5])  # 5 premières phrases max
                                except:
                                    pass
                except:
                    pass
                
                # Stocker le hook dans la vidéo
                video['hook'] = hook_text if hook_text else "Sous-titres non disponibles"
                
                # RÉCUPÉRER COMMENTAIRES
                try:
                    ydl_comments = YoutubeDL({
                        'quiet': True,
                        'no_warnings': True,
                        'socket_timeout': 5,
                        'getcomments': True,
                        'ignoreerrors': True,
                        'extractor_args': {'youtube': {'max_comments': ['20']}}
                    })
                    
                    info = ydl_comments.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
                    comments = info.get('comments', [])
                    
                    if comments:
                        comments_sorted = sorted(comments, key=lambda x: x.get('like_count', 0) or 0, reverse=True)[:20]
                        
                        for comment in comments_sorted:
                            all_comments_list.append({
                                'video': video_title,
                                'video_id': video_id,
                                'keyword': video.get('search_keyword', ''),
                                'author': comment.get('author', 'Anonyme'),
                                'text': comment.get('text', ''),
                                'likes': comment.get('like_count', 0) or 0
                            })
                    else:
                        failed_videos.append(video_title)
                except:
                    failed_videos.append(video_title)
                    continue
            
            progress_bar.progress(90)
            
            # SAUVEGARDER DANS HISTORIQUE
            history_entry = {
                'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'keywords': keywords_list,
                'videos_found': len(all_videos_filtered),
                'comments_found': len(all_comments_list)
            }
            st.session_state.search_history.append(history_entry)
            
            # LAYOUT
            left_col, right_col = st.columns([1, 2])
            
            # === GAUCHE: SECTION COPIE ===
            with left_col:
                st.header("📋 Copie en bas")
                
                st.divider()
                
                # TEXTE À COPIER
                prompt = """Rôle : Tu es un expert en analyse de données sociales et en stratégie de contenu vidéo. Ton but est d'analyser les commentaires et les premières phrases des vidéos concurrentes pour en extraire une stratégie éditoriale unique.

Contraintes de réponse :
* Chaque section doit avoir le titre indiqué.
* Chaque réponse sous les titres doit faire maximum 2 phrases.
* Le ton doit être direct, efficace et sans remplissage.

Instructions d'analyse :
1. Angle de réponse stratégique : Identifie l'approche globale à adopter pour répondre aux attentes ou aux frustrations des utilisateurs.
2. Top 5 des idées récurrentes : Liste les 5 thèmes ou arguments qui reviennent le plus souvent dans les commentaires.
3. Sujets périphériques et opportunités : Propose des sujets connexes mentionnés par l'audience pour de futures vidéos.
4. Éléments indispensables pour la vidéo : Liste les points précis ou questions auxquels tu dois absolument répondre.
5. Analyse des accroches et nouveaux Hooks : Analyse la structure des phrases de début fournies pour proposer 3 nouveaux hooks originaux et percutants sans jamais copier les originaux.

Voici les commentaires :"""
                
                copy_text = prompt + "\n\n" + "="*50 + "\n"
                
                if all_comments_list:
                    copy_text += f"\nMots-clés recherchés: {', '.join(keywords_list)}\n"
                    copy_text += f"Nombre de vidéos analysées: {len(all_videos_filtered)}\n"
                    copy_text += f"Nombre total de commentaires: {len(all_comments_list)}\n\n"
                    copy_text += "="*50 + "\n\n"
                    
                    for i, comment in enumerate(all_comments_list, 1):
                        copy_text += f"{i}. {comment['author']} ({comment['likes']} likes) [Mot-clé: {comment['keyword']}]:\n{comment['text']}\n\n"
                    
                    # AJOUTER LES HOOKS À LA FIN
                    copy_text += "\n" + "="*50 + "\n"
                    copy_text += "PHRASES - HOOK (premières phrases des vidéos):\n"
                    copy_text += "="*50 + "\n\n"
                    
                    for idx, video in enumerate(all_videos_filtered, 1):
                        hook = video.get('hook', 'Non disponible')
                        copy_text += f"Vidéo {idx} - {video.get('title', 'Sans titre')[:60]}...\n"
                        copy_text += f"Hook: {hook}\n\n"
                else:
                    copy_text += "\n[Aucun commentaire trouvé]"
                
                st.text_area("Copie-colle ceci dans ChatGPT:", value=copy_text, height=400, key="copy_area")
            
            # === DROITE: VIDÉOS ===
            with right_col:
                st.header(f"📹 Vidéos ({len(all_videos_filtered)} trouvées)")
                
                for idx, video in enumerate(all_videos_filtered, 1):
                    title = video.get('title', 'Sans titre')
                    views = video.get('view_count', 0) or 0
                    likes = video.get('like_count', 0) or 0
                    duration = video.get('duration', 0) or 0
                    channel = video.get('uploader', 'Inconnu')
                    video_id = video.get('id', '')
                    keyword = video.get('search_keyword', '')
                    upload_date = video.get('upload_date', '')
                    subscribers = video.get('channel_follower_count', 0) or 0
                    hook = video.get('hook', 'Non disponible')
                    
                    # Calculer engagement
                    engagement = (likes / views * 100) if views > 0 else 0
                    
                    # CALCULER SCORE DE VIRALITÉ
                    virality_stars = ""
                    if subscribers > 0:
                        if views >= subscribers:
                            virality_stars = "⭐⭐⭐"
                        elif views >= subscribers * 0.5:
                            virality_stars = "⭐⭐"
                        elif views >= subscribers * 0.2:
                            virality_stars = "⭐"
                        else:
                            virality_stars = "—"
                    else:
                        virality_stars = "N/A"
                    
                    # Formater durée
                    mins = duration // 60
                    secs = duration % 60
                    
                    # Formater date
                    date_str = ""
                    if upload_date:
                        try:
                            date_obj = datetime.strptime(upload_date, '%Y%m%d')
                            date_str = date_obj.strftime('%d/%m/%Y')
                        except:
                            date_str = upload_date
                    
                    video_comments = [c for c in all_comments_list if c['video_id'] == video_id]
                    
                    with st.expander(f"Vidéo {idx}: {title} | 👁️ {views:,} | 📈 {engagement:.2f}% | 🔥 {virality_stars}"):
                        # AFFICHER LA THUMBNAIL
                        thumbnail_url = video.get('thumbnail', '')
                        if thumbnail_url:
                            col_thumb, col_info = st.columns([1, 2])
                            with col_thumb:
                                st.image(thumbnail_url, caption="Miniature", use_container_width=True)
                            with col_info:
                                st.write(f"**🔍 Mot-clé:** {keyword}")
                                st.write(f"**📺 Canal:** {channel} ({subscribers:,} abonnés)")
                                st.write(f"**👁️ Vues:** {views:,}")
                                st.write(f"**👍 Likes:** {likes:,}")
                                st.write(f"**📈 Engagement:** {engagement:.2f}%")
                                st.write(f"**🔥 Viralité:** {virality_stars}")
                                st.write(f"**⏱️ Durée:** {mins}min {secs}s")
                                st.write(f"**📅 Publié:** {date_str}")
                                st.write(f"**🔗** [Regarder](https://www.youtube.com/watch?v={video_id})")
                        else:
                            st.write(f"**🔍 Mot-clé:** {keyword}")
                            st.write(f"**📺 Canal:** {channel} ({subscribers:,} abonnés)")
                            st.write(f"**👁️ Vues:** {views:,}")
                            st.write(f"**👍 Likes:** {likes:,}")
                            st.write(f"**📈 Engagement:** {engagement:.2f}%")
                            st.write(f"**🔥 Viralité:** {virality_stars}")
                            st.write(f"**⏱️ Durée:** {mins}min {secs}s")
                            st.write(f"**📅 Publié:** {date_str}")
                            st.write(f"**🔗** [Regarder](https://www.youtube.com/watch?v={video_id})")
                        
                        st.divider()
                        st.write("### 🎯 HOOK (Premières phrases)")
                        st.info(hook)
                        
                        st.divider()
                        st.write("### 💬 Top 20 Commentaires (par likes)")
                        
                        if video_comments:
                            for i, comment in enumerate(video_comments, 1):
                                st.write(f"**{i}. {comment['author']}** 👍 {comment['likes']}")
                                st.write(f"> {comment['text']}")
                                st.write("")
                        else:
                            st.info("⚠️ Aucun commentaire disponible pour cette vidéo")
            
            progress_bar.progress(100)
            status.text("✅ Terminé!")
        
        except Exception as e:
            st.error(f"❌ Erreur: {str(e)}")
            st.exception(e)

# ============ HISTORIQUE ============
if st.session_state.search_history:
    with st.expander("📚 Historique des recherches"):
        for i, entry in enumerate(reversed(st.session_state.search_history[-10:]), 1):
            st.write(f"**{i}. {entry['date']}**")
            st.write(f"   🔍 Mots-clés: {', '.join(entry['keywords'])}")
            st.write(f"   📹 {entry['videos_found']} vidéos | 💬 {entry['comments_found']} commentaires")
            st.divider()
