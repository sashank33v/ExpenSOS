with open('templates/base.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Replace all occurrences of class="nav-link with class="nav-link group
# The templates have exact formats: class="nav-link {% if ...
html = html.replace('class="nav-link ', 'class="nav-link group ')

with open('templates/base.html', 'w', encoding='utf-8') as f:
    f.write(html)

print("Fixed nav links")
