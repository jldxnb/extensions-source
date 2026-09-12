# 禁漫天堂扩展 · 登录态

> ✅ **状态：已实现**（2026-09-12）。接口契约由实抓 HAR 确定，代码见 `src/zh/jinmantiantang/.../Auth.kt`。
> §1–§13 描述代码现状，本文（§14）记录登录功能的**接口契约、设计依据与实现**。
> 尚未实机验证的项在 §14.10 单独列出。
>
> 索引：[`docs/README.md`](../README.md) · 本文对应全局章节 §14

---

## 14.0 状态总览

| 项 | 状态 | 依据 |
| --- | --- | --- |
| 需求确认 | ✅ | 用户选定「方案 A：齿轮填账密，自动登录」 |
| 站点接口实测 | ✅ | 2026-09-12 实抓 HAR（`har/18comic.vip_login.har`、`har/18comic.vip_nologin.har`） |
| 宿主能力确认 | ✅ | 已读宿主源码（见 §14.5） |
| CSRF 需求 | ✅ **无需** | 实测表单无 token 字段，页面无 csrf 关键词 |
| CF 是否阻塞登录 | ✅ **不阻塞** | 实测登录接口一次成功返回 200 |
| 凭证载体 | ✅ **Cookie**（非 localStorage） | 见 §14.3 |
| 失败/失效判据 | ✅ **已确定**（与初版设计不同） | 见 §14.6.4 |
| 登录失败的响应形态 | ✅ **已实测** | `status:2` + `errors[0]` 为可展示文案，见 §14.2.3 |
| `submit_login` 取值 | ✅ **已确认 = `"1"`** | 见 §14.2.1 |
| 代码实现 | ✅ **已完成** | `Auth.kt` 200 行；主类挂载见 §14.7.3 |
| **CI 编译通过** | ✅ | run 34685907943，产物已上传（见 §14.16） |
| 实机功能验证 | ❌ **未做** | 见 §14.12 验收清单 |

**实测推翻了两处初版假设**，见 §14.2.3 与 §14.6.4 的「⚠️ 修正」标记。

---

## 14.1 需求

### 14.1.1 用户诉求

> 「设计一个能够保持登录状态存在的功能。就想 picacomic 的齿轮部分，就可以填入用户名和密码，这样的话就能够保持登录的状态，以获取更多的资源。」

### 14.1.2 目标（完成定义）

1. 扩展设置页（源列表右侧齿轮）中出现**账号 / 密码**两个输入项
2. 填写后自动完成登录，**无需用户每次手动操作**
3. 登录态**跨应用重启保持**
4. 登录态**失效时能自动恢复**
5. 未填写凭据时**不改变现有行为**

### 14.1.3 非目标

- 不做注册、找回密码、多账号切换
- 不做签到（`/ajax/user_daily_sign`）—— 见 §14.10 附注

---

## 14.2 站点登录机制（实测确定）

**来源：2026-09-12 实抓 HAR**，域名 `18comic.vip`。以下为原始证据，非推测。

### 14.2.1 请求形态

```
POST https://18comic.vip/login
```

| 项 | 实测值 |
| --- | --- |
| 状态码 | **`200`** |
| Content-Type | `application/x-www-form-urlencoded; charset=UTF-8` |
| 表单字段 | `username`、`password`、`submit_login`（取值实测为 **`1`**） |
| 响应 Content-Type | `application/json` |
| 成功响应体 | `{"status":1,"errors":["/"]}` |
| 失败响应体 | `{"status":2,"errors":["無效的用戶名和/或密碼！_1"]}` |

**必需请求头**（实测存在）：

| 头 | 值 |
| --- | --- |
| `X-Requested-With` | `XMLHttpRequest` |
| `Origin` | `https://18comic.vip` |
| `Referer` | `https://18comic.vip/` |
| `sec-fetch-dest` | `empty` |
| `sec-fetch-mode` | `cors` |

### 14.2.2 ⚠️ 修正 1：这是 AJAX 调用，不是表单提交

**初版设计基于第三方开源客户端的文档，认为登录是普通表单 POST、成功标志为 HTTP 301。实测证明这是错的。**

证据：

