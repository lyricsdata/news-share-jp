# 日本語ニュース収集アプリ

キオクシア・日本電波工業・日経平均のニュースを Google ニュース日本語版(RSS)から集めて表示する Streamlit アプリ。

## 公開URL
（Streamlit Community Cloud にデプロイ後、ここにURLを貼る）

## ローカル実行
```bash
pip install -r requirements.txt
streamlit run news_scraper_jp.py
```

## ファイル
- `news_scraper_jp.py` … アプリ本体
- `news_data_jp.csv` … 取得済みニュースデータ（初期表示用）
- `requirements.txt` … 依存ライブラリ
