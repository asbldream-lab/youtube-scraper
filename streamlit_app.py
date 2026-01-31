import streamlit as st
from yt_dlp import YoutubeDL
from concurrent.futures import ThreadPoolExecutor, as_completed
from langdetect import detect, DetectorFactory
import os

# Sécurité pour la détection de langue
DetectorFactory.seed = 0

# --- CONFIG ---
LANGUAGE_MAP = {
    "Auto": {"hl": "en", "code": None},
    "Français": {"hl": "fr", "code": "fr"},
    "English": {"hl": "en", "code": "en"},
    "Spanish": {"hl": "es", "code": "es"}
}

def is_right_lang(text, target_code):
    if not target_code or not text or len(text) < 12: return True
    try:
        return detect(text) == target_code
    except:
        return True

# --- LOGIQUE ---
def get_fast_info(keyword, max_results, lang_name):
    config = LANGUAGE_MAP.get(lang_name, LANGUAGE_MAP["Auto"])
    # On injecte la langue dans le mot-clé pour aider YouTube
    search_keyword = f"{keyword} lang:{config['code']}" if config['code'] else keyword
    
    opts = {
        'quiet': True,
        'extract_flat': True,
        'socket_timeout': 7,
        'http_headers': {'Accept-Language': config["hl"]}
    }
    
    with YoutubeDL(opts) as ydl:
        try:
            res = ydl.extract_info(f"ytsearch{max_results}:{search_keyword}", download=False)
            entries = res.get('entries', [])
            # FIX: On s'assure que chaque entrée a une URL complète pour la suite
            for e in entries:
                if 'url' not in e:
                    e['url'] = f"https://www.youtube.com/watch?v={e['id']}"
            return entries
        except Exception as e:
            st.error(f"Erreur de recherche: {e}")
            return []

def get_full_details(video_url):
    opts = {
        'quiet': True,
        'skip_download': True,
        'getcomments': True,
        'max_comments': 15, # On prend un peu plus de commentaires
        'socket_timeout': 10,
        'ignoreerrors': True
    }
    with YoutubeDL(opts) as ydl:
        return ydl.extract_info(video_url, download=False)

# --- APP ---
st.title("🚀 YouTube Viral Sniper V9 (Fixed)")

with st.sidebar:
    kw_input = st.text_area("Mots-clés (1 par ligne)", "immigration ICE")
    lang = st.selectbox("Langue cible", list(LANGUAGE_MAP.keys()))
    min_v = st.number_input("Vues Min", value=10000)
    limit = st.slider("Vidéos/Mot-clé", 5, 50, 15)
    threads = st.slider("Threads (Vitesse)", 1, 15, 8)
    go = st.button("LANCER", type="primary", use_container_width=True)

if go:
    keywords = [k.strip() for k in kw_input.split('\n') if k.strip()]
    all_candidates = []
    
    with st.status("Recherche et filtrage...", expanded=True) as status:
        # Phase 1: Scan rapide
        for kw in keywords:
            status.write(f"🔍 Scan: {kw}")
            raw_list = get_fast_info(kw, limit, lang)
            target_code = LANGUAGE_MAP[lang]["code"]
            
            for entry in raw_list:
                # Filtre Langue + Vues (si dispos dans le scan rapide)
                if is_right_lang(entry.get('title', ''), target_code):
                    views = entry.get('view_count') or 0
                    if views >= min_v or views == 0: # 0 car parfois non dispo en scan plat
                        all_candidates.append(entry)
        
        status.write(f"🎯 {len(all_candidates)} vidéos à analyser profondément...")
        
        # Phase 2: Deep Dive (Parallel)
        final_data = []
        with ThreadPoolExecutor(max_workers=threads) as executor:
            # On se limite aux 25 meilleures premières pour la vitesse
            futures = {executor.submit(get_full_details, v['url']): v for v in all_candidates[:25]}
            for f in as_completed(futures):
                res = f.result()
                if res and res.get('channel_follower_count'):
                    subs = res['channel_follower_count']
                    views = res.get('view_count', 0)
                    res['_ratio'] = views / subs if subs > 0 else 0
                    # Filtre final sur les vues réelles obtenues
                    if views >= min_v:
                        final_data.append(res)

        final_data = sorted(final_data, key=lambda x: x.get('_ratio', 0), reverse=True)

    # --- RÉSULTATS ---
    if not final_data:
        st.warning("Aucune vidéo n'a passé les filtres. Baisse le nombre de vues min.")
    
    for vid in final_data:
        with st.container(border=True):
            c1, c2 = st.columns([1, 2])
            c1.image(vid.get('thumbnail'))
            c2.subheader(f"{vid.get('_ratio', 0):.1f}x | {vid.get('title')}")
            c2.write(f"👁️ {vid.get('view_count', 0):,} vues | 👥 {vid.get('channel_follower_count', 0):,} abonnés")
            c2.link_button("Ouvrir YouTube", vid.get('webpage_url'))
            with st.expander("Voir les commentaires"):
                for c in vid.get('comments', [])[:8]:
                    st.write(f"💬 {c.get('text')}")
