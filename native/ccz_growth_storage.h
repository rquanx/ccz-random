#ifndef CCZ_GROWTH_STORAGE_H
#define CCZ_GROWTH_STORAGE_H
#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#define CCZ_GROWTH_FIRST 102
#define CCZ_GROWTH_COUNT 215
#define CCZ_GROWTH_FIELDS 7
#define CCZ_GROWTH_HIGH_COUNT (CCZ_GROWTH_COUNT - CCZ_GROWTH_FIRST)
#define CCZ_GROWTH_PAYLOAD_BYTES (CCZ_GROWTH_HIGH_COUNT * CCZ_GROWTH_FIELDS * sizeof(SHORT))
#define CCZ_GROWTH_MAX_SAVE_BYTES (32 * 1024 * 1024)

/* 1: valid extension, 0: legacy/stale-body extension (output cleared),
 * -1: invalid extension or I/O failure (output unchanged). */
int ccz_growth_read(const WCHAR *path, SHORT *output, DWORD *error);
BOOL ccz_growth_save(const WCHAR *path, DWORD body_size, const SHORT *growth, DWORD *error);

#endif
