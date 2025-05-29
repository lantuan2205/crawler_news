import argparse
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from threading import Thread
from logger import log
from utils import utils
from crawler.factory import get_crawler
from utils.ui_checker import UIChecker
from functools import partial
from constants.crawlerselenium import CRAWLERS_SELENIUM

def crawl_site(webname, config, ui_checker):
    print(f"🚀 Bắt đầu crawl báo: {webname}")
    
    base_url = config["news_sites"].get(webname, "")

    #if ui_checker.check_ui_change(base_url):
    #    print(f"UI của {webname} đã thay đổi! Bỏ qua crawling.")
    #    return

    custom_config = config.copy()
    custom_config["webname"] = webname
    custom_config["output_dpath"] = f"{config['output_dpath']}/{webname}"

    crawler = get_crawler(**custom_config)
    crawler.start_crawling()

def wrapper(webname, config, ui_hash_file):
    local_ui_checker = UIChecker(ui_hash_file)
    return crawl_site(webname, config, local_ui_checker)

def run_requests(requests_webs, wrapped_func):
    with ThreadPoolExecutor(max_workers=len(requests_webs) or 1) as executor:
        futures = [executor.submit(wrapped_func, w) for w in requests_webs]
        for future in futures:
            try:
                future.result()
            except Exception as e:
                print(f"❌ Lỗi khi crawl báo (requests): {e}")

def run_selenium(selenium_webs, wrapped_func):
    with ProcessPoolExecutor(max_workers=len(selenium_webs) or 1) as executor:
        futures = [executor.submit(wrapped_func, w) for w in selenium_webs]
        for future in futures:
            try:
                future.result()
            except Exception as e:
                print(f"❌ Lỗi khi crawl báo (selenium): {e}")

def main(config_fpath):
    config = utils.get_config(config_fpath)
    log.setup_logging(log_dir=config["output_dpath"], 
                      config_fpath=config["logger_fpath"])

    webnames = config.get("webnames", [])
    ui_hash_file = config["ui_hash_file"]

    selenium_webs = [w for w in webnames if w in CRAWLERS_SELENIUM]
    requests_webs = [w for w in webnames if w not in CRAWLERS_SELENIUM]

    wrapped_func = partial(wrapper, config=config, ui_hash_file=ui_hash_file)

    # Tạo 2 thread chạy song song requests và selenium
    # request and selenium khong chay chung ThreadPoolExecutor 
    # => request chay ThreadPoolExecutor
    # => selenium chay ProcessPoolExecutor
    thread_requests = Thread(target=run_requests, args=(requests_webs, wrapped_func))
    thread_selenium = Thread(target=run_selenium, args=(selenium_webs, wrapped_func))

    thread_requests.start()
    thread_selenium.start()

    thread_requests.join()
    thread_selenium.join()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vietnamese News crawler (with url/type)")
    parser.add_argument("--config", 
                        default="crawler_config.yml", 
                        help="path to config file",
                        dest="config_fpath") 
    args = parser.parse_args()
    main(**vars(args))