"""
🚀 YouTube Keyword Research Tool PRO - V7 FIXED
===============================================
CORRECTION CRITIQUE: st.session_state ne fonctionne PAS dans les threads!
Solution: Les fonctions de traitement retournent leurs logs au lieu d'écrire directement.
"""

import streamlit as st
from yt_dlp import YoutubeDL
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import random
from typing import List, Dict, Optional, Tuple
import re
import traceback

# ==========================================
# 📋 CONFIGURATION
# ==========================================

st.set_page_config(
    page_title="YouTube Research V7", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Safari/537.36',
]

# Mots-clés pour détection de langue
LANGUAGE_KEYWORDS = {
    "French": {
        "code": "fr",
        "markers": ["le", "la", "les", "de", "du", "des", "un", "une", "et", "est", "sont", 
                   "dans", "pour", "sur", "avec", "qui", "que", "ce", "cette", "nous", "vous",
                   "je", "tu", "il", "elle", "c'est", "très", "plus", "mais", "aussi", "tout"]
    },
    "English": {
        "code": "en", 
        "markers": ["the", "and", "is", "are", "was", "were", "have", "has", "been",
                   "this", "that", "with", "for", "not", "you", "all", "can", "had",
                   "but", "what", "when", "your", "which", "will", "would", "they"]
    },
    "Spanish": {
        "code": "es",
        "markers": ["el", "la", "los", "las", "de", "en", "que", "es", "un", "una",
                   "por", "con", "para", "como", "más", "pero", "sus", "este", "son"]
    },
}


# ==========================================
# 🔍 FONCTIONS PURES (SANS st.session_state!)
# ==========================================

def detect_language_simple(text: str) -> Optional[str]:
    """Détecte la langue - retourne 'fr', 'en', 'es' ou None"""
    if not text or len(text) < 5:
        return None
    
    text_lower = text.lower()
    words = set(re.findall(r'\b[a-zàâäéèêëïîôùûüçñ]+\b', text_lower))
    
    scores = {}
    for lang_name, config in LANGUAGE_KEYWORDS.items():
        markers = set(config["markers"])
        matches = len(words & markers)
        if matches > 0:
            scores[config["code"]] = matches
    
    if not scores:
        return None
    
    return max(scores, key=scores.get)


def matches_language(text: str, target_lang: str) -> bool:
    """ULTRA PERMISSIF - retourne True dans presque tous les cas"""
    if target_lang == "Auto (all languages)":
        return True
    
    if not text or len(text) < 30:
        return True
    
    target_config = LANGUAGE_KEYWORDS.get(target_lang)
    if not target_config:
        return True
    
    target_code = target_config["code"]
    detected = detect_language_simple(text)
    
    if detected is None:
        return True
    
    if detected == target_code:
        return True
    
    # Vérifier si au moins 1 mot de la langue cible est présent
    text_lower = text.lower()
    words = set(re.findall(r'\b[a-zàâäéèêëïîôùûüçñ]+\b', text_lower))
    target_markers = set(target_config["markers"])
    if len(words & target_markers) >= 1:
        return True
    
    return False


