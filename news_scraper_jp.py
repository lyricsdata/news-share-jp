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
from urllib.parse import quote
from datetime import datetime
from email.utils import parsedate_to_datetime

# 有料記事が多いソース（チェックボックスで除外できる）
PAYWALLED_SOURCES = {
    "日本経済新聞", "日経電子版", "日経ビジネス", "日経クロステック",
    "Bloomberg", "ブルームバーグ",
    "ウォール・ストリート・ジャーナル", "The Wall Street Journal",
    "Financial Times", "東洋経済オンライン",
}

# 表示名 → Google ニュース検索クエリ
TARGETS = {
    "キオクシア":     "キオクシア",
    "日本電波工業":   "日本電波工業",
    "日経平均":       "日経平均株価",
}

TIME_RANGE_OPTIONS = {
    "過去24時間": "qdr:d",
    "過去3日":   "qdr:3d",
    "過去1週間": "qdr:w",
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
    tbs = f"&tbs={time_range}" if time_range else ""
    # hl=ja&gl=JP&ceid=JP:ja で日本語・日本のニュースに限定
    url = (
        f"https://news.google.com/rss/search"
        f"?q={quote(query)}{tbs}&hl=ja&gl=JP&ceid=JP:ja"
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
            "summary":   strip_html(entry.get("summary", "")),
        })
    return articles


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner="最新ニュースを取得中…")
def fetch_all(time_range: str) -> tuple[pd.DataFrame, str]:
    """全対象をライブ取得してDataFrameと取得時刻を返す（30分キャッシュ）。"""
    rows = []
    for label, query in TARGETS.items():
        rows.extend(fetch_target(label, query, time_range))
    df = pd.DataFrame(rows).drop_duplicates(subset=["url"], keep="last")
    fetched_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    return df, fetched_at


# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(page_title="日本語ニュース", page_icon="📰", layout="wide")
st.title("📰 日本語ニュース")
st.caption("キオクシア・日本電波工業・日経平均の最新ニュース（Google ニュース日本語版）")

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 設定")

    st.write("**期間**")
    selected_range_label = st.selectbox(
        "期間",
        list(TIME_RANGE_OPTIONS.keys()),
        index=1,  # デフォルト「過去3日」
        label_visibility="collapsed",
    )
    selected_range = TIME_RANGE_OPTIONS[selected_range_label]

    exclude_paywall = st.checkbox("有料記事ソースを除外", value=True)

    st.divider()
    if st.button("🔄 最新に更新", use_container_width=True, type="primary"):
        st.cache_data.clear()
        st.rerun()
    st.caption(f"※ 自動で最新を表示します（{CACHE_TTL_SECONDS // 60}分ごとに更新）")

# ── ライブ取得 ───────────────────────────────────────────────────────────────────
df, fetched_at = fetch_all(selected_range)

if exclude_paywall and not df.empty:
    df = df[~df["source"].isin(PAYWALLED_SOURCES)]

if df.empty:
    st.info("📭 該当するニュースが見つかりませんでした。期間を広げてみてください。")
    st.stop()

# Stats
c1, c2, c3 = st.columns(3)
c1.metric("📰 記事数", len(df))
c2.metric("🎯 対象数", df["target"].nunique())
c3.metric("🕐 取得時刻", fetched_at)

st.divider()

# Filters
f1, f2, f3 = st.columns([2, 2, 3])
with f1:
    tgt_opts = ["すべての対象"] + [t for t in TARGETS if t in df["target"].values]
    filter_tgt = st.selectbox("対象", tgt_opts, label_visibility="collapsed")
with f2:
    sources = sorted(df["source"].dropna().unique().tolist())
    src_opts = ["すべてのソース"] + sources
    filter_src = st.selectbox("ソース", src_opts, label_visibility="collapsed")
with f3:
    search_q = st.text_input("検索", placeholder="🔍 タイトルを検索…", label_visibility="collapsed")

# Apply filters
df_view = df.copy()
if filter_tgt != "すべての対象":
    df_view = df_view[df_view["target"] == filter_tgt]
if filter_src != "すべてのソース":
    df_view = df_view[df_view["source"] == filter_src]
if search_q.strip():
    df_view = df_view[
        df_view["title"].str.lower().str.contains(search_q.strip().lower(), na=False)
    ]

# Sort newest first
df_view = df_view.sort_values("published", ascending=False)

st.caption(f"{len(df)}件中 {len(df_view)}件を表示")

# Article cards
for _, row in df_view.iterrows():
    st.markdown(f"**[{row['title']}]({row['url']})**")

    meta_parts = []
    if row.get("source"):
        meta_parts.append(f"📡 {row['source']}")
    if row.get("published"):
        meta_parts.append(f"🗓 {row['published']}")
    meta_parts.append(f"`{row['target']}`")
    st.caption("  |  ".join(meta_parts))

    summary = str(row.get("summary", "")).strip()
    if summary:
        with st.expander("概要"):
            st.write(summary)

    st.divider()
