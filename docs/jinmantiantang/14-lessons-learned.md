# 禁漫天堂扩展 · 难点与经验总结

> 本文件是「禁漫天堂扩展技术档案」文档集的一部分，对应全局章节 **§19**（层 4 · 经验沉淀）。
> 记录范围：2026-09-12 的代码审查 → CI 流水线补齐 → 实跑验证 → 客户端接入排查。
> 内部条目标识为 `D1…D13`，交叉引用请写作 `§19-D5` 形式——不另占用 §x.y 编号，避免与既有体系冲突。
> 索引：[`docs/README.md`](../README.md)

---

## 一、项目背景与硬约束

**目标**：维护 `keiyoushi/extensions-source` 的 fork，只对自己加的「禁漫天堂账号登录」负责；
上游更新 → 同步 → 自动构建签名 APK → 发布到 `repo` 分支 → Mihon 通过 `index.min.json` 自动更新。

这些约束决定了后面所有处理方式：

| 约束 | 影响 |
| --- | --- |
| 本地**没有 Android 构建环境**（无 SDK） | 唯一编译器是 GitHub Actions。任何 Kotlin 改动的"能不能编过"只能由 CI 回答 |
| 仓库 205 MB、本机网络约 90 KB/s | 全量克隆不可行；本地是 `--filter=blob:none` + 稀疏检出，非标准状态 |
| fork 上无仓库管理权限 | 读不到 Actions 日志（403），只能靠检查注解 / job summary / 公开 API |
| 本机没有 `gh` CLI | 触发靠 push，观察靠 `api.github.com` 公开接口 |
| 流水线是**无人值守**的 | 出错要"红着停住"，不能静默降级 |

---

## 二、难点总表

| 编号 | 难点 | 处理方式 | 一句话教训 |
| --- | --- | --- | --- |
| D1 | 没有本地编译器 | 把"编不过"变成 CI 关卡 + 本地只做静态校验 | 用 CI 当编译器时，必须先加"防呆关卡" |
| D2 | 工作区与 HEAD 大面积不一致 | blob 哈希比对定性，`git reset` + 精确路径还原 | 破坏性命令要精确到路径，别用 `.` |
| D3 | 绿灯不等于做对了 | 逐 step 核对 + 产物独立验证 | 绿灯只是"没报错"，不是"做对了" |
| D4 | versionCode 是合成值（104059≠59） | 实测反推公式 + 自动推进 + 三道关卡 | 反直觉的元数据要实测确认，别按直觉 |
| D5 | APK 签名一致性无法用现成工具验 | 自己解析 APK Signing Block，再用 keytool 交叉验证 | 工具不适用时，就自己按规范解析 |
| D6 | 证据夹具本身是"脏"的 | 比对证书指纹定性夹具来源 | 夹具要标注来源，否则会误导判断 |
| D7 | 分清"我们的代码"和"上游代码" | API 列目录 + 逐行 diff 定量 | 动手前先划边界 |
| D8 | 登录功能并发缺陷 | 加锁 + 双重检查 + 原子化 | 拦截器是并发入口，必须假设多线程 |
| D9 | 构建与发布在两个地方 | 收敛成单一入口 | 同一件事两处实现，迟早互相打架 |
| D10 | protobuf 依赖会随机炸 | 钉死与 gencode 一致的版本 | 提交生成的产物，就要锁对应的运行时 |
| D11 | 发布脚本自身的细节坑 | 严格筛选产物 + 对齐上游编码 | 脚本要"宁可报错，不要猜" |
| D12 | 客户端不认索引 | 读 Mihon 源码定位分流逻辑与必填字段 | 报错文案里的类名就是最好线索 |
| D13 | 本地 ref 写不进去 | 改用 `ls-remote` | 别信本地缓存，必要时问远端 |
| D14 | "内容没变却发布"空发空涨号 | 版本无关的规范化哈希 + fail-open | 判定"要不要发布"要盯**产物内容**，而不是"跑过构建没" |

---

## 三、逐个展开

### D1 没有本地编译器：一切靠 CI

