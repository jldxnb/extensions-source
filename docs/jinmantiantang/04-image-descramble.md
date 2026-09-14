# 禁漫天堂扩展 · 图片还原算法规格

> 本文件是「禁漫天堂扩展技术档案」文档集的一部分。
> 索引：[`docs/README.md`](../README.md)
> 包含全局章节：§7（**全局编号跨文件连续，请勿重排**）

---

## 7. 图片还原算法规格

**触发条件**（`ScrambledImageInterceptor.kt:22-25`）：

```
1. URL 含 "media/photos"（忽略大小写）
2. aid = url.pathSegments[size - 2].toInt()     ← 倒数第二段是章节 ID
3. aid >= 220980
```

三者同时满足才处理，否则原样放行。

**常量**（L51）：

```kotlin
private const val SCRAMBLE_ID = 220980   // 2020-10-27 起站点启用图片分割
```

**切块数计算**（L53-66）：

```kotlin
private fun md5LastCharCode(input: String): Int {
    val lastByte = MessageDigest.getInstance("MD5").digest(input.toByteArray()).last().toInt() and 0xFF
    return lastByte.toString(16).last().code          // 十六进制串最后一个字符的 ASCII 码
}

private fun getRows(aid: Int, imgIndex: String): Int {
    val modulus = when {
        aid >= 421926 -> 8        // 混淆规则第二轮
        aid >= 268850 -> 10
        else -> return 10         // 220980..268849 直接返回 10
    }
    return 2 * (md5LastCharCode(aid.toString() + imgIndex) % modulus) + 2
}
```

| aid 区间 | modulus | rows 取值域 |
| --- | --- | --- |
| 220980 – 268849 | 10（短路返回） | 恒为 10 |
| 268850 – 421925 | 10 | {2,4,…,20} |
| ≥ 421926 | 8 | {2,4,…,16} |

`imgIndex` = URL 最后一段去掉扩展名（L28：`pathSegments.last().substringBefore('.')`）。

**重排算法**（`decodeImage`，L69-108）：

```
输入：已解 gzip 的字节流 + rows
1. BitmapFactory.decodeStream → 原图 bitmap
2. remainder = height % rows
3. for x in 0 until rows:
       copyH = floor(height / rows)
       py    = copyH * x
       y     = height - copyH*(x+1) - remainder
       x == 0 ? copyH += remainder : py += remainder
       crop  = Rect(0, y, width, y + copyH)          ← 源区域（自下而上取）
       splic = Rect(0, py, width, py + copyH)        ← 目标区域（自上而下放）
       canvas.drawBitmap(input, crop, splic, null)
4. JPEG 质量 90 压缩回 Buffer
5. recycle() 两个 bitmap
```

**gzip 处理**（L29-39）：若响应头 `Content-Encoding == gzip`，用 `GZIPInputStream` 包装，并从响应头中**移除 `Content-Encoding` 与 `Content-Length`**（body 已被重建，长度不再匹配）。

**注释溯源**（L48-50）：算法对应站点 HTML 页面约 1800 行处的 `function scramble_image(img)`。

**外部依赖风险**：该算法跟随站点服务端规则。站点历史上已变更过一次（新增 421926 档位）。若站点再改，看图功能会静默失效（图片错位而非报错）。
