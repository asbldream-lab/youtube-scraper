from __future__ import annotations
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple, Set

import streamlit as st

# Google API (YouTube Data API v3)
try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ModuleNotFoundError:
    build = None
    HttpError = Exception

st.set_page_config(page_title="YouTube Research", layout="wide", initial_sidebar_state="expanded")

DEADLINE_SECONDS = 10.0
MAX_PAGES = 5

PROMPT_INTRO = (
    "analyse moi ces commentaires et relève les points suivant : "
    "les idées qui reviennet le plus souvent, propose moi 3 sujets qui marcheront sur base des commentaire "
    "et propose moi 3 sujets périphérique qui pourraient marcher par rapport aux commentaires !"
)

LANGUAGE_CONFIG = {
    "Auto (no language filter)": {"code": None, "relevanceLanguage": None, "regionCode": None},
    "French":  {"code": "fr", "relevanceLanguage": "fr", "regionCode": "FR"},
    "English": {"code": "en", "relevanceLanguage": "en", "regionCode": "US"},
    "Spanish": {"code": "es", "relevanceLanguage": "es", "regionCode": "ES"},
}

ISO_DURATION_RE = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")


@st.cache_resource(show_spinner=False)
def yt_client():
    if build is None:
        raise RuntimeError("Dépendance manquante: google-api-python-client (ajoute-le dans requirements.txt)")
    api_key = st.secrets.get("YOUTUBE_API_KEY")
    if not api_key:
        raise RuntimeError("Secret manquant: YOUTUBE_API_KEY (dans Streamlit Secrets)")
    return build("youtube", "v3", developerKey=api_key)


def http_error_to_text(ex: Exception) -> str:
    if HttpError is not Exception and isinstance(ex, HttpError):
        return f"HttpError: {ex}"
    return str(ex)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def rfc3339_to_dt(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        if s.endswith("Z"):
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        return datetime.fromisoformat(s)
    except ValueError:
        return None


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


def normalize_text(s: str) -> str:
    s = (s or "").lower()
    s = s.replace(".", "")  # I.C.E -> ice
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def parse_and_tokens(query: str) -> List[str]:
    """
    - "ice + trump" => ["ice","trump"]  (AND)
    - "ice trump"   => ["ice","trump"]  (AND)
    - '"donald trump" ice' => ["donald trump","ice"]
    """
    if not query:
        return []
    q = query.strip()
    quoted = re.findall(r'"([^"]+)"', q)
    q_wo_quotes = re.sub(r'"[^"]+"', " ", q)

    if "+" in q_wo_quotes:
        parts = [p.strip() for p in re.split(r"\s*\+\s*", q_wo_quotes) if p.strip()]
    else:
        parts = [p.strip() for p in re.split(r"\s+", q_wo_quotes) if p.strip()]

    tokens = [*quoted, *parts]
    return [normalize_text(t) for t in tokens if t.strip()]


def token_present(text: str, token: str) -> bool:
    t = normalize_text(text)
    tok = normalize_text(token)

    if not tok:
        return True

    if " " in tok:  # phrase
        return tok in t

    return re.search(rf"\b{re.escape(tok)}\b", t) is not None


def tokens_all_present(text: str, tokens: List[str]) -> bool:
    return all(token_present(text, tok) for tok in tokens)


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


def language_proof_ok(
    default_audio_language: Optional[str],
    default_language: Optional[str],
    target_code: Optional[str],
    require_proof: bool
) -> Tuple[bool, str]:
    """
    Preuve de langue = defaultAudioLanguage ou defaultLanguage
    Si require_proof=True et aucune preuve => rejet
    """
    if target_code is None:
        return True, "langue=auto"

    dal = (default_audio_language or "").strip().lower()
    dl = (default_language or "").strip().lower()

    def matches(code: str) -> bool:
        return code == target_code or code.startswith(target_code + "-")

    if dal:
        return (matches(dal), f"defaultAudioLanguage={dal}")
    if dl:
        return (matches(dl), f"defaultLanguage={dl}")

    if require_proof:
        return False, "pas de preuve langue (audio/meta absents)"
    return True, "pas de preuve langue (accepté)"


def stars_from_ratio(ratio: Optional[float]) -> str:
    if ratio is None:
        return "⭐"
    if ratio >= 5:
        return "⭐⭐⭐🔥"
    if ratio >= 2:
        return "⭐⭐⭐"
    if ratio >= 1:
        return "⭐⭐"
    return "⭐"


def api_search_video_ids(
    query: str,
    pages: int,
    per_page: int,
    relevance_language: Optional[str],
    region_code: Optional[str],
    published_after: Optional[datetime],
    deadline_t: float,
    logs: List[str],
) -> List[str]:
    yt = yt_client()
    q_for_api = query.replace("+", " ").strip()

    ids: List[str] = []
    page_token: Optional[str] = None

    for _ in range(pages):
        if time.monotonic() > deadline_t:
            logs.append("[WARN] deadline atteinte pendant search.list")
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
                publishedAfter=published_after.isoformat().replace("+00:00", "Z") if published_after else None,
                fields="nextPageToken,items/id/videoId",
            )
            res = req.execute()
        except Exception as ex:
            logs.append(f"[ERROR] search.list: {http_error_to_text(ex)}")
            break

        for it in (res.get("items") or []):
            vid = ((it.get("id") or {}).get("videoId"))
            if vid:
                ids.append(vid)

        page_token = res.get("nextPageToken")
        if not page_token:
            break

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

    for i in range(0, len(video_ids), 50):
        if time.monotonic() > deadline_t:
            logs.append("[WARN] deadline atteinte pendant videos.list")
            break

        chunk = video_ids[i:i+50]
        try:
            req = yt.videos().list(
                part="snippet,statistics,contentDetails",
                id=",".join(chunk),
                fields=(
                    "items("
                    "id,"
                    "snippet(title,description,tags,channelId,channelTitle,publishedAt,defaultAudioLanguage,defaultLanguage,thumbnails),"
                    "statistics(viewCount),"
                    "contentDetails(duration)"
                    ")"
                ),
            )
            res = req.execute()
        except Exception as ex:
            logs.append(f"[ERROR] videos.list: {http_error_to_text(ex)}")
            continue

        for it in (res.get("items") or []):
            out[it["id"]] = it

    return out


