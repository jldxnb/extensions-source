#!/usr/bin/env python3
"""单扩展发布：生成 index.json / index.min.json / index.pb 并布置 repo 目录。

从官方 publish-repo.py 简化而来——只处理一个扩展，产物直接放进 repo 目录，
用 raw.githubusercontent.com 提供下载，不经 GitHub Releases。

用法（在仓库根目录执行）：
    python3 .github/scripts/publish-single.py <module_dir> <artifact_dir>

    <module_dir>    源码模块目录（含 res/ 图标）
    <artifact_dir>  download-artifact 解包目录（含 keiyoushi-source-info.json 与
                    outputs/{apk,jar}/release/*；布局会因上传路径裁剪而异，
                    本脚本用 glob 自适应）

环境变量：
    SIGNING_KEY_FP  证书 SHA-256 指纹（十六进制）。缺省则索引不含 signingKey 字段，
                    宿主会把扩展标记为需要手动信任。
"""
import gzip
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path


def _configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


_configure_stdout()

sys.path.insert(0, str(Path(__file__).resolve().parent))
import index_pb2  # noqa: E402
from google.protobuf.json_format import MessageToJson  # noqa: E402

import google.protobuf  # noqa: E402

REPO_URL_BASE = "https://raw.githubusercontent.com/jldxnb/extensions-source/repo"
SIGNING_KEY = os.environ.get("SIGNING_KEY_FP", "")
REPO_NAME = "jldxnb 扩展仓库"
ICON_REL = "res/mipmap-xhdpi/ic_launcher.png"


def pick_single(root: Path, suffix: str, what: str) -> Path:
    """挑出唯一的 release 产物。

    刻意不取"字典序第一个"：若构建同时产出 -release.apk 与 -release-unsigned.apk
    （例如签名 secret 配错后回落），字典序会静默选到错的那个，最终发布一个装不上的包。
    这里显式排除 unsigned，并且在有多个候选时直接报错要求人工判断，而不是猜。

    注意 release 出现在**目录**上（outputs/apk/release/tachiyomi-*.apk），文件名里没有，
    所以要按相对路径判断；万一路径被裁掉了 release，退回"所有非 unsigned 产物"。
    """
    all_files = sorted(
        p for p in root.glob(f"**/*{suffix}") if "unsigned" not in p.name.lower()
    )
    if not all_files:
        raise FileNotFoundError(
            f"没有找到可发布的{what}（文件名不含 unsigned）。\n"
            f"  {root} 下实际内容: "
            f"{[str(p.relative_to(root)) for p in root.rglob('*')][:40]}"
        )
    preferred = [
        p for p in all_files if "release" in p.relative_to(root).as_posix().lower()
    ]
    candidates = preferred or all_files
    if len(candidates) > 1:
        raise RuntimeError(
            f"{what}有多个候选，无法确定发布哪一个：{[p.name for p in candidates]}"
        )
    return candidates[0]


def main() -> None:
    print(f"protobuf runtime: {google.protobuf.__version__}")

    module_dir = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path("module").resolve()
    art_dir = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else Path("artifacts").resolve()
    out_dir = Path("repo-out").resolve()

    print(f"module_dir = {module_dir}")
    print(f"art_dir    = {art_dir}")

    # --- 定位构建产物（上传时路径会被裁剪到最少公共祖先，用 glob 自适应）---
    info_file = next(iter(sorted(art_dir.glob("**/keiyoushi-source-info.json"))), None)
    if info_file is None:
        raise FileNotFoundError(
            f"缺少 keiyoushi-source-info.json\n"
            f"  art_dir 下实际内容: "
            f"{[str(p.relative_to(art_dir)) for p in art_dir.rglob('*')][:40]}"
        )
    apk = pick_single(art_dir, ".apk", "release APK")
    jar = pick_single(art_dir, ".jar", "release JAR")
    print(f"info_file = {info_file}")
    print(f"apk = {apk.name}  jar = {jar.name}")

    info = json.loads(info_file.read_text(encoding="utf-8"))
    print(f"info keys: {sorted(info.keys())}")
    print(f"module={info['module']}  versionCode={info['versionCode']}  "
          f"contentWarning={info['contentWarning']}")

    # --- 布置 repo 目录 ---
    if out_dir.exists():
        shutil.rmtree(out_dir)

    apk_out = out_dir / "apk" / apk.name
    jar_out = out_dir / "jar" / jar.name
    icon_out = out_dir / "icon" / "ic_launcher.png"
    for p in (apk_out, jar_out, icon_out):
        p.parent.mkdir(parents=True, exist_ok=True)

    shutil.copy2(apk, apk_out)
    shutil.copy2(jar, jar_out)
    icon_src = module_dir / ICON_REL
    shutil.copy2(icon_src, icon_out)

    def url(rel: Path) -> str:
        return f"{REPO_URL_BASE}/{rel.relative_to(out_dir).as_posix()}"

    ext = index_pb2.Extension(
        name=info["name"],
        packageName=info["packageName"],
        resources=index_pb2.Resources(
            apkUrl=url(apk_out),
            iconUrl=url(icon_out),
            jarUrl=url(jar_out),
        ),
        extensionLib=info["extensionLib"],
        versionCode=info["versionCode"],
        versionName=info["versionName"],
        contentWarning=info["contentWarning"],
        sources=[
            index_pb2.Source(
                id=int(s["id"]),
                name=s["name"],
                language=s["lang"],
                homeUrl=s["baseUrl"],
                mirrorUrls=s.get("mirrorUrls", []),
            )
            for s in info["sources"]
        ],
    )

    index = index_pb2.Index(
        name=REPO_NAME,
        # Mihon 扩展列表里显示的角标，用来和官方仓库的包区分（官方是 "KEI"）
        badgeLabel="JLD",
        contact=index_pb2.Contact(website="https://github.com/jldxnb/extensions-source"),
        extensionList=index_pb2.ExtensionList(extensions=[ext]),
    )
    if SIGNING_KEY:
        index.signingKey = SIGNING_KEY

    (out_dir / "index.json").write_text(
        MessageToJson(index, indent=2, preserving_proto_field_name=True),
        encoding="utf-8",
    )
    (out_dir / "index.min.json").write_text(
        MessageToJson(index, preserving_proto_field_name=True),
        encoding="utf-8",
    )
    # 与上游 publish-repo.py 对齐：index.pb 是 gzip 压缩后的 protobuf。
    # 原先写成裸 protobuf，一旦将来在 Mihon 里改用 .pb 地址就会解析失败。
    (out_dir / "index.pb").write_bytes(
        gzip.compress(index.SerializeToString(deterministic=True), mtime=0)
    )

    print(f"✅ 已生成 {out_dir}")
    print("   index.json / index.min.json / index.pb")
    print(f"   apk : {apk.name}  sha256={hashlib.sha256(apk.read_bytes()).hexdigest()}")
    print(f"   jar : {jar.name}  sha256={hashlib.sha256(jar.read_bytes()).hexdigest()}")
    if SIGNING_KEY:
        print(f"   signingKey: {SIGNING_KEY}")
    else:
        print("   ⚠ 未提供 SIGNING_KEY_FP，索引不含 signingKey（宿主会要求手动信任）")


if __name__ == "__main__":
    main()
