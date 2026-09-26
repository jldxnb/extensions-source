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
1. `Auth.kt` 仍然存在，且包含 AuthManager / login() / loginOnStartup() / reLogin() /
   intercept() / addAuthStatusPreference() / 旧凭据迁移
2. `Auth.kt` **不得**再声明 `USERNAME_PREF` / `PASSWORD_PREF`：上游 1.6.59 起在
   `Preferences.kt` 顶层声明了同名常量，同包重名会直接编译失败
3. 上游 `Preferences.kt` 的凭据键与 `clearSessionCookies()` 仍在（我们复用它们；
   上游改名 → 登录静默失效，必须报警）
4. `Jinmantiantang.kt` 中 AuthManager 的构造、拦截器挂载、设置页入口与启动登录各**恰好 1 处**
   （0 = 被挤掉，2 = 被重复插入）
5. 挂载点本身、图片还原拦截器与上游 `LoginInterceptor` 仍在链上——个人拦截器**必须**排在
   上游 LoginInterceptor 之前，会话失效自愈要靠重放请求让它在下游跟着生效

上游相关变更（改变过锚点，勿重复踩）
----------------------------------
* 2026-09-22 `#19244`：迁移到 KeiSource 1.6，主类改为 `configureClient()` 挂拦截器，
  镜像自愈一度变成 `build.gradle.kts` 的 `baseUrl { custom(...) }`，
  因此锚点从 `interceptors().add(0, updateUrlInterceptor)` 换成 `configureClient()`。
* 2026-09-25 `#19278`：上游**自己实现了账号登录**（`LoginInterceptor`，只按 `jmc_id`
  cookie 是否存在触发，没有启动登录与会话失效自愈），并恢复了模块自带的镜像/限速偏好，
  顶部重新定义了 `USERNAME_PREF`/`PASSWORD_PREF`。
  个人实现保留为主路径、与上游共用这两个键，旧键（`jmUsername`/`jmPassword`）由
  `migrateLegacyCredentials()` 一次性搬运；设置页的账号/密码两项改用上游那套，
  个人只补一行「登录状态」。

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
AUTH_FILE = "Auth.kt"
MAIN_FILE = "Jinmantiantang.kt"
PREFS_FILE = "Preferences.kt"

# (文件, 关键片段, 期望出现次数, 说明)
CHECKS: list[tuple[str, str, int, str]] = [
    # —— Auth.kt：个人登录实现本体 ——
    (AUTH_FILE, "internal class AuthManager(", 1, "AuthManager 类"),
    (AUTH_FILE, "fun login()", 1, "登录请求实现"),
    (AUTH_FILE, "fun loginOnStartup()", 1, "应用启动登录入口"),
    (AUTH_FILE, "private fun migrateLegacyCredentials()", 1, "旧凭据键一次性迁移"),
    (AUTH_FILE, "private var sessionGeneration = 0", 1, "会话代数"),
    (AUTH_FILE, "private fun reLogin(expectedGeneration: Int)", 1, "会话失效重登去重"),
    (AUTH_FILE, "fun intercept(chain: Interceptor.Chain): Response", 1, "请求拦截与自愈"),
    (AUTH_FILE, "internal fun addAuthStatusPreference(", 1, "登录状态设置项"),
    (AUTH_FILE, "private const val LOGIN_ERROR_PATH", 1, "会话失效判据常量"),
    (AUTH_FILE, 'internal const val LOGGED_IN_HOST_PREF = "jmLoggedInHost"', 1, "偏好键 LOGGED_IN_HOST_PREF"),
    # 防回归：与上游 Preferences.kt 同包重名会直接编译失败
    (AUTH_FILE, "const val USERNAME_PREF", 0, "Auth.kt 不得声明 USERNAME_PREF"),
    (AUTH_FILE, "const val PASSWORD_PREF", 0, "Auth.kt 不得声明 PASSWORD_PREF"),
    # —— 上游 Preferences.kt：个人实现复用的键与工具 ——
    (PREFS_FILE, 'internal const val USERNAME_PREF = "username"', 1, "复用上游用户名键"),
    (PREFS_FILE, 'internal const val PASSWORD_PREF = "password"', 1, "复用上游密码键"),
    (PREFS_FILE, "internal fun clearSessionCookies(", 1, "复用上游清 cookie 工具"),
    # —— 主类挂载点（3 处）——
    (MAIN_FILE, "fun OkHttpClient.Builder.configureClient()", 1, "KeiSource 客户端挂载点"),
    (MAIN_FILE, "= AuthManager(", 1, "主类中构造 AuthManager"),
    (MAIN_FILE, "authManager.intercept(chain)", 1, "把登录拦截器挂到 client 链上"),
    (MAIN_FILE, "addAuthStatusPreference(screen, preferences, { baseUrl })", 1, "设置页接入登录状态项"),
    (MAIN_FILE, "authManager.loginOnStartup()", 1, "应用启动时触发登录"),
    # —— 链上其它拦截器（顺序有依赖）——
    (MAIN_FILE, "addInterceptor(ScrambledImageInterceptor)", 1, "图片还原拦截器仍在链上"),
    (MAIN_FILE, "addInterceptor(LoginInterceptor(", 1, "上游自动登录仍在链上（兜底）"),
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
    for name in (AUTH_FILE, MAIN_FILE, PREFS_FILE):
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
        "把我们的插桩挤掉或重复插入了。请人工核对登录契约与实现。"
        "§14.7.3 与 §14.8 的 4 个挂载点后重试——本次不会构建、不会发布，"
        "repo 分支上仍是上一个可用版本。"
    )
    print(f"::error title=登录功能锚点校验失败::{summary}")


if __name__ == "__main__":
    sys.exit(main())
