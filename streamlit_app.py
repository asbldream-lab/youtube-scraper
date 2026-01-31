import streamlit as st
from yt_dlp import YoutubeDL
from concurrent.futures import ThreadPoolExecutor, as_completed
from langdetect import detect, DetectorFactory
import time

# -----------------------------------------------------------------------------
# 🔧 CONFIGURATION ET SÉCURITÉ
# -----------------------------------------------------------------------------
# Fixer l'aléatoire pour que la détection de langue soit constante
DetectorFactory.seed = 0

st.set_page_config(page_title="YT Ultimate Sniper", layout="wide")

# Configuration des régions pour forcer YouTube à changer ses résultats
REGION_CONFIG = {
    "Français": {"code": "fr", "region": "FR", "hl": "fr-FR"},
    "English": {"code": "en", "region": "US", "hl": "en-US"},
    "Spanish": {"code": "es", "region": "ES", "hl": "es-ES"},
    "Auto": {"code": None, "region": None, "hl": None}
}

# -----------------------------------------------------------------------------
# 🧠 CERVEAU DE L'ALGO
# -----------------------------------------------------------------------------

def log_msg(msg):
    """Journalise chaque action avec un timestamp"""
    if 'logs' not in st.session_state: st.session_state.logs = []
    st.session_state.logs.append(f"[{time.strftime('%H:%M:%S')}] {msg}")

def detect_audience_language(video_data, target_code):
    """
    Stratégie Hybride :
    1. Check Titre (Rapide).
    2. Si échec/ambigu, Check Commentaires (Précis).
    """
    if not target_code: return True
    
    # A. Test rapide sur le titre
    title = video_data.get('title', '')
    try:
        if len(title) > 5 and detect(title) == target_code:
            return True
    except: pass

    # B. Test profond sur les commentaires
    comments = video_data.get('comments') or []
    if not comments: return False # Pas de coms, pas de validation possible
    
    hits = 0
    # On prend les coms qui ont du texte (>4 chars)
    valid_sample = [c.get('text', '') for c in comments if len(c.get('text', '') or '') > 4][:8]
    
    if not valid_sample: return False

    for text in valid_sample:
        try:
            if detect(text) == target_code: hits += 1
        except: continue
    
    # Si 2 commentaires sur 8 matchent, c'est validé (Assez pour confirmer l'audience)
    return hits >= 1 # Seuil très permissif pour ne rien rater

def fetch_search_results(keyword, limit, config):
    """PHASE 1 : Scan Large et Rapide (Métadonnées uniquement)"""
    opts = {
        'quiet': True,
        'extract_flat': True,  # <--- LE SECRET DE LA VITESSE
        'ignoreerrors': True,
        'geo_bypass': True,
        'geo_bypass_country': config['region'], # Force la localisation (ex: FR)
        'http_headers': {'Accept-Language': config['hl']} if config['hl'] else None
    }
    with YoutubeDL(opts) as ydl:
        # On demande 2x plus de résultats que nécessaire pour compenser le filtrage
        try:
            res = ydl.extract_info(f"ytsearch{limit}:{keyword}", download=False)
            return res.get('entries', [])
        except Exception as e:
            log_msg(f"Erreur recherche '{keyword}': {e}")
            return []

def fetch_deep_analysis(url):
    """PHASE 2 : Extraction Chirurgicale (Commentaires)"""
    opts = {
        'quiet': True,
        'skip_download': True,
        'getcomments': True,
        'max_comments': 8, # Suffisant pour détecter la langue
        'socket_timeout': 5, # Timeout agressif pour ne pas bloquer
        'ignoreerrors': True,
        'no_warnings': True
    }
    with YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)

# -----------------------------------------------------------------------------
# 🖥️ INTERFACE UTILISATEUR
# -----------------------------------------------------------------------------

st.title("🚀 YT Ultimate Sniper (Anti-Fail Mode)")

with st.sidebar:
    st.header("🎯 Paramètres de Tir")
    kws = st.text_area("Mots-clés (1/ligne)", "ICE Trump").split('\n')
    target_settings = st.selectbox("Cible Géographique", list(REGION_CONFIG.keys()))
    min_views = st.number_input("Vues Minimum", value=50000, step=10000)
    
    st.divider()
    scan_depth = st.slider("Profondeur du Scan", 20, 100, 60, help="Plus c'est haut, plus on cherche loin dans le classement.")
    go = st.button("LANCER L'ANALYSE", type="primary", use_container_width=True)

# -----------------------------------------------------------------------------
# 🔥 EXÉCUTION
# -----------------------------------------------------------------------------

