
from flask import Flask, render_template, request, redirect, session, send_file
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from datetime import datetime
import os, zipfile, shutil

# ------------------ AI Imports ------------------
import openai
import PyPDF2
import docx
try:
    import pytesseract
    from PIL import Image
except:
    pytesseract = None
try:
    import whisper
except:
    whisper = None
try:
    from pdf2image import convert_from_path
except:
    convert_from_path = None
def reset_all_data_once():
    """
    WARNING: Deletes ALL users, uploads, and files.
    Use ONLY when you want a fresh start.
    """
    if os.path.exists("database.db"):
        os.remove("database.db")

    if os.path.exists("uploads"):
        shutil.rmtree("uploads")

    print("✅ ALL previous uploads and database cleared")

# ------------------ APP SETUP ------------------
app = Flask(__name__)
app.secret_key = "supersecretkey"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"
app.config["UPLOAD_FOLDER"] = "uploads"

db = SQLAlchemy(app)

# ------------------ DATABASE MODELS ------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True)
    password = db.Column(db.String(50))
    is_admin = db.Column(db.Boolean, default=False)

class Upload(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    filename = db.Column(db.String(200))
    category = db.Column(db.String(100))
    date = db.Column(db.String(50))

# ------------------ FILE EXTENSION CATEGORIES ------------------
EXTENSION_MAP = {
    "Images": [".jpg", ".jpeg", ".png", ".gif", ".bmp"],
    "PDFs": [".pdf"],
    "Word Documents": [".doc", ".docx"],
    "Excel Files": [".xls", ".xlsx", ".csv"],
    "PowerPoint": [".ppt", ".pptx"],
    "Text Files": [".txt"],
    "Audio": [".mp3", ".wav", ".aac", ".m4a", ".ogg"],
    "Video": [".mp4", ".avi", ".mkv", ".mov", ".wmv"],
    "Archives": [".zip", ".rar", ".7z"],
    "Code Files": [".py", ".java", ".c", ".cpp", ".js", ".html", ".css"],
    "Executables": [".exe", ".msi"],
    "Fonts": [".ttf", ".otf"],
    "Database": [".db", ".sql"],
    "Email": [".eml", ".msg"],
    "eBook": [".epub", ".mobi"],
    "Design": [".psd", ".ai", ".fig", ".xd"],
    "Logs": [".log"],
    "Shaders": [".glsl", ".shader"]
}

def detect_extension_category(filename):
    name = filename.lower()
    for cat, exts in EXTENSION_MAP.items():
        for ext in exts:
            if name.endswith(ext):
                return cat
    return "Others"

# ------------------ OPENAI ------------------
openai.api_key = os.getenv("OPENAI_API_KEY")


# ------------------ STRONG DOCUMENT INTENT ------------------
DOCUMENT_TYPES = {
    "Certificate": [
        "certificate", "certified", "this is to certify",
        "successfully completed", "course completion", "awarded", "diploma"
    ],
    "Academic": [
        "assignment", "experiment", "abstract", "introduction",
        "methodology", "results", "conclusion",
        "university", "college", "lab", "project report"
    ],
    "Work": [
        "resume", "curriculum vitae", "experience",
        "skills", "employment", "internship"
    ],
    "Business": [
        "invoice", "receipt", "gst", "tax",
        "amount", "payment", "bill"
    ],
    "Personal": [
        "aadhaar", "passport", "pan card",
        "date of birth", "address", "identity"
    ]
}

# ------------------ AI HELPERS ------------------
def score_by_keywords(text):
    scores = {k: 0 for k in DOCUMENT_TYPES}
    for cat, kws in DOCUMENT_TYPES.items():
        for kw in kws:
            if kw in text:
                scores[cat] += 2
    best = max(scores, key=scores.get)
    return best if scores[best] >= 4 else None

def clean_text_for_ai(text):
    lines = text.splitlines()
    useful = [l for l in lines if len(l.strip()) > 20]
    return "\n".join(useful[:40])

# ------------------ OCR & TEXT EXTRACTION ------------------
def ocr_pdf(file_path):
    text = ""
    if convert_from_path and pytesseract:
        try:
            images = convert_from_path(file_path)
            for img in images:
                text += pytesseract.image_to_string(img)
        except:
            pass
    return text

def extract_text(file_path, filename):
    text = ""
    ext = filename.lower().split(".")[-1]

    try:
        if ext == "pdf":
            with open(file_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text += page.extract_text() or ""
            if not text.strip():
                text = ocr_pdf(file_path)

        elif ext in ["doc", "docx"]:
            doc = docx.Document(file_path)
            text = "\n".join(p.text for p in doc.paragraphs)

        elif ext in ["txt", "csv"]:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()

        elif ext in ["jpg", "jpeg", "png", "bmp", "gif"] and pytesseract:
            text = pytesseract.image_to_string(Image.open(file_path))

        elif ext in ["mp3", "wav", "mp4", "avi"] and whisper:
            model = whisper.load_model("base")
            result = model.transcribe(file_path)
            text = result.get("text", "")

    except Exception as e:
        print("Extraction error:", e)

    return text.strip()

# ------------------ FINAL AI CLASSIFIER ------------------
def analyze_file_content(file_path, filename):
    text = extract_text(file_path, filename)
    text_lower = text.lower()

    # Filename intent
    if "certificate" in filename.lower():
        return "Certificate"
    if "resume" in filename.lower() or "cv" in filename.lower():
        return "Work"

    # Keyword scoring
    scored = score_by_keywords(text_lower)
    if scored:
        return scored

    # No text fallback
    if not text.strip():
        return detect_extension_category(filename)

    # GPT final fallback
    prompt = f"""
Classify this document into ONE category only:
Academic, Work, Business, Certificate, Personal, Others

Rules:
- College, lab, experiment → Academic
- Award, certified → Certificate
- Resume, CV → Work
- Invoice, tax → Business
- ID, DOB → Personal

Content:
{clean_text_for_ai(text)}
"""

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        return response.choices[0].message.content.strip()
    except:
        return detect_extension_category(filename)
# ------------------ AUTO CREATE ADMINS ------------------
@app.route("/health")
def health():
    return "OK", 200

def create_admins():
    admins = [
        "rishi31@gmail.com",
        "du07@gmail.com",
        "thomasedwinrte@gmail.com",
        "anbuselvan@gmail.com"
    ]
    for email in admins:
        if not User.query.filter_by(email=email).first():
            db.session.add(User(email=email, password="admin123", is_admin=True))
    db.session.commit()

# ------------------ ROUTES ------------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(email=request.form["email"], password=request.form["password"]).first()
        if user:
            session["user_id"] = user.id
            session["email"] = user.email
            session["is_admin"] = user.is_admin
            return redirect("/admin_panel" if user.is_admin else "/dashboard")
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        if User.query.filter_by(email=email).first():
            return "User already exists"
        new_user = User(email=email, password=password)
        db.session.add(new_user)
        db.session.commit()
        return redirect("/")
    return render_template("register.html")

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/")
    files = Upload.query.filter_by(user_id=session["user_id"]).all()
    categories = {}
    for f in files:
        categories.setdefault(f.category, []).append(f)
    return render_template("dashboard.html", categories=categories)

@app.route("/admin_dashboard")
def admin_dashboard_view():
    if "user_id" not in session or not session.get("is_admin"):
        return redirect("/")
    files = Upload.query.all()
    categories = {}
    for f in files:
        categories.setdefault(f.category, []).append(f)
    return render_template("admin_dashboard.html", categories=categories)

@app.route("/admin_panel")
def admin_panel():
    if "user_id" not in session or not session.get("is_admin"):
        return redirect("/")
    users = User.query.all()
    return render_template("admin_panel.html", users=users)
@app.route("/upload", methods=["POST"])
def upload():
    if "user_id" not in session:
        return redirect("/")

    files = request.files.getlist("files")
    user_folder = os.path.join(app.config["UPLOAD_FOLDER"], f"user_{session['user_id']}")
    os.makedirs(user_folder, exist_ok=True)

    for file in files:
        if file.filename == "":
            continue
        filename = secure_filename(file.filename)

        temp_folder = os.path.join(user_folder, "temp")
        os.makedirs(temp_folder, exist_ok=True)
        file_path = os.path.join(temp_folder, filename)
        file.save(file_path)

        # AI classification
        ai_category = analyze_file_content(file_path, filename)
        final_folder = os.path.join(user_folder, ai_category)
        os.makedirs(final_folder, exist_ok=True)

        # Handle collisions
        base, ext = os.path.splitext(filename)
        counter = 1
        while os.path.exists(os.path.join(final_folder, filename)):
            filename = f"{base}_{counter}{ext}"
            counter += 1
        final_path = os.path.join(final_folder, filename)
        os.rename(file_path, final_path)

        db.session.add(Upload(
            user_id=session["user_id"],
            filename=filename,
            category=ai_category,
            date=datetime.now().strftime("%d-%m-%Y")
        ))
    db.session.commit()
    return redirect("/dashboard")

# ------------------ USER EDIT / UPLOAD ------------------
@app.route("/edit_user/<int:user_id>", methods=["GET", "POST"])
def edit_user(user_id):
    if "user_id" not in session or not session.get("is_admin"):
        return redirect("/")
    user = User.query.get_or_404(user_id)

    if request.method == "POST":
        user.email = request.form["email"]
        user.password = request.form["password"]
        db.session.commit()

        if "files" in request.files:
            files = request.files.getlist("files")
            user_folder = os.path.join(app.config["UPLOAD_FOLDER"], f"user_{user.id}")
            for file in files:
                if file.filename == "":
                    continue
                filename = secure_filename(file.filename)

                temp_folder = os.path.join(user_folder, "temp")
                os.makedirs(temp_folder, exist_ok=True)
                file_path = os.path.join(temp_folder, filename)
                file.save(file_path)

                # --- AI classification ---
                ai_category = analyze_file_content(file_path, filename)
                final_folder = os.path.join(user_folder, ai_category)
                os.makedirs(final_folder, exist_ok=True)

                # Handle file collisions
                base, ext = os.path.splitext(filename)
                counter = 1
                while os.path.exists(os.path.join(final_folder, filename)):
                    filename = f"{base}_{counter}{ext}"
                    counter += 1
                final_path = os.path.join(final_folder, filename)
                os.rename(file_path, final_path)

                db.session.add(Upload(
                    user_id=user.id,
                    filename=filename,
                    category=ai_category,
                    date=datetime.now().strftime("%d-%m-%Y")
                ))
            db.session.commit()
        return redirect(f"/edit_user/{user.id}")

    # Fetch uploads
    files = Upload.query.filter_by(user_id=user.id).all()
    categories = {}
    for f in files:
        categories.setdefault(f.category, []).append(f)

    # --- Compute statistics ---
    total_files = len(files)
    total_categories = len(categories)
    most_files_category = None
    if categories:
        most_files_category = max(categories.items(), key=lambda x: len(x[1]))[0]

    return render_template(
        "edit_user.html",
        user=user,
        categories=categories,
        total_files=total_files,
        total_categories=total_categories,
        most_files_category=most_files_category
    )

# ------------------ DOWNLOAD & DELETE ------------------
@app.route("/download_file/<int:file_id>")
def download_file(file_id):
    f = Upload.query.get_or_404(file_id)
    if not session.get("is_admin") and f.user_id != session.get("user_id"):
        return "Access Denied"
    path = os.path.join(app.config["UPLOAD_FOLDER"], f"user_{f.user_id}", f.category, f.filename)
    if not os.path.exists(path):
        return "File not found"
    return send_file(path, as_attachment=True)

@app.route("/delete_file/<int:file_id>")
def delete_file(file_id):
    f = Upload.query.get_or_404(file_id)
    if not session.get("is_admin"):
        return "Access Denied"
    file_path = os.path.join(app.config["UPLOAD_FOLDER"], f"user_{f.user_id}", f.category, f.filename)
    if os.path.exists(file_path):
        os.remove(file_path)
    db.session.delete(f)
    db.session.commit()
    return redirect(request.referrer or "/admin_panel")

@app.route("/delete_user/<int:user_id>")
def delete_user(user_id):
    if "user_id" not in session or not session.get("is_admin"):
        return "Access Denied"

    user = User.query.get_or_404(user_id)

    # Delete all uploads
    uploads = Upload.query.filter_by(user_id=user.id).all()
    for f in uploads:
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], f"user_{user.id}", f.category, f.filename)
        if os.path.exists(file_path):
            os.remove(file_path)
        db.session.delete(f)

    # Delete user folder
    user_folder = os.path.join(app.config["UPLOAD_FOLDER"], f"user_{user.id}")
    if os.path.exists(user_folder):
        shutil.rmtree(user_folder)

    # Delete user
    db.session.delete(user)
    db.session.commit()
    return redirect(request.referrer or "/admin_panel")

@app.route("/download_category/<int:user_id>/<category>")
def download_category(user_id, category):
    if not session.get("is_admin") and user_id != session.get("user_id"):
        return "Access Denied"
    folder = os.path.join(app.config["UPLOAD_FOLDER"], f"user_{user_id}", category)
    zip_path = f"{category}_user{user_id}.zip"
    with zipfile.ZipFile(zip_path, "w") as zipf:
        for file in os.listdir(folder):
            zipf.write(os.path.join(folder, file), file)
    return send_file(zip_path, as_attachment=True)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ------------------ RUN ------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        create_admins()

    os.makedirs("uploads", exist_ok=True)

    app.run(host="0.0.0.0", port=10000)

