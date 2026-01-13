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
# ✅ MOTEUR DE LANGUE RENFORCÉ (SPÉCIAL ES/FR)
# ==========================================

FR_WORDS = {"le","la","les","un","une","des","du","de","et","ou","est","dans","sur","avec","pour","par","en","au","aux","qui","que","ce","cette","mais","donc"}
EN_WORDS = {"the","and","is","in","on","at","to","for","of","with","that","this","it","you","are","was","were","how","why","from"}
# Dictionnaire Espagnol étendu pour éviter les confusions avec le FR
ES_WORDS = {"el","la","los","las","un","una","unos","unas","y","o","es","en","con","para","por","de","del","al","este","esta","que","como","su","sus","lo","se","no","si","pero","todo"}

ACCENT_FR = set("àâäçéèêëîïôöùûüÿœæ")
ACCENT_ES = set("áéíóúñü¡¿") # Inclus le ñ et les signes inversés

def _clean_text(s: str) -> str:
    if not s: return ""
    s = s.lower()
    s = re.sub(r"[\W_]+", " ", s, flags=re.UNICODE)
    return s.strip()

def _has_caption(info: dict, lang: str) -> bool:
    subs = info.get("subtitles") or {}
    autos = info.get("automatic_captions") or {}
    for d in (subs, autos):
        if isinstance(d, dict):
            for k in d.keys():
                if str(k).lower().startswith(lang): return True
    return False

def keep_by_language(info: dict, target: str):
    """Calcule un score de probabilité précis pour éviter les rejets sur mots uniques."""
    if not target or target == "auto": return True, "Mode Auto"
    
    title = (info.get("title") or "").lower()
    desc = (info.get("description") or "").lower()
    yt_lang = (info.get("language") or "").lower()

    # 1. YouTube metadata (Signal de confiance 100%)
    if yt_lang.startswith(target): return True, f"YouTube Meta: {yt_lang}"
    
    # 2. Captions (Signal de confiance 95%)
    if _has_caption(info, target): return True, f"Captions: {target}"

    # 3. Analyse lexicale profonde
    text_blob = title + " " + desc[:700]
    tokens = _clean_text(text_blob).split()

    if len(tokens) < 10: 
        return True, "Texte trop court (Gardé par défaut)"

    hits = {
        "fr": sum(1 for t in tokens if t in FR_WORDS),
        "en": sum(1 for t in tokens if t in EN_WORDS),
        "es": sum(1 for t in tokens if t in ES_WORDS)
    }
    
    accents = {
        "fr": sum(1 for ch in text_blob if ch in ACCENT_FR),
        "es": sum(1 for ch in text_blob if ch in ACCENT_ES)
    }

    # Calcul du score : les accents valent cher en espagnol
    score_target = hits.get(target, 0) + (accents.get(target, 0) * 1.5)
    
    # Comparaison avec les autres langues
    other_langs = [l for l in hits.keys() if l != target]
    max_other = max([hits[l] + (accents.get(l, 0) * 1.5) for l in other_langs]) if other_langs else 0

    # On rejette seulement si une autre langue est archi-dominante (marge de 15 points)
    if max_other > score_target + 15:
        return False, f"Rejet ({max_other} vs {score_target})"

    return True, f"Score OK ({score_target})"

# ============ SIDEBAR ============
st.sidebar.header("⚙️ Paramètres")

keywords_input = st.sidebar.text_area("🔍 Mots-clés (un par ligne) :", placeholder="guerre irak\nguerra de las galaxias")
keywords_list = [k.strip() for k in keywords_input.split('\n') if k.strip()]

language_choice = st.sidebar.selectbox("🌍 Langue cible :", ["Auto (toutes langues)", "Français", "Anglais", "Espagnol"])
# Codes ISO et Régions pour forcer YouTube
lang_map = {
    "Français": {"code": "fr", "region": "FR"},
    "Anglais": {"code": "en", "region": "US"},
    "Espagnol": {"code": "es", "region": "ES"},
    "Auto (toutes langues)": {"code": "auto", "region": None}
}
selected_config = lang_map[language_choice]

st.sidebar.write("### 👁️ Vues minimum")
col1, col2, col3, col4 = st.sidebar.columns(4)
selected_views = []
if st.sidebar.checkbox("10K-50K"): selected_views.append((10000, 50000))
if st.sidebar.checkbox("50K-100K"): selected_views.append((50000, 100000))
if st.sidebar.checkbox("100K+"): selected_views.append((100000, 1000000))
if st.sidebar.checkbox("1M+"): selected_views.append((1000000, float('inf')))

st.sidebar.write("### 📈 Engagement & Période")
use_engagement = st.sidebar.checkbox("Filtrer Engagement")
min_engagement = st.sidebar.slider("% Min Like/Vue", 0.0, 10.0, 1.0) if use_engagement else 0.0
date_filter = st.sidebar.selectbox("Date :", ["Toutes", "7 derniers jours", "30 derniers jours", "1 an"])