def search_youtube_pure(keyword: str, max_results: int = 20) -> Tuple[List[Dict], List[str]]:
    """
    Recherche YouTube - FONCTION PURE (pas de st.session_state)
    Retourne: (liste de vidéos, liste de logs)
    """
    logs = []
    
    if not keyword or not keyword.strip():
        logs.append("[WARN] Mot-clé vide")
        return [], logs
    
    logs.append(f"[INFO] SEARCH: Recherche pour '{keyword}' (max {max_results})")
    
    opts = {
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'socket_timeout': 20,
        'http_headers': {'User-Agent': random.choice(USER_AGENTS)},
        'extract_flat': True,
    }
    
    try:
        search_query = f"ytsearch{max_results}:{keyword.strip()}"
        
        with YoutubeDL(opts) as ydl:
            result = ydl.extract_info(search_query, download=False)
            
            if not result:
                logs.append(f"[ERROR] Résultat None pour '{keyword}'")
                return [], logs
            
            entries = result.get('entries', [])
            logs.append(f"[INFO] {len(entries)} entrées brutes reçues")
            
            valid_entries = []
            for i, e in enumerate(entries):
                if not e:
                    continue
                
                video_id = e.get('id')
                
                if not video_id:
                    url = e.get('url', '') or e.get('webpage_url', '')
                    if 'watch?v=' in url:
                        video_id = url.split('watch?v=')[1].split('&')[0]
                    elif 'youtu.be/' in url:
                        video_id = url.split('youtu.be/')[1].split('?')[0]
                    elif '/shorts/' in url:
                        video_id = url.split('/shorts/')[1].split('?')[0]
                
                if video_id:
                    e['id'] = video_id
                    valid_entries.append(e)
                    logs.append(f"[INFO] Vidéo {i}: ID={video_id}, titre={e.get('title', 'N/A')[:40]}")
            
            logs.append(f"[INFO] {len(valid_entries)} vidéos valides")
            return valid_entries, logs
    
    except Exception as ex:
        logs.append(f"[ERROR] SEARCH ERROR: {ex}")
        logs.append(f"[ERROR] {traceback.format_exc()}")
        return [], logs


def get_video_details_pure(video_id: str) -> Tuple[Optional[Dict], List[str]]:
    """
    Récupère les détails d'une vidéo - FONCTION PURE
    Retourne: (info dict ou None, liste de logs)
    """
    logs = []
    
    if not video_id:
        logs.append("[WARN] ID vide")
        return None, logs
    
    logs.append(f"[INFO] DETAILS: Extraction de {video_id}")
    
    opts = {
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'socket_timeout': 30,
        'http_headers': {'User-Agent': random.choice(USER_AGENTS)},
        'skip_download': True,
        'getcomments': True,
    }
    
    try:
        url = f"https://www.youtube.com/watch?v={video_id}"
        
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if not info:
                logs.append(f"[ERROR] Info None pour {video_id}")
                return None, logs
            
            logs.append(f"[INFO] DETAILS OK: {video_id}")
            logs.append(f"[INFO]   title: {info.get('title', 'N/A')[:50]}")
            logs.append(f"[INFO]   views: {info.get('view_count', 'N/A')}")
            logs.append(f"[INFO]   subs: {info.get('channel_follower_count', 'N/A')}")
            logs.append(f"[INFO]   date: {info.get('upload_date', 'N/A')}")
            logs.append(f"[INFO]   duration: {info.get('duration', 'N/A')}s")
            logs.append(f"[INFO]   comments: {len(info.get('comments', []) or [])}")
            
            return info, logs
    
    except Exception as ex:
        logs.append(f"[ERROR] DETAILS ERROR ({video_id}): {ex}")
        return None, logs


