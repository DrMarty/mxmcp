"""Session state shared by all tools.

A *project* here is one CubeMX engine instance: CubeMX keeps exactly one project
in memory per process, so the server owns a small pool of warm processes and
maps `project_id` -> process. Every tool that mutates configuration goes through
the same engine that loaded/created the project, which keeps behaviour identical
to the GUI.

State files live under `<workspace>/projects/<project_id>/`:
  project.ioc      authoritative snapshot (written by `config saveas`)
  meta.json        mcu ref, toolchain, output dir, timestamps, flag cache
  mx.log           engine transcript for auditing failures
"""
from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from .catalog import Catalog
from .engine import DEFAULT_ROOT, EngineError, Session
from .ioc import IocProject

WORKSPACE = Path(os.environ.get("MXMCP_WORKSPACE",
                                Path.home() / ".mxmcp")).expanduser()
CUBEMX_ROOT = Path(os.environ.get("MXMCP_CUBEMX_ROOT", DEFAULT_ROOT))


def slug(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_.-]+", "_", text.strip())
    return s.strip("_") or "project"


@dataclass
class Project:
    pid: str
    dir: Path
    mcu: str = ""
    user_mcu: str = ""
    toolchain: str = ""
    output_dir: str = ""
    created: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)
    step: int = 0
    open: bool = False

    @property
    def ioc_path(self) -> Path:
        return self.dir / "project.ioc"

    @property
    def meta_path(self) -> Path:
        return self.dir / "meta.json"

    def meta(self) -> dict:
        return {
            "project_id": self.pid, "mcu": self.mcu, "user_mcu": self.user_mcu,
            "toolchain": self.toolchain, "output_dir": self.output_dir,
            "created": self.created, "updated": self.updated,
            "ioc": str(self.ioc_path),
        }

    def save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.meta_path.write_text(json.dumps(self.meta(), indent=1), encoding="utf-8")

    def ioc(self) -> IocProject:
        if not self.ioc_path.exists():
            raise RuntimeError(f"project {self.pid} has no saved .ioc yet")
        return IocProject.load(self.ioc_path)


