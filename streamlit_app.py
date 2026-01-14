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
# ✅ SYSTÈME DE DÉTECTION INTELLIGENT (3 NIVEAUX)
# ==========================================
def detect_language_with_confidence(info, use_comments=False):
    """
    Retourne (langue_détectée, niveau_confiance)
    Niveaux : "high" (>0.85), "medium" (0.60-0.85), "low" (<0.60), "unknown"
    """
    
    # ========================================
    # NIVEAU 1 : MÉTADONNÉES YOUTUBE (CONFIANCE ABSOLUE)
    # ========================================
    yt_lang = info.get('language')
    if yt_lang:
        lang_code = yt_lang[:2].lower()
        return lang_code, "high", "youtube_metadata"
    
    # ========================================
    # NIVEAU 2 : SOUS-TITRES (CONFIANCE HAUTE)
    # ========================================
    # Sous-titres automatiques générés par YouTube
    auto_captions = info.get('automatic_captions') or {}
    if auto_captions:
        first_lang = list(auto_captions.keys())[0]
        if first_lang:
            lang_code = first_lang[:2].lower()
            return lang_code, "high", "auto_captions"
    
    # Sous-titres manuels ajoutés par le créateur
    subtitles = info.get('subtitles') or {}
    if subtitles:
        first_lang = list(subtitles.keys())[0]
        if first_lang:
            lang_code = first_lang[:2].lower()
            return lang_code, "high", "manual_subtitles"
    
    # ========================================
    # NIVEAU 3 : ANALYSE TEXTUELLE (CONFIANCE VARIABLE)
    # ========================================
    texts_to_analyze = []
    
    # Titre (poids : important)
    title = info.get('title') or ""
    if title and len(title) > 20:
        texts_to_analyze.append(("title", title, 3))  # poids 3
    
    # Description (poids : moyen)
    description = info.get('description') or ""
    if description:
        clean_desc = re.sub(r'http\S+|#\S+|@\S+', '', description[:1500])
        if len(clean_desc) > 80:
            texts_to_analyze.append(("description", clean_desc, 2))  # poids 2
    
    # Commentaires (poids : très important pour la langue réelle)
    if use_comments:
        comments = info.get('comments') or []
        if comments:
            # ⚡ Analyser PLUS de commentaires (40 au lieu de 20)
            comment_texts = [c.get('text', '') for c in comments[:40] if len(c.get('text', '')) > 25]
            if comment_texts:
                combined_comments = " ".join(comment_texts[:20])
                texts_to_analyze.append(("comments", combined_comments, 5))  # poids 5 (le plus important)
    
    # Détection sur chaque source
    detections = []
    for source_name, text, weight in texts_to_analyze:
        # Nettoyer
        clean_text = re.sub(r'[^\w\s\u00C0-\u017F\u0400-\u04FF]', ' ', text)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        
        if len(clean_text) > 30:
            try:
                detected_langs = detect_langs(clean_text)
                if detected_langs:
                    best = detected_langs[0]
                    # Pondérer la confiance par le poids de la source
                    weighted_prob = best.prob * (weight / 5.0)  # Normaliser sur 5
                    detections.append({
                        'lang': best.lang,
                        'prob': best.prob,
                        'weighted_prob': weighted_prob,
                        'source': source_name,
                        'weight': weight
                    })
            except LangDetectException:
                pass
    
    if detections:
        # Calculer un score global pour chaque langue détectée
        lang_scores = {}
        for d in detections:
            lang = d['lang']
            if lang not in lang_scores:
                lang_scores[lang] = {'total_weighted': 0, 'max_prob': 0, 'sources': []}
            lang_scores[lang]['total_weighted'] += d['weighted_prob']
            lang_scores[lang]['max_prob'] = max(lang_scores[lang]['max_prob'], d['prob'])
            lang_scores[lang]['sources'].append(d['source'])
        
        # Trouver la langue avec le meilleur score
        best_lang = max(lang_scores.items(), key=lambda x: x[1]['total_weighted'])
        lang_code = best_lang[0]
        max_prob = best_lang[1]['max_prob']
        sources = best_lang[1]['sources']
        
        # Déterminer le niveau de confiance
        if max_prob >= 0.85 and len(sources) >= 2:
            confidence = "high"
        elif max_prob >= 0.65 or len(sources) >= 2:
            confidence = "medium"
        else:
            confidence = "low"
        
        source_info = f"detected_from_{'+'.join(set(sources))}"
        return lang_code, confidence, source_info
    
    return None, "unknown", "no_data"

