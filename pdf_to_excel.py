#!/usr/bin/env python3
"""
PDF to Excel converter for Rivelle Tampines Price List.
Robust parser with OCR correction. Uses DPI=200 for speed.
"""

import pytesseract
from pdf2image import convert_from_path
import pandas as pd
import re
import os
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

PDF_PATH = "/Users/denghuiyao/Volumes/itfs/DHOC Win/share_file.pdf"
OUTPUT_PATH = "/Users/denghuiyao/Volumes/itfs/DHOC Win/share_file.xlsx"

VALID_BLOCKS = {'51', '53', '55', '57', '59', '61', '63', '65', '67', '69', '71'}
VALID_AREAS = {883, 926, 1044, 1109, 1184, 1292, 1378}

BLOCK_CORRECTIONS = {
    # 51
    'si': '51', 'sr': '51', 's1': '51', 'st': '51', 'sl': '51', '81': '51',
    'Ts': '51', 'Tei': '51', 'csi': '51', 'rst': '51',
    '(1': '51',
    # 53
    's3': '53', 'S3': '53', 'sa': '53', 'Sa': '53',
    'rsa': '53', 'Rsa': '53', '"sa': '53', 'fs3': '53', '"3': '53',
    '(sa': '53', '[sa': '53', 'sa]': '53',
    # 55
    'ss': '55', 'S5': '55', 'rss': '55', 'Rss': '55', 'P55': '55', 'p55': '55',
    'Pss': '55', 'pss': '55', 'r55': '55', 'R55': '55', 'RSS': '55',
    'ps5': '55', '(s5': '55', '(s5|': '55',
    # 57
    's7': '57', 'S7': '57', '87': '57',
    # 59
    's9': '59', 'S9': '59', 'so': '59', 'So': '59', 'SO': '59',
    'Tse': '59', 'tse': '59', 'Tso': '59', 'tso': '59',
    '§9': '59', 's9{': '59', '(so': '59', '"se': '59', '"so': '59',
    # 61
    'ei': '61', 'E1': '61', '6i': '61',
    # 63
    'e3': '63', 'E3': '63',
    # 65
    'e5': '65', 'E5': '65', 'es': '65', 'Es': '65', 'eS': '65',
    '6s': '65', '05': '65', 'os': '65',
    # 67
    'e7': '67', 'E7': '67', 'ez': '67', 'Ez': '67', 'er': '67', 'Er': '67',
    'rer': '67', 'Rer': '67', 'rev': '67', 'Rev': '67', 're7': '67',
    'Ter': '67', 'ter': '67', 'fev': '67', 'Fev': '67',
    'ev': '67', 'Ev': '67', '[e7': '67', '(67': '67', '(e7': '67',
    'ret': '67', 'Ret': '67', 'rei': '67', 'Rei': '67', 'rel': '67',
    # 69
    'eo': '69', 'e0': '69', 'Eo': '69', 'eg': '69', 'E0': '69',
    'res': '69', 'Res': '69', 'rea': '69', 'Rea': '69',
    'pes': '69', 'Pes': '69', 'Fes': '69', 'fes': '69',
    'Tes': '69', 'tes': '69', '"es': '69', '"ea': '69',
    '(es': '69', 'rea]': '69', 'res]': '69',
    'peo': '69', 'Peo': '69', 'reo': '69', 'Reo': '69',
    'feo': '69', 'Feo': '69', 'reg': '69', 'Reg': '69',
    'peg': '69', 'Peg': '69', 'oo': '69', '(9': '69',
    'mea': '69', 'Mea': '69', 'poo': '69', 'Tea': '69',
    '(oo': '69', '(eo': '69', 'rex': '69', 'Rex': '69',
    'rex]': '69', 'res]': '69', '"ea': '69',
    'ea': '69', 'Ea': '69', '"ea': '69',  # e→6, a→9
    # 71
    'ri': '71', 'r1': '71', 'Ti': '71', 'T1': '71', 'Tl': '71',
    'R1': '71', 'Ri': '71', 'P71': '71', 'p71': '71',
    'rma': '71', 'Rma': '71', 'rm': '71', 'Rm': '71',
    'rai': '71', 'Rai': '71', 'ral': '71',
    'fm': '71', 'Fm': '71', 'Tm': '71', 'tm': '71',
    'mi': '71', 'Mi': '71', '7': '71',
    '[7': '71', '(7': '71',
    # Single digit ambiguous
    '5': '65',  # "5" alone most likely 65
}

