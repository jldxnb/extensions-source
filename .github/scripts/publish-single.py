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
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import index_pb2  # noqa: E402
from google.protobuf.json_format import MessageToJson  # noqa: E402

import google.protobuf  # noqa: E402

REPO_URL_BASE = "https://raw.githubusercontent.com/jldxnb/extensions-source/repo"
SIGNING_KEY = os.environ.get("SIGNING_KEY_FP", "")
REPO_NAME = "jldxnb 扩展仓库"
ICON_REL = "res/mipmap-xhdpi/ic_launcher.png"


def main() -> None:
    print(f"protobuf runtime: {google.protobuf.__version__}")

    module_dir = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path("module").resolve()
    art_dir = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else Path("artifacts").resolve()
    out_dir = Path("repo-out").resolve()

    print(f"module_dir = {module_dir}")
    print(f"art_dir    = {art_dir}")

    # --- 定位构建产物（上传时路径会被裁剪到最少公共祖先，用 glob 自适应）---
    info_file = next(iter(sorted(art_dir.glob("**/keiyoushi-source-info.json"))), None)
    apk = next(iter(sorted(art_dir.glob("**/*.apk"))), None)
    jar = next(iter(sorted(art_dir.glob("**/*.jar"))), None)
    if info_file is None or apk is None or jar is None:
        raise FileNotFoundError(
            f"构建产物不完整：info={info_file} apk={apk} jar={jar}\n"
            f"  art_dir 下实际内容: "
            f"{[str(p.relative_to(art_dir)) for p in art_dir.rglob('*')][:40]}"
        )
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
        name="jldxnb 扩展仓库",
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
    (out_dir / "index.pb").write_bytes(index.SerializeToString())

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