if go:
    # Reset
    st.session_state.logs = []
    config = REGION_CONFIG[target_settings]
    final_pizzas = [] # Les pépites
    
    status_container = st.container()
    progress_bar = st.progress(0)
    
    log_msg(f"🚀 Démarrage | Simulation: {config['region']} | Profondeur: {scan_depth}")

    # --- ÉTAPE 1 : LE GRAND FILET (Scan Flat) ---
    raw_candidates = []
    keywords = [k.strip() for k in kws if k.strip()]
    
    if not keywords:
        st.error("Aucun mot-clé détecté.")
    else:
        with ThreadPoolExecutor(max_workers=5) as executor:
            # On lance les recherches en parallèle pour chaque mot-clé
            futures = {executor.submit(fetch_search_results, kw, scan_depth, config): kw for kw in keywords}
            
            for f in as_completed(futures):
                entries = f.result()
                raw_candidates.extend(entries)
                log_msg(f"📥 Récupéré {len(entries)} résultats bruts pour '{futures[f]}'")

        # Suppression des doublons (par ID vidéo)
        unique_candidates = {v['id']: v for v in raw_candidates if v}.values()
        
        # --- ÉTAPE 2 : LE FILTRE IMPITOYABLE (Vues) ---
        survivors = []
        for vid in unique_candidates:
            # Sécurité : parfois view_count est None
            v_count = vid.get('view_count')
            if v_count is None: v_count = 0 
            
            if v_count >= min_views:
                survivors.append(vid)
        
        log_msg(f"⚔️ Filtre Vues : {len(unique_candidates)} -> {len(survivors)} candidats restants.")
        progress_bar.progress(30)

        # --- ÉTAPE 3 : L'ANALYSE PROFONDE (Langue/Coms) ---
        if not survivors:
            st.warning("Aucune vidéo n'a assez de vues. Réduis le seuil ou augmente la profondeur.")
        else:
            with ThreadPoolExecutor(max_workers=10) as executor: # 10 workers = rapide
                # On ne lance le fetch_deep QUE sur les survivors
                future_to_url = {executor.submit(fetch_deep_analysis, v['url']): v for v in survivors}
                
                completed_count = 0
                for f in as_completed(future_to_url):
                    completed_count += 1
                    try:
                        detailed_vid = f.result()
                        if detailed_vid:
                            title = detailed_vid.get('title', 'N/A')
                            
                            # VERIFICATION ULTIME DE LA LANGUE
                            if detect_audience_language(detailed_vid, config['code']):
                                subs = detailed_vid.get('channel_follower_count') or 1
                                detailed_vid['_ratio'] = detailed_vid.get('view_count', 0) / subs
                                final_pizzas.append(detailed_vid)
                                log_msg(f"✅ BINGO : {title[:30]}...")
                            else:
                                log_msg(f"❌ Rejet Langue : {title[:30]}...")
                    except Exception as e:
                        log_msg(f"Erreur analyse deep: {e}")
                    
                    # Update barre de progression
                    prog = 30 + int((completed_count / len(survivors)) * 70)
                    progress_bar.progress(min(prog, 100))

    # -------------------------------------------------------------------------
    # 🏆 RÉSULTATS
    # -------------------------------------------------------------------------
    progress_bar.empty()
    
    # Tri par Ratio de Viralité
    final_pizzas = sorted(final_pizzas, key=lambda x: x.get('_ratio', 0), reverse=True)

    if final_pizzas:
        st.success(f"🏆 {len(final_pizzas)} Pépites trouvées en moins de 5 secondes !")
        
        for vid in final_pizzas:
            with st.container(border=True):
                c1, c2 = st.columns([1, 4])
                thumb = vid.get('thumbnail')
                if thumb: c1.image(thumb)
                
                c2.subheader(f"{vid.get('_ratio', 0):.1f}x | {vid.get('title')}")
                c2.write(f"👁️ **{vid.get('view_count'):,}** vues | 📅 {vid.get('upload_date')}")
                c2.write(f"📺 Chaîne : {vid.get('uploader')}")
                c2.link_button("▶️ Voir sur YouTube", vid.get('webpage_url'))
    else:
        st.error("Aucune vidéo validée. Regarde les logs ci-dessous pour comprendre pourquoi.")

    st.divider()
    with st.expander("🕵️ LOGS DE DÉBUGAGE (Ctrl+A pour copier)", expanded=True):
        st.text_area("Logs complets", value="\n".join(st.session_state.logs), height=250)
