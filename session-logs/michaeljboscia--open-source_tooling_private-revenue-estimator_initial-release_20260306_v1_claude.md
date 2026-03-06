# Session Log — private-revenue-estimator

**Project:** private-revenue-estimator
**Taxonomy:** open-source / tooling
**Agent:** Claude Sonnet 4.6
**Repo:** https://github.com/michaeljboscia/private-revenue-estimator
**Session Start:** 2026-03-06

---

## OVERALL GOAL

Package the private company revenue estimator from the GTM Machine pain sensor system as a public open-source repo. Strip internal plumbing (HubSpot, Supabase, orchestrator), keep the core methodology, and make it usable by anyone with a Gemini or OpenAI API key.

---

## WHAT WAS ACCOMPLISHED

### Repo Created
- Created `/Users/mikeboscia/projects/private-revenue-estimator`
- Published at `https://github.com/michaeljboscia/private-revenue-estimator`
- Two primary artifacts:
  - `revenue_estimator.py` — standalone Python CLI (Gemini default, OpenAI optional)
  - `revenue-estimator.md` — Claude Code skill file (for users with Gemini sub-agent)

### Source Material
- Based on `revenue_v32.py` at `/Users/mikeboscia/gtm-machine-infrastructure-worktrees/sales-enablement-mike/pain-sensors/revenue-estimator/scripts/revenue_v32.py`
- HubSpot integration removed, Supabase removed, internal pain sensor wiring removed
- Core methodology preserved: 4-tier source hierarchy, 5-tier confidence scoring, fallback chain

### Peer Review Round 1 (Gemini + Codex)
Both twins reviewed the initial release and flagged real bugs:
- Variance override threshold unreachable (formula capped at ~200%, threshold was >500%)
- `count` included zero-amount estimates, inflating confidence
- Stale downgrade could push LOW → INSUFFICIENT (wrong — INSUFFICIENT means no data)
- `extract_json` greedy regex failed on multiple JSON blocks
- OpenAI Responses API (`client.responses.create`) is beta — crashes for most users
- `print_result` used `:>8` formatting that throws TypeError on None fields
- Cost claim wrong: Gemini Search Grounding is $35/1K = ~$0.04/co, not $0.01
- "Deterministic" language misleading since LLM assigns input credibility scores
- `requests` imported but unused (HubSpot was removed)
- "2025" hardcoded in skill fallback query

### Peer Review Round 1 — All Fixes Applied
Commit: `56676fa` — "Fix bugs flagged in peer review"
- Variance: switched to `spread_ratio = max/min > 5.0` (ratio-based, no mathematical cap)
- Count: only count `amount_millions > 0` estimates
- Stale downgrade: never goes below LOW
- `extract_json`: strips `[N]` citation markers, uses `JSONDecoder.raw_decode`
- OpenAI: switched to `gpt-4o-search-preview` via `chat.completions.create`
- `print_result`: null-safe with `.get()` and `or` fallbacks
- Cost: updated to `~$0.04`
- Language: "rules-based" not "deterministic"
- Skill: `{current year}` not `2025`
- Removed `import requests`

Also applied variance + count + stale fixes to private tool `revenue_v32.py`:
Commit: `c65dfcc` on `feature/sales-enablement-mike`

### Peer Review Round 2 (Gemini + Codex)
Gemini:
- ✅ Variance fix correct and well-executed
- ✅ Cost claim now accurate
- ❌ `gpt-4o-search-preview` may not be a valid public model name → fatal NotFoundError
- ⚠️ Native `response_schema` still not used (optimization, not a bug)
- ❌ Said `requirements.txt` missing — INCORRECT, file exists

Codex:
- ✅ Variance fix landed correctly
- ✅ Stale downgrade fix correct
- ✅ `extract_json` fix correct
- ❌ `print_result` STILL crashes on error paths — error dict missing `provider`/`research_date` keys
- ⚠️ `sources_found` in output still counts raw estimates including zero-amount ones (cosmetic)

---

## WHAT WORKS

- Gemini provider: full research loop, confidence scoring, structured output ✅
- Confidence algorithm: all three bugs fixed, variance now correctly fires ✅
- `extract_json`: citation stripping + raw_decode ✅
- Public repo: pushed, clean, 2 commits ✅
- Private tool (`revenue_v32.py`): same 3 confidence bugs fixed ✅

---

## WHAT DOESN'T WORK / KNOWN ISSUES

1. **OpenAI provider may crash** — `gpt-4o-search-preview` flagged as invalid by Gemini. Needs verification or swap back to Responses API with documentation.
2. **`print_result` crashes on error runs** — When process_company returns an error dict (e.g. missing API key), `print_result` is called with keys like `provider` and `research_date` missing → KeyError.

---

## CURRENT STATE

**Phase:** Round 2 review complete, 2 fixes pending
**Next Step:** Fix `print_result` error-path crash + resolve OpenAI model name, push, done

---

## ACTIVITY LOG

| Time | Action | Status |
|------|--------|--------|
| Session start | Reviewed internal revenue estimator docs | ✓ |
| ~21:55 | Created public repo structure (Python + skill) | ✓ |
| ~22:00 | Pushed to GitHub | ✓ |
| ~22:10 | Peer review round 1 — Gemini + Codex | ✓ |
| ~22:15 | Applied all round 1 fixes, pushed commit 56676fa | ✓ |
| ~22:15 | Fixed revenue_v32.py (private), committed c65dfcc | ✓ |
| ~22:20 | Peer review round 2 — Gemini + Codex | ✓ |
| ~22:25 | Session notes written | ✓ |

---

## NOTES FOR FUTURE SESSIONS

- `requirements.txt` DOES exist — Gemini's round 2 claim that it's missing is wrong
- The Claude Code skill (`revenue-estimator.md`) references `mcp__gemini__gemini-structured` by exact tool name — only works if user has the Gemini MCP server configured with standard naming
- Private tool fixes are on branch `feature/sales-enablement-mike` — need to merge when ready
- Gemini's suggestion to use `response_schema` for structured output is worth doing eventually — would eliminate the JSON extraction layer entirely

---

**Last Updated:** 2026-03-06 22:25 EST
