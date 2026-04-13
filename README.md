# News App

Google NewsのRSSをランダムに3件取得し、カード形式で読めるニュースリーダーアプリ。

## 機能

- ニュース記事をカード表示（Google News RSS）
- スワイプ / 矢印キーで記事を切り替え
- 上スワイプ / ↑キー で保存
- AI要約（GPT-4o-mini）
- 保存記事の管理

## 操作方法

| 操作 | 動作 |
|------|------|
| タップ / Enter | 記事を開く（既読） |
| 左右スワイプ / ←→ | 記事をめくる |
| 上スワイプ / ↑ | 保存する |
| AI要約ボタン | GPTで要約を表示 |

## 技術スタック

- Python / Flask
- SQLite
- feedparser（Google News RSS）
- OpenAI API（gpt-4o-mini）

## セットアップ

```bash
pip install -r requirements.txt
export OPENAI_API_KEY=your_key_here
python app.py
```

## Renderへのデプロイ

1. GitHubにリポジトリを作成してpush
2. [Render.com](https://render.com) でNew > Web Service
3. リポジトリを接続
4. 以下を設定：
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
   - **Environment Variable**: `OPENAI_API_KEY` = あなたのAPIキー
5. Deployをクリック

> **注意**: RenderのフリープランはSQLiteが再デプロイのたびにリセットされます。  
> 保存データを永続化したい場合はRender PostgreSQLへの移行を検討してください。
