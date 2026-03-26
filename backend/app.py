from flask import Flask, render_template, request, redirect, jsonify, flash, session, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
from collections import defaultdict
from database import init_db, get_user_settings
from translations import get_translations_dict
from datetime import datetime, timedelta
from functools import wraps
import os
try:
    import easyocr
except ImportError:
    easyocr = None
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "frontend"))

app = Flask(
    __name__,
    template_folder=os.path.join(FRONTEND_DIR, "templates"),
    static_folder=os.path.join(FRONTEND_DIR, "static"),
)
app.secret_key = 'spendwise_secret_key_2024'

# Upload configuration
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

# Create uploads folder if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

DB_PATH = os.path.join(BASE_DIR, "data", "expenses.db")

# ── OCR Reader (EasyOCR) ───────────────────────────────────────────
# Initialized once. Uses CPU (gpu=False) for better compatibility.
try:
    if easyocr:
        ocr_reader = easyocr.Reader(['en'], gpu=False)
    else:
        ocr_reader = None
except Exception as e:
    print(f"OCR Reader Init Error: {e}")
    ocr_reader = None

def extract_amount_python(text):
    # Strip long digits (TINs, GST, etc) to avoid false positives
    t = re.sub(r'\b\d{9,}\b', '', text)
    t = t.replace('|', '1').replace('l', '1').replace('O', '0')
    
    # Tier 1: Keywords (Cash, Total, Amount)
    tier1_patterns = [
        r'\bcash\b[\s\S]{0,25}?(?:Rs\.?|INR|₹)?\s*([\d,]+(?:\.\d{1,2})?)\s*\/?-?',
        r'(?:grand\s+total|balance\s+due|amount\s+due|amount\s+payable|net\s+payable|bill\s+total|payable\s+amount)[\s\S]{0,30}?(?:Rs\.?|INR|₹)?\s*([\d,]+(?:\.\d{1,2})?)\s*\/?-?',
        r'(?:net\s+total|total\s+amount|total\s+due|total\s+payable|sub\s*total|total)[\s\S]{0,20}?(?:Rs\.?|INR|₹|\$)?\s*([\d,]+(?:\.\d{1,2})?)\s*\/?-?',
        r'(?:bill\s+amount|invoice\s+amount|bill\s+value)\s*[:\-]?\s*(?:Rs\.?|INR|₹|\$)?\s*([\d,]+(?:\.\d{1,2})?)\s*\/?-?'
    ]
    
    for pattern in tier1_patterns:
        matches = list(re.finditer(pattern, t, re.IGNORECASE))
        if matches:
            # Use the first match for cash, or the best weighted match
            for m in matches:
                raw = m.group(1).replace(',', '')
                try:
                    val = float(raw)
                    if 1 <= val < 1000000: return val
                except: continue
            
    # Tier 2: Currency symbol alone
    tier2_matches = re.finditer(r'(?:Rs\.?\s*|₹\s*|INR\s*)([\d,]+(?:\.\d{1,2})?)\s*\/?-?', t, re.IGNORECASE)
    for m in tier2_matches:
        raw = m.group(1).replace(',', '')
        try:
            val = float(raw)
            if 1 <= val < 1000000: return val
        except: continue
        
    # Tier 3: Last plausible number in tail (bottom 40%)
    tail = t[int(len(t)*0.6):]
    numbers = re.findall(r'\b(\d{1,6}(?:\.\d{2})?)\s*\/?-?\b', tail)
    if numbers:
        try:
            return float(numbers[-1].replace(',', ''))
        except: pass
        
    return None

