from __future__ import annotations

import argparse
import struct
from pathlib import Path

import pefile


RT_ICON = 3
RT_GROUP_ICON = 14


def resource_type(pe: pefile.PE, resource_id: int):
    for entry in pe.DIRECTORY_ENTRY_RESOURCE.entries:
        if entry.id == resource_id:
            return entry
    raise ValueError(f"PE 中没有资源类型 {resource_id}")


def resource_data(pe: pefile.PE, entry) -> bytes:
    directory = entry.directory.entries[0]
    if hasattr(directory, "directory"):
        directory = directory.directory.entries[0]
    data = directory.data.struct
    return pe.get_data(data.OffsetToData, data.Size)


def extract_first_icon(executable: Path, output: Path) -> None:
    pe = pefile.PE(str(executable))
    pe.parse_data_directories(
        directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"]]
    )
    group_type = resource_type(pe, RT_GROUP_ICON)
    icon_type = resource_type(pe, RT_ICON)
    icon_entries = {
        entry.id: entry
        for entry in icon_type.directory.entries
    }

    group = resource_data(pe, group_type.directory.entries[0])
    reserved, icon_kind, count = struct.unpack_from("<HHH", group)
    if reserved != 0 or icon_kind != 1 or count == 0:
        raise ValueError("首个组图标资源格式无效")

    images: list[tuple[bytes, bytes]] = []
    for index in range(count):
        entry = group[6 + index * 14 : 6 + (index + 1) * 14]
        if len(entry) != 14:
            raise ValueError("组图标资源条目不完整")
        icon_id = struct.unpack_from("<H", entry, 12)[0]
        if icon_id not in icon_entries:
            raise ValueError(f"找不到组图标引用的图像资源 {icon_id}")
        images.append((entry[:8], resource_data(pe, icon_entries[icon_id])))

    header_size = 6 + count * 16
    offset = header_size
    directory = bytearray(struct.pack("<HHH", 0, 1, count))
    payload = bytearray()
    for metadata, image in images:
        directory.extend(metadata)
        directory.extend(struct.pack("<II", len(image), offset))
        payload.extend(image)
        offset += len(image)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(directory + payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    extract_first_icon(args.executable.resolve(), args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
