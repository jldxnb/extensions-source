# 文档索引

本目录存放 `extensions-source` 仓库的**审查、设计与经验文档**。

> **全局章节编号跨文件连续（§1…§17），不得重排。** 章节号是跨文件的稳定标识，文中交叉引用依赖它。新增内容一律追加新编号。

---

## 分层结构

```
层 1 · 总览          本文件
   │
层 2 · 现状档案      §1–§14        代码现在是什么样
   │
层 3 · 计划设计      （暂无）       打算改成什么样
   │
层 4 · 经验沉淀      §15–§19        怎么构建、怎么发布、怎么调研、踩过哪些坑
```

---

## 层 1 · 总览

| 文档 | 说明 |
| --- | --- |
| [`../review.md`](../review.md) | **仓库级审查**：整体架构、模块划分、代码组织、CI/CD、风险 |
| [jinmantiantang/13-code-review.md](jinmantiantang/13-code-review.md) | **扩展级审查快照**：5 个源文件的结构、执行流程与缺陷（无 § 编号；新增缺陷号 JMT-13 起，可并入 §10） |
| 本文件 | 文档集索引、命名约定、维护规则 |

---

## 层 2 · 现状档案（禁漫天堂扩展）

描述 `src/zh/jinmantiantang` 的**当前代码状态**。

| 文件 | 主题 | 章节 |
| --- | --- | --- |
| [00-overview.md](jinmantiantang/00-overview.md) | 总览与维护约定 | §0、§13 |
| [01-identity-and-build.md](jinmantiantang/01-identity-and-build.md) | 标识、派生常量、构建契约 | §1、§2 |
| [02-runtime-and-network.md](jinmantiantang/02-runtime-and-network.md) | 文件职责、运行时模型、网络链路 | §3、§4、§6 |
| [03-features.md](jinmantiantang/03-features.md) | 功能规格（列表/搜索/详情/章节/图片/过滤器） | §5 |
| [04-image-descramble.md](jinmantiantang/04-image-descramble.md) | 图片还原算法规格 | §7 |
| [05-settings.md](jinmantiantang/05-settings.md) | 设置项规格与实测快照 | §8 |
| [06-host-integration.md](jinmantiantang/06-host-integration.md) | Mihon 宿主侧集成与安装落地 | §12 |
| [07-risks-and-maintenance.md](jinmantiantang/07-risks-and-maintenance.md) | 缺陷登记、变更手册、溯源验证 | §9、§10、§11 |
| [08-login.md](jinmantiantang/08-login.md) | 登录态：接口契约、设计依据与实现 | §14 |

## 层 3 · 计划设计

描述**尚未实现**的目标状态。当前**无计划中的功能**。

> 上一个计划项「登录态」已于 2026-09-12 实现，文档归档至层 2 的 [08-login.md](jinmantiantang/08-login.md)。新增计划文档时，文首须有明确的状态标记，且不得与层 2 混为一谈。

## 层 4 · 经验沉淀

方法论与踩坑记录，**可复用于其他扩展**，不限于禁漫天堂。

| 文件 | 主题 | 章节 |
| --- | --- | --- |
| [09-build-and-toolchain.md](jinmantiantang/09-build-and-toolchain.md) | 构建环境、工具链、产物、签名、本地构建命令 | §15 |
| [10-cicd-on-fork.md](jinmantiantang/10-cicd-on-fork.md) | 在 fork 上用 GitHub Actions 构建的完整攻略 | §16 |
| [11-har-capture.md](jinmantiantang/11-har-capture.md) | 抓包调研方法论（含 Chrome 清理机制） | §17 |
| [12-development-log.md](jinmantiantang/12-development-log.md) | **开发记录与维护手册**：变更台账、上游适配 SOP、恢复上下文清单 | §18 |
| [14-lessons-learned.md](jinmantiantang/14-lessons-learned.md) | **难点与经验总结**：无本地编译环境下的验证方法、版本号合成、APK 签名核验、客户端索引兼容、本地 clone 怪象 | §19 |

