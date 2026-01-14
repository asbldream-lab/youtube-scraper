import streamlit as st
from yt_dlp import YoutubeDL
import json
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import re

# ==========================================
# ✅ INSTALLATION ET IMPORT ROBUSTE
# ==========================================
try:
    from langdetect import detect, LangDetectException
except ImportError:
    import subprocess
    st.warning("Installation de la librairie de langue en cours...")
    subprocess.check_call(['pip', 'install', 'langdetect'])
    from langdetect import detect, LangDetectException

# ==========================================
# ✅ CONFIGURATION
# ==========================================
st.set_page_config(page_title="YouTube Scraper Pro", layout="wide")
st.title("🚀 YouTube Keyword Research Tool PRO")

if 'search_history' not in st.session_state:
    st.session_state.search_history = []

# Mots-clés "stop words" pour forcer YouTube à trouver la bonne langue
LANGUAGE_RULES = {
    "Auto (toutes langues)": {"code": None, "helpers": []},
    "Français": {"code": "fr", "helpers": ["le", "la", "et", "est", "dans", "pour"]},
    "Anglais": {"code": "en", "helpers": ["the", "and", "is", "to", "in", "for"]},
    "Espagnol": {"code": "es", "helpers": ["el", "la", "y", "en", "es", "por"]},
}

# ==========================================
# ✅ FONCTION DE VALIDATION (CŒUR DU SYSTÈME)
# ==========================================
def validate_language(info, target_lang_name):
    """
    Vérifie si la vidéo correspond à la langue demandée.
    Rapide : Analyse uniquement Titre + Description.
    """
    if target_lang_name == "Auto (toutes langues)":
        return True

    target_code = LANGUAGE_RULES[target_lang_name]["code"]
    
    # 1. Construction du texte d'analyse
    title = info.get('title', '')
    desc = info.get('description', '')
    # On répète le titre pour lui donner plus de poids
    full_text = f"{title} {title} {desc[:500]}"
    
    # 2. Nettoyage basique
    full_text = re.sub(r'http\S+', '', full_text)
    
    # 3. Détection via langdetect
    try:
        detected = detect(full_text)
        if detected == target_code:
            return True
    except LangDetectException:
        # Si le texte est trop court (ex: juste un emoji), on passe à l'étape suivante
        pass

    # 4. RATTAPAGE (Si langdetect échoue ou doute)
    # On vérifie manuellement la présence de mots clés courants
    full_text_lower = full_text.lower()
    helpers = LANGUAGE_RULES[target_lang_name]["helpers"]
    
    # Compte combien de mots communs (le, la, et...) sont présents
    score = sum(1 for word in helpers if f" {word} " in full_text_lower)
    
    # S'il y a au moins 2 mots de liaison typiques, on accepte
    if score >= 2:
        return True

    return False

# ============ SIDEBAR ============
st.sidebar.header("⚙️ Paramètres")

keywords_input = st.sidebar.text_area(
    "🔍 Mots-clés (un par ligne):",
    placeholder="guerre irak\nstarlink",
    height=100
)
keywords_list = [k.strip() for k in keywords_input.split('\n') if k.strip()]

language = st.sidebar.selectbox("🌍 Langue:", list(LANGUAGE_RULES.keys()))

st.sidebar.write("### 👁️ Vues & Durée")
col1, col2 = st.sidebar.columns(2)
with col1:
    v_min = st.number_input("Vues Min", value=10000, step=5000)
with col2:
    min_duration = st.radio("Durée Min", ["Toutes", "2 min", "5 min"])

date_filter = st.sidebar.selectbox(
    "📅 Période:",
    ["Toutes", "7 derniers jours", "30 derniers jours", "6 derniers mois", "1 an"]
)

