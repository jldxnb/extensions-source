# 禁漫天堂扩展 · 构建与工具链

> 本文件是「禁漫天堂扩展技术档案」文档集的一部分。
> 索引：[`docs/README.md`](../README.md)
> 包含全局章节：§15（**全局编号跨文件连续，请勿重排**）
>
> **性质**：本文记录的是**实践积累的经验**，不是代码规格。内容分两类，已分别标注：
> `[实测]` = 在本机实际测过；`[推导]` = 依据源码/文档推断，未实测。

---

## 15. 构建与工具链

### 15.1 环境要求

| 项 | 要求 | 依据 |
| --- | --- | --- |
| Java | **17**（CI 使用 temurin 17） | `.github/workflows/build_push.yml:67` |
| JVM target | 11 | `gradle/kei.versions.toml` 的 `java = "11"` |
| compileSdk / targetSdk | **37** | 同上，`android-sdk-compile/target = "37"` |
| minSdk | 26 | 同上 |
| Gradle | **9.7.1**（由 wrapper 自动下载） | `gradle/wrapper/gradle-wrapper.properties` |
| Android SDK 组件 | `platforms;android-37`、`build-tools` | AGP 按 compileSdk 推导 |

`[实测]` 本机环境勘察结果（2026-09-12）：

| 项 | 实测值 |
| --- | --- |
| `java -version` | 17.0.12 LTS ✓ |
| `JAVA_HOME` | `C:\dev\toolchains\java\jdk17` |
| Android SDK | `D:\Android\Sdk` ✓（`ANDROID_HOME` 未设置） |
| 已装 platforms | `android-37.0`、`android-36` |
| 已装 build-tools | `35.0.0`、`36.0.0`（**无 37.x**） |
| SDK 许可 | `licenses/android-sdk-license` 存在 ✓ |
| Gradle 缓存 | `~/.gradle/wrapper/dists` 仅有 **9.3.1**（缺 9.7.1） |
| `local.properties` | **不存在**（需手动指定 `sdk.dir`，或依赖 `ANDROID_HOME`） |

**结论**：Java 与 SDK 基本就绪，但缺 Gradle 9.7.1 发行包与可能的 build-tools 37.x。

> ⚠️ **注意**：截至本文写作，**本地尚未实际跑通一次完整构建**。以上仅为环境勘察，不代表构建一定成功。首次构建前请先执行 §15.6。

### 15.2 网络实测（关键经验）

`[实测]` 2026-09-12 在本机对构建所需的各下载源逐个测速：

| 源 | 用途 | 实测速度 | 评价 |
| --- | --- | --- | --- |
| `dl.google.com/android/maven2` | AGP 等 Google 依赖 | **~9.4 MB/s**（12 MB / 1.3 s） | ✅ 快 |
| `mirrors.cloud.tencent.com/gradle` | Gradle 发行包镜像 | **~12 MB/s**（151 MB / 12.7 s） | ✅ **推荐** |
| `mirrors.huaweicloud.com/gradle` | Gradle 发行包镜像 | ~9 MB/s | ✅ 可用 |
| `services.gradle.org` | Gradle 官方发行站 | **~59 KB/s**（1.8 MB / 29 s） | ❌ **极慢** |
| `repo.maven.apache.org` | Maven Central | 慢（大文件 21 s 未完成） | ⚠️ 一般 |
| `github.com`（git clone） | 拉取源码 | **~90 KB/s** | ❌ **极慢** |

**核心结论**：

1. **瓶颈不在 Google Maven，而在 Gradle 发行站与 GitHub。**
2. Gradle 发行包若走官方站，130 MB 需要约 35 分钟；**换腾讯镜像可降到 13 秒**。
3. 这解释了为什么 `git clone` 体验极差，而手动下载 zip 反而更快。

**应对手段**（按推荐度）：

| 场景 | 方案 |
| --- | --- |
| 下载 Gradle 发行包 | 手动下载到 `~/.gradle/wrapper/dists/gradle-9.7.1-bin/<hash>/`，或临时改 `distributionUrl` 指向腾讯镜像 |
| 获取源码 | 用 GitHub 的「Download ZIP」，或按官方建议做部分克隆（§15.3） |
| Maven 依赖 | 官方源可用，暂不需要换镜像 |

### 15.3 源码获取策略

`[实测]` 全量 `git clone` 失败经历：

```
仓库 pack 体积   ≈ 205 MB（GitHub API: size = 210246 KB）
实测下载速率     ≈ 90 KB/s
结果             ≈ 运行 5 分钟后 .git 仍只有 9 KB，未写入 HEAD
```

**可选方案**：

| 方案 | 优点 | 缺点 |
| --- | --- | --- |
| **Download ZIP**（本次采用） | 最快、最简单 | 无 `.git`，丢失历史；`generate-build-matrices.py` 依赖 `git diff` 会失效 |
| **部分克隆 + 稀疏检出**（官方推荐） | 保留可 `git diff` 的历史，体积可控 | 命令略复杂 |
| 全量 clone | 完整 | 在本机网络下几乎不可行 |

