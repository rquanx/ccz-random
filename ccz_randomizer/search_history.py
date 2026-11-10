"""Small persistent LRU for completed searches, independent of game snapshots."""
import json
import os
import sys
from pathlib import Path
from uuid import uuid4


def default_search_history_path(scope="recruitment"):
    directory = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
    return directory / "ccz_fast_data" / f"{scope}_searches.json"


def normalize_keyword(value):
    return " ".join(value.split()) if isinstance(value, str) else ""


class SearchHistory:
    def __init__(self, path: Path, limit=10):
        self.path, self.limit = Path(path), limit
        self.items = self._read() or []

    def _read(self):
        try:
            if self.path.stat().st_size > 32768:
                return None
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("version") != 1 or not isinstance(payload.get("keywords"), list):
                return None
            result, seen = [], set()
            for value in payload["keywords"]:
                word = normalize_keyword(value)
                if word and len(word) <= 128 and word.casefold() not in seen:
                    result.append(word)
                    seen.add(word.casefold())
                    if len(result) == self.limit:
                        break
            return result
        except (OSError, ValueError, TypeError):
            return None

    def remember(self, value, *, replace=None):
        word = normalize_keyword(value)
        if not word or len(word) > 128:
            return False
        current = self._read()
        current = self.items if current is None else current
        removed = {word.casefold()}
        if replace:
            removed.add(replace.casefold())
        updated = [word, *(item for item in current if item.casefold() not in removed)][:self.limit]
        if updated == self.items and current == self.items:
            return False
        self.items = updated
        temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.{uuid4().hex}.tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(json.dumps({"version": 1, "keywords": updated}, ensure_ascii=False), encoding="utf-8")
            temporary.replace(self.path)
        except OSError:
            pass  # Search and in-memory history remain usable in read-only folders.
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        return True


class SearchSession:
    """Fold newly recorded prefixes into the completed query while typing."""
    def __init__(self, history):
        self.history = history
        self.provisional = None

    def reset(self):
        self.provisional = None

    def remember(self, value, *, finalize=False):
        word = normalize_keyword(value)
        if not word:
            self.reset()
            return False
        existed = any(item.casefold() == word.casefold() for item in self.history.items)
        previous = self.provisional
        replacement = previous if previous and word.casefold().startswith(previous.casefold()) else None
        changed = self.history.remember(word, replace=replacement)
        self.provisional = None if finalize or existed and word != previous else word
        return changed
