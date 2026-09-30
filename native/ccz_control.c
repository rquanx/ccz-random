#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <commctrl.h>
#include <oleacc.h>
#include <dwmapi.h>
#include <tlhelp32.h>
#include <intrin.h>
#include <limits.h>
#include <string.h>
#include <stdio.h>

#pragma comment(linker, "/EXPORT:ControlAction=_ControlAction@4")
#pragma comment(lib, "dwmapi.lib")
#pragma comment(lib, "oleacc.lib")
#pragma comment(lib, "oleaut32.lib")

enum {
    ACTION_LIST_ITEM = 1,
    ACTION_CLICK = 2,
    ACTION_GUARD = 3,
    ACTION_WAKE = 4,
    ACTION_DIRECT_LOAD = 5,
    ACTION_DIRECT_SAVE = 6,
    ACTION_LOAD_DIALOG_ITEM = 7,
    ACTION_CLOSE_LIST_DIALOG = 8,
    ACTION_STATUS = 9,
    ACTION_WNDPROC = 10,
    ACTION_TRACE_RANDOM_WRITE = 11,
    ACTION_NOTIFY_LIST_ITEM = 12,
    ACTION_REAL_LIST_ITEM = 13,
    ACTION_TRACE_DIALOG_CREATE = 14,
    ACTION_OPEN_LOAD_DIALOG = 15,
    ACTION_TRACE_LOAD_CALL = 16,
    ACTION_TRACE_ADDRESS = 17,
    ACTION_REAL_RANDOM = 18,
    ACTION_CONFIRM_SELECTION = 19,
    ACTION_GAME_MOUSE = 20,
    ACTION_GAME_FRAME_CLICK = 21,
    ACTION_SILENT_CLICK = 22,
    ACTION_DUMP_LIST = 23,
    ACTION_DIALOG_DBLCLICK = 24,
    ACTION_REAL_LOAD = 25,
    ACTION_DIALOG_ENTER = 26,
    ACTION_DIALOG_NOTIFY = 27,
    ACTION_DIALOG_WINDOW = 28,
    ACTION_DIALOG_ACCESSIBLE = 29,
    ACTION_GAME_TICK = 30,
    ACTION_PROCESS_LOAD_STATE = 31,
    ACTION_DISPATCH_LOAD_STATE = 32,
    ACTION_MARK_LOAD_READY = 33,
    ACTION_DUMP_CONTEXTS = 34,
    ACTION_MAIN_LOOP_LOAD = 35,
    ACTION_START_GAME_LOOP = 36,
    ACTION_TITLE_LOAD = 37,
    ACTION_PULSE_CLICK = 38,
    ACTION_ARM_FIRST_CHOICE = 39,
    ACTION_PULSE_BURST = 40,
    ACTION_SILENT_CLICK_BURST = 41,
    ACTION_LIST_WINDOW_ITEM = 42,
    ACTION_END_DIALOG = 43,
    ACTION_MUTE_AUDIO = 44,
    ACTION_TIMED_SILENT_CLICK = 45,
    ACTION_TIMED_SILENT_CLICK_BURST = 46,
    ACTION_ENABLE_ACCELERATION = 47
};

typedef struct ControlRequest {
    int action;
    DWORD window;
    int x;
    int y;
    int count;
    int right;
    int item_index;
} ControlRequest;

typedef struct InlineHook {
    BYTE *target;
    BYTE original[5];
    BOOL installed;
} InlineHook;

static POINT synthetic_cursor;
static HWND synthetic_root = NULL;
static HWND synthetic_focus = NULL;
static volatile LONG synthetic_left_down = 0;
static volatile LONG synthetic_right_down = 0;
static volatile LONG input_hook_update_lock = 0;
static InlineHook key_state_hook;
static InlineHook async_key_state_hook;
static InlineHook cursor_pos_hook;
static InlineHook set_cursor_pos_hook;
static InlineHook message_pos_hook;
static InlineHook get_foreground_window_hook;
static InlineHook get_active_window_hook;
static InlineHook get_focus_hook;
static InlineHook foreground_window_hook;
static InlineHook bring_window_to_top_hook;
static InlineHook show_window_hook;
static InlineHook create_window_ex_hook;
static InlineHook create_window_ex_a_hook;
static InlineHook dialog_box_param_a_hook;
static InlineHook create_dialog_indirect_param_a_hook;
static InlineHook peek_message_hook;
static InlineHook game_mouse_action_hook;
static InlineHook first_choice_hook;
static volatile LONG guard_started = 0;
static volatile LONG guard_tick = 0;
static HWND guarded_foreground = NULL;
static volatile LONG allow_game_foreground = 0;
static volatile LONG game_on_hidden_desktop = -1;
static WNDPROC original_game_wndproc = NULL;
static volatile LONG game_call_completed = 0;
static volatile DWORD game_call_result = 0;
static void *dialog_object_to_load = NULL;
static int dialog_item_to_load = 0;
static HWND load_dialog_to_confirm = NULL;
static HWND confirm_dialog_target = NULL;
static WNDPROC confirm_original_wndproc = NULL;
static PVOID random_trace_handler = NULL;
static volatile LONG random_trace_hits = 0;
static volatile LONG trace_dialog_create = 0;
static volatile DWORD debug_trace_address = 0x00503F40;
static volatile DWORD debug_trace_kind = 1;
static volatile UINT requested_mouse_message = 0;
static volatile int requested_mouse_x = 0;
static volatile int requested_mouse_y = 0;
static volatile LONG synthetic_game_mouse_action = 0;
static volatile LONG main_loop_hook_installed = 0;
static volatile LONG main_loop_action = 0;
static volatile LONG main_loop_slot = 0;
static volatile DWORD main_loop_result = 0;
static volatile LONG force_first_choice = 0;
static HANDLE main_loop_event = NULL;
static BYTE main_loop_original[5];

typedef struct TemporaryCodePatch {
    BYTE *address;
    BYTE original[16];
    DWORD protection;
    BOOL active;
} TemporaryCodePatch;

#define WM_CCZ_DIRECT_LOAD (WM_APP + 0x4C3)
#define WM_CCZ_DIRECT_SAVE (WM_APP + 0x4C4)
#define WM_CCZ_DIALOG_LOAD (WM_APP + 0x4C5)
#define WM_CCZ_HIDDEN_ACTIVATE (WM_APP + 0x4C6)
#define WM_CCZ_OPEN_LOAD_DIALOG (WM_APP + 0x4C7)
#define WM_CCZ_REAL_RANDOM (WM_APP + 0x4C8)
#define WM_CCZ_CONFIRM_SELECTION (WM_APP + 0x4C9)
#define WM_CCZ_GAME_MOUSE (WM_APP + 0x4CA)
#define WM_CCZ_GAME_FRAME_CLICK (WM_APP + 0x4CB)
#define WM_CCZ_CONFIRM_CLOSE (WM_APP + 0x4CC)
#define WM_CCZ_GAME_TICK (WM_APP + 0x4CD)
#define WM_CCZ_PROCESS_LOAD_STATE (WM_APP + 0x4CE)
#define WM_CCZ_DISPATCH_LOAD_STATE (WM_APP + 0x4CF)
#define WM_CCZ_MARK_LOAD_READY (WM_APP + 0x4D0)
#define WM_CCZ_START_GAME_LOOP (WM_APP + 0x4D1)
#define WM_CCZ_END_DIALOG (WM_APP + 0x4D2)
#define WM_CCZ_ENABLE_ACCELERATION (WM_APP + 0x4D3)
#define GAME_LOAD_FUNCTION_ADDRESS 0x0041888D
#define GAME_LOAD_MODAL_STATE_ADDRESS 0x0040B913
#define GAME_LOAD_CONFIRM_FUNCTION_ADDRESS 0x00418C34
#define GAME_SAVE_FUNCTION_ADDRESS 0x0040531A
#define GAME_DIALOG_LOAD_FUNCTION_ADDRESS 0x0040B84C
#define GAME_RANDOM_JOB_ADDRESS 0x00503F40
#define GAME_MODAL_DIALOG_FUNCTION_ADDRESS 0x0046D098
#define GAME_OPEN_LOAD_FUNCTION_ADDRESS 0x0041933D
#define GAME_EVENT_INPUT_FUNCTION_ADDRESS 0x004298B8
#define GAME_CONFIRM_SELECTION_FUNCTION_ADDRESS 0x00426B52
#define GAME_UPDATE_HOVER_FUNCTION_ADDRESS 0x00429D47
#define GAME_UPDATE_MAP_HOVER_FUNCTION_ADDRESS 0x00429E48
#define GAME_READ_MOUSE_ACTION_FUNCTION_ADDRESS 0x0042C56B
#define GAME_HANDLE_MOUSE_ACTION_FUNCTION_ADDRESS 0x00429B68
#define GAME_FINISH_MOUSE_ACTION_FUNCTION_ADDRESS 0x00426BA0
#define GAME_MOUSE_INPUT_FUNCTION_ADDRESS 0x00426075
#define GAME_MOUSE_INPUT_OBJECT_ADDRESS 0x004B2C50
#define GAME_MOUSE_ACTION_ADDRESS 0x004B0754
#define GAME_PREVIOUS_MOUSE_ACTION_ADDRESS 0x004ABF98
#define GAME_TICK_FUNCTION_ADDRESS 0x0042BF90
#define GAME_LOAD_STATE_DISPATCH_ADDRESS 0x0042C223
#define GAME_LOAD_TRANSITION_ADDRESS 0x0044F058
#define GAME_MAIN_LOOP_HOOK_ADDRESS 0x0042BFB8
#define GAME_MAIN_LOOP_HOOK_RETURN 0x0042BFBD
#define GAME_MAIN_LOOP_FUNCTION_ADDRESS 0x0040E326
#define GAME_TITLE_MOUSE_POSITION_ADDRESS 0x00426727
#define GAME_TITLE_CLICK_TEST_ADDRESS 0x00403659
#define GAME_CHOICE_FINALIZE_ADDRESS 0x0042E11E
#define GAME_CHOICE_FINALIZE_RETURN 0x0042E123
#define GAME_CHOICE_FINALIZE_FUNCTION_ADDRESS 0x0041E5F6
#define GAME_ACCELERATION_TOGGLE_FUNCTION_ADDRESS 0x004250B3
#define GAME_ACCELERATION_ENABLED_ADDRESS 0x004CE7BF

static HWND find_game_window(void);
static HWND find_list_dialog(void);
static DWORD run_list_item(int item_index);
static DWORD dialog_double_click_item(int item_index);
static DWORD real_list_item(int item_index);
static DWORD dialog_notify_double_click(int item_index);
static DWORD run_load_dialog_item(
    int item_index, DWORD dialog_object_hint
);
static DWORD dump_thread_contexts(void);
static DWORD install_main_loop_hook(void);
static DWORD run_main_loop_load(int item_index);
static DWORD run_start_game_loop(void);
static DWORD run_title_load(int item_index);
static DWORD run_pulse_click(int x, int y);
static DWORD arm_first_choice(void);
static DWORD run_pulse_burst(int x, int y, int count);
static DWORD post_silent_click_burst(
    HWND window, int x, int y, int count
);
static DWORD post_silent_click_burst_timed(
    HWND window,
    int x,
    int y,
    int count,
    int down_delay_ms,
    int up_delay_ms
);
static DWORD post_silent_click_timed(
    HWND window, int x, int y, int tail_delay_ms
);
static DWORD activate_list_window_item(HWND dialog, int item_index);

static BOOL patch_return_constant(
    DWORD address,
    DWORD value,
    WORD stack_bytes,
    TemporaryCodePatch *patch
) {
    ZeroMemory(patch, sizeof(*patch));
    patch->address = (BYTE *)(UINT_PTR)address;
    if (!VirtualProtect(
            patch->address,
            sizeof(patch->original),
            PAGE_EXECUTE_READWRITE,
            &patch->protection
        )) {
        return FALSE;
    }
    memcpy(
        patch->original,
        patch->address,
        sizeof(patch->original)
    );
    patch->address[0] = 0xB8;
    *(DWORD *)(patch->address + 1) = value;
    if (stack_bytes == 0) {
        patch->address[5] = 0xC3;
    } else {
        patch->address[5] = 0xC2;
        *(WORD *)(patch->address + 6) = stack_bytes;
    }
    FlushInstructionCache(
        GetCurrentProcess(),
        patch->address,
        sizeof(patch->original)
    );
    patch->active = TRUE;
    return TRUE;
}

static BOOL patch_return_true(
    DWORD address, TemporaryCodePatch *patch
) {
    return patch_return_constant(address, 1, 0x10, patch);
}

static BOOL patch_mouse_coordinates(
    DWORD address,
    DWORD x,
    DWORD y,
    TemporaryCodePatch *patch
) {
    ZeroMemory(patch, sizeof(*patch));
    patch->address = (BYTE *)(UINT_PTR)address;
    if (!VirtualProtect(
            patch->address,
            sizeof(patch->original),
            PAGE_EXECUTE_READWRITE,
            &patch->protection
        )) {
        return FALSE;
    }
    memcpy(
        patch->original,
        patch->address,
        sizeof(patch->original)
    );
    BYTE replacement[16] = {
        0xB8, 0, 0, 0, 0,
        0xBA, 0, 0, 0, 0,
        0xC3,
        0x90, 0x90, 0x90, 0x90, 0x90
    };
    *(DWORD *)(replacement + 1) = x;
    *(DWORD *)(replacement + 6) = y;
    memcpy(patch->address, replacement, sizeof(replacement));
    FlushInstructionCache(
        GetCurrentProcess(),
        patch->address,
        sizeof(patch->original)
    );
    patch->active = TRUE;
    return TRUE;
}

static void restore_code_patch(TemporaryCodePatch *patch) {
    if (!patch->active) {
        return;
    }
    memcpy(
        patch->address,
        patch->original,
        sizeof(patch->original)
    );
    FlushInstructionCache(
        GetCurrentProcess(),
        patch->address,
        sizeof(patch->original)
    );
    DWORD ignored = 0;
    VirtualProtect(
        patch->address,
        sizeof(patch->original),
        patch->protection,
        &ignored
    );
    patch->active = FALSE;
}

__declspec(naked) static void synthetic_read_mouse_action(void) {
    __asm {
        xor eax, eax
        xchg eax, synthetic_game_mouse_action
        ret
    }
}

__declspec(naked) static void force_first_choice_hook(void) {
    __asm {
        mov eax, GAME_CHOICE_FINALIZE_FUNCTION_ADDRESS
        call eax
        cmp force_first_choice, 0
        je choice_done
        mov byte ptr [ebp - 0x0C], 0
        mov force_first_choice, 0
choice_done:
        mov eax, GAME_CHOICE_FINALIZE_RETURN
        jmp eax
    }
}

static void append_control_log(const char *message) {
    char path[MAX_PATH];
    DWORD length = GetTempPathA(sizeof(path), path);
    if (length == 0 || length >= sizeof(path) - 32) {
        return;
    }
    lstrcatA(path, "ccz_real_load.log");
    FILE *file = fopen(path, "a");
    if (file == NULL) {
        return;
    }
    fprintf(file, "%lu %s\n", GetTickCount(), message);
    fclose(file);
}

static LONG record_control_exception(
    PEXCEPTION_POINTERS exception
) {
    char text[512];
    DWORD address = exception != NULL &&
            exception->ExceptionRecord != NULL
        ? (DWORD)(UINT_PTR)exception->ExceptionRecord->ExceptionAddress
        : 0;
    DWORD code = exception != NULL &&
            exception->ExceptionRecord != NULL
        ? exception->ExceptionRecord->ExceptionCode
        : 0;
    if (
        exception != NULL &&
        exception->ContextRecord != NULL
    ) {
        CONTEXT *context = exception->ContextRecord;
        DWORD *stack = (DWORD *)(UINT_PTR)context->Esp;
        DWORD stack0 = 0;
        DWORD stack1 = 0;
        DWORD stack2 = 0;
        __try {
            stack0 = stack[0];
            stack1 = stack[1];
            stack2 = stack[2];
        } __except (EXCEPTION_EXECUTE_HANDLER) {
            stack0 = 0;
            stack1 = 0;
            stack2 = 0;
        }
        sprintf(
            text,
            "control-exception-%08lX-%08lX "
            "eax=%08lX ebx=%08lX ecx=%08lX edx=%08lX "
            "esi=%08lX edi=%08lX ebp=%08lX esp=%08lX "
            "stack=%08lX,%08lX,%08lX",
            code,
            address,
            context->Eax,
            context->Ebx,
            context->Ecx,
            context->Edx,
            context->Esi,
            context->Edi,
            context->Ebp,
            context->Esp,
            stack0,
            stack1,
            stack2
        );
    } else {
        sprintf(
            text,
            "control-exception-%08lX-%08lX",
            code,
            address
        );
    }
    append_control_log(text);
    return EXCEPTION_EXECUTE_HANDLER;
}