- 请求带 `X-Requested-With: XMLHttpRequest` 与 `sec-fetch-mode: cors`
- 响应码是 **200 而非 301**
- 响应体是 **JSON**：`{"status":1,"errors":["/"]}`

**影响**：
1. 成功判据**不能看状态码**（成功失败都是 200），**必须解析响应体**
2. 必须显式携带 `X-Requested-With: XMLHttpRequest`
3. 第三方文档中「成功 = 301」的描述针对的是**非 AJAX 的旧版登录路径**，不适用于当前站点

### 14.2.3 成功/失败信号（已完整实测）

**HTTP 状态码无区分度** —— 成功与失败**都返回 200**。唯一的信号在响应体的 `status` 字段：

| `status` | 含义 | `errors` 字段 | 实测样本 |
| --- | --- | --- | --- |
| `1` | **登录成功** | `["/"]`（疑似跳转目标） | `{"status":1,"errors":["/"]}` |
| `2` | **凭据无效** | `["無效的用戶名和/或密碼！_1"]` | 两次独立尝试结果一致 |

**`errors[0]` 是站点直接给出的、面向用户的中文错误文案，可直接展示。** 不必自己编提示语。

> 文案末尾的 `_1` 疑为站点内部的计数或占位后缀，建议**原样展示**，不做二次加工（避免站点改格式后解析失败）。

### 14.2.4 无 CSRF 防护

实测表单仅有 `username` / `password` / `submit_login` 三个字段，无任何 token 字段。首页 HTML 中 `csrf`、`authenticity` 关键词出现 **0 次**。

> 对比：同仓库的 `mangadash` 需要先 GET 登录页抽取 `csrf-token`。**禁漫不需要。**

### 14.2.5 关于「AVS」

`AVS` 并非某个令牌的名称，而是站点所用 CMS 的名字 —— **A**dult**V**ideo**S**cript。证据：站点 CSS/JS 中出现 `AVS Bootstrap Core Theme v3.0` 与 `adultvideoscript.com`。

第三方文档所称的「AVS cookie」应理解为**该 CMS 的默认会话 cookie 名**。本设计**不依赖该名字**（原因见 §14.5.3）。

---

## 14.3 凭证载体：Cookie（已排除 localStorage）

这是决定方案 A 能否成立的关键问题。**结论：凭证是服务端下发的 Cookie。**

排查过程：

| 假设 | 检验 | 结果 |
| --- | --- | --- |
| 凭证在登录响应体里 | 响应体为 `{"status":1,"errors":["/"]}` | ❌ 无 token、无 session id |
| 凭证存 localStorage | 首页 HTML 中 localStorage 仅用于 `hide-float-image-jmn`（UI 偏好） | ❌ 不存凭证 |
| 凭证存 sessionStorage | 使用次数为 3，无凭证特征 | ❌ 排除 |
| 凭证是 Cookie | 页面引用 `jquery.cookie.min.js`，`$.cookie` 出现 12 次 / `document.cookie` 4 次；登录后首页出现 `logout` 链接（服务端渲染的已登录状态） | ✅ **成立** |

**推论**：登录响应体不含任何可作为凭证的字符串，因此凭证只能由 `Set-Cookie` 下发；服务端能渲染出「登出」链接，说明它凭 Cookie 识别用户。

> **辅证**：登录后访问 `GET /album/519180/...` 返回 200（461 KB 真实作品页）；未登录访问同一 URL 返回 301（见 §14.6.4）。同一 URL 的差异只可能来自请求携带的 Cookie。

### ⚠️ 关于本次 HAR 中「没有 Cookie」的说明

HAR 中 `set-cookie` 字面出现 **0 次**，所有 `cookies` 数组为空，无任何 `Cookie` 请求头。

**这不是抓取失误**：Chrome 自 **v130** 起，DevTools 导出的 HAR **默认经过「清理」（sanitized）**，会移除 `Cookie`、`Set-Cookie`、`Authorization` 等敏感头。若要导出未清理版本，需在 DevTools → 设置 → 偏好设置 → 网络 → 勾选「允许生成包含敏感数据的 HAR」，然后**长按**导出按钮选择未清理版本。

**该缺失不影响本设计**（见 §14.5.3）。若后续需要确认 cookie 名，再补抓一次未清理版本。

