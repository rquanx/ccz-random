# 游戏数据包与更新

当前应用默认 profile 为 `ccz-v2.20-1104-night`，由 PyInstaller 内置。首次使用只需一个 EXE，无须联网或旁置资源。

## 数据边界

`resources/data/profiles/<id>/manifest.json` 声明 profile ID、游戏版本、修订号、引擎布局、资源清单和 SHA-256。

- `fingerprints.json`：EXE 指纹仅作为已知版本提示，未命中时按当前激活的数据包执行；其他文件指纹仅记录来源。任何文件指纹差异都不会阻止运行，游戏版本与工具数据的适配由用户确认。
- `jobs.json`：兵种名称、编号、评分和类型。
- `fixed_entries.json`：固定入队人员、记录编号、关卡、筛选顺序和展示顺序。
- `recruitment.json`：招募人员、消耗、可选兵种和关卡。
- `skills.json`：特技评分、类型、专属标记、运行目录、名称标签和声明式显示规则。显示规则涵盖格式模板、索引范围、能力位掩码、源/目标能力转换、旧名称映射，以及宝物名称、分类、套装、优质标记、特效和记录布局。
- `memory_layout.json`：Python 内存读取所使用的表地址、字段偏移和表大小。
- `script_rules.json`：招募解析特征、已核实特殊指令、招募开启标记。

历史 `ccz-v2.2` 仅供历史夹具和显式旧数据 API 回归；应用自动识别只使用当前激活包的指纹，不扫描旧版。未识别的游戏发行文件按当前激活数据包执行，不因版本未命中而拦截。真正的文件读取错误、进程启动失败、内存异常和写入校验失败仍由对应操作报告，不伪装成版本问题。

`personnel-v1` 是工具当前引擎 ABI：人物记录大小和字段结构固定。Windows 调用、原生 DLL 的函数地址和控制流程、游戏脚本执行方式、声明式规则解释器仍属于引擎。若这些改变，更新工具 EXE；单改内存读取地址不能自动适配原生 DLL。更新作者必须对新构建做探测和真实随机/存档回读冒烟验证。

## 用户更新

启动后在后台读取当前兼容组的 HTTPS 清单，只有发现新数据包才下载 ZIP 并自动安装。版本相同不下载；同一 profile 的较旧修订不会自动覆盖本地新版。仅当清单确认有适配当前工具、且本地需要更新的数据包，而自动下载或安装失败时，才通过 Toast 引导到“常见问题 → 手动更新数据”。检查失败、网络无法访问清单、清单不兼容、无需更新及更新成功均静默；错误细节写入诊断日志。下载完成后在无随机任务时立即生效；随机运行中保留当前快照，停止后切换，无需重启。

常见问题中的“手动更新数据”用于自动更新失败时恢复，只提供两个操作：

1. **下载文件**：用默认浏览器打开当前兼容组的 OSS `latest.zip` 直链，不依赖 Python 的下载连接成功。
2. **上传数据包**：导入下载的 ZIP；兼容信息、文件清单及 SHA-256 全部验证通过才激活，失败保留当前数据。

手动更新入口在随机运行时禁用。当前启动检查的默认地址为 `https://ccz-fast-profile.oss-cn-guangzhou.aliyuncs.com/channels/ccz-fast-v2/profile.feed.json`。旧版共享配置中的根目录/v1 官方源与自定义源均不直接继承到新版，默认使用 v2 官方源；旧配置明确关闭检查时保持关闭，新版单独保存的配置优先。

4.0.1 安装目录为 EXE 旁 `ccz_fast_data/profiles/channels/ccz-fast-v2/`，更新源配置为 `ccz_fast_data/profile_update.ccz-fast-v2.json`。这属于更新缓存；未更新时不需要该目录。完整验证后安装到不可变目录，再原子切换 `active.json`；旧包保留，安装失败保持原激活包。工具仅启动时检查一次更新，下载完成后在没有随机任务运行时刷新数据快照、人物名单、兵种、特技、内存地址及相关缓存，不需要重启。正在运行的 Worker 及其子实例通过 `CCZ_PROFILE_DIRECTORY` 固定使用原不可变目录，任务结束后 GUI 再激活新数据，避免一轮内混用两份数据。