**难点**：本机没有 Android SDK，`./gradlew` 跑不起来；而改的是 Kotlin 代码。

**处理**：
1. 在构建前加一道**登录功能锚点关卡**（`.github/scripts/verify-login.py`），把"上游改版把我们的插桩挤掉"这种**编译能过但功能已丢**的情况拦住。
   关键设计：每个锚点要求**恰好 1 处**，而不是"至少 1 处"——0 处=被挤掉，2 处=被重复插入，两种都要抓。
2. 本地能做的一律做掉：`py_compile` 语法检查、花括号/圆括号平衡统计、YAML 结构解析（`yaml.safe_load` 后打印 job/step 列表核对）。
3. 编译失败时的可观测性沿用项目原有机制：`::error::` 检查注解 + job summary（无仓库权限也能读）。

**教训**：把 CI 当编译器时，"能不能编过"反而成了最弱的一环；必须额外补上"编过但功能没了""编过但用户收不到"这类关卡。

### D2 工作区与 HEAD 大面积不一致

**现象**：53 个扩展文件显示为已修改，`docs/` 14 个文件是**已暂存删除**，还有一个 `.pyc` 被暂存。

**难点**：不能想当然认为"这些是用户的未提交改动"，也不能盲目 `git checkout -- .`（那会连同我自己的改动一起还原）。

**处理**：
1. 用 **blob 哈希**定性，而不是看内容猜：

   ```bash
   git hash-object src/en/infinityscans/build.gradle.kts      # 工作区 c0c5b8d1c3
   git log --format=%H -6 -- src/en/infinityscans/build.gradle.kts   # 找出各历史版本
   ```

   结果：工作区那版恰好等于 `1ad4b8728`（2026-09-04）的 blob → 是**脏检出**，不是有意改动。
   对 `CONTRIBUTING.md` 复核，同样是 09-04 的版本。`lib/seedrandom/` 也是残留（上游已在
   `2629669be core: move seedrandom to utils` 移走）。
2. `git reset` 只解除暂存（不动工作区文件），消掉"一提交就删掉 docs/"的地雷。
3. 还原命令精确到路径，而不是 `.`：

   ```bash
   git checkout -- CONTRIBUTING.md lib-multisrc src    # 只还原那 53 个
   ```

**教训**：破坏性 git 命令一律精确到路径；判"脏检出 vs 有意改动"要用哈希与历史对齐，别凭感觉。

### D3 绿灯不等于做对了

**难点**：CI 显示 success，但完全可能是"该跑的都没跑"（步骤被 `if` 跳过、job 被跳过）。

**处理**：不看结论看**步骤明细**，并明确"哪个步骤 skipped 才算正常"：

```bash
curl -s "https://api.github.com/repos/<owner>/<repo>/actions/runs/<id>/jobs"
```

实测正常形态：`Build` 与 `Publish` 两个 job 全部 success，`Report build failure` /
`Report publish failure` 为 **skipped**（说明没走失败分支）。

**教训**：把"skipped 的期望值"也写进验收标准，否则"跳过"会被当成"通过"。

### D4 versionCode 是合成值

**难点**：`build.gradle.kts` 里写着 `versionCode = 59`，但线上索引与 APK 里实际是 **104059**。
按直觉判断"我已经 +1 了"会直接导致用户永远收不到更新（Mihon 只比较 versionCode，不比较内容）。

**处理**：
1. 用构建产物实测反推：`out/jinmantiantang/keiyoushi-source-info.json` 给出
   `libVersion="1.4" + versionCode=59 → versionCode=104059`，即
   `effective = major*100000 + minor*1000 + versionCode`。
2. 写了 `ensure-version-bump.py`，两种模式：
   - **构建前**：读线上索引，若本次有效值不大于已发布值，就地把模块 versionCode 提到
     "已发布值 + 1"（只改 CI 工作区、**不提交**，因此也不会再和上游产生 versionCode 冲突）；
   - **构建后**：用产物里的**真实** versionCode 做硬闸门，不大于就拒绝发布。
