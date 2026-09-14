# 禁漫天堂扩展 · 标识与构建契约

> 本文件是「禁漫天堂扩展技术档案」文档集的一部分。
> 索引：[`docs/README.md`](../README.md)
> 包含全局章节：§1、§2（**全局编号跨文件连续，请勿重排**）

---

## 1. 标识与派生常量

### 1.1 目录与包名

```
仓库路径        src/zh/jinmantiantang/
源码包名        eu.kanade.tachiyomi.extension.zh.jinmantiantang
Android 命名空间 eu.kanade.tachiyomi.extension      （由 ExtensionPlugin 固定）
applicationId   eu.kanade.tachiyomi.extension.zh.jinmantiantang
                = namespace + "." + pkgName
pkgName         "zh.jinmantiantang"                 （未设 pkgName 覆盖，取目录后缀）
```

### 1.2 源 ID（极其重要，改动即用户数据失联）

计算规则见 `gradle/build-logic/.../ExtensionPlugin.kt:323`：

```
key    = "<name.lowercase()>/<lang>/<versionId>"
id     = MD5(key) 的前 8 字节按大端拼成 Int64，再 & Long.MAX_VALUE
```

本扩展的具体值（`[推导]` 按上述规则精确计算）：

```
key  = "禁漫天堂/zh/1"
id   = 6286738698187452081
```

**该 ID 决定的资源**：

| 资源 | 位置 |
| --- | --- |
| SharedPreferences 文件名 | `source_6286738698187452081` |
| 过滤数据缓存目录 | `<cacheDir>/source_6286738698187452081/` |

**变更红线**：`name`（`禁漫天堂`）、`lang`（`zh`）、`versionId`（默认 1）三者任一改动，ID 都会变，用户的镜像选择、限速设置、屏蔽词列表会全部回到默认值。若必须改，需用 `source { id = <旧值> }` 显式钉住旧 ID。

### 1.3 版本号派生

| 项 | 计算式 | 当前值 |
| --- | --- | --- |
| `versionName` | `"$libVersion.$versionCode"` | `1.4.59` |
| `androidVersionCode` | `libVersion` 各段补零成两位拼接 → ×1000 → +versionCode | `104 × 1000 + 59 = 104059` |
| `versionCode`（DSL） | 手工维护，改代码须递增 | `59` |
| 主题叠加 | 本扩展无 `theme`，不参与叠加 | — |

> `104` 的来源：`"1.4"` 各段补零成两位得 `"0104"`，转 Int 即 `104`。

### 1.4 构建产物 `[推导]`

```
APK  src/zh/jinmantiantang/build/outputs/apk/release/tachiyomi-zh.jinmantiantang-v1.4.59.apk
JAR  src/zh/jinmantiantang/build/outputs/jar/release/tachiyomi-zh.jinmantiantang-v1.4.59.jar
元数据 src/zh/jinmantiantang/build/keiyoushi-source-info.json
```

产物文件名模板见 `ExtensionPlugin.kt:196`：`"tachiyomi-${pkgName}-v${versionName}"`。

### 1.5 运行时入口

```
Manifest 元数据  tachiyomi.extension.class = keiyoushi.source.Generated
生成类           internal class Generated : Jinmantiantang()
```

由 KSP 处理器 `compiler/.../SourceProcessor.kt` 生成。因为本模块是**单个 source + 抽象类**，走 `buildSingleSourceClass()` 分支，生成的是子类而非 `SourceFactory`。

## 2. 构建契约（build.gradle.kts）

```kotlin
plugins { alias(kei.plugins.extension) }

keiyoushi {
    name = "Jinman Tiantang"           // 仓库索引里的显示名，不带语言后缀
    versionCode = 59
    contentWarning = ContentWarning.NSFW
    libVersion = "1.4"
    source {
        name = "禁漫天堂"               // 单源级别覆盖显示名（实际显示的中文名）
        lang = "zh"
        baseUrl = "https://18comic.vip"
    }
    deeplink {
        host("18comic.vip"); host("18comic.ink")
        host("jmcomic-zzz.one"); host("jmcomic-zzz.org")
        path("/album/..*")
    }
}
dependencies { implementation(project(":lib:randomua")) }
```

### 2.1 DSL 各字段的实际作用范围

| 字段 | 影响面 |
| --- | --- |
| `name` | 仓库索引名、生成的 Manifest 元数据（`tachiyomix.name`） |
| `source.name = "禁漫天堂"` | KSP 生成 `override val name`，即**用户界面显示的名字**；同时参与源 ID 计算 |
| `source.baseUrl` | **仅用于元数据与深链 host 推导**，运行时被类自身 override（见 2.2） |
| `versionCode` | 版本号三处派生（见 1.3） |
| `contentWarning` | 生成的 Manifest 中 `tachiyomi.extension.nsfw=1`、`tachiyomix.contentWarning=2` |
| `libVersion` | 决定 `compileOnly` 依赖：`1.4` → `com.github.keiyoushi:extensions-lib:18a8e26be2` |
| `deeplink` | 生成的 Manifest 中 `UrlActivity` 的 intent-filter |

### 2.2 baseUrl 的双轨制（易踩坑）

主类第 42 行自行 override：

```kotlin
override val baseUrl: String = "https://" + preferences.baseUrl
```

`SourceProcessor` 检测到这一情况（`overridden` 含 `baseUrl` 且 DSL 为 static）后会打印警告并**跳过生成 baseUrl**：

```
baseUrl is provided by Jinmantiantang; skipping generated baseUrl
(DSL baseUrl is used for metadata/hosts only)
```

因此：

- **运行时实际请求的域名** = 用户在设置里选的镜像
- **DSL 里的 `18comic.vip`** = 只写进索引元数据 + 给深链推导默认 host

### 2.3 deeplink host 与源码常量必须手工同步

| 来源 | 值 |
| --- | --- |
| `build.gradle.kts` 的 4 个 `host(...)` | `18comic.vip`、`18comic.ink`、`jmcomic-zzz.one`、`jmcomic-zzz.org` |
| `Preferences.kt:85` 的 `SITE_ENTRIES_ARRAY` | 完全相同的 4 个域名 |

源码 `Preferences.kt:84` 留有注释 `// Please also update AndroidManifest`——这是 manifest 尚需手写时代的遗留提醒。**新增主线域名时必须同时改这两处**，否则从浏览器点链接打不开对应站点。