右上角版本号后仅显示数据包状态圆点，不显示修订号或状态文字：旧版本为红点，下载中为黄色呼吸点，最新为绿点。下载已完成但随机仍在运行时显示黄色静态点；未完成检查、断网或更新源不可用时显示灰点，不会误报最新。具体说明悬停圆点时显示；悬停工具版本号提示“双击查看更新日志”。仅确认存在兼容的新数据包且更新失败时弹出原有失败提示。

ZIP 限制 8 MiB、最多 64 项、展开后最多 16 MiB，拒绝越界路径和符号链接；数据包只作为 JSON 读取，不执行包内代码。SHA-256 检查损坏和清单一致性，**不是发布者数字签名**；应只使用开发者发布的包和更新源。

## 工具兼容组

工具发布号与数据包修订号独立。`ccz_randomizer/profile_compatibility.py` 的 `PROFILE_COMPATIBILITY_ID` 固定声明这个 EXE 理解哪一组数据，例如 `ccz-fast-v2`。

| 工具版本（举例） | 兼容组 | 独立更新清单 |
| --- | --- | --- |
| 4.0.0（关羽修复 r3） | ccz-fast-v1 | channels/ccz-fast-v1/profile.feed.json |
| 4.0.1（声明式显示规则，内置 r5） | ccz-fast-v2 | channels/ccz-fast-v2/profile.feed.json |

每个组有自己的最新数据包，不能按 Bucket 内文件名或上传时间选全局最新。工具先检查清单的 `compatibilityId`，然后检查包内 manifest 的 `toolCompatibility` 列表；不匹配或缺失都拒绝。该校验覆盖启动加载、自动更新及手动导入，不能靠手动导入绕开。

同一个包可以声明多个组，例如 `"toolCompatibility": ["ccz-fast-v2", "future-compatible-group"]`，对应组的清单可以指向同一 ZIP，但发布者必须分别验证这些引擎确实支持它。若引擎不兼容，发布新工具并修改组 ID，保留旧组最后可用的清单和 ZIP。旧根目录清单保留为旧 EXE 的独立入口，不向其发布不兼容数据。


### 4.0.0 / 4.0.1 本地共存

4.0.0 的共享 profiles/active.json、安装目录和更新源配置原样保留；4.0.1 只读取自己的渠道目录，不迁移、不删除旧包。新版安装、恢复内置及错误包导入均不会修改旧版激活记录。启动时同一 profile 的外部修订低于内置修订则使用内置；已经开始的一轮和子进程按不可变目录固定快照，不在中途切换。不同渠道的修订号不互相比较。

v2 未发布（HTTP 404）、无法联网或清单不兼容时静默使用当前有效数据，首次启动即为内置 r5。离线运行不需要旁置 ZIP。下载按钮始终指向当前渠道的 latest.zip，发布 v2 之前该链接不可下载，不能退回 v1 来凑包。

发布本次 v2/r5 时只上传 channels/ccz-fast-v2/ 的三个文件；保留 v1 的 r3、latest.zip 和清单，保证 4.0.0 仍能获得关羽修复。

### 显示规则能更新什么

formats 支持 literal、number、strategy、index、mask、transfer 六种受限操作；模板只允许白名单变量，不支持表达式、属性访问、转换或格式指令。参数边界、位数、进位规则、能力源回退、分隔符、查表结果均为数据。catalogOverrides 修正目录中的旧名，aliases 与 normalization 保留用户旧名称设置。equipment 同时定义内存记录分组、名称分类及特效渲染，不再在 EXE 中列游戏特效分支。

