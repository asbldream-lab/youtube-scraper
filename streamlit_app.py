"""
🚀 YouTube Keyword Research Tool PRO - V5 STABLE
==============================================
Basé sur V3 qui fonctionnait + corrections critiques

CORRECTIONS:
1. Options yt-dlp TESTÉES et FONCTIONNELLES
2. Filtre de langue PERMISSIF (accepte en cas de doute)
3. 20 commentaires avec fallback
4. Flamme OPTIONNELLE (désactivable si trop lent)
5. LOGS pour déboguer
"""

import streamlit as st
from yt_dlp import YoutubeDL
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import random
from typing import List, Dict, Optional
import re

# ==========================================
# 📋 CONFIGURATION
# ==========================================

st.set_page_config(
    page_title="YouTube Research Pro V5", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

# Mode debug - mettre à True pour voir les logs
DEBUG_MODE = True

def debug_log(msg: str):
    """Affiche un log si DEBUG_MODE est activé"""
    if DEBUG_MODE:
        print(f"[DEBUG] {msg}")

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Safari/537.36',
]

# Mots-clés pour détection de langue SIMPLE (sans dépendance externe)
LANGUAGE_KEYWORDS = {
    "French": {
        "code": "fr",
        "markers": ["le", "la", "les", "de", "du", "des", "un", "une", "et", "est", "sont", 
                   "dans", "pour", "sur", "avec", "qui", "que", "ce", "cette", "nous", "vous",
                   "je", "tu", "il", "elle", "c'est", "n'est", "qu'il", "qu'elle", "très",
                   "plus", "mais", "aussi", "comme", "tout", "tous", "faire", "fait"]
    },
    "English": {
        "code": "en",
        "markers": ["the", "and", "is", "are", "was", "were", "have", "has", "been",
                   "this", "that", "with", "for", "not", "you", "all", "can", "had",
                   "but", "what", "when", "your", "which", "their", "will", "would",
                   "there", "from", "they", "been", "have", "or", "an", "be", "it"]
    },
    "Spanish": {
        "code": "es",
        "markers": ["el", "la", "los", "las", "de", "en", "que", "es", "un", "una",
                   "por", "con", "para", "como", "más", "pero", "sus", "este", "esta",
                   "son", "del", "se", "al", "lo", "todo", "esta", "entre", "cuando"]
    },
    "German": {
        "code": "de",
        "markers": ["der", "die", "das", "und", "ist", "von", "mit", "den", "für",
                   "auf", "nicht", "sich", "auch", "als", "noch", "nach", "bei", "aus"]
    },
}

PROMPT_TEMPLATES = {
    "French": {
        "text": """Tu es un expert YouTube. Analyse ces vidéos virales et leurs commentaires pour trouver des opportunités de contenu:\n\nThème recherché: {subjects}\n\n""",
        "header": "💬 TOP COMMENTAIRES",
        "label": "Com"
    },
    "English": {
        "text": """You are a YouTube expert. Analyze these viral videos and comments to find content opportunities:\n\nTopic: {subjects}\n\n""",
        "header": "💬 TOP COMMENTS",
        "label": "Comment"
    },
    "Spanish": {
        "text": """Eres un experto en YouTube. Analiza estos videos virales y comentarios:\n\nTema: {subjects}\n\n""",
        "header": "💬 TOP COMENTARIOS",
        "label": "Comentario"
    },
}

# Fallback pour les langues non définies
for lang in ["Auto (all languages)", "German"]:
    PROMPT_TEMPLATES[lang] = PROMPT_TEMPLATES["English"]


# ==========================================
# 🛠️ DÉTECTION DE LANGUE (SANS DÉPENDANCE)
# ==========================================

