import subprocess
import time
from datetime import datetime, timedelta

def run_cron_job():
    while True:
        now = datetime.now()
        print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Running daily cron job...")

        cmd = ["python", "./VNNewsCrawler.py", "--config", "config/crawler_config.yml"]
        subprocess.run(cmd)

        # Xác định thời gian chạy tiếp theo vào 12:00 PM ngày hôm sau
        next_run_time = now.replace(hour=12, minute=0, second=0, microsecond=0)
        if now >= next_run_time:  # Nếu đã qua 12h trưa hôm nay, đặt lại thành trưa ngày mai
            next_run_time += timedelta(days=1)

        sleep_time = (next_run_time - datetime.now()).total_seconds()
        
        print(f"Next run at: {next_run_time.strftime('%Y-%m-%d %H:%M:%S')}")
        time.sleep(max(sleep_time, 1))

if __name__ == "__main__":
    run_cron_job()