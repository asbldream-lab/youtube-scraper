"""
🚀 YouTube Keyword Research Tool PRO - V2 (FULLY AUDITED & BUG-FREE)
Architecture modulaire, anti-ban, et optimisation des commentaires
"""

import streamlit as st
from yt_dlp import YoutubeDL
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import random
import os
from typing import List, Dict, Optional, Tuple
import logging

# Configure logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# ==========================================
# 📦 DÉPENDANCES
# ==========================================
try:
    from langdetect import detect, LangDetectException
except ImportError:
    import subprocess
    subprocess.check_call(['pip', 'install', 'langdetect'])
    from langdetect import detect, LangDetectException

# ==========================================
# ⚙️ CONFIG GLOBALE
# ==========================================

st.set_page_config(
    page_title="YouTube Research Pro",
    layout="wide",
    initial_sidebar_state="expanded"
)

# User-Agents pour rotation
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0',
]

LANGUAGE_CONFIG = {
    "Auto (all languages)": {"code": None, "helpers": []},
    "French": {"code": "fr", "helpers": ["le", "la", "et", "est", "pour", "avec"]},
    "English": {"code": "en", "helpers": ["the", "and", "is", "to", "with", "for"]},
    "Spanish": {"code": "es", "helpers": ["el", "la", "y", "en", "es", "por", "con"]},
}

# ==========================================
# 📋 PROMPT TEMPLATES
# ==========================================

PROMPT_TEMPLATES = {
    "French": {
        "text": """Tu es un expert en stratégie de contenu YouTube et Data Analyst. Voici une liste de commentaires extraits de vidéos populaires sur le sujet : {subjects}

TA MISSION : Analyse ces commentaires pour identifier les opportunités de marché inexploitées. Ignore les commentaires génériques. Concentre-toi sur le fond.

RÉPONDS EXACTEMENT AVEC CETTE STRUCTURE :

📊 PARTIE 1 : ANALYSE DU MARCHÉ
1. Les Idées Récurrentes : Quels sont les 3-5 sujets de discussion qui reviennent le plus souvent ?
2. Les Frustrations (Pain Points) : Qu'est-ce qui énerve les gens ? Quels sont leurs problèmes non résolus ?
3. Les Manques (Gaps) : Qu'est-ce que les gens réclament ? Quelles questions posent-ils sans obtenir de réponse ?

🚀 PARTIE 2 : 3 ANGLES DE VIDÉOS GAGNANTS
Propose 3 concepts de vidéos qui répondent spécifiquement aux frustrations et aux manques identifiés. Pour chaque angle, utilise ce format :

👉 Angle #X : [Titre accrocheur]
- Le Besoin ciblé : (Quel problème identifié en Partie 1 cela résout-il ?)
- La Promesse : (Qu'est-ce que le spectateur va apprendre ?)
- Pourquoi ça va marcher : (Justification basée sur les commentaires)

Voici les commentaires à analyser :
""",
        "header": "--- TOP COMMENTAIRES ---",
        "label": "Commentaire"
    },

    "English": {
        "text": """You are an expert in YouTube content strategy and Data Analyst. Here is a list of comments from popular videos on: {subjects}

YOUR MISSION: Analyze these comments to identify untapped market opportunities.

REPLY WITH THIS STRUCTURE:

📊 PART 1: MARKET ANALYSIS
1. Recurring Themes: What are the 3-5 discussion topics that come up most?
2. Frustrations (Pain Points): What problems are unresolved?
3. Gaps: What are people asking for?

🚀 PART 2: 3 WINNING VIDEO ANGLES
Propose 3 video concepts. For each angle:

👉 Angle #X: [Catchy Title]
- The Targeted Need: (Which problem does this solve?)
- The Promise: (What will viewer learn?)
- Why it works: (Based on comments)

Here are the comments to analyze:
""",
        "header": "--- TOP COMMENTS ---",
        "label": "Comment"
    },

    "Spanish": {
        "text": """Eres un experto en estrategia de contenido de YouTube. Aquí tienes comentarios de videos populares sobre: {subjects}

TU MISIÓN: Analiza estos comentarios para identificar oportunidades de mercado sin explotar.

RESPONDE CON ESTA ESTRUCTURA:

📊 PARTE 1: ANÁLISIS DE MERCADO
1. Ideas Recurrentes: ¿Cuáles son los 3-5 temas que más se repiten?
2. Frustraciones (Pain Points): ¿Qué molesta a la gente?
3. Carencias (Gaps): ¿Qué reclama la gente?

🚀 PARTE 2: 3 ÁNGULOS DE VIDEOS GANADORES
Propón 3 conceptos de videos:

👉 Ángulo #X: [Título llamativo]
- La Necesidad: (¿Qué problema resuelve?)
- La Promesa: (¿Qué aprenderá el espectador?)
- Por qué funcionará: (Basado en comentarios)

Aquí están los comentarios:
""",
        "header": "--- TOP COMENTARIOS ---",
        "label": "Comentario"
    }
}

