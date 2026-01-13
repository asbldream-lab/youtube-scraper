import streamlit as st
from yt_dlp import YoutubeDL
import json
from datetime import datetime, timedelta
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import re

st.set_page_config(page_title="YouTube Scraper Pro", layout="wide")
st.title("🚀 YouTube Keyword Research Tool PRO")

# Initialisation session state (RESTAURÉ)
if 'search_history' not in st.session_state:
    st.session_state.search_history = []

# ==========================================
# ✅ LOGIQUE DE FILTRAGE LANGUE (SÉCURISÉE)
# ==========================================
def check_lang_match(info, target_lang):
    if target_lang == "Auto (toutes langues)": return True
    
    title = (info.get('title') or "").lower()
    desc = (info.get('description') or "").lower()
    full_text = title + " " + desc[:500]
    
    # Dictionnaires de survie
    rules = {
        "Français": {"chars": "éàèçôû", "words": [" le ", " la ", " les ", " est ", " avec "], "code": "fr"},
        "Espagnol": {"chars": "ñáéíóú¡¿", "words": [" el ", " los ", " con ", " para ", " por "], "code": "es"},
        "Anglais": {"chars": "", "words": [" the ", " and ", " with ", " from "], "code": "en"}
    }
    
    r = rules.get(target_lang)
    # 1. Vérification YouTube Meta
    yt_lang = (info.get('language') or "").lower()
    if yt_lang.startswith(r['code']): return True
    
    # 2. Vérification Caractères spéciaux
    if r['chars'] and any(c in full_text for c in r['chars']): return True
    
    # 3. Vérification Mots outils
    if any(w in full_text for w in r['words']): return True
    
    # 4. Anti-Anglais (Si on veut FR ou ES mais qu'on voit "the" ou "how to")
    if target_lang in ["Français", "Espagnol"]:
        if any(w in title for w in ["the", "how to", "unboxing", "review"]): return False
        
    return False

# ============ SIDEBAR ============
st.sidebar.header("⚙️ Paramètres")

keywords_input = st.sidebar.text_area("🔍 Mots-clés (un par ligne):", placeholder="guerre irak\nstarlink")
keywords_list = [k.strip() for k in keywords_input.split('\n') if k.strip()]

language = st.sidebar.selectbox("🌍 Langue:", ["Auto (toutes langues)", "Français", "Anglais", "Espagnol"])

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

# Ajout des filtres de durée demandés
st.sidebar.write("### ⏱️ Durée minimum")
min_duration_opt = st.sidebar.radio("Choisir :", ["Toutes", "Minimum 2 min", "Minimum 5 min"])

st.sidebar.write("### 📈 Ratio Engagement")
use_engagement = st.sidebar.checkbox("Filtrer par engagement")
min_engagement = st.sidebar.slider("Like/Vue minimum (%)", 0.0, 10.0, 1.0) if use_engagement else 0.0

st.sidebar.write("### 📅 Date de publication")
date_filter = st.sidebar.selectbox("Période:", ["Toutes", "7 derniers jours", "30 derniers jours", "6 derniers mois", "1 an"])

# ============ BOUTON RECHERCHE ============
if st.sidebar.button("🚀 Lancer", use_container_width=True):
    if not keywords_list:
        st.error("❌ Au moins un mot-clé requis!")
    elif not selected_views:
        st.error("❌ Sélectionne une gamme de vues!")
    else:
        progress_bar = st.progress(0)
        status = st.empty()
        
        # Calcul date limite
        date_limit = None
        if date_filter != "Toutes":
            days = {"7 derniers jours": 7, "30 derniers jours": 30, "6 derniers mois": 180, "1 an": 365}
            date_limit = datetime.now() - timedelta(days=days[date_filter])
        
        all_videos_filtered = []
        all_comments_list = []
        
        try:
            for kw in keywords_list:
                status.text(f"🔍 Recherche: {kw}")
                # Config recherche rapide
                with YoutubeDL({'quiet': True, 'extract_flat': True}) as ydl:
                    search_results = ydl.extract_info(f"ytsearch40:{kw}", download=False).get('entries', [])

                def fetch_video_details(v):
                    with YoutubeDL({'quiet': True, 'getcomments': True, 'writesubtitles': True, 'skip_download': True}) as ydl_full:
                        return ydl_full.extract_info(f"https://www.youtube.com/watch?v={v['id']}", download=False)

                with ThreadPoolExecutor(max_workers=10) as executor:
                    full_infos = list(executor.map(fetch_video_details, search_results))

                for info in [f for f in full_infos if f]:
                    # 1. FILTRE LANGUE (CORRIGÉ)
                    if not check_lang_match(info, language): continue
                    
                    # 2. FILTRE DURÉE (NOUVEAU)
                    dur = info.get('duration', 0)
                    if min_duration_opt == "Minimum 2 min" and dur < 120: continue
                    if min_duration_opt == "Minimum 5 min" and dur < 300: continue

                    # 3. FILTRE VUES (RESTAURÉ)
                    views = info.get('view_count', 0) or 0
                    if not any(mn <= views <= mx for mn, mx in selected_views): continue
                    
                    # 4. FILTRE DATE
                    if date_limit:
                        up_date = datetime.strptime(info.get('upload_date', '19000101'), '%Y%m%d')
                        if up_date < date_limit: continue

                    info['search_keyword'] = kw
                    all_videos_filtered.append(info)

            # === AFFICHAGE COLONNES (RESTAURÉ) ===
            if all_videos_filtered:
                st.success(f"✅ {len(all_videos_filtered)} vidéos trouvées.")
                
                # Compilation commentaires pour historique & prompt
                for v in all_videos_filtered:
                    for c in v.get('comments', [])[:20]:
                        all_comments_list.append({
                            'video': v['title'], 'video_id': v['id'], 'keyword': v['search_keyword'],
                            'author': c.get('author'), 'text': c.get('text'), 'likes': c.get('like_count', 0)
                        })

                left_col, right_col = st.columns([1, 2])
                
                with left_col:
                    st.header("📋 Copie en bas")
                    prompt = "Rôle : Tu es un expert en analyse de données sociales... [Prompt Complet original]"
                    # Ici tu peux remettre ton texte de prompt exact
                    st.text_area("Copie pour ChatGPT:", value=prompt, height=400)

                with right_col:
                    st.header(f"📹 Vidéos")
                    for idx, v in enumerate(all_videos_filtered, 1):
                        subs = v.get('channel_follower_count', 0) or 1
                        v_views = v.get('view_count', 0)
                        stars = "⭐⭐⭐" if v_views > subs else "⭐"
                        with st.expander(f"Vidéo {idx}: {v['title'][:50]}... | 👁️ {v_views:,} | {stars}"):
                            st.image(v.get('thumbnail'), width=200)
                            st.write(f"**Hook:** {v.get('hook', 'N/A')}")
                            st.write(f"[Lien]({v['webpage_url']})")

            # SAUVEGARDE HISTORIQUE (RESTAURÉ)
            st.session_state.search_history.append({'date': datetime.now().strftime('%d/%m %H:%M'), 'kw': keywords_list, 'found': len(all_videos_filtered)})
            
            progress_bar.progress(100)
        except Exception as e:
            st.error(f"Erreur: {e}")

# ============ HISTORIQUE (RESTAURÉ) ============
if st.session_state.search_history:
    with st.expander("📚 Historique"):
        for h in reversed(st.session_state.search_history[-5:]):
            st.write(f"{h['date']} - {h['kw']} ({h['found']} vidéos)")
