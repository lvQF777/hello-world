#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub 加速节点一键测速 / 排序工具
------------------------------------------
只用 Python 标准库，无需 pip 安装任何东西。

用法:
    python gh_speedtest.py                 # 测全部节点并排序
    python gh_speedtest.py --top 5         # 只看前 5 名
    python gh_speedtest.py --insecure      # 忽略证书错误(某些节点证书过期但仍可用)
    python gh_speedtest.py --save          # 把可用节点写入 nodes_ok.txt
    python gh_speedtest.py --add https://xxx/   # 临时追加自定义节点
    python gh_speedtest.py --file my.txt   # 从文件读取节点列表
    python gh_speedtest.py --use-proxy     # 走环境代理(默认绕过, 见下方说明)

测速方式: 每个节点真实下载同一个 GitHub raw 文件(约 700KB 的
torvalds/linux MAINTAINERS), 计时并校验内容, 避免"能连上但被劫持"的假可用节点。

关于代理(重要):
    默认【绕过】HTTP_PROXY/HTTPS_PROXY 等环境代理, 因为浏览器走的是
    Windows 系统代理(IE 设置), 而环境代理是命令行特有的。若环境里存在
    127.0.0.1 之类的本地代理, 它会劫持 DNS 并返回伪造的 502,
    导致测速结果失真。想按命令行环境测就加 --use-proxy。
