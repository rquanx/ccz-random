# ST-009 并发与循环运行的共享历史接入

## 目标

让普通运行、并发运行和循环运行都把结果写入同一套结构化历史模型，同时保持
运行、轮次、存档和尝试之间的边界，避免 worker 异常或发布回调乱序造成统计
假完成、漏记录或串档。

## 范围

- 主协调者创建唯一 `run_id`，每个循环轮次创建唯一 `round_id`。
- worker 使用共享 SQLite 写入尝试和评分结果。
- worker 不负责结束共享 run/round；由协调者统一收尾。
- 结果发布完成后，由协调者按 `run_id + round_id + slot + save_sha256`
  更新 `published` 和 `is_final_result`。
- worker 异常、停止、重试和提前完成时，历史记录必须有明确最终状态。

## 验收标准

- 并发 1、3、5 个 worker 写入同一运行时，运行和轮次只创建一份。
- 循环两轮以上时，相同 slot 在不同轮次的尝试互不覆盖。
- 一个 worker 异常退出不会让对应任务永久停留在 saving/saved。
- 发布一个存档不会更新其他运行、其他轮次或其他 slot。
- 只有 `accepted + save_confirmed + published` 的记录进入 final 统计。
- 停止运行后，未完成任务有 stopped/unfinished 状态，不伪造为 accepted。

## 测试

- SQLite 多连接写入和幂等创建测试。
- worker 异常后重新入队或结束状态测试。
- 发布回调重复、乱序和错误 hash 测试。
- 多轮相同 slot 的统计隔离测试。
- 真实游戏多实例和循环冒烟测试，并记录未覆盖的设备风险。
