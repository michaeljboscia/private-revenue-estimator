# Revenue Estimator

**Trigger:** User asks to "estimate revenue for [company]", "research [company] revenue", "how much does [company] make", or similar.

**Prerequisites:** Gemini MCP tools must be available (`mcp__gemini__gemini-structured`, `mcp__gemini__gemini-search`, `mcp__gemini__gemini-extract`).

---

## What This Does

Estimates annual revenue for private companies using Gemini with Google Search grounding. Searches primary sources first (SEC filings, CEO interviews, analyst reports), then aggregators as fallback. Returns estimates with source attribution and a 5-tier confidence score.

Cost: ~$0.01 per company. Accuracy: ~80-85% vs. manual research.

---

## Step 1: Identify Company

Extract from the user's message:
- `domain` — company domain (e.g. `acme.com`)
- `company_name` — company name (e.g. `Acme Corp`)

If the user provides only a domain, derive a reasonable company name from it. If you have neither, ask the user before proceeding.

---

## Step 2: Primary Research

Call `mcp__gemini__gemini-structured` with **Google Search grounding enabled** and the following prompt and schema.

**Prompt:**

```
You are a financial research analyst specializing in private company revenue estimation.

Research annual revenue for {company_name} (domain: {domain}).

INSTRUCTIONS:
1. Search for the company's most recent annual revenue figures.

2. Prioritize sources in this order:
   - Tier 1 (90-100 credibility): SEC filings, audited financials, official company reports
   - Tier 2 (70-89): CEO/CFO interviews in major publications, analyst reports, verified funding announcements
   - Tier 3 (50-69): Industry publications, trade journals, financial news outlets
   - Tier 4 (30-49): Data aggregators (Growjo, RocketReach, ZoomInfo, Owler, LeadIQ, Zippia)

3. For EACH revenue estimate found, record:
   - Amount in millions (number, e.g. 47.3)
   - Display format (e.g. "$47.3M")
   - Source name and URL
   - Source tier (1-4)
   - Credibility score (0-100)
   - Year of the data

4. Detect company ownership:
   - public: Publicly traded
   - private: Privately held
   - subsidiary_public: Subsidiary of a public company
   - subsidiary_private: Subsidiary of a private company
   - unknown: Cannot determine

5. CRITICAL: For subsidiaries, report SUBSIDIARY revenue only — NOT the parent company total.

6. Note red flags:
   - all_aggregators: Only Tier 4 sources found
   - high_variance: Sources differ by more than 3x
   - stale_data: Most recent data is more than 3 years old
   - single_source: Only one source found

Return ONLY valid JSON matching this schema — no markdown, no explanation.
```

**Schema:**

```json
{
  "company_name": "string",
  "domain": "string",
  "revenue_estimates": [
    {
      "amount_millions": 0,
      "amount_display": "",
      "source_name": "",
      "source_url": "",
      "source_tier": 0,
      "credibility_score": 0,
      "year": 0,
      "notes": ""
    }
  ],
  "employee_count": {
    "count": 0,
    "source": "",
    "year": 0
  },
  "ownership": {
    "type": "",
    "parent_company_name": "",
    "parent_ticker": ""
  },
  "company_context": "",
  "research_quality": {
    "sources_found": 0,
    "highest_tier_found": 0,
    "red_flags": []
  }
}
```

**After the call — decision gate:**

- Got 1+ estimates → go to Step 3
- Got 0 estimates → go to Step 2a (Validation Fallback)
- Tool error or crash → go to Step 2b (WebSearch Fallback)

---

## Step 2a: Validation Fallback (0 estimates returned)

Call `mcp__gemini__gemini-search` with query: `"{company_name}" annual revenue estimate {current year}`

Then call `mcp__gemini__gemini-extract` on those results using the same `revenue_estimates` array schema from Step 2.

Merge any found estimates and continue to Step 3.

---

## Step 2b: WebSearch Fallback (Gemini tools unavailable)

Run 6 parallel `WebSearch` calls:

```
site:growjo.com "{company_name}" revenue
site:rocketreach.co "{company_name}" revenue annual
site:zoominfo.com "{company_name}" revenue
site:leadiq.com "{company_name}" revenue
site:owler.com "{company_name}" revenue
site:theorg.com "{company_name}" revenue employees
```

Extract any `$XXM` or `$XXB` patterns from results. Treat all as Tier 4 / credibility score 40. Continue to Step 3 with whatever was found.

---

## Step 3: Confidence Scoring

Calculate confidence in pure logic — no LLM call needed.

**Inputs:**
- `best_score` = highest `credibility_score` across all estimates
- `count` = number of estimates
- `variance_pct` = `(max - min) / mean * 100` across `amount_millions` values

**Base tier:**

| Condition | Confidence |
|-----------|-----------|
| best_score ≥ 80, count ≥ 2, variance ≤ 20% | HIGH |
| best_score ≥ 70, count ≥ 2, variance ≤ 40% | MODERATE-HIGH |
| best_score ≥ 80, count = 1 | MODERATE-HIGH |
| best_score ≥ 50, count ≥ 2 | MODERATE |
| best_score ≥ 60, count = 1 | MODERATE |
| Data found but below above | LOW |
| No estimates found | INSUFFICIENT |

**Overrides (apply after base tier):**
- `high_variance` flag OR variance > 500% → cap at MODERATE
- `stale_data` flag → downgrade one level (e.g. MODERATE-HIGH → MODERATE)

---

## Step 4: Present Results

Display in this format:

---

### Revenue Research: {company_name} ({domain})

**Recommended:** {best estimate by credibility score} — **{CONFIDENCE}**

| Source | Amount | Tier | Score | Year |
|--------|--------|------|-------|------|
| {source_name} | {amount_display} | {source_tier} | {credibility_score}/100 | {year} |

**Ownership:** {type}
**Employees:** {count} ({source}, {year}) — *omit if not found*
**Company:** {company_context}

**Confidence rationale:** {1-sentence explanation — e.g. "Two Tier 4 sources within 7% variance; no primary sources found."}
**Red flags:** {list, or "None" if clean}

---

If confidence is INSUFFICIENT, say so clearly and suggest the user try manual research on Crunchbase, PitchBook, or the company's own press releases.

---

## Source Reference

| Tier | Score Range | Examples |
|------|-------------|---------|
| 1 | 90–100 | SEC filings, Bloomberg Terminal, audited financials |
| 2 | 70–89 | TechCrunch/Forbes CEO quotes, Crunchbase verified, Gartner/Forrester |
| 3 | 50–69 | Industry trade journals, conference presentations |
| 4 | 30–49 | Growjo, RocketReach, ZoomInfo, Owler, LeadIQ, Zippia |
