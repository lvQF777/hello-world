#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
填写 GitHub 个人资料 (settings/profile)。

用法:
    python profile_setup.py                      使用内置默认值
    python profile_setup.py "昵称" "一句话简介"    自定义
    python profile_setup.py --dry                只看页面结构, 不改任何东西
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
URL = "https://github.com/settings/profile"

# 默认值
DEFAULT_NAME = "lvQF777"
DEFAULT_BIO = "刚开始使用 GitHub，正在学习中"

# GitHub 资料页字段 -> CSS 选择器(按优先级尝试)
# 注意: 昵称输入框的 id 是 user_display_name, 不是 user_profile_name
FIELDS = [
    ("Name",     ["#user_display_name", "#user_profile_name"]),
    ("Bio",      ["#user_profile_bio"]),
    ("Blog",     ["#user_profile_blog"]),
    ("Company",  ["#user_profile_company"]),
    ("Location", ["#user_profile_location"]),
]


def safe_fill(page, label, sels, value, dry=False):
    """填入一个字段, 依次尝试多个选择器, 返回是否成功。"""
    if not value:
        return None
    if isinstance(sels, str):
        sels = [sels]
    if dry:
        print(f"  [dry] {label}: 将填入 {value!r}")
        return None
    for sel in sels:
        try:
            el = page.query_selector(sel)
            if not el:
                continue
            el.click(timeout=3000)
            page.fill(sel, value, timeout=5000)
            time.sleep(0.4)
            print(f"  + {label}: {value}")
            return True
        except Exception as e:
            print(f"  ! {label} 用 {sel} 失败: {str(e)[:50]}")
            continue
    print(f"  - {label}: 所有选择器都未找到 {sels}")
    return False


def read_field(page, sels):
    """读取字段当前值, 找不到返回 None。"""
    if isinstance(sels, str):
        sels = [sels]
    for sel in sels:
        try:
            el = page.query_selector(sel)
            if el:
                return el.input_value()
        except Exception:
            continue
    return None


def main():
    args = [a for a in sys.argv[1:]]
    dry = "--dry" in args
    args = [a for a in args if a != "--dry"]

    name = args[0] if len(args) > 0 else DEFAULT_NAME
    bio = args[1] if len(args) > 1 else DEFAULT_BIO

    with sync_playwright() as pw:
        b = pw.chromium.connect_over_cdp(CDP)
        ctx = b.contexts[0]
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        print("打开资料页...", flush=True)
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(5)
        print("URL:", page.url, flush=True)
        if "/login" in page.url:
            print(">> 未登录, 请先登录")
            return

        if dry:
            print("\n=== 页面上的输入框 ===")
            for el in page.query_selector_all("input, textarea"):
                try:
                    i = el.get_attribute("id") or ""
                    n = el.get_attribute("name") or ""
                    p = el.get_attribute("placeholder") or ""
                    if any(k in (i + n).lower() for k in
                           ["profile", "bio", "blog", "company", "location",
                            "twitter", "name"]):
                        print(f"   id={i!r:38} name={n!r:26} ph={p!r}")
                except Exception:
                    pass
            print()
        else:
            # 先读一遍现有值, 避免覆盖掉用户自己填过的内容
            print("\n当前值:")
            for label, sels in FIELDS:
                v = read_field(page, sels)
                if v is not None:
                    print(f"   {label}: {v!r}")

        print("\n填写:")
        safe_fill(page, "Name", dict(FIELDS)["Name"], name, dry)
        safe_fill(page, "Bio", dict(FIELDS)["Bio"], bio, dry)

        if dry:
            print("\n[dry] 未做任何修改")
            return

        # 提交
        print("\n点击 Update profile...", flush=True)
        clicked = False
        for sel in ["button[type=submit]:has-text('Update profile')",
                    "button:has-text('Update profile')"]:
            try:
                page.click(sel, timeout=8000)
                clicked = True
                break
            except Exception:
                continue
        if not clicked:
            try:
                page.get_by_role("button", name="Update profile").click(timeout=8000)
                clicked = True
            except Exception as e:
                print("提交按钮点击失败:", str(e)[:80], flush=True)
        if not clicked:
            return

        time.sleep(5)
        print("\n提交后 URL:", page.url, flush=True)

        # 校验: 重新打开页面看是否保存成功
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(4)
        print("\n回读校验:")
        ok = True
        d = dict(FIELDS)
        for label, expect in [("Name", name), ("Bio", bio)]:
            v = read_field(page, d[label])
            hit = (v == expect)
            ok = ok and hit
            print(f"   {label}: {v!r}  {'OK' if hit else 'MISMATCH'}")

        # 看看有没有错误提示
        try:
            t = page.inner_text("body")
            for l in t.splitlines():
                l = l.strip()
                if l and ("error" in l.lower() or "failed" in l.lower()
                          or "错误" in l or "失败" in l):
                    print("   提示:", l[:100])
        except Exception:
            pass

        print("\n>> 资料更新完成" if ok else "\n>> 部分字段可能未生效, 建议手动确认")


if __name__ == "__main__":
    main()