def api_channels_list(channel_ids: List[str], deadline_t: float, logs: List[str]) -> Dict[str, dict]:
    yt = yt_client()
    out: Dict[str, dict] = {}

    for i in range(0, len(channel_ids), 50):
        if time.monotonic() > deadline_t:
            logs.append("[WARN] deadline atteinte pendant channels.list")
            break

        chunk = channel_ids[i:i+50]
        try:
            req = yt.channels().list(
                part="statistics",
                id=",".join(chunk),
                fields="items(id,statistics(subscriberCount,hiddenSubscriberCount))",
            )
            res = req.execute()
        except Exception as ex:
            logs.append(f"[ERROR] channels.list: {http_error_to_text(ex)}")
            continue

        for it in (res.get("items") or []):
            out[it["id"]] = it

    return out


@st.cache_data(show_spinner=False, ttl=3600)
def api_fetch_top_comments_20(video_id: str) -> List[str]:
    """
    20 TOP commentaires = order='relevance' + maxResults=20
    (Si commentaires désactivés => [])
    """
    yt = yt_client()
    try:
        req = yt.commentThreads().list(
            part="snippet",
            videoId=video_id,
            maxResults=20,
            order="relevance",
            textFormat="plainText",
            fields="items(snippet(topLevelComment(snippet(textDisplay))))",
        )
        res = req.execute()
    except Exception:
        return []

    out: List[str] = []
    for it in (res.get("items") or []):
        sn = (((it.get("snippet") or {}).get("topLevelComment") or {}).get("snippet") or {})
        txt = sn.get("textDisplay")
        if txt:
            out.append(txt)
    return out


def build_prompt_plus_comments(videos: List[dict], comments_by_video: Dict[str, List[str]]) -> str:
    blocks: List[str] = []
    for idx, v in enumerate(videos, 1):
        vid = v["video_id"]
        blocks.append(f"================ VIDEO {idx} ================\n")
        blocks.append(f"TITRE: {v['title']}\n")
        blocks.append(f"LIEN:  {v['url']}\n\n")
        blocks.append(PROMPT_INTRO + "\n\n")
        blocks.append("COMMENTAIRES:\n")

        comments = comments_by_video.get(vid, [])
        if comments:
            for c in comments:
                blocks.append(f"- {c.replace(chr(10), ' ').strip()}\n")
        else:
            blocks.append("- (aucun commentaire)\n")

        blocks.append("\n")

    return "".join(blocks).strip()


