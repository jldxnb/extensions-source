# 个人 fork 分支维护规范

> 状态：2026-09-14 起生效。
> 本文是分支、上游同步、发布归属问题的**唯一权威说明**。
> `docs/jinmantiantang/10-cicd-on-fork.md`、`12-development-log.md`、`14-lessons-learned.md`
> 记录的是迁移前历史，如与本文冲突，以本文为准。

---

## 1. 核心模型

本项目长期采用三段式职责：

```text
keiyoushi/extensions-source:main
              │
              ▼
origin:main                  官方基线，不含个人提交
              │
              │ rebase
              ▼
origin:personal              官方基线 + 本项目全部个人修改
              │
              │ build / sign
              ▼
origin:repo                  APK / JAR / index，供 Mihon 订阅
```

一句话规则：

> `main` 只跟随官方；`personal` 只承载个人修改；`repo` 只承载发布产物。

---

## 2. 分支职责

| 分支 | 允许内容 | 禁止内容 | 角色 |
| --- | --- | --- | --- |
| `main` | 与 `upstream/main` 完全一致的官方代码 | 个人功能、品牌、CI、文档改动 | 官方镜像 |
| `personal` | 禁漫登录、个人 CI、维护文档、发布配置 | 直接把官方 merge 到个人历史、长期堆积冲突提交 | 完整个人源码 |
| `repo` | 构建产物、索引、图标 | 源码、密钥、抓包资料 | 分发通道 |

`personal` 不是“另一份官方仓库”。它是建立在当前 `main` 上的一组个人提交，等价于：

```text
personal = main + personal commits
```

查看真正需要维护的内容：

```bash
git log --oneline main..personal
git diff main...personal
```

---

## 3. 远端约定

```text
origin   = https://github.com/jldxnb/extensions-source.git
upstream = https://github.com/keiyoushi/extensions-source.git
```

首次配置：

```bash
git remote add upstream https://github.com/keiyoushi/extensions-source.git
git fetch upstream main --no-tags
```

---

## 4. 日常开发

开发统一在 `personal` 上完成：

```bash
git switch personal
git pull --ff-only origin personal
# 修改、测试
git add <paths>
git commit -m "feat(...): ..."
git push origin personal
```

个人修改按主题提交，不把以下内容混成一个提交：

- 登录功能；
- 发布/同步基础设施；
- 技术文档；
- 版本号或品牌配置。

push 到 `personal` 后，`Build jinmantiantang` 自动构建、校验并发布到 `repo`。

---

## 5. 官方更新

标准流程固定为：

```text
fetch upstream
  -> fast-forward main
  -> rebase personal onto main
  -> 冲突则停止
  -> 构建 / 测试
  -> 发布
```

本地手工执行：

```bash
git fetch upstream main --no-tags

git switch main
git merge --ff-only upstream/main
git push origin main

git switch personal
git rebase main
# 有冲突：解决后 git rebase --continue；无法处理则 git rebase --abort
git push --force-with-lease origin personal
```

禁止：

- 把官方直接 merge 进 `personal` 来制造新的 merge commit；
- 在 patch/rebase 失败后继续构建；
- 自动猜测冲突结果；
- 为了掩盖 patch 不兼容而修改 `main`。

---

## 6. 自动化流程

### 6.1 `.github/workflows/sync-upstream.yml`

每天北京时间 02:30：

1. checkout `personal`；
2. fetch `upstream/main`；
3. 将 `main` fast-forward 到官方；
4. 在 runner 内执行 `git rebase main`；
5. 若冲突，中止 rebase，保持 `personal` 和 `repo` 原样；
6. 若成功，用 `--force-with-lease` 推送 `personal`；
7. 若有变更，调用单模块构建 workflow，并把官方 commit SHA 传给发布记录。

### 6.2 `.github/workflows/build-jinmantiantang.yml`

唯一构建发布入口：

1. 固定 checkout `personal`；
2. 校验登录挂载点；
3. 将有效 `versionCode` 推进到线上值 + 1；
4. 构建、签名 APK/JAR；
5. 内容未变则跳过发布；
6. 校验产物版本号；
7. 生成索引并发布到 `repo`。

发布提交会记录：

```text
Publish v<version> (versionCode <code>) from <personal-sha> upstream=<upstream-sha>
```

### 6.3 默认分支要求

GitHub Actions 的 `schedule` 只在默认分支上的 workflow 文件生效。
迁移完成后必须将仓库默认分支设为 `personal`；否则定时同步不会运行。

该设置需要在 GitHub 仓库 Settings -> Branches 中修改，或使用 GitHub API 修改仓库 `default_branch`。

---

## 7. 一次性远端迁移

当前历史中，`main` 曾经同时包含官方和个人提交。迁移顺序：

```text
1. 备份旧 main
2. 推送新的 personal
3. 把 main 强制对齐 upstream/main
4. 把默认分支改为 personal
5. 验证定时同步、push build、手动发布
```

建议命令：

```bash
# 0. 本地先确认 personal 的父提交就是 upstream/main
git merge-base --is-ancestor upstream/main personal

# 1. 保存迁移前远端 main
git push origin refs/remotes/origin/main:refs/heads/legacy/pre-split-main

# 2. 建立个人分支
git push -u origin personal

# 3. main 对齐官方。此处会改写远端 main 历史，执行前确认备份分支存在
git push --force-with-lease origin personal:main

# 4. 到 GitHub Settings -> Branches 将默认分支设为 personal
```

> 第 3 步是唯一需要改写历史的远端操作。没有完成默认分支切换前，不要启用新的定时同步。

---

## 8. Agent 工作规则

1. `main` 只用于跟踪官方，不提交个人功能。
2. 功能、UI、品牌、CI、文档修改统一提交到 `personal`。
3. 一个主题一个提交，提交信息说明目的。
4. 官方更新先推进 `main`，再把 `personal` rebase 到新 `main`。
5. 不用复制官方源码覆盖个人修改。
6. 不删除已有个人修改，除非用户明确要求。
7. rebase 冲突只处理冲突位置；无法确定时停止并报告。
8. patch/rebase 失败不得静默继续。
9. Release 必须能追溯到 `personal` commit 与官方基线 commit。
10. 修改后优先执行本地检查；本地不能编译时，以 CI 结果为准并明确说明。
