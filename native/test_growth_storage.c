#include "ccz_growth_storage.h"
#include <stdio.h>
#include <string.h>

static int checks = 0;
#define CHECK(expression) do { ++checks; if (!(expression)) { fprintf(stderr, "Storage check failed at line %d: %s\n", __LINE__, #expression); return 1; } } while (0)

static BOOL write_body(const WCHAR *path, DWORD size, BYTE seed, BOOL truncate) {
    HANDLE file = CreateFileW(path, GENERIC_WRITE, 0, NULL, truncate ? CREATE_ALWAYS : OPEN_EXISTING, 0, NULL);
    BYTE buffer[4096];
    DWORD count;
    if (file == INVALID_HANDLE_VALUE) return FALSE;
    memset(buffer, seed, sizeof(buffer));
    while (size) {
        DWORD chunk = size < sizeof(buffer) ? size : sizeof(buffer);
        if (!WriteFile(file, buffer, chunk, &count, NULL) || count != chunk) { CloseHandle(file); return FALSE; }
        size -= chunk;
    }
    return CloseHandle(file);
}

static BOOL flip(const WCHAR *path, DWORD offset) {
    HANDLE file = CreateFileW(path, GENERIC_READ | GENERIC_WRITE, 0, NULL, OPEN_EXISTING, 0, NULL);
    BYTE value;
    DWORD count;
    BOOL ok = FALSE;
    if (file == INVALID_HANDLE_VALUE) return FALSE;
    SetFilePointer(file, offset, NULL, FILE_BEGIN);
    if (!ReadFile(file, &value, 1, &count, NULL) || count != 1) goto done;
    value ^= 0x40;
    SetFilePointer(file, offset, NULL, FILE_BEGIN);
    ok = WriteFile(file, &value, 1, &count, NULL) && count == 1;
done:
    CloseHandle(file);
    return ok;
}

static DWORD file_size(const WCHAR *path) {
    WIN32_FILE_ATTRIBUTE_DATA data;
    return GetFileAttributesExW(path, GetFileExInfoStandard, &data) ? data.nFileSizeLow : 0;
}

int wmain(void) {
    WCHAR temp[MAX_PATH], path[MAX_PATH];
    SHORT growth[CCZ_GROWTH_HIGH_COUNT * CCZ_GROWTH_FIELDS] = {0};
    SHORT output[CCZ_GROWTH_HIGH_COUNT * CCZ_GROWTH_FIELDS];
    DWORD error, original_size;
    HANDLE lock;
    const DWORD body_size = 263760;
    CHECK(GetTempPathW(MAX_PATH, temp));
    CHECK(GetTempFileNameW(temp, L"cgt", 0, path));
    CHECK(write_body(path, body_size, 0x31, TRUE));
    memset(output, 0x7f, sizeof(output));
    CHECK(ccz_growth_read(path, output, &error) == 0 && error == 0);
    CHECK(output[0] == 0 && output[ARRAYSIZE(output)-1] == 0);
    /* 143 is the real character used in the isolated engine evidence. */
    growth[(143-CCZ_GROWTH_FIRST)*7+5] = 25;
    growth[(143-CCZ_GROWTH_FIRST)*7+6] = 8;
    growth[(214-CCZ_GROWTH_FIRST)*7+5] = 50;
    CHECK(ccz_growth_save(path, body_size, growth, &error));
    CHECK(file_size(path) == body_size + sizeof(growth) + 32);
    CHECK(ccz_growth_read(path, output, &error) == 1 && !memcmp(output, growth, sizeof(growth)));
    original_size = file_size(path);
    growth[(143-CCZ_GROWTH_FIRST)*7+5] = 28;
    CHECK(ccz_growth_save(path, body_size, growth, &error));
    CHECK(file_size(path) == original_size);
    CHECK(ccz_growth_read(path, output, &error) == 1 && !memcmp(output, growth, sizeof(growth)));
    CHECK(flip(path, body_size + 10));
    memset(output, 0x42, sizeof(output));
    CHECK(ccz_growth_read(path, output, &error) == -1 && output[0] == 0x4242);
    CHECK(flip(path, body_size + 10));
    CHECK(flip(path, 100));
    CHECK(ccz_growth_read(path, output, &error) == 0 && error == ERROR_SUCCESS);
    {
        SHORT cleared[CCZ_GROWTH_HIGH_COUNT * CCZ_GROWTH_FIELDS] = {0};
        CHECK(!memcmp(output, cleared, sizeof(output)));
    }
    /* A stale body does not excuse a corrupt extension payload. */
    CHECK(flip(path, body_size + 10));
    memset(output, 0x42, sizeof(output));
    CHECK(ccz_growth_read(path, output, &error) == -1 && output[0] == 0x4242);
    CHECK(flip(path, body_size + 10));
    CHECK(flip(path, 100));
    CHECK(ccz_growth_read(path, output, &error) == 1 && !memcmp(output, growth, sizeof(growth)));
    CHECK(flip(path, file_size(path)-1));
    CHECK(ccz_growth_read(path, output, &error) == -1);
    CHECK(flip(path, file_size(path)-1));
    CHECK(!ccz_growth_save(path, 42, growth, &error) && file_size(path) == original_size);
    CHECK(!ccz_growth_save(path, CCZ_GROWTH_MAX_SAVE_BYTES, growth, &error) && file_size(path) == original_size);
    CHECK(!ccz_growth_save(path, original_size+1, growth, &error) && file_size(path) == original_size);
    /* Simulate original engine overwriting a shorter body without truncating. */
    CHECK(write_body(path, body_size-1024, 0x22, FALSE));
    memset(output, 0x7f, sizeof(output));
    CHECK(ccz_growth_read(path, output, &error) == 0 && error == ERROR_SUCCESS);
    CHECK(output[0] == 0 && output[ARRAYSIZE(output)-1] == 0);
    CHECK(ccz_growth_save(path, body_size-1024, growth, &error));
    CHECK(file_size(path) == body_size-1024+sizeof(growth)+32);
    CHECK(ccz_growth_read(path, output, &error) == 1 && !memcmp(output, growth, sizeof(growth)));
    CHECK(write_body(path, body_size+2048, 0x23, FALSE));
    CHECK(ccz_growth_save(path, body_size+2048, growth, &error));
    CHECK(file_size(path) == body_size+2048+sizeof(growth)+32);
    CHECK(ccz_growth_read(path, output, &error) == 1 && !memcmp(output, growth, sizeof(growth)));
    lock = CreateFileW(path, GENERIC_READ, 0, NULL, OPEN_EXISTING, 0, NULL);
    CHECK(lock != INVALID_HANDLE_VALUE);
    CHECK(!ccz_growth_save(path, body_size+2048, growth, &error));
    CloseHandle(lock);
    CHECK(ccz_growth_read(path, output, &error) == 1 && !memcmp(output, growth, sizeof(growth)));
    CHECK(DeleteFileW(path));
    printf("Growth storage: %d checks passed.\n", checks);
    return 0;
}
