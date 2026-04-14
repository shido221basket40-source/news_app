import hashlib
import logging
import os
import random
import secrets
import time

import sendgrid
from flask import Flask, jsonify, redirect, render_template, request, session
from openai import OpenAI
from sendgrid.helpers.mail import Mail

from models import get_conn, init_db, is_postgres, pq
from services import NewsManager

# ── ロガー設定 ──────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s')
logger = logging.getLogger(__name__)

# ── .env 読み込み ────────────────────────────────────────
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _key, _val = _line.split('=', 1)
                os.environ.setdefault(_key.strip(), _val.strip())

# ── アプリ初期化 ─────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key-change-in-prod")
init_db()

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@example.com")

GENRES = [
    'スポーツ', 'テクノロジー', '政治', '経済', 'エンタメ',
    '科学', '健康', '国際', '社会', '芸能', 'ビジネス', '教育',
    '気象', '犯罪', 'IT', 'AI', '環境', '医療', 'スタートアップ', '文化',
]

UPDATE_HOURS = [5, 11, 17]
UPDATE_MINUTE = 30


# ── ユーティリティ ───────────────────────────────────────

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def get_current_user():
    return session.get("user_email")


def send_otp_email(to_email: str, code: str):
    sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
    message = Mail(
        from_email=FROM_EMAIL,
        to_emails=to_email,
        subject="【ニュースアプリ】ログインコード",
        plain_text_content=f"ログインコード: {code}\n\nこのコードは5分間有効です。",
    )
    sg.send(message)


def should_fetch() -> bool:
    import datetime
    now = datetime.datetime.now()
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key='last_fetch'")
    row = c.fetchone()
    conn.close()
    if not row:
        return True
    last = datetime.datetime.fromtimestamp(int(row[0]))
    for h in UPDATE_HOURS:
        update_time = now.replace(hour=h, minute=UPDATE_MINUTE, second=0, microsecond=0)
        if last < update_time <= now:
            return True
    return False


