import streamlit as st
from yt_dlp import YoutubeDL
import json
from datetime import datetime, timedelta
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

st.set_page_config(page_title="YouTube Scraper Pro", layout="wide")

# Détection de langue robuste
try:
    from langdetect import detect, LangDetectException
    # Test rapide pour s'assurer que ça fonctionne
    test_result = detect("This is a test")
    LANGDETECT_AVAILABLE = True
except (ImportError, Exception):
    LANGDETECT_AVAILABLE = False

st.title("🚀 YouTube Keyword Research Tool PRO")

# Avertissement si langdetect pas dispo
if not LANGDETECT_AVAILABLE:
    st.error("🚨 **langdetect n'est PAS installé !** Le filtrage par langue sera très limité. Installe-le: `pip install langdetect`")

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
        # ============ INSTANCES YoutubeDL RÉUTILISABLES (OPTIMISATION #1) ============
        # Créées UNE FOIS par session de recherche !
        YDL_SEARCH = YoutubeDL({
            'quiet': True,
            'no_warnings': True,
            'extract_flat': 'in_playlist',
            'socket_timeout': 5,
            'ignoreerrors': True,
        })
        
        YDL_FULL = YoutubeDL({
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 5,
            'ignoreerrors': True,
            'skip_download': True,
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': ['fr', 'en', 'es'],
            'getcomments': True,
            'extractor_args': {'youtube': {'max_comments': ['20']}}
        })
        
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
                
                search_limit = 40
                search_query = f"ytsearch{search_limit}:{keyword}"
                
                # RECHERCHE avec instance réutilisable
                results = YDL_SEARCH.extract_info(search_query, download=False)
                video_ids = results.get('entries', [])
                video_ids = [v for v in video_ids if v is not None][:search_limit]
                
                progress_bar.progress(10 + int((keyword_idx / len(keywords_list)) * 10))
                
                # RÉCUPÉRATION COMPLÈTE - OPTIMISÉE (Métadonnées + Sous-titres + Commentaires EN UN SEUL APPEL)
                status.text(f"📊 Récupération complète: {keyword} (parallèle turbo)...")
                
                def fetch_all_data(vid, keyword):
                    """OPTIMISATION #2: Tout en un seul appel API !"""
                    try:
                        video_id = vid.get('id')
                        if not video_id:
                            return None
                        
                        # UN SEUL APPEL pour métadonnées + sous-titres + commentaires !
                        info = YDL_FULL.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
                        
                        if not info:
                            return None
                        
                        info['search_keyword'] = keyword
                        
                        # Extraire HOOK des sous-titres (OPTIMISATION #4: Simplifié)
                        hook_text = ""
                        subtitles = info.get('subtitles', {})
                        auto_subs = info.get('automatic_captions', {})
                        
                        # Essayer FR, EN, ES seulement
                        subtitle_data = None
                        for lang in ['fr', 'en', 'es', 'fr-FR', 'en-US', 'es-ES']:
                            if lang in subtitles and subtitles[lang]:
                                subtitle_data = subtitles[lang]
                                break
                            elif lang in auto_subs and auto_subs[lang]:
                                subtitle_data = auto_subs[lang]
                                break
                        
                        if subtitle_data and len(subtitle_data) > 0:
                            try:
                                sub_url = subtitle_data[0].get('url')
                                if sub_url:
                                    response = requests.get(sub_url, timeout=5)  # TIMEOUT AUGMENTÉ
                                    if response.status_code == 200:
                                        content = response.text
                                        hook_sentences = []
                                        
                                        # Parser simple
                                        if content.strip().startswith('{'):
                                            sub_json = json.loads(content)
                                            events = sub_json.get('events', [])
                                            for event in events[:10]:
                                                if 'segs' in event:
                                                    text = ''.join([seg.get('utf8', '') for seg in event['segs']])
                                                    if text.strip():
                                                        hook_sentences.append(text.strip())
                                            hook_text = ' '.join(hook_sentences[:5])
                                        else:
                                            # VTT/SRT simple
                                            lines = content.split('\n')
                                            for line in lines[:30]:
                                                line = line.strip()
                                                if line and '-->' not in line and len(line) > 10:
                                                    hook_sentences.append(line)
                                                    if len(hook_sentences) >= 5:
                                                        break
                                            hook_text = ' '.join(hook_sentences)
                            except:
                                pass
                        
                        info['hook'] = hook_text if hook_text else "Sous-titres non disponibles"
                        
                        # Extraire commentaires
                        comments = info.get('comments', [])
                        if comments:
                            comments_sorted = sorted(comments, key=lambda x: x.get('like_count', 0) or 0, reverse=True)[:20]
                            info['top_comments'] = comments_sorted
                        else:
                            info['top_comments'] = []
                        
                        return info
                        
                    except:
                        return None
                
                # OPTIMISATION #5: 15 workers au lieu de 5-10
                videos = []
                with ThreadPoolExecutor(max_workers=15) as executor:
                    futures = {executor.submit(fetch_all_data, vid, keyword): vid for vid in video_ids}
                    
                    for future in as_completed(futures):
                        result = future.result()
                        if result:
                            videos.append(result)
                
                # DEBUG
                st.info(f"✅ {len(videos)} vidéos avec métadonnées complètes")
                
                progress_bar.progress(20)
                
                # FILTRAGE STRICT SI MOTS ENTRE GUILLEMETS
                if keyword.startswith('"') and keyword.endswith('"'):
                    strict_words = keyword.strip('"').lower().split()
                    
                    videos_temp = []
                    for video in videos:
                        title = (video.get('title') or '').lower()
                        description = (video.get('description') or '').lower()
                        full_text = title + ' ' + description
                        
                        if all(word in full_text for word in strict_words):
                            videos_temp.append(video)
                    
                    videos = videos_temp
                    st.info(f"🔍 Recherche stricte \"{keyword.strip('\"')}\" : {len(videos)} vidéos")
                
                # FILTRAGE PAR LANGUE - VERSION STRICTE (REJET PAR DÉFAUT)
                if language != "Auto (toutes langues)":
                    videos_temp = []
                    target_lang_code = {"Français": "fr", "Anglais": "en", "Espagnol": "es"}.get(language)
                    
                    rejected_count = 0
                    no_lang_count = 0
                    rejected_examples = []  # Pour debug
                    
                    for video in videos:
                        # PAR DÉFAUT : ON REJETTE (inverse de avant !)
                        keep_video = False
                        reject_reason = "Non détecté"
                        
                        video_lang = (video.get('language') or '').lower().split('-')[0]
                        title = video.get('title', '')
                        description = video.get('description', '')
                        
                        # MÉTHODE 1 : Champ language de YouTube (PRIORITÉ ABSOLUE)
                        if video_lang and len(video_lang) == 2:
                            if video_lang == target_lang_code:
                                # C'est la bonne langue selon YouTube !
                                keep_video = True
                                reject_reason = f"✅ YouTube: {video_lang}"
                            else:
                                # C'est une autre langue selon YouTube
                                keep_video = False
                                reject_reason = f"❌ YouTube: {video_lang} (attendu: {target_lang_code})"
                                rejected_count += 1
                                if len(rejected_examples) < 3:
                                    rejected_examples.append((title[:60], video_lang, reject_reason))
                        else:
                            # Pas de champ language
                            no_lang_count += 1
                            
                            # MÉTHODE 2 : Détection avec langdetect (STRICT)
                            if LANGDETECT_AVAILABLE:
                                text_to_analyze = f"{title} {description[:500]}"
                                
                                if len(text_to_analyze.strip()) > 30:
                                    try:
                                        detected = detect(text_to_analyze)
                                        
                                        if detected == target_lang_code:
                                            # Détecté comme la bonne langue !
                                            keep_video = True
                                            reject_reason = f"✅ Détecté: {detected}"
                                        else:
                                            # Détecté comme une autre langue
                                            keep_video = False
                                            reject_reason = f"❌ Détecté: {detected} (attendu: {target_lang_code})"
                                            rejected_count += 1
                                            if len(rejected_examples) < 3:
                                                rejected_examples.append((title[:60], detected, reject_reason))
                                    except Exception as e:
                                        # Erreur de détection = REJET (strict)
                                        keep_video = False
                                        reject_reason = f"❌ Erreur détection: {type(e).__name__}"
                                        rejected_count += 1
                                else:
                                    # Pas assez de texte = REJET (strict)
                                    keep_video = False
                                    reject_reason = "❌ Pas assez de texte"
                                    rejected_count += 1
                            else:
                                # langdetect pas dispo = REJET (strict)
                                keep_video = False
                                reject_reason = "❌ langdetect non disponible"
                                rejected_count += 1
                        
                        if keep_video:
                            videos_temp.append(video)
                    
                    videos = videos_temp
                    
                    # DEBUG DÉTAILLÉ
                    st.info(f"🌍 **{len(videos)} vidéos en {language}** (filtre STRICT)")
                    st.write(f"   • Gardées: {len(videos)} | Rejetées: {rejected_count} | Sans champ language: {no_lang_count}")
                    
                    # Montrer exemples de vidéos rejetées
                    if rejected_examples:
                        with st.expander("🔍 Voir exemples de vidéos rejetées (debug)"):
                            for title, lang, reason in rejected_examples:
                                st.write(f"• **{title}...** → Langue: `{lang}` | {reason}")
                    
                    if not LANGDETECT_AVAILABLE:
                        st.warning("⚠️ **ATTENTION**: langdetect n'est pas installé ! Le filtrage est limité. Installe-le: `pip install langdetect`")
                
                progress_bar.progress(30)
                
                # DEBUG: Afficher les vidéos avant filtrage par vues
                st.write(f"📊 **DEBUG: {len(videos)} vidéos avant filtrage par vues**")
                if videos:
                    st.write("**Exemple de vues des 5 premières vidéos:**")
                    for i, v in enumerate(videos[:5], 1):
                        views = v.get('view_count', 0) or 0
                        st.write(f"  {i}. {v.get('title', '')[:50]}... → **{views:,} vues**")
                    
                    st.write(f"**Filtres de vues actifs:** {[f'{min_v:,}-{max_v:,}' for min_v, max_v, _ in selected_views]}")
                
                # FILTRER PAR VUES + AUTRES
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
                        if "short" in duration_filters and duration < 300:
                            duration_match = True
                        if "medium" in duration_filters and 300 <= duration <= 1200:
                            duration_match = True
                        if "long" in duration_filters and duration > 1200:
                            duration_match = True
                        
                        if not duration_match:
                            continue
                    
                    all_videos_filtered.append(video)
            
            # DEBUG: Vidéos après TOUS les filtres
            st.success(f"✅ {len(all_videos_filtered)} vidéo(s) après TOUS les filtres (vues, engagement, date, durée)")
            
            if len(all_videos_filtered) == 0:
                st.error(f"❌ Aucune vidéo trouvée avec tous les filtres.")
                st.stop()
            
            st.success(f"✅ {len(all_videos_filtered)} vidéo(s) trouvée(s) pour {len(keywords_list)} mot(s)-clé(s)!")
            st.divider()
            
            # Construire la liste des commentaires
            progress_bar.progress(60)
            status.text("📝 Compilation des données...")
            
            for video in all_videos_filtered:
                video_id = video['id']
                video_title = video['title']
                keyword = video.get('search_keyword', '')
                
                for comment in video.get('top_comments', []):
                    all_comments_list.append({
                        'video': video_title,
                        'video_id': video_id,
                        'keyword': keyword,
                        'author': comment.get('author', 'Anonyme'),
                        'text': comment.get('text', ''),
                        'likes': comment.get('like_count', 0) or 0
                    })
            
            progress_bar.progress(70)
            
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
                
                # TRIER PAR SUCCÈS
                def calculate_success_score(video):
                    views = video.get('view_count', 0) or 0
                    subscribers = video.get('channel_follower_count', 0) or 0
                    
                    if subscribers > 0:
                        virality_multiplier = views / subscribers
                    else:
                        virality_multiplier = 1
                    
                    return views * (1 + virality_multiplier)
                
                all_videos_filtered_sorted = sorted(all_videos_filtered, key=calculate_success_score, reverse=True)
                
                st.info("🔥 Vidéos triées par succès (viralité + vues)")
                st.divider()
                
                # GALERIE DE THUMBNAILS
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
                        
                        engagement = (likes / views * 100) if views > 0 else 0
                        
                        # Score viralité
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
                        
                        mins = duration // 60
                        secs = duration % 60
                        
                        with col:
                            if thumbnail_url:
                                st.image(thumbnail_url, use_container_width=True)
                            else:
                                st.info("🖼️ Pas de miniature")
                            
                            st.markdown(f"**#{video_idx+1} - {virality_stars}**")
                            st.caption(f"{title[:60]}...")
                            st.caption(f"👁️ {views:,} | 📈 {engagement:.1f}% | ⏱️ {mins}:{secs:02d}")
                            st.caption(f"📺 {channel[:30]}...")
                            
                            with st.expander("📋 Voir détails"):
                                st.write(f"**🔍 Mot-clé:** {keyword}")
                                st.write(f"**📺 Canal:** {channel} ({subscribers:,} abonnés)")
                                st.write(f"**👁️ Vues:** {views:,}")
                                st.write(f"**👍 Likes:** {likes:,}")
                                st.write(f"**📈 Engagement:** {engagement:.2f}%")
                                st.write(f"**🔥 Viralité:** {virality_stars}")
                                st.write(f"**⏱️ Durée:** {mins}min {secs}s")
                                
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