class SimpleLanguageDetector:
    """
    Détecteur de langue SIMPLE basé sur des mots-clés.
    Pas de dépendance externe = pas de risque d'erreur.
    """
    
    @staticmethod
    def detect(text: str) -> Optional[str]:
        """
        Détecte la langue d'un texte.
        Retourne: 'fr', 'en', 'es', 'de' ou None si indéterminé
        """
        if not text or len(text) < 10:
            return None
        
        text_lower = text.lower()
        # Extraire les mots
        words = set(re.findall(r'\b[a-zàâäéèêëïîôùûüç]+\b', text_lower))
        
        scores = {}
        for lang_name, config in LANGUAGE_KEYWORDS.items():
            markers = set(config["markers"])
            # Compter combien de marqueurs sont présents
            matches = len(words & markers)
            if matches > 0:
                scores[config["code"]] = matches
        
        if not scores:
            return None
        
        # Retourner la langue avec le plus de matches
        best_lang = max(scores, key=scores.get)
        # Seuil minimum: au moins 2 mots marqueurs
        if scores[best_lang] >= 2:
            return best_lang
        
        return None
    
    @staticmethod
    def matches_language(text: str, target_lang: str) -> bool:
        """
        Vérifie si un texte correspond à la langue cible.
        PERMISSIF: retourne True en cas de doute.
        """
        # Si "Auto", tout est accepté
        if target_lang == "Auto (all languages)":
            return True
        
        # Si texte trop court, on accepte (pas assez d'info)
        if not text or len(text) < 20:
            return True
        
        # Récupérer le code ISO de la langue cible
        target_config = LANGUAGE_KEYWORDS.get(target_lang)
        if not target_config:
            return True  # Langue non supportée = accepter
        
        target_code = target_config["code"]
        
        # Détecter la langue du texte
        detected = SimpleLanguageDetector.detect(text)
        
        # Si on n'a pas pu détecter, on accepte (permissif)
        if detected is None:
            return True
        
        # Sinon, vérifier si ça correspond
        return detected == target_code


# ==========================================
# 🎬 YOUTUBE PROCESSOR
# ==========================================

