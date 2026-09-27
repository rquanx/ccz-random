#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <wchar.h>

typedef struct ControlRequest {
    int action;
    DWORD window;
    int x;
    int y;
    int count;
    int right;
    int item_index;
} ControlRequest;

typedef LONG (NTAPI *NtCreateThreadExFunction)(
    PHANDLE,
    ACCESS_MASK,
    PVOID,
    HANDLE,
    PVOID,
    PVOID,
    ULONG,
    SIZE_T,
    SIZE_T,
    SIZE_T,
    PVOID
);

enum InjectorError {
    ERROR_INJECTOR_LOAD_WAIT_FAILED = 200,
    ERROR_INJECTOR_LOAD_TIMEOUT = 201,
    ERROR_INJECTOR_LOAD_EXIT_FAILED = 202,
    ERROR_INJECTOR_LOAD_STILL_ACTIVE = 203,
    ERROR_INJECTOR_REMOTE_MODULE_INVALID = 204,
    ERROR_INJECTOR_REQUEST_WRITE_FAILED = 205,
    ERROR_INJECTOR_CONTROL_WAIT_FAILED = 206,
    ERROR_INJECTOR_CONTROL_TIMEOUT = 207,
    ERROR_INJECTOR_CONTROL_EXIT_FAILED = 208,
    ERROR_INJECTOR_CONTROL_STILL_ACTIVE = 209
};

static HANDLE create_remote_thread_compatible(
    HANDLE process,
    LPTHREAD_START_ROUTINE start_routine,
    LPVOID parameter,
    DWORD *create_thread_error,
    LONG *nt_status
) {
    HANDLE thread = CreateRemoteThread(
        process, NULL, 0, start_routine, parameter, 0, NULL
    );
    if (thread != NULL) {
        *create_thread_error = ERROR_SUCCESS;
        *nt_status = 0;
        return thread;
    }

    *create_thread_error = GetLastError();
    HMODULE ntdll = GetModuleHandleW(L"ntdll.dll");
    NtCreateThreadExFunction nt_create_thread = (
        NtCreateThreadExFunction
    )GetProcAddress(ntdll, "NtCreateThreadEx");
    if (nt_create_thread == NULL) {
        *nt_status = (LONG)0xC0000139;
        return NULL;
    }

    thread = NULL;
    *nt_status = nt_create_thread(
        &thread,
        THREAD_QUERY_INFORMATION | SYNCHRONIZE,
        NULL,
        process,
        start_routine,
        parameter,
        0,
        0,
        0,
        0,
        NULL
    );
    if (*nt_status < 0) {
        return NULL;
    }
    return thread;
}

static BOOL is_remote_module_valid(HANDLE process, DWORD module) {
    IMAGE_DOS_HEADER dos_header;
    SIZE_T bytes_read = 0;
    if (module == 0 || module == STILL_ACTIVE) {
        return FALSE;
    }
    if (!ReadProcessMemory(
            process,
            (LPCVOID)(ULONG_PTR)module,
            &dos_header,
            sizeof(dos_header),
            &bytes_read
        )) {
        return FALSE;
    }
    return bytes_read == sizeof(dos_header) &&
        dos_header.e_magic == IMAGE_DOS_SIGNATURE;
}

