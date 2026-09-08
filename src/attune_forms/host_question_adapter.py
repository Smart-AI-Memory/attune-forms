"""The consuming half of the host-question line: decode, re-ask, receipt.

AF-2 shipped the outbound half — a pure admissibility predicate and a
renderer returning a frozen :class:`~attune_forms.host_question.HostQuestionBatch`
whose ``answer_bindings`` stay server-side. This module is the inbound
half a server adapter needs, and it is deliberately the only place that
touches a raw host response.

Every value is reached through a binding or named as a problem. Nothing
here parses host display text heuristically, infers an answer from a
near match, or drops an unmappable atom: a host response that cannot be
correlated is a named failure, never a partial success. That is the same
rule the renderer applies outbound, where an over-cap form is a problem
rather than a truncation.

The decoder needs the form as well as the batch. One source question can
emit several host questions (``to_ask_user_formats`` expands a triage
into one question per item), and whether an emitted question is
multi-select is a property of that flat question, not of the binding.
Re-deriving the flat controls from the form is deterministic and costs
nothing, which is why :class:`~attune_forms.host_question.QuestionAnswerBinding`
did not have to grow a field it would carry for one consumer.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from attune_forms.bridge import FormValidationError, collect_form_response
from attune_forms.canonical_fixtures import digest
from attune_forms.host_question import (
    HostQuestionBatch,
    HostQuestionProfile,
    MultiSelectEncoding,
    QuestionAnswerBinding,
    form_to_host_question,
    host_question_admissibility,
)
from attune_forms.models import FormResponse, FormSchema

#: Terminal and continuable turn outcomes, in the order they are checked.
TURN_OUTCOMES: tuple[str, ...] = (
    "accepted",
    "cancelled",
    "undecodable",
    "invalid",
    "exhausted",
)


def _facet(profile: Any) -> HostQuestionProfile:
    """The facet of an interaction profile, or a bare facet passed directly."""
    if isinstance(profile, HostQuestionProfile):
        return profile
    facet = getattr(profile, "host_question", None)
    if not isinstance(facet, HostQuestionProfile):
        raise ValueError("profile declares no host_question facet")
    return facet


def _profile_id(profile: Any) -> str:
    """The containing profile's id; a bare facet has none of its own."""
    return "" if isinstance(profile, HostQuestionProfile) else str(getattr(profile, "id", ""))


def _flat_controls(form: FormSchema) -> dict[str, str]:
    """Flat question id to host control type, re-derived from the form.

    Mirrors the renderer's own expansion, so the keys are exactly the
    ``question_id``s the bindings carry.
    """
    return {
        str(flat["question_id"]): str(flat.get("type"))
        for question in form.questions
        for flat in question.to_ask_user_formats()
    }


def _correlation_key(binding: QuestionAnswerBinding, facet: HostQuestionProfile) -> str:
    """The raw-response key this binding correlates on."""
    if facet.response_correlation == "question_id":
        return binding.question_id
    if facet.response_correlation == "ordinal":
        return str(binding.ordinal)
    return facet.normalize_question_text(binding.emitted_text)


def _raw_key(key: str, facet: HostQuestionProfile) -> str:
    """A raw key normalized the way its correlation mode compares."""
    if facet.response_correlation == "emitted_text":
        return facet.normalize_question_text(key)
    return key


def _split_atoms(raw: str, encoding: MultiSelectEncoding) -> tuple[list[str], str | None]:
    """Split a delimited multi-select string into atoms, or name the problem."""
    delimiter = encoding.delimiter or ""
    if encoding.escaping == "none":
        return raw.split(delimiter), None
    decoder = json.JSONDecoder()
    atoms: list[str] = []
    index = 0
    length = len(raw)
    while True:
        if index < length and raw[index] == '"':
            try:
                atom, index = decoder.raw_decode(raw, index)
            except ValueError:
                return [], f"unparseable quoted atom at offset {index}"
            if not isinstance(atom, str):
                return [], f"quoted atom at offset {index} is not a string"
            atoms.append(atom)
        else:
            end = raw.find(delimiter, index)
            if end == -1:
                atoms.append(raw[index:])
                return atoms, None
            atoms.append(raw[index:end])
            index = end + len(delimiter)
            continue
        if index >= length:
            return atoms, None
        if not raw.startswith(delimiter, index):
            return [], f"expected {delimiter!r} after a quoted atom at offset {index}"
        index += len(delimiter)


