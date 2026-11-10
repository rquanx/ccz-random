# 历史兼容性回归审计（2026-11-07）

## 结论

不能将“全部现有测试通过”解释成“历史兼容性问题已全部覆盖”。

审计基线：当前 HEAD `25d1125`，加本地未提交的 4.0.0 改动。枚举当前主线从初始化开始的 161 条提交，按 fix/perf 以及 runtime/startup/randomizer/diagnostics 功能提交筛出 98 条。其他分支中的 WPF stash 快照不作为当前 Python 发布入口。下表是逐提交的测试证据清单，并不把修改了测试文件自动视为充分覆盖。

最新结果：完整单元测试 **583 项通过**；本轮新增 12 项测试。前一轮最新版游戏实测 11/11 通过，记录在 `artifacts/game-tests/2026-11-07 19.38.21/suite.json`。这些游戏测试运行源码入口，不能当作最终 EXE 的所有设备兼容性认证。

本轮修复后重新 build，并通过 subprocess 等待最终 EXE 的 `--smoke-startup`、`--smoke-windowed-output`、`--smoke-imports`、`--smoke-changelog` 四项，退出码均为 0。已同步到游戏目录和 release，SHA256：`76A711B2FEBCD20450681D33A053A0766F18A9B4FD421962DF8813E47F829C8E`。详细输出在 `artifacts/compatibility-unit-tests.txt`、`artifacts/compatibility-exe-smoke.json`。

## 本轮确认并处理

- 既有日志上报测试只有两项，没有覆盖历史 TLS 回退、取消、超时、异常返回、失败重试和复制地址。本轮增加 9 项打包/传输行为测试和 1 项真实 Tk 按钮测试（一次覆盖失败 → 再次上传 → 成功 → 复制 URL）。所有网络操作均 Mock，不上传真实日志。
- 为 `1ed90bd` / `7c84080` 补充 Tk 窗口级测试：并发停止后的最终文字、唯一结果图链接、再次启动及旧队列隔离。新测试首次运行失败，复现“进程退出且本次没有新日志时界面停留在正在停止”。已修复进程退出后没有重新置位渲染请求的问题；同一测试复跑通过。
- 测试入口默认游戏目录仍指向 2.10.4c，可能出现“测错游戏版本”。已改为当前 2.20-1104夜，增加命令行解析测试。上一轮误用旧目录的结果不作为最新版证据；指定最新版目录的 11/11 结果才计入。

测试文件：`tests/unit/test_support_diagnostics.py`、`test_support_ui.py`、`test_ui_polling.py`、`test_game_test_framework.py`。

## 已有行为覆盖的核心修复

| 历史问题 | 现行测试证据 | 限制 |
| --- | --- | --- |
| 读档延迟确认、窗口禁用、进程退出 | `test_reused_load_delayed_confirmation_is_closed`、`test_reused_load_without_confirmation_continues_when_ready`、`test_reused_load_reenables_owner_after_dialog_disappears`、`test_reused_load_detects_game_process_exit` | Mock Win32，真实游戏正常路径另测 |
| 模态点击超时、子进程输出乱码 | `test_background_click_timeout_is_treated_as_delivered`、`test_subprocess_output_supports_utf8_and_gb18030` | 不会在本机主动制造驱动级卡死 |
| 被拦截组件、正在退出的进程不应误判 | `test_security_policy_failure_does_not_restart_game`、`test_terminating_process_native_failure_requires_restart`、`test_winerror_225_is_classified_with_blocked_file_path` | 验证分类和恢复决策，不是真实安装杀毒软件验证 |
| 不移动系统鼠标、截图失败回退 | 原生无鼠标调用约束测试；`test_window_capture_recovers_after_waking_game`、`test_window_capture_reports_all_failed_strategies` | 注入、钩子时序仍受 Windows 设备影响 |
| 沙箱/兼容启动失败后回退单实例 | `test_normal_mode_startup_failure_tries_compatibility_multi_instance`、`test_normal_and_compatibility_startup_failure_falls_back_to_original_dir` 等 | 调度 Mock 覆盖，不能替代不同设备实测 |
| 首实例进入随机流程后才扩展 | `test_compatibility_probe_does_not_expand_on_startup_line_only`、`test_compatibility_probe_expands_after_result_detail` | 验证业务进度门槛 |
| 后台失去响应、重复结果、连续失败 | `test_unresponsive_worker_is_restarted_and_slot_is_retried`、`test_duplicate_batch_result_is_retried_before_publication`、`test_repeated_worker_failure_stops_after_three_attempts` | Mock worker 与临时文件 |
| 停止时保护正在保存的结果 | `test_stop_waits_for_critical_save_to_finish_cooperatively`、`test_completed_batch_result_is_published_before_stop_cleanup` | 实际游戏停止另有 case |
| 游戏菜单保存、写入后控制组件卡住 | `test_drive_game_menu_save_waits_for_real_write`、`test_drive_game_menu_save_keeps_written_save_when_control_hangs` | 实际菜单保存已有最新版游戏 case |
| 保存成功后结果图等后处理失败 | `test_workflow.py` 与 `test_round_archive.py` 的后处理失败测试 | 现行断言需与旧实现区分 |
| 新版数据库保护、历史分组、规则导入 | `test_history.py`、`test_rule_editor.py`、`test_legacy_rule_import.py` | 含真实临时数据库、Tk 按钮操作 |
| 清理不得删存档/结果/未知文件 | `test_classified_cleanup_preserves_results_recent_logs_and_live_sessions` 等 | 旧自动删结果策略已撤销，不恢复旧测试预期 |
| 仅静音随机实例 | `test_random_audio_monitor_mutes_only_its_exact_pid` | Mock 音频会话；真实 COM 接口兼容性不由此保证 |

