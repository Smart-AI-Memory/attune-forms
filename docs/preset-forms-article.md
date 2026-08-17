<!--
  This repo copy is the verified MASTER of this article: every code
  block was executed against attune-forms 0.6.0 from PyPI in a fresh
  virtualenv on 2026-08-16; printed values are the values the code
  printed. External publications (LinkedIn, blog, dev.to) are
  projections of it — fix divergences here first, re-run the blocks,
  then re-project. Companion to communication-grammar-article.md,
  six-speech-acts-article.md, and tutorial-dynamic-forms.md.
-->

# Preset Forms: Sculpt Once, Cast Per Use

*The two layers that keep you from building the same form twice — stored templates and generated intakes — and the rules that keep "automatic" from meaning "guessed".*

Three earlier pieces built forms field by field: the constructs, the surfaces, the return path. This one is about not doing that twice. attune-forms ships two preset layers. A **stored template** is a form you sculpted once, saved as data, and cast per use with a couple of slot values. A **generated intake** goes further: its options are computed from your project at ask time, so the form fills itself before the user ever sees it. Both land in the same `form_from_dict` validator as a hand-built dict, which is the whole trick — a preset is a shortcut into the machinery, never a bypass around it.

Everything below runs as written against the published package:

```
pip install attune-forms==0.6.0
```

(The Claude Code plugin — `claude plugin marketplace add Smart-AI-Memory/attune-forms`, then `claude plugin install attune-forms@attune-forms` — gives you forms in your agent's conversations with no Python. Presets are library machinery, so this piece takes the library path.)

## 1. Stored templates: a form as a file

A template is the exact dict `form_from_dict` accepts, saved as JSON, plus a `"slots"` list naming the substitution points — `{project}`-style placeholders in its string fields. The library ships one:

```python
from attune_forms import form_from_template, list_templates

print(list_templates())                        # ['session-contract']

form = form_from_template("session-contract", {"project": "attune-forms"})
print(form.title)                              # Session contract — attune-forms
print([q.id for q in form.questions])
# ['mode', 'outcome', 'done_when', 'effort_cap']
```

That template is not a demo I invented for this article. It is my own session-start protocol — mode, outcome, done-when, effort cap — the four fields I fill before any non-trivial working session, sculpted once into JSON and cast at the top of each one. The form I use to hold my agent accountable is the form the library ships.

A missing slot value is a named problem through the same error type as every other malformed form — a template earns no special leniency:

```python
from attune_forms import FormValidationError

try:
    form_from_template("session-contract", {})
except FormValidationError as e:
    print(e.problems)
# ["missing value for slot 'project'"]
```

And when you collect the answers, passing the template name as `template_id` stamps the response, so answers to the same template are joinable across sessions — fill the session contract daily and you have a queryable record of what you said you'd do:

```python
from attune_forms import collect_form_response

resp = collect_form_response(form, answers, template_id="session-contract")
print(resp.template_id)                        # session-contract
```

## 2. Generated intakes: options computed at ask time

A stored template's *shape* is fixed; only strings substitute. A generated intake computes its **options** from project context when the form is built. The declaration is two dataclasses — `FormTemplate` holds `FieldSlot`s, and a slot may name a *provider*: a plain callable that turns a `ProviderContext` (repo root, the user's raw ask, already-answered fields) into candidate options.

```python
from pathlib import Path
from attune_forms.intake_template import (
    PROVIDERS, FieldSlot, FormTemplate, ProviderContext, build_form,
)

def top_level_dirs(ctx: ProviderContext) -> list[str]:
    return sorted(
        p.name for p in ctx.repo_root.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )

PROVIDERS["top_level_dirs"] = top_level_dirs

template = FormTemplate(
    title="Audit scope",
    description="Where should the audit look?",
    fields=[
        FieldSlot(key="target", text="Which directory?",
                  provider="top_level_dirs",
                  other="somewhere else (name it)"),
        FieldSlot(key="depth", text="How deep?",
                  control="single_select",
                  options=["quick", "standard", "thorough"],
                  default="standard"),
    ],
)

audit = build_form(template, ProviderContext(repo_root=Path(".")))
print(audit.questions[0].options)
# ['docs', 'plugin', 'src', 'tests', 'somewhere else (name it)']
```

