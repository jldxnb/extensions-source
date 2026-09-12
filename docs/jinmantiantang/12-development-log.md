# 禁漫天堂扩展 · 开发记录与维护手册

> 本文件是「禁漫天堂扩展技术档案」文档集的一部分。
> 索引：[`docs/README.md`](../README.md)
> 包含全局章节：§18（**全局编号跨文件连续，请勿重排**）
>
> **性质**：这是文档集里**唯一一份面向"未来的维护者"**的文档。§1–§17 描述"是什么/为什么"，
> 本文描述"怎么继续做下去"——包括每次改动的台账、上游适配流程、以及从零恢复上下文的检查清单。

---

## 18.0 这份文档是给谁看的

三种场景，对应三套恢复动作：

| 场景 | 触发 | 应读章节 | 应做动作 |
| --- | --- | --- | --- |
| **A. 上游发布新版本，需要适配** | `git fetch upstream` 后发现落后 | §18.7（适配 SOP） | 按 SOP 逐步执行 |
| **B. 换电脑 / 重新克隆仓库** | 本地工作副本丢失 | §18.8（恢复清单） | 重新 clone + 检查清单 |
| **C. 接手维护（新会话 / 换人）** | 不记得之前做到哪了 | §18.1 → §18.3 → §18.4 | 读台账 + 现状 |

**核心原则**：本文是**唯一**需要维护的"过程性"文档。代码相关的"是什么/为什么"都在 §1–§17，
本文只负责"过程"——改了什么、为什么、下一步做什么。

---

## 18.1 项目全貌

### 18.1.1 仓库关系

```
keiyoushi/extensions-source        ← 上游（官方），本 fork 的来源
        ▲
        │ fork
        │
jldxnb/extensions-source           ← 你维护的 fork，自定义改动都在这里
        ▲
        │ clone
        │
E:\Codebase\Android\keiyoushi\_push   ← 本地工作仓库（稀疏检出）
```

### 18.1.2 自定义改动总览

| 改动 | 文件 | 性质 | 依赖上游吗 |
| --- | --- | --- | --- |
| 账号登录与会话自愈 | `src/zh/jinmantiantang/.../Auth.kt`（新增 200 行） | **核心功能** | 否（独立新文件） |
| 登录拦截器挂载 | `src/zh/jinmantiantang/.../Jinmantiantang.kt`（+9 行） | 核心 | 轻微（插在既有链上） |
| 单模块 CI 构建 | `.github/workflows/build-jinmantiantang.yml`（新增） | 工程设施 | 否 |
| 排除 `/har/` | `.gitignore`（+4 行） | 工程 | 否 |

**结论**：所有自定义改动都**集中在 1 个新文件 + 主类 9 行插桩 + 2 个工程文件**。
这意味着上游更新时冲突面很小，适配成本低。**这是刻意设计的**——见 §18.4.1。

### 18.1.3 当前版本

| 项 | 值 |
| --- | --- |
| `versionCode` | `59`（`versionName` = `1.4.59`） |
| 源 ID | `6286738698187452081`（**不可变**，见 §1.2） |
| CI 状态 | ✅ 构建成功（run 34685907943） |
| 上游 HEAD | `2025891752e4705effc28e87a043f7205014cde3`（快照 2026-09-11） |

---

## 18.2 核心流程与模块结构

### 18.2.1 文件矩阵

| 文件 | 行数 | 是否被自定义改动 | 职责 |
| --- | --- | --- | --- |
| `Auth.kt` | 200 | ✅ 新增 | 账号登录、会话自愈、账号设置项 |
| `Jinmantiantang.kt` | 323 | ✅ +9 行 | 主类：五段解析 + 拦截器装配 |
| `Preferences.kt` | 161 | ✗ | 镜像、限速、屏蔽词 |
| `Filters.kt` | 131 | ✗ | 4 个过滤器 |
| `ScrambledImageInterceptor.kt` | 111 | ✗ | 图片分块还原 |
| `build.gradle.kts` | 31 | ✅ versionCode | 构建契约 |
| `.github/workflows/build-jinmantiantang.yml` | ~93 | ✅ 新增 | 单模块 CI |
| `docs/` | ~2400 | ✅ 本文档集 | 技术档案 |

### 18.2.2 请求链路（拦截器顺序）

```
请求 → UpdateUrlInterceptor(镜像自愈) → 宿主默认拦截器(UA/CF)
     → ScrambledImageInterceptor(图片还原) → authManager.intercept(登录)
     → rateLimit(限速) → 站点
```

