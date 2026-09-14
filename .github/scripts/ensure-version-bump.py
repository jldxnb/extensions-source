#!/usr/bin/env python3
"""保证本次构建的 versionCode 严格大于 repo 分支上已发布的值。

为什么需要这一步
----------------
Mihon 判断"有没有新版本"**只比较 versionCode**（不比较内容）。索引里的值一旦不大于
已安装的值，用户就永远收不到这一版——而构建和发布都会绿油油地成功，没有任何信号。

两个容易踩的点
--------------
1. **实际生效的 versionCode 不是模块里的裸值**，而是与 `libVersion` 合成的。
   实测（out/jinmantiantang/keiyoushi-source-info.json，与线上索引一致）：

       libVersion = "1.4"  +  versionCode = 59   ->   versionCode = 104059

   即 `effective = major * 100000 + minor * 1000 + versionCode`。

2. sync-upstream.yml 的冲突自动解决只做「上游值 + 1」。若本地已发布值更大
   （例：已发布 104062，上游把 59 改成 60），就会得出 104061 —— 反而回退。

用法
----
    # 构建前（就地改写 build.gradle.kts，只在需要时改；--dry-run 只看结果）
    python3 .github/scripts/ensure-version-bump.py [--dry-run]

    # 构建后（用真实产物做权威校验；退出码 1 = 不能发布）
    python3 .github/scripts/ensure-version-bump.py --check-artifact artifacts

设计取舍
--------
读不到已发布索引时（网络抖动）的处理**分两种模式、刻意不对称**：

* **构建前（默认模式）只告警、不阻断**——此时还没花构建时间，且真正的兜底在后面；
  没必要因为 raw.githubusercontent 抖一下就停掉整条无人值守流水线。
* **构建后（--check-artifact）直接失败**——这是发布前的硬闸门，读不到索引就无法确认
  "新值是否大于线上值"，与其冒"静默把索引版本号回退"的风险，不如红着停住，
  让 repo 分支保持上一个可用版本。
"""
from __future__ import annotations

import argparse
import json
import re
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

VERSION_CODE_RE = re.compile(r"(versionCode\s*=\s*)(\d+)")
LIB_VERSION_RE = re.compile(r'libVersion\s*=\s*"(\d+)\.(\d+)"')

RETRIES = 3
RETRY_DELAY_SEC = 5


class IndexUnavailable(RuntimeError):
    """已发布索引读不到（网络问题），不代表没有发布过。"""


def fetch_published_version_code(index_url: str, index_file: str | None) -> int | None:
    """返回索引中本扩展的 versionCode；索引里没有本扩展时返回 None。"""
    if index_file:
        # 本地文件读取失败也按"索引不可用"处理：保持与网络失败一致的 fail-open/fail-closed 语义，
        # 而不是把 FileNotFoundError 直接抛出去
        try:
            data = json.loads(Path(index_file).read_text(encoding="utf-8"))
        except Exception as error:  # noqa: BLE001
            raise IndexUnavailable(f"本地索引文件读取失败（{index_file}）：{error}") from error
    else:
        last_error: Exception | None = None
        for attempt in range(1, RETRIES + 1):
            try:
                req = urllib.request.Request(
                    index_url,
                    # 让 CDN 重新校验，避免刚发布完读到缓存里的旧索引
                    # （读到旧值最多导致重复发布一次，不会造成版本号回退）
                    headers={"User-Agent": "jldxnb-publish-ci", "Cache-Control": "no-cache"},
                )
                with urllib.request.urlopen(req, timeout=20) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as error:
                if error.code == 404:
                    print(f"已发布索引不存在（HTTP 404）：{index_url} —— 视为首次发布")
                    return None
                last_error = error
            except Exception as error:  # noqa: BLE001 - 网络层任何异常都按不可用处理
                last_error = error
            if attempt < RETRIES:
                print(f"读取索引失败（第 {attempt}/{RETRIES} 次），{RETRY_DELAY_SEC}s 后重试：{last_error}")
                time.sleep(RETRY_DELAY_SEC)
        else:
            raise IndexUnavailable(str(last_error))

    extensions = data.get("extensionList", {}).get("extensions", []) or []
    for ext in extensions:
        if ext.get("packageName") == PACKAGE_NAME:
            return int(ext["versionCode"])
    return None