def process_video_pure(
    video_entry: Dict,
    min_views: int,
    min_duration: str,
    date_limit: Optional[datetime],
    target_language: str,
    bypass_filters: bool = False
) -> Tuple[Optional[Dict], List[str], Dict]:
    """
    Traite une vidéo - FONCTION PURE (pas de st.session_state!)
    Retourne: (video info ou None, liste de logs, stats dict)
    """
    logs = []
    stats = {
        'details_fetched': 0,
        'details_failed': 0,
        'filtered_views': 0,
        'filtered_date': 0,
        'filtered_duration': 0,
        'filtered_language': 0,
        'passed': 0,
    }
    
    video_id = video_entry.get('id')
    if not video_id:
        logs.append("[WARN] Pas d'ID dans l'entrée")
        return None, logs, stats
    
    logs.append(f"[INFO] PROCESS: Début {video_id}")
    
    # 1. Récupérer les détails
    info, detail_logs = get_video_details_pure(video_id)
    logs.extend(detail_logs)
    
    if not info:
        logs.append(f"[ERROR] Impossible de récupérer {video_id}")
        stats['details_failed'] = 1
        return None, logs, stats
    
    stats['details_fetched'] = 1
    
    # Si bypass, on skip les filtres
    if bypass_filters:
        logs.append(f"[INFO] BYPASS: Skip tous les filtres pour {video_id}")
        info['_ratio'] = 1.0
        info['_stars'] = "⭐"
        info['_has_flame'] = False
        raw_comments = info.get('comments') or []
        if raw_comments:
            sorted_comments = sorted(
                [c for c in raw_comments if isinstance(c, dict) and c.get('text')],
                key=lambda x: x.get('like_count', 0) or 0,
                reverse=True
            )
            info['comments'] = sorted_comments[:20]
        else:
            info['comments'] = []
        stats['passed'] = 1
        logs.append(f"[INFO] ✅ {video_id} VALIDÉ (bypass)")
        return info, logs, stats
    
    # 2. FILTRE VUES
    view_count = info.get('view_count') or 0
    if view_count < min_views:
        logs.append(f"[FILTER] VUES: {video_id} REJETÉ - {view_count} < {min_views}")
        stats['filtered_views'] = 1
        return None, logs, stats
    logs.append(f"[INFO] VUES OK: {view_count} >= {min_views}")
    
    # 3. FILTRE DATE
    if date_limit:
        upload_date_str = info.get('upload_date')
        if upload_date_str:
            try:
                upload_date = datetime.strptime(upload_date_str, '%Y%m%d')
                if upload_date < date_limit:
                    logs.append(f"[FILTER] DATE: {video_id} REJETÉ - {upload_date_str} trop ancien")
                    stats['filtered_date'] = 1
                    return None, logs, stats
                logs.append(f"[INFO] DATE OK: {upload_date_str}")
            except ValueError:
                logs.append(f"[WARN] DATE invalide: {upload_date_str}")
    
    # 4. FILTRE DURÉE
    duration = info.get('duration') or 0
    if min_duration == "2 min" and duration < 120:
        logs.append(f"[FILTER] DURÉE: {video_id} REJETÉ - {duration}s < 120s")
        stats['filtered_duration'] = 1
        return None, logs, stats
    elif min_duration == "5 min" and duration < 300:
        logs.append(f"[FILTER] DURÉE: {video_id} REJETÉ - {duration}s < 300s")
        stats['filtered_duration'] = 1
        return None, logs, stats
    elif min_duration == "10 min" and duration < 600:
        logs.append(f"[FILTER] DURÉE: {video_id} REJETÉ - {duration}s < 600s")
        stats['filtered_duration'] = 1
        return None, logs, stats
    logs.append(f"[INFO] DURÉE OK: {duration}s")
    
    # 5. FILTRE LANGUE
    title = info.get('title', '')
    description = (info.get('description') or '')[:500]
    text_to_check = f"{title} {description}"
    
    if not matches_language(text_to_check, target_language):
        detected = detect_language_simple(text_to_check)
        logs.append(f"[FILTER] LANGUE: {video_id} REJETÉ - détecté={detected}, cible={target_language}")
        stats['filtered_language'] = 1
        return None, logs, stats
    logs.append(f"[INFO] LANGUE OK")
    
    # ===== TOUS LES FILTRES PASSÉS =====
    logs.append(f"[INFO] ✅ {video_id} A PASSÉ TOUS LES FILTRES!")
    stats['passed'] = 1
    
    # Calcul du ratio
    subs = info.get('channel_follower_count') or 1
    if subs <= 0:
        subs = 1
    ratio = view_count / subs
    info['_ratio'] = ratio
    
    if ratio >= 2:
        info['_stars'] = "⭐⭐⭐"
    elif ratio >= 1:
        info['_stars'] = "⭐⭐"
    else:
        info['_stars'] = "⭐"
    
    info['_has_flame'] = False
    
    # Commentaires (top 20)
    raw_comments = info.get('comments') or []
    if raw_comments:
        sorted_comments = sorted(
            [c for c in raw_comments if isinstance(c, dict) and c.get('text')],
            key=lambda x: x.get('like_count', 0) or 0,
            reverse=True
        )
        info['comments'] = sorted_comments[:20]
    else:
        info['comments'] = []
    
    return info, logs, stats


