"""
🚀 YouTube Keyword Research Tool PRO - V8
==========================================
CORRECTION: Recherche YouTube dans la langue cible + filtre permissif
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
    page_title="YouTube Research V8", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Safari/537.36',
]

# Configuration des langues avec codes pour YouTube
LANGUAGE_CONFIG = {
    "Auto (all languages)": {
        "hl": None,  # YouTube interface language
        "gl": None,  # Geo location
        "code": None,
        "markers": []
    },
    "French": {
        "hl": "fr",
        "gl": "FR",
        "code": "fr",
        "markers": ["le", "la", "les", "de", "du", "des", "un", "une", "et", "est", "sont", 
                   "dans", "pour", "sur", "avec", "qui", "que", "ce", "cette", "nous", "vous",
                   "je", "tu", "il", "elle", "c'est", "très", "plus", "mais", "aussi", "tout",
                   "être", "avoir", "faire", "dire", "pouvoir", "aller", "voir", "vouloir"]
    },
    "English": {
        "hl": "en",
        "gl": "US",
        "code": "en",
        "markers": ["the", "and", "is", "are", "was", "were", "have", "has", "been",
                   "this", "that", "with", "for", "not", "you", "all", "can", "had",
                   "but", "what", "when", "your", "which", "will", "would", "they"]
    },
    "Spanish": {
        "hl": "es",
        "gl": "ES",
        "code": "es",
        "markers": ["el", "la", "los", "las", "de", "en", "que", "es", "un", "una",
                   "por", "con", "para", "como", "más", "pero", "sus", "este", "son"]
    },
}


# ==========================================
# 🔍 FONCTIONS DE LANGUE
# ==========================================

def detect_language_simple(text: str) -> Optional[str]:
    """Détecte la langue basée sur les mots-clés"""
    if not text or len(text) < 5:
        return None
    
    text_lower = text.lower()
    words = set(re.findall(r'\b[a-zàâäéèêëïîôùûüçñ]+\b', text_lower))
    
    scores = {}
    for lang_name, config in LANGUAGE_CONFIG.items():
        if lang_name == "Auto (all languages)":
            continue
        markers = set(config.get("markers", []))
        matches = len(words & markers)
        if matches > 0:
            scores[config["code"]] = matches
    
    if not scores:
        return None
    
    return max(scores, key=scores.get)


def matches_language(text: str, target_lang: str, strict: bool = False) -> Tuple[bool, str]:
    """
    Vérifie si le texte correspond à la langue cible.
    
    Args:
        text: Le texte à analyser
        target_lang: La langue cible ("French", "English", etc.)
        strict: Si True, rejette si une autre langue est détectée
                Si False (défaut), accepte si au moins quelques mots de la langue cible
    
    Returns:
        (bool, str): (accepté ou non, raison)
    """
    # Auto = tout accepté
    if target_lang == "Auto (all languages)":
        return True, "Auto mode"
    
    # Texte trop court = accepté
    if not text or len(text) < 20:
        return True, "Texte trop court"
    
    target_config = LANGUAGE_CONFIG.get(target_lang)
    if not target_config:
        return True, "Langue non configurée"
    
    target_code = target_config["code"]
    target_markers = set(target_config.get("markers", []))
    
    # Analyser le texte
    text_lower = text.lower()
    words = set(re.findall(r'\b[a-zàâäéèêëïîôùûüçñ]+\b', text_lower))
    
    # Compter les mots de la langue cible
    target_matches = len(words & target_markers)
    
    # Détecter la langue dominante
    detected = detect_language_simple(text)
    
    if strict:
        # Mode strict: la langue détectée doit correspondre
        if detected == target_code:
            return True, f"Langue détectée: {detected}"
        elif detected is None:
            return True, "Langue non détectée (accepté)"
        else:
            return False, f"Langue détectée: {detected}, attendu: {target_code}"
    else:
        # Mode permissif (défaut): accepte si quelques mots de la langue cible
        if target_matches >= 1:
            return True, f"{target_matches} mots {target_lang} trouvés"
        elif detected is None:
            return True, "Langue non détectée (accepté)"
        else:
            return False, f"Aucun mot {target_lang}, détecté: {detected}"


# ==========================================
# 🎬 FONCTIONS YOUTUBE (PURES)
# ==========================================

def search_youtube_pure(
    keyword: str, 
    max_results: int = 20,
    target_lang: str = "Auto (all languages)"
) -> Tuple[List[Dict], List[str]]:
    """
    Recherche YouTube avec paramètres de langue.
    """
    logs = []
    
    if not keyword or not keyword.strip():
        logs.append("[WARN] Mot-clé vide")
        return [], logs
    
    logs.append(f"[INFO] SEARCH: '{keyword}' (max {max_results}, langue={target_lang})")
    
    # Configuration de base
    opts = {
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'socket_timeout': 20,
        'http_headers': {'User-Agent': random.choice(USER_AGENTS)},
        'extract_flat': True,
    }
    
    # Ajouter les paramètres de langue pour la recherche
    lang_config = LANGUAGE_CONFIG.get(target_lang, {})
    if lang_config.get("gl"):
        opts['geo_bypass_country'] = lang_config["gl"]
        logs.append(f"[INFO] Geo: {lang_config['gl']}")
    
    # Construire l'URL de recherche avec paramètres de langue
    search_query = f"ytsearch{max_results}:{keyword.strip()}"
    
    # Si une langue est spécifiée, on peut aussi modifier les headers
    if lang_config.get("hl"):
        opts['http_headers']['Accept-Language'] = f"{lang_config['hl']},{lang_config['hl']}-{lang_config.get('gl', 'XX')};q=0.9"
        logs.append(f"[INFO] Accept-Language: {lang_config['hl']}")
    
    try:
        with YoutubeDL(opts) as ydl:
            result = ydl.extract_info(search_query, download=False)
            
            if not result:
                logs.append(f"[ERROR] Résultat None")
                return [], logs
            
            entries = result.get('entries', [])
            logs.append(f"[INFO] {len(entries)} entrées brutes")
            
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
                    title = e.get('title', 'N/A')[:40]
                    logs.append(f"[INFO] Video {i}: {video_id} - {title}")
            
            logs.append(f"[INFO] {len(valid_entries)} vidéos valides")
            return valid_entries, logs
    
    except Exception as ex:
        logs.append(f"[ERROR] {ex}")
        return [], logs


def get_video_details_pure(video_id: str) -> Tuple[Optional[Dict], List[str]]:
    """Récupère les détails d'une vidéo"""
    logs = []
    
    if not video_id:
        return None, logs
    
    logs.append(f"[INFO] DETAILS: {video_id}")
    
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
            
            logs.append(f"[INFO] OK: {info.get('title', 'N/A')[:40]}")
            logs.append(f"[INFO]   views={info.get('view_count', 0)}, subs={info.get('channel_follower_count', 'N/A')}")
            logs.append(f"[INFO]   comments={len(info.get('comments', []) or [])}")
            
            return info, logs
    
    except Exception as ex:
        logs.append(f"[ERROR] {video_id}: {ex}")
        return None, logs


