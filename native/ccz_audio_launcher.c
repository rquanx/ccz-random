#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>
#include <stdio.h>

#define CONTROL_DLL_RESOURCE 101
#define ACTION_ASYNC_SOUND 48

typedef struct ControlRequest {
    int action;
    DWORD window;
    int x;
    int y;
    int count;
    int right;
    int item_index;
} ControlRequest;

static void remove_file_name(WCHAR *path) {
    WCHAR *cursor = path + lstrlenW(path);
    while (cursor > path) {
        cursor--;
        if (*cursor == L'\\' || *cursor == L'/') {
            *cursor = L'\0';
            return;
        }
    }
}

static BOOL file_exists(const WCHAR *path) {
    DWORD attributes = GetFileAttributesW(path);
    return attributes != INVALID_FILE_ATTRIBUTES
        && (attributes & FILE_ATTRIBUTE_DIRECTORY) == 0;
}

static BOOL build_path(
    WCHAR *output,
    DWORD capacity,
    const WCHAR *directory,
    const WCHAR *name
) {
    return _snwprintf_s(
        output,
        capacity,
        _TRUNCATE,
        L"%s\\%s",
        directory,
        name
    ) >= 0;
}

static void trim_config_value(WCHAR *value) {
    WCHAR *start = value;
    WCHAR *end;
    size_t length;

    while (*start == L' ' || *start == L'\t') {
        start++;
    }
    if (start != value) {
        MoveMemory(
            value,
            start,
            ((size_t)lstrlenW(start) + 1) * sizeof(WCHAR)
        );
    }
    end = value + lstrlenW(value);
    while (
        end > value
        && (
            end[-1] == L' '
            || end[-1] == L'\t'
            || end[-1] == L'\r'
            || end[-1] == L'\n'
        )
    ) {
        *--end = L'\0';
    }
    length = (size_t)lstrlenW(value);
    if (
        length >= 2
        && (
            (value[0] == L'"' && value[length - 1] == L'"')
            || (value[0] == L'\'' && value[length - 1] == L'\'')
        )
    ) {
        MoveMemory(
            value,
            value + 1,
            (length - 2) * sizeof(WCHAR)
        );
        value[length - 2] = L'\0';
    }
}

static BOOL read_config_text(
    const WCHAR *path,
    WCHAR **text
) {
    HANDLE file;
    DWORD size;
    DWORD bytes_read = 0;
    BYTE *bytes;
    const BYTE *encoded;
    DWORD encoded_size;
    UINT code_page = CP_UTF8;
    DWORD flags = MB_ERR_INVALID_CHARS;
    int characters;
    WCHAR *decoded;

    *text = NULL;
    file = CreateFileW(
        path,
        GENERIC_READ,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        NULL,
        OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL,
        NULL
    );
    if (file == INVALID_HANDLE_VALUE) {
        return FALSE;
    }
    size = GetFileSize(file, NULL);
    if (size == INVALID_FILE_SIZE || size == 0 || size > 65536) {
        CloseHandle(file);
        return FALSE;
    }
    bytes = (BYTE *)HeapAlloc(GetProcessHeap(), 0, size);
    if (
        bytes == NULL
        || !ReadFile(file, bytes, size, &bytes_read, NULL)
        || bytes_read != size
    ) {
        if (bytes != NULL) {
            HeapFree(GetProcessHeap(), 0, bytes);
        }
        CloseHandle(file);
        return FALSE;
    }
    CloseHandle(file);

    if (size >= 2 && bytes[0] == 0xFF && bytes[1] == 0xFE) {
        DWORD wide_bytes = size - 2;
        DWORD wide_characters = wide_bytes / sizeof(WCHAR);
        decoded = (WCHAR *)HeapAlloc(
            GetProcessHeap(),
            HEAP_ZERO_MEMORY,
            ((SIZE_T)wide_characters + 1) * sizeof(WCHAR)
        );
        if (decoded != NULL) {
            CopyMemory(decoded, bytes + 2, wide_characters * sizeof(WCHAR));
        }
        HeapFree(GetProcessHeap(), 0, bytes);
        *text = decoded;
        return decoded != NULL;
    }

    encoded = bytes;
    encoded_size = size;
    if (
        size >= 3
        && bytes[0] == 0xEF
        && bytes[1] == 0xBB
        && bytes[2] == 0xBF
    ) {
        encoded += 3;
        encoded_size -= 3;
    }
    characters = MultiByteToWideChar(
        code_page,
        flags,
        (LPCCH)encoded,
        encoded_size,
        NULL,
        0
    );
    if (characters == 0) {
        code_page = CP_ACP;
        flags = 0;
        characters = MultiByteToWideChar(
            code_page,
            flags,
            (LPCCH)encoded,
            encoded_size,
            NULL,
            0
        );
    }
    if (characters == 0) {
        HeapFree(GetProcessHeap(), 0, bytes);
        return FALSE;
    }
    decoded = (WCHAR *)HeapAlloc(
        GetProcessHeap(),
        HEAP_ZERO_MEMORY,
        ((SIZE_T)characters + 1) * sizeof(WCHAR)
    );
    if (
        decoded == NULL
        || MultiByteToWideChar(
            code_page,
            flags,
            (LPCCH)encoded,
            encoded_size,
            decoded,
            characters
        ) != characters
    ) {
        if (decoded != NULL) {
            HeapFree(GetProcessHeap(), 0, decoded);
        }
        HeapFree(GetProcessHeap(), 0, bytes);
        return FALSE;
    }
    HeapFree(GetProcessHeap(), 0, bytes);
    *text = decoded;
    return TRUE;
}

