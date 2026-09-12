# 禁漫天堂扩展 · 代码审查报告

> 审查时间：2026-09-12
> 审查范围：`src/zh/jinmantiantang/src/eu/kanade/tachiyomi/extension/zh/jinmantiantang/` 下 5 个 Kotlin 文件
> （`Jinmantiantang.kt` 324 行、`Auth.kt` 201 行、`Preferences.kt` 161 行、`Filters.kt` 132 行、`ScrambledImageInterceptor.kt` 111 行），
> 以及被引用的 `core/` 工具函数（`Json.kt` / `Jsoup.kt` / `RateLimit.kt`）。
> 代码基线：`60cfe97f`（= `jldxnb/extensions-source` main，本地 `src/zh/jinmantiantang` 与之逐字节一致，无未提交改动）。
>
> 本文**不使用全局 § 编号**，避免与既有文档集的编号体系冲突。缺陷编号沿用 `JMT-13` 起，可并入 `07-risks-and-maintenance.md` §10。

---

## 一、结论摘要

**整体判断：结构清晰、职责边界合理，登录功能的设计（不接管会话、只记"已登录域名"）是正确取舍。主要问题不在架构，而在三处：**

1. **健壮性缺口集中在"解析/解码失败时的降级"**——全篇没有一处 `runCatching` / `getOrElse`。站点改版、限流页、会话失效页返回非预期内容时，扩展的表现是**静默产出空数据**（列表空白条目、详情页空标题）或**直接抛不可读的异常**（NPE / NumberFormatException / SerializationException），而不是给出可诊断的错误。这是当前最高频的故障模式。
2. **入参校验缺失**——搜索框输入、URL 段索引、偏好值、远端下载内容有多处"直接 `toInt()` / 直接取下标 / 直接用 `[1]`"，均可被单个异常输入击穿。
3. **并发与副作用不显然**——登录无并发去重（可能同时发起 N 次登录 POST）、`SimpleDateFormat` 线程不安全、镜像自愈复用同一 chain 导致"探测镜像列表"会顺带触发登录。

**共新增 18 条缺陷（JMT-13 ~ JMT-30），其中中/中高 10 条；复核既有 12 条登记，1 条需升级等级（JMT-06）、1 条需修正描述范围（JMT-08）、2 条需补充触发路径（JMT-03、JMT-09）。**

无高危安全漏洞（无命令注入、无 SSRF、无凭据外传）。安全相关是两处中等项：密码明文存储（既有 JMT-L02）与"远端内容未经校验即作为请求目标域名"（JMT-17，供应链信任边界）。

---

## 二、代码结构与职责

### 2.1 模块职责矩阵

| 文件 | 对外暴露 | 核心职责 | 是否 fork 独有 |
| --- | --- | --- | --- |
| `Jinmantiantang.kt` | `@Source abstract class` | 主类。**5 段解析**（列表 / 搜索 / 详情 / 章节 / 图片）+ 拦截器装配 + 设置页装配 | 否（仅 +9 行插桩） |
| `Auth.kt` | `AuthManager`、`addAuthPreferences()`、3 个偏好键常量 | 登录判定、登录请求、会话自愈、账号设置项 | **是（新增）** |
| `Preferences.kt` | `getPreferenceList()`、`SharedPreferences.baseUrl`、`UpdateUrlInterceptor`、`preferenceMigration()` | 设置项定义、镜像解析、镜像自愈拦截器 | 否 |
| `ScrambledImageInterceptor.kt` | `object ScrambledImageInterceptor` | 分块打乱图片还原；无状态单例 | 否 |
| `Filters.kt` | 4 个过滤器 + `UriPartFilter` 基类 | 纯静态映射表（显示名 → URL 片段） | 否 |

**依赖方向（单向，无环）：**

```
                    ┌──────────────────────────┐
                    │     Jinmantiantang.kt    │  主类：装配者 + 解析者
                    └───┬──────┬──────┬────┬───┘
       构造注�入 4 个 lambda │      │      │    │ 直接引用
              ┌─────────┘      │      │    └────────────┐
              ▼                ▼      ▼                 ▼
        ┌──────────┐   ┌────────────┐ ┌─────────┐ ┌──────────────┐
        │ Auth.kt  │   │Preferences │ │Filters  │ │ScrambledImage│
        │AuthManager│  │  .kt       │ │ .kt     │ │Interceptor   │
        └──────────┘   └────────────┘ └─────────┘ └──────────────┘
              │                │
              │                └─► UpdateUrlInterceptor（同文件，独立类）
              └─► 只依赖构造参数（prefs / baseUrl / headers / client 四个 lambda）
                  → 不反向依赖主类，可单测
```

`Auth.kt` 通过 **4 个 lambda** 接收外部依赖（而非持有主类引用），是本项目里唯一做了依赖倒置的模块，值得作为后续拆分其他解析器的模板。

### 2.2 成员初始化顺序（决定行为，不可重排）

```kotlin
1. preferences           = getPreferences { preferenceMigration() }   // L40  触发设置迁移
2. baseUrl               = "https://" + preferences.baseUrl           // L42  一次性求值 ★
3. updateUrlInterceptor  = UpdateUrlInterceptor(preferences)          // L44
4. authManager           = AuthManager(preferences, { baseUrl }, ...) // L46  捕获 2 的求值结果
5. client                = network.client.newBuilder()...             // L54  依赖 2、3
```

★ `baseUrl` 是 `val`：一旦构造完成就不再变化。这条约束向下传导出三个后果：切换镜像必须重启应用（JMT-07）；`AuthManager.baseHost` 可以用 `by lazy` 安全缓存（因为 `baseUrl()` 恒返回同值）；限速器的 host 比较可以缓存（目前没缓存，见 4.2-JMT-29）。

### 2.3 拦截器链：顺序即语义

装配代码（`Jinmantiantang.kt:54-64`）的执行结果：

```kotlin
override val client = network.client
    .newBuilder()
    .apply { interceptors().add(0, updateUrlInterceptor) }    // ← 插到最前
    .addInterceptor(ScrambledImageInterceptor)                // ← 追加
    .addInterceptor { authManager.intercept(it) }             // ← 追加
    .rateLimit(...) { it.host == baseUrl.toHttpUrl().host }   // ← 网络拦截器（+ 一个 Tagging 应用拦截器）
    .build()
```

