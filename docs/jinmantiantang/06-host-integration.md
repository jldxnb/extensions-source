# 禁漫天堂扩展 · Mihon 宿主侧集成

> 本文件是「禁漫天堂扩展技术档案」文档集的一部分。
> 索引：[`docs/README.md`](../README.md)
> 包含全局章节：§12（**全局编号跨文件连续，请勿重排**）

---

## 12. Mihon 宿主侧集成规格

> 本章描述的是**宿主应用（Mihon / Tachiyomi 系）如何消费本扩展**。§12.3 的元数据映射可由本仓库源码直接验证；§12.4–§12.6 的界面行为引自 Mihon 公开文档与源码结构（`mihonapp/mihon`），已注明来源，随宿主版本可能变动。

### 12.1 定位：不是独立 App，是宿主的扩展包

构建产物 APK 具备以下特征：

- 生成 Manifest 中**没有** `MAIN` / `LAUNCHER` intent-filter，唯一的 Activity 是 `keiyoushi.source.UrlActivity`，且带 `android:excludeFromRecents="true"` + `Theme.NoDisplay`
- 因此安装后**不会在桌面产生图标**，也不会出现在应用启动器里
- 唯一的用户可见入口是 **Mihon 自身**

它在宿主里的身份是：**一个包 → 一个扩展 → 一个源（Source）**。本扩展因为只声明了一个 `source { }` 块，所以是「1 扩展 : 1 源」。

**关键身份数据**（宿主据此识别与管理）：

| 项 | 值 | 作用 |
| --- | --- | --- |
| applicationId | `eu.kanade.tachiyomi.extension.zh.jinmantiantang` | 包管理与信任记录的主键 |
| 源 ID | `6286738698187452081` | 数据库里书签、阅读进度、设置的关联键 |
| 源语言 | `zh` | 决定归入哪个语言分组 |
| 源名称 | `禁漫天堂` | 界面显示名（KSP 注入，非 manifest 值） |

### 12.2 三条安装路径

| 路径 | 机制 | 是否需要安装权限 |
| --- | --- | --- |
| 从仓库在线安装 | 宿主拉取仓库 `index.pb` → 下载 APK → 走安装器 | 需要（或走 Shizuku） |
| 手动安装 APK | 文件管理器点击 APK → 系统安装器 | 需要 |
| **私有扩展** | APK 直接放入宿主内部 `filesDir/exts` 目录并重命名为 `.ext`，由 `ExtensionLoader` 扫描加载 | **不需要** |

第三条路径（"Private extensions"）是 Mihon 提供的免权限方案，实现见宿主 `ExtensionLoader.kt`。把文件放进应用内部目录通常需要 adb（`adb push` 到 `/data/data/<宿主包名>/files/exts/`）或 root。

### 12.3 生成的 Manifest → 宿主读取项映射

本仓库的 `GenerateManifestTask` 产出完全符合 `mihonapp/extensions-lib`(TachiyomiX) 公布的扩展清单规范。本扩展的实际值：

| Manifest 项 | 本扩展的值 | 必需 | 宿主用途 |
| --- | --- | --- | --- |
| `<uses-feature android:name="tachiyomi.extension" />` | 存在 | ✅ | **扩展包标识**，宿主据此筛选候选 APK |
| `tachiyomi.extension.class` | `keiyoushi.source.Generated` | ✅ | 反射加载的入口类 FQN |
| `tachiyomix.name` | `Jinman Tiantang` | — | 扩展列表显示名 |
| `tachiyomix.contentWarning` | `2` | — | 内容分级：0=Safe / 1=Mixed / 2=NSFW |
| `tachiyomix.extensionLib` | `1.4` | — | 库版本兼容校验 |
| `tachiyomi.extension.nsfw` | `1` | — | 遗留布尔键，旧版 NSFW 标记 |
| `android:label` | `Tachiyomi: Jinman Tiantang` | — | 系统层应用名 |

**兼容性硬约束**：宿主侧 `ExtensionLoader` 只接受 `1.4` 与 `1.6` 两个库版本，其他值会导致扩展被拒绝加载。

**注意**：运行时的 `name`（`禁漫天堂`）、`lang`（`zh`）、`id`、`baseUrl` **不来自 manifest**，而是 KSP 生成进 `Generated` 类的。所以扩展列表里显示 "Jinman Tiantang"，而源列表里显示 "禁漫天堂"——两者不同源。

### 12.4 三层呈现

**第 1 层｜更多 → 扩展（Extensions）**

呈现的是**扩展**（整个 APK）：

```
[图标] Jinman Tiantang          ← tachiyomix.name
       中文 · v1.4.59            ← lang + versionName
       NSFW                      ← contentWarning=2
       [信任] / [安装] / [更新] / [卸载]
```

图标取 `res/mipmap-xhdpi/ic_launcher.png`。若是首次安装的自签包，此处会出现**信任（shield）按钮**，未信任前不可用。

**第 2 层｜浏览 → 图源（Sources）**

呈现的是**源**（`Source` 实例）：

```
中文
  [图标] 禁漫天堂        [齿轮]     ← 源名来自 KSP 注入；齿轮来自 ConfigurableSource
  [图标] 其它中文源
```

- 按语言分组；语言可通过该页的**筛选按钮**控制显示哪些
- 右侧齿轮图标是否出现，取决于源是否实现 `ConfigurableSource`（本扩展实现了）
- 点齿轮进入的源设置页，**标题格式为 `<源名> (<语言大写>)`**，本扩展即「禁漫天堂 (ZH)」——该后缀由宿主追加，不由扩展提供
- 长按/菜单里还有：置顶、禁用、打开 WebView

**第 3 层｜点进源之后**