`CONTRIBUTING.md` 给出的官方命令：

```bash
git clone --filter=blob:none --sparse https://github.com/<你的fork>/extensions-source.git
cd extensions-source
git sparse-checkout set --cone --sparse-index
git sparse-checkout add common compiler core gradle lib lib-multisrc
git sparse-checkout add src/zh/jinmantiantang
```

> 本例中 `src/zh/jinmantiantang` 就是要开发的扩展。cone 模式为推荐方式，非 cone 模式官方已废弃。

### 15.4 构建产物

一次 `assembleRelease` 产出**两种**产物：

```
APK   <module>/build/outputs/apk/release/tachiyomi-<pkgName>-v<versionName>.apk
JAR   <module>/build/outputs/jar/release/tachiyomi-<pkgName>-v<versionName>.jar
元数据 <module>/build/keiyoushi-source-info.json
```

本扩展的具体值（`[推导]` 按构建逻辑计算）：

```
APK   src/zh/jinmantiantang/build/outputs/apk/release/tachiyomi-zh.jinmantiantang-v1.4.59.apk
JAR   src/zh/jinmantiantang/build/outputs/jar/release/tachiyomi-zh.jinmantiantang-v1.4.59.jar
```

**JAR 才是扩展的实质载体** —— 由 `CreateExtensionJarTask` 从编译产物重组：剔除与提供方 classpath 重复的类 → ProGuard 收缩 → 拼入 APK 里的 `res/`、`assets/`、`resources.arsc`。APK 则保留为传统分发形态。

**可复现构建**：JAR 内所有条目时间戳固定为 `1704499200000`（2024-01-06，源码注释称 "keiyoushi's birthday"），条目按字典序排列。相同源码产生相同字节。

### 15.5 签名机制（含一个容易踩的坑）

来自 `SignExtensionJarTask` 与 `ExtensionPlugin`：

| 项 | 行为 |
| --- | --- |
| 签名算法 | **仅 V1（JAR 签名）**，V2/V3 显式关闭 |
| 工具 | `com.android.tools.build:apksig` |
| 密钥来源 | 环境变量 `KEY_STORE_PASSWORD` / `ALIAS` / `KEY_PASSWORD` + `signingkey.jks` |
| 无 keystore 时 | 降级为 **debug 签名**，构建仍可成功 |
| 支持格式 | JKS 与 PKCS12（依次尝试） |

> ⚠️ **踩坑记录**：`ExtensionPlugin` 判断是否使用 release 签名的条件是
> `rootProject.file("signingkey.jks").exists()` —— 只看**文件是否存在**，不看内容。
> 因此一个 **0 字节的 `signingkey.jks`** 会让它走 release 分支，然后在
> `loadKeyStore()` 处抛 `Unable to load keystore ... as JKS or PKCS12`，**构建失败**。
>
> 这正是上游 `build_push.yml` 在 fork 上必然崩溃的原因（见 §16.2 坑 2）。

### 15.6 本地构建命令

```bash
# 只构建禁漫天堂这一个扩展
./gradlew :src:zh:jinmantiantang:assembleRelease

# 改动共享模块后必须单独 lint（只 lint 依赖方不可靠）
./gradlew :core:lintRelease
./gradlew :lib:randomua:lintRelease
./gradlew :lib-multisrc:<theme>:lintRelease

# 代码风格
./gradlew spotlessApply
```

> ⚠️ **`spotlessApply` 不是可选项。** `preBuild` 会依赖它，本地构建时会**自动改写你的源码**；而在 CI 上（`CI=true`）依赖的是 `spotlessCheck`，同样的代码会**直接构建失败**——因为本地那份已被自动改好，CI 校验的是"改之前"的版本。
>
> **建议流程：提交前先跑一次 `./gradlew spotlessApply`。** 详见 §16.6。

**本地开发时建议**：`settings.gradle.kts` 默认加载全部 1384 个扩展模块，配置阶段开销极大。可把 `loadAllIndividualExtensions()` 注释掉，改用：

```kotlin
// loadAllIndividualExtensions()
loadIndividualExtension("zh", "jinmantiantang")
```

> 注意：改这一行会同时影响 `:core`、`:lib`、`:lib-multisrc` 之外的所有模块，改完记得还原。

### 15.7 未验证事项

| 事项 | 状态 |
| --- | --- |
| 本机完整构建 | ❌ **未跑通**（仅环境勘察） |
| build-tools 37.x 是否必需 | ⬚ 未验证（当前只有 35/36） |
| Gradle 9.7.1 下载时间（走镜像） | `[推导]` 约 15 秒 |
| 首次构建总耗时 | ⬚ 未测（含依赖下载，估计 10–30 分钟） |

---

**相关章节**：§2 构建契约（DSL 字段含义）、§16 GitHub Actions 在 fork 上的实践、§1.4 构建产物命名。