# ============ MAIN LOGIC ============
if st.sidebar.button("🚀 Lancer l'analyse", use_container_width=True):
    if not keywords_list:
        st.error("❌ Ajoute au moins un mot-clé !")
    else:
        progress_bar = st.progress(0)
        status = st.empty()
        all_videos = []
        
        # Calcul Date
        date_limit = None
        if date_filter != "Toutes":
            days = {"7 derniers jours": 7, "30 derniers jours": 30, "6 derniers mois": 180, "1 an": 365}
            date_limit = datetime.now() - timedelta(days=days[date_filter])

        try:
            total = len(keywords_list)
            for i, kw in enumerate(keywords_list):
                status.markdown(f"### 🔍 Recherche : **{kw}**")
                
                # --- ASTUCE BOOLEAN SEARCH ---
                # On force YouTube à chercher le mot clé ET des mots de la langue
                helpers = LANGUAGE_RULES[language]["helpers"]
                if helpers:
                    # Crée une requête type : starlink ("le" | "la" | "et")
                    # Cela force YouTube à prioriser cette langue
                    helpers_str = " | ".join([f'"{h}"' for h in helpers[:3]])
                    search_query = f'{kw} ({helpers_str})'
                else:
                    search_query = kw

                # 1. Extraction Rapide (Sans commentaires pour l'instant)
                ydl_opts = {
                    'quiet': True,
                    'extract_flat': True, # Extrêmement rapide
                    'ignoreerrors': True,
                    'ytsearch_date': True # Aide au filtrage date
                }

                with YoutubeDL(ydl_opts) as ydl:
                    # On demande 50 résultats car on va en filtrer
                    res = ydl.extract_info(f"ytsearch50:{search_query}", download=False)
                    entries = res.get('entries', [])

                # 2. Traitement Parallèle
                def process_video(entry):
                    if not entry: return None
                    
                    # Filtre Rapide : Titre
                    if not validate_language(entry, language):
                        return None
                        
                    # Filtre : Vues
                    if entry.get('view_count', 0) < v_min:
                        return None
                        
                    # Filtre : Durée (approximatif sur extract_flat, précis après)
                    # Note: extract_flat ne donne pas toujours la durée exacte, on vérifie après si besoin
                    
                    # Si tout est bon, on récupère les détails + commentaires (limités)
                    real_url = f"https://www.youtube.com/watch?v={entry['id']}"
                    
                    full_opts = {
                        'quiet': True,
                        'getcomments': True,
                        'max_comments': 10, # LIMITÉ À 10 POUR LA VITESSE !
                        'skip_download': True,
                        'ignoreerrors': True
                    }
                    
                    try:
                        with YoutubeDL(full_opts) as ydl_full:
                            info = ydl_full.extract_info(real_url, download=False)
                            
                            # Filtre Date Précis
                            if date_limit:
                                upload_date = info.get('upload_date')
                                if upload_date and datetime.strptime(upload_date, '%Y%m%d') < date_limit:
                                    return None
                                    
                            # Filtre Durée Précis
                            dur = info.get('duration', 0)
                            if min_duration == "2 min" and dur < 120: return None
                            if min_duration == "5 min" and dur < 300: return None
                            
                            return info
                    except:
                        return None

                # Lancement des threads
                status.text(f"⚡ Analyse approfondie de {len(entries)} candidats...")
                with ThreadPoolExecutor(max_workers=10) as executor:
                    futures = [executor.submit(process_video, vid) for vid in entries]
                    for f in as_completed(futures):
                        result = f.result()
                        if result:
                            result['keyword'] = kw
                            all_videos.append(result)

                progress_bar.progress((i + 1) / total)

            # === AFFICHAGE ===
            status.empty()
            if all_videos:
                st.success(f"✅ {len(all_videos)} vidéos qualifiées trouvées !")
                
                # Zone de copie pour ChatGPT
                prompt_text = f"Analyse ces vidéos pour le sujet '{keywords_list[0]}' (Langue: {language}).\n\n"
                for v in all_videos:
                    prompt_text += f"=== {v['title']} ===\n"
                    prompt_text += f"Lien: {v['webpage_url']}\n"
                    prompt_text += f"Description: {v.get('description', '')[:300]}...\n"
                    comments = v.get('comments', [])
                    if comments:
                        prompt_text += "Commentaires clés:\n"
                        for c in comments:
                            prompt_text += f"- {c.get('text', '').replace('\n', ' ')}\n"
                    prompt_text += "\n"
                
                st.text_area("📋 Copier ce prompt pour l'IA :", value=prompt_text, height=300)

                # Affichage Visuel
                for v in all_videos:
                    with st.expander(f"{v['view_count']:,} vues | {v['title']}"):
                        c1, c2 = st.columns([1, 3])
                        with c1:
                            st.image(v.get('thumbnail'))
                        with c2:
                            st.write(f"**Chaîne:** {v.get('uploader')}")
                            st.write(f"**Lien:** [Voir sur YouTube]({v['webpage_url']})")
                            st.write(f"**Likes:** {v.get('like_count', 0):,}")

            else:
                st.warning("Aucune vidéo trouvée avec ces critères stricts.")

        except Exception as e:
            st.error(f"Une erreur est survenue : {e}")
