from flask import Flask, render_template, request, redirect, url_for, session
from datetime import datetime
import os
import re
from werkzeug.utils import secure_filename
from difflib import get_close_matches

from db import (
    insert_user,
    get_user,
    insert_medicine,
    get_all_medicines,
    delete_medicine
)

# ================= OCR =================
try:
    from ocr_engine import extract_text, extract_expiry
except Exception as e:
    print("OCR IMPORT ERROR:", e)
    extract_text = lambda x: ""
    extract_expiry = lambda x: None

# ================= ML =================
try:
    from ml_model import predict_stock_status, expiry_alert
except:
    predict_stock_status = lambda x: "OK"
    expiry_alert = lambda x: "UNKNOWN"

# ================= APP =================
app = Flask(__name__)

app.secret_key = os.getenv("SECRET_KEY", "medicine_project_key")

app.config['SESSION_COOKIE_SAMESITE'] = "Lax"
app.config['SESSION_COOKIE_SECURE'] = False

UPLOAD_FOLDER = "/tmp"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ================= MEDICINE DATABASE =================
medicine_database = [
    "Cetirizine", "Paracetamol", "Azithromycin", "Amoxicillin",
    "Ibuprofen", "Dolo", "Crocin", "Aspirin", "Metformin",
    "Pantoprazole", "Omeprazole", "Zincovit", "Montek",
    "Sinarest", "Calpol", "Benadryl", "Augmentin",
    "Azee", "Telma", "Shelcal"
]

# ================= MEDICINE DETECTION =================
def detect_medicine(text):

    if not text:
        return "Unknown Medicine"

    text = text.lower()
    text = re.sub(r'[^a-zA-Z ]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()

    # 1. Direct match (BEST)
    for med in medicine_database:
        if med.lower() in text:
            return med

    # 2. Word match
    words = text.split()

    for word in words:
        if len(word) < 3:
            continue

        match = get_close_matches(
            word,
            [m.lower() for m in medicine_database],
            n=1,
            cutoff=0.4
        )

        if match:
            for m in medicine_database:
                if m.lower() == match[0]:
                    return m

    return "Unknown Medicine"


# ================= LOGIN =================
@app.route('/')
def login():
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def login_check():

    email = request.form.get("email")
    password = request.form.get("password")

    user = get_user(email)

    if user and user.get("password") == password:
        session["user"] = email
        return redirect(url_for("upload_page"))

    return render_template("login.html", error="Invalid login")


# ================= REGISTER =================
@app.route("/register", methods=["POST"])
def register():

    email = request.form.get("email")

    if get_user(email):
        return render_template("login.html", error="User already exists")

    insert_user({
        "name": request.form.get("name"),
        "email": email,
        "phone": request.form.get("phone"),
        "password": request.form.get("password")
    })

    return render_template("login.html", success="Registration Successful!")


# ================= UPLOAD PAGE =================
@app.route('/upload_page')
def upload_page():

    if "user" not in session:
        return redirect(url_for("login"))

    return render_template("index.html")


# ================= UPLOAD =================
@app.route('/upload', methods=['POST'])
def upload():

    try:

        if "user" not in session:
            return redirect(url_for("login"))

        if "file" not in request.files:
            return "No file uploaded"

        file = request.files["file"]

        if file.filename == "":
            return "No file selected"

        # SAVE FILE
        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        # ================= OCR =================
        text = extract_text(filepath)
        print("OCR TEXT:", text)

        # ================= MEDICINE =================
        ocr_name = detect_medicine(text)

        # ================= EXPIRY =================
        ocr_expiry = extract_expiry(text)

        # ================= FORM DATA =================
        name = request.form.get("manual_name") or ocr_name
        expiry = request.form.get("manual_expiry") or ocr_expiry
        stock = int(request.form.get("stock") or 0)

        # ================= ML =================
        stock_status = predict_stock_status(stock)
        expiry_status = expiry_alert(expiry) if expiry else "UNKNOWN"

        # ================= DB =================
        insert_medicine({
            "medicine_name": name,
            "stock": stock,
            "expiry_date": expiry,
            "order_date": datetime.now().strftime("%d-%m-%Y"),
            "image": filename,
            "stock_status": stock_status,
            "expiry_status": expiry_status
        })

        return redirect(url_for("dashboard"))

    except Exception as e:
        print("UPLOAD ERROR:", e)
        return f"Upload Failed: {str(e)}"


# ================= DASHBOARD =================
@app.route('/dashboard')
def dashboard():

    if "user" not in session:
        return redirect(url_for("login"))

    medicines = get_all_medicines()

    low_stock = []
    expiring = []

    today = datetime.now().date()

    for m in medicines:

        if m.get("stock", 0) <= 5:
            low_stock.append(m.get("medicine_name"))

        try:
            if m.get("expiry_date"):

                exp = datetime.strptime(
                    m["expiry_date"],
                    "%Y-%m-%d"
                ).date()

                days = (exp - today).days

                if 0 <= days <= 30:
                    expiring.append(
                        f"{m['medicine_name']} expires in {days} days"
                    )

                m["expiry_date"] = exp.strftime("%d-%m-%Y")

        except:
            pass

    return render_template(
        "dashboard.html",
        medicines=medicines,
        popup_msg="\n".join(expiring) if expiring else None,
        low_stock_msg=", ".join(low_stock) if low_stock else None
    )


# ================= DELETE =================
@app.route('/delete/<id>')
def delete(id):
    delete_medicine(id)
    return redirect(url_for("dashboard"))


# ================= LOGOUT =================
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for("login"))


# ================= RUN =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)