---

## 14.4 登录能解锁什么（实测验证）

### 14.4.1 实测对比

同一受限作品 URL（`/album/519180/...`）：

| 状态 | 结果 |
| --- | --- |
| **未登录** | `GET` → **301** → `Location: https://18comic.vip/error/album_missing` → 该错误页 200 |
| **已登录** | `GET` → 首次 **503**（无响应体）→ 重试 **200**，响应体 **461,121 字符** |

**结论：登录确实是访问受限题材的前提。** 用户「以获取更多的资源」的诉求成立。

### 14.4.2 与 PicACG 的定位差异

| | PicACG | 禁漫天堂 |
| --- | --- | --- |
| 不登录能否使用 | ❌ 完全不可用（全站 API 需 token） | ✅ 大部分内容可用 |
| 登录的收益 | 是可用性前提 | 解锁少量受限题材 |
| 错误提示必要性 | 必须强制引导登录 | 可为静默增强 |

**因此：登录是本扩展的「可选增强」，不是「可用性前提」。** 这决定了 §14.9 的默认行为选择。

### 14.4.3 附注：503 现象

登录版首次请求作品页返回 **503 且无响应体**，立即重试即成功。这不像是登录问题，更像**源站/CF 的瞬时限流**。

> 关联线索：现有扩展代码中已有一段 `rateLimit(1, 3s)`，注释为 `// Add rate limit to fix manga thumbnail load failure`。两者可能是同类现象。

**推论**：登录流程本身**不应**依赖这种重试；但扩展已有限速器，无需额外处理。

---

## 14.5 宿主侧支撑能力（已读源码）

### 14.5.1 `NetworkHelper`

`core/common/src/main/kotlin/eu/kanade/tachiyomi/network/NetworkHelper.kt`：

```kotlin
val cookieJar = AndroidCookieJar()

private val clientBuilder: OkHttpClient.Builder = run {
    val builder = OkHttpClient.Builder()
        .cookieJar(cookieJar)              // ← 客户端自带持久化 CookieJar
        ...
}

val client = clientBuilder
    .addInterceptor(CloudflareInterceptor(context, cookieJar, ::defaultUserAgentProvider))
    .build()
```

### 14.5.2 `AndroidCookieJar`

`core/common/src/main/kotlin/eu/kanade/tachiyomi/network/AndroidCookieJar.kt`：

```kotlin
class AndroidCookieJar : CookieJar {
    private val manager = CookieManager.getInstance()          // android.webkit.CookieManager

    override fun saveFromResponse(url: HttpUrl, cookies: List<Cookie>) {
        cookies.forEach { manager.setCookie(url.toString(), it.toString()) }
    }
    override fun loadForRequest(url: HttpUrl): List<Cookie> = get(url)
    ...
    fun remove(url: HttpUrl, cookieNames: List<String>? = null, maxAge: Int = -1): Int { ... }
}
```

### 14.5.3 三条关键推论

| # | 结论 | 对设计的影响 |
| --- | --- | --- |
| 1 | CookieJar 由 `android.webkit.CookieManager` 支撑，**自动落盘、跨应用重启保持** | **扩展无需实现「保持登录」**；登录一次长期有效 |
| 2 | 扩展的 `client = network.client.newBuilder()...` 继承同一 CookieJar | 登录响应的 `Set-Cookie` 被自动接收并持续带上，**无需手动解析、无需 `addCookie` 注入、无需知道 cookie 名** |
| 3 | 该 CookieJar 与 WebView、与 `CloudflareInterceptor` 共用 | CF 挑战解出的凭证会持久化；「在 WebView 中打开」也是已登录状态 |

**这使方案 A 的实现量大幅低于初始估计。** 扩展只需：判断是否需要登录 → 发一次登录 POST → 记住登录状态。

---

## 14.6 参考实现：PicACG 的可迁移模式

参考对象：`src/zh/picacomic/.../Picacomic.kt`（同仓库，397 行）。
辅助参考：`src/pt/mangadash/.../MangaDash.kt`（cookie 型表单登录）。

### 14.6.1 可迁移清单