@dataclass(frozen=True)
class HostQuestionDecoding:
    """A raw host response mapped back to flat question ids and option ids.

    ``answers`` is keyed by the FLAT question id the bindings carry, which
    is what :func:`~attune_forms.bridge.collect_form_response` folds back
    into canonical shape. A question whose host answer was the profile's
    unanswered marker is listed in ``unanswered`` and absent from
    ``answers`` — absent, never guessed.

    A question where the host user chose the reserved Other option is
    listed in ``other_selected``, with any separately-delivered text in
    ``freeform``. It is deliberately absent from ``answers``: Other is
    the host user rejecting every offered option, and free text is not a
    valid answer to a closed select. The caller re-asks, widens the
    options, or abandons — the adapter will not launder it into an answer.
    """

    answers: Mapping[str, Any]
    freeform: Mapping[str, str]
    unanswered: tuple[str, ...]
    other_selected: tuple[str, ...]
    cancelled: bool
    problems: tuple[str, ...]

    @property
    def ok(self) -> bool:
        """True when the response decoded cleanly and was not cancelled."""
        return not self.problems and not self.cancelled


def decode_host_question_response(
    form: FormSchema,
    batch: HostQuestionBatch,
    profile: Any,
    raw: Mapping[str, Any] | None,
    *,
    freeform: Mapping[str, str] | None = None,
) -> HostQuestionDecoding:
    """Correlate a raw host response back to typed answers via the bindings.

    Args:
        form: The form the batch was rendered from.
        batch: The retained batch, carrying the answer bindings.
        profile: The interaction profile (or bare facet) that rendered it.
        raw: The host's response, or ``None`` for a cancelled batch.
        freeform: Separately-delivered Other text, keyed by flat question id.

    Returns:
        A :class:`HostQuestionDecoding`. Problems are named, never silent.
    """
    facet = _facet(profile)
    problems: list[str] = []

    expected_profile = _profile_id(profile)
    if expected_profile and batch.profile_id != expected_profile:
        problems.append(
            f"batch was rendered for profile {batch.profile_id!r}, "
            f"decoding against {expected_profile!r}"
        )
    if batch.response_correlation != facet.response_correlation:
        problems.append(
            f"batch correlates on {batch.response_correlation!r}, "
            f"profile declares {facet.response_correlation!r}"
        )
    if problems:
        return HostQuestionDecoding({}, {}, (), (), False, tuple(problems))

    if raw is None:
        if facet.cancellation:
            return HostQuestionDecoding({}, {}, (), (), True, ())
        return HostQuestionDecoding(
            {}, {}, (), (), False, ("no response, and the profile declares no cancellation",)
        )
    if not isinstance(raw, Mapping):
        return HostQuestionDecoding(
            {}, {}, (), (), False, (f"raw response must be a mapping, got {type(raw).__name__}",)
        )

    controls = _flat_controls(form)
    supplied = dict(freeform or {})
    indexed: dict[str, Any] = {}
    for key, value in raw.items():
        normalized = _raw_key(str(key), facet)
        if normalized in indexed:
            problems.append(f"raw response repeats the key {key!r} under this correlation")
            continue
        indexed[normalized] = value

    answers: dict[str, Any] = {}
    unanswered: list[str] = []
    other_selected: list[str] = []
    consumed: set[str] = set()

    for binding in batch.answer_bindings:
        key = _correlation_key(binding, facet)
        if key not in indexed:
            problems.append(f"{binding.question_id!r}: no response under key {key!r}")
            continue
        consumed.add(key)
        value = indexed[key]
        decoded, item_problems = _decode_one(
            binding,
            value,
            facet,
            multi=controls.get(binding.question_id) == "multi_select",
        )
        problems.extend(item_problems)
        if item_problems:
            continue
        if decoded is _UNANSWERED:
            unanswered.append(binding.question_id)
        elif decoded is _OTHER:
            other_selected.append(binding.question_id)
            text = supplied.pop(binding.question_id, None)
            if facet.freeform == "none":
                problems.append(
                    f"{binding.question_id!r}: Other was chosen but the profile carries no free text"
                )
            elif text is None:
                problems.append(
                    f"{binding.question_id!r}: Other was chosen but no free text was supplied"
                )
        else:
            answers[binding.question_id] = decoded

    for key in indexed.keys() - consumed:
        problems.append(f"raw response carries key {key!r} that matches no binding")
    for key in supplied:
        problems.append(f"free text supplied for {key!r}, which did not choose Other")

    return HostQuestionDecoding(
        answers=answers,
        freeform={qid: (freeform or {})[qid] for qid in other_selected if qid in (freeform or {})},
        unanswered=tuple(unanswered),
        other_selected=tuple(other_selected),
        cancelled=False,
        problems=tuple(problems),
    )


class _Sentinel:
    """A decode outcome that is not an answer value."""

    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{self.name}>"


_UNANSWERED = _Sentinel("unanswered")
_OTHER = _Sentinel("other")


