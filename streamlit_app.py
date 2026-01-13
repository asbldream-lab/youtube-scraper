import streamlit as st
from yt_dlp import YoutubeDL
import json
from datetime import datetime, timedelta
from collections import Counter
import re

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
    ["Auto (toutes langues)", "Français", "Anglais"]
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

# ANALYSE IA
st.sidebar.write("### 🎯 Analyse IA")
use_ai_analysis = st.sidebar.checkbox("Activer l'analyse automatique des gaps", value=True)

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
                
                search_limit = 15  # RÉDUIT pour vitesse
                
                if language == "Français":
                    ydl_opts_fast['extractor_args'] = {'youtube': {'lang': ['fr']}}
                    search_query = f"ytsearch{search_limit}:{keyword}"
                elif language == "Anglais":
                    ydl_opts_fast['extractor_args'] = {'youtube': {'lang': ['en']}}
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
            
            # RÉCUPÉRER COMMENTAIRES - OPTIMISÉ
            status.text("💬 Récupération commentaires...")
            progress_bar.progress(40)
            
            failed_videos = []
            
            for idx, video in enumerate(all_videos_filtered):
                progress_bar.progress(40 + int((idx / len(all_videos_filtered)) * 40))
                status.text(f"💬 Vidéo {idx+1}/{len(all_videos_filtered)}...")
                
                video_id = video['id']
                video_title = video['title']
                
                try:
                    ydl_comments = YoutubeDL({
                        'quiet': True,
                        'no_warnings': True,
                        'socket_timeout': 5,  # RÉDUIT pour vitesse
                        'getcomments': True,
                        'ignoreerrors': True,
                        'extractor_args': {'youtube': {'max_comments': ['20']}}  # RÉDUIT à 20
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
            
            # === GAUCHE: SECTION COPIE + ANALYSE IA ===
            with left_col:
                st.header("📋 Copie en bas")
                
                # ANALYSE IA - À LA DEMANDE
                if use_ai_analysis and all_comments_list:
                    st.subheader("🎯 Analyse IA des Gaps")
                    
                    if st.button("🤖 Lancer l'analyse IA", use_container_width=True):
                        with st.spinner("🤖 Analyse en cours..."):
                            # Préparer le texte des commentaires pour l'IA
                            comments_text = "\n\n".join([
                                f"{i+1}. {c['author']} ({c['likes']} likes): {c['text']}"
                                for i, c in enumerate(all_comments_list[:30])  # RÉDUIT à 30
                            ])
                            
                            ai_prompt = f"""Analyse ces commentaires YouTube et identifie en 150 mots MAX :

1. **Top 3 Sujets** principaux
2. **Top 3 Frustrations**
3. **Gaps** : Ce qui manque
4. **3 Idées de vidéos**

Commentaires:
{comments_text}

Réponds de façon ULTRA concise."""
                            
                            try:
                                # Appel API Claude
                                import requests
                                response = requests.post(
                                    "https://api.anthropic.com/v1/messages",
                                    headers={"Content-Type": "application/json"},
                                    json={
                                        "model": "claude-sonnet-4-20250514",
                                        "max_tokens": 500,  # RÉDUIT
                                        "messages": [{"role": "user", "content": ai_prompt}]
                                    },
                                    timeout=15  # RÉDUIT
                                )
                                
                                if response.status_code == 200:
                                    data = response.json()
                                    ai_analysis = data['content'][0]['text']
                                    st.success("✅ Analyse terminée!")
                                    st.markdown(ai_analysis)
                                else:
                                    st.warning("⚠️ Analyse IA indisponible")
                            except:
                                st.warning("⚠️ Analyse IA indisponible")
                    else:
                        st.info("👆 Clique sur le bouton pour lancer l'analyse IA")
                
                st.divider()
                
                # NUAGE DE MOTS - SIMPLIFIÉ
                st.subheader("☁️ Top 10 Mots")
                
                if all_comments_list:
                    # Extraire tous les mots
                    all_text = " ".join([c['text'] for c in all_comments_list])
                    # Nettoyer
                    words = re.findall(r'\b[a-zA-ZÀ-ÿ]{4,}\b', all_text.lower())
                    # Mots courants à exclure
                    stop_words = {'cette', 'pour', 'dans', 'avec', 'être', 'avoir', 'faire', 'dire',
                                  'this', 'that', 'with', 'from', 'have', 'been', 'what', 'your'}
                    words_filtered = [w for w in words if w not in stop_words]
                    
                    word_freq = Counter(words_filtered).most_common(10)  # RÉDUIT à 10
                    
                    # Affichage compact
                    words_display = " | ".join([f"{word} ({count})" for word, count in word_freq])
                    st.text(words_display)
                
                st.divider()
                
                # TEXTE À COPIER
                prompt = f"""*"Agis comme un Consultant en Stratégie YouTube Senior. Je te donne des données brutes (commentaires). Ignore les compliments simples. Cherche les problèmes.

Livrable attendu :
1. Le Top des Sujets : De quoi parle la majorité ?
2. Le Mur des Lamentations : De quoi se plaignent-ils ? (Frustrations).
3. Le "Gap" : Qu'est-ce qu'ils ont cherché dans la vidéo sans le trouver ? (Ce qui manque).
4. Le Plan d'Attaque : 3 Angles de vidéos qui comblent ces trous."*"""
                
                copy_text = prompt + "\n\n" + "="*50 + "\n"
                
                if all_comments_list:
                    copy_text += f"\nMots-clés recherchés: {', '.join(keywords_list)}\n"
                    copy_text += f"Nombre de vidéos analysées: {len(all_videos_filtered)}\n"
                    copy_text += f"Nombre total de commentaires: {len(all_comments_list)}\n\n"
                    copy_text += "="*50 + "\n\n"
                    
                    for i, comment in enumerate(all_comments_list, 1):
                        copy_text += f"{i}. {comment['author']} ({comment['likes']} likes) [Mot-clé: {comment['keyword']}]:\n{comment['text']}\n\n"
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
                    
                    # Calculer engagement
                    engagement = (likes / views * 100) if views > 0 else 0
                    
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
                    
                    with st.expander(f"Vidéo {idx}: {title} | 👁️ {views:,} | 📈 {engagement:.2f}%"):
                        st.write(f"**🔍 Mot-clé:** {keyword}")
                        st.write(f"**📺 Canal:** {channel}")
                        st.write(f"**👁️ Vues:** {views:,}")
                        st.write(f"**👍 Likes:** {likes:,}")
                        st.write(f"**📈 Engagement:** {engagement:.2f}%")
                        st.write(f"**⏱️ Durée:** {mins}min {secs}s")
                        st.write(f"**📅 Publié:** {date_str}")
                        st.write(f"**🔗** [Regarder](https://www.youtube.com/watch?v={video_id})")
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
