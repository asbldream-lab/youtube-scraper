import streamlit as st
from yt_dlp import YoutubeDL
from concurrent.futures import ThreadPoolExecutor, as_completed
from langdetect import detect, DetectorFactory, LangDetectException
import time

# --- CONFIGURATION ---
DetectorFactory.seed = 0
st.set_page_config(page_title="YT Sniper Speed", layout="wide")

# --- FONCTIONS ---

def quick_title_check(title, target_code):
    """
    FILTRE ÉCLAIR (0.01s)
    Analyse le titre AVANT de lancer le téléchargement lourd.
    Si le titre est visiblement dans la mauvaise langue, on annule tout.
    """
    if not title or len(title) < 5: return False
    try:
        # Si on cherche du FR et que le titre est détecté EN -> POUBELLE
        detected = detect(title)
        if detected != target_code:
            # Petite sécurité : si le titre est court, l'IA peut se tromper, donc on garde
            if len(title.split()) > 4: 
                return False
        return True
    except:
        return True # Dans le doute, on garde

def check_comments_reading(comments, target_code):
    """Validation finale par lecture des commentaires"""
    if not target_code or not comments: return True
    readable = [c.get('text', '') for c in comments if len(c.get('text', '') or '') > 5]
    if not readable: return False 
    
    hits = 0
    for text in readable[:5]: # On ne lit que les 5 premiers
        try:
            if detect(text) == target_code: hits += 1
        except: continue
    return hits >= 1

def fetch_deep_data(url):
    """Téléchargement des commentaires (Lourd -> Uniquement sur les élus)"""
    opts = {
        'quiet': True, 'skip_download': True, 'getcomments': True, 
        'max_comments': 5, # On réduit à 5 pour la vitesse max
        'socket_timeout': 3, # Timeout agressif
        'ignoreerrors': True, 'no_warnings': True
    }
    with YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)

def search_flat(query, limit):
    """Recherche 'Flat' (Métadonnées seules -> Instantané)"""
    opts = {
        'quiet': True, 'extract_flat': True, 'ignoreerrors': True,
        'geo_bypass_country': 'FR' # Force la localisation
    }
    with YoutubeDL(opts) as ydl:
        try:
            res = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
            return res.get('entries', [])
        except: return []

# --- INTERFACE ---
st.title("🚀 YT Sniper : Speed Demon (Max 10s)")

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
    
    # 1. RECHERCHE CIBLÉE (Ghost Search)
    # On utilise "lang:fr" pour forcer YouTube à faire le tri à la source
    search_queries = []
    for kw in [k.strip() for k in kws if k.strip()]:
        search_queries.append(f"{kw} lang:{lang_code}") 

    status.write(f"⚡ Scan rapide de {len(search_queries)} requêtes...")
    
    candidates = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(search_flat, q, 20) for q in search_queries]
        for f in as_completed(futures):
            res = f.result()
            if res: candidates.extend(res)

    # 2. PRÉ-FILTRAGE CPU (INSTANTANÉ)
    # C'est ici qu'on gagne les 140 secondes.
    # On élimine tout ce qui a un titre anglais ou peu de vues SANS réseau.
    survivors = []
    unique_ids = set()
    
    for vid in candidates:
        if not vid or vid['id'] in unique_ids: continue
        unique_ids.add(vid['id'])
        
        # Filtre Vues
        if vid.get('view_count', 0) < min_v: continue
        
        # Filtre Titre (Le Secret de la Vitesse)
        # Si le titre est anglais, on ne perd pas 5s à télécharger les commentaires
        if not quick_title_check(vid.get('title'), lang_code):
            continue
            
        survivors.append(vid)

    status.write(f"🔍 {len(survivors)} candidats qualifiés. Vérification finale...")
    barre.progress(40)

    # 3. VALIDATION PROFONDE (LIMITÉE AUX MEILLEURS)
    final_results = []
    if survivors:
        # On ne lance le téléchargement lourd QUE sur les 5 meilleures vidéos (par vues)
        # Inutile de vérifier la 20ème vidéo si on veut aller vite.
        top_candidates = sorted(survivors, key=lambda x: x.get('view_count', 0), reverse=True)[:5]
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(fetch_deep_data, v['url']): v for v in top_candidates}
            
            done = 0
            for f in as_completed(futures):
                done += 1
                try:
                    data = f.result()
                    if data:
                        # Validation par commentaires
                        if check_comments_reading(data.get('comments'), lang_code):
                            subs = data.get('channel_follower_count') or 1
                            data['_ratio'] = data.get('view_count', 0) / subs
                            final_results.append(data)
                except: pass
                barre.progress(40 + int((done/len(top_candidates))*60))

    # --- AFFICHAGE ---
    barre.progress(100)
    elapsed = time.time() - start_time
    
    if elapsed < 15:
        status.success(f"Terminé en {elapsed:.1f} secondes ! ⚡")
    else:
        status.warning(f"Terminé en {elapsed:.1f} secondes.")

    final_results = sorted(final_results, key=lambda x: x.get('_ratio', 0), reverse=True)
    
    if not final_results:
        st.error("Aucune vidéo trouvée (Filtres trop stricts ou blocage YouTube).")
    
    for vid in final_results:
        with st.container(border=True):
            c1, c2 = st.columns([1, 4])
            c1.image(vid.get('thumbnail'))
            c2.subheader(f"{vid.get('_ratio', 0):.1f}x | {vid.get('title')}")
            c2.write(f"👁️ {vid.get('view_count'):,} vues | 💬 Langue vérifiée")
            c2.link_button("Voir la vidéo", vid.get('webpage_url'))
