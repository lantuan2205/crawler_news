import subprocess
import time
from datetime import datetime, timedelta

def run_cron_job():
    while True:
        now = datetime.now()
        print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Running daily cron job...")

        cmd = ["python", "./crawler/VNNewsCrawler.py", "--config", "crawler_config.yml"]
        subprocess.run(cmd)

        # Chạy vào 00:00 ngày hôm sau
        next_run_time = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        sleep_time = (next_run_time - datetime.now()).total_seconds()
        
        print(f"Next run at: {next_run_time.strftime('%Y-%m-%d %H:%M:%S')}")
        time.sleep(max(sleep_time, 1))

if __name__ == "__main__":
    run_cron_job()
