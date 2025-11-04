import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import json
import uuid
import time


class WordPressCrawler:
    def __init__(self, input_data, proxy_session=None, template_path="config/wordpress_template.json", driver=None):
        """
        input_data: dict chứa ít nhất 'url' website cần crawl
        proxy_session: requests.Session (nếu có proxy)
        template_path: file json mapping selector
        """
        self.base_url = input_data.get("url")
        self.driver = driver
        self.job_id = input_data.get("jobId", str(uuid.uuid4()))
        self.session = proxy_session or requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/119.0.0.0 Safari/537.36"
        })

        with open(template_path, "r", encoding="utf-8") as f:
            self.template = json.load(f)


    def _init_driver(self):
        """Khởi tạo Selenium driver khi cần"""
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--remote-debugging-port=9222")
        chrome_options.add_argument("--disable-images")
        # chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-popup-blocking")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--blink-settings=imagesEnabled=false")
        chrome_options.set_capability("pageLoadStrategy", "eager")

        if self.proxy_session:
            options.add_argument(f"--proxy-server={self.proxy_session}")
        return webdriver.Chrome(options=chrome_options)

    def _is_html_useful(self, html: str) -> bool:
        """Kiểm tra HTML có chứa nội dung thực không."""
        lower = html.lower()
        if len(lower) < 800:
            return False
        # Có tag bài viết hoặc nội dung chính
        if any(tag in lower for tag in ["<article", "entry-content", "post-body", "post-title"]):
            return True
        # Nếu trang chỉ toàn script (render bằng JS)
        script_count = lower.count("<script")
        p_count = lower.count("<p")
        if script_count > 10 and p_count < 5:
            return False
        # Có chữ hoặc thẻ nội dung hợp lý
        return True
    # -----------------------------
    # Utility
    # -----------------------------
    def _get_html(self, url):
        """
        1️⃣ Thử tải bằng requests.
        2️⃣ Nếu HTML rỗng hoặc không có nội dung thật → fallback qua Selenium.
        """
        try:
            resp = self.session.get(url, headers=self.headers, timeout=15, allow_redirects=True)
            html = resp.text
            if resp.status_code == 200 and self._is_html_useful(html):
                return BeautifulSoup(html, "html.parser")
            else:
                print(f"[!] HTML không đủ nội dung, fallback Selenium: {url}")
        except Exception as e:
            print(f"[!] Request failed: {url} ({e})")

        # --- fallback sang Selenium ---

        print(f"[*] Falling back to Selenium for: {url}")
        try:
            if self.driver is None:
                self.driver = self._init_driver()

            self.driver.get(url)
            time.sleep(2)  # chờ JS render
            html = self.driver.page_source
            if self._is_html_useful(html):
                return BeautifulSoup(html, "html.parser")
            print(f"[!] Selenium HTML vẫn thiếu nội dung: {url}")
        except Exception as e:
            print(f"[x] Selenium failed: {url} ({e})")
        return None

    def _extract_first(self, soup, selectors):
        for sel in selectors:
            el = soup.select_one(sel)
            if el:
                text = el.get_text(strip=True)
                if text:
                    return text
        return None

    def _extract_all(self, soup, selectors, attr=None):
        urls = set()
        for sel in selectors:
            for el in soup.select(sel):
                if attr:
                    link = el.get(attr)
                    if link:
                        urls.add(urljoin(self.base_url, link))
                else:
                    urls.add(el.get_text(strip=True))
        return list(urls)

    # -----------------------------
    # 1️⃣ Lấy thông tin profile
    # -----------------------------
    def get_profile(self):
        print(f"📰 Crawling profile: {self.base_url}")

        soup = self._get_html(self.base_url)
        if not soup:
            return {"error": f"Cannot load homepage: {self.base_url}"}

        profile_tpl = self.template.get("profile", {})
        profile = {
            "name": self._extract_first(soup, profile_tpl.get("name", [])) or self.base_url,
            "description": self._extract_first(soup, profile_tpl.get("description", [])),
            "license": self._extract_first(soup, profile_tpl.get("license", [])),
            "editor_in_chief": self._extract_first(soup, profile_tpl.get("editor_in_chief", [])),
            "address": self._extract_first(soup, profile_tpl.get("address", [])),
            "phone": self._clean_phone(self._extract_first(soup, profile_tpl.get("phone", []))),
            "email": self._clean_email(self._extract_first(soup, profile_tpl.get("email", []))),
            "infor_copyright": self._extract_first(soup, profile_tpl.get("infor_copyright", [])),
            "jobId": self.job_id,
            "logo": self._extract_first(soup, profile_tpl.get("logo", [])),
        }

        # --- fallback: nếu quá nhiều trường trống, thử reload bằng Selenium ---
        missing = sum(1 for v in profile.values() if not v)
        if missing >= 5:
            print("[!] Profile thiếu dữ liệu, thử lại với Selenium...")
            soup = self._get_html(self.base_url)
            if soup:
                for key, sel in profile_tpl.items():
                    if not profile.get(key):
                        profile[key] = self._extract_first(soup, sel)

        # --- Chuẩn hóa dữ liệu ---
        profile = self._normalize_profile(profile)

        print(f"✅ Done profile: {profile.get('name')}")
        return profile


    # ==============================
    # Helper functions
    # ==============================

    def _clean_email(self, text):
        """Tách email hợp lệ từ chuỗi."""
        if not text:
            return None
        match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
        return match.group(0) if match else text.strip()

    def _clean_phone(self, text):
        """Lọc số điện thoại khỏi chuỗi."""
        if not text:
            return None
        match = re.search(r"(\+?\d[\d\-\s]{8,15})", text)
        return match.group(1).strip() if match else text.strip()


    # -----------------------------
    # 2️⃣ Lấy danh sách URL bài viết
    # -----------------------------
    def get_article_links(self, max_pages=5):
        print(f"🧩 Collecting article URLs from: {self.base_url}")
        tpl = self.template.get("article_list", {})
        selectors = tpl.get("articleUrl", [])
        next_selectors = tpl.get("nextPage", [])
        collected = set()

        current_url = self.base_url
        for page in range(max_pages):
            soup = self._get_html(current_url)
            if not soup:
                break

            links = self._extract_all(soup, selectors, attr="href")
            if not links:
                print(f"[!] Page {page + 1} returned no links, stop.")
                break

            collected.update(links)
            print(f"  ➜ Page {page + 1}: {len(links)} links")

            next_url = None
            for sel in next_selectors:
                next_el = soup.select_one(sel)
                if next_el and next_el.get("href"):
                    next_url = urljoin(current_url, next_el.get("href"))
                    break
            if not next_url:
                break
            current_url = next_url
            time.sleep(1.5)

        print(f"✅ Total {len(collected)} article URLs found.")
        return list(collected)

    # -----------------------------
    # 3️⃣ Crawl nội dung từng bài
    # -----------------------------
    def get_article_data(self, article_url):
        soup = self._get_html(article_url)
        if not soup:
            return {"url": article_url, "error": "Cannot load article"}

        tpl = self.template.get("article_data", {})

        article = {
            "dataSource": self.base_url,
            "url": article_url,
            "title": self._extract_first(soup, tpl.get("title", [])),
            "author": self._extract_first(soup, tpl.get("author", [])),
            "publishedDate": self._extract_first(soup, tpl.get("publishedDate", [])),
            "description": self._extract_first(soup, tpl.get("description", [])),
            "content": self._extract_first(soup, tpl.get("content", [])),
            "categories": self._extract_all(soup, tpl.get("categories", [])),
            "contentImageUrls": self._extract_all(soup, ["div.post-body img"], attr="src"),
            "thumbnailUrl": self._extract_first(soup, tpl.get("thumbnailUrl", [])),
            "jobId": self.job_id,
        }

        return article

    # -----------------------------
    # 4️⃣ Run toàn bộ luồng
    # -----------------------------
    def run(self, max_pages=3, limit_articles=10):
        profile = self.get_profile()
        links = self.get_article_links(max_pages=max_pages)
        results = []

        for idx, url in enumerate(links[:limit_articles], start=1):
            print(f"📄 [{idx}/{len(links)}] {url}")
            article = self.get_article_data(url)
            results.append(article)

        return {"profile": profile, "articles": results}
