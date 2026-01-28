"""
🚀 YouTube Keyword Research Tool PRO - V3
COMPLÈTEMENT RÉÉCRITURE - ULTRA SIMPLE & ULTRA RAPIDE
"""

import streamlit as st
from yt_dlp import YoutubeDL
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import random
import os
from typing import List, Dict, Optional, Tuple
import logging

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

st.set_page_config(page_title="YouTube Research Pro", layout="wide", initial_sidebar_state="expanded")

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Safari/537.36',
]

LANGUAGE_CONFIG = {
    "Auto (all languages)": {"code": None, "helpers": []},
    "French": {"code": "fr", "helpers": ["le", "la", "et"]},
    "English": {"code": "en", "helpers": ["the", "and", "is"]},
    "Spanish": {"code": "es", "helpers": ["el", "la", "y"]},
}

PROMPT_TEMPLATES = {
    "French": {
        "text": """Tu es un expert YouTube. Analyse ces commentaires pour trouver des opportunités:\n\nThème: {subjects}\n\n""",
        "header": "--- COMMENTAIRES TOP ---",
        "label": "Com"
    },
    "English": {
        "text": """Analyze these comments to find content opportunities:\n\nTopic: {subjects}\n\n""",
        "header": "--- TOP COMMENTS ---",
        "label": "Comment"
    },
    "Spanish": {
        "text": """Analiza estos comentarios para encontrar oportunidades:\n\nTema: {subjects}\n\n""",
        "header": "--- TOP COMENTARIOS ---",
        "label": "Comentario"
    }
}
PROMPT_TEMPLATES["Auto (all languages)"] = PROMPT_TEMPLATES["English"]

# ==========================================
# 🛠️ CLASSES SIMPLES
# ==========================================

class YTConfig:
    """Config ultra simple"""
    
    @staticmethod
    def get_opts(is_detailed=False):
        """Options yt-dlp - ULTRA MINIMAL"""
        opts = {
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'socket_timeout': 3,
            'http_headers': {'User-Agent': random.choice(USER_AGENTS)},
        }
        
        if is_detailed:
            opts.update({
                'getcomments': True,
                'max_comments': 5,
                'skip_download': True,
            })
        else:
            opts['extract_flat'] = True
        
        return opts


class SimpleValidator:
    """Validateur ultra simple"""
    
    @staticmethod
    def validate_lang(text: str, lang: str) -> bool:
        """Accepte quasi tout sauf si langue spécifique est très clairement pas ça"""
        if lang == "Auto (all languages)":
            return True
        if not text or len(text) < 3:
            return True
        return True  # Accepte presque tout pour trouver assez de résultats


class SimpleCommentFilter:
    """Filtre ultra simple"""
    
    @staticmethod
    def filter(comments: List[Dict], max_count: int = 5) -> List[Dict]:
        if not comments or not isinstance(comments, list):
            return []
        
        valid = [c for c in comments if isinstance(c, dict) and c.get('text', '')]
        valid.sort(key=lambda x: x.get('like_count', 0) or 0, reverse=True)
        
        return valid[:max_count]


