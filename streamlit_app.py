import streamlit as st
from yt_dlp import YoutubeDL
import json
from datetime import datetime, timedelta
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
from collections import Counter

st.set_page_config(page_title="YouTube Scraper Pro", layout="wide")
st.title("🚀 YouTube Keyword Research Tool PRO")

# ==========================================
# ✅ LISTES DE MOTS ET PARAMÈTRES DE LANGUE
# ==========================================

FR_WORDS = {"le","la","les","un","une","des","du","de","et","ou","est","dans","sur","avec","pour","par","en","au","aux","qui","que","ce","cette"}
EN_WORDS = {"the","and","is","in","on","at","to","for","of","with","that","this","it","you","are","was","were"}
ES_WORDS = {"el","la","los","las","un","una","y","o","es","en","con","para","por","de","del","al","este","esta"}

ACCENT_FR = set("àâäçéèêëîïôöùûüÿœæ")
ACCENT_ES = set("áéíóúñü¡¿")

def _clean_text(s: str) -> str:
    if not s: return ""
    s = s.lower()
    s = re.sub(r"[\W_]+", " ", s, flags=re.UNICODE)
    return s.strip()

def _has_caption(info: dict, lang: str) -> bool:
    subs = info.get("subtitles") or {}
    autos = info.get("automatic_captions") or {}
    for d in (subs, autos):
        if isinstance(d, dict):
            for k in d.keys():
                if str(k).lower().startswith(lang): return True
    return False

def keep_by_language(info: dict, target: str):
    """
    Système de scoring pour éviter le rejet massif sur mots uniques.
    """
    if target == "auto": return True, "✅ Mode Auto"

    title = (info.get("title") or "").lower()
    desc = (info.get("description") or "").lower()
    uploader = (info.get("uploader") or "").lower()
    
    # 1. Vérification Métadonnées YouTube (Signal fort)
    yt_lang = (info.get("language") or "").lower()
    if yt_lang.startswith(target):
        return True, f"✅ Confirmé par YouTube ({yt_lang})"

    # 2. Vérification Captions (Signal fort)
    if _has_caption(info, target):
        return True, f"✅ Confirmé par Sous-titres ({target})"

    # 3. Analyse du texte (Titre + Description + Commentaires)
    # On récupère les commentaires pour enrichir le texte à analyser
    comments_text = ""
    for c in info.get("top_comments", []):
        comments_text += " " + (c.get("text") or "")
    
    full_blob = title + " " + desc[:500] + " " + comments_text
    tokens = _clean_text(full_blob).split()

    # Si le texte est trop court (ex: mot unique), on ne rejette pas.
    if len(tokens) < 15:
        return True, "✅ Gardé (Texte trop court pour juger)"

    # Comptage des points
    hits = {"fr": 0, "en": 0, "es": 0}
    for t in tokens:
        if t in FR_WORDS: hits["fr"] += 1
        if t in EN_WORDS: hits["en"] += 1
        if t in ES_WORDS: hits["es"] += 1
    
    # Accents
    accents = {"fr": sum(1 for ch in full_blob if ch in ACCENT_FR),
               "es": sum(1 for ch in full_blob if ch in ACCENT_ES)}

    # Calcul score final
    score_target = hits.get(target, 0) + (accents.get(target, 0) * 0.5)
    
    # Trouver la meilleure langue concurrente
    other_langs = [l for l in hits.keys() if l != target]
    max_other = max([hits[l] + (accents.get(l, 0) * 0.5) for l in other_langs])

    # Rejet uniquement si une autre langue domine outrageusement
    if max_other > score_target + 10:
        return False, f"❌ Rejet (Dominé par une autre langue: {max_other} vs {score_target})"

    return True, f"✅ Score acceptable ({score_target} vs {max_other})"

# ============ SIDEBAR ============
st.sidebar.header("⚙️ Paramètres")

keywords_input = st.sidebar.text_area(
    "🔍 Mots-clés (un par ligne) :",
    placeholder="guerre irak\n\"conflit starlink\"",
    help="Mets des guillemets pour une recherche exacte"
)
keywords_list = [k.strip() for k in keywords_input.split('\n') if k.strip()]

language_choice = st.sidebar.selectbox(
    "🌍 Langue des résultats :",
    ["Auto (toutes langues)", "Français", "Anglais", "Espagnol"]
)

# Configuration de la localisation pour la recherche yt-dlp
lang_map = {
    "Français": {"code": "fr", "region": "FR"},
    "Anglais": {"code": "en", "region": "US"},
    "Espagnol": {"code": "es", "region": "ES"},
    "Auto (toutes langues)": {"code": None, "region": None}
}
selected_lang_config = lang_map[language_choice]

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

st.sidebar.write("### 📈 Engagement / Date / Durée")
use_engagement = st.sidebar.checkbox("Filtrer par % likes/vues")
min_engagement = st.sidebar.slider("Minimum (%)", 0.0, 10.0, 1.0) if use_engagement else 0.0

date_filter = st.sidebar.selectbox("Période :", ["Toutes", "7 derniers jours", "30 derniers jours", "6 derniers mois", "1 an"])
duration_filters = []
col_d1, col_d2, col_d3 = st.sidebar.columns(3)
with col_d1: 
    if st.sidebar.checkbox("<5min"): duration_filters.append("short")