## 不能视为完整覆盖的部分

1. `6ebb3d7` 修改原生 C 注入器和输入钩子：远程线程等待失败、STILL_ACTIVE、模块无效、部分内存写入、钩子并发修改等，没有逐分支故障注入回归。现有本机真实游戏测试只证明正常路径可用。
2. `874308d` 的“三次读档失败才切换兼容模式”现已从 direct reload 演进为 normal reload。当前有源码断言，尚缺一个从真实生产调度入口连续注入失败、成功复位再失败的完整行为测试。不能用检测 `= 3` 文本代替。
3. 扫描现有 583 项中，52 项测试方法含源码读取/源码结构检查标记（粗筛，部分还含行为断言）。这些适合保护接线/禁止调用约束，不足以单独证明界面、资源回收和运行时交互正确。
4. 最终打包 EXE 的多实例、循环、完整窗口操作及长时间内存/句柄增长，在本轮审计中没有重新执行。跨设备 Windows、安全软件、DPI 和网络环境也没有矩阵实测。
5. 七人推进旧路径和旧版本数据规则有的已被替换；保留诊断不等于当前产品仍提供这些模式。不得为通过旧测试恢复错误/过时行为。

因此：**已识别核心回归通过，但目前没有证据支持“历史兼容性修复全部都有充分行为测试且跨设备通过”。**

## 逐提交测试证据

“保留”只表示该提交新增的测试方法仍存在；“源码”表示其中有源码检查。没有新增方法不代表没有后续覆盖；旧用例消失也不代表修复丢失，需结合上方现行路径说明判断。

