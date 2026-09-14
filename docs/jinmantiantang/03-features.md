# 禁漫天堂扩展 · 功能规格

> 本文件是「禁漫天堂扩展技术档案」文档集的一部分。
> 索引：[`docs/README.md`](../README.md)
> 包含全局章节：§5（**全局编号跨文件连续，请勿重排**）

---

## 5. 功能规格

### 5.1 人气榜

| 项 | 内容 |
| --- | --- |
| 触发 | 应用请求「热门」 |
| 请求 | `GET $baseUrl/albums?o=mv&page={page}` （L64） |
| 参数含义 | `o=mv` = order by most views |
| 解析 | `popularMangaParse`（L66） |
| 翻页判定 | 存在 `a.prevnext` 元素即认为有下一页（L71） |
| 后置 | `.filterGenre()` 屏蔽词过滤 |

### 5.2 最新更新

| 项 | 内容 |
| --- | --- |
| 请求 | `GET $baseUrl/albums?o=mr&page={page}` （L100） |
| 参数含义 | `o=mr` = order by most recent |
| 解析 | 直接复用 `popularMangaParse`（L102） |
| `supportsLatest` | `true`（L38，直接赋值而非 getter） |

### 5.3 列表项解析（列表/搜索共用）

`popularMangaFromElement`（L84-97）按**子元素下标**取字段：

```
element = div.list-col > div.p-b-15:not([data-group])
  ├── 预处理：若 children[0] 是 <a>，先 removeAt(0)          L86
  └── 要求 children.size >= 4，否则整个 SManga 留空          L87
      children[1].text()                     → title
      children[0].selectFirst("a").attr(href) → url（setUrlWithoutDomain）
      children[0].selectFirst("img")          → thumbnail_url
      children[2].select("a") 逗号拼接         → author
      children[3].select("a") 逗号拼接         → genre
```

**缩略图 URL 取法**（`extractThumbnailUrl`，L212-217）——按优先级回退：

```
data-original  →  src  →  data-cfsrc  →  ""
```

然后 `.substringBeforeLast('?')` 去掉查询串。

### 5.4 屏蔽词过滤

| 项 | 内容 |
| --- | --- |
| 入口 | `filterGenre()`（L75-82），在列表解析末尾调用 |
| 存储键 | `BLOCK_GENRES_LIST`（`Preferences.kt:67`） |
| 解析规则 | `getString(...).substringBefore("//").trim()`，再 `lowercase().split(' ')` |
| 匹配方式 | 作品的 `genre` 字段 `lowercase().split(", ")` 与屏蔽词**任一项相等**即剔除 |
| 默认值 | 以 `//` 开头的示例文本 → `substringBefore("//")` 得空串 → **默认不过滤** |

**设计要点**：默认值整段以 `//` 开头，因此默认状态下 `substringBefore("//")` 返回空串，等于「未启用」。用户需自行改写为 `关键词A 关键词B // 备注` 的形式，`//` 之后的内容会被忽略。这是一个「把注释语法当开关」的巧妙但隐晦的设计。

### 5.5 编号 / 链接直达

`fetchSearchManga` 重写（L113-130），三路分支：

```
入参 query
├─ 以 "https://" 开头
│   ├─ host != 当前 baseUrl 的 host  →  throw Exception("Unsupported url")   L117
│   └─ host 匹配 → titleid = url.pathSegments[1]
│                  递归调用 fetchSearchManga(page, "JM:$titleid", filters)    L120
├─ 以 "JM" 开头（忽略大小写）或 纯数字
│   └─ id = query.removePrefix("JM").removePrefix(":")
│      client.newCall(GET $baseUrl/album/{id}) → searchMangaByIdParse         L124-126
│      searchMangaByIdParse：复用详情解析 → 强制 url="/album/{id}/" → 包成单条 MangasPage
└─ 其他
    └─ super.fetchSearchManga() → 走常规搜索
```

常量（L311-312）：

```kotlin
private const val PREFIX_ID_SEARCH_NO_COLON = "JM"
const val PREFIX_ID_SEARCH = "JM:"
```

`removePrefix` 对 `"JM:123"` 的效果：先去掉 `"JM"` 得 `":123"`，再去掉 `":"` 得 `"123"`；对 `"123"` 两次都无匹配 → 保持 `"123"`。

