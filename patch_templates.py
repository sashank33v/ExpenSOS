import os
import re

def exact_replace(filepath, old, new):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    content = content.replace(old, new)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

# Patch input.css
with open('input.css', 'r', encoding='utf-8') as f:
    input_css = f.read()

auth_styles = """
    .auth-glass-panel {
        @apply bg-white/80 dark:bg-premium-card/90 backdrop-blur-2xl border border-gray-200 dark:border-white/10 rounded-3xl shadow-2xl;
    }
    .auth-glass-input {
        @apply bg-white dark:bg-white/5 border border-gray-200 dark:border-white/10 text-gray-900 dark:text-white rounded-xl focus:ring-2 focus:ring-brand-500 focus:border-transparent focus:outline-none transition-all duration-200 placeholder-gray-400 dark:placeholder-premium-muted px-4 py-3.5 w-full;
    }
    .auth-btn-primary {
        @apply bg-brand-600 hover:bg-brand-500 text-white font-medium rounded-xl px-4 py-3.5 transition-all duration-200 shadow-[0_4px_15px_rgba(6,182,212,0.3)] hover:shadow-[0_8px_25px_rgba(6,182,212,0.4)] hover:-translate-y-0.5 w-full flex justify-center items-center;
    }
"""
if '.auth-glass-panel' not in input_css:
    input_css = input_css.replace('.btn-danger {', auth_styles + '\n    .btn-danger {')
    with open('input.css', 'w', encoding='utf-8') as f:
        f.write(input_css)

# Patch login & register
for tmpl in ['templates/login.html', 'templates/register.html']:
    exact_replace(tmpl, 'glass-panel', 'auth-glass-panel')
    exact_replace(tmpl, 'glass-input', 'auth-glass-input')
    exact_replace(tmpl, 'btn-primary', 'auth-btn-primary')

# Patch base.html & auth_base.html
for filepath in [ 'templates/base.html', 'templates/auth_base.html' ]:
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Remove tailwindcdn script
    content = re.sub(r'<script src="https://cdn\.tailwindcss\.com"></script>\s*', '', content)
    
    # Remove tailwind.config script block
    content = re.sub(r'<script>\s*tailwind\.config = \{.*?\n\s*\}\s*</script>\s*', '', content, flags=re.DOTALL)
    
    # Remove tailwindcss style block
    content = re.sub(r'<style type="text/tailwindcss">.*?</style>\s*', '', content, flags=re.DOTALL)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

print('Patched successfully!')
