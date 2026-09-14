# 禁漫天堂扩展 · 设置项规格

> 本文件是「禁漫天堂扩展技术档案」文档集的一部分。
> 索引：[`docs/README.md`](../README.md)
> 包含全局章节：§8（**全局编号跨文件连续，请勿重排**）

---

## 8. 设置项规格

设置页由 `setupPreferenceScreen`（`Jinmantiantang.kt:313-317`）装配，共 **9 行**，来自三个来源：

| 来源 | 行数 | 说明 |
| --- | --- | --- |
| `Auth.kt` 的 `addAuthPreferences()` | 3 | 账号 / 密码 / 登录状态（§8.7） |
| `Preferences.kt` 的 `getPreferenceList()` | 4 | 限速 / 镜像 / 屏蔽词（§8.1） |
| `lib/randomua` 的 `addRandomUAPreference()` | 2 | 随机 UA / 自定义 UA（§8.5） |

装配顺序：**账号 → 网络 → 内容**。

### 8.1 本扩展自定义的 4 项（`Preferences.kt:12-57`）

| 序 | SharedPreferences 键 | 类型 | 标题 | 默认值 | 取值域 | 副标题（summary） |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `mainSiteRateLimitPreference` | ListPreference | 在限制时间内（下个设置项）允许的请求数量。 | `"1"` | 1–10 | 说明文本 + `\n当前值：%s` |
| 2 | `mainSiteRateLimitPeriodPreference` | ListPreference | 限制持续时间。单位秒 | `"3"` | 1–60 | 说明文本 + `\n当前值：%s` |
| 3 | `useMirrorWebsitePreference` | ListPreference | 使用镜像网址 | `"0"` | 0 – (4 + 动态数量 − 1) | `<当前镜像描述>\n<自愈状态文案>` |
| 4 | `BLOCK_GENRES_LIST` | EditTextPreference | 屏蔽词列表 | `// 例如 "YAOI cos 扶他 毛絨絨 獵奇 韩漫 韓漫", 关键词之间用空格分离, 大小写不敏感, "//"后的字符会被忽略` | 自由文本（`dialogTitle` = 「关键词列表」） | 无 |

第 1、2 项的文案均含 **「需要重启软件以生效」**——因为 `client` 与 `rateLimit` 在源实例构造时固化（§4）。

第 3 项的副标题是**二选一**（`Preferences.kt:43`）：

```kotlin
summary = if (isUrlUpdated) "%s\n镜像列表已自动更新，请选择合适的镜像并重启应用。"
          else             "%s\n镜像列表会自动更新。重启后生效。"
```

其中 `%s` 由 ListPreference 自动替换为**当前选中项的文本**，格式为 `"<描述> (<域名>)"`，例如 `主站1 (18comic.vip)`。

**该副标题是一个可读的状态指示器**：`isUrlUpdated` 来自 `UpdateUrlInterceptor.isUpdated`（§6.3），为 `true` 说明**本次源实例存活期间曾触发过镜像自愈**。

### 8.2 镜像地址解析（Preferences.kt:59-65）

```kotlin
val SharedPreferences.baseUrl: String
    get() {
        val list = SITE_ENTRIES_ARRAY                      // 4 个固定
        val index = mirrorIndex
        if (index in list.indices) return list[index]
        return urlList.getOrNull(index - list.size) ?: list[0]   // 动态段，越界回落到主站1
    }
```

| 下拉项下标 | 值 |
| --- | --- |
| 0 – 3 | 主站1 `18comic.vip` / 主站2 `18comic.ink` / 东南亚线路1 `jmcomic-zzz.one` / 东南亚线路2 `jmcomic-zzz.org` |
| 4+ | 来自 `URL_LIST_PREF` 的逗号分隔列表，显示为 `内地线路N` |

选项文本 = `"${描述} (${域名})"`，选项值 = 下标字符串（`Preferences.kt:26-46`）。

