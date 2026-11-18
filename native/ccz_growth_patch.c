/* Experimental patch for the exact 2.20-1104-night executable copy.
 * The PE import is changed from PSAPI.DLL to CCZFX.DLL, without moving
 * sections or the protected executable's overlay. Keep the real PSAPI API.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <tlhelp32.h>
#include <bcrypt.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>
#include "ccz_growth_storage.h"
#pragma comment(linker, "/export:GetModuleFileNameExW=PSAPI.GetModuleFileNameExW")

__declspec(dllexport) volatile DWORD CczGrowthStatus = 0;
__declspec(dllexport) SHORT CczGrowthTable[CCZ_GROWTH_COUNT][CCZ_GROWTH_FIELDS];
__declspec(dllexport) volatile DWORD CczGrowthLastBodySize = 0;

static BYTE *lookup_original, *reader_original, *update_original;
static BYTE *save_original, *load_original;
static DWORD record_function = 0x4061E4;
static DWORD update_continue = 0x408B5B;
static WCHAR game_directory[MAX_PATH];

static void failure(const WCHAR *message) {
    MessageBoxW(NULL, message, L"高编号人物成长修复（实验版）", MB_OK | MB_ICONERROR);
}

__declspec(naked) static void lookup_hook(void) {
    __asm {
        cmp ax, CCZ_GROWTH_FIRST
        jb old_path
        cmp ax, CCZ_GROWTH_COUNT
        jae old_path
        push ebp
        mov ebp, esp
        push eax
        cmp dword ptr [ebp+8], 1
        je accepted
        push eax
        call dword ptr [record_function]
        cmp byte ptr [ecx+2Ah], 0FFh
        je rejected
    accepted:
        pop eax
        imul edx, eax, 14
        add edx, offset CczGrowthTable
        mov esp, ebp
        pop ebp
        ret 4
    rejected:
        pop eax
        mov al, 0FFh
        mov esp, ebp
        pop ebp
        ret 4
    old_path:
        jmp dword ptr [lookup_original]
    }
}

__declspec(naked) static void reader_hook(void) {
    __asm {
        cmp ax, CCZ_GROWTH_FIRST
        jb old_path
        cmp ax, CCZ_GROWTH_COUNT
        jae old_path
        push ebp
        mov ebp, esp
        push eax
        push eax
        call dword ptr [record_function]
        pop edx
        cmp byte ptr [ecx+2Ah], 0
        jne zero
        imul edx, edx, 14
        add edx, offset CczGrowthTable
        mov eax, dword ptr [ebp+8]
        cmp eax, CCZ_GROWTH_FIELDS
        jae zero
        movsx eax, word ptr [edx+eax*2]
        jmp done
    zero:
        xor eax, eax
    done:
        mov esp, ebp
        pop ebp
        ret 4
    old_path:
        jmp dword ptr [reader_original]
    }
}

__declspec(naked) static void update_hook(void) {
    __asm {
        cmp ax, CCZ_GROWTH_FIRST
        jb old_path
        cmp ax, CCZ_GROWTH_COUNT
        jae old_path
        push ebp
        mov ebp, esp
        mov edx, offset CczGrowthTable
        jmp dword ptr [update_continue]
    old_path:
        jmp dword ptr [update_original]
    }
}

/* The original save totals successful WriteFile byte counts in [ebp-4]. */
__declspec(naked) static void save_return_size(void) {
    __asm {
        mov eax, dword ptr [ebp-4]
        mov esp, ebp
        pop ebp
        ret 4
    }
}

static BOOL slot_path(DWORD slot, WCHAR *path) {
    typedef void (__stdcall *SlotName)(char *, DWORD);
    char relative[64] = {0};
    WCHAR wide[64];
    ((SlotName)0x4288F4)(relative, slot);
    if (!MultiByteToWideChar(CP_ACP, MB_ERR_INVALID_CHARS, relative, -1, wide, 64)) return FALSE;
    return _snwprintf_s(path, MAX_PATH, _TRUNCATE, L"%s\\%s", game_directory, wide) >= 0;
}