# ==========================================
# 📊 TRI ET PROMPT
# ==========================================

def sort_videos(videos: List[Dict]) -> List[Dict]:
    return sorted(videos, key=lambda v: v.get('_ratio', 0), reverse=True)


def build_prompt(videos: List[Dict], keywords: List[str], lang: str) -> str:
    if not videos:
        return "Aucune vidéo."
    
    subjects = ", ".join(keywords) if keywords else "N/A"
    prompt = f"Analyse ces {len(videos)} vidéos virales sur: {subjects}\n\n"
    
    for idx, v in enumerate(videos, 1):
        title = v.get('title', '?')
        url = v.get('webpage_url', '')
        views = v.get('view_count', 0)
        subs = v.get('channel_follower_count', 0)
        ratio = v.get('_ratio', 0)
        stars = v.get('_stars', '⭐')
        channel = v.get('uploader', '?')
        
        prompt += f"{'='*50}\n"
        prompt += f"#{idx} {stars} | {title}\n"
        prompt += f"{'='*50}\n"
        prompt += f"📺 {channel}\n"
        prompt += f"🔗 {url}\n"
        prompt += f"👁️ {views:,} vues | 👥 {subs:,} abonnés | 📊 {ratio:.2f}x\n"
        
        comments = v.get('comments', [])
        if comments:
            prompt += f"\n💬 TOP {len(comments)} COMMENTAIRES:\n"
            for i, c in enumerate(comments, 1):
                text = c.get('text', '').replace('\n', ' ')[:150]
                likes = c.get('like_count', 0)
                prompt += f"[{i}] ({likes}👍) {text}\n"
        
        prompt += "\n"
    
    return prompt


# ==========================================
# 🎨 INTERFACE STREAMLIT
# ==========================================

def render_sidebar() -> dict:
    st.sidebar.title("🔍 YouTube Research V7")
    st.sidebar.caption("Version corrigée - threads OK")
    
    # Mots-clés
    st.sidebar.header("📝 Mots-clés")
    keywords_text = st.sidebar.text_area(
        "Un par ligne",
        height=80,
        placeholder="trump\nmacron\nelon musk"
    )
    keywords = [k.strip() for k in keywords_text.split('\n') if k.strip()]
    
    st.sidebar.divider()
    
    # Filtres
    st.sidebar.header("🎯 Filtres")
    
    language = st.sidebar.selectbox(
        "🌍 Langue",
        ["Auto (all languages)", "French", "English", "Spanish"]
    )
    
    min_views = st.sidebar.number_input(
        "👁️ Vues minimum",
        value=10000,
        step=5000,
        min_value=0
    )
    
    min_duration = st.sidebar.selectbox(
        "⏱️ Durée minimum",
        ["Toutes", "2 min", "5 min", "10 min"]
    )
    
    date_period = st.sidebar.selectbox(
        "📅 Période",
        ["Tout", "7 jours", "30 jours", "6 mois", "1 an"]
    )
    
    date_limit = None
    if date_period == "7 jours":
        date_limit = datetime.now() - timedelta(days=7)
    elif date_period == "30 jours":
        date_limit = datetime.now() - timedelta(days=30)
    elif date_period == "6 mois":
        date_limit = datetime.now() - timedelta(days=180)
    elif date_period == "1 an":
        date_limit = datetime.now() - timedelta(days=365)
    
    st.sidebar.divider()
    
    # Options
    st.sidebar.header("⚙️ Options")
    
    videos_per_keyword = st.sidebar.slider(
        "Vidéos par mot-clé",
        min_value=3,
        max_value=20,
        value=10
    )
    
    max_workers = st.sidebar.slider(
        "Threads parallèles",
        min_value=1,
        max_value=10,
        value=5
    )
    
    st.sidebar.divider()
    st.sidebar.header("🔧 Debug")
    
    bypass_filters = st.sidebar.checkbox(
        "🚫 BYPASS tous les filtres",
        value=False,
        help="Désactive tous les filtres pour tester"
    )
    
    return {
        'keywords': keywords,
        'language': language,
        'min_views': int(min_views),
        'min_duration': min_duration,
        'date_limit': date_limit,
        'videos_per_keyword': videos_per_keyword,
        'max_workers': max_workers,
        'bypass_filters': bypass_filters,
    }