UNIT_TYPE_MAP = {
    'C2S': 'C2S', 'c2s': 'C2S', 'C2s': 'C2S', 'c28': 'C2S', 'C28': 'C2S',
    '2s': 'C2S', '2S': 'C2S', 'ozs': 'C2S', 'C2S(p)': 'C2S(p)',
    'C1P': 'C1P', 'c1p': 'C1P', 'CIP': 'C1P', 'Cip': 'C1P', 'clp': 'C1P',
    'CIP(P)': 'C1P(p)', 'C1P(P)': 'C1P(p)', 'C1P(p)': 'C1P(p)',
    'C1P(p)': 'C1P(p)', 'C1Pp': 'C1P(p)', 'C1P(P)': 'C1P(p)',
    'D1': 'D1', 'd1': 'D1', 'Di': 'D1', 'D1(p)': 'D1(p)', 'D1(P)': 'D1(p)',
    'D2S': 'D2S', 'd2s': 'D2S', 'D28': 'D2S', 'O2S': 'D2S', '02S': 'D2S', 'D2s': 'D2S',
    'D3F': 'D3F', 'DSF': 'D3F', 'D3f': 'D3F',
    'D4P': 'D4P', 'DAP': 'D4P', 'DaP': 'D4P', 'D4p': 'D4P', 'dap': 'D4P', 'oap': 'D4P',
    'E1': 'E1', 'El': 'E1',
}