static void append_dialog_trace(
    LPCWSTR class_name, LPCWSTR window_name, void *return_address
) {
    WCHAR path[MAX_PATH];
    WCHAR line[1024];
    WCHAR class_buffer[32];
    if (IS_INTRESOURCE(class_name)) {
        wsprintfW(
            class_buffer,
            L"#%u",
            (UINT)(UINT_PTR)class_name
        );
        class_name = class_buffer;
    }
    if (IS_INTRESOURCE(window_name)) {
        window_name = L"<resource>";
    }
    DWORD length = GetModuleFileNameW(NULL, path, ARRAYSIZE(path));
    if (length == 0 || length >= ARRAYSIZE(path)) {
        return;
    }
    WCHAR *separator = wcsrchr(path, L'\\');
    if (separator == NULL) {
        return;
    }
    lstrcpyW(separator + 1, L"ccz_dialog_trace.log");
    int chars = wsprintfW(
        line,
        L"return=%08lX class=%s title=%s\r\n",
        (DWORD)(UINT_PTR)return_address,
        class_name != NULL ? class_name : L"<null>",
        window_name != NULL ? window_name : L"<null>"
    );
    HANDLE file = CreateFileW(
        path,
        FILE_APPEND_DATA,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        NULL,
        OPEN_ALWAYS,
        FILE_ATTRIBUTE_NORMAL,
        NULL
    );
    if (file == INVALID_HANDLE_VALUE) {
        return;
    }
    DWORD bytes = 0;
    WriteFile(
        file,
        line,
        (DWORD)(chars * sizeof(WCHAR)),
        &bytes,
        NULL
    );
    CloseHandle(file);
}

static void append_random_trace(CONTEXT *context) {
    WCHAR path[MAX_PATH];
    WCHAR line[8192];
    DWORD length = GetModuleFileNameW(NULL, path, ARRAYSIZE(path));
    if (length == 0 || length >= ARRAYSIZE(path)) {
        return;
    }
    WCHAR *separator = wcsrchr(path, L'\\');
    if (separator == NULL) {
        return;
    }
    lstrcpyW(separator + 1, L"ccz_random_trace.log");

    int chars = wsprintfW(
        line,
        L"hit=%ld eip=%08lX esp=%08lX ebp=%08lX "
        L"eax=%08lX ebx=%08lX ecx=%08lX edx=%08lX "
        L"esi=%08lX edi=%08lX\r\n",
        InterlockedIncrement(&random_trace_hits),
        context->Eip,
        context->Esp,
        context->Ebp,
        context->Eax,
        context->Ebx,
        context->Ecx,
        context->Edx,
        context->Esi,
        context->Edi
    );
    __try {
        DWORD *stack = (DWORD *)(UINT_PTR)context->Esp;
        chars += wsprintfW(line + chars, L"stack=");
        for (int index = 0; index < 192; ++index) {
            chars += wsprintfW(
                line + chars,
                index == 191 ? L"%08lX\r\n" : L"%08lX ",
                stack[index]
            );
        }
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        chars += wsprintfW(line + chars, L"stack=<unreadable>\r\n");
    }
    __try {
        DWORD *frame = (DWORD *)(UINT_PTR)context->Ebp;
        chars += wsprintfW(line + chars, L"frames=");
        DWORD last_return = 0;
        int printed = 0;
        for (int index = 0; index < 4096 && frame != NULL; ++index) {
            DWORD *previous = (DWORD *)(UINT_PTR)frame[0];
            DWORD return_address = frame[1];
            if (
                return_address != 0x004108C0 &&
                return_address != 0x004106E3 &&
                (
                    return_address != last_return ||
                    printed < 8
                )
            ) {
                chars += wsprintfW(
                    line + chars,
                    L"%08lX:%08lX ",
                    (DWORD)(UINT_PTR)frame,
                    return_address
                );
                last_return = return_address;
                ++printed;
            }
            if (previous <= frame) {
                break;
            }
            frame = previous;
        }
        chars += wsprintfW(line + chars, L"\r\n");
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        chars += wsprintfW(line + chars, L"frames=<unreadable>\r\n");
    }
    HANDLE file = CreateFileW(
        path,
        FILE_APPEND_DATA,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        NULL,
        OPEN_ALWAYS,
        FILE_ATTRIBUTE_NORMAL,
        NULL
    );
    if (file == INVALID_HANDLE_VALUE) {
        return;
    }
    DWORD bytes = 0;
    WriteFile(
        file,
        line,
        (DWORD)(chars * sizeof(WCHAR)),
        &bytes,
        NULL
    );
    CloseHandle(file);
}

static LONG CALLBACK random_trace_exception(
    PEXCEPTION_POINTERS exception
) {
    if (
        exception->ExceptionRecord->ExceptionCode !=
            EXCEPTION_SINGLE_STEP ||
        (exception->ContextRecord->Dr6 & 1) == 0
    ) {
        return EXCEPTION_CONTINUE_SEARCH;
    }
    if (debug_trace_kind == 4) {
        __try {
            DWORD *stack =
                (DWORD *)(UINT_PTR)exception->ContextRecord->Esp;
            if (stack[1] != 1) {
                exception->ContextRecord->Dr6 = 0;
                return EXCEPTION_CONTINUE_EXECUTION;
            }
                } __except (EXCEPTION_EXECUTE_HANDLER) {
        }
    }
    append_random_trace(exception->ContextRecord);
    exception->ContextRecord->Dr6 = 0;
    if (debug_trace_kind == 0) {
        exception->ContextRecord->Dr0 = 0;
        exception->ContextRecord->Dr7 &= ~0x000F0003;
    }
    return EXCEPTION_CONTINUE_EXECUTION;
}

static DWORD enable_debug_trace(DWORD address, DWORD kind) {
    debug_trace_address = address;
    debug_trace_kind = kind;
    if (random_trace_handler == NULL) {
        random_trace_handler = AddVectoredExceptionHandler(
            1, random_trace_exception
        );
        if (random_trace_handler == NULL) {
            return 40;
        }
    }

    HANDLE snapshot = CreateToolhelp32Snapshot(
        TH32CS_SNAPTHREAD, 0
    );
    if (snapshot == INVALID_HANDLE_VALUE) {
        return 41;
    }
    DWORD process_id = GetCurrentProcessId();
    DWORD current_thread = GetCurrentThreadId();
    DWORD updated = 0;
    HWND game_window = find_game_window();
    DWORD game_thread = game_window == NULL
        ? 0
        : GetWindowThreadProcessId(game_window, NULL);
    THREADENTRY32 entry;
    ZeroMemory(&entry, sizeof(entry));
    entry.dwSize = sizeof(entry);
    if (Thread32First(snapshot, &entry)) {
        do {
            if (
                entry.th32OwnerProcessID != process_id ||
                entry.th32ThreadID == current_thread
            ) {
                continue;
            }
            HANDLE thread = OpenThread(
                THREAD_SUSPEND_RESUME |
                    THREAD_GET_CONTEXT |
                    THREAD_SET_CONTEXT,
                FALSE,
                entry.th32ThreadID
            );
            if (thread == NULL) {
                continue;
            }
            if (SuspendThread(thread) != (DWORD)-1) {
                CONTEXT context;
                ZeroMemory(&context, sizeof(context));
                context.ContextFlags = CONTEXT_DEBUG_REGISTERS;
                if (GetThreadContext(thread, &context)) {
                    context.Dr0 = address;
                    context.Dr6 = 0;
                    context.Dr7 &= ~0x000F0003;
                    if (kind == 1) {
                        context.Dr7 |= 0x000D0001;
                    } else if (kind == 2) {
                        context.Dr7 |= 0x00010001;
                    } else if (kind == 3) {
                        context.Dr7 |= 0x00050001;
                    } else {
                        context.Dr7 |= 0x00000001;
                    }
                    if (SetThreadContext(thread, &context)) {
                        updated += entry.th32ThreadID == game_thread
                            ? 1000
                            : 1;
                    }
                }
                ResumeThread(thread);
            }
            CloseHandle(thread);
        } while (Thread32Next(snapshot, &entry));
    }
    CloseHandle(snapshot);
    return updated >= 1000 ? 0 : 42;
}

static DWORD enable_random_trace(void) {
    return enable_debug_trace(GAME_RANDOM_JOB_ADDRESS, 1);
}

static DWORD dump_thread_contexts(void) {
    WCHAR path[MAX_PATH];
    DWORD length = GetTempPathW(ARRAYSIZE(path), path);
    if (length == 0 || length >= ARRAYSIZE(path) - 32) {
        return 110;
    }
    lstrcatW(path, L"ccz_thread_contexts.log");
    FILE *file = _wfopen(path, L"w, ccs=UTF-8");
    if (file == NULL) {
        return 111;
    }
    DWORD process_id = GetCurrentProcessId();
    DWORD current_thread = GetCurrentThreadId();
    HWND game = find_game_window();
    DWORD game_thread = game == NULL
        ? 0
        : GetWindowThreadProcessId(game, NULL);
    HANDLE snapshot = CreateToolhelp32Snapshot(
        TH32CS_SNAPTHREAD, 0
    );
    if (snapshot == INVALID_HANDLE_VALUE) {
        fclose(file);
        return 112;
    }
    THREADENTRY32 entry;
    ZeroMemory(&entry, sizeof(entry));
    entry.dwSize = sizeof(entry);
    if (Thread32First(snapshot, &entry)) {
        do {
            if (entry.th32OwnerProcessID != process_id) {
                continue;
            }
            if (entry.th32ThreadID == current_thread) {
                continue;
            }
            HANDLE thread = OpenThread(
                THREAD_SUSPEND_RESUME |
                    THREAD_GET_CONTEXT |
                    THREAD_QUERY_INFORMATION,
                FALSE,
                entry.th32ThreadID
            );
            if (thread == NULL) {
                continue;
            }
            DWORD suspended = SuspendThread(thread);
            CONTEXT context;
            ZeroMemory(&context, sizeof(context));
            context.ContextFlags = CONTEXT_CONTROL;
            BOOL got = suspended != (DWORD)-1 &&
                GetThreadContext(thread, &context);
            fwprintf(
                file,
                L"tid=%lu game=%d suspend=%lu got=%d "
                L"eip=%08lX esp=%08lX ebp=%08lX\r\n",
                entry.th32ThreadID,
                entry.th32ThreadID == game_thread,
                suspended,
                got,
                got ? context.Eip : 0,
                got ? context.Esp : 0,
                got ? context.Ebp : 0
            );
            if (got) {
                DWORD *stack = (DWORD *)(UINT_PTR)context.Esp;
                fwprintf(file, L"stack=");
                __try {
                    for (int index = 0; index < 24; ++index) {
                        fwprintf(
                            file,
                            index == 23 ? L"%08lX\r\n" : L"%08lX ",
                            stack[index]
                        );
                    }
                } __except (EXCEPTION_EXECUTE_HANDLER) {
                    fwprintf(file, L"<unreadable>\r\n");
                }
                fwprintf(file, L"game-returns=");
                __try {
                    int found = 0;
                    for (int index = 0; index < 512; ++index) {
                        DWORD value = stack[index];
                        if (
                            value >= 0x00401000 &&
                            value < 0x00560000
                        ) {
                            fwprintf(
                                file,
                                L"%d:%08lX ",
                                index,
                                value
                            );
                            if (++found >= 48) {
                                break;
                            }
                        }
                    }
                    fwprintf(file, L"\r\n");
                } __except (EXCEPTION_EXECUTE_HANDLER) {
                    fwprintf(file, L"<unreadable>\r\n");
                }
            }
            if (suspended != (DWORD)-1) {
                ResumeThread(thread);
            }
            CloseHandle(thread);
        } while (Thread32Next(snapshot, &entry));
    }
    CloseHandle(snapshot);
    fclose(file);
    return 0;
}

static BOOL install_hook(
    InlineHook *hook, const char *name, const void *replacement
);
static BOOL install_address_hook(
    InlineHook *hook, DWORD address, const void *replacement
);
static void remove_hook(InlineHook *hook);
static void install_input_hooks(void);
static void remove_input_hooks(void);
static BOOL WINAPI hooked_set_foreground_window(HWND window);
static HWND find_game_window(void);

static BOOL is_hidden_desktop_window(HWND window) {
    LONG cached = InterlockedCompareExchange(
        &game_on_hidden_desktop, -1, -1
    );
    if (cached >= 0) {
        return cached != 0;
    }
    DWORD thread_id = GetWindowThreadProcessId(window, NULL);
    HDESK game_desktop = GetThreadDesktop(thread_id);
    HDESK input_desktop = OpenInputDesktop(
        0, FALSE, DESKTOP_READOBJECTS
    );
    WCHAR game_name[128];
    WCHAR input_name[128];
    DWORD needed = 0;
    BOOL hidden = FALSE;
    if (
        game_desktop != NULL &&
        input_desktop != NULL &&
        GetUserObjectInformationW(
            game_desktop,
            UOI_NAME,
            game_name,
            sizeof(game_name),
            &needed
        ) &&
        GetUserObjectInformationW(
            input_desktop,
            UOI_NAME,
            input_name,
            sizeof(input_name),
            &needed
        )
    ) {
        hidden = lstrcmpiW(game_name, input_name) != 0;
    }
    if (input_desktop != NULL) {
        CloseDesktop(input_desktop);
    }
    InterlockedExchange(&game_on_hidden_desktop, hidden ? 1 : 0);
    return hidden;
}

static void activate_hidden_desktop_window(HWND window) {
    if (!is_hidden_desktop_window(window)) {
        return;
    }
    DWORD thread_id = GetWindowThreadProcessId(window, NULL);
    HDESK desktop = GetThreadDesktop(thread_id);
    SetThreadDesktop(desktop);
    InterlockedExchange(&allow_game_foreground, 1);
    remove_hook(&foreground_window_hook);
    SetForegroundWindow(window);
    install_hook(
        &foreground_window_hook,
        "SetForegroundWindow",
        hooked_set_foreground_window
    );
}

typedef struct ConfirmButtonSearch {
    HWND button;
    LONG left;
} ConfirmButtonSearch;

typedef struct DialogSearch {
    HWND source;
    HWND result;
} DialogSearch;

static BOOL CALLBACK find_leftmost_button(HWND window, LPARAM parameter) {
    ConfirmButtonSearch *search = (ConfirmButtonSearch *)parameter;
    WCHAR class_name[16];
    class_name[0] = L'\0';
    GetClassNameW(window, class_name, ARRAYSIZE(class_name));
    if (
        lstrcmpW(class_name, L"Button") != 0 ||
        !IsWindowVisible(window)
    ) {
        return TRUE;
    }
    RECT rect;
    if (
        GetWindowRect(window, &rect) &&
        (search->button == NULL || rect.left < search->left)
    ) {
        search->button = window;
        search->left = rect.left;
    }
    return TRUE;
}

static BOOL CALLBACK enum_thread_dialog(HWND window, LPARAM parameter) {
    DialogSearch *search = (DialogSearch *)parameter;
    WCHAR class_name[16];
    class_name[0] = L'\0';
    GetClassNameW(window, class_name, ARRAYSIZE(class_name));
    if (
        window != search->source &&
        lstrcmpW(class_name, L"#32770") == 0 &&
        IsWindowVisible(window) &&
        FindWindowExW(window, NULL, L"SysListView32", NULL) == NULL &&
        (
            GetDlgItem(window, IDYES) != NULL ||
            GetDlgItem(window, IDOK) != NULL
        )
    ) {
        search->result = window;
        return FALSE;
    }
    return TRUE;
}