详见 §6.2 与 §14.7.3。

---

## 18.3 变更台账（**每次代码变更必须在此追加一条**）

> **格式约定**：日期｜commit｜类型｜内容｜原因｜验证方式。
> 台账是本档案的"时间线"，**只追加不修改**。回溯任何决策都从这里开始。

| 日期 | commit | 类型 | 内容 | 原因 | 验证 |
| --- | --- | --- | --- | --- | --- |
| 2026-09-12 | `904d1a9f` | feat | 登录功能：`Auth.kt`（200 行）、主类挂载、versionCode 59、CI workflow、`.gitignore` 排除 `/har/` | 用户需求：保持登录态以访问受限题材 | CI run 34684043567 |
| 2026-09-12 | `889b7d40` | ci | 失败时把 Gradle 错误摘要写入检查注解与 job summary | fork 无仓库管理权限，API 拿不到日志 | CI run 34685121691 |
| 2026-09-12 | `28409a1b` | fix | 登录状态行 `Preference` → `EditTextPreference` | 基类 `Preference` 在本编译类路径上无法以 `Preference(context)` 构造 | CI run 34685479063 |
| 2026-09-12 | `64564dc4` | fix | `SharedPreferences.getString()` 返回 `String?`，状态行补 `orEmpty()` | 可空性缺失导致编译失败 | **CI run 34685907943 ✅** |
| 2026-09-12 | （本次） | docs | 新增 §18 开发记录；`docs/` 首次推送到 fork | 使经验记录随仓库持久化，重克隆可恢复 | — |
| 2026-09-12 | `7868a84a` | docs | 补充 §18.10 自动化流水线可行性分析 | 回应「能否全自动同步+构建+发布」的疑问 | — |
| 2026-09-12 | — | ✅实测 | **APK 实机验证通过**：安装使用正常 | 用户确认 | 实机 |
| 2026-09-12 | （本次） | chore | 删除 6 个上游 workflow（build_push/codeberg_mirror/build_pull_request/cleanup_releases/issue_moderator/lock），只保留 build-jinmantiantang 与 zizmor | 用户要求 Actions 只跑我们自己那一个；上游 CI 在 fork 上必然失败且无产物 | push 后 Actions 列表 |
| 2026-09-12 | （本次） | feat | 新增 `sync-upstream.yml`（每日自动同步上游→合并→构建→发布到 repo 分支）与 `publish-single.py`；build workflow 增加可选签名支持与 workflow_call | 实现全自动流水线（用户决定不加人工闸门，见 §18.10.4） | 首次合并后观察 |
| 2026-09-12 | （本次） | feat | 生成扩展专用签名密钥（本地 `keiyoushi/signing/`，不入库），等待用户配置 4 个 GitHub secret 后启用 release 签名与自动更新 | debug 签名每次不同，无法用于自动更新；稳定密钥是自动更新的前提 | 配置 secret 后 |

**未提交的本地产物**（不入库，仅在本地）：