3. 线上验证：模块文件始终是 59，但索引从 104060 走到 **104061** —— 说明自动推进真的生效了。

**教训**：版本号的"有效值"可能由构建插件合成；判定"用户能否收到更新"必须用**最终生效值**。

### D5 APK 签名一致性验证（技术含量最高的一环）

**为什么必须验**：索引里的 `signingKey` 一旦与 APK 实际签名不一致，Mihon 会拒绝更新或要求卸载重装。

**难点**：
1. `keytool -printcert -jarfile x.apk` 直接报 **"不是已签名的 jar 文件"**——因为现代 APK 只做
   v2/v3 签名，没有 v1（JAR）签名，keytool 读不到。
2. 本机没有 `apksigner`。
3. 需要自己从 **APK Signing Block** 里取出证书 DER。

**处理**：按规范手写解析 → 再让 `keytool` 做独立交叉验证。

```python
# 直接按签名对 ID 定位（v2 = 0x7109871a），比解析块头稳
pos = data.find(struct.pack('<I', 0x7109871a))
width = struct.unpack_from('<Q', data, pos - 8)[0]      # 该对的长度
v = data[pos + 4 : pos + 4 + width - 4]
# signers -> signer -> signed_data -> (digests 跳过) -> certificates -> 第一个证书
# 最后按 DER 自身声明的长度裁剪
if raw[0] == 0x30 and raw[1] == 0x82:
    raw = raw[:4 + struct.unpack_from('>H', raw, 2)[0]]
```

然后用 JDK 自带的 keytool 读这份 DER：

```bash
keytool -printcert -file new.der | grep SHA256
```

**结果**：`9E:AE:77:A0:…:49:12` 与索引 `signingKey` 完全一致 → Mihon 会正常更新。

**过程中踩的坑（都值得记）**：
- 套错层级没裁剪 DER，导致前后两次"算出不同指纹"，差点误判成"两个包用了不同密钥"；
- APK Signing Block 的两个 size 字段我按规范读出来是 `8 / 4088`，不相等，没有深究，
  改为**按签名对 ID 定位**这种更稳的方式；
- 定位 Signing Block 必须用 EOCD 里的**中央目录偏移**，不能用 `rfind('PK\x05\x06')` 的位置。

**教训**：解析类验证必须用"已知答案"的样本自校验（见 D6）；解析结果再用独立工具复核一遍。

### D6 证据夹具本身是脏的

**难点**：我用 `out/jinmantiantang/…v1.4.59.apk` 作为"已发布版本"对照，结果它的证书指纹和索引
完全不一致，一度怀疑流水线签名错了。

**处理**：比对两包的证书指纹与来源，确认 `out/` 里那份是**配置签名 secret 之前**的测试产物
（证书 `BE:AF:F8:98:…`），不是线上版本；线上那份（`9E:AE:77:A0:…`）与索引一致。

**教训**：测试夹具必须标注"它是哪一次、用哪把密钥产生的"；否则它会以最坏的方式误导你。

### D7 分清"我们的代码"与"上游代码"

**难点**：用户只授权改自己加的部分，但目录里 5 个文件混着上游代码。

**处理**：两步定量，而不是靠记忆：

```bash
# 1) 上游有没有这个文件（没有的就是我们独有的）
curl -s "https://api.github.com/repos/keiyoushi/extensions-source/contents/<目录>"
# 2) 有交集的文件逐行 diff
diff -u up_main.kt Jinmantiantang.kt | grep -c '^[<>]'    # → 9
```

结果：上游只有 `Filters.kt / Jinmantiantang.kt / Preferences.kt / ScrambledImageInterceptor.kt`，
**没有 `Auth.kt`**；主类与上游的差异**恰好是那 9 行插桩**，别无其它。

**额外收获**：这 9 行的差异同时说明"当前与上游这个文件完全同步"，下次夜间同步不会撞冲突。

**教训**：动手前先划边界；边界用 API + diff 定量，不要靠"我记得"。

### D8 登录功能的并发缺陷

**难点**：登录拦截器挂在每个请求上，而 Mihon 阅读/更新书架会并发发请求。

