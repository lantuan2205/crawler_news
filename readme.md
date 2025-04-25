# News scraper
[![Python 3.10.7](https://img.shields.io/badge/python-3.10.7-blue)](https://www.python.org/downloads/release/python-3107/)
[![BeautifulSoup 0.0.1](https://img.shields.io/badge/BeautifulSoup-0.0.1-purple)](https://pypi.org/project/bs4/)
[![Requests 2.28.1](https://img.shields.io/badge/Requests-2.28.1-black)](https://pypi.org/project/requests/)
[![tqdm 4.64.1](https://img.shields.io/badge/tqdm-4.64.1-orange)](https://pypi.org/project/tqdm/)  

Đang support 2 báo sau:
- [VNExpress](https://vnexpress.net/)
- [VietNamNet](https://vietnamnet.vn/)

## Cài đặt môi trường
- Requirement: python 3.10
- Tạo môi trường install package:
```
pip install -r requirements.txt
```

## Cách dùng
- Sửa file Cấu Hình `config/crawler_config.yml`.

## Run
```
python3 VNNewsCrawler.py --config config/crawler_config.yml
```



### Run Service API

- fastAPI, Uvicorn

- Run: 
```
 uvicorn app.crawl_request:app --host 0.0.0.0 --port 8000 --reload
```

- Check SwaggerAPI
```
http://127.0.0.1:8000/docs
```

