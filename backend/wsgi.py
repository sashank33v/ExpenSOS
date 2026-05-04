try:
    from .app import app
    from .database import init_db
except ImportError:
    from app import app
    from database import init_db

init_db()

application = app
