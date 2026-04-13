from flask import Flask, render_template, redirect, request
import sqlite3
import os
from services import NewsManager
from models import init_db, DB_PATH

# .envファイルがあれば読み込む
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                os.environ.setdefault(key.strip(), val.strip())
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = Flask(__name__)
init_db()

# ---------------- HOME ----------------
@app.route('/')
def index():
    NewsManager.fetch_and_store()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, title, source, link, is_read, is_saved
        FROM articles
        ORDER BY id DESC
    """)
    articles = c.fetchall()
    conn.close()
    return render_template('index.html', articles=articles, page_title="HOME")

# ---------------- SAVED ----------------
@app.route('/saved')
def saved():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, title, source, link, is_read, is_saved
        FROM articles
        WHERE is_saved = 1
        ORDER BY id DESC
    """)
    articles = c.fetchall()
    conn.close()
    return render_template('index.html', articles=articles, page_title="SAVED")

# ---------------- 保存解除 ----------------
@app.route('/delete/<int:article_id>')
def delete_article(article_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE articles SET is_saved = 0 WHERE id = ?", (article_id,))
    conn.commit()
    conn.close()
    return redirect('/saved')

# ---------------- 記事を読む ----------------
@app.route('/read/<int:article_id>')
def read(article_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        c.execute("UPDATE articles SET is_read = 1 WHERE id = ?", (article_id,))
        conn.commit()
        conn.close()
        return "OK"

    c.execute("SELECT link FROM articles WHERE id = ?", (article_id,))
    res = c.fetchone()
    conn.close()
    return redirect(res[0]) if res else redirect('/')

# ---------------- AI要約 ----------------
@app.route('/summarize/<int:article_id>')
def summarize(article_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT title FROM articles WHERE id = ?", (article_id,))
    res = c.fetchone()

    if not res:
        conn.close()
        return "記事が見つかりませんでした", 404

    title = res[0]

    # 保存フラグON（既読にはしない）
    c.execute("UPDATE articles SET is_saved = 1 WHERE id = ?", (article_id,))
    conn.commit()
    conn.close()

    prompt = f"次のニュース記事タイトルに関する3点要約を日本語で出力してください：『{title}』"

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        summary = response.choices[0].message.content.strip()
    except Exception as e:
        return f"AI要約中にエラーが発生しました: {e}", 500

    # 要約を保存
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE articles SET summary = ? WHERE id = ?", (summary, article_id))
    conn.commit()
    conn.close()

    return f"【AI要約】\n{summary}"

# ---------------- 更新 ----------------
@app.route('/refresh')
def refresh():
    NewsManager.fetch_and_store()
    return redirect('/')

# ---------------- 保存 ----------------
@app.route('/save/<int:article_id>')
def save_article(article_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE articles SET is_saved = 1, is_read = 1 WHERE id = ?", (article_id,))
    conn.commit()
    conn.close()
    return "OK"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
