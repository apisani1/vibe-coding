# planning/ — the contract

What an agent, or a person, should read before changing anything in this repository. These
are **copies**: the working originals live in `.claude/vibe-reports/`, which is the run of
record and carries the build log, the checklists and every approval. This directory is the
same content without needing to know that a pipeline produced it.

| File | What it is | Read it when |
| --- | --- | --- |
| [`SPEC.md`](SPEC.md) | The specification — what the product is and what it must do | Always first |
| [`DESIGN.md`](DESIGN.md) | The technical design: data model, modules, flows, edge-case tables, limitations | Before touching architecture |
| [`DECISIONS.md`](DECISIONS.md) | 26 decisions, each with the alternatives rejected and why | When something looks wrong — the reason is usually here |
| [`PLAN.md`](PLAN.md) | The 19 checkpoints, what each touched, and how each was verified | To find out when and why a thing was built |
| [`VERIFICATION-PLAN.md`](VERIFICATION-PLAN.md) | Every check, written **before** the code existed, plus what cannot be verified | Before claiming something works |

## The five things most likely to bite you

Each of these cost a rejected checkpoint, and each is a rule that is invisible from the code
that depends on it.

1. **No current price is ever stored** (D1). Market value, unrealised P&L and total value are
   computed at read time against an in-memory cache. `trades.price` is a historical fill, not
   a current price.
2. **A rule enforced in a Pydantic model is invisible to every non-HTTP caller.** The
   assistant calls the service functions directly. A quantity guard that lives in a request
   model does not exist for it — that gap once let a model-authored `-5` fill and *credit*
   cash.
3. **A quote is not a membership claim.** The producer prices `watchlist ∪ open positions`,
   and the cache never evicts. Any list built from the streamed tickers will show symbols that
   are not on it.
4. **A fill at the mark does not change total value.** Cash falls by exactly what the position
   gains. Anything keyed on "total value changed" is dead code.
5. **A rejection is an outcome, not an error** (D6). A refused assistant action returns HTTP
   200 and is rendered as refused, with the reason. This is the one behaviour the whole chat
   design exists to protect.

## What is not verified

`VERIFICATION-PLAN.md` ends with an explicit list. The three worth knowing: the Massive real
-data path has never run against the live API; the mid-session SSE reconnect (a *live* stream
cut, rather than a refused one) is not stageable from Playwright; and nothing in this
repository asserts that the UI looks good — that is what `test/screenshots/` is for, and it
needs a human.