| PicACG 的做法 | 行号 | 禁漫适配 | 迁移性 |
| --- | --- | --- | --- |
| 拦截器内**懒登录**：`if (token.isEmpty()) getToken()` | 57 | `if (!isLoggedIn()) ensureLoggedIn()` | ✅ **核心思路，直接搬** |
| **短路登录接口自身**，防递归 | 53-55 | 改为短路 `encodedPath == "/login"` | ✅ **必须搬** |
| **失效自愈**：401 → 重登 → 重试一次 | 63-67 | 信号完全改写，见 §14.7.4 | ⚠️ **思路搬，信号换** |
| **凭证持久化属性**（自定义 setter 写回 prefs） | 287-291 | 存 `loggedInHost` 而非 token | ✅ 结构搬 |
| 齿轮内两个 `EditTextPreference` | 301-309 | 同 | ✅ 完全一致 |
| **凭据为空抛中文 `IOException`** | 358 | 同（默认行为另议，见 §14.9） | ✅ 文案搬 |
| `getToken()` / `fetchToken()` **分两层** | 357-371 | 拆 `ensureLoggedIn()` / `performLogin()` | ✅ 直接搬 |
| 登录请求走 `network.client` 而非 `this.client` | 387-389 | 同（防递归） | ✅ 搬 |
| `request.applyToken()` 手动注入 `Authorization` | 391 | **不需要** —— CookieJar 自动带 | ❌ **省略** |

### 14.6.2 最重要的简化

PicACG 需要在**每一次请求**上手动注入凭证（`applyToken()`），因为它用的是自定义请求头。禁漫用的是标准 Cookie，**由 CookieJar 在 OkHttp 内部自动完成注入**。

> **拦截器里不需要「改写请求」这一步，只保留「决策」这一步。**

### 14.6.3 PicACG 没有的坑：镜像域绑定（本扩展独有）

`AVS`（会话 Cookie）**绑定域名**，第三方客户端文档对此有醒目警告。而本扩展的 `baseUrl` 是**用户可切换的**（4 个固定镜像 + 动态线路，见 §8.2）。

> **换镜像后必须重新登录。**

设计上以 `loggedInHost` 承载该约束（§14.7.1）。

### 14.6.4 ⚠️ 修正 2：失效判据

**初版设计假设**：未登录会被重定向到 `/login`，故用 `encodedPath == "/login"` 判定。

**实测推翻**：站点**不**跳登录页，而是伪装成「作品不存在」——

```
未登录访问受限作品：
  GET /album/519180/<title>
    → 301  Location: /error/album_missing
  GET /error/album_missing
    → 200（错误页）
```

**修正后的判据**（OkHttp 默认跟随重定向，`response.request.url` 是最终落点）：

```kotlin
response.request.url.encodedPath == "/error/album_missing"
```

该判据的优点：

1. 是**服务端明确给出的信号**，不需要猜测页面内容
2. 与「作品真的不存在」在语义上重合 —— 但两者对扩展而言**处理方式相同**（都该重登一次再试，若仍失败则如实报错）
3. 只在访问受限内容时触发，天然懒惰

**副作用**：对于真正不存在的作品，会多一次无谓的登录重试。这是可接受的代价。

---

## 14.7 设计

### 14.7.1 数据模型

| 项 | 存储位置 | 键名（实现值） | 默认值 |
| --- | --- | --- | --- |
| 用户名 | 源级 SharedPreferences（`source_6286738698187452081`） | `jmUsername` | `""` |
| 密码 | 同上 | `jmPassword` | `""` |
| 已登录域名 | 同上 | `jmLoggedInHost` | `""`（host，不含 scheme） |

**不存储会话 Cookie** —— 它由 CookieJar 管理，重复存储会造成两个真相来源。

### 14.7.2 登录状态判定

```
needsLogin =
     用户名非空 && 密码非空          ← 未填凭据时恒为 false（可选增强）
  && loggedInHost != 当前镜像 host    ← 域不一致即需重登
```

### 14.7.3 拦截器结构

实现见 `Auth.kt` 的 `AuthManager.intercept()`。核心结构：

