import argparse

from logger import log
from utils import utils
from crawler.factory import get_crawler


def main(config_fpath):
    config = utils.get_config(config_fpath)
    log.setup_logging(log_dir=config["output_dpath"], 
                      config_fpath=config["logger_fpath"])
    webnames = config.get("webnames", [])
    for webname in webnames:
        print(f"🚀 Bắt đầu crawl báo: {webname}")

        # Tạo một bản config mới cho từng báo
        custom_config = config.copy()
        custom_config["webname"] = webname
        custom_config["output_dpath"] = f"{config['output_dpath']}/{webname}"

        # Khởi tạo crawler với config mới
        crawler = get_crawler(**custom_config)
        crawler.start_crawling()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vietnamese News crawler (with url/type)")
    parser.add_argument("--config", 
                        default="crawler_config.yml", 
                        help="path to config file",
                        dest="config_fpath") 
    args = parser.parse_args()
    main(**vars(args))