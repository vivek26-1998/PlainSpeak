"""JSON file storage, one file per case.

Mutations are serialized per case and written via a temporary file plus atomic replace.
Only the backend reads and writes these files.
"""

import re
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from plainspeak.contracts import Case

_CASE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


class CaseNotFoundError(LookupError):
    pass


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


class CaseStore:
    def __init__(self, cases_dir: Path, uploads_dir: Path) -> None:
        self.cases_dir = cases_dir
        self.uploads_dir = uploads_dir
        self.cases_dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def _path(self, case_id: str) -> Path:
        if not _CASE_ID.match(case_id):
            raise CaseNotFoundError(case_id)
        return self.cases_dir / f"{case_id}.json"

    def _lock(self, case_id: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(case_id, threading.Lock())

    def exists(self, case_id: str) -> bool:
        return self._path(case_id).exists()

    def load(self, case_id: str) -> Case:
        path = self._path(case_id)
        if not path.exists():
            raise CaseNotFoundError(case_id)
        return Case.model_validate_json(path.read_text(encoding="utf-8"))

    def _write(self, case: Case) -> None:
        path = self._path(case.case_id)
        tmp = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
        tmp.write_text(case.model_dump_json(by_alias=True, indent=2), encoding="utf-8")
        tmp.replace(path)

    def create(self, case_id: str, *, reset: bool = False) -> Case:
        with self._lock(case_id):
            if self.exists(case_id) and not reset:
                return self.load(case_id)
            case = Case(case_id=case_id)
            self._write(case)
            return case

    @contextmanager
    def update(self, case_id: str) -> Iterator[Case]:
        """Load, let the caller mutate, then persist atomically. Not saved if the body raises."""
        with self._lock(case_id):
            case = self.load(case_id)
            yield case
            self._write(case)

    def upload_path(self, case_id: str, source_id: str) -> Path:
        self._path(case_id)  # validates the case id
        return self.uploads_dir / f"{case_id}_{source_id}.pdf"
