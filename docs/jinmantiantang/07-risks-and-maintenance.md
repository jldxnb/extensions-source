# 禁漫天堂扩展 · 缺陷、变更与溯源

> 本文件是「禁漫天堂扩展技术档案」文档集的一部分。
> 索引：[`docs/README.md`](../README.md)
> 包含全局章节：§9、§10、§11（**全局编号跨文件连续，请勿重排**）

---

## 9. 变更操作手册

改动本扩展时，以下位置必须联动：

| 变更 | 必须同步的位置 |
| --- | --- |
| 新增/更换主线域名 | ① `build.gradle.kts` 的 `deeplink { host(...) }` ② `Preferences.kt:85` 的 `SITE_ENTRIES_ARRAY` ③ `Preferences.kt:77` 的 `SITE_ENTRIES_ARRAY_DESCRIPTION`（保持顺序对应） |
| 更换 `source { name }` | 源 ID 会变 → 用户设置全部重置。须同时加 `id = 6286738698187452081` 钉住旧 ID |
| 修改代码 | `versionCode` 递增（当前 `59` → 下次 `60`） |
| 改动登录相关（`Auth.kt`） | ① 若改了偏好键名，须同步 `Auth.kt` 的常量与 §8.7 ② 若站点改了登录接口或错误路径，须重抓 HAR 并更新 §14.2 / §14.6.4 ③ 若新增设置项，`05-settings.md` §8 的行数需更新 |
| 更换会话凭证机制（若站点从 Cookie 改为 token） | §14.3、§14.5.3 的核心结论失效，须重新调研并重写 §14 |
| 迁移到 libVersion 1.6 | 基类改 `KeiSource`；`client` 改为 `configureClient()`；`override val client` 不可再覆盖；`headersBuilder` 变为 final（改用 `configureHeaders()`）；需要重写 `fetchMangaUpdate` / `getSearchMangaList` / `getPageList`；`baseUrl` 的手写 override 需改走 DSL（因为静态 + 手写 override 只警告，而 mirrors 型会直接报错） |
| 新增过滤器 | `Filters.kt` 定义类 → `getFilterList()` 注册 → 若为 `UriPartFilter` 子类则 `searchMangaRequest` 自动收集 |

## 10. 已知缺陷与风险登记

| 编号 | 等级 | 位置 | 问题 | 影响 |
| --- | --- | --- | --- | --- |
| JMT-01 | 低 | `Jinmantiantang.kt:200` | `img?.extractThumbnailUrl()?.substringBeforeLast('.') + "_3x4.jpg"` —— 当 `img` 为 null 时，Kotlin 的 `String?.plus` 会拼出字面量 `"null_3x4.jpg"`；当属性全缺时得到 `"_3x4.jpg"` | 详情页缩略图错误（仅在选择器未命中时触发） |
| JMT-02 | 低 | `Filters.kt:16,18` | 「汉化」条目重复两次，均指向 `/albums/doujin/sub/chinese?` | 下拉里出现重复项 |
| JMT-03 | 中 | `ScrambledImageInterceptor.kt:71-74` | `BitmapFactory.decodeStream` 返回 null 时未判空，下一行 `input.height` 触发 NPE | 单张异常图导致整章加载失败 |
| JMT-04 | 中 | `Jinmantiantang.kt:84-97` | 列表项靠 `children[0..3]` 下标定位字段 | 站点改版后静默产出错位数据，不报错 |
| JMT-05 | 中 | `Jinmantiantang.kt:220-226` | 作者取 `tag-block` 的第 4 个（硬编码下标 3） | 站点调整版块顺序即失效 |
| JMT-06 | 低 | `Jinmantiantang.kt:247` | 使用 `SimpleDateFormat`，仓库规范已废弃 | 技术债；不影响功能 |
| JMT-07 | 低 | `Jinmantiantang.kt:42` | `baseUrl` 为一次性求值的 `val` | 切换镜像必须重启应用（已在 UI 文案说明） |
| JMT-08 | 低 | `Jinmantiantang.kt:152` | `-` 排除语法与关键词搜索互斥 | 源码注释自述的功能限制 |
| JMT-09 | 低 | `Preferences.kt:120-138` | 任何主站请求失败（含单次抖动）都会触发远端拉取 + 抛出用户可见异常 | 网络不稳时误报 |
| JMT-10 | 中 | `ScrambledImageInterceptor.kt:69-108` | 整图 decode 为 ARGB_8888 再重编码为 JPEG 90 | 大图内存峰值高、有二次压缩损失 |
| JMT-11 | 低 | `Jinmantiantang.kt:232,236` | 同一组 `span[itemprop=genre]` 下的 `<a>` 被用两种写法计算两遍；`value.select("a")` 依赖「select 包含自身」这一 Jsoup 语义才能正确工作 | 功能正常，属可读性与冗余问题；若有人误按「嵌套选择器返回空」的直觉重构会引入真 bug |
| JMT-12 | 高（外部） | `ScrambledImageInterceptor.kt` 整体 | 算法依赖站点服务端规则，历史已变更一次 | 站点再改则看图功能静默失效 |