def _decode_one(
    binding: QuestionAnswerBinding,
    value: Any,
    facet: HostQuestionProfile,
    *,
    multi: bool,
) -> tuple[Any, list[str]]:
    """Decode one question's raw value to option ids, or name the problems."""
    qid = binding.question_id
    marker = facet.unanswered_marker
    if marker is not None and isinstance(value, str) and _is_marker(value, marker, facet):
        return _UNANSWERED, []

    atoms_by_label = {
        facet.normalize_option_label(atom): option_id
        for _, atom, option_id in binding.option_bindings
    }
    other = facet.normalize_option_label(facet.other_label)
    codec = facet.multi_select_encoding

    if not multi:
        if not isinstance(value, str):
            return None, [f"{qid!r}: expected a single label, got {type(value).__name__}"]
        return _map_atom(qid, value, atoms_by_label, other, facet)

    atoms, problem = _multi_atoms(qid, value, codec, facet)
    if problem is not None:
        return None, [problem]
    chosen: list[str] = []
    problems: list[str] = []
    for atom in atoms:
        mapped, item_problems = _map_atom(qid, atom, atoms_by_label, other, facet)
        if item_problems:
            problems.extend(item_problems)
        elif mapped is _OTHER:
            return _OTHER, []
        elif mapped is _UNANSWERED:
            problems.append(f"{qid!r}: the unanswered marker cannot be one of several selections")
        else:
            chosen.append(mapped)
    if problems:
        return None, problems
    if len(set(chosen)) != len(chosen):
        return None, [f"{qid!r}: the response selects the same option more than once"]
    return chosen, []


def _is_marker(value: str, marker: str, facet: HostQuestionProfile) -> bool:
    """Whether a raw value is the profile's unanswered marker."""
    return value == marker or facet.normalize_option_label(value) == facet.normalize_option_label(
        marker
    )


def _map_atom(
    qid: str,
    atom: str,
    atoms_by_label: Mapping[str, str],
    other: str,
    facet: HostQuestionProfile,
) -> tuple[Any, list[str]]:
    """Map one response atom to its bound option id, Other, or a problem."""
    normalized = facet.normalize_option_label(atom)
    if normalized in atoms_by_label:
        return atoms_by_label[normalized], []
    if normalized == other:
        return _OTHER, []
    marker = facet.unanswered_marker
    if marker is not None and normalized == facet.normalize_option_label(marker):
        return _UNANSWERED, []
    return None, [f"{qid!r}: response {atom!r} matches no emitted option"]


def _multi_atoms(
    qid: str,
    value: Any,
    codec: MultiSelectEncoding,
    facet: HostQuestionProfile,
) -> tuple[list[str], str | None]:
    """Decode a multi-select raw value into response atoms per the codec."""
    if codec.kind == "list":
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            return [], f"{qid!r}: profile declares a list encoding; got {type(value).__name__}"
        return list(value), None
    if not isinstance(value, str):
        return [], f"{qid!r}: profile declares a delimited string; got {type(value).__name__}"
    if codec.escaping != "none" and not codec.escaping_verified and '"' in value:
        return [], (
            f"{qid!r}: response uses quoting the host has not demonstrated "
            "(escaping_verified is false)"
        )
    atoms, problem = _split_atoms(value, codec)
    if problem is not None:
        return [], f"{qid!r}: {problem}"
    if codec.canonical_reencode and codec.encode(atoms) != value:
        return [], f"{qid!r}: response does not re-encode to itself under the declared codec"
    return atoms, None


@dataclass(frozen=True)
class HostQuestionReceipt:
    """What one host-question turn did, as a joinable record.

    ``facet_digest`` is the digest of the serialized facet, so a receipt
    cannot be silently re-read against a profile that has since changed.
    """

    profile_id: str
    facet_digest: str
    response_correlation: str
    attempt: int
    max_attempts: int
    outcome: str
    question_ids: tuple[str, ...]
    answered: tuple[str, ...]
    unanswered: tuple[str, ...]
    other_selected: tuple[str, ...]
    problems: tuple[str, ...]
    response_id: str

    def serialize(self) -> dict[str, Any]:
        """The receipt as JSON-safe data."""
        return {
            "profile_id": self.profile_id,
            "facet_digest": self.facet_digest,
            "response_correlation": self.response_correlation,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "outcome": self.outcome,
            "question_ids": list(self.question_ids),
            "answered": list(self.answered),
            "unanswered": list(self.unanswered),
            "other_selected": list(self.other_selected),
            "problems": list(self.problems),
            "response_id": self.response_id,
        }


@dataclass(frozen=True)
class HostQuestionTurn:
    """One decode-and-validate turn, plus the re-ask it licenses.

    ``next_form`` and ``next_batch`` are populated only when the outcome
    is ``invalid`` and the profile's attempt budget still allows a
    re-ask. They are ``None`` on every terminal outcome, so a caller that
    loops while ``turn.next_batch is not None`` cannot exceed the budget.
    """

    outcome: str
    decoding: HostQuestionDecoding
    response: FormResponse | None
    problems: tuple[str, ...]
    attempt: int
    next_form: FormSchema | None
    next_batch: HostQuestionBatch | None
    receipt: HostQuestionReceipt

    @property
    def done(self) -> bool:
        """True when no further host turn is licensed."""
        return self.next_batch is None