def is_valid_language(info, target_lang, phase="phase1"):
    """
    Vérifie si une vidéo correspond à la langue cible.
    
    Phase 1 (sans commentaires) : PERMISSIF - rejette seulement si TRÈS SÛR que c'est faux
    Phase 2 (avec commentaires) : MODÉRÉ - rejette si confiance moyenne+ que c'est faux
    """
    if target_lang == "Auto (toutes langues)":
        return True
    
    config = LANGUAGE_CONFIG.get(target_lang)
    if not config or not config['code']:
        return True
    
    target_code = config['code']
    
    # Détecter avec le bon niveau d'analyse
    use_comments = (phase == "phase2")
    detected_lang, confidence, source = detect_language_with_confidence(info, use_comments)
    
    # Stocker pour debug
    info['_detected_language'] = detected_lang
    info['_detection_confidence'] = confidence
    info['_detection_source'] = source
    
    # ========================================
    # STRATÉGIE DE FILTRAGE PAR PHASE
    # ========================================
    
    if phase == "phase1":
        # 🟢 PHASE 1 : TRÈS PERMISSIF
        # On rejette SEULEMENT si on est TRÈS SÛR que c'est la mauvaise langue
        if detected_lang is None:
            return True  # Pas de détection = on garde (sera vérifié en Phase 2)
        
        if detected_lang.startswith(target_code):
            return True  # Match parfait
        
        # Rejeter seulement si confiance HAUTE et langue différente
        if confidence == "high":
            # Exception : certaines langues proches (es/pt, fr/it)
            if target_code == "es" and detected_lang == "pt":
                return True  # Espagnol/Portugais proches
            if target_code == "pt" and detected_lang == "es":
                return True
            if target_code == "fr" and detected_lang in ["it", "es"]:
                return True  # Langues latines
            return False  # Clairement pas la bonne langue
        
        return True  # Confiance basse/moyenne = on garde pour Phase 2
    
    elif phase == "phase2":
        # 🟡 PHASE 2 : MODÉRÉ (on a plus d'infos via commentaires)
        if detected_lang is None:
            return True  # Si impossible de détecter même avec commentaires, on garde (mieux vaut un faux positif)
        
        if detected_lang.startswith(target_code):
            return True  # Match parfait
        
        # Rejeter si confiance moyenne+ et langue clairement différente
        if confidence in ["high", "medium"]:
            # Exceptions pour langues proches
            if target_code == "es" and detected_lang in ["pt", "ca"]:  # catalan proche espagnol
                return True
            if target_code == "pt" and detected_lang == "es":
                return True
            if target_code == "fr" and detected_lang in ["it", "es", "pt"]:
                return True
            if target_code == "en" and detected_lang in ["en-us", "en-gb"]:
                return True
            
            # Langue clairement différente avec bonne confiance = rejeter
            return False
        
        return True  # Confiance basse = on garde (doute = bénéfice au contenu)
    
    return True  # Fallback : garder

# ==========================================
# ✅ FONCTION DE RECHERCHE
# ==========================================
def build_search_query(keyword, target_lang):
    """
    Construit une requête de recherche optimisée pour la langue cible.
    """
    config = LANGUAGE_CONFIG.get(target_lang, {})
    query = f"ytsearch50:{keyword}"
    return query, config.get('yt_lang'), config.get('yt_region')

def get_ydl_options(target_lang, get_comments=False):
    """
    Retourne les options yt-dlp configurées pour la langue cible.
    """
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
    
    if get_comments:
        opts['getcomments'] = True
        opts['writesubtitles'] = True
        opts['writeautomaticsub'] = True
        opts['skip_download'] = True
    else:
        opts['writesubtitles'] = True
        opts['writeautomaticsub'] = True
        opts['skip_download'] = True
    
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
    st.sidebar.info(f"🔬 Détection intelligente à 3 niveaux : métadonnées YouTube, sous-titres, analyse textuelle des commentaires.")

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

