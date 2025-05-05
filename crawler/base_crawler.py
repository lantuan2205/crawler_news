from abc import ABC, abstractmethod
import concurrent.futures
import json
from tqdm import tqdm
import time

from utils.utils import init_output_dirs, create_dir, read_file
from utils.service_utils import save_to_json, send_json_to_api, save_to_db
class BaseCrawler(ABC):

    @abstractmethod
    def extract_content(self, url):
        title = str()
        description = list()
        paragraphs = list()

        return title, description, paragraphs

    @abstractmethod
    def write_content(self, url):
        return True
    
    @abstractmethod
    def get_urls_of_type_thread(self, article_type, page_number):
        articles_urls = list()
        return articles_urls

    def start_crawling(self):
        error_urls = list()
        if self.task=="url":
            error_urls = self.crawl_urls(self.urls_fpath, None)
        elif self.task=="type":
            error_urls = self.crawl_types()

    def crawl_urls(self, urls_fpath, article_type):
        self.logger.info(f"Start crawling urls from {urls_fpath} file...")
        urls = list(read_file(urls_fpath))
        num_urls = len(urls)
        self.index_len = len(str(num_urls))

        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.num_workers) as executor:
            for result in tqdm(executor.map(lambda url: self.crawl_url_thread(url, article_type), urls), total=num_urls, desc="URLs"):
                if result:
                    results.append(result)

        grouped_results = {}
        for article in results:
            grouped_results.setdefault(article_type, []).append(article)
        return grouped_results

    def crawl_url_thread(self, url, article_type):
        data = self.write_content(url, article_type)
        if data is None:
            self.logger.info(f"Crawling unsuccessfully: {url}")
            return None
        data['article_type'] = article_type
        save_to_json(data)
        save_to_db(data)
        # send_json_to_api()
        time.sleep(1)
        return {"url": url, "data": data}

    def crawl_types(self):
        urls_dpath, results_dpath = init_output_dirs(self.output_dpath)

        if self.article_type == "all":
            error_urls = self.crawl_all_types(urls_dpath, results_dpath)
        else:
            error_urls = self.crawl_type(self.article_type, urls_dpath, results_dpath)
        return error_urls

    def crawl_type(self, article_type, urls_dpath, results_dpath):
        self.logger.info(f"Crawl articles type {article_type}")
        error_urls = list()
        valid_article_type = article_type.replace("/", "-")

        # getting urls
        self.logger.info(f"Getting urls of {article_type}...")
        articles_urls = self.get_urls_of_type(article_type)
        articles_urls_fpath = "/".join([urls_dpath, f"{valid_article_type}.txt"])
        with open(articles_urls_fpath, "w") as urls_file:
            urls_file.write("\n".join(articles_urls)) 

        # crawling urls
        self.logger.info(f"Crawling from urls of {article_type}...")
        data = self.crawl_urls(articles_urls_fpath, article_type)
        
        return data

    def crawl_all_types(self, urls_dpath, results_dpath):
        total_error_urls = list()
        json_data =[]
        num_types = len(self.article_type_dict) 
        for i in range(num_types):
            article_type = self.article_type_dict[i]
            data = self.crawl_type(article_type, urls_dpath, results_dpath)
            json_data.append(data)
            self.logger.info("-" * 79)
        
        # output_fpath = "".join([results_dpath, "/articles", ".json"])
        # with open(output_fpath, "w", encoding="utf-8") as file:
        #     json.dump(json_data, file, ensure_ascii=False, indent=4)
        return True

    def get_urls_of_type(self, article_type):
        articles_urls = set()
        page_number = 100
        progress = tqdm(desc="Pages", unit=" page")

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.num_workers) as executor:
            futures = {}
            while True:
                # Gửi batch gồm num_workers page một lúc
                for _ in range(self.num_workers):
                    future = executor.submit(self.get_urls_of_type_thread, article_type, page_number)
                    futures[future] = page_number
                    page_number += 1

                stop = False
                for future in concurrent.futures.as_completed(futures):
                    page = futures[future]
                    try:
                        result = future.result()
                        progress.update(1)
                        if not result:
                            self.logger.info(f"[!] Page {page} returned empty. Stopping further crawl.")
                            stop = True
                        else:
                            articles_urls.update(result)
                    except Exception as e:
                        self.logger.warning(f"[!] Error on page {page}: {e}")

                futures.clear()
                if stop:
                    break

        return list(articles_urls)