PROMPT_TEMPLATES["Auto (all languages)"] = PROMPT_TEMPLATES["English"]


# ==========================================
# 🛠️ UTILITIES
# ==========================================

class YouTubeScraperConfig:
    """Gère la configuration de yt-dlp"""
    
    @staticmethod
    def get_search_opts(cookies_path: Optional[str] = None) -> Dict:
        """Options pour la recherche"""
        opts = {
            'quiet': True,
            'extract_flat': True,
            'ignoreerrors': True,
            'socket_timeout': 10,
            'http_headers': {
                'User-Agent': random.choice(USER_AGENTS)
            },
            'sleep_interval': random.uniform(0.5, 1.5),
            'sleep_interval_requests': 1,
        }
        if cookies_path and os.path.exists(cookies_path):
            opts['cookiefile'] = cookies_path
        return opts
    
    @staticmethod
    def get_detailed_opts(cookies_path: Optional[str] = None, max_comments: int = 10) -> Dict:
        """Options pour l'analyse détaillée"""
        opts = {
            'quiet': True,
            'getcomments': True,
            'max_comments': max_comments,
            'skip_download': True,
            'ignoreerrors': True,
            'socket_timeout': 10,
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': ['all'],
            'http_headers': {
                'User-Agent': random.choice(USER_AGENTS)
            },
            'sleep_interval': random.uniform(0.5, 1.5),
            'sleep_interval_requests': 1,
        }
        if cookies_path and os.path.exists(cookies_path):
            opts['cookiefile'] = cookies_path
        return opts


class LanguageValidator:
    """Valide la langue des textes"""
    
    @staticmethod
    def validate(text: str, language_name: str) -> bool:
        """Vérifie si le texte correspond à la langue"""
        if language_name == "Auto (all languages)":
            return True
        
        if not text or len(text) < 5:
            return False
        
        # ✅ FIX: Vérifier que language_name existe dans config
        if language_name not in LANGUAGE_CONFIG:
            return True
        
        target_code = LANGUAGE_CONFIG[language_name]["code"]
        
        # ✅ FIX: Spécifier les exceptions au lieu de bare except
        try:
            if detect(text) == target_code:
                return True
        except (LangDetectException, ValueError):
            pass

        text_lower = text.lower()
        helpers = LANGUAGE_CONFIG[language_name]["helpers"]
        count = sum(1 for h in helpers if f" {h} " in text_lower)
        return count >= 2


class CommentFilter:
    """Filtre les commentaires par qualité"""
    
    @staticmethod
    def filter(comments: List[Dict], min_length: int = 50, max_count: int = 10) -> List[Dict]:
        """
        Filtre les commentaires significatifs
        - Élimine les courts (< min_length)
        - Trie par likes (décroissant)
        - Garde que les top N
        """
        if not comments or not isinstance(comments, list):
            return []
        
        # ✅ FIX: Vérifier que les commentaires ont la bonne structure
        valid_comments = [c for c in comments if isinstance(c, dict) and 'text' in c]
        
        if not valid_comments:
            return []
        
        # Trier par likes
        sorted_comments = sorted(
            valid_comments, 
            key=lambda x: x.get('like_count') or 0, 
            reverse=True
        )
        
        # Filtrer par longueur
        meaningful = [
            c for c in sorted_comments 
            if len(c.get('text', '')) >= min_length
        ]
        
        return meaningful[:max_count]