**发现的真 bug**：
1. **并发重复登录**：N 个并发请求各判断一次"需要登录"，于是各发一次登录 POST；
   会话失效自愈时更糟——每个线程都会先清掉"已登录"标记，然后各登一次。
2. **异常类型不契约**：站点被 CF 挑战或维护时返回 HTML，`parseAs` 抛的是
   `SerializationException` / `MissingFieldException`，而 KDoc 承诺"失败抛 IOException"，
   用户会看到解析器的内部报错文案。

**处理**（只改 `Auth.kt`，上游文件一行未动）：
- 拆出 `performLogin()`（真正发请求），`login()` 与 `reLogin()` 都加 `loginLock` 并做**双重检查**；
- 自愈路径的"清标记 + 重登"放进同一把锁里**原子完成**，消除互相清标记；
- 解析失败用 `runCatching { }.getOrElse { throw IOException(可读文案, cause) }` 归一到 IOException。

**验证**：本地跑关卡（13 锚点全绿）+ 边界检查（括号平衡）+ CI 实跑（commit `29d550f0` 构建发布成功，
线上索引走到 104061）。

**教训**：拦截器天然并发，任何"读-判断-写"的序列都要当成临界区；对外承诺的异常类型要真的兑现。

### D9 构建与发布在两处实现

**难点**：`build-jinmantiantang.yml` 只构建（产物 14 天过期），发布逻辑在 `sync-upstream.yml` 且
前置条件绑死 `merged == 'true'` → **改了代码 push 之后 Mihon 收不到更新**，与使用者的预期不符。

**处理**：把 publish job 收敛到 `build-jinmantiantang.yml`（构建即发布），
`sync-upstream.yml` 只负责"合并上游 → 触发构建"。

如果两边都实现发布，夜间会发布两次、两个 job 抢着推 `repo` 分支——**单一入口是硬要求**。
另加两个闸门：签名 secret 缺失时**拒绝发布**（debug 签名的包会让老用户装不上）、
手动触发可勾 `skip_publish` 只出产物。

**教训**：同一件事只能有一个实现；"能跑"和"用户能收到"是两件事。

### D10 依赖版本漂移

**难点**：`index_pb2.py` 是提交进仓库的 protoc 生成物，文件头写着
`Protobuf Python Version: 7.35.1`，导入时会执行 `ValidateProtobufRuntimeVersion`。
原来用 `pip install -U protobuf`，一旦 PyPI 出新版本，**某个夜里发布会突然挂掉**。

**处理**：钉死 `pip install 'protobuf==7.35.1'`，并在注释里写明"升级要同时重新生成 gencode 并改这里"。

**教训**：提交生成产物，就必须锁对应运行时版本；无人值守流水线不能吃"最新版"。

### D11 发布脚本自身的细节坑

| 坑 | 后果 | 处理 |
| --- | --- | --- |
| 取 APK 用 `sorted(glob('**/*.apk'))[0]` | 出现 `-unsigned.apk` 时静默取错 | 排除 `unsigned`；多候选直接报错，不猜 |
| 按**文件名**筛 `release`（实际 release 在**目录名**上） | 正确的包被判定为"找不到" | 改按相对路径判断，并保留回退（这个 bug 是我自己写完本地跑才发现的） |
| `index.pb` 写裸 protobuf | 上游是 gzip；将来切 `.pb` 地址会解析失败 | `gzip.compress(..., mtime=0)` 对齐上游 |
| 索引缺 `badgeLabel` | Mihon 模型里它是**必填非空**，缺了直接解码失败 | 补 `badgeLabel="JLD"` |

**教训**：脚本要"宁可报错，不要猜"；写入前先和上游参考实现对齐编码（gzip、字段名、必填项）。

### D12 客户端不认索引

**现象**：Mihon 报 `Error while decoding mihon.data.extension.model.NetworkExtensionStore`。

**定位过程**（关键是顺着报错里的类名找源码）：
1. 取 `data/src/main/java/mihon/data/extension/service/ExtensionStoreService.kt`，
   发现它**按首字节分流**：`{` 走 JSON、`[` 走旧版数组、**其它走 protobuf**；
