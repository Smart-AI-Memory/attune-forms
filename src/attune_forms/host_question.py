"""Host-profile structured-question renderer (attune-ai host-surface-parity AF-2).

A host's built-in question control (Claude Code's ``AskUserQuestion`` is
the first) is described by a :class:`HostQuestionProfile` facet on the
installed :class:`~attune_forms.conformance.InteractionProfile`. The
profile, never a vendor name or a universal constant, declares the
question and option limits, multi-select support, the reserved free-text
label and where free text arrives, cancellation, validation-feedback
delivery with its finite attempt cap and response deadline, the closed
text-normalization algorithms, the raw multi-select response encoding,
and how responses correlate back to questions.

Two pure functions consume it:

- :func:`host_question_admissibility` decides, before any render, whether
  a form can be asked on the profile without truncation or ambiguity.
- :func:`form_to_host_question` renders an admissible form to one frozen
  :class:`HostQuestionBatch`: the host-visible ``payload`` plus immutable
  ``answer_bindings`` the server retains to map raw host answers back to
  option ids. A direct call on an inadmissible form returns ``None``.

The package keeps no hidden state and ships no raw-host decoder: response
correlation, Other/cancellation decoding, validation feedback, retries,
deadlines and receipts belong to the consuming server adapter
(attune-ai Task 2).

Copyright 2026 Smart-AI-Memory
Licensed under Apache 2.0
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

from attune_forms.models import FormQuestion, FormSchema, QuestionType

#: Closed vocabularies. Every profile field that names an algorithm or a
#: mode draws from one of these; an unknown value fails at construction.
CORRELATION_MODES: tuple[str, ...] = ("question_id", "emitted_text", "ordinal")
NORMALIZATIONS: tuple[str, ...] = ("exact", "nfc_casefold_collapse_whitespace")
FREEFORM_MODES: tuple[str, ...] = ("none", "separate_response", "option_token")
FEEDBACK_MODES: tuple[str, ...] = ("none", "re_ask")
ENCODING_KINDS: tuple[str, ...] = ("list", "comma_delimited")
ATOM_KINDS: tuple[str, ...] = ("emitted_label", "response_token")
ESCAPINGS: tuple[str, ...] = ("none", "json_quote_when_delimiter_or_quote")

#: The recommendation marker appended to the emitted label of the one
#: recommended option. It is part of the exact emitted label and of the
#: bound response atom; a consumer resolves it through the binding and
#: never strips it.
RECOMMENDED_SUFFIX = " (Recommended)"

#: Question types whose flat payload ``default`` is a recommendation or a
#: proposal (decision/pushback/deliberation/progress carry ``recommended``;
#: triage/ranking/assumption review carry ``suggested``). A plain select's
#: ``default`` is a default, not a recommendation, and is never suffixed.
_RECOMMENDATION_TYPES = frozenset(
    {
        QuestionType.DECISION,
        QuestionType.PUSHBACK,
        QuestionType.DELIBERATION,
        QuestionType.PROGRESS,
        QuestionType.TRIAGE,
        QuestionType.RANKING,
        QuestionType.ASSUMPTION_REVIEW,
    }
)

#: Flat payload types a host question control can carry. Everything else
#: (``text_input``, ``textarea``, ``number``, ``date``) has no option list
#: and is asked conversationally or on a richer surface instead.
_HOST_CONTROL_TYPES = frozenset({"single_select", "multi_select"})


def _check_vocab(name: str, value: str, vocabulary: tuple[str, ...]) -> None:
    if value not in vocabulary:
        raise ValueError(f"{name} must be one of {vocabulary}, got {value!r}")


def _positive_int(name: str, value: Any) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer, got {value!r}")


@dataclass(frozen=True)
class MultiSelectEncoding:
    """How a host returns a multi-select answer, declared as data.

    ``kind`` is ``list`` (one atom per element) or ``comma_delimited``
    (one string; atoms joined with ``delimiter``). ``atom`` says what each
    element is: the exact emitted label or a host token the binding must
    carry. ``escaping`` names the closed rule for atoms that contain the
    delimiter or a quote. ``canonical_reencode`` requires a decoder to
    accept a raw string only when re-encoding the decoded atoms reproduces
    it byte for byte.
    """

    kind: str = "list"
    delimiter: str | None = None
    atom: str = "emitted_label"
    escaping: str = "none"
    canonical_reencode: bool = False

    def __post_init__(self) -> None:
        _check_vocab("encoding kind", self.kind, ENCODING_KINDS)
        _check_vocab("atom kind", self.atom, ATOM_KINDS)
        _check_vocab("escaping", self.escaping, ESCAPINGS)
        if self.kind == "comma_delimited" and not self.delimiter:
            raise ValueError("comma_delimited encoding requires a non-empty delimiter")
        if self.kind == "list" and self.delimiter is not None:
            raise ValueError("list encoding carries no delimiter")
        if self.escaping != "none" and self.kind != "comma_delimited":
            raise ValueError("escaping applies only to comma_delimited encoding")

    def encode(self, atoms: Sequence[str]) -> str | list[str]:
        """Encode response atoms the way the host would return them.

        Used to construct canonical fixtures. ``list`` returns the atoms;
        ``comma_delimited`` joins them, JSON-string-quoting any atom that
        contains the delimiter or a double quote when that escaping rule
        is declared.
        """
        if self.kind == "list":
            return list(atoms)
        delimiter = self.delimiter or ""
        if self.escaping == "none":
            return delimiter.join(atoms)
        return delimiter.join(
            json.dumps(atom) if (delimiter in atom or '"' in atom) else atom for atom in atoms
        )


@dataclass(frozen=True)
class HostQuestionProfile:
    """The structured-question facet of an installed interaction profile.

    The containing ``InteractionProfile.id`` is the sole profile identity;
    this facet has none of its own. Every field is immutable metadata a
    consumer may rely on; changing any field changes the serialized facet
    and therefore every digest built on it.
    """

    max_questions: int
    max_options: int
    min_options: int = 2
    max_header_chars: int | None = None
    max_option_label_chars: int | None = None
    multi_select: bool = False
    other_label: str = "Other"
    freeform: str = "none"
    cancellation: bool = False
    validation_feedback: str = "none"
    max_validation_attempts: int = 1
    response_deadline_seconds: int = 600
    question_text_normalization: str = "exact"
    option_label_normalization: str = "exact"
    response_correlation: str = "emitted_text"
    multi_select_encoding: MultiSelectEncoding = field(default_factory=MultiSelectEncoding)
    recommended_suffix: str = RECOMMENDED_SUFFIX
    unanswered_marker: str | None = None
    inadmissible_types: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("max_questions", "max_options", "min_options"):
            _positive_int(name, getattr(self, name))
        for name in ("max_header_chars", "max_option_label_chars"):
            value = getattr(self, name)
            if value is not None:
                _positive_int(name, value)
        if self.min_options > self.max_options:
            raise ValueError("min_options must not exceed max_options")
        _positive_int("max_validation_attempts", self.max_validation_attempts)
        _positive_int("response_deadline_seconds", self.response_deadline_seconds)
        _check_vocab("freeform", self.freeform, FREEFORM_MODES)
        _check_vocab("validation_feedback", self.validation_feedback, FEEDBACK_MODES)
        _check_vocab(
            "question_text_normalization", self.question_text_normalization, NORMALIZATIONS
        )
        _check_vocab("option_label_normalization", self.option_label_normalization, NORMALIZATIONS)
        _check_vocab("response_correlation", self.response_correlation, CORRELATION_MODES)
        if not isinstance(self.multi_select_encoding, MultiSelectEncoding):
            raise TypeError("multi_select_encoding must be a MultiSelectEncoding")
        if not self.other_label.strip():
            raise ValueError("other_label must not be empty")
        if not self.recommended_suffix:
            raise ValueError("recommended_suffix must not be empty")
        object.__setattr__(self, "inadmissible_types", tuple(self.inadmissible_types))
        known = {t.value for t in QuestionType}
        unknown = [t for t in self.inadmissible_types if t not in known]
        if unknown:
            raise ValueError(f"inadmissible_types names unknown question types: {unknown}")

    def normalize_question_text(self, text: str) -> str:
        """Apply the declared question-text normalization."""
        return _normalize(text, self.question_text_normalization)

    def normalize_option_label(self, label: str) -> str:
        """Apply the declared option-label normalization."""
        return _normalize(label, self.option_label_normalization)

    def serialize(self) -> dict[str, Any]:
        """The complete facet as JSON-safe data; the digest input."""
        return asdict(self)


def _normalize(text: str, algorithm: str) -> str:
    if algorithm == "exact":
        return text
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


#: Claude Code's built-in ``AskUserQuestion`` as observed on the desktop
#: Code tab (Claude Code 2.1.260, 2026-09-07 live trial recorded in
#: attune-ai ``docs/probes/host-surface-parity/host-native-trials-2026-09-07.md``):
#: 1–4 questions per call, 2–4 options each, a ``header`` of at most 12
#: characters, ``multiSelect``, a built-in "Other" whose free text is the
#: host's separate global response, Escape cancels the call (a tool error,
#: no answers), a skipped question returns the literal ``[No preference]``,
#: and a multi-select answer returns the chosen labels joined by a bare
#: comma. The comma-space delimiter the parity design text assumed was not
#: observed. Quoting of an atom that itself contains the delimiter is
#: declared, not yet observed. The option-label bound is profile policy
#: (the tool asks for concise labels), not a measured host limit. Ranking
#: is inadmissible by ruling (attune-ai D16): the control has no ordering
#: affordance and the per-slot expansion cannot remove already-picked
#: options.
ASKUSERQUESTION_HOST_QUESTION = HostQuestionProfile(
    max_questions=4,
    max_options=4,
    min_options=2,
    max_header_chars=12,
    max_option_label_chars=100,
    multi_select=True,
    other_label="Other",
    freeform="separate_response",
    cancellation=True,
    validation_feedback="re_ask",
    max_validation_attempts=3,
    response_deadline_seconds=1800,
    question_text_normalization="nfc_casefold_collapse_whitespace",
    option_label_normalization="nfc_casefold_collapse_whitespace",
    response_correlation="emitted_text",
    multi_select_encoding=MultiSelectEncoding(
        kind="comma_delimited",
        delimiter=",",
        atom="emitted_label",
        escaping="json_quote_when_delimiter_or_quote",
        canonical_reencode=True,
    ),
    unanswered_marker="[No preference]",
    inadmissible_types=(QuestionType.RANKING.value,),
)


@dataclass(frozen=True)
class Admissibility:
    """Pre-render verdict: can ``form`` be asked on the profile without loss?"""

    admissible: bool
    problems: tuple[str, ...]
    question_count: int


@dataclass(frozen=True)
class QuestionAnswerBinding:
    """Server-side binding from one emitted question back to its options.

    ``option_bindings`` is ordered as emitted: ``(emitted_label,
    response_atom, option_id)``. The atom equals the emitted label only
    when the profile declares ``atom: emitted_label``.
    """

    question_id: str
    ordinal: int
    emitted_text: str
    option_bindings: tuple[tuple[str, str, str], ...]


@dataclass(frozen=True)
class HostQuestionBatch:
    """One host call: the visible ``payload`` plus retained bindings.

    Only ``payload`` crosses the host boundary. ``answer_bindings`` stay
    with the server adapter that will correlate the raw response.
    """

    payload: dict[str, Any]
    answer_bindings: tuple[QuestionAnswerBinding, ...]
    profile_id: str
    response_correlation: str


@dataclass(frozen=True)
class _Emitted:
    question_id: str
    ordinal: int
    text: str
    header: str
    multi_select: bool
    options: tuple[tuple[str, str, str], ...]
    descriptions: tuple[str, ...]


def _facet(profile: Any) -> HostQuestionProfile | None:
    """The facet of an interaction profile, or a bare facet passed directly."""
    if isinstance(profile, HostQuestionProfile):
        return profile
    facet = getattr(profile, "host_question", None)
    return facet if isinstance(facet, HostQuestionProfile) else None


def _header(question_id: str, ordinal: int, bound: int | None) -> str:
    """A short heading derived from the id; the ordinal label when it would overflow.

    Never truncates: a heading that does not fit the profile bound is
    replaced whole by ``Q<ordinal>``, which always fits.
    """
    text = " ".join(re.split(r"[_\-.]+", question_id)).strip()
    text = text[:1].upper() + text[1:]
    if bound is None or len(text) <= bound:
        return text
    return f"Q{ordinal}"


def _emit_question(
    source: FormQuestion, flat: dict[str, Any], ordinal: int, facet: HostQuestionProfile
) -> tuple[_Emitted | None, list[str]]:
    """Map one flat payload to a host question; every problem is named."""
    qid = str(flat["question_id"])
    problems: list[str] = []
    if source.type.value in facet.inadmissible_types:
        problems.append(f"{qid!r}: {source.type.value} is inadmissible on this profile")
    flat_type = str(flat.get("type"))
    if flat_type not in _HOST_CONTROL_TYPES:
        problems.append(f"{qid!r}: {flat_type} has no host question control")
    multi = flat_type == "multi_select"
    if multi and not facet.multi_select:
        problems.append(f"{qid!r}: profile has no multi-select control")
    if facet.multi_select_encoding.atom != "emitted_label":
        problems.append(
            f"{qid!r}: profile declares response tokens; this renderer binds emitted labels only"
        )
    options = [str(option) for option in (flat.get("options") or [])]
    if len(options) < facet.min_options:
        problems.append(
            f"{qid!r}: {len(options)} option(s), profile needs at least {facet.min_options}"
        )
    if len(options) > facet.max_options:
        problems.append(
            f"{qid!r}: {len(options)} options exceed the profile maximum {facet.max_options}"
        )
    if problems:
        return None, problems

    recommended = flat.get("default") if source.type in _RECOMMENDATION_TYPES else None
    ordered = list(options)
    if recommended in ordered:
        ordered = [recommended] + [option for option in ordered if option != recommended]
    bindings: list[tuple[str, str, str]] = []
    seen: dict[str, str] = {}
    other = facet.normalize_option_label(facet.other_label)
    for option in ordered:
        emitted = f"{option}{facet.recommended_suffix}" if option == recommended else option
        bound = facet.max_option_label_chars
        if bound is not None and len(emitted) > bound:
            problems.append(f"{qid!r}: emitted label {emitted!r} exceeds {bound} characters")
        normalized = facet.normalize_option_label(emitted)
        if normalized == other:
            problems.append(f"{qid!r}: option {emitted!r} collides with the reserved Other label")
        if normalized in seen:
            problems.append(f"{qid!r}: options {seen[normalized]!r} and {emitted!r} collide")
        seen.setdefault(normalized, emitted)
        bindings.append((emitted, emitted, option))
    if problems:
        return None, problems

    text = str(flat["question"])
    help_text = flat.get("help_text")
    if help_text:
        text = f"{text} — {help_text}"
    notes = source.option_notes or {}
    descriptions = tuple(str(notes.get(option_id, "")) for _, _, option_id in bindings)
    emitted_question = _Emitted(
        question_id=qid,
        ordinal=ordinal,
        text=text,
        header=_header(qid, ordinal, facet.max_header_chars),
        multi_select=multi,
        options=tuple(bindings),
        descriptions=descriptions,
    )
    return emitted_question, []


def _emit(form: FormSchema, facet: HostQuestionProfile) -> tuple[list[_Emitted], list[str]]:
    emitted: list[_Emitted] = []
    problems: list[str] = []
    if not form.questions:
        return emitted, ["form has no questions"]
    ordinal = 0
    for source in form.questions:
        for flat in source.to_ask_user_formats():
            ordinal += 1
            item, item_problems = _emit_question(source, flat, ordinal, facet)
            problems.extend(item_problems)
            if item is not None:
                emitted.append(item)
    if ordinal > facet.max_questions:
        problems.append(
            f"{ordinal} emitted questions exceed the profile maximum {facet.max_questions}"
        )
    if facet.response_correlation == "emitted_text":
        seen: dict[str, str] = {}
        for item in emitted:
            key = facet.normalize_question_text(item.text)
            if key in seen:
                problems.append(
                    f"questions {seen[key]!r} and {item.question_id!r} emit the same text "
                    "and cannot be correlated by emitted text"
                )
            seen.setdefault(key, item.question_id)
    return emitted, problems


def host_question_admissibility(form: FormSchema, profile: Any) -> Admissibility:
    """Decide before rendering whether ``form`` fits ``profile`` without loss.

    Pure. ``profile`` is an installed interaction profile carrying a
    host-question facet, or the facet itself. Every reason a form is
    inadmissible is named in ``problems``; nothing is truncated to fit.
    """
    facet = _facet(profile)
    if facet is None:
        return Admissibility(False, ("profile has no host-question facet",), 0)
    emitted, problems = _emit(form, facet)
    return Admissibility(not problems, tuple(problems), len(emitted))


def form_to_host_question(form: FormSchema, profile: Any) -> HostQuestionBatch | None:
    """Render ``form`` to one host question batch, or ``None`` when inadmissible.

    The routed path checks :func:`host_question_admissibility` first and
    selects another surface when it is false; this ``None`` is only the
    defensive answer to a direct call that skipped the predicate.
    """
    facet = _facet(profile)
    if facet is None:
        return None
    emitted, problems = _emit(form, facet)
    if problems:
        return None
    questions: list[dict[str, Any]] = []
    bindings: list[QuestionAnswerBinding] = []
    for item in emitted:
        question: dict[str, Any] = {
            "question": item.text,
            "header": item.header,
            "multiSelect": item.multi_select,
            "options": [
                {"label": label, "description": description}
                for (label, _, _), description in zip(item.options, item.descriptions, strict=False)
            ],
        }
        if facet.response_correlation == "question_id":
            question["question_id"] = item.question_id
        questions.append(question)
        bindings.append(
            QuestionAnswerBinding(
                question_id=item.question_id,
                ordinal=item.ordinal,
                emitted_text=item.text,
                option_bindings=item.options,
            )
        )
    return HostQuestionBatch(
        payload={"questions": questions},
        answer_bindings=tuple(bindings),
        profile_id=str(getattr(profile, "id", "")),
        response_correlation=facet.response_correlation,
    )


__all__ = [
    "ASKUSERQUESTION_HOST_QUESTION",
    "ATOM_KINDS",
    "CORRELATION_MODES",
    "ENCODING_KINDS",
    "ESCAPINGS",
    "FEEDBACK_MODES",
    "FREEFORM_MODES",
    "NORMALIZATIONS",
    "RECOMMENDED_SUFFIX",
    "Admissibility",
    "HostQuestionBatch",
    "HostQuestionProfile",
    "MultiSelectEncoding",
    "QuestionAnswerBinding",
    "form_to_host_question",
    "host_question_admissibility",
]
