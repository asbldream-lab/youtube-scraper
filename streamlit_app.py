"""
YouTube Research Tool - V13
- Recherche identique à V12 (AND keywords, vues, durée, date, langue, scoring)
- Commentaires: affichés uniquement dans une fenêtre à gauche (Ctrl+A),
  avec la phrase d'intro demandée
- Aucune section commentaires sous les vidéos
"""

from __future__ import annotations
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple, Set

import streamlit as st

st.set_page_config(page_title="YouTube Research (V13)", layout="wide", initial_sidebar_state="expanded")

DEADLINE_SECONDS = 10.0
MAX_PAGES = 5
DEFAULT_PER_PAGE = 50

LANGUAGE_CONFIG = {
    "Auto (no language filter)": {"code": None, "relevanceLanguage": None, "regionCode": None},
    "French":  {"code": "fr", "relevanceLanguage": "fr", "regionCode": "FR"},
    "English": {"code": "en", "relevanceLanguage": "en", "regionCode": "US"},
    "Spanish": {"code": "es", "relevanceLanguage": "es", "regionCode": "ES"},
}

ISO_DURATION_RE = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")


# =========================
# GOOGLE API CLIENT
# =========================

@st.cache_resource(show_spinner=False)
def yt_client():
    try:
        from googleapiclient.discovery import build
    except ModuleNotFoundError:
        raise RuntimeError("Dépendance manquante: ajoute `google-api-python-client` dans requirements.txt")

    api_key = st.secrets.get("YOUTUBE_API_KEY")
    if not api_key:
        raise RuntimeError("Clé API manquante: ajoute YOUTUBE_API_KEY dans Streamlit Secrets (TOML)")
    return build("youtube", "v3", developerKey=api_key)

def http_error_to_text(ex: Exception) -> str:
    try:
        from googleapiclient.errors import HttpError
        if isinstance(ex, HttpError):
            return f"HttpError: {ex}"
    except Exception:
        pass
    return str(ex)