每次修改还应同步运行目录与默认评分中的最终名称。若未来需要新的操作类型、人物记录结构或原生控制流程，则必须升级 EXE 和必要时更换兼容组，不能仅在包里加未支持的字段。验证失败时拒绝导入，保留当前激活数据。

## 发布新包

复制当前 profile，修改数据、`profileId`、`gameVersion`、`fingerprintVersion`、`toolCompatibility` 和 `catalogVersion`。同一 profile 修订时递增 `catalogVersion`，新游戏版本使用新 ID。文件指纹必须来自完整新游戏。

```powershell
.\.venv-win10-py314\Scripts\python.exe -m tools.build_profile_package resources/data/profiles/ccz-v2.20-1104-night release/channels/ccz-fast-v2/ccz-v2.20-1104-night-r5.zip --download-url https://ccz-fast-profile.oss-cn-guangzhou.aliyuncs.com/channels/ccz-fast-v2/ccz-v2.20-1104-night-r5.zip
```

构建工具生成 ZIP 和同名 `.feed.json`。发布时：

1. 上传带修订号的不可变 ZIP，验证匿名 HTTPS 下载及 SHA-256。
2. 将同一 ZIP 复制为该组的 `latest.zip`，供浏览器手动下载。建议 Cache-Control 为 no-cache，避免浏览器缓存旧包。
3. 将生成的 `.feed.json` 最后发布为该组的 `profile.feed.json`。清单指向不可变 ZIP，避免发布过程中出现新清单配旧 ZIP 的校验冲突。

```json
{
  "schemaVersion": 1,
  "compatibilityId": "ccz-fast-v2",
  "profileId": "ccz-v2.20-1104-night",
  "catalogVersion": 5,
  "url": "https://ccz-fast-profile.oss-cn-guangzhou.aliyuncs.com/channels/ccz-fast-v2/ccz-v2.20-1104-night-r5.zip",
  "sha256": "ZIP 的 SHA-256"
}
```

清单和 ZIP 均需公开 HTTPS 直链。发布前运行单元测试及 `tools.diagnostics.probe_game_version`、`tools.diagnostics.smoke_recruitment_22 --all-rule-members`。

## 托管选择

当前使用阿里云 OSS 广州地域的 `ccz-fast-profile` Bucket，文件公共读、标准存储。只分发 profile ZIP 和清单，不在这里分发 EXE。发布新版本时先上传带修订号的 ZIP，确认匿名 HTTPS 下载及 SHA-256 正确，再覆盖 `profile.feed.json`。已发布 ZIP 保持不变，以免旧清单与下载内容不一致。

纯免费且长期保证国内顺畅的公开直链平台无法作保证。GitHub Releases、Cloudflare Pages 可作为海外备用源，但不应承诺大陆连通性。Gitee 等代码托管平台的附件/原始文件访问规则应在选定后实测，不能把需要登录或反爬验证的地址直接作为更新源。国内 OSS/COS/OBS 对这种小包成本很低，但免费额度和有效期需查当前套餐。

OSS 按用量计费；费用预算告警不等于硬性消费上限，不会自动停止服务。

## 2026-11-08：补齐蓝线关羽

内置数据包修订号升至 3。固定／剧情人员补入关羽（记录 3），入队节点为蓝线江陵之战前；固定／剧情人员共 18 人，与 126 名招募候选合计 144 人。当前游戏 `RS/R_48.eex` 的 SHA-256 为 `2173b3fbe33d549703ef6dc88bdf05087478348f3ffe809273cfc846ee142ed6`，0x17a8 为关羽入队指令，随后有“关羽兵种赋值”并读取初始随机兵种。原始脚本夹具为 `tests/fixtures/personnel_220_1104/r48.eex`。这是名单遗漏修复；未逐关实玩至江陵验证。旧历史保留原快照，不补造关羽数据。