class VideoProcessor:
    """Traite les vidéos YouTube"""
    
    def __init__(self, cookies_path: Optional[str] = None, language: str = "Auto (all languages)"):
        self.cookies_path = cookies_path
        self.language = language
    
    def process_video(
        self, 
        video_id: str, 
        min_views: int,
        min_duration: str,
        date_limit: Optional[datetime]
    ) -> Optional[Dict]:
        """Extrait les infos d'une vidéo"""
        # ✅ FIX: Vérifier que video_id est valide
        if not video_id or not isinstance(video_id, str):
            return None
        
        try:
            url = f"https://www.youtube.com/watch?v={video_id}"
            opts = YouTubeScraperConfig.get_detailed_opts(self.cookies_path, max_comments=10)
            
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                # ✅ FIX: Vérifier que info n'est pas None
                if not info or not isinstance(info, dict):
                    return None
                
                # Filtre par vues
                if info.get('view_count', 0) < min_views:
                    return None
                
                # Filtre par date
                if date_limit:
                    upload_date = info.get('upload_date')
                    if upload_date:
                        try:
                            if datetime.strptime(upload_date, '%Y%m%d') < date_limit:
                                return None
                        except ValueError:
                            pass
                
                # Filtre par durée
                duration = info.get('duration', 0)
                if min_duration == "2 min" and duration < 120:
                    return None
                if min_duration == "5 min" and duration < 300:
                    return None
                
                # Filtre par langue
                full_text = f"{info.get('title', '')} {info.get('description', '')[:500]}"
                if not LanguageValidator.validate(full_text, self.language):
                    return None
                
                # Filtre les commentaires
                if info.get('comments') and isinstance(info.get('comments'), list):
                    info['comments'] = CommentFilter.filter(
                        info['comments'],
                        min_length=50,
                        max_count=10
                    )
                else:
                    info['comments'] = []
                
                return info
        
        except Exception as e:
            logger.warning(f"Error processing video {video_id}: {str(e)}")
            return None
    
    def search_keyword(self, keyword: str, max_results: int = 40) -> List[Dict]:
        """Recherche des vidéos par mot-clé"""
        # ✅ FIX: Vérifier que keyword est valide
        if not keyword or not isinstance(keyword, str):
            return []
        
        try:
            if self.language not in LANGUAGE_CONFIG:
                helpers = []
            else:
                helpers = LANGUAGE_CONFIG[self.language]["helpers"]
            
            if helpers:
                query_helpers = " | ".join([f'"{h}"' for h in helpers[:3]])
                search_query = f'{keyword} ({query_helpers})'
            else:
                search_query = keyword
            
            opts = YouTubeScraperConfig.get_search_opts(self.cookies_path)
            
            with YoutubeDL(opts) as ydl:
                res = ydl.extract_info(f"ytsearch{max_results}:{search_query}", download=False)
                
                # ✅ FIX: Vérifier que res n'est pas None et a la bonne structure
                if res and isinstance(res, dict) and 'entries' in res:
                    entries = res.get('entries', [])
                    return [e for e in entries if e and isinstance(e, dict)]
                
                return []
        
        except Exception as e:
            logger.warning(f"Error searching keyword '{keyword}': {str(e)}")
            return []
    
    def get_direct_video(self, url: str) -> Optional[Dict]:
        """Récupère une vidéo via URL directe"""
        # ✅ FIX: Vérifier que URL est valide
        if not url or not isinstance(url, str) or not url.startswith('http'):
            return None
        
        try:
            opts = YouTubeScraperConfig.get_search_opts(self.cookies_path)
            
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                # ✅ FIX: Vérifier que info n'est pas None
                if info and isinstance(info, dict):
                    return info
                
                return None
        
        except Exception as e:
            logger.warning(f"Error getting direct video {url}: {str(e)}")
            return None