# =========================
# UTILITAIRES
# =========================

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
    s = s.replace(".", "")          # I.C.E -> ice
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def parse_and_tokens(query: str) -> List[str]:
    """
    Règle V12:
    - "ice + trump" => AND
    - "ice trump"   => AND aussi
    - guillemets => phrase
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
    tokens = [normalize_text(t) for t in tokens if t.strip()]
    return tokens

def token_present(text: str, token: str) -> bool:
    t = normalize_text(text)
    tok = normalize_text(token)

    if not tok:
        return True

    if " " in tok:  # phrase
        return tok in t

    # mot entier (évite ice dans justice)
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
    if target_code is None:
        return True, "Langue: Auto (pas de filtre)"

    dal = (default_audio_language or "").strip().lower()
    dl = (default_language or "").strip().lower()

    def matches(code: str) -> bool:
        return code == target_code or code.startswith(target_code + "-")

    if dal:
        return (matches(dal), f"Audio={dal}" if matches(dal) else f"Audio={dal} (attendu {target_code})")
    if dl:
        return (matches(dl), f"Meta={dl}" if matches(dl) else f"Meta={dl} (attendu {target_code})")

    if require_proof:
        return False, "Aucune preuve langue (audio/meta absents)"
    return True, "Aucune preuve langue (accepté)"

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

def comments_box(comments: List[str]) -> str:
    # ✅ TA PHRASE EXACTE
    intro = (
        " analyse moi ces commentaires et relève les points suivant : "
        " les idées qui reviennet le plus souvent, propose moi 3 sujets qui marcheront sur base des commentaire "
        " et propose moi 3 sujets périphérique qui pourraient marcher par rapport aux commentaires !\n\n"
    )
    return intro + "\n\n".join(comments)


# =========================
# YOUTUBE API
# =========================

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

    for p in range(pages):
        if time.monotonic() > deadline_t:
            logs.append("[WARN] Deadline atteinte pendant search.list (stop).")
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
            logs.append(f"[ERROR] search.list page {p+1}: {http_error_to_text(ex)}")
            break

        items = res.get("items", []) or []
        for it in items:
            vid = ((it.get("id") or {}).get("videoId"))
            if vid:
                ids.append(vid)

        page_token = res.get("nextPageToken")
        logs.append(f"[INFO] search page {p+1}: +{len(items)} (next={'YES' if page_token else 'NO'})")

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
            logs.append("[WARN] Deadline atteinte pendant videos.list (stop).")
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

        for it in res.get("items", []) or []:
            out[it["id"]] = it

    return out

def api_channels_list(channel_ids: List[str], deadline_t: float, logs: List[str]) -> Dict[str, dict]:
    yt = yt_client()
    out: Dict[str, dict] = {}

    for i in range(0, len(channel_ids), 50):
        if time.monotonic() > deadline_t:
            logs.append("[WARN] Deadline atteinte pendant channels.list (stop).")
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

        for it in res.get("items", []) or []:
            out[it["id"]] = it

    return out

@st.cache_data(show_spinner=False, ttl=3600)
def api_fetch_comments_20(video_id: str) -> List[str]:
    yt = yt_client()
    try:
        req = yt.commentThreads().list(
            part="snippet",
            videoId=video_id,
            maxResults=20,
            order="relevance",
            textFormat="plainText",
            fields="items(snippet(topLevelComment(snippet(textDisplay))))"
        )
        res = req.execute()
    except Exception:
        return []

    texts: List[str] = []
    for it in res.get("items", []) or []:
        top = (((it.get("snippet") or {}).get("topLevelComment") or {}).get("snippet") or {})
        txt = top.get("textDisplay")
        if txt:
            texts.append(txt)
    return texts


# =========================
# UI
# =========================

def render_sidebar() -> dict:
    st.sidebar.title("🔍 YouTube Research (V13)")

    st.sidebar.header("📝 Mots-clés")
    keywords_text = st.sidebar.text_area(
        "1 requête par ligne (espace = AND, + = AND)",
        height=90,
        placeholder='ICE trump\nICE + trump\n"donald trump" ICE'
    )
    keywords = [k.strip() for k in keywords_text.split("\n") if k.strip()]

    st.sidebar.divider()
    st.sidebar.header("🎯 Filtres")
    language = st.sidebar.selectbox("🌍 Langue", list(LANGUAGE_CONFIG.keys()), index=1)
    require_proof = st.sidebar.checkbox("✅ Exiger preuve langue", value=True)

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
    per_page = st.sidebar.slider("Résultats/page", 10, 50, DEFAULT_PER_PAGE, step=10)

    st.sidebar.divider()
    st.sidebar.header("⚡ Vitesse")
    hard_deadline = st.sidebar.checkbox("⏱️ Couper si > 10s", value=True)
    max_display = st.sidebar.slider("Max vidéos affichées", 5, 50, 20)

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


def main():
    st.title("🚀 YouTube Research (V13)")
    st.caption("Recherche + scoring. Commentaires dans la fenêtre à gauche (Ctrl+A).")

    params = render_sidebar()

    if "comments_cache" not in st.session_state:
        st.session_state.comments_cache = {}
    if "selected_video" not in st.session_state:
        st.session_state.selected_video = None
    if "selected_title" not in st.session_state:
        st.session_state.selected_title = ""

    if not st.sidebar.button("🚀 LANCER", type="primary", use_container_width=True):
        st.info("Écris une requête (ex: ICE trump) puis clique LANCER.")
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
    }

    if not params["keywords"]:
        st.error("❌ Mets au moins 1 ligne.")
        return

    lang_cfg = LANGUAGE_CONFIG.get(params["language"], {})
    target_code = lang_cfg.get("code")
    rel_lang = lang_cfg.get("relevanceLanguage")
    region = lang_cfg.get("regionCode")

    status = st.status("Recherche...", expanded=True)
    progress = st.progress(0)

    kw_tokens = {kw: parse_and_tokens(kw) for kw in params["keywords"]}
    published_after = params["date_limit"]

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
            published_after=published_after,
            deadline_t=deadline_t,
            logs=logs,
        )
        for vid in ids:
            video_sources.setdefault(vid, set()).add(kw)
        all_ids.extend(ids)
        progress.progress(min(0.25, (i + 1) / max(1, len(params["keywords"])) * 0.25))

    uniq_ids: List[str] = []
    seen: Set[str] = set()
    for vid in all_ids:
        if vid not in seen:
            uniq_ids.append(vid)
            seen.add(vid)

    stats["ids_found"] = len(uniq_ids)
    logs.append(f"[INFO] Unique IDs: {len(uniq_ids)}")

    if not uniq_ids:
        status.update(label="❌ Aucun ID trouvé", state="error")
        st.text_area("Logs", value="\n".join(logs[-200:]), height=240)
        return

    status.update(label="📥 Métadonnées vidéos...", state="running")
    videos_map = api_videos_list(uniq_ids, deadline_t, logs)
    stats["videos_meta"] = len(videos_map)
    progress.progress(0.55)

    channel_ids: List[str] = []
    for it in videos_map.values():
        ch = (it.get("snippet") or {}).get("channelId")
        if ch:
            channel_ids.append(ch)
    channel_ids = list(dict.fromkeys(channel_ids))

    channels_map = api_channels_list(channel_ids, deadline_t, logs)
    progress.progress(0.65)

    status.update(label="🧪 Filtrage & scoring...", state="running")

    results: List[dict] = []
    for vid, it in videos_map.items():
        if time.monotonic() > deadline_t:
            logs.append("[WARN] Deadline atteinte pendant filtrage.")
            break

        sn = it.get("snippet") or {}
        stt = it.get("statistics") or {}
        cd = it.get("contentDetails") or {}

        title = sn.get("title", "") or ""
        desc = sn.get("description", "") or ""
        tags = sn.get("tags") or []

        if params["match_in"] == "Titre seulement":
            combined = title
        else:
            combined = f"{title}\n{desc}\n{' '.join(tags)}"

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
        subs = None
        if channel_id and channel_id in channels_map:
            ch_stats = (channels_map[channel_id].get("statistics") or {})
            sc = ch_stats.get("subscriberCount")
            if sc is not None:
                try:
                    subs = int(sc)
                except ValueError:
                    subs = None

        ratio = None
        if subs and subs > 0:
            ratio = views / subs

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

    progress.progress(1.0)
    status.update(label=f"✅ {len(display)} vidéos affichées (validées total: {stats['passed_total']})", state="complete")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("IDs trouvés", stats["ids_found"])
    c2.metric("Meta vidéos", stats["videos_meta"])
    c3.metric("Validées (total)", stats["passed_total"])
    c4.metric("Rejet langue", stats["filtered_language"])

    st.divider()
    st.subheader("🔎 Diagnostic rapide")
    d1, d2, d3, d4, d5 = st.columns(5)
    d1.metric("Rejet keywords", stats["filtered_keywords"])
    d2.metric("Rejet vues", stats["filtered_views"])
    d3.metric("Rejet durée", stats["filtered_duration"])
    d4.metric("Rejet date", stats["filtered_date"])
    d5.metric("Rejet langue", stats["filtered_language"])

    st.divider()

    # ✅ LAYOUT FINAL: gauche commentaires / droite vidéos
    left, right = st.columns([1, 2])

    with left:
        st.subheader("📝 Commentaires (Ctrl+A)")

        if st.session_state.selected_video:
            vid = st.session_state.selected_video
            st.caption(f"Vidéo sélectionnée : {st.session_state.selected_title}")

            # charge si pas en cache
            if vid not in st.session_state.comments_cache:
                st.session_state.comments_cache[vid] = api_fetch_comments_20(vid)

            comments = st.session_state.comments_cache.get(vid, [])
            st.text_area(
                "Copie-colle",
                value=comments_box(comments) if comments else "Aucun commentaire trouvé.",
                height=520
            )
        else:
            st.text_area(
                "Copie-colle",
                value="Clique sur une vidéo à droite (bouton 💬) pour charger 20 commentaires ici.",
                height=520
            )

    with right:
        st.subheader("📹 Vidéos")
        for idx, v in enumerate(display, 1):
            # ligne compacte + bouton sélection commentaires
            cols = st.columns([1, 9])
            with cols[0]:
                if st.button("💬", key=f"pick_{v['video_id']}"):
                    st.session_state.selected_video = v["video_id"]
                    st.session_state.selected_title = v["title"]

            with cols[1]:
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

    st.divider()
    st.subheader("📜 Logs (dernier 200)")
    st.text_area("", value="\n".join(logs[-200:]), height=240)


if __name__ == "__main__":
    main()
