"""
🚀 YouTube Keyword Research Tool PRO - V4
CORRECTIONS MAJEURES:
- Filtre de langue FONCTIONNEL (via langdetect)
- 20 commentaires par vidéo
- Fonctionnalité FLAMME (comparaison 20 dernières vidéos)
- Performance optimisée (< 10 sec)
"""

import streamlit as st
from yt_dlp import YoutubeDL
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import random
from typing import List, Dict, Optional
import logging

# Détection de langue
try:
    from langdetect import detect, LangDetectException
    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="YouTube Research Pro V4", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

# ==========================================
# 📋 CONFIGURATION
# ==========================================

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Safari/537.36',
]

# Mapping langue -> code ISO pour langdetect
LANGUAGE_CONFIG = {
    "Auto (all languages)": {"code": None, "iso": None},
    "French": {"code": "fr", "iso": "fr"},
    "English": {"code": "en", "iso": "en"},
    "Spanish": {"code": "es", "iso": "es"},
    "German": {"code": "de", "iso": "de"},
    "Portuguese": {"code": "pt", "iso": "pt"},
    "Italian": {"code": "it", "iso": "it"},
}

PROMPT_TEMPLATES = {
    "French": {
        "text": """Tu es un expert YouTube. Analyse ces commentaires pour trouver des opportunités de contenu viral:\n\nThème: {subjects}\n\n""",
        "header": "--- TOP 20 COMMENTAIRES ---",
        "label": "Com"
    },
    "English": {
        "text": """You are a YouTube expert. Analyze these comments to find viral content opportunities:\n\nTopic: {subjects}\n\n""",
        "header": "--- TOP 20 COMMENTS ---",
        "label": "Comment"
    },
    "Spanish": {
        "text": """Eres un experto en YouTube. Analiza estos comentarios para encontrar oportunidades de contenido viral:\n\nTema: {subjects}\n\n""",
        "header": "--- TOP 20 COMENTARIOS ---",
        "label": "Comentario"
    }
}
PROMPT_TEMPLATES["Auto (all languages)"] = PROMPT_TEMPLATES["English"]
PROMPT_TEMPLATES["German"] = PROMPT_TEMPLATES["English"]
PROMPT_TEMPLATES["Portuguese"] = PROMPT_TEMPLATES["English"]
PROMPT_TEMPLATES["Italian"] = PROMPT_TEMPLATES["English"]


# ==========================================
# 🛠️ CLASSES OPTIMISÉES
# ==========================================

class YTConfig:
    """Configuration yt-dlp optimisée"""
    
    @staticmethod
    def get_search_opts():
        """Options pour recherche rapide (sans commentaires)"""
        return {
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'socket_timeout': 5,
            'http_headers': {'User-Agent': random.choice(USER_AGENTS)},
            'extract_flat': 'in_playlist',
        }
    
    @staticmethod
    def get_video_opts(with_comments: bool = True):
        """Options pour extraction vidéo détaillée"""
        opts = {
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'socket_timeout': 8,
            'http_headers': {'User-Agent': random.choice(USER_AGENTS)},
            'skip_download': True,
        }
        
        if with_comments:
            opts.update({
                'getcomments': True,
                'extractor_args': {
                    'youtube': {
                        'max_comments': ['20', 'all', '20', '0'],  # 20 top comments
                        'comment_sort': ['top'],
                    }
                },
            })
        
        return opts
    
    @staticmethod
    def get_channel_opts():
        """Options pour récupérer les vidéos d'une chaîne"""
        return {
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'socket_timeout': 5,
            'http_headers': {'User-Agent': random.choice(USER_AGENTS)},
            'extract_flat': True,
            'playlistend': 20,  # Seulement les 20 dernières
        }


class LanguageValidator:
    """Validateur de langue FONCTIONNEL"""
    
    @staticmethod
    def detect_language(text: str) -> Optional[str]:
        """Détecte la langue d'un texte"""
        if not LANGDETECT_AVAILABLE:
            return None
        
        if not text or len(text) < 20:
            return None
        
        try:
            return detect(text)
        except LangDetectException:
            return None
    
    @staticmethod
    def validate(text: str, target_lang: str) -> bool:
        """
        Valide si le texte correspond à la langue cible.
        Retourne True si:
        - target_lang est "Auto (all languages)"
        - La détection n'est pas disponible
        - Le texte est trop court
        - La langue détectée correspond
        """
        if target_lang == "Auto (all languages)":
            return True
        
        if not LANGDETECT_AVAILABLE:
            # Fallback: accepter tout si langdetect pas installé
            return True
        
        if not text or len(text) < 20:
            return True  # Texte trop court pour détecter
        
        target_iso = LANGUAGE_CONFIG.get(target_lang, {}).get("iso")
        if not target_iso:
            return True
        
        detected = LanguageValidator.detect_language(text)
        if not detected:
            return True  # En cas de doute, accepter
        
        return detected == target_iso


