import streamlit as st
from yt_dlp import YoutubeDL
import json
from datetime import datetime, timedelta
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
from langdetect import detect, LangDetectException

# ==========================================
# ✅ CONFIGURATION & SESSION STATE
# ==========================================
st.set_page_config(page_title="YouTube Scraper Pro", layout="wide")
st.title("🚀 YouTube Keyword Research Tool PRO")

if 'search_history' not in st.session_state:
    st.session_state.search_history = []

# ==========================================
# ✅ NOUVEAU MOTEUR DE LANGUE (AVEC LANGDETECT)
# ==========================================
def is_valid_language(info, target_lang_ui):
    """
    Détermine si une vidéo correspond à la langue cible via analyse NLP.
    """
    if target_lang_ui == "Auto (toutes langues)":
        return True
    
    # Mapping UI vers Code ISO
    lang_map = {
        "Français": "fr",
        "Espagnol": "es",
        "Anglais": "en"
    }
    target_iso = lang_map.get(target_lang_ui)
    
    # 1. Récupération des textes
    title = (info.get('title') or "")
    desc = (info.get('description') or "")
    # On prend un échantillon suffisant pour la détection
    full_text = f"{title} {title} {desc[:500]}" 

    # 2. Vérification Meta YouTube (Si disponible et fiable)
    yt_lang = (info.get('language') or "").lower()
    if yt_lang.startswith(target_iso):
        return True

    # 3. ANALYSE NLP VIA LANGDETECT (Le coeur de la correction)
    try:
        # On essaie de détecter la langue du texte combiné
        detected_lang = detect(full_text)
        if detected_lang == target_iso:
            return True
    except LangDetectException:
        pass # Si le texte est trop court ou illisible (ex: emojis)

    # 4. RATTRAPAGE MANUEL (Fallback pour les textes courts)
    # Si langdetect échoue ou est incertain, on utilise tes règles manuelles strictes
    full_text_lower = full_text.lower()
    
    rules = {
        "Français": {"words": [" le ", " la ", " et ", " du ", " pour ", " avec "], "reject": [" the ", " how to "]},
        "Espagnol": {"words": [" el ", " la ", " los ", " y ", " en ", " con ", " para "], "reject": [" the ", " review "]},
        "Anglais":  {"words": [" the ", " and ", " to ", " of ", " with "], "reject": []}
    }
    
    r = rules.get(target_lang_ui)
    
    # Vérification des mots interdits (Anti-fuite)
    # Si on cherche Espagnol mais qu'il y a "how to" -> Poubelle immédiate
    if any(bad in full_text_lower for bad in r['reject']):
        return False

    # Vérification des mots obligatoires
    score = sum(1 for w in r['words'] if w in full_text_lower)
    
    # Il faut au moins 2 indicateurs forts pour valider si langdetect a échoué
    if score >= 2:
        return True

    return False

# ============ SIDEBAR ============
st.sidebar.header("⚙️ Paramètres")

keywords_input = st.sidebar.text_area(
    "🔍 Mots-clés (un par ligne):",
    placeholder="guerre irak\nstarlink",
    help="Entre plusieurs mots-clés, un par ligne"
)
keywords_list = [k.strip() for k in keywords_input.split('\n') if k.strip()]

language = st.sidebar.selectbox(
    "🌍 Langue:",
    ["Auto (toutes langues)", "Français", "Anglais", "Espagnol"]
)

# VUES
st.sidebar.write("### 👁️ Vues minimum")
col1, col2, col3, col4 = st.sidebar.columns(4)
selected_views = []
with col1:
    if st.sidebar.checkbox("10K-50K"): selected_views.append((10000, 50000))
with col2:
    if st.sidebar.checkbox("50K-100K"): selected_views.append((50000, 100000))
with col3:
    if st.sidebar.checkbox("100K+"): selected_views.append((100000, 1000000))
with col4:
    if st.sidebar.checkbox("1M+"): selected_views.append((1000000, float('inf')))

# DURÉE
st.sidebar.write("### ⏱️ Durée de la vidéo")
min_duration = st.sidebar.radio("Minimum :", ["Toutes", "Minimum 2 min", "Minimum 5 min"])

# DATE
st.sidebar.write("### 📅 Période")
date_filter = st.sidebar.selectbox(
    "Période:",
    ["Toutes", "7 derniers jours", "30 derniers jours", "6 derniers mois", "1 an"]
)