static BOOL read_configured_executable(
    const WCHAR *path,
    WCHAR *configured,
    DWORD capacity
) {
    WCHAR *text;
    WCHAR *line;
    BOOL game_section = FALSE;
    BOOL found = FALSE;

    configured[0] = L'\0';
    if (!read_config_text(path, &text)) {
        return FALSE;
    }
    line = text;
    while (*line != L'\0') {
        WCHAR *next = line;
        WCHAR *separator;
        while (*next != L'\0' && *next != L'\r' && *next != L'\n') {
            next++;
        }
        if (*next != L'\0') {
            *next++ = L'\0';
            while (*next == L'\r' || *next == L'\n') {
                next++;
            }
        }
        trim_config_value(line);
        if (line[0] == L'[') {
            game_section = lstrcmpiW(line, L"[game]") == 0;
        } else if (
            game_section
            && line[0] != L'\0'
            && line[0] != L';'
            && line[0] != L'#'
        ) {
            separator = wcschr(line, L'=');
            if (separator != NULL) {
                *separator = L'\0';
                trim_config_value(line);
                if (lstrcmpiW(line, L"exe") == 0) {
                    trim_config_value(separator + 1);
                    lstrcpynW(configured, separator + 1, capacity);
                    found = configured[0] != L'\0';
                    break;
                }
            }
        }
        line = next;
    }
    HeapFree(GetProcessHeap(), 0, text);
    return found;
}

static BOOL resolve_configured_game(
    WCHAR *game,
    DWORD capacity,
    const WCHAR *launcher_directory,
    BOOL *configured_present
) {
    WCHAR config[MAX_PATH];
    WCHAR configured[MAX_PATH];
    WCHAR candidate[MAX_PATH];
    BOOL absolute;

    if (!build_path(
            config,
            ARRAYSIZE(config),
            launcher_directory,
            L"ccz_audio_fix.ini"
        )) {
        return FALSE;
    }
    if (!read_configured_executable(
            config,
            configured,
            ARRAYSIZE(configured)
        )) {
        return FALSE;
    }
    *configured_present = TRUE;
    absolute = (
        (configured[0] != L'\0' && configured[1] == L':')
        || (configured[0] == L'\\' && configured[1] == L'\\')
    );
    if (absolute) {
        lstrcpynW(candidate, configured, ARRAYSIZE(candidate));
    } else if (!build_path(
            candidate,
            ARRAYSIZE(candidate),
            launcher_directory,
            configured
        )) {
        return FALSE;
    }
    if (!file_exists(candidate)) {
        return FALSE;
    }
    return GetFullPathNameW(
        candidate,
        capacity,
        game,
        NULL
    ) > 0;
}

static BOOL extract_control_dll(
    HINSTANCE instance,
    WCHAR *path,
    DWORD capacity
) {
    WCHAR temp[MAX_PATH];
    WCHAR directory[MAX_PATH];
    HRSRC resource;
    HGLOBAL loaded;
    const void *data;
    DWORD size;
    HANDLE file;
    DWORD written = 0;

    if (
        GetTempPathW(ARRAYSIZE(temp), temp) == 0
        || !build_path(
            directory,
            ARRAYSIZE(directory),
            temp,
            L"CCZAudioFix"
        )
    ) {
        return FALSE;
    }
    CreateDirectoryW(directory, NULL);
    if (_snwprintf_s(
            path,
            capacity,
            _TRUNCATE,
            L"%s\\ccz_control_%lu.dll",
            directory,
            GetCurrentProcessId()
        ) < 0) {
        return FALSE;
    }
    resource = FindResourceW(
        instance,
        MAKEINTRESOURCEW(CONTROL_DLL_RESOURCE),
        RT_RCDATA
    );
    if (resource == NULL) {
        return FALSE;
    }
    loaded = LoadResource(instance, resource);
    data = loaded != NULL ? LockResource(loaded) : NULL;
    size = SizeofResource(instance, resource);
    if (data == NULL || size == 0) {
        return FALSE;
    }
    file = CreateFileW(
        path,
        GENERIC_WRITE,
        0,
        NULL,
        CREATE_ALWAYS,
        FILE_ATTRIBUTE_TEMPORARY,
        NULL
    );
    if (file == INVALID_HANDLE_VALUE) {
        return FALSE;
    }
    if (!WriteFile(file, data, size, &written, NULL) || written != size) {
        CloseHandle(file);
        DeleteFileW(path);
        return FALSE;
    }
    CloseHandle(file);
    return TRUE;
}

