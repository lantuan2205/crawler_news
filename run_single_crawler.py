import argparse
from utils import utils
from news_crawler.factory import get_crawler
from utils.ui_checker import UIChecker

def crawl_site(webname, config, ui_checker):
    print(f"🚀 [Subprocess] Bắt đầu crawl báo: {webname}")
    base_url = config["news_sites"].get(webname, "")
    
    custom_config = config.copy()
    custom_config["webname"] = webname
    custom_config["output_dpath"] = f"{config['output_dpath']}/{webname}"
    
    crawler = get_crawler(**custom_config)
    try:
        crawler.start_crawling()
    except Exception as e:
        print(f"❌ Lỗi khi chạy crawler trong subprocess cho {webname}: {e}")

def main(webname, config_fpath):
    config = utils.get_config(config_fpath)
    ui_checker = UIChecker(config["ui_hash_file"])
    crawl_site(webname, config, ui_checker)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--webname", required=True)
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    main(args.webname, args.config)