```kotlin
fun intercept(chain: Interceptor.Chain): Response {
    val request = chain.request()

    // ① 登录请求自身放行，否则递归
    if (request.url.encodedPath == LOGIN_PATH) return chain.proceed(request)

    // ② 懒登录：只在真的要发请求时才检查（对标 PicACG L57）
    val needsLoginNow = needsLogin
    if (needsLoginNow) login()

    // ③ 不改写请求 —— CookieJar 自动带会话 Cookie（PicACG 此步被省略，见 §14.6.2）
    var response = chain.proceed(request)

    // ④ 会话失效自愈（替代 PicACG 的 401 分支，判据见 §14.6.4）
    if (!needsLoginNow && isConfigured && response.request.url.encodedPath == LOGIN_ERROR_PATH) {
        response.close()
        clearSession()
        login()
        response = chain.proceed(request)      // 每个请求最多重试一次，不递归
    }

    return response
}
```

**为什么先把判定存进 `needsLoginNow`**：登录成功后 `loggedInHost` 已被写入，此时再读 `needsLogin` 会得到 `false`，就无法区分「本次请求刚登录过」与「本地以为已登录」。前者不该再重试（刚登完还失败说明作品真不存在），后者才需要自愈重登。

**⚠️ 注意 ④ 的 `isConfigured` 守卫**：未配置凭据的用户访问不存在的作品时，不应被尝试登录。这与 §14.9 的 A1 决策一致。

### 14.7.4 一键重登的边界

重试**仅一次**，且不递归：

- 若重登后仍返回 `/error/album_missing` → 说明作品确实不存在，或凭据无效 → 原样返回响应
- 若登录接口本身失败 → `performLogin()` 抛 `IOException`，用户看到明确提示

### 14.7.5 齿轮 UI 设计

账号项**置于设置页最前面**，按「账号 → 网络 → 内容」语义排序：

| 序 | 标题 | 类型 | key | 说明 |
| --- | --- | --- | --- | --- |
| 0 | 禁漫账号 | EditTextPreference | `jmUsername` | 用 `dialogTitle` 去掉输入框里的默认提示 |
| 1 | 密码 | EditTextPreference | `jmPassword` | `TYPE_TEXT_VARIATION_PASSWORD` 掩码；summary 说明「留空则不使用登录功能」 |
| 2 | 登录状态 | Preference（无 key，不持久化） | — | 标题显示「未登录 / 已登录（域名）」；点击清除登录态 |

现有 6 项（§8.1 的 4 项 + §8.5 的 2 项）**保持不变**，追加在账号项之后。

---

## 14.8 实现落点

| 文件 | 变更 | 行数 |
| --- | --- | --- |
| `Auth.kt` | **新增**：偏好键、`LoginResult` DTO、`AuthManager`、`addAuthPreferences()` | 200 |
| `Jinmantiantang.kt` | 新增 `authManager` 字段；`client` 链上加拦截器；`setupPreferenceScreen` 首行接入账号项 | 323（+9） |
| `Preferences.kt` | 无变更 | 161 |
| `build.gradle.kts` | `versionCode` 58 → **59** | — |

**与初版骨架的六处差异**（前 4 处为实现时的修正，后 2 处为 CI 编译期修正，均非笔误）：

1. **不抛「请填写账号密码」** —— 初版骨架沿用了 PicACG 的强制登录思路。但 `needsLogin` 在凭据为空时恒为 `false`，`login()` 根本不会被调用，那个异常是**不可达代码**。改为 `login()` 开头 `if (!isConfigured) return`。
2. **缓存 `baseHost`** —— 主类 `baseUrl` 是一次性求值的 `val`，运行期不变，故用 `by lazy` 缓存 host，避免每个请求都重新 `toHttpUrl()` 解析。
3. **密码输入框掩码** —— 同仓库 `e621` 有同样写法。PicACG 未做掩码，这里比它严一点。
4. **不做登录状态自动刷新** —— 状态项在每次打开设置页时重新渲染（`setupPreferenceScreen` 会被重新调用），无需额外机制。
5. **登录状态行改用 `EditTextPreference`** —— 基类 `Preference` 在本扩展的编译类路径上无法以 `Preference(context)` 形式构造，见 §14.8.1。
6. **`SharedPreferences.getString()` 返回 `String?`** —— 状态行改用 `orEmpty()` 取出 `host` 再判断，见 §14.8.1。

