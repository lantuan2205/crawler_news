# Sử dụng Python
FROM python:3.10

# Đặt thư mục làm việc
WORKDIR /app



# Cài đặt Chromium (thay vì Google Chrome)
RUN apt-get update && apt-get install -y wget unzip chromium
RUN CHROME_VERSION=142.0.7444.59 && \
    wget -O /tmp/chromedriver.zip "https://storage.googleapis.com/chrome-for-testing-public/$CHROME_VERSION/linux64/chromedriver-linux64.zip" && \
    unzip /tmp/chromedriver.zip -d /usr/local/bin/ && \
    rm /tmp/chromedriver.zip


# Cài đặt thư viện Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy mã nguồn
COPY . .

# Chạy Commandline
#CMD ["python","-m" , "app/crawl_request.py"]

# Copy entrypoint.sh
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Entrypoint chạy script
ENTRYPOINT ["/app/entrypoint.sh"]
