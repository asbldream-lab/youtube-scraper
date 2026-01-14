import streamlit as st
from yt_dlp import YoutubeDL
import json
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import time

# ==========================================
# 📦 SILENT INSTALLATION
# ==========================================
try:
    from langdetect import detect, LangDetectException
except ImportError:
    import subprocess
    subprocess.check_call(['pip', 'install', 'langdetect'])
    from langdetect import detect, LangDetectException

# ==========================================
# ⚙️ CONFIGURATION & TEMPLATES
# ==========================================
st.set_page_config(page_title="YouTube Scraper Pro", layout="wide")
st.title("🚀 YouTube Keyword Research Tool PRO")

if 'search_history' not in st.session_state:
    st.session_state.search_history = []

# KEYS UPDATED TO ENGLISH FOR THE INTERFACE
LANGUAGE_RULES = {
    "Auto (all languages)": {"code": None, "helpers": []},
    "French": {"code": "fr", "helpers": ["le", "la", "et", "est", "pour", "avec"]},
    "English": {"code": "en", "helpers": ["the", "and", "is", "to", "with", "for"]},
    "Spanish": {"code": "es", "helpers": ["el", "la", "y", "en", "es", "por", "con"]},
}

# --- PROMPT TEMPLATES (Dictionary keys match the English Interface now) ---
PROMPT_TEMPLATES = {
    "French": {
        "text": """Tu es un expert en stratégie de contenu YouTube et Data Analyst. Voici une liste de commentaires extraits de vidéos populaires sur le sujet : {subjects}

TA MISSION : Analyse ces commentaires pour identifier les opportunités de marché inexploitées. Ignore les commentaires génériques (type "super vidéo", "first"). Concentre-toi sur le fond.

RÉPONDS EXACTEMENT AVEC CETTE STRUCTURE :

📊 PARTIE 1 : ANALYSE DU MARCHÉ
1. Les Idées Récurrentes : Quels sont les 3-5 sujets de discussion qui reviennent le plus souvent ?
2. Les Frustrations (Pain Points) : Qu'est-ce qui énerve les gens ? Quels sont leurs problèmes non résolus ?
3. Les Manques (Gaps) : Qu'est-ce que les gens réclament ? Quelles questions posent-ils sans obtenir de réponse ?

🚀 PARTIE 2 : 3 ANGLES DE VIDÉOS GAGNANTS
Propose 3 concepts de vidéos qui répondent spécifiquement aux frustrations et aux manques identifiés ci-dessus. Pour chaque angle, utilise ce format :

👉 Angle #X : [Titre accrocheur et Pute-à-clic Éthique]
- Le Besoin ciblé : (Quel problème identifié en Partie 1 cela résout-il ?)
- La Promesse : (Qu'est-ce que le spectateur va apprendre ?)
- Pourquoi ça va marcher : (Justification basée sur les commentaires)

Voici les commentaires à analyser :
""",
        "header": "--- TOP 20 COMMENTAIRES (LES PLUS LIKÉS) ---",
        "label": "Commentaire"
    },

    "English": {
        "text": """You are an expert in YouTube content strategy and Data Analyst. Here is a list of comments extracted from popular videos on the topic: {subjects}

YOUR MISSION: Analyze these comments to identify untapped market opportunities. Ignore generic comments (like "great video", "first"). Focus on the substance.

REPLY EXACTLY WITH THIS STRUCTURE:

📊 PART 1: MARKET ANALYSIS
1. Recurring Themes: What are the 3-5 discussion topics that come up most often?
2. Frustrations (Pain Points): What annoys people? What are their unresolved problems?
3. Gaps: What are people asking for? What questions are they asking without getting an answer?

🚀 PART 2: 3 WINNING VIDEO ANGLES
Propose 3 video concepts that specifically address the frustrations and gaps identified above. For each angle, use this format:

👉 Angle #X: [Catchy & Ethical Clickbait Title]
- The Targeted Need: (Which problem identified in Part 1 does this solve?)
- The Promise: (What will the viewer learn?)
- Why it will work: (Justification based on the comments)

Here are the comments to analyze:
""",
        "header": "--- TOP 20 COMMENTS (MOST LIKED) ---",
        "label": "Comment"
    },

    "Spanish": {
        "text": """Eres un experto en estrategia de contenido de YouTube y Analista de Datos. Aquí tienes una lista de comentarios extraídos de videos populares sobre el tema: {subjects}

TU MISIÓN: Analiza estos comentarios para identificar oportunidades de mercado sin explotar. Ignora los comentarios genéricos (tipo "buen video", "primero"). Céntrate en el fondo.

RESPONDE EXACTAMENTE CON ESTA ESTRUCTURA:

📊 PARTE 1: ANÁLISIS DE MERCADO
1. Ideas Recurrentes: ¿Cuáles son los 3-5 temas de discusión que más se repiten?
2. Frustraciones (Pain Points): ¿Qué molesta a la gente? ¿Cuáles son sus problemas no resueltos?
3. Carencias (Gaps): ¿Qué reclama la gente? ¿Qué preguntas hacen sin obtener respuesta?

🚀 PARTE 2: 3 ÁNGULOS DE VIDEOS GANADORES
Propón 3 conceptos de videos que respondan específicamente a las frustraciones y carencias identificadas anteriormente. Para cada ángulo, utiliza este formato:

👉 Ángulo #X: [Título llamativo y Clickbait Ético]
- La Necesidad: (¿Qué problema identificado en la Parte 1 resuelve esto?)
- La Promesa: (¿Qué aprenderá el espectador?)
- Por qué funcionará: (Justificación basada en los comentarios)

Aquí están los comentarios para analizar:
""",
        "header": "--- TOP 20 COMENTARIOS (MÁS GUSTADOS) ---",
        "label": "Comentario"
    }
}

