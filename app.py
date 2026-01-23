from flask import Flask, render_template, request, redirect, url_for, send_file, session
from flask_cors import CORS
import os
from werkzeug.utils import secure_filename
from zipfile import ZipFile
from PIL import Image
import pytesseract

app = Flask(__name__)
CORS(app)
app.secret_key = "supersecretkey"  # for session

# Folder to store uploads
UPLOAD_FOLDER = "uploads"
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Dummy users (email:password) for simplicity
USERS = {
    "rishi@gmail.com": "1234",
    "student@gmail.com": "pass"
}

# ---------------- Helper Functions ----------------

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

def create_user_folders(email):
    user_path = os.path.join(UPLOAD_FOLDER, email.replace("@","_"))
    categories = ["Certificate", "Academic", "Financial", "Personal"]
    for cat in categories:
        cat_path = os.path.join(user_path, cat)
        if not os.path.exists(cat_path):
            os.makedirs(cat_path)
    return user_path

# ---------------- Routes ----------------

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        if email in USERS and USERS[email] == password:
            session["email"] = email
            return redirect(url_for("upload"))
        else:
            return render_template("login.html", error="Invalid credentials")
    return render_template("login.html")

@app.route("/upload", methods=["GET", "POST"])
def upload():
    if "email" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        files = request.files.getlist("files")
        user_folder = create_user_folders(session["email"])
        uploaded_info = []

        for f in files:
            filename = secure_filename(f.filename)
            img = Image.open(f)
            text = pytesseract.image_to_string(img)
            category = categorize(text)

            save_path = os.path.join(user_folder, category, filename)
            img.save(save_path)

            uploaded_info.append({"name": filename, "category": category})

        return render_template("dashboard.html", files=uploaded_info)

    return render_template("upload.html")

@app.route("/download")
def download():
    if "email" not in session:
        return redirect(url_for("login"))

    user_folder = os.path.join(UPLOAD_FOLDER, session["email"].replace("@","_"))
    zip_path = f"{user_folder}.zip"

    # Create ZIP
    with ZipFile(zip_path, "w") as zipf:
        for root, dirs, files in os.walk(user_folder):
            for file in files:
                zipf.write(os.path.join(root, file),
                           os.path.relpath(os.path.join(root, file), user_folder))

    return send_file(zip_path, as_attachment=True)

@app.route("/logout")
def logout():
    session.pop("email", None)
    return redirect(url_for("login"))

# ---------------- Run App ----------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
