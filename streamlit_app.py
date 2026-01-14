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
# ✅ NOUVEAU MOTEUR DE DÉTECTION DE LANGUE (ROBUSTE)
# ==========================================
def detect_video_language(info):
    """
    Détecte la langue d'une vidéo en analysant plusieurs sources.
    Retourne le code langue (ex: 'fr', 'es', 'en') ou None si indétectable.
    """
    texts_to_analyze = []
    
    # 1. Titre (priorité haute)
    title = info.get('title') or ""
    if title:
        texts_to_analyze.append(title)
    
    # 2. Description (les 1000 premiers caractères)
    description = info.get('description') or ""
    if description:
        # Nettoyer les URLs et hashtags
        clean_desc = re.sub(r'http\S+|#\S+|@\S+', '', description[:1000])
        if len(clean_desc) > 50:
            texts_to_analyze.append(clean_desc)
    
    # 3. Commentaires (très fiables pour la langue)
    comments = info.get('comments') or []
    comment_texts = []
    for c in comments[:20]:  # Analyser jusqu'à 20 commentaires
        text = c.get('text', '')
        if text and len(text) > 20:
            comment_texts.append(text)
    if comment_texts:
        texts_to_analyze.append(" ".join(comment_texts[:10]))
    
    # 4. Métadonnées YouTube (si disponibles)
    yt_lang = info.get('language')
    if yt_lang:
        return yt_lang[:2].lower()  # Retourne 'fr', 'es', etc.
    
    # 5. Sous-titres automatiques (indicateur fort)
    auto_captions = info.get('automatic_captions') or {}
    subtitles = info.get('subtitles') or {}
    
    # Si des sous-titres existent, la première langue est souvent la langue originale
    if auto_captions:
        first_lang = list(auto_captions.keys())[0] if auto_captions else None
        if first_lang:
            return first_lang[:2].lower()
    
    # 6. Détection via langdetect sur les textes collectés
    if texts_to_analyze:
        combined_text = " ".join(texts_to_analyze)
        # Nettoyer le texte
        combined_text = re.sub(r'[^\w\s\u00C0-\u017F]', ' ', combined_text)
        combined_text = re.sub(r'\s+', ' ', combined_text).strip()
        
        if len(combined_text) > 30:  # Minimum pour une détection fiable
            try:
                detected = detect_langs(combined_text)
                if detected:
                    # Prendre la langue avec la plus haute probabilité
                    best = detected[0]
                    if best.prob > 0.5:  # Seuil de confiance
                        return best.lang
            except LangDetectException:
                pass
    
    return None

def is_valid_language(info, target_lang):
    """
    Vérifie si une vidéo correspond à la langue cible.
    """
    if target_lang == "Auto (toutes langues)":
        return True
    
    config = LANGUAGE_CONFIG.get(target_lang)
    if not config or not config['code']:
        return True
    
    target_code = config['code']
    detected_lang = detect_video_language(info)
    
    # Debug info (optionnel, peut être affiché dans l'interface)
    info['_detected_language'] = detected_lang
    
    if detected_lang:
        # Match exact ou variantes (ex: 'es' match 'es', 'es-419', 'es-mx')
        return detected_lang.startswith(target_code)
    
    # Si on ne peut pas détecter, on rejette par sécurité
    # (évite les faux positifs en anglais)
    return False

# ==========================================
# ✅ FONCTION DE RECHERCHE AMÉLIORÉE
# ==========================================
def build_search_query(keyword, target_lang):
    """
    Construit une requête de recherche optimisée pour la langue cible.
    """
    config = LANGUAGE_CONFIG.get(target_lang, {})
    
    # Recherche de base
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
        'socket_timeout': 15,
    }
    
    # Ajouter les paramètres de langue/région si spécifiés
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

# Info sur la détection de langue
if language != "Auto (toutes langues)":
    st.sidebar.info(f"🔬 Détection intelligente activée : analyse du titre, description, commentaires et sous-titres pour garantir des résultats en {language}.")

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

# Option de debug
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
        rejected_count = 0
        
        try:
            total_keywords = len(keywords_list)
            
            for kw_idx, kw in enumerate(keywords_list):
                status.text(f"🔍 Recherche YouTube : {kw} ({kw_idx + 1}/{total_keywords})")
                progress_bar.progress(int((kw_idx / total_keywords) * 30))
                
                # Construire la requête avec paramètres de langue
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
                
                status.text(f"📥 Extraction détaillée de {len(entries)} vidéos pour '{kw}'...")
                progress_bar.progress(int((kw_idx / total_keywords) * 30) + 15)

                # Extraction complète en parallèle
                def fetch_full(vid):
                    if not vid or not vid.get('id'):
                        return None
                    try:
                        opts = get_ydl_options(language, get_comments=True)
                        with YoutubeDL(opts) as ydl_full:
                            return ydl_full.extract_info(
                                f"https://www.youtube.com/watch?v={vid['id']}", 
                                download=False
                            )
                    except Exception:
                        return None

                with ThreadPoolExecutor(max_workers=8) as executor:
                    futures = [executor.submit(fetch_full, vid) for vid in entries]
                    full_infos = []
                    for future in as_completed(futures):
                        try:
                            result = future.result()
                            if result:
                                full_infos.append(result)
                        except Exception:
                            pass

                status.text(f"🔬 Filtrage par langue : {language}...")
                progress_bar.progress(int((kw_idx / total_keywords) * 30) + 25)

                for info in full_infos:
                    if not info:
                        continue
                    
                    # 1. FILTRE LANGUE (NOUVEAU SYSTÈME ROBUSTE)
                    if not is_valid_language(info, language):
                        rejected_count += 1
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

                    info['search_keyword'] = kw
                    all_videos_filtered.append(info)

            progress_bar.progress(90)

            # === AFFICHAGE RÉSULTATS ===
            if all_videos_filtered:
                st.success(f"✅ {len(all_videos_filtered)} vidéos trouvées en {language}.")
                if rejected_count > 0 and language != "Auto (toutes langues)":
                    st.info(f"🔬 {rejected_count} vidéos rejetées car pas en {language}")
                
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
                            data_blob += f"[DEBUG] Langue détectée: {v.get('_detected_language', 'N/A')}\n"
                        
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
                        
                        # Score de performance
                        if ratio > 2:
                            stars = "🔥🔥🔥"
                        elif ratio > 1:
                            stars = "⭐⭐"
                        else:
                            stars = "⭐"
                        
                        detected_lang = v.get('_detected_language', '?')
                        lang_badge = f"[{detected_lang.upper()}]" if show_debug else ""
                        
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
                                    st.write(f"**🔬 Langue détectée :** `{detected_lang}`")
                            
                            # Afficher quelques commentaires
                            comments = v.get('comments') or []
                            if comments:
                                st.write("---")
                                st.write("**💬 Top commentaires :**")
                                for c in comments[:5]:
                                    st.write(f"• {c.get('text', '')[:150]}...")

            else:
                st.warning(f"⚠️ Aucune vidéo trouvée correspondant aux critères.")
                if rejected_count > 0:
                    st.info(f"🔬 {rejected_count} vidéos ont été rejetées car elles n'étaient pas en {language}")

            # SAUVEGARDE HISTORIQUE
            st.session_state.search_history.append({
                'date': datetime.now().strftime('%d/%m %H:%M'),
                'kw': keywords_list,
                'lang': language,
                'found': len(all_videos_filtered),
                'rejected': rejected_count
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
