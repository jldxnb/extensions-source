# 禁漫天堂扩展 · 在 fork 上用 GitHub Actions 构建

> 本文件是「禁漫天堂扩展技术档案」文档集的一部分。
> 索引：[`docs/README.md`](../README.md)
> 包含全局章节：§16（**全局编号跨文件连续，请勿重排**）
>
> **性质**：实践经验。上游 workflow 的三处守卫已由源码确证 `[已核对源码]`；耗时估计为 `[推导]`。

---

## 16. 在 fork 上用 GitHub Actions 构建

### 16.0 结论速览

| 问题 | 答案 |
| --- | --- |
| fork 的公开仓库能用 Actions 吗？ | ✅ 能，而且分钟数免费不限量 |
| 上游自带 workflow 能直接用吗？ | ❌ **不能**，有三处会挡路 |
| 能自己写 workflow 吗？ | ✅ **能，且推荐**（约 25 行） |
| 产物能装到手机上吗？ | ✅ 能，但需先卸载官方同包名扩展并手动「信任」 |

---

### 16.1 上游 workflow 的结构

`.github/workflows/build_push.yml` 分三个 job：

```
prepare  →  build（矩阵分片）  →  publish
```

- `prepare`：用 `nrwl/nx-set-shas` 找上次成功的 CI commit，再跑 `generate-build-matrices.py` 算出**受影响的模块闭包**，按 `CI_CHUNK_SIZE = 80` 切分
- `build`：矩阵并行，每个分片跑 `./gradlew <modules>:assembleRelease`
- `publish`：把产物发布到 `keiyoushi/extensions@repo` 分支

---

### 16.2 三个必须知道的坑

#### 坑 1：产物被守卫挡住，fork 上不上传

```yaml
- name: Upload APKs (${{ matrix.chunk.number }})
  uses: actions/upload-artifact@...
  if: "github.repository == 'keiyoushi/extensions-source'"   # ← fork 上为 false
```

`build_push.yml:94` 与 `build_pull_request.yml` 中同一句。**fork 上 `build` job 会正常编译，但产物不上传**，网页上什么都下载不到。

`publish` job 的 `if` 里也有同一守卫，且额外需要 `secrets.BOT_PAT` 和 `keiyoushi/extensions` 仓库的写入权限——fork 上必然跳过。

> **注意区分**：「不生成」和「生成了不上传」是两回事。APK/JAR 确实在 CI runner 上被构建出来了，只是随后随 runner 销毁。

#### 坑 2：签名步骤必然让构建崩溃

```yaml
- name: Prepare signing key
  run: echo ${{ secrets.SIGNING_KEY }} | base64 -d > signingkey.jks
```

fork 上没有 `SIGNING_KEY` secret → 这行产出一个 **0 字节**的 `signingkey.jks`。而 `ExtensionPlugin` 判断是否用 release 签名时只看**文件是否存在**：

```kotlin
signingConfig = if (rootProject.file("signingkey.jks").exists()) {
    signingConfigs.getByName("release")     // 空文件也算「存在」
} else {
    signingConfigs.getByName("debug")
}
```

于是走 release 分支 → `SignExtensionJarTask.loadKeyStore()` 加载空 keystore → 抛
`Unable to load keystore signingkey.jks as JKS or PKCS12` → **构建失败**。

**这意味着在 fork 上，很可能连「生成产物」这一步都到不了。**

#### 坑 3：首次运行是全量重建

矩阵靠 `nrwl/nx-set-shas` 找「上一次成功的 CI commit」，并写死了回退值：

```yaml
with:
  fallback-sha: 4b825dc642cb6eb9a060e54bf8d69288fbee4904 # empty tree
```

fork 没有历史成功记录 → 回退到空树 SHA → `git diff` 认为「所有文件都变了」→ **1384 个模块全部进入矩阵**（约 18 片，每片 30 分钟超时）。

