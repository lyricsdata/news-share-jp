# cd C:\Users\onetw\PyCharmMiscProject\news_share
# streamlit run news_scraper_jp.py

# Requires: pip install streamlit pandas feedparser yfinance
#
# 日本語ニュース版（ライブ取得方式）。
# 開かれるたびに Google ニュース日本語版(RSS)から最新を取得して表示する。
# データはCSVに保存せず、@st.cache_data(ttl=30分)でキャッシュするだけ。
# → 共有相手はいつ開いても「常に最新」を見られる。
# 対象: キオクシア / 日本電波工業 / 日経平均（?targets= で変更可）

import streamlit as st
import pandas as pd
import feedparser
import yfinance as yf
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

# 表示名 → {検索クエリ, yfinanceティッカー}。ティッカーはフェーズ2の株価表示で使用。
STOCK_CONFIG = {
    "キオクシア":     {"query": "キオクシア",     "ticker": "285A.T"},
    "日本電波工業":   {"query": "日本電波工業",   "ticker": "6779.T"},
    "日経平均":       {"query": '"日経平均株価"', "ticker": "^N225"},
    # 追加登録用（デフォルト対象には含めないが、?targets=で指定すると株価も出せる）
    "ソニー":         {"query": "ソニーグループ", "ticker": "6758.T"},
    "任天堂":         {"query": "任天堂",         "ticker": "7974.T"},
    "トヨタ":         {"query": "トヨタ自動車",   "ticker": "7203.T"},
}
DEFAULT_TARGETS = ["キオクシア", "日本電波工業", "日経平均"]


def resolve_targets() -> dict[str, str]:
    """URLパラメータ ?targets=名前1,名前2 から対象名→検索クエリの辞書を解決する。

    - パラメータなし/空 → DEFAULT_TARGETS
    - STOCK_CONFIG に登録済みの名前 → 登録済みクエリを使用（株価も表示対象になりうる）
    - 未登録の名前 → 名前そのものを検索クエリとして使う（ニュースのみ、株価なし）
    """
    raw = st.query_params.get("targets", "")
    names = [n.strip() for n in raw.split(",")] if raw else []
    names = [n for n in names if n]
    if not names:
        names = DEFAULT_TARGETS
    return {
        name: STOCK_CONFIG[name]["query"] if name in STOCK_CONFIG else name
        for name in names
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
        # RSSのpubDateはソースによりタイムゾーンがまちまち（EST等）なので、
        # 表示前に必ずJSTへ変換する。
        return parsedate_to_datetime(date_str).astimezone(JST).strftime("%Y-%m-%d %H:%M")
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


STOCK_QUOTE_TTL_SECONDS = 900  # 15分。ニュースの30分キャッシュとは独立


@st.cache_data(ttl=STOCK_QUOTE_TTL_SECONDS, show_spinner=False)
def fetch_stock_quotes(tickers: tuple[str, ...]) -> dict[str, dict[str, float]]:
    """ティッカーごとに現在値・前日比を取得する（15分キャッシュ）。

    ネットワーク障害・上場廃止・レート制限などで個別ティッカーの取得に失敗しても、
    その銘柄を結果から除くだけでアプリ全体は止めない。
    """
    quotes: dict[str, dict[str, float]] = {}
    for ticker in tickers:
        try:
            info = yf.Ticker(ticker).fast_info
            price = info.last_price
            prev_close = info.previous_close
            if price is None or prev_close is None:
                continue
            change = price - prev_close
            change_pct = (change / prev_close * 100) if prev_close else 0.0
            quotes[ticker] = {
                "price": price,
                "prev_close": prev_close,
                "change": change,
                "change_pct": change_pct,
            }
        except Exception:
            continue
    return quotes


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner="最新ニュースを取得中…")
def fetch_all(time_range: str, targets: dict[str, str]) -> tuple[pd.DataFrame, str]:
    """全対象をライブ取得してDataFrameと取得時刻を返す（30分キャッシュ）。"""
    rows = []
    for label, query in targets.items():
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
/* Streamlitは値を内側のdivで nowrap+ellipsis 表示するため、そちらも上書きする必要がある */
[data-testid="stMetricValue"], [data-testid="stMetricValue"] div {
    white-space: normal !important;
    overflow: visible !important;
    text-overflow: unset !important;
    word-break: break-word;
    line-height: 1.3;
    width: auto !important;
}
@media (max-width: 480px) {
    [data-testid="stMetricValue"] { font-size: 1.4rem !important; }
}