class VideoProcessor:
    """Processeur ultra simple"""
    
    def __init__(self, language="Auto"):
        self.language = language
    
    def search_keyword(self, keyword: str) -> List[Dict]:
        """Recherche 30 vidéos"""
        if not keyword:
            return []
        
        try:
            opts = YTConfig.get_opts(is_detailed=False)
            with YoutubeDL(opts) as ydl:
                res = ydl.extract_info(f"ytsearch30:{keyword}", download=False)
                if res and 'entries' in res:
                    return [e for e in res['entries'] if e]
            return []
        except Exception as e:
            logger.error(f"Search error: {e}")
            return []
    
    def process_video(self, video_id: str, min_views: int, min_duration: str, date_limit) -> Optional[Dict]:
        """Traite 1 vidéo"""
        if not video_id:
            return None
        
        try:
            url = f"https://www.youtube.com/watch?v={video_id}"
            opts = YTConfig.get_opts(is_detailed=True)
            
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                if not info:
                    return None
                
                # Filtre par vues
                if info.get('view_count', 0) < min_views:
                    return None
                
                # Filtre par date
                if date_limit and info.get('upload_date'):
                    try:
                        upload = datetime.strptime(info['upload_date'], '%Y%m%d')
                        if upload < date_limit:
                            return None
                    except:
                        pass
                
                # Filtre par durée
                dur = info.get('duration', 0)
                if min_duration == "2 min" and dur < 120:
                    return None
                if min_duration == "5 min" and dur < 300:
                    return None
                
                # Filtre par langue
                text = f"{info.get('title', '')} {info.get('description', '')[:200]}"
                if not SimpleValidator.validate_lang(text, self.language):
                    return None
                
                # Commentaires
                if info.get('comments'):
                    info['comments'] = SimpleCommentFilter.filter(info['comments'], max_count=5)
                else:
                    info['comments'] = []
                
                return info
        
        except Exception as e:
            logger.error(f"Process error: {e}")
            return None
    
    def get_direct_video(self, url: str) -> Optional[Dict]:
        """Récupère URL directe"""
        if not url or not url.startswith('http'):
            return None
        
        try:
            opts = YTConfig.get_opts(is_detailed=False)
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return info
        except:
            return None


class VideoAnalyzer:
    """Analyste ultra simple"""
    
    @staticmethod
    def calculate_ratio(video: Dict) -> float:
        if not isinstance(video, dict):
            return 0.0
        subs = video.get('channel_follower_count') or 1
        views = video.get('view_count', 0)
        if subs <= 0:
            subs = 1
        return float(views) / float(subs)
    
    @staticmethod
    def sort_by_ratio(videos: List[Dict]) -> List[Dict]:
        for v in videos:
            v['_ratio'] = VideoAnalyzer.calculate_ratio(v)
        return sorted(videos, key=lambda x: x.get('_ratio', 0), reverse=True)
    
    @staticmethod
    def get_stars(ratio: float) -> str:
        if ratio > 2:
            return "⭐⭐⭐"
        elif ratio > 1:
            return "⭐⭐"
        return "⭐"


class PromptBuilder:
    """Builder ultra simple"""
    
    @staticmethod
    def build(videos: List[Dict], keywords: List[str], lang: str) -> str:
        if not videos:
            return "No videos."
        
        if lang not in PROMPT_TEMPLATES:
            lang = "English"
        
        pack = PROMPT_TEMPLATES[lang]
        subjects = ", ".join(keywords) if keywords else "Unknown"
        
        prompt = pack["text"].format(subjects=subjects)
        
        for video in videos:
            if not isinstance(video, dict):
                continue
            
            title = video.get('title', 'Unknown')
            url = video.get('webpage_url', '')
            views = video.get('view_count', 0)
            ratio = video.get('_ratio', 0)
            desc = video.get('description', '')[:100] if video.get('description') else "N/A"
            comments = video.get('comments', [])
            
            prompt += f"\n=== {title} ===\n"
            prompt += f"Link: {url}\n"
            prompt += f"Views: {views:,} | Ratio: {ratio:.2f}x\n"
            prompt += f"Desc: {desc}...\n"
            
            if comments:
                prompt += f"\n{pack['header']}\n"
                for i, c in enumerate(comments[:5], 1):
                    txt = c.get('text', '').replace('\n', ' ')[:80]
                    likes = c.get('like_count', 0)
                    prompt += f"[{pack['label']} {i}] ({likes}👍): {txt}\n"
            
            prompt += "\n"
        
        return prompt


# ==========================================
# 🎨 UI STREAMLIT
# ==========================================

