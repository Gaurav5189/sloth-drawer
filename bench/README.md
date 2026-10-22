# `bench/` — the model benchmark harness

This directory is where the numbers in the post come from. Every claim about
latency, tokens-per-second or model accuracy in `PLAN.md` §3.1 was printed by
one of these three scripts on the reference box.

**Do not edit these files to make a number look better.** They are the
measurement, not the product. They are also excluded from `ruff` (see
`pyproject.toml`) so the source that produced the published numbers stays
byte-stable.

---

## Prerequisites

```bash
ollama serve                                   # in another terminal
ollama pull gemma3:270m
ollama pull gemma3:1b
ollama pull phi4-mini:latest
```

The scripts talk to `http://localhost:11434` over stdlib `urllib` — no extra
dependency, no SDK.

---

## The three scripts

### `bench2.py` — array schema vs one-fact schema

Answers the question that shaped the whole extraction layer: *should the model
return an array of intervals, or one fact per call?*

```bash
python bench/bench2.py gemma3:270m gemma3:1b phi4-mini:latest
```

For each model it runs three prompts against the same synthetic manual page:

| Run | Prompt | Schema |
|---|---|---|
| A | "extract every maintenance task" | array of interval objects |
| B | "answer ONE question" | flat, one fact |
| C | "extract every maintenance task" | bare `"json"` (no schema) |

and prints the raw response, the elapsed time, the token counts and the
tokens-per-second.

**The published result:** `phi4-mini` answers A and C with
`{"intervals": []}` — schema-valid, semantically empty. `gemma3:270m` gets the
interval *wrong*. `gemma3:1b` passes both schema patterns. Hence the
one-fact-per-call, flat-schema design in `RULES.md` §1.4.

### `final.py` — one-fact extraction on a multi-interval page + the verdict paths

```bash
python bench/final.py gemma3:270m gemma3:1b phi4-mini:latest
```

Three parts:

1. the live model call on a page that contains **four** intervals, so a model
   that only ever looks at the first one is caught;
2. the **rejection and repair paths**, driven by three deliberately bad model
   outputs — a hallucinated quote, a real quote with the wrong number, and a
   citation of a sentence that contains no interval at all;
3. the ground truth for the page, so the output can be read against it.

Part 2 is the important one: it is the origin of the four verdicts in
`PLAN.md` §3.2, and of the rule that a REJECT is a result rather than an
error.

### `validate.py` — the quote expansion and repair path, in isolation

```bash
python bench/validate.py gemma3:1b
```

Same idea as `final.py`, but with the verifier's `expand_quote` /
`months_from_text` functions exposed step by step: it prints the model's raw
JSON, whether the quote was found in the page, the sentence the **code**
expanded it to, the interval the **code** re-parsed from that sentence, and
whether the two agree.

This is the script to run when you want to see the "model points, code quotes,
code recomputes" split in isolation.

---

## Re-running the published table

Phase 3 re-runs all three and captures the final table for the post. To
reproduce the numbers in `PLAN.md` §3.1 as they stand:

```bash
ollama serve &
python bench/bench2.py gemma3:270m gemma3:1b phi4-mini:latest \
  | tee out/bench2.txt
python bench/final.py gemma3:270m gemma3:1b phi4-mini:latest \
  | tee out/final.txt
```

Record the machine you ran it on. The published numbers were taken on
**4 cores, 7.5 GB RAM, no GPU, Ollama 0.40.6, CachyOS**; a different box will
move the latencies, and the post must quote the box it actually ran on.