def parse_line(line):
    """Parse a single OCR line into a data row"""
    line = line.strip().strip('"').strip("'").strip()
    if not line:
        return None
    
    lower = line.lower()
    if any(skip in lower for skip in [
        'rivelle', 'price list', 'march', 'block', 'unit no',
        'bedroom type', 'unit type', 'area', 'normal', 'deferred', 'scheme'
    ]):
        return None
    
    # Normalize price separators: replace . with , in price patterns like "$1,787.000"
    line_price = re.sub(r'(\d),(\d{3})\.(\d{3})', r'\1,\2,\3', line)
    # Also handle "$1.787.000" pattern
    line_price = re.sub(r'\$(\d)[.](\d{3})[.](\d{3})', r'$\1,\2,\3', line_price)
    # Handle [ used as separator in prices like "$2,295,000 [$2,062,000]" → treat [ as |
    line_price = line_price.replace('[', ' ').replace(']', ' ')
    
    # Find prices
    prices = re.findall(r'\$?([\d,]{7,})', line_price)
    price_values = []
    for p in prices:
        val = int(p.replace(',', ''))
        if 1000000 <= val <= 5000000:
            price_values.append(val)
    
    # Also try to find prices with missing first digit like "$,965,000"
    if len(price_values) < 2:
        alt_prices = re.findall(r'\$,?(\d{3},\d{3})', line_price)
        for ap in alt_prices:
            val = int(ap.replace(',', ''))
            if 500000 <= val <= 999999:
                price_values.append(val + 1000000)
    
    # Try prices as 6-digit like "$205,000" → could be truncated $2,050,000
    if len(price_values) < 2:
        alt_prices2 = re.findall(r'\$(\d{3},\d{3})', line_price)
        for ap in alt_prices2:
            val = int(ap.replace(',', ''))
            if 100000 <= val <= 999999:
                # Try multiplying by 10 to get 7-digit
                val10 = val * 10
                if 1000000 <= val10 <= 5000000:
                    price_values.append(val10)
    
    # Try prices where any 7-digit number appears
    if len(price_values) < 2:
        all_nums = re.findall(r'(\d{1,2}[,.]?\d{3}[,.]?\d{3})', line_price)
        for n in all_nums:
            val = int(re.sub(r'[,.]', '', n))
            if 1000000 <= val <= 5000000 and val not in price_values:
                price_values.append(val)
    
    if len(price_values) < 2:
        return None
    
    # Sanity check: deferred should be >= normal (or very close)
    normal_payment = price_values[-2]
    deferred_payment = price_values[-1]
    
    # If deferred < normal by a lot, prices might be swapped or OCR error
    if deferred_payment < normal_payment * 0.9:
        # Try swapping
        normal_payment, deferred_payment = deferred_payment, normal_payment
    
    # Fix obvious OCR first-digit errors in prices
    # e.g., $3,748,000 should be $1,748,000 or $4,714,000 → $1,714,000
    if normal_payment > 3000000:
        # First digit likely wrong, try replacing with 1 or 2
        s = str(normal_payment)
        for d in ['1', '2']:
            alt = int(d + s[1:])
            if 1000000 <= alt <= 3000000:
                normal_payment = alt
                break
    if deferred_payment > 3500000:
        s = str(deferred_payment)
        for d in ['1', '2']:
            alt = int(d + s[1:])
            if 1000000 <= alt <= 3500000:
                deferred_payment = alt
                break
    
    # Find unit number
    unit_no = None
    # Pattern 1: clean XX-XX
    m = re.search(r'(\d{2})[-](\d{2})', line)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if 1 <= a <= 14 and 1 <= b <= 50:
            unit_no = f"{m.group(1)}-{m.group(2)}"
    # Pattern 2: XX:XX (colon instead of dash)
    if not unit_no:
        m = re.search(r'(\d{2})[:](\d{2})', line)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if 1 <= a <= 14 and 1 <= b <= 50:
                unit_no = f"{m.group(1)}-{m.group(2)}"
    # Pattern 3: XX-XX with ) instead of -
    if not unit_no:
        m = re.search(r'(\d{2})[)]\s*(\d{2})', line)
        if m:
            unit_no = f"{m.group(1)}-{m.group(2)}"
    # Pattern 4: XXXX (4 consecutive digits representing unit number like 0312, 0516)
    if not unit_no:
        for m in re.finditer(r'(?<!\d)(\d{4})(?!\d)', line):
            val = m.group(1)
            first, second = int(val[:2]), int(val[2:])
            if 1 <= first <= 14 and 1 <= second <= 50:
                unit_no = f"{val[:2]}-{val[2:]}"
                break
            # Floor 15-19: OCR might have misread first digit (1→1 but 5→9 wrong)
            # e.g., "1912" → try "09-12" 
            if 15 <= first <= 19 and 1 <= second <= 50:
                alt_first = int('0' + val[1])
                if 1 <= alt_first <= 14:
                    unit_no = f"0{val[1]}-{val[2:]}"
                    break
            # Floor == 0 or > 14: try "00-XX" scenario
            if first == 0 and len(val) == 4:
                alt = val[1:]
                if len(alt) == 3:
                    f2, s1 = int(alt[:2]), int(alt[2])
                    if 1 <= f2 <= 14:
                        unit_no = f"{alt[:2]}-0{alt[2]}"
                        break
            # "1200" pattern: last 2 digits are "00" which is invalid
            # Could be "12-30" or "12-20" etc — too ambiguous, try "12-00" → skip
            # But "1200" is likely floor 12, unit might be garbled
    # Pattern 4b: XXXXX (5 consecutive digits like "10501" → "10-01" or "05-01")
    if not unit_no:
        for m in re.finditer(r'(?<!\d)(\d{5})(?!\d)', line):
            val = m.group(1)
            # Try splitting as XX-XX with extra digit
            # Could be "10" + "50" + "1" → but more likely "10" + "01" with "5" as noise
            # Or first 2 + last 2 digits
            first2, last2 = int(val[:2]), int(val[3:])
            if 1 <= first2 <= 14 and 1 <= last2 <= 50:
                unit_no = f"{val[:2]}-{val[3:]}"
                break
            # Try splitting as first 2 + middle 2
            mid2 = int(val[1:3])
            last2b = int(val[3:])
            if 1 <= mid2 <= 14 and 1 <= last2b <= 50:
                unit_no = f"{val[1:3]}-{val[3:]}"
                break
    # Pattern 4b: Handle 3-digit unit numbers and other edge cases
    if not unit_no:
        parts = re.split(r'[\s|(\["\'}]+', line[:30])
        for p in parts:
            p = p.strip(')]}|')
            # 3-digit: could be XX-0Y (like "102"→"10-02") or X-YZ
            if re.match(r'^\d{3}$', p):
                d = p
                # Try as first2 + "0" + last1 → XX-0Y  
                first2, last1 = int(d[:2]), int(d[2])
                if 1 <= first2 <= 14 and 1 <= last1 <= 9:
                    unit_no = f"{d[:2]}-0{d[2]}"
                    break
                # Try as first1 + last2 → 0X-YZ
                first1, last2 = int(d[0]), int(d[1:])
                if 1 <= first1 <= 9 and 1 <= last2 <= 50:
                    unit_no = f"0{d[0]}-{d[1:]}"
                    break
            # "04s" → translate s→5 → "045" → "04-05"
            if re.match(r'^[\da-zA-Z]{3}$', p):
                trans = str.maketrans('oOiIlLtTsSaAeEnN', '0011117755440011')
                translated = p.translate(trans)
                digits = re.sub(r'[^0-9]', '', translated)
                if len(digits) == 3:
                    first2, last1 = int(digits[:2]), int(digits[2])
                    if 1 <= first2 <= 14 and 1 <= last1 <= 9:
                        unit_no = f"{digits[:2]}-0{digits[2]}"
                        break
    # Pattern 5: OCR letter→digit confusion in unit numbers (e.g., "osa2"→"0542", "o7t2"→"0712")
    if not unit_no:
        parts = re.split(r'[\s|(\["\'}]+', line)
        # For unit numbers, t→1 (not 7), s→5 or s→8 context dependent
        trans_unit = str.maketrans('oOiIlLtTsSaAeEnN', '0011111155440011')
        for p in parts:
            p = p.strip(')]}|')
            if 3 <= len(p) <= 6 and any(c.isalpha() for c in p):
                translated = p.translate(trans_unit)
                digits_only = re.sub(r'[^0-9]', '', translated)
                if len(digits_only) == 4:
                    first, second = int(digits_only[:2]), int(digits_only[2:])
                    if 1 <= first <= 14 and 1 <= second <= 50:
                        unit_no = f"{digits_only[:2]}-{digits_only[2:]}"
                        break
                    # If first=0, skip first digit and try remaining 3 digits as X-YZ
                    if first == 0 and len(digits_only) >= 3:
                        first1 = int(digits_only[1])
                        second2 = int(digits_only[2:])
                        if 1 <= first1 <= 9 and 1 <= second2 <= 50:
                            unit_no = f"0{digits_only[1]}-{digits_only[2:]}"
                            break
                elif len(digits_only) == 5:
                    first2, last2 = int(digits_only[:2]), int(digits_only[3:])
                    if 1 <= first2 <= 14 and 1 <= last2 <= 50:
                        unit_no = f"{digits_only[:2]}-{digits_only[3:]}"
                        break
                elif len(digits_only) == 3:
                    first2, last1 = int(digits_only[:2]), int(digits_only[2])
                    if 1 <= first2 <= 14 and 1 <= last1 <= 9:
                        unit_no = f"{digits_only[:2]}-0{digits_only[2]}"
                        break
    
    # Pattern 6: Handle pure alpha tokens that look like unit nums with aggressive translation
    if not unit_no:
        parts = re.split(r'[\s|(\["\'}]+', line[:40])
        for p in parts:
            p = p.strip(')]}|').lower()
            # "ise" could be "15-0" etc — too unreliable, skip very short ones
            if len(p) < 4:
                continue
            # Map: a→4, b→8, c→0, d→0, e→0, g→9, h→4, n→1, o→0, r→1, s→5, t→1, z→2
            aggressive_trans = str.maketrans(
                'abcdeghnorstz',
                '4800091105152'
            )
            translated = p.translate(aggressive_trans)
            digits_only = re.sub(r'[^0-9]', '', translated)
            if len(digits_only) == 4:
                first, second = int(digits_only[:2]), int(digits_only[2:])
                if 1 <= first <= 14 and 1 <= second <= 50:
                    unit_no = f"{digits_only[:2]}-{digits_only[2:]}"
                    break
    
    if not unit_no:
        return None
    
    # Find block number
    block = find_block(line, unit_no)
    if not block:
        return None
    
    # Find area
    area = None
    
    # Known OCR area misreads
    AREA_CORRECTIONS = {
        '178': 1378, '1978': 1378, '1378': 1378, '(1978': 1378, '(178': 1378,
        '1878': 1378, '17e': 1378, '178e': 1378,
        '1278': 1292, '1282': 1292, '1202': 1292,
        '18a': 1184, '184': 1184, '1484': 1184, 'tea': 1184, 'tae': 1184,
        'nea': 1184, 'aea': 1184, '118a': 1184, 'ttea': 1184, 'tlea': 1184,
        '11ea': 1184, 't184': 1184, 'tt84': 1184, '1lea': 1184,
        't044': 1044, 'toaa': 1044, 'toad': 1044, 'toa4': 1044, '104a': 1044,
        'some': 1044, 'soaa': 1044, '10aa': 1044, '1oaa': 1044, 'lo44': 1044,
        '2044': 1044, '3044': 1044, '204a': 1044,
        '04a': 1044, '044': 1044, 'oaa': 1044,
        'e83': 883, '8a3': 883, '083': 883, 'eas': 883, 'ea3': 883,
        '983': 883, 'aaa': 883, 'aa': 883, '88a': 883, 'eaa': 883,
        'sea': 926, '92e': 926, '826': 926, '9a6': 926, '026': 926,
        'ex': None, 'EX': None,  # will handle below
        't109': 1109, 'tl09': 1109, 'tt09': 1109, '1l09': 1109,
    }
    
    # First, try direct 3-4 digit match
    for m in re.finditer(r'(\d{3,4})', line):
        val = int(m.group(1))
        if val in VALID_AREAS:
            area = val
            break
    if not area:
        # Try to snap close values to known areas
        for m in re.finditer(r'(\d{3,4})', line):
            val = int(m.group(1))
            if 800 <= val <= 1500:
                best = min(VALID_AREAS, key=lambda a: abs(a - val))
                if abs(best - val) <= 50:
                    area = best
                    break
    if not area:
        # Try known OCR corrections by looking at tokens
        parts = re.split(r'[\s|]+', line)
        for p in parts:
            p_clean = p.strip('_—-()[]{}\'\"~|,+').lower()
            if p_clean in AREA_CORRECTIONS:
                area = AREA_CORRECTIONS[p_clean]
                break
            # Also try letter→digit translation
            trans = str.maketrans('oOiIlLtTsSaAeE', '00111177554400')
            translated = p_clean.translate(trans)
            digits = re.sub(r'[^0-9]', '', translated)
            if len(digits) in [3, 4]:
                val = int(digits)
                if val in VALID_AREAS:
                    area = val
                    break
                if 800 <= val <= 1500:
                    best = min(VALID_AREAS, key=lambda a: abs(a - val))
                    if abs(best - val) <= 80:  # Increased tolerance
                        area = best
                        break
    if not area:
        # Handle 2-digit area fragments like "83" → 883
        for m in re.finditer(r'(?<!\d)(\d{2})(?!\d)', line):
            val = int(m.group(1))
            for va in VALID_AREAS:
                va_str = str(va)
                if va_str.endswith(str(val).zfill(2)):
                    area = va
                    break
            if area:
                break
    if not area:
        # Last resort: infer area from price range
        # Price ranges per area (approximate):
        # 883 (3BR Prem): $1.5M-$1.75M
        # 926 (3BR Prem+Study): $1.6M-$1.9M
        # 1044 (4BR): $1.9M-$2.1M
        # 1109 (4BR+Study): $2.0M-$2.2M
        # 1184 (4BR Prem): $2.1M-$2.4M
        # 1292 (5BR): $2.4M-$2.6M
        # 1378 (5BR): $2.5M-$2.8M
        if len(price_values) >= 2:
            avg_price = (price_values[-2] + price_values[-1]) / 2
            if avg_price < 1750000:
                area = 883
            elif avg_price < 1950000:
                area = 926
            elif avg_price < 2100000:
                area = 1044
            elif avg_price < 2250000:
                area = 1109
            elif avg_price < 2500000:
                area = 1184
            elif avg_price < 2650000:
                area = 1292
            else:
                area = 1378
    if not area:
        return None
    
    # Bedroom type
    bedroom_type = identify_bedroom_type(line, area)
    if not bedroom_type:
        return None
    
    # Unit type
    unit_type = identify_unit_type(line, area)
    
    return {
        'Block': block, 'Unit No.': unit_no, 'Bedroom Type': bedroom_type,
        'Unit Type': unit_type or '', 'Area (Sqft)': area,
        'Normal Payment Scheme': normal_payment, 'Deferred Payment Scheme': deferred_payment,
    }