### 14.8.1 CI 编译期修正记录

首两次 CI 运行在 `compileReleaseKotlin` 阶段失败，暴露出**本地无法察觉**的两处问题：

| # | 编译错误 | 根因 | 修正 |
| --- | --- | --- | --- |
| 1 | `Auth.kt:184 Too many arguments for 'constructor(): Preference'` | **全仓库没有任何扩展直接构造过 `Preference(context)`**——3 个 import 它的文件都只把它当类型用。本扩展的编译类路径上该基类无法以此形式构造，而其子类（`EditTextPreference` / `ListPreference` / `PreferenceScreen`）均可正常构造 | 登录状态行改用 `EditTextPreference`，配合 `setOnBindEditTextListener { it.inputType = TYPE_NULL }` 与「点击监听器返回 true」实现只读操作行（同仓库 `mangadash` 的信息行写法）；同步移除该 import |
| 2 | `Auth.kt:189:67 Only safe (?.) or non-null asserted (!!.) calls allowed on a nullable receiver 'String?'` | `SharedPreferences.getString()` 在 Kotlin 中返回 **`String?`**，状态行里对它直接调 `.isBlank()` | 改为先 `orEmpty()` 取出 `host` 再判断，顺带避免重复查询 |

**经验教训**：

- 初版骨架里那个「请填写账号密码」异常是**不可达代码**——`needsLogin` 在凭据为空时恒为 `false`，`login()` 不会被调用。写代码时没发现，直到整理差异清单才意识到。**推导出的代码路径要重新审视可达性。**
- `SharedPreferences.getString()` 返回可空值，而仓库惯用写法是 `getString(...)!!`。初版状态行用了 `orEmpty()`，重写时把空值处理弄丢了。**重写已有逻辑时要对照原实现的可空性处理。**
- 这两处都无法在本地发现（本地没有可用的 Gradle/编译环境），**完全依赖 CI 的反馈**。这正是要搭好这条 CI 链路的原因。

---

## 14.9 待决策项：凭据为空时的行为

PicACG 是「不登录就完全不可用」，因此敢在凭据为空时直接抛异常。**禁漫不是**（§14.4.2），照搬会误伤现有用户。

| 选项 | 凭据为空时 | 凭据已填但登录失败时 | 影响 |
| --- | --- | --- | --- |
| **A1（推荐）** | 静默跳过，保持现状 | 抛中文异常 | 现有用户零影响；登录是纯增量 |
| A2 | 抛异常要求配置 | 抛中文异常 | 强制登录，与 PicACG 一致，但现有用户全部报错 |
| A3 | 静默跳过 | 静默跳过，仅记日志 | 用户无法感知失败 |

**§14.7.3 与 §14.8 已按 A1 编写**（② 与 ④ 均带 `username.isNotBlank()` 守卫）。若选 A2，去掉守卫即可。

**待用户确认。**

---

## 14.10 残留待验证项

### ~~A. 登录失败的响应形态~~ ✅ 已实测解决（2026-09-12）

实测结果：`status = 2`，`errors[0] = "無效的用戶名和/或密碼！_1"`。两次独立尝试一致。

**结论**：可直接把 `errors[0]` 作为用户提示文案，无需自己编写。设计已按此更新（§14.8）。

### ~~B. `submit_login` 的取值~~ ✅ 已实测解决

实测为 **`"1"`**。设计已按此固定（§14.8）。

### C. 会话 Cookie 的名字（无影响）

因 Chrome 清理，本次无法看到 Cookie 名。**本设计不依赖它**（§14.5.3）。

仅当未来想加「登录前先检查 cookie 是否存在」这类优化时才需要。

### 附注：签到接口

HAR 中出现 `GET /ajax/user_daily_event`，第三方文档另提到 `POST /ajax/user_daily_sign`。若登录可行，可顺带实现自动签到。**本项目范围内不实现。**

### D. 运行时行为未实机验证（**当前唯一未验证项**）

以上全部为**接口契约**层面的验证，均已由 HAR 证据支撑。但**代码本身从未在真机上跑过**：

