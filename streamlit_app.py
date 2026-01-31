"""
🚀 YouTube Keyword Research Tool - V16
- yt_dlp search
- Filtres: vues, date, durée
- Langue: heuristique title+desc (optionnel) OU via commentaires (optionnel)
- Scoring: ratio vues / abonnés (si dispo)
- Commentaires: PAS sous les vidéos
- À gauche: 1 fenêtre Ctrl+A avec PROMPT + 20 commentaires par vidéo (TOP likes si dispo)
"""

import streamlit as st
from yt_dlp import YoutubeDL
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import random
from typing import List, Dict, Optional, Tuple
import re
import traceback
import time

# ==========================================
# 📋 CONFIGURATION
# ==========================================

st.set_page_config(
    page_title="YouTube Research V16",
    layout="wide",
    initial_sidebar_state="expanded"
)

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Safari/537.36',
]

LANGUAGE_CONFIG = {
    "Auto (all languages)": {"hl": None, "gl": None, "code": None, "markers": []},
    "French": {
        "hl": "fr", "gl": "FR", "code": "fr",
        "markers": ["le","la","les","de","du","des","un","une","et","est","sont","dans","pour","sur","avec",
                    "qui","que","ce","cette","nous","vous","je","tu","il","elle","c'est","très","plus","mais"]
    },
    "English": {
        "hl": "en", "gl": "US", "code": "en",
        "markers": ["the","and","is","are","was","were","have","has","been","this","that","with","for","not","you"]
    },
    "Spanish": {
        "hl": "es", "gl": "ES", "code": "es",
        "markers": ["el","la","los","las","de","en","que","es","un","una","por","con","para","como","más","pero"]
    },
}

PROMPT_INTRO = (
    "analyse moi ces commentaires et relève les points suivant : "
    "les idées qui reviennet le plus souvent, propose moi 3 sujets qui marcheront sur base des commentaire "
    "et propose moi 3 sujets périphérique qui pourraient marcher par rapport aux commentaires !"
)

# ==========================================
# 🔤 LANGUE (HEURISTIQUE SIMPLE)
# ==========================================

def detect_language_simple(text: str) -> Optional[str]:
    if not text or len(text) < 5:
        return None
    text_lower = text.lower()
    words = set(re.findall(r'\b[a-zàâäéèêëïîôùûüçñ]+\b', text_lower))
    scores = {}
    for lang_name, config in LANGUAGE_CONFIG.items():
        if lang_name == "Auto (all languages)":
            continue
        markers = set(config.get("markers", []))
        matches = len(words & markers)
        if matches > 0:
            scores[config["code"]] = matches
    if not scores:
        return None
    return max(scores, key=scores.get)

def matches_language_text(text: str, target_lang: str, strict: bool) -> Tuple[bool, str]:
    if target_lang == "Auto (all languages)":
        return True, "Auto mode"
    if not text or len(text) < 20:
        return True, "Texte trop court (accepté)"
    target_config = LANGUAGE_CONFIG.get(target_lang)
    if not target_config:
        return True, "Langue non configurée (accepté)"
    target_code = target_config["code"]
    detected = detect_language_simple(text)
    if strict:
        if detected == target_code:
            return True, f"Langue détectée: {detected}"
        return False, f"Langue détectée: {detected}, attendu: {target_code}"
    else:
        if detected == target_code:
            return True, f"Langue détectée: {detected}"
        if detected is None:
            return True, "Langue non détectée (accepté)"
        return False, f"Langue détectée: {detected}, attendu: {target_code}"

# ==========================================
# 🎬 YT-DLP
# ==========================================

def search_youtube(keyword: str, max_results: int, target_lang: str) -> Tuple[List[Dict], List[str]]:
    logs = []
    if not keyword or not keyword.strip():
        return [], ["[WARN] Mot-clé vide"]

    opts = {
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "socket_timeout": 15,
        "http_headers": {"User-Agent": random.choice(USER_AGENTS)},
        "extract_flat": True,
    }

    lang_config = LANGUAGE_CONFIG.get(target_lang, {})
    if lang_config.get("gl"):
        opts["geo_bypass_country"] = lang_config["gl"]
    if lang_config.get("hl"):
        opts["http_headers"]["Accept-Language"] = f"{lang_config['hl']},{lang_config['hl']};q=0.9"

    query = f"ytsearch{max_results}:{keyword.strip()}"
    logs.append(f"[INFO] SEARCH: {query} lang={target_lang}")

    try:
        with YoutubeDL(opts) as ydl:
            res = ydl.extract_info(query, download=False)
        if not res:
            return [], logs + ["[ERROR] search result None"]

        entries = res.get("entries", []) or []
        vids = []
        for e in entries:
            if not e:
                continue
            vid = e.get("id")
            if not vid:
                continue
            vids.append(e)
        logs.append(f"[INFO] Found raw entries={len(entries)} valid={len(vids)}")
        return vids, logs
    except Exception as ex:
        return [], logs + [f"[ERROR] search: {ex}"]

