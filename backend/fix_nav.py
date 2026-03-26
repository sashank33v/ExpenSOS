import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "frontend"))
TARGET = os.path.join(FRONTEND_DIR, 'templates', 'base.html')

with open(TARGET, 'r', encoding='utf-8') as f:
    html = f.read()

# Replace all occurrences of class="nav-link with class="nav-link group
# The templates have exact formats: class="nav-link {% if ...
html = html.replace('class="nav-link ', 'class="nav-link group ')

with open(TARGET, 'w', encoding='utf-8') as f:
    f.write(html)

print("Fixed nav links")
