import streamlit as st
from yt_dlp import YoutubeDL
import json
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import time

# ==========================================
# 📦 INSTALLATION SILENCIEUSE DES DÉPENDANCES
# ==========================================
try:
    from langdetect import detect, LangDetectException
except ImportError:
    import subprocess
    # Installation au cas où
    subprocess.check_call(['pip', 'install', 'langdetect'])
    from langdetect import detect, LangDetectException

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
st.set_page_config(page_title="YouTube Scraper Pro", layout="wide")
st.title("🚀 YouTube Keyword Research Tool PRO")

if 'search_history' not in st.session_state:
    st.session_state.search_history = []

# Dictionnaire de stratégie pour forcer YouTube à donner la bonne langue
LANGUAGE_RULES = {
    "Auto (toutes langues)": {"code": None, "helpers": []},
    "Français": {"code": "fr", "helpers": ["le", "la", "et", "est", "pour", "avec"]},
    "Anglais": {"code": "en", "helpers": ["the", "and", "is", "to", "with", "for"]},
    "Espagnol": {"code": "es", "helpers": ["el", "la", "y", "en", "es", "por", "con"]},
}

# ==========================================
# 🧠 MOTEUR INTELLIGENT
# ==========================================
def validate_language(text, target_lang_name):
    """
    Vérifie si le texte est dans la langue cible.
    Retourne True/False.
    """
    if target_lang_name == "Auto (toutes langues)":
        return True
    
    if not text or len(text) < 5:
        return False

    target_code = LANGUAGE_RULES[target_lang_name]["code"]
    
    # 1. Essai avec l'IA (Langdetect)
    try:
        if detect(text) == target_code:
            return True
    except:
        pass

    # 2. Essai manuel (comptage de mots clés)
    # Si l'IA échoue, on regarde si on trouve 2 mots très courants (ex: "el", "y")
    text_lower = text.lower()
    helpers = LANGUAGE_RULES[target_lang_name]["helpers"]
    count = sum(1 for h in helpers if f" {h} " in text_lower)
    
    if count >= 2:
        return True
        
    return False

# ============ SIDEBAR (PARAMÈTRES) ============
st.sidebar.header("1. Recherche")
keywords_input = st.sidebar.text_area("Mots-clés (un par ligne)", height=100, placeholder="starlink\nias")
keywords_list = [k.strip() for k in keywords_input.split('\n') if k.strip()]

language = st.sidebar.selectbox("Langue cible", list(LANGUAGE_RULES.keys()))

st.sidebar.header("2. Filtres")
min_views = st.sidebar.number_input("Vues Minimum", value=5000, step=1000)
min_duration = st.sidebar.selectbox("Durée Minimum", ["Toutes", "2 min", "5 min"])

date_options = ["Toutes", "7 derniers jours", "30 derniers jours", "6 derniers mois", "1 an"]
date_choice = st.sidebar.selectbox("Période", date_options)