static DWORD run_remote_thread(
    HANDLE process,
    LPTHREAD_START_ROUTINE function,
    LPVOID parameter,
    DWORD timeout
) {
    HANDLE thread;
    DWORD result = ERROR_GEN_FAILURE;

    if (function == NULL) {
        return ERROR_PROC_NOT_FOUND;
    }
    thread = CreateRemoteThread(
        process,
        NULL,
        0,
        function,
        parameter,
        0,
        NULL
    );
    if (thread == NULL) {
        return GetLastError();
    }
    if (WaitForSingleObject(thread, timeout) == WAIT_OBJECT_0) {
        if (!GetExitCodeThread(thread, &result)) {
            result = GetLastError();
        }
    } else {
        result = ERROR_TIMEOUT;
    }
    CloseHandle(thread);
    return result;
}

static DWORD install_audio_patch(
    DWORD pid,
    const WCHAR *dll_path
) {
    HANDLE process;
    SIZE_T path_size;
    LPVOID remote_path = NULL;
    LPVOID remote_request = NULL;
    DWORD remote_module;
    HMODULE local_module = NULL;
    FARPROC local_export;
    LPTHREAD_START_ROUTINE remote_export;
    ControlRequest request;
    DWORD result = ERROR_GEN_FAILURE;

    process = OpenProcess(
        PROCESS_CREATE_THREAD
            | PROCESS_QUERY_INFORMATION
            | PROCESS_VM_OPERATION
            | PROCESS_VM_WRITE
            | PROCESS_VM_READ,
        FALSE,
        pid
    );
    if (process == NULL) {
        return GetLastError();
    }

    path_size = ((SIZE_T)lstrlenW(dll_path) + 1) * sizeof(WCHAR);
    remote_path = VirtualAllocEx(
        process,
        NULL,
        path_size,
        MEM_COMMIT | MEM_RESERVE,
        PAGE_READWRITE
    );
    if (
        remote_path == NULL
        || !WriteProcessMemory(
            process,
            remote_path,
            dll_path,
            path_size,
            NULL
        )
    ) {
        result = GetLastError();
        goto cleanup;
    }
    remote_module = run_remote_thread(
        process,
        (LPTHREAD_START_ROUTINE)GetProcAddress(
            GetModuleHandleW(L"kernel32.dll"),
            "LoadLibraryW"
        ),
        remote_path,
        15000
    );
    if (remote_module < 0x10000) {
        result = remote_module != 0 ? remote_module : ERROR_DLL_INIT_FAILED;
        goto cleanup;
    }

    local_module = LoadLibraryExW(
        dll_path,
        NULL,
        DONT_RESOLVE_DLL_REFERENCES
    );
    if (local_module == NULL) {
        result = GetLastError();
        goto cleanup;
    }
    local_export = GetProcAddress(local_module, "ControlAction");
    if (local_export == NULL) {
        result = GetLastError();
        goto cleanup;
    }
    remote_export = (LPTHREAD_START_ROUTINE)(
        (BYTE *)(UINT_PTR)remote_module
        + ((BYTE *)local_export - (BYTE *)local_module)
    );

    ZeroMemory(&request, sizeof(request));
    request.action = ACTION_ASYNC_SOUND;
    remote_request = VirtualAllocEx(
        process,
        NULL,
        sizeof(request),
        MEM_COMMIT | MEM_RESERVE,
        PAGE_READWRITE
    );
    if (
        remote_request == NULL
        || !WriteProcessMemory(
            process,
            remote_request,
            &request,
            sizeof(request),
            NULL
        )
    ) {
        result = GetLastError();
        goto cleanup;
    }
    result = run_remote_thread(
        process,
        remote_export,
        remote_request,
        15000
    );

cleanup:
    if (local_module != NULL) {
        FreeLibrary(local_module);
    }
    if (remote_request != NULL) {
        VirtualFreeEx(process, remote_request, 0, MEM_RELEASE);
    }
    if (remote_path != NULL) {
        VirtualFreeEx(process, remote_path, 0, MEM_RELEASE);
    }
    CloseHandle(process);
    return result;
}

