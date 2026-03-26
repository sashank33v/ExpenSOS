import os
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "frontend"))
template_root = os.path.join(FRONTEND_DIR, 'templates')

for root, _, files in os.walk(template_root):
    for file in files:
        if file.endswith('.html'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                
            def add_size(match):
                svg_tag = match.group(0)
                if 'class="' in svg_tag:
                    if 'w-' not in svg_tag and 'h-' not in svg_tag:
                        return svg_tag.replace('class="', 'class="w-5 h-5 ')
                elif "class='" in svg_tag:
                    if 'w-' not in svg_tag and 'h-' not in svg_tag:
                        return svg_tag.replace("class='", "class='w-5 h-5 ")
                elif 'class=' not in svg_tag:
                    return svg_tag.replace('<svg', '<svg class="w-5 h-5"')
                return svg_tag
                
            new_content = re.sub(r'<svg[^>]*>', add_size, content)
            
            if new_content != content:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f'Fixed SVGs in: {filepath}')
