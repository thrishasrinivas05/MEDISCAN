from flask import Flask, render_template, request, redirect, url_for, session
from datetime import datetime
import os
import re

from db import insert_user, get_user
from db import insert_medicine, get_all_medicines, delete_medicine

from ocr_engine import extract_text
from dotenv import load_dotenv


load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

UPLOAD_FOLDER = os.path.join(os.getcwd(), "static", "images")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

import traceback

@app.errorhandler(500)
def internal_error(e):
    print(traceback.format_exc())
    return "Internal Server Error", 500

# ================= HOME =================
@app.route('/')
def home():
    return render_template("login.html")

# ================= LOGIN =================
@app.route("/login", methods=["GET", "POST"])
def login_check():
    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email")
    password = request.form.get("password")

    user = get_user(email)

    if user and user.get("password") == password:
        session["user"] = email
        return redirect(url_for("upload_page"))

    return render_template("login.html", error="Invalid credentials")

# ================= REGISTER =================
@app.route("/register", methods=["POST"])
def register():
    name = request.form.get("name")
    email = request.form.get("email")
    phone = request.form.get("phone")
    password = request.form.get("password")

    if get_user(email) is not None:
        return render_template("login.html", error="User already exists")

    insert_user({
        "name": name,
        "email": email,
        "phone": phone,
        "password": password
    })

    return render_template("login.html", success="Registered successfully")

# ================= UPLOAD PAGE =================
@app.route('/upload_page')
def upload_page():
    if "user" not in session:
        return redirect(url_for("home"))
    return render_template("index.html")

# ================= CLEAN TEXT =================
def clean_text(text):
    text = text.upper()
    text = re.sub(r'[^A-Z0-9 ]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

# ================= NAME EXTRACTION =================
def extract_name(text):
    text = clean_text(text)
    words = text.split()

    ignore = {"TABLET","CAPSULE","CAP","TAB","MG","ML","IP","BP","USP"}

    name = []
    for w in words:
        if w in ignore or len(w) <= 2 or w.isdigit():
            continue
        name.append(w)
        if len(name) == 3:
            break

    return " ".join(name) if name else "Unknown"

# ================= EXPIRY =================
def extract_expiry(text):
    text = clean_text(text)

    months = {
        "JAN":"01","FEB":"02","MAR":"03","APR":"04",
        "MAY":"05","JUN":"06","JUL":"07","AUG":"08",
        "SEP":"09","OCT":"10","NOV":"11","DEC":"12"
    }

    match = re.search(r'([A-Z]{3})\s*([0-9]{4})', text)
    if match:
        m, y = match.groups()
        return f"{y}-{months.get(m,'01')}-01"

    return None

# ================= UPLOAD =================
@app.route('/upload', methods=['POST'])
def upload():

    if "user" not in session:
        return redirect(url_for("home"))

    file = request.files.get('file')

    if not file or file.filename == '':
        return "No file selected"

    filename = file.filename.replace(" ", "_")
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    text = extract_text(filepath)

    ocr_name = extract_name(text)
    ocr_expiry = extract_expiry(text)

    manual_name = request.form.get("manual_name")
    manual_expiry = request.form.get("manual_expiry")

    medicine_name = manual_name.strip() if manual_name else ocr_name
    expiry_date = manual_expiry if manual_expiry else ocr_expiry

    stock = request.form.get("stock")
    stock = int(stock) if stock and stock.isdigit() else 0

    insert_medicine({
        "medicine_name": medicine_name,
        "stock": stock,
        "expiry_date": expiry_date,
        "order_date": datetime.now().strftime("%Y-%m-%d"),
        "image": filename
    })

    return redirect(url_for("dashboard"))

# ================= DASHBOARD =================
@app.route('/dashboard')
def dashboard():

    if "user" not in session:
        return redirect(url_for("home"))

    medicines = get_all_medicines()
    today = datetime.now().date()

    low_items = []
    expiring_list = []

    for med in medicines:

        # LOW STOCK
        if med.get("stock", 0) <= 5:
            low_items.append(med.get("medicine_name", "Unknown"))

        # EXPIRY
        try:
            if med.get("expiry_date"):
                exp = datetime.strptime(med["expiry_date"], "%Y-%m-%d").date()
                days_left = (exp - today).days

                med["days_left"] = days_left
                med["is_expiring"] = days_left <= 30

                if days_left <= 30:
                    expiring_list.append(
                        f"{med.get('medicine_name')} → {days_left} days"
                    )
            else:
                med["days_left"] = None
                med["is_expiring"] = False

        except:
            med["days_left"] = None
            med["is_expiring"] = False

    popup_msg = "\n".join(expiring_list) if expiring_list else None
    low_stock_msg = ", ".join(low_items) if low_items else None

    return render_template(
        "dashboard.html",
        medicines=medicines,
        popup_msg=popup_msg,
        low_stock_msg=low_stock_msg
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
    return redirect(url_for("home"))

# ================= RUN =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)