import logging
import re
from flask import Flask, render_template, request, redirect, jsonify, flash, session, url_for, send_from_directory
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from collections import defaultdict
from datetime import datetime, timedelta
from functools import wraps
import os

try:
    from .database import get_db_connection, init_db, get_user_settings
    from .translations import get_translations_dict
except ImportError:
    from database import get_db_connection, init_db, get_user_settings
    from translations import get_translations_dict

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "frontend"))

app = Flask(
    __name__,
    template_folder=os.path.join(FRONTEND_DIR, "templates"),
    static_folder=os.path.join(FRONTEND_DIR, "static"),
)

_secret = os.environ.get("SECRET_KEY", "")
if not _secret:
    import warnings
    warnings.warn(
        "SECRET_KEY is not set. Using an insecure default. "
        "Set the SECRET_KEY environment variable in production.",
        RuntimeWarning,
        stacklevel=1,
    )
    _secret = "spendwise_dev_secret_do_not_use_in_prod"
app.secret_key = _secret

csrf = CSRFProtect()
csrf.init_app(app)

@app.route('/ads.txt')
def ads_txt():
    return send_from_directory(app.static_folder, 'ads.txt')

@app.route('/manifest.json')
def manifest():
    return send_from_directory(app.static_folder, 'manifest.json')

@app.route('/sw.js')
def service_worker():
    response = send_from_directory(app.static_folder, 'sw.js')
    response.headers['Service-Worker-Allowed'] = '/'
    return response

# Upload configuration
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max

# Security headers
@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ITEMS_PER_PAGE = 10

# Max lengths for text inputs
MAX_NOTE_LEN = 500
MAX_NAME_LEN = 80
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

# ---------------- HELPERS ----------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page.", "error")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_current_user_id():
    """Return the logged-in user's ID, or None if unauthenticated."""
    return session.get('user_id')

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def validate_amount(raw: str):
    """Parse and validate a monetary amount string. Returns (float, error_str)."""
    try:
        value = float(raw)
    except (ValueError, TypeError):
        return None, "Amount must be a valid number."
    if value <= 0:
        return None, "Amount must be greater than zero."
    if value > 99_999_999:
        return None, "Amount is unreasonably large."
    return value, None

def validate_date(year: str, month: str, day: str):
    """Validate and return an ISO date string, or (None, error_str)."""
    try:
        dt = datetime(int(year), int(month), int(day))
        return dt.strftime('%Y-%m-%d'), None
    except (ValueError, TypeError):
        return None, "Invalid date. Please check the day, month, and year."

# ---------------- CONTEXT PROCESSOR ----------------
@app.context_processor
def inject_settings():
    """Make user settings and translations available in all templates."""
    user_id = get_current_user_id()
    logged_in = user_id is not None
    if logged_in:
        settings = get_user_settings(user_id)
    else:
        settings = {}
    lang = settings.get('language', 'en')
    return {
        'currency': settings.get('currency', '₹'),
        'theme': settings.get('theme') or 'dark',
        'language': lang,
        'font_size': settings.get('font_size', 'medium'),
        'logged_in': logged_in,
        'username': session.get('username', 'Guest'),
        't': get_translations_dict(lang),
    }
# ---------------- AUTH ROUTES ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        if not email or not password:
            flash("Email and password are required.", "error")
            return render_template("login.html")

        with get_db_connection() as conn:
            cursor = conn.execute(
                "SELECT id, username, password_hash FROM users WHERE email = %s",
                (email,),
            )
            user = cursor.fetchone()
            cursor.close()

        if user and user['password_hash'] and check_password_hash(user['password_hash'], password):
            session.clear()
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash("Welcome back!", "success")
            return redirect("/")

        flash("Invalid email or password.", "error")

    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        if not username or len(username) > MAX_NAME_LEN:
            flash("Username is required and must be under 80 characters.", "error")
            return render_template("register.html")

        if not email or not EMAIL_RE.match(email):
            flash("A valid email address is required.", "error")
            return render_template("register.html")

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("register.html")

        with get_db_connection() as conn:
            cursor = conn.execute(
                "SELECT id FROM users WHERE email = %s OR username = %s",
                (email, username),
            )
            existing = cursor.fetchone()
            cursor.close()

            if existing:
                flash("Username or email already exists.", "error")
                return render_template("register.html")

            password_hash = generate_password_hash(password)
            cursor = conn.execute(
                """
                INSERT INTO users (username, email, password_hash, is_verified)
                VALUES (%s, %s, %s, TRUE)
                RETURNING id
                """,
                (username, email, password_hash),
            )
            user_id = cursor.fetchone()["id"]
            cursor.close()

            conn.execute(
                "INSERT INTO user_settings (user_id, currency, theme, language, font_size) "
                "VALUES (%s, %s, %s, %s, %s)",
                (user_id, '₹', 'dark', 'en', 'medium'),
            ).close()
            conn.commit()

        session.clear()
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