| 提交 | 内容 | 原提交测试文件数 | 新增方法现存/原数 | 证据/需核对点 |
| --- | --- | ---: | ---: | --- |
| `39ad825` | fix(ui): center rule editor over main window | 0 | 0/0 | test_window_position.py 已有父窗口居中行为测试；原生边框/DPI 仍需实测 |
| `c79b5b2` | fix(inspection): retry opening candidate roster | 0 | 0/0 | 旧候选列表路径已演进；现行 roster fallback / inspection retry 测试保留，原四次重试实现不再原样存在 |
| `a421826` | fix(ui): align rule help with active rule action | 0 | 0/0 | test_rule_editor.py 的规则帮助/高级帮助接线测试；文案有源码约束 |
| `ccac599` | perf(ui): optimize scoring grid rendering | 0 | 0/0 | test_score_grid_uses_one_canvas_and_edits_values / test_score_grid_filters_items_by_search_text：Tk 行为测试 |
| `44c1eda` | perf(ui): improve score cards and startup time | 0 | 0/0 | 现行 Canvas 评分控件有行为测试；启动性能无量化门槛 |
| `d8933e4` | fix(rules): persist imported profiles immediately | 0 | 0/0 | test_import_saves_profiles_immediately：Tk 操作及持久化验证 |
| `4a00032` | fix(ui): remove duplicate rule failure reason | 0 | 0/0 | test_rule_reason_is_hidden_from_user_log：用户可见日志转换验证 |
| `dda8199` | fix(runtime): reuse background game session | 0 | 0/0 | 现行重启决策、普通菜单读档有行为测试；完整复用切换链仍需补测 |
| `4a45c53` | fix(inspection): recover from background click timeout | 0 | 0/0 | test_background_click_timeout_is_treated_as_delivered / test_subprocess_output_supports_utf8_and_gb18030：后续行为测试 |
| `2ce62c8` | fix(report): show correct initial roster skills | 0 | 0/0 | 原图像特技解析被已验证内存读取替代；现行 test_skill_memory.py / test_selected_skills.py 覆盖 |
| `6edcb4d` | fix(ui): simplify stopped flow summary | 0 | 0/0 | 本轮 Tk 停止测试检查最终停止文案和唯一结果链接 |
| `c0f2624` | fix(report): use actual initial roster abilities | 1 | 4/4 | `test_session_management.py::test_equipment_order_matches_game_numbers`；部分为源码检查 |
| `49220be` | fix(runtime): handle missing windowed output stream | 1 | 2/2 | `test_session_management.py::test_tee_ignores_missing_windowed_stream` |
| `5543821` | perf(report): reuse initial roster inspection session | 0 | 0/0 | 同实例采集有源码接线检查和 three-member-inspection 实测；不是单独性能基准 |
| `5ef2570` | fix(rules): filter skills in three-person mode | 2 | 2/2 | `test_rule_editor.py::test_initial_skill_check_progress_is_visible` |
| `11b64f3` | perf(runtime): remove redundant verified waits | 0 | 0/0 | 等待策略已继续演进；有场景稳定/菜单读档行为测试，耗时基准非默认回归 |
| `5e71bba` | feat(diagnostics): capture skill storage evidence | 2 | 5/6 | `test_session_management.py::test_initial_roster_uses_xiahou_yuan_not_cao_ren`；旧方法消失/替换 1 项 |
| `0d6d423` | fix(runtime): recover interrupted save verification | 1 | 3/3 | `test_session_management.py::test_partial_memory_read_requires_restart` |
| `98b34e8` | feat(runtime): validate environment before randomization | 1 | 4/4 | `test_start_environment.py::test_valid_environment_passes` |
| `481b316` | fix(runtime): restore scene settle before reload | 0 | 0/0 | test_title_load_waits_until_scene_transition_is_settled：后续行为测试 |
| `4ba1286` | feat(diagnostics): embed build identity in logs | 1 | 2/2 | `test_build_info.py::test_frozen_build_info_is_loaded_from_bundle` |
| `a3107ab` | fix(runtime): stop retrying blocked native control | 1 | 4/4 | `test_session_management.py::test_security_policy_failure_does_not_restart_game` |
| `8ff4f9a` | fix(runtime): explain blocked background control | 1 | 2/2 | `test_session_management.py::test_non_admin_security_hint_recommends_admin_mode` |
| `5dfdd20` | fix(ui): hide build identity from progress | 1 | 0/0 | 有测试修改但无现存新增方法；需按现行流程判断 |
| `454dc70` | fix(runtime): refresh game scene between attempts | 1 | 1/2 | `test_session_management.py::test_admin_security_hint_does_not_ask_for_admin_again`；旧方法消失/替换 1 项 |
| `69b1783` | fix(runtime): diagnose reused game interaction failures | 2 | 0/0 | 有测试修改但无现存新增方法；需按现行流程判断 |
| `36d3a17` | perf(runtime): reduce per-attempt fixed waits | 4 | 5/5 | `test_session_management.py::test_timed_silent_click_passes_tail_delay_to_native_control` |
| `5e71908` | fix(runtime): diagnose reused interaction failures | 1 | 0/2 | 有测试修改但无现存新增方法；需按现行流程判断；旧方法消失/替换 2 项 |
| `eed5c6a` | fix(inspection): retry member panel transitions | 1 | 0/2 | 有测试修改但无现存新增方法；需按现行流程判断；旧方法消失/替换 2 项 |
| `bccffe8` | fix(runtime): close stale load confirmation | 2 | 0/3 | 有测试修改但无现存新增方法；需按现行流程判断；旧方法消失/替换 3 项 |
| `5f806de` | fix(runtime): wait for reused load readiness | 2 | 0/0 | 有测试修改但无现存新增方法；需按现行流程判断 |
| `493ef81` | fix(ui): simplify rule save feedback | 1 | 0/0 | 有测试修改但无现存新增方法；需按现行流程判断 |
| `611dbb4` | feat(runtime): support continuous random rounds | 1 | 5/6 | `test_round_archive.py::test_incomplete_round_preserves_only_completed_saves`；部分为源码检查；旧方法消失/替换 1 项 |
| `9ceac94` | fix(inspection): follow actual member panel order | 1 | 1/2 | `test_session_management.py::test_full_inspection_accepts_actual_game_member_order`；旧方法消失/替换 1 项 |
| `ef1da67` | fix(runtime): complete delayed reused-load confirmation | 2 | 2/3 | `test_session_management.py::test_reused_load_delayed_confirmation_is_closed`；旧方法消失/替换 1 项 |
| `4aea157` | fix(runtime): bound console and log growth | 1 | 5/5 | `test_log_retention.py::test_removes_expired_managed_files_only`；部分为源码检查 |
| `43e7369` | fix(runtime): recover disabled load owner and panel navigation | 1 | 1/3 | `test_session_management.py::test_reused_load_reenables_owner_after_dialog_disappears`；旧方法消失/替换 2 项 |
| `3a3ad31` | fix(runtime): fall back when direct reload exits game | 1 | 2/2 | `test_session_management.py::test_reused_load_detects_game_process_exit` |
| `675ba20` | fix(workflow): preserve saved results after post-processing failures | 3 | 5/6 | `test_rule_editor.py::test_score_grid_uses_one_canvas_and_edits_values`；部分为源码检查；旧方法消失/替换 1 项 |
| `ac07931` | fix(ui): hide runtime recovery details from console | 1 | 1/1 | `test_rule_editor.py::test_runtime_recovery_details_are_hidden_from_user_log` |
| `51fb18e` | fix(inspection): inject real mouse clicks for member navigation | 1 | 1/3 | `test_session_management.py::test_dialog_fixed_fallback_uses_injected_mouse`；旧方法消失/替换 2 项 |
| `4cd3e25` | fix(inspection): fall back to roster for unread members | 1 | 1/2 | `test_session_management.py::test_roster_fallback_skips_captured_member`；旧方法消失/替换 1 项 |
| `c2bb348` | fix(inspection): recover member panels through roster | 1 | 4/5 | `test_session_management.py::test_forced_dialog_click_uses_dialog_relative_mouse`；旧方法消失/替换 1 项 |
| `cbc135f` | fix(rules): scope active-run save notice | 1 | 1/2 | `test_rule_editor.py::test_current_run_notice_only_when_running_profile_changes`；旧方法消失/替换 1 项 |
| `0d01712` | fix(runtime): limit diagnostics and fall back after reload failure | 1 | 1/2 | `test_session_management.py::test_tee_ignores_missing_windowed_stream`；旧方法消失/替换 1 项 |
| `8f416bc` | fix(diagnostics): deduplicate failure screenshots by type | 1 | 2/2 | `test_session_management.py::test_diagnostic_screenshots_keep_only_one_per_error_type` |
| `874308d` | fix(runtime): delay compatibility mode until third reload failure | 0 | 0/0 | 已改普通菜单读档；三次切换目前仅源码约束，不算充分行为覆盖 |
| `ffc7ed6` | feat(startup): block low memory and active 360 environments | 1 | 2/3 | `test_start_environment.py::test_low_available_memory_blocks_start`；旧方法消失/替换 1 项 |
| `948aff4` | fix(runtime): restart when target process is terminating | 1 | 2/2 | `test_session_management.py::test_terminating_process_native_failure_requires_restart` |
| `6ebb3d7` | fix(native): harden background control compatibility | 0 | 0/0 | 原生错误分支缺专项故障注入；本机游戏正常路径通过 |
| `8709ade` | feat(diagnostics): add structured failure tracing | 4 | 7/7 | `test_runtime_diagnostics.py::test_records_include_sequence_context_and_elapsed_time`；部分为源码检查 |
| `9c83c22` | fix(inspector): fall back after roster command failure | 1 | 2/2 | `test_session_management.py::test_roster_fallback_uses_injected_click_after_list_command_error` |
| `99ccc99` | fix(runtime): use normal game loading for randomization | 5 | 4/6 | `test_session_management.py::test_normal_load_uses_game_menu_and_verifies_memory`；部分为源码检查；旧方法消失/替换 2 项 |
| `5e4e46d` | fix(inspector): avoid background panel timeout | 2 | 7/7 | `test_runtime_diagnostics.py::test_wrapped_inspection_timeout_is_classified_as_native_timeout` |
| `60364fe` | fix(inspector): pace seven-member story progression | 1 | 1/1 | `test_session_management.py::test_seven_member_story_progress_is_paced` |
| `03a35eb` | fix(inspector): retry Xu Zijiang with injected click | 1 | 3/3 | `test_session_management.py::test_inspection_npc_click_uses_injected_background_mouse` |
| `5f99b64` | feat(diagnostics): trace seven-member inspection stages | 2 | 2/2 | `test_session_management.py::test_inspection_attempt_logs_are_outside_retry_directory`；部分为源码检查 |
| `43a176a` | fix(inspector): trace corrected seven-member progression | 3 | 5/5 | `test_log_retention.py::test_keeps_only_newest_diagnostic_screenshots_per_run` |
| `fe8e4ea` | fix(inspector): inspect seven members in active session | 2 | 0/0 | 有测试修改但无现存新增方法；需按现行流程判断 |
| `5092268` | fix(runtime): explain antivirus quarantined components | 1 | 2/2 | `test_start_environment.py::test_missing_injector_explains_antivirus_quarantine` |
| `28bff16` | fix(randomization): stabilize seven-member inspection | 2 | 3/3 | `test_session_management.py::test_inspection_npc_click_uses_injected_background_mouse`；部分为源码检查 |
| `b5f1f16` | perf(inspector): stop seven-member story when ready | 2 | 2/2 | `test_session_management.py::test_seven_member_story_stops_when_scene_is_ready` |
| `14283ee` | perf(randomizer): accelerate inspection and show score details | 4 | 5/6 | `test_result_details.py::test_result_detail_round_trip_preserves_chinese_text`；部分为源码检查；旧方法消失/替换 1 项 |
| `05f050b` | fix(randomizer): make stop requests interrupt current work | 4 | 4/4 | `test_session_management.py::test_native_control_stops_without_waiting_for_timeout` |
| `c4adc2f` | perf(randomizer): shorten seven-member story clicks | 3 | 0/0 | 有测试修改但无现存新增方法；需按现行流程判断 |
| `1899bff` | feat(randomizer): improve background game reliability | 4 | 10/11 | `test_session_management.py::test_process_alive_checks_the_requested_pid`；部分为源码检查；旧方法消失/替换 1 项 |
| `ade1b44` | feat(randomizer): add concurrent sandbox workflow | 0 | 0/0 | 后续 3ca275f / test_concurrent.py / test_game_sandbox.py 补充调度、回退和沙箱行为测试 |
| `3c9f8df` | feat(randomizer): improve concurrent workflow and control reuse | 6 | 27/27 | `test_concurrent.py::test_console_render_signature_changes_only_for_visible_output`；部分为源码检查 |
| `6d33554` | fix(archive): respect configured result slots | 1 | 3/3 | `test_round_archive.py::test_complete_round_rejects_missing_configured_slot`；部分为源码检查 |
| `db0a886` | fix(concurrent): retry duplicate results and exit cleanly | 2 | 6/6 | `test_concurrent.py::test_result_signature_ignores_slot_attempt_and_scores`；部分为源码检查 |
| `4893396` | fix(history): preserve newer schema databases | 1 | 1/1 | `test_history.py::test_newer_history_database_is_preserved_and_uses_compatible_file` |
| `b972872` | fix(editor): cancel toast callback after destruction | 1 | 2/2 | `test_rule_editor.py::test_destroyed_toast_cancels_pending_close_callback` |
| `56f5e4f` | fix(game-22): capture job catalog for every score detail | 0 | 0/0 | 后续采集可选化；test_job_talents / collection preferences 保护未采集语义 |
| `3690e75` | fix(ui): reduce recruitment popup rendering lag | 2 | 0/0 | 有测试修改但无现存新增方法；需按现行流程判断 |
| `27e7c91` | fix(skills): include 2.2 talent entries | 1 | 2/2 | `test_job_talents.py::test_runtime_catalog_includes_22_new_talents`；部分为源码检查 |
| `07980a0` | fix(skills): sync 2.2 talent catalog and scoring | 2 | 4/4 | `test_skill_catalog_22.py::test_catalog_matches_all_real_22_names_formats_and_parameters` |
| `10ad335` | fix(rules): align settings with 2.2 initial roster | 1 | 0/0 | 有测试修改但无现存新增方法；需按现行流程判断 |
| `835089e` | fix(storage): cap accumulated result artifacts | 1 | 0/2 | 旧自动删结果策略已撤销；当前清理策略保护结果；旧方法消失/替换 2 项 |
| `16d0915` | fix(storage): restrict result cleanup to managed artifacts | 1 | 0/1 | 旧自动删结果策略已撤销；当前清理策略保护结果；旧方法消失/替换 1 项 |
| `60d8195` | fix(storage): focus cleanup on sandboxes and logs | 3 | 7/7 | 现行 test_storage_cleanup 验证结果/存档/未知文件保护 |
| `587c260` | fix(ui): remove duplicate equipment action from history details | 0 | 0/0 | 详情动作接线/顺序仍有源码检查；完整窗口操作非本轮专项 |
| `1cdd88e` | fix(history): bound member previews and reset round scroll | 1 | 1/1 | `test_history_members.py::test_summary_member_text_limits_long_people_lists` |
| `1e0268f` | fix(ui): order detail actions by information priority | 0 | 0/0 | 详情动作接线/顺序仍有源码检查；完整窗口操作非本轮专项 |
| `61a7e21` | fix(ui): restore runtime execution controls | 0 | 0/0 | test_ui_polling：启动、完成、再次启动真实按钮/控件状态 |
| `1ed90bd` | fix(ui): retain concurrent result image link | 0 | 0/0 | 本轮 Tk 验证停止后唯一结果图链接 |
| `c8aeec8` | fix(history): group concurrent slots into one round | 1 | 2/2 | `test_history.py::test_shared_concurrent_run_keeps_one_round_for_all_slots` |
| `7c84080` | fix(concurrent): finalize result image and stop state | 0 | 0/0 | 本轮 Tk 复现并修复最终停止状态未重绘 |
| `e969c1e` | perf(concurrent): reduce UI polling and output overhead | 0 | 0/0 | 渲染签名/轮询异常已有测试；长时资源增长未实测 |
| `72006ba` | fix(ui): rename personnel data tab | 0 | 0/0 | 界面名称后续继续调整；非设备兼容性修复，不能以文案测试证明交互 |
| `02750b0` | fix(ui): rename personnel tab to experimental features | 0 | 0/0 | 界面名称后续继续调整；非设备兼容性修复，不能以文案测试证明交互 |
| `22124a9` | fix(ui): update experimental feature guidance | 0 | 0/0 | 帮助文案由后续使用说明调整；非设备兼容性修复 |
| `77191e6` | fix(support): bound log reads during archive creation | 0 | 0/0 | 本轮新增超大日志有界读取与尾部数据验证 |
| `12560e5` | fix(support): exclude previous report archives | 0 | 0/0 | 本轮新增旧 support 压缩包排除验证 |
| `45b6aa2` | fix(support): show cancellable upload progress | 0 | 0/0 | 本轮新增预取消、curl 取消、超时与进度首尾验证；urllib 在途取消受超时限制 |
| `f21b782` | fix(support): switch log upload provider | 0 | 0/0 | 本轮新增真实响应结构、异常响应验证（Mock 网络） |
| `6e97ca6` | fix(support): make uploaded log URL copyable | 0 | 0/0 | 本轮 Tk 真实按钮验证剪贴板 URL |
| `784da56` | fix(support): add curl fallback for TLS upload failures | 0 | 0/0 | 本轮新增 TLS 回退、取消、超时回收与错误信息验证 |
| `25d1125` | fix(support): allow retry after upload failure | 0 | 0/0 | 本轮 Tk 真实按钮验证失败后重新上传成功 |