# Fallback
PROMPT_TEMPLATES["Auto (all languages)"] = PROMPT_TEMPLATES["English"]


# ==========================================
# 🧠 INTELLIGENT ENGINE
# ==========================================
def validate_language(text, target_lang_name):
    if target_lang_name == "Auto (all languages)": return True
    if not text or len(text) < 5: return False
    target_code = LANGUAGE_RULES[target_lang_name]["code"]
    
    try:
        if detect(text) == target_code: return True
    except:
        pass

    text_lower = text.lower()
    helpers = LANGUAGE_RULES[target_lang_name]["helpers"]
    count = sum(1 for h in helpers if f" {h} " in text_lower)
    return count >= 2

# ============ SIDEBAR (ENGLISH) ============
st.sidebar.header("1. Search")
keywords_input = st.sidebar.text_area("Keywords (one per line)", height=100, placeholder="starlink\nias")
keywords_list = [k.strip() for k in keywords_input.split('\n') if k.strip()]

language = st.sidebar.selectbox("Target Language", list(LANGUAGE_RULES.keys()))

st.sidebar.header("2. Filters")
min_views = st.sidebar.number_input("Minimum Views", value=5000, step=1000)
min_duration = st.sidebar.selectbox("Minimum Duration", ["All", "2 min", "5 min"])

# Translation of date options for logic mapping
date_options_display = ["All time", "Last 7 days", "Last 30 days", "Last 6 months", "1 year"]
date_choice = st.sidebar.selectbox("Time Period", date_options_display)