def extract_date_python(text):
    patterns = [
        r'\b(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{4})\b',
        r'\b(\d{4})[\/\-](\d{1,2})[\/\-](\d{1,2})\b',
        r'\b(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{2})\b'
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            g1, g2, g3 = m.groups()
            try:
                if len(g3) == 4: 
                    if len(g1) == 4: y, month, d = int(g1), int(g2), int(g3)
                    else: d, month, y = int(g1), int(g2), int(g3)
                else: 
                    d, month, y = int(g1), int(g2), int(g3)
                    y += 2000 if y < 50 else 1900
                
                if 1 <= d <= 31 and 1 <= month <= 12 and 2000 <= y <= 2099:
                    return {'day': d, 'month': month, 'year': y}
            except: continue
    return None

# Items per page for pagination
ITEMS_PER_PAGE = 10

# ---------------- DATABASE CONNECTION ----------------
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ---------------- AUTH DECORATOR ----------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page.", "error")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_current_user_id():
    return session.get('user_id', 1)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ---------------- CONTEXT PROCESSOR ----------------
@app.context_processor
def inject_settings():
    """Make user settings and translations available in all templates"""
    user_id = get_current_user_id()
    settings = get_user_settings(user_id)
    lang = settings.get('language', 'en')
    return {
        'currency': settings.get('currency', '₹'),
        'theme': settings.get('theme', 'dark'),
        'language': lang,
        'font_size': settings.get('font_size', 'medium'),
        'logged_in': 'user_id' in session,
        'username': session.get('username', 'Guest'),
        't': get_translations_dict(lang)
    }

# ---------------- AUTH ROUTES ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        
        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()
        
        if user and user['password_hash'] and check_password_hash(user["password_hash"], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash("Welcome back!", "success")
            return redirect("/")
        else:
            flash("Invalid email or password.", "error")
    
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")
        
        # Validate required fields
        if not username:
            flash("Username is required.", "error")
            return render_template("register.html")
        
        if not email:
            flash("Email is required.", "error")
            return render_template("register.html")
        
        if not password or len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("register.html")
        
        conn = get_db_connection()
        
        # Check if user exists
        existing = conn.execute(
            "SELECT id FROM users WHERE email = ? OR username = ?", 
            (email, username)
        ).fetchone()
        
        if existing:
            flash("Username or email already exists.", "error")
            conn.close()
            return render_template("register.html")
        
        # Create user directly
        password_hash = generate_password_hash(password)
        cursor = conn.execute(
            "INSERT INTO users (username, email, password_hash, is_verified, created_at) VALUES (?, ?, ?, 1, ?)",
            (username, email, password_hash, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        )
        user_id = cursor.lastrowid
        
        # Create default settings
        conn.execute(
            "INSERT INTO user_settings (user_id, currency, theme) VALUES (?, ?, ?)",
            (user_id, '₹', 'dark')
        )
        
        conn.commit()
        conn.close()
        
        session['user_id'] = user_id
        session['username'] = username
        flash("Account created successfully! Welcome to ExpenSOS!", "success")
        return redirect("/")
    
    return render_template("register.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect("/login")

# ---------------- OCR API ----------------
@app.route("/api/ocr", methods=["POST"])
@login_required
def ocr_process():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    if file.filename == '' or not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type'}), 400
    
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], f"ocr_tmp_{filename}")
    file.save(filepath)
    
    try:
        if not ocr_reader:
            return jsonify({'error': 'OCR engine loading. Please wait.'}), 503
            
        # EasyOCR processing
        results = ocr_reader.readtext(filepath)
        full_text = "\n".join([res[1] for res in results])
        
        # Extract features
        amount = extract_amount_python(full_text)
        date_obj = extract_date_python(full_text)
        
        confidence = sum([res[2] for res in results]) / len(results) if results else 0
        
        # Cleanup
        if os.path.exists(filepath):
            os.remove(filepath)
            
        return jsonify({
            'success': True,
            'amount': amount,
            'date': date_obj,
            'confidence': round(confidence * 100, 1),
            'raw_text': full_text  # Useful for debugging
        })
    except Exception as e:
        if os.path.exists(filepath):
            os.remove(filepath)
        return jsonify({'error': str(e)}), 500

# ---------------- HOME / DASHBOARD ----------------
@app.route("/")
@login_required
def index():
    user_id = get_current_user_id()
    conn = get_db_connection()
    
    expenses = conn.execute(
        "SELECT * FROM expenses WHERE user_id = ? ORDER BY date DESC",
        (user_id,)
    ).fetchall()
    
    # Get current month's expenses
    current_month = datetime.now().strftime('%Y-%m')
    month_expenses = conn.execute(
        "SELECT * FROM expenses WHERE user_id = ? AND strftime('%Y-%m', date) = ?",
        (user_id, current_month)
    ).fetchall()
    
    # Get budgets with progress
    budgets = conn.execute(
        "SELECT * FROM budgets WHERE user_id = ?",
        (user_id,)
    ).fetchall()
    
    budget_progress = []
    for budget in budgets:
        if budget['period'] == 'monthly':
            spent = sum(e['amount'] for e in month_expenses if e['category'] == budget['category'])
        else:  # weekly
            week_start = (datetime.now() - timedelta(days=datetime.now().weekday())).strftime('%Y-%m-%d')
            week_expenses = conn.execute(
                "SELECT SUM(amount) as total FROM expenses WHERE user_id = ? AND category = ? AND date >= ?",
                (user_id, budget['category'], week_start)
            ).fetchone()
            spent = week_expenses['total'] or 0
        
        percentage = min((spent / budget['amount']) * 100, 100) if budget['amount'] > 0 else 0
        status = 'success' if percentage < 70 else ('warning' if percentage < 90 else 'danger')
        
        budget_progress.append({
            'category': budget['category'],
            'budget': budget['amount'],
            'spent': spent,
            'percentage': round(percentage, 1),
            'status': status,
            'period': budget['period']
        })
    
    conn.close()

    total = sum(e["amount"] for e in expenses)
    month_total = sum(e["amount"] for e in month_expenses)
    
    # Category breakdown for pie chart
    category_data = defaultdict(float)
    for e in expenses:
        category_data[e["category"]] += e["amount"]

    # Smart Insights
    insights = generate_insights(expenses, month_expenses, category_data, total)
    
    # Category comparison (month-over-month)
    comparisons = get_category_comparison(user_id)

    today = datetime.now()

    return render_template(
        "index.html",
        expenses=expenses[:10],  # Show only recent 10
        total=total,
        month_total=month_total,
        category_data=dict(category_data),
        today=today,
        budget_progress=budget_progress,
        insights=insights,
        comparisons=comparisons
    )

def generate_insights(expenses, month_expenses, category_data, total):
    """Generate smart insights from expense data"""
    insights = []
    
    if not expenses:
        return insights
    
    # Highest spending day
    day_spending = defaultdict(float)
    for e in expenses:
        day_name = datetime.strptime(e['date'], '%Y-%m-%d').strftime('%A')
        day_spending[day_name] += e['amount']
    
    if day_spending:
        highest_day = max(day_spending, key=day_spending.get)
        insights.append(f"📅 Your highest spending day is {highest_day}")
    
    # Biggest category
    if category_data and total > 0:
        biggest_cat = max(category_data, key=category_data.get)
        percentage = round((category_data[biggest_cat] / total) * 100)
        insights.append(f"🏆 {biggest_cat} is your biggest expense at {percentage}%")
    
    # This month's trend
    if month_expenses:
        avg_per_expense = sum(e['amount'] for e in month_expenses) / len(month_expenses)
        insights.append(f"💰 Average expense this month: ₹{round(avg_per_expense)}")
    
    # Total expenses count
    insights.append(f"📊 You've logged {len(expenses)} expenses total")
    
    return insights[:4]  # Limit to 4 insights

def get_category_comparison(user_id):
    """Get month-over-month category comparison"""
    conn = get_db_connection()
    
    now = datetime.now()
    current_month = now.strftime('%Y-%m')
    last_month = (now.replace(day=1) - timedelta(days=1)).strftime('%Y-%m')
    
    current = conn.execute(
        "SELECT category, SUM(amount) as total FROM expenses WHERE user_id = ? AND strftime('%Y-%m', date) = ? GROUP BY category",
        (user_id, current_month)
    ).fetchall()
    
    previous = conn.execute(
        "SELECT category, SUM(amount) as total FROM expenses WHERE user_id = ? AND strftime('%Y-%m', date) = ? GROUP BY category",
        (user_id, last_month)
    ).fetchall()
    
    conn.close()
    
    prev_dict = {r['category']: r['total'] for r in previous}
    comparisons = []
    
    for row in current:
        cat = row['category']
        curr_amount = row['total']
        prev_amount = prev_dict.get(cat, 0)
        
        if prev_amount > 0:
            change = ((curr_amount - prev_amount) / prev_amount) * 100
            direction = "more" if change > 0 else "less"
            comparisons.append({
                'category': cat,
                'change': abs(round(change)),
                'direction': direction,
                'current': curr_amount,
                'previous': prev_amount
            })
    
    return comparisons[:3]  # Top 3 comparisons

# ---------------- ADD EXPENSE ----------------
@app.route("/add", methods=["POST"])
@login_required
def add_expense():
    user_id = get_current_user_id()
    amount = request.form["amount"]
    category = request.form["category"]
    note = request.form["note"]
    day = request.form["day"]
    month = request.form["month"]
    year = request.form["year"]
    is_recurring = 1 if request.form.get("is_recurring") else 0

    formatted_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"

    conn = get_db_connection()
    cursor = conn.execute(
        "INSERT INTO expenses (user_id, amount, category, note, date, is_recurring) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, amount, category, note, formatted_date, is_recurring)
    )
    expense_id = cursor.lastrowid
    conn.commit()
    
    # Handle receipt upload
    if 'receipt' in request.files:
        file = request.files['receipt']
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(f"{expense_id}_{file.filename}")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            conn.execute("UPDATE expenses SET receipt_path = ? WHERE id = ?", (filename, expense_id))
            conn.commit()
    
    conn.close()

    # Check budget alerts
    check_budget_alerts(user_id, category, float(amount))

    flash("Expense added successfully!", "success")
    return redirect("/")

def check_budget_alerts(user_id, category, new_amount):
    """Check if budget threshold is reached and show alert"""
    conn = get_db_connection()
    
    budget = conn.execute(
        "SELECT * FROM budgets WHERE user_id = ? AND category = ?",
        (user_id, category)
    ).fetchone()
    
    if budget:
        current_month = datetime.now().strftime('%Y-%m')
        spent = conn.execute(
            "SELECT SUM(amount) as total FROM expenses WHERE user_id = ? AND category = ? AND strftime('%Y-%m', date) = ?",
            (user_id, category, current_month)
        ).fetchone()['total'] or 0
        
        percentage = (spent / budget['amount']) * 100
        
        if percentage >= 100:
            flash(f"⚠️ Budget exceeded! You've spent ₹{spent:.0f} of ₹{budget['amount']:.0f} on {category}.", "error")
        elif percentage >= 80:
            flash(f"⚡ Heads up! You've used {percentage:.0f}% of your {category} budget.", "warning")
    
    conn.close()

# ---------------- DELETE EXPENSE ----------------
@app.route("/delete/<int:id>")
@login_required
def delete_expense(id):
    user_id = get_current_user_id()
    conn = get_db_connection()
    
    # Get receipt path to delete file
    expense = conn.execute("SELECT receipt_path FROM expenses WHERE id = ? AND user_id = ?", (id, user_id)).fetchone()
    if expense and expense['receipt_path']:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], expense['receipt_path']))
        except:
            pass
    
    conn.execute("DELETE FROM expenses WHERE id = ? AND user_id = ?", (id, user_id))
    conn.commit()
    conn.close()

    flash("Expense deleted.", "info")
    return redirect("/")

