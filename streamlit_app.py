import streamlit as st
from yt_dlp import YoutubeDL
from concurrent.futures import ThreadPoolExecutor, as_completed
from langdetect import detect, DetectorFactory
import time

# Fixer le seed pour la précision de lecture
DetectorFactory.seed = 0

st.set_page_config(page_title="YT Sniper V16", layout="wide")

LANG_MAP = {"Auto": None, "Français": "fr", "English": "en", "Spanish": "es"}

def log_step(msg):
    if 'logs' not in st.session_state: st.session_state.logs = []
    st.session_state.logs.append(f"[{time.strftime('%H:%M:%S')}] {msg}")

def detect_language_by_reading(video_data, target_code):
    """L'algo 'lit' les commentaires pour identifier la langue"""
    if not target_code: return True
    
    comments = video_data.get('comments') or []
    if not comments:
        # Si pas de coms, on essaie de lire le titre
        try: return detect(video_data.get('title', '')) == target_code
        except: return False

    text_to_read = [c.get('text', '') for c in comments[:5] if len(c.get('text', '')) > 3]
    
    hits = 0
    for text in text_to_read:
        try:
            # L'IA lit et identifie la langue du texte
            if detect(text) == target_code:
                hits += 1
        except: continue
    
    # Si au moins 1 commentaire sur les 5 est clairement dans la langue, on valide
    return hits >= 1

def fetch_video(url):
    """Extraction flash : métadonnées + 5 commentaires"""
    opts = {
        'quiet': True, 'skip_download': True, 'getcomments': True, 
        'max_comments': 5, 'socket_timeout': 4, 'ignoreerrors': True,
        'no_warnings': True
    }
    with YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)

# --- UI ---
st.title("🚀 YouTube Sniper V16")

with st.sidebar:
    st.header("Paramètres")
    kw_input = st.text_area("Mots-clés", "ICE Trump")
    target_lang = st.selectbox("Langue à détecter", list(LANG_MAP.keys()))
    min_v = st.number_input("Vues Minimum", value=50000)
    limit = st.slider("Nombre de vidéos à scanner", 5, 50, 20)
    go = st.button("LANCER L'ANALYSE", type="primary", use_container_width=True)

if go:
    st.session_state.logs = []
    log_step("Démarrage immédiat...")
    target_code = LANG_MAP[target_lang]
    results = []
    
    barre = st.progress(0)
    
    # 1. Capture des URLs (Scan plat ultra-rapide)
    urls = []
    with YoutubeDL({'quiet': True, 'extract_flat': True}) as ydl:
        for kw in kw_input.split('\n'):
            if not kw.strip(): continue
            log_step(f"Recherche YouTube pour : {kw}")
            res = ydl.extract_info(f"ytsearch{limit}:{kw}", download=False)
            urls.extend([f"https://www.youtube.com/watch?v={e['id']}" for e in res.get('entries', []) if e])
    
    urls = list(set(urls)) # Supprimer doublons
    barre.progress(20)

    # 2. Lecture et Filtrage (Multi-threadé pour < 5s)
    log_step(f"Lecture de {len(urls)} vidéos en parallèle...")
    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = [executor.submit(fetch_video, u) for u in urls]
        for i, f in enumerate(as_completed(futures)):
            v = f.result()
            if v:
                v_views = v.get('view_count', 0)
                v_title = v.get('title', '')[:40]
                
                if v_views >= min_v:
                    # L'étape de "lecture" des commentaires
                    if detect_language_by_reading(v, target_code):
                        subs = v.get('channel_follower_count') or 1
                        v['_ratio'] = v_views / subs
                        results.append(v)
                        log_step(f"✅ LU ET VALIDÉ ({v_views} vues) : {v_title}")
                    else:
                        log_step(f"🌍 LANGUE INCORRECTE : {v_title}")
                else:
                    log_step(f"📉 TROP PEU DE VUES ({v_views}) : {v_title}")
            
            # Mise à jour barre de progression
            current_p = 20 + int((i+1)/len(urls)*80)
            barre.progress(min(current_p, 100))

    # Affichage des résultats
    results = sorted(results, key=lambda x: x.get('_ratio', 0), reverse=True)
    for vid in results:
        with st.container(border=True):
            c1, c2 = st.columns([1, 4])
            c1.image(vid.get('thumbnail'))
            c2.subheader(f"{vid['_ratio']:.1f}x | {vid['title']}")
            c2.write(f"👁️ {vid['view_count']:,} vues | 👥 {vid['channel_follower_count']:,} abos")
            c2.link_button("Lien", vid['webpage_url'])

st.divider()
st.subheader("📋 Zone de Debug (Logs) - Ctrl+A disponible")
st.text_area("Journal des étapes :", value="\n".join(st.session_state.get('logs', [])), height=300)
