"""
YouTube Research Tool - V11 (Streamlit)
- Pagination: jusqu’à 5 pages via pageToken (YouTube Data API)
- AND keywords: "ICE + trump" => ICE ET trump (dans title+description), avec normalisation "I.C.E" -> "ice"
- Langue: preuve via snippet.defaultAudioLanguage (fallback snippet.defaultLanguage)
- Filtres: vues min, durée min, période
- Score: vues / abonnés (subscriberCount)
- Commentaires: 20 par vidéo (chargés à la demande pour rester rapide)
- Timing: best-effort < 10s (si l’API est lente, on coupe sans planter)
"""

from __future__ import annotations
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple, Set

import streamlit as st


# =========================
# CONFIG
# =========================

st.set_page_config(page_title="YouTube Research (V11)", layout="wide", initial_sidebar_state="expanded")

DEADLINE_SECONDS = 10.0  # best-effort
MAX_PAGES = 5            # demandé
DEFAULT_PER_PAGE = 50    # 2 pages x 50 = 100 résultats, souvent plus rapide que 5 x 20

LANGUAGE_CONFIG = {
    "Auto (no language filter)": {"code": None, "relevanceLanguage": None, "regionCode": None},
    "French":  {"code": "fr", "relevanceLanguage": "fr", "regionCode": "FR"},
    "English": {"code": "en", "relevanceLanguage": "en", "regionCode": "US"},
    "Spanish": {"code": "es", "relevanceLanguage": "es", "regionCode": "ES"},
}

ISO_DURATION_RE = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")


# =========================
# SAFE GOOGLE API CLIENT
# =========================

@st.cache_resource(show_spinner=False)
def yt_client():
    """
    Import local => si le module manque, l’app affiche une erreur claire au lieu de planter à l’import.
    """
    try:
        from googleapiclient.discovery import build
    except ModuleNotFoundError:
        raise RuntimeError("Dépendance manquante: ajoute `google-api-python-client` dans requirements.txt")

    api_key = st.secrets.get("YOUTUBE_API_KEY")
    if not api_key:
        raise RuntimeError("Clé API manquante: ajoute YOUTUBE_API_KEY dans Streamlit Secrets (TOML)")
    return build("youtube", "v3", developerKey=api_key)


def http_error_to_text(ex: Exception) -> str:
    # Import optionnel (ne casse pas si absent)
    try:
        from googleapiclient.errors import HttpError
        if isinstance(ex, HttpError):
            return f"HttpError: {ex}"
    except Exception:
        pass
    return str(ex)


# =========================
# TEXT / KEYWORDS
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
    """
    Normalisation pour matcher ICE vs I.C.E, etc.
    """
    s = (s or "").lower()
    s = s.replace(".", "")  # i.c.e -> ice
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def parse_and_tokens(query: str) -> List[str]:
    """
    'ice + trump' => ['ice', 'trump']
    Support des guillemets: '"donald trump" + ice' => ['donald trump', 'ice']
    """
    if not query:
        return []
    q = query.strip()

    quoted = re.findall(r'"([^"]+)"', q)
    q_wo_quotes = re.sub(r'"[^"]+"', "", q)

    parts = [p.strip() for p in re.split(r"\s*\+\s*", q_wo_quotes) if p.strip()]
    tokens = [*quoted, *parts]
    tokens = [normalize_text(t) for t in tokens if t.strip()]
    return tokens

def token_present(text: str, token: str) -> bool:
    """
    - token multi-mots: on cherche la sous-chaîne
    - token 1 mot: on cherche un mot entier (évite 'ice' dans 'justice')
    """
    t = normalize_text(text)
    tok = normalize_text(token)

    if not tok:
        return True

    if " " in tok:
        return tok in t

    return re.search(rf"\b{re.escape(tok)}\b", t) is not None

def tokens_all_present(text: str, tokens: List[str]) -> bool:
    return all(token_present(text, tok) for tok in tokens)