static BOOL CALLBACK enum_process_confirmation(HWND window, LPARAM parameter) {
    DialogSearch *search = (DialogSearch *)parameter;
    DWORD process_id = 0;
    GetWindowThreadProcessId(window, &process_id);
    DWORD game_process_id = 0;
    GetWindowThreadProcessId(search->source, &game_process_id);
    if (
        process_id != game_process_id ||
        window == search->source ||
        !IsWindowVisible(window)
    ) {
        return TRUE;
    }
    WCHAR class_name[16];
    class_name[0] = L'\0';
    GetClassNameW(window, class_name, ARRAYSIZE(class_name));
    if (
        lstrcmpW(class_name, L"#32770") == 0 &&
        FindWindowExW(window, NULL, L"SysListView32", NULL) == NULL &&
        (
            GetDlgItem(window, IDYES) != NULL ||
            GetDlgItem(window, IDOK) != NULL
        )
    ) {
        search->result = window;
        return FALSE;
    }
    return TRUE;
}

static HWND find_load_confirmation(void) {
    DialogSearch search;
    search.source = load_dialog_to_confirm;
    search.result = NULL;

    DWORD thread_id = GetWindowThreadProcessId(
        load_dialog_to_confirm, NULL
    );
    if (thread_id != 0) {
        EnumThreadWindows(
            thread_id, enum_thread_dialog, (LPARAM)&search
        );
    }
    if (search.result == NULL) {
        EnumWindows(
            enum_process_confirmation, (LPARAM)&search
        );
    }
    return search.result;
}

static LRESULT CALLBACK confirm_dialog_wndproc(
    HWND window, UINT message, WPARAM wparam, LPARAM lparam
) {
    if (message == WM_CCZ_CONFIRM_CLOSE) {
        append_control_log("confirm-wndproc");
        WNDPROC original = confirm_original_wndproc;
        /*
         * EndDialog must run on the dialog's owner thread.  This
         * window procedure is entered through SendMessage from the
         * worker thread, so the call executes on that UI thread and
         * lets the game's modal load handler unwind normally.
         */
        BOOL closed = EndDialog(window, (int)wparam);
        append_control_log(closed ? "confirm-enddialog-ok" :
            "confirm-enddialog-fail");
        if (IsWindow(window)) {
            SetWindowLongPtrW(
                window,
                GWLP_WNDPROC,
                (LONG_PTR)original
            );
        }
        confirm_original_wndproc = NULL;
        return 0;
    }
    return CallWindowProcW(
        confirm_original_wndproc, window, message, wparam, lparam
    );
}

static DWORD WINAPI confirm_load_dialog(LPVOID parameter) {
    (void)parameter;
    DWORD deadline = GetTickCount() + 10000;
    while ((LONG)(deadline - GetTickCount()) > 0) {
        HWND dialog = find_load_confirmation();
        if (dialog != NULL) {
            append_control_log("confirm-found");
            activate_hidden_desktop_window(dialog);
            HWND button = GetDlgItem(dialog, IDYES);
            if (button == NULL) {
                button = GetDlgItem(dialog, IDOK);
            }
            if (button == NULL) {
                ConfirmButtonSearch search;
                search.button = NULL;
                search.left = LONG_MAX;
                EnumChildWindows(
                    dialog, find_leftmost_button, (LPARAM)&search
                );
                button = search.button;
            }
            if (button != NULL) {
                append_control_log("confirm-clicked");
                /*
                 * Deliver the same button messages as a real click.  Some
                 * versions of the game's dialog procedure distinguish
                 * BM_CLICK from the mouse-button path when restoring the
                 * scene loop after the modal dialog closes.
                 */
                RECT rect;
                GetClientRect(button, &rect);
                LPARAM point = MAKELPARAM(
                    (rect.right - rect.left) / 2,
                    (rect.bottom - rect.top) / 2
                );
                SendMessageW(button, WM_MOUSEMOVE, 0, point);
                SendMessageW(
                    button, WM_LBUTTONDOWN, MK_LBUTTON, point
                );
                SendMessageW(button, WM_LBUTTONUP, 0, point);
                append_control_log("confirm-close-posted");
                return 0;
            }
        }
        Sleep(20);
    }
    return 1;
}

static DWORD WINAPI select_native_load_item(LPVOID parameter) {
    int item_index = (int)(INT_PTR)parameter;
    DWORD deadline = GetTickCount() + 10000;
    HWND dialog = NULL;
    while ((LONG)(deadline - GetTickCount()) > 0) {
        dialog = find_list_dialog();
        if (dialog != NULL) {
            break;
        }
        Sleep(10);
    }
    if (dialog == NULL) {
        return 120;
    }

    load_dialog_to_confirm = dialog;
    HANDLE confirm_thread = CreateThread(
        NULL, 0, confirm_load_dialog, NULL, 0, NULL
    );
    DWORD result = real_list_item(item_index);
    if (confirm_thread != NULL) {
        DWORD wait = WaitForSingleObject(confirm_thread, 10000);
        if (wait == WAIT_OBJECT_0) {
            DWORD confirm_result = 0;
            GetExitCodeThread(confirm_thread, &confirm_result);
            if (result == 0 && confirm_result != 0) {
                result = 121;
            }
        } else if (result == 0) {
            result = 122;
        }
        CloseHandle(confirm_thread);
    } else if (result == 0) {
        result = 123;
    }
    load_dialog_to_confirm = NULL;
    return result;
}

static void process_main_loop_action(void) {
    if (InterlockedCompareExchange(&main_loop_action, 0, 1) != 1) {
        return;
    }
    typedef DWORD (__stdcall *GameOpenLoadFunction)(DWORD);
    GameOpenLoadFunction open_dialog =
        (GameOpenLoadFunction)GAME_OPEN_LOAD_FUNCTION_ADDRESS;
    int item_index = (int)main_loop_slot;
    main_loop_result = 124;
    HANDLE select_thread = CreateThread(
        NULL,
        0,
        select_native_load_item,
        (LPVOID)(INT_PTR)item_index,
        0,
        NULL
    );
    if (select_thread != NULL) {
        DWORD open_result = open_dialog(1);
        DWORD select_result = 125;
        if (WaitForSingleObject(select_thread, 12000) == WAIT_OBJECT_0) {
            GetExitCodeThread(select_thread, &select_result);
        }
        CloseHandle(select_thread);
        main_loop_result = select_result == 0
            ? open_result
            : select_result;
    }
    if (main_loop_event != NULL) {
        SetEvent(main_loop_event);
    }
}

__declspec(naked) static void main_loop_hook(void) {
    __asm {
        pushfd
        pushad
        call process_main_loop_action
        popad
        popfd
        mov eax, GAME_MAIN_LOOP_HOOK_RETURN
        jmp eax
    }
}

static DWORD install_main_loop_hook(void) {
    if (InterlockedCompareExchange(
            &main_loop_hook_installed, 1, 0
        ) != 0) {
        return 0;
    }
    BYTE *target = (BYTE *)(UINT_PTR)GAME_MAIN_LOOP_HOOK_ADDRESS;
    DWORD protection = 0;
    if (!VirtualProtect(
            target,
            sizeof(main_loop_original),
            PAGE_EXECUTE_READWRITE,
            &protection
        )) {
        main_loop_hook_installed = 0;
        return 126;
    }
    memcpy(main_loop_original, target, sizeof(main_loop_original));
    target[0] = 0xE9;
    *(DWORD *)(target + 1) =
        (DWORD)((BYTE *)main_loop_hook - target - 5);
    FlushInstructionCache(
        GetCurrentProcess(), target, sizeof(main_loop_original)
    );
    DWORD ignored = 0;
    VirtualProtect(
        target, sizeof(main_loop_original), protection, &ignored
    );
    return 0;
}

static DWORD run_main_loop_load(int item_index) {
    DWORD install_result = install_main_loop_hook();
    if (install_result != 0) {
        return install_result;
    }
    if (InterlockedCompareExchange(&main_loop_action, 0, 0) != 0) {
        return 127;
    }
    if (main_loop_event != NULL) {
        CloseHandle(main_loop_event);
        main_loop_event = NULL;
    }
    main_loop_event = CreateEventW(NULL, TRUE, FALSE, NULL);
    if (main_loop_event == NULL) {
        return 128;
    }
    main_loop_slot = item_index;
    main_loop_result = 129;
    InterlockedExchange(&main_loop_action, 1);
    DWORD wait = WaitForSingleObject(main_loop_event, 30000);
    DWORD result = wait == WAIT_OBJECT_0 ? main_loop_result : 130;
    CloseHandle(main_loop_event);
    main_loop_event = NULL;
    InterlockedExchange(&main_loop_action, 0);
    return result;
}

static LRESULT CALLBACK control_game_wndproc(
    HWND window, UINT message, WPARAM wparam, LPARAM lparam
) {
    if (message == WM_CCZ_START_GAME_LOOP) {
        typedef void (__cdecl *GameMainLoopFunction)(void);
        GameMainLoopFunction game_loop =
            (GameMainLoopFunction)GAME_MAIN_LOOP_FUNCTION_ADDRESS;
        WNDPROC original = original_game_wndproc;
        SetWindowLongPtrW(window, GWLP_WNDPROC, (LONG_PTR)original);
        original_game_wndproc = NULL;
        game_call_result = 1;
        InterlockedExchange(&game_call_completed, 1);
        __try {
            game_loop();
        } __except (
            record_control_exception(GetExceptionInformation())
        ) {
            game_call_result = 0x10000000 |
                (GetExceptionCode() & 0x0FFFFFFF);
        }
        return 0;
    }
    if (message == WM_CCZ_HIDDEN_ACTIVATE) {
        synthetic_root = window;
        synthetic_focus = window;
        if (is_hidden_desktop_window(window)) {
            InterlockedExchange(&allow_game_foreground, 1);
            SetForegroundWindow(window);
            SetActiveWindow(window);
            SetFocus(window);
            InterlockedExchange(&allow_game_foreground, 0);
        }
        CallWindowProcW(
            original_game_wndproc,
            window,
            WM_ACTIVATEAPP,
            TRUE,
            GetCurrentThreadId()
        );
        CallWindowProcW(
            original_game_wndproc, window, WM_ACTIVATE, WA_ACTIVE, 0
        );
        CallWindowProcW(
            original_game_wndproc,
            window,
            WM_NCACTIVATE,
            TRUE,
            0
        );
        CallWindowProcW(
            original_game_wndproc,
            window,
            WM_SETFOCUS,
            0,
            0
        );
        InterlockedExchange(&game_call_completed, 1);
        return 0;
    }
    if (message == WM_CCZ_END_DIALOG) {
        return DestroyWindow(window) ? 0 : 1;
    }
    if (message == WM_CCZ_DIRECT_LOAD) {
        typedef DWORD (__stdcall *GameLoadFunction)(DWORD);
        GameLoadFunction load_function =
            (GameLoadFunction)GAME_LOAD_FUNCTION_ADDRESS;
        game_call_result = load_function((DWORD)wparam);
        InterlockedExchange(&game_call_completed, 1);
        return 0;
    }
    if (message == WM_CCZ_DIRECT_SAVE) {
        typedef void (__stdcall *GameSaveFunction)(DWORD);
        GameSaveFunction save_function =
            (GameSaveFunction)GAME_SAVE_FUNCTION_ADDRESS;
        save_function((DWORD)wparam);
        game_call_result = 1;
        InterlockedExchange(&game_call_completed, 1);
        return 0;
    }
    if (message == WM_CCZ_GAME_TICK) {
        typedef void (__cdecl *GameTickFunction)(void);
        GameTickFunction tick_function =
            (GameTickFunction)GAME_TICK_FUNCTION_ADDRESS;
        game_call_result = 0;
        __try {
            tick_function();
            game_call_result = 1;
        } __except (
            record_control_exception(GetExceptionInformation())
        ) {
            game_call_result = 0x10000000 |
                (GetExceptionCode() & 0x0FFFFFFF);
        }
        InterlockedExchange(&game_call_completed, 1);
        return 0;
    }
    if (message == WM_CCZ_PROCESS_LOAD_STATE) {
        game_call_result = 0;
        __try {
            DWORD transition_result = 0;
            __asm {
                mov ecx, 0x4B3D08
                mov eax, GAME_LOAD_TRANSITION_ADDRESS
                call eax
                mov transition_result, eax
            }
            (void)transition_result;
            game_call_result = 1;
        } __except (
            record_control_exception(GetExceptionInformation())
        ) {
            game_call_result = 0x10000000 |
                (GetExceptionCode() & 0x0FFFFFFF);
        }
        InterlockedExchange(&game_call_completed, 1);
        return 0;
    }
    if (message == WM_CCZ_DISPATCH_LOAD_STATE) {
        typedef DWORD (__cdecl *GameLoadDispatchFunction)(void);
        GameLoadDispatchFunction dispatch =
            (GameLoadDispatchFunction)GAME_LOAD_STATE_DISPATCH_ADDRESS;
        game_call_result = 0;
        __try {
            game_call_result = dispatch();
        } __except (
            record_control_exception(GetExceptionInformation())
        ) {
            game_call_result = 0x10000000 |
                (GetExceptionCode() & 0x0FFFFFFF);
        }
        InterlockedExchange(&game_call_completed, 1);
        return 0;
    }
    if (message == WM_CCZ_MARK_LOAD_READY) {
        typedef void (__stdcall *MarkLoadReadyFunction)(DWORD);
        MarkLoadReadyFunction mark =
            (MarkLoadReadyFunction)0x0043BFD4;
        game_call_result = 0;
        __try {
            mark((DWORD)wparam);
            game_call_result = 1;
        } __except (
            record_control_exception(GetExceptionInformation())
        ) {
            game_call_result = 0x10000000 |
                (GetExceptionCode() & 0x0FFFFFFF);
        }
        InterlockedExchange(&game_call_completed, 1);
        return 0;
    }
    if (message == WM_CCZ_DIALOG_LOAD) {
        DWORD dialog_result = 0;
        void *dialog_object = dialog_object_to_load;
        int item_index = dialog_item_to_load;
        TemporaryCodePatch state_patch;
        ZeroMemory(&state_patch, sizeof(state_patch));
        HANDLE confirm_thread = NULL;
        game_call_result = 1;
        __try {
            game_call_result = 2;
            /*
             * Run the dialog's complete load handler on its owning UI
             * thread. The method performs validation, state transitions,
             * the actual load, and closes the dialog itself. Its normal
             * path asks for a confirmation through 0x418C34.  Leave that
             * call intact and answer the real modal dialog from a helper
             * thread so the game's own confirmation continuation runs.
             */
            load_dialog_to_confirm = window;
            confirm_thread = CreateThread(
                NULL, 0, confirm_load_dialog, NULL, 0, NULL
            );
            __asm {
                push item_index
                mov ecx, dialog_object
                mov eax, GAME_DIALOG_LOAD_FUNCTION_ADDRESS
                call eax
                mov dialog_result, eax
            }
            if (confirm_thread != NULL) {
                WaitForSingleObject(confirm_thread, 12000);
                CloseHandle(confirm_thread);
                confirm_thread = NULL;
            }
            restore_code_patch(&state_patch);
            append_control_log(
                dialog_result ? "dialog-method-true" : "dialog-method-false"
            );
            game_call_result = 5;
        } __except (EXCEPTION_EXECUTE_HANDLER) {
            if (confirm_thread != NULL) {
                CloseHandle(confirm_thread);
            }
            restore_code_patch(&state_patch);
            game_call_result = 0x10000000 |
                (GetExceptionCode() & 0x0FFFFFFF);
        }
        load_dialog_to_confirm = NULL;
        InterlockedExchange(&game_call_completed, 1);
        return (LRESULT)dialog_result;
    }
    if (message == WM_CCZ_OPEN_LOAD_DIALOG) {
        typedef DWORD (__stdcall *GameOpenLoadFunction)(DWORD);
        GameOpenLoadFunction open_dialog =
            (GameOpenLoadFunction)GAME_OPEN_LOAD_FUNCTION_ADDRESS;
        game_call_result = open_dialog(1);
        InterlockedExchange(&game_call_completed, 1);
        return 0;
    }
    if (message == WM_CCZ_REAL_RANDOM) {
        typedef DWORD (__stdcall *GameEventInputFunction)(
            DWORD, DWORD
        );
        GameEventInputFunction event_input =
            (GameEventInputFunction)GAME_EVENT_INPUT_FUNCTION_ADDRESS;
        game_call_result = 0;
        __try {
            event_input(LOWORD(wparam), HIWORD(wparam));
            game_call_result = 1;
        } __except (EXCEPTION_EXECUTE_HANDLER) {
            game_call_result = 0x10000000 |
                (GetExceptionCode() & 0x0FFFFFFF);
        }
        InterlockedExchange(&game_call_completed, 1);
        return 0;
    }
    if (message == WM_CCZ_CONFIRM_SELECTION) {
        typedef DWORD (__stdcall *GameConfirmSelectionFunction)(
            DWORD
        );
        GameConfirmSelectionFunction confirm_selection =
            (GameConfirmSelectionFunction)
                GAME_CONFIRM_SELECTION_FUNCTION_ADDRESS;
        typedef void (__stdcall *GameUpdateHoverFunction)(void);
        GameUpdateHoverFunction update_hover =
            (GameUpdateHoverFunction)
                GAME_UPDATE_HOVER_FUNCTION_ADDRESS;
        DWORD mouse_point = MAKELPARAM(
            LOWORD(wparam), HIWORD(wparam)
        );
        game_call_result = 0;
        __try {
            __asm {
                push mouse_point
                push 0
                push 0x200
                mov ecx, GAME_MOUSE_INPUT_OBJECT_ADDRESS
                mov eax, GAME_MOUSE_INPUT_FUNCTION_ADDRESS
                call eax
            }
            update_hover();
            confirm_selection(0);
            game_call_result = 1;
        } __except (EXCEPTION_EXECUTE_HANDLER) {
            game_call_result = 0x10000000 |
                (GetExceptionCode() & 0x0FFFFFFF);
        }
        InterlockedExchange(&game_call_completed, 1);
        return 0;
    }
    if (message == WM_CCZ_GAME_MOUSE) {
        DWORD mouse_point = MAKELPARAM(
            requested_mouse_x, requested_mouse_y
        );
        game_call_result = 0;
        __try {
            __asm {
                push mouse_point
                push requested_mouse_message
                push window
                mov ecx, GAME_MOUSE_INPUT_OBJECT_ADDRESS
                mov eax, GAME_MOUSE_INPUT_FUNCTION_ADDRESS
                call eax
            }
            game_call_result = 1;
        } __except (EXCEPTION_EXECUTE_HANDLER) {
            game_call_result = 0x10000000 |
                (GetExceptionCode() & 0x0FFFFFFF);
        }
        InterlockedExchange(&game_call_completed, 1);
        return 0;
    }
    if (message == WM_CCZ_GAME_FRAME_CLICK) {
        typedef DWORD (__stdcall *GameReadMouseActionFunction)(void);
        typedef void (__stdcall *GameUpdateHoverFunction)(void);
        typedef void (__stdcall *GameUpdateMapHoverFunction)(void);
        typedef DWORD (__stdcall *GameHandleMouseActionFunction)(void);
        typedef void (__stdcall *GameFinishMouseActionFunction)(void);
        GameReadMouseActionFunction read_mouse_action =
            (GameReadMouseActionFunction)
                GAME_READ_MOUSE_ACTION_FUNCTION_ADDRESS;
        GameUpdateHoverFunction update_hover =
            (GameUpdateHoverFunction)
                GAME_UPDATE_HOVER_FUNCTION_ADDRESS;
        GameUpdateMapHoverFunction update_map_hover =
            (GameUpdateMapHoverFunction)
                GAME_UPDATE_MAP_HOVER_FUNCTION_ADDRESS;
        GameHandleMouseActionFunction handle_mouse_action =
            (GameHandleMouseActionFunction)
                GAME_HANDLE_MOUSE_ACTION_FUNCTION_ADDRESS;
        GameFinishMouseActionFunction finish_mouse_action =
            (GameFinishMouseActionFunction)
                GAME_FINISH_MOUSE_ACTION_FUNCTION_ADDRESS;
        DWORD mouse_point = MAKELPARAM(
            requested_mouse_x, requested_mouse_y
        );
        DWORD mouse_action = 0;
        DWORD frame_stage = 70;
        game_call_result = frame_stage;
        __try {
            __asm {
                push mouse_point
                push WM_MOUSEMOVE
                push window
                mov ecx, GAME_MOUSE_INPUT_OBJECT_ADDRESS
                mov eax, GAME_MOUSE_INPUT_FUNCTION_ADDRESS
                call eax

                push mouse_point
                push WM_LBUTTONUP
                push window
                mov ecx, GAME_MOUSE_INPUT_OBJECT_ADDRESS
                mov eax, GAME_MOUSE_INPUT_FUNCTION_ADDRESS
                call eax
            }
            frame_stage = 71;
            game_call_result = frame_stage;
            mouse_action = read_mouse_action();
            frame_stage = 72;
            game_call_result = frame_stage;
            *(DWORD *)GAME_MOUSE_ACTION_ADDRESS = mouse_action;
            *(DWORD *)GAME_PREVIOUS_MOUSE_ACTION_ADDRESS = 0;
            frame_stage = 73;
            game_call_result = frame_stage;
            update_hover();
            frame_stage = 74;
            game_call_result = frame_stage;
            update_map_hover();
            frame_stage = 76;
            game_call_result = frame_stage;
            if ((handle_mouse_action() & 0xFF) == 1) {
                frame_stage = 75;
                game_call_result = frame_stage;
                finish_mouse_action();
            }
            game_call_result = 1;
        } __except (EXCEPTION_EXECUTE_HANDLER) {
            game_call_result = 0x20000000 |
                ((frame_stage & 0xFF) << 16) |
                (GetExceptionCode() & 0xFFFF);
        }
        InterlockedExchange(&game_call_completed, 1);
        return 0;
    }
    if (message == WM_CCZ_ENABLE_ACCELERATION) {
        typedef void (__stdcall *GameAccelerationToggleFunction)(void);
        GameAccelerationToggleFunction toggle_acceleration =
            (GameAccelerationToggleFunction)
                GAME_ACCELERATION_TOGGLE_FUNCTION_ADDRESS;
        game_call_result = 0;
        __try {
            if (*(BYTE *)GAME_ACCELERATION_ENABLED_ADDRESS != 1) {
                toggle_acceleration();
            }
            game_call_result =
                *(BYTE *)GAME_ACCELERATION_ENABLED_ADDRESS == 1 ? 1 : 0;
        } __except (EXCEPTION_EXECUTE_HANDLER) {
            game_call_result = 0x10000000 |
                (GetExceptionCode() & 0x0FFFFFFF);
        }
        InterlockedExchange(&game_call_completed, 1);
        return 0;
    }
    return CallWindowProcW(
        original_game_wndproc, window, message, wparam, lparam
    );
}