def get_video_details(video_id: str) -> Tuple[Optional[Dict], List[str]]:
    logs = []
    if not video_id:
        return None, logs

    opts = {
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "socket_timeout": 20,
        "http_headers": {"User-Agent": random.choice(USER_AGENTS)},
        "skip_download": True,
        "getcomments": True,
    }

    try:
        url = f"https://www.youtube.com/watch?v={video_id}"
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if not info:
            return None, logs + [f"[ERROR] Info None {video_id}"]
        return info, logs
    except Exception as ex:
        return None, logs + [f"[ERROR] details {video_id}: {ex}"]

def pick_top_20_comments(info: Dict) -> List[Dict]:
    raw = info.get("comments") or []
    valid = [c for c in raw if isinstance(c, dict) and c.get("text")]
    # yt_dlp peut donner like_count ; si absent => 0
    valid.sort(key=lambda x: (x.get("like_count") or 0), reverse=True)
    return valid[:20]

def process_video(entry: Dict, params: Dict) -> Tuple[Optional[Dict], Dict]:
    stats = {"passed": 0, "filtered_views": 0, "filtered_date": 0, "filtered_duration": 0, "filtered_language": 0}
    vid = entry.get("id")
    if not vid:
        return None, stats

    info, _ = get_video_details(vid)
    if not info:
        return None, stats

    # vues
    views = info.get("view_count") or 0
    if views < params["min_views"]:
        stats["filtered_views"] = 1
        return None, stats

    # date
    if params["date_limit"]:
        up = info.get("upload_date")
        if up:
            try:
                d = datetime.strptime(up, "%Y%m%d")
                if d < params["date_limit"]:
                    stats["filtered_date"] = 1
                    return None, stats
            except ValueError:
                pass

    # durée
    dur = info.get("duration") or 0
    if params["min_duration"] == "2 min" and dur < 120:
        stats["filtered_duration"] = 1
        return None, stats
    if params["min_duration"] == "5 min" and dur < 300:
        stats["filtered_duration"] = 1
        return None, stats
    if params["min_duration"] == "10 min" and dur < 600:
        stats["filtered_duration"] = 1
        return None, stats

    # langue (sur texte OU commentaires selon option)
    if params["language"] != "Auto (all languages)":
        if params["lang_source"] == "Titre + Description":
            txt = f"{info.get('title','')} {(info.get('description') or '')[:500]}"
            ok, _ = matches_language_text(txt, params["language"], params["strict_language"])
            if not ok:
                stats["filtered_language"] = 1
                return None, stats
        else:
            # commentaires: on prend un échantillon et on détecte
            comms = pick_top_20_comments(info)
            sample = " ".join([(c.get("text") or "") for c in comms])[:1200]
            ok, _ = matches_language_text(sample, params["language"], params["strict_language"])
            if not ok:
                stats["filtered_language"] = 1
                return None, stats

    # scoring ratio
    subs = info.get("channel_follower_count") or 1
    if subs <= 0:
        subs = 1
    ratio = views / subs
    info["_ratio"] = ratio
    info["_stars"] = "⭐⭐⭐" if ratio >= 2 else ("⭐⭐" if ratio >= 1 else "⭐")

    # commentaires top 20
    info["comments"] = pick_top_20_comments(info)

    stats["passed"] = 1
    return info, stats

def sort_videos(videos: List[Dict]) -> List[Dict]:
    return sorted(videos, key=lambda v: v.get("_ratio", 0), reverse=True)

# ==========================================
# 🧠 BUILD LEFT WINDOW TEXT
# ==========================================

def build_left_text(videos: List[Dict]) -> str:
    out = []
    for idx, v in enumerate(videos, 1):
        title = v.get("title", "")
        url = v.get("webpage_url", "") or v.get("original_url", "")
        if not url:
            vid = v.get("id", "")
            url = f"https://www.youtube.com/watch?v={vid}"

        out.append(f"================ VIDEO {idx} ================\n")
        out.append(f"TITRE: {title}\n")
        out.append(f"LIEN: {url}\n\n")
        out.append(PROMPT_INTRO + "\n\n")
        out.append("COMMENTAIRES:\n")

        comms = v.get("comments", []) or []
        if comms:
            for c in comms:
                txt = (c.get("text") or "").replace("\n", " ").strip()
                out.append(f"- {txt}\n")
        else:
            out.append("- (aucun commentaire)\n")

        out.append("\n")
    return "".join(out)

# ==========================================
# 🎨 UI
# ==========================================

