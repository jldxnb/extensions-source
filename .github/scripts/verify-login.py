#!/usr/bin/env python3
"""构建前校验：fork 自己加的「账号登录」是否仍然完整挂在扩展上。

为什么需要这一步
----------------
上游会改动 `src/zh/jinmantiantang/Jinmantiantang.kt`。只要上游的改动和我们的插桩
不在同一处，git 就会**静默自动合并成功**——构建照样通过，但挂载点可能被挤掉或
被重复插入，于是发布出一个「没有登录功能」的版本，而且没有任何信号。
（真正的冲突反而安全：sync-upstream 会 abort 整个合并，上一版继续可用。）

检查项
------
1. `Auth.kt` 仍然存在，且包含 AuthManager / login() / intercept() / addAuthPreferences()
2. `Auth.kt` 的三个偏好键常量仍在（改了键名会导致老用户凭据"消失"）
3. `Jinmantiantang.kt` 中 AuthManager 的构造与拦截器挂载各**恰好 1 处**（0 = 被挤掉，2 = 被重复插入）
4. 原有的镜像自愈与图片还原拦截器仍在链上（避免上游重构 client 时把整条链换掉）

退出码：0 = 通过；1 = 有锚点缺失/重复（调用方应中止构建与发布）

用法：
    python3 .github/scripts/verify-login.py [--root <仓库根目录>]

只用标准库，可本地直接跑（刻意不用 shell grep：计数、多处报错与退出码更可控）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PKG_REL = "src/zh/jinmantiantang/src/eu/kanade/tachiyomi/extension/zh/jinmantiantang"
AUTH_FILE = "Auth.kt"
MAIN_FILE = "Jinmantiantang.kt"

# (文件, 关键片段, 期望出现次数, 说明)
CHECKS: list[tuple[str, str, int, str]] = [
    (AUTH_FILE, "internal class AuthManager(", 1, "AuthManager 类"),
    (AUTH_FILE, "fun login()", 1, "登录请求实现"),
    (AUTH_FILE, "fun intercept(chain: Interceptor.Chain): Response", 1, "请求拦截与自愈"),
    (AUTH_FILE, "internal fun addAuthPreferences(", 1, "账号设置项"),
    (AUTH_FILE, 'internal const val USERNAME_PREF = "jmUsername"', 1, "偏好键 USERNAME_PREF"),
    (AUTH_FILE, 'internal const val PASSWORD_PREF = "jmPassword"', 1, "偏好键 PASSWORD_PREF"),
    (AUTH_FILE, 'internal const val LOGGED_IN_HOST_PREF = "jmLoggedInHost"', 1, "偏好键 LOGGED_IN_HOST_PREF"),
    (AUTH_FILE, "private const val LOGIN_ERROR_PATH", 1, "会话失效判据常量"),
    (MAIN_FILE, "= AuthManager(", 1, "主类中构造 AuthManager"),
    (MAIN_FILE, "authManager.intercept(chain)", 1, "把登录拦截器挂到 client 链上"),
    (MAIN_FILE, "addAuthPreferences(screen, preferences)", 1, "设置页接入账号设置项"),
    (MAIN_FILE, "interceptors().add(0, updateUrlInterceptor)", 1, "镜像自愈拦截器仍在链上"),
    (MAIN_FILE, "addInterceptor(ScrambledImageInterceptor)", 1, "图片还原拦截器仍在链上"),
]


def find_matches(text: str, needle: str) -> list[int]:
    return [i + 1 for i, line in enumerate(text.splitlines()) if needle in line]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        default=str(Path(__file__).resolve().parents[2]),
        help="仓库根目录（默认按脚本位置推断）",
    )
    args = parser.parse_args()

    pkg_dir = Path(args.root).resolve() / PKG_REL
    print(f"检查目录: {pkg_dir}")

    texts: dict[str, str] = {}
    failures: list[str] = []
    for name in (AUTH_FILE, MAIN_FILE):
        path = pkg_dir / name
        if not path.is_file():
            failures.append(f"{name} 不存在：{path}")
        else:
            texts[name] = path.read_text(encoding="utf-8")

    if failures:
        for msg in failures:
            print(f"[缺失] {msg}")
        _report(failures)
        return 1

    print("\n锚点检查：")
    for name, needle, expected, label in CHECKS:
        found = find_matches(texts[name], needle)
        ok = len(found) == expected
        mark = "ok  " if ok else "FAIL"
        print(f"  [{mark}] {name:22s} {label:28s} 期望 {expected} 处，实际 {len(found)} 处 {found}")
        if not ok:
            if not found:
                failures.append(f"{name}: 缺少 {label}（`{needle}` 未找到）")
            else:
                failures.append(f"{name}: {label} 出现 {len(found)} 处（期望 {expected}）：行 {found}")

    if failures:
        _report(failures)
        return 1

    print("\n✅ 登录功能锚点完整")
    return 0


def _report(failures: list[str]) -> None:
    """把失败原因同时写进日志与检查注解（注解可用公开 API 读取）。"""
    summary = "；".join(failures)[:800]
    print("\n❌ 登录功能锚点校验失败：")
    for msg in failures:
        print(f"  - {msg}")
    print(
        "\n处理方式：这通常意味着上游改写了 Jinmantiantang.kt 或 Auth.kt，"
        "把我们的插桩挤掉或重复插入了。请人工核对 docs/jinmantiantang/08-login.md "
        "§14.7.3 与 §14.8 的 4 个挂载点后重试——本次不会构建、不会发布，"
        "repo 分支上仍是上一个可用版本。"
    )
    print(f"::error title=登录功能锚点校验失败::{summary}")


if __name__ == "__main__":
    sys.exit(main())