### 5.6 关键词搜索 URL 拼装

`searchMangaRequest`（L133-158），两条互斥路径：

**路径 A — 关键词不以 `-` 开头**（走站点搜索页）

```
newQuery = query.replace("+", "%2B").replace(" ", "+")
           ↑ "+" 转义为 %2B（AND 语义）
                              ↑ 空格转 + （OR 语义）
params   = 所有 UriPartFilter 的 toUriPart() 拼接后 substringAfter("?")
若 params 含 "search_query"（即分类选了 /search/photos? 型）：
    keyword = params.substringBefore("&").substringAfter("=")
    newQuery = "$newQuery+%2B$keyword"
    params   = params.substringAfter("&")
URL = "$baseUrl/search/photos?search_query=$newQuery&page=$page&$params"
```

**路径 B — 关键词为空，或含 `-`**（走目录页 / 标签排除）

```
params = 拼接结果（为空则用 "/albums?"）
若 query 为空：
    URL = "$baseUrl$params&page=$page"
否则（提取所有 - 开头的词做排除）：
    removedGenres = query.split(" ").filter { it.startsWith("-") }
                          .joinToString("+") { it.removePrefix("-") }
    URL = "$baseUrl$params&page=$page&screen=$removedGenres"
```

**源码自述的限制**（L152 注释）：

> 在搜索栏的关键词前添加-号来实现对筛选结果的过滤, 像 `"-YAOI -扶他 -毛絨絨 -獵奇"`, 注意此时搜索功能不可用

即：`-` 排除语法与关键词搜索**不能同时使用**。

### 5.7 详情解析（含 base64 隐藏 HTML 解包）

站点把真实详情 HTML 藏在 `<script>` 里，需先解包：

`mangaDetailsResolve`（L163-189）：

```kotlin
document.select("#wrapper > script:containsData(function base64DecodeUtf8):containsData(document.write(html))")
→ 逐行扫描，命中以 const/let/var html 开头的行
→ 截取 base64DecodeUtf8(" ... "); 之间的内容
→ Base64.decode(..., Base64.DEFAULT)
→ document.body().append(String(html))
```

**该方法被 `mangaDetailsParse` 和 `chapterListParse` 共用**（章节数据也在同一段隐藏 HTML 内）。

字段映射（`mangaDetailsParse(document)`，L196-208）：

| 字段 | 选择器 / 规则 |
| --- | --- |
| `title` | `h1` 的文本 |
| `thumbnail_url` | `.thumb-overlay > img` → `extractThumbnailUrl()` → `substringBeforeLast('.') + "_3x4.jpg"` |
| `author` | `div.panel-body div.tag-block` 的**第 4 个**（下标 3）内的 `.btn-primary` 文本，逗号拼接 |
| `genre` | `selectDetailsStatusAndGenre(doc, 0)` → 空串分隔后转逗号 |
| `status` | `selectDetailsStatusAndGenre(doc, 1)` → `toIntOrNull() ?: 0` |
| `description` | `#intro-block .p-t-5.p-b-5` 文本，取 `敘述：` 之后并 trim |

**状态与标签共用一个解析函数**（L229-245），靠 `index` 参数分流：

```
遍历 span[itemprop=genre] a 的文本：
    "連載中" → status = "1"
    "完結"   → status = "2"
    其他     → 追加到 genre 字符串
返回 index==1 ? status : genre
```

**一处容易误判的写法**（L236-238）：

```kotlin
val elements = document.selectFirst("span[itemprop=genre]")?.select("a") ?: return ""
for (value in elements) {
    when (val vote: String = value.select("a").text()) { ... }
}
```

`value` 本身已是 `<a>` 元素，又对其调用 `.select("a")`。这**不是错误**——Jsoup 的 `Element.select(css)` 语义是「以该元素为上下文，**匹配结果可能包含元素自身**」，因此 `value.select("a")` 会返回 `[value]` 自身，`.text()` 得到的就是标签文本。

但它是**冗余**的：L232 的 `document.select("span[itemprop=genre] a")` 与 L236 的链式写法结果相同，同一个集合被计算了两遍，而且写了两种不同风格。L233 的空集合早退判断实际上只对 L236 取得的结果有意义。

