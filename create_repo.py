#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
在已登录的浏览器里创建 GitHub 仓库。
用法: python create_repo.py <repo-name> [public|private] [描述]
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
    name = sys.argv[1] if len(sys.argv) > 1 else "hello-world"
    vis = (sys.argv[2] if len(sys.argv) > 2 else "public").lower()
    desc = sys.argv[3] if len(sys.argv) > 3 else "我的第一个 GitHub 仓库"

    with sync_playwright() as pw:
        b = pw.chromium.connect_over_cdp(CDP)
        ctx = b.contexts[0]
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        print("打开新建仓库页...", flush=True)
        page.goto("https://github.com/new", wait_until="domcontentloaded", timeout=60000)
        time.sleep(4)

        print(f"填写仓库名: {name}", flush=True)
        page.fill("#repository-name-input", name)
        time.sleep(1)

        # 描述(可选)
        try:
            page.fill("#_r_c_", desc)
            print(f"填写描述: {desc}", flush=True)
        except Exception as e:
            print("描述跳过:", str(e)[:40], flush=True)

        # 可见性
        if vis == "private":
            try:
                page.get_by_role("radio", name="Private").check()
                print("设为 Private", flush=True)
            except Exception:
                try:
                    page.click("text=Private")
                    print("设为 Private(点击)", flush=True)
                except Exception as e:
                    print("设置 Private 失败:", str(e)[:40], flush=True)
        else:
            print("保持 Public", flush=True)

        # README 复选框: GitHub 新版是自定义控件, 多种方式尝试
        readme_ok = False
        for label in ["Add README", "Add a README file", "README"]:
            try:
                el = page.get_by_text(label, exact=False).first
                el.click(timeout=4000)
                time.sleep(1)
                readme_ok = True
                print(f"已勾选 README (匹配: {label})", flush=True)
                break
            except Exception:
                continue
        if not readme_ok:
            for sel in ["input[type=checkbox]", "[role=checkbox]",
                        "[aria-checked]", "label:has-text('README')"]:
                try:
                    els = page.query_selector_all(sel)
                    for e in els:
                        try:
                            e.click(timeout=2500)
                            readme_ok = True
                            print(f"已勾选 README (选择器: {sel})", flush=True)
                            break
                        except Exception:
                            continue
                    if readme_ok:
                        break
                except Exception:
                    continue
        if not readme_ok:
            print("!! 未找到 README 选项, 将创建空仓库(稍后本地推送 README)", flush=True)

        # 提交
        print("点击 Create repository...", flush=True)
        try:
            page.click("button[type=submit]:has-text('Create repository')", timeout=15000)
        except Exception:
            page.get_by_role("button", name="Create repository").click(timeout=15000)

        # 等待跳转
        for i in range(30):
            time.sleep(1)
            u = page.url
            if "/new" not in u:
                break
        print("\n结果 URL:", page.url, flush=True)
        print("标题    :", page.title(), flush=True)

        if f"/{name}" in page.url or page.url.rstrip("/").endswith(name):
            print(f"\n>> 仓库创建成功: {page.url}", flush=True)
        else:
            try:
                t = page.inner_text("body")
                for l in t.splitlines():
                    l = l.strip()
                    if l and ("error" in l.lower() or "already" in l.lower()
                              or "错误" in l or "已存在" in l):
                        print("   ", l[:100], flush=True)
            except Exception:
                pass


if __name__ == "__main__":
    main()