# ============ CORE LOGIC ============
if st.sidebar.button("🚀 START ANALYSIS", type="primary", use_container_width=True):
    if not keywords_list:
        st.error("❌ You need at least one keyword!")
    else:
        status_text = st.empty()
        progress_bar = st.progress(0)
        all_videos_found = []
        
        date_limit = None
        if date_choice != "All time":
            # Mapping English options to days
            days_map = {
                "Last 7 days": 7, 
                "Last 30 days": 30, 
                "Last 6 months": 180, 
                "1 year": 365
            }
            date_limit = datetime.now() - timedelta(days=days_map[date_choice])

        total_keywords = len(keywords_list)

        for idx, kw in enumerate(keywords_list):
            status_text.markdown(f"### 🔍 Searching for: **{kw}**...")
            
            # --- 1. SEARCH ---
            helpers = LANGUAGE_RULES[language]["helpers"]
            if helpers:
                query_helpers = " | ".join([f'"{h}"' for h in helpers[:3]]) 
                search_query = f'{kw} ({query_helpers})'
            else:
                search_query = kw

            ydl_opts_search = {'quiet': True, 'extract_flat': True, 'ignoreerrors': True}

            entries = []
            with YoutubeDL(ydl_opts_search) as ydl:
                try:
                    res = ydl.extract_info(f"ytsearch40:{search_query}", download=False)
                    if res is None: 
                        progress_bar.progress((idx + 1) / total_keywords)
                        continue
                    
                    entries = res.get('entries', [])
                    if not entries: 
                        st.warning(f"⚠️ No videos found for '{kw}'.")
                        progress_bar.progress((idx + 1) / total_keywords)
                        continue
                except Exception: 
                    progress_bar.progress((idx + 1) / total_keywords)
                    continue

            # --- 2. DETAILED ANALYSIS ---
            total_entries = len(entries)
            status_text.text(f"⚡ Starting analysis of {total_entries} videos...")
            
            def process_video(entry):
                if not entry: return None

                # Quick Filters
                v_count = entry.get('view_count')
                if v_count is not None and v_count < min_views: return None

                title = entry.get('title', '')
                if not validate_language(title, language): pass 

                url = f"https://www.youtube.com/watch?v={entry['id']}"
                
                # --- CONFIGURATION ---
                opts_full = {
                    'quiet': True,
                    'getcomments': True,
                    'max_comments': 40,
                    'skip_download': True,
                    'ignoreerrors': True,
                    'socket_timeout': 10,
                    'writesubtitles': True,
                    'writeautomaticsub': True,
                    'subtitleslangs': ['all'],
                }
                
                try:
                    with YoutubeDL(opts_full) as ydl_full:
                        info = ydl_full.extract_info(url, download=False)
                        
                        if date_limit:
                            ud = info.get('upload_date')
                            if ud and datetime.strptime(ud, '%Y%m%d') < date_limit: return None

                        dur = info.get('duration', 0)
                        if min_duration == "2 min" and dur < 120: return None
                        if min_duration == "5 min" and dur < 300: return None

                        full_text = f"{info['title']} {info['description'][:500]}"
                        if not validate_language(full_text, language): return None
                            
                        return info
                except:
                    return None

            with ThreadPoolExecutor(max_workers=20) as executor:
                futures = [executor.submit(process_video, e) for e in entries]
                
                for i, f in enumerate(as_completed(futures)):
                    res = f.result()
                    if res:
                        res['keyword_source'] = kw
                        all_videos_found.append(res)
                    
                    # Smooth Bar
                    kw_progress = (i + 1) / total_entries
                    global_progress = (idx + kw_progress) / total_keywords
                    
                    progress_bar.progress(min(global_progress, 1.0))
                    status_text.text(f"⚡ Analyzing: {i+1}/{total_entries} videos processed for '{kw}'...")

            progress_bar.progress((idx + 1) / total_keywords)

        status_text.empty()
        
        # --- 3. RESULTS DISPLAY ---
        if all_videos_found:
            st.success(f"✅ {len(all_videos_found)} qualified videos found!")
            
            col1, col2 = st.columns([1, 2])
            
            with col1:
                st.subheader("📋 Copy for AI")
                
                # ============================================================
                # 🌍 PROMPT GENERATION
                # ============================================================
                subjects = ", ".join(keywords_list)
                
                # Get correct template based on English keys
                lang_pack = PROMPT_TEMPLATES.get(language, PROMPT_TEMPLATES["English"])
                
                # 1. Main text
                prompt = lang_pack["text"].format(subjects=subjects)
                
                for v in all_videos_found:
                    prompt += f"=== VIDEO: {v['title']} ===\n"
                    prompt += f"Link: {v['webpage_url']}\n"
                    prompt += f"Views: {v.get('view_count', 0):,}\n"
                    desc = v.get('description', '').replace('\n', ' ')[:200]
                    prompt += f"Desc: {desc}...\n"
                    
                    if v.get('automatic_captions') or v.get('subtitles'):
                        prompt += "[Transcription available on link]\n"

                    comms = v.get('comments', [])
                    if comms:
                        # 2. Translated Header
                        prompt += f"\n{lang_pack['header']}\n"
                        
                        # --- SMART SORTING (Top 20 Likes) ---
                        comms.sort(key=lambda x: x.get('like_count', 0) or 0, reverse=True)
                        top_comments = comms[:20] 

                        for i, c in enumerate(top_comments, 1): 
                            txt = c.get('text', '').replace('\n', ' ').strip()
                            likes = c.get('like_count', 0)
                            # 3. Translated Label
                            prompt += f"[{lang_pack['label']} {i}] ({likes} likes) : \"{txt}\"\n"
                            
                    prompt += "\n" + "="*30 + "\n\n"
                
                st.text_area(f"Generated Prompt ({language}) :", value=prompt, height=600)
            
            with col2:
                st.subheader("📹 Video Preview")
                for v in all_videos_found:
                    subs = v.get('channel_follower_count') or 1
                    views = v.get('view_count', 0)
                    ratio = views / subs
                    
                    if ratio > 2: stars = "⭐⭐⭐"
                    elif ratio > 1: stars = "⭐⭐"
                    else: stars = "⭐"
                    
                    with st.expander(f"{stars} | {views:,} views | {v['title']}"):
                        c_img, c_txt = st.columns([1, 2])
                        with c_img: st.image(v.get('thumbnail'), use_container_width=True)
                        with c_txt:
                            st.write(f"**Channel:** {v.get('uploader')}")
                            st.write(f"**Subscribers:** {subs:,}")
                            st.write(f"**Ratio:** {ratio:.2f}x")
                            st.write(f"[Watch on YouTube]({v['webpage_url']})")
        else:
            st.warning("No videos found matching your strict criteria.")