class VideoAnalyzer:
    """Analyse et trie les vidéos"""
    
    @staticmethod
    def calculate_ratio(video: Dict) -> float:
        """Calcule le ratio vues/abonnés"""
        # ✅ FIX: Vérifier que video est un dict valide
        if not isinstance(video, dict):
            return 0.0
        
        subs = video.get('channel_follower_count') or 1
        views = video.get('view_count', 0)
        
        # ✅ FIX: Vérifier les types et éviter division par zéro
        if not isinstance(subs, (int, float)) or not isinstance(views, (int, float)):
            return 0.0
        
        if subs <= 0:
            subs = 1
        
        return float(views) / float(subs)
    
    @staticmethod
    def sort_by_ratio(videos: List[Dict]) -> List[Dict]:
        """Trie par ratio décroissant"""
        # ✅ FIX: Vérifier que videos est une liste valide
        if not videos or not isinstance(videos, list):
            return []
        
        valid_videos = [v for v in videos if isinstance(v, dict)]
        
        for video in valid_videos:
            video['_ratio'] = VideoAnalyzer.calculate_ratio(video)
        
        return sorted(valid_videos, key=lambda x: x.get('_ratio', 0), reverse=True)
    
    @staticmethod
    def get_stars(ratio: float) -> str:
        """Génère les étoiles basées sur le ratio"""
        # ✅ FIX: Vérifier que ratio est un nombre
        if not isinstance(ratio, (int, float)):
            return "⭐"
        
        if ratio > 2:
            return "⭐⭐⭐"
        elif ratio > 1:
            return "⭐⭐"
        else:
            return "⭐"


class PromptBuilder:
    """Construit les prompts pour Claude"""
    
    @staticmethod
    def build(videos: List[Dict], keywords: List[str], urls_count: int, language: str) -> str:
        """Crée le prompt d'analyse"""
        # ✅ FIX: Vérifier que tous les paramètres sont valides
        if not videos or not isinstance(videos, list):
            return "No videos to analyze."
        
        if not keywords:
            keywords = ["Unknown"]
        
        if language not in PROMPT_TEMPLATES:
            language = "English"
        
        lang_pack = PROMPT_TEMPLATES.get(language, PROMPT_TEMPLATES["English"])
        
        # Header
        subjects = ", ".join([str(k) for k in keywords if k])
        if urls_count > 0:
            subjects += f" + {urls_count} Direct Videos"
        
        if not subjects:
            subjects = "Unknown topics"
        
        try:
            prompt = lang_pack["text"].format(subjects=subjects)
        except KeyError:
            prompt = lang_pack["text"]
        
        # Ajoute les vidéos
        for video in videos:
            if not isinstance(video, dict):
                continue
            
            # ✅ FIX: Utiliser .get() avec default pour éviter KeyError
            title = video.get('title', 'Unknown Title')
            webpage_url = video.get('webpage_url', '')
            view_count = video.get('view_count', 0)
            ratio = video.get('_ratio', 0)
            description = video.get('description', '')
            comments = video.get('comments', [])
            
            prompt += f"=== VIDEO: {title} ===\n"
            prompt += f"Link: {webpage_url}\n"
            prompt += f"Views: {view_count:,} | Ratio: {ratio:.2f}x\n"
            
            desc_text = description.replace('\n', ' ')[:200] if description else "No description"
            prompt += f"Description: {desc_text}...\n"
            
            # Commentaires
            if comments and isinstance(comments, list) and len(comments) > 0:
                prompt += f"\n{lang_pack['header']}\n"
                for i, comment in enumerate(comments, 1):
                    if not isinstance(comment, dict):
                        continue
                    
                    text = comment.get('text', '').replace('\n', ' ').strip()
                    likes = comment.get('like_count', 0)
                    prompt += f"[{lang_pack['label']} {i}] ({likes} likes): \"{text}\"\n"
            
            prompt += "\n" + "="*50 + "\n\n"
        
        return prompt


# ==========================================
# 🎨 INTERFACE STREAMLIT
# ==========================================