class YouTubeProcessor:
    """
    Processeur YouTube robuste avec options TESTÉES.
    """
    
    def __init__(self, language: str = "Auto (all languages)"):
        self.language = language
        self.channel_cache = {}  # Cache pour les moyennes de chaînes
    
    def _get_base_opts(self) -> dict:
        """Options de base communes"""
        return {
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'socket_timeout': 15,
            'http_headers': {'User-Agent': random.choice(USER_AGENTS)},
        }
    
    def search_videos(self, keyword: str, max_results: int = 20) -> List[Dict]:
        """
        Recherche des vidéos par mot-clé.
        Retourne une liste d'entrées BRUTES (id + titre basique).
        """
        if not keyword or not keyword.strip():
            debug_log(f"search_videos: mot-clé vide")
            return []
        
        opts = self._get_base_opts()
        opts['extract_flat'] = True  # IMPORTANT: True, pas 'in_playlist'
        
        try:
            search_query = f"ytsearch{max_results}:{keyword.strip()}"
            debug_log(f"search_videos: recherche '{search_query}'")
            
            with YoutubeDL(opts) as ydl:
                result = ydl.extract_info(search_query, download=False)
                
                if not result:
                    debug_log(f"search_videos: aucun résultat pour '{keyword}'")
                    return []
                
                entries = result.get('entries', [])
                valid_entries = []
                
                for e in entries:
                    if e and (e.get('id') or e.get('url')):
                        # Extraire l'ID de différentes manières possibles
                        video_id = e.get('id')
                        if not video_id and e.get('url'):
                            # Essayer d'extraire l'ID de l'URL
                            url = e.get('url', '')
                            if 'watch?v=' in url:
                                video_id = url.split('watch?v=')[1].split('&')[0]
                            elif 'youtu.be/' in url:
                                video_id = url.split('youtu.be/')[1].split('?')[0]
                        
                        if video_id:
                            e['id'] = video_id
                            valid_entries.append(e)
                
                debug_log(f"search_videos: {len(valid_entries)} vidéos trouvées pour '{keyword}'")
                return valid_entries
        
        except Exception as ex:
            debug_log(f"search_videos ERROR: {ex}")
            return []
    
    def get_video_details(self, video_id: str, get_comments: bool = True) -> Optional[Dict]:
        """
        Récupère les détails complets d'une vidéo.
        """
        if not video_id:
            return None
        
        opts = self._get_base_opts()
        opts['skip_download'] = True
        
        if get_comments:
            opts['getcomments'] = True
            # Format simple qui fonctionne
            opts['extractor_args'] = {'youtube': {'max_comments': ['100']}}
        
        try:
            url = f"https://www.youtube.com/watch?v={video_id}"
            debug_log(f"get_video_details: extraction de {video_id}")
            
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                if info:
                    debug_log(f"get_video_details OK: {info.get('title', 'N/A')[:30]}... | vues={info.get('view_count', 0)}")
                else:
                    debug_log(f"get_video_details: aucune info pour {video_id}")
                
                return info
        
        except Exception as ex:
            debug_log(f"get_video_details ERROR ({video_id}): {ex}")
            return None
    
    def get_channel_videos(self, channel_id: str, max_videos: int = 20) -> List[Dict]:
        """
        Récupère les dernières vidéos d'une chaîne (pour calcul flamme).
        """
        if not channel_id:
            return []
        
        # Vérifier le cache
        if channel_id in self.channel_cache:
            return self.channel_cache[channel_id]
        
        opts = self._get_base_opts()
        opts['extract_flat'] = True
        opts['playlistend'] = max_videos
        
        try:
            url = f"https://www.youtube.com/channel/{channel_id}/videos"
            
            with YoutubeDL(opts) as ydl:
                result = ydl.extract_info(url, download=False)
                
                if result and 'entries' in result:
                    entries = [e for e in result['entries'] if e][:max_videos]
                    self.channel_cache[channel_id] = entries
                    return entries
            
            return []
        
        except Exception as ex:
            debug_log(f"get_channel_videos ERROR: {ex}")
            return []
    
    def process_video(
        self,
        video_entry: Dict,
        min_views: int,
        min_duration: str,
        date_limit: Optional[datetime],
        enable_flame: bool = False
    ) -> Optional[Dict]:
        """
        Traitement complet d'une vidéo:
        1. Récupère les détails
        2. Applique les filtres
        3. Calcule ratio et flamme
        4. Filtre les commentaires
        
        Retourne None si la vidéo ne passe pas les filtres.
        """
        video_id = video_entry.get('id')
        if not video_id:
            debug_log(f"process_video: pas d'ID dans l'entrée")
            return None
        
        # 1. Récupérer les détails
        info = self.get_video_details(video_id, get_comments=True)
        if not info:
            debug_log(f"process_video: impossible de récupérer {video_id}")
            return None
        
        # 2. FILTRE PAR VUES
        view_count = info.get('view_count') or 0
        if view_count < min_views:
            debug_log(f"process_video SKIP (vues): {video_id} a {view_count} vues < {min_views}")
            return None
        
        # 3. FILTRE PAR DATE
        if date_limit:
            upload_date_str = info.get('upload_date')
            if upload_date_str:
                try:
                    upload_date = datetime.strptime(upload_date_str, '%Y%m%d')
                    if upload_date < date_limit:
                        debug_log(f"process_video SKIP (date): {video_id} uploadé le {upload_date_str}")
                        return None
                except ValueError:
                    pass  # Date invalide, on ignore le filtre
        
        # 4. FILTRE PAR DURÉE
        duration = info.get('duration') or 0
        if min_duration == "2 min" and duration < 120:
            debug_log(f"process_video SKIP (durée): {video_id} dure {duration}s < 120s")
            return None
        elif min_duration == "5 min" and duration < 300:
            debug_log(f"process_video SKIP (durée): {video_id} dure {duration}s < 300s")
            return None
        elif min_duration == "10 min" and duration < 600:
            debug_log(f"process_video SKIP (durée): {video_id} dure {duration}s < 600s")
            return None
        
        # 5. FILTRE PAR LANGUE (PERMISSIF)
        title = info.get('title', '')
        description = info.get('description', '')[:300] if info.get('description') else ''
        text_to_check = f"{title} {description}"
        
        if not SimpleLanguageDetector.matches_language(text_to_check, self.language):
            debug_log(f"process_video SKIP (langue): {video_id} ne correspond pas à {self.language}")
            return None
        
        # ===== VIDÉO ACCEPTÉE - Calculs supplémentaires =====
        
        # 6. CALCUL DU RATIO (étoiles)
        subs = info.get('channel_follower_count') or 1
        if subs <= 0:
            subs = 1
        ratio = view_count / subs
        info['_ratio'] = ratio
        info['_stars'] = self._get_stars(ratio)
        
        # 7. CALCUL DE LA FLAMME (optionnel)
        info['_has_flame'] = False
        info['_channel_avg'] = 0
        
        if enable_flame:
            channel_id = info.get('channel_id')
            if channel_id:
                channel_videos = self.get_channel_videos(channel_id)
                if channel_videos:
                    views_list = []
                    for cv in channel_videos:
                        cv_views = cv.get('view_count')
                        if cv_views and cv_views > 0:
                            views_list.append(cv_views)
                    
                    if views_list:
                        avg_views = sum(views_list) / len(views_list)
                        info['_channel_avg'] = avg_views
                        if view_count > avg_views:
                            info['_has_flame'] = True
                            debug_log(f"process_video FLAME: {video_id} a {view_count} vues > {avg_views:.0f} moyenne")
        
        # 8. FILTRER LES COMMENTAIRES (top 20)
        raw_comments = info.get('comments') or []
        if raw_comments:
            # Trier par likes
            sorted_comments = sorted(
                [c for c in raw_comments if isinstance(c, dict) and c.get('text')],
                key=lambda x: x.get('like_count', 0) or 0,
                reverse=True
            )
            info['comments'] = sorted_comments[:20]
            debug_log(f"process_video: {len(info['comments'])} commentaires pour {video_id}")
        else:
            info['comments'] = []
        
        debug_log(f"process_video OK: {video_id} | ratio={ratio:.2f} | flamme={info['_has_flame']}")
        return info
    
    @staticmethod
    def _get_stars(ratio: float) -> str:
        """
        Système d'étoiles:
        - < 1x abonnés = ⭐
        - >= 1x abonnés = ⭐⭐
        - >= 2x abonnés = ⭐⭐⭐
        """
        if ratio >= 2:
            return "⭐⭐⭐"
        elif ratio >= 1:
            return "⭐⭐"
        return "⭐"


