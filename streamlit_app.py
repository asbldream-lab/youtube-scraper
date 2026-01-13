import streamlit as st
from yt_dlp import YoutubeDL
import json
from datetime import datetime, timedelta
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import re

# ==========================================
# ✅ CONFIGURATION & SESSION STATE
# ==========================================
st.set_page_config(page_title="YouTube Scraper Pro", layout="wide")
st.title("🚀 YouTube Keyword Research Tool PRO")

if 'search_history' not in st.session_state:
    st.session_state.search_history = []

# ==========================================
# ✅ NOUVEAU MOTEUR DE LANGUE (ANTI-ERREUR)
# ==========================================
def is_valid_language(info, target_lang):
    if target_lang == "Auto (toutes langues)": return True
    
    title = (info.get('title') or "").lower()
    desc = (info.get('description') or "").lower()
    full_text = title + " " + desc[:500]
    
    # Signaux spécifiques
    rules = {
        "Français": {"chars": "éàèçôû", "words": [" le ", " la ", " les ", " est "], "code": "fr"},
        "Espagnol": {"chars": "ñáéíóú¡¿", "words": [" el ", " los ", " con ", " para ", " por "], "code": "es"},
        "Anglais": {"chars": "", "words": [" the ", " and ", " with ", " from "], "code": "en"}
    }
    
    r = rules.get(target_lang)
    if not r: return True

    # 1. Vérification Meta YouTube
    yt_lang = (info.get('language') or "").lower()
    if yt_lang.startswith(r['code']): return True

    # 2. ANTI-ANGLAIS : Si on veut ES ou FR mais que le titre contient "How to", "Review" ou "The"
    if target_lang in ["Français", "Espagnol"]:
        if any(w in title for w in ["the ", "how to", "unboxing", "review", "bought"]):
            return False

    # 3. Vérification Caractères & Mots outils
    if r['chars'] and any(c in full_text for c in r['chars']): return True
    if any(w in full_text for w in r['words']): return True

    # 4. Vérification des sous-titres (Preuve finale)
    if r['code'] in (info.get('automatic_captions') or {}) or r['code'] in (info.get('subtitles') or {}):
        return True

    return False

# ============ SIDEBAR ============
st.sidebar.header("⚙️ Paramètres")

keywords_input = st.sidebar.text_area(
    "🔍 Mots-clés (un par ligne):",
    placeholder="guerre irak\nstarlink",
    help="Entre plusieurs mots-clés, un par ligne"
)
keywords_list = [k.strip() for k in keywords_input.split('\n') if k.strip()]

language = st.sidebar.selectbox(
    "🌍 Langue:",
    ["Auto (toutes langues)", "Français", "Anglais", "Espagnol"]
)

# VUES (Structure Originale Restaurée)
st.sidebar.write("### 👁️ Vues minimum")
col1, col2, col3, col4 = st.sidebar.columns(4)
selected_views = []
with col1:
    if st.sidebar.checkbox("10K-50K"): selected_views.append((10000, 50000))
with col2:
    if st.sidebar.checkbox("50K-100K"): selected_views.append((50000, 100000))
with col3:
    if st.sidebar.checkbox("100K+"): selected_views.append((100000, 1000000))
with col4:
    if st.sidebar.checkbox("1M+"): selected_views.append((1000000, float('inf')))

# DURÉE (Nouveau Filtre demandé)
st.sidebar.write("### ⏱️ Durée de la vidéo")
min_duration = st.sidebar.radio("Minimum :", ["Toutes", "Minimum 2 min", "Minimum 5 min"])

# ENGAGEMENT & DATE
st.sidebar.write("### 📈 Ratio & Période")
use_engagement = st.sidebar.checkbox("Filtrer par engagement")
min_engagement = st.sidebar.slider("Like/Vue min (%)", 0.0, 10.0, 1.0) if use_engagement else 0.0

date_filter = st.sidebar.selectbox(
    "Période:",
    ["Toutes", "7 derniers jours", "30 derniers jours", "6 derniers mois", "1 an"]
)

