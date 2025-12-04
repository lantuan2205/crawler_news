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

        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--remote-debugging-port=9222")
        chrome_options.add_argument("--disable-images")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-popup-blocking")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--blink-settings=imagesEnabled=false")
        chrome_options.set_capability("pageLoadStrategy", "eager")

        return webdriver.Chrome(options=chrome_options)

    def __enter__(self):
        if self.driver is None:
            self.driver = self._init_driver()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close_driver()

    def close_driver(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                print(f"[!] Error quitting driver: {e}")
            finally:
                self.driver = None

    def __del__(self):
        """Fallback: tự động đóng driver khi object bị hủy"""
        self.close_driver()

    def _is_html_useful(self, html: str) -> bool:
        lower = html.lower()
        if len(lower) < 800:
            return False
        if any(tag in lower for tag in ["<article", "entry-content", "post-body", "post-title"]):
            return True
        script_count = lower.count("<script")
        p_count = lower.count("<p")
        if script_count > 10 and p_count < 5:
            return False
        return True

    def _scroll_to_bottom(self, max_scrolls=15, pause=0.8):

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

        try:
            if self.driver is None:
                self.driver = self._init_driver()

            self.driver.get(url)
            time.sleep(1.0)

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

                    try:
                        new_h = self.driver.execute_script("return document.body.scrollHeight") or 0
                    except Exception:
                        new_h = 0

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

    def extract_profile_domain(self, url:str):

        soup = self._get_html(self.base_url)
        if not soup:
            print(f"Cannot load homepage: {self.base_url}")
            return ("", "", "", "", "", "", "", "")

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

        profile = self._normalize_profile(profile)

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
        normalized = {}
        for k, v in profile.items():
            if isinstance(v, str):
                v = v.strip()
            if v in ("", None):
                v = None
            normalized[k] = v
        return normalized

    def _clean_email(self, text):
        if not text:
            return None
        match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
        return match.group(0) if match else text.strip()

    def _clean_phone(self, text):
        if not text:
            return None
        match = re.search(r"(\+?\d[\d\-\s]{8,15})", text)
        return match.group(1).strip() if match else text.strip()

    def _pick_news_list_url(self, soup):
        """
        Trả về URL trang danh sách bài (nếu đoán được) hoặc None.

        Cải tiến:
        - Thêm nhiều từ khóa text/href
        - Scoring thông minh hơn
        - Check thêm footer + toàn bộ links fallback
        """
        from urllib.parse import urljoin

        if not soup:
            return None

        # Các từ khóa có thể xuất hiện trong text
        kw_text = [
            "tin tức", "tintuc", "bài viết", "bai viet",
            "chuyên mục", "chuyen muc", "blog", "tin công ty",
            "tin hoạt động", "news", "event", "sự kiện", "tuyển dụng",
        ]

        # Các từ khóa có thể xuất hiện trong URL
        kw_href = [
            "/tin", "/news", "/blog", "/bai-viet", "/chuyen-muc",
            "/category", "/categories", "/posts", "/post",
            "/event", "/su-kien", "/tuyen-dung","/tin-tuc",
            "/cam-nang-nha-nong","/tin-tuc-moi-nhat", "/webinar",
        ]

        # Khu vực quan trọng: menu/navigation
        zones = [
            "nav a[href]", "header a[href]",
            ".navbar a[href]", ".navigation a[href]"
        ]

        best = None
        best_score = -1

        def _score(a):
            text = (a.get_text(" ", strip=True) or "").lower()
            href = (a.get("href") or "").strip().lower()
            score = 0

            # Bỏ qua các link vô nghĩa
            if href.startswith("javascript") or href.startswith("#") \
            or href.startswith("tel:") or href.startswith("mailto:"):
                return -1

            # Từ khóa trong text
            for k in kw_text:
                if k in text:
                    score += 4

            # Từ khóa trong href
            for k in kw_href:
                if k in href:
                    score += 3

            # Link kiểu "/path"
            if href.startswith("/"):
                score += 1
            
            # URL ngắn → thường là category
            if len(href) <= 50:
                score += 1

            return score

        # Ưu tiên quét menu / header
        for sel in zones:
            for a in soup.select(sel):
                href = a.get("href")
                if not href:
                    continue

                sc = _score(a)
                if sc > best_score:
                    best_score = sc
                    best = href

            if best_score >= 4:  # tìm được ứng viên đủ mạnh
                break

        # FALLBACK: nếu vẫn chưa thấy → scan toàn bộ link
        if best_score < 4:
            for a in soup.select("a[href]"):
                href = a.get("href")
                if not href:
                    continue
                sc = _score(a)
                if sc > best_score:
                    best_score = sc
                    best = href

        return urljoin(self.base_url, best) if best and best_score >= 3 else None

    def _resolve_next_url(self, soup, current_url, next_selectors):
        # CHỈ dùng selector trong template (yêu cầu của bạn)
        for sel in (next_selectors or []):
            try:
                el = soup.select_one(sel)
            except Exception as e:
                continue
            if not el:
                continue
            href = el.get("href")
            if href:
                return urljoin(current_url, href)
        return None

    def _is_article_link(self, url):
        """Detect link bài viết dựa trên pattern WordPress phổ biến."""
        WP_URL_PATTERNS = [
            r"/20\d{2}/\d{1,2}/\d{1,2}/",
            r"/20\d{2}/\d{1,2}/",
            r"/category/[^/]+/[^/]+",
            r"/tag/[^/]+/[^/]+",
            r"/post[s]?/",
            r"/bai-viet/",
            r"/tin-tuc/",
            r"/news/",
            r"/bai-viet-[\w-]+"
        ]

        for pat in WP_URL_PATTERNS:
            if re.search(pat, url):
                return True
        return False


    def _load_sitemap(self):
        """Crawl sitemap từ 3 nguồn phổ biến của WordPress."""
        sitemap_urls = [
            urljoin(self.base_url, "/wp-sitemap.xml"),
            urljoin(self.base_url, "/sitemap_index.xml"),
            urljoin(self.base_url, "/sitemap.xml"),
        ]

        links = []
        for sm in sitemap_urls:
            try:
                r = self.session.get(sm, timeout=5)
                if r.status_code != 200: continue

                soup = BeautifulSoup(r.text, "xml")
                for loc in soup.find_all("loc"):
                    url = loc.get_text(strip=True)
                    if self._is_article_link(url):
                        links.append(url)
            except:
                pass

        return list(set(links))

    def get_article_links(self, max_pages=5):
        

        tpl = self.template.get("article_list", {}) or {}
        selectors = tpl.get("articleUrl", []) or []
        next_selectors = tpl.get("nextPage", []) or []
        collected = set()

        # ------------------------------------------------------------
        # CRAWLER CORE
        # ------------------------------------------------------------
        def crawl_list(start_url):
            """Crawl 1 list page với phân trang"""
            seen = set()
            cur = start_url

            for page in range(max_pages):
                if cur in seen:
                    break
                seen.add(cur)

                is_wp = self._is_wp_com(cur)
                soup = self._get_html(cur, scroll=is_wp)
                if not soup:
                    break

                before = len(collected)
                links = self._extract_all(soup, selectors, attr="href")
                if not links:
                    
                    break

                collected.update(links)

                # tìm nextPage từ template
                nxt = self._resolve_next_url(soup, cur, next_selectors)

                # WP.com special: scroll xong URL nhảy sang /page/N/
                if not nxt and is_wp and self.driver:
                    after = self.driver.current_url
                    if after != cur and re.search(r"/page/\d+/?$", after):
                        nxt = after

                if not nxt:
                    break

                cur = nxt
                time.sleep(1.0)

        # ------------------------------------------------------------
        # PHASE 1 — Crawl homepage hoặc list page đoán được
        # ------------------------------------------------------------
        home_soup = self._get_html(self.base_url)
        start_url = self.base_url

        has_home_links = False
        if home_soup:
            has_home_links = bool(
                self._extract_all(home_soup, selectors, attr="href", base_url=self.base_url)
            )

        if not has_home_links:
            guess = None
            if home_soup:
                guess = self._pick_news_list_url(home_soup)
            elif self.driver:
                guess = self._pick_news_list_url(
                    BeautifulSoup(self.driver.page_source, "html.parser")
                )

            if guess:
                start_url = guess

        crawl_list(start_url)

        # ------------------------------------------------------------
        # PHASE 2 — Crawl list page "tin tức" riêng nếu có
        # ------------------------------------------------------------
        news_url = None
        if home_soup:
            news_url = self._pick_news_list_url(home_soup)

        if news_url and news_url.rstrip("/") != self.base_url.rstrip("/"):
            
            before = len(collected)
            crawl_list(news_url)
            if len(collected) == before:
                print("[AUTO] News list added 0 links → stop early.")

        def _extract_categories(soup):
            cats = set()
            if not soup:
                return cats

            for a in soup.select("a[href]"):
                href = a.get("href", "")
                if "/category/" in href:
                    full = urljoin(self.base_url, href)
                    if not full.endswith("/"):
                        full += "/"
                    cats.add(full)

            return cats

        categories = set()
        try:
            categories.update(_extract_categories(home_soup))
        except:
            pass

        # detect thêm từ start_url page
        try:
            if start_url and start_url != self.base_url:
                page_soup = self._get_html(start_url)
                categories.update(_extract_categories(page_soup))
        except:
            pass

        # loại base_url
        categories = {
            re.sub(r'/page/\d+/?$', '', urljoin(self.base_url, c).rstrip('/'))
            for c in categories
            if c and re.sub(r'/page/\d+/?$', '', urljoin(self.base_url, c).rstrip('/')) != self.base_url.rstrip('/')
        }

        # Crawl từng category
        for cat in categories:
            before = len(collected)
            crawl_list(cat)
            break

        try:
            soup = self._get_html(self.base_url)
            if soup:
                for a in soup.select("a[href]"):
                    href = urljoin(self.base_url, a.get("href", ""))
                    if self._is_article_link(href):
                        collected.add(href)
        except:
            pass

        try:
            for art in soup.select("article a[href]"):
                collected.add(urljoin(self.base_url, art.get("href")))
        except:
            pass

        for i in range(2, max_pages):
            url = urljoin(self.base_url, f"page/{i}/")
            soup = self._get_html(url)
            if not soup:
                break

            links = self._extract_all(soup, selectors, attr="href")
            if not links:
                break

            collected.update(links)

        print(f"✅ Total {len(collected)} article URLs found.")
        return list(collected)

    def extract_content(self, article_url, has_video):
        try:
            soup = self._get_html(article_url)
            if not soup:
                return None

            tpl = self.template.get("article_data", {}) or {}
            published_date= self._extract_first(soup, tpl.get("publishedDate", [])) or None
            title = self._extract_first(soup, tpl.get("title", [])) or None
            description= self._extract_first(soup, tpl.get("description", [])) or None
            content= self._extract_first(soup, tpl.get("content", [])) or None
            published_date = normalize_tuple_date(published_date) if published_date else None
            author= self._extract_first(soup, tpl.get("author", [])) or None
            content_image_urls = self._extract_all(soup, tpl.get("contentImageUrls", []), attr="src") or []
            categories_list = self._extract_all(soup, tpl.get("categories", [])) or []
            categories = ", ".join(categories_list)
            video_url = self._extract_first(soup, tpl.get("videoUrl", [])) or None
            thumbnail_url= self._extract_first(soup, tpl.get("thumbnailUrl", [])) or None
            location= self._extract_first(soup, tpl.get("location", [])) or None

            data = {
                "title": title,
                "description": description,
                "content": content,
                "published_date": published_date,
                "author": author,
                "content_image_urls": content_image_urls,
                "categories": categories,
                "video_url": video_url,
                "thumbnail_url": thumbnail_url,
                "location": location,
            }

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

