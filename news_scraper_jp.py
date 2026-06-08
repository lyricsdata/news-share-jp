# streamlit run news_scraper_jp.py
# Requires: pip install feedparser
#
# 日本語ニュース版。Google ニュース日本語版(RSS)をキーワード検索して収集する。
# 対象: キオクシア / 日本電波工業 / 日経平均

import streamlit as st
import pandas as pd
import feedparser
import re
import os
from urllib.parse import quote
from datetime import datetime
from email.utils import parsedate_to_datetime

CSV_FILE = "news_data_jp.csv"
LAST_FETCHED_FILE = "last_fetched_jp.txt"

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


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def parse_date(date_str: str) -> str:
    try:
        return parsedate_to_datetime(date_str).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return date_str or ""


def fetch_target(label: str, query: str, time_range: str = "qdr:d") -> list[dict]:
    import time as _time
    tbs = f"&tbs={time_range}" if time_range else ""
    # hl=ja&gl=JP&ceid=JP:ja で日本語・日本のニュースに限定
    url = (
        f"https://news.google.com/rss/search"
        f"?q={quote(query)}{tbs}&hl=ja&gl=JP&ceid=JP:ja&_={int(_time.time())}"
    )
    feed = feedparser.parse(
        url,
        request_headers={"Cache-Control": "no-cache", "Pragma": "no-cache"},
    )
    fetched_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    articles = []
    for entry in feed.entries:
        source = entry.get("source", {}).get("title", "")
        articles.append({
            "target":     label,
            "title":      strip_html(entry.get("title", "")),
            "url":        entry.get("link", ""),
            "source":     source,
            "published":  parse_date(entry.get("published", "")),
            "summary":    strip_html(entry.get("summary", "")),
            "fetched_at": fetched_at,
        })
    return articles


def load_csv() -> pd.DataFrame:
    if os.path.exists(CSV_FILE):
        return pd.read_csv(CSV_FILE)
    return pd.DataFrame()


def save_to_csv(new_articles: list[dict]) -> pd.DataFrame:
    new_df = pd.DataFrame(new_articles)
    if os.path.exists(CSV_FILE):
        existing = pd.read_csv(CSV_FILE)
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df
    combined = combined.drop_duplicates(subset=["url"], keep="last")
    combined.to_csv(CSV_FILE, index=False)
    return combined


# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(page_title="日本語ニュース収集", page_icon="📰", layout="wide")
st.title("📰 日本語ニュース収集")
st.caption("Google ニュース日本語版(RSS)から、選択した銘柄のニュースを集めます")

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 設定")
    st.write("**対象**")

    selected_targets = []
    for label in TARGETS:
        if st.checkbox(label, value=True, key=f"tgt_{label}"):
            selected_targets.append(label)

    st.divider()
    st.write("**期間**")
    selected_range_label = st.selectbox(
        "期間",
        list(TIME_RANGE_OPTIONS.keys()),
        index=0,
        label_visibility="collapsed",
    )
    selected_range = TIME_RANGE_OPTIONS[selected_range_label]

    exclude_paywall = st.checkbox("有料記事ソースを除外", value=True)

    st.divider()
    fetch_clicked = st.button("🔄 ニュース取得", use_container_width=True, type="primary")

    df_sidebar = load_csv()
    if not df_sidebar.empty:
        csv_bytes = df_sidebar.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "⬇️ CSVダウンロード", csv_bytes, "news_data_jp.csv", "text/csv",
            use_container_width=True,
        )
        if st.button("🗑️ データを全消去", use_container_width=True):
            os.remove(CSV_FILE)
            st.rerun()

# ── Fetch logic ────────────────────────────────────────────────────────────────
if fetch_clicked:
    if not selected_targets:
        st.error("対象を1つ以上選んでください。")
        st.stop()

    all_articles = []
    progress_bar = st.progress(0, text="開始中…")

    for i, label in enumerate(selected_targets):
        progress_bar.progress((i + 1) / len(selected_targets), text=f"取得中: {label}…")
        articles = fetch_target(label, TARGETS[label], selected_range)
        if exclude_paywall:
            articles = [a for a in articles if a["source"] not in PAYWALLED_SOURCES]
        all_articles.extend(articles)

    df_saved = save_to_csv(all_articles)
    progress_bar.empty()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(LAST_FETCHED_FILE, "w", encoding="utf-8") as f:
        f.write(now_str)
    st.success(
        f"✅ {len(all_articles)}件取得 → 重複除外後 合計{len(df_saved)}件"
    )
    st.rerun()

# ── Main display ───────────────────────────────────────────────────────────────
df = load_csv()

if df.empty:
    st.info("📭 まだデータがありません。対象を選んで **ニュース取得** を押してください。")
    st.stop()

# Stats
c1, c2, c3 = st.columns(3)
c1.metric("📰 記事数", len(df))
c2.metric("🎯 対象数", df["target"].nunique())
_lf = open(LAST_FETCHED_FILE, encoding="utf-8").read().strip() if os.path.exists(LAST_FETCHED_FILE) else "—"
c3.metric("🕐 最終取得", _lf)

st.divider()

# Filters
f1, f2, f3 = st.columns([2, 2, 3])
with f1:
    tgt_opts = ["すべての対象"] + [t for t in TARGETS if t in df["target"].values]
    filter_tgt = st.selectbox("対象", tgt_opts, label_visibility="collapsed")
with f2:
    sources = sorted(df["source"].dropna().unique().tolist()) if "source" in df.columns else []
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
if "published" in df_view.columns:
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