def get_user_genres(email: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute(pq("SELECT genre1, genre2 FROM user_genres WHERE email=?"), (email,))
    row = c.fetchone()
    conn.close()
    return row if row else ('', '')


# ── ルーティング ─────────────────────────────────────────

@app.route('/')
def index():
    user = get_current_user()
    if should_fetch():
        NewsManager.fetch_and_store()

    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, title, source, link, is_read, is_saved FROM articles ORDER BY id DESC")
    all_articles = c.fetchall()
    conn.close()

    if user:
        genre1, genre2 = get_user_genres(user)

        def filter_by_genre(articles, keyword):
            if not keyword:
                return []
            return [a for a in articles if keyword in (a[1] or '')]

        g1_articles = filter_by_genre(all_articles, genre1)[:1]
        g2_articles = filter_by_genre(all_articles, genre2)[:1]
        used_ids = {a[0] for a in g1_articles + g2_articles}
        remaining = [a for a in all_articles if a[0] not in used_ids]
        random_pick = random.sample(remaining, min(1, len(remaining))) if remaining else []
        articles = g1_articles + g2_articles + random_pick
    else:
        genre1, genre2 = '', ''
        g1_articles, g2_articles = [], []
        articles = random.sample(all_articles, min(3, len(all_articles))) if all_articles else []

    return render_template(
        'index.html',
        articles=articles,
        page_title="RANDOM",
        user=user,
        genre1=genre1,
        genre2=genre2,
        g1_empty=(genre1 and not g1_articles),
        g2_empty=(genre2 and not g2_articles),
    )


@app.route('/genre', methods=['GET', 'POST'])
def genre():
    user = get_current_user()
    if not user:
        return redirect('/login?next=/genre')

    if request.method == 'POST':
        g1 = request.form.get('genre1', '').strip()
        g2 = request.form.get('genre2', '').strip()
        conn = get_conn()
        c = conn.cursor()
        if is_postgres():
            c.execute(
                "INSERT INTO user_genres (email, genre1, genre2) VALUES (%s,%s,%s) "
                "ON CONFLICT (email) DO UPDATE SET genre1=EXCLUDED.genre1, genre2=EXCLUDED.genre2",
                (user, g1, g2)
            )
        else:
            c.execute(
                "INSERT OR REPLACE INTO user_genres (email, genre1, genre2) VALUES (?,?,?)",
                (user, g1, g2)
            )
        conn.commit()
        conn.close()
        return redirect('/')

    g1, g2 = get_user_genres(user)
    return render_template('genre.html', genre1=g1, genre2=g2, user=user, genres=GENRES)


@app.route('/saved')
def saved():
    if not get_current_user():
        return redirect('/login?next=/saved')
    conn = get_conn()
    c = conn.cursor()
    if is_postgres():
        c.execute("SELECT id, title, source, link, is_read, is_saved FROM articles WHERE is_saved = TRUE ORDER BY id DESC")
    else:
        c.execute("SELECT id, title, source, link, is_read, is_saved FROM articles WHERE is_saved = 1 ORDER BY id DESC")
    articles = c.fetchall()
    conn.close()
    return render_template('index.html', articles=articles, page_title="SAVED", user=get_current_user())


@app.route('/save/<int:article_id>')
def save_article(article_id):
    if not get_current_user():
        return jsonify({"error": "login_required"}), 401
    conn = get_conn()
    c = conn.cursor()
    if is_postgres():
        c.execute("UPDATE articles SET is_saved = TRUE, is_read = TRUE WHERE id = %s", (article_id,))
    else:
        c.execute("UPDATE articles SET is_saved = 1, is_read = 1 WHERE id = ?", (article_id,))
    conn.commit()
    conn.close()
    return "OK"


@app.route('/delete/<int:article_id>')
def delete_article(article_id):
    if not get_current_user():
        return redirect('/login')
    conn = get_conn()
    c = conn.cursor()
    if is_postgres():
        c.execute("UPDATE articles SET is_saved = FALSE WHERE id = %s", (article_id,))
    else:
        c.execute("UPDATE articles SET is_saved = 0 WHERE id = ?", (article_id,))
    conn.commit()
    conn.close()
    return redirect('/saved')


@app.route('/read/<int:article_id>')
def read(article_id):
    conn = get_conn()
    c = conn.cursor()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        c.execute(pq("UPDATE articles SET is_read = 1 WHERE id = ?"), (article_id,))
        conn.commit()
        conn.close()
        return "OK"
    c.execute(pq("SELECT link FROM articles WHERE id = ?"), (article_id,))
    row = c.fetchone()
    conn.close()
    return redirect(row[0]) if row else redirect('/')


@app.route('/summarize/<int:article_id>')
def summarize(article_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute(pq("SELECT title FROM articles WHERE id = ?"), (article_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return "記事が見つかりませんでした", 404

    title = row[0]
    if is_postgres():
        c.execute("UPDATE articles SET is_saved = TRUE WHERE id = %s", (article_id,))
    else:
        c.execute("UPDATE articles SET is_saved = 1 WHERE id = ?", (article_id,))
    conn.commit()
    conn.close()

    prompt = f"次のニュース記事タイトルに関する3点要約を日本語で出力してください：『{title}』"
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
        )
        summary = response.choices[0].message.content.strip()
    except Exception as e:
        logger.error("AI要約失敗 (id=%d): %s", article_id, e)
        return f"AI要約中にエラーが発生しました: {e}", 500

    conn = get_conn()
    c = conn.cursor()
    c.execute(pq("UPDATE articles SET summary = ? WHERE id = ?"), (summary, article_id))
    conn.commit()
    conn.close()
    return f"【AI要約】\n{summary}"


# ── 認証 ─────────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    next_url = request.args.get('next', '/')
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        mode = request.form.get('mode', 'password')

        if not email:
            return render_template('login.html', error="メールアドレスを入力してください", next=next_url)

        if mode == 'otp':
            code = str(random.randint(100000, 999999))
            expires_at = int(time.time()) + 300
            conn = get_conn()
            c = conn.cursor()
            c.execute(
                pq("INSERT INTO otp_codes (email, code, expires_at) VALUES (?, ?, ?)"),
                (email, code, expires_at)
            )
            conn.commit()
            conn.close()
            try:
                send_otp_email(email, code)
            except Exception as e:
                logger.error("OTPメール送信失敗: %s", e)
                return render_template('login.html', error=f"メール送信に失敗しました: {e}", next=next_url)
            session['otp_email'] = email
            session['otp_next'] = next_url
            return redirect('/otp')

        # パスワードモード
        if not password:
            return render_template('login.html', error="パスワードを入力してください", next=next_url)
        conn = get_conn()
        c = conn.cursor()
        c.execute(pq("SELECT password_hash FROM users WHERE email=?"), (email,))
        row = c.fetchone()
        conn.close()
        if not row:
            return redirect(f'/register?email={email}')
        if not row[0]:
            return render_template(
                'login.html',
                error="パスワードが設定されていません。「メールでコードを送る」からログインしてパスワードを設定してください",
                next=next_url
            )
        if row[0] != hash_password(password):
            return render_template('login.html', error="パスワードが違います", next=next_url)
        session['user_email'] = email
        return redirect(next_url)

    return render_template('login.html', next=next_url)


@app.route('/set-password', methods=['GET', 'POST'])
def set_password():
    user = get_current_user()
    if not user:
        return redirect('/login')
    if request.method == 'POST':
        pw = request.form.get('password', '').strip()
        pw2 = request.form.get('password2', '').strip()
        if not pw or len(pw) < 6:
            return render_template('set_password.html', error="6文字以上で入力してください")
        if pw != pw2:
            return render_template('set_password.html', error="パスワードが一致しません")
        conn = get_conn()
        c = conn.cursor()
        c.execute(pq("UPDATE users SET password_hash=? WHERE email=?"), (hash_password(pw), user))
        conn.commit()
        conn.close()
        return render_template('set_password.html', success="パスワードを設定しました")
    return render_template('set_password.html')


@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        if not email:
            return render_template('reset_password.html', error="メールアドレスを入力してください")
        conn = get_conn()
        c = conn.cursor()
        c.execute(pq("SELECT id FROM users WHERE email=?"), (email,))
        if not c.fetchone():
            conn.close()
            return render_template('reset_password.html', error="このメールアドレスは登録されていません")
        token = secrets.token_urlsafe(32)
        expires_at = int(time.time()) + 1800
        c.execute(
            pq("INSERT INTO otp_codes (email, code, expires_at) VALUES (?, ?, ?)"),
            (email, f"RESET:{token}", expires_at)
        )
        conn.commit()
        conn.close()
        reset_url = request.host_url + "reset-password/confirm?token=" + token + "&email=" + email
        try:
            sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
            message = Mail(
                from_email=FROM_EMAIL,
                to_emails=email,
                subject="【ニュースアプリ】パスワードリセット",
                plain_text_content="以下のリンクからパスワードをリセットしてください（30分有効）:\n\n" + reset_url,
            )
            sg.send(message)
        except Exception as e:
            logger.error("リセットメール送信失敗: %s", e)
            return render_template('reset_password.html', error=f"メール送信に失敗しました: {e}")
        return render_template('reset_password.html', success="リセットリンクをメールに送信しました")
    return render_template('reset_password.html')


@app.route('/reset-password/confirm', methods=['GET', 'POST'])
def reset_password_confirm():
    token = request.args.get('token', '')
    email = request.args.get('email', '')
    if request.method == 'POST':
        pw = request.form.get('password', '').strip()
        pw2 = request.form.get('password2', '').strip()
        if not pw or len(pw) < 6:
            return render_template('reset_confirm.html', error="6文字以上で入力してください", token=token, email=email)
        if pw != pw2:
            return render_template('reset_confirm.html', error="パスワードが一致しません", token=token, email=email)
        conn = get_conn()
        c = conn.cursor()
        c.execute(
            pq("SELECT id FROM otp_codes WHERE email=? AND code=? AND used=0 AND expires_at>?"),
            (email, f"RESET:{token}", int(time.time()))
        )
        row = c.fetchone()
        if not row:
            conn.close()
            return render_template('reset_confirm.html', error="リンクが無効か期限切れです", token=token, email=email)
        if is_postgres():
            c.execute("UPDATE otp_codes SET used=TRUE WHERE id=%s", (row[0],))
        else:
            c.execute("UPDATE otp_codes SET used=1 WHERE id=?", (row[0],))
        c.execute(pq("UPDATE users SET password_hash=? WHERE email=?"), (hash_password(pw), email))
        conn.commit()
        conn.close()
        return redirect('/login')
    return render_template('reset_confirm.html', token=token, email=email)


@app.route('/otp', methods=['GET', 'POST'])
def otp():
    email = session.get('otp_email')
    if not email:
        return redirect('/login')
    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        conn = get_conn()
        c = conn.cursor()
        c.execute(
            pq("SELECT id FROM otp_codes WHERE email=? AND code=? AND used=0 AND expires_at>? ORDER BY id DESC LIMIT 1"),
            (email, code, int(time.time()))
        )
        row = c.fetchone()
        if not row:
            conn.close()
            return render_template('otp.html', error="コードが違うか期限切れです", email=email)
        if is_postgres():
            c.execute("UPDATE otp_codes SET used=TRUE WHERE id=%s", (row[0],))
            c.execute("INSERT INTO users (email) VALUES (%s) ON CONFLICT (email) DO NOTHING", (email,))
        else:
            c.execute("UPDATE otp_codes SET used=1 WHERE id=?", (row[0],))
            c.execute("INSERT OR IGNORE INTO users (email) VALUES (?)", (email,))
        reg_pw = session.pop('register_password', None)
        if reg_pw:
            c.execute(pq("UPDATE users SET password_hash=? WHERE email=?"), (reg_pw, email))
        conn.commit()
        conn.close()
        session['user_email'] = email
        session.pop('otp_email', None)
        next_url = session.pop('otp_next', '/')
        return redirect(next_url)
    return render_template('otp.html', email=email)


@app.route('/register', methods=['GET', 'POST'])
def register():
    prefill_email = request.args.get('email', '')
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        password2 = request.form.get('password2', '').strip()

        if not email:
            return render_template('register.html', error="メールアドレスを入力してください", email=email)
        if not password or len(password) < 6:
            return render_template('register.html', error="パスワードは6文字以上で入力してください", email=email)
        if password != password2:
            return render_template('register.html', error="パスワードが一致しません", email=email)

        conn = get_conn()
        c = conn.cursor()
        c.execute(pq("SELECT id FROM users WHERE email=?"), (email,))
        if c.fetchone():
            conn.close()
            return render_template('register.html', error="このメールアドレスはすでに登録されています", email=email)
        conn.close()

        code = str(random.randint(100000, 999999))
        expires_at = int(time.time()) + 300
        conn = get_conn()
        c = conn.cursor()
        c.execute(
            pq("INSERT INTO otp_codes (email, code, expires_at) VALUES (?, ?, ?)"),
            (email, code, expires_at)
        )
        conn.commit()
        conn.close()
        try:
            send_otp_email(email, code)
        except Exception as e:
            logger.error("登録OTPメール送信失敗: %s", e)
            return render_template('register.html', error=f"メール送信に失敗しました: {e}", email=email)

        session['otp_email'] = email
        session['otp_next'] = '/'
        session['register_password'] = hash_password(password)
        return redirect('/otp')

    return render_template('register.html', email=prefill_email)


@app.route('/resend-otp', methods=['POST'])
def resend_otp():
    email = session.get('otp_email')
    if not email:
        return "NG", 400
    code = str(random.randint(100000, 999999))
    expires_at = int(time.time()) + 300
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        pq("INSERT INTO otp_codes (email, code, expires_at) VALUES (?, ?, ?)"),
        (email, code, expires_at)
    )
    conn.commit()
    conn.close()
    try:
        send_otp_email(email, code)
    except Exception as e:
        logger.error("OTP再送失敗: %s", e)
        return f"NG: {e}", 500
    return "OK"


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


@app.route('/refresh')
def refresh():
    NewsManager.fetch_and_store()
    return redirect('/')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
