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
# ✅ CONFIGURATION DES LANGUES
# ==========================================
LANGUAGE_CONFIG = {
    "Auto (toutes langues)": {"code": None, "yt_lang": None, "yt_region": None},
    "Français": {"code": "fr", "yt_lang": "fr", "yt_region": "FR"},
    "Anglais": {"code": "en", "yt_lang": "en", "yt_region": "US"},
    "Espagnol": {"code": "es", "yt_lang": "es", "yt_region": "ES"},
    "Portugais": {"code": "pt", "yt_lang": "pt", "yt_region": "BR"},
    "Allemand": {"code": "de", "yt_lang": "de", "yt_region": "DE"},
    "Italien": {"code": "it", "yt_lang": "it", "yt_region": "IT"},
}

# ==========================================
# ✅ LANGUES PROCHES (pour éviter faux rejets)
# ==========================================
LANGUAGE_FAMILIES = {
    "es": ["es", "pt", "ca", "gl"],  # Espagnol, Portugais, Catalan, Galicien
    "pt": ["pt", "es", "gl"],
    "fr": ["fr", "it", "es", "pt", "ca"],  # Langues latines
    "it": ["it", "fr", "es", "pt"],
    "en": ["en"],  # Anglais seul
    "de": ["de", "nl", "af"],  # Allemand, Néerlandais, Afrikaans
}

# ==========================================
# ✅ DÉTECTION ULTRA-ROBUSTE
# ==========================================
def detect_language_comprehensive(info, use_comments=False):
    """
    Détection complète avec score de confiance.
    Retourne : (langue, confiance, source, debug_info)
    """
    debug_info = {}
    
    # ========================================
    # NIVEAU 1 : MÉTADONNÉES YOUTUBE (100% fiable)
    # ========================================
    yt_lang = info.get('language')
    if yt_lang:
        lang_code = yt_lang[:2].lower()
        debug_info['youtube_metadata'] = lang_code
        return lang_code, 1.0, "youtube_metadata", debug_info
    
    # ========================================
    # NIVEAU 2 : SOUS-TITRES (95% fiable)
    # ========================================
    auto_captions = info.get('automatic_captions') or {}
    if auto_captions:
        langs = list(auto_captions.keys())
        if langs:
            primary_lang = langs[0][:2].lower()
            debug_info['auto_captions'] = primary_lang
            debug_info['all_caption_langs'] = [l[:2] for l in langs[:3]]
            return primary_lang, 0.95, "auto_captions", debug_info
    
    subtitles = info.get('subtitles') or {}
    if subtitles:
        langs = list(subtitles.keys())
        if langs:
            primary_lang = langs[0][:2].lower()
            debug_info['manual_subtitles'] = primary_lang
            return primary_lang, 0.90, "manual_subtitles", debug_info
    
    # ========================================
    # NIVEAU 3 : ANALYSE TEXTUELLE (variable)
    # ========================================
    texts = []
    
    # Titre
    title = info.get('title', '')
    if len(title) > 20:
        texts.append(('title', title, 2.0))
    
    # Description
    desc = info.get('description', '')
    if desc:
        clean_desc = re.sub(r'http\S+|#\S+|@\S+', '', desc[:1500])
        if len(clean_desc) > 80:
            texts.append(('description', clean_desc, 1.5))
    
    # Commentaires (CRITIQUES)
    if use_comments:
        comments = info.get('comments', [])
        if comments:
            # Prendre jusqu'à 50 commentaires avec au moins 30 caractères
            valid_comments = [c.get('text', '') for c in comments[:50] if len(c.get('text', '')) > 30]
            if valid_comments:
                combined = " ".join(valid_comments[:25])
                texts.append(('comments', combined, 5.0))  # Poids maximum
    
    # Détection sur chaque source
    detections = {}
    
    for source, text, weight in texts:
        clean = re.sub(r'[^\w\s\u00C0-\u017F\u0400-\u04FF\u0370-\u03FF]', ' ', text)
        clean = re.sub(r'\s+', ' ', clean).strip()
        
        if len(clean) > 40:
            try:
                detected = detect_langs(clean)
                if detected:
                    for lang_prob in detected[:3]:  # Top 3
                        lang = lang_prob.lang
                        prob = lang_prob.prob
                        
                        if lang not in detections:
                            detections[lang] = {'score': 0, 'sources': [], 'max_prob': 0}
                        
                        detections[lang]['score'] += prob * weight
                        detections[lang]['sources'].append(source)
                        detections[lang]['max_prob'] = max(detections[lang]['max_prob'], prob)
            except LangDetectException:
                pass
    
    if detections:
        # Trouver la meilleure langue
        best = max(detections.items(), key=lambda x: x[1]['score'])
        lang = best[0]
        data = best[1]
        
        debug_info['text_detection'] = {
            'lang': lang,
            'score': data['score'],
            'sources': data['sources'],
            'max_prob': data['max_prob']
        }
        
        # Calculer confiance globale
        confidence = min(0.85, data['max_prob'] + (len(data['sources']) * 0.1))
        
        return lang, confidence, f"text_{'+'.join(set(data['sources']))}", debug_info
    
    debug_info['no_detection'] = True
    return None, 0.0, "unknown", debug_info

