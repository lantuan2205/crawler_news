import requests
import sys
from pathlib import Path
import time
import random
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import os
from datetime import datetime
import paramiko
from io import BytesIO
from selenium.webdriver.common.by import By
import re
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException, ElementNotInteractableException

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
FILE = Path(__file__).resolve()
ROOT = FILE.parents[1]  # root directory
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))  # add ROOT to PATH

from logger import log
from news_crawler.base_crawler import BaseCrawler
from utils.beautifulSoup_utils import get_text_from_tag
from utils.service_utils import clean_date, get_urls_of_type
from utils.service_utils import clean_date, get_urls_of_type, send_podcast_to_kafka, parse_vnexpress_time_ms, normalize_url_to_root_https


headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

class VTCNewsCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://vtcnews.vn"
        self.article_type_dict = {
            0: "chinh-tri-47",
            1: "quan-su-49",
            2: "bao-ve-nguoi-tieu-dung-51",
            3: "thoi-su-quoc-te-53",
            4: "tin-tuc-bien-dong-55",
            5: "tin-tuc-su-kien-56",
            6: "ban-tin-113-online-58",
            7: "chuyen-vu-an-59",
            8: "hoa-hau-60",
            9: "nhac-62",
            10: "sao-the-gioi-63",
            11: "sao-viet-64",
            12: "bong-da-anh-66",
            13: "benh-va-thuoc-68",
            14: "dinh-duong-69",
            15: "nguoi-dep-va-xe-72",
            16: "tu-van-73",
            17: "gioi-tinh-90",
            18: "gioi-tre-85",
            19: "thi-truong-100",
            20: "lich-thi-dau-bong-da-101",
            21: "tin-tuc-trong-ngay-105",
            22: "bat-dong-san-112",
            23: "tin-gia-vang-113",
            24: "bong-da-viet-nam-115",
            25: "du-lich-195",
            26: "tin-tuc-202",
            27: "khoe-dep-203",
            28: "tu-van-204",
            29: "dien-dan-207",
            30: "du-hoc-208",
            31: "chuyen-bon-phuong-209",
            32: "y-kien-211",
            33: "gia-dinh-212",
            34: "tuyen-sinh-220",
            35: "an-sinh-239",
            36: "thu-thuat-267",
            37: "hom-thu-phap-luat-268",
            38: "chuyen-doi-so-271",
            39: "phong-chong-chay-no-272",
            40: "v-league-274",
            41: "ky-nguyen-vuon-minh-285",
            42: "nguoi-viet-bon-phuong-292",
            43: "tin-xe-247-293",
            44: "trai-nghiem-294",
            45: "thi-truong-295",
            46: "xe-dien-296"
                                                                                                
        }   
        
    def extract_profile_domain(self, url: str):
        job_id = 1
        base_url = "https://vtcnews.vn"
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
            container = soup.select_one("div.topbar") 
            logo_img = container.select_one("h1.logo img") if container else None

            src = ""
            if logo_img:
                # Ưu tiên src thật (nếu không phải base64)
                real_src = logo_img.get("src") or ""
                data_src = logo_img.get("data-src") or ""

                # Nếu src bị base64 thì lấy data-src
                if real_src.startswith("data:image"):
                    src = data_src
                else:
                    src = real_src

            info["logo"] = urljoin(url, src) if src else ""
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
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.zone-menus"))
                )
            except TimeoutException:
                print("⚠️ Không tìm thấy footer.")
                return info

            soup = BeautifulSoup(driver.page_source, "html.parser")
            footer_copyright = soup.find("div", class_="zone-menus")
            if footer_copyright:

                # Description = 2 dòng đầu tiên
                ul = soup.select_one("ul.mb20.font13.gray-31.clearfix")
                info["description"] = (
                    ul.select_one(":scope > li:nth-of-type(2)").get_text(" ", strip=True) if ul else ""
                )
                # License
                ul = soup.select_one("ul.mb20.font13.gray-31.clearfix")
                info["license"] = ""
                if ul:
                    lis = ul.find_all("li", recursive=False)  # chỉ con trực tiếp
                    if len(lis) >= 3:
                        info["license"] = lis[2].get_text(" ", strip=True)

                # Tổng biên tập
                li = next((x for x in soup.select("ul.mb20.font13.gray-31.clearfix li")
                        if "phó tổng biên tập phụ trách" in x.get_text(" ", strip=True).lower()), None)
                info["editor_in_chief"] =  li.select_one("span").get_text(strip=True) if li else ""

                # Địa chỉ
                li = next((x for x in soup.select("ul.mb20.font13.gray-31.clearfix li")
                        if x.select_one("i.icon-location-6")), None)

                address = li.get_text(" ", strip=True) if li else ""
                info["address"] = address


                # Điện thoại
                phones = []
                for a in soup.select('a[href^="tel:"]'):
                    # ưu tiên text hiển thị; nếu rỗng lấy từ href sau "tel:"
                    txt = a.get_text(strip=True) or a["href"][len("tel:"):]
                    phones.append(txt)

                info["phone"] = ", ".join(phones)
                
                # Email
                email_tag = footer_copyright.select_one("a[href^=mailto]")
                if email_tag:
                    info["email"] = email_tag.get_text(strip=True).replace("Email:", "").strip()

                # Thông tin bản quyền
                last_p = footer_copyright.select("p")[-1]
                if last_p:
                    info["infor_copyright"] = last_p.get_text(strip=True)

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
        """
        Extract title, description, content, publish date, author, and content images from url.
        @param url (str): url to crawl
        @return tuple: (title, description, content, publish_date, author, content_images)
        """
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            # Trích xuất tiêu đề
            title_tag = soup.find("header", class_="mb5").find("h1")
            title = title_tag.get_text(strip=True) if title_tag else None

            description = soup.select_one('h2')
            description = description.get_text(strip=True) if description else ''

            content_elements = soup.select('.edittor-content p')
            content = '\n'.join(p.get_text(strip=True) for p in content_elements if p.get_text(strip=True))

            # Trích xuất ngày viết bài
            date_tag = soup.find('span', class_='time-update')
            publish_date = date_tag.get_text(strip=True) if date_tag else None

            # Lấy các URL ảnh và alt text từ các thẻ img trong thẻ figure
            figures = soup.select("figure.expNoEdit img")
            content_images = [img.get("data-src") for img in figures if img.get("data-src")]

            # Trích xuất tác giả
            author = soup.select_one('.author-make span')
            author = author.get_text(strip=True) if author else ''

            categories_tag = soup.select_one('a.mt-category')
            categories = categories_tag.get_text(strip=True) if categories_tag else ''
            location = ""

            video_url = ""
            thumbnail_url = ""
            try:
                chrome_options = Options()
                chrome_options.add_argument("--headless=new")
                chrome_options.add_argument("--disable-gpu")
                chrome_options.add_argument("--no-sandbox")
                chrome_options.add_argument("--disable-extensions")
                chrome_options.add_argument("--disable-popup-blocking")
                chrome_options.add_argument("--disable-notifications")
                chrome_options.add_argument("--window-size=1200,900")
                chrome_options.add_argument("--log-level=3")

                driver = webdriver.Chrome(options=chrome_options)
                driver.get(url)
                driver.switch_to.default_content()
                wait = WebDriverWait(driver, 10, poll_frequency=0.2)

                # Lấy video src (nếu có)

                try:
                    # 1) Lấy container JWPlayer và <video>
                    root = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.jwplayer")))
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", root)
                    video_el = wait.until(lambda d: root.find_element(By.CSS_SELECTOR, "video.jw-video"))

                    # 2) Thử click THUMB (overlay) hoặc nút Play của JW
                    clicked = False
                    for sel in (".jw-preview", ".jw-display-icon-container", ".jw-display .jw-icon",
                                "button[aria-label='Play']", ".jw-icon-play"):
                        els = root.find_elements(By.CSS_SELECTOR, sel)
                        if not els:
                            continue
                        try:
                            driver.execute_script("arguments[0].click();", els[0])  # click JS tránh intercept
                            clicked = True
                            break
                        except Exception:
                            pass

                    # 3) Nếu chưa được → click giữa player theo tọa độ (bypass overlay lạ)
                    if not clicked:
                        rect = driver.execute_script("""
                            const r = arguments[0].getBoundingClientRect();
                            return {x: Math.floor(r.left + r.width/2), y: Math.floor(r.top + r.height/2)};
                        """, root)
                        actions = ActionChains(driver)
                        actions.move_by_offset(rect["x"], rect["y"]).click().perform()
                        # trả chuột về (tránh offset tích lũy)
                        actions.move_by_offset(-rect["x"], -rect["y"]).perform()
                        clicked = True

                    # 4) Nếu vẫn chưa chạy → dùng JWPlayer API
                    if clicked:
                        container_id = root.get_attribute("id") or driver.execute_script(
                            "return arguments[0].closest('[id]')?.id || '';", root
                        )
                        if container_id:
                            driver.execute_script("""
                                try {
                                if (window.jwplayer) {
                                    const p = jwplayer(arguments[0]);
                                    p.setMute(true);
                                    p.play(true);  // autoplay không cần gesture
                                }
                                } catch(e) {}
                            """, container_id)

                    # 5) Đợi nguồn được gán rồi lấy currentSrc/src/<source>
                    wait.until(lambda d: (d.execute_script(
                        "const v=arguments[0]; return v.currentSrc || v.src || (v.querySelector('source')?.src||'');",
                        video_el
                    ) or "").strip() != "")

                    video_url = (driver.execute_script(
                        "const v=arguments[0]; return v.currentSrc || v.src || (v.querySelector('source')?.src||'');",
                        video_el
                    ) or "").strip()

                except TimeoutException:
                    video_url = ""
                # Lấy FULL style của div.vjs-poster
                try:
                    # đảm bảo ở đúng context
                    driver.switch_to.default_content()
                    poster = WebDriverWait(driver, 2).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "div.jw-preview.jw-reset"))
                    )
                    print("thum",poster)
                    def _extract_url(s: str) -> str:
                        m = re.search(r'url\((["\']?)(.*?)\1\)', s or "")
                        return (m.group(2).strip() if m else "")

                    # ưu tiên inline style
                    style_attr = poster.get_attribute("style") or ""
                    thumbnail_url = _extract_url(style_attr)

                except TimeoutException:
                    thumbnail_url = ""

            except WebDriverException as e:
                print("⚠️ Selenium error:", e)
            finally:
                try:
                    if driver:
                        driver.quit()
                except:
                    pass

            return title, description, content, publish_date, author, content_images,categories, video_url, thumbnail_url, location

        except requests.exceptions.RequestException as e:
            print(f"Lỗi khi tải trang: {e}")
            return None, None, None, None, None, []
        except Exception as e:
            print(f"Lỗi trong quá trình phân tích HTML: {e}")
            return None, None, None, None, None, []
    
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
        chrome_options.set_capability("pageLoadStrategy", "eager")
        driver = None
        try:
            driver = webdriver.Chrome(options=chrome_options)
            driver.set_page_load_timeout(60)

            try:
                driver.get(url)
            except TimeoutException:
                print("⚠️ Load trang quá lâu, bỏ qua:", url)
            # --- Click "Xem thêm ý kiến" để load thêm comment ---
            while True:
                try:
                    show_more_btn = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, "a.btn-show-comment"))
                    )
                    # Cuộn tới nút

                    driver.execute_script("arguments[0].scrollIntoView(true);", show_more_btn)
                    time.sleep(0.2)
                    # Click bằng JS (bypass quảng cáo che)
                    driver.execute_script("arguments[0].click();", show_more_btn)
                    time.sleep(0.5)  # chờ comment load
                except (TimeoutException, NoSuchElementException):
                    break  # hết nút để click

            soup = BeautifulSoup(driver.page_source, "html.parser")
            comments = []
            base_url = "https://vtcnews.vn"
            for item in soup.select("div.comment-items"):
                # comment_id
                comment_id = item.select_one("a.btn-reply")
                comment_id = comment_id["data-id"] if comment_id else ""
          
                # username
                nickname = item.select_one("div.pl50 label a.font14.bold")
                username = nickname.get_text(strip=True) if nickname else ""

                # avatar
                avatar_tag = item.select_one("img.h35.w35.radius-circle.overflow")
                avatar = urljoin(base_url, avatar_tag["src"])  if avatar_tag else ""

                # content: ưu tiên content_more, nếu không thì lấy full_content
                content_tag = item.select_one("div.pl50 p.mt2") or item.select_one("p.mt2.gray-21.pd7.radius-10.bg-cmt.fl.break-word")
                content = content_tag.get_text(" ", strip=True).replace(username, "") if content_tag else ""

                # time
                time_tag = item.select_one("span.gray-71.mr10")
                if not time_tag:
                    time_tag = item.select_one("span.gray-71") or item.find("span", class_=["gray-71", "mr10"])
                time_text = time_tag.get_text(strip=True) if time_tag else ""
                time_comment = parse_vnexpress_time_ms(time_text) if time_text else None
                
                # reactions
                reaction_map = {
                    "Thích": "Like",
                    "Yêu thích": "Love",
                    "Haha": "Haha",
                    "Wow": "Wow",
                    "Buồn": "Sad",
                    "Phẫn nộ": "Angry",
                }

                reactions = {}
                for r in item.select("div.list-reaction div.abs-reaction"):
                    img_tag = r.select_one("i.mr2.fl")
                    label = ""
                    if img_tag:
                        classes = img_tag.get("class", [])
                        label = next((c.split("cmt-icon-")[1] for c in classes if c.startswith("cmt-icon-")), "")
                    label_en = reaction_map.get(label, label)
                    print("laber",label_en)
                    count_tag = r.select_one("div.abs-reaction")
                    reactions[label_en] = int(count_tag.get_text()) if count_tag else 0

                reply_count = 0

                comments.append({
                    "domain": normalize_url_to_root_https(url),
                    "url": url,
                    "commentId": comment_id,
                    "userId": username,
                    "username": username,
                    "userUrl": "",
                    "avatar": avatar,
                    "content": content,
                    "time": time_comment,
                    "reactions": reactions,
                    "replyCount": reply_count
                })
            return comments
        except WebDriverException as e:
            print("⚠️ Lỗi Selenium:", e)
        finally:
            if driver:
                driver.quit()

    def write_content(self, url: str, article_type: str) -> bool:
        """
        From url, extract title, description and paragraphs then write in output_fpath
        @param url (str): url to crawl
        @param output_fpath (str): file path to save crawled result
        @return (bool): True if crawl successfully and otherwise
        """
        title, description, content, publish_date, author, content_images = self.extract_content(url)
        if not title:
            return None

        article_data = {
            "dataSource": "/".join(url.split("/")[:3]),
            "url": url,
            "publishedDate": clean_date(publish_date),
            "author": author,
            "title": title,
            "description": description,
            "content": content,
            "contentImageUrls": content_images,
            # "localContentImagePaths": content_image_paths
        }

        return article_data
    
    def get_urls_of_type_thread(self, article_type, page_number):
        """" Get URLs of articles in a specific type on a given page"""
        if(page_number == 5):
            return []
        page_url = f"https://vtcnews.vn/{article_type}/trang-{page_number}.html"
        urls = []
        try:
            response = requests.get(page_url, headers=headers, timeout=10)
            sleep_time = random.uniform(1, 3)
            time.sleep(sleep_time)
            response.raise_for_status()  # Kiểm tra nếu request thất bại
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching {page_url}: {e}")
            return []

        soup = BeautifulSoup(response.content, "html.parser")
        articles = soup.find_all("article")
        if (len(articles) == 0):
            return []

        for article in articles:
            # Tìm <h3> hoặc <h2>
            heading = article.find(["h3", "h2"])
            if heading:
                a_tag = heading.find("a")
                if a_tag and a_tag.get("href"):
                    url = a_tag["href"]
                    full_url = "https://vtcnews.vn/" + url
                    urls.append(full_url)

        return urls

    def get_all_articles(self, category):
        
        all_articles = []

        urls = get_urls_of_type(self, category)
        all_articles.extend(urls)

        return all_articles