# ---------------- HOME / DASHBOARD ----------------
@app.route("/")
@login_required
def index():
    user_id = get_current_user_id()
    now = datetime.now()
    current_month = now.strftime('%Y-%m')

    with get_db_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM expenses WHERE user_id = %s ORDER BY date DESC",
            (user_id,),
        )
        expenses = cursor.fetchall()
        cursor.close()

        cursor = conn.execute(
            "SELECT * FROM expenses WHERE user_id = %s "
            "AND TO_CHAR(date, 'YYYY-MM') = %s",
            (user_id, current_month),
        )
        month_expenses = cursor.fetchall()
        cursor.close()

        cursor = conn.execute(
            "SELECT * FROM budgets WHERE user_id = %s",
            (user_id,),
        )
        budgets = cursor.fetchall()
        cursor.close()

        budget_progress = []
        for budget in budgets:
            if budget['period'] == 'monthly':
                spent = sum(
                    e['amount'] for e in month_expenses
                    if e['category'] == budget['category']
                )
            else:  # weekly
                week_start = (
                    now - timedelta(days=now.weekday())
                ).strftime('%Y-%m-%d')
                cursor = conn.execute(
                    "SELECT COALESCE(SUM(amount), 0) AS total "
                    "FROM expenses WHERE user_id = %s AND category = %s AND date >= %s",
                    (user_id, budget['category'], week_start),
                )
                spent = cursor.fetchone()['total']
                cursor.close()

            percentage = (
                min((float(spent) / float(budget['amount'])) * 100, 100)
                if budget['amount'] > 0 else 0
            )
            status = (
                'success' if percentage < 70
                else ('warning' if percentage < 90 else 'danger')
            )
            budget_progress.append({
                'category': budget['category'],
                'budget': budget['amount'],
                'spent': spent,
                'percentage': round(percentage, 1),
                'status': status,
                'period': budget['period'],
            })

        # Category comparison using a single connection
        comparisons = _get_category_comparison(conn, user_id, now)

    total = sum(float(e["amount"]) for e in expenses)
    month_total = sum(float(e["amount"]) for e in month_expenses)

    category_data = defaultdict(float)
    for e in expenses:
        category_data[e["category"]] += float(e["amount"])

    insights = generate_insights(expenses, month_expenses, dict(category_data), total)

    with get_db_connection() as conn:
        # Check for due reminders (within next 3 days)
        cursor = conn.execute(
            "SELECT message, remind_date FROM reminders "
            "WHERE user_id = %s AND active = TRUE "
            "AND remind_date BETWEEN CURRENT_DATE AND (CURRENT_DATE + INTERVAL '3 days')",
            (user_id,)
        )
        due_reminders = cursor.fetchall()
        cursor.close()

        for r in due_reminders:
            flash(f"🔔 Reminder: {r['message']} is due on {r['remind_date']}!", "budget_alert")

    return render_template(
        "index.html",
        expenses=expenses[:10],
        total=total,
        month_total=month_total,
        category_data=dict(category_data),
        today=now,
        budget_progress=budget_progress,
        insights=insights,
        comparisons=comparisons,
    )


def generate_insights(expenses, month_expenses, category_data, total):
    """Generate smart insights from expense data."""
    insights = []
    if not expenses:
        return insights

    day_spending = defaultdict(float)
    for e in expenses:
        day_spending[e['date'].strftime('%A')] += float(e['amount'])

    if day_spending:
        highest_day = max(day_spending, key=day_spending.get)
        insights.append(f"📅 Your highest spending day is {highest_day}")

    if category_data and total > 0:
        biggest_cat = max(category_data, key=category_data.get)
        percentage = round((category_data[biggest_cat] / total) * 100)
        insights.append(f"🏆 {biggest_cat} is your biggest expense at {percentage}%")

    if month_expenses:
        month_total = sum(float(e['amount']) for e in month_expenses)
        avg = month_total / len(month_expenses)
        insights.append(f"💰 Average expense this month: {round(avg, 2)}")

    insights.append(f"📊 You've logged {len(expenses)} expenses total")
    return insights[:4]


