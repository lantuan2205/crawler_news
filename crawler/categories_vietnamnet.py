import requests
from bs4 import BeautifulSoup
import json

# URL trang chủ của Vietnamnet
BASE_URL = "https://vietnamnet.vn/"

def get_main_categories():
    response = requests.get(BASE_URL, headers={"User-Agent": "Mozilla/5.0"})
    if response.status_code != 200:
        print("Không thể truy cập Vietnamnet:", response.status_code)
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    # Tìm danh sách chuyên mục từ menu chính
    menu_section = soup.select_one("nav")  # Tìm thẻ <nav> chứa menu
    if not menu_section:
        print("Không tìm thấy menu chính")
        return []

    categories = menu_section.select("a[href^='/']")  # Tất cả <a> trong <nav>
    
    result = []
    for category in categories:
        name = category.text.strip()
        link = category["href"]

        # Bỏ qua các mục không phải chuyên mục tin tức
        if name.lower() in ["logo htvn", "toàn văn", "english", "đính chính"]:
            continue

        full_link = BASE_URL + link.lstrip("/") if not link.startswith("http") else link
        result.append({"name": name, "url": full_link})

    return result

# Lấy danh sách chuyên mục chính
categories = get_main_categories()

# Ghi ra file JSON
output_file = "../result-vietnamnet/categories.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(categories, f, ensure_ascii=False, indent=4)

print(f"Đã lưu {len(categories)} chuyên mục vào {output_file}")
