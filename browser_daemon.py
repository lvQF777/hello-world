#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
常驻守护: 启动带远程调试端口的 Edge, 并保持进程存活。

关键点:
1. Edge 默认开启 DNS-over-HTTPS, 会绕过系统 hosts 文件。
   因此这里用 --host-resolver-rules 直接把域名钉到 IP, 最可靠。
2. 守护进程常驻, 避免浏览器被回收。
3. 创建 .browser-stop 文件可让守护退出(浏览器也一起关)。
"""
import os
import socket
import subprocess
import sys
import time
import ssl
import http.client
import concurrent.futures

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILE = os.path.join(HERE, ".edge-profile")
STOP = os.path.join(HERE, ".browser-stop")
PIDFILE = os.path.join(HERE, ".edge_pid.txt")
BESTIP = os.path.join(HERE, ".best_ip.txt")
PORT = 9222

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if not os.path.exists(EDGE):
    EDGE = r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")
CANDIDATES = ["20.27.177.113", "20.205.243.166", "140.82.113.3", "140.82.112.4",
              "140.82.114.3", "140.82.113.4", "140.82.114.4", "140.82.121.3",
              "20.233.83.145", "20.200.245.247", "20.207.73.82"]


def port_open(port=PORT):
    s = socket.socket()
    s.settimeout(1)
    try:
        s.connect(("127.0.0.1", port)); s.close(); return True
    except Exception:
        try: s.close()
        except Exception: pass
        return False


def probe(ip):
    ctx = ssl.create_default_context()
    t = time.time()
    try:
        raw = socket.create_connection((ip, 443), timeout=5)
        sock = ctx.wrap_socket(raw, server_hostname="github.com")
        c = http.client.HTTPSConnection(ip, 443, timeout=5, context=ctx)
        c.sock = sock
        c.request("GET", "/login", headers={"Host": "github.com", "User-Agent": UA})
        r = c.getresponse(); d = r.read(); c.close()
        if r.status == 200 and len(d) > 5000:
            return ip, int((time.time()-t)*1000)
    except Exception:
        pass
    return None


def pick_ip():
    if os.path.exists(BESTIP):
        try:
            v = open(BESTIP).read().strip()
            if v:
                print(f"使用已记录的 IP: {v}", flush=True)
                return v
        except Exception:
            pass
    print("测速选择最快 IP...", flush=True)
    good = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=11) as ex:
        for r in ex.map(probe, CANDIDATES):
            if r: good.append(r)
    if not good:
        return None
    good.sort(key=lambda x: x[1])
    print(f"  最快: {good[0][0]} ({good[0][1]}ms)", flush=True)
    with open(BESTIP, "w") as f:
        f.write(good[0][0])
    return good[0][0]


def kill_old():
    if os.path.exists(PIDFILE):
        try:
            pid = open(PIDFILE).read().strip()
            if pid:
                subprocess.run(["taskkill", "/PID", pid, "/T", "/F"],
                               capture_output=True, timeout=20)
                print(f"已结束旧实例 pid={pid}", flush=True)
                time.sleep(2)
        except Exception as e:
            print("清理旧实例失败:", str(e)[:50], flush=True)


def main():
    # 清掉残留的停止信号, 否则刚启动就自杀
    if os.path.exists(STOP):
        try:
            os.remove(STOP)
            print("已清除残留停止信号", flush=True)
        except Exception:
            pass

    kill_old()

    ip = pick_ip()
    if not ip:
        print("!! 没有可用 IP", flush=True)
        return

    rules = f"MAP github.com {ip},MAP www.github.com {ip}"
    print(f"host-resolver-rules: {rules}", flush=True)

    cmd = [
        EDGE,
        f"--remote-debugging-port={PORT}",
        f"--user-data-dir={PROFILE}",
        f"--host-resolver-rules={rules}",
        "--no-first-run",
        "--no-default-browser-check",
        "https://github.com/login",
    ]
    print("启动 Edge...", flush=True)
    p = subprocess.Popen(cmd)
    with open(PIDFILE, "w") as f:
        f.write(str(p.pid))
    print("pid:", p.pid, flush=True)

    for i in range(40):
        time.sleep(1)
        if port_open():
            print(f"[READY] 调试端口 {PORT} 就绪", flush=True)
            print(f"[READY] 已强制 github.com -> {ip}", flush=True)
            print("[READY] 登录页: https://github.com/login", flush=True)
            break
    else:
        print("!! 端口未就绪", flush=True)
        return

    print("守护中...", flush=True)
    tick = 0
    while True:
        time.sleep(3)
        tick += 1
        if os.path.exists(STOP):
            print("收到停止信号", flush=True)
            kill_old()
            try: os.remove(STOP)
            except Exception: pass
            break
        if tick % 20 == 0:
            print(f"  存活 {tick*3}s, 端口: {port_open()}", flush=True)


if __name__ == "__main__":
    main()