def find_block(line, unit_no):
    """Find block number from line"""
    # Get text before unit number
    unit_idx = line.find(unit_no[:2])
    if unit_idx < 0:
        unit_idx = 15
    prefix = line[:min(unit_idx + 3, 25)]
    
    # Clean prefix - split by whitespace and pipe only (keep parens/brackets as part of token)
    tokens = re.split(r'[\s|,]+', prefix)
    tokens = [t.strip() for t in tokens if t.strip()]
    
    for t in tokens:
        # Try various cleanings of the token
        variants = [
            t,
            t.strip(')]}{}'),
            t.lstrip('"\'([{§"'),
            re.sub(r'[{}\[\]()]+$', '', t),
            re.sub(r'^[{}\[\]()]+', '', re.sub(r'[{}\[\]()]+$', '', t)),
        ]
        
        for v in variants:
            if not v:
                continue
            # Direct match
            if v in VALID_BLOCKS:
                return v
            # Correction
            if v in BLOCK_CORRECTIONS:
                return BLOCK_CORRECTIONS[v]
            if v.lower() in BLOCK_CORRECTIONS:
                return BLOCK_CORRECTIONS[v.lower()]
        
        # Pure digits
        digits = re.sub(r'[^0-9]', '', t)
        if digits in VALID_BLOCKS:
            return digits
    
    # Last resort: try the entire prefix for any known correction
    prefix_clean = re.sub(r'[\s|,]+', '', prefix[:15])
    for key in sorted(BLOCK_CORRECTIONS.keys(), key=len, reverse=True):
        if key in prefix_clean or key.lower() in prefix_clean.lower():
            return BLOCK_CORRECTIONS[key]
    
    return None