2. 用户用的 `github.com/.../blob/...` 返回 HTML，首字节 `<` → 落进 protobuf 分支 → 报错点名
   `NetworkExtensionStore`；
3. 再取 `NetworkExtensionStore.kt` 发现 `badgeLabel: String` **非空且无默认值 = 必填**，
   而我们的索引此前正好缺它 → 两种原因都会产生同一条报错。

**证据**：
```
blob 地址 → HTTP 200  Content-Type: text/html
raw  地址 → HTTP 200  Content-Type: text/plain
```

**结论与处理**：地址必须用 raw（三种等价写法见 `说明文档.md` §3.4）；
`badgeLabel` 已补上；并按 Mihon 模型逐项校验线上索引的必填字段（全部满足）。
顺带确认两个易误判点：Mihon 的 `Json` 设了 `ignoreUnknownKeys = true`（我们多出的 `jarUrl` 无害）、
kotlinx 词法器 `consumeNumericLiteral()` 显式支持带引号数字（`"versionCode": "104061"` 能被解析）。

**教训**：报错里的**类型名**是最强线索，直接去读客户端的模型与解析代码，比猜格式快得多。

### D13 本地 ref 写不进去

**现象**：`git fetch` 报告 `60cfe97fc..29d550f08 main -> origin/main` 成功，但读回仍是旧值；
`git update-ref` 返回 0 也无效；`git status` 因此误报 `[ahead 2]`（该 ref 只存在于 `packed-refs`，
且新的松散 ref 似乎写不进去）。

**处理**：不依赖本地引用，直接问远端：

```bash
git ls-remote origin main     # → 29d550f0…（与实际一致）
```

并与 `api.github.com/repos/<owner>/<repo>/commits/main` 交叉确认。

**教训**：本地缓存/引用不可信时，用远端事实作为判据；同时**不要**执行
`git reset --hard origin/main` 这类依赖本地引用的破坏性命令。

### D14 「内容没变却发布」：空发、空涨号

**难点**：原设计是「每次构建都发布」，于是夜间只要上游任何文件变化就会发布一版、versionCode +1。
而 Mihon 只比较 versionCode，用户会收到一次「什么都没改」的更新提示，版本号也被白白消耗。
实测上游近 30 天：336 次提交里只有 **6 次**动了禁漫本体，但 `core/**` 被改了 14 次、
`gradle/**` 10 次——都会触发发布。

**为什么不能直接比 APK / JAR 的整体哈希**：两者都内嵌 `AndroidManifest.xml`，而它含
versionCode / versionName；构建前关卡会先把 versionCode 提到「已发布值 + 1」，
所以整体哈希必然不同，比较没有意义。

**处理**：`check-content-changed.py` 对 JAR 做**版本无关**的规范化哈希——按条目名排序，
逐个喂入（条目名 + 内容），跳过 `AndroidManifest.xml` 与 `META-INF/**`
（签名材料里含所有条目的摘要，会随 manifest 一起变）。实测该 JAR 的 51 个条目里
**只有 AndroidManifest.xml 含版本号**，跳过它们后剩 47 个：混淆后的 class、`res/*.png`、
`resources.arsc`。脚本 **fail-open**：任何异常都按「内容已变」处理，绝不卡住发布。

**线上验证**（run 34704362394，只改 CI、不改扩展代码）：`Check content changed` = success、
`Notice skipped publish` 执行，而 `Install protobuf runtime` / `Verify versionCode` /
`Generate index` / `Deploy to repo branch` **全部 skipped**；线上索引保持 `104061` 不变、
`repo` 分支没有新提交。这同时证明了该构建在源码不变时是**可复现**的
（新旧 JAR 的规范化哈希相等）——判据成立的前提。

**附带修正**：
- versionCode 守卫从 `999` 放宽到 `9999`。插件的编码是 `基准 × 1000 + 模块值`（无掩码），
  模块值超过 999 只是让有效值进入下一个千位段，仍然唯一且严格递增；这也把「剩余发布额度」
  从 938 次提到 9389 次。