def render_video_card(video: Dict, idx: int):
    ratio = video.get('_ratio', 0)
    stars = video.get('_stars', '⭐')
    views = video.get('view_count', 0)
    title = video.get('title', 'Sans titre')
    
    header = f"#{idx} {stars} | {ratio:.1f}x | {views:,} vues"
    
    with st.expander(header, expanded=(idx <= 3)):
        col1, col2 = st.columns([1, 2])
        
        with col1:
            thumb = video.get('thumbnail')
            if thumb:
                st.image(thumb, use_container_width=True)
        
        with col2:
            st.markdown(f"**{title}**")
            st.write(f"📺 {video.get('uploader', 'Inconnu')}")
            st.write(f"👥 Abonnés: {video.get('channel_follower_count', 0):,}")
            st.write(f"👁️ Vues: {views:,}")
            st.write(f"📊 Ratio: **{ratio:.2f}x**")
            
            url = video.get('webpage_url', '')
            if url:
                st.link_button("▶️ YouTube", url)
        
        # Commentaires
        comments = video.get('comments', [])
        if comments:
            st.divider()
            st.subheader(f"💬 {len(comments)} Commentaires")
            for i, c in enumerate(comments, 1):
                text = c.get('text', '')
                likes = c.get('like_count', 0)
                st.markdown(f"**#{i}** ({likes}👍)")
                st.text(text[:300])
                st.markdown("---")