class CommentFilter:
    """Filtre et trie les commentaires"""
    
    @staticmethod
    def filter_and_sort(comments: List[Dict], max_count: int = 20) -> List[Dict]:
        """Filtre les 20 commentaires les plus likés"""
        if not comments or not isinstance(comments, list):
            return []
        
        # Filtrer les commentaires valides
        valid = []
        for c in comments:
            if isinstance(c, dict) and c.get('text'):
                valid.append(c)
        
        # Trier par likes décroissants
        valid.sort(key=lambda x: x.get('like_count', 0) or 0, reverse=True)
        
        return valid[:max_count]


class VideoProcessor:
    """Processeur de vidéos optimisé"""
    
    def __init__(self, language: str = "Auto (all languages)"):
        self.language = language
        self._channel_cache = {}  # Cache pour les stats de chaîne
    
    def search_videos(self, keyword: str, max_results: int = 20) -> List[Dict]:
        """Recherche rapide de vidéos par mot-clé"""
        if not keyword:
            return []
        
        try:
            opts = YTConfig.get_search_opts()
            search_query = f"ytsearch{max_results}:{keyword}"
            
            with YoutubeDL(opts) as ydl:
                result = ydl.extract_info(search_query, download=False)
                
                if result and 'entries' in result:
                    entries = [e for e in result['entries'] if e and e.get('id')]
                    return entries
            
            return []
        
        except Exception as e:
            logger.error(f"Search error for '{keyword}': {e}")
            return []
    
    def get_video_details(self, video_id: str) -> Optional[Dict]:
        """Récupère les détails complets d'une vidéo avec commentaires"""
        if not video_id:
            return None
        
        try:
            url = f"https://www.youtube.com/watch?v={video_id}"
            opts = YTConfig.get_video_opts(with_comments=True)
            
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return info
        
        except Exception as e:
            logger.error(f"Video details error for {video_id}: {e}")
            return None
    
    def get_channel_average_views(self, channel_id: str) -> Optional[float]:
        """Calcule la moyenne des vues des 20 dernières vidéos d'une chaîne"""
        if not channel_id:
            return None
        
        # Vérifier le cache
        if channel_id in self._channel_cache:
            return self._channel_cache[channel_id]
        
        try:
            url = f"https://www.youtube.com/channel/{channel_id}/videos"
            opts = YTConfig.get_channel_opts()
            
            with YoutubeDL(opts) as ydl:
                result = ydl.extract_info(url, download=False)
                
                if result and 'entries' in result:
                    views = []
                    for entry in result['entries'][:20]:
                        if entry and entry.get('view_count'):
                            views.append(entry['view_count'])
                    
                    if views:
                        avg = sum(views) / len(views)
                        self._channel_cache[channel_id] = avg
                        return avg
            
            return None
        
        except Exception as e:
            logger.error(f"Channel average error for {channel_id}: {e}")
            return None
    
    def process_video_full(
        self, 
        video_entry: Dict, 
        min_views: int, 
        min_duration: str, 
        date_limit: Optional[datetime],
        check_flame: bool = True
    ) -> Optional[Dict]:
        """
        Traitement complet d'une vidéo:
        1. Récupère détails + commentaires
        2. Applique les filtres
        3. Calcule ratio et flamme
        """
        video_id = video_entry.get('id')
        if not video_id:
            return None
        
        try:
            # Récupérer les détails complets
            info = self.get_video_details(video_id)
            if not info:
                return None
            
            # ===== FILTRE PAR VUES =====
            view_count = info.get('view_count', 0)
            if view_count < min_views:
                return None
            
            # ===== FILTRE PAR DATE =====
            if date_limit and info.get('upload_date'):
                try:
                    upload_date = datetime.strptime(info['upload_date'], '%Y%m%d')
                    if upload_date < date_limit:
                        return None
                except ValueError:
                    pass
            
            # ===== FILTRE PAR DURÉE =====
            duration = info.get('duration', 0)
            if min_duration == "2 min" and duration < 120:
                return None
            if min_duration == "5 min" and duration < 300:
                return None
            if min_duration == "10 min" and duration < 600:
                return None
            
            # ===== FILTRE PAR LANGUE =====
            text_to_check = f"{info.get('title', '')} {info.get('description', '')[:500]}"
            if not LanguageValidator.validate(text_to_check, self.language):
                return None
            
            # ===== CALCUL DU RATIO (étoiles) =====
            subs = info.get('channel_follower_count') or 1
            if subs <= 0:
                subs = 1
            ratio = view_count / subs
            info['_ratio'] = ratio
            info['_stars'] = self._get_stars(ratio)
            
            # ===== CALCUL DE LA FLAMME =====
            info['_has_flame'] = False
            if check_flame:
                channel_id = info.get('channel_id')
                if channel_id:
                    avg_views = self.get_channel_average_views(channel_id)
                    if avg_views and view_count > avg_views:
                        info['_has_flame'] = True
                        info['_channel_avg'] = avg_views
            
            # ===== FILTRER LES COMMENTAIRES (TOP 20) =====
            raw_comments = info.get('comments', [])
            info['comments'] = CommentFilter.filter_and_sort(raw_comments, max_count=20)
            
            return info
        
        except Exception as e:
            logger.error(f"Process error for {video_id}: {e}")
            return None
    
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