static SHORT WINAPI hooked_get_key_state(int key) {
    if (key == VK_LBUTTON && synthetic_left_down) {
        return (SHORT)0x8000;
    }
    if (key == VK_RBUTTON && synthetic_right_down) {
        return (SHORT)0x8000;
    }
    return 0;
}

static SHORT WINAPI hooked_get_async_key_state(int key) {
    if (key == VK_LBUTTON && synthetic_left_down) {
        return (SHORT)0x8001;
    }
    if (key == VK_RBUTTON && synthetic_right_down) {
        return (SHORT)0x8001;
    }
    return 0;
}

static BOOL WINAPI hooked_get_cursor_pos(LPPOINT point) {
    if (point == NULL) {
        return FALSE;
    }
    *point = synthetic_cursor;
    return TRUE;
}

static BOOL WINAPI hooked_set_cursor_pos(int x, int y) {
    (void)x;
    (void)y;
    return TRUE;
}

static DWORD WINAPI hooked_get_message_pos(void) {
    return MAKELONG(synthetic_cursor.x, synthetic_cursor.y);
}

static HWND WINAPI hooked_get_foreground_window(void) {
    return synthetic_root;
}

static HWND WINAPI hooked_get_active_window(void) {
    return synthetic_root;
}

static HWND WINAPI hooked_get_focus(void) {
    return synthetic_focus;
}

static BOOL WINAPI hooked_set_foreground_window(HWND window) {
    if (
        InterlockedCompareExchange(
            &allow_game_foreground, 0, 0
        ) != 0
    ) {
        remove_hook(&foreground_window_hook);
        BOOL result = SetForegroundWindow(window);
        install_hook(
            &foreground_window_hook,
            "SetForegroundWindow",
            hooked_set_foreground_window
        );
        return result;
    }
    return FALSE;
}

static BOOL WINAPI hooked_bring_window_to_top(HWND window) {
    (void)window;
    return FALSE;
}

static BOOL WINAPI hooked_peek_message(
    LPMSG message,
    HWND window,
    UINT minimum,
    UINT maximum,
    UINT remove_message
) {
    remove_hook(&peek_message_hook);
    BOOL result = PeekMessageW(
        message, window, minimum, maximum, remove_message
    );
    install_hook(
        &peek_message_hook, "PeekMessageW", hooked_peek_message
    );
    if (!result || message == NULL) {
        return result;
    }
    if (message->message == WM_ACTIVATEAPP) {
        message->wParam = TRUE;
    } else if (
        message->message == WM_ACTIVATE &&
        LOWORD(message->wParam) == WA_INACTIVE
    ) {
        message->wParam = WA_ACTIVE;
    } else if (message->message == WM_KILLFOCUS) {
        message->message = WM_SETFOCUS;
        message->wParam = (WPARAM)synthetic_root;
    } else if (message->message == WM_NCACTIVATE) {
        message->wParam = TRUE;
    }
    return result;
}

static BOOL WINAPI hooked_show_window(HWND window, int command) {
    BOOL top_level =
        (GetWindowLongW(window, GWL_STYLE) & WS_CHILD) == 0;
    if (top_level && command != SW_HIDE) {
        WCHAR class_name[32];
        class_name[0] = L'\0';
        GetClassNameW(window, class_name, ARRAYSIZE(class_name));
        RECT rect;
        if (GetWindowRect(window, &rect)) {
            LONG style = GetWindowLongW(window, GWL_EXSTYLE);
            SetWindowLongW(window, GWL_EXSTYLE, style | WS_EX_LAYERED);
            SetLayeredWindowAttributes(window, 0, 1, LWA_ALPHA);
            BOOL cloak = FALSE;
            DwmSetWindowAttribute(
                window,
                DWMWA_CLOAK,
                &cloak,
                sizeof(cloak)
            );
            SetWindowPos(
                window,
                HWND_BOTTOM,
                0,
                0,
                rect.right - rect.left,
                rect.bottom - rect.top,
                SWP_NOACTIVATE
            );
        }
        command = SW_SHOWNOACTIVATE;
    }
    remove_hook(&show_window_hook);
    BOOL result = ShowWindow(window, command);
    install_hook(
        &show_window_hook, "ShowWindow", hooked_show_window
    );
    return result;
}

static HWND WINAPI hooked_create_window_ex(
    DWORD extended_style,
    LPCWSTR class_name,
    LPCWSTR window_name,
    DWORD style,
    int x,
    int y,
    int width,
    int height,
    HWND parent,
    HMENU menu,
    HINSTANCE instance,
    LPVOID parameter
) {
    if (InterlockedCompareExchange(
            &trace_dialog_create, 0, 0
        ) != 0) {
        append_dialog_trace(
            class_name, window_name, _ReturnAddress()
        );
    }
    BOOL top_level = (style & WS_CHILD) == 0;
    BOOL requested_visible = top_level && (style & WS_VISIBLE) != 0;
    BOOL guarding = InterlockedCompareExchange(
        &guard_started, 0, 0
    ) != 0;
    if (top_level && guarding) {
        style &= ~WS_VISIBLE;
        x = 0;
        y = 0;
    }

    remove_hook(&create_window_ex_hook);
    HWND window = CreateWindowExW(
        extended_style,
        class_name,
        window_name,
        style,
        x,
        y,
        width,
        height,
        parent,
        menu,
        instance,
        parameter
    );
    install_hook(
        &create_window_ex_hook,
        "CreateWindowExW",
        hooked_create_window_ex
    );
    if (window != NULL && requested_visible && guarding) {
        ShowWindow(window, SW_SHOWNOACTIVATE);
    }
    return window;
}

static HWND WINAPI hooked_create_window_ex_a(
    DWORD extended_style,
    LPCSTR class_name,
    LPCSTR window_name,
    DWORD style,
    int x,
    int y,
    int width,
    int height,
    HWND parent,
    HMENU menu,
    HINSTANCE instance,
    LPVOID parameter
) {
    WCHAR class_wide[128];
    WCHAR title_wide[256];
    LPCWSTR class_for_log = L"<null>";
    LPCWSTR title_for_log = L"<null>";
    if (IS_INTRESOURCE(class_name)) {
        wsprintfW(
            class_wide, L"#%u", (UINT)(UINT_PTR)class_name
        );
        class_for_log = class_wide;
    } else if (class_name != NULL) {
        MultiByteToWideChar(
            CP_ACP, 0, class_name, -1,
            class_wide, ARRAYSIZE(class_wide)
        );
        class_for_log = class_wide;
    }
    if (IS_INTRESOURCE(window_name)) {
        title_for_log = L"<resource>";
    } else if (window_name != NULL) {
        MultiByteToWideChar(
            CP_ACP, 0, window_name, -1,
            title_wide, ARRAYSIZE(title_wide)
        );
        title_for_log = title_wide;
    }
    if (InterlockedCompareExchange(
            &trace_dialog_create, 0, 0
        ) != 0) {
        append_dialog_trace(
            class_for_log, title_for_log, _ReturnAddress()
        );
    }

    BOOL top_level = (style & WS_CHILD) == 0;
    BOOL requested_visible = top_level && (style & WS_VISIBLE) != 0;
    BOOL guarding = InterlockedCompareExchange(
        &guard_started, 0, 0
    ) != 0;
    if (top_level && guarding) {
        style &= ~WS_VISIBLE;
        x = 0;
        y = 0;
    }
    remove_hook(&create_window_ex_a_hook);
    HWND window = CreateWindowExA(
        extended_style,
        class_name,
        window_name,
        style,
        x,
        y,
        width,
        height,
        parent,
        menu,
        instance,
        parameter
    );
    install_hook(
        &create_window_ex_a_hook,
        "CreateWindowExA",
        hooked_create_window_ex_a
    );
    if (window != NULL && requested_visible && guarding) {
        ShowWindow(window, SW_SHOWNOACTIVATE);
    }
    return window;
}

static INT_PTR WINAPI hooked_dialog_box_param_a(
    HINSTANCE instance,
    LPCSTR template_name,
    HWND parent,
    DLGPROC dialog_proc,
    LPARAM parameter
) {
    WCHAR template_text[128];
    if (IS_INTRESOURCE(template_name)) {
        wsprintfW(
            template_text,
            L"DialogBoxParamA:#%u",
            (UINT)(UINT_PTR)template_name
        );
    } else {
        WCHAR name[96];
        MultiByteToWideChar(
            CP_ACP, 0, template_name, -1,
            name, ARRAYSIZE(name)
        );
        wsprintfW(template_text, L"DialogBoxParamA:%s", name);
    }
    append_dialog_trace(
        L"#32770", template_text, _ReturnAddress()
    );
    WCHAR detail[256];
    wsprintfW(
        detail,
        L"DialogBoxParamA parent=%08lX proc=%08lX param=%08lX",
        (DWORD)(UINT_PTR)parent,
        (DWORD)(UINT_PTR)dialog_proc,
        (DWORD)(UINT_PTR)parameter
    );
    append_dialog_trace(
        L"#32770", detail, _ReturnAddress()
    );
    remove_hook(&dialog_box_param_a_hook);
    INT_PTR result = DialogBoxParamA(
        instance, template_name, parent, dialog_proc, parameter
    );
    install_hook(
        &dialog_box_param_a_hook,
        "DialogBoxParamA",
        hooked_dialog_box_param_a
    );
    return result;
}