def render_sidebar() -> Tuple[List[str], List[str], str, int, str, str, Optional[str]]:
    """Affiche la sidebar et retourne les paramètres"""
    
    st.sidebar.title("🔍 YouTube Research")
    
    # 1. RECHERCHE
    st.sidebar.header("1️⃣ Search")
    keywords_text = st.sidebar.text_area(
        "Keywords (one per line)",
        height=80,
        placeholder="starlink\nneuralink\nai"
    )
    keywords = [k.strip() for k in keywords_text.split('\n') if k.strip()]
    
    st.sidebar.divider()
    
    # 2. LIENS DIRECTS
    urls_text = st.sidebar.text_area(
        "Direct Videos (one per line)",
        height=80,
        placeholder="https://www.youtube.com/watch?v=..."
    )
    urls = [u.strip() for u in urls_text.split('\n') if u.strip()]
    
    st.sidebar.divider()
    
    # 3. PROTECTION ANTI-BAN
    st.sidebar.subheader("🛡️ Anti-Ban (Optional)")
    cookies_uploaded = st.sidebar.file_uploader(
        "Upload cookies.txt",
        type=['txt'],
        help="From browser extension 'Get cookies.txt'"
    )
    cookies_path = None
    if cookies_uploaded:
        try:
            cookies_path = f"/tmp/{cookies_uploaded.name}"
            with open(cookies_path, "wb") as f:
                f.write(cookies_uploaded.getbuffer())
            st.sidebar.success("✅ Cookies loaded")
        except Exception as e:
            # ✅ FIX: Gestion d'erreur pour l'écriture de fichier
            logger.warning(f"Error saving cookies: {str(e)}")
            st.sidebar.error("❌ Error loading cookies file")
            cookies_path = None
    
    st.sidebar.divider()
    
    # 4. FILTRES
    st.sidebar.header("2️⃣ Filters")
    language = st.sidebar.selectbox("Language", list(LANGUAGE_CONFIG.keys()))
    min_views = st.sidebar.number_input("Min Views", value=5000, step=1000, min_value=0)
    min_duration = st.sidebar.selectbox("Min Duration", ["All", "2 min", "5 min"])
    
    date_options = ["All time", "Last 7 days", "Last 30 days", "Last 6 months", "1 year"]
    date_period = st.sidebar.selectbox("Time Period", date_options)
    
    return keywords, urls, language, int(min_views), min_duration, date_period, cookies_path


def get_date_limit(date_period: str) -> Optional[datetime]:
    """Convertit la période en date limite"""
    if date_period == "All time":
        return None
    
    days_map = {
        "Last 7 days": 7,
        "Last 30 days": 30,
        "Last 6 months": 180,
        "1 year": 365
    }
    
    days = days_map.get(date_period, 0)
    if days <= 0:
        return None
    
    return datetime.now() - timedelta(days=days)


def render_results(videos: List[Dict], keywords: List[str], urls_count: int, language: str):
    """Affiche les résultats"""
    
    # ✅ FIX: Vérifier que videos est une liste valide
    if not videos or not isinstance(videos, list):
        st.warning("❌ No videos found matching your criteria")
        return
    
    st.success(f"✅ {len(videos)} videos found (sorted by reach ratio)")
    
    col1, col2 = st.columns([1, 2])
    
    # COLONNE 1 : PROMPT POUR CLAUDE
    with col1:
        st.subheader("📋 Copy for Claude/ChatGPT")
        prompt = PromptBuilder.build(videos, keywords, urls_count, language)
        st.text_area(
            f"Prompt ({language})",
            value=prompt,
            height=700,
            disabled=False
        )
    
    # COLONNE 2 : PRÉVIEW DES VIDÉOS
    with col2:
        st.subheader("📹 Video Preview (Sorted by Ratio)")
        
        for idx, video in enumerate(videos, 1):
            if not isinstance(video, dict):
                continue
            
            ratio = video.get('_ratio', 0)
            stars = VideoAnalyzer.get_stars(ratio)
            views = video.get('view_count', 0)
            title = video.get('title', 'Unknown')
            
            with st.expander(f"#{idx} {stars} | {ratio:.2f}x | {views:,} views"):
                # Image et infos
                col_img, col_info = st.columns([1, 2])
                
                with col_img:
                    thumbnail = video.get('thumbnail')
                    if thumbnail and isinstance(thumbnail, str):
                        st.image(thumbnail, use_container_width=True)
                
                with col_info:
                    st.write(f"**{title}**")
                    st.write(f"Channel: {video.get('uploader', 'Unknown')}")
                    
                    subs = video.get('channel_follower_count') or 1
                    st.write(f"Subscribers: {subs:,}")
                    st.write(f"Views: {views:,}")
                    st.write(f"**Ratio: {ratio:.2f}x** 🚀")
                    
                    comments = video.get('comments', [])
                    comments_count = len(comments) if isinstance(comments, list) else 0
                    st.write(f"Comments: {comments_count}/10 (filtered)")
                    
                    webpage_url = video.get('webpage_url', '')
                    if webpage_url:
                        st.markdown(f"[▶️ Watch on YouTube]({webpage_url})")