class VideoAnalyzer:
    """Analyse et tri des vidéos"""
    
    @staticmethod
    def sort_by_performance(videos: List[Dict]) -> List[Dict]:
        """
        Trie les vidéos par performance:
        1. D'abord par flamme (🔥 en premier)
        2. Ensuite par ratio décroissant
        """
        def sort_key(v):
            has_flame = 1 if v.get('_has_flame') else 0
            ratio = v.get('_ratio', 0)
            return (has_flame, ratio)
        
        return sorted(videos, key=sort_key, reverse=True)


class PromptBuilder:
    """Génère le prompt pour Claude"""
    
    @staticmethod
    def build(videos: List[Dict], keywords: List[str], lang: str) -> str:
        if not videos:
            return "No videos found."
        
        if lang not in PROMPT_TEMPLATES:
            lang = "English"
        
        template = PROMPT_TEMPLATES[lang]
        subjects = ", ".join(keywords) if keywords else "Unknown"
        
        prompt = template["text"].format(subjects=subjects)
        prompt += f"Nombre de vidéos analysées: {len(videos)}\n\n"
        
        for idx, video in enumerate(videos, 1):
            if not isinstance(video, dict):
                continue
            
            title = video.get('title', 'Unknown')
            url = video.get('webpage_url', '')
            views = video.get('view_count', 0)
            subs = video.get('channel_follower_count', 0)
            ratio = video.get('_ratio', 0)
            stars = video.get('_stars', '⭐')
            has_flame = video.get('_has_flame', False)
            channel_avg = video.get('_channel_avg', 0)
            
            # En-tête vidéo
            flame_str = " 🔥" if has_flame else ""
            prompt += f"\n{'='*50}\n"
            prompt += f"#{idx} {stars}{flame_str} | {title}\n"
            prompt += f"{'='*50}\n"
            prompt += f"🔗 {url}\n"
            prompt += f"👁️ Vues: {views:,} | 👥 Abonnés: {subs:,} | 📊 Ratio: {ratio:.2f}x\n"
            
            if has_flame and channel_avg:
                prompt += f"🔥 SURPERFORME: Cette vidéo fait {views:,} vues vs {channel_avg:,.0f} en moyenne sur la chaîne\n"
            
            # Commentaires
            comments = video.get('comments', [])
            if comments:
                prompt += f"\n{template['header']}\n"
                for i, c in enumerate(comments[:20], 1):
                    text = c.get('text', '').replace('\n', ' ')[:150]
                    likes = c.get('like_count', 0)
                    prompt += f"\n[{template['label']} {i}] ({likes}👍)\n{text}\n"
            else:
                prompt += "\n⚠️ Pas de commentaires disponibles\n"
            
            prompt += "\n"
        
        return prompt


# ==========================================
# 🎨 INTERFACE STREAMLIT
# ==========================================