# ============ LOGIQUE DE RECHERCHE ============
if st.sidebar.button("🚀 LANCER L'ANALYSE EXPERTE", use_container_width=True):
    if not keywords_list or not selected_views:
        st.error("❌ Mots-clés et gammes de vues requis !")
    else:
        target_code = selected_config["code"]
        target_region = selected_config["region"]
        
        # Options yt-dlp optimisées pour la langue choisie
        YDL_OPTS = {
            'quiet': True, 'ignoreerrors': True, 'skip_download': True,
            'writesubtitles': True, 'writeautomaticsub': True, 'getcomments': True,
            'subtitleslangs': ['fr', 'en', 'es'],
            'extractor_args': {
                'youtube': {
                    'max_comments': ['30'],
                    'lang': [target_code] if target_code != 'auto' else [],
                    'region': [target_region] if target_region else []
                }
            }
        }

        progress_bar = st.progress(0)
        status = st.empty()
        all_videos_filtered = []

        try:
            for kw in keywords_list:
                status.text(f"🔍 Recherche YouTube ({language_choice}) : {kw}")
                with YoutubeDL({'quiet': True, 'extract_flat': True}) as ydl:
                    search_res = ydl.extract_info(f"ytsearch40:{kw}", download=False)
                    entries = search_res.get('entries', [])

                def fetch_full_data(v):
                    try:
                        with YoutubeDL(YDL_OPTS) as ydl_full:
                            return ydl_full.extract_info(f"https://www.youtube.com/watch?v={v['id']}", download=False)
                    except: return None

                with ThreadPoolExecutor(max_workers=12) as executor:
                    results = list(executor.map(fetch_full_data, entries))
                
                for v in [r for r in results if r]:
                    # 1. Filtre Langue
                    keep, why = keep_by_language(v, target_code)
                    if not keep: continue
                    
                    # 2. Filtre Vues
                    v_views = v.get('view_count', 0) or 0
                    if not any(m <= v_views <= x for m, x in selected_views): continue
                    
                    # 3. Filtre Engagement
                    if use_engagement:
                        ratio = (v.get('like_count', 0) or 0) / v_views * 100 if v_views > 0 else 0
                        if ratio < min_engagement: continue

                    v['search_keyword'] = kw
                    all_videos_filtered.append(v)

            # === INTERFACE DE SORTIE ===
            if all_videos_filtered:
                st.success(f"✅ Analyse terminée : {len(all_videos_filtered)} vidéos trouvées.")
                
                left_col, right_col = st.columns([1, 2])

                # --- GAUCHE : LE PROMPT COMPLET ---
                with left_col:
                    st.header("📋 Prompt Expert ChatGPT")
                    
                    prompt_txt = """Rôle : Tu es un expert en analyse de données sociales et en stratégie de contenu vidéo. Ton but est d'analyser les commentaires et les premières phrases des vidéos concurrentes pour en extraire une stratégie éditoriale unique.

Contraintes de réponse :
* Chaque section doit avoir le titre indiqué.
* Chaque réponse sous les titres doit faire maximum 2 phrases.
* Le ton doit être direct, efficace et sans remplissage.

Instructions d'analyse :
1. Angle de réponse stratégique : Identifie l'approche globale à adopter pour répondre aux attentes ou aux frustrations des utilisateurs.
2. Top 5 des idées récurrentes : Liste les 5 thèmes ou arguments qui reviennent le plus souvent dans les commentaires.
3. Sujets périphériques et opportunités : Propose des sujets connexes mentionnés par l'audience pour de futures vidéos.
4. Éléments indispensables pour la vidéo : Liste les points précis ou questions auxquels tu dois absolument répondre.
5. Analyse des accroches et nouveaux Hooks : Analyse la structure des phrases de début fournies pour proposer 3 nouveaux hooks originaux et percutants sans jamais copier les originaux.

Voici les données collectées :
"""
                    # Compilation des données vidéos + commentaires
                    full_data = f"\nRecherche : {', '.join(keywords_list)} | Langue : {language_choice}\n"
                    for v in all_videos_filtered:
                        full_data += f"\n--- VIDEO: {v.get('title')} ---\n"
                        full_data += f"HOOK: {v.get('hook', 'Non extrait')}\n"
                        for c in v.get('comments', [])[:15]:
                            full_data += f"- {c.get('text')[:300]} ({c.get('like_count', 0)} likes)\n"
                    
                    st.text_area("Copie ce texte dans ChatGPT :", value=prompt_txt + full_data, height=600)

                # --- DROITE : ANALYSE VISUELLE ---
                with right_col:
                    st.header("📹 Analyse des Vidéos")
                    for v in sorted(all_videos_filtered, key=lambda x: x.get('view_count', 0), reverse=True):
                        subs = v.get('channel_follower_count', 0) or 1
                        v_views = v.get('view_count', 0) or 0
                        virality = v_views / subs
                        stars = "⭐⭐⭐" if virality > 1.2 else ("⭐⭐" if virality > 0.6 else "⭐")
                        
                        with st.expander(f"{stars} | {v_views:,} vues | {v.get('title')[:60]}..."):
                            c1, c2 = st.columns([1, 2])
                            with c1:
                                st.image(v.get('thumbnail'), use_container_width=True)
                            with c2:
                                st.write(f"**Chaîne :** {v.get('uploader')} ({subs:,} abonnés)")
                                st.write(f"**Succès :** {virality:.1f}x la taille de la base fans")
                                st.write(f"**Lien :** [Ouvrir YouTube]({v.get('webpage_url')})")
                            
                            st.subheader("💬 Commentaires Clés")
                            for c in v.get('comments', [])[:5]:
                                st.write(f"👉 {c.get('text')[:200]}... ({c.get('like_count', 0)} 👍)")

            progress_bar.progress(100)
            status.text("Traitement terminé.")
            
        except Exception as e:
            st.error(f"Une erreur est survenue : {e}")