| 待验证 | 风险 |
| --- | --- |
| 登录 POST 在 Android OkHttp 上能否一次成功（UA/Cookie/CF 环境与桌面浏览器不同） | 中 |
| 宿主 `AndroidCookieJar` 是否确实接收并持久化会话 Cookie | 中（依据宿主源码推断，非实测） |
| 换镜像后 `loggedInHost` 机制是否按预期触发重登 | 低 |
| `/error/album_missing` 判据在真实会话失效时是否命中 | 中 |

**验证方式**：按 §14.12 清单实机走一遍。若某项失败，回到 §14.13.3 补抓对照 HAR 定位差异。

---

## 14.11 风险登记

| 编号 | 等级 | 风险 | 说明 |
| --- | --- | --- | --- |
| JMT-L01 | ~~高~~ **低** | ~~CF 拦截登录 POST~~ | **实测已解除**：登录接口一次返回 200。CF 挑战只出现在 `/media/users/`（头像）与 `/captcha` 上（403 + `cf-mitigated: challenge`），不影响 API 调用 |
| JMT-L02 | **高** | 密码明文存储 | 写入 `source_<id>` 明文。生态惯例（PicACG 亦然），但自签 APK 场景下风险更高。缓解：改用方案 B 存 Cookie，或配合 `lib/cryptoaes` 加密 |
| JMT-L03 | 中 | 镜像切换导致静默失效 | 已由 `loggedInHost` 处理；用户换镜像后会多一次登录请求 |
| JMT-L04 | 中 | `/error/album_missing` 判据可能变化 | 若站点改版换成别的错误路径，重登将不触发。表现为「受限内容打不开且不提示」 |
| JMT-L05 | 低 | 登录请求被限流 | 登录走 `network.client`，**不经过**本扩展的 `RateLimitInterceptor` |
| JMT-L06 | 低 | 凭据变更无即时反馈 | 改密码后需等下次失败才重登；可在密码项变更时主动清空 `loggedInHost` |
| JMT-L07 | 低 | 「清除登录态」依赖宿主 API | `AndroidCookieJar.remove` 在扩展侧可达性未验证。退化方案：只清 `loggedInHost` |
| JMT-L08 | 低 | 503 瞬时限流被误判 | 实测作品页首次请求可能 503。当前设计不处理，交由宿主 OkHttp 重试机制 |
| JMT-L09 | 低 | 依赖 `status` 数值语义 | 实测 `1`=成功、`2`=凭据无效。若站点新增其他状态码（如风控 `3`），会被归入「失败」并用 `errors[0]` 提示——行为可接受，但提示文案可能不准确。加了兜底文案（§14.8） |

---

## 14.12 验收清单

- [ ] 不填账号密码 → 现有功能完全不受影响（热门/最新/搜索/阅读/受限内容报「作品不存在」）
- [ ] 填入正确账号密码 → 能浏览，且**重启 App 后仍为登录态**
- [ ] 填入错误密码 → 出现明确的中文错误提示，而非静默失败
- [ ] 登录前后访问同一受限作品：前者 301 → `/error/album_missing`，后者 200 且有正文
- [ ] 切换镜像 → 自动针对新域名重新登录
- [ ] 在 WebView 中打开站点 → 显示为已登录（验证 CookieJar 共享）
- [ ] 手动清除登录态 → 后续请求重新登录
- [ ] 清除 App 数据 → 全部设置回到默认，不崩溃

---

## 14.13 HAR 证据附录

### 14.13.1 证据文件

| 文件 | 大小 | 内容 |
| --- | --- | --- |
| `har/18comic.vip_login.har` | 60 MB / 609 条目 | 登录全过程 + 登录后访问受限作品 |
| `har/18comic.vip_nologin.har` | 5.8 MB | 未登录访问同一受限作品 |
| `har/18comic.vip_wrongPassword.har` | 88 KB / 7 条目 | 两次错误密码登录 |

> 三个文件均已通过 `.gitignore` 的 `/har/` 规则排除出版本控制（含个人会话数据）。

> **注意**：Chrome v130+ 默认导出「已清理」HAR，**不含 Cookie / Set-Cookie / Authorization**。这是浏览器行为，不是抓取失误（§14.3）。

### 14.13.2 关键证据索引