def process_video_pure(
    video_entry: Dict,
    min_views: int,
    min_duration: str,
    date_limit: Optional[datetime],
    target_language: str,
    strict_language: bool = False,
    bypass_filters: bool = False
) -> Tuple[Optional[Dict], List[str], Dict]:
    """
    Traite une vidéo - FONCTION PURE
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
        return None, logs, stats
    
    # 1. Récupérer les détails
    info, detail_logs = get_video_details_pure(video_id)
    logs.extend(detail_logs)
    
    if not info:
        stats['details_failed'] = 1
        return None, logs, stats
    
    stats['details_fetched'] = 1
    
    # Si bypass, on skip les filtres
    if bypass_filters:
        logs.append(f"[INFO] BYPASS pour {video_id}")
        info['_ratio'] = 1.0
        info['_stars'] = "⭐"
        info['_has_flame'] = False
        raw_comments = info.get('comments') or []
        sorted_comments = sorted(
            [c for c in raw_comments if isinstance(c, dict) and c.get('text')],
            key=lambda x: x.get('like_count', 0) or 0,
            reverse=True
        )
        info['comments'] = sorted_comments[:20]
        stats['passed'] = 1
        return info, logs, stats
    
    # 2. FILTRE VUES
    view_count = info.get('view_count') or 0
    if view_count < min_views:
        logs.append(f"[FILTER] VUES: {video_id} - {view_count} < {min_views}")
        stats['filtered_views'] = 1
        return None, logs, stats
    logs.append(f"[OK] VUES: {view_count}")
    
    # 3. FILTRE DATE
    if date_limit:
        upload_date_str = info.get('upload_date')
        if upload_date_str:
            try:
                upload_date = datetime.strptime(upload_date_str, '%Y%m%d')
                if upload_date < date_limit:
                    logs.append(f"[FILTER] DATE: {video_id} - {upload_date_str}")
                    stats['filtered_date'] = 1
                    return None, logs, stats
            except ValueError:
                pass
    
    # 4. FILTRE DURÉE
    duration = info.get('duration') or 0
    if min_duration == "2 min" and duration < 120:
        logs.append(f"[FILTER] DURÉE: {video_id} - {duration}s < 120s")
        stats['filtered_duration'] = 1
        return None, logs, stats
    elif min_duration == "5 min" and duration < 300:
        logs.append(f"[FILTER] DURÉE: {video_id} - {duration}s < 300s")
        stats['filtered_duration'] = 1
        return None, logs, stats
    elif min_duration == "10 min" and duration < 600:
        logs.append(f"[FILTER] DURÉE: {video_id} - {duration}s < 600s")
        stats['filtered_duration'] = 1
        return None, logs, stats
    
    # 5. FILTRE LANGUE (avec option strict/permissif)
    title = info.get('title', '')
    description = (info.get('description') or '')[:500]
    text_to_check = f"{title} {description}"
    
    lang_ok, lang_reason = matches_language(text_to_check, target_language, strict=strict_language)
    
    if not lang_ok:
        logs.append(f"[FILTER] LANGUE: {video_id} - {lang_reason}")
        stats['filtered_language'] = 1
        return None, logs, stats
    logs.append(f"[OK] LANGUE: {lang_reason}")
    
    # ===== PASSÉ =====
    logs.append(f"[SUCCESS] ✅ {video_id} VALIDÉ!")
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
    sorted_comments = sorted(
        [c for c in raw_comments if isinstance(c, dict) and c.get('text')],
        key=lambda x: x.get('like_count', 0) or 0,
        reverse=True
    )
    info['comments'] = sorted_comments[:20]
    
    return info, logs, stats


# ==========================================
# 📊 UTILITAIRES
# ==========================================

def sort_videos(videos: List[Dict]) -> List[Dict]:
    return sorted(videos, key=lambda v: v.get('_ratio', 0), reverse=True)


def build_prompt(videos: List[Dict], keywords: List[str]) -> str:
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
    st.sidebar.title("🔍 YouTube Research V8")
    
    # Mots-clés
    st.sidebar.header("📝 Mots-clés")
    keywords_text = st.sidebar.text_area(
        "Un par ligne",
        height=80,
        placeholder="trump ice\nmacron france\nelon musk"
    )
    keywords = [k.strip() for k in keywords_text.split('\n') if k.strip()]
    
    st.sidebar.divider()
    
    # Filtres
    st.sidebar.header("🎯 Filtres")
    
    language = st.sidebar.selectbox(
        "🌍 Langue des vidéos",
        list(LANGUAGE_CONFIG.keys()),
        help="Recherche ET filtre par cette langue"
    )
    
    strict_language = st.sidebar.checkbox(
        "🔒 Filtre langue STRICT",
        value=False,
        help="Si coché: rejette si la langue détectée ne correspond pas\nSi décoché: accepte si quelques mots de la langue sont présents"
    )
    
    min_views = st.sidebar.number_input(
        "👁️ Vues minimum",
        value=50000,
        step=10000,
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
        min_value=5,
        max_value=30,
        value=15
    )
    
    max_workers = st.sidebar.slider(
        "Threads",
        min_value=1,
        max_value=10,
        value=5
    )
    
    st.sidebar.divider()
    
    bypass_filters = st.sidebar.checkbox(
        "🚫 BYPASS filtres",
        value=False
    )
    
    return {
        'keywords': keywords,
        'language': language,
        'strict_language': strict_language,
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
            st.write(f"📺 {video.get('uploader', '?')}")
            st.write(f"👥 {video.get('channel_follower_count', 0):,} abonnés")
            st.write(f"👁️ {views:,} vues")
            st.write(f"📊 Ratio: **{ratio:.2f}x**")
            
            url = video.get('webpage_url', '')
            if url:
                st.link_button("▶️ YouTube", url)
        
        comments = video.get('comments', [])
        if comments:
            st.divider()
            st.subheader(f"💬 {len(comments)} Commentaires")
            for i, c in enumerate(comments, 1):
                text = c.get('text', '')
                likes = c.get('like_count', 0)
                st.markdown(f"**#{i}** ({likes}👍)")
                st.text(text[:400])
                st.markdown("---")


def main():
    st.title("🚀 YouTube Research V8")
    st.caption("Recherche de vidéos virales avec filtrage par langue")
    
    # Info box
    st.info("""
    **💡 Conseil pour la langue:**
    - La recherche YouTube utilise les paramètres de langue sélectionnés
    - Le filtre "Strict" rejette les vidéos qui ne sont clairement pas dans la langue cible
    - Le filtre "Permissif" (par défaut) accepte les vidéos qui contiennent quelques mots de la langue
    - Utilise "Auto" pour chercher dans toutes les langues
    """)
    
    params = render_sidebar()
    
    # State
    if 'all_logs' not in st.session_state:
        st.session_state.all_logs = []
    if 'all_stats' not in st.session_state:
        st.session_state.all_stats = {}
    
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
        all_logs.append(f"Mots-clés: {params['keywords']}")
        all_logs.append(f"Langue: {params['language']} (strict={params['strict_language']})")
        all_logs.append(f"Vues min: {params['min_views']}")
        all_logs.append("="*50)
        
        progress = st.progress(0)
        status = st.status("Recherche...", expanded=True)
        
        all_raw_videos = []
        
        # RECHERCHE
        for i, kw in enumerate(params['keywords']):
            status.write(f"🔍 Recherche: '{kw}'...")
            
            entries, search_logs = search_youtube_pure(
                kw, 
                params['videos_per_keyword'],
                params['language']
            )
            all_logs.extend(search_logs)
            
            for e in entries:
                e['_source_keyword'] = kw
                all_raw_videos.append(e)
            
            st.session_state.all_stats['search_results'] += len(entries)
            progress.progress((i + 1) / len(params['keywords']) * 0.3)
        
        all_logs.append(f"TOTAL: {len(all_raw_videos)} vidéos trouvées")
        status.write(f"✅ {len(all_raw_videos)} vidéos")
        
        if not all_raw_videos:
            status.update(label="❌ Aucune vidéo", state="error")
            st.session_state.all_logs = all_logs
            return
        
        # TRAITEMENT
        status.update(label=f"⏳ Analyse...", state="running")
        
        processed = []
        total = len(all_raw_videos)
        done = 0
        
        with ThreadPoolExecutor(max_workers=params['max_workers']) as executor:
            futures = {
                executor.submit(
                    process_video_pure,
                    entry,
                    params['min_views'],
                    params['min_duration'],
                    params['date_limit'],
                    params['language'],
                    params['strict_language'],
                    params['bypass_filters']
                ): entry for entry in all_raw_videos
            }
            
            for future in as_completed(futures):
                try:
                    result, logs, stats = future.result()
                    all_logs.extend(logs)
                    
                    for k, v in stats.items():
                        if k in st.session_state.all_stats:
                            st.session_state.all_stats[k] += v
                    
                    if result:
                        processed.append(result)
                
                except Exception as ex:
                    all_logs.append(f"[ERROR] {ex}")
                
                done += 1
                progress.progress(0.3 + (done / total) * 0.6)
        
        # TRI
        if processed:
            processed = sort_videos(processed)
        
        progress.progress(1.0)
        st.session_state.all_logs = all_logs
        
        # RÉSULTATS
        if not processed:
            status.update(label="❌ Aucune vidéo", state="error")
            st.error("""
            **Aucune vidéo validée!**
            
            Essaie:
            - Mets la langue sur **"Auto"** ou décoche **"Filtre strict"**
            - Réduis les **vues minimum**
            - Utilise des **mots-clés dans la langue cible** (ex: "trump france" pour français)
            """)
        else:
            status.update(label=f"✅ {len(processed)} vidéos!", state="complete")
            
            col1, col2 = st.columns(2)
            col1.metric("📹 Vidéos", len(processed))
            avg_ratio = sum(v.get('_ratio', 0) for v in processed) / len(processed)
            col2.metric("📊 Ratio moyen", f"{avg_ratio:.2f}x")
            
            col_prompt, col_videos = st.columns([1, 2])
            
            with col_prompt:
                st.subheader("📋 Prompt")
                prompt = build_prompt(processed, params['keywords'])
                st.text_area("Copie:", value=prompt, height=500)
                st.download_button("📥 Télécharger", data=prompt, file_name="prompt.txt")
            
            with col_videos:
                st.subheader("📹 Vidéos")
                for idx, v in enumerate(processed[:15], 1):
                    render_video_card(v, idx)
    
    # DIAGNOSTIC
    st.divider()
    st.header("🔬 Diagnostic")
    
    stats = st.session_state.all_stats
    if stats:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("🔍 Trouvées", stats.get('search_results', 0))
        col2.metric("📥 Détails OK", stats.get('details_fetched', 0))
        col3.metric("❌ Détails KO", stats.get('details_failed', 0))
        col4.metric("✅ Validées", stats.get('passed', 0))
        
        st.subheader("🚫 Filtrées par")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Vues", stats.get('filtered_views', 0))
        col2.metric("Date", stats.get('filtered_date', 0))
        col3.metric("Durée", stats.get('filtered_duration', 0))
        col4.metric("Langue", stats.get('filtered_language', 0))
    
    logs = st.session_state.all_logs
    if logs:
        st.subheader("📜 Logs")
        st.text_area("", value="\n".join(logs[-200:]), height=250)
        st.download_button("📥 Logs complets", data="\n".join(logs), file_name="logs.txt")


if __name__ == "__main__":
    main()