static HWND WINAPI hooked_create_dialog_indirect_param_a(
    HINSTANCE instance,
    LPCDLGTEMPLATEA template_data,
    HWND parent,
    DLGPROC dialog_proc,
    LPARAM parameter
) {
    append_dialog_trace(
        L"#32770",
        L"CreateDialogIndirectParamA",
        _ReturnAddress()
    );
    remove_hook(&create_dialog_indirect_param_a_hook);
    HWND result = CreateDialogIndirectParamA(
        instance, template_data, parent, dialog_proc, parameter
    );
    install_hook(
        &create_dialog_indirect_param_a_hook,
        "CreateDialogIndirectParamA",
        hooked_create_dialog_indirect_param_a
    );
    return result;
}

static BOOL install_hook(
    InlineHook *hook, const char *name, const void *replacement
) {
    if (hook->installed) {
        return TRUE;
    }
    HMODULE user = GetModuleHandleW(L"user32.dll");
    BYTE *target = (BYTE *)GetProcAddress(user, name);
    if (target == NULL) {
        return FALSE;
    }

    DWORD old_protect = 0;
    if (!VirtualProtect(
            target, 5, PAGE_EXECUTE_READWRITE, &old_protect
        )) {
        return FALSE;
    }
    hook->target = target;
    CopyMemory(hook->original, target, 5);
    target[0] = 0xE9;
    *(LONG *)(target + 1) =
        (LONG)((BYTE *)replacement - target - 5);
    FlushInstructionCache(GetCurrentProcess(), target, 5);
    VirtualProtect(target, 5, old_protect, &old_protect);
    hook->installed = TRUE;
    return TRUE;
}

static BOOL install_address_hook(
    InlineHook *hook, DWORD address, const void *replacement
) {
    BYTE *target = (BYTE *)(UINT_PTR)address;
    DWORD old_protect = 0;
    if (!VirtualProtect(
            target, 5, PAGE_EXECUTE_READWRITE, &old_protect
        )) {
        return FALSE;
    }
    hook->target = target;
    CopyMemory(hook->original, target, 5);
    target[0] = 0xE9;
    *(LONG *)(target + 1) =
        (LONG)((BYTE *)replacement - target - 5);
    FlushInstructionCache(GetCurrentProcess(), target, 5);
    VirtualProtect(target, 5, old_protect, &old_protect);
    hook->installed = TRUE;
    return TRUE;
}

static void remove_hook(InlineHook *hook) {
    if (!hook->installed) {
        return;
    }
    DWORD old_protect = 0;
    if (VirtualProtect(
            hook->target, 5, PAGE_EXECUTE_READWRITE, &old_protect
        )) {
        CopyMemory(hook->target, hook->original, 5);
        FlushInstructionCache(GetCurrentProcess(), hook->target, 5);
        VirtualProtect(
            hook->target, 5, old_protect, &old_protect
        );
    }
    hook->installed = FALSE;
}

static void install_input_hooks(void) {
    install_hook(
        &key_state_hook, "GetKeyState", hooked_get_key_state
    );
    install_hook(
        &async_key_state_hook,
        "GetAsyncKeyState",
        hooked_get_async_key_state
    );
    install_hook(
        &cursor_pos_hook, "GetCursorPos", hooked_get_cursor_pos
    );
    install_hook(
        &message_pos_hook, "GetMessagePos", hooked_get_message_pos
    );
}

static void remove_input_hooks(void) {
    remove_hook(&message_pos_hook);
    remove_hook(&cursor_pos_hook);
    remove_hook(&async_key_state_hook);
    remove_hook(&key_state_hook);
}

static void update_input_hooks_safely(HWND window, BOOL install) {
    while (InterlockedCompareExchange(
            &input_hook_update_lock, 1, 0
        ) != 0) {
        Sleep(1);
    }

    HANDLE window_thread = NULL;
    DWORD window_thread_id = GetWindowThreadProcessId(window, NULL);
    if (
        window_thread_id != 0 &&
        window_thread_id != GetCurrentThreadId()
    ) {
        window_thread = OpenThread(
            THREAD_SUSPEND_RESUME, FALSE, window_thread_id
        );
        if (window_thread != NULL) {
            if (SuspendThread(window_thread) == (DWORD)-1) {
                CloseHandle(window_thread);
                window_thread = NULL;
            }
        }
    }

    if (install) {
        install_input_hooks();
    } else {
        remove_input_hooks();
    }

    if (window_thread != NULL) {
        ResumeThread(window_thread);
        CloseHandle(window_thread);
    }
    InterlockedExchange(&input_hook_update_lock, 0);
}

static HWND find_list_dialog(void) {
    HWND window = NULL;
    DWORD current_pid = GetCurrentProcessId();
    while ((window = FindWindowExW(NULL, window, L"#32770", NULL)) != NULL) {
        DWORD window_pid = 0;
        GetWindowThreadProcessId(window, &window_pid);
        if (window_pid != current_pid || !IsWindowVisible(window)) {
            continue;
        }
        if (FindWindowExW(window, NULL, L"SysListView32", NULL) != NULL) {
            return window;
        }
    }
    return NULL;
}

static HWND find_game_window(void) {
    HWND window = NULL;
    DWORD current_pid = GetCurrentProcessId();
    while ((window = FindWindowExW(NULL, window, L"SOUSOU", NULL)) != NULL) {
        DWORD window_pid = 0;
        GetWindowThreadProcessId(window, &window_pid);
        if (window_pid == current_pid) {
            return window;
        }
    }
    return NULL;
}

static BOOL CALLBACK move_window_offscreen(
    HWND window, LPARAM parameter
) {
    DWORD window_pid = 0;
    GetWindowThreadProcessId(window, &window_pid);
    if (window_pid != (DWORD)parameter) {
        return TRUE;
    }
    WCHAR class_name[32];
    class_name[0] = L'\0';
    GetClassNameW(window, class_name, ARRAYSIZE(class_name));
    RECT rect;
    if (GetWindowRect(window, &rect)) {
        BOOL hidden_desktop = is_hidden_desktop_window(window);
        if (!hidden_desktop) {
            LONG style = GetWindowLongW(window, GWL_EXSTYLE);
            if ((style & WS_EX_LAYERED) == 0) {
                SetWindowLongW(
                    window, GWL_EXSTYLE, style | WS_EX_LAYERED
                );
            }
            SetLayeredWindowAttributes(window, 0, 1, LWA_ALPHA);
        }
        BOOL cloak = FALSE;
        DwmSetWindowAttribute(
            window,
            DWMWA_CLOAK,
            &cloak,
            sizeof(cloak)
        );
        SetWindowPos(
            window,
            HWND_BOTTOM,
            0,
            0,
            rect.right - rect.left,
            rect.bottom - rect.top,
            SWP_NOACTIVATE
        );
        if (lstrcmpW(class_name, L"SOUSOU") == 0) {
            synthetic_root = window;
            if (synthetic_focus == NULL || !IsWindow(synthetic_focus)) {
                synthetic_focus = window;
            }
            if ((guard_tick % 40) == 0) {
                PostMessageW(window, WM_ACTIVATEAPP, TRUE, 0);
                PostMessageW(window, WM_ACTIVATE, WA_ACTIVE, 0);
            }
        }
    }
    return TRUE;
}

static DWORD WINAPI offscreen_guard(LPVOID parameter) {
    DWORD pid = (DWORD)(UINT_PTR)parameter;
    while (TRUE) {
        InterlockedIncrement(&guard_tick);
        EnumWindows(move_window_offscreen, (LPARAM)pid);
        HWND foreground = GetForegroundWindow();
        DWORD foreground_pid = 0;
        GetWindowThreadProcessId(foreground, &foreground_pid);
        if (
            foreground_pid == pid &&
            InterlockedCompareExchange(
                &allow_game_foreground, 0, 0
            ) == 0 &&
            guarded_foreground != NULL &&
            IsWindow(guarded_foreground)
        ) {
            remove_hook(&foreground_window_hook);
            SetForegroundWindow(guarded_foreground);
            install_hook(
                &foreground_window_hook,
                "SetForegroundWindow",
                hooked_set_foreground_window
            );
        }
        Sleep(5);
    }
}

static DWORD start_guard(void) {
    if (InterlockedCompareExchange(&guard_started, 1, 0) != 0) {
        return 0;
    }
    guarded_foreground = GetForegroundWindow();
    install_hook(
        &foreground_window_hook,
        "SetForegroundWindow",
        hooked_set_foreground_window
    );
    install_hook(
        &bring_window_to_top_hook,
        "BringWindowToTop",
        hooked_bring_window_to_top
    );
    install_hook(
        &show_window_hook,
        "ShowWindow",
        hooked_show_window
    );
    install_hook(
        &create_window_ex_hook,
        "CreateWindowExW",
        hooked_create_window_ex
    );
    install_hook(
        &create_window_ex_a_hook,
        "CreateWindowExA",
        hooked_create_window_ex_a
    );
    install_hook(
        &dialog_box_param_a_hook,
        "DialogBoxParamA",
        hooked_dialog_box_param_a
    );
    install_hook(
        &create_dialog_indirect_param_a_hook,
        "CreateDialogIndirectParamA",
        hooked_create_dialog_indirect_param_a
    );
    install_hook(
        &get_foreground_window_hook,
        "GetForegroundWindow",
        hooked_get_foreground_window
    );
    install_hook(
        &get_active_window_hook,
        "GetActiveWindow",
        hooked_get_active_window
    );
    install_hook(
        &get_focus_hook, "GetFocus", hooked_get_focus
    );
    install_hook(
        &set_cursor_pos_hook, "SetCursorPos", hooked_set_cursor_pos
    );
    install_hook(
        &peek_message_hook, "PeekMessageW", hooked_peek_message
    );
    HANDLE thread = CreateThread(
        NULL,
        0,
        offscreen_guard,
        (LPVOID)(UINT_PTR)GetCurrentProcessId(),
        0,
        NULL
    );
    if (thread == NULL) {
        guard_started = 0;
        return 6;
    }
    CloseHandle(thread);
    return 0;
}

static void activate_control(HWND window) {
    HWND root = GetAncestor(window, GA_ROOT);
    synthetic_root = root;
    synthetic_focus = window;
    SendMessageW(window, WM_SETFOCUS, 0, 0);
}

static void post_synthetic_click(
    HWND window, int x, int y, int count, BOOL right
) {
    UINT move = WM_MOUSEMOVE;
    UINT down = right ? WM_RBUTTONDOWN : WM_LBUTTONDOWN;
    UINT up = right ? WM_RBUTTONUP : WM_LBUTTONUP;
    UINT double_click =
        right ? WM_RBUTTONDBLCLK : WM_LBUTTONDBLCLK;
    WPARAM button = right ? MK_RBUTTON : MK_LBUTTON;
    LPARAM point = MAKELPARAM(x, y);
    HWND root = GetAncestor(window, GA_ROOT);
    HWND previous_foreground = GetForegroundWindow();

    synthetic_cursor.x = x;
    synthetic_cursor.y = y;
    ClientToScreen(window, &synthetic_cursor);
    InterlockedExchange(&allow_game_foreground, 1);
    remove_hook(&foreground_window_hook);
    SetForegroundWindow(root);
    activate_control(window);
    update_input_hooks_safely(window, TRUE);
    SendMessageW(
        root,
        WM_ACTIVATEAPP,
        TRUE,
        GetCurrentThreadId()
    );
    SendMessageW(root, WM_ACTIVATE, WA_ACTIVE, 0);

    SendMessageW(
        root,
        WM_MOUSEACTIVATE,
        (WPARAM)root,
        MAKELPARAM(HTCLIENT, down)
    );
    SendMessageW(
        window,
        WM_SETCURSOR,
        (WPARAM)window,
        MAKELPARAM(HTCLIENT, move)
    );
    SendMessageW(window, move, 0, point);
    for (int index = 0; index < count; ++index) {
        if (index == 1) {
            if (right) {
                synthetic_right_down = 1;
            } else {
                synthetic_left_down = 1;
            }
            SendMessageW(window, double_click, button, point);
        } else {
            if (right) {
                synthetic_right_down = 1;
            } else {
                synthetic_left_down = 1;
            }
            SendMessageW(window, down, button, point);
        }
        Sleep(250);
        synthetic_left_down = 0;
        synthetic_right_down = 0;
        SendMessageW(window, up, 0, point);
        Sleep(250);
    }

    Sleep(1800);
    update_input_hooks_safely(window, FALSE);
    if (
        previous_foreground != NULL &&
        previous_foreground != root &&
        IsWindow(previous_foreground)
    ) {
        SetForegroundWindow(previous_foreground);
    }
    install_hook(
        &foreground_window_hook,
        "SetForegroundWindow",
        hooked_set_foreground_window
    );
    InterlockedExchange(&allow_game_foreground, 0);
}

static DWORD post_silent_click_timed(
    HWND window, int x, int y, int tail_delay_ms
) {
    if (!IsWindow(window)) {
        return 80;
    }
    if (tail_delay_ms < 0 || tail_delay_ms > 5000) {
        return 150;
    }
    synthetic_root = GetAncestor(window, GA_ROOT);
    synthetic_focus = window;
    synthetic_cursor.x = x;
    synthetic_cursor.y = y;
    if (!ClientToScreen(window, &synthetic_cursor)) {
        return 81;
    }

    update_input_hooks_safely(window, TRUE);
    PostMessageW(
        synthetic_root,
        WM_ACTIVATEAPP,
        TRUE,
        GetCurrentThreadId()
    );
    PostMessageW(
        synthetic_root, WM_ACTIVATE, WA_ACTIVE, 0
    );
    PostMessageW(window, WM_SETFOCUS, 0, 0);
    PostMessageW(
        synthetic_root,
        WM_MOUSEACTIVATE,
        (WPARAM)synthetic_root,
        MAKELPARAM(HTCLIENT, WM_LBUTTONDOWN)
    );
    PostMessageW(
        window, WM_MOUSEMOVE, 0, MAKELPARAM(x, y)
    );
    synthetic_left_down = 1;
    PostMessageW(
        window, WM_LBUTTONDOWN, MK_LBUTTON, MAKELPARAM(x, y)
    );
    Sleep(350);
    synthetic_left_down = 0;
    PostMessageW(
        window, WM_LBUTTONUP, 0, MAKELPARAM(x, y)
    );
    Sleep((DWORD)tail_delay_ms);
    update_input_hooks_safely(window, FALSE);
    return 0;
}

static DWORD post_silent_click(HWND window, int x, int y) {
    return post_silent_click_timed(window, x, y, 1200);
}

static DWORD post_silent_click_burst(
    HWND window, int x, int y, int count
) {
    return post_silent_click_burst_timed(
        window, x, y, count, 55, 95
    );
}

static DWORD post_silent_click_burst_timed(
    HWND window,
    int x,
    int y,
    int count,
    int down_delay_ms,
    int up_delay_ms
) {
    if (!IsWindow(window)) {
        return 147;
    }
    if (count < 1 || count > 100) {
        return 148;
    }
    if (
        down_delay_ms < 10 || down_delay_ms > 500 ||
        up_delay_ms < 0 || up_delay_ms > 500
    ) {
        return 150;
    }
    synthetic_root = GetAncestor(window, GA_ROOT);
    synthetic_focus = window;
    synthetic_cursor.x = x;
    synthetic_cursor.y = y;
    if (!ClientToScreen(window, &synthetic_cursor)) {
        return 149;
    }

    update_input_hooks_safely(window, TRUE);
    PostMessageW(
        synthetic_root,
        WM_ACTIVATEAPP,
        TRUE,
        GetCurrentThreadId()
    );
    PostMessageW(
        synthetic_root, WM_ACTIVATE, WA_ACTIVE, 0
    );
    PostMessageW(window, WM_SETFOCUS, 0, 0);
    PostMessageW(
        synthetic_root,
        WM_MOUSEACTIVATE,
        (WPARAM)synthetic_root,
        MAKELPARAM(HTCLIENT, WM_LBUTTONDOWN)
    );
    for (int index = 0; index < count; ++index) {
        PostMessageW(
            window, WM_MOUSEMOVE, 0, MAKELPARAM(x, y)
        );
        synthetic_left_down = 1;
        PostMessageW(
            window,
            WM_LBUTTONDOWN,
            MK_LBUTTON,
            MAKELPARAM(x, y)
        );
        Sleep((DWORD)down_delay_ms);
        synthetic_left_down = 0;
        PostMessageW(
            window, WM_LBUTTONUP, 0, MAKELPARAM(x, y)
        );
        Sleep((DWORD)up_delay_ms);
    }
    update_input_hooks_safely(window, FALSE);
    return 0;
}

