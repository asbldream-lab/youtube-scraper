import streamlit as st
from yt_dlp import YoutubeDL
import json
from datetime import datetime, timedelta
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import re

# ==========================================
# ✅ INSTALLATION AUTOMATIQUE DE LANGDETECT
# ==========================================
try:
    from langdetect import detect, detect_langs, LangDetectException
except ImportError:
    import subprocess
    subprocess.check_call(['pip', 'install', 'langdetect', '--quiet'])
    from langdetect import detect, detect_langs, LangDetectException

# ==========================================
# ✅ CONFIGURATION & SESSION STATE
# ==========================================
st.set_page_config(page_title="YouTube Scraper Pro", layout="wide")
st.title("🚀 YouTube Keyword Research Tool PRO")

if 'search_history' not in st.session_state:
    st.session_state.search_history = []

# ==========================================
# ✅ CONFIGURATION DES LANGUES (SIMPLIFIÉ)
# ==========================================
LANGUAGE_CONFIG = {
    "Auto (toutes langues)": {"code": None, "yt_lang": None, "yt_region": None},
    "Français": {"code": "fr", "yt_lang": "fr", "yt_region": "FR"},
    "Anglais": {"code": "en", "yt_lang": "en", "yt_region": "US"},
    "Espagnol": {"code": "es", "yt_lang": "es", "yt_region": "ES"},
}

# ==========================================
# ✅ DÉTECTION SIMPLIFIÉE ET RAPIDE
# ==========================================
def detect_primary_language(info, use_comments=False):
    """
    Détecte la langue principale avec un système simple et rapide.
    Retourne : (langue, confiance_score)
    """
    
    # 1. Métadonnées YouTube (confiance maximale)
    yt_lang = info.get('language')
    if yt_lang:
        lang = yt_lang[:2].lower()
        return lang, 1.0
    
    # 2. Sous-titres automatiques
    auto_captions = info.get('automatic_captions') or {}
    if auto_captions:
        first_lang = list(auto_captions.keys())[0][:2].lower()
        return first_lang, 0.95
    
    # 3. Sous-titres manuels
    subtitles = info.get('subtitles') or {}
    if subtitles:
        first_lang = list(subtitles.keys())[0][:2].lower()
        return first_lang, 0.90
    
    # 4. Analyse textuelle (titre + description)
    text_parts = []
    
    title = info.get('title', '')
    if len(title) > 15:
        text_parts.append(title)
    
    desc = info.get('description', '')
    if desc:
        clean_desc = re.sub(r'http\S+|#\S+|@\S+', '', desc[:800])
        if len(clean_desc) > 60:
            text_parts.append(clean_desc)
    
    # 5. Commentaires (si disponibles)
    if use_comments:
        comments = info.get('comments', [])
        if comments:
            # Prendre 30 commentaires représentatifs
            comment_texts = [c.get('text', '') for c in comments[:30] if len(c.get('text', '')) > 25]
            if comment_texts:
                text_parts.append(" ".join(comment_texts[:15]))
    
    # Détecter sur l'ensemble du texte
    if text_parts:
        combined = " ".join(text_parts)
        clean = re.sub(r'[^\w\s\u00C0-\u017F\u0400-\u04FF]', ' ', combined)
        clean = re.sub(r'\s+', ' ', clean).strip()
        
        if len(clean) > 50:
            try:
                detected = detect_langs(clean)
                if detected and detected[0].prob > 0.6:
                    return detected[0].lang, detected[0].prob
            except LangDetectException:
                pass
    
    return None, 0.0

