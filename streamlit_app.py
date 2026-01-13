import streamlit as st
from yt_dlp import YoutubeDL
import json
from datetime import datetime, timedelta
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
from collections import Counter

# Configuration
st.set_page_config(page_title="YouTube Scraper Pro", layout="wide")
st.title("🚀 YouTube Keyword Research Tool PRO")

# ==========================================
# ✅ MOTEUR DE LANGUE PAR EXCLUSION (STRICT)
# ==========================================

# Mots qui indiquent à 100% qu'une vidéo est en ANGLAIS (à bannir si ES ou FR choisi)
EN_FORBIDDEN = {
    "the", "and", "how", "with", "from", "for", "about", "today", "is", "was", 
    "bought", "shocked", "unboxing", "review", "vs", "setup", "tutorial", "official"
}

# Règles de preuve par langue
LANG_RULES = {
    "es": {
        "proof_words": {"el", "los", "las", "un", "una", "por", "para", "con", "pero", "su", "sus", "son", "es", "y", "esta", "donde"},
        "chars": set("ñáéíóúü¡¿"),
        "region": "ES"
    },
    "fr": {
        "proof_words": {"le", "la", "les", "un", "une", "des", "du", "de", "et", "ou", "est", "dans", "pour", "par", "avec", "sur", "plus"},
        "chars": set("àâäçéèêëîïôöùûüÿœæ"),
        "region": "FR"
    },
    "en": {
        "proof_words": {"the", "and", "is", "are", "was", "were", "with", "about", "from", "for", "how"},
        "chars": set(),
        "region": "US"
    }
}

def _clean_text(s: str) -> str:
    if not s: return ""
    s = s.lower()
    s = re.sub(r"[\W_]+", " ", s, flags=re.UNICODE)
    return s.strip()

def is_valid_language(info, target_code):
    """Vérifie si la vidéo correspond REELLEMENT à la langue choisie."""
    if target_code == "auto": return True, "Auto"
    
    title = (info.get("title") or "").lower()
    desc = (info.get("description") or "").lower()
    full_text = title + " " + desc[:500]
    tokens = set(_clean_text(full_text).split())

    # 1. ANTI-ANGLAIS : Si on cherche ES ou FR mais qu'il y a du 'poison' anglais
    if target_code in ["es", "fr"]:
        if any(word in tokens for word in EN_FORBIDDEN):
            return False, "Rejet : Anglais détecté"

    # 2. PREUVE PAR CARACTÈRES (Infaillible pour ES/FR)
    if any(char in full_text for char in LANG_RULES[target_code]["chars"]):
        return True, "Preuve : Caractères spécifiques"

    # 3. PREUVE PAR SOUS-TITRES
    autos = info.get("automatic_captions") or {}
    subs = info.get("subtitles") or {}
    if target_code in autos or target_code in subs:
        return True, "Preuve : Sous-titres présents"

    # 4. PREUVE PAR MOTS OUTILS
    if any(word in tokens for word in LANG_RULES[target_code]["proof_words"]):
        return True, "Preuve : Mots outils détectés"

    # 5. SI AUCUNE PREUVE ET TEXTE COURT -> On rejette pour éviter le hors-sujet
    if len(tokens) > 5:
        return False, "Rejet : Aucune preuve de langue"
    
    return True, "Gardé (Texte trop court)"

# ============ SIDEBAR ============
st.sidebar.header("⚙️ Paramètres")

keywords_input = st.sidebar.text_area("🔍 Mots-clés (un par ligne) :", placeholder="Starlink\nGuerra")
keywords_list = [k.strip() for k in keywords_input.split('\n') if k.strip()]

language_choice = st.sidebar.selectbox("🌍 Langue cible :", ["Espagnol", "Français", "Anglais", "Auto (toutes langues)"])
lang_map = {"Espagnol": "es", "Français": "fr", "Anglais": "en", "Auto (toutes langues)": "auto"}

st.sidebar.write("### 👁️ Vues minimum")
selected_views = []
if st.sidebar.checkbox("100K+", value=True): selected_views.append((100000, 1000000))
if st.sidebar.checkbox("1M+"): selected_views.append((1000000, float('inf')))

st.sidebar.write("### ⏱️ Durée de la vidéo")
min_duration = st.sidebar.radio("Durée minimum :", ["Toutes", "Minimum 2 min", "Minimum 5 min"])

st.sidebar.write("### 📈 Engagement")
use_engagement = st.sidebar.checkbox("Filtrer Engagement")
min_eng = st.sidebar.slider("% Likes/Vues", 0.0, 10.0, 1.0) if use_engagement else 0.0