static DWORD run_wake(HWND window, int duration_ms) {
    if (!IsWindow(window)) {
        return 4;
    }
    synthetic_root = window;
    synthetic_focus = window;
    original_game_wndproc = (WNDPROC)GetWindowLongPtrW(
        window, GWLP_WNDPROC
    );
    if (original_game_wndproc == NULL) {
        return 5;
    }
    SetLastError(0);
    LONG_PTR previous = SetWindowLongPtrW(
        window,
        GWLP_WNDPROC,
        (LONG_PTR)control_game_wndproc
    );
    if (previous == 0 && GetLastError() != 0) {
        original_game_wndproc = NULL;
        return 6;
    }
    InterlockedExchange(&game_call_completed, 0);
    DWORD_PTR message_result = 0;
    BOOL sent = SendMessageTimeoutW(
        window,
        WM_CCZ_HIDDEN_ACTIVATE,
        0,
        0,
        SMTO_ABORTIFHUNG,
        3000,
        &message_result
    );
    SetWindowLongPtrW(
        window, GWLP_WNDPROC, (LONG_PTR)original_game_wndproc
    );
    original_game_wndproc = NULL;
    if (!sent || !game_call_completed) {
        return 7;
    }
    Sleep(duration_ms > 0 ? duration_ms : 1500);
    return 0;
}

static DWORD run_end_dialog(HWND window, int result) {
    if (!IsWindow(window)) {
        return 4;
    }
    original_game_wndproc = (WNDPROC)GetWindowLongPtrW(
        window, GWLP_WNDPROC
    );
    if (original_game_wndproc == NULL) {
        return 5;
    }
    SetLastError(0);
    LONG_PTR previous = SetWindowLongPtrW(
        window,
        GWLP_WNDPROC,
        (LONG_PTR)control_game_wndproc
    );
    if (previous == 0 && GetLastError() != 0) {
        original_game_wndproc = NULL;
        return 6;
    }
    DWORD_PTR message_result = 1;
    BOOL sent = SendMessageTimeoutW(
        window,
        WM_CCZ_END_DIALOG,
        (WPARAM)result,
        0,
        SMTO_ABORTIFHUNG,
        3000,
        &message_result
    );
    if (IsWindow(window)) {
        SetWindowLongPtrW(
            window, GWLP_WNDPROC, (LONG_PTR)original_game_wndproc
        );
    }
    original_game_wndproc = NULL;
    if (!sent) {
        return 7;
    }
    return (DWORD)message_result;
}

static DWORD run_game_call(int slot, UINT message, BOOL is_load) {
    HWND window = find_game_window();
    if (window == NULL) {
        return 12;
    }
    InterlockedExchange(&allow_game_foreground, 1);
    remove_hook(&foreground_window_hook);
    SetForegroundWindow(window);
    SetActiveWindow(window);
    install_hook(
        &foreground_window_hook,
        "SetForegroundWindow",
        hooked_set_foreground_window
    );
    original_game_wndproc = (WNDPROC)GetWindowLongPtrW(
        window, GWLP_WNDPROC
    );
    if (original_game_wndproc == NULL) {
        return 13;
    }
    SetLastError(0);
    LONG_PTR previous = SetWindowLongPtrW(
        window,
        GWLP_WNDPROC,
        (LONG_PTR)control_game_wndproc
    );
    if (previous == 0 && GetLastError() != 0) {
        original_game_wndproc = NULL;
        return 14;
    }

    game_call_result = 0;
    InterlockedExchange(&game_call_completed, 0);
    if (!PostMessageW(window, message, (WPARAM)slot, 0)) {
        SetWindowLongPtrW(
            window, GWLP_WNDPROC, (LONG_PTR)original_game_wndproc
        );
        original_game_wndproc = NULL;
        return 15;
    }

    DWORD elapsed = 0;
    while (
        InterlockedCompareExchange(
            &game_call_completed, 0, 0
        ) == 0 &&
        elapsed < 15000
    ) {
        Sleep(10);
        elapsed += 10;
    }
    SetWindowLongPtrW(
        window, GWLP_WNDPROC, (LONG_PTR)original_game_wndproc
    );
    original_game_wndproc = NULL;
    if (game_call_completed == 0) {
        InterlockedExchange(&allow_game_foreground, 0);
        return 16;
    }
    Sleep(
        message == WM_CCZ_GAME_MOUSE ||
        message == WM_CCZ_ENABLE_ACCELERATION
            ? 10
            : 1800
    );
    if (
        guarded_foreground != NULL &&
        IsWindow(guarded_foreground)
    ) {
        remove_hook(&foreground_window_hook);
        SetForegroundWindow(guarded_foreground);
        install_hook(
            &foreground_window_hook,
            "SetForegroundWindow",
            hooked_set_foreground_window
        );
    }
    InterlockedExchange(&allow_game_foreground, 0);
    if (message == WM_CCZ_GAME_FRAME_CLICK) {
        return game_call_result == 1 ? 0 : game_call_result;
    }
    if (!is_load) {
        return game_call_result == 1 ? 0 : 17;
    }
    return game_call_result == 1 ? 0 : 17;
}

static DWORD run_start_game_loop(void) {
    HWND window = find_game_window();
    if (window == NULL) {
        return 131;
    }
    original_game_wndproc = (WNDPROC)GetWindowLongPtrW(
        window, GWLP_WNDPROC
    );
    if (original_game_wndproc == NULL) {
        return 132;
    }
    SetLastError(0);
    LONG_PTR previous = SetWindowLongPtrW(
        window,
        GWLP_WNDPROC,
        (LONG_PTR)control_game_wndproc
    );
    if (previous == 0 && GetLastError() != 0) {
        original_game_wndproc = NULL;
        return 133;
    }
    game_call_result = 0;
    InterlockedExchange(&game_call_completed, 0);
    if (!PostMessageW(window, WM_CCZ_START_GAME_LOOP, 0, 0)) {
        SetWindowLongPtrW(
            window, GWLP_WNDPROC, (LONG_PTR)original_game_wndproc
        );
        original_game_wndproc = NULL;
        return 134;
    }
    DWORD elapsed = 0;
    while (
        InterlockedCompareExchange(
            &game_call_completed, 0, 0
        ) == 0 &&
        elapsed < 5000
    ) {
        Sleep(10);
        elapsed += 10;
    }
    if (game_call_completed == 0) {
        SetWindowLongPtrW(
            window, GWLP_WNDPROC, (LONG_PTR)original_game_wndproc
        );
        original_game_wndproc = NULL;
        return 135;
    }
    return game_call_result == 1 ? 0 : game_call_result;
}

static DWORD run_open_load_dialog(void) {
    HWND window = find_game_window();
    if (window == NULL) {
        return 50;
    }
    original_game_wndproc = (WNDPROC)GetWindowLongPtrW(
        window, GWLP_WNDPROC
    );
    if (original_game_wndproc == NULL) {
        return 51;
    }
    SetLastError(0);
    LONG_PTR previous = SetWindowLongPtrW(
        window,
        GWLP_WNDPROC,
        (LONG_PTR)control_game_wndproc
    );
    if (previous == 0 && GetLastError() != 0) {
        original_game_wndproc = NULL;
        return 52;
    }
    game_call_result = 0;
    InterlockedExchange(&game_call_completed, 0);
    if (!PostMessageW(window, WM_CCZ_OPEN_LOAD_DIALOG, 0, 0)) {
        SetWindowLongPtrW(
            window, GWLP_WNDPROC, (LONG_PTR)original_game_wndproc
        );
        original_game_wndproc = NULL;
        return 53;
    }
    DWORD elapsed = 0;
    while (
        InterlockedCompareExchange(
            &game_call_completed, 0, 0
        ) == 0 &&
        elapsed < 60000
    ) {
        Sleep(20);
        elapsed += 20;
    }
    SetWindowLongPtrW(
        window, GWLP_WNDPROC, (LONG_PTR)original_game_wndproc
    );
    original_game_wndproc = NULL;
    return game_call_completed ? 0 : 54;
}

static DWORD WINAPI select_real_load_item(LPVOID parameter) {
    int item_index = (int)(INT_PTR)parameter;
    append_control_log("selector-start");
    DWORD deadline = GetTickCount() + 10000;
    HWND dialog = NULL;
    while ((LONG)(deadline - GetTickCount()) > 0) {
        dialog = find_list_dialog();
        if (dialog != NULL) {
            break;
        }
        Sleep(20);
    }
    if (dialog == NULL) {
        append_control_log("selector-no-dialog");
        return 55;
    }
    append_control_log("selector-dialog");
    DWORD result = run_load_dialog_item(item_index, 0);
    append_control_log(
        result == 0 ? "selector-click-ok" : "selector-click-fail"
    );
    if (result != 0) {
        char text[64];
        sprintf(text, "selector-result-%lu", result);
        append_control_log(text);
    }
    return result;
}

static DWORD run_real_load(int item_index) {
    append_control_log("real-load-start");
    HANDLE select_thread = CreateThread(
        NULL,
        0,
        select_real_load_item,
        (LPVOID)(INT_PTR)item_index,
        0,
        NULL
    );
    if (select_thread == NULL) {
        return 56;
    }
    DWORD result = run_open_load_dialog();
    append_control_log(result == 0 ? "openload-ok" : "openload-fail");
    DWORD select_result = 57;
    if (WaitForSingleObject(select_thread, 12000) == WAIT_OBJECT_0) {
        GetExitCodeThread(select_thread, &select_result);
    }
    CloseHandle(select_thread);
    load_dialog_to_confirm = NULL;
    append_control_log(select_result == 0 ? "real-load-ok" : "real-load-select-fail");
    if (result != 0) {
        return result;
    }
    return select_result;
}

static DWORD run_title_load(int item_index) {
    HWND window = find_game_window();
    if (window == NULL) {
        return 136;
    }
    DWORD window_thread_id = GetWindowThreadProcessId(window, NULL);
    HANDLE window_thread = OpenThread(
        THREAD_SUSPEND_RESUME, FALSE, window_thread_id
    );
    if (window_thread == NULL) {
        return 137;
    }

    TemporaryCodePatch mouse_patch;
    TemporaryCodePatch click_patch;
    ZeroMemory(&mouse_patch, sizeof(mouse_patch));
    ZeroMemory(&click_patch, sizeof(click_patch));

    SuspendThread(window_thread);
    BOOL mouse_ok = patch_mouse_coordinates(
        GAME_TITLE_MOUSE_POSITION_ADDRESS, 0x200, 0xA8, &mouse_patch
    );
    BOOL click_ok = mouse_ok && patch_return_constant(
        GAME_TITLE_CLICK_TEST_ADDRESS, 1, 8, &click_patch
    );
    ResumeThread(window_thread);

    if (!click_ok) {
        SuspendThread(window_thread);
        restore_code_patch(&click_patch);
        restore_code_patch(&mouse_patch);
        ResumeThread(window_thread);
        CloseHandle(window_thread);
        return 138;
    }

    DWORD deadline = GetTickCount() + 10000;
    HWND dialog = NULL;
    while ((LONG)(deadline - GetTickCount()) > 0) {
        dialog = find_list_dialog();
        if (dialog != NULL) {
            break;
        }
        Sleep(10);
    }

    SuspendThread(window_thread);
    restore_code_patch(&click_patch);
    restore_code_patch(&mouse_patch);
    ResumeThread(window_thread);
    CloseHandle(window_thread);

    if (dialog == NULL) {
        return 139;
    }
    return run_load_dialog_item(item_index, 0);
}

static DWORD run_pulse_click(int x, int y) {
    HWND window = find_game_window();
    if (window == NULL) {
        return 140;
    }
    DWORD window_thread_id = GetWindowThreadProcessId(window, NULL);
    HANDLE window_thread = OpenThread(
        THREAD_SUSPEND_RESUME, FALSE, window_thread_id
    );
    if (window_thread == NULL) {
        return 141;
    }

    TemporaryCodePatch mouse_patch;
    TemporaryCodePatch action_patch;
    ZeroMemory(&mouse_patch, sizeof(mouse_patch));
    ZeroMemory(&action_patch, sizeof(action_patch));
    SuspendThread(window_thread);
    BOOL mouse_ok = patch_mouse_coordinates(
        GAME_TITLE_MOUSE_POSITION_ADDRESS,
        (DWORD)x,
        (DWORD)y,
        &mouse_patch
    );
    BOOL action_ok = mouse_ok && patch_return_constant(
        GAME_READ_MOUSE_ACTION_FUNCTION_ADDRESS,
        1,
        0,
        &action_patch
    );
    ResumeThread(window_thread);

    if (!action_ok) {
        SuspendThread(window_thread);
        restore_code_patch(&action_patch);
        restore_code_patch(&mouse_patch);
        ResumeThread(window_thread);
        CloseHandle(window_thread);
        return 142;
    }

    PostMessageW(
        window, WM_ACTIVATEAPP, TRUE, GetCurrentThreadId()
    );
    PostMessageW(window, WM_ACTIVATE, WA_ACTIVE, 0);
    PostMessageW(window, WM_SETFOCUS, 0, 0);
    PostMessageW(window, WM_NULL, 0, 0);
    Sleep(160);

    SuspendThread(window_thread);
    restore_code_patch(&action_patch);
    restore_code_patch(&mouse_patch);
    ResumeThread(window_thread);
    CloseHandle(window_thread);
    return 0;
}

static DWORD arm_first_choice(void) {
    HWND window = find_game_window();
    if (window == NULL) {
        return 143;
    }
    DWORD window_thread_id = GetWindowThreadProcessId(window, NULL);
    HANDLE window_thread = OpenThread(
        THREAD_SUSPEND_RESUME, FALSE, window_thread_id
    );
    if (window_thread == NULL) {
        return 144;
    }

    SuspendThread(window_thread);
    BOOL installed = first_choice_hook.installed ||
        install_address_hook(
            &first_choice_hook,
            GAME_CHOICE_FINALIZE_ADDRESS,
            force_first_choice_hook
        );
    if (installed) {
        InterlockedExchange(&force_first_choice, 1);
    }
    ResumeThread(window_thread);
    CloseHandle(window_thread);
    return installed ? 0 : 145;
}

static DWORD run_pulse_burst(int x, int y, int count) {
    if (count < 1 || count > 500) {
        return 146;
    }
    for (int index = 0; index < count; ++index) {
        DWORD result = run_pulse_click(x, y);
        if (result != 0) {
            return result;
        }
        Sleep(20);
    }
    return 0;
}

static DWORD run_direct_load(int slot) {
    BYTE *state_reader = (BYTE *)(UINT_PTR)
        GAME_LOAD_MODAL_STATE_ADDRESS;
    BYTE original[6];
    DWORD old_protection = 0;
    BOOL patched = FALSE;
    if (VirtualProtect(
            state_reader,
            sizeof(original),
            PAGE_EXECUTE_READWRITE,
            &old_protection
        )) {
        memcpy(original, state_reader, sizeof(original));
        state_reader[0] = 0xB8;
        *(DWORD *)(state_reader + 1) = 3;
        state_reader[5] = 0xC3;
        FlushInstructionCache(
            GetCurrentProcess(),
            state_reader,
            sizeof(original)
        );
        patched = TRUE;
    }
    DWORD result = run_game_call(slot, WM_CCZ_DIRECT_LOAD, TRUE);
    if (patched) {
        DWORD ignored = 0;
        memcpy(state_reader, original, sizeof(original));
        FlushInstructionCache(
            GetCurrentProcess(),
            state_reader,
            sizeof(original)
        );
        VirtualProtect(
            state_reader,
            sizeof(original),
            old_protection,
            &ignored
        );
    }
    return result;
}

