import requests
import sys
import json
import os
import re
from pathlib import Path
import random
import time
import uuid
from urllib.parse import urljoin
import paramiko
from io import BytesIO
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from bs4 import BeautifulSoup
from utils.service_utils import clean_date, get_urls_of_type
from urllib.parse import urljoin, urlparse

FILE = Path(__file__).resolve()
ROOT = FILE.parents[1]  # root directory
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))  # add ROOT to PATH

from logger import log
from news_crawler.base_crawler import BaseCrawler
from utils.beautifulSoup_utils import get_text_from_tag
from utils.service_utils import clean_date, get_urls_of_type,time_to_seconds, send_podcast_to_kafka, parse_vnexpress_time_ms, normalize_url_to_root_https
from utils.mongodb_utils import save_image_metadata

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

class VietNamNetCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://vietnamnet.vn"
        self.article_type_dict = {
            0: "thoi-su",
            1: "kinh-doanh",
            2: "the-thao",
            3: "van-hoa",
            4: "giai-tri",
            5: "the-gioi",
            6: "doi-song",
            7: "giao-duc",
            8: "suc-khoe",
            9: "thong-tin-truyen-thong",
            10: "phap-luat",
            11: "oto-xe-may",
            12: "bat-dong-san",
            13: "du-lich",
            14: "chinh-tri",
            15: "ban-doc",
        }

    def download_image(self, image_url, article_title, category, published_date):
        """Tải và lưu ảnh, trả về đường dẫn local và metadata"""
        try:

            # === CẤU HÌNH SSH đến máy B ===
            ssh_host = "192.168.161.230"
            ssh_user = "htsc"
            ssh_password = "Htsc@123"
            remote_base_dir = "/mnt/data/news"
            # Tạo cấu trúc thư mục: vnexpress/category/date
            newspaper_name = "vietnamnet"
            date_parts = clean_date(published_date).split(',')[0].strip()
            day, month, year = date_parts.split('/')
            date_folder = f"{day}-{month}-{year}"

            # Tạo đường dẫn thư mục đầy đủ
            remote_dir = Path(remote_base_dir) / newspaper_name / category / date_folder

            clean_url = image_url.split('?')[0]
            image_filename = Path(clean_url).name
            remote_path = remote_dir / image_filename

            # Tải ảnh
            response = requests.get(image_url, headers=headers, timeout=10)
            response.raise_for_status()
            image_data = BytesIO(response.content)


            # Kết nối SSH/SFTP
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(ssh_host, username=ssh_user, password=ssh_password)
            sftp = ssh.open_sftp()

            # Xử lý URL ảnh
            # Tạo thư mục nếu chưa có (đệ quy)
            path_parts = str(remote_dir).split('/')
            current = ''
            for part in path_parts:
                if not part:
                    continue
                current += f'/{part}'
                try:
                    sftp.stat(current)
                except IOError:
                    sftp.mkdir(current)

            # Ghi ảnh vào máy B
            with sftp.open(str(remote_path), 'wb') as remote_file:
                remote_file.write(image_data.getbuffer())

            sftp.close()
            ssh.close()
            # Lưu metadata vào MongoDB
            image_data = {
                'image_url': image_url,
                'local_path': str(remote_path),
                'file_size': len(image_data.getbuffer())
            }
            save_image_metadata(image_data)

            return str(remote_path)

        except Exception as e:
            print(f"Lỗi khi tải ảnh {image_url}: {e}")
            return None
            
    def extract_profile_domain(self, url: str):
        job_id = 1
        info = {
            "name": url,
            "description": "",
            "license": None,
            "editor_in_chief": None,
            "address": None,
            "phone": None,
            "email": None,
            "infor_copyright": None,
            "jobId": job_id or str(uuid.uuid4()),
            "logo": None,
        }

        # --- Phase 1: lấy logo bằng requests ---
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")
            logo_tag = soup.select_one("header.vnn-header img")
            logo_src = logo_tag["src"] if logo_tag and logo_tag.has_attr("src") else None
            info["logo"] = logo_src
        except Exception as e:
            print("⚠️ Lỗi khi lấy logo:", e)

        # --- Phase 2: lấy footer bằng Selenium ---
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
        chrome_options.add_experimental_option(
            "prefs",
            {
                "profile.managed_default_content_settings.images": 2,  # tắt ảnh
                "profile.managed_default_content_settings.javascript": 1,  # bật JS
            }
        )
        chrome_options.set_capability("pageLoadStrategy", "eager")

        driver = None
        try:
            driver = webdriver.Chrome(options=chrome_options)
            driver.set_page_load_timeout(100)

            try:
                driver.get(url)
            except TimeoutException:
                print("⚠️ Load trang quá lâu, bỏ qua:", url)
                return info

            # Chờ phần footer xuất hiện
            try:
                footer = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.footer__bottom"))
                )
            except TimeoutException:
                print("⚠️ Không tìm thấy footer.")
                return info

            soup = BeautifulSoup(driver.page_source, "html.parser")
            footer_copyright = soup.find("div", class_="footer__bottom")
            if footer_copyright:
                text = footer_copyright.get_text("\n", strip=True)
                lines = text.split("\n")

                # Description = 2 dòng đầu tiên
                if len(lines) >= 2:
                    info["description"] = f"{lines[0]} - {lines[1]}"

                # License
                if "Số giấy phép:" in text:
                    license_line = [line for line in lines if "Số giấy phép:" in line]
                    if license_line:
                        info["license"] = license_line[0].replace("Số giấy phép:", "").strip()

                # Tổng biên tập
                if "Tổng biên tập:" in text:
                    editor_line = [line for line in lines if "Tổng biên tập:" in line]
                    if editor_line:
                        info["editor_in_chief"] = editor_line[0].replace("Tổng biên tập:", "").strip()

                # Địa chỉ
                if "Địa chỉ:" in text:
                    addr_line = [line for line in lines if "Địa chỉ:" in line]
                    if addr_line:
                        info["address"] = addr_line[0].replace("Địa chỉ:", "").strip()

                # Điện thoại
                li_phone = soup.select_one("div.footer__bottom-address li:-soup-contains('Điện thoại')")

                if li_phone:
                    text = li_phone.get_text(" ", strip=True)
                    cleaned = text.replace("Điện thoại:", "", 1).strip()
                    info["phone"] = cleaned

                # Email
                email_tag = footer_copyright.select_one("a[href^=mailto]")
                if email_tag:
                    info["email"] = email_tag.get_text(strip=True).replace("Email:", "").strip()
                else:
                    li_tags = footer_copyright.select("li")
                    email_found = None
                    for li in li_tags:
                        text = li.get_text(strip=True)
                        # Tìm cụm có chứa chữ "Email" hoặc có định dạng email
                        if "email" in text.lower() or "@" in text:
                            match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
                            if match:
                                email_found = match.group(0)
                                break
                    if email_found:
                        info["email"] = email_found
                        
                # Thông tin bản quyền
                last_li = soup.select_one("div.footer__bottom-address li:last-child")
                if last_li:
                    info["infor_copyright"] = last_li.get_text(strip=True)

        except WebDriverException as e:
            print("⚠️ Lỗi Selenium:", e)
        finally:
            if driver:
                driver.quit()

        return (
            info.get("license", ""),
            info.get("description", ""),
            info.get("editor_in_chief", ""),
            info.get("address", ""), 
            info.get("phone", ""),
            info.get("email", ""),
            info.get("infor_copyright", ""),
            info.get("logo", "")
        )
    
    def extract_content(self, url: str, has_video) -> tuple:
        content = requests.get(url, headers=headers, timeout=10).content
        sleep_time = random.uniform(1, 2)
        time.sleep(sleep_time)
        soup = BeautifulSoup(content, "html.parser")

        title_tag = soup.find("h1", class_="content-detail-title")
        desc_tag = soup.find("h2", class_=["content-detail-sapo", "sm-sapo-mb-0"])
        main_content_tag = soup.find("div", class_=["maincontent", "main-content"])

        date_tag = soup.find("div", class_="bread-crumb-detail__time")
        published_date = date_tag.text.strip() if date_tag else "Không có thông tin"

        # Lấy tất cả các ảnh trong nội dung bài viết (cập nhật theo cấu trúc HTML Vietnamnet)
        content_images = []
        if main_content_tag:
            img_tags = main_content_tag.find_all("img")
            for img in img_tags:
                img_url_content = img.get("src") or img.get("data-original")
                if img_url_content and not img_url_content.startswith("data:image"):
                    content_images.append(urljoin("https://vietnamnet.vn", img_url_content) if img_url_content.startswith("/") else img_url_content)
                elif img.find_parent("picture"):
                    source = img.find_previous("source")
                    if source and source.get("data-srcset"):
                        srcset = source["data-srcset"].split(',')[0].strip().split()[0].strip()
                        content_images.append(urljoin("https://vietnamnet.vn", srcset))

        if not all([title_tag, desc_tag, main_content_tag]):
            return None, None, None, None, None, None, None, None

        title = title_tag.text
        description = desc_tag.get_text(strip=True) if desc_tag else ""
        paragraphs = (get_text_from_tag(p) for p in main_content_tag.find_all("p"))
        content = "\n".join(paragraphs)
        author = ""
        author_box = soup.find("div", class_="article-detail-author")
        if author_box:
            name_span = author_box.find("span", class_="name")
            if name_span:
                author = name_span.text.strip()
            else:
                link_author = author_box.find("a")
                if link_author:
                    author = link_author.text.strip()

        breadcrumb = soup.select("div.bread-crumb-detail ul > li > a")
        categories = []
        for a in breadcrumb:
            text = a.get_text(strip=True)
            if text and "icon-home" not in a.get("class", []):
                categories.append(text)
        categories = ", ".join(categories)
        
        location = ""
        video_url = ""
        try:
            chrome_options = Options()
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--disable-popup-blocking")
            chrome_options.add_argument("--disable-notifications")

            driver = webdriver.Chrome(options=chrome_options)
            driver.get(url)

            # iframe trong figure.vnn-template-noneditable
            try:
                iframe_el = driver.find_element(By.CSS_SELECTOR, "figure.vnn-template-noneditable iframe")
                video_url = iframe_el.get_attribute("src") or ""
            except NoSuchElementException:
                video_url = ""

        except WebDriverException as e:
            print("⚠️ Selenium error:", e)
        finally:
            try:
                driver.quit()
            except:
                pass
        
        thumbnail_url = ""
        try:
            chrome_options = Options()
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--disable-popup-blocking")
            chrome_options.add_argument("--disable-notifications")

            driver = webdriver.Chrome(options=chrome_options)
            driver.get(url)
            WebDriverWait(driver, 12).until(
                EC.frame_to_be_available_and_switch_to_it(
                    (By.CSS_SELECTOR, "figure.vnn-template-noneditable iframe")
                )
            )
            img_el = WebDriverWait(driver, 12).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "picture.vjs-poster img"))
            )
            thumbnail_url = (img_el.get_attribute("src") or "").strip()
            # iframe trong figure.vnn-template-noneditable
            if not thumbnail_url:
                # a) thuộc tính poster trên thẻ <video>
                try:
                    video_el = driver.find_element(By.CSS_SELECTOR, "video.vjs-tech")
                    thumbnail_url = (video_el.get_attribute("poster") or "").strip()
                except Exception:
                    pass

        except WebDriverException as e:
            print("⚠️ Selenium error:", e)
        finally:
            try:
                driver.quit()
            except:
                pass
        return title, description, content, published_date, author, content_images, categories, video_url, thumbnail_url, location

    def extract_comment(self, url: str):
        # Sử dụng session từ base class (có thể là proxy session)
        # --- Phase 2: lấy footer bằng Selenium ---
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--remote-debugging-port=9222")
        chrome_options.add_argument("--disable-images")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-popup-blocking")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_experimental_option("prefs", {
            "profile.managed_default_content_settings.images": 2,
            "profile.default_content_setting_values.notifications": 2
        })
        driver = None
        try:
            driver = webdriver.Chrome(options=chrome_options)
            driver.set_page_load_timeout(60)

            try:
                driver.get(url)
            except TimeoutException:
                print("⚠️ Load trang quá lâu, bỏ qua:", url)
            # --- Click "Xem thêm ý kiến" để load thêm comment ---
            try:
                iframe = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "iframe[src*='comment']"))
                )
                driver.switch_to.frame(iframe)
                print("Đã switch vào iframe comment")
            except Exception as e:
                print("Không tìm thấy iframe comment:", e)
                return []

            while True:
                try:
                    show_more_btn = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, "i.arrow"))
                    )
                    driver.execute_script("arguments[0].scrollIntoView(true);", show_more_btn)
                    time.sleep(0.2)
                    driver.execute_script("arguments[0].click();", show_more_btn)
                    time.sleep(0.5)
                except (TimeoutException, NoSuchElementException):
                    break

            soup = BeautifulSoup(driver.page_source, "html.parser")
            comments = []
            tab_panel = soup.find("div", class_="react-tabs__tab-panel react-tabs__tab-panel--selected")
            items = tab_panel.find_all("div", class_="mb-[10px]") if tab_panel else []

            for item in items:

                comment_id = ""
                username_tag = item.find("div", class_=re.compile(r"text-\[#2D67AD\]"))
                username = username_tag.get_text(strip=True) if username_tag else ""
                content_tag = item.select_one("div.content__wrapper p") or item.select_one("div.LinesEllipsis")
                content = ""
                if content_tag:
                    content = content_tag.get_text(" ", strip=True)
                    # Nếu phần username lẫn trong nội dung thì loại bỏ
                    if username and content.startswith(username):
                        content = content.replace(username, "").strip()

                time_text = ""
                for span in item.find_all("span"):
                    txt = span.get_text(strip=True)
                    if "trước" in txt or "giây" in txt or "giờ" in txt:
                        time_text = txt
                        break
                time_comment = parse_vnexpress_time_ms(time_text) if time_text else None

                reactions = {}
                tooltip_div = item.find("div", class_=lambda c: c and "tooltip-actions" in c)

                if tooltip_div:
                    like_span = tooltip_div.find("span", class_=lambda c: c and "text-[#838383]" in c)
                    if like_span:
                        txt = like_span.get_text(strip=True)
                        try:
                            reactions["like"] = int(txt)
                        except ValueError:
                            reactions["like"] = txt
                    else:
                        reactions["like"] = 0
                else:
                    reactions["like"] = 0

                comments.append({
                    "domain": normalize_url_to_root_https(url),
                    "url": url,
                    "userId": username,
                    "commentId": f"{username.replace(' ', '')}_{uuid.uuid4().hex}",
                    "username": username,
                    "content": content,
                    "userUrl": "",
                    "avatar": "",
                    "time": time_comment,
                    "reactions": reactions,
                    "replyCount": 0
                })


            return comments

        except WebDriverException as e:
            print("⚠️ Lỗi Selenium:", e)
            return []

        finally:
            if driver:
                driver.quit()


    
    def write_content(self, url: str, article_type: str) -> bool:
        try:
            title, description, content, published_date, author, content_images, categories = self.extract_content(url)
            if not title:
                return None
            
            # Lấy thể loại từ URL
            category = article_type
                
            # Tải và lưu ảnh nội dung
            # content_image_paths = []
            # for img_url in content_images:
            #     if img_url:
            #         img_path = self.download_image(img_url, title, category, published_date)
            #         if img_path:
            #             content_image_paths.append(img_path)
            
            article_data = {
                "dataSource": "/".join(url.split("/")[:3]),
                "url": url,
                "title": title,
                "author": author,
                "publishedDate": clean_date(published_date),
                "description": description,
                "content": content,
                "contentImageUrls": content_images,
                "categories": categories
                # # "localContentImagePaths": content_image_paths
            }

            return article_data
            
        except Exception as e:
            print(f"Lỗi khi xử lý URL {url}: {e}")       
            return None
    
    def get_urls_of_type_thread(self, article_type, page_number):
        page_url = f"https://vietnamnet.vn/{article_type}-page{page_number-1}"
        if(page_number == 2):
            return []
        articles_urls = []
        try:
            content = requests.get(page_url, headers=headers, timeout=10).content
            sleep_time = random.uniform(1, 2)
            time.sleep(sleep_time)
            soup = BeautifulSoup(content, "html.parser")
            titles = soup.find_all(class_=["horizontalPost__main-title", "vnn-title", "title-bold"])

            if (len(titles) == 0):
                self.logger.info(f"Couldn't find any news in {page_url} \nMaybe you sent too many requests, try using less workers")
                return []

            for title in titles:
                full_url = title.find_all("a")[0].get("href")
                if self.base_url not in full_url:
                    full_url = self.base_url + full_url
                articles_urls.append(full_url)
        except Exception as e:
            self.logger.warning(f"[!] Error while fetching {page_url}: {e}")
            return []

        return articles_urls

    def get_all_articles(self, category):
        all_articles = []

        for category in self.article_type_dict.values():
            urls = get_urls_of_type(self, category)
            all_articles.extend(urls)

        return all_articles
    
    def get_all_articles_by_keyword(self, page_url):
        print(f"page_url: {page_url}")
        try:
            content = requests.get(page_url, headers=headers, timeout=10).content
            sleep_time = random.uniform(1, 2)
            time.sleep(sleep_time)
            soup = BeautifulSoup(content, "html.parser")
            urls = set()
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"]
                if href.startswith("https://vietnamnet.vn/"):
                    urls.add(href)
            return list(urls)
        except Exception as e:
            return []

    def get_url_podcast(self, url, category):
        base = "https://vietnamnet.vn"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }

        all_urls = set()
        base_url = url.rstrip("/")
        page = 0

        while True:
            page_url = f"{base_url}/{category}-page{page}"
            print(f"Đang crawl: {page_url}")

            res = requests.get(page_url, headers=headers)
            if res.status_code != 200:
                print(f"⛔ Trang không tồn tại hoặc lỗi HTTP ({res.status_code}), dừng!")
                break

            soup = BeautifulSoup(res.text, "html.parser")
            
            # Lấy bài viết theo class yêu cầu:
            posts = soup.select("div.horizontalPost.podcast.stream.mb-20 a[href]")
            
            if not posts:  # Nếu không còn bài => dừng
                print("✅ Không còn bài viết nào nữa, dừng!")
                break

            for a in posts:
                link = a.get("href", "")
                if not link:
                    continue
                if link.startswith("/"):
                    link = base + link
                all_urls.add(link)

            page += 1
        return all_urls

    def get_audio_from_article(self, url):
        try:
            chrome_options = Options()
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--disable-popup-blocking")
            chrome_options.add_argument("--disable-notifications")
            chrome_options.add_argument("--blink-settings=imagesEnabled=false")

            driver = webdriver.Chrome(options=chrome_options)
            driver.get(url)
            
            headers = {
                "User-Agent": "Mozilla/5.0"
            }
            resp = requests.get(url, headers=headers)
            soup = BeautifulSoup(resp.text, "html.parser")

            # 2 DESCRIPTION
            s_tag = soup.select_one("h2.content-detail-sapo")
            description = s_tag.get_text(strip=True) if s_tag else ""

            # 3 PUBLISHED DATE
            t_tag = soup.select_one("div.bread-crumb-detail__time")
            time_text = t_tag.get_text(strip=True) if t_tag else ""
            publishedDate = parse_vnexpress_time_ms(time_text)

            # 4 AUTHOR
            a_tag = soup.select_one("span.name a, div.name a")
            author = a_tag.get("title", "").strip() if a_tag else ""

            # end_time
            try:
                dur_el = WebDriverWait(driver, 12).until(
                    lambda d: d.find_element(By.CSS_SELECTOR, '[aria-label="Duration"]')
                )
                WebDriverWait(driver, 12).until(
                    lambda d: (dur_el.text or "").strip() not in ("", "00:00")
                )

                end_time_mp3_url = dur_el.text.strip()
            except Exception as e:
                print("⚠️ Không lấy được end_time_mp3:")
                end_time_mp3_url= ""
            driver.quit()
            return {
                "description": description,
                "author": author,
                "duration": time_to_seconds(end_time_mp3_url),
                "publishedDate": publishedDate
            }         
        except Exception as e:
            print(f"❌ Lỗi trong quá trình crawl {url}: {e}")
            # trả dict rỗng để crawler vẫn tiếp tục
            return {
                "description": "",
                "author": "",
                "duration": "",
                "publishedDate": "",
            }

    def crawl_podcast_bs4(self, url: str, category: str):
        def build_domain_username( domain, author_url):
            return f"{domain}_{author_url.replace(' ', '')}"
        domain = "vietnamnet"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        res = requests.get(url, headers=headers)
        soup = BeautifulSoup(res.text, "html.parser")

        # Title
        title_tag = soup.find("h1", class_="content-detail-title")
        title = title_tag.get_text(strip=True) if title_tag else ""

        # Thumbnail
        thumb = soup.find("meta", property="og:image")
        thumbnail = thumb["content"] if thumb else ""
        # Audio URL
        audio_url = ""
        audio_tag = soup.find("audio")
        if audio_tag:
            # Ưu tiên lấy từ <source src="">
            source_tag = audio_tag.find("source")
            if source_tag and source_tag.get("src"):
                audio_url = source_tag.get("src")

            # Nếu <audio src="">
            if audio_tag.get("src"):
                audio_url = audio_tag.get("src")

        meta = self.get_audio_from_article(url)
        content_url   = meta["description"]
        author_url    = meta["author"]
        end_time_url  = meta["duration"]
        datetime_url  = meta["publishedDate"]
        domain_username = build_domain_username(domain, author_url) if author_url else ""

        podcast = {
            "title": title,
            "url": url,
            "thumbnail": thumbnail,
            "category": category,
            "audio_url": audio_url,
            "author": author_url,
            "description": content_url,
            "duration": end_time_url,
            "publishedDate": datetime_url,
            "authorId": domain_username,
}
        send_podcast_to_kafka(podcast)

    def crawl_postcast(self):
        podcast_type_dict = {
            0:  "doc-la",
            1:  "goc-nhin",
            2:  "ban-tin-thoi-su",
            3:  "song-tre",
            4:  "sach-hay",
            5:  "chuyen-cua-nhung-dong-song",
        }

        BASE_URL = "https://vietnamnet.vn/podcast"

        for idx, slug in podcast_type_dict.items():
            urls = self.get_url_podcast(BASE_URL, slug)
            for url in urls:
                self.crawl_podcast_bs4(url, slug)
            