# ---------------- EDIT EXPENSE ----------------
@app.route("/edit/<int:id>")
@login_required
def edit_expense(id):
    user_id = get_current_user_id()
    conn = get_db_connection()
    expense = conn.execute(
        "SELECT * FROM expenses WHERE id = ? AND user_id = ?",
        (id, user_id)
    ).fetchone()
    conn.close()

    if not expense:
        flash("Expense not found.", "error")
        return redirect("/")

    date_parts = expense["date"].split("-")
    edit_year = int(date_parts[0])
    edit_month = int(date_parts[1])
    edit_day = int(date_parts[2])

    return render_template(
        "edit.html", 
        expense=expense,
        edit_day=edit_day,
        edit_month=edit_month,
        edit_year=edit_year
    )

# ---------------- UPDATE EXPENSE ----------------
@app.route("/update/<int:id>", methods=["POST"])
@login_required
def update_expense(id):
    user_id = get_current_user_id()
    amount = request.form["amount"]
    category = request.form["category"]
    note = request.form["note"]
    day = request.form["day"]
    month = request.form["month"]
    year = request.form["year"]
    is_recurring = 1 if request.form.get("is_recurring") else 0

    formatted_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"

    conn = get_db_connection()
    conn.execute(
        """
        UPDATE expenses
        SET amount = ?, category = ?, note = ?, date = ?, is_recurring = ?
        WHERE id = ? AND user_id = ?
        """,
        (amount, category, note, formatted_date, is_recurring, id, user_id)
    )
    
    # Handle receipt upload
    if 'receipt' in request.files:
        file = request.files['receipt']
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(f"{id}_{file.filename}")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            conn.execute("UPDATE expenses SET receipt_path = ? WHERE id = ?", (filename, id))
    
    conn.commit()
    conn.close()

    flash("Expense updated successfully!", "success")
    return redirect("/")