# ============ LOGIQUE DE RECHERCHE ============
if st.sidebar.button("🚀 LANCER L'ANALYSE EXPERTE", use_container_width=True):
    if not keywords_list:
        st.error("❌ Mots-clés requis !")
    else:
        target_code = lang_map[language_choice]
        
        # Options YDL avec forçage de région
        region = LANG_RULES.get(target_code, {}).get("region", "US")
        YDL_OPTS = {
            'quiet': True, 'ignoreerrors': True, 'skip_download': True,
            'writesubtitles': True, 'writeautomaticsub': True, 'getcomments': True,
            'subtitleslangs': ['fr', 'en', 'es'],
            'extractor_args': {'youtube': {'max_comments': ['30'], 'lang': [target_code], 'region': [region]}}
        }

        progress_bar = st.progress(0)
        status = st.empty()
        all_videos_filtered = []

        try:
            for kw in keywords_list:
                status.text(f"🔍 Recherche YouTube : {kw}")
                with YoutubeDL({'quiet': True, 'extract_flat': True}) as ydl:
                    # On cherche 50 vidéos pour compenser le filtrage strict
                    search_res = ydl.extract_info(f"ytsearch50:{kw}", download=False)
                    entries = search_res.get('entries', [])

                def fetch_parallel(vid):
                    try:
                        return YoutubeDL(YDL_OPTS).extract_info(f"https://www.youtube.com/watch?v={vid['id']}", download=False)
                    except: return None

                with ThreadPoolExecutor(max_workers=12) as executor:
                    results = list(executor.map(fetch_parallel, entries))
                
                for v in [r for r in results if r]:
                    # 1. FILTRE LANGUE STRICT
                    valid, reason = is_valid_language(v, target_code)
                    if not valid: continue

                    # 2. FILTRE DURÉE
                    v_duration = v.get('duration', 0)
                    if min_duration == "Minimum 2 min" and v_duration < 120: continue
                    if min_duration == "Minimum 5 min" and v_duration < 300: continue

                    # 3. FILTRE VUES
                    v_views = v.get('view_count', 0) or 0
                    if not any(m <= v_views <= x for m, x in selected_views): continue
                    
                    # 4. FILTRE ENGAGEMENT
                    if use_engagement:
                        ratio = (v.get('like_count', 0) or 0) / v_views * 100 if v_views > 0 else 0
                        if ratio < min_eng: continue

                    v['lang_reason'] = reason
                    all_videos_filtered.append(v)

            # === AFFICHAGE DES RÉSULTATS ===
            if not all_videos_filtered:
                st.warning("Aucune vidéo trouvée avec ces filtres stricts. Essayez d'élargir les vues.")
            else:
                st.success(f"✅ {len(all_videos_filtered)} vidéos filtrées avec succès.")
                
                l_col, r_col = st.columns([1, 2])

                with l_col:
                    st.header("📋 Prompt Expert ChatGPT")
                    prompt_base = """Rôle : Tu es un expert en analyse stratégique de contenu. Analyse ces données pour en extraire :
1. Angle stratégique (Attentes/Frustrations).
2. Top 5 idées récurrentes dans les commentaires.
3. Sujets périphériques & Opportunités.
4. Éléments indispensables pour ma future vidéo.
5. Analyse des Hooks (Accroches) et proposition de 3 nouveaux hooks originaux.

Données à analyser :
"""
                    data_blob = ""
                    for v in all_videos_filtered[:15]:
                        data_blob += f"\n--- VIDEO: {v.get('title')} ---\n"
                        for c in v.get('comments', [])[:15]:
                            data_blob += f"- {c.get('text')[:200]} ({c.get('like_count', 0)} likes)\n"
                    
                    st.text_area("Copier pour ChatGPT :", value=prompt_base + data_blob, height=600)

                with r_col:
                    st.header("📹 Analyse des Vidéos")
                    for v in sorted(all_videos_filtered, key=lambda x: x.get('view_count', 0), reverse=True):
                        # Viralité stars
                        subs = v.get('channel_follower_count', 0) or 1
                        ratio = v.get('view_count', 0) / subs
                        stars = "⭐⭐⭐" if ratio > 1.2 else ("⭐⭐" if ratio > 0.6 else "⭐")
                        
                        dur_min = v.get('duration', 0) // 60
                        dur_sec = v.get('duration', 0) % 60

                        with st.expander(f"{stars} | {v.get('view_count', 0):,} vues | {dur_min}m{dur_sec:02d} | {v['title'][:50]}..."):
                            c1, c2 = st.columns([1, 2])
                            with c1: st.image(v.get('thumbnail'), use_container_width=True)
                            with c2:
                                st.write(f"**Chaîne :** {v.get('uploader')}")
                                st.write(f"**Langue Validée :** {v['lang_reason']}")
                                st.write(f"**Lien :** [Lien YouTube]({v['webpage_url']})")
                            
                            st.subheader("💬 Meilleurs commentaires")
                            for c in v.get('comments', [])[:5]:
                                st.caption(f"👍 {c.get('like_count', 0)} | {c.get('text')[:150]}...")

            progress_bar.progress(100)
            status.text("Traitement terminé.")

        except Exception as e:
            st.error(f"Erreur : {e}")