# ==========================================
# ✅ FILTRAGE ULTRA-MINIMALISTE
# ==========================================
def should_accept_video(info, target_lang, phase="phase1"):
    """
    Décision d'accepter une vidéo.
    
    RÈGLE D'OR : Dans le DOUTE, on ACCEPTE !
    
    Phase 1 : Rejeter SEULEMENT si métadonnées YouTube indiquent clairement une autre langue
    Phase 2 : Rejeter SEULEMENT si 90%+ des commentaires sont dans une autre langue
    """
    
    if target_lang == "Auto (toutes langues)":
        return True, "auto_mode"
    
    config = LANGUAGE_CONFIG.get(target_lang)
    if not config or not config['code']:
        return True, "no_filter"
    
    target_code = config['code']
    
    # Détecter
    use_comments = (phase == "phase2")
    detected, confidence = detect_primary_language(info, use_comments)
    
    # Stocker pour debug
    info['_detected'] = detected or "?"
    info['_confidence'] = f"{confidence:.2f}"
    info['_phase'] = phase
    
    # ========================================
    # PHASE 1 : REJETER SEULEMENT CAS ÉVIDENTS
    # ========================================
    if phase == "phase1":
        # Pas de détection ? → ACCEPTER
        if detected is None:
            return True, "no_detection"
        
        # Match direct ? → ACCEPTER
        if detected == target_code:
            return True, "match"
        
        # REJETER seulement si :
        # - Confiance >= 0.95 (métadonnées YouTube ou sous-titres)
        # - ET langue complètement différente (pas d'ambiguïté)
        
        if confidence >= 0.95:
            # Langues incompatibles
            incompatible = {
                'fr': ['en', 'de', 'ru', 'ar', 'zh', 'ja', 'ko'],
                'en': ['fr', 'de', 'ru', 'ar', 'zh', 'ja', 'ko', 'es'],
                'es': ['en', 'de', 'ru', 'ar', 'zh', 'ja', 'ko', 'fr'],
            }
            
            if detected in incompatible.get(target_code, []):
                return False, f"clear_mismatch_{detected}"
        
        # TOUT LE RESTE : ACCEPTER
        return True, "phase1_permissive"
    
    # ========================================
    # PHASE 2 : TRÈS PERMISSIF AUSSI
    # ========================================
    elif phase == "phase2":
        # Pas de détection ? → ACCEPTER
        if detected is None:
            return True, "no_detection"
        
        # Match direct ? → ACCEPTER
        if detected == target_code:
            return True, "match"
        
        # REJETER seulement si :
        # - Confiance >= 0.85
        # - Langue clairement incompatible
        
        if confidence >= 0.85:
            # Même liste d'incompatibilités
            incompatible = {
                'fr': ['en', 'de', 'ru', 'ar', 'zh', 'ja', 'ko'],
                'en': ['fr', 'de', 'ru', 'ar', 'zh', 'ja', 'ko', 'es'],
                'es': ['en', 'de', 'ru', 'ar', 'zh', 'ja', 'ko', 'fr'],
            }
            
            if detected in incompatible.get(target_code, []):
                return False, f"comment_mismatch_{detected}"
        
        # DANS LE DOUTE : ACCEPTER
        return True, "phase2_permissive"
    
    return True, "fallback"

# ==========================================
# ✅ FONCTIONS YT-DLP
# ==========================================
def build_search_query(keyword, target_lang):
    config = LANGUAGE_CONFIG.get(target_lang, {})
    query = f"ytsearch50:{keyword}"
    return query, config.get('yt_lang'), config.get('yt_region')

def get_ydl_options(target_lang, get_comments=False):
    config = LANGUAGE_CONFIG.get(target_lang, {})
    
    opts = {
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'socket_timeout': 30,
        'retries': 3,
    }
    
    if config.get('yt_lang'):
        opts['extractor_args'] = {
            'youtube': {
                'lang': [config['yt_lang']],
            }
        }
    
    if config.get('yt_region'):
        opts['geo_bypass_country'] = config['yt_region']
    
    opts['writesubtitles'] = True
    opts['writeautomaticsub'] = True
    opts['skip_download'] = True
    
    if get_comments:
        opts['getcomments'] = True
    
    return opts

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
    list(LANGUAGE_CONFIG.keys())
)

if language != "Auto (toutes langues)":
    st.sidebar.success(f"✅ Filtre minimaliste : rejette SEULEMENT si 95%+ de certitude que c'est la mauvaise langue.")

# VUES
st.sidebar.write("### 👁️ Vues minimum")
col1, col2, col3, col4 = st.sidebar.columns(4)
selected_views = []
with col1:
    if st.checkbox("10K-50K", key="v1"): selected_views.append((10000, 50000))
with col2:
    if st.checkbox("50K-100K", key="v2"): selected_views.append((50000, 100000))
with col3:
    if st.checkbox("100K+", key="v3"): selected_views.append((100000, 1000000))
with col4:
    if st.checkbox("1M+", key="v4"): selected_views.append((1000000, float('inf')))

# DURÉE
st.sidebar.write("### ⏱️ Durée de la vidéo")
min_duration = st.sidebar.radio("Minimum :", ["Toutes", "Minimum 2 min", "Minimum 5 min"])

# ENGAGEMENT & DATE
st.sidebar.write("### 📈 Ratio & Période")
use_engagement = st.sidebar.checkbox("Filtrer par engagement")
min_engagement = st.sidebar.slider("Like/Vue min (%)", 0.0, 10.0, 1.0) if use_engagement else 0.0

date_filter = st.sidebar.selectbox(
    "Période:",
    ["Toutes", "7 derniers jours", "30 derniers jours", "6 derniers mois", "1 an"]
)

