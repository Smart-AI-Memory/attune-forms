# Host trial: multi-select escaping on Claude Code's AskUserQuestion

**Date:** 2026-09-08 · **Host:** Claude Code, desktop Code tab ·
**Profile:** `claude-askuserquestion`

## What was unverified

`ASKUSERQUESTION_HOST_QUESTION` declared its multi-select codec as

```python
MultiSelectEncoding(
    kind="comma_delimited",
    delimiter=",",
    escaping="json_quote_when_delimiter_or_quote",   # <- never demonstrated
    canonical_reencode=True,
    escaping_verified=False,
)
```

The 2026-09-07 trial (attune-ai
`docs/probes/host-surface-parity/host-native-trials-2026-09-07.md`)
established the delimiter — "multi-select answers are the chosen labels
joined by commas with no spaces" — but every label it exercised was free
of commas and quotes, so the **escaping rule was never tested**. The AF-2
handoff said so explicitly: *"Do not enable the profile flag without
retained host evidence covering delimiters, quotes, backslashes, and
ordering."*

While unverified, `host_question_admissibility` refused any multi-select
label containing the delimiter or a quote. That fail-closed refusal was
correct, but its reason was a guess.

## Method

One `AskUserQuestion` call, two multi-select questions
(`metadata.source: elicit-form`), each asking for an exact selection so
the returned string is decisive rather than a preference.

| Question | Options offered | Asked to select |
|---|---|---|
| Delimiter | `red, green` · `blue` · `amber` | `red, green` and `blue` |
| Quote / backslash | `say "hi"` · `back\slash` · `neither` | the first two |

## Result — verbatim

```
"TRIAL 1 …"="red, green,blue", "TRIAL 2 …"="say "hi",back\slash"
```

## Findings

1. **No escaping of any kind.** `red, green` + `blue` returned
   `red, green,blue` — a bare comma join. The result is **ambiguous**:
   nothing in the string distinguishes it from the three atoms `red`,
   `green`, `blue`. A decoder cannot recover the selection.
2. **Quotes pass through raw.** `say "hi"` returned as `say "hi"`, not
   `"say \"hi\""`. The declared JSON-quoting does not happen.
3. **Backslashes pass through raw.** `back\slash` returned unchanged and
   unescaped.
4. **Order followed the offered order** in both questions, matching the
   2026-09-07 observation.

## Ruling

The declared `escaping="json_quote_when_delimiter_or_quote"` is **false
for this host**. The profile now declares `escaping="none"` with
`escaping_verified=True` — verified as *none*, which is what the flag
means: the host has demonstrated its declared escaping.

The practical effect is unchanged and now correctly explained.
Delimiter-bearing and quote-bearing multi-select labels stay
inadmissible, but **permanently** rather than pending evidence, and the
refusal says why:

```
'x': option 'red, green': the host joins with ',' and escapes nothing,
so this label cannot be carried unambiguously
```

That distinction matters to a caller. An unverified rule may become
admissible once a host demonstrates it; `none` never will. A form
needing such a label must route to the widget or portable markdown.

## What this does not establish

- Only this host. Another host declaring an escaping rule still needs
  its own trial before `escaping_verified` may be set.
- Free text through "Other" remains unexercised here.
- The observation surface is the tool result the agent receives, which
  is the contract the profile describes. Whether the host's internal
  representation differs before that point is out of scope.