| 结论 | 证据位置 |
| --- | --- |
| 登录是 AJAX + JSON，非表单 301 | `POST /login` → 200，`application/json`，`{"status":1,"errors":["/"]}` |
| 表单三字段 | `POST /login` 的 postData：`username`、`password`、`submit_login=1` |
| 成功信号 | 登录版 `POST /login` → `{"status":1,"errors":["/"]}` |
| 失败信号 | 错误密码版 `POST /login` → `{"status":2,"errors":["無效的用戶名和/或密碼！_1"]}`（两次一致） |
| HTTP 码无区分度 | 成功与失败**均为 200** |
| 无 CSRF | 首页 HTML 中 `csrf`/`authenticity` 命中 0 次 |
| 未登录 = 伪装的 404 | 未登录版 `GET /album/519180/...` → 301 → `/error/album_missing` |
| 登录后受限内容可读 | 登录版同一 URL → 200，响应体 461,121 字符 |
| CF 不拦登录 | `POST /login` 一次 200；挑战仅见于 `/media/users/`（403 + `cf-mitigated: challenge`） |
| 凭证非 localStorage | 首页 localStorage 仅 `hide-float-image-jmn` |
| 凭证是 Cookie | 页面引用 `jquery.cookie.min.js`，`$.cookie` 12 次，登录后首页含 `logout` |

### 14.13.3 复现方法

```bash
# 用浏览器打开 devtools → Network → Preserve log，完成登录后导出 HAR
# 如需含 Cookie 的未清理版本：
#   设置 → 偏好设置 → 网络 → 勾选「允许生成包含敏感数据的 HAR」
#   然后长按导出按钮 → 选择「导出 HAR（包含敏感数据）」
```

---

## 14.14 落地后需同步的档案章节

| 章节 | 需更新的内容 | 状态 |
| --- | --- | --- |
| §3 文件清单 | 新增 `Auth.kt`，更新行数与职责矩阵 | ✅ 已同步 |
| §5.11 设置界面装配 | 登录项加入后的装配顺序 | ✅ 已同步 |
| §8 设置项规格 | 新增 3 项（§8.7） | ✅ 已同步 |
| §8.6 实测快照 | 需重截（新增账号项） | ⬚ 待实机 |
| §12 宿主侧集成 | 若登录改变扩展/源列表表现 | ✅ 无需改 |
| §11.2 行号索引 | 所有新增/移动的行号 | ✅ 已同步 |
| §10 风险登记 | JMT-L01…L09 | ⬚ 待实机后转正 |
| 本文 §14.0 | 状态标记 | ✅ 已更新 |

---

## 14.15 CI 构建记录

### 14.15.1 运行历史

| run | commit | 结论 | 失败原因 |
| --- | --- | --- | --- |
| 34684043567 | `904d1a9f` | ❌ failure | `Auth.kt:184 Too many arguments for 'constructor(): Preference'` |
| 34685121691 | `889b7d40` | ❌ failure | `Auth.kt:189:67 Only safe (?.) ... calls allowed on nullable receiver 'String?'` |
| **34685907943** | **`64564dc4`** | ✅ **success** | — |

### 14.15.2 产物

| 项 | 值 |
| --- | --- |
| artifact 名称 | `jinmantiantang` |
| 大小 | 452,058 字节（0.4 MB，含 APK + JAR + source-info） |
| 过期时间 | 2026-09-26（14 天） |
| 网页入口 | https://github.com/jldxnb/extensions-source/actions/runs/34685907943 |

### 14.15.3 自诊断机制

fork 上无仓库管理权限，无法通过 `/actions/jobs/{id}/logs` 下载日志（返回 403）。
为此 workflow 增加了 `Report build failure` 步骤：

- 把 Gradle 输出中匹配 `FAILURE:` / `^e: ` / `What went wrong` / `> Task .* FAILED` / `Caused by` 的行
  以 **`::error::` 检查注解** 形式输出（注解可用公开 API `/check-runs/{id}/annotations` 读取）
- 同时把**最后 120 行**完整输出写入 **job summary**

这样即使没有仓库管理权限，也能从公开 API 定位失败原因。本次调试正是靠它拿到的编译错误。