def identify_bedroom_type(line, area=None):
    """Identify bedroom type"""
    normalized = re.sub(r'[_—\-\s|.]+', '', line).lower()
    
    # Order matters: check more specific patterns first
    if '5bed' in normalized or '5bedroom' in normalized:
        return '5 Bedroom'
    if re.search(r'3.*prem.*stud', normalized) or re.search(r's.*prem.*stud', normalized):
        return '3 Bedroom Premium + Study'
    if re.search(r'3.*premium', normalized) or re.search(r's.*premium', normalized):
        return '3 Bedroom Premium'
    if re.search(r'4.*prem', normalized):
        return '4 Bedroom Premium'
    if re.search(r'4.*flex', normalized):
        return '4 Bedroom Flexi'
    if re.search(r'4.*stud', normalized):
        return '4 Bedroom + Study'
    if re.search(r'4.*bed', normalized):
        return '4 Bedroom'
    if re.search(r'[3s].*bed', normalized):
        return '3 Bedroom Premium + Study'  # Most 3-bed are this type
    
    # Page 4 pattern: just "Bedroom" (for 5 Bedroom with area 1378)
    if 'bed' in normalized.lower() or 'room' in normalized.lower():
        # Infer from area
        if area == 1378:
            return '5 Bedroom'
        if area == 926:
            return '3 Bedroom Premium + Study'
        if area == 883:
            return '3 Bedroom Premium'
        if area == 1044:
            return '4 Bedroom'
        if area == 1109:
            return '4 Bedroom + Study'
        if area == 1184:
            return '4 Bedroom Premium'
        return '4 Bedroom'
    
    # Last resort: infer purely from area
    if area:
        area_bedroom_map = {
            926: '3 Bedroom Premium + Study',
            883: '3 Bedroom Premium',
            1044: '4 Bedroom',
            1109: '4 Bedroom + Study',
            1184: '4 Bedroom Premium',
            1378: '5 Bedroom',
            1292: '5 Bedroom',
        }
        if area in area_bedroom_map:
            return area_bedroom_map[area]
    
    return None