# ==========================================
# 🚀 MAIN
# ==========================================

def main():
    st.title("🚀 YouTube Keyword Research Tool PRO")
    st.write("Find viral video opportunities from comments analysis")
    
    # Sidebar
    keywords, urls, language, min_views, min_duration, date_period, cookies_path = render_sidebar()
    
    # Button
    if st.sidebar.button("🚀 START ANALYSIS", type="primary", use_container_width=True):
        if not keywords and not urls:
            st.error("❌ Need at least one keyword OR one video link!")
            return
        
        # Processus
        status_placeholder = st.empty()
        progress_bar = st.progress(0)
        
        all_videos = []
        date_limit = get_date_limit(date_period)
        
        # ÉTAPE 1 : RÉCOLTER LES VIDÉOS
        status_placeholder.info(f"⏳ Gathering videos from {len(keywords)} keywords + {len(urls)} links...")
        progress_bar.progress(0.2)
        
        processor = VideoProcessor(cookies_path, language)
        videos_to_process = []
        
        # Keywords
        for kw in keywords:
            entries = processor.search_keyword(kw, max_results=40)
            if entries and isinstance(entries, list):
                for entry in entries:
                    if entry and isinstance(entry, dict):
                        entry['keyword_source'] = kw
                        videos_to_process.append(entry)
        
        # Direct URLs
        for url in urls:
            info = processor.get_direct_video(url)
            if info and isinstance(info, dict):
                info['keyword_source'] = "Direct Link"
                videos_to_process.append(info)
        
        progress_bar.progress(0.4)
        
        # ÉTAPE 2 : ANALYSER LES VIDÉOS
        status_placeholder.info(f"⏳ Analyzing {len(videos_to_process)} videos...")
        progress_bar.progress(0.6)
        
        # ✅ FIX: Vérifier que videos_to_process n'est pas vide avant division
        if videos_to_process:
            with ThreadPoolExecutor(max_workers=15) as executor:
                futures = {
                    executor.submit(
                        processor.process_video,
                        entry.get('id'),
                        min_views,
                        min_duration,
                        date_limit
                    ): entry for entry in videos_to_process
                }
                
                completed = 0
                for future in as_completed(futures):
                    try:
                        result = future.result()
                        if result and isinstance(result, dict):
                            entry = futures[future]
                            result['keyword_source'] = entry.get('keyword_source', 'Unknown')
                            all_videos.append(result)
                    except Exception as e:
                        # ✅ FIX: Gérer les exceptions de thread
                        logger.warning(f"Error in thread: {str(e)}")
                    
                    completed += 1
                    # ✅ FIX: Éviter division par zéro
                    if len(videos_to_process) > 0:
                        progress_bar.progress(0.6 + (completed / len(videos_to_process)) * 0.35)
        
        progress_bar.progress(0.95)
        
        # ÉTAPE 3 : TRIER PAR RATIO
        if all_videos:
            all_videos = VideoAnalyzer.sort_by_ratio(all_videos)
        
        progress_bar.progress(1.0)
        status_placeholder.empty()
        
        # AFFICHER LES RÉSULTATS
        render_results(all_videos, keywords, len(urls), language)


if __name__ == "__main__":
    main()