def render_sidebar() -> dict:
    st.sidebar.title("🔍 YouTube Research")

    st.sidebar.header("📝 Mots-clés")
    keywords_text = st.sidebar.text_area(
        "1 requête par ligne (espace = AND, + = AND)",
        height=90,
        placeholder='ICE trump\nICE + trump\n"donald trump" ICE',
    )
    keywords = [k.strip() for k in keywords_text.split("\n") if k.strip()]

    st.sidebar.divider()
    st.sidebar.header("🎯 Filtres")

    language = st.sidebar.selectbox("🌍 Langue", list(LANGUAGE_CONFIG.keys()), index=1)
    require_proof = st.sidebar.checkbox("✅ Exiger preuve langue (audio/meta)", value=True)

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
    pages = st.sidebar.slider("Pages (max 5)", 1, MAX_PAGES, 2)
    per_page = st.sidebar.slider("Résultats/page", 10, 50, 50, step=10)

    st.sidebar.divider()
    st.sidebar.header("⚡ Vitesse")
    hard_deadline = st.sidebar.checkbox("⏱️ Couper si > 10s", value=True)
    max_display = st.sidebar.slider("Max vidéos affichées", 3, 30, 10)

    st.sidebar.divider()
    st.sidebar.header("🔎 Matching")
    match_in = st.sidebar.selectbox("Chercher les mots-clés dans", ["Titre + Description + Tags", "Titre seulement"])

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
        "max_display": max_display,
        "match_in": match_in,
    }


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
            st.write(f"🔎 Match: {v['matched_kw']}")
            st.write(f"👁️ {v['views']:,} vues")

            subs = v.get("subs")
            st.write(f"👥 abonnés: {subs:,}" if isinstance(subs, int) else "👥 abonnés: N/A")

            if isinstance(v.get("ratio"), (int, float)):
                st.write(f"📊 Ratio vues/abonnés: **{v['ratio']:.2f}x**")

            st.link_button("▶️ YouTube", v["url"])


