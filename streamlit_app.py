import streamlit as st
from yt_dlp import YoutubeDL
from concurrent.futures import ThreadPoolExecutor, as_completed
from langdetect import detect, DetectorFactory
import re
import time

# ==========================================
# 🔧 CONFIGURATION ULTIME
# ==========================================
DetectorFactory.seed = 0
st.set_page_config(page_title="YT Sniper V20 (Final)", layout="wide")

# LISTE DE MOTS QUI NE TROMPENT PAS (Stopwords)
# Si un titre contient "le" ou "c'est", il est 100% français, même s'il parle de Trump.
STOPWORDS = {
    "fr": {"le", "la", "les", "du", "de", "et", "en", "un", "une", "des", "au", "aux", "ce", "sur", "pour", "par", "qui", "que", "avec", "dans", "est", "c'est"},
    "en": {"the", "a", "an", "and", "is", "of", "to", "in", "on", "at", "for", "with", "that", "this", "it", "by", "from"},
    "es": {"el", "la", "los", "las", "un", "una", "y", "en", "de", "con", "por", "para", "es", "que", "del", "al"}
}

REGION_CONFIG = {
    "Français": {"code": "fr", "region": "FR", "stops": STOPWORDS["fr"]},
    "English": {"code": "en", "region": "US", "stops": STOPWORDS["en"]},
    "Spanish": {"code": "es", "region": "ES", "stops": STOPWORDS["es"]},
}

# ==========================================
# 🧠 MOTEUR INTELLIGENT
# ==========================================

def log_msg(msg):
    if 'logs' not in st.session_state: st.session_state.logs = []
    st.session_state.logs.append(f"[{time.strftime('%H:%M:%S')}] {msg}")

def is_likely_target_lang(title, target_stops):
    """
    FILTRE BALISTIQUE (0.00001s)
    Vérifie la présence de mots de liaison typiques.
    Ex: "Trump vs ICE : Le bilan" -> Contient "le" -> GARDE.
    Ex: "Trump vs ICE : Full report" -> Pas de mots FR -> POUBELLE.
    """
    if not title: return False
    # Nettoyage: minuscules et on garde que les mots
    words = set(re.findall(r'\w+', title.lower()))
    # Intersection : est-ce qu'on a des mots communs ?
    common = words.intersection(target_stops)
    return len(common) >= 1

def check_comments_deep(comments, target_code):
    """Validation finale par l'audience (Commentaires)"""
    if not target_code or not comments: return True
    valid_texts = [c.get('text', '') for c in comments if len(c.get('text', '') or '') > 5]
    if not valid_texts: return False # Pas de coms exploitables -> Dans le doute on rejette pour la qualité

    hits = 0
    # On check max 8 commentaires
    for text in valid_texts[:8]:
        try:
            if detect(text) == target_code: hits += 1
        except: continue
    
    # Si au moins 1 commentaire est clairement dans la langue, c'est bon.
    return hits >= 1

def fetch_details(url):
    """Extraction chirurgicale (Commentaires)"""
    opts = {
        'quiet': True, 'skip_download': True, 'getcomments': True, 
        'max_comments': 8, 'socket_timeout': 4, # Timeout agressif
        'ignoreerrors': True, 'no_warnings': True
    }
    with YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)

# ==========================================
# 🖥️ INTERFACE
# ==========================================
st.title("🚀 YT Sniper V20 (The One Billion Fix)")
st.caption("Algorithme à Entonnoir : Scan Large -> Filtre Mots -> Validation IA")

with st.sidebar:
    st.header("🎯 Ciblage")
    kws = st.text_area("Mots-clés", "ICE Trump").split('\n')
    target_lang = st.selectbox("Langue Cible", list(REGION_CONFIG.keys()))
    min_v = st.number_input("Vues Minimum", value=50000)
    # Scan depth forcé haut par défaut pour trouver ARTE
    scan_depth = st.slider("Profondeur du Scan (Titres)", 50, 200, 100) 
    go = st.button("LANCER L'ANALYSE", type="primary")