# ============ BOUTON RECHERCHE ============
if st.sidebar.button("🚀 Lancer l'analyse", use_container_width=True):
    if not keywords_list or not selected_views:
        st.error("❌ Mots-clés et gammes de vues requis !")
    else:
        progress_bar = st.progress(0)
        status = st.empty()
        
        # Calcul Date
        date_limit = None
        if date_filter != "Toutes":
            days = {"7 derniers jours": 7, "30 derniers jours": 30, "6 derniers mois": 180, "1 an": 365}
            date_limit = datetime.now() - timedelta(days=days[date_filter])

        all_videos_filtered = []
        all_comments_list = []

        try:
            for kw_idx, kw in enumerate(keywords_list):
                status.text(f"🔍 Recherche YouTube : {kw}")
                
                # Recherche initiale
                with YoutubeDL({'quiet': True, 'extract_flat': True}) as ydl:
                    search_res = ydl.extract_info(f"ytsearch40:{kw}", download=False).get('entries', [])

                # Extraction complète en parallèle (Vitesse max)
                def fetch_full(vid):
                    opts = {
                        'quiet': True, 'getcomments': True, 'writesubtitles': True, 
                        'skip_download': True, 'ignoreerrors': True, 'socket_timeout': 10
                    }
                    with YoutubeDL(opts) as ydl_full:
                        return ydl_full.extract_info(f"https://www.youtube.com/watch?v={vid['id']}", download=False)

                with ThreadPoolExecutor(max_workers=10) as executor:
                    full_infos = list(executor.map(fetch_full, search_results if 'search_results' in locals() else search_res))

                for info in [f for f in full_infos if f]:
                    # 1. FILTRE LANGUE (CORRIGÉ)
                    if not is_valid_language(info, language): continue
                    
                    # 2. FILTRE DURÉE (CORRIGÉ)
                    v_dur = info.get('duration', 0)
                    if min_duration == "Minimum 2 min" and v_dur < 120: continue
                    if min_duration == "Minimum 5 min" and v_dur < 300: continue

                    # 3. FILTRE VUES
                    v_views = info.get('view_count', 0) or 0
                    if not any(mn <= v_views <= mx for mn, mx in selected_views): continue

                    # 4. FILTRE DATE
                    if date_limit:
                        v_date = datetime.strptime(info.get('upload_date', '19000101'), '%Y%m%d')
                        if v_date < date_limit: continue

                    info['search_keyword'] = kw
                    all_videos_filtered.append(info)

            # === AFFICHAGE RÉSULTATS (Layout Original) ===
            if all_videos_filtered:
                st.success(f"✅ {len(all_videos_filtered)} vidéos trouvées.")
                
                left_col, right_col = st.columns([1, 2])

                # GAUCHE : LE PROMPT COMPLET
                with left_col:
                    st.header("📋 Copie en bas")
                    prompt_expert = """Rôle : Tu es un expert en analyse de données sociales... [Mets ici ton texte de prompt original complet]"""
                    
                    data_blob = f"\nMots-clés : {', '.join(keywords_list)}\n"
                    for v in all_videos_filtered:
                        data_blob += f"\n--- VIDEO: {v['title']} ---\n"
                        for c in v.get('comments', [])[:15]:
                            data_blob += f"- {c.get('text')} ({c.get('like_count')} likes)\n"
                    
                    st.text_area("Copie pour ChatGPT :", value=prompt_expert + data_blob, height=500)

                # DROITE : LES VIDÉOS
                with right_col:
                    st.header("📹 Vidéos")
                    for idx, v in enumerate(all_videos_filtered, 1):
                        subs = v.get('channel_follower_count', 0) or 1
                        ratio = v.get('view_count', 0) / subs
                        stars = "⭐⭐⭐" if ratio > 1 else "⭐"
                        with st.expander(f"#{idx} | {stars} | {v.get('view_count'):,} vues | {v['title'][:60]}..."):
                            st.image(v.get('thumbnail'), width=250)
                            st.write(f"**Chaîne :** {v.get('uploader')}")
                            st.write(f"**Lien :** [Regarder]({v.get('webpage_url')})")

            # SAUVEGARDE HISTORIQUE
            st.session_state.search_history.append({
                'date': datetime.now().strftime('%d/%m %H:%M'),
                'kw': keywords_list,
                'found': len(all_videos_filtered)
            })
            
            progress_bar.progress(100)
            status.text("✅ Analyse terminée.")

        except Exception as e:
            st.error(f"Erreur : {e}")

# ============ HISTORIQUE (RESTAURÉ) ============
if st.session_state.search_history:
    with st.expander("📚 Historique des recherches"):
        for h in reversed(st.session_state.search_history[-5:]):
            st.write(f"📅 {h['date']} | 🔍 {h['kw']} | 📹 {h['found']} vidéos")