show_debug = st.sidebar.checkbox("🔧 Afficher infos de détection", value=False)

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
                # 🚀 PHASE 1 : EXTRACTION RAPIDE SANS COMMENTAIRES
                # ==========================================
                status.text(f"⚡ Phase 1 : Extraction rapide de {len(entries)} vidéos pour '{kw}'...")
                progress_bar.progress(int((kw_idx / total_keywords) * 20) + 10)

                def fetch_metadata_only(vid):
                    """Extraction légère : métadonnées + sous-titres seulement"""
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

                status.text(f"🔬 Filtrage Phase 1 de {len(metadata_infos)} vidéos...")
                progress_bar.progress(int((kw_idx / total_keywords) * 20) + 15)

                # Filtrage Phase 1 (PERMISSIF)
                candidates = []
                for info in metadata_infos:
                    if not info:
                        continue
                    
                    # 1. FILTRE LANGUE (PERMISSIF - rejette seulement si TRÈS SÛR)
                    if not is_valid_language(info, language, phase="phase1"):
                        rejected_phase1 += 1
                        continue
                    
                    # 2. FILTRE DURÉE
                    v_dur = info.get('duration') or 0
                    if min_duration == "Minimum 2 min" and v_dur < 120:
                        continue
                    if min_duration == "Minimum 5 min" and v_dur < 300:
                        continue

                    # 3. FILTRE VUES
                    v_views = info.get('view_count') or 0
                    if not any(mn <= v_views <= mx for mn, mx in selected_views):
                        continue

                    # 4. FILTRE DATE
                    if date_limit:
                        upload_date = info.get('upload_date')
                        if upload_date:
                            try:
                                v_date = datetime.strptime(upload_date, '%Y%m%d')
                                if v_date < date_limit:
                                    continue
                            except ValueError:
                                pass

                    # 5. FILTRE ENGAGEMENT
                    if use_engagement:
                        likes = info.get('like_count') or 0
                        views = info.get('view_count') or 1
                        engagement_ratio = (likes / views) * 100
                        if engagement_ratio < min_engagement:
                            continue

                    candidates.append(info)

                # ==========================================
                # 🚀 PHASE 2 : EXTRACTION COMMENTAIRES
                # ==========================================
                if candidates:
                    status.text(f"💬 Phase 2 : Extraction commentaires ({len(candidates)} vidéos qualifiées)...")
                    progress_bar.progress(int((kw_idx / total_keywords) * 20) + 18)

                    def fetch_comments_only(info):
                        """Récupère les commentaires pour une vidéo déjà validée"""
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
                                    # Validation Phase 2 (MODÉRÉE - plus d'infos)
                                    if is_valid_language(enriched_info, language, phase="phase2"):
                                        enriched_info['search_keyword'] = kw
                                        all_videos_filtered.append(enriched_info)
                                    else:
                                        rejected_phase2 += 1
                            except Exception:
                                pass

            progress_bar.progress(90)

            # === AFFICHAGE RÉSULTATS ===
            total_rejected = rejected_phase1 + rejected_phase2
            
            if all_videos_filtered:
                st.success(f"✅ {len(all_videos_filtered)} vidéos trouvées en {language}.")
                if total_rejected > 0 and language != "Auto (toutes langues)":
                    st.info(f"🔬 {total_rejected} vidéos rejetées (Phase 1: {rejected_phase1}, Phase 2: {rejected_phase2})")
                
                left_col, right_col = st.columns([1, 2])

                # GAUCHE : LE PROMPT COMPLET
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
                            data_blob += f"[DEBUG] Langue: {v.get('_detected_language', 'N/A')} | Confiance: {v.get('_detection_confidence', 'N/A')} | Source: {v.get('_detection_source', 'N/A')}\n"
                        
                        comments = v.get('comments') or []
                        if comments:
                            data_blob += f"\nTOP COMMENTAIRES ({len(comments[:15])} affichés):\n"
                            for c in comments[:15]:
                                likes = c.get('like_count', 0)
                                text = c.get('text', '')[:200]
                                data_blob += f"  • [{likes} ❤️] {text}\n"
                    
                    st.text_area("Copie pour ChatGPT/Claude :", value=prompt_expert + data_blob, height=500)

                # DROITE : LES VIDÉOS
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
                        
                        detected_lang = v.get('_detected_language', '?')
                        confidence = v.get('_detection_confidence', '?')
                        source = v.get('_detection_source', '?')
                        
                        lang_badge = f"[{detected_lang.upper()} • {confidence}]" if show_debug else ""
                        
                        with st.expander(f"#{idx} {stars} | {views:,} vues | {v.get('title', 'N/A')[:55]}... {lang_badge}"):
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
                                    st.write(f"**🔬 Langue :** `{detected_lang}` (confiance: {confidence})")
                                    st.write(f"**📊 Source :** `{source}`")
                            
                            comments = v.get('comments') or []
                            if comments:
                                st.write("---")
                                st.write("**💬 Top commentaires :**")
                                for c in comments[:5]:
                                    st.write(f"• {c.get('text', '')[:150]}...")

            else:
                st.warning(f"⚠️ Aucune vidéo trouvée correspondant aux critères.")
                if total_rejected > 0:
                    st.info(f"🔬 {total_rejected} vidéos rejetées (Phase 1: {rejected_phase1} • Phase 2: {rejected_phase2})")
                    st.info("💡 **Conseil** : Le filtre est peut-être trop strict. Active le mode debug pour voir les détections.")

            st.session_state.search_history.append({
                'date': datetime.now().strftime('%d/%m %H:%M'),
                'kw': keywords_list,
                'lang': language,
                'found': len(all_videos_filtered),
                'rejected': total_rejected
            })
            
            progress_bar.progress(100)
            status.text("✅ Analyse terminée.")

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