/* Stock quote row (phase 2) */
.stock-row {
    display: flex; flex-wrap: wrap; gap: 0.6rem;
    margin: 0.6rem 0 0.3rem;
}
.stock-card {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 6px;
    padding: 0.55rem 0.9rem;
    font-family: 'IBM Plex Mono', 'Noto Sans JP', monospace;
    min-width: 150px;
}
.stock-card .stock-label {
    color: var(--ink-dim); font-size: 0.7rem; letter-spacing: 0.05em;
}
.stock-card .stock-price {
    color: var(--ink); font-size: 1.15rem; font-weight: 600; margin-top: 0.15rem;
}
.stock-card .stock-delta { font-size: 0.78rem; margin-top: 0.1rem; }
.stock-up { color: #4CC97A; }
.stock-down { color: #E0616B; }
.stock-note {
    color: var(--ink-dim); font-size: 0.68rem;
    margin: 0 0 0.7rem;
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
.new-badge {
    color: #F0A840; border: 1px solid #F0A840;
    border-radius: 3px; padding: 0.05rem 0.45rem;
    letter-spacing: 0.05em; font-weight: 700;
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

# URLパラメータ ?targets=名前1,名前2 で対象を切り替える（省略時はデフォルト3対象）
active_targets = resolve_targets()

st.markdown(
    '<div class="wire-masthead">'
    '<span class="title">NEWSWIRE<span style="color:var(--ink-dim)">/</span>JP</span>'
    f'<span class="sub">google news 日本語版 · {html.escape(" / ".join(active_targets.keys()))}</span>'
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
df, fetched_at = fetch_all(selected_range, active_targets)

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

# ── NEWバッジ判定 ────────────────────────────────────────────────────────────────
# 対象/ソース/検索の絞り込み（f1/f2/f3）は表示だけを変えるものなので、
# NEW判定はそれらを適用する前のdf全体のURL集合を基準にする
# （フィルタを切り替えただけで誤ってNEW表示が変わらないようにするため）。
current_urls = set(df["url"])
if "seen_urls" in st.session_state:
    new_urls = current_urls - st.session_state["seen_urls"]
else:
    # 初回表示は比較対象がないため全記事NEW扱いになってしまう。
    # うるさいだけなので初回はバッジなしとし、集合の記録だけ行う。
    new_urls = set()
st.session_state["seen_urls"] = current_urls

# Stats
c1, c2, c3 = st.columns(3)
c1.metric("記事数", len(df))
c2.metric("対象数", df["target"].nunique())
c3.metric("取得時刻 (JST)", fetched_at)

# ── 株価スニペット（表示中の対象のうちtickerを持つものだけ） ──────────────────────
stock_targets = [
    (label, STOCK_CONFIG[label]["ticker"])
    for label in active_targets
    if label in STOCK_CONFIG and STOCK_CONFIG[label].get("ticker")
]
if stock_targets:
    quotes = fetch_stock_quotes(tuple(ticker for _, ticker in stock_targets))
    cards_html = []
    for label, ticker in stock_targets:
        q = quotes.get(ticker)
        if not q:
            continue
        direction = "stock-up" if q["change"] >= 0 else "stock-down"
        sign = "+" if q["change"] >= 0 else ""
        cards_html.append(
            f'<div class="stock-card">'
            f'<div class="stock-label">{html.escape(label)} '
            f'<span style="opacity:.6">{html.escape(ticker)}</span></div>'
            f'<div class="stock-price">{q["price"]:,.1f}</div>'
            f'<div class="stock-delta {direction}">{sign}{q["change"]:,.1f} '
            f'（{sign}{q["change_pct"]:.2f}%）</div>'
            f'</div>'
        )
    if cards_html:
        st.markdown(f'<div class="stock-row">{"".join(cards_html)}</div>', unsafe_allow_html=True)
        st.markdown('<div class="stock-note">※ 株価は15〜20分遅延</div>', unsafe_allow_html=True)

st.write("")

# Filters
f1, f2, f3 = st.columns([2, 2, 3])
with f1:
    tgt_opts = ["すべての対象"] + [t for t in active_targets if t in df["target"].values]
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
    if row["url"] in new_urls:
        meta_bits.append('<span class="new-badge">NEW</span>')
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
