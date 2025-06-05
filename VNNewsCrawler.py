import argparse
from concurrent.futures import ThreadPoolExecutor
from threading import Thread
import subprocess
from logger import log
from utils import utils
from crawler.factory import get_crawler
from utils.ui_checker import UIChecker
from constants.crawlerselenium import CRAWLERS_SELENIUM

def crawl_site(webname, config, ui_checker):
    print(f"🚀 Bắt đầu crawl báo: {webname}")
    base_url = config["news_sites"].get(webname, "")

    custom_config = config.copy()
    custom_config["webname"] = webname
    custom_config["output_dpath"] = f"{config['output_dpath']}/{webname}"

    crawler = get_crawler(**custom_config)
    try:
        crawler.start_crawling()
    except Exception as e:
        print(f"❌ Lỗi khi chạy crawler.start_crawling() cho {webname}: {e}")

def wrapper(webname, config, ui_hash_file):
    local_ui_checker = UIChecker(ui_hash_file)
    return crawl_site(webname, config, local_ui_checker)

def run_requests(requests_webs, config, ui_hash_file):
    with ThreadPoolExecutor(max_workers=len(requests_webs) or 1) as executor:
        futures = [executor.submit(wrapper, w, config, ui_hash_file) for w in requests_webs]
        for future in futures:
            try:
                future.result()
            except Exception as e:
                print(f"❌ Lỗi khi crawl báo (requests): {e}")

def run_selenium(selenium_webs, config_fpath):
    processes = []
    for web in selenium_webs:
        print(f"🧪 Chạy selenium subprocess cho báo: {web}")
        p = subprocess.Popen(["python3", "run_single_crawler.py", "--webname", web, "--config", config_fpath])
        processes.append(p)

    for p in processes:
        p.wait()

def main(config_fpath):
    config = utils.get_config(config_fpath)
    log.setup_logging(log_dir=config["output_dpath"], 
                      config_fpath=config["logger_fpath"])

    webnames = config.get("webnames", [])
    ui_hash_file = config["ui_hash_file"]

    selenium_webs = [w for w in webnames if w in CRAWLERS_SELENIUM]
    requests_webs = [w for w in webnames if w not in CRAWLERS_SELENIUM]

    thread_requests = Thread(target=run_requests, args=(requests_webs, config, ui_hash_file))
    thread_selenium = Thread(target=run_selenium, args=(selenium_webs, config_fpath))

    thread_requests.start()
    thread_selenium.start()

    thread_requests.join()
    thread_selenium.join()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vietnamese News crawler")
    parser.add_argument("--config", default="crawler_config.yml", help="Path to config file", dest="config_fpath") 
    args = parser.parse_args()
    main(**vars(args))
