import streamlit as st
from yt_dlp import YoutubeDL
from concurrent.futures import ThreadPoolExecutor, as_completed
from langdetect import detect, DetectorFactory

# Fixer le seed pour des résultats de détection constants
DetectorFactory.seed = 0

# --- CONFIGURATION INTERFACE ---
st.set_page_config(page_title="YouTube Sniper V13", layout="wide")

LANG_MAP = {
    "Auto": None,
    "Français": "fr",
    "English": "en",
    "Spanish": "es"
}

# --- FONCTIONS ALGORITHMIQUES ---

def check_audience_lang(comments, target_code):
    """Analyse les commentaires pour confirmer la langue de l'audience"""
    if not target_code or not comments:
        return True
    
    hits = 0
    # On extrait le texte des commentaires valides
    sample = [c.get('text') for c in comments if c.get('text') and len(c.get('text')) > 5][:10]
    
    if not sample:
        return False

    for text in sample:
        try:
            if detect(text) == target_code:
                hits += 1
        except:
            continue
    
    # Seuil de validation : 30% des commentaires dans la langue cible
    return hits >= (len(sample) * 0.3)

def get_deep_info(url):
    """Récupère les métadonnées et les commentaires d'une vidéo spécifique"""
    opts = {
        'quiet': True,
        'skip_download': True,
        'getcomments': True,
        'max_comments': 10,
        'socket_timeout': 10,
        'ignoreerrors': True,
        'no_warnings': True
    }
    with YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)

# --- APPLICATION PRINCIPALE ---

st.title("🚀 YouTube Sniper V13")
st.markdown("---")

with st.sidebar:
    st.header("⚙️ Configuration")
    kw_input = st.text_area("Mots-clés (un par ligne)", "ICE immigration\nTrump immigration")
    target_lang = st.selectbox("Langue de l'audience", list(LANG_MAP.keys()))
    min_views = st.number_input("Vues minimum", value=50000, step=10000)
    search_limit = st.slider("Vidéos à scanner par mot-clé", 5, 50, 15)
    threads = st.slider("Puissance de calcul (Threads)", 1, 20, 10)
    
    st.divider()
    run_btn = st.button("LANCER L'ANALYSE", type="primary", use_container_width=True)

if run_btn:
    keywords = [k.strip() for k in kw_input.split('\n') if k.strip()]
    target_code = LANG_MAP[target_lang]
    final_results = []

    if not keywords:
        st.error("Veuillez entrer au moins un mot-clé.")
    else:
        with st.status("Chasse aux pépites en cours...", expanded=True) as status:
            # ÉTAPE 1 : Collecte rapide des URLs
            video_urls = []
            search_opts = {'quiet': True, 'extract_flat': True}
            
            with YoutubeDL(search_opts) as ydl:
                for kw in keywords:
                    status.write(f"🔎 Recherche : {kw}")
                    try:
                        search_res = ydl.extract_info(f"ytsearch{search_limit}:{kw}", download=False)
                        if 'entries' in search_res:
                            video_urls.extend([f"https://www.youtube.com/watch?v={e['id']}" for e in search_res['entries'] if e])
                    except:
                        continue
            
            # Nettoyage des doublons
            video_urls = list(set(video_urls))
            status.write(f"🧠 Analyse profonde de {len(video_urls)} vidéos...")

            # ÉTAPE 2 : Analyse multi-threadée (Commentaires + Ratio)
            with ThreadPoolExecutor(max_workers=threads) as executor:
                futures = [executor.submit(get_deep_info, url) for url in video_urls]
                
                for f in as_completed(futures):
                    v = f.result()
                    if v and v.get('view_count', 0) >= min_views:
                        # On valide la langue via les commentaires
                        if check_audience_lang(v.get('comments'), target_code):
                            # Calcul du ratio de viralité
                            subs = v.get('channel_follower_count') or 1
                            v['_ratio'] = v['view_count'] / subs
                            final_results.append(v)

        # --- AFFICHAGE DES RÉSULTATS ---
        # Tri par ratio de viralité décroissant
        final_results = sorted(final_results, key=lambda x: x.get('_ratio', 0), reverse=True)

        if not final_results:
            st.warning("Aucune vidéo ne correspond à vos filtres. Essayez de baisser le nombre de vues minimum.")
        else:
            st.success(f"Trouvé {len(final_results)} vidéos virales !")
            
            for vid in final_results:
                with st.container(border=True):
                    col1, col2 = st.columns([1, 3])
                    with col1:
                        st.image(vid.get('thumbnail'), use_container_width=True)
                    with col2:
                        st.subheader(f"{vid.get('_ratio', 0):.1f}x | {vid.get('title')}")
                        st.write(f"👤 **Chaîne :** {vid.get('uploader')}")
                        st.write(f"👁️ **Vues :** {vid.get('view_count', 0):,} | 👥 **Abos :** {vid.get('channel_follower_count', 0):,}")
                        st.link_button("▶️ Voir la vidéo", vid.get('webpage_url'))
                        
                        with st.expander("Voir les meilleurs commentaires"):
                            for c in vid.get('comments', [])[:5]:
                                st.caption(f"💬 {c.get('text')[:300]}")

else:
    st.info("Configurez vos mots-clés dans la barre latérale et cliquez sur Lancer.")