static DWORD __stdcall save_hook(DWORD slot) {
    typedef DWORD (__stdcall *Save)(DWORD);
    WCHAR path[MAX_PATH], backup[MAX_PATH] = {0};
    WCHAR directory[MAX_PATH], *slash;
    BOOL existed;
    DWORD body_size, error = 0;
    if (!slot_path(slot, path)) return 0;
    existed = GetFileAttributesW(path) != INVALID_FILE_ATTRIBUTES;
    if (existed) {
        lstrcpyW(directory, path);
        slash = wcsrchr(directory, L'\\');
        if (!slash) return 0;
        *slash = 0;
        if (!GetTempFileNameW(directory, L"cgb", 0, backup) || !CopyFileW(path, backup, FALSE)) {
            if (backup[0]) DeleteFileW(backup);
            failure(L"无法备份测试存档，本次保存已取消。");
            return 0;
        }
    }
    body_size = ((Save)save_original)(slot);
    CczGrowthLastBodySize = body_size;
    if (body_size < 0x30000 || !ccz_growth_save(path, body_size,
            &CczGrowthTable[CCZ_GROWTH_FIRST][0], &error)) {
        BOOL restored = existed ? MoveFileExW(backup, path, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH) : DeleteFileW(path);
        CczGrowthStatus = 5;
        failure(restored ? L"成长数据保存失败，已撤销本次保存。" :
            L"成长数据保存失败，恢复测试存档也未成功。请保留 SV 目录中的 cgb 临时备份，停止继续保存。");
        return 0;
    }
    if (backup[0]) DeleteFileW(backup);
    return body_size;
}

static DWORD __stdcall load_hook(DWORD slot) {
    typedef DWORD (__stdcall *Load)(DWORD);
    WCHAR path[MAX_PATH];
    SHORT incoming[CCZ_GROWTH_HIGH_COUNT * CCZ_GROWTH_FIELDS];
    SHORT previous[CCZ_GROWTH_HIGH_COUNT * CCZ_GROWTH_FIELDS];
    DWORD result, error;
    if (!slot_path(slot, path)) return 0;
    if (ccz_growth_read(path, incoming, &error) < 0) {
        CczGrowthStatus = 5;
        failure(L"测试存档无法读取，或扩展成长数据校验失败。本次读档已取消。");
        return 0;
    }
    memcpy(previous, &CczGrowthTable[CCZ_GROWTH_FIRST][0], sizeof(previous));
    memcpy(&CczGrowthTable[CCZ_GROWTH_FIRST][0], incoming, sizeof(incoming));
    result = ((Load)load_original)(slot);
    if (!(result & 0xFF)) memcpy(&CczGrowthTable[CCZ_GROWTH_FIRST][0], previous, sizeof(previous));
    return result;
}

static BOOL expected_executable(void) {
    static const BYTE expected[32] = {
        0x80,0xe0,0x3a,0xa0,0xe5,0x7c,0x87,0x0b,0x94,0xd5,0x1b,0x36,0x1e,0x58,0x88,0x31,
        0x19,0x09,0x72,0xef,0xd0,0x0b,0x53,0x36,0x25,0xa3,0x96,0x9c,0x66,0x57,0x99,0x90
    };
    BCRYPT_ALG_HANDLE algorithm = NULL;
    BCRYPT_HASH_HANDLE hash = NULL;
    WCHAR path[MAX_PATH], *slash;
    HANDLE file = INVALID_HANDLE_VALUE;
    BYTE buffer[65536], digest[32];
    DWORD count;
    BOOL success = FALSE;
    if (!GetModuleFileNameW(NULL, path, MAX_PATH)) return FALSE;
    lstrcpyW(game_directory, path);
    slash = wcsrchr(game_directory, L'\\');
    if (!slash) return FALSE;
    *slash = 0;
    file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
    if (file == INVALID_HANDLE_VALUE || BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, NULL, 0) < 0 ||
        BCryptCreateHash(algorithm, &hash, NULL, 0, NULL, 0, 0) < 0) goto done;
    for (;;) {
        if (!ReadFile(file, buffer, sizeof(buffer), &count, NULL)) goto done;
        if (!count) break;
        if (BCryptHashData(hash, buffer, count, 0) < 0) goto done;
    }
    if (BCryptFinishHash(hash, digest, sizeof(digest), 0) < 0) goto done;
    success = memcmp(expected, digest, sizeof(expected)) == 0;
done:
    if (hash) BCryptDestroyHash(hash);
    if (algorithm) BCryptCloseAlgorithmProvider(algorithm, 0);
    if (file != INVALID_HANDLE_VALUE) CloseHandle(file);
    return success;
}

typedef struct Hook {
    DWORD address;
    BYTE expected[8];
    DWORD size;
    DWORD replacement;
    BYTE **original;
    DWORD protection;
} Hook;

static void jump(BYTE *address, DWORD target, DWORD size) {
    address[0] = 0xE9;
    *(DWORD *)(address + 1) = target - (DWORD)(UINT_PTR)address - 5;
    if (size > 5) memset(address + 5, 0x90, size - 5);
}