```
[禁漫天堂]
 ├─ 热门      ← popularMangaRequest (o=mv)
 ├─ 最新      ← latestUpdatesRequest (o=mr)
 ├─ 搜索框    ← searchMangaRequest / fetchSearchManga
 │    └─ [筛选] ← getFilterList() 的 4 个过滤器
 └─ 作品 → 详情页 → 章节列表 → 阅读器
```

### 12.5 功能 → 界面映射表

| 扩展内的实现 | 在 Mihon 中的显现 |
| --- | --- |
| `popularMangaRequest`（`o=mv`） | 源内「热门」标签页 |
| `latestUpdatesRequest`（`o=mr`）、`supportsLatest=true` | 源内「最新」标签页；同时参与「更新」主标签页的章节更新 |
| `getFilterList()` → CategoryGroup / SortFilter / TimeFilter / TypeFilter | 源内搜索页的「筛选」弹层（68 项分类下拉 + 3 组单选） |
| `fetchSearchManga` 的 `JM` 前缀 / 纯数字 / URL 识别 | 源内搜索框、**全局搜索**框、深链 |
| `mangaDetailsParse`（含 base64 解包） | 漫画详情页（标题/作者/标签/状态/简介） |
| `chapterListParse` + 单章节兜底 | 详情页下方的章节列表 |
| `pageListParse` | 阅读器的页面流 |
| `ScrambledImageInterceptor` | 阅读器里"图片正常显示"——用户完全无感 |
| `headersBuilder` + `setRandomUserAgent()` | 无直接 UI；UA 选项出现在设置页（`addRandomUAPreference`） |
| `getPreferenceList(...)` 4 项 + randomua 项 | 源列表右侧齿轮 → 设置页（`SourcePreferencesScreen`） |
| `UpdateUrlInterceptor` 抛的 `IOException` | 加载失败时的错误提示条（文案即异常 message） |
| `deeplink { }` → 生成的 `UrlActivity` | 浏览器点击站点链接 → 跳转 Mihon 并定位作品 |

**深链的完整链路**（`core/.../UrlActivity.kt`，本仓库可直接验证）：

```
浏览器点击 https://18comic.vip/album/xxx
  → Android 匹配扩展 APK 内 UrlActivity 的 intent-filter
     （scheme=http/https + host ∈ {18comic.vip, 18comic.ink, jmcomic-zzz.one, jmcomic-zzz.org}
       + pathPattern=/album/..*）
  → UrlActivity 构造 Intent{ action="eu.kanade.tachiyomi.SEARCH",
                              query=<完整 URL>, filter=<本扩展包名> }
  → 启动 Mihon
  → Mihon 在 filter 指定的扩展范围内，用 query 调用 fetchSearchManga
  → 命中 §5.5 的「URL 识别」分支，直接打开该作品
```

要点：**深链不是独立代码路径，而是"把 URL 当搜索词喂进搜索入口"**，`filter` extra 用来把搜索范围限定在本扩展。这也解释了为什么 `fetchSearchManga` 里要处理 `startsWith("https://")`。

### 12.6 界面上不可见的部分

以下实现对用户完全透明，只影响行为不影响界面：

- `ScrambledImageInterceptor` 的图片还原（用户只看到"图是正的"）
- `rateLimit` 限速（只能通过加载速度感知）
- `preferenceMigration()` 设置迁移
- 生成的 `Generated` 类与 Manifest 合成
- ProGuard 收缩、类去重、JAR 打包（构建期行为）

### 12.7 自签 APK 的完整落地步骤

针对"自己改代码 → 自建 Action 构建 → 手机安装"这条路径：

1. CI 产出 `tachiyomi-zh.jinmantiantang-v1.4.59.apk`
2. 手机上先开启：**更多 → 设置 → 浏览 → 勾选 "Show in sources and extensions list"**
   （不开这一步，NSFW 扩展**不会出现在列表里**——这是最常见的"装了没反应"）
3. **卸载**官方同包名扩展（`eu.kanade.tachiyomi.extension.zh.jinmantiantang`）
   —— 签名不同，Android 不允许覆盖安装
4. 安装自签 APK
5. **更多 → 扩展** 里点**信任（盾牌图标）** —— 自签包的签名不在宿主的信任集合里，会先落到 `Untrusted` 状态
6. 回到 **浏览 → 图源**，确认「中文」语言已启用，能看到「禁漫天堂」
7. 点右侧齿轮进入设置，按需调整镜像/限速/屏蔽词

**关于数据延续**：只要不改 `source { name }` / `lang` / `versionId`，源 ID 保持 `6286738698187452081` 不变，**原有书架里的漫画、阅读进度、章节关联都会自动接上**，无需迁移。

### 12.8 宿主侧风险

| 编号 | 风险 | 说明 |
| --- | --- | --- |
| JMT-H01 | 源 ID 变更导致数据断裂 | 改 `source { name }` 会让 ID 变化，书架条目退化为 `StubSource`，需要走宿主的手动迁移流程。这是本档案反复强调的红线 |
| JMT-H02 | 自签包不被视为官方更新 | 自签扩展不会收到官方更新推送，每次官方修复站点都要自己重新编译、重装 |
| JMT-H03 | 库版本不被接受 | 宿主只支持 `1.4` / `1.6`。若误改成其他值，扩展直接被拒载且无明确提示 |
| JMT-H04 | NSFW 开关未开 | 扩展在列表中不可见，用户会误判为"安装失败" |
| JMT-H05 | 签名信任状态 | 首次安装自签包必须手动信任；宿主会在信任前保持 `Untrusted` 状态 |
| JMT-H06 | 宿主版本差异 | 界面条目与设置项名称随 Mihon 版本演进（如"Show NSFW sources"与"Show in sources and extensions list"的说法在不同版本/文档中并存），以实机为准 |
