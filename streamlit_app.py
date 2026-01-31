import streamlit as st
from yt_dlp import YoutubeDL
from concurrent.futures import ThreadPoolExecutor, as_completed
from langdetect import detect, DetectorFactory
import time
import re

# --- CONFIG ---
DetectorFactory.seed = 0
st.set_page_config(page_title="YT Sniper Corrected", layout="wide")

# LE SECRET DE LA FIABILITÉ : Mots obligatoires par langue
# Si le titre contient un de ces mots, on est SÛR de la langue.
STOPWORDS = {
    "fr": ["le", "la", "les", "du", "de", "et", "en", "un", "une", "des", "au", "ce", "sur", "pour", "qui", "que", "dans", "est", "c'est"],
    "en": ["the", "a", "an", "and", "is", "of", "to", "in", "on", "at", "for", "with", "that", "this", "it", "by"],
    "es": ["el", "la", "los", "las", "un", "una", "y", "en", "de", "con", "por", "para", "es", "que", "del"]
}

# --- FONCTIONS ---

def quick_title_validate(title, lang_code):
    """
    FILTRE HYBRIDE (0.0s) :
    1. Vérifie la présence de petits mots (le, la, de...) -> 100% Fiable & Rapide.
    2. Si aucun mot clé trouvé, on laisse le bénéfice du doute (True).
    """
    if not title: return False
    
    # On récupère la liste des mots sûrs pour la langue cible
    target_words = STOPWORDS.get(lang_code, [])
    if not target_words: return True # Si langue inconnue, on garde tout
    
    # Nettoyage rapide
    title_words = set(re.findall(r'\w+', title.lower()))
    
    # Intersection : Y a-t-il un mot français dans le titre ?
    # "ICE : la milice de trump" -> contient "la", "de" -> GARDE !
    has_stopword = any(w in title_words for w in target_words)
    
    if has_stopword:
        return True
        
    # Si le titre est très court (ex: "Trump 2024"), pas de stopwords, donc on garde pour vérifier les commentaires
    return True 

def check_comments_reading(comments, target_code):
    """Validation finale par les commentaires"""
    if not target_code or not comments: return True
    readable = [c.get('text', '') for c in comments if len(c.get('text', '') or '') > 5]
    if not readable: return False 
    
    hits = 0
    # On lit max 5 commentaires pour aller vite
    for text in readable[:5]: 
        try:
            if detect(text) == target_code: hits += 1
        except: continue
    return hits >= 1

def fetch_deep_data(url):
    """Téléchargement ciblé"""
    opts = {
        'quiet': True, 'skip_download': True, 'getcomments': True, 
        'max_comments': 5, 
        'socket_timeout': 3,
        'ignoreerrors': True, 'no_warnings': True
    }
    with YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)

def search_flat(query, limit):
    """Scan rapide"""
    opts = {
        'quiet': True, 'extract_flat': True, 'ignoreerrors': True,
        'geo_bypass_country': 'FR'
    }
    with YoutubeDL(opts) as ydl:
        try:
            res = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
            return res.get('entries', [])
        except: return []

# --- APP ---
st.title("🚀 YT Sniper : Precision & Speed")

with st.sidebar:
    kws = st.text_area("Mots-clés", "ICE Trump").split('\n')
    lang_code = st.selectbox("Langue cible", ["fr", "en", "es"])
    min_v = st.number_input("Vues Min", value=50000)
    go = st.button("LANCER", type="primary")

if go:
    st.session_state.logs = []
    start_time = time.time()
    barre = st.progress(0)
    status = st.empty()
    
    # 1. GHOST SEARCH (Trouve ARTE grâce à 'lang:fr')
    search_queries = []
    for kw in [k.strip() for k in kws if k.strip()]:
        # On ne fait QUE la recherche ciblée pour gagner du temps
        # Si tu veux du FR, inutile de chercher sans le filtre lang:fr
        search_queries.append(f"{kw} lang:{lang_code}") 

    status.write(f"⚡ Scan optimisé...")
    
    candidates = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(search_flat, q, 25) for q in search_queries]
        for f in as_completed(futures):
            res = f.result()
            if res: candidates.extend(res)

    # 2. FILTRE STOPWORDS (C'est ça qui sauve ARTE)
    survivors = []
    unique_ids = set()
    
    for vid in candidates:
        if not vid or vid['id'] in unique_ids: continue
        unique_ids.add(vid['id'])
        
        if vid.get('view_count', 0) < min_v: continue
        
        # Le nouveau filtre vérifie la présence de "le", "la", "de"...
        if quick_title_validate(vid.get('title'), lang_code):
            survivors.append(vid)

    status.write(f"🔍 {len(survivors)} candidats. Analyse finale...")
    barre.progress(40)

    # 3. DEEP SCAN (Top 8 pour être sûr)
    final_results = []
    if survivors:
        # On augmente légèrement la tolérance (Top 8 au lieu de 5) pour ne pas rater ARTE si elle est 6ème
        top_candidates = sorted(survivors, key=lambda x: x.get('view_count', 0), reverse=True)[:8]
        
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(fetch_deep_data, v['url']): v for v in top_candidates}
            
            done = 0
            for f in as_completed(futures):
                done += 1
                try:
                    data = f.result()
                    if data:
                        if check_comments_reading(data.get('comments'), lang_code):
                            subs = data.get('channel_follower_count') or 1
                            data['_ratio'] = data.get('view_count', 0) / subs
                            final_results.append(data)
                except: pass
                barre.progress(40 + int((done/len(top_candidates))*60))

    # --- RÉSULTATS ---
    barre.progress(100)
    elapsed = time.time() - start_time
    status.success(f"Terminé en {elapsed:.1f} secondes.")

    final_results = sorted(final_results, key=lambda x: x.get('_ratio', 0), reverse=True)
    
    if not final_results:
        st.error("Aucune vidéo trouvée. Essaie de baisser les vues min.")
    
    for vid in final_results:
        with st.container(border=True):
            c1, c2 = st.columns([1, 4])
            c1.image(vid.get('thumbnail'))
            c2.subheader(f"{vid.get('_ratio', 0):.1f}x | {vid.get('title')}")
            c2.write(f"👁️ {vid.get('view_count'):,} vues")
            c2.link_button("Voir la vidéo", vid.get('webpage_url'))