# ==========================================
# 📊 ANALYSE ET TRI
# ==========================================

def sort_videos_by_performance(videos: List[Dict]) -> List[Dict]:
    """
    Trie les vidéos:
    1. Flammes d'abord (🔥)
    2. Par ratio décroissant
    """
    def sort_key(v):
        flame_priority = 1 if v.get('_has_flame') else 0
        ratio = v.get('_ratio', 0)
        return (flame_priority, ratio)
    
    return sorted(videos, key=sort_key, reverse=True)


def build_prompt(videos: List[Dict], keywords: List[str], lang: str) -> str:
    """Génère le prompt pour Claude"""
    if not videos:
        return "Aucune vidéo trouvée."
    
    template = PROMPT_TEMPLATES.get(lang, PROMPT_TEMPLATES["English"])
    subjects = ", ".join(keywords) if keywords else "Non spécifié"
    
    prompt = template["text"].format(subjects=subjects)
    prompt += f"📊 {len(videos)} vidéos analysées\n\n"
    
    for idx, video in enumerate(videos, 1):
        title = video.get('title', 'Titre inconnu')
        url = video.get('webpage_url', '')
        views = video.get('view_count', 0)
        subs = video.get('channel_follower_count', 0)
        ratio = video.get('_ratio', 0)
        stars = video.get('_stars', '⭐')
        has_flame = video.get('_has_flame', False)
        channel_avg = video.get('_channel_avg', 0)
        channel = video.get('uploader', 'Chaîne inconnue')
        
        # En-tête
        flame_str = " 🔥" if has_flame else ""
        prompt += f"{'='*60}\n"
        prompt += f"#{idx} {stars}{flame_str} | {title}\n"
        prompt += f"{'='*60}\n"
        prompt += f"📺 Chaîne: {channel}\n"
        prompt += f"🔗 {url}\n"
        prompt += f"👁️ Vues: {views:,} | 👥 Abonnés: {subs:,} | 📊 Ratio: {ratio:.2f}x\n"
        
        if has_flame and channel_avg:
            prompt += f"🔥 SURPERFORME: {views:,} vues vs {channel_avg:,.0f} en moyenne\n"
        
        # Commentaires
        comments = video.get('comments', [])
        if comments:
            prompt += f"\n{template['header']} ({len(comments)})\n"
            prompt += "-" * 40 + "\n"
            for i, c in enumerate(comments, 1):
                text = c.get('text', '').replace('\n', ' ')[:200]
                likes = c.get('like_count', 0)
                prompt += f"[{i}] ({likes}👍) {text}\n\n"
        else:
            prompt += "\n⚠️ Commentaires non disponibles\n"
        
        prompt += "\n"
    
    return prompt


