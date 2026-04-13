from flask import Flask, render_template, redirect, request, session, jsonify
import sqlite3
import os
import random
import time
import sendgrid
from sendgrid.helpers.mail import Mail
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
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key-change-in-prod")
init_db()

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@example.com")

def send_otp_email(to_email, code):
    sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
    message = Mail(
        from_email=FROM_EMAIL,
        to_emails=to_email,
        subject="【ニュースアプリ】ログインコード",
        plain_text_content=f"ログインコード: {code}\n\nこのコードは5分間有効です。"
    )
    sg.send(message)

def get_current_user():
    return session.get("user_email")

# ---------------- RANDOM ----------------
UPDATE_HOURS = [5, 11, 17]  # 5:30, 11:30, 17:30
UPDATE_MINUTE = 30

def should_fetch():
    """指定時刻（5:30, 11:30, 17:30）のみ更新する"""
    import datetime
    now = datetime.datetime.now()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key='last_fetch'")
    row = c.fetchone()
    conn.close()
    if not row:
        return True
    last = datetime.datetime.fromtimestamp(int(row[0]))
    # 最後の更新以降に更新時刻を跨いだか確認
    for h in UPDATE_HOURS:
        update_time = now.replace(hour=h, minute=UPDATE_MINUTE, second=0, microsecond=0)
        if last < update_time <= now:
            return True
    return False

@app.route('/')
def index():
    if should_fetch():
        NewsManager.fetch_and_store()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, title, source, link, is_read, is_saved FROM articles ORDER BY id DESC")
    articles = c.fetchall()
    conn.close()
    return render_template('index.html', articles=articles, page_title="RANDOM", user=get_current_user())

# ---------------- ホーム（無限ニュース）----------------
@app.route('/home')
def home():
    if not get_current_user():
        return redirect('/login?next=/home')
    return render_template('home.html', user=get_current_user())

# ---------------- SAVED ----------------
@app.route('/saved')
def saved():
    if not get_current_user():
        return redirect('/login?next=/saved')
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, title, source, link, is_read, is_saved FROM articles WHERE is_saved = 1 ORDER BY id DESC")
    articles = c.fetchall()
    conn.close()
    return render_template('index.html', articles=articles, page_title="SAVED", user=get_current_user())

# ---------------- 保存 ----------------
@app.route('/save/<int:article_id>')
def save_article(article_id):
    if not get_current_user():
        return jsonify({"error": "login_required"}), 401
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE articles SET is_saved = 1, is_read = 1 WHERE id = ?", (article_id,))
    conn.commit()
    conn.close()
    return "OK"

# ---------------- 保存解除 ----------------
@app.route('/delete/<int:article_id>')
def delete_article(article_id):
    if not get_current_user():
        return redirect('/login')
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
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE articles SET summary = ? WHERE id = ?", (summary, article_id))
    conn.commit()
    conn.close()
    return f"【AI要約】\n{summary}"

# ---------------- ログイン ----------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    next_url = request.args.get('next', '/')
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        if not email:
            return render_template('login.html', error="メールアドレスを入力してください", next=next_url)
        # OTPを生成して送信
        code = str(random.randint(100000, 999999))
        expires_at = int(time.time()) + 300  # 5分
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO otp_codes (email, code, expires_at) VALUES (?, ?, ?)", (email, code, expires_at))
        conn.commit()
        conn.close()
        try:
            send_otp_email(email, code)
        except Exception as e:
            return render_template('login.html', error=f"メール送信に失敗しました: {e}", next=next_url)
        session['otp_email'] = email
        session['otp_next'] = next_url
        return redirect('/otp')
    return render_template('login.html', next=next_url)

# ---------------- OTP確認 ----------------
@app.route('/otp', methods=['GET', 'POST'])
def otp():
    email = session.get('otp_email')
    if not email:
        return redirect('/login')
    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""SELECT id FROM otp_codes 
                     WHERE email=? AND code=? AND used=0 AND expires_at>?
                     ORDER BY id DESC LIMIT 1""",
                  (email, code, int(time.time())))
        row = c.fetchone()
        if not row:
            conn.close()
            return render_template('otp.html', error="コードが違うか期限切れです", email=email)
        c.execute("UPDATE otp_codes SET used=1 WHERE id=?", (row[0],))
        c.execute("INSERT OR IGNORE INTO users (email) VALUES (?)", (email,))
        conn.commit()
        conn.close()
        session['user_email'] = email
        session.pop('otp_email', None)
        next_url = session.pop('otp_next', '/')
        return redirect(next_url)
    return render_template('otp.html', email=email)

# ---------------- OTP再送信 ----------------
@app.route('/resend-otp', methods=['POST'])
def resend_otp():
    email = session.get('otp_email')
    if not email:
        return "NG", 400
    code = str(random.randint(100000, 999999))
    expires_at = int(time.time()) + 300
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO otp_codes (email, code, expires_at) VALUES (?, ?, ?)", (email, code, expires_at))
    conn.commit()
    conn.close()
    try:
        send_otp_email(email, code)
    except Exception as e:
        return f"NG: {e}", 500
    return "OK"

# ---------------- ログアウト ----------------
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# ---------------- 更新 ----------------
@app.route('/refresh')
def refresh():
    NewsManager.fetch_and_store()
    return redirect('/')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
