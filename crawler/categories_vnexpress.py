import requests
import json
from bs4 import BeautifulSoup

def get_categories():
    base_url = "https://vnexpress.net"
    response = requests.get(base_url, headers={"User-Agent": "Mozilla/5.0"})

    if response.status_code != 200:
        print("Lỗi khi truy cập VnExpress:", response.status_code)
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    # Lấy danh sách chuyên mục từ menu chính
    categories = soup.select("nav a[href^='/']")
    result = {}

    for category in categories:
        name = category.text.strip()
        link = category["href"]

        if name and link:
            full_link = base_url + link if not link.startswith("http") else link
            result[name] = full_link

    # Thêm chuyên mục "Thư giãn" nếu nó không xuất hiện trong menu
    if "Thư giãn" not in result:
        thu_gian_url = base_url + "/thu-gian"  # Thử URL mặc định
        test_response = requests.get(thu_gian_url, headers={"User-Agent": "Mozilla/5.0"})

        if test_response.status_code == 200:
            result["Thư giãn"] = thu_gian_url

    return [{"name": name, "url": url} for name, url in result.items()]

# Chạy thử
categories = get_categories()

# Lưu file JSON

json_fpath = "../result-vnexpress/categories.json"
with open(json_fpath, "w", encoding="utf-8") as json_file:
    json.dump(categories, json_file, ensure_ascii=False, indent=4)

print(f"Dữ liệu đã được lưu vào {json_fpath}")



