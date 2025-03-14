# Sử dụng Python
FROM python:3.10

# Set thư mục làm việc
WORKDIR /app

# Copy toàn bộ code vào container
COPY . .

# Cài đặt dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Cài đặt supervisor
RUN apt-get update && apt-get install -y supervisor

# Copy file cấu hình supervisor
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Chạy supervisor để quản lý API và cronjob
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
