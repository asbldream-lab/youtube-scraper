from __future__ import annotations
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple, Set

import streamlit as st

try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ModuleNotFoundError:
    build = None
    HttpError = Exception

st.set_page_config(page_title="YouTube Research", layout="wide", initial_sidebar_state="expanded")

# ----------------------
# SETTINGS
# ----------------------
DEADLINE_SECONDS = 10.0
MAX_PAGES = 5

# ✅ PROMPT (1 SEULE FOIS)
PROMPT_INTRO = """analyse moi ces commentaires et relève les points suivant : les idées qui reviennet le plus souvent, propose moi 3 sujets qui marcheront sur base des commentaire et propose moi 3 sujets périphérique qui pourraient marcher par rapport aux commentaires !

Les points que je te demande, doivent faire maximum 1 seule phrase ! pas + 1 seule !

Tu mets :

Idée qui reviennent le plus souvent (3) :
1) ...
2) ...
3) ...

3 Sujets qui pourraient marcher (3) :
1) ...
2) ...
3) ...

3 sujets périphérique (3) :
1) ...
2) ...
3) ...

Voici les commentaires :
"""

LANGUAGE_CONFIG = {
    "Auto (no language filter)": {"code": None, "relevanceLanguage": None, "regionCode": None},
    "French":  {"code": "fr", "relevanceLanguage": "fr", "regionCode": "FR"},
    "English": {"code": "en", "relevanceLanguage": "en", "regionCode": "US"},
    "Spanish": {"code": "es", "relevanceLanguage": "es", "regionCode": "ES"},
}

# Heuristique langue (fallback via commentaires)
LANG_MARKERS = {
    "fr": {"le","la","les","de","du","des","un","une","et","est","sont","dans","pour","sur","avec","qui","que","ce","cette",
           "nous","vous","je","tu","il","elle","mais","plus","très","pas","comme","ça","cest"},
    "en": {"the","and","is","are","was","were","have","has","been","this","that","with","for","not","you","they","but","what",
           "when","your","will","would"},
    "es": {"el","la","los","las","de","en","que","es","un","una","por","con","para","como","más","pero","sus","este","son"},
}

ISO_DURATION_RE = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")

# Max de checks langue via commentaires (pour tenir 10s)
MAX_LANG_COMMENT_CHECKS = 30


# =========================
# CLIENT
# =========================
@st.cache_resource(show_spinner=False)
def yt_client():
    if build is None:
        raise RuntimeError("Dépendance manquante: google-api-python-client (ajoute-le dans requirements.txt)")
    api_key = st.secrets.get("YOUTUBE_API_KEY")
    if not api_key:
        raise RuntimeError("Secret manquant: YOUTUBE_API_KEY (Streamlit Secrets)")
    return build("youtube", "v3", developerKey=api_key)


def http_error_to_text(ex: Exception) -> str:
    if HttpError is not Exception and isinstance(ex, HttpError):
        return f"HttpError: {ex}"
    return str(ex)