最终链路（**顺序本身就是行为**）：

| 序 | 位置 | 拦截器 | 生效条件 | 作用 |
| --- | --- | --- | --- | --- |
| 0 | 应用 | `UpdateUrlInterceptor` | URL 以 baseUrl 开头 | 失败时拉取新镜像列表并抛中文异常 |
| 1-3 | 应用 | `UncaughtException` / `UserAgent` / `Cloudflare` | 全部 | 由宿主 `network.client` 提供 |
| 4 | 应用 | `ScrambledImageInterceptor` | URL 含 `media/photos` 且 aid ≥ 220980 | 解码 gzip → 图片重排 → 重建 body |
| 5 | 应用 | **`AuthManager.intercept`** | 全部（除 `/login`） | 按需登录；命中错误页则重登并重试一次 |
| 6 | 应用 | `RateLimitInterceptor.TaggingInterceptor` | 全部 | 打标签，防止重复限速 |
| 7 | 网络 | `RateLimitInterceptor` | host == 主站 host | 滑动窗口限速 |
| — | 内部 | `RetryAndFollowUpInterceptor` | 全部 | 跟随重定向（位于应用拦截器**之下**，故应用拦截器能看到最终落点） |

**两个关键推论：**

- **图片请求会经过 ScrambledImage（4）再经过 Auth（5）。** 因此 Auth 内部的"重登 + 重试"发生在 ScrambledImage 调用 `chain.proceed` 的**下游**，ScrambledImage 只会拿到最终响应——功能正确。但如果最终响应是 HTML 错误页（会话失效、限流页），ScrambledImage 依然会尝试当图片解码 → 这正是 JMT-03 NPE 的真实触发路径（4.2-JMT-23）。
- **`RateLimitInterceptor` 是网络拦截器**，所以登录 POST（走 `network.client`）与镜像探测请求（github.io）都**不受限速约束**；漫画图片走 CDN host 时也不受约束（只匹配主站 host）。

---

## 三、关键执行流程

### 3.1 列表请求（人气 / 最新 / 搜索 · 共用一条解析路径）

```
popularMangaRequest(page)                       latestUpdatesRequest(page)
  GET /albums?o=mv&page=N                          GET /albums?o=mr&page=N
        └──────────────┬──────────────────────────────┘
                       ▼
              （拦截器链，见 2.3）
                       ▼
        popularMangaParse(response)                ← latestUpdatesParse 直接委托给它
          ├─ select("div.list-col > div.p-b-15:not([data-group])")   ← 站点列表项
          ├─ map { popularMangaFromElement(it) }                     ← 靠 children 下标取字段 ★
          ├─ filterGenre()                                           ← 屏蔽词过滤
          └─ hasNextPage = selectFirst("a.prevnext") != null

搜索另有一条前置分派（fetchSearchManga，L121-138）：
   query 是 https:// 开头  → 校验 host → 抽第 2 个路径段当作品 ID → 递归调用自己
   query 是 JM:xx / 纯数字 → 走 ID 直达：GET /album/{id} → mangaDetailsParse → 包装成单条 MangasPage
   其它                    → super.fetchSearchManga → searchMangaRequest（字符串拼 URL，L141-166）
```

### 3.2 详情 / 章节请求：base64 解包两段式

```
mangaDetailsParse(response) / chapterListParse(response)
        ▼
   mangaDetailsResolve(response)                 ← 站点把正文 HTML 塞进 <script> 里
     ├─ asJsoup()  解析外层页面
     ├─ select("#wrapper > script:containsData(function base64DecodeUtf8):containsData(document.write(html))")
     ├─ 逐行找 const/let/var html = base64DecodeUtf8("...")
     ├─ Base64.decode → String(html) → document.body().append(...)   ← 把解出的 HTML 追加进文档
     └─ 返回同一个 Document（外层 + 内层合并）
        ▼
   再走各自的字段映射：
     详情：h1 / .thumb-overlay>img / tag-block[3] / span[itemprop=genre] / #intro-block
     章节：div#episode-block a[href^=/photo/]，空则兜底产出「单章节」
```

这是全项目最脆弱的一段：**5 个环节中任一失效都不报错，只产出空字段**（4.2-JMT-26）。

### 3.3 看图请求：三个拦截器协作

```
GET https://<host>/media/photos/<aid>/<imgIndex>.jpg
  │
  ├─[0] UpdateUrlInterceptor   仅主站 host 命中；成功直接放行
  ├─[4] ScrambledImageInterceptor
  │      ├─ URL 含 media/photos ?  aid = pathSegments[size-2].toInt() ★未校验
  │      ├─ aid < 220980 ?        直接放行
  │      ├─ 解 gzip（如有）→ 去掉 Content-Encoding / Content-Length
  │      ├─ decodeImage：BitmapFactory → rows 块倒序重排 → JPEG/90 回写 Buffer
  │      └─ responseBuilder.body(newBody)
  ├─[5] AuthManager.intercept   未配置凭据则完全透明
  ├─[7] RateLimitInterceptor    仅当 host == 主站 host
  │
  └─ 站点

rows 的算法（getRows）：aid ≥ 421926 → modulus 8；≥ 268850 → modulus 10；否则恒 10
                        rows = 2 * (md5(aid + imgIndex) 末尾十六进制字符的 ASCII 码 % modulus) + 2
```

### 3.4 登录自愈状态机

```
每个请求（除 encodedPath == "/login"）：

  needsLoginNow = isConfigured(账密均非空) && loggedInHost != baseHost
  │
  ├─ true ──► login()  ──成功──► loggedInHost = baseHost ──► chain.proceed
  │              └──失败──► 抛 IOException（中文文案，面向用户）
  │
  └─ false ─► response = chain.proceed(request)
               │
               └─ isConfigured && 最终落点 == /error/album_missing ?
                    ├─ 是 ─► response.close() → clearSession() → login() → chain.proceed（仅重试一次）
                    └─ 否 ─► 原样返回
```

设计上两个值得肯定的点：`needsLoginNow` 先取值再登录，用来区分"本次刚登过"与"本地以为已登录"（否则刚登完失败还会无限重试）；失效判据用**服务端给出的明确信号**（301→`/error/album_missing`）而不是猜页面内容。