static DWORD run_direct_save(int slot) {
    return run_game_call(slot, WM_CCZ_DIRECT_SAVE, FALSE);
}

static DWORD run_game_event(int event_type, int event_value) {
    DWORD packed = MAKELONG(
        event_type & 0xFFFF, event_value & 0xFFFF
    );
    return run_game_call(
        (int)packed, WM_CCZ_REAL_RANDOM, FALSE
    );
}

static DWORD run_confirm_selection(int x, int y) {
    DWORD packed = MAKELONG(x & 0xFFFF, y & 0xFFFF);
    return run_game_call(
        (int)packed, WM_CCZ_CONFIRM_SELECTION, FALSE
    );
}

static DWORD run_game_mouse(UINT message, int x, int y) {
    requested_mouse_message = message;
    requested_mouse_x = x;
    requested_mouse_y = y;
    return run_game_call(0, WM_CCZ_GAME_MOUSE, FALSE);
}

static DWORD run_game_frame_click(int x, int y) {
    requested_mouse_x = x;
    requested_mouse_y = y;
    return run_game_call(0, WM_CCZ_GAME_FRAME_CLICK, FALSE);
}

static DWORD run_enable_acceleration(void) {
    return run_game_call(
        0, WM_CCZ_ENABLE_ACCELERATION, FALSE
    );
}

static DWORD run_list_item(int item_index) {
    HWND dialog = find_list_dialog();
    if (dialog == NULL) {
        return 2;
    }
    HWND list = FindWindowExW(
        dialog, NULL, L"SysListView32", NULL
    );
    if (list == NULL) {
        return 3;
    }
    ListView_SetItemState(
        list,
        item_index,
        LVIS_SELECTED | LVIS_FOCUSED,
        LVIS_SELECTED | LVIS_FOCUSED
    );
    ListView_SetSelectionMark(list, item_index);
    ListView_EnsureVisible(list, item_index, FALSE);
    Sleep(80);

    RECT item_rect;
    if (!ListView_GetItemRect(
            list, item_index, &item_rect, LVIR_BOUNDS
        )) {
        return 7;
    }
    RECT client_rect;
    GetClientRect(list, &client_rect);
    int click_x = 230;
    if (click_x >= client_rect.right) {
        click_x = client_rect.right - 10;
    }
    if (click_x < 10) {
        click_x = 10;
    }
    int click_y = (item_rect.top + item_rect.bottom) / 2;
    post_synthetic_click(list, click_x, click_y, 1, FALSE);
    return 0;
}

static DWORD notify_list_item(int item_index) {
    HWND dialog = find_list_dialog();
    if (dialog == NULL) {
        return 43;
    }
    HWND list = FindWindowExW(
        dialog, NULL, L"SysListView32", NULL
    );
    if (list == NULL) {
        return 44;
    }
    ListView_SetItemState(
        list,
        -1,
        0,
        LVIS_SELECTED | LVIS_FOCUSED
    );
    ListView_SetItemState(
        list,
        item_index,
        LVIS_SELECTED | LVIS_FOCUSED,
        LVIS_SELECTED | LVIS_FOCUSED
    );
    ListView_SetSelectionMark(list, item_index);
    ListView_EnsureVisible(list, item_index, FALSE);

    NMITEMACTIVATE notification;
    ZeroMemory(&notification, sizeof(notification));
    notification.hdr.hwndFrom = list;
    notification.hdr.idFrom = GetDlgCtrlID(list);
    notification.hdr.code = NM_CLICK;
    notification.iItem = item_index;
    notification.iSubItem = 1;
    notification.iSubItem = 1;
    RECT rect;
    if (ListView_GetItemRect(
            list, item_index, &rect, LVIR_BOUNDS
        )) {
        notification.ptAction.x =
            (rect.left + rect.right) / 2;
        notification.ptAction.y =
            (rect.top + rect.bottom) / 2;
    }
    SendMessageW(
        dialog,
        WM_NOTIFY,
        notification.hdr.idFrom,
        (LPARAM)&notification
    );
    notification.hdr.code = NM_DBLCLK;
    SendMessageW(
        dialog,
        WM_NOTIFY,
        notification.hdr.idFrom,
        (LPARAM)&notification
    );
    notification.hdr.code = LVN_ITEMACTIVATE;
    SendMessageW(
        dialog,
        WM_NOTIFY,
        notification.hdr.idFrom,
        (LPARAM)&notification
    );
    return 0;
}

static DWORD dump_list_items(void) {
    HWND dialog = find_list_dialog();
    if (dialog == NULL) {
        return 82;
    }
    HWND list = FindWindowExW(
        dialog, NULL, L"SysListView32", NULL
    );
    if (list == NULL) {
        return 83;
    }
    WCHAR path[MAX_PATH];
    GetTempPathW(MAX_PATH, path);
    lstrcatW(path, L"ccz_list_items.log");
    FILE *file = _wfopen(path, L"w, ccs=UTF-8");
    if (file == NULL) {
        return 84;
    }
    int count = ListView_GetItemCount(list);
    for (int index = 0; index < count; ++index) {
        WCHAR text[512];
        text[0] = L'\0';
        ListView_GetItemText(
            list, index, 0, text, ARRAYSIZE(text)
        );
        fwprintf(file, L"%d\t%s\n", index, text);
    }
    fclose(file);
    return 0;
}

static DWORD dialog_double_click_item(int item_index) {
    HWND dialog = find_list_dialog();
    if (dialog == NULL) return 85;
    HWND list = FindWindowExW(
        dialog, NULL, L"SysListView32", NULL
    );
    if (list == NULL) return 86;
    RECT rect;
    if (!ListView_GetItemRect(
            list, item_index, &rect, LVIR_BOUNDS
        )) return 87;
    LPARAM point = MAKELPARAM(
        (rect.left + rect.right) / 2,
        (rect.top + rect.bottom) / 2
    );
    ListView_SetItemState(
        list, -1, 0, LVIS_SELECTED | LVIS_FOCUSED
    );
    ListView_SetItemState(
        list, item_index,
        LVIS_SELECTED | LVIS_FOCUSED,
        LVIS_SELECTED | LVIS_FOCUSED
    );
    SendMessageW(
        list, WM_LBUTTONDBLCLK, MK_LBUTTON, point
    );
    return 0;
}

static DWORD dialog_enter_item(int item_index) {
    HWND dialog = find_list_dialog();
    if (dialog == NULL) return 88;
    HWND list = FindWindowExW(dialog, NULL, L"SysListView32", NULL);
    if (list == NULL) return 89;
    ListView_SetItemState(
        list, -1, 0, LVIS_SELECTED | LVIS_FOCUSED
    );
    ListView_SetItemState(
        list, item_index,
        LVIS_SELECTED | LVIS_FOCUSED,
        LVIS_SELECTED | LVIS_FOCUSED
    );
    ListView_SetSelectionMark(list, item_index);
    SetFocus(list);
    SendMessageW(list, WM_KEYDOWN, VK_RETURN, 0);
    SendMessageW(list, WM_KEYUP, VK_RETURN, 0);
    SendMessageW(dialog, WM_KEYDOWN, VK_RETURN, 0);
    SendMessageW(dialog, WM_KEYUP, VK_RETURN, 0);
    return 0;
}

static DWORD dialog_notify_double_click(int item_index) {
    HWND dialog = find_list_dialog();
    if (dialog == NULL) return 90;
    HWND list = FindWindowExW(dialog, NULL, L"SysListView32", NULL);
    if (list == NULL) return 91;
    RECT rect;
    if (!ListView_GetItemRect(list, item_index, &rect, LVIR_BOUNDS)) {
        return 92;
    }
    ListView_SetItemState(
        list, -1, 0, LVIS_SELECTED | LVIS_FOCUSED
    );
    ListView_SetItemState(
        list, item_index,
        LVIS_SELECTED | LVIS_FOCUSED,
        LVIS_SELECTED | LVIS_FOCUSED
    );
    ListView_SetSelectionMark(list, item_index);
    NMITEMACTIVATE notification;
    ZeroMemory(&notification, sizeof(notification));
    notification.hdr.hwndFrom = list;
    notification.hdr.idFrom = (UINT_PTR)GetDlgCtrlID(list);
    notification.hdr.code = NM_DBLCLK;
    notification.iItem = item_index;
    notification.iSubItem = 0;
    notification.ptAction.x = (rect.left + rect.right) / 2;
    notification.ptAction.y = (rect.top + rect.bottom) / 2;
    SendMessageW(
        dialog,
        WM_NOTIFY,
        notification.hdr.idFrom,
        (LPARAM)&notification
    );
    return 0;
}

static DWORD dialog_window_double_click(int item_index) {
    HWND dialog = find_list_dialog();
    if (dialog == NULL) return 93;
    HWND list = FindWindowExW(dialog, NULL, L"SysListView32", NULL);
    if (list == NULL) return 94;
    RECT rect;
    if (!ListView_GetItemRect(list, item_index, &rect, LVIR_BOUNDS)) {
        return 95;
    }
    POINT point = {
        (rect.left + rect.right) / 2,
        (rect.top + rect.bottom) / 2
    };
    ClientToScreen(list, &point);
    ScreenToClient(dialog, &point);
    LPARAM packed = MAKELPARAM(point.x, point.y);
    SendMessageW(dialog, WM_LBUTTONDOWN, MK_LBUTTON, packed);
    SendMessageW(dialog, WM_LBUTTONUP, 0, packed);
    SendMessageW(dialog, WM_LBUTTONDBLCLK, MK_LBUTTON, packed);
    SendMessageW(dialog, WM_LBUTTONUP, 0, packed);
    return 0;
}

static DWORD dialog_accessible_default(int item_index) {
    HWND dialog = find_list_dialog();
    if (dialog == NULL) return 96;
    HWND list = FindWindowExW(dialog, NULL, L"SysListView32", NULL);
    if (list == NULL) return 97;
    IAccessible *accessible = NULL;
    HRESULT result = AccessibleObjectFromWindow(
        list,
        OBJID_CLIENT,
        &IID_IAccessible,
        (void **)&accessible
    );
    if (FAILED(result) || accessible == NULL) {
        return 98;
    }
    VARIANT child;
    VariantInit(&child);
    child.vt = VT_I4;
    child.lVal = item_index + 1;
    result = accessible->lpVtbl->accDoDefaultAction(
        accessible, child
    );
    accessible->lpVtbl->Release(accessible);
    return SUCCEEDED(result) ? 0 : 99;
}

static DWORD real_list_item(int item_index) {
    HWND dialog = find_list_dialog();
    if (dialog == NULL) {
        return 45;
    }
    activate_hidden_desktop_window(dialog);
    HWND list = FindWindowExW(
        dialog, NULL, L"SysListView32", NULL
    );
    if (list == NULL) {
        return 46;
    }
    ListView_SetItemState(
        list,
        -1,
        0,
        LVIS_SELECTED | LVIS_FOCUSED
    );
    ListView_SetItemState(
        list,
        item_index,
        LVIS_SELECTED | LVIS_FOCUSED,
        LVIS_SELECTED | LVIS_FOCUSED
    );
    ListView_SetSelectionMark(list, item_index);
    ListView_EnsureVisible(list, item_index, FALSE);
    Sleep(100);
    RECT rect;
    if (!ListView_GetItemRect(
            list, item_index, &rect, LVIR_BOUNDS
        )) {
        return 47;
    }
    POINT point;
    point.x = (rect.left + rect.right) / 2;
    point.y = (rect.top + rect.bottom) / 2;
    LPARAM packed_point = MAKELPARAM(point.x, point.y);
    PostMessageW(list, WM_MOUSEMOVE, 0, packed_point);
    PostMessageW(list, WM_LBUTTONDOWN, MK_LBUTTON, packed_point);
    PostMessageW(list, WM_LBUTTONUP, 0, packed_point);
    PostMessageW(list, WM_LBUTTONDBLCLK, MK_LBUTTON, packed_point);
    PostMessageW(list, WM_LBUTTONUP, 0, packed_point);
    Sleep(150);
    return 0;
}

static DWORD activate_list_window_item(HWND dialog, int item_index) {
    if (!IsWindow(dialog)) return 160;
    HWND list = FindWindowExW(dialog, NULL, L"SysListView32", NULL);
    if (list == NULL) return 161;
    RECT rect;
    if (!ListView_GetItemRect(list, item_index, &rect, LVIR_BOUNDS)) {
        return 162;
    }
    ListView_SetItemState(
        list, -1, 0, LVIS_SELECTED | LVIS_FOCUSED
    );
    ListView_SetItemState(
        list, item_index,
        LVIS_SELECTED | LVIS_FOCUSED,
        LVIS_SELECTED | LVIS_FOCUSED
    );
    ListView_SetSelectionMark(list, item_index);
    SetFocus(list);
    post_synthetic_click(
        list,
        (rect.left + rect.right) / 2,
        (rect.top + rect.bottom) / 2,
        1,
        FALSE
    );
    NMITEMACTIVATE notification;
    ZeroMemory(&notification, sizeof(notification));
    notification.hdr.hwndFrom = list;
    notification.hdr.idFrom = (UINT_PTR)GetDlgCtrlID(list);
    notification.hdr.code = NM_CLICK;
    notification.iItem = item_index;
    notification.iSubItem = 0;
    notification.ptAction.x = (rect.left + rect.right) / 2;
    notification.ptAction.y = (rect.top + rect.bottom) / 2;
    SendMessageW(
        dialog,
        WM_NOTIFY,
        notification.hdr.idFrom,
        (LPARAM)&notification
    );
    Sleep(300);
    return 0;
}

static DWORD run_load_dialog_item(
    int item_index, DWORD dialog_object_hint
) {
    HWND dialog = find_list_dialog();
    if (dialog == NULL) {
        return 18;
    }
    BYTE *dialog_object = (BYTE *)(UINT_PTR)dialog_object_hint;
    if (
        dialog_object != NULL &&
        (
            *(DWORD *)dialog_object != 0x00486668 ||
            *(HWND *)(dialog_object + 12) != dialog
        )
    ) {
        dialog_object = NULL;
    }
    SYSTEM_INFO system_info;
    GetSystemInfo(&system_info);
    BYTE *address = (BYTE *)system_info.lpMinimumApplicationAddress;
    BYTE *maximum = (BYTE *)system_info.lpMaximumApplicationAddress;
    while (address < maximum) {
        MEMORY_BASIC_INFORMATION info;
        SIZE_T queried = VirtualQuery(
            address, &info, sizeof(info)
        );
        if (queried == 0) {
            break;
        }
        DWORD protection = info.Protect & 0xff;
        BOOL readable =
            protection == PAGE_READONLY ||
            protection == PAGE_READWRITE ||
            protection == PAGE_WRITECOPY ||
            protection == PAGE_EXECUTE_READ ||
            protection == PAGE_EXECUTE_READWRITE ||
            protection == PAGE_EXECUTE_WRITECOPY;
        if (
            info.State == MEM_COMMIT &&
            readable &&
            (info.Protect & PAGE_GUARD) == 0
        ) {
            BYTE *region = (BYTE *)info.BaseAddress;
            BYTE *cursor = region;
            BYTE *end = region + info.RegionSize;
            while (cursor + 16 <= end) {
                BYTE *candidate = (BYTE *)memchr(
                    cursor,
                    0x68,
                    (SIZE_T)(end - cursor - 15)
                );
                if (candidate == NULL) {
                    break;
                }
                if (
                    ((ULONG_PTR)candidate & 3) == 0 &&
                    *(HWND *)(candidate + 12) == dialog
                ) {
                    if (*(DWORD *)candidate == 0x00486668) {
                        dialog_object = candidate;
                        break;
                    }
                    static int logged_candidates = 0;
                    if (logged_candidates < 8) {
                        logged_candidates++;
                        append_control_log(
                            "dialog-object-other-vtable"
                        );
                    }
                }
                cursor = candidate + 1;
            }
        }
        if (dialog_object != NULL) {
            break;
        }
        address = (BYTE *)info.BaseAddress + info.RegionSize;
    }
    if (dialog_object == NULL) {
        return 19;
    }

    DWORD *dialog_mode_field = (DWORD *)(
        (BYTE *)dialog_object + 0x664
    );
    DWORD dialog_mode_original = *dialog_mode_field;
    {
        char text[96];
        sprintf(
            text,
            "dialog-object-mode-%lu",
            dialog_mode_original
        );
        append_control_log(text);
    }
    /*
     * The same dialog class is reused for save and load.  The list
     * window object found from the native load dialog can retain the
     * save-mode bit from the previous invocation; force the native
     * handler down its load branch for this call and restore it after.
     */
    *dialog_mode_field = 0;
    dialog_object_to_load = dialog_object;
    dialog_item_to_load = item_index;
    original_game_wndproc = (WNDPROC)GetWindowLongPtrW(
        dialog, GWLP_WNDPROC
    );
    if (original_game_wndproc == NULL) {
        return 20;
    }
    SetLastError(0);
    LONG_PTR previous = SetWindowLongPtrW(
        dialog,
        GWLP_WNDPROC,
        (LONG_PTR)control_game_wndproc
    );
    if (previous == 0 && GetLastError() != 0) {
        original_game_wndproc = NULL;
        return 21;
    }
    game_call_result = 0;
    InterlockedExchange(&game_call_completed, 0);
    DWORD_PTR message_result = 0;
    if (!SendMessageTimeoutW(
            dialog,
            WM_CCZ_DIALOG_LOAD,
            0,
            0,
            SMTO_ABORTIFHUNG,
            5000,
            &message_result
        )) {
        SetWindowLongPtrW(
            dialog, GWLP_WNDPROC, (LONG_PTR)original_game_wndproc
        );
        original_game_wndproc = NULL;
        *dialog_mode_field = dialog_mode_original;
        return 22;
    }
    if (IsWindow(dialog)) {
        SetWindowLongPtrW(
            dialog, GWLP_WNDPROC, (LONG_PTR)original_game_wndproc
        );
    }
    original_game_wndproc = NULL;
    dialog_object_to_load = NULL;
    return game_call_completed ? (
        game_call_result == 5 ? 0 : 30 + game_call_result
    ) : 23;
}