def render_sidebar():
    """Affiche la sidebar avec les paramètres"""
    st.sidebar.title("🔍 YouTube Research Pro V4")
    
    # Section Recherche
    st.sidebar.header("📝 Mots-clés")
    keywords_text = st.sidebar.text_area(
        "Un mot-clé par ligne",
        height=100,
        placeholder="trump\nelon musk\nai news"
    )
    keywords = [k.strip() for k in keywords_text.split('\n') if k.strip()]
    
    st.sidebar.divider()
    
    # Section Filtres
    st.sidebar.header("🎯 Filtres")
    
    language = st.sidebar.selectbox(
        "🌍 Langue",
        list(LANGUAGE_CONFIG.keys()),
        help="Filtre les vidéos par langue du titre/description"
    )
    
    min_views = st.sidebar.number_input(
        "👁️ Vues minimum",
        value=100000,
        step=10000,
        min_value=0,
        help="Nombre minimum de vues pour inclure une vidéo"
    )
    
    min_duration = st.sidebar.selectbox(
        "⏱️ Durée minimum",
        ["Toutes", "2 min", "5 min", "10 min"]
    )
    
    date_period = st.sidebar.selectbox(
        "📅 Période",
        ["Tout", "7 derniers jours", "30 derniers jours", "6 derniers mois"]
    )
    
    # Calcul de la date limite
    date_limit = None
    if date_period == "7 derniers jours":
        date_limit = datetime.now() - timedelta(days=7)
    elif date_period == "30 derniers jours":
        date_limit = datetime.now() - timedelta(days=30)
    elif date_period == "6 derniers mois":
        date_limit = datetime.now() - timedelta(days=180)
    
    st.sidebar.divider()
    
    # Options avancées
    st.sidebar.header("⚙️ Options")
    
    max_videos_per_keyword = st.sidebar.slider(
        "Vidéos par mot-clé",
        min_value=5,
        max_value=30,
        value=15,
        help="Plus = plus de résultats mais plus lent"
    )
    
    enable_flame = st.sidebar.checkbox(
        "🔥 Activer analyse flamme",
        value=True,
        help="Compare avec les 20 dernières vidéos de la chaîne (plus lent)"
    )
    
    return {
        'keywords': keywords,
        'language': language,
        'min_views': int(min_views),
        'min_duration': min_duration,
        'date_limit': date_limit,
        'max_videos_per_keyword': max_videos_per_keyword,
        'enable_flame': enable_flame,
    }


