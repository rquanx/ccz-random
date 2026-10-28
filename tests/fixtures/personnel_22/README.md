# 2.2 真实标题界面数据

来源：用户提供的 `E:/game/ccz/曹操传加强版2.2/Ekd5.exe` 隔离副本。
采集日期：2026-10-28。可执行文件 SHA-256 见 title.json。

`records.bin` 为标题界面人物表的前 8 条原始记录，每条 0x48 字节。
`title.json` 为同版本标题界面实际读取的对应天赋数据。
姓名位于记录 +8 至 +16（GB18030、零结尾），首 DWORD 为 0x1000 + 记录索引。

这些数据仅验证读取/分类/展示，不代表随机结果，也不能证明招募资格或关卡。
不得用此夹具为任何角色假设招募关卡、随机后兵种或天赋。


## 招募与随机后的真实夹具

- `r99-stage-assignments.bin`：内置 R_99.EEX 的 0x6cf..0x18ee 赋值区域；验证 42 个关卡窗口和全部人物索引。完整脚本哈希见 resources/data/recruitment/recruits_2.2.json。
- `recruitment-before.bin` / `recruitment-after.bin`：同一隔离游戏选择招募模式第一项前后的状态切片，原范围 0x8a80..0x8ad0，包含真实开启标志。
- `randomized-memory.json`：隔离副本通过真实随机及保存后，再读取第 1 栏存档所采集的内存片段。键为绝对地址:长度，值为原始字节十六进制；用作无游戏进程的回放 reader。
- `randomized-personnel.json`：上述随机的 116 名候选及其关卡信息。已验证保存后采集和读回存档后的兵种、兵种天赋、人物天赋完全一致。

这些新夹具由 tools/diagnostics/smoke_recruitment_22.py 于 2026-10-28 在临时副本采集，未修改用户源第 20 栏存档或源脚本。首次试验发现保存前过早读取会遗漏首关剧情追加的关羽、张飞天赋，因此生产采集发生在完成保存之后。
