#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub 官网 hosts 修复工具 (DNS 污染绕过)
------------------------------------------------
现象: api.github.com / raw.githubusercontent.com 都通, 唯独 github.com 打不开。
原因: github.com 的 DNS 被污染, 解析到不可达地址。GitHub 的 IP 段本身是可达的。
做法: 实测出可直连的 GitHub IP, 写进 hosts 让浏览器直接连 IP。

用法:
    python github_hosts_fix.py            # 测速选最快 IP 并写入 hosts (需管理员)
    python github_hosts_fix.py --check    # 只检查当前状态, 不改任何东西
    python github_hosts_fix.py --restore  # 从备份恢复 hosts
    python github_hosts_fix.py --dry      # 只测速并打印将要写入的内容, 不写入
    python github_hosts_fix.py --ip 1.2.3.4   # 跳过测速, 直接把该 IP 写进 hosts

注意: 修改 hosts 需要管理员权限。若提示权限不足, 请用"以管理员身份运行"
      的终端重新执行本脚本。
"""

import os
import re
import socket
import ssl
import sys
import time
import shutil
import http.client
import concurrent.futures

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HOSTS = r"C:\Windows\System32\drivers\etc\hosts"
BACKUP_DIR = os.path.dirname(os.path.abspath(__file__))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

# 经实测可返回完整 GitHub 首页的 IP。140.82.112.0/20 是 GitHub 官方 web 段,
# 稳定性高于 Azure 临时 CDN 节点, 故排在前面。
CANDIDATES = [
    "140.82.113.3", "140.82.112.4", "140.82.114.3", "140.82.113.4",
    "140.82.114.4", "140.82.112.3",
    "20.205.243.166", "20.233.83.145", "20.200.245.247", "20.207.73.82",
]
DOMAINS = ["github.com", "www.github.com"]
MARKER = "# >>> github-hosts-fix >>>"


# ----------------------------------------------------------- 测速

def probe(ip: str, timeout=10):
    """用该 IP 直连拉取 GitHub 首页, 返回 (ip, 耗时ms, 大小) 或 None。"""
    ctx = ssl.create_default_context()
    t = time.time()
    try:
        raw = socket.create_connection((ip, 443), timeout=timeout)
        sock = ctx.wrap_socket(raw, server_hostname="github.com")
        c = http.client.HTTPSConnection(ip, 443, timeout=timeout, context=ctx)
        c.sock = sock
        c.request("GET", "/", headers={"Host": "github.com",
                                       "User-Agent": UA, "Accept": "text/html"})
        r = c.getresponse()
        data = r.read()
        c.close()
        if r.status == 200 and len(data) > 100_000:
            return ip, int((time.time() - t) * 1000), len(data)
    except Exception:
        pass
    return None


def pick_fastest(verbose=True):
    if verbose:
        print(f"正在实测 {len(CANDIDATES)} 个 GitHub IP (真实拉取首页)...")
    good = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        for r in ex.map(probe, CANDIDATES):
            if r:
                good.append(r)
                if verbose:
                    print(f"   [OK]   {r[0]:<18} {r[1]:>5}ms  {r[2]}B")
            elif verbose:
                print(f"   [FAIL] {r[0]}")
    if not good:
        return None, []
    good.sort(key=lambda x: x[1])
    return good[0][0], good


# ----------------------------------------------------------- hosts 读写

def read_hosts():
    try:
        with open(HOSTS, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except PermissionError:
        return None
    except FileNotFoundError:
        return ""


def strip_github_entries(text: str) -> str:
    """删掉旧的 github.com / www.github.com 映射行, 保留其余内容。"""
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            out.append(line)
            continue
        parts = s.split()
        # 形如:  IP  github.com [www.github.com ...]
        hosts_in_line = [p.lower() for p in parts[1:]]
        if any(h in ("github.com", "www.github.com") for h in hosts_in_line):
            continue  # 丢弃, 稍后统一写入
        out.append(line)
    return "\n".join(out)


def write_hosts(ip: str):
    old = read_hosts()
    if old is None:
        raise PermissionError("没有权限读取 hosts, 请用管理员身份运行")

    backup = os.path.join(
        BACKUP_DIR, f"hosts.backup.{time.strftime('%Y%m%d-%H%M%S')}.txt")
    shutil.copy2(HOSTS, backup)

    cleaned = strip_github_entries(old).rstrip("\n")
    block = (f"\n{MARKER}\n"
             f"# 由 github_hosts_fix.py 写入于 {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
             f"# 备份: {backup}\n"
             f"{ip}\tgithub.com\n"
             f"{ip}\twww.github.com\n"
             f"{MARKER}\n")
    with open(HOSTS, "w", encoding="utf-8") as f:
        f.write(cleaned + block)
    return backup


def restore():
    import glob
    files = sorted(glob.glob(os.path.join(BACKUP_DIR, "hosts.backup.*.txt")),
                   reverse=True)
    if not files:
        print("没有找到备份文件。")
        return False
    latest = files[0]
    try:
        shutil.copy2(latest, HOSTS)
        print(f"已从 {os.path.basename(latest)} 恢复 hosts。")
        return True
    except PermissionError:
        print("权限不足, 请用管理员身份运行。")
        return False


# ----------------------------------------------------------- 检查

def check():
    print("=== 当前状态 ===")
    try:
        ip = socket.gethostbyname("github.com")
        print(f"  github.com 当前解析 -> {ip}")
    except Exception as e:
        print(f"  github.com 解析失败: {e}")
        ip = None

    txt = read_hosts()
    if txt is None:
        print("  (无权限读取 hosts)")
    else:
        lines = [l.strip() for l in txt.splitlines()
                 if "github.com" in l.lower() and not l.strip().startswith("#")]
        if lines:
            print("  hosts 中的 GitHub 条目:")
            for l in lines:
                print("    ", l)
        else:
            print("  hosts 中没有 GitHub 条目")

    # 实测能否打开首页
    t = time.time()
    try:
        ctx = ssl.create_default_context()
        raw = socket.create_connection(("github.com", 443), timeout=12)
        sock = ctx.wrap_socket(raw, server_hostname="github.com")
        c = http.client.HTTPSConnection("github.com", 443, timeout=12, context=ctx)
        c.sock = sock
        c.request("GET", "/", headers={"Host": "github.com", "User-Agent": UA})
        r = c.getresponse()
        d = r.read()
        c.close()
        print(f"  访问 https://github.com/ -> HTTP {r.status}, "
              f"{len(d)}B, {int((time.time()-t)*1000)}ms")
    except Exception as e:
        print(f"  访问 https://github.com/ -> 失败: {str(e)[:60]}")
    return txt


# ----------------------------------------------------------- main

def main():
    args = sys.argv[1:]
    if "--restore" in args:
        restore()
        return
    if "--check" in args:
        check()
        return

    forced = None
    if "--ip" in args:
        i = args.index("--ip")
        if i + 1 < len(args):
            forced = args[i + 1].lstrip("-")
            print(f"已指定 IP: {forced} (跳过测速)")

    ip = forced
    good = [(forced, 0, 0)] if forced else (None, [])
    if not ip:
        ip, good = pick_fastest()
    if not ip:
        print("\n!! 所有候选 IP 均不可用, hosts 方案此刻无效。")
        print("   建议改用真代理(Clash/VPN)访问。")
        return

    if forced:
        print(f"\n>> 使用指定 IP: {ip}")
    else:
        print(f"\n>> 最快可用 IP: {ip} ({good[0][1]}ms), 共 {len(good)} 个可用")

    if "--dry" in args:
        print("\n[演练模式] 将写入以下内容到 hosts, 本次未做修改:")
        print(f"    {ip}\tgithub.com")
        print(f"    {ip}\twww.github.com")
        return

    try:
        backup = write_hosts(ip)
    except PermissionError:
        print("\n!! 权限不足, 无法写入 hosts。")
        print("   请右键终端 -> 以管理员身份运行, 再执行:")
        print(f"   python {os.path.abspath(__file__)}")
        return

    print(f"\n已写入 hosts (原文件已备份到: {os.path.basename(backup)})")
    print(f"    {ip}\tgithub.com")
    print(f"    {ip}\twww.github.com")
    print("\n=== 写入后验证 ===")
    check()
    print("\n提示: 浏览器可能有 DNS 缓存, 若仍打不开, 执行 ipconfig /flushdns 或重启浏览器。")


if __name__ == "__main__":
    main()