### 8.3 索引越界防护（Preferences.kt:109-114）

```kotlin
fun SharedPreferences.Editor.setUrlList(urlList: String, oldIndex: Int): SharedPreferences.Editor {
    putString(URL_LIST_PREF, urlList)
    val maxIndex = SITE_ENTRIES_ARRAY.size + urlList.count { it == ',' }
    if (oldIndex in 0..maxIndex) return this
    return putString(USE_MIRROR_URL_PREF, maxIndex.toString())   // 越界则回落到最后一个
}
```

`maxIndex` 的推导：固定 4 项 + N 个动态项 = 4 + N 个元素，合法下标 0..(4+N-1)；而 `count { it == ',' }` 对 N 个逗号分隔项正好等于 N-1，故 `4 + (N-1) = 4+N-1`，与最大合法下标一致。

### 8.4 设置迁移（Preferences.kt:99-107）

```kotlin
fun SharedPreferences.preferenceMigration() {
    if (getString(DEFAULT_LIST_PREF, "")!! != DEFAULT_LIST) {
        edit()
            .remove("overrideBaseUrl")                 // 清理已废弃的旧键
            .putString(DEFAULT_LIST_PREF, DEFAULT_LIST)
            .setUrlList(DEFAULT_LIST, mirrorIndex)
            .apply()
    }
}
```

触发时机：`getPreferences { preferenceMigration() }`（`Jinmantiantang.kt:40`），**每次源实例构造时执行**——因为 `getPreferences` 的 `migration` 参数不是惰性块，会立即调用。`DEFAULT_LIST_PREF` 存的是「上次迁移时用的默认列表」，用以判断是否需要重跑。

### 8.5 复用 `lib/randomua` 的 2 项（`UserAgentPreference.kt:59-92`）

由 `screen.addRandomUAPreference()`（`Jinmantiantang.kt:307`）注入，与本扩展代码无关，但属于该设置页的可见部分：

| 序 | SharedPreferences 键 | 类型 | 标题 | 默认值 | 副标题 |
| --- | --- | --- | --- | --- | --- |
| 5 | `pref_key_random_ua_` | ListPreference | Random user agent string | `"off"` | `"%s"`（自动显示当前项） |
| 6 | `pref_key_custom_ua_` | EditTextPreference | Custom user agent string | 无（空） | `Leave blank to use the default user agent string` |

**`Random user agent string` 的选项**（`UserAgentPreference.kt:95-96`）：

| 显示 | 存储值 |
| --- | --- |
| `OFF` | `off` |
| `Desktop` | `desktop` |
| `Mobile` | `mobile` |

**两项之间存在 UI 级互斥**：

```kotlin
// 第 6 项的 enabled 状态由第 5 项决定
setEnabled(preferences.getPrefUAType() == UserAgentType.OFF)

// 第 5 项变更时同步第 6 项的可用性
setOnPreferenceChangeListener { _, newValue -> customUaPref.setEnabled(newValue == "off"); ... }
```

即：**只在随机 UA 为 OFF 时，自定义 UA 才可编辑**。两者都改时均 Toast `Restart the app to apply changes`。

**运行时优先级**（`UserAgentPreference.kt:34-54`，`setRandomUserAgent()`）：

```
随机 UA 类型 != OFF          → 生成随机 UA（忽略自定义值）
否则 自定义值非空白           → 使用自定义 UA
否则                        → 不设置 User-Agent，沿用宿主默认
```

自定义值在提交时会用 `Headers.headersOf("User-Agent", value)` 做合法性校验，非法则 Toast 拒绝，不写入。

**与构建期规则的关联**：`SpotlessPlugin.RandomUAChecker` 强制「源码引用了 `keiyoushi.lib.randomua` 就必须 `override fun getMangaUrl(`」。本扩展满足了该约束（`Jinmantiantang.kt:210`）。原因合理——随机 UA 会让站点看到的客户端标识每次不同，若不同步覆盖 `getMangaUrl`，"在 WebView 中打开"等入口可能使用不一致的 UA 而被站点区别对待。

