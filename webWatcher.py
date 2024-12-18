import hashlib
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr
from bs4 import BeautifulSoup
import time
import argparse
import json
import asyncio
import aiohttp

# 加载 JSON 配置文件
def load_config(config_file):
    with open(config_file, 'r', encoding='utf-8') as f:
        config = json.load(f)
    return config

# 获取网页内容并计算哈希值
async def get_page_hash(session, url):
    try:
        async with session.get(url, timeout=10) as response:
            response.raise_for_status()
            content = await response.text()
            soup = BeautifulSoup(content, "html.parser")
            content_text = soup.get_text()  # 提取文本内容
            page_hash = hashlib.sha256(content_text.encode("utf-8")).hexdigest()
            return page_hash
    except Exception as e:
        print(f"[错误] 获取网页内容失败: {e}")
        return None

# 发送邮件通知
def send_email(subject, body, email_config):
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["From"] = email_config["sender_email"]
        msg["To"] = email_config["recipient_email"]
        msg["Subject"] = subject

        with smtplib.SMTP_SSL(email_config["smtp_server"], email_config["smtp_port"]) as server:
            server.login(email_config["sender_email"], email_config["sender_password"])
            server.sendmail(email_config["sender_email"], email_config["recipient_email"], msg.as_string())
        print("[邮件通知] 邮件发送成功")
    except Exception as e:
        print(f"[邮件通知] 邮件发送失败: {e}")

# 读取目标文件中的网站 URL
def load_target_urls(target_file):
    try:
        with open(target_file, 'r', encoding='utf-8') as f:
            urls = [line.strip() for line in f.readlines() if line.strip()]
        return urls
    except Exception as e:
        print(f"[错误] 读取目标文件失败: {e}")
        return []

# 网站监控异步函数
async def monitor_website(session, target_url, last_hashes, check_interval, email_config):
    while True:
        print(f"[监控] 正在检测 {target_url} 的变动...")
        current_hash = await get_page_hash(session, target_url)

        if current_hash is None:
            print(f"[监控] 无法获取 {target_url} 的网页内容，跳过本次检测")
        elif last_hashes.get(target_url) is None:
            last_hashes[target_url] = current_hash
            print(f"[监控] 初次记录 {target_url} 网站内容哈希值")
        elif current_hash != last_hashes.get(target_url):
            print(f"[警告] {target_url} 网站内容发生变动！")
            send_email(
                subject=f"{target_url} 网站变动通知",
                body=f"网站 {target_url} 的内容发生了变动！请检查更新。",
                email_config=email_config
            )
            last_hashes[target_url] = current_hash
        else:
            print(f"[监控] {target_url} 网站内容没有变化")

        await asyncio.sleep(check_interval)

# 主程序
async def monitor_websites(target_file, check_interval, email_config):
    target_urls = load_target_urls(target_file)
    if not target_urls:
        print("[监控] 没有有效的 URL 需要监控。")
        return

    last_hashes = {url: None for url in target_urls}
    async with aiohttp.ClientSession() as session:
        tasks = []
        for target_url in target_urls:
            tasks.append(monitor_website(session, target_url, last_hashes, check_interval, email_config))

        await asyncio.gather(*tasks)

# 命令行参数解析
def parse_args():
    parser = argparse.ArgumentParser(description="网站变动监控脚本")
    parser.add_argument(
        "-t", "--target",
        default="target.txt",
        help="指定包含网站 URL 的目标 TXT 文件"
    )
    parser.add_argument(
        "-c", "--config",
        default="config.json",
        help="指定配置文件路径（默认: config.json）"
    )
    return parser.parse_args()

if __name__ == "__main__":
    # 解析命令行参数
    args = parse_args()

    # 加载配置文件
    config = load_config(args.config)

    # 获取配置
    check_interval = int(config["monitor"]["check_interval"])
    email_config = {
        "smtp_server": config["email"]["smtp_server"],
        "smtp_port": int(config["email"]["smtp_port"]),
        "sender_email": config["email"]["sender_email"],
        "sender_password": config["email"]["sender_password"],
        "recipient_email": config["email"]["recipient_email"],
    }

    # 启动监控
    asyncio.run(monitor_websites(args.target, check_interval, email_config))