def sidebar_params():
    st.sidebar.title("🔍 YouTube Research")
    
    st.sidebar.header("Search")
    kw_text = st.sidebar.text_area("Keywords (one per line)", height=80, placeholder="starlink\nai\nneuralink")
    keywords = [k.strip() for k in kw_text.split('\n') if k.strip()]
    
    st.sidebar.divider()
    
    st.sidebar.header("Filters")
    language = st.sidebar.selectbox("Language", list(LANGUAGE_CONFIG.keys()))
    min_views = st.sidebar.number_input("Min Views", value=100000, step=10000, min_value=0)
    min_duration = st.sidebar.selectbox("Min Duration", ["All", "2 min", "5 min"])
    date_period = st.sidebar.selectbox("Time Period", ["All time", "Last 30 days", "Last 6 months"])
    
    days_map = {"All time": None, "Last 30 days": 30, "Last 6 months": 180}
    date_limit = None
    if date_period in days_map and days_map[date_period]:
        date_limit = datetime.now() - timedelta(days=days_map[date_period])
    
    return keywords, language, int(min_views), min_duration, date_limit


def main():
    st.title("🚀 YouTube Research Tool PRO")
    st.write("Find viral videos from comment analysis")
    
    keywords, language, min_views, min_duration, date_limit = sidebar_params()
    
    if st.sidebar.button("🚀 START ANALYSIS", type="primary", use_container_width=True):
        if not keywords:
            st.error("❌ Enter at least one keyword!")
            return
        
        st_progress = st.progress(0)
        st_status = st.empty()
        
        st_status.info("⏳ Searching videos...")
        st_progress.progress(0.2)
        
        processor = VideoProcessor(language)
        videos_raw = []
        
        # Recherche (RAPIDE)
        for kw in keywords:
            entries = processor.search_keyword(kw)
            for e in entries:
                if e:
                    e['_source_keyword'] = kw
                    videos_raw.append(e)
        
        st_progress.progress(0.4)
        st_status.info(f"⏳ Analyzing {len(videos_raw)} videos...")
        
        # Analyse PARALLÈLE (RAPIDE)
        all_videos = []
        if videos_raw:
            with ThreadPoolExecutor(max_workers=20) as executor:
                futures = {
                    executor.submit(
                        processor.process_video,
                        e.get('id'),
                        min_views,
                        min_duration,
                        date_limit
                    ): e for e in videos_raw
                }
                
                done_count = 0
                for future in as_completed(futures):
                    try:
                        result = future.result()
                        if result and isinstance(result, dict):
                            all_videos.append(result)
                    except:
                        pass
                    
                    done_count += 1
                    pct = 0.4 + (done_count / len(videos_raw)) * 0.5
                    st_progress.progress(min(pct, 0.9))
        
        st_progress.progress(0.95)
        
        # Tri
        if all_videos:
            all_videos = VideoAnalyzer.sort_by_ratio(all_videos)
        
        st_progress.progress(1.0)
        st_status.empty()
        
        # Affichage
        if not all_videos:
            st.warning("❌ No videos found. Try lower min_views or different keywords.")
            return
        
        st.success(f"✅ {len(all_videos)} videos found!")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.subheader("📋 Prompt for Claude")
            prompt = PromptBuilder.build(all_videos, keywords, language)
            st.text_area("Copy this:", value=prompt, height=600)
        
        with col2:
            st.subheader("📹 Videos (Sorted by Ratio)")
            
            for idx, v in enumerate(all_videos[:15], 1):
                if not isinstance(v, dict):
                    continue
                
                ratio = v.get('_ratio', 0)
                stars = VideoAnalyzer.get_stars(ratio)
                views = v.get('view_count', 0)
                title = v.get('title', 'Unknown')
                
                with st.expander(f"#{idx} {stars} | {ratio:.1f}x | {views:,} views"):
                    col_img, col_info = st.columns([1, 2])
                    
                    with col_img:
                        thumb = v.get('thumbnail')
                        if thumb:
                            st.image(thumb, width=150)
                    
                    with col_info:
                        st.write(f"**{title}**")
                        st.write(f"Channel: {v.get('uploader', '?')}")
                        subs = v.get('channel_follower_count') or 0
                        st.write(f"Subs: {subs:,} | Views: {views:,}")
                        st.write(f"Ratio: **{ratio:.2f}x** 🚀")
                        url = v.get('webpage_url', '')
                        if url:
                            st.markdown(f"[▶️ Watch]({url})")


if __name__ == "__main__":
    main()
