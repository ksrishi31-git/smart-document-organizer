from flask import Flask, render_template, request, redirect, session, send_file
import os, sqlite3, zipfile
from PIL import Image
import pytesseract

app = Flask(__name__)
app.secret_key = "secret123"

UPLOAD_FOLDER = "uploads"
CATEGORIES = ["Certificate", "Academic", "Financial", "Personal"]

# ---------- DATABASE ----------
def get_db():
    return sqlite3.connect("database.db")

with get_db() as db:
    db.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE,
        password TEXT
    )
    """)

# ---------- CATEGORY LOGIC ----------
def categorize(text):
    text = text.lower()
    if "certificate" in text:
        return "Certificate"
    elif "university" in text or "assignment" in text:
        return "Academic"
    elif "invoice" in text or "amount" in text or "rs" in text:
        return "Financial"
    else:
        return "Personal"

# ---------- ROUTES ----------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE email=? AND password=?",
            (email, password)
        ).fetchone()

        if user:
            session["email"] = email
            return redirect("/upload")

    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        try:
            db = get_db()
            db.execute("INSERT INTO users (email,password) VALUES (?,?)",
                       (email, password))
            db.commit()
            return redirect("/")
        except:
            pass

    return render_template("register.html")

@app.route("/upload", methods=["GET", "POST"])
def upload():
    if "email" not in session:
        return redirect("/")

    user = session["email"]
    user_path = os.path.join(UPLOAD_FOLDER, user)

    for cat in CATEGORIES:
        os.makedirs(os.path.join(user_path, cat), exist_ok=True)

    if request.method == "POST":
        files = request.files.getlist("files")

        for file in files:
            image = Image.open(file)
            text = pytesseract.image_to_string(image)
            category = categorize(text)

            save_path = os.path.join(user_path, category, file.filename)
            file.seek(0)
            file.save(save_path)

        return redirect("/dashboard")

    return render_template("upload.html")

@app.route("/dashboard")
def dashboard():
    if "email" not in session:
        return redirect("/")

    user = session["email"]
    data = {}

    for cat in CATEGORIES:
        folder = os.path.join(UPLOAD_FOLDER, user, cat)
        data[cat] = os.listdir(folder)

    return render_template("dashboard.html", data=data)

@app.route("/download/<category>")
def download(category):
    user = session["email"]
    folder_path = os.path.join(UPLOAD_FOLDER, user, category)
    zip_name = f"{category}.zip"

    with zipfile.ZipFile(zip_name, "w") as zipf:
        for file in os.listdir(folder_path):
            zipf.write(os.path.join(folder_path, file), file)

    return send_file(zip_name, as_attachment=True)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