# =========================
# YOUTUBE API CALLS (OPTIMISÉS)
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

    # YouTube search ne garantit pas "+" en AND strict => on cherche large,
    # et on force le AND ensuite sur title+description.
    q_for_api = query.replace("+", " ").strip()

    ids: List[str] = []
    page_token: Optional[str] = None

    for p in range(pages):
        if time.monotonic() > deadline_t:
            logs.append("[WARN] Deadline atteinte pendant search.list (pagination stoppée).")
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

    # unique preserving order
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
                    "snippet(title,description,channelId,channelTitle,publishedAt,defaultAudioLanguage,defaultLanguage,thumbnails),"
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

    # channels.list peut ne pas renvoyer subscriberCount si la chaîne cache ses abonnés
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
            fields="items(snippet(topLevelComment(snippet(textDisplay,likeCount))))"
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
# FILTERS / SCORING
# =========================

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
    Preuve langue:
    - 1) defaultAudioLanguage (audio) si présent
    - 2) sinon defaultLanguage (metadata) si présent
    - si require_proof=True => on rejette si aucun champ n’existe
    """
    if target_code is None:
        return True, "Langue: Auto (pas de filtre)"

    dal = (default_audio_language or "").strip().lower()
    dl = (default_language or "").strip().lower()

    def matches(code: str) -> bool:
        return code == target_code or code.startswith(target_code + "-")

    if dal:
        return (matches(dal), f"Audio={dal} (attendu {target_code})" if not matches(dal) else f"Audio={dal}")
    if dl:
        return (matches(dl), f"Meta={dl} (attendu {target_code})" if not matches(dl) else f"Meta={dl}")

    if require_proof:
        return False, "Aucune preuve langue (defaultAudioLanguage/defaultLanguage absents)"
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


# =========================
# UI
# =========================

def render_sidebar() -> dict:
    st.sidebar.title("🔍 YouTube Research")

    st.sidebar.header("📝 Mots-clés")
    keywords_text = st.sidebar.text_area(
        "1 requête par ligne (utilise + pour AND)",
        height=90,
        placeholder='ICE + trump\n"donald trump" + ice\nmacron + france'
    )
    keywords = [k.strip() for k in keywords_text.split("\n") if k.strip()]

    st.sidebar.divider()
    st.sidebar.header("🎯 Filtres")
    language = st.sidebar.selectbox("🌍 Langue", list(LANGUAGE_CONFIG.keys()), index=1)
    require_proof = st.sidebar.checkbox("✅ Exiger preuve langue", value=True, help="Rejette si aucun champ langue n’existe")

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
    hard_deadline = st.sidebar.checkbox("⏱️ Couper si > 10s (best effort)", value=True)
    max_display = st.sidebar.slider("Max vidéos affichées", 5, 50, 20)

    st.sidebar.divider()
    st.sidebar.header("🔎 Matching")
    match_in = st.sidebar.selectbox("Chercher les mots-clés dans", ["Titre + Description", "Titre seulement"])

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


def comments_box(comments: List[str]) -> str:
    instruction = (
        "analyse moi ces commentaires et relève les points suivant :\n"
        "1) les idées qui reviennent le plus souvent\n"
        "2) propose moi 3 sujets qui marcheront sur base des commentaires\n"
        "3) propose moi 3 sujets périphériques qui pourraient marcher par rapport aux commentaires\n\n"
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

        st.divider()
        if st.button("💬 Charger 20 commentaires", key=f"load_{v['video_id']}", use_container_width=True):
            st.session_state.comments_cache[v["video_id"]] = api_fetch_comments_20(v["video_id"])

        comments = st.session_state.comments_cache.get(v["video_id"], [])
        if comments:
            st.subheader("📋 Commentaires (Ctrl+A)")
            st.text_area("Copie-colle", value=comments_box(comments), height=280)


def main():
    st.title("🚀 YouTube Research (V11)")
    st.caption("Filtres stricts + langue (preuve) + scoring + commentaires à la demande")

    params = render_sidebar()

    if "comments_cache" not in st.session_state:
        st.session_state.comments_cache = {}

    if st.sidebar.button("🚀 LANCER", type="primary", use_container_width=True) is False:
        st.info("Entre une requête, puis clique LANCER.")
        return

    # deadline
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

    # basic validation
    if not params["keywords"]:
        st.error("❌ Mets au moins 1 requête (une ligne).")
        return

    # config langue
    lang_cfg = LANGUAGE_CONFIG.get(params["language"], {})
    target_code = lang_cfg.get("code")
    rel_lang = lang_cfg.get("relevanceLanguage")
    region = lang_cfg.get("regionCode")

    status = st.status("Recherche...", expanded=True)
    progress = st.progress(0)

    # 1) search ids
    video_sources: Dict[str, Set[str]] = {}
    all_ids: List[str] = []

    # tokens par keyword
    kw_tokens = {kw: parse_and_tokens(kw) for kw in params["keywords"]}

    # accélération: si date_limit, on peut aussi passer publishedAfter à search.list
    published_after = params["date_limit"]

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

    # unique IDs
    uniq_ids: List[str] = []
    seen: Set[str] = set()
    for vid in all_ids:
        if vid not in seen:
            uniq_ids.append(vid)
            seen.add(vid)

    stats["ids_found"] = len(uniq_ids)
    logs.append(f"[INFO] Unique IDs: {len(uniq_ids)}")

    if not uniq_ids:
        status.update(label="❌ Aucun résultat", state="error")
        st.text_area("Logs", value="\n".join(logs[-200:]), height=240)
        return

    # 2) videos.list
    status.update(label="📥 Métadonnées vidéos...", state="running")
    videos_map = api_videos_list(uniq_ids, deadline_t, logs)
    stats["videos_meta"] = len(videos_map)
    progress.progress(0.50)

    # 3) channels.list
    channel_ids: List[str] = []
    for it in videos_map.values():
        ch = (it.get("snippet") or {}).get("channelId")
        if ch:
            channel_ids.append(ch)
    # unique
    channel_ids = list(dict.fromkeys(channel_ids))

    channels_map = api_channels_list(channel_ids, deadline_t, logs)
    progress.progress(0.60)

    # 4) filtering + scoring
    status.update(label="🧪 Filtrage & scoring...", state="running")

    results: List[dict] = []
    for vid, it in videos_map.items():
        if time.monotonic() > deadline_t:
            logs.append("[WARN] Deadline atteinte pendant filtrage (incomplet).")
            break

        sn = it.get("snippet") or {}
        stt = it.get("statistics") or {}
        cd = it.get("contentDetails") or {}

        title = sn.get("title", "") or ""
        desc = sn.get("description", "") or ""
        combined = title if params["match_in"] == "Titre seulement" else f"{title}\n{desc}"

        # AND sur tokens: doit matcher au moins une requête source
        matched_kw = None
        for kw in video_sources.get(vid, []):
            toks = kw_tokens.get(kw, [])
            if toks and tokens_all_present(combined, toks):
                matched_kw = kw
                break
        if not matched_kw:
            stats["filtered_keywords"] += 1
            continue

        # vues
        try:
            views = int(stt.get("viewCount") or 0)
        except ValueError:
            views = 0
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
            default_language=sn.get("defaultLanguage"),
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
            "channel_title": sn.get("channelTitle", "") or "",
            "views": views,
            "subs": subs,
            "ratio": ratio,
            "stars": stars_from_ratio(ratio),
            "lang_reason": reason,
            "matched_kw": matched_kw,
        })

    # sort: ratio desc (None last), puis vues desc
    results.sort(key=lambda v: (v["ratio"] is not None, v["ratio"] or 0, v["views"]), reverse=True)

    stats["passed_total"] = len(results)

    # display limit
    display = results[: params["max_display"]]

    progress.progress(1.0)
    status.update(label=f"✅ {len(display)} vidéos affichées (validées total: {stats['passed_total']})", state="complete")

    # metrics
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("IDs trouvés", stats["ids_found"])
    c2.metric("Meta vidéos", stats["videos_meta"])
    c3.metric("Validées (total)", stats["passed_total"])
    c4.metric("Rejet langue", stats["filtered_language"])

    # debug: si tu as 0 résultat, on dit pourquoi
    st.divider()
    st.subheader("🔎 Diagnostic rapide")
    d1, d2, d3, d4, d5 = st.columns(5)
    d1.metric("Rejet keywords", stats["filtered_keywords"])
    d2.metric("Rejet vues", stats["filtered_views"])
    d3.metric("Rejet durée", stats["filtered_duration"])
    d4.metric("Rejet date", stats["filtered_date"])
    d5.metric("Rejet langue", stats["filtered_language"])

    # prompt global
    st.divider()
    st.subheader("📋 Prompt global")
    prompt_lines = []
    prompt_lines.append("Analyse ces vidéos et leurs métriques.\n")
    for i, v in enumerate(display, 1):
        prompt_lines.append("=" * 60)
        prompt_lines.append(f"#{i} {v['stars']} | {v['title']}")
        prompt_lines.append(f"Mot-clé match: {v['matched_kw']}")
        prompt_lines.append(f"URL: {v['url']}")
        prompt_lines.append(f"Vues: {v['views']:,} | Abonnés: {v['subs'] if v['subs'] is not None else 'N/A'} | Ratio: {v['ratio']:.2f}x" if v["ratio"] is not None else f"Vues: {v['views']:,} | Abonnés: N/A | Ratio: N/A")
        prompt_lines.append(f"Langue (preuve): {v['lang_reason']}")
        prompt_lines.append("")
    st.text_area("Copie-colle", value="\n".join(prompt_lines), height=260)

    # render results
    st.divider()
    st.subheader("📹 Vidéos")
    for idx, v in enumerate(display, 1):
        render_video_card(v, idx)

    # logs
    st.divider()
    st.subheader("📜 Logs (dernier 200)")
    st.text_area("", value="\n".join(logs[-200:]), height=240)


if __name__ == "__main__":
    main()
