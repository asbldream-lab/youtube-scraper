import streamlit as st
from yt_dlp import YoutubeDL
import json
from datetime import datetime, timedelta
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import re

# Configuration
st.set_page_config(page_title="YouTube Scraper Pro", layout="wide")
st.title("🚀 YouTube Keyword Research Tool PRO")

# ==========================================
# ✅ MOTEUR DE LANGUE PAR EXCLUSION (STRICT)
# ==========================================

# Mots "Poison" : S'ils sont là, c'est de l'anglais (à bannir si ES ou FR choisi)
EN_FORBIDDEN = {
    "the", "and", "how", "with", "from", "for", "about", "today", "is", "was", 
    "bought", "shocked", "unboxing", "review", "vs", "setup", "tutorial", "official", "testing"
}

LANG_RULES = {
    "es": {
        "proof": {"el", "los", "las", "un", "una", "por", "para", "con", "pero", "su", "sus", "son", "es", "y", "esta"},
        "chars": set("ñáéíóúü¡¿"),
        "region": "ES"
    },
    "fr": {
        "proof": {"le", "la", "les", "un", "une", "des", "du", "de", "et", "ou", "est", "dans", "pour", "par", "avec", "sur"},
        "chars": set("àâäçéèêëîïôöùûüÿœæ"),
        "region": "FR"
    },
    "en": {
        "proof": {"the", "and", "is", "are", "was", "were", "with", "about", "from", "for", "how"},
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
    if target_code == "auto": return True, "Auto"
    title = (info.get("title") or "").lower()
    desc = (info.get("description") or "").lower()
    full_text = title + " " + desc[:500]
    tokens = set(_clean_text(full_text).split())

    # 1. Filtre Anti-Anglais (Crucial pour Starlink/Irak)
    if target_code in ["es", "fr"]:
        if any(word in tokens for word in EN_FORBIDDEN):
            return False, "Rejet : Anglais détecté"

    # 2. Preuve par caractères
    if any(char in full_text for char in LANG_RULES[target_code]["chars"]):
        return True, "Validé (Caractères)"

    # 3. Preuve par mots outils
    if any(word in tokens for word in LANG_RULES[target_code]["proof"]):
        return True, "Validé (Mots outils)"

    # 4. Sous-titres
    if target_code in (info.get("automatic_captions") or {}) or target_code in (info.get("subtitles") or {}):
        return True, "Validé (Sous-titres)"

    return False, "Rejet : Langue non prouvée"

# ============ SIDEBAR ============
st.sidebar.header("⚙️ Paramètres")

keywords_input = st.sidebar.text_area("🔍 Mots-clés (un par ligne) :", placeholder="Starlink\nIrak")
keywords_list = [k.strip() for k in keywords_input.split('\n') if k.strip()]

language_choice = st.sidebar.selectbox("🌍 Langue cible :", ["Espagnol", "Français", "Anglais", "Auto (toutes langues)"])
lang_map = {"Espagnol": "es", "Français": "fr", "Anglais": "en", "Auto (toutes langues)": "auto"}

st.sidebar.write("### 👁️ Vues minimum")
selected_views = []
c1, c2 = st.sidebar.columns(2)
with c1:
    if st.checkbox("< 10K"): selected_views.append((0, 10000))
    if st.checkbox("10K-50K"): selected_views.append((10000, 50000))
with c2:
    if st.checkbox("50K-100K"): selected_views.append((50000, 100000))
    if st.checkbox("100K+"): selected_views.append((100000, 1000000))
if st.checkbox("1M+"): selected_views.append((1000000, float('inf')))

st.sidebar.write("### ⏱️ Durée de la vidéo")
min_duration = st.sidebar.radio("Filtrer par durée :", ["Toutes", "Minimum 2 min", "Minimum 5 min"])

st.sidebar.write("### 📈 Engagement")
use_eng = st.sidebar.checkbox("Filtrer % Likes/Vues")
min_eng = st.sidebar.slider("Seuil (%)", 0.0, 10.0, 1.0) if use_eng else 0.0

# ============ LOGIQUE DE RECHERCHE ============
if st.sidebar.button("🚀 LANCER L'ANALYSE COMPLÈTE", use_container_width=True):
    if not keywords_list or not selected_views:
        st.error("❌ Mots-clés et Tranches de vues requis !")
    else:
        target_code = lang_map[language_choice]
        region = LANG_RULES.get(target_code, {}).get("region", "US")
        
        YDL_OPTS = {
            'quiet': True, 'ignoreerrors': True, 'skip_download': True,
            'writesubtitles': True, 'writeautomaticsub': True, 'getcomments': True,
            'subtitleslangs': ['fr', 'en', 'es'],
            'extractor_args': {'youtube': {'max_comments': ['30'], 'lang': [target_code], 'region': [region]}}
        }

        progress_bar = st.progress(0)
        all_videos_filtered = []

        try:
            for kw in keywords_list:
                with YoutubeDL({'quiet': True, 'extract_flat': True}) as ydl:
                    search_res = ydl.extract_info(f"ytsearch60:{kw}", download=False)
                    entries = search_res.get('entries', [])

                def fetch_parallel(vid):
                    try:
                        return YoutubeDL(YDL_OPTS).extract_info(f"https://www.youtube.com/watch?v={vid['id']}", download=False)
                    except: return None

                with ThreadPoolExecutor(max_workers=15) as executor:
                    results = list(executor.map(fetch_parallel, entries))
                
                for v in [r for r in results if r]:
                    # 1. LANGUE
                    valid, reason = is_valid_language(v, target_code)
                    if not valid: continue

                    # 2. DURÉE
                    dur = v.get('duration', 0)
                    if min_duration == "Minimum 2 min" and dur < 120: continue
                    if min_duration == "Minimum 5 min" and dur < 300: continue

                    # 3. VUES
                    v_views = v.get('view_count', 0) or 0
                    if not any(m <= v_views <= x for m, x in selected_views): continue
                    
                    # 4. ENGAGEMENT
                    if use_eng:
                        ratio = (v.get('like_count', 0) or 0) / v_views * 100 if v_views > 0 else 0
                        if ratio < min_eng: continue

                    v['lang_reason'] = reason
                    all_videos_filtered.append(v)

            # === AFFICHAGE DES RÉSULTATS ===
            if all_videos_filtered:
                st.success(f"✅ {len(all_videos_filtered)} vidéos trouvées.")
                l_col, r_col = st.columns([1, 2])

                with l_col:
                    st.header("📋 Prompt Expert ChatGPT")
                    prompt_txt = """Rôle : Tu es un expert en stratégie de contenu. Analyse ces données pour extraire :
1. Angle stratégique (Attentes/Frustrations).
2. Top 5 idées récurrentes dans les commentaires.
3. Sujets périphériques & Opportunités.
4. Éléments indispensables pour ma future vidéo.
5. Analyse des Hooks (Accroches) et 3 nouveaux hooks originaux.

Données collectées :
"""
                    full_data = ""
                    for v in all_videos_filtered[:15]:
                        full_data += f"\n--- VIDEO: {v.get('title')} ---\n"
                        for c in v.get('comments', [])[:15]:
                            full_data += f"- {c.get('text')[:200]} ({c.get('like_count', 0)} 👍)\n"
                    st.text_area("Copier pour ChatGPT :", value=prompt_txt + full_data, height=600)

                with r_col:
                    st.header("📹 Analyse des Vidéos")
                    for v in sorted(all_videos_filtered, key=lambda x: x.get('view_count', 0), reverse=True):
                        subs = v.get('channel_follower_count', 0) or 1
                        ratio = v.get('view_count', 0) / subs
                        stars = "⭐⭐⭐" if ratio > 1.2 else ("⭐⭐" if ratio > 0.6 else "⭐")
                        m, s = divmod(v.get('duration', 0), 60)

                        with st.expander(f"{stars} | {v.get('view_count', 0):,} vues | {m}m{s:02d} | {v['title'][:50]}..."):
                            c1, c2 = st.columns([1, 2])
                            with c1: st.image(v.get('thumbnail'), use_container_width=True)
                            with c2:
                                st.write(f"**Chaîne :** {v.get('uploader')}")
                                st.write(f"**Succès (Viralité) :** {ratio:.1f}x son audience")
                                st.write(f"**Vérification Langue :** {v['lang_reason']}")
                                st.write(f"[Lien YouTube]({v['webpage_url']})")
                            st.subheader("💬 Meilleurs commentaires")
                            for c in v.get('comments', [])[:5]:
                                st.caption(f"👍 {c.get('like_count', 0)} | {c.get('text')[:150]}...")
            else:
                st.warning("Aucun résultat. Essayez d'ajouter d'autres tranches de vues.")
            
            progress_bar.progress(100)
        except Exception as e:
            st.error(f"Erreur : {e}")
