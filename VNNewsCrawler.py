import argparse
from concurrent.futures import ThreadPoolExecutor
from logger import log
from utils import utils
from crawler.factory import get_crawler
from utils.ui_checker import UIChecker


def crawl_site(webname, config, ui_checker):
    print(f"🚀 Bắt đầu crawl báo: {webname}")
    
    # Lấy URL của trang báo từ config
    base_url = config["news_sites"].get(webname, "")

    # if ui_checker.check_ui_change(base_url):
    #     print(f"UI của {webname} đã thay đổi! Bỏ qua crawling.")
    #     return

    # Tạo một bản config mới cho từng báo
    custom_config = config.copy()
    custom_config["webname"] = webname
    custom_config["output_dpath"] = f"{config['output_dpath']}/{webname}"

    # Khởi tạo crawler với config mới
    crawler = get_crawler(**custom_config)
    crawler.start_crawling()


def main(config_fpath):
    config = utils.get_config(config_fpath)
    log.setup_logging(log_dir=config["output_dpath"], 
                      config_fpath=config["logger_fpath"])
    webnames = config.get("webnames", [])
    # Khởi tạo UI Checker
    ui_checker = UIChecker(config["ui_hash_file"])

    # Sử dụng ThreadPoolExecutor để chạy song song
    with ThreadPoolExecutor(max_workers=len(webnames)) as executor:
        futures = []
        for webname in webnames:
            future = executor.submit(crawl_site, webname, config, ui_checker)
            futures.append(future)
        
        # Đợi tất cả các luồng hoàn thành
        for future in futures:
            future.result()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vietnamese News crawler (with url/type)")
    parser.add_argument("--config", 
                        default="crawler_config.yml", 
                        help="path to config file",
                        dest="config_fpath") 
    args = parser.parse_args()
    main(**vars(args))