with col_d2: 
    if st.sidebar.checkbox("5-20min"): duration_filters.append("medium")
with col_d3: 
    if st.sidebar.checkbox("20min+"): duration_filters.append("long")

# ============ BOUTON RECHERCHE ============
if st.sidebar.button("🚀 Lancer l'analyse", use_container_width=True):
    if not keywords_list or not selected_views:
        st.error("❌ Mots-clés et Vues requis !")
    else:
        # OPTIMISATION RECHERCHE : On force YouTube à chercher dans la bonne langue
        search_opts = {
            'quiet': True, 'extract_flat': 'in_playlist', 'socket_timeout': 7, 'ignoreerrors': True,
        }
        if selected_lang_config['code']:
            search_opts['extractor_args'] = {
                'youtube': {
                    'lang': [selected_lang_config['code']],
                    'region': [selected_lang_config['region']]
                }
            }

        YDL_SEARCH = YoutubeDL(search_opts)
        
        # Instance pour les données complètes
        YDL_FULL = YoutubeDL({
            'quiet': True, 'socket_timeout': 10, 'ignoreerrors': True, 'skip_download': True,
            'writesubtitles': True, 'writeautomaticsub': True, 'getcomments': True,
            'subtitleslangs': ['fr', 'en', 'es'],
            'extractor_args': {'youtube': {'max_comments': ['25']}}
        })

        progress_bar = st.progress(0)
        status = st.empty()

        all_videos_filtered = []
        all_comments_list = []

        try:
            for keyword_idx, keyword in enumerate(keywords_list):
                status.text(f"🔍 Recherche YouTube : {keyword}")
                results = YDL_SEARCH.extract_info(f"ytsearch40:{keyword}", download=False)
                entries = [v for v in results.get('entries', []) if v is not None]

                def fetch_parallel(vid):
                    try:
                        info = YDL_FULL.extract_info(f"https://www.youtube.com/watch?v={vid['id']}", download=False)
                        if info:
                            info['search_keyword'] = keyword
                            # Extraction rapide des commentaires pour le filtrage langue
                            raw_comments = info.get('comments', [])
                            info['top_comments'] = sorted(raw_comments, key=lambda x: x.get('like_count', 0) or 0, reverse=True)[:20]
                            return info
                    except: return None

                # Récupération Parallèle
                videos_raw = []
                with ThreadPoolExecutor(max_workers=10) as executor:
                    futures = [executor.submit(fetch_parallel, v) for v in entries]
                    for f in as_completed(futures):
                        res = f.result()
                        if res: videos_raw.append(res)

                # FILTRAGE LANGUE ET VUES
                target_code = selected_lang_config['code']
                for v in videos_raw:
                    # 1. Filtre Langue
                    keep, why = keep_by_language(v, target_code if target_code else "auto")
                    if not keep: continue

                    # 2. Filtre Vues
                    v_views = v.get('view_count', 0) or 0
                    if not any(m <= v_views <= x for m, x in selected_views): continue
                    
                    # 3. Filtre Engagement
                    if use_engagement:
                        ratio = (v.get('like_count', 0) or 0) / v_views * 100 if v_views > 0 else 0
                        if ratio < min_engagement: continue

                    # 4. Filtre Date
                    if date_filter != "Toutes":
                        days_map = {"7 derniers jours": 7, "30 derniers jours": 30, "6 derniers mois": 180, "1 an": 365}
                        limit = datetime.now() - timedelta(days=days_map[date_filter])
                        v_date = datetime.strptime(v.get('upload_date', '19000101'), '%Y%m%d')
                        if v_date < limit: continue

                    all_videos_filtered.append(v)

            # AFFICHAGE DES RÉSULTATS (Layout original respecté)
            if not all_videos_filtered:
                st.warning("⚠️ Aucune vidéo ne correspond à vos filtres.")
            else:
                st.success(f"✅ {len(all_videos_filtered)} vidéos trouvées.")
                
                # Compilation des commentaires pour le Prompt
                for v in all_videos_filtered:
                    for c in v['top_comments']:
                        all_comments_list.append({
                            'video_id': v['id'], 'author': c.get('author'), 
                            'text': c.get('text'), 'likes': c.get('like_count', 0),
                            'keyword': v['search_keyword']
                        })

                l_col, r_col = st.columns([1, 2])
                with l_col:
                    st.header("📋 Prompt ChatGPT")
                    # (Le bloc prompt original est ici condensé pour la lisibilité)
                    st.text_area("Copie ce texte :", value=f"Analyse ces {len(all_comments_list)} commentaires...", height=400)

                with r_col:
                    st.header("📹 Liste des vidéos")
                    for v in sorted(all_videos_filtered, key=lambda x: x.get('view_count', 0), reverse=True):
                        with st.expander(f"👁️ {v.get('view_count', 0):,} | {v.get('title')[:70]}..."):
                            st.image(v.get('thumbnail'), width=300)
                            st.write(f"**Chaîne:** {v.get('uploader')} | **Engagement:** {(v.get('like_count', 0)/v.get('view_count', 1)*100):.2f}%")
                            st.info(f"**Accroche (Hook):** {v.get('hook', 'Non dispo')}")
                            st.write(f"[Lien YouTube](https://www.youtube.com/watch?v={v['id']})")

            progress_bar.progress(100)

        except Exception as e:
            st.error(f"❌ Erreur critique : {e}")
