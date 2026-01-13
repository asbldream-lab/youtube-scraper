import streamlit as st
from yt_dlp import YoutubeDL
import json
from datetime import datetime, timedelta
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# Détection de langue robuste
try:
    from langdetect import detect, LangDetectException
    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False
    st.warning("⚠️ Pour un filtrage de langue optimal, installez langdetect: `pip install langdetect`")

st.set_page_config(page_title="YouTube Scraper Pro", layout="wide")
st.title("🚀 YouTube Keyword Research Tool PRO")

# ============ SIDEBAR ============
st.sidebar.header("⚙️ Paramètres")

# MULTI-MOTS-CLÉS
st.sidebar.write("### 🔍 Mots-clés")
st.sidebar.info("💡 **Recherche stricte avec guillemets** :\n- `guerre irak` → recherche normale\n- `\"guerre starlink\"` → TOUS les mots doivent être présents !")

keywords_input = st.sidebar.text_area(
    "Entre un mot-clé par ligne :",
    placeholder="guerre irak\n\"conflit starlink\"\ngéopolitique",
    help="Mets des guillemets pour forcer la présence de TOUS les mots"
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
                
                # Récupérer métadonnées - MULTITHREADING ⚡
                status.text(f"📊 Stats: {keyword} (parallèle)...")
                
                def fetch_video_metadata(vid, keyword):
                    """Fonction pour récupérer les métadonnées d'une vidéo"""
                    try:
                        video_id = vid.get('id')
                        if not video_id:
                            return None
                        
                        ydl_opts = {
                            'quiet': True,
                            'no_warnings': True,
                            'socket_timeout': 5,
                            'ignoreerrors': True,
                            'skip_download': True,
                        }
                        
                        with YoutubeDL(ydl_opts) as ydl:
                            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
                            if info:
                                info['search_keyword'] = keyword
                                return info
                    except:
                        return None
                    return None
                
                # Lancer en parallèle avec 10 threads
                videos = []
                with ThreadPoolExecutor(max_workers=10) as executor:
                    futures = {executor.submit(fetch_video_metadata, vid, keyword): vid for vid in video_ids}
                    
                    for future in as_completed(futures):
                        result = future.result()
                        if result:
                            videos.append(result)
                
                # FILTRAGE STRICT SI MOTS ENTRE GUILLEMETS
                # Exemple: "guerre starlink" → il FAUT les 2 mots
                if keyword.startswith('"') and keyword.endswith('"'):
                    # Extraire les mots entre guillemets
                    strict_words = keyword.strip('"').lower().split()
                    
                    videos_temp = []
                    for video in videos:
                        title = (video.get('title') or '').lower()
                        description = (video.get('description') or '').lower()
                        full_text = title + ' ' + description
                        
                        # Vérifier que TOUS les mots sont présents
                        all_words_present = all(word in full_text for word in strict_words)
                        
                        if all_words_present:
                            videos_temp.append(video)
                    
                    videos = videos_temp
                    st.info(f"🔍 Recherche stricte \"{keyword.strip('\"')}\" : {len(videos)} vidéos contiennent TOUS les mots")
                
                # FILTRAGE STRICT PAR LANGUE - MÉTHODE ROBUSTE
                if language != "Auto (toutes langues)":
                    videos_temp = []
                    
                    # Mapping langue sélectionnée → codes ISO
                    lang_map = {
                        "Français": ["fr"],
                        "Anglais": ["en"],
                        "Espagnol": ["es"]
                    }
                    target_langs = lang_map.get(language, [])
                    
                    for video in videos:
                        keep_video = False
                        
                        # MÉTHODE 1 : Champ language de YouTube (priorité)
                        video_lang = (video.get('language') or '').lower()
                        if video_lang:
                            # Extraire le code langue (ex: "fr-FR" → "fr")
                            lang_code = video_lang.split('-')[0]
                            if lang_code in target_langs:
                                keep_video = True
                        
                        # MÉTHODE 2 : Détection automatique avec langdetect (si disponible)
                        if not keep_video and LANGDETECT_AVAILABLE:
                            title = (video.get('title') or '')
                            description = (video.get('description') or '')
                            
                            # Combiner titre + début description pour avoir assez de texte
                            text_to_analyze = f"{title} {description[:500]}"
                            
                            if len(text_to_analyze.strip()) > 20:  # Au moins 20 caractères
                                try:
                                    detected_lang = detect(text_to_analyze)
                                    if detected_lang in target_langs:
                                        keep_video = True
                                except LangDetectException:
                                    # Si détection échoue, fallback sur heuristiques
                                    pass
                        
                        # MÉTHODE 3 : Heuristiques de backup (si langdetect pas dispo ou échoue)
                        if not keep_video and not LANGDETECT_AVAILABLE:
                            title = (video.get('title') or '').lower()
                            description = (video.get('description') or '').lower()
                            full_text = title + ' ' + description
                            
                            if language == "Français":
                                # Indicateurs français forts
                                french_strong = ['français', 'france', ' le ', ' la ', ' les ', ' un ', ' une ', ' des ', 
                                               ' de ', ' du ', ' ce ', ' cette ', ' je ', ' tu ', ' nous ', ' vous ']
                                french_chars = ['à', 'é', 'è', 'ê', 'ç', 'û', 'î', 'ô']
                                
                                has_french_words = sum(1 for w in french_strong if w in full_text) >= 2
                                has_french_chars = any(c in full_text for c in french_chars)
                                
                                # Exclure anglais/espagnol
                                has_english = ' the ' in title or ' and ' in title or ' is ' in title
                                has_spanish = '¿' in full_text or '¡' in full_text
                                
                                if (has_french_words or has_french_chars) and not has_english and not has_spanish:
                                    keep_video = True
                            
                            elif language == "Anglais":
                                # Indicateurs anglais forts
                                english_strong = [' the ', ' and ', ' is ', ' are ', ' was ', ' were ', 
                                                ' have ', ' has ', ' will ', ' would ', ' this ', ' that ']
                                
                                has_english_words = sum(1 for w in english_strong if w in full_text) >= 2
                                
                                # Exclure français/espagnol
                                has_french = any(c in full_text for c in ['à', 'é', 'è', 'ê', 'ç'])
                                has_spanish = '¿' in full_text or '¡' in full_text
                                
                                if has_english_words and not has_french and not has_spanish:
                                    keep_video = True
                            
                            elif language == "Espagnol":
                                # Indicateurs espagnol forts
                                spanish_strong = [' el ', ' la ', ' los ', ' las ', ' un ', ' una ', ' de ', 
                                                ' del ', ' que ', ' es ', ' está ', ' son ']
                                spanish_chars = ['¿', '¡', 'ñ', 'á', 'é', 'í', 'ó', 'ú']
                                
                                has_spanish_words = sum(1 for w in spanish_strong if w in full_text) >= 2
                                has_spanish_chars = any(c in full_text for c in spanish_chars)
                                
                                # Exclure anglais/français
                                has_english = ' the ' in title or ' and ' in title
                                has_french = 'français' in full_text
                                
                                if (has_spanish_words or has_spanish_chars) and not has_english and not has_french:
                                    keep_video = True
                        
                        if keep_video:
                            videos_temp.append(video)
                    
                    videos = videos_temp
                    if LANGDETECT_AVAILABLE:
                        st.info(f"🌍 {len(videos)} vidéos en {language} (détection automatique)")
                    else:
                        st.info(f"🌍 {len(videos)} vidéos en {language} (heuristiques)")
                
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
            
            # RÉCUPÉRER COMMENTAIRES + SOUS-TITRES - MULTITHREADING ⚡
            status.text("💬 Récupération (parallèle)...")
            progress_bar.progress(40)
            
            def fetch_video_data(video):
                """Fonction pour récupérer commentaires + sous-titres d'une vidéo"""
                video_id = video['id']
                video_title = video['title']
                result = {
                    'video': video,
                    'comments': [],
                    'hook': 'Sous-titres non disponibles',
                    'failed': False
                }
                
                # RÉCUPÉRER SOUS-TITRES (HOOK) - VERSION AGRESSIVE
                hook_text = ""
                try:
                    ydl_subs = YoutubeDL({
                        'quiet': True,
                        'no_warnings': True,
                        'socket_timeout': 8,
                        'writesubtitles': True,
                        'writeautomaticsub': True,
                        'allsubtitles': True,  # NOUVEAU : Récupère TOUTES les langues
                        'skip_download': True,
                        'ignoreerrors': True,
                    })
                    
                    info_subs = ydl_subs.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
                    
                    subtitles = info_subs.get('subtitles', {})
                    auto_subs = info_subs.get('automatic_captions', {})
                    
                    # STRATÉGIE AGRESSIVE : Essayer TOUTES les langues disponibles
                    subtitle_data = None
                    
                    # 1. Priorité : sous-titres manuels
                    if subtitles:
                        for lang in subtitles.keys():
                            if subtitles[lang]:
                                subtitle_data = subtitles[lang]
                                break
                    
                    # 2. Fallback : sous-titres automatiques
                    if not subtitle_data and auto_subs:
                        # Priorité aux langues principales
                        priority_langs = ['fr', 'en', 'es', 'fr-FR', 'en-US', 'es-ES', 
                                        'en-GB', 'pt', 'de', 'it', 'ru', 'ar']
                        
                        for lang in priority_langs:
                            if lang in auto_subs and auto_subs[lang]:
                                subtitle_data = auto_subs[lang]
                                break
                        
                        # Si toujours rien, prendre la première langue dispo
                        if not subtitle_data:
                            for lang in auto_subs.keys():
                                if auto_subs[lang]:
                                    subtitle_data = auto_subs[lang]
                                    break
                    
                    # Extraire le texte des sous-titres
                    if subtitle_data and len(subtitle_data) > 0:
                        sub_url = subtitle_data[0].get('url')
                        
                        if sub_url:
                            response = requests.get(sub_url, timeout=8)
                            if response.status_code == 200:
                                content = response.text
                                
                                # Détecter le format et parser en conséquence
                                hook_sentences = []
                                
                                # Format JSON3 (YouTube)
                                if content.strip().startswith('{'):
                                    try:
                                        sub_json = json.loads(content)
                                        events = sub_json.get('events', [])
                                        
                                        for event in events[:15]:  # Plus d'événements
                                            if 'segs' in event:
                                                text = ''.join([seg.get('utf8', '') for seg in event['segs']])
                                                if text.strip():
                                                    hook_sentences.append(text.strip())
                                        
                                        hook_text = ' '.join(hook_sentences[:8])  # Plus de phrases
                                    except:
                                        pass
                                
                                # Format VTT
                                elif 'WEBVTT' in content:
                                    lines = content.split('\n')
                                    for line in lines[:50]:  # Premières 50 lignes
                                        line = line.strip()
                                        # Ignorer les timestamps et lignes vides
                                        if line and '-->' not in line and not line.startswith('WEBVTT') and not line.isdigit():
                                            if len(line) > 10:  # Au moins 10 caractères
                                                hook_sentences.append(line)
                                                if len(hook_sentences) >= 8:
                                                    break
                                    
                                    hook_text = ' '.join(hook_sentences)
                                
                                # Format SRT ou autre
                                else:
                                    lines = content.split('\n')
                                    for line in lines[:50]:
                                        line = line.strip()
                                        if line and '-->' not in line and not line.isdigit():
                                            if len(line) > 10:
                                                hook_sentences.append(line)
                                                if len(hook_sentences) >= 8:
                                                    break
                                    
                                    hook_text = ' '.join(hook_sentences)
                except Exception as e:
                    # En cas d'erreur, on note le type d'erreur
                    hook_text = f"Erreur récupération: {type(e).__name__}"
                
                result['hook'] = hook_text if hook_text else "Sous-titres non disponibles"
                
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
                            result['comments'].append({
                                'video': video_title,
                                'video_id': video_id,
                                'keyword': video.get('search_keyword', ''),
                                'author': comment.get('author', 'Anonyme'),
                                'text': comment.get('text', ''),
                                'likes': comment.get('like_count', 0) or 0
                            })
                    else:
                        result['failed'] = True
                except:
                    result['failed'] = True
                
                return result
            
            # Lancer en parallèle avec 5 threads
            failed_videos = []
            completed = 0
            
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = {executor.submit(fetch_video_data, video): video for video in all_videos_filtered}
                
                for future in as_completed(futures):
                    completed += 1
                    progress_bar.progress(40 + int((completed / len(all_videos_filtered)) * 40))
                    status.text(f"💬 Vidéo {completed}/{len(all_videos_filtered)}...")
                    
                    result = future.result()
                    
                    # Stocker le hook dans la vidéo
                    result['video']['hook'] = result['hook']
                    
                    # Ajouter les commentaires
                    all_comments_list.extend(result['comments'])
                    
                    if result['failed'] and not result['comments']:
                        failed_videos.append(result['video']['title'])
            
            progress_bar.progress(90)
            
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
                
                # TRIER PAR SUCCÈS (Vues + Viralité)
                def calculate_success_score(video):
                    """Calcule un score de succès basé sur vues et viralité"""
                    views = video.get('view_count', 0) or 0
                    subscribers = video.get('channel_follower_count', 0) or 0
                    
                    # Score de viralité
                    if subscribers > 0:
                        virality_multiplier = views / subscribers
                    else:
                        virality_multiplier = 1
                    
                    # Score final = vues * multiplicateur viralité
                    return views * (1 + virality_multiplier)
                
                # Trier par score décroissant
                all_videos_filtered_sorted = sorted(all_videos_filtered, key=calculate_success_score, reverse=True)
                
                st.info("🔥 Vidéos triées par succès (viralité + vues)")
                st.divider()
                
                # GALERIE DE THUMBNAILS - Grille 3 colonnes
                for idx in range(0, len(all_videos_filtered_sorted), 3):
                    cols = st.columns(3)
                    
                    for col_idx, col in enumerate(cols):
                        video_idx = idx + col_idx
                        if video_idx >= len(all_videos_filtered_sorted):
                            break
                        
                        video = all_videos_filtered_sorted[video_idx]
                        
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
                        thumbnail_url = video.get('thumbnail', '')
                        
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
                        
                        with col:
                            # THUMBNAIL EN GRAND
                            if thumbnail_url:
                                st.image(thumbnail_url, use_container_width=True)
                            else:
                                st.info("🖼️ Pas de miniature")
                            
                            # Infos compactes
                            st.markdown(f"**#{video_idx+1} - {virality_stars}**")
                            st.caption(f"{title[:60]}...")
                            st.caption(f"👁️ {views:,} | 📈 {engagement:.1f}% | ⏱️ {mins}:{secs:02d}")
                            st.caption(f"📺 {channel[:30]}...")
                            
                            # DÉTAILS EN EXPANDER (clic direct)
                            with st.expander("📋 Voir détails"):
                                st.write(f"**🔍 Mot-clé:** {keyword}")
                                st.write(f"**📺 Canal:** {channel} ({subscribers:,} abonnés)")
                                st.write(f"**👁️ Vues:** {views:,}")
                                st.write(f"**👍 Likes:** {likes:,}")
                                st.write(f"**📈 Engagement:** {engagement:.2f}%")
                                st.write(f"**🔥 Viralité:** {virality_stars}")
                                st.write(f"**⏱️ Durée:** {mins}min {secs}s")
                                
                                # Formater date
                                if upload_date:
                                    try:
                                        date_obj = datetime.strptime(upload_date, '%Y%m%d')
                                        date_str = date_obj.strftime('%d/%m/%Y')
                                        st.write(f"**📅 Publié:** {date_str}")
                                    except:
                                        pass
                                
                                st.write(f"**🔗** [Regarder sur YouTube](https://www.youtube.com/watch?v={video_id})")
                                
                                st.divider()
                                st.write("### 🎯 HOOK (Premières phrases)")
                                st.info(hook)
                                
                                st.divider()
                                st.write("### 💬 Top 20 Commentaires (par likes)")
                                
                                video_comments = [c for c in all_comments_list if c['video_id'] == video_id]
                                
                                if video_comments:
                                    for i, comment in enumerate(video_comments, 1):
                                        st.write(f"**{i}. {comment['author']}** 👍 {comment['likes']}")
                                        st.write(f"> {comment['text']}")
                                        st.write("")
                                else:
                                    st.info("⚠️ Aucun commentaire disponible")
                    
                    st.divider()
            
            progress_bar.progress(100)
            status.text("✅ Terminé!")
        
        except Exception as e:
            st.error(f"❌ Erreur: {str(e)}")
            st.exception(e)
