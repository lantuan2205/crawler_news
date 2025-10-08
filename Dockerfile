# Sử dụng Python
FROM python:3.10

# Đặt thư mục làm việc
WORKDIR /app



# Cài đặt Chromium (thay vì Google Chrome)
RUN apt-get update && \
    apt-get install -y wget unzip gnupg ca-certificates chromium chromium-driver && \
    CHROME_VERSION=$(chromium --version | grep -oE '[0-9]+' | head -1) && \
    echo "Detected Chromium version: ${CHROME_VERSION}" && \
    DRIVER_VERSION=$(wget -qO- "https://googlechromelabs.github.io/chrome-for-testing/LATEST_RELEASE_${CHROME_VERSION}") && \
    echo "Installing matching ChromeDriver version: ${DRIVER_VERSION}" && \
    wget -O /tmp/chromedriver.zip "https://storage.googleapis.com/chrome-for-testing-public/${DRIVER_VERSION}/linux64/chromedriver-linux64.zip" && \
    unzip /tmp/chromedriver.zip -d /usr/local/bin/ && \
    mv /usr/local/bin/chromedriver-linux64/chromedriver /usr/local/bin/chromedriver && \
    chmod +x /usr/local/bin/chromedriver && \
    rm -rf /tmp/chromedriver.zip && \
    apt-get clean && rm -rf /var/lib/apt/lists/*


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
