"""Renderer registry, no-escape sweep and digests (host-surface-parity AF-1).

The registry is the package's public, non-empty inventory of every
production projection of a :class:`FormSchema` or :class:`WorkspaceView`.
A record names its RICH, PORTABLE and HEADLESS targets and any
host-native targets; each target is a stable id plus the fully
qualified callable, a status and an evidence mode. The consuming gate
(attune-ai Task 1B) locks the released registry's digests, so every
field here is part of the contract.

The sweep proves no production renderer escapes the registry: it scans
``src/attune_forms`` for callables that accept a form or a workspace
view and return one of the closed ``projection_output_types``, plus
every ``form_to_*`` / ``workspace_to_*`` callable as a naming guardrail,
and requires each candidate to be exactly one registry target, an
``__all__`` export, or a fully qualified allowlist entry with a
rationale. Unresolved annotations fail closed.
"""

from __future__ import annotations

import ast
import functools
import importlib
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from attune_forms.canonical_fixtures import digest

PACKAGE = "attune_forms"
PACKAGE_ROOT = Path(__file__).resolve().parent

#: Input types a projection accepts (annotation text as written).
INPUT_TYPES: frozenset[str] = frozenset({"FormSchema", "WorkspaceView"})

#: Closed vocabulary of projection return annotations. Adding or
#: removing an entry is registry drift by construction.
projection_output_types: tuple[str, ...] = (
    "str",
    "dict[str, Any]",
    "list[list[dict[str, Any]]]",
)

SURFACES = ("rich", "portable", "headless", "host_native")
STATUSES = ("core", "route_active", "compatibility_only")
EVIDENCE_MODES = {
    "core": "projection",
    "route_active": "route_roundtrip",
    "compatibility_only": "compatibility_projection",
}

#: The legacy fixed-shape AskUserQuestion contract the specialized
#: renderer binds. The digest pins the canonical fixture's exact output.
ASKUSERQUESTION_CONTRACT_ID = "claude-code.askuserquestion/v1"
ASKUSERQUESTION_SHAPE_DIGEST = "a1ad02822880a84cbff0bf580cd9ff20e9d6da99939e50725770e3dcb3b5f5b9"