| 项 | 路径 | 说明 |
| --- | --- | --- |
| HAR 抓包 | `har/`（66 MB） | 已被 `.gitignore` 排除 |
| 技术档案工作区 | `E:\Codebase\Android\keiyoushi\extensions-source\docs\` | 已推送至 fork |
| **本地工作仓库** | `E:\Codebase\Android\keiyoushi\_push` | **永久保留**，勿删（见 §18.7） |

---

## 18.4 关键实现思路

### 18.4.1 登录功能：为什么做成"低侵入增量"

登录功能没有重构任何既有代码，而是：

- **新增独立文件** `Auth.kt`，通过构造参数（4 个 lambda）取得所需能力，不反向依赖主类
- 主类只加 **9 行**：`authManager` 字段、1 个拦截器、1 行设置项装配

**原因**：上游会持续修改扩展本身。改动越集中，上游更新时的冲突面越小、适配成本越低。
这是本次维护中最重要的一个架构决策。

### 18.4.2 会话保持：为什么扩展不持有凭证

站点凭证是 `Set-Cookie` 下发的会话 Cookie。宿主的 `AndroidCookieJar`（底层 `android.webkit.CookieManager`）
**自动持久化并自动携带**，因此扩展只需发一次登录请求，其余全部交给 CookieJar。

**推论**：扩展**不需要知道 Cookie 名**、**不需要实现"保持登录"**、**切换镜像后需重新登录**（Cookie 域绑定）。
详见 §14.5.3。

### 18.4.3 失效判据：为什么是 `/error/album_missing`

站点未登录访问受限作品**不跳登录页**，而是伪装成「作品不存在」→ 301 到 `/error/album_missing`。
这是实测结论（§14.6.4），第三方文档的说法是错的。

### 18.4.4 CI：为什么绕开上游流程

| 上游流程的问题 | 本 workflow 的对策 |
| --- | --- |
| 上传产物有 `github.repository` 守卫，fork 上被跳过 | 不加守卫 |
| `Prepare signing key` 在无 secret 时产生空 keystore → 构建失败 | 刻意不创建 `signingkey.jks`，回落 debug 签名 |
| 首次运行回退到空树 SHA → 1384 个模块全量重建 | 只建单模块 |
| fork 无仓库管理权限，日志 API 返回 403 | 失败时把错误摘要写进检查注解与 job summary（公开 API 可读） |

### 18.4.5 自诊断：为什么把错误写进注解

fork 无仓库管理权限，`/actions/jobs/{id}/logs` 返回 403。
改用 `::error::` 检查注解输出错误摘要——**注解可用公开 API 读取**，
同时把最后 120 行写入 job summary。本次调试正是靠它拿到编译错误的。

---

## 18.5 依赖关系

### 18.5.1 模块依赖

```
src/zh/jinmantiantang
 ├── :core                     （UrlActivity、Cookie、OkHttp 扩展、工具）
 ├── :lib:randomua             （随机 UA；Spotless 强制要求 override getMangaUrl()）
 ├── :compiler                 （KSP：生成 Generated 类与 Manifest）
 └── gradle/build-logic        （ExtensionPlugin：构建契约、产物、签名）
