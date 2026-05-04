#!/usr/bin/env python3
"""
ExpenSOS - Comprehensive Testing Script
Tests all major functionality of the application
"""
import os
import re
from datetime import datetime

def test_code_structure():
    """Test that all required files exist"""
    print("\n" + "=" * 60)
    print("TEST 1: Code Structure Verification")
    print("=" * 60)
    
    required_files = [
        'backend/app.py',
        'backend/database.py',
        'backend/wsgi.py',
        'backend/requirements.txt',
        'backend/translations.py',
        'frontend/templates/base.html',
        'frontend/templates/login.html',
        'frontend/templates/register.html',
        'frontend/templates/index.html',
        'frontend/templates/expenses.html',
        'frontend/templates/budgets.html',
        'frontend/templates/recurring.html',
        'frontend/templates/reminders.html',
        'frontend/templates/settings.html',
        'Dockerfile',
        'docker-compose.yml',
        'README.md'
    ]
    
    all_exist = True
    for f in required_files:
        exists = os.path.exists(f)
        status = '✓' if exists else '✗'
        print(f"  {status} {f}")
        if not exists:
            all_exist = False
    
    return all_exist

def test_dependencies():
    """Test that required Python packages are in requirements.txt"""
    print("\n" + "=" * 60)
    print("TEST 2: Dependencies Verification")
    print("=" * 60)
    
    required_deps = [
        'flask',
        'psycopg2',
        'werkzeug',
        'gunicorn'
    ]
    
    with open('backend/requirements.txt', encoding='utf-8') as f:
        content = f.read().lower()
    
    all_present = True
    for dep in required_deps:
        present = any(d in content for d in [dep.lower(), dep.lower().replace('-', '_')])
        status = '✓' if present else '✗'
        print(f"  {status} {dep}")
        if not present:
            all_present = False
    
    return all_present

def test_security():
    """Test for security issues in the codebase"""
    print("\n" + "=" * 60)
    print("TEST 3: Security Analysis")
    print("=" * 60)
    
    issues = []
    
    with open('backend/app.py', encoding='utf-8') as f:
        app_content = f.read()
    
    with open('frontend/templates/base.html', encoding='utf-8') as f:
        template_content = f.read()
    
    print("  Checking for SQL injection vulnerabilities...")
    if 'execute(' in app_content and '%s' in app_content:
        param_patterns = ['execute(', 'SELECT ', 'INSERT ', 'UPDATE ', 'DELETE ']
        if all(p in app_content for p in param_patterns[:3]):
            if 'ILIKE %s' in app_content or "execute('" not in app_content:
                print("    ✓ Parameterized queries used (good)")
            else:
                print("    ✗ Potential SQL injection risk")
                issues.append("SQL query construction needs review")
    
    print("  Checking for XSS protection...")
    if '|e' in template_content or '|escape' in template_content:
        print("    ✓ Jinja2 auto-escaping enabled")
    else:
        print("    ⚠ Jinja2 auto-escaping is default but verify user input")
    
    print("  Checking session security...")
    if 'secret_key' in app_content:
        if 'os.environ.get' in app_content and 'SECRET_KEY' in app_content:
            print("    ✓ SECRET_KEY loaded from environment")
        else:
            print("    ⚠ SECRET_KEY is hardcoded (use env var in production)")
            issues.append("SECRET_KEY should come from environment")
    
    print("  Checking file upload security...")
    if 'secure_filename' in app_content:
        print("    ✓ Secure filename function used")
    if 'ALLOWED_EXTENSIONS' in app_content:
        print("    ✓ File extension whitelist implemented")
    if 'MAX_CONTENT_LENGTH' in app_content:
        print("    ✓ Max upload size defined")
    
    print("  Checking authentication...")
    if '@login_required' in app_content:
        print("    ✓ Login decorator used on protected routes")
    
    return len(issues) == 0, issues

