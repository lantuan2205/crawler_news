from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time
import re
import unicodedata

# ----------------------------- #
# 1. Slugify: Chuyển tên thành slug
# ----------------------------- #
def slugify(text):
    text = unicodedata.normalize('NFD', text)
    text = text.encode('ascii', 'ignore').decode('utf-8')
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[\s\-]+", "-", text).strip("-")
    return text

# ----------------------------- #
# 2. Khởi tạo trình duyệt
# ----------------------------- #
def init_driver():
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()))

# ----------------------------- #
# 3. Lấy menu chuyên mục từ trang chủ
# ----------------------------- #
def get_menu_links(driver):
    driver.get("https://voz.vn/t/my-ong-trump-cam-thay-buon-chuc-ong-biden-chua-tri-ung-thu-nhanh-hoi-phuc.1101906/")
    time.sleep(10)
    menu_links = driver.find_elements(By.CSS_SELECTOR, "div.c-menu ul li a")

    menu_dict = {}
    for link in menu_links:
        name = link.text.strip()
        href = link.get_attribute("href")
        if name and href and "congly.vn" in href:
            slug = slugify(name)
            menu_dict[slug] = href
    return menu_dict

# ----------------------------- #
# 4. Ghi bài viết ra file (tránh trùng)
# ----------------------------- #
def save_articles(articles, seen_links, file_path="articles.txt"):
    with open(file_path, "a", encoding="utf-8") as file:
        for article in articles:
            title = article.text.strip()
            link = article.get_attribute("href")
            if title and link and link not in seen_links:
                file.write(f"- {title}: {link}\n")
                seen_links.add(link)

# ----------------------------- #
# 5. Lấy toàn bộ bài viết của chuyên mục (bao gồm "Xem thêm")
# ----------------------------- #
def crawl_category(driver, url):
    print(f"🔗 Đang xử lý chuyên mục: {url}")
    driver.get(url)
    time.sleep(2)

    seen_links = set()
    ul_element = driver.find_element(By.CSS_SELECTOR, "ul.onecms__loading")

    while True:
        # Lấy các bài viết hiện tại
        articles = ul_element.find_elements(By.CSS_SELECTOR, "h3.b-grid__title a")
        save_articles(articles, seen_links)

        # Thử click nút "Xem thêm"
        try:
            load_more_button = driver.find_element(By.CSS_SELECTOR, "div.c-more.onecms__loadmore a")
            if load_more_button.is_displayed():
                load_more_button.click()
                print("🔄 Đã click 'Xem thêm'")
                time.sleep(3)
            else:
                break
        except Exception:
            print("✅ Không còn 'Xem thêm' hoặc gặp lỗi.")
            break

# ----------------------------- #
# 6. Hàm chính
# ----------------------------- #
def main():
    driver = init_driver()
    try:
        menu_dict = get_menu_links(driver)

        # Chỉ lấy chuyên mục đầu tiên để thử
        first_slug, first_url = next(iter(menu_dict.items()))
        print(f"🗂️ Chuyên mục đầu tiên: {first_slug.upper()} -> {first_url}")
        crawl_category(driver, first_url)

    finally:
        driver.quit()
        print("✅ Đã hoàn tất và đóng trình duyệt.")

# ----------------------------- #
# 7. Chạy chương trình
# ----------------------------- #
if __name__ == "__main__":
    main()