# ==========================================
# ✅ FILTRAGE ULTRA-PERMISSIF
# ==========================================
def should_keep_video(info, target_lang, phase="phase1"):
    """
    Décision de garder ou rejeter une vidéo.
    Phase 1 : ULTRA PERMISSIF - rejeter seulement cas évidents
    Phase 2 : MODÉRÉ - filtrage avec commentaires
    """
    
    if target_lang == "Auto (toutes langues)":
        return True, "auto_mode"
    
    config = LANGUAGE_CONFIG.get(target_lang)
    if not config or not config['code']:
        return True, "no_filter"
    
    target_code = config['code']
    target_family = LANGUAGE_FAMILIES.get(target_code, [target_code])
    
    # Détecter
    use_comments = (phase == "phase2")
    detected_lang, confidence, source, debug = detect_language_comprehensive(info, use_comments)
    
    # Stocker pour affichage
    info['_detected_language'] = detected_lang or "?"
    info['_detection_confidence'] = f"{confidence:.2f}"
    info['_detection_source'] = source
    info['_detection_debug'] = debug
    
    # ========================================
    # PHASE 1 : ULTRA PERMISSIF
    # ========================================
    if phase == "phase1":
        # Pas de détection ? GARDER (sera vérifié en Phase 2)
        if detected_lang is None:
            return True, "no_detection_keep"
        
        # Match direct ? GARDER
        if detected_lang in target_family:
            return True, "direct_match"
        
        # REJETER seulement si :
        # 1. Confiance >= 0.90 (très haute)
        # 2. Source = métadonnées YouTube ou sous-titres
        # 3. Langue clairement différente ET pas proche
        
        if confidence >= 0.90 and source in ["youtube_metadata", "auto_captions", "manual_subtitles"]:
            # Vérifier si langue proche
            if detected_lang not in target_family:
                # Cas spéciaux : certaines langues sont acceptables pour certaines recherches
                # Ex: vidéo technique en anglais mais commentaires espagnols
                if source == "youtube_metadata" and detected_lang == "en" and target_code in ["es", "pt"]:
                    # Vidéo en anglais mais peut avoir audience espagnole/portugaise
                    # Garder pour vérifier en Phase 2
                    return True, "en_technical_keep"
                
                return False, f"clear_mismatch_{detected_lang}_vs_{target_code}"
        
        # TOUS LES AUTRES CAS : GARDER
        return True, "phase1_permissive"
    
    # ========================================
    # PHASE 2 : MODÉRÉ (avec commentaires)
    # ========================================
    elif phase == "phase2":
        # Pas de détection même avec commentaires ? GARDER (dans le doute)
        if detected_lang is None:
            return True, "no_detection_benefit_doubt"
        
        # Match direct ? GARDER
        if detected_lang in target_family:
            return True, "direct_match"
        
        # REJETER si :
        # - Confiance >= 0.70
        # - Langue clairement différente
        # - Source inclut les commentaires
        
        if confidence >= 0.70:
            if detected_lang not in target_family:
                # Si commentaires sont dans la mauvaise langue, c'est clair
                if 'comments' in source:
                    return False, f"comments_mismatch_{detected_lang}_vs_{target_code}"
                
                # Si métadonnées + texte concordent sur une autre langue
                if confidence >= 0.85:
                    return False, f"strong_mismatch_{detected_lang}_vs_{target_code}"
        
        # Dans le doute, GARDER
        return True, "phase2_benefit_doubt"
    
    return True, "fallback_keep"

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
    st.sidebar.success(f"✅ Filtre ultra-permissif : on garde tout sauf si YouTube indique CLAIREMENT une autre langue.")

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

