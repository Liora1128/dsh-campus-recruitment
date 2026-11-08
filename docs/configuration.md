# 配置说明

将 `config.example.json` 复制为 `config.local.json`，或运行 `Setup.ps1`。本地配置已被 `.gitignore` 排除，也不属于发布包允许清单。不要把密钥写入配置；未知字段（例如 `apiKey`）会被拒绝。

| 字段 | 含义 |
|---|---|
| `dataRoot` | 独立数据根目录；相对路径相对于源码根目录，而非 DSH 当前工作目录 |
| `python` / `node` / `browser` | 程序完整路径；空字符串表示自动发现 |
| `provider` / `model` / `reasoningEffort` | DSH 已配置的模型路由、模型ID和推理强度；示例名称不代表自动开通模型 |
| `credentialRef` | DSH 受管 MiniMax 订阅密钥的引用名称，默认 `MINIMAX_API_KEY`，不是明文密钥 |
| `region` | `cn` 或 `global`，必须与密钥地区一致；国际线路未在作者账户上实测 |
| `monthlySearchLimit` | 本地每月搜索请求硬上限，默认260，不表示订阅本身有260次额度，也不代购额度 |
| `graduation_year` | 目标毕业年份，默认2027 |
| `profile` | 自己的学历、技能、岗位优先级、地点和排除条件；评分缓存包含此内容，修改后重新分析相关岗位 |
| `keywords` | 最多8个岗位方向关键词组合，不是固定企业名单 |
| `official_domains` | 人工确认的招聘官网域名；空列表不会把第三方页面冒称官网 |

自动发现顺序为进程环境覆盖、明确配置、DSH_HOME 下已有运行时、已有 PATH。浏览器优先现有 Edge/Chrome 标准位置。不会下载浏览器、读取个人浏览器配置或修改注册表。Windows Apps 商店 Python 占位程序会被跳过。

环境变量只作用于启动进程：`CAMPUS_PYTHON`、`CAMPUS_NODE`、`CAMPUS_BROWSER`、`CAMPUS_DATA_ROOT`、`CAMPUS_CONFIG_FILE`。不要为了运行本插件永久修改系统 PATH。DSH_HOME 的默认值是当前用户主目录下 `.dsh`；如果自己的 DSH 使用其他位置，可在配置中直接写运行时路径。

修改 Host 侧路径或模型配置后重启 DSH。Python/浏览器均按需启动，没有后台服务。原生任务固定19:00 Asia/Shanghai；暂停任务后插件不会擅自恢复。跨地区账户须自己核实订阅接口，失败时程序停止，不切换成按量计费 Key。