# ============ COEUR DU PROGRAMME ============
if st.sidebar.button("🚀 LANCER L'ANALYSE", type="primary", use_container_width=True):
    if not keywords_list:
        st.error("❌ Il faut au moins un mot-clé !")
    else:
        # Initialisation
        status_text = st.empty()
        progress_bar = st.progress(0)
        
        all_videos_found = []
        
        # Calcul de la date limite
        date_limit = None
        if date_choice != "Toutes":
            days_map = {"7 derniers jours": 7, "30 derniers jours": 30, "6 derniers mois": 180, "1 an": 365}
            date_limit = datetime.now() - timedelta(days=days_map[date_choice])

        # BOUCLE SUR LES MOTS-CLÉS
        for idx, kw in enumerate(keywords_list):
            status_text.markdown(f"### 🔍 Analyse de : **{kw}**...")
            
            # 1. CONSTRUCTION DE LA REQUÊTE INTELLIGENTE
            helpers = LANGUAGE_RULES[language]["helpers"]
            if helpers:
                query_helpers = " | ".join([f'"{h}"' for h in helpers[:3]]) 
                search_query = f'{kw} ({query_helpers})'
            else:
                search_query = kw

            # 2. RECHERCHE RAPIDE
            ydl_opts_search = {
                'quiet': True,
                'extract_flat': True,
                'ignoreerrors': True,
            }

            entries = []
            with YoutubeDL(ydl_opts_search) as ydl:
                try:
                    res = ydl.extract_info(f"ytsearch40:{search_query}", download=False)
                    
                    if res is None: 
                        st.warning(f"⚠️ YouTube n'a pas répondu pour '{kw}'.")
                        continue
                        
                    entries = res.get('entries', [])
                    if not entries:
                        st.warning(f"⚠️ Aucune vidéo trouvée pour '{kw}'.")
                        continue
                        
                except Exception as e:
                    st.error(f"Erreur de connexion pour '{kw}': {e}")
                    continue

            # 3. ANALYSE DÉTAILLÉE (PARALLÈLE)
            status_text.text(f"⚡ Filtrage de {len(entries)} vidéos (Mode Turbo)...")
            
            def process_video(entry):
                if not entry: return None

                # Filtre 1 : Vues
                v_count = entry.get('view_count')
                if v_count is not None and v_count < min_views:
                    return None

                # Filtre 2 : Langue sur le TITRE
                title = entry.get('title', '')
                if not validate_language(title, language):
                    pass 

                # TÉLÉCHARGEMENT DES DÉTAILS
                url = f"https://www.youtube.com/watch?v={entry['id']}"
                opts_full = {
                    'quiet': True,
                    'getcomments': True,
                    'max_comments': 40,
                    'skip_download': True,
                    'ignoreerrors': True,
                    'socket_timeout': 10 # <--- VITESSE : Si ça traine > 10s, on coupe
                }
                
                try:
                    with YoutubeDL(opts_full) as ydl_full:
                        info = ydl_full.extract_info(url, download=False)
                        
                        # Filtre 3 : Date
                        if date_limit:
                            ud = info.get('upload_date')
                            if ud and datetime.strptime(ud, '%Y%m%d') < date_limit:
                                return None

                        # Filtre 4 : Durée
                        dur = info.get('duration', 0)
                        if min_duration == "2 min" and dur < 120: return None
                        if min_duration == "5 min" and dur < 300: return None

                        # Filtre 5 : LANGUE FINAL
                        full_text = f"{info['title']} {info['description'][:500]}"
                        if not validate_language(full_text, language):
                            return None
                            
                        return info
                except:
                    return None

            # Lancement des threads
            # <--- VITESSE : 20 OUVRIERS AU LIEU DE 10
            with ThreadPoolExecutor(max_workers=20) as executor:
                futures = [executor.submit(process_video, e) for e in entries]
                for f in as_completed(futures):
                    res = f.result()
                    if res:
                        res['keyword_source'] = kw
                        all_videos_found.append(res)
            
            progress_bar.progress((idx + 1) / len(keywords_list))

        # ============ AFFICHAGE DES RÉSULTATS ============
        status_text.empty()
        
        if all_videos_found:
            st.success(f"✅ {len(all_videos_found)} vidéos qualifiées trouvées !")
            
            col1, col2 = st.columns([1, 2])
            
            # COLONNE GAUCHE : PROMPT
            with col1:
                st.subheader("📋 Copier pour l'IA")
                prompt = f"Je veux analyser ces vidéos ({language}) sur le sujet : {', '.join(keywords_list)}.\n"
                prompt += "Trouve-moi les angles les plus performants et les avis des spectateurs.\n\n"
                
                for v in all_videos_found:
                    prompt += f"=== VIDÉO : {v['title']} ===\n"
                    prompt += f"Lien: {v['webpage_url']}\n"
                    prompt += f"Vues: {v.get('view_count', 0):,}\n"
                    desc = v.get('description', '').replace('\n', ' ')[:200]
                    prompt += f"Desc: {desc}...\n"
                    
                    comms = v.get('comments', [])
                    if comms:
                        prompt += "Avis spectateurs:\n"
                        for c in comms[:5]:
                            txt = c.get('text', '').replace('\n', ' ')
                            prompt += f"- {txt}\n"
                    prompt += "\n"
                
                st.text_area("Prompt généré :", value=prompt, height=600)
            
            # COLONNE DROITE : VISUELS
            with col2:
                st.subheader("📹 Aperçu des vidéos")
                for v in all_videos_found:
                    
                    # --- CALCUL DES ÉTOILES ---
                    subs = v.get('channel_follower_count') or 1
                    views = v.get('view_count', 0)
                    ratio = views / subs
                    
                    if ratio > 2:
                        stars = "⭐⭐⭐" # Banger
                    elif ratio > 1:
                        stars = "⭐⭐"   # Bonne perf
                    else:
                        stars = "⭐"     # Normal
                    
                    # AFFICHAGE
                    with st.expander(f"{stars} | {views:,} vues | {v['title']}"):
                        c_img, c_txt = st.columns([1, 2])
                        with c_img:
                            st.image(v.get('thumbnail'), use_container_width=True)
                        with c_txt:
                            st.write(f"**Chaîne:** {v.get('uploader')}")
                            st.write(f"**Abonnés:** {subs:,}")
                            st.write(f"**Ratio:** {ratio:.2f}x (Vues/Abonnés)")
                            st.write(f"[Voir sur YouTube]({v['webpage_url']})")
        else:
            st.warning("Aucune vidéo ne correspond à tes critères stricts. Essaie d'élargir la date ou de baisser les vues minimum.")