# =========================
# UTILS
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
    s = s.replace(".", "")  # I.C.E -> ice
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def parse_and_tokens(query: str) -> List[str]:
    """
    "ice + trump" => AND
    "ice trump"   => AND
    '"donald trump" ice' => phrase + mot
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

def detect_lang_from_text(text: str) -> Optional[str]:
    """
    Heuristique: compte mots fréquents.
    Retourne 'fr'/'en'/'es' ou None.
    """
    if not text or len(text) < 40:
        return None
    words = set(re.findall(r"\b[a-zàâäéèêëïîôùûüçñ]+\b", text.lower()))
    best_lang = None
    best_score = 0
    for lang, markers in LANG_MARKERS.items():
        score = len(words & markers)
        if score > best_score:
            best_score = score
            best_lang = lang
    return best_lang if best_score >= 3 else None

def language_ok_with_fallback(
    target_code: Optional[str],
    default_audio_language: Optional[str],
    default_language: Optional[str],
    comments_text: str,
    require_proof: bool,
) -> Tuple[bool, str]:
    """
    Ordre:
    1) meta audio/lang si dispo
    2) sinon comments détectés
    3) sinon => si require_proof=True rejet, sinon accept
    """
    if target_code is None:
        return True, "langue=auto"

    dal = (default_audio_language or "").strip().lower()
    dl = (default_language or "").strip().lower()

    def matches(code: str) -> bool:
        return code == target_code or code.startswith(target_code + "-")

    if dal:
        return (matches(dal), f"meta audio={dal}")
    if dl:
        return (matches(dl), f"meta lang={dl}")

    detected = detect_lang_from_text(comments_text)
    if detected:
        return (detected == target_code, f"comments détecté={detected}")

    if require_proof:
        return False, "aucune preuve (meta vide + comments indétectable)"
    return True, "aucune preuve (accepté)"


# =========================
# API CALLS
# =========================
def api_search_video_ids_once(
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
            logs.append("[WARN] deadline pendant search.list")
            break

        params = {
            "part": "id",
            "q": q_for_api,
            "type": "video",
            "maxResults": per_page,
            "pageToken": page_token,
            "fields": "nextPageToken,items/id/videoId",
        }
        if relevance_language:
            params["relevanceLanguage"] = relevance_language
        if region_code:
            params["regionCode"] = region_code
        if published_after:
            params["publishedAfter"] = published_after.isoformat().replace("+00:00", "Z")

        try:
            res = yt.search().list(**params).execute()
        except Exception as ex:
            logs.append(f"[ERROR] search.list page {p+1}: {http_error_to_text(ex)}")
            break

        items = res.get("items") or []
        for it in items:
            vid = ((it.get("id") or {}).get("videoId"))
            if vid:
                ids.append(vid)

        page_token = res.get("nextPageToken")
        logs.append(f"[INFO] search page {p+1}: +{len(items)}")
        if not page_token:
            break

    seen: Set[str] = set()
    out: List[str] = []
    for vid in ids:
        if vid not in seen:
            out.append(vid)
            seen.add(vid)
    return out

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
    ids = api_search_video_ids_once(query, pages, per_page, relevance_language, region_code, published_after, deadline_t, logs)

    if not ids and (relevance_language or region_code):
        logs.append("[WARN] 0 résultat avec langue/region -> retry sans langue/region")
        ids = api_search_video_ids_once(query, pages, per_page, None, None, published_after, deadline_t, logs)

    return ids

def api_videos_list(video_ids: List[str], deadline_t: float, logs: List[str]) -> Dict[str, dict]:
    yt = yt_client()
    out: Dict[str, dict] = {}

    for i in range(0, len(video_ids), 50):
        if time.monotonic() > deadline_t:
            logs.append("[WARN] deadline pendant videos.list")
            break

        chunk = video_ids[i:i+50]
        try:
            res = yt.videos().list(
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
            ).execute()
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
            logs.append("[WARN] deadline pendant channels.list")
            break

        chunk = channel_ids[i:i+50]
        try:
            res = yt.channels().list(
                part="statistics",
                id=",".join(chunk),
                fields="items(id,statistics(subscriberCount,hiddenSubscriberCount))",
            ).execute()
        except Exception as ex:
            logs.append(f"[ERROR] channels.list: {http_error_to_text(ex)}")
            continue

        for it in (res.get("items") or []):
            out[it["id"]] = it
    return out

@st.cache_data(show_spinner=False, ttl=3600)
def api_fetch_top_comments_20(video_id: str) -> List[str]:
    """
    20 TOP = order=relevance + 20 premiers
    """
    yt = yt_client()
    try:
        res = yt.commentThreads().list(
            part="snippet",
            videoId=video_id,
            maxResults=20,
            order="relevance",
            textFormat="plainText",
            fields="items(snippet(topLevelComment(snippet(textDisplay))))",
        ).execute()
    except Exception:
        return []

    out: List[str] = []
    for it in (res.get("items") or []):
        sn = (((it.get("snippet") or {}).get("topLevelComment") or {}).get("snippet") or {})
        txt = sn.get("textDisplay")
        if txt:
            out.append(txt)
    return out


# =========================
# BUILD LEFT WINDOW
# =========================
def build_prompt_plus_comments(videos: List[dict], comments_by_video: Dict[str, List[str]]) -> str:
    """
    ✅ 1 SEUL PROMPT au début
    ✅ puis commentaires des vidéos (groupés par vidéo)
    """
    blocks: List[str] = []
    blocks.append(PROMPT_INTRO.strip() + "\n\n")

    for idx, v in enumerate(videos, 1):
        vid = v["video_id"]
        blocks.append(f"================ VIDEO {idx} ================\n")
        blocks.append(f"TITRE: {v['title']}\n")
        blocks.append(f"LIEN:  {v['url']}\n\n")
        blocks.append("COMMENTAIRES:\n")

        comments = comments_by_video.get(vid, [])
        if comments:
            for c in comments:
                blocks.append(f"- {c.replace(chr(10), ' ').strip()}\n")
        else:
            blocks.append("- (aucun commentaire)\n")

        blocks.append("\n")

    return "".join(blocks).strip()


# =========================
# UI
# =========================
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

    require_proof = st.sidebar.checkbox("✅ Exiger preuve langue", value=True)
    st.sidebar.caption("Preuve = meta audio/lang. Si absent → on tente via commentaires.")

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
    pages = st.sidebar.slider("Pages (max 5)", 1, MAX_PAGES, 5)
    per_page = st.sidebar.slider("Résultats/page", 10, 50, 50, step=10)

    st.sidebar.divider()
    st.sidebar.header("⚡ Vitesse")
    hard_deadline = st.sidebar.checkbox("⏱️ Couper si > 10s", value=True)
    max_display = st.sidebar.slider("Max vidéos affichées", 3, 30, 15)

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
    st.caption("À gauche: 1 prompt + 20 TOP commentaires par vidéo (Ctrl+A). À droite: vidéos.")

    try:
        _ = yt_client()
    except Exception as ex:
        st.error(str(ex))
        st.info("Vérifie: requirements.txt + Streamlit Secrets.")
        return

    params = render_sidebar()

    if not st.sidebar.button("🚀 LANCER", type="primary", use_container_width=True):
        st.info("Écris une requête puis clique LANCER.")
        return

    if not params["keywords"]:
        st.error("❌ Mets au moins 1 ligne de mots-clés.")
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
        "comments_used_for_lang": 0,
        "comments_loaded": 0,
        "comments_skipped_deadline": 0,
        "lang_comment_checks": 0,
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
        logs.append(f"[INFO] ids '{kw}': {len(ids)}")
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

    if not uniq_ids:
        status.update(label="❌ 0 vidéo trouvée", state="error")
        st.error("Aucun ID renvoyé par YouTube. Regarde les logs.")
        st.text_area("Logs", value="\n".join(logs[-200:]), height=260)
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
    comments_by_video: Dict[str, List[str]] = {}

    for vid, it in videos_map.items():
        if time.monotonic() > deadline_t:
            logs.append("[WARN] deadline pendant filtrage")
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

        dal = sn.get("defaultAudioLanguage")
        dl = sn.get("defaultLanguage")
        comments_text_for_lang = ""

        need_comments_for_lang = (target_code is not None) and (not (dal or dl))

        if need_comments_for_lang:
            if stats["lang_comment_checks"] >= MAX_LANG_COMMENT_CHECKS:
                comments_text_for_lang = ""
            elif time.monotonic() > deadline_t:
                stats["comments_skipped_deadline"] += 1
                comments_text_for_lang = ""
            else:
                stats["lang_comment_checks"] += 1
                comms = api_fetch_top_comments_20(vid)
                comments_by_video[vid] = comms
                stats["comments_used_for_lang"] += 1
                comments_text_for_lang = " ".join(comms)[:2000]

        ok_lang, reason = language_ok_with_fallback(
            target_code=target_code,
            default_audio_language=dal,
            default_language=dl,
            comments_text=comments_text_for_lang,
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

    status.update(label="💬 Commentaires (top)...", state="running")
    for v in display:
        vid = v["video_id"]
        if vid in comments_by_video:
            continue
        if time.monotonic() > deadline_t:
            stats["comments_skipped_deadline"] += 1
            comments_by_video[vid] = ["(Commentaires non chargés: limite temps atteinte)"]
            continue
        comments_by_video[vid] = api_fetch_top_comments_20(vid)
        stats["comments_loaded"] += 1

    left_text = build_prompt_plus_comments(display, comments_by_video)

    progress.progress(1.0)
    status.update(label=f"✅ {len(display)} vidéos affichées (validées total: {stats['passed_total']})", state="complete")

    left, right = st.columns([1, 2])

    with left:
        st.subheader("📝 PROMPT + commentaires (Ctrl+A)")
        st.text_area("Copie-colle", value=left_text, height=650)
        st.download_button("📥 Télécharger", data=left_text, file_name="prompt_commentaires.txt")

    with right:
        st.subheader("📹 Vidéos")
        for idx, v in enumerate(display, 1):
            render_video_card(v, idx)

    st.divider()
    st.subheader("🔬 Diagnostic")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("IDs trouvés", stats["ids_found"])
    c2.metric("Meta vidéos", stats["videos_meta"])
    c3.metric("Validées", stats["passed_total"])
    c4.metric("Affichées", len(display))

    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Rejet keywords", stats["filtered_keywords"])
    r2.metric("Rejet vues", stats["filtered_views"])
    r3.metric("Rejet durée", stats["filtered_duration"])
    r4.metric("Rejet date", stats["filtered_date"])

    l1, l2, l3, l4 = st.columns(4)
    l1.metric("Rejet langue", stats["filtered_language"])
    l2.metric("Comments langue", stats["comments_used_for_lang"])
    l3.metric("Checks comments langue", stats["lang_comment_checks"])
    l4.metric("Skip deadline", stats["comments_skipped_deadline"])

    st.subheader("📜 Logs (dernier 200)")
    st.text_area("", value="\n".join(logs[-200:]), height=260)


if __name__ == "__main__":
    main()