def identify_unit_type(line, area):
    """Identify unit type from line"""
    # Split by pipe and check each part
    parts = re.split(r'[|]', line)
    for part in parts:
        clean = re.sub(r'[_—\-\s]+', '', part).strip()
        if clean in UNIT_TYPE_MAP:
            return UNIT_TYPE_MAP[clean]
        if clean.upper() in UNIT_TYPE_MAP:
            return UNIT_TYPE_MAP[clean.upper()]
        # Try lowercase
        if clean.lower() in UNIT_TYPE_MAP:
            return UNIT_TYPE_MAP[clean.lower()]
    
    # Regex search
    for m in re.finditer(r'([CcDdEeOo0][\d][A-Za-z]?(?:\([pP]\))?)', line):
        candidate = m.group(1)
        for key, val in UNIT_TYPE_MAP.items():
            if candidate.lower() == key.lower():
                return val
    
    # Infer from area  
    area_type_map = {926: 'C2S', 883: 'C1P', 1044: 'D1', 1109: 'D2S', 1184: 'D4P', 1292: 'E1', 1378: 'E1'}
    return area_type_map.get(area, '')


def main():
    print(f"正在读取 PDF: {PDF_PATH}")
    
    # Use DPI=200 for faster processing
    print("正在将 PDF 转换为图片 (DPI=200)...")
    images = convert_from_path(PDF_PATH, dpi=200)
    print(f"共 {len(images)} 页\n")
    
    all_rows = []
    total_failed = 0
    
    for i, img in enumerate(images):
        page_num = i + 1
        text = pytesseract.image_to_string(img, lang='eng', config='--psm 6')
        
        page_rows = []
        page_failed = 0
        page_failed_lines = []
        
        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue
            # Quick check: only process lines with price patterns
            if not re.search(r'\$[\d,.]{7,}', line):
                continue
            
            row = parse_line(line)
            if row:
                page_rows.append(row)
            else:
                page_failed += 1
                page_failed_lines.append(line[:100])
        
        print(f"第 {page_num:2d} 页: 提取 {len(page_rows):3d} 行, 失败 {page_failed:2d} 行")
        if page_failed_lines:
            for fl in page_failed_lines:
                print(f"    FAIL: [{fl}]")
        all_rows.extend(page_rows)
        total_failed += page_failed
    
    if not all_rows:
        print("\n❌ 未能提取任何数据")
        return
    
    df = pd.DataFrame(all_rows)
    df = df.sort_values(['Block', 'Unit No.']).reset_index(drop=True)
    
    before = len(df)
    df = df.drop_duplicates(subset=['Block', 'Unit No.'], keep='first').reset_index(drop=True)
    after = len(df)
    if before > after:
        print(f"\n移除了 {before - after} 条重复数据")
    
    print(f"\n总计 {len(df)} 行数据 (失败 {total_failed} 行)")
    
    print(f"\nBedroom Type:")
    print(df['Bedroom Type'].value_counts().to_string())
    print(f"\nUnit Type:")
    print(df['Unit Type'].value_counts().to_string())
    print(f"\nBlock:")
    print(df['Block'].value_counts().sort_index().to_string())
    print(f"\nArea:")
    print(df['Area (Sqft)'].value_counts().sort_index().to_string())
    
    # Save to Excel
    with pd.ExcelWriter(OUTPUT_PATH, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Price List', index=False)
        ws = writer.sheets['Price List']
        for col, w in {'A': 8, 'B': 10, 'C': 30, 'D': 12, 'E': 12, 'F': 22, 'G': 22}.items():
            ws.column_dimensions[col].width = w
        for row in range(2, len(df) + 2):
            for col in [6, 7]:
                ws.cell(row=row, column=col).number_format = '$#,##0'
    
    print(f"\n✅ Excel 已保存: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
