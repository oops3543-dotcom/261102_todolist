import os
import sqlite3
from datetime import date
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from flask import Flask, abort, g, redirect, render_template, request, url_for

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Vercel에서는 /tmp만 쓰기 가능 (서버가 재시작되면 데이터가 초기화됨)
DB_DIR = "/tmp" if os.environ.get("VERCEL") else BASE_DIR
DB_PATH = os.path.join(DB_DIR, "todos.db")

# Supabase(Postgres) 주소가 있으면 Postgres를, 없으면 로컬 SQLite를 사용
DATABASE_URL = os.environ.get("POSTGRES_URL") or os.environ.get("DATABASE_URL")
USE_PG = bool(DATABASE_URL)
if USE_PG:
    # Vercel이 넣어주는 주소에는 psycopg가 모르는 옵션(supa=...)이 붙어 있어 sslmode만 남김
    parts = urlsplit(DATABASE_URL)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k == "sslmode"]
    DATABASE_URL = urlunsplit(parts._replace(query=urlencode(query)))

app = Flask(__name__)

PRIORITIES = {"high": "높음", "medium": "보통", "low": "낮음"}


class PgDB:
    """sqlite3 연결처럼 execute()/commit()을 쓸 수 있게 감싼 Postgres 연결"""

    def __init__(self):
        import psycopg
        from psycopg.rows import dict_row

        # Supabase 풀러(트랜잭션 모드)는 prepared statement를 지원하지 않음
        self.conn = psycopg.connect(
            DATABASE_URL, row_factory=dict_row, prepare_threshold=None
        )

    def execute(self, sql, params=()):
        return self.conn.execute(sql.replace("?", "%s"), params)

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()


def connect():
    if USE_PG:
        return PgDB()
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def get_db():
    if "db" not in g:
        g.db = connect()
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    if USE_PG:
        schema = """
            CREATE TABLE IF NOT EXISTS todos (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                priority TEXT NOT NULL DEFAULT 'medium',
                due_date TEXT,
                done INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """
    else:
        schema = """
            CREATE TABLE IF NOT EXISTS todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                priority TEXT NOT NULL DEFAULT 'medium',
                due_date TEXT,
                done INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
        """
    db = connect()
    try:
        db.execute(schema)
        db.commit()
    finally:
        db.close()


def get_todo(todo_id):
    todo = get_db().execute("SELECT * FROM todos WHERE id = ?", (todo_id,)).fetchone()
    if todo is None:
        abort(404)
    return todo


def read_form():
    title = request.form.get("title", "").strip()
    priority = request.form.get("priority", "medium")
    if priority not in PRIORITIES:
        priority = "medium"
    due_date = request.form.get("due_date") or None
    return title, priority, due_date


@app.route("/")
def index():
    status = request.args.get("status", "all")
    q = request.args.get("q", "").strip()

    sql = "SELECT * FROM todos WHERE 1=1"
    params = []
    if status == "active":
        sql += " AND done = 0"
    elif status == "done":
        sql += " AND done = 1"
    if q:
        sql += " AND title LIKE ?"
        params.append(f"%{q}%")
    sql += """
        ORDER BY done,
                 CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
                 due_date IS NULL, due_date, id DESC
    """
    todos = get_db().execute(sql, params).fetchall()

    counts = get_db().execute(
        "SELECT COUNT(*) AS total, COALESCE(SUM(done), 0) AS done FROM todos"
    ).fetchone()

    return render_template(
        "index.html",
        todos=todos,
        status=status,
        q=q,
        total=counts["total"],
        done_count=counts["done"],
        priorities=PRIORITIES,
        today=date.today().isoformat(),
    )


@app.route("/add", methods=["POST"])
def add():
    title, priority, due_date = read_form()
    if title:
        db = get_db()
        db.execute(
            "INSERT INTO todos (title, priority, due_date) VALUES (?, ?, ?)",
            (title, priority, due_date),
        )
        db.commit()
    return redirect(request.referrer or url_for("index"))


@app.route("/toggle/<int:todo_id>", methods=["POST"])
def toggle(todo_id):
    get_todo(todo_id)
    db = get_db()
    db.execute("UPDATE todos SET done = 1 - done WHERE id = ?", (todo_id,))
    db.commit()
    return redirect(request.referrer or url_for("index"))


@app.route("/edit/<int:todo_id>", methods=["GET", "POST"])
def edit(todo_id):
    todo = get_todo(todo_id)
    if request.method == "POST":
        title, priority, due_date = read_form()
        if title:
            db = get_db()
            db.execute(
                "UPDATE todos SET title = ?, priority = ?, due_date = ? WHERE id = ?",
                (title, priority, due_date, todo_id),
            )
            db.commit()
        return redirect(url_for("index"))
    return render_template("edit.html", todo=todo, priorities=PRIORITIES)


@app.route("/delete/<int:todo_id>", methods=["POST"])
def delete(todo_id):
    db = get_db()
    db.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
    db.commit()
    return redirect(request.referrer or url_for("index"))


@app.route("/clear-done", methods=["POST"])
def clear_done():
    db = get_db()
    db.execute("DELETE FROM todos WHERE done = 1")
    db.commit()
    return redirect(url_for("index"))


init_db()

if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