---

## 四、缺陷清单

### 4.1 总表

| 编号 | 等级 | 位置 | 一句话 |
| --- | --- | --- | --- |
| **JMT-13** | 中 | `Jinmantiantang.kt:130-131` | `startsWith(..., ignoreCase=true)` 配大小写敏感的 `removePrefix` → `jm123456` 走 ID 分支却剥离失败，请求 `/album/jm123456` → 静默返回空条目 |
| **JMT-14** | 中 | `Jinmantiantang.kt:122-128` | `url.pathSegments[1]` 对 `/`、`/album/`、`/search/xxx` 等链接越界或取错段；`toHttpUrl()` 对畸形串抛 `IllegalArgumentException` |
| **JMT-15** | 中高 | `Auth.kt:92-126` | 登录无并发去重：并发请求会同时发起 N 次登录 POST（首次阅读、切镜像后最明显） |
| **JMT-16** | 中高 | `Auth.kt:110-118` | `parseAs` 的异常类型契约不成立：非 JSON 响应抛 `SerializationException`/`MissingFieldException`（非 `IOException`），用户看到 kotlinx 原始报错 |
| **JMT-17** | 中（安全） | `Preferences.kt:141-160`、`96-97` | 远端下载内容**未校验**即写入偏好并**用作请求目标域名**；`startsWith(baseUrl)` 前缀比较可被 `18comic.vip.evil.tld` 绕过 |
| **JMT-18** | 中 | `Preferences.kt:140-160` | 内容未变化也报"镜像列表已自动更新"，并用误导文案替换掉原始异常 |
| **JMT-19** | 中 | `Preferences.kt:96`、`Jinmantiantang.kt:61-62` | 偏好值直接 `toInt()/toLong()`：脏数据 → 源实例化即崩溃（表现为空白源） |
| **JMT-20** | 中 | `Jinmantiantang.kt:255、260` | `SimpleDateFormat` 实例字段**线程不安全**，可被并发章节解析触发（JMT-06 应升级） |
| **JMT-21** | 中 | `Jinmantiantang.kt:279-300` | 图片分页递归无上限、中途异常无兜底 → 站点异常时可无限请求/整章失败 |
| **JMT-22** | 中 | `ScrambledImageInterceptor.kt:22-25` | `pathSegments[size-2].toInt()` 无校验 + URL 判定过宽（`contains("media/photos")`）→ `NumberFormatException` |
| **JMT-23** | 中高 | `ScrambledImageInterceptor.kt:69-108` | 解码失败无降级：非图片内容（限流页/错误页）→ NPE，且**整章读不了**（JMT-03 的真实触发路径） |
| **JMT-24** | 低中 | `Jinmantiantang.kt:83-105、220-226` | 解析失败静默产出空字段：无 url 的空白列表项、`"null_3x4.jpg"` / `"_3x4.jpg"`（JMT-01 的兄弟情形） |
| **JMT-25** | 低中（可维护性） | `Jinmantiantang.kt:141-166` | 搜索 URL 靠 `substringAfter("?")` 等位置关系拼装，与 `Filters.kt` 的字符串约定强耦合；`contains("-")` 判定过宽 |
| **JMT-26** | 低 | `Jinmantiantang.kt:171-195` | `String(html)` 依赖平台默认字符集（函数名却是 Utf8）；base64 解包全链路无失败信号 |
| **JMT-27** | 低 | `Auth.kt:131-157、84-87` | `/login` 短路实为防御性死代码；`clearSession()` 的"清登录标记"与用户理解的"退出登录"语义不符 |
| **JMT-28** | 低 | `Auth.kt:163-200` | 设置项直接改偏好键绕过 `AuthManager`（双写者）；`EditTextPreference` 替身写法缺"何时可撤掉"的 TODO |
| **JMT-29** | 低 | `Jinmantiantang.kt:54-64`、`Preferences.kt:143-147` | 镜像自愈复用同一 chain 请求跨域资源 → 会顺带穿过 Auth（触发登录）与 Cloudflare 拦截器；`baseUrl.toHttpUrl()` 每请求重算 |
| **JMT-30** | 低（文档） | `docs/…/02-runtime-and-network.md` §6.2 | 拦截器链图**缺 Auth 拦截器**；§3 文件清单行数快照漂移（Auth.kt 实测 201 行，文档记 195） |

### 4.2 逐条说明与修复

#### JMT-13【中】ID 直达的大小写陷阱

```kotlin
// 现状：判定忽略大小写，剥离却大小写敏感
if (query.startsWith(PREFIX_ID_SEARCH_NO_COLON, true) || query.toIntOrNull() != null) {
    val id = query.removePrefix(PREFIX_ID_SEARCH_NO_COLON).removePrefix(":")
```

`"jm123456"` / `"Jm123456"` 都能进入该分支，但 `removePrefix("JM")` 不生效 → `id = "jm123456"` → `GET /album/jm123456` → 站点 404 页 → `mangaDetailsParse` 取不到字段 → **返回一个标题为空的"作品"**，用户看到的是空白结果而不是"搜不到"。

```kotlin
private val ID_SEARCH_REGEX = Regex("^(?:JM:?)?(\\d+)$", RegexOption.IGNORE_CASE)

val idMatch = ID_SEARCH_REGEX.find(query.trim())
return if (idMatch != null) {
    val id = idMatch.groupValues[1]
    client.newCall(searchMangaByIdRequest(id)).asObservableSuccess().map { searchMangaByIdParse(it, id) }
} else {
    super.fetchSearchManga(page, query, filters)
}
```

顺带修掉两个相关问题：`query.toIntOrNull() != null` 让**纯数字关键词永远无法做文本搜索**（输入 `2024` 只会去查作品 2024）；正则方案可保留该行为，但建议在 `03-features.md` 里把它记为**有意的取舍**。

#### JMT-14【中】粘贴链接的越界与取错段

```kotlin
val url = query.toHttpUrl()
if (url.host != baseUrl.toHttpUrl().host) throw Exception("Unsupported url")
val titleid = url.pathSegments[1]        // ← 越界 / 取错
```

