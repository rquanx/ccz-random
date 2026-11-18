"""Versioned game data profiles and safe profile package updates."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
import sys
import re
from functools import lru_cache
from urllib.parse import urlparse
from ccz_randomizer.profile_compatibility import require_profile_compatibility, PROFILE_COMPATIBILITY_ID
from threading import Lock
from ccz_randomizer.file_lock import process_lock

_INSTALL_LOCK = Lock()

DEFAULT_PROFILE_ID = "ccz-v2.20-1104-night"
PROFILE_SCHEMA_VERSION = 1
_PINNED_PROFILE_DIRECTORY: str | None = None
PROFILE_LOAD_ERROR = ""


def profile_id_for_game_version(version: str) -> str:
    if version == "2.2":
        return "ccz-v2.2"  # Archived fixtures and history only.
    profile = load_profile()
    if version in (profile.game_version, "2.20-1104"):
        return profile.root.name
    raise ValueError("没有匹配的游戏数据包")


def _embedded_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1])) / "resources" / "data" / "profiles"


def profile_storage_root(app_directory: Path) -> Path:
    return app_directory / "ccz_fast_data" / "profiles" / "channels" / PROFILE_COMPATIBILITY_ID


def _default_app_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"数据文件格式无效：{path.name}")
    return value


@dataclass(frozen=True)
class GameProfile:
    root: Path
    manifest: dict
    jobs: dict
    fixed_entries: dict
    recruitment: dict
    fingerprints: dict
    memory_layout: dict
    skills: dict
    script_rules: dict
    effect_dictionary: dict | None = None

    @property
    def profile_id(self) -> str:
        return self.manifest["profileId"]

    @property
    def game_version(self) -> str:
        return self.manifest["gameVersion"]

    def address(self, name: str) -> int:
        value = self.memory_layout.get(name)
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            return int(value, 0)
        raise ValueError(f"内存布局缺少地址：{name}")


def validate_profile(root: Path) -> GameProfile:
    manifest = _read_json(root / "manifest.json")
    require_profile_compatibility(manifest)
    if manifest.get("schemaVersion") != PROFILE_SCHEMA_VERSION:
        raise ValueError("不支持的数据包版本")
    profile_id = manifest.get("profileId")
    if not isinstance(profile_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,79}", profile_id):
        raise ValueError("数据包缺少 profileId")
    if manifest.get("engineLayout") != "personnel-v1":
        raise ValueError("该数据包需要更新工具引擎")
    if type(manifest.get("catalogVersion")) is not int or manifest["catalogVersion"] < 1:
        raise ValueError("数据包修订号无效")
    if not isinstance(manifest.get("gameVersion"), str) or not manifest["gameVersion"]:
        raise ValueError("数据包缺少游戏版本")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ValueError("数据包缺少文件清单")
    loaded = {}
    keys = ("jobs", "fixedEntries", "recruitment", "fingerprints", "memoryLayout", "skills", "scriptRules")
    if 'effectDictionary' in files:
        keys += ('effectDictionary',)
    for key in keys:
        name = files.get(key)
        if not isinstance(name, str) or Path(name).name != name:
            raise ValueError(f"数据包文件名无效：{key}")
        loaded[key] = _read_json(root / name)
        expected = manifest.get("sha256", {}).get(name)
        if not isinstance(expected, str) or hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"数据文件校验失败：{name}")
    jobs = loaded["jobs"].get("jobs")
    if not isinstance(jobs, list) or not jobs:
        raise ValueError("兵种目录为空")
    job_ids = {item.get("id") for item in jobs if isinstance(item, dict)}
    if len(job_ids) != len(jobs) or any(type(i) is not int for i in job_ids):
        raise ValueError("兵种编号重复或无效")
    for job in jobs:
        if not 0 <= job["id"] <= 255 or not isinstance(job.get("name"), str) or not job["name"] or type(job.get("score")) not in (int, float) or job.get("type") not in ("ALL_ROUNDER", "WARRIOR", "MASTER"):
            raise ValueError("兵种配置无效")
    members = loaded["fixedEntries"].get("members")
    if not isinstance(members, list) or not members:
        raise ValueError("固定入队目录为空")
    indices = [item.get("recordIndex") for item in members if isinstance(item, dict)]
    if len(indices) != len(set(indices)) or any(type(i) is not int or i < 0 or i >= 1024 for i in indices):
        raise ValueError("固定入队记录位置无效")
    people = loaded["recruitment"].get("people")
    if not isinstance(people, list) or not people:
        raise ValueError("招募目录为空")
    if any(item.get("recordIndex") in indices for item in people if isinstance(item, dict) and item.get("fixedConfiguration") is False):
        raise ValueError("固定入队与普通招募目录重叠")
    for person in members + people:
        if not isinstance(person, dict) or type(person.get("recordIndex")) is not int or not 0 <= person["recordIndex"] < 1024 or not isinstance(person.get("name"), str) or not person["name"]:
            raise ValueError("人物目录格式无效")
        if not isinstance(person.get("stages"), list) or not person["stages"]:
            raise ValueError("人物缺少入队关卡")
        for stage in person["stages"]:
            if not isinstance(stage, dict) or type(stage.get("stageId")) is not int or stage["stageId"] < 0:
                raise ValueError("人物关卡编号无效")
    order = loaded["fixedEntries"].get("memberOrder")
    if not isinstance(order, list) or len(order) != len(indices) or set(order) != set(indices):
        raise ValueError("固定入队排序无效")
    recruit_ids = [p["recordIndex"] for p in people]
    if len(set(recruit_ids)) != len(recruit_ids) or set(recruit_ids).intersection(indices):
        raise ValueError("人物记录编号重复")
    for person in people:
        if type(person.get("cost")) is not int or not 1 <= person["cost"] <= 4 or type(person.get("fixedConfiguration")) is not bool or not isinstance(person.get("jobChoices"), list) or any(not isinstance(x, str) for x in person["jobChoices"]):
            raise ValueError("招募配置无效")
        for stage in person["stages"]:
            if stage.get("route") not in ("共通", "红线", "蓝线") or not isinstance(stage.get("name"), str) or not stage["name"]:
                raise ValueError("招募关卡格式无效")
    for person in members:
        if any(not isinstance(stage.get("label"), str) or not stage["label"] for stage in person["stages"]):
            raise ValueError("固定入队关卡格式无效")
    layout = loaded["memoryLayout"]
    if layout.get("recordSize") != 72 or layout.get("recordJobOffset") != 43 or layout.get("recordIdOffset") != 4 or layout.get("recordNameOffset") != 8 or layout.get("recordIndexIdBase") != 4096:
        raise ValueError("人物结构变化，需要更新工具引擎")
    if not isinstance(loaded["skills"].get("defaults"), list) or not isinstance(loaded["skills"].get("runtimeCatalog"), list):
        raise ValueError("特技目录无效")
    for row in loaded["skills"]["defaults"]:
        if not isinstance(row, list) or len(row) != 4 or not isinstance(row[0], str) or type(row[1]) not in (int, float) or row[3] not in ("ALL_ROUNDER", "WARRIOR", "MASTER"):
            raise ValueError("特技评分格式无效")
    from ccz_randomizer.display_rules import validate_display_rules
    validate_display_rules(loaded["skills"].get("displayRules"), loaded["skills"].get("nameFormatting"))
    runtime_skills = loaded["skills"]["runtimeCatalog"]
    formatting = loaded["skills"].get("nameFormatting")
    if formatting is not None:
        if (not isinstance(formatting, dict)
                or set(formatting) != {"ability_short_names", "ability_names", "all_ability_name"}
                or not isinstance(formatting["all_ability_name"], str)
                or not formatting["all_ability_name"]
                or any(not isinstance(formatting[key], list) or len(formatting[key]) != count
                       or any(not isinstance(name, str) or not name for name in formatting[key])
                       for key, count in (("ability_short_names", 6), ("ability_names", 8)))):
            raise ValueError("特技名称格式表无效")
    if not runtime_skills or any(not isinstance(row, dict) or type(row.get("id")) is not int or not isinstance(row.get("name"), str) for row in runtime_skills):
        raise ValueError("运行特技目录无效")
    if len({row["id"] for row in runtime_skills}) != len(runtime_skills):
        raise ValueError("运行特技编号重复")
    for key in ("plannedJobArrayAddress", "recordArrayBasePointerAddress", "SKILL_RULE_TABLE_POINTER_ADDRESS", "DIRECT_JOB_MATCH_FLAG_ADDRESS", "SKILL_NAME_TABLE_ADDRESS", "ABILITY_SHORT_NAMES_ADDRESS", "ALL_ABILITY_NAME_ADDRESS", "ABILITY_NAMES_ADDRESS", "STRATEGY_NAMES_ADDRESS", "SKILL_RULE_COUNT", "SKILL_RULE_STRIDE", "SKILL_NAME_RECORD_SIZE", "STRATEGY_RECORD_SIZE"):
        value = layout.get(key)
        try:
            address = int(value, 0) if isinstance(value, str) else value
            if type(address) is not int or not 0 < address < 2**32:
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError(f"内存布局字段无效：{key}") from None
    try:
        rules = loaded["scriptRules"]
        for key in ("stageCondition", "assignPrefix", "assignMiddle"):
            if not bytes.fromhex(rules[key]):
                raise ValueError()
        for key, value in rules["stageExtras"].items():
            int(key)
            if not bytes.fromhex(value):
                raise ValueError()
        rules["recruitmentEnabledMarker"].encode("gb18030")
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ValueError("脚本规则格式无效") from None
    fingerprint_version = manifest.get("fingerprintVersion", manifest["gameVersion"])
    fingerprints = loaded["fingerprints"]
    if fingerprint_version not in fingerprints or not fingerprints[fingerprint_version].get("Ekd5.exe"):
        raise ValueError("缺少游戏指纹")
    for fileset in fingerprints.values():
        for name, digest in fileset.items():
            if not isinstance(name, str) or name.startswith(("/", "\\")) or ":" in name or ".." in name.replace("\\", "/").split("/"):
                raise ValueError("游戏指纹路径无效")
            if digest is not None and (not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)):
                raise ValueError("游戏指纹无效")
    if 'effectDictionary' in loaded:
        from ccz_randomizer.effect_dictionary_data import validate_effect_dictionary
        validate_effect_dictionary(loaded['effectDictionary'], manifest)
    return GameProfile(root, manifest, loaded["jobs"], loaded["fixedEntries"], loaded["recruitment"], fingerprints, layout, loaded["skills"], loaded["scriptRules"], loaded.get('effectDictionary'))


@lru_cache(maxsize=16)
def _load_immutable_profile(root: Path) -> GameProfile:
    return validate_profile(root)


def _load_profile(profile_id: str | None = None, *, app_directory: Path | None = None) -> GameProfile:
    global _PINNED_PROFILE_DIRECTORY
    pin_process = app_directory is None and profile_id is None
    automatic = profile_id is None
    pinned = pin_process and (_PINNED_PROFILE_DIRECTORY is not None or bool(os.environ.get("CCZ_PROFILE_DIRECTORY")))
    app_directory = app_directory or _default_app_directory()
    if profile_id is None:
        if pin_process and _PINNED_PROFILE_DIRECTORY is not None:
            selected = _PINNED_PROFILE_DIRECTORY
        else:
            active = profile_storage_root(app_directory) / "active.json"
            selected = (os.environ.get("CCZ_PROFILE_DIRECTORY") if pin_process else None) or (
                _read_json(active)["profileId"] if active.is_file() else DEFAULT_PROFILE_ID)
        if pin_process:
            if _PINNED_PROFILE_DIRECTORY is None:
                _PINNED_PROFILE_DIRECTORY = selected
            selected = _PINNED_PROFILE_DIRECTORY
        profile_id = selected
    if not isinstance(profile_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,79}", profile_id):
        raise ValueError("激活的数据包编号无效")
    external = profile_storage_root(app_directory) / profile_id
    if profile_id != DEFAULT_PROFILE_ID and (external / "manifest.json").is_file():
        candidate = _load_immutable_profile(external)
        if automatic and not pinned and candidate.profile_id == DEFAULT_PROFILE_ID:
            embedded_default = _load_immutable_profile(_embedded_root() / DEFAULT_PROFILE_ID)
            if candidate.manifest["catalogVersion"] < embedded_default.manifest["catalogVersion"]:
                if pin_process:
                    _PINNED_PROFILE_DIRECTORY = DEFAULT_PROFILE_ID
                return embedded_default
        return candidate
    embedded = _embedded_root() / profile_id
    return _load_immutable_profile(embedded)


def load_profile(profile_id: str | None = None, *, app_directory: Path | None = None) -> GameProfile:
    global PROFILE_LOAD_ERROR, _PINNED_PROFILE_DIRECTORY
    try:
        return _load_profile(profile_id, app_directory=app_directory)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        if profile_id is not None:
            raise
        PROFILE_LOAD_ERROR = f"更新数据包不可用，已使用内置数据包：{exc}"
        if app_directory is None:
            _PINNED_PROFILE_DIRECTORY = DEFAULT_PROFILE_ID
        return _load_immutable_profile(_embedded_root() / DEFAULT_PROFILE_ID)


def profile_fingerprint_manifest(profile: GameProfile) -> dict:
    return profile.fingerprints


def _safe_extract(archive: zipfile.ZipFile, target: Path) -> None:
    if len(archive.infolist()) > 64 or sum(x.file_size for x in archive.infolist()) > 16 * 1024 * 1024:
        raise ValueError("数据包超过大小限制")
    for member in archive.infolist():
        if "\\" in member.filename or ":" in member.filename or member.filename.startswith("/"):
            raise ValueError("数据包包含非法路径")
        destination = (target / member.filename).resolve()
        if target.resolve() not in destination.parents or (member.external_attr >> 16) & 0o170000 == 0o120000:
            raise ValueError("数据包包含非法路径")
    archive.extractall(target)


def install_profile_package(source: str | Path, app_directory: Path) -> GameProfile:
    """Install a local ZIP or HTTPS URL after strict validation."""
    with _INSTALL_LOCK:
        return _install_profile_package(source, app_directory)


def _install_profile_package(source: str | Path, app_directory: Path) -> GameProfile:
    app_directory = Path(app_directory)
    with tempfile.TemporaryDirectory(prefix="ccz-profile-") as temp:
        archive_path = Path(temp) / "profile.zip"
        source_text = str(source)
        if source_text.startswith(("https://", "http://")):
            if urlparse(source_text).scheme != "https":
                raise ValueError("下载地址必须使用 HTTPS")
            request = urllib.request.Request(source_text, headers={"User-Agent": "CCZRandomizer/4"})
            with urllib.request.urlopen(request, timeout=20) as response, archive_path.open("wb") as output:
                if urlparse(response.geturl()).scheme != "https":
                    raise ValueError("下载地址跳转到非 HTTPS 地址")
                total = 0
                while chunk := response.read(65536):
                    total += len(chunk)
                    if total > 8 * 1024 * 1024:
                        raise ValueError("下载的数据包超过大小限制")
                    output.write(chunk)
        else:
            if Path(source_text).stat().st_size > 8 * 1024 * 1024:
                raise ValueError("数据包超过大小限制")
            shutil.copyfile(Path(source_text), archive_path)
        extracted = Path(temp) / "unpacked"
        extracted.mkdir()
        with zipfile.ZipFile(archive_path) as archive:
            _safe_extract(archive, extracted)
        manifests = list(extracted.rglob("manifest.json"))
        if len(manifests) != 1:
            raise ValueError("压缩包必须包含且只能包含一个 profile manifest.json")
        profile = validate_profile(manifests[0].parent)
        target_root = profile_storage_root(app_directory)
        target_root.mkdir(parents=True, exist_ok=True)
        install_id = profile.profile_id[:66] + "." + profile_package_sha256(profile.root)[:12]
        target = target_root / install_id
        # Extraction/download is private and outside the lock. Only publication
        # is serialized; no process ever removes another installer's workspace.
        with tempfile.TemporaryDirectory(prefix=".staging-", dir=target_root) as staging_dir:
            staging = Path(staging_dir) / "package"
            shutil.copytree(profile.root, staging)
            validate_profile(staging)
            with process_lock(target_root / ".install.lock"):
                if target.exists():
                    validate_profile(target)
                else:
                    staging.replace(target)
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                        prefix=".active-", suffix=".tmp", dir=target_root, delete=False) as output:
                    active_tmp = Path(output.name)
                    json.dump({"profileId": install_id}, output)
                    output.flush()
                    os.fsync(output.fileno())
                try:
                    active_tmp.replace(target_root / "active.json")
                finally:
                    active_tmp.unlink(missing_ok=True)
        return validate_profile(target)


def restore_embedded_profile(app_directory: Path) -> None:
    root = profile_storage_root(app_directory)
    with _INSTALL_LOCK, process_lock(root / ".install.lock"):
        (root / "active.json").unlink(missing_ok=True)


def profile_package_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()
