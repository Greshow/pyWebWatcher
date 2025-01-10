import hashlib
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr
from bs4 import BeautifulSoup
from lxml import etree
import time
import argparse
import json
import asyncio
import aiohttp
import os

# 加载 JSON 配置文件
def load_config(config_file):
    with open(config_file, 'r', encoding='utf-8') as f:
        config = json.load(f)
    return config

# 获取网页内容并计算哈希值
async def get_page_hash(session, url, xpath=None):
    try:
        async with session.get(url, timeout=10) as response:
            response.raise_for_status()
            content = await response.text()
            soup = BeautifulSoup(content, "html.parser")
            
            if xpath:
                tree = etree.HTML(str(soup))
                elements = tree.xpath(xpath)
                content_text = " ".join([elem.text for elem in elements if elem.text])
            else:
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
            targets = json.load(f)
        return targets
    except Exception as e:
        print(f"[错误] 读取目标文件失败: {e}")
        return []

# 网站监控异步函数
async def monitor_website(session, target, last_hashes, check_interval, email_config):
    url = target["url"]
    xpath = target.get("xpath")  # Get the optional XPath

    while True:
        # print(f"[监控] 正在检测 {url} 的变动...")
        current_hash = await get_page_hash(session, url, xpath)

        if current_hash is None:
            print(f"[监控] 无法获取 {url} 的网页内容，跳过本次检测")
        elif last_hashes.get(url) is None:
            last_hashes[url] = current_hash
            print(f"[监控] 初次记录 {url} 网站内容哈希值")
        elif current_hash != last_hashes.get(url):
            print(f"[警告] {url} 网站内容发生变动！")
            send_email(
                subject=f"{url} 网站变动通知",
                body=f"网站 {url} 的内容发生了变动！请检查更新。",
                email_config=email_config
            )
            last_hashes[url] = current_hash
        else:
            print(f"[监控] {url} 网站内容没有变动")

        await asyncio.sleep(check_interval)

# 检查目标文件是否被修改
async def check_target_file_modification(target_file, last_modification_time):
    while True:
        current_modification_time = os.path.getmtime(target_file)
        if current_modification_time != last_modification_time:
            print(f"[监控] 检测到 {target_file} 文件被修改")
            last_modification_time = current_modification_time
            return True, last_modification_time
        await asyncio.sleep(300)  # 每 5 秒检查一次文件修改时间

# 主程序
async def monitor_websites(target_file, check_interval, email_config):
    last_modification_time = os.path.getmtime(target_file)  # 记录文件的最后修改时间
    targets = load_target_urls(target_file)  # 启动时立即加载目标 URL
    if not targets:
        print("[监控] 没有有效的 URL 需要监控。")
        return

    last_hashes = {target["url"]: None for target in targets}  # 初始化哈希值记录
    tasks = {}  # 用于存储每个 URL 对应的监控任务

    async with aiohttp.ClientSession() as session:
        # 启动时立即开始监控所有目标 URL
        for target in targets:
            url = target["url"]
            tasks[url] = asyncio.create_task(monitor_website(session, target, last_hashes, check_interval, email_config))
            print(f"[监控] 开始监控 {url}")

        while True:
            # 检查文件是否被修改
            file_modified, last_modification_time = await check_target_file_modification(target_file, last_modification_time)
            if file_modified:
                new_targets = load_target_urls(target_file)
                # 停止已删除的 URL 的监控任务
                for target in list(tasks.keys()):
                    if target not in [t["url"] for t in new_targets]:
                        tasks[target].cancel()
                        del tasks[target]
                        del last_hashes[target]
                        print(f"[监控] 停止监控 {target}")
                # 启动新增的 URL 的监控任务
                for target in new_targets:
                    url = target["url"]
                    if url not in tasks:
                        tasks[url] = asyncio.create_task(monitor_website(session, target, last_hashes, check_interval, email_config))
                        print(f"[监控] 开始监控 {url}")
            
# 命令行参数解析
def parse_args():
    parser = argparse.ArgumentParser(description="网站变动监控脚本")
    parser.add_argument(
        "-t", "--target",
        default="target.json",
        help="指定包含网站 URL 的目标 JSON 文件"
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
    