typedef HANDLE (WINAPI *CreateFileAFunction)(
    LPCSTR, DWORD, DWORD, LPSECURITY_ATTRIBUTES, DWORD, DWORD, HANDLE
);
typedef HANDLE (WINAPI *CreateFileWFunction)(
    LPCWSTR, DWORD, DWORD, LPSECURITY_ATTRIBUTES, DWORD, DWORD, HANDLE
);

static CreateFileAFunction original_create_file_a = NULL;
static CreateFileWFunction original_create_file_w = NULL;

static BOOL is_muted_audio_path_a(LPCSTR path) {
    if (path == NULL) {
        return FALSE;
    }
    const char *extension = strrchr(path, '.');
    if (extension == NULL) {
        return FALSE;
    }
    return (
        _stricmp(extension, ".wav") == 0 ||
        _stricmp(extension, ".mid") == 0 ||
        _stricmp(extension, ".midi") == 0 ||
        _stricmp(extension, ".mp3") == 0 ||
        _stricmp(extension, ".ogg") == 0 ||
        _stricmp(extension, ".wma") == 0
    );
}

static BOOL is_muted_audio_path_w(LPCWSTR path) {
    if (path == NULL) {
        return FALSE;
    }
    const wchar_t *extension = wcsrchr(path, L'.');
    if (extension == NULL) {
        return FALSE;
    }
    return (
        _wcsicmp(extension, L".wav") == 0 ||
        _wcsicmp(extension, L".mid") == 0 ||
        _wcsicmp(extension, L".midi") == 0 ||
        _wcsicmp(extension, L".mp3") == 0 ||
        _wcsicmp(extension, L".ogg") == 0 ||
        _wcsicmp(extension, L".wma") == 0
    );
}

static HANDLE WINAPI muted_create_file_a(
    LPCSTR file_name,
    DWORD desired_access,
    DWORD share_mode,
    LPSECURITY_ATTRIBUTES security_attributes,
    DWORD creation_disposition,
    DWORD flags_and_attributes,
    HANDLE template_file
) {
    if (
        (desired_access & GENERIC_READ) != 0 &&
        is_muted_audio_path_a(file_name)
    ) {
        SetLastError(ERROR_FILE_NOT_FOUND);
        return INVALID_HANDLE_VALUE;
    }
    return original_create_file_a(
        file_name,
        desired_access,
        share_mode,
        security_attributes,
        creation_disposition,
        flags_and_attributes,
        template_file
    );
}

static HANDLE WINAPI muted_create_file_w(
    LPCWSTR file_name,
    DWORD desired_access,
    DWORD share_mode,
    LPSECURITY_ATTRIBUTES security_attributes,
    DWORD creation_disposition,
    DWORD flags_and_attributes,
    HANDLE template_file
) {
    if (
        (desired_access & GENERIC_READ) != 0 &&
        is_muted_audio_path_w(file_name)
    ) {
        SetLastError(ERROR_FILE_NOT_FOUND);
        return INVALID_HANDLE_VALUE;
    }
    return original_create_file_w(
        file_name,
        desired_access,
        share_mode,
        security_attributes,
        creation_disposition,
        flags_and_attributes,
        template_file
    );
}

static BOOL patch_import(
    HMODULE module,
    const char *function_name,
    PROC replacement,
    PROC *original
) {
    BYTE *base = (BYTE *)module;
    IMAGE_DOS_HEADER *dos_header = (IMAGE_DOS_HEADER *)base;
    if (dos_header->e_magic != IMAGE_DOS_SIGNATURE) {
        return FALSE;
    }
    IMAGE_NT_HEADERS *nt_headers = (
        IMAGE_NT_HEADERS *)(base + dos_header->e_lfanew);
    if (nt_headers->Signature != IMAGE_NT_SIGNATURE) {
        return FALSE;
    }
    DWORD import_rva = nt_headers->OptionalHeader.DataDirectory[
        IMAGE_DIRECTORY_ENTRY_IMPORT
    ].VirtualAddress;
    if (import_rva == 0) {
        return FALSE;
    }

    IMAGE_IMPORT_DESCRIPTOR *descriptor = (
        IMAGE_IMPORT_DESCRIPTOR *)(base + import_rva);
    for (; descriptor->Name != 0; descriptor++) {
        if (descriptor->OriginalFirstThunk == 0) {
            continue;
        }
        IMAGE_THUNK_DATA *lookup = (
            IMAGE_THUNK_DATA *)(base + descriptor->OriginalFirstThunk);
        IMAGE_THUNK_DATA *address = (
            IMAGE_THUNK_DATA *)(base + descriptor->FirstThunk);
        for (; lookup->u1.AddressOfData != 0; lookup++, address++) {
            if (IMAGE_SNAP_BY_ORDINAL(lookup->u1.Ordinal)) {
                continue;
            }
            IMAGE_IMPORT_BY_NAME *import_name = (
                IMAGE_IMPORT_BY_NAME *)(base + lookup->u1.AddressOfData);
            if (strcmp((char *)import_name->Name, function_name) != 0) {
                continue;
            }
            DWORD old_protection = 0;
            if (!VirtualProtect(
                    &address->u1.Function,
                    sizeof(address->u1.Function),
                    PAGE_READWRITE,
                    &old_protection
                )) {
                return FALSE;
            }
            *original = (PROC)(UINT_PTR)address->u1.Function;
            address->u1.Function = (ULONG_PTR)replacement;
            DWORD ignored = 0;
            VirtualProtect(
                &address->u1.Function,
                sizeof(address->u1.Function),
                old_protection,
                &ignored
            );
            FlushInstructionCache(
                GetCurrentProcess(),
                &address->u1.Function,
                sizeof(address->u1.Function)
            );
            return TRUE;
        }
    }
    return FALSE;
}

static DWORD install_audio_mute_hooks(void) {
    HMODULE executable = GetModuleHandleW(NULL);
    BOOL patched_a = original_create_file_a != NULL;
    BOOL patched_w = original_create_file_w != NULL;
    if (!patched_a) {
        patched_a = patch_import(
            executable,
            "CreateFileA",
            (PROC)muted_create_file_a,
            (PROC *)&original_create_file_a
        );
    }
    if (!patched_w) {
        patched_w = patch_import(
            executable,
            "CreateFileW",
            (PROC)muted_create_file_w,
            (PROC *)&original_create_file_w
        );
    }
    return patched_a || patched_w ? 0 : 160;
}

__declspec(dllexport) DWORD WINAPI ControlAction(LPVOID parameter) {
    ControlRequest request = *(ControlRequest *)parameter;
    if (request.action == ACTION_LIST_ITEM) {
        return run_list_item(request.item_index);
    }
    if (request.action == ACTION_CLICK) {
        HWND window = (HWND)(UINT_PTR)request.window;
        if (!IsWindow(window)) {
            return 4;
        }
        post_synthetic_click(
            window,
            request.x,
            request.y,
            request.count > 0 ? request.count : 1,
            request.right != 0
        );
        return 0;
    }
    if (request.action == ACTION_GUARD) {
        return start_guard();
    }
    if (request.action == ACTION_WAKE) {
        return run_wake(
            (HWND)(UINT_PTR)request.window,
            request.count
        );
    }
    if (request.action == ACTION_DIRECT_LOAD) {
        return run_direct_load(request.item_index);
    }
    if (request.action == ACTION_DIRECT_SAVE) {
        return run_direct_save(request.item_index);
    }
    if (request.action == ACTION_LOAD_DIALOG_ITEM) {
        return run_load_dialog_item(
            request.item_index, request.window
        );
    }
    if (request.action == ACTION_CLOSE_LIST_DIALOG) {
        HWND dialog = find_list_dialog();
        if (dialog == NULL) {
            return 24;
        }
        return EndDialog(
            dialog, request.item_index
        ) ? 0 : 25;
    }
    if (request.action == ACTION_END_DIALOG) {
        HWND dialog = (HWND)(UINT_PTR)request.window;
        return run_end_dialog(dialog, request.item_index);
    }
    if (request.action == ACTION_MUTE_AUDIO) {
        return install_audio_mute_hooks();
    }
    if (request.action == ACTION_TIMED_SILENT_CLICK) {
        HWND window = request.window != 0
            ? (HWND)(UINT_PTR)request.window
            : find_game_window();
        return post_silent_click_timed(
            window,
            request.x,
            request.y,
            request.item_index
        );
    }
    if (request.action == ACTION_STATUS) {
        return game_call_result;
    }
    if (request.action == ACTION_GAME_TICK) {
        return run_game_call(0, WM_CCZ_GAME_TICK, FALSE);
    }
    if (request.action == ACTION_PROCESS_LOAD_STATE) {
        return run_game_call(
            0, WM_CCZ_PROCESS_LOAD_STATE, FALSE
        );
    }
    if (request.action == ACTION_DISPATCH_LOAD_STATE) {
        return run_game_call(
            0, WM_CCZ_DISPATCH_LOAD_STATE, FALSE
        );
    }
    if (request.action == ACTION_MARK_LOAD_READY) {
        return run_game_call(
            request.item_index, WM_CCZ_MARK_LOAD_READY, FALSE
        );
    }
    if (request.action == ACTION_DUMP_CONTEXTS) {
        return dump_thread_contexts();
    }
    if (request.action == ACTION_MAIN_LOOP_LOAD) {
        return run_main_loop_load(request.item_index);
    }
    if (request.action == ACTION_START_GAME_LOOP) {
        return run_start_game_loop();
    }
    if (request.action == ACTION_TITLE_LOAD) {
        return run_title_load(request.item_index);
    }
    if (request.action == ACTION_PULSE_CLICK) {
        return run_pulse_click(request.x, request.y);
    }
    if (request.action == ACTION_ARM_FIRST_CHOICE) {
        return arm_first_choice();
    }
    if (request.action == ACTION_PULSE_BURST) {
        return run_pulse_burst(
            request.x, request.y, request.count
        );
    }
    if (request.action == ACTION_SILENT_CLICK_BURST) {
        HWND window = request.window != 0
            ? (HWND)(UINT_PTR)request.window
            : find_game_window();
        return post_silent_click_burst(
            window, request.x, request.y, request.count
        );
    }
    if (request.action == ACTION_TIMED_SILENT_CLICK_BURST) {
        HWND window = request.window != 0
            ? (HWND)(UINT_PTR)request.window
            : find_game_window();
        return post_silent_click_burst_timed(
            window,
            request.x,
            request.y,
            request.count,
            request.right,
            request.item_index
        );
    }
    if (request.action == ACTION_LIST_WINDOW_ITEM) {
        return activate_list_window_item(
            (HWND)(UINT_PTR)request.window,
            request.item_index
        );
    }
    if (request.action == ACTION_WNDPROC) {
        HWND game = find_game_window();
        if (game == NULL) {
            return 0;
        }
        return (DWORD)(UINT_PTR)GetWindowLongPtrW(game, GWLP_WNDPROC);
    }
    if (request.action == ACTION_TRACE_RANDOM_WRITE) {
        return enable_random_trace();
    }
    if (request.action == ACTION_NOTIFY_LIST_ITEM) {
        return notify_list_item(request.item_index);
    }
    if (request.action == ACTION_REAL_LIST_ITEM) {
        return real_list_item(request.item_index);
    }
    if (request.action == ACTION_TRACE_DIALOG_CREATE) {
        InterlockedExchange(&trace_dialog_create, 1);
        BOOL wide = install_hook(
            &create_window_ex_hook,
            "CreateWindowExW",
            hooked_create_window_ex
        );
        BOOL ansi = install_hook(
            &create_window_ex_a_hook,
            "CreateWindowExA",
            hooked_create_window_ex_a
        );
        BOOL dialog = install_hook(
            &dialog_box_param_a_hook,
            "DialogBoxParamA",
            hooked_dialog_box_param_a
        );
        BOOL indirect = install_hook(
            &create_dialog_indirect_param_a_hook,
            "CreateDialogIndirectParamA",
            hooked_create_dialog_indirect_param_a
        );
        return wide || ansi || dialog || indirect ? 0 : 49;
    }
    if (request.action == ACTION_OPEN_LOAD_DIALOG) {
        return run_open_load_dialog();
    }
    if (request.action == ACTION_TRACE_LOAD_CALL) {
        return enable_debug_trace(
            GAME_MODAL_DIALOG_FUNCTION_ADDRESS, 0
        );
    }
    if (request.action == ACTION_TRACE_ADDRESS) {
        return enable_debug_trace(
            request.window, request.item_index
        );
    }
    if (request.action == ACTION_REAL_RANDOM) {
        return run_game_event(request.x, request.y);
    }
    if (request.action == ACTION_CONFIRM_SELECTION) {
        return run_confirm_selection(request.x, request.y);
    }
    if (request.action == ACTION_GAME_MOUSE) {
        return run_game_mouse(
            (UINT)request.count, request.x, request.y
        );
    }
    if (request.action == ACTION_GAME_FRAME_CLICK) {
        return run_game_frame_click(request.x, request.y);
    }
    if (request.action == ACTION_ENABLE_ACCELERATION) {
        return run_enable_acceleration();
    }
    if (request.action == ACTION_SILENT_CLICK) {
        HWND window = request.window != 0
            ? (HWND)(UINT_PTR)request.window
            : find_game_window();
        return post_silent_click(window, request.x, request.y);
    }
    if (request.action == ACTION_DUMP_LIST) {
        return dump_list_items();
    }
    if (request.action == ACTION_DIALOG_DBLCLICK) {
        return dialog_double_click_item(request.item_index);
    }
    if (request.action == ACTION_REAL_LOAD) {
        return run_real_load(request.item_index);
    }
    if (request.action == ACTION_DIALOG_ENTER) {
        return dialog_enter_item(request.item_index);
    }
    if (request.action == ACTION_DIALOG_NOTIFY) {
        return dialog_notify_double_click(request.item_index);
    }
    if (request.action == ACTION_DIALOG_WINDOW) {
        return dialog_window_double_click(request.item_index);
    }
    if (request.action == ACTION_DIALOG_ACCESSIBLE) {
        return dialog_accessible_default(request.item_index);
    }
    return 5;
}

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved) {
    (void)instance;
    (void)reason;
    (void)reserved;
    return TRUE;
}
