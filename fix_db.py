import sqlite3

# データベースに接続
conn = sqlite3.connect('news_app.db')
cursor = conn.cursor()

try:
    # 保存用の列を追加する命令を実行
    cursor.execute("ALTER TABLE articles ADD COLUMN is_saved INTEGER DEFAULT 0")
    conn.commit()
    print("✅ 成功しました！'is_saved' 列を追加しました。")
except sqlite3.OperationalError:
    # すでに列がある場合はこのエラーが出るので、問題なし
    print("ℹ️ すでに 'is_saved' 列は存在しています。作業は不要です。")
except Exception as e:
    print(f"❌ エラーが発生しました: {e}")

conn.close()