def _subset(form: FormSchema, field_ids: Sequence[str]) -> FormSchema:
    """The form narrowed to the named source questions, order preserved."""
    keep = [question for question in form.questions if question.id in set(field_ids)]
    return FormSchema(
        title=form.title,
        description=form.description,
        questions=keep,
        form_id=form.form_id,
    )


def _reask(
    form: FormSchema, profile: Any, error: FormValidationError
) -> tuple[FormSchema, HostQuestionBatch] | None:
    """The narrowest admissible re-ask for a validation failure, or None.

    Narrows to the offending questions only when every problem names one:
    an unattributed problem (an unknown answer key, a fold-time shape
    error) is not fixed by re-asking a subset, so the whole form goes
    back. An inadmissible subset falls back to the whole form rather
    than asking something the host cannot carry.
    """
    candidates: list[FormSchema] = []
    if error.fully_attributed and error.fields:
        candidates.append(_subset(form, error.fields))
    candidates.append(form)
    for candidate in candidates:
        if not candidate.questions:
            continue
        if not host_question_admissibility(candidate, profile).admissible:
            continue
        batch = form_to_host_question(candidate, profile)
        if batch is not None:
            return candidate, batch
    return None


def host_question_turn(
    form: FormSchema,
    batch: HostQuestionBatch,
    profile: Any,
    raw: Mapping[str, Any] | None,
    *,
    freeform: Mapping[str, str] | None = None,
    attempt: int = 1,
    template_id: str = "",
) -> HostQuestionTurn:
    """Decode one host response, validate it, and license a bounded re-ask.

    Stateless: the caller carries ``attempt`` across turns, which keeps
    the profile's ``max_validation_attempts`` budget auditable from the
    receipts alone rather than from adapter state.

    Args:
        form: The form the batch was rendered from.
        batch: The retained batch carrying the answer bindings.
        profile: The interaction profile (or bare facet) that rendered it.
        raw: The host's response, or ``None`` for a cancelled batch.
        freeform: Separately-delivered Other text, keyed by flat question id.
        attempt: 1-based attempt number for this exchange.
        template_id: Passed through to the validated response.

    Returns:
        A :class:`HostQuestionTurn`.
    """
    facet = _facet(profile)
    if attempt < 1:
        raise ValueError("attempt is 1-based")
    decoding = decode_host_question_response(form, batch, profile, raw, freeform=freeform)
    question_ids = tuple(binding.question_id for binding in batch.answer_bindings)

    def finish(
        outcome: str,
        *,
        response: FormResponse | None = None,
        problems: Sequence[str] = (),
        nxt: tuple[FormSchema, HostQuestionBatch] | None = None,
    ) -> HostQuestionTurn:
        receipt = HostQuestionReceipt(
            profile_id=batch.profile_id,
            facet_digest=digest(facet.serialize()),
            response_correlation=facet.response_correlation,
            attempt=attempt,
            max_attempts=facet.max_validation_attempts,
            outcome=outcome,
            question_ids=question_ids,
            answered=tuple(decoding.answers),
            unanswered=decoding.unanswered,
            other_selected=decoding.other_selected,
            problems=tuple(problems),
            response_id=response.response_id if response is not None else "",
        )
        return HostQuestionTurn(
            outcome=outcome,
            decoding=decoding,
            response=response,
            problems=tuple(problems),
            attempt=attempt,
            next_form=nxt[0] if nxt else None,
            next_batch=nxt[1] if nxt else None,
            receipt=receipt,
        )

    if decoding.cancelled:
        return finish("cancelled")
    if decoding.problems:
        # A response we cannot correlate will not correlate on a retry of
        # the same batch, so this is terminal rather than a re-ask.
        return finish("undecodable", problems=decoding.problems)

    try:
        response = collect_form_response(form, dict(decoding.answers), template_id=template_id)
    except FormValidationError as error:
        exhausted = facet.validation_feedback == "none" or attempt >= facet.max_validation_attempts
        nxt = None if exhausted else _reask(form, profile, error)
        if nxt is None:
            return finish("exhausted", problems=tuple(error.problems))
        return finish("invalid", problems=tuple(error.problems), nxt=nxt)
    return finish("accepted", response=response)


__all__ = [
    "TURN_OUTCOMES",
    "HostQuestionDecoding",
    "HostQuestionReceipt",
    "HostQuestionTurn",
    "decode_host_question_response",
    "host_question_turn",
]
