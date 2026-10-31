r"""Full .ioc grammar from a corpus of real project files.

Sources: the 430 board .ioc shipped by the board manager, user projects found
under Documents, and projects generated during reverse engineering.

Produces analysis/ioc_grammar.json:
  key_patterns   regex-normalised key names with occurrence counts and examples
  namespaces     Mcu./ProjectManager./RCC./... groupings
  value_shapes   observed value forms per key pattern (bool/number/enum/list/pin)
  list_keys      keys using the indexed <base>N convention (Mcu.Pin0..)
  escaped        keys whose values contain \: or other escapes
  per_family     which key patterns appear for which MCU family
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
OUT = HERE / "analysis"
ROOT = Path(os.environ.get("USERPROFILE", str(Path.home())))

CORPORA = [
    Path(r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\db\plugins\boardmanager"),
    ROOT / "Documents",
    HERE / "build",
    HERE / "analysis" / "ioc_corpus",
]
INDEXED = re.compile(r"^(.*?)(\d{1,4})$")
PINISH = re.compile(r"^(P[A-E]\d{1,2})(?:-.*)?$")


def read_ioc(path: Path) -> list[tuple[str, str]]:
    rows = []
    try:
        text = path.read_text(encoding="iso-8859-1", errors="replace")
    except OSError:
        return rows
    for line in text.splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        rows.append((k.strip(), v))
    return rows


# filled from the corpus itself: every `Mcu.PinN` value is a real pin name
_PIN_NAMES: set[str] = set()
_PIN_NAMES_SORTED: list[str] = []


def load_pin_names(paths: list[Path]) -> None:
    pin_re = re.compile(r"^Mcu\.Pin\d+$")
    for p in paths:
        for k, v in read_ioc(p):
            if pin_re.match(k) and v.strip():
                _PIN_NAMES.add(v.strip())
    _PIN_NAMES_SORTED.extend(sorted(_PIN_NAMES, key=len, reverse=True))


IP_TOKEN = re.compile(r"^(?:[A-Z]{2,6}\d{0,2})(?:_[A-Z0-9]+)*$")
PINISH = re.compile(r"^(P[A-E]\d{1,2})(?:-[^.]*)?(?=\.|$)")
INDEXED_SUFFIX = re.compile(r"[-_]?(\d{1,3})(?=[.,#]|$)")


def _pin_prefix(key: str) -> str | None:
    """Return the pin name if the key is `<pin>` or `<pin>.<param>`."""
    head = key.split(".", 1)[0]
    if head in _PIN_NAMES:
        return head
    # `PC13-TAMPER-RTC.Signal` -> the db name carries the suffix
    base = head.split("-", 1)[0]
    if base in _PIN_NAMES and head.startswith(base + "-"):
        return head
    return None


def normalise(key: str) -> tuple[str, str | None]:
    """Collapse instance-specific keys into a reusable pattern."""
    pin = _pin_prefix(key)
    if pin:
        rest = key[len(pin):]
        return "PIN" + rest, pin
    m = PINISH.match(key)
    if m:
        return "PIN" + key[m.end():], m.group(1)
    head, _, tail = key.partition(".")
    idx = None
    m2 = INDEXED_SUFFIX.search(head)
    if m2 and not head.startswith(("RCC", "SYS", "VP_SYS")):
        idx = m2.group(1)
        head = head[: m2.start()] + head[m2.end():]
        head = head + "N" if not head.endswith("N") else head
    pattern = head + (("." + tail) if tail else "")
    pattern = re.sub(r"#\d+", "#N", pattern)
    pattern = re.sub(r"(\w)(\d{1,3})(?=[.,#]|$)", r"\1N", pattern)
    return pattern, idx


def shape(value: str) -> str:
    v = value.strip()
    if v == "":
        return "empty"
    if v in ("true", "false"):
        return "bool"
    if re.fullmatch(r"-?\d+", v):
        return "int"
    if re.fullmatch(r"0[xX][0-9a-fA-F]+", v):
        return "hex"
    if "\\:" in v:
        return "colon-escaped"
    if v.endswith(",") and "," in v[:-1]:
        return "trailing-comma-list"
    if "," in v:
        return "comma-list"
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", v):
        return "token"
    return "text"


def main() -> int:
    OUT.mkdir(exist_ok=True)
    files: list[Path] = []

    def walk(top: Path) -> None:
        stack = [top]
        while stack:
            d = stack.pop()
            try:
                with os.scandir(d) as it:
                    for de in it:
                        try:
                            if de.is_dir(follow_symlinks=False):
                                stack.append(Path(de.path))
                            elif de.name.lower().endswith(".ioc"):
                                files.append(Path(de.path))
                        except OSError:
                            pass
            except OSError:
                continue

    for base in CORPORA:
        if base.exists():
            walk(base)
    seen: set[Path] = set()
    uniq = []
    for f in files:
        r = f.resolve()
        if r in seen:
            continue
        seen.add(r)
        uniq.append(f)
    print(f"corpus: {len(uniq)} .ioc files")
    load_pin_names(uniq)
    print(f"pin names discovered: {len(_PIN_NAMES)}")
    patterns: dict[str, dict] = {}
    namespaces: Counter = Counter()
    occurrences: Counter = Counter()
    per_family: dict[str, set[str]] = defaultdict(set)
    examples: dict[str, str] = {}
    indexed_roots: Counter = Counter()
    escaped: Counter = Counter()
    families_seen: dict[str, str] = {}
    for f in uniq:
        rows = read_ioc(f)
        if not rows:
            continue
        fam = dict(rows).get("Mcu.Family", "?")
        families_seen[f.name] = fam
        for k, v in rows:
            pat, idx = normalise(k)
            namespaces[k.split(".")[0] if "." in k else "(root)"] += 1
            rec = patterns.setdefault(pat, {"count": 0, "shapes": Counter(),
                                            "distinct_values": set(),
                                            "families": set()})
            rec["count"] += 1
            rec["shapes"][shape(v)] += 1
            if len(rec["distinct_values"]) < 40:
                rec["distinct_values"].add(v[:120])
            rec["families"].add(fam)
            occurrences[pat] += 1
            pat2, idx2 = normalise(k)
            if idx is not None:
                indexed_roots[pat] += 1
            if "\\:" in v:
                escaped[k] += 1
            if re.fullmatch(r"[\w.\-\\:]+", v or "") and k.endswith(".Signal"):
                examples.setdefault(pat, v)
    per_family = {k: sorted(v["families"]) for k, v in patterns.items()}
    report = {
        "corpus_files": len(uniq),
        "families_in_corpus": sorted(set(families_seen.values())),
        "namespaces": dict(namespaces.most_common(200)),
        "key_patterns": {
            k: {"count": v["count"],
                "shapes": dict(v["shapes"]),
                "sample_values": sorted(v["distinct_values"])[:12],
                "families": sorted(v["families"])[:20]}
            for k, v in sorted(patterns.items(), key=lambda x: -x[1]["count"])},
        "indexed_list_roots": [k for k, _ in indexed_roots.most_common(120)],
        "escaped_value_keys": [k for k, _ in escaped.most_common(120)],
        "signal_examples": examples,
    }
    (OUT / "ioc_grammar.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"{len(patterns)} key patterns -> analysis/ioc_grammar.json")
    for k, v in list(report["key_patterns"].items())[:25]:
        print(f"  {v['count']:6d} {k}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