def main():
    st.title("🚀 YouTube Research")
    st.caption("À gauche: PROMPT + 20 TOP commentaires par vidéo (Ctrl+A). À droite: vidéos.")

    params = render_sidebar()

    if not st.sidebar.button("🚀 LANCER", type="primary", use_container_width=True):
        st.info("Écris une requête puis clique LANCER.")
        return

    if not params["keywords"]:
        st.error("❌ Mets au moins 1 mot-clé (une ligne).")
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
        "passed_total": 0,
        "comments_loaded": 0,
        "comments_skipped_deadline": 0,
    }

    lang_cfg = LANGUAGE_CONFIG.get(params["language"], {})
    target_code = lang_cfg.get("code")
    rel_lang = lang_cfg.get("relevanceLanguage")
    region = lang_cfg.get("regionCode")

    status = st.status("Recherche...", expanded=True)
    progress = st.progress(0)

    kw_tokens = {kw: parse_and_tokens(kw) for kw in params["keywords"]}
    video_sources: Dict[str, Set[str]] = {}
    all_ids: List[str] = []

    # 1) SEARCH
    for i, kw in enumerate(params["keywords"]):
        status.write(f"🔍 Recherche: {kw}")
        ids = api_search_video_ids(
            query=kw,
            pages=params["pages"],
            per_page=params["per_page"],
            relevance_language=rel_lang,
            region_code=region,
            published_after=params["date_limit"],
            deadline_t=deadline_t,
            logs=logs,
        )
        for vid in ids:
            video_sources.setdefault(vid, set()).add(kw)
        all_ids.extend(ids)
        progress.progress(min(0.25, (i + 1) / max(1, len(params["keywords"])) * 0.25))

    # UNIQUE
    uniq_ids: List[str] = []
    seen: Set[str] = set()
    for vid in all_ids:
        if vid not in seen:
            uniq_ids.append(vid)
            seen.add(vid)
    stats["ids_found"] = len(uniq_ids)

    if not uniq_ids:
        status.update(label="❌ Aucun résultat", state="error")
        st.text_area("Logs", value="\n".join(logs[-200:]), height=260)
        return

    # 2) VIDEOS META
    status.update(label="📥 Métadonnées vidéos...", state="running")
    videos_map = api_videos_list(uniq_ids, deadline_t, logs)
    stats["videos_meta"] = len(videos_map)
    progress.progress(0.55)

    # 3) CHANNELS META
    channel_ids: List[str] = []
    for it in videos_map.values():
        ch = (it.get("snippet") or {}).get("channelId")
        if ch:
            channel_ids.append(ch)
    channel_ids = list(dict.fromkeys(channel_ids))
    channels_map = api_channels_list(channel_ids, deadline_t, logs)
    progress.progress(0.65)

    # 4) FILTER + SCORE
    status.update(label="🧪 Filtrage & scoring...", state="running")
    results: List[dict] = []

    for vid, it in videos_map.items():
        if time.monotonic() > deadline_t:
            logs.append("[WARN] deadline atteinte pendant filtrage")
            break

        sn = it.get("snippet") or {}
        stt = it.get("statistics") or {}
        cd = it.get("contentDetails") or {}

        title = sn.get("title", "") or ""
        desc = sn.get("description", "") or ""
        tags = sn.get("tags") or []

        combined = title if params["match_in"] == "Titre seulement" else f"{title}\n{desc}\n{' '.join(tags)}"

        matched_kw = None
        for kw in video_sources.get(vid, []):
            toks = kw_tokens.get(kw, [])
            if toks and tokens_all_present(combined, toks):
                matched_kw = kw
                break
        if not matched_kw:
            stats["filtered_keywords"] += 1
            continue

        try:
            views = int(stt.get("viewCount") or 0)
        except ValueError:
            views = 0
        if views < params["min_views"]:
            stats["filtered_views"] += 1
            continue

        dur_s = parse_iso8601_duration_to_seconds(cd.get("duration", ""))
        if not passes_duration(dur_s, params["min_duration"]):
            stats["filtered_duration"] += 1
            continue

        if params["date_limit"]:
            published_at = rfc3339_to_dt(sn.get("publishedAt", ""))
            if published_at and published_at < params["date_limit"]:
                stats["filtered_date"] += 1
                continue

        ok_lang, reason = language_proof_ok(
            default_audio_language=sn.get("defaultAudioLanguage"),
            default_language=sn.get("defaultLanguage"),
            target_code=target_code,
            require_proof=params["require_proof"],
        )
        if not ok_lang:
            stats["filtered_language"] += 1
            continue

        channel_id = sn.get("channelId")
        subs: Optional[int] = None
        if channel_id and channel_id in channels_map:
            ch_stats = (channels_map[channel_id].get("statistics") or {})
            sc = ch_stats.get("subscriberCount")
            if sc is not None:
                try:
                    subs = int(sc)
                except ValueError:
                    subs = None

        ratio: Optional[float] = (views / subs) if (subs and subs > 0) else None

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
            "channel_title": sn.get("channelTitle", "") or "",
            "views": views,
            "subs": subs,
            "ratio": ratio,
            "stars": stars_from_ratio(ratio),
            "lang_reason": reason,
            "matched_kw": matched_kw,
        })

    results.sort(key=lambda v: (v["ratio"] is not None, v["ratio"] or 0, v["views"]), reverse=True)
    stats["passed_total"] = len(results)

    display = results[: params["max_display"]]

    # 5) COMMENTS (20 TOP) for each displayed video
    status.update(label="💬 Commentaires (top)...", state="running")
    comments_by_video: Dict[str, List[str]] = {}

    for v in display:
        if time.monotonic() > deadline_t:
            stats["comments_skipped_deadline"] += 1
            comments_by_video[v["video_id"]] = ["(Commentaires non chargés: limite temps atteinte)"]
            continue
        comments_by_video[v["video_id"]] = api_fetch_top_comments_20(v["video_id"])
        stats["comments_loaded"] += 1

    left_text = build_prompt_plus_comments(display, comments_by_video)

    progress.progress(1.0)
    status.update(label=f"✅ {len(display)} vidéos affichées (validées total: {stats['passed_total']})", state="complete")

    # UI
    left, right = st.columns([1, 2])

    with left:
        st.subheader("📝 PROMPT + 20 commentaires par vidéo (Ctrl+A)")
        st.text_area("Copie-colle", value=left_text, height=650)
        st.download_button("📥 Télécharger", data=left_text, file_name="prompt_commentaires.txt")

    with right:
        st.subheader("📹 Vidéos")
        for idx, v in enumerate(display, 1):
            render_video_card(v, idx)

    st.divider()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("IDs trouvés", stats["ids_found"])
    c2.metric("Validées (total)", stats["passed_total"])
    c3.metric("Commentaires chargés", stats["comments_loaded"])
    c4.metric("Ignorés (deadline)", stats["comments_skipped_deadline"])

    st.subheader("🚫 Rejets")
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Keywords", stats["filtered_keywords"])
    r2.metric("Vues", stats["filtered_views"])
    r3.metric("Durée", stats["filtered_duration"])
    r4.metric("Langue", stats["filtered_language"])

    st.subheader("📜 Logs (dernier 200)")
    st.text_area("", value="\n".join(logs[-200:]), height=240)


if __name__ == "__main__":
    main()
