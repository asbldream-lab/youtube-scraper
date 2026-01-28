"""
🚀 YouTube Keyword Research Tool PRO - V6 DIAGNOSTIC
====================================================
VERSION AVEC DIAGNOSTIC COMPLET
On va VOIR exactement où ça bloque!
"""

import streamlit as st
from yt_dlp import YoutubeDL
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import random
from typing import List, Dict, Optional
import re
import traceback

# ==========================================
# 📋 CONFIGURATION
# ==========================================

st.set_page_config(
    page_title="YouTube Research V6 DIAG", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

# Stockage global des logs pour diagnostic
if 'diagnostic_logs' not in st.session_state:
    st.session_state.diagnostic_logs = []

if 'filter_stats' not in st.session_state:
    st.session_state.filter_stats = {
        'total_searched': 0,
        'search_results': 0,
        'details_fetched': 0,
        'details_failed': 0,
        'filtered_views': 0,
        'filtered_date': 0,
        'filtered_duration': 0,
        'filtered_language': 0,
        'passed_all_filters': 0,
    }

def reset_diagnostics():
    st.session_state.diagnostic_logs = []
    st.session_state.filter_stats = {
        'total_searched': 0,
        'search_results': 0,
        'details_fetched': 0,
        'details_failed': 0,
        'filtered_views': 0,
        'filtered_date': 0,
        'filtered_duration': 0,
        'filtered_language': 0,
        'passed_all_filters': 0,
    }

def log(msg: str, level: str = "INFO"):
    """Ajoute un log au diagnostic"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    st.session_state.diagnostic_logs.append(f"[{timestamp}] [{level}] {msg}")
    print(f"[{timestamp}] [{level}] {msg}")  # Aussi dans le terminal

def increment_stat(key: str, value: int = 1):
    """Incrémente une statistique"""
    if key in st.session_state.filter_stats:
        st.session_state.filter_stats[key] += value


USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Safari/537.36',
]

# Mots-clés pour détection de langue SIMPLE
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
# 🔍 DÉTECTION DE LANGUE (ULTRA PERMISSIVE)
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
    """
    ULTRA PERMISSIF - retourne True dans presque tous les cas
    Ne retourne False que si on est SÛR que c'est pas la bonne langue
    """
    # Auto = tout accepté
    if target_lang == "Auto (all languages)":
        return True
    
    # Texte trop court = accepté
    if not text or len(text) < 30:
        return True
    
    # Récupérer le code cible
    target_config = LANGUAGE_KEYWORDS.get(target_lang)
    if not target_config:
        return True
    
    target_code = target_config["code"]
    detected = detect_language_simple(text)
    
    # Pas détecté = accepté (permissif)
    if detected is None:
        return True
    
    # Correspond = accepté
    if detected == target_code:
        return True
    
    # Ne correspond pas MAIS on est permissif pour éviter les faux négatifs
    # On rejette seulement si on a détecté une AUTRE langue avec confiance
    text_lower = text.lower()
    words = set(re.findall(r'\b[a-zàâäéèêëïîôùûüçñ]+\b', text_lower))
    target_markers = set(target_config["markers"])
    target_matches = len(words & target_markers)
    
    # Si on trouve AU MOINS 1 mot de la langue cible, on accepte
    if target_matches >= 1:
        return True
    
    # Sinon on rejette
    return False


# ==========================================
# 🎬 YOUTUBE PROCESSOR AVEC DIAGNOSTIC
# ==========================================

def search_youtube(keyword: str, max_results: int = 20) -> List[Dict]:
    """
    Recherche YouTube avec diagnostic complet
    """
    if not keyword or not keyword.strip():
        log(f"SEARCH: Mot-clé vide, abandon", "WARN")
        return []
    
    log(f"SEARCH: Début recherche pour '{keyword}' (max {max_results})")
    
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
                log(f"SEARCH: Résultat None pour '{keyword}'", "ERROR")
                return []
            
            entries = result.get('entries', [])
            log(f"SEARCH: {len(entries)} entrées brutes reçues")
            
            valid_entries = []
            for i, e in enumerate(entries):
                if not e:
                    log(f"SEARCH: Entrée {i} est None", "WARN")
                    continue
                
                # Essayer d'extraire l'ID
                video_id = e.get('id')
                
                if not video_id:
                    # Essayer depuis l'URL
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
                    log(f"SEARCH: Vidéo {i} OK - ID={video_id}, titre={e.get('title', 'N/A')[:40]}")
                else:
                    log(f"SEARCH: Vidéo {i} SKIP - pas d'ID trouvé. Keys: {list(e.keys())}", "WARN")
            
            log(f"SEARCH: {len(valid_entries)} vidéos valides pour '{keyword}'")
            increment_stat('search_results', len(valid_entries))
            return valid_entries
    
    except Exception as ex:
        log(f"SEARCH ERROR: {ex}", "ERROR")
        log(f"SEARCH TRACEBACK: {traceback.format_exc()}", "ERROR")
        return []


def get_video_details(video_id: str) -> Optional[Dict]:
    """
    Récupère les détails d'une vidéo avec diagnostic
    """
    if not video_id:
        log(f"DETAILS: ID vide", "WARN")
        return None
    
    log(f"DETAILS: Extraction de {video_id}")
    
    opts = {
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'socket_timeout': 20,
        'http_headers': {'User-Agent': random.choice(USER_AGENTS)},
        'skip_download': True,
        'getcomments': True,
    }
    
    try:
        url = f"https://www.youtube.com/watch?v={video_id}"
        
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if not info:
                log(f"DETAILS: Info None pour {video_id}", "ERROR")
                increment_stat('details_failed')
                return None
            
            # Log des infos clés
            log(f"DETAILS OK: {video_id}")
            log(f"  - title: {info.get('title', 'N/A')[:50]}")
            log(f"  - view_count: {info.get('view_count', 'N/A')}")
            log(f"  - channel_follower_count: {info.get('channel_follower_count', 'N/A')}")
            log(f"  - upload_date: {info.get('upload_date', 'N/A')}")
            log(f"  - duration: {info.get('duration', 'N/A')}")
            log(f"  - comments: {len(info.get('comments', []) or [])}")
            
            increment_stat('details_fetched')
            return info
    
    except Exception as ex:
        log(f"DETAILS ERROR ({video_id}): {ex}", "ERROR")
        increment_stat('details_failed')
        return None


def process_single_video(
    video_entry: Dict,
    min_views: int,
    min_duration: str,
    date_limit: Optional[datetime],
    target_language: str,
    bypass_filters: bool = False
) -> Optional[Dict]:
    """
    Traite une vidéo avec diagnostic détaillé de chaque filtre
    """
    video_id = video_entry.get('id')
    if not video_id:
        log(f"PROCESS: Pas d'ID dans l'entrée", "WARN")
        return None
    
    log(f"PROCESS: Début traitement {video_id}")
    
    # 1. Récupérer les détails
    info = get_video_details(video_id)
    if not info:
        log(f"PROCESS: Impossible de récupérer détails pour {video_id}", "ERROR")
        return None
    
    # Si bypass_filters, on skip tous les filtres
    if bypass_filters:
        log(f"PROCESS: BYPASS mode - skip tous les filtres")
        info['_ratio'] = 1.0
        info['_stars'] = "⭐"
        info['_has_flame'] = False
        info['comments'] = (info.get('comments') or [])[:20]
        increment_stat('passed_all_filters')
        return info
    
    # 2. FILTRE VUES
    view_count = info.get('view_count')
    if view_count is None:
        log(f"PROCESS: view_count est None pour {video_id} - on accepte quand même", "WARN")
        view_count = 0
    
    if view_count < min_views:
        log(f"FILTER VIEWS: {video_id} REJETÉ - {view_count} < {min_views}", "FILTER")
        increment_stat('filtered_views')
        return None
    log(f"FILTER VIEWS: {video_id} OK - {view_count} >= {min_views}")
    
    # 3. FILTRE DATE
    if date_limit:
        upload_date_str = info.get('upload_date')
        if upload_date_str:
            try:
                upload_date = datetime.strptime(upload_date_str, '%Y%m%d')
                if upload_date < date_limit:
                    log(f"FILTER DATE: {video_id} REJETÉ - {upload_date_str} trop ancien", "FILTER")
                    increment_stat('filtered_date')
                    return None
                log(f"FILTER DATE: {video_id} OK - {upload_date_str}")
            except ValueError:
                log(f"FILTER DATE: {video_id} date invalide '{upload_date_str}' - accepté", "WARN")
    
    # 4. FILTRE DURÉE
    duration = info.get('duration') or 0
    if min_duration == "2 min" and duration < 120:
        log(f"FILTER DURATION: {video_id} REJETÉ - {duration}s < 120s", "FILTER")
        increment_stat('filtered_duration')
        return None
    elif min_duration == "5 min" and duration < 300:
        log(f"FILTER DURATION: {video_id} REJETÉ - {duration}s < 300s", "FILTER")
        increment_stat('filtered_duration')
        return None
    elif min_duration == "10 min" and duration < 600:
        log(f"FILTER DURATION: {video_id} REJETÉ - {duration}s < 600s", "FILTER")
        increment_stat('filtered_duration')
        return None
    log(f"FILTER DURATION: {video_id} OK - {duration}s")
    
    # 5. FILTRE LANGUE
    title = info.get('title', '')
    description = (info.get('description') or '')[:500]
    text_to_check = f"{title} {description}"
    
    if not matches_language(text_to_check, target_language):
        detected = detect_language_simple(text_to_check)
        log(f"FILTER LANG: {video_id} REJETÉ - détecté={detected}, cible={target_language}", "FILTER")
        log(f"  Texte analysé: {text_to_check[:100]}...", "FILTER")
        increment_stat('filtered_language')
        return None
    log(f"FILTER LANG: {video_id} OK")
    
    # ===== TOUS LES FILTRES PASSÉS =====
    log(f"PROCESS: {video_id} A PASSÉ TOUS LES FILTRES! ✅")
    increment_stat('passed_all_filters')
    
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
    
    return info


# ==========================================
# 📊 TRI ET PROMPT
# ==========================================

def sort_videos(videos: List[Dict]) -> List[Dict]:
    """Trie par ratio décroissant"""
    return sorted(videos, key=lambda v: v.get('_ratio', 0), reverse=True)


def build_prompt(videos: List[Dict], keywords: List[str], lang: str) -> str:
    """Génère le prompt"""
    if not videos:
        return "Aucune vidéo."
    
    subjects = ", ".join(keywords) if keywords else "N/A"
    prompt = f"Analyse ces {len(videos)} vidéos virales sur le thème: {subjects}\n\n"
    
    for idx, v in enumerate(videos, 1):
        title = v.get('title', '?')
        url = v.get('webpage_url', '')
        views = v.get('view_count', 0)
        subs = v.get('channel_follower_count', 0)
        ratio = v.get('_ratio', 0)
        stars = v.get('_stars', '⭐')
        
        prompt += f"{'='*50}\n"
        prompt += f"#{idx} {stars} | {title}\n"
        prompt += f"{'='*50}\n"
        prompt += f"🔗 {url}\n"
        prompt += f"👁️ Vues: {views:,} | 👥 Abonnés: {subs:,} | Ratio: {ratio:.2f}x\n"
        
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
    st.sidebar.title("🔍 YouTube Research V6")
    st.sidebar.caption("Version DIAGNOSTIC")
    
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
        value=10000,  # RÉDUIT pour plus de résultats
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
    
    # Option de debug
    st.sidebar.divider()
    st.sidebar.header("🔧 Debug")
    
    bypass_filters = st.sidebar.checkbox(
        "🚫 BYPASS tous les filtres",
        value=False,
        help="Désactive TOUS les filtres pour voir si le problème vient des filtres"
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


def render_diagnostics():
    """Affiche la section de diagnostic"""
    st.divider()
    st.header("🔬 DIAGNOSTIC COMPLET")
    
    # Stats des filtres
    stats = st.session_state.filter_stats
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🔍 Vidéos recherchées", stats['search_results'])
    col2.metric("📥 Détails récupérés", stats['details_fetched'])
    col3.metric("❌ Détails échoués", stats['details_failed'])
    col4.metric("✅ Passé tous filtres", stats['passed_all_filters'])
    
    st.subheader("📊 Filtres appliqués")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🚫 Filtrées (vues)", stats['filtered_views'], delta_color="inverse")
    col2.metric("🚫 Filtrées (date)", stats['filtered_date'], delta_color="inverse")
    col3.metric("🚫 Filtrées (durée)", stats['filtered_duration'], delta_color="inverse")
    col4.metric("🚫 Filtrées (langue)", stats['filtered_language'], delta_color="inverse")
    
    # Logs détaillés
    st.subheader("📜 Logs détaillés")
    logs = st.session_state.diagnostic_logs
    
    if logs:
        # Filtrer par type
        log_filter = st.multiselect(
            "Filtrer les logs",
            ["INFO", "WARN", "ERROR", "FILTER"],
            default=["INFO", "WARN", "ERROR", "FILTER"]
        )
        
        filtered_logs = [l for l in logs if any(f"[{f}]" in l for f in log_filter)]
        
        # Afficher dans une zone scrollable
        log_text = "\n".join(filtered_logs[-200:])  # 200 derniers
        st.text_area(
            f"Logs ({len(filtered_logs)} entrées)",
            value=log_text,
            height=400
        )
        
        # Bouton pour télécharger tous les logs
        st.download_button(
            "📥 Télécharger tous les logs",
            data="\n".join(logs),
            file_name="youtube_research_logs.txt",
            mime="text/plain"
        )
    else:
        st.info("Aucun log. Lance une analyse pour voir les logs.")


def render_video_card(video: Dict, idx: int):
    """Affiche une carte vidéo"""
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
    st.title("🚀 YouTube Research V6 - DIAGNOSTIC")
    st.caption("Version avec logs complets pour identifier le problème")
    
    params = render_sidebar()
    
    # Bouton principal
    if st.sidebar.button("🚀 LANCER", type="primary", use_container_width=True):
        
        if not params['keywords']:
            st.error("❌ Entre au moins un mot-clé!")
            return
        
        # Reset diagnostics
        reset_diagnostics()
        
        log("="*50)
        log("DÉBUT DE L'ANALYSE")
        log(f"Mots-clés: {params['keywords']}")
        log(f"Langue: {params['language']}")
        log(f"Vues min: {params['min_views']}")
        log(f"Durée min: {params['min_duration']}")
        log(f"Bypass filtres: {params['bypass_filters']}")
        log("="*50)
        
        progress = st.progress(0)
        status = st.status("Initialisation...", expanded=True)
        
        all_raw_videos = []
        
        # ===== ÉTAPE 1: RECHERCHE =====
        status.update(label="🔍 Recherche...", state="running")
        
        for i, kw in enumerate(params['keywords']):
            status.write(f"Recherche: '{kw}'...")
            increment_stat('total_searched')
            
            entries = search_youtube(kw, params['videos_per_keyword'])
            
            for e in entries:
                e['_source_keyword'] = kw
                all_raw_videos.append(e)
            
            progress.progress((i + 1) / len(params['keywords']) * 0.3)
        
        log(f"RECHERCHE TERMINÉE: {len(all_raw_videos)} vidéos brutes")
        status.write(f"✅ {len(all_raw_videos)} vidéos trouvées")
        
        if not all_raw_videos:
            status.update(label="❌ Aucune vidéo", state="error")
            st.error("La recherche n'a retourné aucune vidéo. Vérifie ta connexion internet.")
            render_diagnostics()
            return
        
        # ===== ÉTAPE 2: TRAITEMENT =====
        status.update(label=f"⏳ Analyse de {len(all_raw_videos)} vidéos...", state="running")
        
        processed = []
        total = len(all_raw_videos)
        done = 0
        
        # Traitement séquentiel pour mieux voir les logs (ou parallèle)
        if params['max_workers'] <= 1:
            # Séquentiel
            for entry in all_raw_videos:
                result = process_single_video(
                    entry,
                    params['min_views'],
                    params['min_duration'],
                    params['date_limit'],
                    params['language'],
                    params['bypass_filters']
                )
                if result:
                    processed.append(result)
                
                done += 1
                progress.progress(0.3 + (done / total) * 0.6)
                status.write(f"Traité: {done}/{total}")
        else:
            # Parallèle
            with ThreadPoolExecutor(max_workers=params['max_workers']) as executor:
                futures = {
                    executor.submit(
                        process_single_video,
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
                        result = future.result()
                        if result:
                            processed.append(result)
                    except Exception as ex:
                        log(f"FUTURE ERROR: {ex}", "ERROR")
                    
                    done += 1
                    progress.progress(0.3 + (done / total) * 0.6)
        
        log(f"TRAITEMENT TERMINÉ: {len(processed)} vidéos validées")
        
        # ===== ÉTAPE 3: TRI =====
        if processed:
            processed = sort_videos(processed)
        
        progress.progress(1.0)
        
        # ===== RÉSULTATS =====
        if not processed:
            status.update(label="❌ Aucune vidéo validée", state="error")
            st.error("Aucune vidéo n'a passé les filtres. Regarde le DIAGNOSTIC ci-dessous!")
            render_diagnostics()
            return
        
        status.update(label=f"✅ {len(processed)} vidéos!", state="complete")
        
        # Stats
        col1, col2 = st.columns(2)
        col1.metric("📹 Vidéos trouvées", len(processed))
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
        
        # Diagnostic
        render_diagnostics()
    
    else:
        # Afficher diagnostic même sans lancer
        if st.session_state.diagnostic_logs:
            render_diagnostics()


if __name__ == "__main__":
    main()
