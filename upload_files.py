#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通过网页上传文件到 GitHub 仓库(无需本地 git)。
用法: python upload_files.py <owner/repo> <文件1> [文件2 ...]
"""
import os
import sys
import time

for _k in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
           "ALL_PROXY", "all_proxy"]:
    os.environ.pop(_k, None)
os.environ["NO_PROXY"] = "*"
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from playwright.sync_api import sync_playwright

CDP = "http://127.0.0.1:9222"


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return
    repo = sys.argv[1]
    files = [os.path.abspath(f) for f in sys.argv[2:]]
    for f in files:
        if not os.path.exists(f):
            print("!! 文件不存在:", f)
            return

    url = f"https://github.com/{repo}/upload"
    with sync_playwright() as pw:
        b = pw.chromium.connect_over_cdp(CDP)
        ctx = b.contexts[0]
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        print("打开上传页:", url, flush=True)
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        time.sleep(4)
        print("当前 URL:", page.url, flush=True)

        # 找 file input
        fi = None
        for sel in ["input[type=file]", "input[type='file']"]:
            try:
                els = page.query_selector_all(sel)
                if els:
                    fi = els[0]
                    print(f"找到上传控件 ({sel}), 共 {len(els)} 个", flush=True)
                    break
            except Exception:
                continue
        if not fi:
            print("!! 未找到文件上传控件")
            try:
                print(page.inner_text("body")[:600])
            except Exception:
                pass
            return

        print("上传文件:", [os.path.basename(f) for f in files], flush=True)
        fi.set_input_files(files)
        time.sleep(8)

        # 提交
        for label in ["Commit changes", "Commit", "提交"]:
            try:
                page.click(f"button:has-text('{label}')", timeout=8000)
                print(f"点击提交 ({label})", flush=True)
                break
            except Exception:
                continue

        for i in range(30):
            time.sleep(1)
            if "/upload" not in page.url:
                break
        print("\n结果 URL:", page.url, flush=True)
        print("标题    :", page.title(), flush=True)


if __name__ == "__main__":
    main()
