# Sử dụng Python
FROM python:3.10

# Set thư mục làm việc
WORKDIR /app

# Copy toàn bộ code
COPY . .

# Cài đặt các dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Cài đặt Supervisor
RUN apt-get update && apt-get install -y supervisor

# Copy file cấu hình Supervisord
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Chạy Supervisor để quản lý API, Cronjob, Worker
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