# ---------------- EXPENSES TAB (FILTER + SEARCH + PAGINATION) ----------------
@app.route("/expenses")
@login_required
def expenses():
    user_id = get_current_user_id()
    year = request.args.get("year")
    month = request.args.get("month")
    day = request.args.get("day")
    category = request.args.get("category")
    search = request.args.get("search", "").strip()
    page = request.args.get("page", 1, type=int)

    query = "SELECT * FROM expenses WHERE user_id = ?"
    params = [user_id]

    if year:
        query += " AND strftime('%Y', date) = ?"
        params.append(year)

    if month:
        query += " AND strftime('%m', date) = ?"
        params.append(month.zfill(2))

    if day:
        query += " AND strftime('%d', date) = ?"
        params.append(day.zfill(2))
    
    if category:
        query += " AND category = ?"
        params.append(category)
    
    if search:
        query += " AND (note LIKE ? OR category LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])

    query += " ORDER BY date DESC"

    conn = get_db_connection()
    
    # Get total count for pagination
    count_query = query.replace("SELECT *", "SELECT COUNT(*)")
    total_count = conn.execute(count_query, params).fetchone()[0]
    total_pages = (total_count + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    
    # Add pagination
    offset = (page - 1) * ITEMS_PER_PAGE
    query += f" LIMIT {ITEMS_PER_PAGE} OFFSET {offset}"
    
    all_expenses = conn.execute(query, params).fetchall()
    
    # Get all categories for filter dropdown
    categories = conn.execute(
        "SELECT DISTINCT category FROM expenses WHERE user_id = ?",
        (user_id,)
    ).fetchall()
    
    conn.close()

    # Calculate total for filtered results (without pagination)
    conn = get_db_connection()
    total_query = query.replace(f" LIMIT {ITEMS_PER_PAGE} OFFSET {offset}", "").replace("SELECT *", "SELECT SUM(amount) as total")
    total_result = conn.execute(total_query, params).fetchone()
    total = total_result[0] if total_result[0] else 0
    conn.close()

    return render_template(
        "expenses.html",
        expenses=all_expenses,
        total=total,
        year=year,
        month=month,
        day=day,
        category=category,
        search=search,
        categories=[c['category'] for c in categories],
        page=page,
        total_pages=total_pages,
        total_count=total_count
    )

# ---------------- SETTINGS ----------------
@app.route("/settings")
@login_required
def settings():
    user_id = get_current_user_id()
    settings = get_user_settings(user_id)
    
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    
    currencies = [
        ('₹', 'Indian Rupee (₹)'),
        ('$', 'US Dollar ($)'),
        ('€', 'Euro (€)'),
        ('£', 'British Pound (£)'),
        ('¥', 'Japanese Yen (¥)'),
        ('₿', 'Bitcoin (₿)')
    ]
    
    languages = [
        ('en', 'English'),
        ('hi', 'हिंदी (Hindi)'),
        ('te', 'తెలుగు (Telugu)')
    ]
    
    font_sizes = [
        ('small', 'Small'),
        ('medium', 'Medium'),
        ('large', 'Large')
    ]
    
    return render_template("settings.html", settings=settings, user=user, 
                         currencies=currencies, languages=languages, font_sizes=font_sizes)

@app.route("/settings/update", methods=["POST"])
@login_required
def update_settings():
    user_id = get_current_user_id()
    currency = request.form.get("currency", "₹")
    theme = request.form.get("theme", "dark")
    language = request.form.get("language", "en")
    font_size = request.form.get("font_size", "medium")
    
    conn = get_db_connection()
    
    # Check if settings exist
    existing = conn.execute("SELECT id FROM user_settings WHERE user_id = ?", (user_id,)).fetchone()
    
    if existing:
        conn.execute(
            "UPDATE user_settings SET currency = ?, theme = ?, language = ?, font_size = ? WHERE user_id = ?",
            (currency, theme, language, font_size, user_id)
        )
    else:
        conn.execute(
            "INSERT INTO user_settings (user_id, currency, theme, language, font_size) VALUES (?, ?, ?, ?, ?)",
            (user_id, currency, theme, language, font_size)
        )
    
    conn.commit()
    conn.close()
    
    flash("Settings updated successfully!", "success")
    return redirect("/settings")

# ---------------- BUDGETS ----------------
@app.route("/budgets")
@login_required
def budgets():
    user_id = get_current_user_id()
    conn = get_db_connection()
    
    budgets = conn.execute(
        "SELECT * FROM budgets WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,)
    ).fetchall()
    
    # Calculate progress for each budget
    current_month = datetime.now().strftime('%Y-%m')
    budget_list = []
    
    for budget in budgets:
        if budget['period'] == 'monthly':
            spent_result = conn.execute(
                "SELECT SUM(amount) as total FROM expenses WHERE user_id = ? AND category = ? AND strftime('%Y-%m', date) = ?",
                (user_id, budget['category'], current_month)
            ).fetchone()
        else:  # weekly
            week_start = (datetime.now() - timedelta(days=datetime.now().weekday())).strftime('%Y-%m-%d')
            spent_result = conn.execute(
                "SELECT SUM(amount) as total FROM expenses WHERE user_id = ? AND category = ? AND date >= ?",
                (user_id, budget['category'], week_start)
            ).fetchone()
        
        spent = spent_result['total'] or 0
        percentage = min((spent / budget['amount']) * 100, 100) if budget['amount'] > 0 else 0
        remaining = max(budget['amount'] - spent, 0)
        
        budget_list.append({
            'id': budget['id'],
            'category': budget['category'],
            'amount': budget['amount'],
            'period': budget['period'],
            'spent': spent,
            'remaining': remaining,
            'percentage': round(percentage, 1)
        })
    
    conn.close()
    
    categories = ['Food', 'Transport', 'Shopping', 'Rent', 'Others']
    
    return render_template("budgets.html", budgets=budget_list, categories=categories)

@app.route("/budgets/add", methods=["POST"])
@login_required
def add_budget():
    user_id = get_current_user_id()
    category = request.form["category"]
    amount = float(request.form["amount"])
    period = request.form.get("period", "monthly")
    
    conn = get_db_connection()
    
    # Check if budget already exists for this category
    existing = conn.execute(
        "SELECT id FROM budgets WHERE user_id = ? AND category = ?",
        (user_id, category)
    ).fetchone()
    
    if existing:
        conn.execute(
            "UPDATE budgets SET amount = ?, period = ? WHERE id = ?",
            (amount, period, existing['id'])
        )
        flash(f"Budget for {category} updated!", "success")
    else:
        conn.execute(
            "INSERT INTO budgets (user_id, category, amount, period, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, category, amount, period, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        )
        flash(f"Budget for {category} created!", "success")
    
    conn.commit()
    conn.close()
    
    return redirect("/budgets")

@app.route("/budgets/delete/<int:id>")
@login_required
def delete_budget(id):
    user_id = get_current_user_id()
    conn = get_db_connection()
    conn.execute("DELETE FROM budgets WHERE id = ? AND user_id = ?", (id, user_id))
    conn.commit()
    conn.close()
    
    flash("Budget deleted.", "info")
    return redirect("/budgets")

# ---------------- RECURRING EXPENSES ----------------
@app.route("/recurring")
@login_required
def recurring():
    user_id = get_current_user_id()
    conn = get_db_connection()
    
    recurring_expenses = conn.execute(
        "SELECT * FROM recurring_expenses WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,)
    ).fetchall()
    
    conn.close()
    
    return render_template("recurring.html", recurring_expenses=recurring_expenses)

@app.route("/recurring/add", methods=["POST"])
@login_required
def add_recurring():
    user_id = get_current_user_id()
    amount = float(request.form["amount"])
    category = request.form["category"]
    note = request.form.get("note", "")
    frequency = request.form["frequency"]
    
    # Calculate next date based on frequency
    today = datetime.now()
    if frequency == 'daily':
        next_date = (today + timedelta(days=1)).strftime('%Y-%m-%d')
    elif frequency == 'weekly':
        next_date = (today + timedelta(weeks=1)).strftime('%Y-%m-%d')
    else:  # monthly
        next_date = (today + timedelta(days=30)).strftime('%Y-%m-%d')
    
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO recurring_expenses (user_id, amount, category, note, frequency, next_date, active, created_at) VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
        (user_id, amount, category, note, frequency, next_date, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    )
    conn.commit()
    conn.close()
    
    flash("Recurring expense added!", "success")
    return redirect("/recurring")

@app.route("/recurring/toggle/<int:id>")
@login_required
def toggle_recurring(id):
    user_id = get_current_user_id()
    conn = get_db_connection()
    
    current = conn.execute(
        "SELECT active FROM recurring_expenses WHERE id = ? AND user_id = ?",
        (id, user_id)
    ).fetchone()
    
    if current:
        new_status = 0 if current['active'] == 1 else 1
        conn.execute(
            "UPDATE recurring_expenses SET active = ? WHERE id = ?",
            (new_status, id)
        )
        conn.commit()
        flash("Recurring expense " + ("enabled" if new_status else "paused") + ".", "info")
    
    conn.close()
    return redirect("/recurring")

@app.route("/recurring/delete/<int:id>")
@login_required
def delete_recurring(id):
    user_id = get_current_user_id()
    conn = get_db_connection()
    conn.execute("DELETE FROM recurring_expenses WHERE id = ? AND user_id = ?", (id, user_id))
    conn.commit()
    conn.close()
    
    flash("Recurring expense deleted.", "info")
    return redirect("/recurring")

# ---------------- MONTHLY DATA (FOR CHARTS) ----------------
@app.route("/monthly-data")
@login_required
def monthly_data():
    user_id = get_current_user_id()
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT date, amount FROM expenses WHERE user_id = ?",
        (user_id,)
    ).fetchall()
    conn.close()

    monthly = defaultdict(float)

    for r in rows:
        month = r["date"][:7]
        monthly[month] += r["amount"]

    return jsonify(monthly)

# ---------------- REMINDERS ----------------
@app.route("/reminders")
@login_required
def reminders():
    user_id = get_current_user_id()
    conn = get_db_connection()
    reminders = conn.execute(
        "SELECT * FROM reminders WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,)
    ).fetchall()
    conn.close()
    return render_template("reminders.html", reminders=reminders)

@app.route("/reminders/add", methods=["POST"])
@login_required
def add_reminder():
    user_id = get_current_user_id()
    days = request.form.getlist("days")
    time = request.form["time"]
    reminder_count = request.form["reminder_count"]
    
    if not days:
        flash("Please select at least one day.", "error")
        return redirect("/reminders")
    
    days_str = ",".join(days)
    created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO reminders (user_id, days, time, reminder_count, active, created_at) VALUES (?, ?, ?, ?, 1, ?)",
        (user_id, days_str, time, reminder_count, created_at)
    )
    conn.commit()
    conn.close()
    
    flash("Reminder added successfully!", "success")
    return redirect("/reminders")