static BOOL install_hooks(void) {
    Hook hooks[] = {
        {0x4224A8, {0x55,0x8b,0xec,0x66,0x83,0xf8,0x66}, 7, (DWORD)(UINT_PTR)lookup_hook, &lookup_original, 0},
        {0x41055D, {0x55,0x8b,0xec,0x66,0x83,0xf8,0x66}, 7, (DWORD)(UINT_PTR)reader_hook, &reader_original, 0},
        {0x408B52, {0x55,0x8b,0xec,0x66,0x83,0xf8,0x66}, 7, (DWORD)(UINT_PTR)update_hook, &update_original, 0},
        {0x40531A, {0x55,0x8b,0xec,0x6a,0x00}, 5, (DWORD)(UINT_PTR)save_hook, &save_original, 0},
        {0x41888D, {0x55,0x8b,0xec,0x6a,0x00}, 5, (DWORD)(UINT_PTR)load_hook, &load_original, 0},
        {0x4053C6, {0x8b,0xe5,0x5d,0xc2,0x04,0x00}, 6, (DWORD)(UINT_PTR)save_return_size, NULL, 0}
    };
    HANDLE threads[128], snapshot;
    THREADENTRY32 entry;
    DWORD i, writable = 0, thread_count = 0;
    BOOL success = FALSE;
    for (i = 0; i < ARRAYSIZE(hooks); ++i) {
        Hook *hook = &hooks[i];
        if (memcmp((void *)hook->address, hook->expected, hook->size)) return FALSE;
        if (hook->original) {
            BYTE *code = VirtualAlloc(NULL, hook->size + 5, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
            if (!code) return FALSE;
            memcpy(code, (void *)hook->address, hook->size);
            jump(code + hook->size, hook->address + hook->size, 5);
            *hook->original = code;
        }
    }
    snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
    if (snapshot == INVALID_HANDLE_VALUE) return FALSE;
    entry.dwSize = sizeof(entry);
    if (!Thread32First(snapshot, &entry)) { CloseHandle(snapshot); return FALSE; }
    do {
        HANDLE thread;
        if (entry.th32OwnerProcessID != GetCurrentProcessId() || entry.th32ThreadID == GetCurrentThreadId()) continue;
        if (thread_count >= ARRAYSIZE(threads)) goto resume;
        thread = OpenThread(THREAD_SUSPEND_RESUME, FALSE, entry.th32ThreadID);
        if (!thread) goto resume;
        if (SuspendThread(thread) == (DWORD)-1) { CloseHandle(thread); goto resume; }
        threads[thread_count++] = thread;
    } while (Thread32Next(snapshot, &entry));
    for (i = 0; i < ARRAYSIZE(hooks); ++i) {
        if (!VirtualProtect((void *)hooks[i].address, hooks[i].size, PAGE_EXECUTE_READWRITE, &hooks[i].protection)) goto protect_done;
        ++writable;
    }
    for (i = 0; i < ARRAYSIZE(hooks); ++i) jump((BYTE *)hooks[i].address, hooks[i].replacement, hooks[i].size);
    FlushInstructionCache(GetCurrentProcess(), NULL, 0);
    success = TRUE;
protect_done:
    for (i = 0; i < writable; ++i) {
        DWORD ignored;
        VirtualProtect((void *)hooks[i].address, hooks[i].size, hooks[i].protection, &ignored);
    }
resume:
    while (thread_count) {
        HANDLE thread = threads[--thread_count];
        ResumeThread(thread);
        CloseHandle(thread);
    }
    CloseHandle(snapshot);
    return success;
}

static DWORD WINAPI initialize(void *unused) {
    DWORD attempt;
    MEMORY_BASIC_INFORMATION info;
    const BYTE signature[] = {0x55,0x8b,0xec,0x66,0x83,0xf8,0x66};
    (void)unused;
    if (!expected_executable()) { CczGrowthStatus = 2; failure(L"EXE 与本实验版不匹配，成长修复未加载。请使用完整测试副本。"); return 2; }
    for (attempt = 0; attempt < 1500; ++attempt) {
        if (VirtualQuery((void *)0x4224A8, &info, sizeof(info)) == sizeof(info) &&
            info.State == MEM_COMMIT && !(info.Protect & (PAGE_GUARD | PAGE_NOACCESS)) &&
            !memcmp((void *)0x4224A8, signature, sizeof(signature))) break;
        Sleep(10);
    }
    if (attempt == 1500) { CczGrowthStatus = 3; failure(L"等待游戏解包超时，成长修复未加载。"); return 3; }
    if (!install_hooks()) { CczGrowthStatus = 4; failure(L"游戏指令与实验补丁不兼容，成长修复未加载。"); return 4; }
    CczGrowthStatus = 1;
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        HANDLE thread;
        DisableThreadLibraryCalls(instance);
        thread = CreateThread(NULL, 0, initialize, NULL, 0, NULL);
        if (thread) CloseHandle(thread);
        else CczGrowthStatus = 4;
    }
    return TRUE;
}
