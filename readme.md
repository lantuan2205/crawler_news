# Web Crawler - Hướng Dẫn Cài Đặt và Sử Dụng

## 1. Yêu Cầu Hệ Thống

Trước khi bắt đầu, hãy đảm bảo đã cài đặt:

- **Python** (phiên bản 3.8 trở lên)
- **Google Chrome** (dành cho Selenium)
- **ChromeDriver** (tương thích với phiên bản Chrome hiện tại)

## 2. Cài Đặt Python

Nếu chưa có Python, tải và cài đặt từ [trang chủ Python](https://www.python.org/downloads/).
Sau khi cài đặt, kiểm tra phiên bản:

```sh
python --version
```

## 3. Cài Đặt Thư Viện Yêu Cầu

Chạy lệnh sau để cài đặt các thư viện cần thiết:

```sh
pip install selenium scrapy beautifulsoup4 requests lxml webdriver-manager
```

- `selenium`: Dùng để tự động điều khiển trình duyệt
- `scrapy`: Hỗ trợ crawl dữ liệu mạnh mẽ
- `beautifulsoup4`: Phân tích và trích xuất dữ liệu HTML
- `requests`: Gửi yêu cầu HTTP
- `lxml`: Phân tích cú pháp HTML/XML nhanh chóng
- `webdriver-manager`: Tự động tải và cập nhật ChromeDriver

## 4. Cài Đặt ChromeDriver

Có thể tải ChromeDriver từ [trang chủ](https://chromedriver.chromium.org/downloads) hoặc sử dụng `webdriver-manager` để tự động cài đặt:

```python
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
```
