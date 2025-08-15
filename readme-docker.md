# Hướng dẫn triển khai Docker cho FastAPI và Cron Job

Dự án này hướng dẫn cách triển khai một ứng dụng FastAPI cùng với một cron job trong cùng một container Docker, được quản lý bởi Supervisor.

## Cấu trúc
- **docker-compose.yml**: Tệp cấu hình Docker Compose.
- **Dockerfile**: Tệp định nghĩa cách xây dựng image Docker.
- **supervisord.conf**: Tệp cấu hình Supervisor để quản lý các tiến trình.
- **api/**: Thư mục chứa mã nguồn của ứng dụng FastAPI.
- **cron/**: Thư mục chứa mã nguồn của cron job.

## Hướng dẫn sử dụng

### 1. Build image Docker

Trong thư mục gốc của dự án, chạy lệnh sau để xây dựng image Docker:

```bash
docker compose build
```

### 2. Khởi động dịch vụ

Sau khi build xong, khởi động dịch vụ bằng lệnh:

```bash
docker compose up -d
```

Lệnh này sẽ chạy container ở chế độ nền.

### 3. Kiểm tra logs

Để xem logs của dịch vụ, sử dụng lệnh:

```bash
docker compose logs -f
```

### 4. Truy cập API

Sau khi dịch vụ đã khởi động, bạn có thể truy cập API tại: [http://localhost:8000](http://localhost:8000)

Nếu FastAPI được cấu hình với Swagger UI, bạn có thể truy cập tài liệu API tại: [http://localhost:8000/docs](http://localhost:8000/docs)