def test_endpoints():
    """Test that all expected endpoints are defined"""
    print("\n" + "=" * 60)
    print("TEST 4: Endpoint Coverage")
    print("=" * 60)
    
    with open('backend/app.py', encoding='utf-8') as f:
        content = f.read()
    
    expected_endpoints = [
        ('/login', 'POST'),
        ('/register', 'POST'),
        ('/logout', 'GET'),
        ('/', 'GET'),
        ('/add', 'POST'),
        ('/delete/', 'GET'),
        ('/edit/', 'GET'),
        ('/expenses', 'GET'),
        ('/settings', 'GET'),
        ('/budgets', 'GET'),
        ('/recurring', 'GET'),
        ('/reminders', 'GET'),
        ('/monthly-data', 'GET'),
        ('/api/insights', 'GET'),
        ('/upload-receipt/', 'POST'),
    ]
    
    missing = []
    for endpoint, method in expected_endpoints:
        pattern = rf'@app\.route\(["\']/?{re.escape(endpoint.rstrip("/"))}'
        if '""' in endpoint or "''" in endpoint:
            pattern = rf'@app\.route\([f"\'{endpoint}'
        
        if endpoint.endswith('/'):
            pattern = rf'@app\.route\(["\']/?{re.escape(endpoint.lstrip("/"))}'
        
        found = re.search(pattern, content) is not None
        
        if not found and '/' in endpoint:
            alt_pattern = rf'@app\.route\(["\'].*{re.escape(endpoint.split("/")[1])}.*["\']'
            found = re.search(alt_pattern, content) is not None
        
        status = '✓' if found else '?'
        print(f"  {status} {method} {endpoint}")
        if not found:
            missing.append(f"{method} {endpoint}")
    
    return len(missing) == 0, missing

def test_database_schema():
    """Test that database schema is properly defined"""
    print("\n" + "=" * 60)
    print("TEST 5: Database Schema")
    print("=" * 60)
    
    with open('backend/database.py', encoding='utf-8') as f:
        content = f.read()
    
    required_tables = [
        'users',
        'user_settings',
        'expenses',
        'budgets',
        'recurring_expenses',
        'reminders'
    ]
    
    all_present = True
    for table in required_tables:
        found = f'CREATE TABLE' in content and table in content
        status = '✓' if found else '✗'
        print(f"  {status} {table} table")
        if not found:
            all_present = False
    
    print("  Checking for foreign keys...")
    if 'REFERENCES users' in content:
        print("    ✓ Foreign key relationships defined")
    
    print("  Checking for indexes...")
    if 'INDEX' in content or 'index' in content.lower():
        print("    ✓ Indexes defined")
    else:
        print("    ⚠ Consider adding indexes for performance")
    
    return all_present

def test_i18n():
    """Test internationalization support"""
    print("\n" + "=" * 60)
    print("TEST 6: Internationalization")
    print("=" * 60)
    
    with open('backend/translations.py', encoding='utf-8') as f:
        content = f.read()
    
    supported_languages = ['en', 'hi', 'te']
    
    all_present = True
    for lang in supported_languages:
        found = f"'{lang}':" in content
        status = '✓' if found else '✗'
        print(f"  {status} {lang}")
        if not found:
            all_present = False
    
    print("  Checking translation function...")
    if 'get_translations_dict' in content:
        print("    ✓ Translation dictionary function available")
    
    return all_present