class RegistryError(ValueError):
    """The registry or the sweep found problems; ``problems`` names each."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = list(problems)


@dataclass(frozen=True)
class RendererTarget:
    """One projection callable and its evidence contract."""

    target_id: str
    surface: str
    module: str
    name: str
    status: str = "core"
    evidence_mode: str = "projection"
    profile_id: str = ""
    compatibility_contract_id: str = ""
    compatibility_shape_digest: str = ""

    @property
    def qualname(self) -> str:
        return f"{self.module}.{self.name}"

    def resolve(self) -> Callable[..., Any]:
        """Import and return the target callable."""
        return getattr(importlib.import_module(self.module), self.name)


@dataclass(frozen=True)
class RendererRecord:
    """One renderer family: the projections of a single input type."""

    record_id: str
    family: str
    input_type: str
    fixture: str
    targets: tuple[RendererTarget, ...] = field(default_factory=tuple)

    def target(self, surface: str) -> RendererTarget:
        """The first target for a surface (``host_native`` may repeat; use ``targets``)."""
        for t in self.targets:
            if t.surface == surface:
                return t
        raise KeyError(surface)


@dataclass(frozen=True)
class AllowlistEntry:
    """A public callable that looks like a projection but is not one."""

    qualname: str
    rationale: str


def _t(target_id: str, surface: str, module: str, name: str, **kw: str) -> RendererTarget:
    return RendererTarget(target_id, surface, f"{PACKAGE}.{module}", name, **kw)


RENDERER_REGISTRY: tuple[RendererRecord, ...] = (
    RendererRecord(
        record_id="standalone-form",
        family="form",
        input_type="FormSchema",
        fixture=f"{PACKAGE}.canonical_fixtures.canonical_form",
        targets=(
            _t("form.rich", "rich", "widget", "form_to_widget_html"),
            _t("form.portable", "portable", "markdown_surface", "form_to_markdown"),
            _t("form.headless", "headless", "elicitation_schema", "form_to_elicitation_schema"),
            _t(
                "form.askuserquestion",
                "host_native",
                "bridge",
                "form_to_askuserquestion",
                status="compatibility_only",
                evidence_mode="compatibility_projection",
                compatibility_contract_id=ASKUSERQUESTION_CONTRACT_ID,
                compatibility_shape_digest=ASKUSERQUESTION_SHAPE_DIGEST,
            ),
        ),
    ),
    RendererRecord(
        record_id="generic-workspace",
        family="workspace",
        input_type="WorkspaceView",
        fixture=f"{PACKAGE}.canonical_fixtures.canonical_workspace_view",
        targets=(
            _t("workspace.rich", "rich", "workspace", "workspace_to_widget_html"),
            _t("workspace.portable", "portable", "workspace", "workspace_to_markdown"),
            _t("workspace.headless", "headless", "headless", "workspace_to_headless"),
        ),
    ),
)

#: Small, fully qualified, rationale-bearing. Mutation-tested.
SWEEP_ALLOWLIST: tuple[AllowlistEntry, ...] = (
    AllowlistEntry(
        f"{PACKAGE}.bridge.form_response_summary",
        "summarizes a FormResponse for the transcript; consumes the form only to label answers",
    ),
    AllowlistEntry(
        f"{PACKAGE}.markdown_ingestion.problems_to_markdown",
        "re-asks only the offending fields through the PORTABLE renderer's own field "
        "formatter; a partial re-ask, not a whole-form projection",
    ),
    AllowlistEntry(
        f"{PACKAGE}.bridge.select_form_surface",
        "returns the NAME of the surface to use (a routing decision), not a projection",
    ),
    AllowlistEntry(
        f"{PACKAGE}.markdown_surface.reply_skeleton",
        "the answer skeleton shared by the PORTABLE renderer and its partial re-ask; "
        "embedded verbatim in both outputs and bound by their implementation digests",
    ),
    AllowlistEntry(
        f"{PACKAGE}.canonical_fixtures.canonical_workspace_response",
        "builds the host's response payload from the HEADLESS projection's contract; "
        "an answer, not a projection",
    ),
)


def iter_targets(
    records: tuple[RendererRecord, ...] = RENDERER_REGISTRY,
) -> Iterator[RendererTarget]:
    """Every target of every record, in registry order."""
    for record in records:
        yield from record.targets


def validate_registry(records: tuple[RendererRecord, ...] = RENDERER_REGISTRY) -> None:
    """Raise :class:`RegistryError` naming every structural problem."""
    problems: list[str] = []
    if not records:
        problems.append("registry is empty")
    seen_records: set[str] = set()
    seen_targets: set[str] = set()
    for record in records:
        if record.record_id in seen_records:
            problems.append(f"duplicate record id {record.record_id!r}")
        seen_records.add(record.record_id)
        if record.input_type not in INPUT_TYPES:
            problems.append(
                f"{record.record_id}: input type {record.input_type!r} is not a projection input"
            )
        surfaces = [t.surface for t in record.targets]
        for required in ("portable", "headless"):
            if required not in surfaces:
                problems.append(f"{record.record_id}: missing required {required} target")
        route_active: set[str] = set()
        for t in record.targets:
            if t.target_id in seen_targets:
                problems.append(f"duplicate target id {t.target_id!r}")
            seen_targets.add(t.target_id)
            problems.extend(_target_problems(record, t, route_active))
    if problems:
        raise RegistryError(problems)


def _target_problems(
    record: RendererRecord, t: RendererTarget, route_active: set[str]
) -> list[str]:
    problems: list[str] = []
    if t.surface not in SURFACES:
        problems.append(f"{t.target_id}: unknown surface {t.surface!r}")
    if t.status not in STATUSES:
        problems.append(f"{t.target_id}: unknown status {t.status!r}")
    elif EVIDENCE_MODES[t.status] != t.evidence_mode:
        problems.append(
            f"{t.target_id}: status {t.status} requires evidence_mode "
            f"{EVIDENCE_MODES[t.status]!r}, got {t.evidence_mode!r}"
        )
    if t.surface != "host_native" and t.status != "core":
        problems.append(f"{t.target_id}: only host_native targets carry a host status")
    if t.surface == "host_native" and t.status == "core":
        problems.append(
            f"{t.target_id}: host_native targets must be route_active or compatibility_only"
        )
    if t.status == "route_active":
        if not t.profile_id:
            problems.append(f"{t.target_id}: route_active target must name its profile_id")
        if t.profile_id in route_active:
            problems.append(
                f"{record.record_id}: more than one route_active target for profile {t.profile_id!r}"
            )
        route_active.add(t.profile_id)
    if t.status == "compatibility_only":
        if t.profile_id:
            problems.append(f"{t.target_id}: compatibility_only target cannot name a live profile")
        if not (t.compatibility_contract_id and len(t.compatibility_shape_digest) == 64):
            problems.append(
                f"{t.target_id}: compatibility_only target needs a contract id and a sha256 shape digest"
            )
    try:
        if not callable(t.resolve()):
            problems.append(f"{t.qualname} is not callable")
    except (ImportError, AttributeError) as exc:
        problems.append(f"{t.qualname} does not resolve: {exc}")
    return problems


def record_digest(record: RendererRecord) -> str:
    """Owning-record-slice digest: every field, status and evidence mode included."""
    return digest(
        {
            "record_id": record.record_id,
            "family": record.family,
            "input_type": record.input_type,
            "fixture": record.fixture,
            "targets": [t.__dict__ for t in record.targets],
        }
    )


def registry_digest(records: tuple[RendererRecord, ...] = RENDERER_REGISTRY) -> str:
    """Digest over every record digest plus the closed vocabularies."""
    return digest(
        {
            "records": [record_digest(r) for r in records],
            "projection_output_types": list(projection_output_types),
            "allowlist": [e.__dict__ for e in SWEEP_ALLOWLIST],
        }
    )


# --- implementation digest --------------------------------------------------


def _module_path(module: str, root: Path) -> Path:
    return root / (module.removeprefix(PACKAGE + ".") + ".py")


@functools.lru_cache(maxsize=256)
def _module_index(module: str, root: Path) -> tuple[dict[str, str], dict[str, str]]:
    """(name -> source segment, name -> ``module:name`` it was imported from)."""
    source = _module_path(module, root).read_text(encoding="utf-8")
    tree = ast.parse(source)
    defs: dict[str, str] = {}
    imports: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            defs[node.name] = ast.get_source_segment(source, node) or ""
        elif isinstance(node, ast.Assign | ast.AnnAssign):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if isinstance(t, ast.Name):
                    defs[t.id] = ast.get_source_segment(source, node) or ""
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith(PACKAGE):
                origin = node.module
            elif node.level:
                origin = f"{PACKAGE}.{node.module}"
            else:
                continue
            for alias in node.names:
                imports[alias.asname or alias.name] = f"{origin}:{alias.name}"
    return defs, imports


def implementation_digest(target: RendererTarget, root: Path | None = None) -> str:
    """Cycle-safe digest of the target's statically resolvable package-local closure.

    Starts at the target callable and follows every referenced name that
    resolves to a module-level definition (function, class, constant,
    default, decorator) in the same package, across package-local
    imports. A name that does not resolve statically is outside the
    closure by construction: a behavior-affecting dynamic dependency
    must be referenced explicitly or it is not bound.
    """
    root = root or PACKAGE_ROOT
    seen: set[str] = set()
    segments: list[tuple[str, str]] = []
    stack = [(target.module, target.name)]
    while stack:
        module, name = stack.pop()
        key = f"{module}:{name}"
        if key in seen:
            continue
        seen.add(key)
        defs, imports = _module_index(module, root)
        if name in imports:
            other_module, other_name = imports[name].split(":", 1)
            stack.append((other_module, other_name))
            continue
        source = defs.get(name)
        if source is None:
            continue
        segments.append((key, source))
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Name) and node.id != name:
                stack.append((module, node.id))
    return digest(sorted(segments))


# --- no-escape sweep --------------------------------------------------------


@dataclass(frozen=True)
class SweepCandidate:
    """A callable the sweep decided is projection-shaped."""

    qualname: str
    reason: str  # "typed" | "naming" | "unresolved"
    detail: str = ""


@dataclass(frozen=True)
class SweepReport:
    """Every candidate found and every problem with how it is registered."""

    candidates: tuple[SweepCandidate, ...]
    problems: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.problems


def _strip_optional(text: str) -> str | None:
    """``Optional[T]`` / ``T | None`` -> ``T``; any other union -> None (unresolved)."""
    if text.startswith("Optional[") and text.endswith("]"):
        return text[len("Optional[") : -1]
    if "|" in text:
        rest = [a.strip() for a in text.split("|") if a.strip() != "None"]
        return rest[0] if len(rest) == 1 else None
    return text


def _accepts_projection_input(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    for arg in fn.args.posonlyargs + fn.args.args + fn.args.kwonlyargs:
        if arg.annotation is None:
            continue
        stripped = _strip_optional(ast.unparse(arg.annotation))
        if stripped in INPUT_TYPES:
            return stripped
    return None


def _cross_module_private_imports(root: Path) -> set[str]:
    """Private names imported from one production module into another."""
    used: set[str] = set()
    for path in root.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.ImportFrom) and node.module):
                continue
            module = node.module if node.module.startswith(PACKAGE) else f"{PACKAGE}.{node.module}"
            used.update(f"{module}.{a.name}" for a in node.names if a.name.startswith("_"))
    return used


def _classify(
    fn: ast.FunctionDef | ast.AsyncFunctionDef, qualname: str, public: bool
) -> tuple[SweepCandidate | None, str | None]:
    """(candidate or None, problem or None) for one module-level function."""
    naming = fn.name.startswith(("form_to_", "workspace_to_"))
    input_type = _accepts_projection_input(fn)
    if input_type is None and not naming:
        return None, None
    if fn.returns is None:
        if not (public or naming):
            return None, None
        return (
            SweepCandidate(qualname, "unresolved", "no return annotation"),
            f"{qualname}: accepts {input_type or 'a projection input'} but has no return "
            "annotation (fails closed)",
        )
    ret = ast.unparse(fn.returns)
    stripped = _strip_optional(ret)
    if stripped is None and (public or naming):
        return (
            SweepCandidate(qualname, "unresolved", ret),
            f"{qualname}: return annotation {ret!r} is an unresolved union (fails closed)",
        )
    typed = stripped in projection_output_types
    if not (typed and public) and not naming:
        return None, None
    return SweepCandidate(qualname, "typed" if typed else "naming", ret), None


def sweep_production_renderers(
    root: Path | None = None,
    records: tuple[RendererRecord, ...] = RENDERER_REGISTRY,
    allowlist: tuple[AllowlistEntry, ...] = SWEEP_ALLOWLIST,
    exports: frozenset[str] | None = None,
) -> SweepReport:
    """Find every projection-shaped callable and check it is registered exactly once.

    Args:
        root: Package directory to scan (defaults to this package).
        records: Registry to check against.
        allowlist: Non-renderer exceptions, each with a rationale.
        exports: The package's ``__all__``; defaults to the live package.
    """
    root = root or PACKAGE_ROOT
    if exports is None:
        exports = frozenset(importlib.import_module(PACKAGE).__all__)
    registered: dict[str, int] = {}
    for t in iter_targets(records):
        registered[t.qualname] = registered.get(t.qualname, 0) + 1
    allowed = {e.qualname for e in allowlist}
    private_used = _cross_module_private_imports(root)
    candidates: list[SweepCandidate] = []
    problems: list[str] = []
    for path in sorted(root.glob("*.py")):
        module = PACKAGE if path.stem == "__init__" else f"{PACKAGE}.{path.stem}"
        for fn in ast.parse(path.read_text(encoding="utf-8")).body:
            if not isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            qualname = f"{module}.{fn.name}"
            public = not fn.name.startswith("_") or qualname in private_used
            candidate, problem = _classify(fn, qualname, public)
            if candidate is None:
                continue
            candidates.append(candidate)
            if problem is not None:
                problems.append(problem)
                continue
            count = registered.get(qualname, 0)
            if count > 1:
                problems.append(f"{qualname}: registered {count} times; must be exactly once")
            elif count == 1:
                if fn.name not in exports:
                    problems.append(
                        f"{qualname}: registry target is not exported from {PACKAGE}.__all__"
                    )
            elif qualname not in allowed:
                problems.append(
                    f"{qualname}: projection-shaped callable is neither a registry target "
                    "nor allowlisted"
                )
    found = {c.qualname for c in candidates}
    problems.extend(
        f"{e.qualname}: allowlist entry matches no projection-shaped callable (stale)"
        for e in allowlist
        if e.qualname not in found
    )
    problems.extend(
        f"{e.qualname}: allowlist entry has no rationale"
        for e in allowlist
        if not e.rationale.strip()
    )
    problems.extend(
        f"{q}: registry target was not found by the sweep (moved, renamed, or unannotated)"
        for q in registered
        if q not in found
    )
    return SweepReport(tuple(candidates), tuple(problems))


__all__ = [
    "ASKUSERQUESTION_CONTRACT_ID",
    "ASKUSERQUESTION_SHAPE_DIGEST",
    "AllowlistEntry",
    "RENDERER_REGISTRY",
    "RegistryError",
    "RendererRecord",
    "RendererTarget",
    "SWEEP_ALLOWLIST",
    "SweepCandidate",
    "SweepReport",
    "implementation_digest",
    "iter_targets",
    "projection_output_types",
    "record_digest",
    "registry_digest",
    "sweep_production_renderers",
    "validate_registry",
]
