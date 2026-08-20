"""Form data models — the surface-agnostic elicitation artifact.

`FormSchema` / `FormQuestion` / `FormResponse` and the `QuestionType`
vocabulary, extracted from attune-ai's meta_workflows models. These are
pure dataclasses (stdlib only): every renderer and validator in this
package operates on them, and host applications may re-export them for
backward-compatible import paths.

Copyright 2026 Smart-AI-Memory
Licensed under Apache 2.0
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class QuestionType(str, Enum):
    """Types of form questions supported.

    The first four are v1 controls (rendered via AskUserQuestion). The
    last three are v2.1 rich controls — natively expressible on the MCP
    elicitation surface (D8): number (with min/max), date (ISO-8601
    string), and textarea (multi-line string with max_length).
    """

    TEXT_INPUT = "text_input"
    SINGLE_SELECT = "single_select"
    MULTI_SELECT = "multi_select"
    BOOLEAN = "boolean"
    NUMBER = "number"
    DATE = "date"
    TEXTAREA = "textarea"
    # v3 (communication grammar member #1): a presentation-enriched
    # single-select.
    # The agent offers a recommended option with rationale + per-option
    # tradeoffs; the answer is one selected option (validated exactly as a
    # single-select). The rich card layout is widget-surface only.
    DECISION = "decision"
    # v4 (communication grammar member #2): a pushback — the agent
    # disagrees with the user's stated approach (``user_position``) and
    # offers a concrete alternative (``recommended``) + a disagreement
    # ``rationale``. Same enriched-single-select answer path as DECISION;
    # only the dissent framing (your-approach tag, "I'd suggest instead"
    # badge, "Why I'd push back" callout) differs. Widget-surface only.
    PUSHBACK = "pushback"
    # v5 (communication grammar member #3): a progress report — the agent
    # reports a set of items by status (done / in_flight / blocked) via
    # ``progress_items`` and offers the blocked items as a single-select
    # picker ("which blocker to tackle?"). The answer is one selected
    # blocked option (validated exactly as a single-select); when nothing
    # is blocked it degrades to a pure status display. Widget-surface only.
    PROGRESS = "progress"
    # v6 (communication grammar member #4): a deliberation — several
    # named voices (e.g. the round-table seats claude / antigravity /
    # codex) each endorse candidate positions via ``endorsements``
    # ({option: [voice, ...]}); the user chairs the pick. The answer is
    # one selected option (validated exactly as a single-select); the
    # per-option endorsement chips and the "synthesis pick" badge are
    # widget-surface only.
    DELIBERATION = "deliberation"
    # v6 (communication grammar member #5): a triage board — a reviewed
    # list (``triage_items``) where EVERY item gets its own ruling from a
    # small shared vocabulary (``dispositions``, e.g. fix now / ticket /
    # dismiss). The answer is a {item label: disposition} mapping — the
    # one construct whose answer is not a scalar or a flat list. On
    # non-widget surfaces it expands to one single-select per item
    # (ids ``"<id>.<label>"``) and folds back at collection time.
    TRIAGE = "triage"
    # v7 (communication grammar member #6): a confirm — an action
    # preview with an explicit ``consequences`` list and a two-way
    # approve/abort gate (exactly two author-nameable options, default
    # ["Approve", "Abort"]). No default and no recommended are permitted
    # — a pre-selected approval defeats the gate (confirm-construct spec
    # D2); approving is an explicit act on every surface. The answer is
    # one of the two options (validated as a single-select).
    CONFIRM = "confirm"
    # v8 (communication grammar member #7, ranking-construct spec): a
    # ranking — the user ORDERS the options, optionally only the top
    # ``top_n``. The answer is an ordered list of option labels (distinct,
    # every entry an option, length == top_n or len(options)) — the one
    # construct whose answer is an ordered list. A ``suggested`` order
    # renders visibly as a proposal, never as the answer; ``default`` is
    # rejected (D2-c). On flat surfaces it expands to one single-select
    # per rank slot (ids ``"<id>.<k>"``, D2-b) and folds back at
    # collection time.
    RANKING = "ranking"
    # v8 (communication grammar member #8, assumption-review-construct
    # spec): an assumption review — the agent lists the assumptions it
    # INFERRED from context (``assumptions``: {label, id?, detail?,
    # source?}) and the user rules each one from the FIXED vocabulary
    # accept / edit / reject, supplying replacement text for an edit. The
    # answer is {item key: "accept" | "reject" | {"edit": text}} — the
    # triage mapping shape plus an edit lane (D2-c). ``suggested`` may
    # pre-mark ``accept`` only, visibly (D2-b); ``default`` and
    # ``dispositions`` are rejected (D2-a: the vocabulary IS the
    # construct). Flat surfaces expand to one single-select per item
    # (``"<id>.<key>"``) paired with an optional text question
    # (``"<id>.<key>.text"``); the fold enforces text-iff-edit.
    ASSUMPTION_REVIEW = "assumption_review"


#: The fixed ruling vocabulary of an ASSUMPTION_REVIEW (D2-a). Not
#: author-renameable: the meaning of the construct is these three words.
ASSUMPTION_RULINGS = ("accept", "edit", "reject")

#: Suffix of the flat-surface text question paired with each assumption
#: (``"<id>.<key>.text"``): the replacement text when the ruling is edit.
ASSUMPTION_TEXT_SUFFIX = ".text"


def ranking_slot_count(question: "FormQuestion") -> int:
    """How many entries a RANKING answer carries: ``top_n`` or all options.

    Every surface (widget header, ordinal flat expansion, elicitation
    array bounds, markdown skeleton, validator) sizes the answer through
    this one function so they can never disagree.
    """
    return question.top_n if question.top_n is not None else len(question.options)


def decimal_key_number(text: str) -> int | None:
    """Parse a numeric answer key — a 1-based field number or the ``k`` of
    a dotted rank slot ``"<id>.<k>"`` — or ``None`` when it is not a
    plain ASCII decimal.

    Every surface parses one through this single function.
    ``str.isdigit()`` is True for 95 BMP characters ``int()`` rejects
    (``²``, ``①``, Ethiopic digits …), so pairing the two raised a raw
    ValueError out of ``collect_form_response`` and the MCP collect tool
    (which catches only :class:`FormValidationError`) on a superscript
    suffix — review finding, 2026-08-16.
    """
    return int(text) if text.isascii() and text.isdigit() else None


def _consequences_summary(consequences: list[dict[str, str]] | None) -> str | None:
    """One-line "Will: ..." digest of a confirm's consequences.

    The flat-surface projection of the preview: label, severity in
    parentheses, detail after a dash — compact enough for help_text or
    an elicitation description without dumping a paragraph per item.
    """
    if not consequences:
        return None
    bits = []
    for item in consequences:
        bit = item.get("label", "")
        if item.get("severity"):
            bit += f" ({item['severity']})"
        if item.get("detail"):
            bit += f" — {item['detail']}"
        bits.append(bit)
    return "Will: " + "; ".join(bits)


def triage_item_key(item: dict[str, str]) -> str:
    """The answer key for one triage item: its ``id``, else its ``label``.

    Display labels may be edited or collide; a stable ``id`` keeps the
    {key: disposition} answer and the dotted-id flat expansion
    unambiguous. Every consumer (widget, fallback expansion, elicitation
    schema, markdown skeleton, validator) keys through this one function
    so the surfaces can never disagree.
    """
    return item.get("id") or item.get("label", "")


#: The options a CONFIRM carries when the author names none. Exactly
#: two, always — the gate is two-way by ruling (confirm-construct D1).
#: Single-sourced here so ``form_from_dict`` and a directly-built
#: :class:`FormQuestion` default identically (0.5.0 cleanup batch).
CONFIRM_DEFAULT_OPTIONS = ("Approve", "Abort")

#: The Yes/No vocabulary of a BOOLEAN question — the values every
#: surface renders its control with and the only answers the validator
#: accepts. Single-sourced here so the widget's select, the flat-surface
#: options, and ``collect_form_response`` can never disagree (0.6.x
#: cleanup batch: it was defined independently in bridge and widget).
BOOLEAN_OPTIONS = ("Yes", "No")

#: Status icon per PROGRESS status — the widget rows and the markdown
#: surface render the same three glyphs (0.6.x cleanup batch: each
#: surface carried its own copy with a "matches the widget" comment
#: nothing enforced).
PROGRESS_STATUS_ICONS = {"done": "✓", "in_flight": "◐", "blocked": "✕"}

#: Rationale callout header per construct — the widget and markdown
#: surfaces show the same words above ``rationale`` (0.6.x cleanup
#: batch: previously duplicated per surface). Types absent here head
#: the callout "Why".
RATIONALE_HEADERS: dict["QuestionType", str] = {
    QuestionType.PUSHBACK: "Why I'd push back",
    QuestionType.PROGRESS: "Summary",
    QuestionType.DELIBERATION: "Synthesis",
}


def recommended_first(question: "FormQuestion") -> list[str]:
    """``question.options`` with ``question.recommended`` moved to the
    front, when it names one of them.

    The recommended-first ordering is construct policy (the proposal
    leads on every surface), so the widget's cards, the markdown option
    lines, and the AskUserQuestion fallback all order through this one
    function (0.6.x cleanup batch: it was implemented three times).
    """
    ordered = list(question.options)
    if question.recommended and question.recommended in ordered:
        ordered = [question.recommended] + [o for o in ordered if o != question.recommended]
    return ordered


def expansion_items(question: "FormQuestion") -> list[tuple[str, dict[str, str]]]:
    """The reviewed rows of an item-keyed construct as ``(key, item)``
    pairs — TRIAGE's ``triage_items`` or ASSUMPTION_REVIEW's
    ``assumptions``, keyed by :func:`triage_item_key`.

    Every surface that expands per item (AskUserQuestion payloads, the
    elicitation schema, markdown rows, the collect-time fold and
    validators) iterates through this one function, so the item set and
    its keys can never differ between surfaces (0.5.0 cleanup batch:
    triage-expansion unification).
    """
    if question.type is QuestionType.TRIAGE:
        items = question.triage_items
    elif question.type is QuestionType.ASSUMPTION_REVIEW:
        items = question.assumptions
    else:
        items = None
    return [(triage_item_key(item), item) for item in items or []]


def suggested_pick(question: "FormQuestion", key: str) -> str | None:
    """The agent's proposed value for one expanded row, or ``None``.

    ``suggested`` is a union type (mapping for item-keyed constructs, a
    list for RANKING) — this guard belongs in exactly one place: a
    direct-built question carrying the wrong shape degrades to "no
    suggestion" instead of crashing whichever surface forgot its own
    isinstance check (0.5.0 cleanup batch: helper dedup).
    """
    if isinstance(question.suggested, dict):
        return question.suggested.get(key)
    return None


def item_context(question: "FormQuestion", item: dict[str, str]) -> str | None:
    """The one-line context of an expanded row, or ``None`` when bare.

    TRIAGE rows carry ``tag · detail``, ASSUMPTION_REVIEW rows
    ``source · detail`` — the same join every flat surface shows
    (AskUserQuestion help text, elicitation property description).
    Markdown keeps its own per-field decoration deliberately.
    """
    fields = ("tag", "detail") if question.type is QuestionType.TRIAGE else ("source", "detail")
    joined = " · ".join(b for b in (item.get(f) for f in fields) if b)
    return joined or None


# =============================================================================
# Form Components
# =============================================================================


@dataclass
class FormQuestion:
    """A single question in a Socratic form.

    Attributes:
        id: Unique identifier for this question
        text: The question text shown to user
        type: Question type (text_input, single_select, etc.)
        options: Available options for select questions
        default: Default value if user doesn't provide one
        help_text: Additional help text shown to user
        required: Whether this question must be answered
        minimum: Lower bound for NUMBER answers (inclusive); None = none
        maximum: Upper bound for NUMBER answers (inclusive); None = none
        max_length: Max character length for TEXT_INPUT/TEXTAREA; None = none
        rationale: DECISION only — the "why this recommendation" callout
            rendered beneath the options; None = none
        option_notes: DECISION only — {option: one-line tradeoff} shown
            under each option card; None = none
        recommended: DECISION/PUSHBACK — the option to badge (recommended,
            or the agent's alternative for PUSHBACK) and order first; must
            be one of options; None = none
        user_position: PUSHBACK only — the option that is the user's stated
            approach (tagged "your approach"); must be one of options;
            None = none
        progress_items: PROGRESS only — the reported items as a list of
            {label, status, detail?} dicts, status ∈ {done, in_flight,
            blocked}. The blocked subset must equal options (the picker);
            done/in_flight items are reported but not answerable. None = none
        progress_style: PROGRESS only — "report" renders a neutral digest
            (item status is a free-form category tag, no task semantics or
            strikethrough; options may be any subset of item labels, offered
            as a "go deeper" picker). Pure presentation: the answer and its
            validation are unchanged. None = the default task-status render.
        endorsements: DELIBERATION only — {option: [voice, ...]} naming
            which deliberating voices endorsed each option; keys must be
            options, each value a non-empty list of names. Rendered as
            per-option chips so a 2-1 split (and its minority) is visible
            at a glance. None = none
        triage_items: TRIAGE only — the reviewed items as a list of
            {label, id?, detail?, tag?} dicts (tag is a free-form
            category, e.g. a severity). The answer keys on the item's
            ``id`` when present, else its ``label`` (see
            :func:`triage_item_key`) — a stable id survives label edits
            and keeps the dotted-id expansion unambiguous (round-table
            ruling, thread q-forms-grammar-expansion-001). Keys must be
            unique non-empty strings. None = none
        dispositions: TRIAGE only — the shared per-item ruling vocabulary
            (≥2 unique non-empty strings, e.g. ["fix now", "ticket",
            "dismiss"]). Every ruling in the answer must be one of these.
            None = none
        suggested: TRIAGE — {item label: disposition}: the agent's
            proposed ruling per item, rendered pre-selected and marked
            "suggested" (a guess to confirm, never silently accepted).
            Keys must be item labels, values dispositions. RANKING — the
            agent's proposed order as a list of options (distinct, one
            entry per answer slot), rendered pre-arranged and badged
            "proposed"; never treated as the answer. None = none
        top_n: RANKING only — rank just the top N options (1 <= N <=
            len(options)); None = the answer is a full permutation.
        assumptions: ASSUMPTION_REVIEW only — the inferred assumptions as
            a non-empty list of {label, id?, detail?, source?} dicts
            (``source`` = where the agent inferred it from). Keyed like
            triage items (:func:`triage_item_key`); keys unique. The
            ruling vocabulary is fixed (:data:`ASSUMPTION_RULINGS`);
            ``suggested`` may pre-mark ``accept`` only. None = none
        consequences: CONFIRM only — what happens if the action is
            approved, as a non-empty list of {label, severity?, detail?}
            dicts (severity a free tag; conventional vocabulary low /
            medium / high / irreversible). Required for CONFIRM — a
            confirm with nothing to preview is a bare boolean and should
            be one. None = none
        list_style: SINGLE_SELECT/MULTI_SELECT only — render the options as
            an "ordered" (numbered) or "unordered" (bulleted) selectable
            list instead of the default dropdown/checkboxes. Pure
            presentation: the answer and its validation are unchanged.
            None = the default render.
        inferred_from: Why this field's ``default`` was inferred from
            context, e.g. "you've been editing src/attune/elicitation/".
            Presence means the value is the agent's GUESS, not a static
            suggestion, and the renderer marks it visibly as such so a
            wrong guess is catchable. Requires ``default`` to be set.
            None = not inferred.

    """

    id: str
    text: str
    type: QuestionType
    options: list[str] = field(default_factory=list)
    default: str | None = None
    help_text: str | None = None
    required: bool = True
    minimum: float | None = None
    maximum: float | None = None
    max_length: int | None = None
    rationale: str | None = None
    option_notes: dict[str, str] | None = None
    recommended: str | None = None
    user_position: str | None = None
    progress_items: list[dict[str, str]] | None = None
    progress_style: str | None = None
    endorsements: dict[str, list[str]] | None = None
    triage_items: list[dict[str, str]] | None = None
    dispositions: list[str] | None = None
    suggested: dict[str, str] | list[str] | None = None
    consequences: list[dict[str, str]] | None = None
    list_style: str | None = None
    inferred_from: str | None = None
    top_n: int | None = None
    assumptions: list[dict[str, str]] | None = None

    def __post_init__(self) -> None:
        """Default a CONFIRM's options to the two-way gate.

        ``form_from_dict`` has always defaulted them; a directly-built
        question skipped that path and rendered a gate with no options
        (0.5.0 review, queued with the cleanup batch). The gate is
        two-way by ruling (confirm-construct D1) on every construction
        path.
        """
        if self.type is QuestionType.CONFIRM and not self.options:
            self.options = list(CONFIRM_DEFAULT_OPTIONS)

    def _fallback_help(self) -> str | None:
        """Help text for AskUserQuestion, carrying any inference provenance.

        ``AskUserQuestion`` has no slot for "this value is a guess", so the
        provenance folds into help_text — otherwise the fallback surface
        would present an inferred value as indistinguishable from a
        settled one, which is the exact failure the widget badge exists
        to prevent.
        """
        if not self.inferred_from:
            return self.help_text
        note = f"Guessed: {self.default} — {self.inferred_from}"
        return f"{self.help_text} · {note}" if self.help_text else note

    def to_ask_user_format(self) -> dict[str, Any]:
        """Convert to format compatible with AskUserQuestion tool.

        Returns:
            Dictionary with question data for AskUserQuestion

        Raises:
            ValueError: For a TRIAGE question — its {item: disposition}
                answer has no single-payload equivalent, and the old
                fall-through silently produced an unrenderable
                ``{"type": "triage", "options": []}`` payload (review
                finding, 2026-08-14). Likewise for a RANKING question,
                whose ordered-list answer expands to one payload per rank
                slot (D2-b), and an ASSUMPTION_REVIEW, whose mapping
                answer expands to one payload per assumption plus a paired
                text question. Callers on the one-payload contract must
                use :meth:`to_ask_user_formats`.
        """
        if self.type is QuestionType.TRIAGE:
            raise ValueError(
                "a triage question expands to one payload per item — use to_ask_user_formats()"
            )
        if self.type is QuestionType.RANKING:
            raise ValueError(
                "a ranking question expands to one payload per rank slot — "
                "use to_ask_user_formats()"
            )
        if self.type is QuestionType.ASSUMPTION_REVIEW:
            raise ValueError(
                "an assumption review expands to one payload per assumption "
                "(plus a paired text question) — use to_ask_user_formats()"
            )
        # Decision (v3), pushback (v4), and progress (v5) all fall back to a
        # single-select with the recommended option ordered first — the
        # richer card layout is widget-only; the answer is one selected
        # option either way. For progress the options are the blocked items
        # (done/in_flight items are reported in the text, not pickable); when
        # options is empty there is nothing to ask and the caller narrates
        # the report instead.
        if self.type in (
            QuestionType.DECISION,
            QuestionType.PUSHBACK,
            QuestionType.PROGRESS,
            QuestionType.DELIBERATION,
        ):
            opts = recommended_first(self)
            # DELIBERATION: the fallback surface has no chip row, so the
            # per-option endorsements fold into help_text — otherwise the
            # 2-1 split (the construct's whole payload) would be invisible.
            help_text = self._fallback_help()
            if self.type is QuestionType.DELIBERATION and self.endorsements:
                who = "; ".join(
                    f"{opt}: {', '.join(names)}" for opt, names in self.endorsements.items()
                )
                note = f"Endorsements — {who}"
                help_text = f"{help_text} · {note}" if help_text else note
            return {
                "question_id": self.id,
                "question": self.text,
                "type": "single_select",
                "options": opts,
                "default": self.default or self.recommended,
                "help_text": help_text,
            }

        # CONFIRM: a two-option single-select; the consequences preview
        # folds compactly into help_text (the ruled degradation — never a
        # silent boolean that hides the receipt). No default, ever (D2).
        if self.type is QuestionType.CONFIRM:
            help_text = self._fallback_help()
            summary = _consequences_summary(self.consequences)
            if summary:
                help_text = f"{help_text} · {summary}" if help_text else summary
            return {
                "question_id": self.id,
                "question": self.text,
                "type": "single_select",
                "options": list(self.options),
                "default": None,
                "help_text": help_text,
            }

        # Boolean questions convert to Yes/No select
        if self.type == QuestionType.BOOLEAN:
            return {
                "question_id": self.id,
                "question": self.text,
                "type": "single_select",
                "options": ["Yes", "No"],
                "default": self.default,  # Preserve default for boolean questions
                "help_text": self._fallback_help(),
            }

        return {
            "question_id": self.id,
            "question": self.text,
            "type": self.type.value,
            "options": self.options,
            "default": self.default,
            "help_text": self._fallback_help(),
        }

    def to_ask_user_formats(self) -> list[dict[str, Any]]:
        """Per-call ``AskUserQuestion`` payloads for this question.

        Every type yields its single :meth:`to_ask_user_format` payload
        except TRIAGE, whose {item: disposition} answer has no
        single-question equivalent: it expands to one single-select per
        item (ids ``"<id>.<label>"``, the suggested ruling as default);
        and RANKING, whose ordered-list answer expands to one single-select
        per rank slot (ids ``"<id>.<k>"``, k 1-based, titled "Rank #k";
        every slot offers every option because a host question tool
        cannot remove already-picked ones — the collect-time validator
        catches a repeat); and ASSUMPTION_REVIEW, which expands to one
        single-select per assumption over the fixed vocabulary PAIRED
        with an optional text question (``"<id>.<key>.text"``) for the
        edit lane. :func:`attune_forms.collect_form_response` folds the
        dotted ids back into the mapping / list answer, so the round-trip
        is lossless.
        """
        if self.type is QuestionType.RANKING:
            slots = ranking_slot_count(self)
            proposed = self.suggested if isinstance(self.suggested, list) else []
            help_text = self._fallback_help()
            note = f"Rank {slots} of {len(self.options)}; each option may be used once"
            help_text = f"{help_text} · {note}" if help_text else note
            return [
                {
                    "question_id": f"{self.id}.{k}",
                    "question": f"{self.text} — Rank #{k}",
                    "type": "single_select",
                    "options": list(self.options),
                    "default": proposed[k - 1] if k - 1 < len(proposed) else None,
                    "help_text": help_text,
                }
                for k in range(1, slots + 1)
            ]
        if self.type is QuestionType.ASSUMPTION_REVIEW:
            # One single-select per assumption over the fixed vocabulary,
            # each PAIRED with an optional text question for the edit lane
            # — a host question tool cannot branch, so the text is always
            # offered; the collect-time fold keeps it only when the ruling
            # is edit, and the validator requires it then.
            payloads: list[dict[str, Any]] = []
            for key, item in expansion_items(self):
                payloads.append(
                    {
                        "question_id": f"{self.id}.{key}",
                        "question": f"{self.text} — {item.get('label', '')}",
                        "type": "single_select",
                        "options": list(ASSUMPTION_RULINGS),
                        "default": suggested_pick(self, key),
                        "help_text": item_context(self, item),
                    }
                )
                payloads.append(
                    {
                        "question_id": f"{self.id}.{key}{ASSUMPTION_TEXT_SUFFIX}",
                        "question": f"Replacement text if editing — {item.get('label', '')}",
                        "type": "text_input",
                        "options": [],
                        "default": None,
                        "help_text": "Only read when the ruling is edit",
                    }
                )
            return payloads
        if self.type is not QuestionType.TRIAGE:
            return [self.to_ask_user_format()]
        payloads = []
        for key, item in expansion_items(self):
            payloads.append(
                {
                    "question_id": f"{self.id}.{key}",
                    "question": f"{self.text} — {item.get('label', '')}",
                    "type": "single_select",
                    "options": list(self.dispositions or []),
                    "default": suggested_pick(self, key),
                    "help_text": item_context(self, item),
                }
            )
        return payloads


@dataclass
class FormSchema:
    """Schema defining a collection of questions for a meta-workflow.

    Attributes:
        title: Form title
        description: Form description
        questions: List of questions to ask

    """

    title: str
    description: str
    questions: list[FormQuestion] = field(default_factory=list)

    def get_question_batches(self, batch_size: int = 4) -> list[list[FormQuestion]]:
        """Batch questions for asking (AskUserQuestion supports max 4 at once).

        Args:
            batch_size: Maximum questions per batch (default: 4)

        Returns:
            List of question batches

        """
        batches = []
        for i in range(0, len(self.questions), batch_size):
            batches.append(self.questions[i : i + batch_size])
        return batches


@dataclass
class FormResponse:
    """User's responses to a form.

    Attributes:
        template_id: ID of template this response is for
        responses: Dictionary mapping question_id → user's answer
        timestamp: When response was submitted
        response_id: Unique ID for this response

    """

    template_id: str
    responses: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    response_id: str = field(
        # The uuid suffix keeps the id unique when two responses land in
        # the same second — the timestamp alone collided (discovery-sweep
        # finding, 2026-08-20). Nothing parses the format; it is only
        # displayed and joined on.
        default_factory=lambda: (
            f"resp-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
        ),
    )

    def get(self, question_id: str, default: Any = None) -> Any:
        """Get response for a question.

        Args:
            question_id: ID of question
            default: Default value if not found

        Returns:
            User's response or default

        """
        return self.responses.get(question_id, default)