@app.route("/reminders/toggle/<int:id>")
@login_required
def toggle_reminder(id):
    user_id = get_current_user_id()
    conn = get_db_connection()
    reminder = conn.execute("SELECT active FROM reminders WHERE id = ? AND user_id = ?", (id, user_id)).fetchone()
    if reminder:
        new_status = 0 if reminder["active"] == 1 else 1
        conn.execute("UPDATE reminders SET active = ? WHERE id = ?", (new_status, id))
        conn.commit()
        status_text = "enabled" if new_status == 1 else "disabled"
        flash(f"Reminder {status_text}.", "info")
    conn.close()
    return redirect("/reminders")

@app.route("/reminders/delete/<int:id>")
@login_required
def delete_reminder(id):
    user_id = get_current_user_id()
    conn = get_db_connection()
    conn.execute("DELETE FROM reminders WHERE id = ? AND user_id = ?", (id, user_id))
    conn.commit()
    conn.close()
    
    flash("Reminder deleted.", "info")
    return redirect("/reminders")

# ---------------- RECEIPT UPLOAD ----------------
@app.route("/upload-receipt/<int:expense_id>", methods=["POST"])
@login_required
def upload_receipt(expense_id):
    user_id = get_current_user_id()
    
    if 'receipt' not in request.files:
        flash("No file selected.", "error")
        return redirect(f"/edit/{expense_id}")
    
    file = request.files['receipt']
    if file.filename == '':
        flash("No file selected.", "error")
        return redirect(f"/edit/{expense_id}")
    
    if file and allowed_file(file.filename):
        filename = secure_filename(f"{expense_id}_{file.filename}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        conn = get_db_connection()
        conn.execute(
            "UPDATE expenses SET receipt_path = ? WHERE id = ? AND user_id = ?",
            (filename, expense_id, user_id)
        )
        conn.commit()
        conn.close()
        
        flash("Receipt uploaded successfully!", "success")
    else:
        flash("Invalid file type. Please upload an image.", "error")
    
    return redirect(f"/edit/{expense_id}")

@app.route("/uploads/<filename>")
@login_required
def uploaded_file(filename):
    from flask import send_from_directory
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ---------------- API ENDPOINTS ----------------
@app.route("/api/insights")
@login_required
def api_insights():
    user_id = get_current_user_id()
    conn = get_db_connection()
    expenses = conn.execute("SELECT * FROM expenses WHERE user_id = ?", (user_id,)).fetchall()
    conn.close()
    
    category_data = defaultdict(float)
    for e in expenses:
        category_data[e["category"]] += e["amount"]
    
    total = sum(e["amount"] for e in expenses)
    current_month = datetime.now().strftime('%Y-%m')
    month_expenses = [e for e in expenses if e['date'].startswith(current_month)]
    insights = generate_insights(expenses, month_expenses, category_data, total)
    
    return jsonify({"insights": insights})

@app.route("/api/budget-progress")
@login_required
def api_budget_progress():
    user_id = get_current_user_id()
    conn = get_db_connection()
    
    budgets = conn.execute("SELECT * FROM budgets WHERE user_id = ?", (user_id,)).fetchall()
    current_month = datetime.now().strftime('%Y-%m')
    
    progress = []
    for budget in budgets:
        spent = conn.execute(
            "SELECT SUM(amount) as total FROM expenses WHERE user_id = ? AND category = ? AND strftime('%Y-%m', date) = ?",
            (user_id, budget['category'], current_month)
        ).fetchone()['total'] or 0
        
        percentage = (spent / budget['amount']) * 100 if budget['amount'] > 0 else 0
        progress.append({
            'category': budget['category'],
            'budget': budget['amount'],
            'spent': spent,
            'percentage': round(percentage, 1)
        })
    
    conn.close()
    return jsonify(progress)



# ---------------- APP START ----------------
if __name__ == "__main__":
    init_db()
    app.run(host='0.0.0.0', port=6969, debug=True)