int wmain(int argc, wchar_t **argv) {
    if (argc < 4) {
        return 64;
    }

    DWORD pid = wcstoul(argv[1], NULL, 10);
    ControlRequest request;
    ZeroMemory(&request, sizeof(request));
    if (wcscmp(argv[3], L"guard") == 0 && argc == 4) {
        request.action = 3;
    } else if (wcscmp(argv[3], L"wake") == 0 && argc == 6) {
        request.action = 4;
        request.window = wcstoul(argv[4], NULL, 10);
        request.count = _wtoi(argv[5]);
    } else if (wcscmp(argv[3], L"load") == 0 && argc == 5) {
        request.action = 5;
        request.item_index = _wtoi(argv[4]);
    } else if (wcscmp(argv[3], L"save") == 0 && argc == 5) {
        request.action = 6;
        request.item_index = _wtoi(argv[4]);
    } else if (wcscmp(argv[3], L"loadui") == 0 && argc == 6) {
        request.action = 7;
        request.item_index = _wtoi(argv[4]);
        request.window = wcstoul(argv[5], NULL, 10);
    } else if (wcscmp(argv[3], L"closedialog") == 0 && argc == 5) {
        request.action = 8;
        request.item_index = _wtoi(argv[4]);
    } else if (wcscmp(argv[3], L"status") == 0 && argc == 4) {
        request.action = 9;
    } else if (wcscmp(argv[3], L"tick") == 0 && argc == 4) {
        request.action = 30;
    } else if (
        wcscmp(argv[3], L"process-state") == 0 && argc == 4
    ) {
        request.action = 31;
    } else if (
        wcscmp(argv[3], L"dispatch-state") == 0 && argc == 4
    ) {
        request.action = 32;
    } else if (
        wcscmp(argv[3], L"mark-ready") == 0 && argc == 5
    ) {
        request.action = 33;
        request.item_index = _wtoi(argv[4]);
    } else if (
        wcscmp(argv[3], L"dump-contexts") == 0 && argc == 4
    ) {
        request.action = 34;
    } else if (wcscmp(argv[3], L"wndproc") == 0 && argc == 4) {
        request.action = 10;
    } else if (wcscmp(argv[3], L"trace-random") == 0 && argc == 4) {
        request.action = 11;
    } else if (wcscmp(argv[3], L"notifylist") == 0 && argc == 5) {
        request.action = 12;
        request.item_index = _wtoi(argv[4]);
    } else if (wcscmp(argv[3], L"reallist") == 0 && argc == 5) {
        request.action = 13;
        request.item_index = _wtoi(argv[4]);
    } else if (wcscmp(argv[3], L"trace-dialog") == 0 && argc == 4) {
        request.action = 14;
    } else if (wcscmp(argv[3], L"openload") == 0 && argc == 4) {
        request.action = 15;
    } else if (wcscmp(argv[3], L"trace-load") == 0 && argc == 4) {
        request.action = 16;
    } else if (wcscmp(argv[3], L"trace-address") == 0 && argc == 6) {
        request.action = 17;
        request.window = wcstoul(argv[4], NULL, 0);
        request.item_index = _wtoi(argv[5]);
    } else if (wcscmp(argv[3], L"event") == 0 && argc == 6) {
        request.action = 18;
        request.x = _wtoi(argv[4]);
        request.y = _wtoi(argv[5]);
    } else if (wcscmp(argv[3], L"confirm-choice") == 0 && argc == 6) {
        request.action = 19;
        request.x = _wtoi(argv[4]);
        request.y = _wtoi(argv[5]);
    } else if (wcscmp(argv[3], L"mouse") == 0 && argc == 7) {
        request.action = 20;
        request.count = _wtoi(argv[4]);
        request.x = _wtoi(argv[5]);
        request.y = _wtoi(argv[6]);
    } else if (
        wcscmp(argv[3], L"frame-click") == 0 && argc == 6
    ) {
        request.action = 21;
        request.x = _wtoi(argv[4]);
        request.y = _wtoi(argv[5]);
    } else if (
        wcscmp(argv[3], L"silent-click") == 0 && argc == 7
    ) {
        request.action = 22;
        request.window = wcstoul(argv[4], NULL, 10);
        request.x = _wtoi(argv[5]);
        request.y = _wtoi(argv[6]);
    } else if (wcscmp(argv[3], L"dump-list") == 0 && argc == 4) {
        request.action = 23;
    } else if (
        wcscmp(argv[3], L"dialog-dblclick") == 0 && argc == 5
    ) {
        request.action = 24;
        request.item_index = _wtoi(argv[4]);
    } else if (wcscmp(argv[3], L"real-load") == 0 && argc == 5) {
        request.action = 25;
        request.item_index = _wtoi(argv[4]);
    } else if (wcscmp(argv[3], L"loop-load") == 0 && argc == 5) {
        request.action = 35;
        request.item_index = _wtoi(argv[4]);
    } else if (wcscmp(argv[3], L"start-loop") == 0 && argc == 4) {
        request.action = 36;
    } else if (wcscmp(argv[3], L"title-load") == 0 && argc == 5) {
        request.action = 37;
        request.item_index = _wtoi(argv[4]);
    } else if (wcscmp(argv[3], L"pulse-click") == 0 && argc == 6) {
        request.action = 38;
        request.x = _wtoi(argv[4]);
        request.y = _wtoi(argv[5]);
    } else if (wcscmp(argv[3], L"arm-first-choice") == 0 && argc == 4) {
        request.action = 39;
    } else if (wcscmp(argv[3], L"pulse-burst") == 0 && argc == 7) {
        request.action = 40;
        request.x = _wtoi(argv[4]);
        request.y = _wtoi(argv[5]);
        request.count = _wtoi(argv[6]);
    } else if (wcscmp(argv[3], L"silent-burst") == 0 && argc == 8) {
        request.action = 41;
        request.window = wcstoul(argv[4], NULL, 10);
        request.x = _wtoi(argv[5]);
        request.y = _wtoi(argv[6]);
        request.count = _wtoi(argv[7]);
    } else if (
        wcscmp(argv[3], L"silent-burst-timed") == 0 && argc == 10
    ) {
        request.action = 46;
        request.window = wcstoul(argv[4], NULL, 10);
        request.x = _wtoi(argv[5]);
        request.y = _wtoi(argv[6]);
        request.count = _wtoi(argv[7]);
        request.right = _wtoi(argv[8]);
        request.item_index = _wtoi(argv[9]);
    } else if (
        wcscmp(argv[3], L"enable-acceleration") == 0 && argc == 4
    ) {
        request.action = 47;
    } else if (
        wcscmp(argv[3], L"list-window") == 0 && argc == 6
    ) {
        request.action = 42;
        request.window = wcstoul(argv[4], NULL, 10);
        request.item_index = _wtoi(argv[5]);
    } else if (
        wcscmp(argv[3], L"end-dialog") == 0 && argc == 6
    ) {
        request.action = 43;
        request.window = wcstoul(argv[4], NULL, 10);
        request.item_index = _wtoi(argv[5]);
    } else if (
        wcscmp(argv[3], L"mute-audio") == 0 && argc == 4
    ) {
        request.action = 44;
    } else if (
        wcscmp(argv[3], L"silent-click-timed") == 0 && argc == 8
    ) {
        request.action = 45;
        request.window = wcstoul(argv[4], NULL, 10);
        request.x = _wtoi(argv[5]);
        request.y = _wtoi(argv[6]);
        request.item_index = _wtoi(argv[7]);
    } else if (wcscmp(argv[3], L"dialog-enter") == 0 && argc == 5) {
        request.action = 26;
        request.item_index = _wtoi(argv[4]);
    } else if (wcscmp(argv[3], L"dialog-notify") == 0 && argc == 5) {
        request.action = 27;
        request.item_index = _wtoi(argv[4]);
    } else if (wcscmp(argv[3], L"dialog-window") == 0 && argc == 5) {
        request.action = 28;
        request.item_index = _wtoi(argv[4]);
    } else if (wcscmp(argv[3], L"dialog-accessible") == 0 && argc == 5) {
        request.action = 29;
        request.item_index = _wtoi(argv[4]);
    } else if (wcscmp(argv[3], L"list") == 0 && argc == 5) {
        request.action = 1;
        request.item_index = _wtoi(argv[4]);
    } else if (wcscmp(argv[3], L"click") == 0 && argc == 9) {
        request.action = 2;
        request.window = wcstoul(argv[4], NULL, 10);
        request.x = _wtoi(argv[5]);
        request.y = _wtoi(argv[6]);
        request.count = _wtoi(argv[7]);
        request.right = _wtoi(argv[8]);
    } else {
        return 65;
    }
    HANDLE process = OpenProcess(
        PROCESS_CREATE_THREAD | PROCESS_QUERY_INFORMATION |
            PROCESS_VM_OPERATION | PROCESS_VM_WRITE | PROCESS_VM_READ,
        FALSE,
        pid
    );
    if (process == NULL) {
        return 2;
    }

    SIZE_T dll_bytes = (wcslen(argv[2]) + 1) * sizeof(wchar_t);
    LPVOID remote_path = VirtualAllocEx(
        process, NULL, dll_bytes, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE
    );
    if (remote_path == NULL) {
        fwprintf(
            stderr,
            L"VirtualAllocEx(dll path) failed: win32=%lu\n",
            GetLastError()
        );
        CloseHandle(process);
        return 3;
    }
    if (!WriteProcessMemory(
            process, remote_path, argv[2], dll_bytes, NULL
        )) {
        fwprintf(
            stderr,
            L"WriteProcessMemory(dll path) failed: win32=%lu\n",
            GetLastError()
        );
        VirtualFreeEx(process, remote_path, 0, MEM_RELEASE);
        CloseHandle(process);
        return 4;
    }

    HMODULE kernel = GetModuleHandleW(L"kernel32.dll");
    LPTHREAD_START_ROUTINE load_library =
        (LPTHREAD_START_ROUTINE)GetProcAddress(kernel, "LoadLibraryW");
    DWORD load_thread_error = ERROR_SUCCESS;
    LONG load_nt_status = 0;
    HANDLE load_thread = create_remote_thread_compatible(
        process,
        load_library,
        remote_path,
        &load_thread_error,
        &load_nt_status
    );
    if (load_thread == NULL) {
        fwprintf(
            stderr,
            L"LoadLibrary remote thread failed: win32=%lu, ntstatus=0x%08lX\n",
            load_thread_error,
            (DWORD)load_nt_status
        );
        VirtualFreeEx(process, remote_path, 0, MEM_RELEASE);
        CloseHandle(process);
        return 5;
    }
    DWORD load_wait = WaitForSingleObject(load_thread, 5000);
    if (load_wait == WAIT_TIMEOUT) {
        fwprintf(
            stderr,
            L"LoadLibrary remote thread timed out: wait=%lu, timeout_ms=5000\n",
            load_wait
        );
        CloseHandle(load_thread);
        CloseHandle(process);
        return ERROR_INJECTOR_LOAD_TIMEOUT;
    }
    if (load_wait != WAIT_OBJECT_0) {
        fwprintf(
            stderr,
            L"LoadLibrary remote thread wait failed: wait=%lu, win32=%lu\n",
            load_wait,
            GetLastError()
        );
        CloseHandle(load_thread);
        CloseHandle(process);
        return ERROR_INJECTOR_LOAD_WAIT_FAILED;
    }

    DWORD remote_module = 0;
    if (!GetExitCodeThread(load_thread, &remote_module)) {
        fwprintf(
            stderr,
            L"GetExitCodeThread(LoadLibrary) failed: win32=%lu\n",
            GetLastError()
        );
        CloseHandle(load_thread);
        VirtualFreeEx(process, remote_path, 0, MEM_RELEASE);
        CloseHandle(process);
        return ERROR_INJECTOR_LOAD_EXIT_FAILED;
    }
    CloseHandle(load_thread);
    VirtualFreeEx(process, remote_path, 0, MEM_RELEASE);
    if (remote_module == STILL_ACTIVE) {
        fwprintf(
            stderr,
            L"LoadLibrary remote thread still active after signaled wait\n"
        );
        CloseHandle(process);
        return ERROR_INJECTOR_LOAD_STILL_ACTIVE;
    }
    if (remote_module == 0) {
        CloseHandle(process);
        return 6;
    }
    if (!is_remote_module_valid(process, remote_module)) {
        fwprintf(
            stderr,
            L"LoadLibrary returned invalid module: module=0x%08lX, win32=%lu\n",
            remote_module,
            GetLastError()
        );
        CloseHandle(process);
        return ERROR_INJECTOR_REMOTE_MODULE_INVALID;
    }

    HMODULE local_module = LoadLibraryExW(
        argv[2], NULL, DONT_RESOLVE_DLL_REFERENCES
    );
    if (local_module == NULL) {
        CloseHandle(process);
        return 7;
    }
    FARPROC local_export = GetProcAddress(local_module, "ControlAction");
    if (local_export == NULL) {
        FreeLibrary(local_module);
        CloseHandle(process);
        return 8;
    }

    ULONG_PTR export_offset =
        (ULONG_PTR)local_export - (ULONG_PTR)local_module;
    LPTHREAD_START_ROUTINE remote_export =
        (LPTHREAD_START_ROUTINE)((ULONG_PTR)remote_module + export_offset);

    LPVOID remote_request = VirtualAllocEx(
        process,
        NULL,
        sizeof(request),
        MEM_COMMIT | MEM_RESERVE,
        PAGE_READWRITE
    );
    if (remote_request == NULL) {
        fwprintf(
            stderr,
            L"VirtualAllocEx(request) failed: win32=%lu\n",
            GetLastError()
        );
        FreeLibrary(local_module);
        CloseHandle(process);
        return 9;
    }
    SIZE_T request_bytes_written = 0;
    if (!WriteProcessMemory(
            process,
            remote_request,
            &request,
            sizeof(request),
            &request_bytes_written
        ) || request_bytes_written != sizeof(request)) {
        fwprintf(
            stderr,
            L"WriteProcessMemory(request) failed: win32=%lu, written=%Iu, expected=%Iu\n",
            GetLastError(),
            request_bytes_written,
            sizeof(request)
        );
        VirtualFreeEx(process, remote_request, 0, MEM_RELEASE);
        FreeLibrary(local_module);
        CloseHandle(process);
        return ERROR_INJECTOR_REQUEST_WRITE_FAILED;
    }

    DWORD control_thread_error = ERROR_SUCCESS;
    LONG control_nt_status = 0;
    HANDLE control_thread = create_remote_thread_compatible(
        process,
        remote_export,
        remote_request,
        &control_thread_error,
        &control_nt_status
    );
    if (control_thread == NULL) {
        fwprintf(
            stderr,
            L"ControlAction remote thread failed: win32=%lu, ntstatus=0x%08lX\n",
            control_thread_error,
            (DWORD)control_nt_status
        );
        VirtualFreeEx(process, remote_request, 0, MEM_RELEASE);
        FreeLibrary(local_module);
        CloseHandle(process);
        return 10;
    }

    DWORD control_timeout = (
        request.action == 15 || request.action == 25 ||
        request.action == 41 || request.action == 46
    ) ? 65000 : 7000;
    DWORD control_wait = WaitForSingleObject(
        control_thread, control_timeout
    );
    if (control_wait == WAIT_TIMEOUT) {
        fwprintf(
            stderr,
            L"ControlAction remote thread timed out: action=%d, "
            L"wait=%lu, timeout_ms=%lu, remote_module=0x%08lX, "
            L"remote_export=0x%08lX\n",
            request.action,
            control_wait,
            control_timeout,
            remote_module,
            (DWORD)(ULONG_PTR)remote_export
        );
        CloseHandle(control_thread);
        FreeLibrary(local_module);
        CloseHandle(process);
        return ERROR_INJECTOR_CONTROL_TIMEOUT;
    }
    if (control_wait != WAIT_OBJECT_0) {
        fwprintf(
            stderr,
            L"ControlAction remote thread wait failed: action=%d, "
            L"wait=%lu, win32=%lu\n",
            request.action,
            control_wait,
            GetLastError()
        );
        CloseHandle(control_thread);
        FreeLibrary(local_module);
        CloseHandle(process);
        return ERROR_INJECTOR_CONTROL_WAIT_FAILED;
    }

    DWORD result = 11;
    if (!GetExitCodeThread(control_thread, &result)) {
        fwprintf(
            stderr,
            L"GetExitCodeThread(ControlAction) failed: action=%d, win32=%lu\n",
            request.action,
            GetLastError()
        );
        CloseHandle(control_thread);
        VirtualFreeEx(process, remote_request, 0, MEM_RELEASE);
        FreeLibrary(local_module);
        CloseHandle(process);
        return ERROR_INJECTOR_CONTROL_EXIT_FAILED;
    }
    CloseHandle(control_thread);
    VirtualFreeEx(process, remote_request, 0, MEM_RELEASE);
    FreeLibrary(local_module);
    CloseHandle(process);
    if (result == STILL_ACTIVE) {
        fwprintf(
            stderr,
            L"ControlAction remote thread still active after signaled wait: "
            L"action=%d\n",
            request.action
        );
        return ERROR_INJECTOR_CONTROL_STILL_ACTIVE;
    }
    if (request.action == 9 || request.action == 10) {
        wprintf(L"%lu\n", result);
        return 0;
    }
    if (result != 0) {
        fwprintf(
            stderr,
            L"ControlAction returned failure: action=%d, result=%lu "
            L"(0x%08lX), remote_module=0x%08lX, remote_export=0x%08lX\n",
            request.action,
            result,
            result,
            remote_module,
            (DWORD)(ULONG_PTR)remote_export
        );
    }
    return (int)result;
}
