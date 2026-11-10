"""Legacy game runtime adapter; dependencies are captured for one worker session."""
from __future__ import annotations
from pathlib import Path


def patch_runtime(
    task_module,
    pid: int,
    three_person_mode: bool = False,
    rules: dict | None = None,
    game_executable: Path | None = None,
    *, services,
) -> None:
    INITIAL_TEAM_MEMBERS = services.INITIAL_TEAM_MEMBERS
    InteractionNotTriggered = services.InteractionNotTriggered
    JOB_MAP = services.JOB_MAP
    JOB_POSITIONS_R0 = services.JOB_POSITIONS_R0
    JOB_POSITIONS_R1 = services.JOB_POSITIONS_R1
    NativeControlError = services.NativeControlError
    NativeControlTimeout = services.NativeControlTimeout
    NormalReloadUnsupported = services.NormalReloadUnsupported
    Point = services.Point
    R0_MEMORY_SIZE = services.R0_MEMORY_SIZE
    SOURCE_SAVE_NUMBER = services.SOURCE_SAVE_NUMBER
    SOURCE_TITLE_LIST_INDEX = services.SOURCE_TITLE_LIST_INDEX
    ScratchSaveGuard = services.ScratchSaveGuard
    SimpleNamespace = services.SimpleNamespace
    TEAM_MEMBERS = services.TEAM_MEMBERS
    VALID_GAME_VERSIONS = services.VALID_GAME_VERSIONS
    WindowCaptureError = services.WindowCaptureError
    WindowCaptureUnavailable = services.WindowCaptureUnavailable
    XU_CLIENT_POSITION = services.XU_CLIENT_POSITION
    active_profile = services.active_profile
    advance_seven_member_story = services.advance_seven_member_story
    attach_fixed_entries = services.attach_fixed_entries
    attach_recruitment = services.attach_recruitment
    build_equipment_specials = services.build_equipment_specials
    capture_initial_member_panels = services.capture_initial_member_panels
    capture_interaction_failure = services.capture_interaction_failure
    capture_window_with_fallbacks = services.capture_window_with_fallbacks
    check_stop_requested = services.check_stop_requested
    click_geometry_diagnostic = services.click_geometry_diagnostic
    close_member_dialog = services.close_member_dialog
    commit_qualified_result_save = services.commit_qualified_result_save
    critical_random_operation = services.critical_random_operation
    ctypes = services.ctypes
    current_game_version = services.current_game_version
    decode_equipment_records = services.decode_equipment_records
    deepest_child_at = services.deepest_child_at
    default_rule_config = services.default_rule_config
    diagnostic_log = services.diagnostic_log
    drive_game_menu_load = services.drive_game_menu_load
    drive_game_menu_save = services.drive_game_menu_save
    enable_game_acceleration = services.enable_game_acceleration
    ensure_game_menu_ready = services.ensure_game_menu_ready
    evaluate_job_rules = services.evaluate_job_rules
    evaluate_task_skill_rules = services.evaluate_task_skill_rules
    expand_rule_members = services.expand_rule_members
    find_any_member_dialog = services.find_any_member_dialog
    find_process_window = services.find_process_window
    find_process_window_by_class = services.find_process_window_by_class
    fixed_member_indices = services.fixed_member_indices
    game_state_diagnostic = services.game_state_diagnostic
    hashlib = services.hashlib
    interaction_failure_type = services.interaction_failure_type
    interruptible_sleep = services.interruptible_sleep
    is_enhanced_game_version = services.is_enhanced_game_version
    job_rule_report = services.job_rule_report
    load_catalog = services.load_catalog
    load_member_skills_from_memory = services.load_member_skills_from_memory
    load_selected_rule_members = services.load_selected_rule_members
    native_background_click = services.native_background_click
    native_silent_click = services.native_silent_click
    native_silent_click_burst = services.native_silent_click_burst
    native_wake_game = services.native_wake_game
    normal_load_verified = services.normal_load_verified
    np = services.np
    os = services.os
    post_click = services.post_click
    post_key_to_game = services.post_key_to_game
    print_window_mat = services.print_window_mat
    process_executable = services.process_executable
    process_is_alive = services.process_is_alive
    process_windows = services.process_windows
    read_equipment_records = services.read_equipment_records
    read_job_ids = services.read_job_ids
    read_job_talents = services.read_job_talents
    read_personnel = services.read_personnel
    render_member_text_panel = services.render_member_text_panel
    required_data_collection = services.required_data_collection
    rule_member_indices = services.rule_member_indices
    run_native_control = services.run_native_control
    shutil = services.shutil
    skill_result_detail = services.skill_result_detail
    time = services.time
    title_load_verified = services.title_load_verified
    trigger_random_choice_click = services.trigger_random_choice_click
    trigger_seven_member_story = services.trigger_seven_member_story
    user32 = services.user32
    validate_personnel_identity = services.validate_personnel_identity
    validate_profile_members = services.validate_profile_members
    wait_for_seven_member_scene = services.wait_for_seven_member_scene
    window_text = services.window_text
    wintypes = services.wintypes
    from window.BaseWindow import BaseWindow
    from window.CczWindow import CczPeopleWindow

    if not hasattr(task_module.CczReRandTask, "_ccz_original_check_r0"):
        task_module.CczReRandTask._ccz_original_check_r0 = (
            task_module.CczReRandTask.checkPeopleAtR0
        )
        task_module.CczReRandTask._ccz_original_version_check = (
            task_module.CczReRandTask.checkCczVersion
        )
        task_module.CczReRandTask._ccz_original_load_and_confirm = (
            task_module.CczReRandTask.loadAndConfirm
        )
        task_module.CczReRandTask._ccz_original_save_and_confirm = (
            task_module.CczReRandTask.saveAndConfirm
        )
    if not hasattr(BaseWindow, "_ccz_original_get_mat"):
        BaseWindow._ccz_original_get_mat = BaseWindow.getMat
    original_check = task_module.CczReRandTask._ccz_original_check_r0
    original_version_check = (
        task_module.CczReRandTask._ccz_original_version_check
    )
    original_save_and_confirm = (
        task_module.CczReRandTask._ccz_original_save_and_confirm
    )
    original_get_mat = BaseWindow._ccz_original_get_mat
    rules = rules or default_rule_config()
    game_path = (
        game_executable.resolve()
        if game_executable is not None
        else process_executable(pid)
    )
    if game_path is None:
        raise RuntimeError("无法定位游戏目录")
    source_save = game_path.parent / "SV" / "SV020.E5S"
    source_save_bytes = source_save.read_bytes()
    source_memory = source_save_bytes[:R0_MEMORY_SIZE]
    from ccz_randomizer.runtime.random_interaction import RandomInteractionSession
    interactions = RandomInteractionSession(services, pid, turbo_enabled=os.environ.get("CCZ_TURBO_MODE") == "1")

    def get_hwnd_by_name(self, window_name: str) -> None:
        self._BaseWindow__hwnd = find_process_window(pid, window_name)

    def set_foreground(self) -> None:
        return None

    def silent_click_rect(
        self, x: int, y: int, w: int, h: int, rightClick: bool = False
    ) -> None:
        if not self.hwnd or not user32.IsWindow(self.hwnd):
            return
        point = Point(x + w // 2, y + h // 2)
        user32.ClientToScreen(self.hwnd, ctypes.byref(point))
        post_click(
            self.hwnd,
            point.x,
            point.y,
            right=rightClick,
        )

    def silent_move_mouse_to_end(self) -> None:
        return None

    def robust_get_mat(
        self,
        x: int = 0,
        y: int = 0,
        w: int = 0,
        h: int = 0,
        toGray: bool = False,
    ):
        def print_window(flags: int):
            return print_window_mat(
                self.hwnd,
                x,
                y,
                w,
                h,
                strip_client=False,
                flags=flags,
            )

        def wake() -> None:
            current_main = find_process_window_by_class(pid, "SOUSOU")
            if current_main:
                native_wake_game(pid, current_main, 400)

        try:
            result = capture_window_with_fallbacks(
                print_window=print_window,
                bitblt=lambda: original_get_mat(
                    self, x, y, w, h, False
                ),
                wake=wake,
                is_usable=lambda mat, require_variance: bool(
                    mat is not None
                    and getattr(mat, "size", 0)
                    and (
                        not require_variance
                        or float(np.std(mat)) > 1
                    )
                ),
                sleep_after_wake=lambda: interruptible_sleep(0.08),
            )
        except WindowCaptureError as exc:
            diagnostic_log(
                "window_capture_unavailable",
                pid=pid,
                hwnd=self.hwnd,
                region=[x, y, w, h],
                errors=exc.errors,
            )
            raise WindowCaptureUnavailable(
                "后台能力窗口截图暂时不可用"
            ) from exc
        if result.recovered:
            diagnostic_log(
                "window_capture_recovered",
                pid=pid,
                hwnd=self.hwnd,
                method=result.method,
                previous_errors=result.previous_errors,
            )
        if toGray:
            task_module.CvUtils.transNotBlackToWhite(result.image, 100)
        return result.image

    def click_relative_hwnd(
        hwnd: int, x: int, y: int, w: int, h: int, count: int = 1
    ) -> None:
        rect = wintypes.RECT()
        if not hwnd or not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return
        post_click(
            hwnd,
            rect.left + x + w // 2,
            rect.top + y + h // 2,
            count=count,
        )

    def robust_load_and_confirm(self, index: int) -> None:
        check_stop_requested()
        if not getattr(self, "wind", None):
            self.initWind()
        game = self.wind.hwnd if getattr(self, "wind", None) else 0
        if not game:
            raise RuntimeError("读档前未找到游戏主窗口")
        drive_game_menu_load(
            pid=pid,
            game=game,
            save_path=(
                game_path.parent / "SV" / f"SV{index:03}.E5S"
            ),
            slot=index,
            **interactions.menu_load_options(),
        )

    def menu_save_and_confirm(self, index: int) -> None:
        check_stop_requested()
        ensure_game_menu_ready(self)
        game = self.wind.hwnd if getattr(self, "wind", None) else 0
        if not game:
            raise RuntimeError("存档前未找到游戏主窗口")

        target_path = game_path.parent / "SV" / f"SV{index:03}.E5S"
        drive_game_menu_save(
            pid=pid,
            game=game,
            target_path=target_path,
            slot=index,
        )

    def fast_check_people_at_r0(self) -> bool:
        check_stop_requested()
        positions = (
            JOB_POSITIONS_R0 if three_person_mode else JOB_POSITIONS_R1
        )
        members = (
            INITIAL_TEAM_MEMBERS if three_person_mode else TEAM_MEMBERS
        )
        ids = read_job_ids(pid, positions)
        initial_ids = ids
        if three_person_mode:
            from ccz_randomizer.runtime.personnel_memory import read_rule_job_ids
            selected = rules["profiles"][rules["activeProfile"]]["threePerson"]["qualifiedMembers"]
            ids, members = expand_rule_members(
                ids, members, selected, lambda positions: read_rule_job_ids(pid, positions),
            )
        if any(job_id not in JOB_MAP for job_id in ids):
            print(f"内存快筛遇到未收录兵种编号 {ids}，本轮放弃")
            return False

        summaries = []
        jobs = []
        member_rules = []
        runtime_members = {
            member.name: member
            for member in task_module.TEAM_MEMBER_LIST
        }
        for job_id, member in zip(ids, members):
            name, score, job_type = JOB_MAP[job_id]
            member_name, primary_type, secondary_type = member
            runtime_member = runtime_members.get(member_name)
            if runtime_member is not None:
                runtime_member.job = SimpleNamespace(
                    name=name,
                    score=score,
                    type=job_type,
                )
            jobs.append({"name": name, "score": score, "type": job_type})
            member_rules.append(
                {
                    "name": member_name,
                    "primaryType": primary_type,
                    "secondaryType": secondary_type,
                }
            )
            summaries.append(f"{member_name}:{name}")

        evaluation = evaluate_job_rules(
            rules,
            "three" if three_person_mode else "seven",
            jobs,
            member_rules,
        )
        average = evaluation.metrics["qualificationAverage"]
        success = (
            os.environ.get("CCZ_TEST_ACCEPT_FIRST") == "1"
            or evaluation.qualified
        )
        self._r0_job_ids = initial_ids
        self._r0_average = average
        self._r0_rule_reasons = evaluation.reasons
        self._job_evaluation_detail, summaries = job_rule_report(
            evaluation, jobs, members, qualified=success,
        )
        self._r0_summaries = summaries
        print(
            f"R0 {'三人' if three_person_mode else '七人'}兵种筛选: "
            + "; ".join(summaries)
            + "; 结果="
            + ("通过" if success else "未通过")
        )
        diagnostic_log(
            "job_rule_evaluation",
            mode="three" if three_person_mode else "seven",
            qualified=success,
            reasons=evaluation.reasons,
            metrics=evaluation.metrics,
        )
        if not success and evaluation.reasons:
            print("规则原因: " + "；".join(evaluation.reasons))
        return success

    def collect_equipment(self):
        check_stop_requested()
        records = read_equipment_records(pid)
        equip_info, effects = decode_equipment_records(records)
        self._equip_info = equip_info
        self._equip_effects = effects
        self._equip_specials = build_equipment_specials(effects)
        equip_count = sum(len(items) for items, _type_name in equip_info)
        print(
            f"宝物内存读取完成：{len(equip_info)} 类，共 {equip_count} 件，"
            "未打开宝物图鉴"
        )
        return equip_info

    def verified_start_rand(self) -> bool:
        check_stop_requested()
        self.initWind()
        if not self.wind.isInitSuccess():
            print("随机前游戏窗口初始化失败")
            return False
        before = read_job_ids(pid, JOB_POSITIONS_R1)
        left, top, _right, _bottom = self.wind.getRect()
        npc_x = left + 356 + 16
        npc_y = top + 251 + 29
        choice_x = left + 240 + 130
        choice_y = top + 255 + 9

        for attempt in range(3):
            check_stop_requested()
            print(f"后台随机尝试 {attempt + 1}/3")
            native_wake_game(pid, self.wind.hwnd, 800)
            post_click(
                self.wind.hwnd,
                npc_x,
                npc_y,
                count=1 if attempt == 0 else 2,
            )
            native_wake_game(pid, self.wind.hwnd, 900)
            post_click(
                self.wind.hwnd,
                choice_x,
                choice_y,
                count=1 if attempt < 2 else 2,
            )
            native_wake_game(pid, self.wind.hwnd, 1200)

            deadline = time.perf_counter() + 2
            while time.perf_counter() < deadline:
                check_stop_requested()
                current = read_job_ids(pid, JOB_POSITIONS_R1)
                if current != before and any(current):
                    print(f"随机兵种已更新: {before}->{current}")
                    return True
                interruptible_sleep(0.1)
        print(f"随机操作未改变兵种内存: {before}")
        return False

    def cached_version_check(self) -> bool:
        if getattr(self, "is2_08", None) is not None:
            return True
        return original_version_check(self)

    def direct_open_people(self) -> None:
        check_stop_requested()
        self.initWind()
        for attempt in range(1, 5):
            check_stop_requested()
            self.initPeopleWind()
            if self.peopleWind.isInitSuccess():
                return
            method = "deepest_child_message"
            try:
                if attempt == 1:
                    point = Point(138, 18)
                    user32.ClientToScreen(
                        self.wind.hwnd,
                        ctypes.byref(point),
                    )
                    target, client_x, client_y = deepest_child_at(
                        self.wind.hwnd,
                        point.x,
                        point.y,
                    )
                    lparam = (client_y << 16) | (client_x & 0xFFFF)
                    user32.PostMessageW(
                        target,
                        0x0201,
                        0x0001,
                        lparam,
                    )
                    user32.PostMessageW(target, 0x0202, 0, lparam)
                elif attempt == 2:
                    method = "silent_click"
                    native_silent_click(
                        pid,
                        self.wind.hwnd,
                        138,
                        18,
                        tail_delay_ms=350,
                    )
                elif attempt == 3:
                    method = "silent_burst"
                    native_silent_click_burst(
                        self.wind.hwnd,
                        138,
                        18,
                        2,
                    )
                else:
                    method = "screen_message"
                    point = Point(138, 18)
                    user32.ClientToScreen(
                        self.wind.hwnd,
                        ctypes.byref(point),
                    )
                    post_click(self.wind.hwnd, point.x, point.y)
            except (NativeControlError, NativeControlTimeout) as exc:
                diagnostic_log(
                    "same_session_roster_open_click_failed",
                    pid=pid,
                    attempt=attempt,
                    method=method,
                    error=repr(exc),
                )
                continue
            native_wake_game(pid, self.wind.hwnd, 600)
            diagnostic_log(
                "same_session_roster_open_attempt",
                pid=pid,
                attempt=attempt,
                method=method,
            )
            deadline = time.perf_counter() + 3.0
            while time.perf_counter() < deadline:
                interruptible_sleep(0.15)
                self.initPeopleWind()
                if self.peopleWind.isInitSuccess():
                    return

    def direct_click_people(self, index: int) -> None:
        check_stop_requested()
        main_window = find_process_window_by_class(pid, "SOUSOU")
        for hwnd in process_windows(pid, visible_only=False):
            if window_text(hwnd) == "武将情报":
                close_member_dialog(pid, main_window, hwnd)
        user32.EnableWindow(self.hwnd, True)
        member_names = tuple(
            member.name for member in task_module.TEAM_MEMBER_LIST
        )
        for method in ("list_window_command", "injected_row_click"):
            check_stop_requested()
            try:
                if method == "list_window_command":
                    run_native_control(
                        pid,
                        ["list-window", str(self.hwnd), str(index)],
                    )
                else:
                    native_background_click(
                        self.hwnd,
                        54,
                        129 + 60 * index,
                        1,
                        False,
                    )
            except (NativeControlError, NativeControlTimeout) as exc:
                diagnostic_log(
                    "same_session_member_row_click_failed",
                    pid=pid,
                    index=index,
                    method=method,
                    error=repr(exc),
                )
                continue
            if main_window:
                native_wake_game(pid, main_window, 800)
            deadline = time.perf_counter() + 4.0
            while time.perf_counter() < deadline:
                check_stop_requested()
                info_hwnd, shown_name = find_any_member_dialog(
                    pid,
                    member_names,
                )
                if info_hwnd:
                    diagnostic_log(
                        "same_session_member_dialog_opened",
                        pid=pid,
                        index=index,
                        member=shown_name,
                        method=method,
                        info_hwnd=info_hwnd,
                    )
                    return
                interruptible_sleep(0.1)
            diagnostic_log(
                "same_session_member_row_no_dialog",
                pid=pid,
                index=index,
                method=method,
            )
        raise RuntimeError(
            f"同一游戏实例未能打开第 {index + 1} 个武将能力窗口"
        )

    def inspect_current_seven_members(self) -> dict:
        check_stop_requested()
        main_window = find_process_window_by_class(pid, "SOUSOU")
        if not main_window:
            raise RuntimeError("同一游戏实例检查前未找到游戏主窗口")
        # Advancing to the seven-member scene consumes this session. The
        # source scene cannot be restored reliably through an in-game load.
        self._session_consumed = True
        trigger_seven_member_story(
            self,
            pid,
            main_window,
            click_strategy="same_session",
        )
        check_stop_requested()
        accelerated = wait_for_seven_member_scene(pid)
        diagnostic_log(
            "same_session_accelerated_story_result",
            pid=pid,
            ready=accelerated,
            timeout_seconds=3.2,
        )
        if not accelerated and not advance_seven_member_story(
            pid, main_window
        ):
            return {"completed": False}
        check_stop_requested()
        job_ids = read_job_ids(pid, JOB_POSITIONS_R1)
        for member, job_id in zip(task_module.TEAM_MEMBER_LIST, job_ids):
            job_name, score, job_type = JOB_MAP[job_id]
            member.job = SimpleNamespace(
                name=job_name,
                score=score,
                type=job_type,
            )
        load_member_skills_from_memory(
            task_module,
            pid,
            JOB_POSITIONS_R1,
            task_module.TEAM_MEMBER_LIST,
        )
        check_stop_requested()
        ordered_panels = tuple(
            render_member_text_panel(
                member.name,
                member.job.name,
                member.skillList,
            )
            for member in task_module.TEAM_MEMBER_LIST
        )
        self.teamJobAndSkillInfoMat = np.vstack(ordered_panels)

        evaluation = evaluate_task_skill_rules(
            rules,
            task_module,
            task_module.TEAM_MEMBER_LIST,
            self._r0_average,
        )
        forced_accept = (
            os.environ.get("CCZ_TEST_ACCEPT_FIRST") == "1"
            and not evaluation.qualified
        )
        result = {
            "completed": True,
            "qualified": forced_accept or evaluation.qualified,
            "reasons": [] if forced_accept else list(evaluation.reasons),
            "job_names": [JOB_MAP[job_id][0] for job_id in job_ids],
            "skills": [
                [skill.name for skill in member.skillList]
                for member in task_module.TEAM_MEMBER_LIST
            ],
            "panels": ordered_panels,
            "metrics": evaluation.metrics,
            "skill_detail": skill_result_detail(
                evaluation,
                task_module.TEAM_MEMBER_LIST,
            ),
        }
        if forced_accept:
            result["skill_detail"]["qualified"] = True
            result["skill_detail"]["reasons"] = []
        diagnostic_log(
            "same_session_seven_member_memory_inspection_completed",
            pid=pid,
            qualified=result["qualified"],
            job_names=result["job_names"],
            skills=result["skills"],
            panel_count=len(result["panels"]),
        )
        return result

    def r0_only_run(self) -> bool:
        check_stop_requested()
        print(f"{self.name} 原生随机内存快筛流程 start")
        self._game_version = current_game_version()
        validate_profile_members(active_profile(rules), self._game_version)
        self._three_person_mode = three_person_mode
        self._normal_load_succeeded = False
        self._result_outcome = ""
        self._data_collection = required_data_collection(active_profile(rules))
        self._result_save_committed = False
        self._result_save_path = None
        self._result_save_verification_warning = ""
        self._job_evaluation_detail = None
        self._skill_evaluation_detail = None
        self._scored_members = None
        self._result_image_settings = active_profile(rules).get("resultImage", {"mode": "selected", "members": []})
        self._equip_info = None
        self._equip_specials = ()
        self._personnel_snapshot = None
        self._fixed_personnel_snapshot = None
        self._job_talents_snapshot = None
        diagnostic_log(
            "random_run_start",
            pid=pid,
            target_slot=getattr(self, "_target_save_pos", None),
            source_loaded=bool(getattr(self, "_source_loaded", False)),
            random_mode="three" if three_person_mode else "seven",
        )
        self.savePos = getattr(
            self,
            "_target_save_pos",
            int(os.environ.get("CCZ_OUTPUT_SLOT", "1")),
        )
        if not 1 <= self.savePos <= 15:
            raise ValueError("结果存档槽位只能是第 1–15 号")

        def save_qualified_result(
            *,
            candidate_save: bytes | None = None,
        ) -> None:
            target_path = (
                game_path.parent / "SV" / f"SV{self.savePos:03}.E5S"
            )
            with critical_random_operation("qualified-result-save"):
                (
                    previous_signature,
                    saved_signature,
                    save_method,
                ) = commit_qualified_result_save(
                    self,
                    self.savePos,
                    target_path,
                    candidate_save=candidate_save,
                )
            diagnostic_log(
                "game_menu_save_confirmed",
                result_slot=self.savePos,
                save_path=target_path,
                previous_signature=previous_signature,
                saved_signature=saved_signature,
                save_method=save_method,
            )
            self._result_save_committed = True
            self._result_save_path = target_path
            print(
                f"第 {self.savePos} 号结果存档已通过游戏菜单保存"
            )

        self.is2_08 = None
        game = find_process_window_by_class(pid, "SOUSOU")
        if not game:
            raise RuntimeError("未找到游戏主窗口")

        load_started = time.perf_counter()
        reused_session = bool(getattr(self, "_source_loaded", False))
        if reused_session:
            load_mode = "normal"
            diagnostic_log("source_load_start", pid=pid, mode=load_mode)
            normal_load_verified(
                pid,
                game,
                SOURCE_SAVE_NUMBER,
                source_save,
                self.loadAndConfirm,
            )
            check_stop_requested()
            self._normal_load_succeeded = True
            scene_ready_delay = 1.0
        else:
            load_mode = "title"
            diagnostic_log("source_load_start", pid=pid, mode=load_mode)
            if not title_load_verified(
                pid, SOURCE_TITLE_LIST_INDEX, source_save
            ):
                diagnostic_log(
                    "source_load_failed",
                    pid=pid,
                    mode="title",
                )
                raise RuntimeError(
                    "第 20 号源存档读取失败，已停止本次随机；"
                    "请将普通日志和诊断日志一起发回"
                )
            check_stop_requested()
            self._source_loaded = True
            scene_ready_delay = 1.5

        active_positions = (
            JOB_POSITIONS_R0 if three_person_mode else JOB_POSITIONS_R1
        )
        load_deadline = time.perf_counter() + 8
        before = ()
        while time.perf_counter() < load_deadline:
            check_stop_requested()
            before = read_job_ids(pid, active_positions)
            if before == (0,) * len(active_positions):
                break
            interruptible_sleep(0.1)
        else:
            diagnostic_log(
                "source_jobs_invalid",
                pid=pid,
                jobs=before,
            )
            raise RuntimeError(
                f"第 {SOURCE_SAVE_NUMBER} 号存档已经包含随机结果，"
                "不能作为源存档。\n"
                "请重新准备存档：完成许子将配置后，"
                "在与许子将对话并选择第一个选项之前，"
                f"将存档保存到第 {SOURCE_SAVE_NUMBER} 栏，然后重新运行工具。"
            )
        diagnostic_log(
            "source_ready",
            pid=pid,
            hwnd=game,
            jobs=before,
            elapsed_ms=round(
                (time.perf_counter() - load_started) * 1000
            ),
            scene_ready_delay_ms=round(scene_ready_delay * 1000),
            window_valid=bool(user32.IsWindow(game)),
            load_mode=load_mode,
            reused_session=reused_session,
            state=game_state_diagnostic(
                pid,
                game,
                jobs=before,
                source_memory=source_memory,
            ),
        )
        acceleration_method = enable_game_acceleration(pid)
        check_stop_requested()
        diagnostic_log(
            "randomization_acceleration_enabled",
            pid=pid,
            key="z",
            method=acceleration_method,
            load_mode=load_mode,
            reused_session=reused_session,
        )
        interruptible_sleep(interactions.scene_delay(scene_ready_delay))

        if is_enhanced_game_version(self._game_version):
            validate_personnel_identity(pid, rule_member_indices(self._game_version))

        current = before
        interaction_limit = 3
        for interaction_attempt in range(1, interaction_limit + 1):
            check_stop_requested()
            interaction = interactions.for_attempt(interaction_attempt)
            interaction_started = time.perf_counter()
            diagnostic_log(
                "interaction_start",
                pid=pid,
                hwnd=game,
                attempt=interaction_attempt,
                before_jobs=before,
                window_valid=bool(user32.IsWindow(game)),
                load_mode=load_mode,
                reused_session=reused_session,
                geometry=click_geometry_diagnostic(game),
                state=game_state_diagnostic(
                    pid,
                    game,
                    jobs=before,
                    source_memory=source_memory,
                ),
            )
            npc_click_started = time.perf_counter()
            try:
                interaction.click_npc(game, XU_CLIENT_POSITION, interaction_attempt)
            except NativeControlError as exc:
                if reused_session:
                    diagnostic_log(
                        "normal_reload_native_control_failed",
                        pid=pid,
                        hwnd=game,
                        return_code=exc.return_code,
                        error=repr(exc),
                    )
                    raise NormalReloadUnsupported(
                        "正常读档后，后台交互组件未能继续响应"
                    ) from exc
                raise
            interaction.settle_npc()
            after_npc = read_job_ids(pid, active_positions)
            diagnostic_log(
                "interaction_npc_clicked",
                pid=pid,
                attempt=interaction_attempt,
                jobs=after_npc,
                elapsed_ms=round(
                    (time.perf_counter() - npc_click_started) * 1000
                ),
                window_valid=bool(user32.IsWindow(game)),
                load_mode=load_mode,
                reused_session=reused_session,
                geometry=click_geometry_diagnostic(game),
                state=game_state_diagnostic(
                    pid,
                    game,
                    jobs=after_npc,
                    source_memory=source_memory,
                ),
            )
            choice_click_started = time.perf_counter()
            current = interaction.select_choice(
                game,
                active_positions,
                before,
                interaction_attempt,
            )
            check_stop_requested()
            diagnostic_log(
                "interaction_choice_clicked",
                pid=pid,
                attempt=interaction_attempt,
                jobs=current,
                elapsed_ms=round(
                    (time.perf_counter() - choice_click_started) * 1000
                ),
                load_mode=load_mode,
                reused_session=reused_session,
                geometry=click_geometry_diagnostic(game),
            )
            current = interaction.wait_for_result(active_positions, before, current)
            if current != before and any(current):
                diagnostic_log(
                    "interaction_succeeded",
                    pid=pid,
                    attempt=interaction_attempt,
                    jobs=current,
                    elapsed_ms=round(
                        (time.perf_counter() - interaction_started) * 1000
                    ),
                )
                break
            diagnostic_log(
                "interaction_no_change",
                pid=pid,
                attempt=interaction_attempt,
                jobs=current,
                elapsed_ms=round(
                    (time.perf_counter() - interaction_started) * 1000
                ),
                process_alive=process_is_alive(pid),
                window_valid=bool(user32.IsWindow(game)),
                load_mode=load_mode,
                reused_session=reused_session,
                state=game_state_diagnostic(
                    pid,
                    game,
                    jobs=current,
                    source_memory=source_memory,
                ),
            )
            interactions.on_no_change(interaction, scene_ready_delay)
            if interaction_attempt < interaction_limit:
                print(
                    "许子将后台交互未触发随机，"
                    f"重试 {interaction_attempt}/{interaction_limit}"
                )
                native_wake_game(pid, game, 900)
            else:
                print("许子将后台交互未触发随机，正在记录现场")
        else:
            failure_state = game_state_diagnostic(
                pid,
                game,
                jobs=current,
                source_memory=source_memory,
            )
            failure_type = interaction_failure_type(
                pid,
                failure_state,
                load_mode=load_mode,
                reused_session=reused_session,
            )
            failure_capture = capture_interaction_failure(
                pid,
                game,
                failure_type,
            )
            diagnostic_log(
                "interaction_failed",
                pid=pid,
                before_jobs=before,
                final_jobs=current,
                load_mode=load_mode,
                reused_session=reused_session,
                geometry=click_geometry_diagnostic(game),
                state=failure_state,
                error_type=failure_type,
                screenshot=failure_capture,
            )
            raise InteractionNotTriggered(
                f"连续 {interaction_limit} 次点击许子将并选择第一项后，"
                f"{'初始三人' if three_person_mode else '七人'}"
                "兵种内存仍未发生变化"
            )
        print(f"游戏原生随机已触发: {before}->{current}")
        check_stop_requested()
        self._r0_initial_three = read_job_ids(pid, JOB_POSITIONS_R0)
        if (current_game_version() in VALID_GAME_VERSIONS
                and self._data_collection.get("jobTalents", False)):
            # Capture the complete job catalog immediately after the roll so
            # failed score attempts can open the same detail entry.
            self._job_talents_snapshot = read_job_talents(pid)

        if not self.checkPeopleAtR0():
            diagnostic_log(
                "job_filter_rejected",
                pid=pid,
                jobs=current,
            )
            self._result_outcome = "job_failed"
            print("用户进度: 本轮最终结果=兵种不合格")
            return False
        diagnostic_log("job_filter_accepted", pid=pid, jobs=current)

        if three_person_mode:
            check_stop_requested()
            print("所选人物兵种筛选通过，正在检查特技条件")
            members = load_selected_rule_members(task_module, pid, rules)
            check_stop_requested()
            evaluation = evaluate_task_skill_rules(
                rules,
                task_module,
                members,
                self._r0_average,
            )
            self._scored_members = members
            self._skill_evaluation_detail = skill_result_detail(
                evaluation,
                members,
            )
            diagnostic_log(
                "selected_skill_rule_evaluation",
                qualified=evaluation.qualified,
                reasons=evaluation.reasons,
                skills={
                    member.name: [
                        skill.name for skill in member.skillList
                    ]
                    for member in members
                },
                metrics=evaluation.metrics,
            )
            if not evaluation.qualified:
                self._result_outcome = "skill_failed"
                if evaluation.reasons:
                    print("规则原因: " + "；".join(evaluation.reasons))
                print("用户进度: 本轮最终结果=特技不合格")
                return False
            panels, initial_members = capture_initial_member_panels(task_module, pid, game, self)
            self._job_names = tuple(JOB_MAP[job_id][0] for job_id in self._r0_job_ids)
            self._member_panels = panels
            self._team_members = initial_members
            self.teamJobAndSkillInfoMat = np.vstack(panels)
            print("R1 特技界面筛选: 通过")
        else:
            check_stop_requested()
            scratch_slot = 16
            scratch_guard = ScratchSaveGuard(game_path.parent)
            scratch_guard.prepare()
            scratch_guard.begin()
            inspection_dir = None
            try:
                self.saveAndConfirm(scratch_slot)
                check_stop_requested()
                candidate_path = scratch_guard.target
                if not candidate_path.is_file():
                    raise RuntimeError("游戏菜单保存后未找到候选存档")
                candidate_save = candidate_path.read_bytes()
                if not candidate_save:
                    raise RuntimeError("游戏菜单保存的候选存档为空")
                diagnostic_log(
                    "seven_member_candidate_save_captured",
                    save_path=candidate_path,
                    size=len(candidate_save),
                    sha256=hashlib.sha256(candidate_save).hexdigest(),
                )
                print("候选存档已通过游戏菜单保存")

                inspection = inspect_current_seven_members(self)
                check_stop_requested()
                if not inspection.get("completed", True):
                    self._result_outcome = "inspection_abandoned"
                    diagnostic_log(
                        "seven_member_attempt_abandoned",
                        pid=pid,
                        reason="story_scene_not_ready",
                    )
                    return False
                self._job_names = tuple(inspection["job_names"])
                self._member_panels = tuple(inspection["panels"])
                self._team_members = task_module.TEAM_MEMBER_LIST
                self._skill_evaluation_detail = inspection["skill_detail"]
                if not inspection["qualified"]:
                    self._result_outcome = "skill_failed"
                    reasons = inspection.get("reasons", [])
                    if reasons:
                        print("规则原因: " + "；".join(reasons))
                    print("用户进度: 本轮最终结果=特技不合格")
                    return False
                self._result_outcome = "accepted"
                print("用户进度: 本轮最终结果=合格，开始保存")
                save_qualified_result(candidate_save=candidate_save)
            finally:
                if inspection_dir is not None:
                    shutil.rmtree(inspection_dir, ignore_errors=True)
                scratch_guard.restore()

        if three_person_mode:
            self._result_outcome = "accepted"
            print("用户进度: 本轮最终结果=合格，开始保存")
            save_qualified_result()
            if (current_game_version() in VALID_GAME_VERSIONS
                    and self._data_collection.get("recruitment", False)):
                catalog = load_catalog()
                self._personnel_snapshot = attach_recruitment(read_personnel(
                    pid, [person["recordIndex"] for person in catalog], planned=True,
                    fixed_indices=[person["recordIndex"] for person in catalog if person["fixedConfiguration"]],
                ), catalog)
                self._fixed_personnel_snapshot = attach_fixed_entries(read_personnel(
                    pid, fixed_member_indices().values(), planned=True,
                ))
                for row in self._personnel_snapshot + self._fixed_personnel_snapshot:
                    if row["jobId"] in JOB_MAP:
                        row["job"] = JOB_MAP[row["jobId"]][0]
        return True

    BaseWindow.setForeground = set_foreground
    BaseWindow._BaseWindow__getHwndbyName = get_hwnd_by_name
    BaseWindow.clickRect = silent_click_rect
    BaseWindow.moveMouseToEnd = silent_move_mouse_to_end
    BaseWindow.getMat = robust_get_mat
    CczPeopleWindow.clickPeople = direct_click_people
    task_module.KeyboardUtils.tapKey = lambda key: post_key_to_game(pid, key)
    task_module.CczReRandTask.checkPeopleAtR0 = fast_check_people_at_r0
    # The legacy 0x6800 hypothesis has not matched UI-recognized skills.
    # Keep the proven UI inspection path until evidence establishes a mapping.
    task_module.CczReRandTask.collect_equipment = collect_equipment
    task_module.CczReRandTask.startRand = verified_start_rand
    task_module.CczReRandTask.checkCczVersion = cached_version_check
    task_module.CczReRandTask.openPeople = direct_open_people
    task_module.CczReRandTask.loadAndConfirm = robust_load_and_confirm
    task_module.CczReRandTask.saveAndConfirm = menu_save_and_confirm
    task_module.CczReRandTask.run = r0_only_run