# ============ BOUTON RECHERCHE ============
if st.sidebar.button("🚀 Lancer l'analyse", use_container_width=True):
    if not keywords_list or not selected_views:
        st.error("❌ Mots-clés et gammes de vues requis !")
    else:
        progress_bar = st.progress(0)
        status = st.empty()
        
        # Calcul Date
        date_limit = None
        if date_filter != "Toutes":
            days = {"7 derniers jours": 7, "30 derniers jours": 30, "6 derniers mois": 180, "1 an": 365}
            date_limit = datetime.now() - timedelta(days=days[date_filter])

        all_videos_filtered = []

        try:
            total_kw = len(keywords_list)
            for kw_idx, kw in enumerate(keywords_list):
                status.markdown(f"### 🔍 Recherche : **{kw}** ({kw_idx+1}/{total_kw})")
                
                # ASTUCE : Si une langue est sélectionnée, on ajoute un "biais" à la recherche
                # Cela aide YouTube à nous donner les bonnes vidéos AVANT le filtrage
                search_query = kw
                if language == "Espagnol":
                    search_query = f"{kw} (la | el | y | de)" # Astuce boolean search
                elif language == "Français":
                    search_query = f"{kw} (le | la | et | de)"

                # Recherche initiale (On demande plus de résultats car on va beaucoup filtrer)
                # On augmente ytsearch40 -> ytsearch60 pour compenser le filtrage de langue
                with YoutubeDL({'quiet': True, 'extract_flat': True}) as ydl:
                    search_res = ydl.extract_info(f"ytsearch60:{search_query}", download=False).get('entries', [])

                # Fonction de récupération (Isolée pour les threads)
                def fetch_full(vid):
                    if not vid: return None
                    opts = {
                        'quiet': True, 
                        'getcomments': True, # Important pour l'analyse future
                        'writesubtitles': False, # Désactivé pour vitesse, sauf si critique
                        'skip_download': True, 
                        'ignoreerrors': True,
                        'socket_timeout': 10
                    }
                    try:
                        with YoutubeDL(opts) as ydl_full:
                            return ydl_full.extract_info(f"https://www.youtube.com/watch?v={vid['id']}", download=False)
                    except:
                        return None

                # Téléchargement parallèle
                status.text(f"📥 Récupération des données pour {len(search_res)} vidéos...")
                full_infos = []
                with ThreadPoolExecutor(max_workers=10) as executor:
                    futures = [executor.submit(fetch_full, vid) for vid in search_res]
                    for future in as_completed(futures):
                        res = future.result()
                        if res:
                            full_infos.append(res)

                # FILTRAGE FINAL
                count_for_kw = 0
                for info in full_infos:
                    # 1. FILTRE LANGUE (Prioritaire)
                    if not is_valid_language(info, language): 
                        continue
                    
                    # 2. FILTRE DURÉE
                    v_dur = info.get('duration', 0) or 0
                    if min_duration == "Minimum 2 min" and v_dur < 120: continue
                    if min_duration == "Minimum 5 min" and v_dur < 300: continue

                    # 3. FILTRE VUES
                    v_views = info.get('view_count', 0) or 0
                    if not any(mn <= v_views <= mx for mn, mx in selected_views): continue

                    # 4. FILTRE DATE
                    if date_limit:
                        upload_date = info.get('upload_date')
                        if upload_date:
                            v_date = datetime.strptime(upload_date, '%Y%m%d')
                            if v_date < date_limit: continue

                    info['search_keyword'] = kw
                    all_videos_filtered.append(info)
                    count_for_kw += 1

                progress_bar.progress((kw_idx + 1) / total_kw)

            # === AFFICHAGE RÉSULTATS ===
            status.empty()
            if all_videos_filtered:
                st.success(f"✅ {len(all_videos_filtered)} vidéos trouvées parfaitement triées !")
                
                left_col, right_col = st.columns([1, 2])

                # GAUCHE : LE PROMPT
                with left_col:
                    st.subheader("📋 Données pour Analyse")
                    
                    data_blob = f"Objectif : Analyser ces vidéos sur le thème : {', '.join(keywords_list)}\n"
                    for v in all_videos_filtered:
                        data_blob += f"\n=== VIDÉO: {v['title']} ===\n"
                        data_blob += f"Lien: {v.get('webpage_url')}\n"
                        # Ajout de la description tronquée pour aider l'IA
                        desc_snippet = (v.get('description') or "")[:200].replace('\n', ' ')
                        data_blob += f"Description: {desc_snippet}...\n"
                        
                        # Commentaires
                        comments = v.get('comments', [])
                        if comments:
                            data_blob += "Commentaires pertinents:\n"
                            # On prend les top 10 commentaires triés par likes (si dispo)
                            # Note: yt-dlp ne trie pas toujours par likes par défaut, c'est souvent par date
                            for c in comments[:10]:
                                txt = c.get('text', '').replace('\n', ' ')
                                likes = c.get('like_count', 0)
                                data_blob += f"- [{likes} likes] {txt}\n"
                    
                    st.text_area("Copier ceci dans ChatGPT/Claude :", value=data_blob, height=600)

                # DROITE : LES VIDÉOS
                with right_col:
                    st.subheader("📹 Résultats Vidéos")
                    for idx, v in enumerate(all_videos_filtered, 1):
                        subs = v.get('channel_follower_count', 0) or 1
                        views = v.get('view_count', 0)
                        ratio = views / subs if subs > 0 else 0
                        
                        stars = "🔥" if ratio > 1 else "😐"
                        
                        with st.expander(f"#{idx} {stars} | {views:,} vues | {v['title']}"):
                            c1, c2 = st.columns([1, 2])
                            with c1:
                                st.image(v.get('thumbnail'), use_container_width=True)
                            with c2:
                                st.write(f"**Chaîne :** {v.get('uploader')}")
                                st.write(f"**Date :** {v.get('upload_date')}")
                                st.markdown(f"[Voir la vidéo]({v.get('webpage_url')})")

            else:
                st.warning("Aucune vidéo trouvée avec ces filtres stricts. Essaie d'élargir la période ou les vues.")

            # SAUVEGARDE HISTORIQUE
            st.session_state.search_history.append({
                'date': datetime.now().strftime('%d/%m %H:%M'),
                'kw': keywords_list,
                'found': len(all_videos_filtered),
                'lang': language
            })
            
            progress_bar.progress(100)

        except Exception as e:
            st.error(f"Une erreur est survenue : {e}")
            st.exception(e) # Affiche la trace complète pour le debug

# ============ HISTORIQUE ============
if st.session_state.search_history:
    st.divider()
    with st.expander("📚 Historique des recherches"):
        for h in reversed(st.session_state.search_history[-5:]):
            st.write(f"📅 {h['date']} | 🌍 {h.get('lang', '?')} | 🔍 {h['kw']} | 📹 {h['found']} vidéos")