# ==========================================
# 🎨 INTERFACE STREAMLIT
# ==========================================

def render_sidebar() -> dict:
    """Affiche et récupère les paramètres de la sidebar"""
    st.sidebar.title("🔍 YouTube Research V5")
    
    # Mots-clés
    st.sidebar.header("📝 Mots-clés")
    keywords_text = st.sidebar.text_area(
        "Un par ligne",
        height=100,
        placeholder="trump\nelon musk\nmacron"
    )
    keywords = [k.strip() for k in keywords_text.split('\n') if k.strip()]
    
    st.sidebar.divider()
    
    # Filtres
    st.sidebar.header("🎯 Filtres")
    
    language = st.sidebar.selectbox(
        "🌍 Langue",
        ["Auto (all languages)", "French", "English", "Spanish", "German"]
    )
    
    min_views = st.sidebar.number_input(
        "👁️ Vues minimum",
        value=50000,  # Réduit à 50k par défaut pour avoir plus de résultats
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
    
    # Conversion période -> date limite
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
    
    # Options avancées
    st.sidebar.header("⚙️ Options")
    
    videos_per_keyword = st.sidebar.slider(
        "Vidéos recherchées par mot-clé",
        min_value=5,
        max_value=30,
        value=15
    )
    
    enable_flame = st.sidebar.checkbox(
        "🔥 Analyser surperformance",
        value=False,  # Désactivé par défaut car ralentit
        help="Compare avec les 20 dernières vidéos de la chaîne (plus lent)"
    )
    
    max_workers = st.sidebar.slider(
        "Threads parallèles",
        min_value=3,
        max_value=20,
        value=10,
        help="Plus = plus rapide mais risque de blocage YouTube"
    )
    
    return {
        'keywords': keywords,
        'language': language,
        'min_views': int(min_views),
        'min_duration': min_duration,
        'date_limit': date_limit,
        'videos_per_keyword': videos_per_keyword,
        'enable_flame': enable_flame,
        'max_workers': max_workers,
    }


def render_video_card(video: Dict, idx: int):
    """Affiche une carte de vidéo avec commentaires"""
    ratio = video.get('_ratio', 0)
    stars = video.get('_stars', '⭐')
    has_flame = video.get('_has_flame', False)
    views = video.get('view_count', 0)
    title = video.get('title', 'Sans titre')
    
    flame_str = " 🔥" if has_flame else ""
    header = f"#{idx} {stars}{flame_str} | {ratio:.1f}x | {views:,} vues"
    
    with st.expander(header, expanded=(idx <= 2)):
        # Info principale
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
            st.write(f"📊 Ratio: **{ratio:.2f}x** {stars}")
            
            if has_flame:
                avg = video.get('_channel_avg', 0)
                st.success(f"🔥 Surperforme! (moyenne: {avg:,.0f})")
            
            url = video.get('webpage_url', '')
            if url:
                st.link_button("▶️ Voir sur YouTube", url)
        
        # Commentaires
        comments = video.get('comments', [])
        if comments:
            st.divider()
            st.subheader(f"💬 Top {len(comments)} Commentaires")
            
            for i, c in enumerate(comments, 1):
                text = c.get('text', '')
                likes = c.get('like_count', 0)
                author = c.get('author', 'Anonyme')
                
                with st.container():
                    st.markdown(f"**#{i}** - _{author}_ ({likes} 👍)")
                    st.text(text[:500] + ('...' if len(text) > 500 else ''))
                    st.markdown("---")


def main():
    st.title("🚀 YouTube Research Tool PRO V5")
    st.caption("Trouve les vidéos virales et analyse leurs commentaires")
    
    # Sidebar
    params = render_sidebar()
    
    # Zone de logs (si debug activé)
    if DEBUG_MODE:
        log_container = st.expander("🔧 Logs de debug", expanded=False)
    
    # Bouton principal
    if st.sidebar.button("🚀 LANCER L'ANALYSE", type="primary", use_container_width=True):
        
        if not params['keywords']:
            st.error("❌ Entre au moins un mot-clé!")
            return
        
        # Progress
        progress = st.progress(0)
        status = st.status("Initialisation...", expanded=True)
        
        processor = YouTubeProcessor(params['language'])
        all_raw_videos = []
        
        # ===== ÉTAPE 1: RECHERCHE =====
        status.update(label="🔍 Recherche des vidéos...", state="running")
        
        for i, kw in enumerate(params['keywords']):
            status.write(f"Recherche: '{kw}'...")
            entries = processor.search_videos(kw, params['videos_per_keyword'])
            
            for entry in entries:
                entry['_source_keyword'] = kw
                all_raw_videos.append(entry)
            
            progress.progress((i + 1) / len(params['keywords']) * 0.25)
        
        status.write(f"✅ {len(all_raw_videos)} vidéos trouvées au total")
        
        if not all_raw_videos:
            status.update(label="❌ Aucune vidéo trouvée", state="error")
            st.error("Aucune vidéo trouvée. Vérifie tes mots-clés.")
            return
        
        # ===== ÉTAPE 2: ANALYSE PARALLÈLE =====
        status.update(label=f"⏳ Analyse de {len(all_raw_videos)} vidéos...", state="running")
        
        processed_videos = []
        total = len(all_raw_videos)
        completed = 0
        skipped = 0
        
        with ThreadPoolExecutor(max_workers=params['max_workers']) as executor:
            futures = {
                executor.submit(
                    processor.process_video,
                    entry,
                    params['min_views'],
                    params['min_duration'],
                    params['date_limit'],
                    params['enable_flame']
                ): entry for entry in all_raw_videos
            }
            
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result:
                        processed_videos.append(result)
                    else:
                        skipped += 1
                except Exception as ex:
                    skipped += 1
                    debug_log(f"Future error: {ex}")
                
                completed += 1
                pct = 0.25 + (completed / total) * 0.65
                progress.progress(min(pct, 0.9))
                
                if completed % 10 == 0:
                    status.write(f"Analysé: {completed}/{total} ({len(processed_videos)} validées)")
        
        status.write(f"✅ Analyse terminée: {len(processed_videos)} vidéos validées, {skipped} filtrées")
        
        # ===== ÉTAPE 3: TRI =====
        status.update(label="📊 Tri par performance...", state="running")
        
        if processed_videos:
            processed_videos = sort_videos_by_performance(processed_videos)
        
        progress.progress(1.0)
        
        # ===== RÉSULTATS =====
        if not processed_videos:
            status.update(label="❌ Aucune vidéo ne correspond", state="error")
            st.error("""
            ❌ Aucune vidéo ne correspond à tes critères.
            
            **Essaie:**
            - Réduire le nombre de vues minimum (ex: 10000)
            - Mettre la langue sur "Auto"
            - Élargir la période
            - Utiliser des mots-clés plus populaires
            """)
            return
        
        status.update(label=f"✅ {len(processed_videos)} vidéos trouvées!", state="complete")
        
        # Stats
        flame_count = sum(1 for v in processed_videos if v.get('_has_flame'))
        col_stat1, col_stat2, col_stat3 = st.columns(3)
        col_stat1.metric("📹 Vidéos", len(processed_videos))
        col_stat2.metric("🔥 Surperformantes", flame_count)
        col_stat3.metric("⭐ Moyenne ratio", f"{sum(v.get('_ratio', 0) for v in processed_videos) / len(processed_videos):.2f}x")
        
        # Layout résultats
        col_prompt, col_videos = st.columns([1, 2])
        
        with col_prompt:
            st.subheader("📋 Prompt pour Claude")
            prompt = build_prompt(processed_videos, params['keywords'], params['language'])
            st.text_area("Copie ce prompt:", value=prompt, height=600)
            st.download_button(
                "📥 Télécharger",
                data=prompt,
                file_name="youtube_research.txt",
                mime="text/plain",
                use_container_width=True
            )
        
        with col_videos:
            st.subheader("📹 Résultats")
            
            tab_all, tab_flame = st.tabs(["📊 Toutes", "🔥 Surperformantes"])
            
            with tab_all:
                for idx, video in enumerate(processed_videos[:20], 1):
                    render_video_card(video, idx)
            
            with tab_flame:
                flame_videos = [v for v in processed_videos if v.get('_has_flame')]
                if flame_videos:
                    for idx, video in enumerate(flame_videos, 1):
                        render_video_card(video, idx)
                else:
                    st.info("Aucune vidéo surperformante. Active l'option 🔥 dans la sidebar.")


if __name__ == "__main__":
    main()
