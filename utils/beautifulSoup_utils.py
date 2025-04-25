import requests
import re

from bs4 import BeautifulSoup, NavigableString


def get_text_from_tag(tag):
    if isinstance(tag, NavigableString):
        return tag
    return tag.text

def extract_author_from_strong_tags(soup):
    strong_tags = soup.select("p > strong")
    possible_authors = []

    for tag in strong_tags:
        text = tag.get_text(strip=True)
        if is_author_strong_tag(text):
            possible_authors.append(clean_prefix(text))

    # Ưu tiên tag cuối cùng trong bài viết (thường là tác giả thật)
    return possible_authors[-1] if possible_authors else None


def clean_prefix(text):
    if ':' in text:
        parts = text.split(':', 1)
        if parts[0].strip().upper() in ['TIN, ẢNH', 'TIN', 'ẢNH']:
            return parts[1].strip()
    return text.strip()

def is_author_strong_tag(text):
    text = clean_prefix(text)

    # Loại trừ các tag vô nghĩa
    if text.strip() in ['', ':', 'PV', 'PV:', '–', '—']:
        return False

    # Loại trừ các cụm không phải tác giả
    if any(kw in text.upper() for kw in ['GIÁ VÀNG', 'GIÁ DẦU', 'BẢN CHẤT', 'DIỄN']):
        return False

    # Match kiểu toàn chữ hoa + số lượng từ hợp lý
    if re.match(r'^[A-ZÀ-Ỵ0-9\- ()]+$', text.strip()) and len(text.split()) <= 6:
        return True

    # Cho phép tên người dài, có học hàm, chức danh
    if 3 <= len(text.split()) <= 10 and not text.isupper():
        return True

    return False