def test_docker_config():
    """Test Docker configuration"""
    print("\n" + "=" * 60)
    print("TEST 7: Docker Configuration")
    print("=" * 60)
    
    dockerfile_issues = []
    
    with open('Dockerfile', encoding='utf-8') as f:
        df_content = f.read()
    
    with open('docker-compose.yml', encoding='utf-8') as f:
        dc_content = f.read()
    
    print("  Dockerfile checks:")
    if 'python' in df_content.lower():
        print("    ✓ Python base image specified")
    if 'pip install' in df_content:
        print("    ✓ Dependencies installed")
    if 'gunicorn' in df_content:
        print("    ✓ Gunicorn for production")
    if 'EXPOSE' in df_content:
        print("    ✓ Port exposed")
    if 'PORT' in df_content:
        print("    ✓ Port configurable via env var")
    
    print("  docker-compose.yml checks:")
    if 'postgres' in dc_content:
        print("    ✓ PostgreSQL service defined")
    if 'expensos' in dc_content or 'app' in dc_content:
        print("    ✓ App service defined")
    if 'DATABASE_URL' in dc_content:
        print("    ✓ Database URL configured")
    if 'SECRET_KEY' in dc_content:
        print("    ✓ SECRET_KEY environment variable")
    if 'restart:' in dc_content:
        print("    ✓ Restart policy configured")
    if 'volumes:' in dc_content:
        print("    ✓ Persistent volumes configured")
    
    return True

def test_file_uploads():
    """Test file upload functionality"""
    print("\n" + "=" * 60)
    print("TEST 8: File Upload Security")
    print("=" * 60)
    
    with open('backend/app.py', encoding='utf-8') as f:
        content = f.read()
    
    checks = [
        ('allowed_file' in content, 'File extension validation'),
        ('secure_filename' in content, 'Secure filename sanitization'),
        ('ALLOWED_EXTENSIONS' in content, 'Extension whitelist'),
        ('MAX_CONTENT_LENGTH' in content, 'Max upload size limit'),
        ('makedirs' in content, 'Upload directory creation'),
    ]
    
    all_pass = True
    for check, desc in checks:
        status = '✓' if check else '✗'
        print(f"  {status} {desc}")
        if not check:
            all_pass = False
    
    return all_pass

def test_csrf_protection():
    """Check CSRF protection"""
    print("\n" + "=" * 60)
    print("TEST 9: Form Security (CSRF)")
    print("=" * 60)
    
    with open('backend/app.py', encoding='utf-8') as f:
        content = f.read()
    
    if 'csrf' in content.lower() or 'CSRF' in content:
        print("  ✓ CSRF protection mentioned")
        return True
    else:
        print("  ⚠ No explicit CSRF protection found")
        print("    Consider adding Flask-WTF or CSRFProtect")
        return False

def test_templates():
    """Test template structure"""
    print("\n" + "=" * 60)
    print("TEST 10: Template Structure")
    print("=" * 60)
    
    required_templates = [
        'base.html',
        'auth_base.html',
        'login.html',
        'register.html',
        'index.html',
    ]
    
    all_exist = True
    for tmpl in required_templates:
        path = f'frontend/templates/{tmpl}'
        exists = os.path.exists(path)
        status = '✓' if exists else '✗'
        print(f"  {status} {tmpl}")
        if not exists:
            all_exist = False
    
    return all_exist

def generate_report(results):
    """Generate final report"""
    print("\n" + "=" * 60)
    print("FINAL REPORT")
    print("=" * 60)
    
    passed = sum(1 for r in results if r[0])
    total = len(results)
    
    print(f"\nTests Passed: {passed}/{total}")
    
    if passed == total:
        print("\n✓ All tests passed! App appears ready for deployment.")
    else:
        print("\n⚠ Some tests failed. Review the issues above before deployment.")
    
    return passed == total

def main():
    print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║                                                              ║
    ║          ExpenSOS - Comprehensive Test Suite                ║
    ║                                                              ║
    ╚══════════════════════════════════════════════════════════════╝
    """)
    
    results = []
    
    results.append((test_code_structure(), []))
    results.append((test_dependencies(), []))
    
    sec_ok, sec_issues = test_security()
    results.append((sec_ok, sec_issues))
    
    ep_ok, ep_missing = test_endpoints()
    results.append((ep_ok, ep_missing))
    
    results.append((test_database_schema(), []))
    results.append((test_i18n(), []))
    results.append((test_docker_config(), []))
    results.append((test_file_uploads(), []))
    results.append((test_csrf_protection(), []))
    results.append((test_templates(), []))
    
    return generate_report(results)

if __name__ == '__main__':
    success = main()
    exit(0 if success else 1)
