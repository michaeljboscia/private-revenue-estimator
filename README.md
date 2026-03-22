# Private Revenue Estimator

Estimates annual revenue for private companies using AI-powered web research.

The core contribution is a **rules-based confidence scoring methodology** — rather than asking an LLM "how confident are you?" (inconsistent, expensive), the system collects structured source data and scores confidence in pure Python based on source quality, count, and variance. The scoring logic is fully deterministic given its inputs; note that credibility scores and source tiers are LLM-assigned, so two runs may produce slightly different raw inputs but the tier logic itself is stable.

```
$ python revenue_estimator.py --domain north40.com --company-name "North 40 Outfitters"

Researching North 40 Outfitters (north40.com) via gemini... done (8.4s)

============================================================
  North 40 Outfitters (north40.com)
============================================================

  Recommended:  $62M  [MODERATE-HIGH]
  Source:       RocketReach

  All estimates (2 found):
      $62M  Tier 4   70/100  RocketReach (2025)
      $58M  Tier 4   65/100  Growjo (2025)

  Variance:     7% across sources
  Ownership:    private
  Employees:    450

  Red flags:    all_aggregators
```

**Cost:** ~$0.04/company (Gemini, includes Search Grounding) | ~$0.03/company (OpenAI)
**Accuracy:** ~80-85% vs. manual research

---

## The Methodology

### Source Hierarchy

Research prioritizes sources by credibility. Most private companies only have Tier 4 data — knowing that is itself useful.

| Tier | Score | Sources |
|------|-------|---------|
| 1 | 90–100 | SEC filings, audited financials, official company reports |
| 2 | 70–89 | CEO/CFO interviews, analyst reports, verified funding announcements |
| 3 | 50–69 | Industry publications, trade journals, financial news |
| 4 | 30–49 | Aggregators: Growjo, RocketReach, ZoomInfo, Owler, LeadIQ, Zippia |

### Confidence Scoring

Scored in Python from structured data returned by the LLM — no second LLM call.

| Confidence | Criteria |
|------------|----------|
| HIGH | Best source ≥80, 2+ sources, ≤20% variance |
| MODERATE-HIGH | Best source ≥70, 2+ sources, ≤40% variance (or single source ≥80) |
| MODERATE | Best source ≥50, 2+ sources (or single source ≥60) |
| LOW | Data found but below above thresholds |
| INSUFFICIENT | No estimates found |

**Overrides:**
- Variance > 500% → cap at MODERATE (sources too far apart to trust)
- `stale_data` flag (>3 years old) → downgrade one level

### Why Deterministic Scoring?

LLMs produce inconsistent confidence assessments across runs and companies, making it impossible to rank or threshold a list of prospects. A rules-based system gives scores you can sort, filter, and act on.

---

## Installation

```bash
git clone https://github.com/michaeljboscia/private-revenue-estimator.git
cd private-revenue-estimator
pip install -r requirements.txt
```

Get a free Gemini API key at [aistudio.google.com](https://aistudio.google.com), then:

```bash
export GEMINI_API_KEY=your_key_here
```

---

## Usage

### Single company

```bash
python revenue_estimator.py --domain acme.com
python revenue_estimator.py --domain acme.com --company-name "Acme Corp"
python revenue_estimator.py --domain acme.com --provider openai
```

### Batch from CSV

```csv
domain,company_name
north40.com,North 40 Outfitters
primaryarms.com,Primary Arms
batteriesplus.com,Batteries Plus
```

```bash
python revenue_estimator.py --batch companies.csv
python revenue_estimator.py --batch companies.csv --json > results.json
```

### JSON output (for scripting)

```bash
python revenue_estimator.py --domain acme.com --json
```

```json
{
  "company": "Acme Corp",
  "domain": "acme.com",
  "research_date": "2026-03-05",
  "provider": "gemini",
  "recommended_estimate": "$47M",
  "recommended_source": "RocketReach",
  "confidence": "MODERATE-HIGH",
  "estimates_summary": "$47M (RocketReach 2025), $44M (Growjo 2025)",
  "revenue_estimates": [...],
  "ownership_type": "private",
  "employee_count": 250,
  "red_flags": ["all_aggregators"],
  "sources_found": 2,
  "variance_pct": 6.6,
  "elapsed_seconds": 8.4,
  "success": true
}
```

---

## Claude Code Skill

If you use Claude Code with Gemini configured as a sub-agent, you can run this natively without the Python script. Copy the skill file to your skills directory:

```bash
cp revenue-estimator.md ~/.claude/skills/
```

Then just ask Claude:

```
estimate revenue for acme.com
research revenue for "Acme Corp"
how much does Batteries Plus make?
```

---

## Provider Comparison

| | Gemini | OpenAI |
|---|---|---|
| Model | gemini-2.0-flash | gpt-4o |
| Search | Google Search grounding | web_search_preview |
| Cost/company | ~$0.04 (incl. Search Grounding) | ~$0.03 |
| Speed | ~8s | ~15s |
| Accuracy | ~80-85% | ~80-85% |

---

## Known Limitations

- **Aggregator dependency** — Most private companies have no Tier 1–2 sources. Confidence caps at MODERATE or MODERATE-HIGH in most cases.
- **Subsidiary ambiguity** — Hard to isolate subsidiary revenue from parent totals. The prompt explicitly instructs the model to report subsidiary-only figures, but this isn't always achievable.
- **No funding detection** — Recent funding rounds change trajectories but may not appear in aggregators yet.
- **International coverage** — Aggregators are US-heavy. EU/APAC companies return INSUFFICIENT more often.

---

## License

[FSL-1.1-ALv2](LICENSE) — Free for internal use, education, and research. Commercial competing use prohibited for 2 years per release, then auto-converts to Apache 2.0.