Run in the attune-forms checkout, the `target` slot materializes as a single-select over the repo's actual directories, with the `other` sentinel appended so the provider's guess at the candidate set is never a cage. Run it in your repo and you get *your* directories. That is the whole meaning of "automatic" here: the form adapts to the project, at build time, through a function you wrote and registered by name.

When a provider returns nothing, the slot degrades to a required free-text input rather than an empty select — a form this layer builds is always answerable:

```python
PROVIDERS["empty"] = lambda ctx: []
bare = build_form(FormTemplate(title="T", description="", fields=[
    FieldSlot(key="target", text="Which directory?", provider="empty",
              fallback_text="Name the directory to audit"),
]), ProviderContext(repo_root=Path(".")))
print(bare.questions[0].type.value, "—", bare.questions[0].text)
# text_input — Name the directory to audit
```

## 3. What "automatic" refuses to do

The layer's design review ruled a set of boundaries, and they are the part I would actually sell you on, because every one of them is a refusal:

- **Nothing guesses candidates.** A list-typed slot with no provider is a build-time error, not an empty dropdown:

```python
from attune_forms import TemplateError, validate_template

try:
    validate_template(FormTemplate(title="T", description="", fields=[
        FieldSlot(key="x", text="X?", other="other"),
    ]))
except TemplateError as e:
    print(e)                                   # slot 'x': 'other'/'fallback_text' require a provider
```

- **Prefill is exact-match only.** A slot pre-fills from already-answered fields only when the key matches exactly — never a heuristic, never an LLM deciding your answer resembles a previous one.
- **Tighten-only.** A template may make a schema-optional field required; rendering a schema-required field optional rejects at build time.
- **No template means no form.** Ask for an intake that doesn't exist and you get `None` plus a logged demand marker — the caller falls back to asking in prose:

```python
from attune_forms import intake_form

print(intake_form("no-such-intake"))           # None  (+ a demand-telemetry log line)
```

That last one is my favorite. The tempting design was to auto-derive a form from whatever schema hints exist, so every intake "just works". The ruling went the other way: a missing template is a *signal*, logged, and the log is what tells you which intake is asked for often enough to deserve sculpting. Demand-driven authoring instead of speculative generation. The earlier pieces argued that trust in the return path is the product; this layer applies the same argument one step earlier — trust in the *question* is also the product, and a question nobody designed is not yet trustworthy.

## 4. The host seams

A host application wires the layer with two hooks: append a loader to `TEMPLATE_LOADERS` (it imports your intake modules, whose templates register as an import-time side effect) and, for templates bound to a named workflow, set `WORKFLOW_SCHEMA_RESOLVER` so slot declarations are cross-checked against the workflow's input schema at build time. That is the entire integration surface — attune-ai, the library's first consumer, registers its fix, spec, and workflow intakes through exactly these two seams and nothing else.

## Try it

Sculpt the form you fill most often. Mine turned out to be the four questions I answer at the start of every session; the library ships it, so you can cast it right now:

```python
from attune_forms import form_from_template
form = form_from_template("session-contract", {"project": "your-project"})
```

Which form do you fill by hand often enough that it deserves to be a file?

---

*Patrick Roebuck builds Smart AI Memory. attune-forms: https://github.com/Smart-AI-Memory/attune-forms — PyPI: https://pypi.org/project/attune-forms/ — the tutorial: docs/tutorial-dynamic-forms.md — the concept: https://www.linkedin.com/pulse/communication-grammar-ai-agents-patrick-roebuck-sutse*
