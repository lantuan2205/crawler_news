import json
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

class DanTriCrawler:
    def __init__(self):
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        self.base_url = "https://dantri.com.vn"

    def get_categories(self):
        self.driver.get(self.base_url)
        soup = BeautifulSoup(self.driver.page_source, "lxml")
        categories = soup.select("nav a[href^='/']")
        result = []

        for category in categories:
            name = category.text.strip()
            link = self.base_url + category["href"] if "https" not in category["href"] else category["href"]
            result.append({"name": name, "url": link})

        return result

    def get_articles(self, category_url):
        self.driver.get(category_url)
        time.sleep(2)
        soup = BeautifulSoup(self.driver.page_source, "lxml")
        articles = soup.select(".article-title a")
        result = []

        for article in articles:
            title = article.text.strip()
            link = self.base_url + article["href"]
            result.append({"title": title, "url": link})

        return result

    def get_article_detail(self, article_url):
        self.driver.get(article_url)
        time.sleep(2)
        soup = BeautifulSoup(self.driver.page_source, "lxml")

        title = soup.find("h1", class_="title-page").text.strip() if soup.find("h1", class_="title-page") else "N/A"
        date = soup.find("span", class_="dt-news__time").text.strip() if soup.find("span", class_="dt-news__time") else "N/A"
        content = "\n".join([p.text.strip() for p in soup.select(".dt-news__content p")])

        return {"title": title, "date": date, "content": content}

    def save_json(self, data, filename="dantri_data.json"):
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def close(self):
        self.driver.quit()