if go:
    st.session_state.logs = []
    config = REGION_CONFIG[target_lang]
    log_msg(f"🔥 Démarrage | Région: {config['region']} | Profondeur: {scan_depth}")
    
    barre = st.progress(0)
    final_pizzas = []
    
    # --- PHASE 1 : LE CHALUTAGE (Scan Flat) ---
    # On récupère BEAUCOUP de vidéos (100) très VITE (0.5s)
    raw_candidates = []
    search_opts = {
        'quiet': True, 'extract_flat': True, 
        'geo_bypass_country': config['region'], # Force YouTube à penser qu'on est en France
        'ignoreerrors': True
    }
    
    with YoutubeDL(search_opts) as ydl:
        for kw in [k.strip() for k in kws if k.strip()]:
            log_msg(f"📡 Scan de {scan_depth} titres pour '{kw}'...")
            try:
                res = ydl.extract_info(f"ytsearch{scan_depth}:{kw}", download=False)
                raw_candidates.extend(res.get('entries', []))
            except: pass
    
    # Suppression doublons
    unique_map = {v['id']: v for v in raw_candidates if v}
    candidates = list(unique_map.values())
    log_msg(f"📥 {len(candidates)} vidéos scannées.")
    barre.progress(20)

    # --- PHASE 2 : LE FILTRE FLASH (CPU) ---
    # C'est ici qu'on gagne le match. On filtre sans réseau.
    survivors = []
    for vid in candidates:
        # 1. Filtre Vues
        views = vid.get('view_count', 0) or 0
        if views < min_v: continue
        
        # 2. Filtre Linguistique (Stopwords)
        # Si ça ne contient pas "le", "la", "et"... on jette ! (Sauf si mode Auto)
        title = vid.get('title', '')
        if config['stops'] and not is_likely_target_lang(title, config['stops']):
            # log_msg(f"🚫 Rejet Titre (Langue) : {title[:30]}") # Decommenter pour debug
            continue
            
        survivors.append(vid)

    log_msg(f"⚡ Après filtre Titre+Vues : {len(survivors)} vidéos restantes à vérifier.")
    barre.progress(40)

    # --- PHASE 3 : VALIDATION FINALE (RÉSEAU) ---
    # On ne télécharge que les vrais candidats potentiels
    if survivors:
        # On limite l'analyse profonde aux 10 meilleurs pour garantir les <10s
        to_analyze = survivors[:15] 
        
        with ThreadPoolExecutor(max_workers=15) as executor:
            futures = {executor.submit(fetch_details, v['url']): v for v in to_analyze}
            
            completed = 0
            for f in as_completed(futures):
                completed += 1
                try:
                    data = f.result()
                    if data:
                        title = data.get('title', 'N/A')
                        # Check des commentaires pour être SÛR à 100%
                        if check_comments_deep(data.get('comments'), config['code']):
                            subs = data.get('channel_follower_count') or 1
                            data['_ratio'] = data.get('view_count', 0) / subs
                            final_pizzas.append(data)
                            log_msg(f"✅ VALIDÉ : {title}")
                        else:
                            log_msg(f"❌ Rejet (Commentaires) : {title[:30]}")
                except: pass
                
                # Barre de progression fluide
                prog = 40 + int((completed/len(to_analyze))*60)
                barre.progress(min(prog, 100))

    # --- RÉSULTATS ---
    barre.progress(100)
    final_pizzas = sorted(final_pizzas, key=lambda x: x.get('_ratio', 0), reverse=True)

    if final_pizzas:
        st.success(f"🏆 {len(final_pizzas)} Vidéos trouvées !")
        for vid in final_pizzas:
            with st.container(border=True):
                c1, c2 = st.columns([1, 4])
                c1.image(vid.get('thumbnail'))
                c2.subheader(f"{vid.get('_ratio', 0):.1f}x | {vid.get('title')}")
                c2.write(f"👁️ **{vid.get('view_count'):,}** vues | 📅 {vid.get('upload_date')}")
                c2.write(f"📺 {vid.get('uploader')}")
                c2.link_button("Lien Vidéo", vid.get('webpage_url'))
    else:
        st.error("Aucune vidéo trouvée. Vérifie les logs ci-dessous.")

    st.divider()
    with st.expander("🛠️ LOGS TECHNIQUES (Ctrl+A)", expanded=True):
        st.text_area("Logs", value="\n".join(st.session_state.logs), height=300)
