
import os
import json
import urllib.request
import sqlite3
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, render_template_string, request, redirect, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "replace-before-launch")

DB = os.environ.get("DATABASE_PATH", "kikisms.db")


FLEEXA_BASE = "https://fleexa.com.ng/developer"

def fleexa_request(path):
    api_key = os.environ.get("FLEEXA_API_KEY")

    if not api_key:
        return None, "Fleexa API key is not configured."

    req = urllib.request.Request(
        FLEEXA_BASE + path,
        headers={
            "Authorization": "Bearer " + api_key,
            "Accept": "application/json"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.loads(response.read().decode()), None
    except Exception:
        return None, "Unable to connect to Fleexa. Please try again."
def connect():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def initialize():
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS numbers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            country TEXT NOT NULL,
            phone TEXT NOT NULL UNIQUE,
            price REAL NOT NULL,
            status TEXT DEFAULT 'demo'
        );

        CREATE TABLE IF NOT EXISTS rentals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            number_id INTEGER NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            status TEXT DEFAULT 'active'
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rental_id INTEGER NOT NULL,
            sender TEXT,
            body TEXT NOT NULL,
            received_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)

        if db.execute("SELECT COUNT(*) FROM numbers").fetchone()[0] == 0:
            db.executemany(
                "INSERT INTO numbers(country, phone, price) VALUES(?,?,?)",
                [
                    ("United States", "DEMO-US-001", 12),
                    ("United Kingdom", "DEMO-UK-001", 10),
                    ("Canada", "DEMO-CA-001", 11),
                    ("Germany", "DEMO-DE-001", 12),
                ]
            )

initialize()

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/login")
        return fn(*args, **kwargs)
    return wrapper

PAGE = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>KIKISMS</title>
<style>
body {
    margin:0;
    background:#f3f7fa;
    font-family:Arial,sans-serif;
    color:#14243a;
}
header {
    background:#14243a;
    color:white;
    padding:22px;
    font-size:25px;
    font-weight:bold;
}
header span {color:#31c6ad}
main {max-width:850px;margin:35px auto;padding:18px}
.hero {
    background:#14243a;
    color:white;
    padding:35px;
    border-radius:18px;
}
h1 {font-size:34px}
.card {
    background:white;
    padding:22px;
    margin:15px 0;
    border-radius:14px;
    box-shadow:0 3px 12px #00000009;
}
button,.btn {
    display:inline-block;
    background:#16a58d;
    color:white;
    border:0;
    padding:13px 20px;
    border-radius:8px;
    text-decoration:none;
    cursor:pointer;
}
input {
    display:block;
    width:95%;
    padding:13px;
    margin:12px 0;
    border:1px solid #ddd;
    border-radius:8px;
}
.small {color:#6b7a8c;font-size:13px}
</style>
</head>
<body>
<header>KIKI<span>SMS</span></header>
<main>
{{content|safe}}
</main>
</body>
</html>
"""

def page(content):
    return render_template_string(PAGE, content=content)

@app.route("/")
def home():
    with connect() as db:
        numbers = db.execute(
            "SELECT * FROM numbers WHERE status='demo' OR status='available'"
        ).fetchall()

    cards = ""
    for n in numbers:
        cards += f"""
        <div class="card">
        <h3>{n['country']}</h3>
        <p>{n['phone']}</p>
        <h2>${n['price']:.2f} / month</h2>
        <p class="small">Demonstration listing, not a real number.</p>
        <a class="btn" href="/login">Sign in to continue</a>
        </div>
        """

    return page(f"""
    <section class="hero">
    <h1>Your second number.<br> Your privacy.</h1>
    <p>Exclusive monthly phone number rental platform.</p>
    <a class="btn" href="/register">Create account</a>
    </section>
    <h2>Explore countries</h2>
    {cards}
    """)

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        if len(password) < 10:
            return page("Password must contain at least 10 characters.")

        try:
            with connect() as db:
                db.execute(
                    "INSERT INTO users(email,password) VALUES(?,?)",
                    (email,generate_password_hash(password))
                )
            return redirect("/login")
        except sqlite3.IntegrityError:
            return page("Email already registered.")

    return page("""
    <div class="card">
    <h2>Create your KIKISMS account</h2>
    <form method="post">
    <input name="email" type="email" placeholder="Email address" required>
    <input name="password" type="password" placeholder="Password (10+ characters)" required>
    <button>Create account</button>
    </form>
    </div>
    """)

@app.route("/numbers")
@login_required
def live_numbers():
    balance, balance_error = fleexa_request("/balance")
    areas, areas_error = fleexa_request("/rent/sms4/areas")

    if balance_error or areas_error:
        return page("""
        <div class="card">
        <h2>Live number availability</h2>
        <p>We could not retrieve live data right now.</p>
        <a class="btn" href="/">Go home</a>
        </div>
        """)

    return page("""
    <div class="card">
    <h1>Live number availability</h1>
    <p>Fleexa connection successful.</p>
    <h3>Wallet balance</h3>
    <pre>Connected securely</pre>
    <h3>Available rental areas and prices</h3>
    <pre>""" + str(areas) + """</pre>
    <a class="btn" href="/">Go home</a>
    </div>
    """)
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        with connect() as db:
            user = db.execute(
                "SELECT * FROM users WHERE email=?",
                (request.form["email"].strip().lower(),)
            ).fetchone()

        if user and check_password_hash(user["password"],request.form["password"]):
            session["user_id"] = user["id"]
            return redirect("/dashboard")

        return page("Incorrect email or password.")

    return page("""
    <div class="card">
    <h2>Sign in</h2>
    <form method="post">
    <input name="email" type="email" placeholder="Email address" required>
    <input name="password" type="password" placeholder="Password" required>
    <button>Sign in</button>
    </form>
    </div>
    """)

@app.route("/dashboard")
@login_required
def dashboard():
    with connect() as db:
        rentals = db.execute("""
            SELECT rentals.*, numbers.country,numbers.phone
            FROM rentals JOIN numbers ON numbers.id=rentals.number_id
            WHERE rentals.user_id=?
        """,(session["user_id"],)).fetchall()

    content = "<h1>Your dashboard</h1>"

    if not rentals:
        content += "<div class='card'>You have no rentals yet.</div>"

    for r in rentals:
        content += f"""
        <div class="card">
        <h3>{r['country']}</h3>
        <p>{r['phone']}</p>
        <p>Expires: {r['end_date']}</p>
        <a class="btn" href="/inbox/{r['id']}">Open inbox</a>
        </div>
        """

    content += "<a class='btn' href='/logout'>Sign out</a>"
    return page(content)

@app.route("/inbox/<int:rental_id>")
@login_required
def inbox(rental_id):
    with connect() as db:
        rental = db.execute(
            "SELECT id FROM rentals WHERE id=? AND user_id=?",
            (rental_id,session["user_id"])
        ).fetchone()

        if not rental:
            return "Not found",404

        messages = db.execute(
            "SELECT * FROM messages WHERE rental_id=? ORDER BY id DESC",
            (rental_id,)
        ).fetchall()

    content = "<h1>Private SMS inbox</h1>"

    for m in messages:
        content += f"<div class='card'><p>{m['sender']}</p><p>{m['body']}</p></div>"

    if not messages:
        content += "<div class='card'>No incoming messages yet.</div>"

    return page(content)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

if __name__ == "__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)))
      
