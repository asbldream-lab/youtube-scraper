import streamlit as st
from yt_dlp import YoutubeDL
from concurrent.futures import ThreadPoolExecutor, as_completed
from langdetect import detect, DetectorFactory
import time

DetectorFactory.seed = 0

st.set_page_config(page_title="YT Sniper V14", layout="wide")

LANG_MAP = {"Auto": None, "Français": "fr", "English": "en", "Spanish": "es"}

# --- FONCTIONS ---

def log_step(msg):
    """Ajoute une ligne au journal de bord"""
    st.session_state.logs.append(f"[{time.strftime('%H:%M:%S')}] {msg}")

def is_lang(comments, target_code):
    if not target_code or not comments: return True
    hits = 0
    # On s'assure que comments est une liste
    comment_list = comments if isinstance(comments, list) else []
    sample = [c.get('text') for c in comment_list if c.get('text')][:10]
    if not sample: return False
    for t in sample:
        try:
            if detect(t) == target_code: hits += 1
        except: continue
    return hits >= (len(sample) * 0.3)

def fetch_fast(url):
    """Scan ultra rapide sans commentaires"""
    opts = {'quiet': True, 'skip_download': True, 'socket_timeout': 5, 'extract_flat': True}
    with YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)

def fetch_deep(url):
    """Extraction avec commentaires (uniquement pour les finalistes)"""
    opts = {'quiet': True, 'skip_download': True, 'getcomments': True, 'max_comments': 10, 'socket_timeout': 5}
    with YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)

# --- INTERFACE ---
st.title("🚀 YouTube Sniper V14")

if 'logs' not in st.session_state: st.session_state.logs = []

with st.sidebar:
    kws = st.text_area("Mots-clés", "ICE Trump").split('\n')
    target_lang = st.selectbox("Langue", list(LANG_MAP.keys()))
    min_v = st.number_input("Vues Min", value=50000)
    limit = st.slider("Scan max", 5, 30, 10)
    go = st.button("LANCER", type="primary", use_container_width=True)

if go:
    st.session_state.logs = []
    log_step("Démarrage de l'algorithme...")
    target_code = LANG_MAP[target_lang]
    final_results = []
    
    progress_bar = st.progress(0)
    
    # 1. SCAN RAPIDE
    urls = []
    log_step(f"Recherche de vidéos pour {len(kws)} mots-clés...")
    with YoutubeDL({'quiet': True, 'extract_flat': True}) as ydl:
        for i, kw in enumerate(kws):
            if not kw.strip(): continue
            res = ydl.extract_info(f"ytsearch{limit}:{kw}", download=False)
            found = [f"https://www.youtube.com/watch?v={e['id']}" for e in res.get('entries', [])]
            urls.extend(found)
            log_step(f"Mot-clé '{kw}': {len(found)} vidéos trouvées.")
    
    urls = list(set(urls))
    progress_bar.progress(30)

    # 2. ANALYSE PROFONDE (Seulement si vues OK)
    log_step(f"Analyse profonde de {len(urls)} candidates...")
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_deep, u) for u in urls]
        for idx, f in enumerate(as_completed(futures)):
            v = f.result()
            if v:
                title = v.get('title', 'Sans titre')
                views = v.get('view_count', 0)
                if views >= min_v:
                    log_step(f"Vérification langue : {title[:30]}...")
                    if is_lang(v.get('comments'), target_code):
                        subs = v.get('channel_follower_count') or 1
                        v['_ratio'] = views / subs
                        final_results.append(v)
                        log_step(f"✅ VALIDÉE : {title}")
                else:
                    log_step(f"❌ REJETÉE (Vues: {views}) : {title[:30]}")
            progress_bar.progress(min(30 + int((idx/len(urls))*70), 100))

    final_results = sorted(final_results, key=lambda x: x.get('_ratio', 0), reverse=True)
    
    # Affichage
    for vid in final_results:
        with st.container(border=True):
            st.subheader(f"{vid['_ratio']:.1f}x | {vid['title']}")
            st.write(f"👁️ {vid['view_count']:,} vues | 📺 {vid['uploader']}")
            st.link_button("Lien", vid['webpage_url'])

    progress_bar.progress(100)

st.divider()
st.subheader("📋 Journal de l'algorithme (Logs)")
# Case séparée pour Ctrl+A facile
st.text_area("Copie les logs ici pour le débug :", value="\n".join(st.session_state.logs), height=300)