---

## 按问题快速导航

| 我想知道… | 去看 |
| --- | --- |
| 这个扩展支持哪些功能 | §5 |
| 某个界面按钮对应哪段代码 | §12.5 功能→界面映射表 |
| 图片为什么会错位 / 怎么还原的 | §7 |
| 齿轮里每个设置项是什么 | §8 |
| 改代码时哪些地方必须联动改 | §9 变更操作手册 |
| 有哪些已知 bug | §10 缺陷登记 |
| **登录功能是怎么实现的 / 接口契约是什么** | §14 |
| **登录相关有哪些风险** | §14.11 |
| **怎么把改完的代码编译成 APK** | §15 + §16 |
| **怎么在 fork 上一键出安装包** | §16.3（workflow 见 `.github/workflows/build-jinmantiantang.yml`） |
| **为什么本地能构建、CI 却失败** | §16.6 |
| **怎么抓包确认一个接口** | §17 |
| **Mihon 添加仓库报 `Error while decoding …NetworkExtensionStore`** | §19-D12（地址须用 raw，索引须含必填的 `badgeLabel`） |
| **这次踩过哪些坑、怎么绕开的** | §19 |
| 改了 `name` 会怎样 | §1.2 源 ID 红线 |
| 当前版本号是多少 | §1.3（`versionCode = 59`） |

---

## 文档集覆盖的实体

| 项 | 值 |
| --- | --- |
| 扩展模块 | `src/zh/jinmantiantang` |
| 站点 | 18comic / JMComic 系（禁漫天堂） |
| 包名 | `eu.kanade.tachiyomi.extension.zh.jinmantiantang` |
| 源 ID | `6286738698187452081` |
| 代码基线 | `jldxnb/extensions-source` @ `main`，HEAD `29d550f08`（2026-09-12）。**注意**：该提交改动了 `Auth.kt`（200 → 244 行），`07-risks-and-maintenance.md` §11.2 中 Auth.kt 的行号已漂移，检索请以函数名（`login` / `reLogin` / `performLogin` / `intercept`）为准 |

---

## 约定

### 命名与编号

1. **文件名前缀是阅读顺序，不是章节号。** 文件按主题分组（如 §6 网络链路 归入 `02-runtime-and-network.md`）。
2. **全局章节编号跨文件连续，不得重排。** 章节号（§1…§17）是稳定标识，交叉引用依赖它。
3. **已实现与计划中的内容必须分开。** 层 2 描述现状，层 3 描述目标，层 4 是方法论。
4. **来源分级。** 本仓库源码可验证的结论标注文件与行号；宿主（Mihon）侧行为标注来源并承认其随版本变动。经验类文档额外区分 `[实测]` 与 `[推导]`。

### 维护规则（原文见 §13）

- 层 2 只描述当前代码状态，不做路线图或设想（层 3 除外）。
- 代码改动落地后须同步更新：§1 派生常量、§3 行数、§5 功能规格、§11.2 行号索引；若涉及 manifest 元数据、源 ID 或语言，还须同步 §12。
- 功能实现落地后，层 3 对应文档的状态标记须从「未实现」改为「已实现」，并按 §14.14 的清单回填层 2。

### 关于结论的可信度

- 层 2 的结论**均来自对源码的逐行阅读与构建逻辑推导**，未经验证的推断已显式标注 `[推导]` 或 `[存疑，建议实机验证]`。
- 层 3 的接口契约来自**实抓 HAR**，证据索引见 §14.13；被推翻的假设保留原文并加 `⚠️ 修正` 标记，不悄悄改掉。
- 层 4 的经验来自本次实践，区分 `[实测]` 与 `[推导]`。

### 不入库的内容

`/har/` 目录（抓包文件，体积大且含个人会话数据）已通过仓库根 `.gitignore` 排除，详见 §17.6。