"""

import argparse
import concurrent.futures
import json
import os
import socket
import ssl
import sys
import time
import urllib.request

# Windows 控制台乱码兜底
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ---------------------------------------------------------------- 配置

# 测速用的真实文件: torvalds/linux 的 MAINTAINERS, 约 700KB, 长期稳定存在
TEST_FILE = "https://raw.githubusercontent.com/torvalds/linux/master/MAINTAINERS"
EXPECT_MIN_BYTES = 100_000   # 小于这个体积视为劫持/异常
TIMEOUT = 12                 # 单个节点超时(秒)
WORKERS = 12                 # 并发数

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

# 默认候选节点(失效是常态, 脚本的价值就在于随时重测筛掉它们)
DEFAULT_NODES = [
    "https://gh-proxy.com/",
    "https://ghproxy.net/",
    "https://gh-proxy.org/",
    "https://ghfast.top/",
    "https://gh.llkk.cc/",
    "https://ghp.ci/",
    "https://ghproxy.cc/",
    "https://ghproxy.cn/",
    "https://mirror.ghproxy.com/",
    "https://github.moeyy.xyz/",
    "https://gh.99988866.xyz/",
    "https://gh.api.99988866.xyz/",
    "https://gh.xxooo.cf/",
    "https://hub.gitmirror.com/",
    "https://gh.2i.icu/",
    "https://gh.jasonz.top/",
]

# 对照组: 不走代理直连, 用来判断"加速到底有没有意义"
BASELINE = [
    ("直连 raw.githubusercontent.com", TEST_FILE),
    ("直连 github.com", "https://github.com/git/git/blob/master/README.md"),
]


# ---------------------------------------------------------------- 核心

def _sys_proxy_on() -> bool:
    """读注册表, 判断 Windows 系统代理(浏览器实际使用的)是否开启。"""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings") as k:
            return winreg.QueryValueEx(k, "ProxyEnable")[0] == 1
    except Exception:
        return False


def _build_url(prefix: str) -> str:
    """把节点前缀拼成完整的代理 URL。"""
    p = prefix.rstrip("/")
    if p.endswith(("com", "net", "org", "cc", "cn", "xyz", "cf", "top", "icu")):
        # 形如 https://gh-proxy.com/  ->  https://gh-proxy.com/<完整URL>
        p = p + "/https://"
        tail = TEST_FILE.split("://", 1)[1]
        return p + tail
    return prefix.rstrip("/") + "/" + TEST_FILE


def probe(prefix: str, insecure: bool, check_dns: bool = True) -> dict:
    """测单个节点: DNS -> 下载 -> 校验内容。"""
    res = {
        "node": prefix,
        "ok": False,
        "dns_ms": 0,
        "total_ms": 0,
        "bytes": 0,
        "speed": 0.0,
        "note": "",
    }

    host = prefix.split("//", 1)[-1].split("/")[0]
    if not host:
        res["note"] = "地址格式错误"
        return res

    # 1) DNS(仅在直连模式下判定, 代理模式下 DNS 由代理负责)
    if check_dns:
        t0 = time.time()
        try:
            socket.getaddrinfo(host, 443)
        except Exception:
            res["note"] = "DNS 解析失败(域名已失效)"
            return res
        res["dns_ms"] = int((time.time() - t0) * 1000)

    # 2) 下载
    url = _build_url(prefix)
    ctx = None
    if insecure:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    t1 = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as r:
            data = r.read()
    except Exception as e:
        res["total_ms"] = int((time.time() - t1) * 1000)
        res["note"] = _err_cn(e)
        return res

    elapsed = max(time.time() - t1, 0.001)
    res["total_ms"] = int(elapsed * 1000)
    res["bytes"] = len(data)
    res["speed"] = len(data) / elapsed / 1024  # KB/s

    # 3) 内容校验: 防止"连得上但返回的是广告页/劫持页"
    if len(data) < EXPECT_MIN_BYTES:
        res["note"] = f"返回内容异常({len(data)}B), 疑似劫持"
        return res

    res["ok"] = True
    res["note"] = "可用"
    return res


def _err_cn(e: Exception) -> str:
    s = str(e).lower()
    if "timed out" in s or "timeout" in s:
        return "连接超时"
    if "certificate" in s:
        return "证书校验失败(可加 --insecure 重试)"
    if "sslv3" in s or "handshake" in s or "ssl" in s:
        return "TLS 握手失败(节点已失效)"
    if "tunnel connection failed" in s or "502" in s:
        return "被本地代理拦截(502 Tunnel)"
    if "name or service not known" in s or "getaddrinfo" in s:
        return "DNS 解析失败"
    if "404" in s:
        return "节点返回 404"
    if "403" in s:
        return "节点拒绝(403)"
    if "connection refused" in s:
        return "连接被拒绝"
    return str(e)[:48]


GITHUB_HOME = "https://github.com/torvalds/linux"


def probe_site(node: str, insecure: bool) -> dict:
    """测"通过该节点访问 github.com 主站"——这才是大多数人真正的痛点。"""
    ctx = None
    if insecure:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    url = node.rstrip("/") + "/" + GITHUB_HOME
    t = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as r:
            data = r.read()
        el = max(time.time() - t, 0.001)
        if len(data) < 20_000:
            return {"node": node, "ok": False, "total_ms": int(el * 1000),
                    "bytes": len(data), "speed": 0.0, "note": "返回内容异常, 疑似劫持"}
        return {"node": node, "ok": True, "total_ms": int(el * 1000),
                "bytes": len(data), "speed": len(data) / el / 1024, "note": "可用"}
    except Exception as e:
        return {"node": node, "ok": False, "total_ms": int((time.time() - t) * 1000),
                "bytes": 0, "speed": 0.0, "note": _err_cn(e)}


def probe_baseline(item, insecure: bool) -> dict:
    """对照组: 直连测速。"""
    name, url = item
    ctx = None
    if insecure:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    t = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as r:
            data = r.read()
        el = max(time.time() - t, 0.001)
        return {"node": name, "ok": True, "total_ms": int(el * 1000),
                "bytes": len(data), "speed": len(data) / el / 1024,
                "note": "可用"}
    except Exception as e:
        return {"node": name, "ok": False, "total_ms": int((time.time() - t) * 1000),
                "bytes": 0, "speed": 0.0, "note": _err_cn(e)}


# ---------------------------------------------------------------- 输出

def fmt_speed(kb: float) -> str:
    if kb <= 0:
        return "-"
    if kb >= 1024:
        return f"{kb / 1024:.1f} MB/s"
    return f"{kb:.0f} KB/s"


def render(title, rows):
    print(f"\n=== {title} ===")
    print(f"{'#':>3}  {'节点':<34} {'耗时':>8} {'速度':>11}  说明")
    print("-" * 88)
    for i, r in enumerate(rows, 1):
        ms = f"{r['total_ms']}ms" if r["total_ms"] else "-"
        print(f"{i:>3}  {r['node'][:34]:<34} {ms:>8} {fmt_speed(r['speed']):>11}  {r['note']}")
    print("-" * 88)


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="GitHub 加速节点一键测速排序")
    ap.add_argument("--top", type=int, default=0, help="只显示前 N 名")
    ap.add_argument("--insecure", action="store_true", help="忽略 SSL 证书错误")
    ap.add_argument("--save", action="store_true", help="把可用节点写入 nodes_ok.txt")
    ap.add_argument("--add", nargs="*", default=[], help="追加自定义节点")
    ap.add_argument("--file", help="从文件读取节点列表(每行一个)")
    ap.add_argument("--no-baseline", action="store_true", help="跳过直连对照组")
    ap.add_argument("--use-proxy", action="store_true",
                    help="走环境代理测速(默认绕过)")
    args = ap.parse_args()

    # 代理模式处理
    env_proxies = urllib.request.getproxies()
    check_dns = True
    if not args.use_proxy:
        # 绕过 HTTP_PROXY/HTTPS_PROXY, 模拟浏览器(系统代理关闭时)的真实直连
        urllib.request.install_opener(
            urllib.request.build_opener(urllib.request.ProxyHandler({})))
    else:
        check_dns = False  # 代理自己解析域名, 本地 DNS 结果无意义

    if env_proxies:
        print(f"[提示] 检测到环境代理 {env_proxies} —— "
              f"{'本次已绕过, 模拟浏览器直连' if not args.use_proxy else '本次走该代理'}")
        print("       (Windows 系统代理状态: "
              f"{'开启' if _sys_proxy_on() else '关闭'})")

    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            nodes = [l.strip() for l in f if l.strip() and not l.startswith("#")]
    else:
        nodes = list(DEFAULT_NODES)
    nodes += list(args.add)
    # 去重保序
    seen, uniq = set(), []
    for n in nodes:
        if n not in seen:
            seen.add(n)
            uniq.append(n)

    print(f"正在测速 {len(uniq)} 个节点 (每个节点真实下载 ~700KB), 请稍候...")

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(probe, n, args.insecure, check_dns): n for n in uniq}
        done = 0
        for fu in concurrent.futures.as_completed(futs):
            done += 1
            try:
                results.append(fu.result())
            except Exception as e:
                results.append({"node": futs[fu], "ok": False, "total_ms": 0,
                                "bytes": 0, "speed": 0.0, "note": str(e)[:40]})
            print(f"\r  进度 {done}/{len(uniq)}", end="", flush=True)
    print("\r" + " " * 30 + "\r", end="")

    ok = sorted([r for r in results if r["ok"]], key=lambda r: r["speed"], reverse=True)
    bad = [r for r in results if not r["ok"]]

    if args.top:
        ok = ok[: args.top]

    if ok:
        render("可用节点 (按速度排序)", ok)
        print("\n>> 推荐填进「加速列表」的内容 (顺序即优先级):\n")
        for r in ok:
            print(f"    {r['node']}")
    else:
        print("\n!! 全部节点均不可用。建议: 挂全局代理, 或改用 --insecure 重试一次。")

    if bad:
        render("不可用节点", sorted(bad, key=lambda r: r["node"]))

    if not args.no_baseline:
        print("\n正在测试直连对照组...")
        bl = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            for fu in concurrent.futures.as_completed(
                    [ex.submit(probe_baseline, i, args.insecure) for i in BASELINE]):
                bl.append(fu.result())
        render("对照组 (不走加速)", bl)

        # 智能提示: 直连比加速还快时, 提醒别做反向优化
        raw_bl = next((r for r in bl if "raw.githubusercontent" in r["node"]), None)
        if raw_bl and raw_bl["ok"] and ok:
            best = ok[0]["speed"]
            if raw_bl["speed"] > best * 1.2:
                print(f"\n[注意] raw.githubusercontent.com 直连 {fmt_speed(raw_bl['speed'])} "
                      f"明显快于最快节点 {fmt_speed(best)}。")
                print("       => 建议只对 github.com 走加速, 把 raw.githubusercontent.com")
                print("          放进白名单/排除列表, 否则下载 release、raw 文件反而变慢。")

        # 真正的痛点: 通过节点访问 github.com 主站
        if ok:
            print("\n正在测试「通过节点访问 github.com 主站」(真正的痛点场景)...")
            top3 = [r["node"] for r in ok[:3]]
            site = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
                for fu in concurrent.futures.as_completed(
                        [ex.submit(probe_site, n, args.insecure) for n in top3]):
                    site.append(fu.result())
            render("github.com 主站加速效果", site)
            working = [r for r in site if r["ok"]]
            if working:
                b = max(working, key=lambda r: r["speed"])
                print(f"\n>> 访问 github.com 主站最快的节点: {b['node']}")
            else:
                print("\n>> 前三名均无法访问 github.com 主站, 建议换用全局代理。")

    if args.save and ok:
        out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nodes_ok.txt")
        with open(out, "w", encoding="utf-8") as f:
            f.write("# 由 gh_speedtest.py 生成于 %s\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
            for r in ok:
                f.write(r["node"] + "\n")
        print(f"\n已保存可用节点到: {out}")


if __name__ == "__main__":
    main()