| 输入 | `pathSegments` | 结果 |
| --- | --- | --- |
| `https://18comic.vip/` | `[""]` | **IndexOutOfBoundsException** |
| `https://` | — | `toHttpUrl()` 抛 `IllegalArgumentException` |
| `https://18comic.vip/album/` | `["album", ""]` | 得到 `""` → 请求 `/album/` |
| `https://18comic.vip/photos/123/` | `["photos","123",""]` | 把 `123` 当成作品 ID（语义错误） |

```kotlin
if (query.startsWith("http://") || query.startsWith("https://")) {
    val url = runCatching { query.toHttpUrl() }.getOrNull()
        ?: throw Exception("无效的链接")
    if (url.host != baseUrl.toHttpUrl().host) throw Exception("Unsupported url")
    if (url.pathSegments.firstOrNull() != "album") throw Exception("Unsupported url")
    val id = url.pathSegments.getOrNull(1)?.takeIf { it.isNotEmpty() && it.all(Char::isDigit) }
        ?: throw Exception("无法从链接中解析作品编号")
    return fetchSearchManga(page, "$PREFIX_ID_SEARCH$id", filters)
}
```

#### JMT-15【中高】登录风暴：并发请求各登一次

```kotlin
fun intercept(chain: Interceptor.Chain): Response {
    val needsLoginNow = needsLogin
    if (needsLoginNow) login()          // ← 每个请求独立判定，无锁、无去重
```

Mihon 在阅读一章时会对图片发起**多个并发请求**，书架更新也会并发拉取。首次阅读（或切换镜像后）这些请求会同时看到 `needsLogin == true`，于是**同时发起 N 个登录 POST**——既浪费，又会把同一份账号密码在一瞬间反复提交给站点（风控观感差；JMT-L05 已指出登录不受限速器约束，两者叠加）。

注意 `loggedInHost` 的写入是 `apply()`：内存同步、磁盘异步，所以**写后立刻读是可见的**——这恰好让"锁内二次检查"成为可靠修法：

```kotlin
private val loginLock = Any()

fun login() {
    if (!isConfigured) return
    synchronized(loginLock) {
        if (!needsLogin) return        // 已被其他线程登完（含首次成功后）
        val base = baseUrl()
        // ...原逻辑不变...
        loggedInHost = baseHost
    }
}
```

若要更进一步（失败时也不重复提交），可缓存"上次失败时间"，在 N 秒内直接复用异常对象。

#### JMT-16【中高】异常类型契约与文档不符

`Auth.kt` 的 KDoc 写明"凭据无效或接口异常时抛 `IOException`"。但：

```kotlin
response.parseAs<LoginResult>()      // keiyoushi.utils.Json.kt:37 → use { json.decodeFromBufferedSource(...) }
```

`Json` 是**宿主注入的实例**（`jsonInstance = Injekt.get()`），因此解析行为由宿主配置决定。两种常见情况下抛的都不是 `IOException`：

| 场景 | 实际异常 | 用户看到 |
| --- | --- | --- |
| Cloudflare 挑战/维护页返回 HTML（HTTP 200） | `SerializationException` | kotlinx 的原始报错串 |
| 站点改版，响应体缺 `status` 字段 | `MissingFieldException` | 同上 |

```kotlin
val result = client().newCall(POST("$base$LOGIN_PATH", requestHeaders, body)).execute().use { response ->
    if (!response.isSuccessful) throw IOException("禁漫登录失败：HTTP ${response.code}")
    runCatching { response.parseAs<LoginResult>() }.getOrElse {
        throw IOException("禁漫登录失败：站点返回了非预期内容（可能被 Cloudflare 拦截或站点维护中）", it)
    }
}
```

#### JMT-17【中·安全】远端内容 → 请求目标，缺一道校验

`updateUrl()` 把远端文本**原样**写入 `URL_LIST_PREF`，而 `SharedPreferences.baseUrl` 随即把它当作请求目标：

```kotlin
val newList = response.body.string()                 // 来自 stevenyomi.github.io/source-domains/jmcomic.txt
if (newList != preferences.getString(URL_LIST_PREF, "")!!) {
    preferences.edit().setUrlList(newList, preferences.mirrorIndex).apply()
}
```

`baseUrl = "https://" + entry` 且 `entry` 只按 `,` 切分、无任何格式校验：
- 若该 GitHub Pages 仓库被入侵/域名被抢注，攻击者可把**所有用户后续的请求目标**改成任意域名（HTTP 头里的 Cookie、Referer 会一并带过去）；
- 即使非恶意，含空格/换行/`/`/`@`/`&` 的脏行也会产生畸形 URL（`https://evil.com@18comic.vip` 这种形式会静默改变真实 host）。

另有一处相关的判定缺陷：`if (!request.url.toString().startsWith(baseUrl))` —— `startsWith` 是**字符串前缀**比较，`https://18comic.vip.evil.tld/...` 也会被判定为"主站请求"，从而走进镜像自愈逻辑。

```kotlin
private val HOST_PATTERN = Regex("^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")

val hosts = response.body.string().split(',')
    .map { it.trim().lowercase() }
    .filter { HOST_PATTERN.matches(it) }        // 不合法的一律丢弃
if (hosts.isEmpty()) return false               // 绝不把脏数据写进偏好
preferences.edit().setUrlList(hosts.joinToString(","), preferences.mirrorIndex).apply()

// 同时把前缀比较换成 host 比较
private val baseHost by lazy { "https://".toHttpUrl().resolve(...) }   // 或缓存 baseUrl.toHttpUrl().host
if (request.url.host != baseHost) return chain.proceed(request)
```

#### JMT-18【中】"已更新"是个假信号

```kotlin
if (newList != preferences.getString(URL_LIST_PREF, "")!!) { ...写入... }
isUpdated = true
return true          // ← 只要 HTTP 成功就返回 true，内容是否变化并不影响
```

远端内容与本地一致（**大多数时候都一致**）时，用户依然会收到"镜像网址已自动更新，请在插件设置中选择合适的镜像"——被引导去做一件不需要做的事，而真正的失败原因（网络异常）反而被这条文案顶掉了。

```kotlin
val changed = newList != preferences.getString(URL_LIST_PREF, "")!!
if (changed) {
    preferences.edit().setUrlList(newList, preferences.mirrorIndex).apply()
    isUpdated = true
    return true
}
return false         // 内容没变 → 交回调用方重抛原始异常
```

