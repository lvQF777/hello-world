#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通过网页删除仓库里的文件(无需本地 git)。
用法: python delete_file.py <owner/repo> <路径> [分支]
"""
import os
import sys
import time

for _k in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
           "ALL_PROXY", "all_proxy"]:
    os.environ.pop(_k, None)
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from playwright.sync_api import sync_playwright

CDP = "http://127.0.0.1:9222"


def visible(els):
    out = []
    for e in els:
        try:
            if e.is_visible():
                out.append(e)
        except Exception:
            continue
    return out


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return
    repo, path = sys.argv[1], sys.argv[2]
    branch = sys.argv[3] if len(sys.argv) > 3 else "main"

    url = f"https://github.com/{repo}/delete/{branch}/{path}"
    with sync_playwright() as pw:
        b = pw.chromium.connect_over_cdp(CDP)
        ctx = b.contexts[0]
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        print("打开删除页:", url, flush=True)
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        time.sleep(5)
        print("URL:", page.url, flush=True)

        # 删除按钮(红色), 文案 "Delete file"
        clicked = False
        for sel in ["button[type=submit]:has-text('Delete file')",
                    "button:has-text('Delete file')"]:
            try:
                btns = visible(page.query_selector_all(sel))
                if btns:
                    btns[-1].click(timeout=8000)
                    clicked = True
                    print(f"已点击删除 ({sel})", flush=True)
                    break
            except Exception:
                continue
        if not clicked:
            print("!! 未找到删除按钮")
            try:
                for l in page.inner_text("body").splitlines()[:30]:
                    if l.strip():
                        print("   ", l.strip()[:90])
            except Exception:
                pass
            return

        time.sleep(3)
        # 可能又弹一次确认
        for sel in ["[role=dialog] button[type=submit]",
                    "[role=dialog] button:has-text('Delete')",
                    "button:has-text('Delete this file')"]:
            try:
                btns = visible(page.query_selector_all(sel))
                if btns:
                    btns[-1].click(timeout=6000)
                    print(f"对话框确认 ({sel})", flush=True)
                    break
            except Exception:
                continue

        for i in range(30):
            time.sleep(1)
            if "/delete/" not in page.url:
                break
        print("\n结果 URL:", page.url, flush=True)


if __name__ == "__main__":
    main()