static BOOL resolve_game_path(
    WCHAR *game,
    DWORD capacity,
    const WCHAR *launcher_directory
) {
    int argument_count = 0;
    LPWSTR *arguments = CommandLineToArgvW(
        GetCommandLineW(),
        &argument_count
    );
    BOOL resolved = FALSE;
    BOOL configured_present = FALSE;

    if (arguments != NULL && argument_count >= 2) {
        resolved = GetFullPathNameW(
            arguments[1],
            capacity,
            game,
            NULL
        ) > 0;
    } else if (resolve_configured_game(
            game,
            capacity,
            launcher_directory,
            &configured_present
        )) {
        resolved = TRUE;
    } else if (!configured_present) {
        resolved = build_path(
            game,
            capacity,
            launcher_directory,
            L"Ekd5.exe"
        );
    }
    if (arguments != NULL) {
        LocalFree(arguments);
    }
    return resolved && file_exists(game);
}

int WINAPI wWinMain(
    HINSTANCE instance,
    HINSTANCE previous_instance,
    PWSTR command_line,
    int show_command
) {
    WCHAR launcher_directory[MAX_PATH];
    WCHAR game[MAX_PATH];
    WCHAR game_directory[MAX_PATH];
    WCHAR control_dll[MAX_PATH];
    WCHAR game_command[MAX_PATH + 3];
    STARTUPINFOW startup;
    PROCESS_INFORMATION process;
    DWORD inject_result = ERROR_RETRY;
    int attempt;

    (void)previous_instance;
    (void)command_line;
    (void)show_command;

    if (!GetModuleFileNameW(
            NULL,
            launcher_directory,
            ARRAYSIZE(launcher_directory)
        )) {
        return 1;
    }
    remove_file_name(launcher_directory);
    if (!resolve_game_path(
            game,
            ARRAYSIZE(game),
            launcher_directory
        )) {
        MessageBoxW(
            NULL,
            L"没有找到目标游戏 EXE。请检查 ccz_audio_fix.ini，"
            L"或把本程序复制到 Ekd5.exe 所在目录；"
            L"也可以把游戏 EXE 拖到本程序上。",
            L"曹操传 MOD 音效流畅启动",
            MB_OK | MB_ICONERROR
        );
        return 2;
    }
    if (!extract_control_dll(
            instance,
            control_dll,
            ARRAYSIZE(control_dll)
        )) {
        MessageBoxW(
            NULL,
            L"无法释放内置音效补丁，请检查临时目录权限或安全软件。",
            L"曹操传 MOD 音效流畅启动",
            MB_OK | MB_ICONERROR
        );
        return 3;
    }

    lstrcpynW(game_directory, game, ARRAYSIZE(game_directory));
    remove_file_name(game_directory);
    _snwprintf_s(
        game_command,
        ARRAYSIZE(game_command),
        _TRUNCATE,
        L"\"%s\"",
        game
    );
    ZeroMemory(&startup, sizeof(startup));
    ZeroMemory(&process, sizeof(process));
    startup.cb = sizeof(startup);
    if (!CreateProcessW(
            game,
            game_command,
            NULL,
            NULL,
            FALSE,
            CREATE_SUSPENDED,
            NULL,
            game_directory,
            &startup,
            &process
        )) {
        DeleteFileW(control_dll);
        MessageBoxW(
            NULL,
            L"无法启动游戏 EXE。",
            L"曹操传 MOD 音效流畅启动",
            MB_OK | MB_ICONERROR
        );
        return 4;
    }

    if (ResumeThread(process.hThread) == (DWORD)-1) {
        TerminateProcess(process.hProcess, GetLastError());
        CloseHandle(process.hThread);
        CloseHandle(process.hProcess);
        DeleteFileW(control_dll);
        return 5;
    }
    WaitForInputIdle(process.hProcess, 10000);
    for (attempt = 0; attempt < 30; attempt++) {
        inject_result = install_audio_patch(
            process.dwProcessId,
            control_dll
        );
        if (inject_result == 0) {
            break;
        }
        if (WaitForSingleObject(process.hProcess, 0) == WAIT_OBJECT_0) {
            break;
        }
        Sleep(100);
    }
    if (inject_result != 0) {
        TerminateProcess(process.hProcess, inject_result);
        CloseHandle(process.hThread);
        CloseHandle(process.hProcess);
        DeleteFileW(control_dll);
        MessageBoxW(
            NULL,
            L"这个 MOD 没有找到兼容的 sndPlaySoundA 音效接口，"
            L"或补丁被安全软件阻止。游戏未启动。",
            L"曹操传 MOD 音效流畅启动",
            MB_OK | MB_ICONERROR
        );
        return 6;
    }

    CloseHandle(process.hThread);
    WaitForSingleObject(process.hProcess, INFINITE);
    CloseHandle(process.hProcess);
    DeleteFileW(control_dll);
    return 0;
}