（并建议：把 `isUpdated` 标 `@Volatile`；它目前非同步读、非同步写，多线程下可能重复拉取。）

#### JMT-19【中】脏偏好值 = 启动即崩

```kotlin
private val SharedPreferences.mirrorIndex get() = getString(USE_MIRROR_URL_PREF, "0")!!.toInt()   // L96
preferences.getString(MAINSITE_RATELIMIT_PREF, ...)!!.toInt()                                       // L61
preferences.getString(MAINSITE_RATELIMIT_PERIOD, ...)!!.toLong()                                    // L62
```

这三处都在**构造链**上（`baseUrl` → `client`）。偏好文件被外部改写、迁移脚本写入意外值、或数据损坏时，抛的是 `NumberFormatException`，且发生在源实例化阶段——表现为"源加载失败/空白"，没有任何可诊断信息。

```kotlin
private val SharedPreferences.mirrorIndex get() = getString(USE_MIRROR_URL_PREF, "0")?.toIntOrNull() ?: 0
private fun SharedPreferences.intPref(key: String, default: String) =
    getString(key, default)?.toIntOrNull() ?: default.toInt()
```

#### JMT-20【中】`SimpleDateFormat` 的线程安全（原 JMT-06 应升级）

```kotlin
private val dateFormat = SimpleDateFormat("yyyy-MM-dd", Locale.ENGLISH)   // 实例字段，可变状态
...
date_upload = dateFormat.tryParse(...)      // 在 chapterListParse 中被调用
```

`SimpleDateFormat` 内部维护可变的 `Calendar`，**非线程安全**。书架并行更新时 `chapterListParse` 可被多个线程同时进入，可能出现日期错乱、甚至抛 `ArrayIndexOutOfBoundsException`/`NumberFormatException`。原登记把它归为"仓库规范已废弃"的**技术债（低）**，实际应视为**并发缺陷（中）**。

```kotlin
private val dateFormat = DateTimeFormatter.ofPattern("yyyy-MM-dd", Locale.ENGLISH)

private fun parseDate(text: String?): Long = text?.trim()?.let {
    runCatching { LocalDate.parse(it, dateFormat).atStartOfDay(ZoneId.systemDefault()).toInstant().toEpochMilli() }
        .getOrDefault(0L)
} ?: 0L
```

#### JMT-21【中】图片分页：无上限的递归

```kotlin
tailrec fun internalParse(document: Document, pages: MutableList<Page>): List<Page> {
    ...
    val next = document.selectFirst("a.prevnext")
    return if (next == null) pages
    else internalParse(client.newCall(GET(next.attr("abs:href"), headers)).execute().asJsoup(), pages)
}
```

`tailrec` 保证不栈溢出，但**不限制次数**：站点若因改版/异常返回自指的 `a.prevnext`，会无限请求并无限增长 `pages`。另外 `execute()` 抛 `IOException` 时，已成功解析的前几页也一并丢弃，整章读不了。

```kotlin
private const val MAX_PAGE_CHUNKS = 300

tailrec fun internalParse(document: Document, pages: MutableList<Page>, depth: Int = 0): List<Page> {
    // ...原扫码逻辑...
    val next = document.selectFirst("a.prevnext")
    if (next == null || depth >= MAX_PAGE_CHUNKS) return pages
    val nextDoc = runCatching {
        client.newCall(GET(next.attr("abs:href"), headers)).execute().asJsoup()
    }.getOrNull() ?: return pages           // 中途失败：返回已取到的页，而不是全丢
    return internalParse(nextDoc, pages, depth + 1)
}
```

#### JMT-22【中】图片 URL 的隐式假设

```kotlin
if (!url.toString().contains("media/photos", ignoreCase = true)) return response   // 判定过宽
val pathSegments = url.pathSegments
val aid = pathSegments[pathSegments.size - 2].toInt()                             // 无校验
```

`contains` 只看子串，任何路径里出现 `media/photos` 的 URL 都会进入（含 `/media/photos/` 结尾、`/media/photos/album/banner.jpg` 等），随后 `toInt()` 抛 **`NumberFormatException`**。

```kotlin
val segments = url.pathSegments
if (segments.size < 3 || segments[segments.size - 3] != "photos" || segments[segments.size - 4] != "media") {
    return response
}
val aid = segments[segments.size - 2].toIntOrNull() ?: return response
```

#### JMT-23【中高】解码失败不降级：JMT-03 的真实触发路径

原登记（JMT-03）把它描述为"单张异常图导致整章加载失败"。结合 2.3 的链路顺序可以看到更常见的成因：**ScrambledImage 位于 Auth 之下，会拿到所有"最终响应"——包括非图片内容。** 会话失效的重试仍失败时、或源站瞬时限流返回 503/HTML 错误页时（§14.4.3 实测过这个现象），`BitmapFactory.decodeStream` 返回 `null`，紧接着 `input.height` 抛 NPE——用户看到的是一个读不出的章节，而不是"图片加载失败"。

```kotlin
// 一次性读入字节，既可判空、又能复用于降级返回
val bytes = input.use { it.readBytes() }
val bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
    ?: return responseBuilder
        .body(bytes.toResponseBody(response.body.contentType()))    // 非图片内容：原样返回
        .build()

val newBody = decodeImage(bitmap, getRows(aid, imgIndex)).asResponseBody(jpegMediaType)
return responseBuilder.body(newBody).build()
```

顺带解决 JMT-10（内存峰值）：单次 `readBytes()` 比 `decodeStream` + 二次编码更可控；若仍偏高，可给 `BitmapFactory.Options.inPreferredConfig = Bitmap.Config.RGB_565`（漫画图无 alpha，内存直接减半）。

**并把 `decodeImage` 的入参由 `InputStream` 改成 `Bitmap`，把"可能返回 null"的失败点收敛到调用处一处。**

#### JMT-24【低中】静默产出的空数据

```kotlin
private fun popularMangaFromElement(element: Element): SManga = SManga.create().apply {
    if (children.size >= 4) { ... }        // 不满足时什么都不填，但仍返回一个 SManga
```

- 列表项只靠 `children[0..3]` 下标取字段（JMT-04）；当结构不匹配时**返回一个 url 为 null、标题为空的 SManga**，列表里就出现点不开的空白条目；
- 详情页缩略图：`img?.extractThumbnailUrl()?.substringBeforeLast('.') + "_3x4.jpg"` —— `img` 为 null 时拼出 `"null_3x4.jpg"`（JMT-01），三个属性全缺时 `extractThumbnailUrl()` 返回 `""`，拼出 `"_3x4.jpg"`。

