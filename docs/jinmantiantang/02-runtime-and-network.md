# 禁漫天堂扩展 · 运行时与网络链路

> 本文件是「禁漫天堂扩展技术档案」文档集的一部分。
> 索引：[`docs/README.md`](../README.md)
> 包含全局章节：§3、§4、§6（**全局编号跨文件连续，请勿重排**）

---

## 3. 文件清单与职责矩阵

| 文件 | 行数 | 职责 | 对外暴露 |
| --- | --- | --- | --- |
| `build.gradle.kts` | 31 | 声明身份、版本、分级、深链、依赖 | — |
| `Jinmantiantang.kt` | 323 | 主类。列表/搜索/详情/章节/图片五段解析 + 拦截器装配 | `@Source abstract class` |
| `Auth.kt` | 195 | 账号登录与会话自愈；账号相关设置项 | `AuthManager`、`addAuthPreferences()`、偏好键常量 |
| `Preferences.kt` | 161 | 设置项定义、镜像地址解析、镜像自愈拦截器 | `getPreferenceList()`、`baseUrl`、`UpdateUrlInterceptor`、`preferenceMigration()` |
| `Filters.kt` | 131 | 4 个过滤器 + `UriPartFilter` 基类 | `CategoryGroup`、`SortFilter`、`TimeFilter`、`TypeFilter`、`UriPartFilter` |
| `ScrambledImageInterceptor.kt` | 111 | 分块打乱图片还原 | `object ScrambledImageInterceptor` |
| `res/mipmap-*/ic_launcher.png` | 6 个 | 图标（含少见的 `ldpi`） | — |

依赖关系：`Jinmantiantang.kt` 依赖其余四个同包文件；`ScrambledImageInterceptor` 是 `object`（单例），无状态、无外部依赖；`Auth.kt` 通过构造参数接收 `preferences` / `baseUrl` / `headers` / `client` 四个 lambda，不反向依赖主类。

## 4. 运行时对象模型

```
@Source abstract class Jinmantiantang : HttpSource(), ConfigurableSource
  ├── 由 libVersion 1.4 决定：基类是上游 eu.kanade.tachiyomi.source.online.HttpSource
  ├── 实现 ConfigurableSource → 提供 setupPreferenceScreen()
  └── abstract → 由 KSP 生成 internal class Generated : Jinmantiantang()

成员初始化顺序（决定行为）：
  1. preferences      = getPreferences { preferenceMigration() }     L40
  2. baseUrl          = "https://" + preferences.baseUrl             L42  ← 依赖 1，一次性求值
  3. updateUrlInterceptor = UpdateUrlInterceptor(preferences)        L44
  4. client           = ... 装配拦截器 ...                            L47-56 ← 依赖 2、3
```

**关键约束**：`baseUrl` 是 `val`，在对象构造时求值一次。用户在设置里改镜像后，已构造的源实例不会更新 → **必须重启应用**（设置项 summary 中已明示）。

## 6. 网络链路

### 6.1 拦截器装配（L47-56）

```kotlin
override val client: OkHttpClient = network.client
    .newBuilder()
    .apply { interceptors().add(0, updateUrlInterceptor) }   // 插到应用拦截器最前
    .addInterceptor(ScrambledImageInterceptor)               // 追加到应用拦截器最后
    .rateLimit(
        preferences.getString(MAINSITE_RATELIMIT_PREF, MAINSITE_RATELIMIT_PREF_DEFAULT)!!.toInt(),
        preferences.getString(MAINSITE_RATELIMIT_PERIOD, MAINSITE_RATELIMIT_PERIOD_DEFAULT)!!.toLong().seconds,
    ) { it.host == baseUrl.toHttpUrl().host }                // 仅限主站 host
    .build()
```

### 6.2 执行顺序

```
请求发出
 ├─ [应用拦截器] UpdateUrlInterceptor          第 0 位（仅主站 URL）
 ├─ [应用拦截器] UncaughtExceptionInterceptor  ┐
 │              UserAgentInterceptor           │ 由宿主 App 的 network.client 提供
 │              CloudflareInterceptor          ┘
 ├─ [应用拦截器] ScrambledImageInterceptor     仅 media/photos 且 aid ≥ 220980
 └─ [网络拦截器] RateLimitInterceptor          仅主站 host
        ↓
     站点
```

**注意**：本类直接 `=` 覆盖了 `client`，**不经过** `KeiSource` 那套强校验装配（`KeiSource` 会断言三个拦截器存在、把 Cloudflare 移到自定义拦截器之后、把限速器固定在末位）。这是 1.4 世代扩展的普遍状况。

### 6.3 `UpdateUrlInterceptor` 状态机（Preferences.kt:116-161）

```
intercept(chain):
  url 不以 baseUrl 开头              → 直接 proceed
  proceed 成功                       → 直接返回
  proceed 失败 / 抛异常：
      ├─ call.isCanceled() 或 message 含 "Cloudflare"  → 原样抛出（不触发自愈）
      ├─ isUpdated == true                            → 抛 IOException(中文提示)
      └─ updateUrl(chain) 返回 true                   → 抛 IOException(中文提示)
         否则                                          → 重抛原异常

updateUrl(chain)  [@Synchronized]
  GET https://stevenyomi.github.io/source-domains/jmcomic.txt
  失败/非 2xx → 返回 false
  成功且内容与已存不同 → 写入 URL_LIST_PREF
  isUpdated = true; 返回 true
```

**本地缓存的新线路列表**：默认 `18comic-ive.club,18comic-aspa.org,18comic-wantgo.cc`（`Preferences.kt:92`），远端地址 `https://stevenyomi.github.io/source-domains/jmcomic.txt`（L144）。

抛出的用户可见文案（L135）：

> 镜像网址已自动更新，请在插件设置中选择合适的镜像网址并重启应用（如果反复提示，可能是服务器故障）

**设计评价**：把「主站不可达 → 拉取新线路 → 通知用户」压缩进一个拦截器，用异常作为通知载体。副作用是**任何**主站请求失败（包括单次网络抖动）都会触发一次远端拉取与一条用户可见错误。

### 6.4 请求头

```kotlin
override fun headersBuilder() = super.headersBuilder()
    .set("Referer", "$baseUrl/")
    .setRandomUserAgent()          // lib/randomua，每次随机
```

未设置 `Origin`（1.4 的 `HttpSource` 不自动加，`KeiSource` 才会）。