def _get_category_comparison(conn, user_id, now):
    """Month-over-month comparison using an existing connection."""
    current_month = now.strftime('%Y-%m')
    last_month = (now.replace(day=1) - timedelta(days=1)).strftime('%Y-%m')

    cursor = conn.execute(
        "SELECT category, SUM(amount) AS total FROM expenses "
        "WHERE user_id = %s AND TO_CHAR(date, 'YYYY-MM') = %s GROUP BY category",
        (user_id, current_month),
    )
    current = cursor.fetchall()
    cursor.close()

    cursor = conn.execute(
        "SELECT category, SUM(amount) AS total FROM expenses "
        "WHERE user_id = %s AND TO_CHAR(date, 'YYYY-MM') = %s GROUP BY category",
        (user_id, last_month),
    )
    previous = cursor.fetchall()
    cursor.close()

    prev_dict = {r['category']: float(r['total']) for r in previous}
    comparisons = []
    for row in current:
        cat = row['category']
        curr_amount = float(row['total'])
        prev_amount = prev_dict.get(cat, 0)
        if prev_amount > 0:
            change = ((curr_amount - prev_amount) / prev_amount) * 100
            comparisons.append({
                'category': cat,
                'change': abs(round(change)),
                'direction': "more" if change > 0 else "less",
                'current': curr_amount,
                'previous': prev_amount,
            })

    return comparisons[:3]


# Keep public name for API endpoint backward compat
def get_category_comparison(user_id):
    now = datetime.now()
    with get_db_connection() as conn:
        return _get_category_comparison(conn, user_id, now)