### 5.8 章节列表

`chapterListParse`（L255-267）：

```
主选择器：div[id=episode-block] a[href^=/photo/]        L257
  非空 → 逐项 chapterFromElement()，最后 .reversed() 反转（站点是倒序的）
  为空 → 兜底构造单个「单章节」                        L258-265
           name = "单章节"
           url  = #album_photo_cover > div.thumb-overlay > a 的 href
           date = [itemprop=datePublished] 最后一个的 content 属性
```

`chapterFromElement`（L249-253）：

```
url   = a 的 href
name  = "a li h3" 的 ownText()（只取自身文本，不含子节点）
date  = "a li span.hidden-xs" 的文本 → dateFormat.tryParse()
```

日期格式：`SimpleDateFormat("yyyy-MM-dd", Locale.ENGLISH)`（L247）——**已废弃写法**，仓库规范要求改用 `keiyoushi.utils.tryParse*`。

### 5.9 图片列表

`pageListParse`（L270-293）用 `tailrec` 递归翻页：

```
解析器选择器：div[class=center scramble-page spnotice_chk][id*=0]     L272
  对每个元素取 <img>：
      src        = img.attr("src")
      data-cfsrc = img.attr("data-cfsrc")
      若 src 或 data-cfsrc 含 "blank.jpg"（懒加载占位）
          → imageUrl = img.attr("data-original").substringBefore("?")
      否则 → imageUrl = src.substringBefore("?")
翻页：a.prevnext 的 abs:href 存在则递归，否则返回
```

`Page` 的 `index` 取 `pages.size`（累加序号，非站点序号）。因 `pageListParse` 已返回图片 URL，`imageUrlParse` 直接 `throw UnsupportedOperationException()`（L295）。

### 5.10 过滤器

`getFilterList()`（L298-303）顺序固定：

```
CategoryGroup → SortFilter → TimeFilter → TypeFilter
```

| 过滤器 | 显示名 | 条目数 | 输出形态 |
| --- | --- | --- | --- |
| `CategoryGroup` | 按类型 | 68（含 1 处重复，见 §10） | 路径片段 `/albums/...?` 或 `/search/photos?search_query=...&` |
| `SortFilter` | 排序 | 4 | `o=mr&` / `o=mv&` / `o=tf&` / `o=mp&` |
| `TimeFilter` | 时间 | 4 | `t=a&` / `t=t&` / `t=w&` / `t=m&` |
| `TypeFilter` | 搜索范围 | 5 | `main_tag=0..4`（无尾随 `&`） |

`CategoryGroup` 的 68 项分三类：

| 类型 | 数量 | 例 |
| --- | --- | --- |
| 目录型 | 12 | 全部 `/albums?`、同人 `/albums/doujin?`、韩漫 `/albums/hanman?`、单本 `/albums/single?` |
| 搜索型-站内分类 | 2 | P站 `search_query=PIXIV&`、3D `search_query=3D&` |
| 搜索型-标签 | 54 | 劇情、純愛、NTR、扶他、獵奇、血腥暴力 … |

`UriPartFilter` 基类（L125-131）：

```kotlin
open class UriPartFilter(
    displayName: String,
    val vals: Array<Pair<String, String>>,   // <显示名, URI 片段>
    defaultValue: Int = 0,
) : Filter.Select<String>(displayName, vals.map { it.first }.toTypedArray(), defaultValue) {
    open fun toUriPart() = vals[state].second
}
```

**注意**：基类**没有**实现「首项不追加参数」的语义（虽然 L119-123 的文档注释提到了 `firstIsUnspecified`）。所有过滤器**始终**把 `vals[state].second` 拼进 URL。`CategoryGroup` 默认项 `全部 → "/albums?"` 正是靠这点充当了路径前缀。

### 5.11 设置界面装配

`setupPreferenceScreen`（L305-308）：

```kotlin
getPreferenceList(screen.context, preferences, updateUrlInterceptor.isUpdated).forEach(screen::addPreference)
screen.addRandomUAPreference()      // 来自 lib/randomua
```

`isUpdated` 标志被用来自适应 UI 文案：镜像列表刚被自动更新时提示「请选择合适的镜像并重启应用」。