def main():
    st.title("🚀 YouTube Research V7")
    st.caption("Trouve les vidéos virales et analyse leurs commentaires")
    
    params = render_sidebar()
    
    # Initialiser le state pour les logs (seulement dans main, pas dans les threads!)
    if 'all_logs' not in st.session_state:
        st.session_state.all_logs = []
    if 'all_stats' not in st.session_state:
        st.session_state.all_stats = {
            'search_results': 0,
            'details_fetched': 0,
            'details_failed': 0,
            'filtered_views': 0,
            'filtered_date': 0,
            'filtered_duration': 0,
            'filtered_language': 0,
            'passed': 0,
        }
    
    if st.sidebar.button("🚀 LANCER", type="primary", use_container_width=True):
        
        if not params['keywords']:
            st.error("❌ Entre au moins un mot-clé!")
            return
        
        # Reset
        st.session_state.all_logs = []
        st.session_state.all_stats = {
            'search_results': 0,
            'details_fetched': 0,
            'details_failed': 0,
            'filtered_views': 0,
            'filtered_date': 0,
            'filtered_duration': 0,
            'filtered_language': 0,
            'passed': 0,
        }
        
        all_logs = []
        all_logs.append("="*50)
        all_logs.append("DÉBUT DE L'ANALYSE")
        all_logs.append(f"Mots-clés: {params['keywords']}")
        all_logs.append(f"Langue: {params['language']}")
        all_logs.append(f"Vues min: {params['min_views']}")
        all_logs.append(f"Bypass: {params['bypass_filters']}")
        all_logs.append("="*50)
        
        progress = st.progress(0)
        status = st.status("Initialisation...", expanded=True)
        
        all_raw_videos = []
        
        # ===== ÉTAPE 1: RECHERCHE =====
        status.update(label="🔍 Recherche...", state="running")
        
        for i, kw in enumerate(params['keywords']):
            status.write(f"Recherche: '{kw}'...")
            
            entries, search_logs = search_youtube_pure(kw, params['videos_per_keyword'])
            all_logs.extend(search_logs)
            
            for e in entries:
                e['_source_keyword'] = kw
                all_raw_videos.append(e)
            
            st.session_state.all_stats['search_results'] += len(entries)
            progress.progress((i + 1) / len(params['keywords']) * 0.3)
        
        all_logs.append(f"RECHERCHE TERMINÉE: {len(all_raw_videos)} vidéos")
        status.write(f"✅ {len(all_raw_videos)} vidéos trouvées")
        
        if not all_raw_videos:
            status.update(label="❌ Aucune vidéo", state="error")
            st.error("La recherche n'a retourné aucune vidéo.")
            st.session_state.all_logs = all_logs
            return
        
        # ===== ÉTAPE 2: TRAITEMENT =====
        status.update(label=f"⏳ Analyse de {len(all_raw_videos)} vidéos...", state="running")
        
        processed = []
        total = len(all_raw_videos)
        done = 0
        
        # Traitement PARALLÈLE avec fonctions PURES
        with ThreadPoolExecutor(max_workers=params['max_workers']) as executor:
            futures = {
                executor.submit(
                    process_video_pure,  # Fonction PURE!
                    entry,
                    params['min_views'],
                    params['min_duration'],
                    params['date_limit'],
                    params['language'],
                    params['bypass_filters']
                ): entry for entry in all_raw_videos
            }
            
            for future in as_completed(futures):
                try:
                    result, logs, stats = future.result()
                    
                    # Collecter les logs et stats
                    all_logs.extend(logs)
                    for k, v in stats.items():
                        if k in st.session_state.all_stats:
                            st.session_state.all_stats[k] += v
                    
                    if result:
                        processed.append(result)
                
                except Exception as ex:
                    all_logs.append(f"[ERROR] Future exception: {ex}")
                    all_logs.append(traceback.format_exc())
                
                done += 1
                progress.progress(0.3 + (done / total) * 0.6)
        
        all_logs.append(f"TRAITEMENT TERMINÉ: {len(processed)} vidéos validées")
        
        # ===== ÉTAPE 3: TRI =====
        if processed:
            processed = sort_videos(processed)
        
        progress.progress(1.0)
        st.session_state.all_logs = all_logs
        
        # ===== RÉSULTATS =====
        if not processed:
            status.update(label="❌ Aucune vidéo validée", state="error")
            st.error("Aucune vidéo n'a passé les filtres. Regarde le DIAGNOSTIC ci-dessous!")
        else:
            status.update(label=f"✅ {len(processed)} vidéos!", state="complete")
            
            # Stats rapides
            col1, col2 = st.columns(2)
            col1.metric("📹 Vidéos", len(processed))
            col2.metric("📊 Ratio moyen", f"{sum(v.get('_ratio', 0) for v in processed) / len(processed):.2f}x")
            
            # Résultats
            col_prompt, col_videos = st.columns([1, 2])
            
            with col_prompt:
                st.subheader("📋 Prompt")
                prompt = build_prompt(processed, params['keywords'], params['language'])
                st.text_area("Copie:", value=prompt, height=500)
                st.download_button("📥 Télécharger", data=prompt, file_name="prompt.txt")
            
            with col_videos:
                st.subheader("📹 Vidéos")
                for idx, v in enumerate(processed[:15], 1):
                    render_video_card(v, idx)
    
    # ===== SECTION DIAGNOSTIC (toujours visible) =====
    st.divider()
    st.header("🔬 DIAGNOSTIC")
    
    stats = st.session_state.all_stats
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🔍 Trouvées", stats['search_results'])
    col2.metric("📥 Détails OK", stats['details_fetched'])
    col3.metric("❌ Détails KO", stats['details_failed'])
    col4.metric("✅ Validées", stats['passed'])
    
    st.subheader("🚫 Filtrées par")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Vues", stats['filtered_views'])
    col2.metric("Date", stats['filtered_date'])
    col3.metric("Durée", stats['filtered_duration'])
    col4.metric("Langue", stats['filtered_language'])
    
    # Logs
    st.subheader("📜 Logs")
    logs = st.session_state.all_logs
    if logs:
        log_text = "\n".join(logs[-300:])
        st.text_area("Logs", value=log_text, height=300)
        st.download_button(
            "📥 Télécharger logs",
            data="\n".join(logs),
            file_name="youtube_logs.txt",
            mime="text/plain"
        )
    else:
        st.info("Lance une analyse pour voir les logs.")


if __name__ == "__main__":
    main()