- 发布前的硬闸门在读不到索引时改为**失败**（fail-closed），避免静默把索引版本号回退；
  构建前模式仍是 fail-open（本地索引文件读取失败也归入该语义）。

**教训**：判定「要不要发布」要盯**产物内容**（可哈希的东西），而不是「有没有跑过构建」。
只要产物里混进了每次都变的元数据（版本号、时间戳），就必须先把这类字段规范化掉，
否则判据形同虚设。

---

## 四、可复用的方法论

1. **不信绿灯，找独立证据。** 运行成功只说明没报错；要另外验证"产物真的是新的、签名对得上、
   版本号真的变大了"。本次用了四类独立证据：HTTP 状态与 Content-Type、字节级比对（gzip 魔数）、
   二进制 manifest 解析、签名证书 SHA-256。
2. **用已知答案自校验解析器。** 解析新版 APK 的 versionCode 前，先用已知为 104059 的旧包验证
   解析方法本身；解析签名证书时用 `keytool -printcert -file` 复核。
3. **本地能跑的先跑。** 新写的脚本一律先在本地用真实产物跑一遍（正例 + 反例 + 边界），
   这次正是靠这个抓出了"release 在目录名上"和 AXML header 字段顺序两个 bug。
4. **关卡要能区分"缺"和"多"。** 锚点校验用"恰好 N 处"，否则重复插入会被漏掉。
5. **失败要响，不要降级。** 签名缺失拒绝发布、版本号未递增拒绝发布、锚点缺失拒绝构建——
   宁可红着停住，也不要发一个"用户装不上"或"没有登录功能"的包。
6. **边界先行。** 动手前先用 API + diff 明确"哪段是我的"，避免污染上游代码、降低冲突面。
7. **先定性再定量。** 判断"工作区为何与 HEAD 不一致"用 blob 哈希对齐历史，
   而不是看内容猜意图——猜测很容易得出相反结论。

---

## 五、遗留问题（有意未处理）

| 项 | 原因 |
| --- | --- |
| 上游 4 个文件的缺陷（JMT-13/14/19~24 等） | 使用者明确要求"其他最好不动"，避免与上游冲突面变大 |
| `Auth.kt` 里登录状态行直接操作偏好键（封装泄漏） | 属于设计味道而非缺陷，改动要动 `addAuthorizationPreferences` 的签名与调用点，收益低风险高 |
| 夜间同步即使禁漫没变也会发布一版 | 属原有行为，未擅自改变；要收敛只需在 `sync-upstream.yml` 给 build job 加"本次合并是否动了 `src/zh/jinmantiantang/**`"的条件 |
| 本地 clone 的 53 个旧文件 / ref 写不进 | 只影响本地，不影响 CI（CI 每次全新 clone）；修复命令见 `说明文档.md` |
| 单元测试 | 本地无 Gradle，但 CI 有。建议把 `getRows`、搜索参数拼装、状态映射抽成纯函数配 `kotlin.test`，把"唯一验证手段是实机"变成"提交即跑单测" |

---

## 六、关键命令速查

```bash
# 看某次运行到底跑了哪些步骤（不看结论看明细）
curl -s "https://api.github.com/repos/<owner>/<repo>/actions/runs/<id>/jobs"

# 只读索引是否新鲜、字段是否齐全
curl -s -L https://raw.githubusercontent.com/<owner>/<repo>/repo/index.min.json

# 确认地址返回的是 JSON 而不是网页
curl -sI https://raw.githubusercontent.com/<owner>/<repo>/repo/index.min.json | grep -i content-type

# 不信本地引用
git ls-remote origin main

# 只还原"脏检出"的文件，别用 .
git checkout -- CONTRIBUTING.md lib-multisrc src

# 本地跑 CI 关卡（改完 Kotlin/脚本后先自检）
python3 .github/scripts/verify-login.py
python3 .github/scripts/ensure-version-bump.py --dry-run
python3 .github/scripts/ensure-version-bump.py --check-artifact <产物目录>
```