```

### 18.5.2 外部硬约束

| 约束 | 说明 | 违反后果 |
| --- | --- | --- |
| `libVersion = "1.4"` | 宿主只接受 1.4 / 1.6 | 扩展被拒载，无明确提示 |
| 源 ID `6286738698187452081` | 由 `name`/`lang`/`versionId` 派生 | 改了 → 用户书架退化为 `StubSource` |
| 签名 | 自签包不能覆盖安装官方版；首次需在宿主里"信任" | 安装失败或扩展不显示 |
| NSFW 开关 | 宿主默认隐藏 NSFW 扩展 | 列表里看不到，误判为"安装失败" |

### 18.5.3 编译期注意事项

| 坑 | 说明 |
| --- | --- |
| **`Preference` 基类无法 `Preference(context)` 构造** | 本扩展编译类路径实测；子类均可。用 `EditTextPreference` 等替代 |
| **`SharedPreferences.getString()` 返回 `String?`** | 必须 `!!` 或 `orEmpty()` |
| **`CI=true` 时 `preBuild` 依赖 `spotlessCheck`** | 本地能过 ≠ CI 能过；提交前先 `./gradlew spotlessApply` |
| ktlint 默认 import 布局 | `java.*` 排**最后**，非字母序 |
| `RandomUAChecker` | 引用了 `lib/randomua` 就必须 `override fun getMangaUrl(` |

---

## 18.6 注意事项

| 项 | 说明 |
| --- | --- |
| **`docs/` 必须随仓库走** | 本档案集是唯一的"记忆"。换机器重新 clone 后它会自动回来——**前提是已推送到 fork** |
| **`har/` 不入库** | 66 MB 且含个人会话数据，已被 `.gitignore` 排除 |
| **`_push` 目录勿删** | 它是带完整历史的本地工作仓库，重建成本高（见 §18.7） |
| **上游 CI 红叉可无视** | 上游 `build_push.yml` 在 fork 上必然失败（签名坑 + 产物守卫），与本扩展无关 |
| **产物 14 天过期** | 每次构建的 artifact 保留 14 天，过期需重新触发 CI |
| **网络抖动** | 本机到 github.com 走代理，偶发 502 / 连接重置；推送失败就多重试几次 |

---

## 18.7 上游新版本适配流程（SOP）

> 触发条件：上游 `keiyoushi/extensions-source` 的 `main` 有新提交，或站点适配失效需要跟随上游更新。

```
① 同步上游
   git remote add upstream https://github.com/keiyoushi/extensions-source.git   # 首次
   git fetch upstream --tags

② 查看落后多少、上游动了哪些文件
   git log --oneline HEAD..upstream/main | head -30
   git diff --stat HEAD...upstream/main -- src/zh/jinmantiantang core lib compiler

③ 判断冲突风险
   ▸ 上游没动 src/zh/jinmantiantang/  → 直接合并，零冲突
   ▸ 上游动了该目录                    → 合并时重点解决（见第④步）

④ 合并
   git merge upstream/main
   # 若冲突在 src/zh/jinmantiantang/.../Jinmantiantang.kt：
   #   - 保留上游的解析逻辑修改
   #   - 重新插回我们的 3 处：authManager 字段 / 拦截器 / addAuthPreferences()
   #   - 依据：§14.7.3 的插桩点 + 本档案 §18.3 台账

⑤ 适配检查（合并后必做）
   ▸ Auth.kt 是否仍能编译（§18.5.3 的坑逐条对照）
   ▸ §14 的接口契约是否仍成立：
       - POST /login 字段与响应体            → 必要时重抓 HAR（§17）
       - /error/album_missing 失效判据        → 访问受限作品确认 301
       - 站点是否新增 CSRF token              → 查登录表单字段
   ▸ versionCode：取 max(上游 versionCode, 本地) + 1
   ▸ §1.3 重新计算派生常量

⑥ 提交并推送
   git push origin main      → CI 自动构建

⑦ 实机验证
   按 §14.12 验收清单走一遍，重点：受限作品能否打开
```

---

## 18.8 从零恢复上下文检查清单

> 适用场景：换电脑、重新克隆、或新会话从零开始。

```
□ 1. git clone https://github.com/jldxnb/extensions-source.git
     （建议加 --filter=blob:none 省流量；docs/ 会随仓库回来）

□ 2. 读文档恢复认知（按顺序，约 30 分钟）
     ▸ docs/README.md                 ← 索引 + 分层结构
     ▸ 00-overview.md                 ← 现状总览
     ▸ 18-development-log.md（本文）  ← 台账 + SOP
     ▸ 08-login.md                    ← 登录功能契约与实现
     ▸ 需要细节再翻 §1–§17

□ 3. 确认关键常量（§1）
     ▸ versionCode = 59
     ▸ 源 ID = 6286738698187452081
     ▸ applicationId = eu.kanade.tachiyomi.extension.zh.jinmantiantang

□ 4. 确认 CI 在
     ▸ .github/workflows/build-jinmantiantang.yml 存在且 state=active

□ 5. 配置上游
     ▸ git remote add upstream https://github.com/keiyoushi/extensions-source.git
     ▸ git fetch upstream

□ 6. 触发一次构建验证链路
     ▸ Actions 页手动运行 Build jinmantiantang，或 push 一个空提交
     ▸ 确认产物能下载

□ 7. 需要站点接口契约时
     ▸ 读 §14.2 / §14.13（已有实测 HAR 证据）
     ▸ 若怀疑站点改版 → 按 §17 重抓
```

---

## 18.9 维护规则

1. **每次代码变更必须在 §18.3 台账追加一条**，写清内容与原因；台账只追加不修改。
2. 本文档**不重复** §1–§17 的内容，只做引用与过程记录。
3. 涉及"为什么这么设计"的深层说明，写进对应章节并在本文引用。
4. 若某条注意事项升级为"必须遵守的约束"，同步写入 §18.5.2。

---

## 18.10 自动化流水线可行性分析

> 分析日期：2026-09-12。回答的问题：能否实现「上游相关变更 → 自动同步 → 自动构建 → 自动发布到扩展仓库」？自动化会不会使我们添加的部分失效？

### 18.10.1 实测数据：上游更新本模块的频率

上游 `keiyoushi/extensions-source` 触及 `src/zh/jinmantiantang/` 的提交，958 天内 30 次，**平均约 33 天一次**。

且 2026 年以来的提交几乎全是**基建重构**而非站点修复：

| 日期 | 提交 | 性质 |
| --- | --- | --- |
| 2026-08-31 | core: add Jsoup helper | 基建 |
| 2026-08-15 | fix gradle lint errors | 基建 |
| 2026-07-11 | Cleanup gradle/build-logic | 基建 |
| 2026-07-04 | Move rest of zh Extensions to new dsl | 基建（DSL 迁移） |
| 2026-06-26 | Add a new build logic DSL / deeplink support | 基建 |
| 2026-06-09 | Use our ratelimit implementation | 基建（**改动了 client 装配，与我们的插桩点重叠**） |
| 2026-05-02 | Jinman Tiantang: ParsedHttpSource → HttpSource | 基建 |
| 2025-08-06 | add search filters like author | **站点功能**（最后一次） |
| 2025-07-07 | update domains | **站点配置**（域名变更，影响镜像列表） |

**结论**：站点修复是**稀疏**的（一年几次），而 2026 年的重心是基建重构。基建重构恰恰最容易与我们的插桩点（`client` 装配、`setupPreferenceScreen`）冲突。

### 18.10.2 三段流水线的可行性

| 段 | 内容 | 可行性 | 实现方式 | 工作量 |
| --- | --- | --- | --- | --- |
| **① 同步** | 定时 fetch upstream → 判断是否触及相关路径 → merge | ✅ 完全可行 | 定时 workflow（cron）+ merge + 冲突时停下开 issue | ~60 行 workflow + 一个 versionCode 处理脚本 |
| **② 构建** | push 自动触发单模块构建 | ✅ **已就绪** | 现有 `build-jinmantiantang.yml` | 0 |
| **③ 发布** | 产物发到 fork 的 `repo` 分支并生成 index，Mihon 添加我们的仓库地址后**自动更新** | ✅ 可行，工作量最大 | 复用仓库自带的 `publish-repo.py` / `index_pb2.py` / `index.proto`，写单模块简化版；APK/JAR 托管到 GitHub Release | ~100-150 行 |

**③ 的关键便利**：官方发布机制就在本仓库里（`.github/scripts/publish-repo.py` 321 行、`index.proto`、`index_pb2.py`），且我们的构建已产出它需要的 `keiyoushi-source-info.json`。不需要从零发明格式。

### 18.10.3 会不会使我们添加的部分失效？

**自动化本身不会使功能失效。** 真正的失效源有三类，且它们的性质不同：

| 失效源 | 概率 | 表现 | 自动化能否拦截 |
| --- | --- | --- | --- |
| **站点改版**（登录接口、错误路径、DOM） | 中 | 编译通过但登录失败 | ❌ 拦不住——编译不报错。只能靠实机验证 |
| **上游重构**（如迁移到 1.6 / `KeiSource`，或改 client 装配方式） | 中（2026 年频繁） | 编译失败，或需重写挂载方式 | ✅ 编译失败会被 CI 拦下，**不会发布坏包** |
| **上游修改站点契约**（如 login 表单字段变更） | 低 | 编译通过但登录失败 | ❌ 同站点改版 |

**核心认识：自动化不会"弄坏"功能，它只是更快地暴露"本来就坏了"。**
手动维护同样会遇到这三类失效，只是暴露得更慢（等你想起来同步时才发现）。

### 18.10.4 唯一真正的风险点与对策

**风险**：全自动发布可能把一个「编译通过但登录已失效」的包推送到扩展仓库，手机端自动更新后才发现不能用。

**对策：分级发布闸门**——按上游是否触及我们的模块区分对待：

```
上游未触及 src/zh/jinmantiantang/** 与 core/**
   → 纯基建/其他扩展变更，与本扩展无关
   → 自动：同步 + 构建 + 发布            （风险低）

上游触及了上述路径
   → 可能影响解析逻辑或我们的插桩点
   → 自动：同步 + 构建，但停在人工确认
     （开一个 issue，附上游变更摘要与 §14.12 验收清单，等确认后再发布）
```

这样绝大多数同步（其他扩展的更新）完全无人干预。

> **用户决策（2026-09-12）：不加人工确认闸门，全自动发布。**
> 理由：① 出了问题自然会去看；② 不跟随上游更新反而更容易失效——上游修了站点适配而我们不同步，扩展一样不能用。
> 相应地，发布流水线失败时 CI 会直接报红，属于预期行为。

### 18.10.5 实现顺序建议

1. **先实机验证登录功能**（§14.12）——自动化流水线的意义在于"改了能立刻用"，如果功能本身不可用，流水线没有意义
2. 段① 同步自动化（含 versionCode 自动处理与分级闸门）
3. 段③ 发布流水线（自建扩展仓库，Mihon 自动更新）

### 18.10.6 已确认的现状数据

| 项 | 值 |
| --- | --- |
| fork 与上游的差距 | 领先 23 / 落后 5（截至 2026-09-12） |
| 落后的 5 个提交 | 均为其他扩展的修复，未触及我们的路径 |
| 上游最新提交 | 2026-09-12（**几乎每天有提交**） |
| 上游触及本模块频率 | 平均 33 天一次 |
| 官方发布脚本 | `.github/scripts/publish-repo.py`（321 行）+ `index.proto` + `index_pb2.py` |
