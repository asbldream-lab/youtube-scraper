"""
🚀 YouTube Keyword Research Tool PRO - V10
- Recherche: 5 pages max via YouTube Data API (pagination officielle pageToken)
- Filtres: AND avec "+", langue PROUVÉE via snippet.defaultAudioLanguage, min vues, durée, date
- Scoring: vues / abonnés (subscriberCount) => surperformance
- Commentaires: 20 par vidéo, CHARGEMENT À LA DEMANDE (pour rester rapide)
Notes:
- Impossible de "garantir" 10s si l'API répond lentement, mais on:
  * réduit le payload avec fields=
  * évite les appels commentaires au chargement initial
"""

import re
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple, Set

import streamlit as st
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# =============================
# CONFIG
# =============================

st.set_page_config(page_title="YouTube Research V10", layout="wide", initial_sidebar_state="expanded")

DEADLINE_SECONDS = 10.0  # budget "best effort" pour éviter de s'enliser
DEFAULT_PAGES = 5
DEFAULT_PER_PAGE = 20  # 5 pages * 20 = ~100 résultats par mot-clé (raisonnable + rapide)

LANGUAGE_CONFIG = {
    "Auto (no proof)": {"code": None, "relevanceLanguage": None, "regionCode": None},
    "French": {"code": "fr", "relevanceLanguage": "fr", "regionCode": "FR"},
    "English": {"code": "en", "relevanceLanguage": "en", "regionCode": "US"},
    "Spanish": {"code": "es", "relevanceLanguage": "es", "regionCode": "ES"},
}

ISO_DURATION_RE = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")


# =============================
# Helpers
# =============================

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def parse_iso8601_duration_to_seconds(d: str) -> int:
    if not d:
        return 0
    m = ISO_DURATION_RE.match(d.strip())
    if not m:
        return 0
    h = int(m.group(1) or 0)
    mi = int(m.group(2) or 0)
    s = int(m.group(3) or 0)
    return h * 3600 + mi * 60 + s

