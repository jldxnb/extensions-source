#!/usr/bin/env python3
"""校验构建版本与上游 Jinmantiantang 模块完全一致。

版本规则
--------
上游模块是唯一版本源：

    src/zh/jinmantiantang/build.gradle.kts
        versionCode = N
        libVersion = "X.Y"

本 fork 构建出的版本必须完全一致：

    versionName = X.Y.N
    effective versionCode = digits(X.Y) * 1000 + N

本脚本不做“线上版本 + 1”，也不会改写 build.gradle.kts。任何不一致都应停止构建或发布。

用法
----
    # 构建前：校验 personal 的模块版本与 origin/main 一致
    python3 .github/scripts/verify-upstream-version.py module --ref origin/main

    # 构建后：校验产物版本，并给出发布策略
    python3 .github/scripts/verify-upstream-version.py artifact \
        --artifact artifacts \
        --expected-version-code 104058 \
        --expected-version-name 1.4.58 \
        --expected-lib-version 1.4

    # 仅用于一次性版本回退：允许产物 versionCode 小于线上值
    python3 .github/scripts/verify-upstream-version.py artifact ... --allow-version-reset
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def _configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


_configure_stdout()

DEFAULT_MODULE_REL = "src/zh/jinmantiantang/build.gradle.kts"
PACKAGE_NAME = "eu.kanade.tachiyomi.extension.zh.jinmantiantang"
DEFAULT_INDEX_URL = (
    "https://raw.githubusercontent.com/jldxnb/extensions-source/repo/index.min.json"
)

VERSION_CODE_RE = re.compile(r"versionCode\s*=\s*(\d+)")
LIB_VERSION_RE = re.compile(r'libVersion\s*=\s*"(\d+\.\d+)"')

RETRIES = 3
RETRY_DELAY_SEC = 5


class IndexUnavailable(RuntimeError):
    """已发布索引不可用；发布前应按 fail-closed 处理。"""


def read_git_file(ref: str, path: str) -> str:
    try:
        return subprocess.run(
            ["git", "show", f"{ref}:{path}"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip() if error.stderr else "git show failed"
        raise RuntimeError(f"无法读取 {ref}:{path}：{detail}") from error


def parse_module_version(text: str, label: str) -> tuple[int, str]:
    code_match = VERSION_CODE_RE.search(text)
    lib_match = LIB_VERSION_RE.search(text)
    if code_match is None or lib_match is None:
        raise RuntimeError(f"{label} 缺少 versionCode 或 libVersion")
    return int(code_match.group(1)), lib_match.group(1)


def effective_version_code(lib_version: str, module_version_code: int) -> int:
    base = int("".join(part.zfill(2) for part in lib_version.split("."))) * 1000
    return base + module_version_code


def version_name(lib_version: str, module_version_code: int) -> str:
    return f"{lib_version}.{module_version_code}"


def read_source_info(target: Path) -> dict:
    candidates = sorted(target.glob("**/keiyoushi-source-info.json")) if target.is_dir() else []
    if target.is_file():
        candidates = [target]
    if not candidates:
        raise RuntimeError(f"{target} 下找不到 keiyoushi-source-info.json")
    if len(candidates) > 1:
        names = ", ".join(str(path) for path in candidates)
        raise RuntimeError(f"找到多个 keiyoushi-source-info.json：{names}")
    return json.loads(candidates[0].read_text(encoding="utf-8"))


def fetch_published_version_code(index_url: str, index_file: str | None) -> int | None:
    if index_file:
        try:
            data = json.loads(Path(index_file).read_text(encoding="utf-8"))
        except Exception as error:  # noqa: BLE001
            raise IndexUnavailable(f"本地索引文件读取失败（{index_file}）：{error}") from error
    else:
        last_error: Exception | None = None
        for attempt in range(1, RETRIES + 1):
            try:
                request = urllib.request.Request(
                    index_url,
                    headers={"User-Agent": "jldxnb-publish-ci", "Cache-Control": "no-cache"},
                )
                with urllib.request.urlopen(request, timeout=20) as response:
                    data = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as error:
                if error.code == 404:
                    print(f"已发布索引不存在（HTTP 404）：{index_url} —— 视为首次发布")
                    return None
                last_error = error
            except Exception as error:  # noqa: BLE001
                last_error = error
            if attempt < RETRIES:
                print(f"读取索引失败（第 {attempt}/{RETRIES} 次），{RETRY_DELAY_SEC}s 后重试：{last_error}")
                time.sleep(RETRY_DELAY_SEC)
        else:
            raise IndexUnavailable(str(last_error))

    extensions = data.get("extensionList", {}).get("extensions", []) or []
    for extension in extensions:
        if extension.get("packageName") == PACKAGE_NAME:
            return int(extension["versionCode"])
    return None


def write_outputs(values: dict[str, object]) -> None:
    output = os.environ.get("GITHUB_OUTPUT")
    if not output:
        return
    with open(output, "a", encoding="utf-8") as file:
        for key, value in values.items():
            file.write(f"{key}={str(value).lower() if isinstance(value, bool) else value}\n")


def write_summary(lines: list[str]) -> None:
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary:
        return
    with open(summary, "a", encoding="utf-8") as file:
        file.write("\n".join(lines) + "\n")


def module_mode(args: argparse.Namespace) -> int:
    upstream_text = read_git_file(args.ref, args.module_file)
    local_path = Path(args.module_file)
    local_text = local_path.read_text(encoding="utf-8")

    upstream_code, upstream_lib = parse_module_version(upstream_text, f"{args.ref}:{args.module_file}")
    local_code, local_lib = parse_module_version(local_text, str(local_path))

    expected_code = effective_version_code(upstream_lib, upstream_code)
    expected_name = version_name(upstream_lib, upstream_code)
    local_effective = effective_version_code(local_lib, local_code)

    print(f"上游 {args.ref}: versionCode={upstream_code}, libVersion={upstream_lib}")
    print(f"personal 模块    : versionCode={local_code}, libVersion={local_lib}")
    print(f"要求产物         : versionName={expected_name}, versionCode={expected_code}")

    if (local_code, local_lib) != (upstream_code, upstream_lib):
        print(
            "::error title=模块版本与上游不一致::"
            f"personal={local_lib}.{local_code}（{local_effective}），"
            f"upstream={upstream_lib}.{upstream_code}（{expected_code}）。"
            "请先把 personal rebase 到最新 main，且不要在个人提交中修改版本号。"
        )
        return 1

    write_outputs(
        {
            "expected_version_code": expected_code,
            "expected_version_name": expected_name,
            "expected_lib_version": upstream_lib,
        }
    )
    write_summary(
        [
            "### 版本一致性",
            "",
            f"- 来源：`{args.ref}:{args.module_file}`",
            f"- 期望版本：`{expected_name}` / `{expected_code}`",
        ]
    )
    print("✅ personal 模块版本与上游一致")
    return 0


def artifact_mode(args: argparse.Namespace) -> int:
    expected_code = int(args.expected_version_code)
    expected_name = args.expected_version_name
    expected_lib = args.expected_lib_version

    info = read_source_info(Path(args.artifact))
    built_code = int(info["versionCode"])
    built_name = str(info["versionName"])
    built_lib = str(info["extensionLib"])

    print(f"期望产物    : versionName={expected_name}, versionCode={expected_code}, libVersion={expected_lib}")
    print(f"实际产物    : versionName={built_name}, versionCode={built_code}, libVersion={built_lib}")

    if (built_code, built_name, built_lib) != (expected_code, expected_name, expected_lib):
        print(
            "::error title=构建产物版本不符合上游::"
            f"实际={built_lib}/{built_name}/{built_code}，"
            f"期望={expected_lib}/{expected_name}/{expected_code}。"
        )
        return 1

    try:
        published = fetch_published_version_code(args.index_url, args.index_file)
    except IndexUnavailable as error:
        print(
            f"::error title=无法读取已发布索引，拒绝发布::索引不可用（{error}）。"
            "发布前必须确认版本回退策略，因此本次不发布。"
        )
        return 1

    reset_required = published is not None and built_code < published
    if reset_required and not args.allow_version_reset:
        print(
            "::error title=版本回退未获授权::"
            f"构建产物 versionCode={built_code}，线上已发布 versionCode={published}。"
            "严格跟随上游时，一次性回退必须显式传入 --allow-version-reset。"
        )
        return 1

    version_changed = published is None or built_code != published
    print(f"线上版本    : {published if published is not None else '(首次发布)'}")
    print(f"版本变化    : {version_changed}")
    print(f"需要版本重置: {reset_required}")

    write_outputs(
        {
            "built_version_code": built_code,
            "built_version_name": built_name,
            "published_version_code": published if published is not None else "",
            "version_changed": version_changed,
            "version_reset": reset_required,
        }
    )
    write_summary(
        [
            "### 版本一致性",
            "",
            f"- 构建版本：`{built_name}` / `{built_code}`",
            f"- 线上版本：`{published if published is not None else '-'}`",
            f"- 版本变化：`{version_changed}`",
            f"- 一次性版本重置：`{reset_required}`",
        ]
    )
    print("✅ 构建产物版本与上游一致，发布策略校验通过")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="mode", required=True)

    module_parser = subparsers.add_parser("module", help="校验源码模块版本与上游一致")
    module_parser.add_argument("--ref", default="origin/main", help="上游基线 ref")
    module_parser.add_argument("--module-file", default=DEFAULT_MODULE_REL)
    module_parser.set_defaults(func=module_mode)

    artifact_parser = subparsers.add_parser("artifact", help="校验构建产物版本与上游一致")
    artifact_parser.add_argument("--artifact", default="artifacts")
    artifact_parser.add_argument("--expected-version-code", required=True)
    artifact_parser.add_argument("--expected-version-name", required=True)
    artifact_parser.add_argument("--expected-lib-version", required=True)
    artifact_parser.add_argument("--index-url", default=DEFAULT_INDEX_URL)
    artifact_parser.add_argument("--index-file", default=None)
    artifact_parser.add_argument("--allow-version-reset", action="store_true")
    artifact_parser.set_defaults(func=artifact_mode)

    args = parser.parse_args()
    try:
        return args.func(args)
    except RuntimeError as error:
        print(f"::error title=版本校验失败::{error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())