#include "ccz_growth_storage.h"
#include <string.h>
#include <wchar.h>

#pragma pack(push, 1)
typedef struct GrowthFooter {
    BYTE magic[8];
    DWORD version;
    DWORD count;
    DWORD body_size;
    DWORD body_crc;
    DWORD growth_crc;
    DWORD footer_crc;
} GrowthFooter;
#pragma pack(pop)

static const BYTE MAGIC[8] = {'C', 'C', 'Z', 'G', 'R', 'W', '1', 0};

static DWORD crc_update(DWORD crc, const BYTE *data, DWORD size) {
    DWORD i, j;
    for (i = 0; i < size; ++i) {
        crc ^= data[i];
        for (j = 0; j < 8; ++j)
            crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1u)));
    }
    return crc;
}

static DWORD crc(const void *data, DWORD size) {
    return ~crc_update(0xFFFFFFFFu, (const BYTE *)data, size);
}

static BOOL exact_read(HANDLE file, void *data, DWORD size) {
    DWORD count = 0;
    return ReadFile(file, data, size, &count, NULL) && count == size;
}

static BOOL exact_write(HANDLE file, const void *data, DWORD size) {
    DWORD count = 0;
    return WriteFile(file, data, size, &count, NULL) && count == size;
}

static BOOL read_crc(HANDLE file, DWORD size, HANDLE copy, DWORD *result) {
    BYTE buffer[65536];
    DWORD state = 0xFFFFFFFFu;
    while (size) {
        DWORD chunk = size < sizeof(buffer) ? size : sizeof(buffer);
        if (!exact_read(file, buffer, chunk)) return FALSE;
        if (copy != INVALID_HANDLE_VALUE && !exact_write(copy, buffer, chunk)) return FALSE;
        state = crc_update(state, buffer, chunk);
        size -= chunk;
    }
    *result = ~state;
    return TRUE;
}

int ccz_growth_read(const WCHAR *path, SHORT *output, DWORD *error) {
    HANDLE file;
    LARGE_INTEGER length, offset;
    GrowthFooter footer;
    SHORT payload[CCZ_GROWTH_HIGH_COUNT * CCZ_GROWTH_FIELDS];
    DWORD body_crc;
    int result = -1;
    *error = ERROR_INVALID_DATA;
    file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
    if (file == INVALID_HANDLE_VALUE) { *error = GetLastError(); return -1; }
    if (!GetFileSizeEx(file, &length) || length.QuadPart < 0 || length.QuadPart > CCZ_GROWTH_MAX_SAVE_BYTES) goto done;
    if (length.QuadPart < sizeof(footer)) { result = 0; goto done; }
    offset.QuadPart = length.QuadPart - sizeof(footer);
    if (!SetFilePointerEx(file, offset, NULL, FILE_BEGIN) || !exact_read(file, &footer, sizeof(footer))) goto done;
    if (memcmp(footer.magic, MAGIC, sizeof(MAGIC))) { result = 0; goto done; }
    if (footer.version != 1 || footer.count != CCZ_GROWTH_HIGH_COUNT ||
        footer.footer_crc != crc(&footer, sizeof(footer) - sizeof(DWORD)) ||
        footer.body_size < 0x30000 ||
        (ULONGLONG)footer.body_size + sizeof(payload) + sizeof(footer) != (ULONGLONG)length.QuadPart) goto done;
    offset.QuadPart = 0;
    if (!SetFilePointerEx(file, offset, NULL, FILE_BEGIN) ||
        !read_crc(file, footer.body_size, INVALID_HANDLE_VALUE, &body_crc) ||
        !exact_read(file, payload, sizeof(payload)) || crc(payload, sizeof(payload)) != footer.growth_crc) goto done;
    /* The original engine overwrites the body but leaves an old trailer in
     * place. Never apply that stale growth to the new body. Treat it like a
     * legacy save; the native loader remains responsible for the body. */
    if (body_crc != footer.body_crc) { result = 0; goto done; }
    memcpy(output, payload, sizeof(payload));
    result = 1;
done:
    CloseHandle(file);
    if (result == 0) ZeroMemory(output, sizeof(payload));
    if (result >= 0) *error = ERROR_SUCCESS;
    return result;
}

BOOL ccz_growth_save(const WCHAR *path, DWORD body_size, const SHORT *growth, DWORD *error) {
    HANDLE source = INVALID_HANDLE_VALUE, target = INVALID_HANDLE_VALUE;
    WCHAR directory[MAX_PATH], temporary[MAX_PATH] = {0};
    WCHAR *slash;
    LARGE_INTEGER size;
    GrowthFooter footer;
    BOOL success = FALSE;
    *error = ERROR_INVALID_DATA;
    if (body_size < 0x30000 || body_size > CCZ_GROWTH_MAX_SAVE_BYTES - CCZ_GROWTH_PAYLOAD_BYTES - sizeof(footer)) return FALSE;
    if (lstrlenW(path) >= MAX_PATH) { *error = ERROR_FILENAME_EXCED_RANGE; return FALSE; }
    lstrcpyW(directory, path);
    slash = wcsrchr(directory, L'\\');
    if (!slash) return FALSE;
    *slash = 0;
    source = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
    if (source == INVALID_HANDLE_VALUE) goto io_failed;
    if (!GetFileSizeEx(source, &size) || size.QuadPart < body_size) goto done;
    if (!GetTempFileNameW(directory, L"cgp", 0, temporary)) goto io_failed;
    target = CreateFileW(temporary, GENERIC_WRITE, 0, NULL, TRUNCATE_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (target == INVALID_HANDLE_VALUE) goto io_failed;
    ZeroMemory(&footer, sizeof(footer));
    memcpy(footer.magic, MAGIC, sizeof(MAGIC));
    footer.version = 1;
    footer.count = CCZ_GROWTH_HIGH_COUNT;
    footer.body_size = body_size;
    if (!read_crc(source, body_size, target, &footer.body_crc)) goto io_failed;
    footer.growth_crc = crc(growth, CCZ_GROWTH_PAYLOAD_BYTES);
    footer.footer_crc = crc(&footer, sizeof(footer) - sizeof(DWORD));
    if (!exact_write(target, growth, CCZ_GROWTH_PAYLOAD_BYTES) || !exact_write(target, &footer, sizeof(footer)) || !FlushFileBuffers(target)) goto io_failed;
    CloseHandle(target); target = INVALID_HANDLE_VALUE;
    CloseHandle(source); source = INVALID_HANDLE_VALUE;
    if (!MoveFileExW(temporary, path, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)) goto io_failed;
    temporary[0] = 0;
    success = TRUE;
    *error = ERROR_SUCCESS;
    goto done;
io_failed:
    *error = GetLastError();
done:
    if (target != INVALID_HANDLE_VALUE) CloseHandle(target);
    if (source != INVALID_HANDLE_VALUE) CloseHandle(source);
    if (temporary[0]) DeleteFileW(temporary);
    return success;
}
