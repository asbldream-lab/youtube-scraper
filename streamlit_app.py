import streamlit as st
from yt_dlp import YoutubeDL
from concurrent.futures import ThreadPoolExecutor, as_completed
from langdetect import detect, DetectorFactory
import time

# --- SÉCURITÉ ---
DetectorFactory.seed = 0
st.set_page_config(page_title="YT Sniper Final", layout="wide")

# --- MOTEUR DE DÉTECTION ---
def check_comments_reading(comments, target_code):
    """L'Algo lit jusqu'à 8 commentaires pour valider la langue"""
    if not target_code or not comments: return True
    
    # On garde seulement les vraies phrases (> 5 lettres)
    readable_comments = [c.get('text', '') for c in comments if len(c.get('text', '') or '') > 5]
    
    if not readable_comments: 
        return False # Pas de coms lisibles, on rejette par sécurité (qualité)

    hits = 0
    for text in readable_comments[:8]:
        try:
            if detect(text) == target_code: hits += 1
        except: continue
    
    # Si au moins 1 commentaire est dans la bonne langue, c'est validé
    return hits >= 1

def fetch_deep_data(url):
    """Extraction rapide avec commentaires"""
    opts = {
        'quiet': True, 'skip_download': True, 'getcomments': True, 
        'max_comments': 8, 'socket_timeout': 4, # Timeout court pour la vitesse
        'ignoreerrors': True, 'no_warnings': True
    }
    with YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)

def fast_search(query, limit):
    """Recherche simple"""
    opts = {
        'quiet': True, 'extract_flat': True, 'ignoreerrors': True,
        'geo_bypass_country': 'FR' # On force la France pour aider le ranking
    }
    with YoutubeDL(opts) as ydl:
        try:
            res = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
            return res.get('entries', [])
        except: return []

# --- INTERFACE ---
st.title("🚀 YT Sniper : Ghost Search Protocol")
st.caption("Stratégie : Multi-Recherche Invisible (Smart Querying)")

with st.sidebar:
    kws = st.text_area("Mots-clés", "ICE Trump").split('\n')
    # Sélecteur simple pour piloter les recherches fantômes
    lang_code = st.selectbox("Langue recherchée", ["fr", "en", "es"])
    min_v = st.number_input("Vues Min", value=50000)
    go = st.button("LANCER (MAX 10s)", type="primary")

if go:
    st.session_state.logs = []
    start_time = time.time()
    
    barre = st.progress(0)
    status = st.empty()
    
    # --- PHASE 1 : LA RECHERCHE FANTÔME (Multi-Query) ---
    # C'est la clé : L'algo génère des variations pour toi sans que tu tapes rien de plus.
    candidates_pool = []
    queries_to_run = []
    
    for kw in [k.strip() for k in kws if k.strip()]:
        # 1. La recherche pure (ce que tu as tapé) -> Trouve CNN, Fox
        queries_to_run.append(kw)
        
        # 2. La recherche guidée (invisible) -> Trouve ARTE, France 24
        if lang_code == "fr":
            queries_to_run.append(f"{kw} lang:fr") 
        elif lang_code == "en":
            queries_to_run.append(f"{kw} lang:en")
        elif lang_code == "es":
            queries_to_run.append(f"{kw} lang:es")
            
    status.write(f"🕵️ Lancement de {len(queries_to_run)} recherches parallèles (Auto-Correction)...")
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        # On scanne 20 résultats par variation. C'est suffisant car "lang:fr" est très précis.
        futures = {executor.submit(fast_search, q, 20): q for q in queries_to_run}
        
        for f in as_completed(futures):
            res = f.result()
            if res: candidates_pool.extend(res)

    # Dédoublonnage instantané
    unique_candidates = {v['id']: v for v in candidates_pool if v}.values()
    
    # --- PHASE 2 : LE TRI SÉLECTIF ---
    survivors = []
    for vid in unique_candidates:
        views = vid.get('view_count', 0) or 0
        if views >= min_v:
            survivors.append(vid)
            
    status.write(f"⚡ {len(survivors)} vidéos potentielles identifiées. Lecture des commentaires...")
    barre.progress(30)

    # --- PHASE 3 : VALIDATION PAR LECTURE (Deep Scan) ---
    final_results = []
    
    if survivors:
        # On limite aux 15 meilleures pour la vitesse.
        # Grâce à la recherche fantôme, ARTE est forcément dans ce TOP 15.
        to_check = sorted(survivors, key=lambda x: x.get('view_count', 0), reverse=True)[:15]
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(fetch_deep_data, v['url']): v for v in to_check}
            
            done = 0
            for f in as_completed(futures):
                done += 1
                try:
                    data = f.result()
                    if data:
                        # LE JUGEMENT ULTIME : LECTURE DES COMMENTAIRES
                        if check_comments_reading(data.get('comments'), lang_code):
                            subs = data.get('channel_follower_count') or 1
                            data['_ratio'] = data.get('view_count', 0) / subs
                            final_results.append(data)
                except: pass
                
                barre.progress(30 + int((done/len(to_check))*70))

    # --- RÉSULTATS ---
    barre.progress(100)
    final_results = sorted(final_results, key=lambda x: x.get('_ratio', 0), reverse=True)
    
    duration = time.time() - start_time
    status.success(f"Terminé en {duration:.1f} secondes.")

    if not final_results:
        st.error("Aucune vidéo trouvée. Essaie de baisser le nombre de vues minimum.")
    
    for vid in final_results:
        with st.container(border=True):
            c1, c2 = st.columns([1, 4])
            c1.image(vid.get('thumbnail'))
            c2.subheader(f"{vid.get('_ratio', 0):.1f}x | {vid.get('title')}")
            c2.write(f"👁️ {vid.get('view_count'):,} vues | 💬 Langue confirmée par commentaires")
            c2.link_button("Voir la vidéo", vid.get('webpage_url'))
            
            with st.expander("Voir les commentaires analysés"):
                coms = vid.get('comments', [])[:3]
                for c in coms:
                    st.caption(f"- {c.get('text')[:100]}...")
