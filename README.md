# DSH Campus Recruitment

**DSH 原生招聘管理插件 + 按需启动的 Python/SQLite 后端。** 默认用于 2027 届研发方向校招，求职背景、届别、关键词与本地路径均可配置。

本仓库只发布程序和示例配置，不包含作者的岗位库、投递记录、日报、API Key 或任何浏览器登录资料。没有独立桌面应用，也不依赖 Codex 日常运行。

## 功能

- MiniMax 订阅搜索发现企业及岗位，Python 采集公开页面、校验原文、保存历史与去重。
- 支持公开 JavaScript 动态页面：按需使用现有 Edge/Chrome、独立未登录临时配置；无验证码破解、无登录绕过。
- DSH 左侧岗位列表，支持状态、收藏、关键词、筛选、投递日期、平台、备注和修改历史。
- 只把明确的用户操作记为已投递；自动采集不覆盖用户字段，不自动提交简历。
- 唯一的 DSH 原生任务每天 **19:00 Asia/Shanghai** 运行；关闭电脑期间不运行，恢复时由官方调度器补最近一次到期任务。
- SQLite 同日防重、进程锁、失败记录和 Markdown 日报；Python/浏览器工作进程完成后退出。

## 要求

- Windows；本版基于 DSH **0.2.2-rc.1** 接口，声明兼容 `>=0.2.2-rc.1 <0.3.0`。其他发行版本需要自行核实接口，不保证所有版本可用。
- Python **3.10+**、Node **22+**，优先自动发现 DSH 已有运行时，不会全局安装软件或修改 PATH。
- 动态采集可选 Edge/Chrome；找不到浏览器时静态采集仍可用。
- 在 DSH 中配置你自己的 MiniMax 模型和订阅搜索凭据。默认路由 `minimax / MiniMax-M3.1-Flash`、凭据引用 `MINIMAX_API_KEY`。本项目不提供账户、额度或密钥。

## 安装

1. 下载本仓库 ZIP，解压到固定位置，例如 `D:\Apps\dsh-campus-recruitment`，或者克隆仓库。**安装目标是包含根目录 `package.json` 的文件夹，不是其内部 `plugin` 文件夹。**
2. 在该目录打开 PowerShell，运行：

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\Setup.ps1 -DataRoot "D:\RecruitmentData"
   ```

   这里只为本次脚本进程指定执行策略，不修改全局执行策略。脚本生成被 Git 忽略的 `config.local.json`，检查已有 Python/Node，不安装插件、不读取密钥、不创建数据库。
3. 自动发现失败时显式传入现有程序路径：

   ```powershell
   .\Setup.ps1 -DataRoot "D:\RecruitmentData" -Python "D:\Runtimes\Python\python.exe" -Node "D:\Runtimes\Node\node.exe" -Browser "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
   ```

4. 编辑 `config.local.json` 中的 `profile`、`graduation_year`、`keywords`。这些设置不会被提交到 GitHub。**不要填 API Key**，`credentialRef` 是 DSH 受管凭据名称。
5. 打开 DSH → 插件 → 添加插件 → 安装第三方插件，填写解压目录，启用并按界面提示重启。桌面 Profile 由 Electron 管理，本文不通过 CLI 修改它。
6. 左侧打开“招聘管理”。确认任务显示已启用、时间为 19:00，然后点“立即运行”验证自己的模型/订阅/网络。没有密钥时应显示明确错误，不会切换到付费服务。

如果 DSH 插件管理器支持从 GitHub 地址安装，可使用 `https://github.com/Liora1128/dsh-campus-recruitment`。需要自定义配置时，优先下载本地固定目录安装；软件包缓存路径不适合作为用户配置或数据位置。

## 使用

岗位状态下拉框和星标立即保存。填写实际投递日期、平台、备注后点击保存。通过“已投递及后续”查看面试等进展；状态误标可再次修改，历史保留。列表分页，不会只保存当前页。

日报在 DSH 原生任务会话和“日报与执行记录”中查看，磁盘上也保留 Markdown。最近 48 小时为搜索提示，不足时扩展 7 天；推荐仍以正文核实的日期与资格为准，不把搜索日期、抓取日期或更新日期当成发布日期。

电脑需开机、联网且 DSH 正在运行。当天已经处理完成，再点立即运行只记录跳过，不重复推荐。若任务中途被断电中止，官方是否重新交付取决于原生会话状态，必要时点立即运行；不另建系统补跑任务。

## 数据和配置

默认数据根目录是用户主目录下 `.dsh-campus-recruitment`；使用 Setup 后以 `dataRoot` 为准。里面有：

```text
data/recruitment.sqlite3   # 岗位、用户状态、历史、缓存及执行台账
reports/                  # Markdown 日报
logs/                     # 执行和逐来源日志
data/browser-sessions/    # 每次渲染的临时配置，正常退出后删除
```

数据独立于源码，更新代码不应删除数据。路径和模型等配置见 [配置说明](docs/configuration.md)，换电脑见 [迁移说明](docs/migration.md)，停止使用见 [数据清理](docs/privacy-and-removal.md)。

## 限制与验证

采集无法保证覆盖所有企业。验证码、登录限制、403/412、robots 禁止和超时会保留失败原因并跳过；未确认的官网入口、发布日期、截止时间和资格不补造。近似岗位名、城市别名和不同来源仍可能留下需要人工核对的近似记录，不能仅凭评分代替人工核实。

发布前测试在隔离临时数据库及移动后的目录中执行，不连接作者的真实岗位库。已验证的 DSH 调度机制和本机运行不能代表其他实体电脑、所有登录方式或所有 DSH 版本均已验证。Windows x64 是主要验证平台。

本项目的公开发布版尚未自动替换任何现有本机安装；已有使用者应先阅读迁移说明，备份后再自行升级。不要同时安装两份同功能插件或建立两份招聘任务。

## 开发测试

无 pip/npm 运行依赖。已有 Node/Python 时：

```powershell
node --test tests/*.test.mjs
python -X utf8 -m unittest discover -s tests -v
node tools/doctor.mjs
```

可通过 `CAMPUS_PYTHON`、`CAMPUS_NODE`、`CAMPUS_BROWSER`、`CAMPUS_DATA_ROOT`、`CAMPUS_CONFIG_FILE` 为测试进程覆盖配置，不必修改全局环境。

模型与搜索在 DSH 受管 Host 内调用，Python 不接收密钥。协议参考：[MiniMax 官方搜索 MCP](https://platform.minimax.cn/docs/m-plan/mcp-guide)、[官方 MCP 源码](https://github.com/MiniMax-AI/MiniMax-Coding-Plan-MCP/blob/main/minimax_mcp/server.py)；浏览器参考 [Chrome CDP](https://chromedevtools.github.io/devtools-protocol/)。

## 许可

MIT，见 [LICENSE](LICENSE)。DSH、MiniMax、Chrome/Edge 和招聘网站由各自提供方维护，本项目不代表这些服务的官方产品。
