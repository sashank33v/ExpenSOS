import sqlite3

DB_NAME = "expenses.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Users table for authentication
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        email TEXT UNIQUE,
        mobile TEXT UNIQUE,
        password_hash TEXT,
        otp TEXT,
        otp_expiry TEXT,
        is_verified INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """)

    # User settings table (theme, currency, language, font_size)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        currency TEXT DEFAULT '₹',
        theme TEXT DEFAULT 'dark',
        language TEXT DEFAULT 'en',
        font_size TEXT DEFAULT 'medium',
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """)

    # Expenses table with new columns
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,
        amount REAL NOT NULL,
        category TEXT NOT NULL,
        note TEXT,
        date TEXT NOT NULL,
        receipt_path TEXT,
        is_recurring INTEGER DEFAULT 0,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """)

    # Budgets table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS budgets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,
        category TEXT NOT NULL,
        amount REAL NOT NULL,
        period TEXT DEFAULT 'monthly',
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """)

    # Recurring expenses table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS recurring_expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,
        amount REAL NOT NULL,
        category TEXT NOT NULL,
        note TEXT,
        frequency TEXT NOT NULL,
        next_date TEXT NOT NULL,
        active INTEGER DEFAULT 1,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """)

    # Reminders table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,
        days TEXT NOT NULL,
        time TEXT NOT NULL,
        reminder_count INTEGER NOT NULL DEFAULT 1,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """)

    # Add columns to existing tables if they don't exist (migration)
    try:
        cursor.execute("ALTER TABLE expenses ADD COLUMN user_id INTEGER DEFAULT 1")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE expenses ADD COLUMN receipt_path TEXT")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE expenses ADD COLUMN is_recurring INTEGER DEFAULT 0")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE reminders ADD COLUMN user_id INTEGER DEFAULT 1")
    except:
        pass

    # Add language and font_size columns to user_settings if they don't exist
    try:
        cursor.execute("ALTER TABLE user_settings ADD COLUMN language TEXT DEFAULT 'en'")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE user_settings ADD COLUMN font_size TEXT DEFAULT 'medium'")
    except:
        pass

    # Add mobile and OTP columns to users if they don't exist
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN mobile TEXT UNIQUE")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN otp TEXT")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN otp_expiry TEXT")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN is_verified INTEGER DEFAULT 0")
    except:
        pass

    # Create default user if none exists
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        from werkzeug.security import generate_password_hash
        cursor.execute("""
            INSERT INTO users (username, email, password_hash, created_at)
            VALUES (?, ?, ?, datetime('now'))
        """, ('admin', 'admin@example.com', generate_password_hash('admin123')))
        
        # Create default settings for admin
        cursor.execute("""
            INSERT INTO user_settings (user_id, currency, theme, language, font_size)
            VALUES (1, '₹', 'dark', 'en', 'medium')
        """)

    conn.commit()
    conn.close()


def get_user_settings(user_id):
    """Get user settings (currency, theme)"""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    settings = cursor.execute(
        "SELECT * FROM user_settings WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    
    if settings:
        return dict(settings)
    return {'currency': '₹', 'theme': 'dark', 'language': 'en', 'font_size': 'medium'}