**一处遗留瑕疵**：两个 key 均以 `_` 结尾（`pref_key_random_ua_` / `pref_key_custom_ua_`），形似「待拼接 source id 的前缀」。但代码中并未拼接。由于 SharedPreferences 文件本身已按源隔离（`source_<id>`），该下划线冗余但无害。

### 8.6 实测界面快照

以下为实机截图（2026-09-12）与本档案的对照，用于验证 §8.1–§8.5 的准确性：

| 截图显示 | 对应档案条目 | 一致性 |
| --- | --- | --- |
| 页面标题「禁漫天堂 (ZH)」 | 源名 = `禁漫天堂`（KSP 注入），语言 = `zh` | ✅ 宿主在设置页标题追加 ` (<语言大写>)`，此为宿主行为 |
| 「在限制时间内（下个设置项）允许的请求数量。」当前值：**5** | §8.1 第 1 项 | ✅ 标题/格式一致；**当前值 5 ≠ 默认值 1，说明该设置被改动过** |
| 「限制持续时间。单位秒」当前值：**3** | §8.1 第 2 项 | ✅ 与默认值一致 |
| 「使用镜像网址」→ `主站1 (18comic.vip)` | §8.1 第 3 项 + §8.2 下标 0 | ✅ 文本格式 `"<描述> (<域名>)"` 完全吻合 |
| 其副标题「镜像列表会自动更新。重启后生效。」 | §8.1 第 3 项的 **else 分支** | ✅ 说明 `isUrlUpdated == false`，即本次源实例**未触发过镜像自愈** |
| 「屏蔽词列表」（无副标题） | §8.1 第 4 项 | ✅ |
| 「Random user agent string」显示 `OFF` | §8.5 第 5 项 | ✅ |
| 「Custom user agent string」呈可编辑态 + `Leave blank to use the default user agent string` | §8.5 第 6 项 | ✅ `OFF` 状态下该项 enabled，与互斥逻辑一致 |

**结论**：实机界面与源码推导的 6 项设置**逐项吻合**，无偏差。

> ⚠️ 该快照拍摄于登录功能实现**之前**（2026-09-12 15:32），因此**未包含 §8.7 的 3 个账号项**。下次实机验证时应重新截图并覆盖本节。

### 8.7 账号相关 3 项（`Auth.kt`，新增）

由 `addAuthPreferences(screen, preferences)` 装配，**位于设置页最前面**。设计依据见 §14。

| 序 | 标题 | 类型 | SharedPreferences 键 | 默认值 | 说明 |
| --- | --- | --- | --- | --- | --- |
| 0 | 禁漫账号 | EditTextPreference | `jmUsername` | `""` | `dialogTitle` = 「请输入禁漫账号」；summary = 「填入账号密码后自动登录，可解锁少量需要登录的题材」 |
| 1 | 密码 | EditTextPreference | `jmPassword` | `""` | `dialogTitle` = 「请输入密码」；summary = 「留空则不使用登录功能」；输入框做 `TYPE_TEXT_VARIATION_PASSWORD` **掩码** |
| 2 | 登录状态 | Preference（**无 key，不持久化**） | — | — | 标题动态显示「登录状态：未登录」或「登录状态：已登录（域名）」；点击清除登录态 |

**行为要点**：

- 账号与密码**留空时登录功能完全不启用**，扩展行为与旧版本一致（设计决策 A1，见 §14.9）
- 登录状态项的标题在**每次打开设置页时重新计算**（`setupPreferenceScreen` 会被重新调用），无需刷新机制
- 「点击清除登录状态」只清除本地的「已登录域名」记录；会话 Cookie 由宿主 CookieJar 持有，下次请求会重新登录
- 密码以**明文**存入 `source_6286738698187452081`（生态惯例，见 JMT-L02）