show_debug = st.sidebar.checkbox("🔧 Mode debug", value=False)

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
        rejected_phase1 = 0
        rejected_phase2 = 0
        reasons_p1 = []
        reasons_p2 = []
        
        try:
            total_keywords = len(keywords_list)
            
            for kw_idx, kw in enumerate(keywords_list):
                status.text(f"🔍 Recherche : {kw} ({kw_idx + 1}/{total_keywords})")
                progress_bar.progress(int((kw_idx / total_keywords) * 20))
                
                search_query, yt_lang, yt_region = build_search_query(kw, language)
                
                # Recherche
                search_opts = {
                    'quiet': True, 
                    'extract_flat': True,
                    'ignoreerrors': True,
                }
                if yt_region:
                    search_opts['geo_bypass_country'] = yt_region
                
                with YoutubeDL(search_opts) as ydl:
                    search_res = ydl.extract_info(search_query, download=False)
                    entries = search_res.get('entries', []) if search_res else []

                if not entries:
                    st.warning(f"⚠️ Aucun résultat pour '{kw}'")
                    continue
                
                # ==========================================
                # PHASE 1 : EXTRACTION RAPIDE
                # ==========================================
                status.text(f"⚡ Phase 1 : {len(entries)} vidéos...")
                progress_bar.progress(int((kw_idx / total_keywords) * 20) + 10)

                def fetch_light(vid):
                    if not vid or not vid.get('id'):
                        return None
                    try:
                        opts = get_ydl_options(language, get_comments=False)
                        with YoutubeDL(opts) as ydl:
                            return ydl.extract_info(f"https://www.youtube.com/watch?v={vid['id']}", download=False)
                    except Exception:
                        return None

                with ThreadPoolExecutor(max_workers=15) as executor:
                    futures = [executor.submit(fetch_light, vid) for vid in entries]
                    metas = [f.result() for f in as_completed(futures) if f.result()]

                status.text(f"🔬 Filtrage...")
                progress_bar.progress(int((kw_idx / total_keywords) * 20) + 15)

                candidates = []
                for info in metas:
                    if not info:
                        continue
                    
                    # LANGUE
                    keep, reason = should_accept_video(info, language, "phase1")
                    if not keep:
                        rejected_phase1 += 1
                        reasons_p1.append(reason)
                        continue
                    
                    # DURÉE
                    dur = info.get('duration', 0)
                    if min_duration == "Minimum 2 min" and dur < 120:
                        continue
                    if min_duration == "Minimum 5 min" and dur < 300:
                        continue

                    # VUES
                    views = info.get('view_count', 0)
                    if not any(mn <= views <= mx for mn, mx in selected_views):
                        continue

                    # DATE
                    if date_limit:
                        upload = info.get('upload_date')
                        if upload:
                            try:
                                vdate = datetime.strptime(upload, '%Y%m%d')
                                if vdate < date_limit:
                                    continue
                            except ValueError:
                                pass

                    # ENGAGEMENT
                    if use_engagement:
                        likes = info.get('like_count', 0)
                        v = info.get('view_count', 1)
                        ratio = (likes / v) * 100
                        if ratio < min_engagement:
                            continue

                    candidates.append(info)

                # ==========================================
                # PHASE 2 : COMMENTAIRES
                # ==========================================
                if candidates:
                    status.text(f"💬 Phase 2 : {len(candidates)} vidéos...")
                    progress_bar.progress(int((kw_idx / total_keywords) * 20) + 18)

                    def fetch_comments(info):
                        try:
                            opts = get_ydl_options(language, get_comments=True)
                            with YoutubeDL(opts) as ydl:
                                full = ydl.extract_info(f"https://www.youtube.com/watch?v={info['id']}", download=False)
                                info['comments'] = full.get('comments', [])
                                return info
                        except Exception:
                            return info

                    with ThreadPoolExecutor(max_workers=12) as executor:
                        futures = [executor.submit(fetch_comments, c) for c in candidates]
                        for f in as_completed(futures):
                            try:
                                enriched = f.result()
                                if enriched:
                                    keep, reason = should_accept_video(enriched, language, "phase2")
                                    if keep:
                                        enriched['search_keyword'] = kw
                                        all_videos_filtered.append(enriched)
                                    else:
                                        rejected_phase2 += 1
                                        reasons_p2.append(reason)
                            except Exception:
                                pass

            progress_bar.progress(90)

            # === RÉSULTATS ===
            total_rejected = rejected_phase1 + rejected_phase2
            
            if all_videos_filtered:
                st.success(f"✅ **{len(all_videos_filtered)} vidéos trouvées** en {language} !")
                
                if total_rejected > 0:
                    with st.expander(f"📊 Rejets : {total_rejected} (P1: {rejected_phase1} • P2: {rejected_phase2})", expanded=False):
                        if show_debug:
                            from collections import Counter
                            st.write("**Phase 1:**")
                            for r, c in Counter(reasons_p1).most_common(5):
                                st.write(f"  • {r}: {c}x")
                            st.write("**Phase 2:**")
                            for r, c in Counter(reasons_p2).most_common(5):
                                st.write(f"  • {r}: {c}x")
                
                left_col, right_col = st.columns([1, 2])

                with left_col:
                    st.header("📋 Analyse")
                    prompt = """Rôle : Expert en stratégie YouTube.

Objectif : Identifier les angles engageants et idées de vidéos.

Données :
"""
                    
                    blob = f"\nRecherche : {', '.join(keywords_list)}\n"
                    blob += f"Langue : {language}\n"
                    blob += f"Vidéos : {len(all_videos_filtered)}\n\n"
                    
                    for v in all_videos_filtered:
                        blob += f"\n{'='*50}\n"
                        blob += f"VIDÉO: {v.get('title', 'N/A')}\n"
                        blob += f"Vues: {v.get('view_count', 0):,} | Likes: {v.get('like_count', 0):,}\n"
                        blob += f"Chaîne: {v.get('uploader', 'N/A')}\n"
                        
                        if show_debug:
                            blob += f"[DEBUG] {v.get('_detected')} • {v.get('_confidence')}\n"
                        
                        comms = v.get('comments', [])
                        if comms:
                            blob += f"\nCOMMENTAIRES ({min(15, len(comms))}):\n"
                            for c in comms[:15]:
                                blob += f"  • [{c.get('like_count', 0)} ❤️] {c.get('text', '')[:200]}\n"
                    
                    st.text_area("Copie :", value=prompt + blob, height=500)

                with right_col:
                    st.header("📹 Vidéos")
                    
                    for idx, v in enumerate(all_videos_filtered, 1):
                        subs = v.get('channel_follower_count', 1)
                        views = v.get('view_count', 0)
                        ratio = views / subs if subs > 0 else 0
                        
                        stars = "🔥🔥🔥" if ratio > 2 else ("⭐⭐" if ratio > 1 else "⭐")
                        
                        title = v.get('title', 'N/A')[:55]
                        badge = f"[{v.get('_detected')}•{v.get('_confidence')}]" if show_debug else ""
                        
                        with st.expander(f"#{idx} {stars} | {views:,} vues | {title}... {badge}"):
                            c1, c2 = st.columns([1, 2])
                            
                            with c1:
                                if v.get('thumbnail'):
                                    st.image(v['thumbnail'], width=200)
                            
                            with c2:
                                st.write(f"**Chaîne :** {v.get('uploader', 'N/A')}")
                                st.write(f"**Abonnés :** {subs:,}")
                                st.write(f"**Likes :** {v.get('like_count', 0):,}")
                                st.write(f"**Durée :** {v.get('duration', 0) // 60} min")
                                st.write(f"**[Regarder]({v.get('webpage_url', '#')})**")
                                
                                if show_debug:
                                    st.write(f"🔬 {v.get('_detected')} ({v.get('_confidence')})")
                            
                            comms = v.get('comments', [])
                            if comms:
                                st.write("---")
                                st.write("**💬 Commentaires :**")
                                for c in comms[:5]:
                                    st.write(f"• {c.get('text', '')[:150]}...")

            else:
                st.error("⚠️ **Aucune vidéo trouvée.**")
                
                if total_rejected > 0:
                    st.warning(f"""
🔍 **{total_rejected} vidéos rejetées** (P1: {rejected_phase1} • P2: {rejected_phase2})

💡 Active le **mode debug** pour comprendre pourquoi.
                    """)

            st.session_state.search_history.append({
                'date': datetime.now().strftime('%d/%m %H:%M'),
                'kw': keywords_list,
                'lang': language,
                'found': len(all_videos_filtered),
                'rejected': total_rejected
            })
            
            progress_bar.progress(100)
            status.text("✅ Terminé !")

        except Exception as e:
            st.error(f"❌ {e}")
            import traceback
            st.code(traceback.format_exc())

# ============ HISTORIQUE ============
if st.session_state.search_history:
    with st.expander("📚 Historique"):
        for h in reversed(st.session_state.search_history[-10:]):
            rej = f" (🚫 {h.get('rejected', 0)})" if h.get('rejected', 0) > 0 else ""
            st.write(f"📅 {h['date']} | {', '.join(h['kw'])} | {h.get('lang', 'Auto')} | {h['found']} vidéos{rej}")