def rfc3339_to_dt(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        if s.endswith("Z"):
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        return datetime.fromisoformat(s)
    except ValueError:
        return None

def parse_and_tokens(query: str) -> List[str]:
    """
    "ice + trump" => ["ice","trump"] ; support des guillemets:
    '"donald trump" + ice' => ["donald trump","ice"]
    """
    if not query:
        return []
    q = query.strip()
    quoted = re.findall(r'"([^"]+)"', q)
    q_wo_quotes = re.sub(r'"[^"]+"', "", q)
    parts = [p.strip() for p in re.split(r"\s*\+\s*", q_wo_quotes) if p.strip()]
    tokens = [*quoted, *parts]
    return [t.lower() for t in tokens if t.strip()]

def tokens_all_present(text: str, tokens: List[str]) -> bool:
    t = (text or "").lower()
    return all(tok in t for tok in tokens)

def stars_from_ratio(ratio: Optional[float]) -> str:
    if ratio is None:
        return "?"
    if ratio >= 5:
        return "⭐⭐⭐🔥"
    if ratio >= 2:
        return "⭐⭐⭐"
    if ratio >= 1:
        return "⭐⭐"
    return "⭐"


# =============================
# YouTube client
# =============================

@st.cache_resource(show_spinner=False)
def yt_client():
    api_key = st.secrets.get("YOUTUBE_API_KEY")
    if not api_key:
        raise RuntimeError("Clé API manquante: ajoute YOUTUBE_API_KEY dans .streamlit/secrets.toml")
    return build("youtube", "v3", developerKey=api_key)


# =============================
# API calls (optimisés via fields=)
# =============================

def api_search_video_ids(
    query: str,
    pages: int,
    per_page: int,
    relevance_language: Optional[str],
    region_code: Optional[str],
    deadline_t: float,
    logs: List[str],
) -> List[str]:
    yt = yt_client()
    ids: List[str] = []
    page_token: Optional[str] = None

    # Le "+" n'est pas un AND fiable côté YouTube => on cherche large,
    # puis on impose AND ensuite sur title/description.
    q_for_api = query.replace("+", " ").strip()

    for p in range(pages):
        if time.monotonic() > deadline_t:
            logs.append("[WARN] Deadline atteinte pendant la recherche (pagination interrompue).")
            break

        try:
            req = yt.search().list(
                part="id",
                q=q_for_api,
                type="video",
                maxResults=per_page,
                pageToken=page_token,
                relevanceLanguage=relevance_language,
                regionCode=region_code,
                fields="nextPageToken,items/id/videoId",  # ✅ payload minimal
            )
            res = req.execute()
        except HttpError as ex:
            logs.append(f"[ERROR] search.list page {p+1}: {ex}")
            break

        items = res.get("items", []) or []
        ids.extend([(it.get("id") or {}).get("videoId") for it in items if (it.get("id") or {}).get("videoId")])

        page_token = res.get("nextPageToken")
        logs.append(f"[INFO] search page {p+1}: +{len(items)} (nextPageToken={'YES' if page_token else 'NO'})")
        if not page_token:
            break

    # unique + ordre
    seen: Set[str] = set()
    out: List[str] = []
    for vid in ids:
        if vid not in seen:
            out.append(vid)
            seen.add(vid)
    return out

def api_videos_list(video_ids: List[str], deadline_t: float, logs: List[str]) -> Dict[str, dict]:
    yt = yt_client()
    out: Dict[str, dict] = {}

    # chunks de 50 (limite API)
    for i in range(0, len(video_ids), 50):
        if time.monotonic() > deadline_t:
            logs.append("[WARN] Deadline atteinte pendant videos.list (incomplet).")
            break

        chunk = video_ids[i:i+50]
        try:
            req = yt.videos().list(
                part="snippet,statistics,contentDetails",
                id=",".join(chunk),
                fields=(
                    "items("
                    "id,"
                    "snippet(title,description,channelId,channelTitle,publishedAt,defaultAudioLanguage,thumbnails),"
                    "statistics(viewCount),"
                    "contentDetails(duration)"
                    ")"
                ),
            )
            res = req.execute()
        except HttpError as ex:
            logs.append(f"[ERROR] videos.list: {ex}")
            continue

        for it in res.get("items", []) or []:
            out[it["id"]] = it

    return out

def api_channels_list(channel_ids: List[str], deadline_t: float, logs: List[str]) -> Dict[str, dict]:
    yt = yt_client()
    out: Dict[str, dict] = {}

    for i in range(0, len(channel_ids), 50):
        if time.monotonic() > deadline_t:
            logs.append("[WARN] Deadline atteinte pendant channels.list (incomplet).")
            break

        chunk = channel_ids[i:i+50]
        try:
            req = yt.channels().list(
                part="statistics",
                id=",".join(chunk),
                fields="items(id,statistics(subscriberCount,hiddenSubscriberCount))",
            )
            res = req.execute()
        except HttpError as ex:
            logs.append(f"[ERROR] channels.list: {ex}")
            continue

        for it in res.get("items", []) or []:
            out[it["id"]] = it
    return out

@st.cache_data(show_spinner=False, ttl=3600)
def api_fetch_comments_20_cached(video_id: str) -> List[str]:
    """
    Cache 1h => quand tu cliques plusieurs fois, c'est instant.
    """
    yt = yt_client()
    try:
        req = yt.commentThreads().list(
            part="snippet",
            videoId=video_id,
            maxResults=20,
            order="relevance",
            textFormat="plainText",
            fields="items(snippet(topLevelComment(snippet(textDisplay,likeCount))))"
        )
        res = req.execute()
    except HttpError:
        return []

    texts: List[str] = []
    for it in res.get("items", []) or []:
        top = (((it.get("snippet") or {}).get("topLevelComment") or {}).get("snippet") or {})
        txt = top.get("textDisplay")
        if txt:
            texts.append(txt)
    return texts


# =============================
# Filtering & scoring
# =============================

def passes_duration(seconds: int, min_duration: str) -> bool:
    if min_duration == "Toutes":
        return True
    if min_duration == "2 min":
        return seconds >= 120
    if min_duration == "5 min":
        return seconds >= 300
    if min_duration == "10 min":
        return seconds >= 600
    return True

def language_proof_ok(default_audio_language: Optional[str], target_code: Optional[str], require_proof: bool) -> Tuple[bool, str]:
    """
    Preuve langue:
    - si target_code=None => pas de filtre
    - si require_proof=True => on REJETTE si defaultAudioLanguage absent
    - sinon => on accepte si absent (mode permissif)
    """
    if target_code is None:
        return True, "Auto (pas de filtre langue)"

    dal = (default_audio_language or "").strip().lower()
    if not dal:
        if require_proof:
            return False, "defaultAudioLanguage absent (preuve requise)"
        return True, "defaultAudioLanguage absent (accepté: preuve non requise)"

    if dal == target_code or dal.startswith(target_code + "-"):
        return True, f"OK defaultAudioLanguage={dal}"
    return False, f"KO defaultAudioLanguage={dal} (attendu {target_code})"


# =============================
# UI
# =============================

def render_sidebar() -> dict:
    st.sidebar.title("🔍 YouTube Research V10")

    st.sidebar.header("📝 Mots-clés")
    keywords_text = st.sidebar.text_area(
        "1 requête par ligne (utilise '+' pour AND)",
        height=90,
        placeholder='ice + trump\n"donald trump" + ice\nmacron + france'
    )
    keywords = [k.strip() for k in keywords_text.split("\n") if k.strip()]

    st.sidebar.divider()
    st.sidebar.header("🎯 Filtres")
    language = st.sidebar.selectbox("🌍 Langue (preuve audio)", list(LANGUAGE_CONFIG.keys()), index=1)
    require_proof = st.sidebar.checkbox("✅ Exiger la preuve (defaultAudioLanguage doit exister)", value=True)

    min_views = st.sidebar.number_input("👁️ Vues minimum", value=100000, step=10000, min_value=0)
    min_duration = st.sidebar.selectbox("⏱️ Durée minimum", ["Toutes", "2 min", "5 min", "10 min"])

    date_period = st.sidebar.selectbox("📅 Période", ["Tout", "7 jours", "30 jours", "6 mois", "1 an"])
    date_limit = None
    if date_period == "7 jours":
        date_limit = now_utc() - timedelta(days=7)
    elif date_period == "30 jours":
        date_limit = now_utc() - timedelta(days=30)
    elif date_period == "6 mois":
        date_limit = now_utc() - timedelta(days=180)
    elif date_period == "1 an":
        date_limit = now_utc() - timedelta(days=365)

    st.sidebar.divider()
    st.sidebar.header("📄 Pages")
    pages = st.sidebar.slider("Pages (max 5)", 1, 5, DEFAULT_PAGES)
    per_page = st.sidebar.slider("Résultats/page", 10, 50, DEFAULT_PER_PAGE, step=10)

    st.sidebar.divider()
    st.sidebar.header("⚡ Vitesse")
    hard_deadline = st.sidebar.checkbox("⏱️ Stopper si > 10s (best effort)", value=True)
    top_to_display = st.sidebar.slider("Max vidéos affichées", 5, 50, 20)

    return {
        "keywords": keywords,
        "language": language,
        "require_proof": require_proof,
        "min_views": int(min_views),
        "min_duration": min_duration,
        "date_limit": date_limit,
        "pages": pages,
        "per_page": per_page,
        "hard_deadline": hard_deadline,
        "top_to_display": top_to_display,
    }

def build_prompt_blob(videos: List[dict], keywords: List[str]) -> str:
    subjects = ", ".join(keywords) if keywords else "N/A"
    out = [f"Analyse ces vidéos filtrées sur: {subjects}\n"]
    for i, v in enumerate(videos, 1):
        out.append("=" * 60)
        out.append(f"#{i} {v['stars']} | {v['title']}")
        out.append("=" * 60)
        out.append(f"📺 {v['channel_title']}")
        out.append(f"🔗 {v['url']}")
        subs = v.get("subs")
        out.append(f"👁️ {v['views']:,} vues | 👥 {subs if subs is not None else 'N/A'} abonnés | 📊 {v.get('ratio','N/A')}")
        out.append(f"🗣️ Langue preuve: {v['lang_reason']}\n")
        if v.get("comments_loaded"):
            out.append("💬 COMMENTAIRES:\n" + "\n".join([f"- {c}" for c in v.get("comments", [])]))
            out.append("")
        else:
            out.append("💬 COMMENTAIRES: (non chargés) — clique 'Charger commentaires'\n")
    return "\n".join(out)

def comments_box(comments: List[str]) -> str:
    instruction = (
        "analyse moi ces commentaires et relève les points suivant :\n"
        "les idées qui reviennent le plus souvent,\n"
        "propose moi 3 sujets qui marcheront sur base des commentaires\n"
        "et propose moi 3 sujets périphérique qui pourraient marcher par rapport aux commentaires !\n\n"
    )
    return instruction + "\n\n".join([f"- {c}" for c in comments])

def render_video_card(v: dict, idx: int):
    header = f"#{idx} {v['stars']} | {v['views']:,} vues"
    if isinstance(v.get("ratio"), (int, float)):
        header += f" | {v['ratio']:.2f}x"

    with st.expander(header, expanded=(idx <= 3)):
        c1, c2 = st.columns([1, 2])
        with c1:
            if v.get("thumbnail"):
                st.image(v["thumbnail"], use_container_width=True)
        with c2:
            st.markdown(f"**{v['title']}**")
            st.write(f"📺 {v['channel_title']}")
            st.write(f"🗣️ {v['lang_reason']}")
            st.write(f"👁️ {v['views']:,} vues")
            subs = v.get("subs")
            st.write(f"👥 abonnés: {subs:,}" if isinstance(subs, int) else "👥 abonnés: N/A (caché/indispo)")
            if isinstance(v.get("ratio"), (int, float)):
                st.write(f"📊 Ratio vues/abonnés: **{v['ratio']:.2f}x**")
            st.link_button("▶️ YouTube", v["url"])

        # Lazy comments
        st.divider()
        key = f"load_comments_{v['video_id']}"
        if st.button("💬 Charger 20 commentaires", key=key, use_container_width=True):
            comments = api_fetch_comments_20_cached(v["video_id"])
            st.session_state.comments_cache[v["video_id"]] = comments

        comments = st.session_state.comments_cache.get(v["video_id"], [])
        if comments:
            st.subheader("📋 Commentaires (Ctrl+A)")
            st.text_area("Copie-colle", value=comments_box(comments), height=260)


def main():
    st.title("🚀 YouTube Research V10")
    st.caption("Filtrage strict + langue prouvée via defaultAudioLanguage + rendu rapide (commentaires à la demande)")

    st.info(
        "Langue *preuve audio*: `defaultAudioLanguage` indique la langue de la piste audio par défaut selon YouTube. "
        "Si tu coches 'Exiger la preuve', une vidéo sans ce champ est rejetée."
    )

    params = render_sidebar()

    if "comments_cache" not in st.session_state:
        st.session_state.comments_cache = {}
    if "last_logs" not in st.session_state:
        st.session_state.last_logs = []
    if "last_videos" not in st.session_state:
        st.session_state.last_videos = []
    if "last_stats" not in st.session_state:
        st.session_state.last_stats = {}

    if not st.sidebar.button("🚀 LANCER", type="primary", use_container_width=True):
        # Display last run
        if st.session_state.last_videos:
            st.subheader("📹 Derniers résultats")
            for i, v in enumerate(st.session_state.last_videos, 1):
                render_video_card(v, i)
        if st.session_state.last_logs:
            st.subheader("📜 Logs (dernier 200)")
            st.text_area("", value="\n".join(st.session_state.last_logs[-200:]), height=250)
        return

    start_t = time.monotonic()
    deadline_t = start_t + (DEADLINE_SECONDS if params["hard_deadline"] else 10**9)

    logs: List[str] = []
    stats = {
        "ids_found": 0,
        "videos_meta": 0,
        "filtered_keywords": 0,
        "filtered_views": 0,
        "filtered_duration": 0,
        "filtered_date": 0,
        "filtered_language": 0,
        "passed": 0,
    }

    if not params["keywords"]:
        st.error("❌ Mets au moins une requête.")
        return

    lang_cfg = LANGUAGE_CONFIG.get(params["language"], {})
    target_code = lang_cfg.get("code")
    rel_lang = lang_cfg.get("relevanceLanguage")
    region = lang_cfg.get("regionCode")

    status = st.status("Recherche...", expanded=True)
    progress = st.progress(0)

    # 1) Search IDs
    video_sources: Dict[str, Set[str]] = {}
    all_ids: List[str] = []

    for i, kw in enumerate(params["keywords"]):
        status.write(f"🔍 Recherche: {kw}")
        ids = api_search_video_ids(
            query=kw,
            pages=params["pages"],
            per_page=params["per_page"],
            relevance_language=rel_lang,
            region_code=region,
            deadline_t=deadline_t,
            logs=logs,
        )
        for vid in ids:
            video_sources.setdefault(vid, set()).add(kw)
        all_ids.extend(ids)
        progress.progress(min(0.25, (i + 1) / max(1, len(params["keywords"])) * 0.25))

    # unique
    uniq_ids = []
    seen = set()
    for vid in all_ids:
        if vid not in seen:
            uniq_ids.append(vid)
            seen.add(vid)

    stats["ids_found"] = len(uniq_ids)
    logs.append(f"[INFO] Unique IDs: {len(uniq_ids)}")

    if not uniq_ids:
        status.update(label="❌ Aucun résultat", state="error")
        st.session_state.last_logs = logs
        st.session_state.last_videos = []
        st.session_state.last_stats = stats
        return

    # 2) videos.list
    status.update(label="📥 Métadonnées vidéos...", state="running")
    videos_map = api_videos_list(uniq_ids, deadline_t, logs)
    stats["videos_meta"] = len(videos_map)
    progress.progress(0.45)

    # 3) channels.list (subs)
    channel_ids = []
    for it in videos_map.values():
        ch = (it.get("snippet") or {}).get("channelId")
        if ch:
            channel_ids.append(ch)
    channel_ids = list(dict.fromkeys(channel_ids))
    channels_map = api_channels_list(channel_ids, deadline_t, logs)
    progress.progress(0.55)

    # 4) Filter + score
    status.update(label="🧪 Filtrage & scoring...", state="running")

    keyword_tokens = {kw: parse_and_tokens(kw) for kw in params["keywords"]}
    results: List[dict] = []

    for vid, it in videos_map.items():
        if time.monotonic() > deadline_t:
            logs.append("[WARN] Deadline atteinte pendant le filtrage (incomplet).")
            break

        sn = it.get("snippet") or {}
        stt = it.get("statistics") or {}
        cd = it.get("contentDetails") or {}

        title = sn.get("title", "")
        desc = sn.get("description", "") or ""
        combined = f"{title}\n{desc}"

        # AND sur tokens: il faut qu'au moins une ligne de keywords match vraiment
        matched_kw = None
        for kw in video_sources.get(vid, []):
            toks = keyword_tokens.get(kw, [])
            if toks and tokens_all_present(combined, toks):
                matched_kw = kw
                break
        if not matched_kw:
            stats["filtered_keywords"] += 1
            continue

        # vues
        views = int(stt.get("viewCount") or 0)
        if views < params["min_views"]:
            stats["filtered_views"] += 1
            continue

        # durée
        dur_s = parse_iso8601_duration_to_seconds(cd.get("duration", ""))
        if not passes_duration(dur_s, params["min_duration"]):
            stats["filtered_duration"] += 1
            continue

        # date
        if params["date_limit"]:
            published_at = rfc3339_to_dt(sn.get("publishedAt", ""))
            if published_at and published_at < params["date_limit"]:
                stats["filtered_date"] += 1
                continue

        # langue preuve
        ok_lang, reason = language_proof_ok(
            default_audio_language=sn.get("defaultAudioLanguage"),
            target_code=target_code,
            require_proof=params["require_proof"],
        )
        if not ok_lang:
            stats["filtered_language"] += 1
            continue

        # subs
        channel_id = sn.get("channelId")
        subs = None
        if channel_id and channel_id in channels_map:
            ch_stats = (channels_map[channel_id].get("statistics") or {})
            # subscriberCount absent si caché
            sc = ch_stats.get("subscriberCount")
            if sc is not None:
                try:
                    subs = int(sc)
                except ValueError:
                    subs = None

        ratio = None
        if subs and subs > 0:
            ratio = views / subs

        # thumbnail (best available)
        thumb = None
        thumbs = (sn.get("thumbnails") or {})
        for k in ("maxres", "standard", "high", "medium", "default"):
            if k in thumbs and thumbs[k].get("url"):
                thumb = thumbs[k]["url"]
                break

        results.append({
            "video_id": vid,
            "title": title,
            "url": f"https://www.youtube.com/watch?v={vid}",
            "thumbnail": thumb,
            "channel_title": sn.get("channelTitle", ""),
            "views": views,
            "subs": subs,
            "ratio": ratio,
            "stars": stars_from_ratio(ratio),
            "lang_reason": reason,
            "comments_loaded": False,
        })

    # sort by ratio desc (None last), then views desc
    results.sort(key=lambda v: (v["ratio"] is not None, v["ratio"] or 0, v["views"]), reverse=True)

    # limit display
    results = results[: params["top_to_display"]]
    stats["passed"] = len(results)

    progress.progress(1.0)
    status.update(label=f"✅ {len(results)} vidéos (liste prête)", state="complete")

    # Save state
    st.session_state.last_logs = logs
    st.session_state.last_videos = results
    st.session_state.last_stats = stats

    # Render metrics
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("IDs trouvés", stats["ids_found"])
    c2.metric("Meta vidéos", stats["videos_meta"])
    c3.metric("Validées (affichées)", stats["passed"])
    c4.metric("Rejet langue", stats["filtered_language"])

    # Prompt
    st.divider()
    st.subheader("📋 Prompt global (commentaires à la demande)")
    prompt = build_prompt_blob(results, params["keywords"])
    st.text_area("Copie:", value=prompt, height=320)
    st.download_button("📥 Télécharger prompt", data=prompt, file_name="prompt.txt")

    # Results
    st.divider()
    st.subheader("📹 Vidéos")
    for i, v in enumerate(results, 1):
        render_video_card(v, i)

    # Logs
    st.divider()
    st.subheader("📜 Logs (dernier 200)")
    st.text_area("", value="\n".join(logs[-200:]), height=250)

if __name__ == "__main__":
    main()
