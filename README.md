# 📰 每日精选 (daily-reads)

> 每天自动把「靠谱来源」的高质量文章汇总成一份日报，推到你的 GitHub 仓库。
> 公司电脑只通 GitHub？打开这个仓库就能读，什么都不用装。

## 📖 今日阅读

<!-- DIGEST-LIST:START -->
- [2026-08-30](daily/2026-08-30.md)
- [2026-08-29](daily/2026-08-29.md)
- [2026-08-28](daily/2026-08-28.md)
- [2026-08-27](daily/2026-08-27.md)
- [2026-08-26](daily/2026-08-26.md)
- [2026-08-25](daily/2026-08-25.md)
- [2026-08-24](daily/2026-08-24.md)
<!-- DIGEST-LIST:END -->

## 🚀 部署（3 分钟，全程网页操作，不需要 git）

1. 在 GitHub 新建一个**私有仓库**（名字随意，比如 `daily-reads`），**不要**勾选任何初始化文件（README/.gitignore 都不勾）。
2. 下载本项目的 zip → 解压 → 打开仓库页 → `Add file` → `Upload files` → 把解压出来的**整个文件夹拖进上传框**（必须包含 `.github` 文件夹）→ `Commit changes`。
3. 上传完 Actions 会自动跑一次。点仓库顶部 `Actions` 标签看进度，跑完 `daily/` 里就有当天的精选了。
4. 之后**每天早上 06:00（北京时间）自动更新**。想看最新：开仓库首页 → 点上面的「今日阅读」链接。

> 想立刻手动跑一次：`Actions` → 左侧 `每日精选` → `Run workflow` → 绿色按钮。

## ✨ 可选：AI 中文摘要（强烈推荐）

默认用文章自带的简介。想升级成 AI 一句话摘要（DeepSeek 官方 API，每天 40 条摘要成本不到一毛钱）：

1. 去 <https://platform.deepseek.com> 注册，创建一个 API Key；
2. 仓库 `Settings` → `Secrets and variables` → `Actions` → `New repository secret`；
3. 名字填 `DEEPSEEK_API_KEY`，把 Key 粘进去，完成。

> 💡 公司电脑只通 GitHub 的话，正文里的外链打不开是正常的——开 AI 摘要后，日报本身就是一份能直接读完的精华，GitHub 趋势仓库的链接点开就能看。

## 🔧 自定义来源

编辑 `feeds.yaml`：增删 RSS 源、调整每个源收几条、关键词过滤。保存后会自动重新生成日报。
（没有 RSS 的网站，可以用 RSSHub 生成：`https://rsshub.app/任意网站`）

## 📁 结构

| 文件 | 作用 |
| --- | --- |
| `feeds.yaml` | 源配置（想换内容改这里） |
| `scripts/build_digest.py` | 生成脚本：抓取 → 去重 → 过滤 → 摘要 → 写日报 |
| `.github/workflows/daily.yml` | 每天定时跑的流水线 |
| `daily/YYYY-MM-DD.md` | 每日精选（自动生成，即读即看） |

## 💰 费用

- GitHub Actions 免费额度：私有仓库每月 2000 分钟，本流水线每天跑约 2 分钟，**用不到 1/30**。
- AI 摘要：DeepSeek 按量计费，日均几十条摘要 ≈ 每月一两块钱。

## 🔒 隐私

仓库设为私有，内容只有你自己可见。日报里只有标题、链接、摘要，不含任何个人数据。
