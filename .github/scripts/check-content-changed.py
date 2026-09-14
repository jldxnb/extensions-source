#!/usr/bin/env python3
"""发布前的「内容判据」：这次构建出来的扩展，和线上已发布的那份相比，代码/资源是否真的变了。

为什么需要
----------
Mihon 只比较 versionCode（不比较内容）。内容其实没变却发布一版，会产生一次无效更新或
重写 repo 分支；反过来漏发真正的代码变化也不行。

为什么不能直接比 APK / JAR 的整体哈希
------------------------------------
两者都内嵌 `AndroidManifest.xml`，而它含 versionCode / versionName。版本号完全跟随上游，
同一份代码在不同上游版本下也会得到不同的整体哈希，因此不能直接比较整包哈希。

判据：对 JAR 做「版本无关」的规范化哈希
--------------------------------------
按条目名排序，逐个喂入（条目名 + 内容），但跳过：
  - `AndroidManifest.xml` —— 唯一含版本号的条目
  - `META-INF/**`         —— JAR 签名材料（CERT.RSA / CERT.SF / MANIFEST.MF），
                             其中 MANIFEST.MF 含所有条目的摘要，会随 manifest 一起变

实测依据（out/jinmantiantang/…-v1.4.59.jar，51 个条目）：
  - 只有 AndroidManifest.xml 里出现 "104059" / "1.4.59"，其余条目都不含版本号
  - 跳过上述条目后剩 47 个：混淆后的 class、`res/*.png`、`resources.arsc` —— 即代码与资源

若将来某个构建把版本号写进了别的条目，本判据只会退化成「总是认为内容变了」→ 照常发布，
不会卡住发布（fail-open）。

用法
----
    python3 .github/scripts/check-content-changed.py --artifact artifacts
    python3 .github/scripts/check-content-changed.py --artifact <目录> --index-file <本地索引>
    python3 .github/scripts/check-content-changed.py --jar <单个 jar> --index-file <索引>

输出（同时写入 $GITHUB_OUTPUT，若该环境变量存在）
    changed=true|false
    version_name=1.4.58
    version_code=104058

退出码恒为 0：任何异常都按 `changed=true` 处理——宁可多发一版，也不要卡住发布。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from hashlib import sha256
from pathlib import Path


def _configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


_configure_stdout()

DEFAULT_INDEX_URL = "https://raw.githubusercontent.com/jldxnb/extensions-source/repo/index.min.json"
RETRIES = 3
RETRY_DELAY_SEC = 5

SKIP_EXACT = {"AndroidManifest.xml"}
SKIP_PREFIX = ("META-INF/",)


def content_hash(jar: Path) -> str:
    """版本无关的内容哈希：跳过 manifest 与签名材料。"""
    h = sha256()
    with zipfile.ZipFile(jar) as z:
        for name in sorted(z.namelist()):
            if name in SKIP_EXACT or name.startswith(SKIP_PREFIX):
                continue
            h.update(name.encode("utf-8"))
            h.update(b"\0")
            h.update(z.read(name))
            h.update(b"\0")
    return h.hexdigest()


def pick_release_file(root: Path, suffix: str, what: str) -> Path | None:
    """与 publish-single.py 同一套规则：优先路径含 release，排除 unsigned，多个则放弃。"""
    files = sorted(p for p in root.glob(f"**/*{suffix}") if "unsigned" not in p.name.lower())
    if not files:
        return None
    preferred = [p for p in files if "release" in p.relative_to(root).as_posix().lower()]
    candidates = preferred or files
    if len(candidates) > 1:
        print(f"::warning title={what}有多个候选::{ [p.name for p in candidates] }，本次按内容已变处理")
        return None
    return candidates[0]


def fetch_index(index_url: str, index_file: str | None) -> dict | None:
    """读已发布索引；读不到返回 None（调用方按 fail-open 处理）。"""
    if index_file:
        return json.loads(Path(index_file).read_text(encoding="utf-8"))
    last: Exception | None = None
    for attempt in range(1, RETRIES + 1):
        try:
            req = urllib.request.Request(
                index_url,
                headers={"User-Agent": "jldxnb-publish-ci", "Cache-Control": "no-cache"},
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            if error.code == 404:
                print(f"已发布索引不存在（HTTP 404）——视为首次发布：{index_url}")
                return None
            last = error
        except Exception as error:  # noqa: BLE001
            last = error
        if attempt < RETRIES:
            print(f"读取索引失败（第 {attempt}/{RETRIES} 次），{RETRY_DELAY_SEC}s 后重试：{last}")
            time.sleep(RETRY_DELAY_SEC)
    print(f"::warning title=无法读取已发布索引::索引不可用（{last}），按内容已变处理")
    return None


def fetch_bytes(url: str) -> bytes | None:
    for attempt in range(1, RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "jldxnb-publish-ci"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read()
        except Exception as error:  # noqa: BLE001
            if attempt < RETRIES:
                time.sleep(RETRY_DELAY_SEC)
            else:
                print(f"::warning title=无法下载已发布产物::{url}（{error}），按内容已变处理")
    return None


def published_jar_hash(index: dict | None) -> str | None:
    """下载线上已发布的 JAR，算它的规范化哈希。"""
    if not index:
        return None
    try:
        ext = index["extensionList"]["extensions"][0]
        jar_url = ext["resources"]["jarUrl"]
    except (KeyError, IndexError, TypeError):
        print("::warning title=索引结构异常::找不到 jarUrl，按内容已变处理")
        return None
    data = fetch_bytes(jar_url)
    if data is None:
        return None
    tmp = Path(tempfile.gettempdir()) / "published.jar"
    tmp.write_bytes(data)
    print(f"线上 JAR: {jar_url}  ({len(data)} 字节)")
    return content_hash(tmp)


def run(args: argparse.Namespace) -> bool:
    """返回 changed。"""
    art = Path(args.artifact)
    info_files = sorted(art.glob("**/keiyoushi-source-info.json")) if art.is_dir() else []
    if info_files:
        info = json.loads(info_files[0].read_text(encoding="utf-8"))
        args.version_name = str(info.get("versionName", ""))
        args.version_code = str(info.get("versionCode", ""))
        print(f"本次构建: versionName={args.version_name}  versionCode={args.version_code}")
    else:
        print(f"::warning title=缺少产物元数据::{art} 下找不到 keiyoushi-source-info.json")

    new_jar = Path(args.jar) if args.jar else pick_release_file(art, ".jar", "release JAR")
    if new_jar is None or not new_jar.is_file():
        print("::warning title=找不到本次构建的 JAR::按内容已变处理")
        return True

    new_hash = content_hash(new_jar)
    old_hash = published_jar_hash(fetch_index(args.index_url, args.index_file))
    print(f"本次构建 JAR: {new_jar.name}")
    print(f"  内容哈希（版本无关，本次）  = {new_hash}")
    print(f"  内容哈希（版本无关，线上）  = {old_hash}")
    if old_hash is None:
        print("  线上没有可比对的产物（首次发布或读取失败）→ 按内容已变处理")
        return True
    return new_hash != old_hash


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", default="artifacts", help="构建产物目录（含 apk/jar/source-info）")
    parser.add_argument("--jar", default=None, help="直接指定本次构建的 JAR")
    parser.add_argument("--index-url", default=DEFAULT_INDEX_URL)
    parser.add_argument("--index-file", default=None, help="改用本地索引文件（离线自测）")
    args = parser.parse_args()
    args.version_name, args.version_code = "", ""

    # fail-open：任何意外都按「内容已变」处理并正常退出——宁可多发一版，也不要卡住发布
    try:
        changed = run(args)
    except Exception as error:  # noqa: BLE001
        print(f"::warning title=内容判据执行异常::按内容已变处理（{type(error).__name__}: {error}）")
        changed = True

    print(f"\n=> changed={str(changed).lower()}")
    if not changed:
        print("   本次构建的扩展代码/资源与线上已发布的一致：不发布，也不消耗版本号。")

    try:
        summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary_path:
            with open(summary_path, "a", encoding="utf-8") as f:
                if changed:
                    f.write(f"### 内容判据\n\n- 结论：**内容有变化** → 继续发布\n- versionName: `{args.version_name}`\n")
                else:
                    f.write(
                        "### 内容判据\n\n- 结论：**内容未变 → 跳过发布**（不消耗版本号）\n"
                        f"- 线上已发布版本即为最新：`{args.version_name}`\n"
                    )
        out = os.environ.get("GITHUB_OUTPUT")
        if out:
            with open(out, "a", encoding="utf-8") as f:
                f.write(f"changed={str(changed).lower()}\n")
                f.write(f"version_name={args.version_name}\n")
                f.write(f"version_code={args.version_code}\n")
    except OSError as error:
        print(f"::warning title=写入输出失败::{error}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
