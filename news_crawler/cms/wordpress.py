import requests , os
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import json
import uuid
import time, html
from selenium.webdriver.chrome.options import Options
from selenium import webdriver
import re, json
from utils.service_utils import save_to_json, normalize_tuple_date
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from urllib.parse import urljoin, urlparse

class WordPressCrawler:
    def __init__(self, input_data, proxy_session=None, template_path="./config/wordpress_template.json", driver=None):
        """
        input_data: dict chứa ít nhất 'url' website cần crawl
        proxy_session: requests.Session (nếu có proxy)
        template_path: file json mapping selector
        """
        self.base_url = input_data
        self.driver = driver
        self.job_id = input_data
        self.session = proxy_session or requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/119.0.0.0 Safari/537.36"
        })
        base_dir = os.path.dirname(os.path.abspath(__file__))
        template_full_path = os.path.join(base_dir, template_path)

        with open(template_full_path, "r", encoding="utf-8") as f:
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

        # if self.proxy_session:
        #     options.add_argument(f"--proxy-server={self.proxy_session}")
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
    def _scroll_to_bottom(self, max_scrolls=15, pause=0.8):
        """Kéo xuống đáy trang để load thêm nội dung (infinite/lazy)."""
        if not self.driver:
            return
        stable = 0
        last_h = 0
        for _ in range(max_scrolls):
            try:
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            except Exception:
                break
            time.sleep(pause)
            try:
                new_h = self.driver.execute_script("return document.body.scrollHeight") or 0
            except Exception:
                break
            if new_h <= last_h:
                stable += 1
                if stable >= 2:
                    break
            else:
                stable = 0
            last_h = new_h
    def _is_wp_com(self, url: str) -> bool:
        try:
            host = urlparse(url).netloc.lower()
            return host.endswith(".wordpress.com")
        except Exception:
            return False
        
    def _get_html(self, url, scroll=False, link_selectors=None,
                max_scrolls=20, pause=0.8, stable_rounds=2):
        """
        Trả về BeautifulSoup của trang hiện tại.
        - scroll=True: kéo xuống cho tới khi KHÔNG còn link mới (dựa trên link_selectors) 
        hoặc chiều cao trang không tăng trong 'stable_rounds' lần, hoặc chạm 'max_scrolls'.
        - link_selectors: list CSS selectors của các thẻ link bài để đếm số lượng.
        """
        print(f"[*] Falling back to Selenium for: {url}")
        try:
            if self.driver is None:
                self.driver = self._init_driver()

            self.driver.get(url)
            time.sleep(1.0)  # cho JS/HTML khởi tạo

            if scroll:
                link_selectors = link_selectors or []
                last_count = -1
                last_h = 0
                stable = 0

                for _ in range(max_scrolls):
                    # Đếm tổng số link hiện có (nếu cung cấp selector)
                    cur_count = 0
                    for sel in link_selectors:
                        try:
                            cur_count += len(self.driver.find_elements(By.CSS_SELECTOR, sel))
                        except Exception:
                            # selector lỗi thì bỏ qua, không dừng vòng lặp
                            pass

                    # Scroll xuống đáy
                    try:
                        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    except Exception:
                        break

                    time.sleep(pause)

                    # Lấy chiều cao mới
                    try:
                        new_h = self.driver.execute_script("return document.body.scrollHeight") or 0
                    except Exception:
                        new_h = 0

                    # Kiểm tra có “tăng” (số link hoặc chiều cao)
                    grew = (cur_count > last_count) or (new_h > last_h)
                    if not grew:
                        stable += 1
                        if stable >= stable_rounds:
                            break
                    else:
                        stable = 0

                    last_count = max(last_count, cur_count)
                    last_h = max(last_h, new_h)

            html = self.driver.page_source
            if self._is_html_useful(html):
                return BeautifulSoup(html, "html.parser")
            print(f"[!] Selenium HTML vẫn thiếu nội dung: {url}")
        except Exception as e:
            print(f"[x] Selenium failed: {url} ({e})")
        return None


    def _extract_first(self, soup, selectors):
        from soupsieve.util import SelectorSyntaxError
        for sel in (selectors or []):
            if not sel or not isinstance(sel, str):
                continue
            sel = sel.strip()
            if not sel or sel.startswith(','):
                continue
            try:
                el = soup.select_one(sel)
            except SelectorSyntaxError as e:
                print(f"[SEL] bad selector {repr(sel)} → {e}", flush=True)
                continue
            if not el:
                continue

            # ✅ Ưu tiên: nếu là <a href="mailto:..."> → lấy phần sau "mailto:"
            if el.name == "a":
                href = (el.get("href") or "").strip()
                if href.lower().startswith("mailto:"):
                    # trả về địa chỉ email, bỏ query nếu có (?subject=…)
                    return href.split(":", 1)[1].split("?", 1)[0]

            # Sau đó mới fallback: lấy text
            txt = el.get_text(" ", strip=True)
            if txt:
                return txt

            # Cuối cùng: thử các thuộc tính phổ biến
            for attr in ("content","datetime","src","href","value",
                        "data-src","data-lazy-src","data-original"):
                v = el.get(attr)
                if not v:
                    continue
                v = v.replace("\xa0"," ").strip()
                if attr in ("src","href","data-src","data-lazy-src","data-original"):
                    # (tuỳ chọn) bỏ base64 và chuẩn hoá tuyệt đối
                    if v.lower().startswith("data:"):
                        continue
                    v = urljoin(self.base_url, v)
                if v:
                    return v

        return ""

    def _extract_all(self, soup, selectors, attr=None, base_url=None):
        base = base_url or self.base_url
        urls = set()
        for sel in selectors or []:
            for el in soup.select(sel):
                if attr:
                    link = el.get(attr)
                    if link:
                        urls.add(urljoin(base, link))
                else:
                    text = el.get_text(strip=True)
                    if text:
                        urls.add(text)
        return list(urls)


    # -----------------------------
    # 1️⃣ Lấy thông tin profile
    # -----------------------------
    def extract_profile_domain(self, url:str):
        print(f"📰 Crawling profile: {self.base_url}")

        soup = self._get_html(self.base_url)
        if not soup:
            return {"error": f"Cannot load homepage: {self.base_url}"}

        profile_tpl = self.template.get("profile", {})
        profile = {
            "name": self._extract_first(soup, profile_tpl.get("name", [])) or self.base_url,
            "description": self._extract_first(soup, profile_tpl.get("description", [])) or "",
            "license": self._extract_first(soup, profile_tpl.get("license", [])) or "",
            "editor_in_chief": self._extract_first(soup, profile_tpl.get("editor_in_chief", [])) or "",
            "address": self._extract_first(soup, profile_tpl.get("address", [])) or "",
            "phone": self._clean_phone(self._extract_first(soup, profile_tpl.get("phone", []))) or "",
            "email": self._clean_email(self._extract_first(soup, profile_tpl.get("email", []))) or "",
            "infor_copyright": self._extract_first(soup, profile_tpl.get("infor_copyright", [])) or "",
            "jobId": self.job_id,
            "logo": self._extract_first(soup, profile_tpl.get("logo", [])) or "",
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
        return (
            profile.get("license", ""),
            profile.get("description", ""),
            profile.get("editor_in_chief", ""),
            profile.get("address", ""), 
            profile.get("phone", ""),
            profile.get("email", ""),
            profile.get("infor_copyright", ""),
            profile.get("logo", "")
        )
    def _normalize_profile(self, profile):
        """Chuẩn hóa dữ liệu profile: loại bỏ None, strip chuỗi."""
        normalized = {}
        for k, v in profile.items():
            if isinstance(v, str):
                v = v.strip()
            if v in ("", None):
                v = None
            normalized[k] = v
        return normalized

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

    def _pick_news_list_url(self, soup):
        """
        Trả về URL trang danh sách bài (nếu đoán được) hoặc None.
        Quét menu/header/footer để tìm các link có text/href gợi ý 'tin tức', 'news', 'blog', 'category'...
        """
        from urllib.parse import urljoin

        if not soup:
            return None

        # Từ khóa “text” & trong “href”
        kw_text = [
            "tin tức", "tintuc", "bài viết", "bai viet", "chuyên mục", "chuyen muc",
            "webinar", "blog"
        ]
        kw_href = [
            "/tin-tuc", "/webinar", "/blog", "/bai-viet", "/chuyen-muc"
        ]

        zones = [
            "nav a[href]", ".menu a[href]", "header a[href]",
        ]

        best = None
        best_score = -1

        def _score(a):
            text = (a.get_text(" ", strip=True) or "").lower()
            href  = (a.get("href") or "").strip().lower()
            s = 0
            if any(k in text for k in kw_text): s += 3   # text khớp → điểm cao
            if any(k in href for k in kw_href): s += 2   # slug khớp → thêm điểm
            # Ưu tiên link ngắn & không ra ngoài domain
            if href.startswith("/"): s += 1
            if len(href) <= 40: s += 1
            return s

        for sel in zones:
            for a in soup.select(sel):
                href = a.get("href")
                if not href: 
                    continue
                sc = _score(a)
                if sc > best_score:
                    best_score = sc
                    best = href

            if best_score >= 3:  # đã tìm được ứng viên “đủ tốt”
                break

        return urljoin(self.base_url, best) if best and best_score >= 3 else None

    # -----------------------------
    # 2️⃣ Lấy danh sách URL bài viết
    # -----------------------------
    

    def _resolve_next_url(self, soup, current_url, next_selectors):
        # CHỈ dùng selector trong template (yêu cầu của bạn)
        for sel in (next_selectors or []):
            try:
                el = soup.select_one(sel)
            except Exception as e:
                print(f"[SEL] bad nextPage selector {repr(sel)} → {e}", flush=True)
                continue
            if not el:
                continue
            href = el.get("href")
            if href:
                return urljoin(current_url, href)
        return None


    def get_article_links(self, max_pages=5):
        print(f"🧩 Collecting article URLs from: {self.base_url}")
        tpl = self.template.get("article_list", {}) or {}
        selectors = tpl.get("articleUrl", []) or []
        next_selectors = tpl.get("nextPage", []) or []
        collected = set()

        def crawl_list(start_url):
            seen = set()
            cur = start_url
            for page in range(max_pages):
                if cur in seen: break
                seen.add(cur)

                is_wp = self._is_wp_com(cur)
                soup = self._get_html(cur, scroll=is_wp)
                if not soup: break

                before = len(collected)
                links = self._extract_all(soup, selectors, attr="href")
                if not links:
                    print(f"[!] Page {page+1} ({cur}) returned 0 links → stop.")
                    break
                collected.update(links)
                print(f"  ➜ Page {page+1}: +{len(collected)-before} new links (total {len(collected)})")

                nxt = self._resolve_next_url(soup, cur, next_selectors)

                # WP.com: sau scroll, nếu URL đã nhảy /page/N thì dùng luôn
                if not nxt and is_wp and self.driver:
                    after = self.driver.current_url
                    if after != cur and re.search(r"/page/\d+/?$", after):
                        nxt = after

                if not nxt:
                    break
                cur = nxt
                time.sleep(1.0)

        # Phase 1: luôn thử từ homepage (hoặc list page đoán được nếu home không có link)
        home_soup = self._get_html(self.base_url)
        start_url = self.base_url
        if home_soup:
            has_home_links = bool(self._extract_all(
                home_soup, (self.template.get("article_list", {}) or {}).get("articleUrl", []) or [],
                attr="href", base_url=self.base_url
            ))
            if not has_home_links:
                guess = self._pick_news_list_url(home_soup)
                if guess:
                    start_url = guess
                    print(f"[AUTO] Discovered list page: {start_url}")

        crawl_list(start_url)

        # Phase 2: Nếu có trang 'tin tức' riêng & khác homepage → crawl tiếp
        if home_soup:
            news_url = self._pick_news_list_url(home_soup)
            if news_url and news_url.rstrip("/").lower() != self.base_url.rstrip("/").lower():
                print(f"[AUTO] Also crawl list page: {news_url}")
                before = len(collected)
                crawl_list(news_url)
                if len(collected) == before:
                    print("[AUTO] News list added 0 links → stop early.")

        print(f"✅ Total {len(collected)} article URLs found.")
        return list(collected)

    # -----------------------------
    # 3️⃣ Crawl nội dung từng bài
    # -----------------------------
    def extract_content(self, article_url, has_video):
        try:
            soup = self._get_html(article_url)
            if not soup:
                return None

            tpl = self.template.get("article_data", {}) or {}
            published_date= self._extract_first(soup, tpl.get("publishedDate", [])) or None
            print("---------publish_date-----------", published_date) 
            title = self._extract_first(soup, tpl.get("title", [])) or None
            description= self._extract_first(soup, tpl.get("description", [])) or None
            content= self._extract_first(soup, tpl.get("content", [])) or None
            published_date = normalize_tuple_date(published_date) if published_date else None
            author= self._extract_first(soup, tpl.get("author", [])) or None
            content_image_urls= self._extract_all(soup, ["div.et_pb_row_1_tb_body img","div.entry-content img","div.post-content img", "div.entrytext img","div.entry img"], attr="src") or []
            categories= self._extract_all(soup, tpl.get("categories", [])) or []
            video_url = self._extract_first(soup, tpl.get("videoUrl", [])) or None
            thumbnail_url= self._extract_first(soup, tpl.get("thumbnailUrl", [])) or None
            location= self._extract_first(soup, tpl.get("location", [])) or None

            return (
                title,
                description,
                content,
                published_date,
                author,
                content_image_urls,
                categories,
                video_url,
                thumbnail_url,
                location,
            )
        except Exception as e:
            print(f"❌ Lỗi khi trích xuất bài viết: {e}")
            return None