```kotlin
private fun popularMangaFromElement(element: Element): SManga? {
    val children = element.children()
    if (children.size < 4) return null
    // ...
    val href = children[0].selectFirst("a")?.attr("href")
    if (href.isNullOrBlank()) return null          // 无法打开的项目不产出
    setUrlWithoutDomain(href)
    // ...
}

// 调用处：.mapNotNull { popularMangaFromElement(it) }

// 缩略图统一写法
thumbnail_url = img?.extractThumbnailUrl()
    ?.takeIf { it.isNotBlank() }
    ?.substringBeforeLast('.')
    ?.plus("_3x4.jpg")
    .orEmpty()
```

#### JMT-25【低中·可维护性】搜索 URL 的位置耦合（建议一次性重构）

```kotlin
var params = filters.filterIsInstance<UriPartFilter>().joinToString("") { it.toUriPart() }
...
params = params.substringAfter("?")                       // 依赖"第一个 ? 之前是路径"
if (params.contains("search_query")) {
    val keyword = params.substringBefore("&").substringAfter("=")   // 依赖 search_query 必须在首位
    newQuery = "$newQuery+%2B$keyword"
    params = params.substringAfter("&")                   // 依赖后面还有其它参数
}
"$baseUrl/search/photos?search_query=$newQuery&page=$page&$params"
```

`Filters.kt` 里 4 个过滤器的取值同时使用了两种约定：`CategoryGroup` / `SortFilter` / `TimeFilter` 的值**自带** `?` 或 `&`，而 `TypeFilter` 的 `main_tag=0` 两种都没有（靠"排最后"）。于是 `searchMangaRequest` 的正确性依赖"值的内容"与"值在列表中的顺序"两件事同时成立——**任何一个 filter 的取值被改动，都会静默改变解析结果**（不报错，只是搜索行为变了）。

建议统一成"查询参数"模型，用 `HttpUrl.Builder` 拼装：

```kotlin
// Filters.kt：把"URL 片段"改成"参数对"
internal open class UriPartFilter(displayName: String, val vals: Array<Pair<String, String>>, defaultValue: Int = 0) :
    Filter.Select<String>(displayName, vals.map { it.first }.toTypedArray(), defaultValue) {
    open fun toParams(): List<Pair<String, String>> = vals[state].second
        .removePrefix("?").split('&').filter { it.isNotEmpty() }
        .map { it.substringBefore('=') to it.substringAfter('=', "") }
}
```

```kotlin
// Jinmantiantang.kt：用构建器代替字符串手术
val builder = baseUrl.toHttpUrl().newBuilder()
filters.filterIsInstance<UriPartFilter>().forEach { f -> f.toParams().forEach { (k, v) -> builder.addQueryParameter(k, v) } }
```

同一处还有 JMT-08 的加强版：`!query.contains("-")` 这个判定**过宽**——任何含连字符的关键词（`JK-OL`、`S1-no.1`、`BDSM-`）都会被静默切到"排除标签模式"，用户看到"搜索无结果"却无从得知原因。应改为按 token 判定：

```kotlin
val isExclusionQuery = query.split(' ').any { it.startsWith("-") }
```

#### JMT-26【低】base64 解包链路无失败信号

```kotlin
val html = Base64.decode(trimmedLine.substring(start, end), Base64.DEFAULT)
document.body().append(String(html))     // ← 平台默认字符集，但函数语义是 UTF-8
```

1. `String(html)` 用 `Charset.defaultCharset()`。Android 上是 UTF-8，所以目前**侥幸正确**，但这是隐式依赖：应写 `String(html, Charsets.UTF_8)`，与站点 JS 函数名 `base64DecodeUtf8` 对齐。
2. 整条链路（选择器命中 → 找到 `const html` 行 → 解出正文）**任一环节失效都没有任何信号**，最终表现为"详情页标题空白"。建议在选择器未命中时抛可读异常，例如未找到任何 `base64DecodeUtf8` 脚本时 `throw IOException("禁漫详情页结构已变化，请更新扩展")`——把"静默错误"变成"可上报的错误"，这是对抗站点改版最划算的一笔投入。

#### JMT-27【低】登录拦截器的两处边界

```kotlin
if (request.url.encodedPath == LOGIN_PATH) return chain.proceed(request)
```

`login()` 用的是 `client()`（= 宿主 `network.client`，**不含本拦截器**），所以递归在结构上不可能发生，这个短路是**防御性死代码**。它无害，但注释没说明"防的是谁"，后人容易误以为"递归风险靠这行兜住"从而放松对 `client()` 的约束。建议改注释为："防止其他调用方（或未来改动）用主 client 请求 /login 时再次进入登录逻辑"。

```kotlin
fun clearSession() { loggedInHost = "" }     // 只清标记，不动宿主 CookieJar 里的会话 Cookie
```

因此设置页那一行"清除登录状态"的**实际语义是"重置标记 → 下次请求用同一凭据重新登录"**，而不是用户通常理解的"退出登录"。JMT-L07 讨论了 `AndroidCookieJar.remove` 的可达性，但没有点出这个语义落差。最小成本的处理是改文案——标题"登录状态：已登录（host）"、摘要"点击可重置登录标记，下次请求会用当前账号重新登录"；配合 JMT-L06，在密码项变更时自动清空标记，用户改密码后无需手动操作。

#### JMT-28【低】设置项与封装

```kotlin
setOnPreferenceClickListener {
    preferences.edit().remove(LOGGED_IN_HOST_PREF).apply()   // ← 绕过 AuthManager 直接改键
    title = "登录状态：未登录"
    true
}
```

`LOGGED_IN_HOST_PREF` 因此有了两个写者（`AuthManager.loggedInHost` 与设置页），而 `AuthManager.clearSession()` 已是现成的等价入口——`addAuthPreferences` 接收的是 `preferences` 而不是 `authManager`，所以只能绕过去。建议把签名改为 `addAuthPreferences(screen, preferences, onClearSession: () -> Unit)`。

