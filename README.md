# GitHub 网络诊断工具集

在受限制的网络环境下访问 GitHub 时，用于定位问题和自动修复的一组脚本。
全部基于 Python 标准库，无需安装第三方依赖。

## 包含内容

| 脚本 | 用途 |
|------|------|
| `gh_speedtest.py` | 测速并排序 GitHub 加速节点（gh-proxy 等），输出可用/失效清单 |
| `github_hosts_fix.py` | 绕过 DNS 污染：实测可用 IP，写入 hosts 并验证 |
| `browser_daemon.py` | 启动带远程调试端口的 Edge，用于浏览器自动化 |
| `browser_do.py` | 连接浏览器执行检查、截图等操作 |
| `create_repo.py` | 在浏览器内创建 GitHub 仓库 |
| `upload_files.py` | 通过网页上传文件到仓库（本机没装 git 时的替代方案） |
| `profile_setup.py` | 批量填写个人资料（昵称 / 简介等），`--dry` 可只看不改 |

## 典型用法

```bash
# 测速加速节点
python gh_speedtest.py --top 5 --save

# 修复 github.com 打不开（DNS 污染）
python github_hosts_fix.py --check        # 先看状态
python github_hosts_fix.py                # 实际修复，需管理员

# 启动可自动化的浏览器
python browser_daemon.py
python browser_do.py status
python profile_setup.py --dry            # 先看字段结构
python profile_setup.py "昵称" "一句话简介"
```

浏览器相关的四个脚本依赖 `playwright`，安装时若报找不到版本，是本地代理挡了镜像源，
用官方源并关闭代理安装：

```bash
pip install --proxy "" -i https://pypi.org/simple playwright
```

## 背景说明

这套脚本解决的问题链路：

1. `github.com` 域名被 DNS 污染 → 解析到不可达地址 → 网页打不开
2. 但 GitHub 的 IP 段本身大多可达 → 实测出可用 IP 写入 hosts 即可绕过
3. 浏览器若开启 DNS-over-HTTPS 会跳过 hosts → 需用 `--host-resolver-rules` 强制映射
4. 公共加速节点（gh-proxy 类）只代理仓库资源，不能用于浏览网页

## 环境

- Windows 11 / Python 3.13
- 修改 hosts 需要管理员权限
- 自动化脚本必须清掉 `HTTP_PROXY`/`HTTPS_PROXY` 环境变量再连 `127.0.0.1:9222`，
  否则本地代理会把调试端口请求拦成 502
