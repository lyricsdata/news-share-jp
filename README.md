# 日本語ニュース収集アプリ

キオクシア・日本電波工業・日経平均のニュースを Google ニュース日本語版(RSS)から集めて表示する Streamlit アプリ。

## 公開URL
（Streamlit Community Cloud にデプロイ後、ここにURLを貼る）

## ローカル実行
```bash
pip install -r requirements.txt
streamlit run news_scraper_jp.py
```

## 仕組み
開かれるたびに Google ニュース日本語版(RSS)から最新を取得して表示する（ライブ取得方式）。
データはCSV保存せず、30分キャッシュするだけなので、いつ開いても常に最新が見える。

## ファイル
- `news_scraper_jp.py` … アプリ本体
- `requirements.txt` … 依存ライブラリ