另外，用 `EditTextPreference` 冒充只读行是**对编译类路径约束的补丁**（注释已说明原因，很好）。但缺一句"何时可以撤掉"——按 §9 的迁移清单，libVersion 升到 1.6 后这个约束大概率消失。建议补 `TODO(libVersion>=1.6): 回归 androidx.preference.Preference`，否则这段"怪写法"会永久留存。

#### JMT-29【低】镜像自愈的跨域副作用

```kotlin
if (isUpdated || updateUrl(chain)) { throw IOException(...) }

@Synchronized
private fun updateUrl(chain: Interceptor.Chain): Boolean {
    val response = chain.proceed(GET("https://stevenyomi.github.io/source-domains/jmcomic.txt"))
```

`chain.proceed(newRequest)` 会**继续走完后续所有应用拦截器**。因为 `UpdateUrlInterceptor` 被插在第 0 位，这条 github.io 请求会依次穿过：宿主的 `CloudflareInterceptor`（对非 CF 域名也做一遍挑战检测）、`ScrambledImageInterceptor`（不匹配，放行）、以及 **`AuthManager.intercept`**——也就是说，**"探测镜像列表"会顺带触发一次禁漫登录**（若 `needsLogin` 为真）。这不是 bug，但属于不显然的职责耦合：一个用于"站点不可达"的自愈动作，会额外产生一次登录请求。

建议镜像探测使用独立的短连接客户端，或在拦截器里显式排除非主站 host：

```kotlin
private val probeClient = network.client.newBuilder()
    .apply { interceptors().clear(); addInterceptor(CloudflareInterceptor(...)) }   // 只保留必要能力
    .build()
```

同一处的性能小项：`rateLimit(...) { it.host == baseUrl.toHttpUrl().host }` 每个请求都会重新解析一次 `baseUrl`。既然 `baseUrl` 是 `val`，可提为 `private val baseHost by lazy { baseUrl.toHttpUrl().host }` 并复用（与 `AuthManager.baseHost` 保持一致）。

#### JMT-30【低·文档】文档与实现漂移

- `docs/jinmantiantang/02-runtime-and-network.md` §6.2 的拦截器链图只有 4 层（UpdateUrl / 宿主三件套 / ScrambledImage / RateLimit），**缺 Auth 拦截器**（§14 上线时未回填）。按这张图排查"登录为什么不生效"会得出错误结论。建议补一行 `├─ [应用拦截器] AuthManager.intercept（登录自愈）`，并注明它位于 ScrambledImage **之后**、RateLimit **之前**。
- §3 文件清单的行数快照已漂移：`Auth.kt` 实测 201 行（文档记 195），`Jinmantiantang.kt` 实测 324 行（文档记 323）。
- 建议把 2.3 的"顺序表"补进 §6.2——目前文档只给了装配代码，没有给出"最终生效顺序"这个更关键的结论。

---

## 五、对既有 JMT 登记的复核

| 编号 | 复核结论 |
| --- | --- |
| JMT-01 | ✅ 成立，且存在兄弟情形：属性全缺时拼出 `"_3x4.jpg"`（见 JMT-24） |
| JMT-02 | ✅ 成立。`Filters.kt:16` 与 `:18` 均为 `Pair("汉化", "/albums/doujin/sub/chinese?")` |
| JMT-03 | ✅ 成立，**触发路径需修正**：主因不是"单张坏图"，而是服务端返回非图片内容（限流页/错误页/会话失效页）时整章失败（见 JMT-23） |
| JMT-04 | ✅ 成立，且后果更明确：返回的是 **url 为空的空白条目**（见 JMT-24） |
| JMT-05 | ✅ 成立（`selectAuthor` 硬编码 `elements[3]`） |
| JMT-06 | ⚠️ **等级应从"低·技术债"升为"中·并发缺陷"**（见 JMT-20） |
| JMT-07 | ✅ 成立，属设计约束，已由 2.2 的初始化顺序解释 |
| JMT-08 | ⚠️ **描述范围需修正**：实际判定是 `query.contains("-")`，误伤面远大于"排除语法与关键词互斥"（见 JMT-25） |
| JMT-09 | ✅ 成立，**补充第二种误报**：远端内容未变化也报"已自动更新"（见 JMT-18） |
| JMT-10 | ✅ 成立，修复方案已并入 JMT-23 |
| JMT-11 | ✅ 成立。已确认 `Element.select()` 在 Jsoup 中**包含自身**，故 `value.select("a").text()` 对 `<a>` 元素确实返回其自身文本——代码正确，但依赖了这条不成文的语义，建议改为 `value.ownText()` 以免后人"顺手重构"引入真 bug |
| JMT-12 | ✅ 成立，属外部依赖风险，无法在扩展侧消除，只能靠"错位检测/告警"缓解 |

---

## 六、值得保留的设计（不要在重构中改掉）

1. **不接管会话**：凭证完全交给宿主 `AndroidCookieJar`，扩展只记 `loggedInHost`。避免"两个真相来源"——这是本项目最关键的正确决策。
2. **登录是被动增强**：`needsLogin` 在凭据为空时恒为 `false`，老用户行为零变化（§14.9 的 A1 决策）。
3. **登录请求走 `network.client`**：既避开本扩展拦截器链，又继承 CookieJar 与 Cloudflare 能力。
4. **失效判据用服务端明确信号**（最终落点为 `/error/album_missing`），不猜页面内容、不做正则匹配 HTML。
5. **`needsLoginNow` 先取值**：正确区分"本次刚登过"与"本地以为已登录"，避免重试风暴。
6. **`AuthManager` 的 4 参数构造注入**：不反向依赖主类，是整个扩展里唯一可独立测试的模块。
7. **`ScrambledImageInterceptor` 是无状态 `object`**：天然线程安全，且对 aid < 220980 直接放行，不做无谓解码。
8. **装配顺序有明确意图并有文档**：`add(0, updateUrl)` 与后续追加的区别、限速器限定主站 host，都在 §6 有据可查。
9. **算法有溯源注释**（`ScrambledImageInterceptor.kt:48-50` 指向站点 HTML 的 `function scramble_image`），站点改版时能快速定位对照点。

---

## 七、修复优先级建议

**P0（先做，成本极低，直接消除用户可见故障）**