# ---------------- ADD EXPENSE ----------------
@app.route("/add", methods=["POST"])
@login_required
def add_expense():
    user_id = get_current_user_id()
    category = (request.form.get("category") or "").strip()
    note = (request.form.get("note") or "").strip()[:MAX_NOTE_LEN]
    day = (request.form.get("day") or "").strip()
    month = (request.form.get("month") or "").strip()
    year = (request.form.get("year") or "").strip()
    is_recurring = bool(request.form.get("is_recurring"))

    amount_value, err = validate_amount(request.form.get("amount", ""))
    if err:
        flash(err, "error")
        return redirect("/")

    if not all([category, day, month, year]):
        flash("Please fill in all required expense fields.", "error")
        return redirect("/")

    formatted_date, err = validate_date(year, month, day)
    if err:
        flash(err, "error")
        return redirect("/")

    with get_db_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO expenses (user_id, amount, category, note, date, is_recurring) "
            "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
            (user_id, amount_value, category, note, formatted_date, is_recurring),
        )
        expense_id = cursor.fetchone()["id"]
        cursor.close()

        if 'receipt' in request.files:
            file = request.files['receipt']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(f"{expense_id}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                conn.execute(
                    "UPDATE expenses SET receipt_path = %s WHERE id = %s",
                    (filename, expense_id),
                ).close()

        conn.commit()

    # If marked as recurring, also add to recurring_expenses table for tracking in that tab
    if is_recurring:
        with get_db_connection() as conn:
            # We set a default next_date as 1 month from now
            next_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
            conn.execute(
                """
                INSERT INTO recurring_expenses (user_id, amount, category, note, frequency, next_date, active)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (user_id, amount_value, category, note, 'monthly', next_date, True)
            ).close()
            conn.commit()

    check_budget_alerts(user_id, category, amount_value)
    flash("Expense added successfully!", "success")
    return redirect("/")

def check_budget_alerts(user_id, category, new_amount):
    """Check if budget threshold is reached and show alert"""
    conn = get_db_connection()
    with get_db_connection() as conn:
        cursor = conn.execute(
            "SELECT amount FROM budgets WHERE user_id = %s AND category = %s",
            (user_id, category),
        )
        budget = cursor.fetchone()
        cursor.close()

        if budget:
            current_month = datetime.now().strftime('%Y-%m')
            cursor = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) AS total FROM expenses "
                "WHERE user_id = %s AND category = %s AND TO_CHAR(date, 'YYYY-MM') = %s",
                (user_id, category, current_month),
            )
            spent = float(cursor.fetchone()['total'])
            cursor.close()

            budget_amount = float(budget['amount'])
            percentage = (spent / budget_amount) * 100

            if percentage >= 100:
                flash(
                    f"⚠️ Budget exceeded! You've spent {spent:.0f} of {budget_amount:.0f} on {category}.",
                    "budget_alert",
                )
            elif percentage >= 80:
                flash(
                    f"⚡ Heads up! You've used {percentage:.0f}% of your {category} budget.",
                    "budget_alert",
                )

# ---------------- DELETE EXPENSE ----------------
@app.route("/delete/<int:id>")
@login_required
def delete_expense(id):
    user_id = get_current_user_id()
    with get_db_connection() as conn:
        cursor = conn.execute(
            "SELECT receipt_path FROM expenses WHERE id = %s AND user_id = %s",
            (id, user_id),
        )
        expense = cursor.fetchone()
        cursor.close()

        if expense and expense['receipt_path']:
            receipt_path = os.path.join(app.config['UPLOAD_FOLDER'], expense['receipt_path'])
            try:
                os.remove(receipt_path)
            except OSError as exc:
                logger.warning("Could not delete receipt file %s: %s", receipt_path, exc)

        conn.execute(
            "DELETE FROM expenses WHERE id = %s AND user_id = %s",
            (id, user_id),
        ).close()
        conn.commit()

    flash("Expense deleted.", "info")
    return redirect("/")

# ---------------- EDIT / UPDATE EXPENSE ----------------
@app.route("/edit/<int:id>")
@login_required
def edit_expense(id):
    user_id = get_current_user_id()
    with get_db_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM expenses WHERE id = %s AND user_id = %s",
            (id, user_id),
        )
        expense = cursor.fetchone()
        cursor.close()

    if not expense:
        flash("Expense not found.", "error")
        return redirect("/")

    return render_template(
        "edit.html",
        expense=expense,
        edit_day=expense["date"].day,
        edit_month=expense["date"].month,
        edit_year=expense["date"].year,
    )

@app.route("/edit/<int:id>", methods=["POST"])
@login_required
def update_expense(id):
    user_id = get_current_user_id()
    category = (request.form.get("category") or "").strip()
    note = (request.form.get("note") or "").strip()[:MAX_NOTE_LEN]
    day = (request.form.get("day") or "").strip()
    month = (request.form.get("month") or "").strip()
    year = (request.form.get("year") or "").strip()
    is_recurring = bool(request.form.get("is_recurring"))

    amount_value, err = validate_amount(request.form.get("amount", ""))
    if err:
        flash(err, "error")
        return redirect(f"/edit/{id}")

    if not all([category, day, month, year]):
        flash("Please fill in all required expense fields.", "error")
        return redirect(f"/edit/{id}")

    formatted_date, err = validate_date(year, month, day)
    if err:
        flash(err, "error")
        return redirect(f"/edit/{id}")

    with get_db_connection() as conn:
        conn.execute(
            "UPDATE expenses SET amount=%s, category=%s, note=%s, "
            "date=%s, is_recurring=%s WHERE id=%s AND user_id=%s",
            (amount_value, category, note, formatted_date, is_recurring, id, user_id),
        ).close()

        if 'receipt' in request.files:
            file = request.files['receipt']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(f"{id}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                conn.execute(
                    "UPDATE expenses SET receipt_path = %s WHERE id = %s",
                    (filename, id),
                ).close()

        conn.commit()

    flash("Expense updated successfully!", "success")
    return redirect("/")

# ---------------- EXPENSES TAB (FILTER + SEARCH + PAGINATION) ----------------
@app.route("/expenses")
@login_required
def expenses():
    user_id = get_current_user_id()
    year = (request.args.get("year") or "").strip() or None
    month = (request.args.get("month") or "").strip() or None
    day = (request.args.get("day") or "").strip() or None
    category = (request.args.get("category") or "").strip() or None
    search = (request.args.get("search") or "").strip()
    page = max(request.args.get("page", 1, type=int) or 1, 1)

    where = "WHERE user_id = %s"
    params: list = [user_id]

    if year:
        where += " AND TO_CHAR(date, 'YYYY') = %s"
        params.append(year)
    if month:
        where += " AND TO_CHAR(date, 'MM') = %s"
        params.append(month.zfill(2))
    if day:
        where += " AND TO_CHAR(date, 'DD') = %s"
        params.append(day.zfill(2))
    if category:
        where += " AND category = %s"
        params.append(category)
    if search:
        where += " AND (note ILIKE %s OR category ILIKE %s)"
        params.extend([f"%{search}%", f"%{search}%"])

    with get_db_connection() as conn:
        # Total count for pagination
        cursor = conn.execute(f"SELECT COUNT(*) FROM expenses {where}", params)
        total_count = cursor.fetchone()[0]
        cursor.close()
        total_pages = max((total_count + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE, 1)

        # Filtered total amount
        cursor = conn.execute(
            f"SELECT COALESCE(SUM(amount), 0) FROM expenses {where}", params
        )
        total = float(cursor.fetchone()[0])
        cursor.close()

        # Paginated rows
        offset = (page - 1) * ITEMS_PER_PAGE
        cursor = conn.execute(
            f"SELECT * FROM expenses {where} ORDER BY date DESC "
            f"LIMIT {ITEMS_PER_PAGE} OFFSET {offset}",
            params,
        )
        all_expenses = cursor.fetchall()
        cursor.close()

        # Categories for dropdown
        cursor = conn.execute(
            "SELECT DISTINCT category FROM expenses WHERE user_id = %s ORDER BY category",
            (user_id,),
        )
        categories = [r['category'] for r in cursor.fetchall()]
        cursor.close()

    return render_template(
        "expenses.html",
        expenses=all_expenses,
        total=total,
        year=year,
        month=month,
        day=day,
        category=category,
        search=search,
        categories=categories,
        page=page,
        total_pages=total_pages,
        total_count=total_count,
    )

# ---------------- SETTINGS ----------------
@app.route("/settings")
@login_required
def settings():
    user_id = get_current_user_id()
    user_settings = get_user_settings(user_id)

    with get_db_connection() as conn:
        cursor = conn.execute(
            "SELECT username, email, created_at FROM users WHERE id = %s",
            (user_id,),
        )
        user = cursor.fetchone()
        cursor.close()

    if not user:
        user = {
            "username": session.get("username", "Guest"),
            "email": "",
            "created_at": None,
        }

    currencies = [
        ('₹', 'Indian Rupee (₹)'),
        ('$', 'US Dollar ($)'),
        ('€', 'Euro (€)'),
        ('£', 'British Pound (£)'),
        ('¥', 'Japanese Yen (¥)'),
        ('₿', 'Bitcoin (₿)'),
    ]
    languages = [
        ('en', 'English'),
        ('hi', 'हिंदी (Hindi)'),
        ('te', 'తెలుగు (Telugu)'),
    ]
    font_sizes = [('small', 'Small'), ('medium', 'Medium'), ('large', 'Large')]

    created_at = user["created_at"] if user else None
    if hasattr(created_at, "strftime"):
        member_since = created_at.strftime("%Y-%m-%d")
    elif created_at:
        member_since = str(created_at)[:10]
    else:
        member_since = "N/A"

    return render_template(
        "settings.html",
        settings=user_settings,
        user=user,
        member_since=member_since,
        currencies=currencies,
        languages=languages,
        font_sizes=font_sizes,
    )

@app.route("/settings/update", methods=["POST"])
@login_required
def update_settings():
    user_id = get_current_user_id()
    currency = (request.form.get("currency") or "₹").strip()
    theme = (request.form.get("theme") or "dark").strip()
    language = (request.form.get("language") or "en").strip()
    font_size = (request.form.get("font_size") or "medium").strip()

    with get_db_connection() as conn:
        # UPSERT: insert or update in one statement
        conn.execute(
            """
            INSERT INTO user_settings (user_id, currency, theme, language, font_size)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE
              SET currency  = EXCLUDED.currency,
                  theme     = EXCLUDED.theme,
                  language  = EXCLUDED.language,
                  font_size = EXCLUDED.font_size
            """,
            (user_id, currency, theme, language, font_size),
        ).close()
        conn.commit()

    flash("Settings updated successfully!", "success")
    return redirect("/settings")


@app.route("/settings/change-password", methods=["POST"])
@login_required
def change_password():
    user_id = get_current_user_id()
    current_pw = request.form.get("current_password")
    new_pw = request.form.get("new_password")
    confirm_pw = request.form.get("confirm_password")

    if not current_pw or not new_pw or not confirm_pw:
        flash("All password fields are required.", "error")
        return redirect("/settings")

    if new_pw != confirm_pw:
        flash("New passwords do not match.", "error")
        return redirect("/settings")

    if len(new_pw) < 6:
        flash("New password must be at least 6 characters.", "error")
        return redirect("/settings")

    with get_db_connection() as conn:
        cursor = conn.execute("SELECT password_hash FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        cursor.close()

        if not user or not check_password_hash(user["password_hash"], current_pw):
            flash("Current password is incorrect.", "error")
            return redirect("/settings")

        new_hash = generate_password_hash(new_pw)
        conn.execute("UPDATE users SET password_hash = %s WHERE id = %s", (new_hash, user_id))
        conn.commit()

    flash("Password updated successfully!", "success")
    return redirect("/settings")


@app.route("/settings/delete-account", methods=["POST"])
@login_required
def delete_account():
    user_id = get_current_user_id()
    # For security, we could ask for password here too, but let's keep it simple with a POST for now
    with get_db_connection() as conn:
        # Cascading deletes should handle expenses, budgets etc if DB is setup with FKs, 
        # but let's be explicit if needed or trust the init_db schema.
        conn.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
    
    session.clear()
    flash("Your account has been permanently deleted. We're sorry to see you go.", "info")
    return redirect("/login")


# ---------------- BUDGETS ----------------
@app.route("/budgets")
@login_required
def budgets():
    user_id = get_current_user_id()
    now = datetime.now()
    current_month = now.strftime('%Y-%m')

    with get_db_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM budgets WHERE user_id = %s ORDER BY created_at DESC",
            (user_id,),
        )
        raw_budgets = cursor.fetchall()
        cursor.close()

        budget_list = []
        for budget in raw_budgets:
            if budget['period'] == 'monthly':
                cursor = conn.execute(
                    "SELECT COALESCE(SUM(amount), 0) AS total FROM expenses "
                    "WHERE user_id = %s AND category = %s AND TO_CHAR(date, 'YYYY-MM') = %s",
                    (user_id, budget['category'], current_month),
                )
            else:  # weekly
                week_start = (now - timedelta(days=now.weekday())).strftime('%Y-%m-%d')
                cursor = conn.execute(
                    "SELECT COALESCE(SUM(amount), 0) AS total FROM expenses "
                    "WHERE user_id = %s AND category = %s AND date >= %s",
                    (user_id, budget['category'], week_start),
                )
            spent = float(cursor.fetchone()['total'])
            cursor.close()

            budget_amount = float(budget['amount'])
            percentage = min((spent / budget_amount) * 100, 100) if budget_amount > 0 else 0
            budget_list.append({
                'id': budget['id'],
                'category': budget['category'],
                'amount': budget_amount,
                'period': budget['period'],
                'spent': spent,
                'remaining': max(budget_amount - spent, 0),
                'percentage': round(percentage, 1),
            })

    categories = ['Food', 'Transport', 'Shopping', 'Rent', 'Others']
    return render_template("budgets.html", budgets=budget_list, categories=categories)


@app.route("/budgets/add", methods=["POST"])
@login_required
def add_budget():
    user_id = get_current_user_id()
    category = (request.form.get("category") or "").strip()
    period = (request.form.get("period") or "monthly").strip()

    if not category:
        flash("Category is required.", "error")
        return redirect("/budgets")

    amount, err = validate_amount(request.form.get("amount", ""))
    if err:
        flash(err, "error")
        return redirect("/budgets")

    with get_db_connection() as conn:
        cursor = conn.execute(
            "SELECT id FROM budgets WHERE user_id = %s AND category = %s",
            (user_id, category),
        )
        existing = cursor.fetchone()
        cursor.close()

        if existing:
            conn.execute(
                "UPDATE budgets SET amount = %s, period = %s WHERE id = %s",
                (amount, period, existing['id']),
            ).close()
            flash(f"Budget for {category} updated!", "success")
        else:
            conn.execute(
                "INSERT INTO budgets (user_id, category, amount, period) "
                "VALUES (%s, %s, %s, %s)",
                (user_id, category, amount, period),
            ).close()
            flash(f"Budget for {category} created!", "success")
        conn.commit()

    return redirect("/budgets")


@app.route("/budgets/delete/<int:id>")
@login_required
def delete_budget(id):
    user_id = get_current_user_id()
    with get_db_connection() as conn:
        conn.execute(
            "DELETE FROM budgets WHERE id = %s AND user_id = %s", (id, user_id)
        ).close()
        conn.commit()
    flash("Budget deleted.", "info")
    return redirect("/budgets")


# ---------------- RECURRING EXPENSES ----------------
@app.route("/recurring")
@login_required
def recurring():
    user_id = get_current_user_id()
    with get_db_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM recurring_expenses WHERE user_id = %s ORDER BY created_at DESC",
            (user_id,),
        )
        recurring_expenses = cursor.fetchall()
        cursor.close()
    return render_template("recurring.html", recurring=recurring_expenses)


@app.route("/recurring/add", methods=["POST"])
@login_required
def add_recurring():
    user_id = get_current_user_id()
    category = (request.form.get("category") or "").strip()
    note = (request.form.get("note") or "").strip()[:MAX_NOTE_LEN]
    frequency = (request.form.get("frequency") or "").strip()

    if not category or not frequency:
        flash("Category and frequency are required.", "error")
        return redirect("/recurring")

    amount, err = validate_amount(request.form.get("amount", ""))
    if err:
        flash(err, "error")
        return redirect("/recurring")

    today = datetime.now()
    if frequency == 'daily':
        next_date = (today + timedelta(days=1)).strftime('%Y-%m-%d')
    elif frequency == 'weekly':
        next_date = (today + timedelta(weeks=1)).strftime('%Y-%m-%d')
    else:
        next_date = (today + timedelta(days=30)).strftime('%Y-%m-%d')

    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO recurring_expenses "
            "(user_id, amount, category, note, frequency, next_date, active) "
            "VALUES (%s, %s, %s, %s, %s, %s, TRUE)",
            (user_id, amount, category, note, frequency, next_date),
        ).close()
        conn.commit()

    flash("Recurring expense added!", "success")
    return redirect("/recurring")


@app.route("/recurring/toggle/<int:id>")
@login_required
def toggle_recurring(id):
    user_id = get_current_user_id()
    with get_db_connection() as conn:
        cursor = conn.execute(
            "SELECT active FROM recurring_expenses WHERE id = %s AND user_id = %s",
            (id, user_id),
        )
        current = cursor.fetchone()
        cursor.close()
        if current:
            new_status = not current['active']
            conn.execute(
                "UPDATE recurring_expenses SET active = %s WHERE id = %s",
                (new_status, id),
            ).close()
            conn.commit()
            flash(
                "Recurring expense " + ("enabled" if new_status else "paused") + ".",
                "info",
            )
    return redirect("/recurring")


@app.route("/recurring/delete/<int:id>")
@login_required
def delete_recurring(id):
    user_id = get_current_user_id()
    with get_db_connection() as conn:
        conn.execute(
            "DELETE FROM recurring_expenses WHERE id = %s AND user_id = %s",
            (id, user_id),
        ).close()
        conn.commit()
    flash("Recurring expense deleted.", "info")
    return redirect("/recurring")


# ---------------- MONTHLY DATA (FOR CHARTS) ----------------
@app.route("/monthly-data")
@login_required
def monthly_data():
    """Return per-month totals aggregated in SQL."""
    user_id = get_current_user_id()
    with get_db_connection() as conn:
        cursor = conn.execute(
            "SELECT TO_CHAR(date, 'YYYY-MM') AS month, SUM(amount) AS total "
            "FROM expenses WHERE user_id = %s "
            "GROUP BY TO_CHAR(date, 'YYYY-MM') ORDER BY month",
            (user_id,),
        )
        rows = cursor.fetchall()
        cursor.close()

    monthly = {r['month']: float(r['total']) for r in rows}
    return jsonify(monthly)


# ---------------- REMINDERS ----------------
@app.route("/reminders")
@login_required
def reminders():
    user_id = get_current_user_id()
    with get_db_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM reminders WHERE user_id = %s ORDER BY created_at DESC",
            (user_id,),
        )
        reminder_list = cursor.fetchall()
        cursor.close()
    return render_template("reminders.html", reminders=reminder_list)


@app.route("/reminders/add", methods=["POST"])
@login_required
def add_reminder():
    user_id = get_current_user_id()
    message = (request.form.get("message") or "").strip()
    remind_date = (request.form.get("remind_date") or "").strip()

    if not message or not remind_date:
        flash("Message and due date are required.", "error")
        return redirect("/reminders")

    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO reminders (user_id, message, remind_date) VALUES (%s, %s, %s)",
            (user_id, message, remind_date)
        ).close()
        conn.commit()

    flash("Reminder set successfully!", "success")
    return redirect("/reminders")


@app.route("/reminders/toggle/<int:id>")
@login_required
def toggle_reminder(id):
    user_id = get_current_user_id()
    with get_db_connection() as conn:
        cursor = conn.execute(
            "SELECT active FROM reminders WHERE id = %s AND user_id = %s",
            (id, user_id),
        )
        reminder = cursor.fetchone()
        cursor.close()
        if reminder:
            new_status = not reminder["active"]
            conn.execute(
                "UPDATE reminders SET active = %s WHERE id = %s", (new_status, id)
            ).close()
            conn.commit()
            flash(f"Reminder {'enabled' if new_status else 'disabled'}.", "info")
    return redirect("/reminders")


@app.route("/reminders/delete/<int:id>")
@login_required
def delete_reminder(id):
    user_id = get_current_user_id()
    with get_db_connection() as conn:
        conn.execute(
            "DELETE FROM reminders WHERE id = %s AND user_id = %s", (id, user_id)
        ).close()
        conn.commit()
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
    if not file or not file.filename:
        flash("No file selected.", "error")
        return redirect(f"/edit/{expense_id}")

    if not allowed_file(file.filename):
        flash("Invalid file type. Please upload an image (png/jpg/gif/webp).", "error")
        return redirect(f"/edit/{expense_id}")

    filename = secure_filename(f"{expense_id}_{file.filename}")
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

    with get_db_connection() as conn:
        conn.execute(
            "UPDATE expenses SET receipt_path = %s WHERE id = %s AND user_id = %s",
            (filename, expense_id, user_id),
        ).close()
        conn.commit()

    flash("Receipt uploaded successfully!", "success")
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
    with get_db_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM expenses WHERE user_id = %s", (user_id,)
        )
        expenses = cursor.fetchall()
        cursor.close()

    category_data: dict = defaultdict(float)
    for e in expenses:
        category_data[e["category"]] += float(e["amount"])

    total = sum(float(e["amount"]) for e in expenses)
    current_month = datetime.now().strftime('%Y-%m')
    month_expenses = [e for e in expenses if e['date'].strftime('%Y-%m') == current_month]
    insights = generate_insights(expenses, month_expenses, dict(category_data), total)
    return jsonify({"insights": insights})


@app.route("/api/budget-progress")
@login_required
def api_budget_progress():
    """Return budget vs. spend, resolved in a single JOIN query (no N+1)."""
    user_id = get_current_user_id()
    current_month = datetime.now().strftime('%Y-%m')

    with get_db_connection() as conn:
        cursor = conn.execute(
            """
            SELECT b.category,
                   b.amount   AS budget,
                   b.period,
                   COALESCE(SUM(e.amount), 0) AS spent
            FROM budgets b
            LEFT JOIN expenses e
                ON  e.user_id   = b.user_id
                AND e.category  = b.category
                AND TO_CHAR(e.date, 'YYYY-MM') = %s
            WHERE b.user_id = %s
            GROUP BY b.category, b.amount, b.period
            """,
            (current_month, user_id),
        )
        rows = cursor.fetchall()
        cursor.close()

    progress = []
    for row in rows:
        budget_amount = float(row['budget'])
        spent = float(row['spent'])
        percentage = (spent / budget_amount) * 100 if budget_amount > 0 else 0
        progress.append({
            'category': row['category'],
            'budget': budget_amount,
            'spent': spent,
            'percentage': round(percentage, 1),
        })

    return jsonify(progress)


# ---------------- APP START ----------------
if __name__ == "__main__":
    init_db()
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 6969)),
        debug=os.environ.get("FLASK_DEBUG", "").lower() in {"1", "true", "yes"},
    )