def read_module_version(path: Path) -> tuple[str, int, int, int]:
    """返回 (原文, major, minor, 模块 versionCode)。"""
    text = path.read_text(encoding="utf-8")
    vc_match = VERSION_CODE_RE.search(text)
    lib_match = LIB_VERSION_RE.search(text)
    if not vc_match or not lib_match:
        raise RuntimeError(
            f"无法从 {path} 解析 versionCode / libVersion —— 文件结构可能被上游改过，"
            "请人工核对后再重试"
        )
    return text, int(lib_match.group(1)), int(lib_match.group(2)), int(vc_match.group(2))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--module-file", default=DEFAULT_MODULE_REL, help="扩展模块的 build.gradle.kts")
    parser.add_argument("--index-url", default=DEFAULT_INDEX_URL, help="已发布索引地址")
    parser.add_argument("--index-file", default=None, help="改用本地索引文件（离线测试用）")
    parser.add_argument("--dry-run", action="store_true", help="只计算，不改写文件")
    parser.add_argument(
        "--check-artifact",
        default=None,
        help="校验构建产物：keiyoushi-source-info.json 的路径或其所在目录",
    )
    args = parser.parse_args()

    try:
        published = fetch_published_version_code(args.index_url, args.index_file)
    except IndexUnavailable as error:
        if args.check_artifact:
            # 发布前是硬闸门：读不到索引就无法确认"新值是否大于线上值"，此时宁可红着停住，
            # 也不要冒"静默把索引版本号回退"的风险（repo 分支会保持上一个可用版本）。
            print(
                f"::error title=无法读取已发布索引，拒绝发布::索引不可用（{error}）。"
                "发布前必须确认 versionCode 已大于线上值，因此本次不发布；"
                "repo 分支保持上一个可用版本，下次运行会重试。"
            )
            return 1
        print(
            f"::warning title=无法读取已发布索引::索引不可用（{error}）。"
            "本次不做版本号保证，请留意构建后的权威校验结果。"
        )
        return 0

    if args.check_artifact:
        return check_artifact(Path(args.check_artifact), published)

    module_path = Path(args.root) / args.module_file
    text, major, minor, module_vc = read_module_version(module_path)
    offset = major * 100000 + minor * 1000
    effective = offset + module_vc

    print(f"模块文件        : {module_path}")
    print(f"libVersion      : {major}.{minor}")
    print(f"模块 versionCode: {module_vc}  ->  有效 versionCode = {effective}")
    print(f"已发布 versionCode: {published if published is not None else '(索引中没有本扩展)'}")

    if published is None or effective > published:
        print("✅ 无需调整：本次构建的有效 versionCode 已经大于已发布值")
        return 0

    new_module_vc = published + 1 - offset
    # 上界说明：插件并不限制模块值（ExtensionPlugin.kt:137 是 `基准 × 1000 + 模块值`，
    # 没有掩码），模块值超过 999 只是让有效值进到下一个千位段（如 105xxx），仍然唯一且
    # 严格递增；将来上游把 libVersion 升档（基准从 104 跳到 106）时有效值会大幅上升，
    # 而本脚本是按**有效值**比较的，会自动适应。这里给一个宽松的 9999 只为拦住真正的异常
    # （例如 libVersion 被回退导致算出的模块值为负或离谱）。
    if not 0 <= new_module_vc <= 9999:
        print(
            f"::error title=versionCode 无法自动推进::已发布有效值 {published} 与当前 "
            f"libVersion {major}.{minor} 的组合算出的模块 versionCode 为 {new_module_vc}，"
            "超出可自动处理的区间（0-9999）。多半是 libVersion 档位被回退，请人工核对"
            "versionCode 与 libVersion 的合成关系。"
        )
        return 1

    line_no = text.splitlines().index(
        next(line for line in text.splitlines() if VERSION_CODE_RE.search(line))
    ) + 1
    print(f"已发布值不小于本次构建值，将 {module_path.name}:{line_no} 的 versionCode "
          f"{module_vc} -> {new_module_vc}（有效值 {published + 1}）")

    if args.dry_run:
        print("（--dry-run，未改写文件）")
        return 0

    new_text = VERSION_CODE_RE.sub(lambda m: f"{m.group(1)}{new_module_vc}", text, count=1)
    module_path.write_text(new_text, encoding="utf-8")
    print(
        f"::notice title=versionCode 已自动推进::"
        f"{module_vc} -> {new_module_vc}（有效 {offset + module_vc} -> {published + 1}）"
    )
    return 0


def check_artifact(target: Path, published: int | None) -> int:
    """用产物里的真实 versionCode 做发布前的权威校验。"""
    info_file = target
    if target.is_dir():
        candidates = sorted(target.glob("**/keiyoushi-source-info.json"))
        if not candidates:
            print(f"::error title=缺少产物元数据::{target} 下找不到 keiyoushi-source-info.json")
            return 1
        info_file = candidates[0]

    info = json.loads(info_file.read_text(encoding="utf-8"))
    built = int(info["versionCode"])
    print(f"产物            : {info_file}")
    print(f"构建出的 versionCode: {built}（versionName={info['versionName']}）")
    print(f"已发布 versionCode : {published if published is not None else '(索引中没有本扩展)'}")

    if published is None or built > published:
        print("✅ 通过：本次构建的 versionCode 大于已发布值，Mihon 能感知到更新")
        return 0

    print(
        f"::error title=versionCode 未递增，拒绝发布::构建产物 versionCode={built}，"
        f"而已发布值为 {published}。Mihon 只比较 versionCode，发布出去用户也收不到更新。"
        "请检查 build.gradle.kts 的 versionCode / libVersion。"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