show_debug = st.sidebar.checkbox("🔧 Mode debug complet", value=False)

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
        rejection_reasons_p1 = []
        rejection_reasons_p2 = []
        
        try:
            total_keywords = len(keywords_list)
            
            for kw_idx, kw in enumerate(keywords_list):
                status.text(f"🔍 Recherche YouTube : {kw} ({kw_idx + 1}/{total_keywords})")
                progress_bar.progress(int((kw_idx / total_keywords) * 20))
                
                search_query, yt_lang, yt_region = build_search_query(kw, language)
                
                # Recherche initiale
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
                # 🚀 PHASE 1 : EXTRACTION RAPIDE
                # ==========================================
                status.text(f"⚡ Phase 1 : Extraction de {len(entries)} vidéos...")
                progress_bar.progress(int((kw_idx / total_keywords) * 20) + 10)

                def fetch_metadata_only(vid):
                    if not vid or not vid.get('id'):
                        return None
                    try:
                        opts = get_ydl_options(language, get_comments=False)
                        with YoutubeDL(opts) as ydl_light:
                            return ydl_light.extract_info(
                                f"https://www.youtube.com/watch?v={vid['id']}", 
                                download=False
                            )
                    except Exception:
                        return None

                with ThreadPoolExecutor(max_workers=15) as executor:
                    futures = [executor.submit(fetch_metadata_only, vid) for vid in entries]
                    metadata_infos = []
                    for future in as_completed(futures):
                        try:
                            result = future.result()
                            if result:
                                metadata_infos.append(result)
                        except Exception:
                            pass

                status.text(f"🔬 Filtrage Phase 1...")
                progress_bar.progress(int((kw_idx / total_keywords) * 20) + 15)

                candidates = []
                for info in metadata_infos:
                    if not info:
                        continue
                    
                    # FILTRE LANGUE (ULTRA PERMISSIF)
                    keep, reason = should_keep_video(info, language, phase="phase1")
                    if not keep:
                        rejected_phase1 += 1
                        rejection_reasons_p1.append(reason)
                        continue
                    
                    # AUTRES FILTRES
                    v_dur = info.get('duration') or 0
                    if min_duration == "Minimum 2 min" and v_dur < 120:
                        continue
                    if min_duration == "Minimum 5 min" and v_dur < 300:
                        continue

                    v_views = info.get('view_count') or 0
                    if not any(mn <= v_views <= mx for mn, mx in selected_views):
                        continue

                    if date_limit:
                        upload_date = info.get('upload_date')
                        if upload_date:
                            try:
                                v_date = datetime.strptime(upload_date, '%Y%m%d')
                                if v_date < date_limit:
                                    continue
                            except ValueError:
                                pass

                    if use_engagement:
                        likes = info.get('like_count') or 0
                        views = info.get('view_count') or 1
                        engagement_ratio = (likes / views) * 100
                        if engagement_ratio < min_engagement:
                            continue

                    candidates.append(info)

                # ==========================================
                # 🚀 PHASE 2 : COMMENTAIRES
                # ==========================================
                if candidates:
                    status.text(f"💬 Phase 2 : {len(candidates)} vidéos → extraction commentaires...")
                    progress_bar.progress(int((kw_idx / total_keywords) * 20) + 18)

                    def fetch_comments_only(info):
                        try:
                            opts = get_ydl_options(language, get_comments=True)
                            with YoutubeDL(opts) as ydl_comments:
                                full_info = ydl_comments.extract_info(
                                    f"https://www.youtube.com/watch?v={info['id']}", 
                                    download=False
                                )
                                info['comments'] = full_info.get('comments', [])
                                return info
                        except Exception:
                            return info

                    with ThreadPoolExecutor(max_workers=12) as executor:
                        futures = [executor.submit(fetch_comments_only, cand) for cand in candidates]
                        for future in as_completed(futures):
                            try:
                                enriched_info = future.result()
                                if enriched_info:
                                    keep, reason = should_keep_video(enriched_info, language, phase="phase2")
                                    if keep:
                                        enriched_info['search_keyword'] = kw
                                        all_videos_filtered.append(enriched_info)
                                    else:
                                        rejected_phase2 += 1
                                        rejection_reasons_p2.append(reason)
                            except Exception:
                                pass

            progress_bar.progress(90)

            # === AFFICHAGE RÉSULTATS ===
            total_rejected = rejected_phase1 + rejected_phase2
            
            if all_videos_filtered:
                st.success(f"✅ **{len(all_videos_filtered)} vidéos trouvées** en {language}!")
                
                if total_rejected > 0 and language != "Auto (toutes langues)":
                    with st.expander(f"🔬 Détails rejets ({total_rejected} vidéos)", expanded=False):
                        st.write(f"**Phase 1:** {rejected_phase1} rejetées")
                        if show_debug and rejection_reasons_p1:
                            from collections import Counter
                            reasons_count = Counter(rejection_reasons_p1)
                            for reason, count in reasons_count.most_common():
                                st.write(f"  • {reason}: {count}x")
                        
                        st.write(f"**Phase 2:** {rejected_phase2} rejetées")
                        if show_debug and rejection_reasons_p2:
                            from collections import Counter
                            reasons_count = Counter(rejection_reasons_p2)
                            for reason, count in reasons_count.most_common():
                                st.write(f"  • {reason}: {count}x")
                
                left_col, right_col = st.columns([1, 2])

                # GAUCHE : PROMPT
                with left_col:
                    st.header("📋 Copie pour analyse")
                    prompt_expert = """Rôle : Tu es un expert en analyse de données sociales et en stratégie de contenu YouTube.

Objectif : Analyse les données suivantes pour identifier :
1. Les sujets les plus engageants
2. Les angles uniques qui fonctionnent
3. Les patterns dans les commentaires
4. Des idées de vidéos à créer

Données à analyser :
"""
                    
                    data_blob = f"\nMots-clés recherchés : {', '.join(keywords_list)}\n"
                    data_blob += f"Langue : {language}\n"
                    data_blob += f"Nombre de vidéos : {len(all_videos_filtered)}\n\n"
                    
                    for v in all_videos_filtered:
                        data_blob += f"\n{'='*50}\n"
                        data_blob += f"VIDÉO: {v.get('title', 'N/A')}\n"
                        data_blob += f"Vues: {v.get('view_count', 0):,} | Likes: {v.get('like_count', 0):,}\n"
                        data_blob += f"Chaîne: {v.get('uploader', 'N/A')}\n"
                        
                        if show_debug:
                            data_blob += f"[DEBUG] Langue: {v.get('_detected_language')} | Conf: {v.get('_detection_confidence')} | Source: {v.get('_detection_source')}\n"
                        
                        comments = v.get('comments') or []
                        if comments:
                            data_blob += f"\nTOP COMMENTAIRES ({min(15, len(comments))} affichés):\n"
                            for c in comments[:15]:
                                likes = c.get('like_count', 0)
                                text = c.get('text', '')[:200]
                                data_blob += f"  • [{likes} ❤️] {text}\n"
                    
                    st.text_area("Copie pour ChatGPT/Claude :", value=prompt_expert + data_blob, height=500)

                # DROITE : VIDÉOS
                with right_col:
                    st.header("📹 Vidéos trouvées")
                    
                    for idx, v in enumerate(all_videos_filtered, 1):
                        subs = v.get('channel_follower_count') or 1
                        views = v.get('view_count') or 0
                        ratio = views / subs if subs > 0 else 0
                        
                        if ratio > 2:
                            stars = "🔥🔥🔥"
                        elif ratio > 1:
                            stars = "⭐⭐"
                        else:
                            stars = "⭐"
                        
                        title = v.get('title', 'N/A')[:55]
                        
                        if show_debug:
                            lang_badge = f"[{v.get('_detected_language')}•{v.get('_detection_confidence')}]"
                        else:
                            lang_badge = ""
                        
                        with st.expander(f"#{idx} {stars} | {views:,} vues | {title}... {lang_badge}"):
                            col_img, col_info = st.columns([1, 2])
                            
                            with col_img:
                                thumb = v.get('thumbnail')
                                if thumb:
                                    st.image(thumb, width=200)
                            
                            with col_info:
                                st.write(f"**Chaîne :** {v.get('uploader', 'N/A')}")
                                st.write(f"**Abonnés :** {subs:,}")
                                st.write(f"**Likes :** {v.get('like_count', 0):,}")
                                st.write(f"**Durée :** {v.get('duration', 0) // 60} min")
                                st.write(f"**Lien :** [Regarder]({v.get('webpage_url', '#')})")
                                
                                if show_debug:
                                    st.write(f"**🔬 Détection :** `{v.get('_detected_language')}` (conf: {v.get('_detection_confidence')})")
                                    st.write(f"**📊 Source :** `{v.get('_detection_source')}`")
                                    debug_data = v.get('_detection_debug', {})
                                    if debug_data:
                                        st.json(debug_data)
                            
                            comments = v.get('comments') or []
                            if comments:
                                st.write("---")
                                st.write("**💬 Top commentaires :**")
                                for c in comments[:5]:
                                    st.write(f"• {c.get('text', '')[:150]}...")

            else:
                st.error(f"⚠️ **Aucune vidéo** trouvée correspondant aux critères.")
                
                if total_rejected > 0:
                    st.warning(f"""
🔍 **{total_rejected} vidéos rejetées** (Phase 1: {rejected_phase1} • Phase 2: {rejected_phase2})

💡 **Que faire ?**
1. Active le **mode debug** pour voir exactement pourquoi les vidéos sont rejetées
2. Vérifie que la langue sélectionnée ({language}) correspond à ta recherche
3. Si tu cherches un mot technique (ex: "Starlink"), certaines vidéos peuvent être dans plusieurs langues
                    """)
                    
                    if show_debug:
                        st.write("**Raisons des rejets Phase 1:**")
                        from collections import Counter
                        if rejection_reasons_p1:
                            for reason, count in Counter(rejection_reasons_p1).most_common():
                                st.write(f"  • {reason}: {count}x")

            st.session_state.search_history.append({
                'date': datetime.now().strftime('%d/%m %H:%M'),
                'kw': keywords_list,
                'lang': language,
                'found': len(all_videos_filtered),
                'rejected': total_rejected
            })
            
            progress_bar.progress(100)
            status.text("✅ Analyse terminée !")

        except Exception as e:
            st.error(f"❌ Erreur : {e}")
            import traceback
            st.code(traceback.format_exc())

# ============ HISTORIQUE ============
if st.session_state.search_history:
    with st.expander("📚 Historique des recherches"):
        for h in reversed(st.session_state.search_history[-10:]):
            rejected_info = f" (🚫 {h.get('rejected', 0)} rejetées)" if h.get('rejected', 0) > 0 else ""
            st.write(f"📅 {h['date']} | 🔍 {', '.join(h['kw'])} | 🌍 {h.get('lang', 'Auto')} | 📹 {h['found']} vidéos{rejected_info}")
