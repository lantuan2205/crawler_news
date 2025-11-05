import os
import requests
import sys
from pathlib import Path
import re, json

import random
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from datetime import datetime, timedelta
import paramiko
from io import BytesIO
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, WebDriverException

import time
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from typing import Optional  


class BloggerCrawler:
    def __init__(self, input_data, jobId, proxy_session=None, template_path="./config/blogspot_template.json", driver=None):
        """
        input_data: dict chứa ít nhất 'url' website cần crawl
        proxy_session: requests.Session (nếu có proxy)
        template_path: file json mapping selector
        """
        self.base_url = input_data
        self.driver = driver
        self.job_id = jobId
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

    def _get_html(self, url):

        # try:
        #     resp = self.session.get(url, headers=self.headers, timeout=15, allow_redirects=True)
        #     html = resp.text
        #     if resp.status_code == 200 and self._is_html_useful(html):
        #         return BeautifulSoup(html, "html.parser")
        #     else:
        #         print(f"[!] HTML không đủ nội dung, fallback Selenium: {url}")
        # except Exception as e:
        #     print(f"[!] Request failed: {url} ({e})")

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
        return ""

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

    def _validate_logo_url(self, value):
        """Kiểm tra nếu logo hợp lệ (ảnh) thì giữ lại, ngược lại trả về chuỗi rỗng."""
        if not value:
            return ""
        value_lower = value.lower()
        # Các đuôi file hợp lệ
        valid_exts = [".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"]
        if any(ext in value_lower for ext in valid_exts):
            return value
        return ""

    def extract_profile_domain(self, url: str):
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
            "logo": self._validate_logo_url(self._extract_first(soup, profile_tpl.get("logo", []))) or "",
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
        profile = {k: (v if isinstance(v, str) else "" if v is None else str(v)) for k, v in profile.items()}
        print("✅ Done profile:", json.dumps(profile, ensure_ascii=False, indent=2))
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

    def _clean_email(self, text):
        """Tách email hợp lệ từ chuỗi."""
        if not text:
            return ""
        match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
        return match.group(0) if match else text.strip()

    def _clean_phone(self, text):
        """Lọc số điện thoại khỏi chuỗi."""
        if not text:
            return ""
        match = re.search(r"(\+?\d[\d\-\s]{8,15})", text)
        return match.group(1).strip() if match else text.strip()

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