# Sử dụng Python
FROM python:3.10

# Đặt thư mục làm việc
WORKDIR /app

# Cài đặt thư viện Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy mã nguồn
COPY . .

# Chạy Commandline
CMD ["python", "app/crawl_request.py"]