只改 `jinmantiantang` 一个模块却要触发全量构建，浪费极大。第二次运行起才会恢复增量。

> 另有 `retention-days: 1`——产物**只保留 1 天**，过期即删。

---

### 16.3 三条可选路线

| 方案 | 改动量 | 说明 |
| --- | --- | --- |
| **A. 打补丁用上游 workflow** | 改 2 处 YAML | 删掉 `Prepare signing key` 步骤、放开 `upload-artifact` 的 `if`。能跑，但首次全量、耗时长 |
| **B. 写一个极简自定义 workflow**（**推荐**） | 新增 1 个文件约 25 行 | 只构建目标模块并直接上传产物，绕过矩阵/签名/发布全部逻辑 |
| **C. 配自己的 keystore secret** | 加 4 个 secret | 在 A 或 B 基础上产出用自己密钥签名的 APK |

**方案 B 已落地**：文件为 [`.github/workflows/build-jinmantiantang.yml`](../../.github/workflows/build-jinmantiantang.yml)。

```yaml
name: Build jinmantiantang

on:
  workflow_dispatch:
  push:
    branches: [main]
    paths:
      - '.github/workflows/build-jinmantiantang.yml'
      - 'src/zh/jinmantiantang/**'
      - 'core/**'              # 本扩展依赖 :core
      - 'compiler/**'          # KSP 处理器
      - 'common/**'            # 共享 manifest / proguard
      - 'lib/randomua/**'      # build.gradle.kts 里声明的依赖
      - 'gradle/**'            # build-logic 与版本目录
      - 'build.gradle.kts'
      - 'settings.gradle.kts'
      - 'gradle.properties'

permissions: {}

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 40
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: actions/setup-java@dd06d9cba3e5552c54d9f8ea23572deb30010f7c # v6.0.0
        with:
          java-version: 17
          distribution: temurin
      - uses: gradle/actions/setup-gradle@9c971963bec38e04b3d30dcc455b5382be2fdbfb # v6.3.0
      # 刻意不创建 signingkey.jks → 自动降级为 debug 签名（见坑 2）
      - run: ./gradlew :src:zh:jinmantiantang:assembleRelease
      - uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1
        with:
          name: jinmantiantang
          path: |
            src/zh/jinmantiantang/build/outputs/apk/release/*.apk
            src/zh/jinmantiantang/build/outputs/jar/release/*.jar
            src/zh/jinmantiantang/build/keiyoushi-source-info.json
          if-no-files-found: error
          retention-days: 14
```

**关键点**：

1. **不要**写 `Prepare signing key` 那一步——不创建 `signingkey.jks`，构建就会走 debug 签名并成功
2. 不用上游的矩阵逻辑——单模块构建几分钟即可
3. `paths` 过滤要包含 `core/**` 与 `lib/randomua/**`，否则依赖变更时不会触发
4. 所有 Action 固定到 **commit SHA**（上游就是这么做的，也是 zizmor 审计的要求）。本文件的 4 个 SHA **与上游 build_push.yml 逐字一致**，因此不会触发 zizmor 的 `unpinned-uses`
5. `if-no-files-found: error` —— 产物没生成时立即失败，避免"构建成功但下载不到东西"
6. 本 workflow 自身也在 `paths` 里，改它能直接触发验证

---

### 16.4 装到手机上：签名与信任的真相

**这不是「需要官方验证程序批准」。** 是两道互相独立的机制：

#### 第一道：Android 系统的同包名签名一致性（硬性）

同一个 `applicationId` 的 App，新装的 APK 必须与已装的用**同一把密钥**签名，否则系统直接拒绝安装（报「签名冲突」）。

**做法**：把官方那版同包名扩展**先卸载**，再装自己构建的。

#### 第二道：宿主应用对扩展的信任判定

宿主（Mihon 等）会用签名哈希比对信任集合，不在集合里的扩展进入 `Untrusted` 状态，界面上出现**盾牌按钮**，**点一下「信任」即可正常使用**。

