#!/usr/bin/env python3
"""构建前校验：`src/zh/jinmantiantang` 的「账号密码登录 + 保持登录」是否仍然可用。

为什么需要这一步
----------------
本 fork 的登录功能一度是自己的实现（`Auth.kt`：网站 `/login` + cookie）。
上游 `#19278`（2026-09-25）起自带账号登录，`#20484`（2026-10-28）改为首个请求即登录 +
会话失效自愈，`#20502`（2026-10-30）又把整个模块改成 App API（JWT + 401 重登），
于是个人那套基于网站 cookie 的实现被彻底架空——新代码不再访问网站，登录永远不生效。
2026-10-29 起个人登录实现已下线，登录完全交给上游：

    设置页填「用户名 / 密码」→ `preferences.credentials` → `apiPost(apiUrl("login"))`
    → 返回带 `jwttoken` 的 MemberDto 缓存在 `session`，401 时 `withLogin` 自动重登。

这段能力是上游私有实现，**没有对外契约**。上游哪天删掉凭据设置项、改掉登录接口或
挪走 401 重试，扩展就会变成一个"填了密码也登不上"的版本，而构建照样成功、发布照样通过。
本脚本把这条链路的关键锚点钉住，让这种退化变成一次红灯。

检查项
------
1. 设置页仍有「用户名 / 密码」两项（`key = USERNAME_PREF` / `key = PASSWORD_PREF`）
2. `Preferences.kt` 的凭据键与 `credentials` 扩展仍在（键名一改，老用户凭据当场"消失"）
3. 登录接口与请求封装仍在（`login()` + `apiPost(apiUrl("login"))`）
4. 会话保持仍在：登录去重（`loginMutex`）、会话缓存（`member()`）、401 重登（`withLogin`）
5. `MemberDto.jwttoken` 仍在（收藏夹/签到都靠它带 Authorization）
6. `Auth.kt` **不得**复活：个人 cookie 登录已下线，重新出现即说明有人把废弃实现搬了回来

退出码：0 = 通过；1 = 有锚点缺失/重复（调用方应中止构建与发布）

用法：
    python3 .github/scripts/verify-login.py [--root <仓库根目录>]

只用标准库，可本地直接跑（刻意不用 shell grep：计数、多处报错与退出码更可控）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


_configure_stdout()

PKG_REL = "src/zh/jinmantiantang/src/eu/kanade/tachiyomi/extension/zh/jinmantiantang"
MAIN_FILE = "Jinmantiantang.kt"
PREFS_FILE = "Preferences.kt"
DTO_FILE = "Dto.kt"
RETIRED_FILE = "Auth.kt"

# (文件, 关键片段, 期望出现次数, 说明)
CHECKS: list[tuple[str, str, int, str]] = [
    # —— 设置页：用户能填账号密码 ——
    (MAIN_FILE, "key = USERNAME_PREF", 1, "设置页用户名项"),
    (MAIN_FILE, "key = PASSWORD_PREF", 1, "设置页密码项"),
    # —— 凭据读取 ——
    (PREFS_FILE, 'internal const val USERNAME_PREF = "username"', 1, "偏好键 username"),
    (PREFS_FILE, 'internal const val PASSWORD_PREF = "password"', 1, "偏好键 password"),
    (PREFS_FILE, "internal val SharedPreferences.credentials", 1, "凭据读取扩展"),
    (MAIN_FILE, "preferences.credentials", 1, "主类读取凭据"),
    # —— 登录接口 ——
    (MAIN_FILE, "private suspend fun login(", 1, "登录请求实现"),
    (MAIN_FILE, 'apiPost(apiUrl("login")', 1, "登录接口调用"),
    (DTO_FILE, "val jwttoken: String? = null", 1, "登录返回的 JWT 字段"),
    # —— 保持登录：去重 + 缓存 + 401 重登 ——
    (MAIN_FILE, "private val loginMutex = Mutex()", 1, "登录去重锁"),
    (MAIN_FILE, "private suspend fun member(", 1, "会话缓存入口"),
    (MAIN_FILE, "private suspend inline fun <reified T> withLogin(", 1, "会话失效后重登重试"),
    # —— 客户端链完整性（避免上游重构时把整条链换掉）——
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
    for name in (MAIN_FILE, PREFS_FILE, DTO_FILE):
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

    retired = pkg_dir / RETIRED_FILE
    if retired.exists():
        failures.append(f"{RETIRED_FILE} 重新出现：个人 cookie 登录已下线，不该再与上游实现并存")

    print("\n锚点检查：")
    for name, needle, expected, label in CHECKS:
        found = find_matches(texts[name], needle)
        ok = len(found) == expected
        mark = "ok  " if ok else "FAIL"
        print(f"  [{mark}] {name:20s} {label:22s} 期望 {expected} 处，实际 {len(found)} 处 {found}")
        if not ok:
            if not found:
                failures.append(f"{name}: 缺少 {label}（`{needle}` 未找到）")
            else:
                failures.append(f"{name}: {label} 出现 {len(found)} 处（期望 {expected}）：行 {found}")

    if failures:
        _report(failures)
        return 1

    print("\n✅ 上游账号登录链路完整（填账号密码 → 保持登录）")
    return 0


def _report(failures: list[str]) -> None:
    """把失败原因同时写进日志与检查注解（注解可用公开 API 读取）。"""
    summary = "；".join(failures)[:800]
    print("\n❌ 登录功能锚点校验失败：")
    for msg in failures:
        print(f"  - {msg}")
    print(
        "\n处理方式：这通常意味着上游改写了登录链路（设置项、凭据键、login 接口或 401 重试）。"
        "请对照上游最新实现核对锚点，更新本脚本后重试——本次不会构建、不会发布，"
        "repo 分支上仍是上一个可用版本。"
    )
    print(f"::error title=登录功能锚点校验失败::{summary}")


if __name__ == "__main__":
    sys.exit(main())
