# Sử dụng Python
FROM python:3.10

# Cài đặt Supervisor
RUN apt-get update && apt-get install -y supervisor

# Đặt thư mục làm việc
WORKDIR /app

# Cài đặt thư viện Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy mã nguồn
COPY . .

# Copy file Supervisor config
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Expose cổng API
EXPOSE 8000

# Chạy Supervisor
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]