> 依据：宿主 `ExtensionLoader` 计算签名的 SHA-256，不在信任集合中则返回 `LoadResult.Untrusted`，由 `ExtensionManager` 暴露为 `untrustedExtensionsFlow`。

**所以：自签 APK 完全可以正常加载运行。** 代价是收不到官方更新。

#### ⚠️ 源 ID 必须保持不变

只要不改 `source { name }` / `lang` / `versionId`，源 ID 恒为 `6286738698187452081`，**原有书架、阅读进度、章节关联会自动接上**。

一旦改动，书架条目会退化为 `StubSource`，需要走宿主的手动迁移流程。

#### 完整落地步骤

1. 拿到构建产物 `tachiyomi-zh.jinmantiantang-v1.4.59.apk`
2. 手机上开启：**更多 → 设置 → 浏览 → "Show in sources and extensions list"**
   （**不开这一步，NSFW 扩展根本不显示在列表里** —— 最常见的「装了没反应」）
3. **卸载**官方同包名扩展
4. 安装自签 APK
5. 在**更多 → 扩展**里点**信任（盾牌）**
6. 回到**浏览 → 图源**，确认「中文」语言已启用
7. 点右侧齿轮进入设置

---

### 16.5 风险与限制

| 项 | 说明 |
| --- | --- |
| 无自动更新 | 自签扩展不会被识别为官方更新，官方每次修站点后需自行重编重装 |
| 产物过期 | 上游 workflow 的 artifact 只留 1 天（自建 workflow 可自行设置） |
| 公开/私有 | 公开仓库 Actions 分钟数免费不限；私有仓库每月 2000 分钟，全量构建可能吃掉可观份额 |
| Action 版本 | 必须固定到 commit SHA（上游如此，也满足 `zizmor` 安全审计） |

### 16.6 ⚠️ 本地能过 ≠ CI 能过：Spotless 的双面性

**这是本次实现时踩到的坑，值得单独记一笔。**

`AndroidBasePlugin` 把 Spotless 挂在了 `preBuild` 上：

```kotlin
tasks.getByName("preBuild").dependsOn(spotlessTaskName())
```

而 `spotlessTaskName()` 会**根据 `CI` 环境变量切换任务**（`Project.kt:11`）：

```kotlin
internal fun Project.spotlessTaskName() =
    if (providers.environmentVariable("CI").orNull != "true") "spotlessApply" else "spotlessCheck"
```

| 环境 | `preBuild` 依赖 | 行为 |
| --- | --- | --- |
| 本地 | `spotlessApply` | **自动格式化**，风格问题不会让构建失败 |
| **GitHub Actions**（自动设 `CI=true`） | `spotlessCheck` | **严格校验**，风格不合规 → 构建失败 |

**推论**：

1. 在本地反复构建通过，**不代表**推上去 CI 能过 —— 本地那份已经被 `spotlessApply` 改好了，CI 会拿"改之前"的代码去检查
2. 最保险的做法是**本地先跑一次** `./gradlew spotlessApply` 再提交
3. 反过来，如果 CI 报 Spotless 失败，本地跑 `spotlessApply` 会直接把问题改掉

**本次已知易触发的 ktlint 规则**：

| 规则 | 说明 |
| --- | --- |
| `no-unused-imports` | 在 `.editorconfig` 中显式 `enabled` |
| `no-empty-first-line-in-class-body` | 类体 `{` 后不能有空行 |
| import-ordering | 默认布局为 `*,java.**,javax.**,kotlin.**,^` —— `java.*` 要排在**最后**，不是字母序 |
| `no-consecutive-blank-lines` | 不允许连续空行 |

> `max_line_length` 被 Spotless 覆写为 `Int.MAX_VALUE`，不必担心行长。

---

**相关章节**：§15 构建与工具链（签名机制细节、网络实测）、§6.4 安装路径、§12 Mihon 宿主侧集成。
