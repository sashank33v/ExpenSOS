import os
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "frontend"))

# Match <svg ...>
svg_pattern = re.compile(r'<svg([^>]*)>')

def add_explicit_size(match):
    attrs = match.group(1)
    if 'width=' not in attrs and 'height=' not in attrs:
        return f'<svg{attrs} width="24" height="24">'
    return match.group(0)

template_root = os.path.join(FRONTEND_DIR, 'templates')
for root, _, files in os.walk(template_root):
    for file in files:
        if file.endswith('.html'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            new_content = svg_pattern.sub(add_explicit_size, content)
            if new_content != content:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f'Added explicit size to SVGs in: {filepath}')
