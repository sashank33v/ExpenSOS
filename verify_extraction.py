import easyocr
import re
import os

# Copying logic from app.py to avoid complex imports during test
def extract_amount_python(text):
    t = re.sub(r'\b\d{9,}\b', '', text)
    t = t.replace('|', '1').replace('l', '1').replace('O', '0')
    tier1_patterns = [
        r'\bcash\b[\s\S]{0,25}?(?:Rs\.?|INR|₹)?\s*([\d,]+(?:\.\d{1,2})?)\s*\/?-?',
        r'(?:grand\s+total|balance\s+due|amount\s+due|amount\s+payable|net\s+payable|bill\s+total|payable\s+amount)[\s\S]{0,30}?(?:Rs\.?|INR|₹)?\s*([\d,]+(?:\.\d{1,2})?)\s*\/?-?',
        r'(?:net\s+total|total\s+amount|total\s+due|total\s+payable|sub\s*total|total)[\s\S]{0,20}?(?:Rs\.?|INR|₹|\$)?\s*([\d,]+(?:\.\d{1,2})?)\s*\/?-?',
        r'(?:bill\s+amount|invoice\s+amount|bill\s+value)\s*[:\-]?\s*(?:Rs\.?|INR|₹|\$)?\s*([\d,]+(?:\.\d{1,2})?)\s*\/?-?'
    ]
    for pattern in tier1_patterns:
        matches = list(re.finditer(pattern, t, re.IGNORECASE))
        if matches:
            for m in matches:
                raw = m.group(1).replace(',', '')
                try:
                    val = float(raw)
                    if 1 <= val < 1000000: return val
                except: continue
    tier2_matches = re.finditer(r'(?:Rs\.?\s*|₹\s*|INR\s*)([\d,]+(?:\.\d{1,2})?)\s*\/?-?', t, re.IGNORECASE)
    for m in tier2_matches:
        raw = m.group(1).replace(',', '')
        try:
            val = float(raw)
            if 1 <= val < 1000000: return val
        except: continue
    tail = t[int(len(t)*0.6):]
    numbers = re.findall(r'\b(\d{1,6}(?:\.\d{2})?)\s*\/?-?\b', tail)
    if numbers:
        try: return float(numbers[-1].replace(',', ''))
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

def run_test(img_path):
    print(f"Testing on {img_path}...")
    reader = easyocr.Reader(['en'], gpu=False)
    results = reader.readtext(img_path)
    full_text = "\n".join([res[1] for res in results])
    print("OCR RAW TEXT:")
    print("-" * 20)
    print(full_text)
    print("-" * 20)
    
    amt = extract_amount_python(full_text)
    dt = extract_date_python(full_text)
    
    print(f"EXTRACTED AMOUNT: {amt}")
    print(f"EXTRACTED DATE:   {dt}")

if __name__ == "__main__":
    test_img = 'uploads/27_..sk.jpeg'
    if os.path.exists(test_img):
        run_test(test_img)
    else:
        print(f"Test image {test_img} not found.")
