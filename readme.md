# News scraper
[![Python 3.10.7](https://img.shields.io/badge/python-3.10.7-blue)](https://www.python.org/downloads/release/python-3107/)
[![BeautifulSoup 0.0.1](https://img.shields.io/badge/BeautifulSoup-0.0.1-purple)](https://pypi.org/project/bs4/)
[![Requests 2.28.1](https://img.shields.io/badge/Requests-2.28.1-black)](https://pypi.org/project/requests/)
[![tqdm 4.64.1](https://img.shields.io/badge/tqdm-4.64.1-orange)](https://pypi.org/project/tqdm/)  

Đang support 2 báo sau:
- [VNExpress](https://vnexpress.net/)
- [VietNamNet](https://vietnamnet.vn/)

## Cài đặt môi trường
- Create virtual environment then install required packages:
```
pip install -r requirements.txt
```

## Cách dùng
- Sửa file Cấu Hình `crawler_config.yml`.

## Run
```
python VNNewsCrawler.py --config crawler_config.yml
```