class ProjectManager:
    """Owns warm engines, one per open project."""

    def __init__(self, max_open: int = 3) -> None:
        self.workspace = WORKSPACE
        self.workspace.mkdir(parents=True, exist_ok=True)
        (self.workspace / "projects").mkdir(exist_ok=True)
        self.max_open = max_open
        self.last_pid: str | None = None   # most recently used project
        self._lock = threading.RLock()
        self._projects: dict[str, Project] = {}
        self._sessions: dict[str, Session] = {}
        self.catalog = Catalog(CUBEMX_ROOT)
        self._load_existing()

    # ------------------------------------------------------------- storage
    def _load_existing(self) -> None:
        for meta in (self.workspace / "projects").glob("*/meta.json"):
            try:
                m = json.loads(meta.read_text(encoding="utf-8"))
            except Exception:
                continue
            pid = m.get("project_id") or meta.parent.name
            self._projects[pid] = Project(
                pid=pid, dir=meta.parent, mcu=m.get("mcu", ""),
                user_mcu=m.get("user_mcu", ""), toolchain=m.get("toolchain", ""),
                output_dir=m.get("output_dir", ""), created=m.get("created", 0.0),
                updated=m.get("updated", 0.0))

    def list_projects(self) -> list[dict]:
        rows = []
        for p in self._projects.values():
            d = p.meta()
            d["engine"] = p.pid in self._sessions
            d["has_ioc"] = p.ioc_path.exists()
            rows.append(d)
        rows.sort(key=lambda r: r["updated"], reverse=True)
        return rows

    def project_dir(self, name: str) -> Path:
        return self.workspace / "projects" / slug(name)

    def new_id(self, name: str) -> str:
        base = slug(name)
        pid, n = base, 1
        while pid in self._projects or self.project_dir(pid).exists():
            n += 1
            pid = f"{base}-{n}"
        return pid

    def abs_path(self, path: str | Path, pid: str | None = None) -> str:
        """Resolve a caller path to an absolute one.

        Absolute paths (and `~`) are used as given; a bare name resolves under the
        project directory when `pid` is supplied, otherwise under the workspace.
        CubeMX only accepts absolute paths for import/export/compare commands.
        """
        raw = str(path).strip().strip('"')
        if not raw:
            raise ValueError("empty path")
        cand = Path(raw).expanduser()
        if cand.is_absolute():
            return str(cand)
        base = self._projects[pid].dir if pid in self._projects else self.workspace
        return str((base / cand).resolve())

    def get(self, pid: str | None) -> Project:
        with self._lock:
            if pid is None:
                pid = self.last_pid or (next(iter(self._projects), None))
                if pid is None:
                    raise RuntimeError("no project is open; create one first")
            if pid not in self._projects:
                raise RuntimeError(f"unknown project {pid!r}; call project_list")
            self.last_pid = pid
            return self._projects[pid]

    def create(self, pid: str) -> Project:
        p = Project(pid=pid, dir=self.project_dir(pid))
        p.dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._projects[pid] = p
        p.save()
        return p

    # ------------------------------------------------------------- engines
    def engine(self, p: Project) -> Session:
        """Warm engine for this project (started on demand, restarted if dead).

        A fresh engine starts empty, so a project that already has a saved .ioc is
        transparently reloaded to restore the live state.
        """
        exe = Path(CUBEMX_ROOT) / "STM32CubeMX.exe"
        if not exe.exists():
            raise EngineError(
                "CubeMX is not installed at "
                f"{CUBEMX_ROOT}, so the engine-backed tools cannot run.\n"
                "Use the standalone tools instead (no installation needed):\n"
                "  standalone_info / standalone_create / standalone_pin /\n"
                "  standalone_mode / standalone_param / standalone_nvic /\n"
                "  standalone_validate / standalone_generate\n"
                "To enable the full engine, install STM32CubeMX and point\n"
                "  MXMCP_CUBEMX_ROOT  at the installation directory.")
        with self._lock:
            s = self._sessions.get(p.pid)
            if s is not None and s.alive:
                return s
            stale = p.pid in self._sessions
            self._sessions.pop(p.pid, None)
            self._evict_if_needed(keep=p.pid)
            s = Session(root=CUBEMX_ROOT, workdir=p.dir)
            self._sessions[p.pid] = s
            p.open = True
        if (stale or True) and p.ioc_path.exists():
            r = s.send(f"config load {p.ioc_path}", timeout=1200)
            if r.status != "OK":
                # keep the engine; the caller will see a clear error on first use
                pass
        return s

    def _evict_if_needed(self, keep: str) -> None:
        live = [k for k, v in self._sessions.items() if v.alive and k != keep]
        while len(live) >= self.max_open:
            victim = live.pop(0)
            try:
                self._sessions[victim].close()
            except Exception:
                pass
            self._sessions.pop(victim, None)

    def close_engine(self, pid: str) -> None:
        with self._lock:
            s = self._sessions.pop(pid, None)
        if s is not None:
            s.close()

    def close_all(self) -> None:
        for pid in list(self._sessions):
            self.close_engine(pid)

    # ------------------------------------------------------------- commands
    def run(self, p: Project, command: str, timeout: float = 900.0,
            keep_log: bool = True) -> dict:
        """Execute one CubeMX CLI command in the project's engine."""
        s = self.engine(p)
        res = s.send(command, timeout=timeout, keep_log=keep_log)
        p.step += 1
        return {"status": res.status, "command": command,
                "output": res.payload, "seconds": round(res.seconds, 2),
                "log": res.log, "hung": res.hung}

    def run_many(self, p: Project, commands: list[str],
                 timeout: float = 900.0) -> list[dict]:
        out = []
        for c in commands:
            r = self.run(p, c, timeout=timeout)
            out.append(r)
            if r["status"] != "OK":
                break
        return out

    def save(self, p: Project, extend: bool = True) -> dict:
        """Snapshot the live configuration into project.ioc (authoritative)."""
        target = p.dir / f"{slug(p.pid)}.ioc"
        if target.exists():
            target.unlink()
        cmd = f"config saveas {target}"
        r = self.run(p, cmd)
        produced = target
        if not produced.exists():
            # CubeMX may create <basename>/<basename>.ioc under the cwd
            alt = p.dir / slug(p.pid) / f"{slug(p.pid)}.ioc"
            if alt.exists():
                produced = alt
        if not produced.exists():
            raise EngineError(f"config saveas produced no .ioc ({r['output'][:200]})")
        if produced != p.ioc_path:
            shutil.copyfile(produced, p.ioc_path)
        if extend:
            ext = p.dir / "project_ext.ioc"
            if ext.exists():
                ext.unlink()
            self.run(p, f"config saveext {ext}")
        ioc = IocProject.load(p.ioc_path)
        p.mcu = ioc.mcu_name
        p.user_mcu = ioc.mcu_user_name or p.user_mcu
        p.updated = time.time()
        p.save()
        return {"project_id": p.pid, "ioc": str(p.ioc_path), "mcu": p.mcu,
                "status": r["status"]}

    def load_ioc(self, p: Project, path: Path) -> dict:
        r = self.run(p, f"config load {path}", timeout=1200)
        if r["status"] != "OK":
            raise EngineError(f"config load failed: {r['output'][:400]}")
        ioc = IocProject.load(path)
        p.mcu, p.user_mcu = ioc.mcu_name, ioc.mcu_user_name
        p.toolchain = ioc.project_option("TargetToolchain", p.toolchain)
        if Path(path).resolve() != p.ioc_path.resolve():
            shutil.copyfile(path, p.ioc_path)
        return {"project_id": p.pid, "mcu": p.mcu, "toolchain": p.toolchain,
                "ips": ioc.ips, "pins": len(ioc.pins)}

    def load_mcu(self, p: Project, mcu: str) -> dict:
        # `load` only accepts a CubeMX RefName (STM32F103C(8-B)Tx); a marketing
        # part number (STM32F103C8T6) makes the interpreter spin forever.
        ref = self.resolve_ref(mcu)
        r = self.run(p, f"load {ref}", timeout=600)
        if r["status"] != "OK":
            raise EngineError(f"load {ref} failed: {r['output'][:400]}")
        name = self.run(p, "get mcu name", timeout=120)
        p.mcu = (name["output"].strip().splitlines() or [ref])[-1]
        p.user_mcu = mcu
        return {"project_id": p.pid, "mcu": p.mcu, "requested": mcu}

    def resolve_ref(self, mcu: str) -> str:
        """Part number -> exact db RefName, with a friendly error message."""
        names = self.catalog.resolve_mcu(mcu)
        if not names:
            raise EngineError(
                f"unknown MCU {mcu!r}: not in the CubeMX database "
                f"({len(self.catalog.mcus())} parts). Try mcu_search first.")
        # prefer the shortest / most specific RefName
        return names[0]

    def load_board(self, p: Project, board: str, mode: str = "nomode") -> dict:
        r = self.run(p, f"loadboard {board} {mode}", timeout=1200)
        if r["status"] != "OK":
            raise EngineError(f"loadboard {board} failed: {r['output'][:400]}")
        name = self.run(p, "get mcu name", timeout=120)
        p.mcu = name["output"].strip().splitlines()[-1]
        p.user_mcu = board
        return {"project_id": p.pid, "board": board, "mcu": p.mcu}