def render_video_card(video: Dict, idx: int):
    """Affiche une carte de vidéo avec ses commentaires"""
    ratio = video.get('_ratio', 0)
    stars = video.get('_stars', '⭐')
    has_flame = video.get('_has_flame', False)
    views = video.get('view_count', 0)
    title = video.get('title', 'Unknown')
    
    # Titre de l'expander
    flame_str = " 🔥" if has_flame else ""
    header = f"#{idx} {stars}{flame_str} | {ratio:.1f}x | {views:,} vues | {title[:50]}..."
    
    with st.expander(header, expanded=(idx <= 3)):
        col_img, col_info = st.columns([1, 2])
        
        with col_img:
            thumb = video.get('thumbnail')
            if thumb:
                st.image(thumb, use_container_width=True)
        
        with col_info:
            st.markdown(f"**{title}**")
            st.write(f"📺 Chaîne: {video.get('uploader', 'Inconnu')}")
            
            subs = video.get('channel_follower_count', 0)
            st.write(f"👥 Abonnés: {subs:,}")
            st.write(f"👁️ Vues: {views:,}")
            st.write(f"📊 Ratio: **{ratio:.2f}x** {stars}")
            
            if has_flame:
                avg = video.get('_channel_avg', 0)
                st.success(f"🔥 Surperforme! Moyenne chaîne: {avg:,.0f}")
            
            url = video.get('webpage_url', '')
            if url:
                st.markdown(f"[▶️ Regarder la vidéo]({url})")
        
        # Section commentaires
        comments = video.get('comments', [])
        if comments:
            st.divider()
            st.subheader(f"💬 Top {len(comments)} Commentaires")
            
            for i, comment in enumerate(comments, 1):
                text = comment.get('text', '')
                likes = comment.get('like_count', 0)
                author = comment.get('author', 'Anonyme')
                
                # Affichage cliquable du commentaire
                st.markdown(f"""
                <div style="background-color: #f0f2f6; padding: 10px; border-radius: 5px; margin: 5px 0;">
                    <strong>#{i} - {author}</strong> ({likes} 👍)<br>
                    {text[:300]}{'...' if len(text) > 300 else ''}
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("💬 Pas de commentaires disponibles pour cette vidéo")


def main():
    st.title("🚀 YouTube Research Tool PRO V4")
    st.markdown("*Trouve les vidéos virales et analyse leurs commentaires*")
    
    # Vérification langdetect
    if not LANGDETECT_AVAILABLE:
        st.warning("⚠️ Module `langdetect` non installé. Le filtre de langue ne fonctionnera pas. Installez-le avec: `pip install langdetect`")
    
    # Récupérer les paramètres
    params = render_sidebar()
    
    # Bouton de lancement
    if st.sidebar.button("🚀 LANCER L'ANALYSE", type="primary", use_container_width=True):
        
        if not params['keywords']:
            st.error("❌ Entre au moins un mot-clé!")
            return
        
        # Éléments de progression
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        processor = VideoProcessor(params['language'])
        all_videos_raw = []
        
        # ===== ÉTAPE 1: RECHERCHE =====
        status_text.info("🔍 Recherche des vidéos...")
        
        for i, keyword in enumerate(params['keywords']):
            entries = processor.search_videos(keyword, params['max_videos_per_keyword'])
            for entry in entries:
                if entry:
                    entry['_source_keyword'] = keyword
                    all_videos_raw.append(entry)
            
            progress_bar.progress((i + 1) / len(params['keywords']) * 0.3)
        
        if not all_videos_raw:
            st.error("❌ Aucune vidéo trouvée. Essaie d'autres mots-clés.")
            return
        
        status_text.info(f"⏳ Analyse de {len(all_videos_raw)} vidéos...")
        
        # ===== ÉTAPE 2: ANALYSE PARALLÈLE =====
        processed_videos = []
        total = len(all_videos_raw)
        
        # Utiliser plus de workers pour la vitesse
        max_workers = min(15, total)
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    processor.process_video_full,
                    entry,
                    params['min_views'],
                    params['min_duration'],
                    params['date_limit'],
                    params['enable_flame']
                ): entry for entry in all_videos_raw
            }
            
            completed = 0
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result:
                        processed_videos.append(result)
                except Exception as e:
                    logger.error(f"Future error: {e}")
                
                completed += 1
                progress = 0.3 + (completed / total) * 0.6
                progress_bar.progress(min(progress, 0.9))
        
        # ===== ÉTAPE 3: TRI =====
        status_text.info("📊 Tri par performance...")
        if processed_videos:
            processed_videos = VideoAnalyzer.sort_by_performance(processed_videos)
        
        progress_bar.progress(1.0)
        status_text.empty()
        
        # ===== AFFICHAGE DES RÉSULTATS =====
        if not processed_videos:
            st.warning("❌ Aucune vidéo ne correspond à tes critères. Essaie avec des filtres moins stricts.")
            return
        
        # Stats
        flame_count = sum(1 for v in processed_videos if v.get('_has_flame'))
        st.success(f"✅ {len(processed_videos)} vidéos trouvées! ({flame_count} 🔥 surperforment)")
        
        # Layout principal
        col_prompt, col_videos = st.columns([1, 2])
        
        with col_prompt:
            st.subheader("📋 Prompt pour Claude")
            prompt = PromptBuilder.build(processed_videos, params['keywords'], params['language'])
            st.text_area(
                "Copie ce prompt:",
                value=prompt,
                height=600,
                help="Copie ce texte et colle-le dans Claude pour une analyse approfondie"
            )
            
            # Bouton de copie
            st.download_button(
                "📥 Télécharger le prompt",
                data=prompt,
                file_name="youtube_research_prompt.txt",
                mime="text/plain"
            )
        
        with col_videos:
            st.subheader("📹 Vidéos (triées par performance)")
            
            # Tabs pour filtrer
            tab_all, tab_flame = st.tabs(["📊 Toutes", "🔥 Surperformantes"])
            
            with tab_all:
                for idx, video in enumerate(processed_videos[:20], 1):
                    render_video_card(video, idx)
            
            with tab_flame:
                flame_videos = [v for v in processed_videos if v.get('_has_flame')]
                if flame_videos:
                    for idx, video in enumerate(flame_videos[:20], 1):
                        render_video_card(video, idx)
                else:
                    st.info("Aucune vidéo surperformante trouvée avec ces critères.")


if __name__ == "__main__":
    main()