def render_sidebar() -> dict:
    st.sidebar.title("🔍 YouTube Research V16")

    keywords_text = st.sidebar.text_area("Mots-clés (1 par ligne)", height=80, placeholder="ice + trump\nmacron france")
    keywords = [k.strip() for k in keywords_text.split("\n") if k.strip()]

    st.sidebar.divider()
    language = st.sidebar.selectbox("Langue", list(LANGUAGE_CONFIG.keys()))
    strict_language = st.sidebar.checkbox("Filtre langue strict", value=True)

    lang_source = st.sidebar.selectbox("Source langue", ["Commentaires (top)", "Titre + Description"])

    min_views = st.sidebar.number_input("Vues minimum", value=100000, step=10000, min_value=0)
    min_duration = st.sidebar.selectbox("Durée minimum", ["Toutes", "2 min", "5 min", "10 min"])
    date_period = st.sidebar.selectbox("Période", ["Tout", "7 jours", "30 jours", "6 mois", "1 an"])

    date_limit = None
    if date_period == "7 jours":
        date_limit = datetime.now() - timedelta(days=7)
    elif date_period == "30 jours":
        date_limit = datetime.now() - timedelta(days=30)
    elif date_period == "6 mois":
        date_limit = datetime.now() - timedelta(days=180)
    elif date_period == "1 an":
        date_limit = datetime.now() - timedelta(days=365)

    st.sidebar.divider()
    videos_per_keyword = st.sidebar.slider("Vidéos par mot-clé", 5, 30, 15)
    max_workers = st.sidebar.slider("Threads", 1, 10, 5)

    return {
        "keywords": keywords,
        "language": language,
        "strict_language": strict_language,
        "lang_source": lang_source,
        "min_views": int(min_views),
        "min_duration": min_duration,
        "date_limit": date_limit,
        "videos_per_keyword": videos_per_keyword,
        "max_workers": max_workers,
    }

def render_video_card(video: Dict, idx: int):
    ratio = video.get("_ratio", 0)
    stars = video.get("_stars", "⭐")
    views = video.get("view_count", 0)
    title = video.get("title", "Sans titre")
    header = f"#{idx} {stars} | {ratio:.1f}x | {views:,} vues"

    with st.expander(header, expanded=(idx <= 3)):
        col1, col2 = st.columns([1, 2])
        with col1:
            thumb = video.get("thumbnail")
            if thumb:
                st.image(thumb, use_container_width=True)
        with col2:
            st.markdown(f"**{title}**")
            st.write(f"📺 {video.get('uploader', '?')}")
            st.write(f"👥 {video.get('channel_follower_count', 0):,} abonnés")
            st.write(f"👁️ {views:,} vues")
            st.write(f"📊 Ratio: **{ratio:.2f}x**")
            url = video.get("webpage_url", "") or f"https://www.youtube.com/watch?v={video.get('id','')}"
            st.link_button("▶️ YouTube", url)

def main():
    st.title("🚀 YouTube Research V16")
    st.caption("À gauche: PROMPT + 20 commentaires TOP par vidéo (Ctrl+A). À droite: vidéos.")

    params = render_sidebar()

    if st.sidebar.button("🚀 LANCER", type="primary", use_container_width=True):
        if not params["keywords"]:
            st.error("❌ Mets au moins un mot-clé.")
            return

        logs = []
        stats = {"search_results": 0, "passed": 0, "filtered_views": 0, "filtered_date": 0, "filtered_duration": 0, "filtered_language": 0}

        progress = st.progress(0)
        status = st.status("Recherche...", expanded=True)

        all_raw = []
        for i, kw in enumerate(params["keywords"]):
            status.write(f"🔍 Recherche: {kw}")
            entries, l = search_youtube(kw, params["videos_per_keyword"], params["language"])
            logs.extend(l)
            for e in entries:
                e["_source_keyword"] = kw
                all_raw.append(e)
            stats["search_results"] += len(entries)
            progress.progress((i + 1) / len(params["keywords"]) * 0.3)

        if not all_raw:
            st.error("Aucune vidéo trouvée.")
            st.text_area("Logs", "\n".join(logs[-200:]), height=240)
            return

        status.update(label="Analyse...", state="running")

        processed = []
        total = len(all_raw)
        done = 0

        with ThreadPoolExecutor(max_workers=params["max_workers"]) as ex:
            futures = [ex.submit(process_video, entry, params) for entry in all_raw]
            for f in as_completed(futures):
                info, stt = f.result()
                for k, v in stt.items():
                    stats[k] += v
                if info:
                    processed.append(info)
                done += 1
                progress.progress(0.3 + (done / total) * 0.6)

        processed = sort_videos(processed)
        progress.progress(1.0)
        status.update(label=f"✅ {len(processed)} vidéos validées", state="complete")

        # ---- UI RESULTS: left prompt/comments, right videos ----
        left, right = st.columns([1, 2])

        with left:
            st.subheader("📝 PROMPT + Commentaires (Ctrl+A)")
            txt = build_left_text(processed[:15])
            st.text_area("Copie-colle", value=txt, height=650)
            st.download_button("📥 Télécharger", data=txt, file_name="prompt_commentaires.txt")

        with right:
            st.subheader("📹 Vidéos")
            for idx, v in enumerate(processed[:15], 1):
                render_video_card(v, idx)

        st.divider()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Trouvées", stats["search_results"])
        c2.metric("✅ Validées", stats["passed"])
        c3.metric("Rejet vues", stats["filtered_views"])
        c4.metric("Rejet langue", stats["filtered_language"])

        st.subheader("📜 Logs (dernier 200)")
        st.text_area("", "\n".join(logs[-200:]), height=250)

if __name__ == "__main__":
    main()
