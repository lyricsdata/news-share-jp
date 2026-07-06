# cd C:\Users\onetw\PyCharmMiscProject\news_share
# streamlit run news_scraper_jp.py

# Requires: pip install streamlit pandas feedparser
#
# 日本語ニュース版（ライブ取得方式）。
# 開かれるたびに Google ニュース日本語版(RSS)から最新を取得して表示する。
# データはCSVに保存せず、@st.cache_data(ttl=30分)でキャッシュするだけ。
# → 共有相手はいつ開いても「常に最新」を見られる。
# 対象: キオクシア / 日本電波工業 / 日経平均

import streamlit as st
import pandas as pd
import feedparser
import re
import html
from urllib.parse import quote
from datetime import datetime
from zoneinfo import ZoneInfo
from email.utils import parsedate_to_datetime

# 取得時刻はサーバーのローカル時刻（Streamlit Cloud は UTC）ではなく
# 日本時間で表示する。
JST = ZoneInfo("Asia/Tokyo")

# 有料記事が多いソース（チェックボックスで除外できる）
PAYWALLED_SOURCES = {
    "日本経済新聞", "日経電子版", "日経ビジネス", "日経クロステック",
    "Bloomberg", "ブルームバーグ",
    "ウォール・ストリート・ジャーナル", "The Wall Street Journal",
    "Financial Times", "東洋経済オンライン",
}

# 大手・人気メディアの判定キーワード（部分一致）。
# Google ニュースのソース名は表記ゆれが多いので完全一致でなく部分一致で拾う。
# 例: "日経" は 日経CNBC online / 日経クロステック にも一致、"Yahoo!" は両Yahoo系に一致。
MAJOR_SOURCE_KEYWORDS = {
    # 全国紙・新聞社
    "日本経済新聞", "日経", "朝日新聞", "読売新聞", "毎日新聞", "産経", "東京新聞",
    "日刊工業新聞",
    # テレビ・通信社
    "NHK", "TBS", "テレ朝", "日テレ", "テレ東", "FNN",
    "時事", "共同通信", "ロイター", "Reuters", "Bloomberg", "ブルームバーグ",
    # 経済・ビジネス誌
    "東洋経済", "ダイヤモンド", "四季報",
    # 大手アグリゲータ・株情報
    "Yahoo!", "株探", "ライブドアニュース", "みんかぶ", "トウシル",
    "ITmedia", "nippon.com",
}


def is_major_source(source: str) -> bool:
    """ソース名が大手・人気メディアのキーワードを含むか（部分一致・大小文字無視）。"""
    s = (source or "").lower()
    return any(k.lower() in s for k in MAJOR_SOURCE_KEYWORDS)

# 表示名 → Google ニュース検索クエリ
TARGETS = {
    "キオクシア":     "キオクシア",
    "日本電波工業":   "日本電波工業",
    "日経平均":       '"日経平均株価"',
}

TIME_RANGE_OPTIONS = {
    "過去24時間": "when:1d",
    "過去3日":   "when:3d",
    "過去1週間": "when:7d",
    "すべて":    "",
}

CACHE_TTL_SECONDS = 1800  # 30分。これより短い間隔ではRSSを取りに行かない


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def parse_date(date_str: str) -> str:
    try:
        return parsedate_to_datetime(date_str).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return date_str or ""


def fetch_target(label: str, query: str, time_range: str) -> list[dict]:
    # 期間は tbs ではなくクエリ内の when: 演算子で指定する（RSSではこちらが効く）
    full_query = f"{query} {time_range}".strip() if time_range else query
    # hl=ja&gl=JP&ceid=JP:ja で日本語・日本のニュースに限定
    url = (
        f"https://news.google.com/rss/search"
        f"?q={quote(full_query)}&hl=ja&gl=JP&ceid=JP:ja"
    )
    feed = feedparser.parse(url)
    articles = []
    for entry in feed.entries:
        articles.append({
            "target":    label,
            "title":     strip_html(entry.get("title", "")),
            "url":       entry.get("link", ""),
            "source":    entry.get("source", {}).get("title", ""),
            "published": parse_date(entry.get("published", "")),
            # NOTE: Google News RSS の summary はタイトル+ソースの重複でしかないため保存しない
        })
    return articles


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner="最新ニュースを取得中…")
def fetch_all(time_range: str) -> tuple[pd.DataFrame, str]:
    """全対象をライブ取得してDataFrameと取得時刻を返す（30分キャッシュ）。"""
    rows = []
    for label, query in TARGETS.items():
        rows.extend(fetch_target(label, query, time_range))
    df = pd.DataFrame(rows).drop_duplicates(subset=["url"], keep="last")
    fetched_at = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    return df, fetched_at


# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(page_title="NEWSWIRE JP", page_icon="▮", layout="wide")

# ── Theme CSS (cyan phosphor wire-terminal / JP edition) ──────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Noto+Sans+JP:wght@400;500;700&display=swap');

:root {
    --accent: #4FC8D8;
    --accent-dim: #2E7E8A;
    --ink: #D8E2E8;
    --ink-dim: #7C8A94;
    --panel: #131920;
    --line: #24303A;
}

html, body, [class*="css"] { font-family: 'Noto Sans JP', sans-serif; }

/* App + sidebar backgrounds */
[data-testid="stAppViewContainer"] { background: #0B0F13; }
[data-testid="stSidebar"] {
    background: #0F151B;
    border-right: 1px solid var(--line);
}
[data-testid="stSidebar"] .stMarkdown p { font-size: 0.85rem; }

/* Masthead */
.wire-masthead {
    font-family: 'IBM Plex Mono', 'Noto Sans JP', monospace;
    display: flex; align-items: baseline; gap: 0.75rem; flex-wrap: wrap;
    border-bottom: 2px solid var(--accent);
    padding-bottom: 0.6rem; margin-bottom: 0.2rem;
}
.wire-masthead .title {
    color: var(--accent); font-size: 1.55rem; font-weight: 600;
    letter-spacing: 0.18em;
}
.wire-masthead .sub {
    color: var(--ink-dim); font-size: 0.75rem; letter-spacing: 0.08em;
}

/* Metrics row */
[data-testid="stMetric"] {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 6px;
    padding: 0.7rem 1rem;
}
[data-testid="stMetricLabel"] {
    font-family: 'IBM Plex Mono', 'Noto Sans JP', monospace;
    color: var(--ink-dim) !important;
    letter-spacing: 0.1em; font-size: 0.72rem !important;
}
[data-testid="stMetricValue"] {
    font-family: 'IBM Plex Mono', 'Noto Sans JP', monospace;
    color: var(--accent) !important;
}

/* Article card */
.wire-card {
    background: var(--panel);
    border: 1px solid var(--line);
    border-left: 3px solid var(--accent-dim);
    border-radius: 6px;
    padding: 0.85rem 1.1rem 0.75rem;
    margin-bottom: 0.65rem;
    transition: border-color 0.15s ease;
}
.wire-card:hover { border-left-color: var(--accent); }
.wire-card a.headline {
    color: var(--ink); text-decoration: none;
    font-size: 1.02rem; font-weight: 700; line-height: 1.55;
}
.wire-card a.headline:hover { color: var(--accent); }
.wire-meta {
    font-family: 'IBM Plex Mono', 'Noto Sans JP', monospace;
    font-size: 0.72rem; color: var(--ink-dim);
    margin-top: 0.45rem;
    display: flex; flex-wrap: wrap; gap: 0.9rem; align-items: center;
}
.wire-tag {
    color: var(--accent); border: 1px solid var(--accent-dim);
    border-radius: 3px; padding: 0.05rem 0.45rem;
    letter-spacing: 0.05em;
}

/* Sidebar section labels */
.side-label {
    font-family: 'IBM Plex Mono', 'Noto Sans JP', monospace;
    font-size: 0.7rem; letter-spacing: 0.14em;
    color: var(--ink-dim);
    margin: 0.9rem 0 0.25rem;
}
</style>
""", unsafe_allow_html=True)

st.markdown(
    '<div class="wire-masthead">'
    '<span class="title">NEWSWIRE<span style="color:var(--ink-dim)">/</span>JP</span>'
    '<span class="sub">google news 日本語版 · キオクシア / 日本電波工業 / 日経平均</span>'
    '</div>',
    unsafe_allow_html=True,
)

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    # 更新ボタンは最上部固定 — スクロール不要で常に見える
    if st.button("▶ 最新に更新", use_container_width=True, type="primary"):
        st.cache_data.clear()
        st.rerun()
    st.caption(f"自動で最新を表示（{CACHE_TTL_SECONDS // 60}分ごとに更新）")

    st.markdown('<div class="side-label">期間</div>', unsafe_allow_html=True)
    selected_range_label = st.selectbox(
        "期間",
        list(TIME_RANGE_OPTIONS.keys()),
        index=1,  # デフォルト「過去3日」
        label_visibility="collapsed",
    )
    selected_range = TIME_RANGE_OPTIONS[selected_range_label]

    st.markdown('<div class="side-label">ソース絞り込み</div>', unsafe_allow_html=True)
    major_only = st.checkbox(
        "大手・人気メディアのみ", value=True,
        help="全国紙・テレビ・通信社・主要経済誌・Yahoo!/株探などに限定。"
             "（日経は『大手』に含まれますが、『有料記事ソースを除外』をオンにすると外れます）",
    )
    exclude_paywall = st.checkbox("有料記事ソースを除外", value=True)

    st.markdown('<div class="side-label">1対象あたりの最大件数</div>', unsafe_allow_html=True)
    max_per_target = st.slider(
        "1対象あたりの最大件数",
        min_value=3, max_value=30, value=10,
        label_visibility="collapsed",
    )

# ── ライブ取得 ───────────────────────────────────────────────────────────────────
df, fetched_at = fetch_all(selected_range)

if major_only and not df.empty:
    df = df[df["source"].apply(is_major_source)]

if exclude_paywall and not df.empty:
    df = df[~df["source"].isin(PAYWALLED_SOURCES)]

# 対象ごとに新しい順で最大N件まで絞る（ここで df 本体を間引くので metric も連動する）
if not df.empty:
    df = (
        df.sort_values("published", ascending=False)
          .groupby("target", group_keys=False)
          .head(max_per_target)
    )

if df.empty:
    st.info("📭 該当するニュースが見つかりませんでした。期間を広げてみてください。")
    st.stop()

# Stats
c1, c2, c3 = st.columns(3)
c1.metric("記事数", len(df))
c2.metric("対象数", df["target"].nunique())
c3.metric("取得時刻 (JST)", fetched_at)

st.write("")

# Filters
f1, f2, f3 = st.columns([2, 2, 3])
with f1:
    tgt_opts = ["すべての対象"] + [t for t in TARGETS if t in df["target"].values]
    filter_tgt = st.selectbox("対象", tgt_opts, label_visibility="collapsed")
with f2:
    sources = sorted(s for s in df["source"].dropna().unique().tolist() if s)
    filter_srcs = st.multiselect(
        "ソース",
        sources,
        placeholder="📡 ソースで絞り込み（未選択=すべて）",
        label_visibility="collapsed",
    )
with f3:
    search_q = st.text_input("検索", placeholder="🔍 タイトルを検索…", label_visibility="collapsed")

# Apply filters
df_view = df.copy()
if filter_tgt != "すべての対象":
    df_view = df_view[df_view["target"] == filter_tgt]
if filter_srcs:
    df_view = df_view[df_view["source"].isin(filter_srcs)]
if search_q.strip():
    df_view = df_view[
        df_view["title"].str.lower().str.contains(search_q.strip().lower(), na=False)
    ]

# Sort newest first（件数キャップは取得直後に df 側で適用済み）
df_view = df_view.sort_values("published", ascending=False)

st.caption(f"{len(df)}件中 {len(df_view)}件を表示（対象ごと最大{max_per_target}件）")

# Article cards
for _, row in df_view.iterrows():
    title = html.escape(str(row["title"]))
    url = html.escape(str(row["url"]), quote=True)
    source = html.escape(str(row.get("source") or ""))
    published = html.escape(str(row.get("published") or ""))
    target = html.escape(str(row["target"]))

    meta_bits = []
    if source:
        meta_bits.append(f"<span>{source}</span>")
    if published:
        meta_bits.append(f"<span>{published}</span>")
    meta_bits.append(f'<span class="wire-tag">{target}</span>')

    st.markdown(
        f'<div class="wire-card">'
        f'<a class="headline" href="{url}" target="_blank">{title}</a>'
        f'<div class="wire-meta">{"".join(meta_bits)}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