## 11. 溯源与验证方法

### 11.1 快速定位

```bash
# 站点识别
grep -rin "18comic\|禁漫\|jinman" --include="*.kt" --include="*.kts" .

# 定位图片还原算法的站点侧实现（注释给出的线索）
# 站点页面 HTML 约 1800 行处：function scramble_image(img)
```

### 11.2 关键行号索引

| 对象 | 文件 | 行 |
| --- | --- | --- |
| 类声明 | `Jinmantiantang.kt` | 34 |
| preferences / baseUrl | `Jinmantiantang.kt` | 40 / 42 |
| authManager 构造 | `Jinmantiantang.kt` | 46-52 |
| client 装配（含 auth 拦截器） | `Jinmantiantang.kt` | 54-64 |
| 人气 / 最新 | `Jinmantiantang.kt` | 72 / 108 |
| 列表解析 | `Jinmantiantang.kt` | 74-105 |
| 屏蔽词过滤 | `Jinmantiantang.kt` | 83-90 |
| 编号直达 | `Jinmantiantang.kt` | 121-138 |
| 搜索拼装 | `Jinmantiantang.kt` | 141-166 |
| base64 解包 | `Jinmantiantang.kt` | 171-197 |
| 详情字段映射 | `Jinmantiantang.kt` | 204-216 |
| 状态/标签分流 | `Jinmantiantang.kt` | 237-253 |
| 章节解析 | `Jinmantiantang.kt` | 257-275 |
| 图片解析 | `Jinmantiantang.kt` | 278-301 |
| 设置界面装配 | `Jinmantiantang.kt` | 313-317 |
| 偏好键 / DTO | `Auth.kt` | 19-38 |
| `AuthManager` | `Auth.kt` | 53-155 |
| 登录请求实现 | `Auth.kt` | 88-131 |
| 请求拦截与自愈 | `Auth.kt` | 136-163 |
| 账号设置项 | `Auth.kt` | 168-198 |
| 设置项定义 | `Preferences.kt` | 12-57 |
| 镜像解析 | `Preferences.kt` | 59-65, 85-97 |
| 设置迁移 | `Preferences.kt` | 99-114 |
| 镜像自愈拦截器 | `Preferences.kt` | 116-161 |
| 分类过滤器 | `Filters.kt` | 5-83 |
| 过滤器基类 | `Filters.kt` | 125-131 |
| 还原拦截器 | `ScrambledImageInterceptor.kt` | 17-111 |
| MD5 行数计算 | `ScrambledImageInterceptor.kt` | 53-66 |
| 重排算法 | `ScrambledImageInterceptor.kt` | 69-108 |

> **行号会随改动漂移。** 本文档记录的是 2026-09-12 登录功能实现后的快照。查找时优先用函数名检索，行号仅作参考。

### 11.3 验证清单（改代码后必做）

- [ ] 人气榜、最新更新各翻 3 页，确认无错位数据
- [ ] 搜索：纯关键词 / 含 `+`（AND）/ 含 `-`（排除）三种各测一次
- [ ] 编号直达：`JM123456`、`123456`、粘贴完整 URL 三种形态
- [ ] 详情页：标题、作者、标签、状态、简介五项字段正确
- [ ] 章节：多话作品 + 单本作品（验证「单章节」兜底）
- [ ] 图片：打开 aid ≥ 220980 的作品，确认图片无错位；再测一张 aid ≥ 421926 的
- [ ] 屏蔽词：填入 `YAOI`，确认列表页相关作品消失
- [ ] 镜像切换：改镜像 → 重启 → 确认生效
- [ ] 设置迁移：清数据后首次启动，确认不会崩
