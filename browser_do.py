#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
连接到已启动的 Edge (远程调试端口 9222) 并执行操作。

用法:
    python browser_do.py status          检查登录状态
    python browser_do.py emails          查看邮箱验证状态
    python browser_do.py goto <url>      打开指定地址
    python browser_do.py shot <name>     截图保存
    python browser_do.py newrepo <name>  创建仓库
"""
import os
import sys
import time
import json

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 关键: 清掉环境代理, 否则访问 127.0.0.1:9222 会被本地代理拦成 502
for _k in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
           "ALL_PROXY", "all_proxy"]:
    os.environ.pop(_k, None)
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

from playwright.sync_api import sync_playwright

CDP = "http://127.0.0.1:9222"
SHOT_DIR = os.path.dirname(os.path.abspath(__file__))


def get_page(pw):
    b = pw.chromium.connect_over_cdp(CDP)
    ctx = b.contexts[0]
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    return b, ctx, page


def cmd_status(pw):
    b, ctx, page = get_page(pw)
    print("当前 URL:", page.url)
    print("标题    :", page.title())
    page.goto("https://github.com/settings/profile",
              wait_until="domcontentloaded", timeout=60000)
    time.sleep(4)
    print("\n跳转后 URL:", page.url)
    if "/login" in page.url:
        print(">> 未登录 (被重定向到登录页)")
        return
    print(">> 已登录")
    # 尝试读取页面上的账号标识
    try:
        txt = page.inner_text("body")[:1500]
        keep = [l.strip() for l in txt.splitlines() if l.strip()][:25]
        print("\n页面片段:")
        for l in keep:
            print("   ", l[:100])
    except Exception as e:
        print("读取失败:", e)


def cmd_emails(pw):
    b, ctx, page = get_page(pw)
    page.goto("https://github.com/settings/emails",
              wait_until="domcontentloaded", timeout=60000)
    time.sleep(4)
    print("URL:", page.url)
    if "/login" in page.url:
        print(">> 未登录")
        return
    try:
        txt = page.inner_text("body")
    except Exception as e:
        print("读取失败:", e); return
    print("\n=== 邮箱设置页内容 ===")
    for l in txt.splitlines():
        l = l.strip()
        if not l:
            continue
        if any(k in l for k in ["@", "Verified", "Unverified", "Primary",
                                "验证", "Save", "Resend", "Add email"]):
            print("   ", l[:110])
    page.screenshot(path=os.path.join(SHOT_DIR, "shot_emails.png"))
    print("\n截图已保存: shot_emails.png")


def cmd_goto(pw, url):
    b, ctx, page = get_page(pw)
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    time.sleep(3)
    print("URL :", page.url)
    print("标题:", page.title())


def cmd_shot(pw, name="shot"):
    b, ctx, page = get_page(pw)
    path = os.path.join(SHOT_DIR, f"{name}.png")
    page.screenshot(path=path)
    print("已保存:", path)


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__); return
    cmd = args[0]
    with sync_playwright() as pw:
        if cmd == "status":
            cmd_status(pw)
        elif cmd == "emails":
            cmd_emails(pw)
        elif cmd == "goto":
            cmd_goto(pw, args[1] if len(args) > 1 else "https://github.com")
        elif cmd == "shot":
            cmd_shot(pw, args[1] if len(args) > 1 else "shot")
        else:
            print("未知命令:", cmd)


if __name__ == "__main__":
    main()