| 项 | 改动量 |
| --- | --- |
| JMT-23 + JMT-03 + JMT-10 | 单文件 ~15 行，把所有"解码失败"从"整章失败"降级为"放行原响应" |
| JMT-22 | 3 行（`toIntOrNull` + 段判定） |
| JMT-13 | ~6 行（正则替换 `removePrefix` 组合） |
| JMT-14 | ~8 行（越界 + 非数字 + 协议头） |
| JMT-19 | 3 处 `toIntOrNull() ?: 默认值` |
| JMT-16 | ~6 行（`runCatching` → `IOException`） |

**P1（结构性问题，一次性做掉）**

- JMT-15：登录加锁（~8 行，收益是消除登录风暴）
- JMT-20：`SimpleDateFormat` → `java.time`（~10 行）
- JMT-21：分页上限 + 失败兜底（~8 行）
- JMT-18 / JMT-17：镜像自愈的"内容变化判定"与"域名格式校验"（~20 行，同时消掉一个安全信任边界）

**P2（可维护性，建议随下次上游适配一起做）**

- JMT-25：搜索 URL 改用 `HttpUrl.Builder`（改动面最大，但能同时修掉 `contains("-")` 误判）
- JMT-24 / JMT-26：空值与失败信号（决定"站点改版时是静默失效还是明确报错"）
- JMT-29 / JMT-28 / JMT-27 / JMT-30：职责解耦与文档回填
- 把纯函数（`getRows`、`md5LastCharCode`、搜索参数拼装、状态映射）抽为顶层函数并补 `kotlin.test`：本地没有 Gradle 环境，但 **CI 有**——把"唯一验证手段是实机"变成"提交即由 CI 跑单测"，是这套工程里性价比最高的一步。

---

## 八、本次审查的验证方式

- 代码基线：`git log -1` = `60cfe97f`，`git status -- src/zh/jinmantiantang` 无输出（工作副本与 fork main 一致）
- 工具函数行为已核对源码，非推测：
  - `core/src/main/kotlin/keiyoushi/utils/Json.kt:37` —— `Response.parseAs` 使用注入的 `jsonInstance` 并 `use{}` 关闭响应
  - `core/src/main/kotlin/keiyoushi/utils/Jsoup.kt:11` —— `asJsoup()` 设置 baseUri = 请求 URL（故 `abs:href` 可用）并关闭响应
  - `core/src/main/kotlin/keiyoushi/network/RateLimit.kt:54` —— `rateLimit` 注册的是 `addNetworkInterceptor`，并额外插入一个 `TaggingInterceptor`（应用拦截器）
- 未执行编译与实机验证（本机无 Android 构建环境），缺陷判定均基于代码路径推导；JMT-15 / JMT-17 / JMT-18 建议在实机上按 §11.3 验证清单补充一项"并发登录观测"。

---

## 九、CI 实跑验证记录（2026-09-12 晚）

本节取代上面"未执行编译与实机验证"一句：流水线已实际运行并逐项核对过。

### 9.1 两次真实运行

| run | commit | 触发 | 结论 | 耗时 |
| --- | --- | --- | --- | --- |
| 34701043192 | `37ebb064` | push（CI 改动） | ✅ success | ~2.5 min |
| 34701606476 | `29d550f0` | push（Auth.kt 修复） | ✅ success | ~2.5 min |

两次运行的 `Build` 与 `Publish to repo branch` 两个 job 全部步骤均为 success；
`Report build failure` / `Report publish failure` 为 skipped，即没有走过失败分支。

### 9.2 发布产物的独立核对（不只信绿灯）

| 检查项 | 结果 |
| --- | --- |
| 线上 `repo/index.min.json` | `versionCode 104061` / `versionName 1.4.61` / `badgeLabel JLD` |
| `repo/index.pb` | 前两字节 `1f 8b`（gzip，与上游 `publish-repo.py` 一致） |
| APK 内部 manifest | `versionCode 104061`（解析二进制 AXML；旧包 104059 用于自校验解析方法） |
| APK 签名证书 SHA-256 | `9E:AE:77:A0:…:49:12`，与索引 `signingKey` 完全一致（keytool 确认） |

结论：Mihon 会认定为"有新版本"且签名一致，不会要求重新信任。

`out/jinmantiantang/…v1.4.59.apk` 的证书是 `BE:AF:F8:98:…`，**与索引不一致** —— 它是配置签名
secret 之前的测试产物，不能当作"已发布包"来对照签名。

### 9.3 版本号自动推进已在线上验证

模块文件里始终是 `versionCode = 59`（CI 只在构建工作区临时改写，不提交），而线上索引已走到
104061：说明 `ensure-version-bump.py` 读线上索引、按"已发布值 + 1"改写模块值的链路在真实环境
生效，日常改代码不必再手工动版本号。

### 9.4 本次对 Auth.kt（fork 独有文件）的修复

| 缺陷 | 处理 |
| --- | --- |
| JMT-15 并发登录无去重 | `login()` / `reLogin()` 加 `loginLock` + 双重检查；新增 `performLogin()` 承载真实登录；会话失效自愈（清标记 + 重登）改为原子完成 |
| JMT-16 异常类型不契约 | 解析失败（CF 挑战 / 维护页返回 HTML）统一转 `IOException`，附可读中文文案 |
| 注释与实现不符 | `/login` 短路分支的注释改为说明真实用途（不是为了防递归） |

上游文件（`Jinmantiantang.kt` / `Preferences.kt` / `ScrambledImageInterceptor.kt` / `Filters.kt`）
本次**一行未动**。与上游 main 逐行对比，我们的主类差异恰好是那 9 行插桩，别无其它改动。

### 9.5 本地 clone 的两个已知怪象（不影响 CI，CI 每次全新 clone）

1. 53 个扩展文件在工作区里停在 2026-09-04 的状态（blob 哈希与那次同步完全一致），
   `git add -A` 会提交一次"上游回退"。还原：`git checkout -- CONTRIBUTING.md lib-multisrc src`。
2. `packed-refs` 里的 `refs/remotes/origin/main` 写不进去（`git fetch` 报告更新成功、
   `git update-ref` 返回 0，读回仍是旧值），于是 `git status` 会误报 `[ahead 2]`。
   请以 `git ls-remote origin main` 或 API 为准；`git reset --hard origin/main` 这类命令慎用。
