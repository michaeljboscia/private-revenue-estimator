#!/usr/bin/env python3
"""
Private Revenue Estimator

Estimates annual revenue for private companies using AI-powered web research.

The core contribution is the confidence scoring methodology:
  - 4-tier source hierarchy (SEC filings → CEO interviews → trade journals → aggregators)
  - Rules-based 5-tier confidence scoring based on source quality, count, and variance
  - Automatic overrides for high variance and stale data

Supports Google Gemini (recommended) and OpenAI as research providers.

Usage:
    python revenue_estimator.py --domain acme.com
    python revenue_estimator.py --domain acme.com --company-name "Acme Corp"
    python revenue_estimator.py --domain acme.com --provider openai
    python revenue_estimator.py --batch companies.csv --json

Cost:     ~$0.04/company (Gemini, incl. Search Grounding) | ~$0.03/company (OpenAI)
Accuracy: ~80-85% vs. manual research

Environment:
    GEMINI_API_KEY    Required for --provider gemini (default)
    OPENAI_API_KEY    Required for --provider openai
"""

import os
import sys
import json
import argparse
import re
import csv
from datetime import datetime
from typing import Optional, Dict, Any, List

# =============================================================================
# Research Prompt
# =============================================================================

RESEARCH_PROMPT = """You are a financial research analyst specializing in private company revenue estimation.

TASK: Research annual revenue for {company_name} (domain: {domain}).

INSTRUCTIONS:

1. Search for the company's most recent annual revenue figures.

2. Prioritize sources in this order:
   - Tier 1 (90-100 credibility): SEC filings, audited financials, official company reports
   - Tier 2 (70-89): CEO/CFO interviews, analyst reports, verified funding announcements
   - Tier 3 (50-69): Industry publications, trade journals, financial news outlets
   - Tier 4 (30-49): Data aggregators (Growjo, RocketReach, ZoomInfo, Owler, LeadIQ, Zippia)

3. For EACH revenue estimate found, record:
   - Amount in millions (number only, e.g. 47.3 for $47.3M)
   - Display format (e.g. "$47.3M")
   - Source name and URL
   - Source tier (1-4)
   - Credibility score (0-100)
   - Year of the data

4. Detect company ownership:
   - public            Publicly traded company
   - private           Privately held company
   - subsidiary_public Subsidiary of a public company
   - subsidiary_private Subsidiary of a private company
   - unknown           Cannot determine

5. CRITICAL: For subsidiaries, report SUBSIDIARY revenue only — NOT the parent company total.

6. Note any red flags:
   - all_aggregators    Only Tier 4 sources found
   - high_variance      Sources differ by more than 3x
   - stale_data         Most recent data is more than 3 years old
   - single_source      Only one source found

Return ONLY valid JSON (no markdown, no code blocks) matching this exact structure:

{
  "company_name": "string",
  "domain": "string",
  "revenue_estimates": [
    {
      "amount_millions": 47.3,
      "amount_display": "$47.3M",
      "source_name": "RocketReach",
      "source_url": "https://rocketreach.co/acme",
      "source_tier": 4,
      "credibility_score": 70,
      "year": 2025,
      "notes": ""
    }
  ],
  "employee_count": {
    "count": 250,
    "source": "LinkedIn",
    "year": 2025
  },
  "ownership": {
    "type": "private",
    "parent_company_name": "",
    "parent_ticker": ""
  },
  "company_context": "2-3 sentence summary of what the company does",
  "research_quality": {
    "sources_found": 3,
    "highest_tier_found": 4,
    "red_flags": []
  }
}"""


# =============================================================================
# JSON Extraction
# =============================================================================

def extract_json(text: str) -> Dict[str, Any]:
    """
    Extract JSON from an LLM response, handling markdown code blocks,
    citation markers injected by search grounding, and multiple JSON blocks.

    Uses JSONDecoder.raw_decode to find the first complete, valid JSON object
    rather than greedy regex (which breaks when the response contains multiple
    brace-delimited blocks).
    """
    # Strip citation markers Gemini injects when using search grounding: [1], [2] etc.
    cleaned = re.sub(r'\[\d+\]', '', text)

    # Try direct parse first
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Try markdown code block
    match = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', cleaned)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Walk the string finding '{' and attempt raw_decode from each position.
    # This correctly handles responses with multiple JSON-like blocks.
    decoder = json.JSONDecoder()
    idx = 0
    while idx < len(cleaned):
        idx = cleaned.find('{', idx)
        if idx == -1:
            break
        try:
            obj, _ = decoder.raw_decode(cleaned, idx)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
        idx += 1

    return {
        "parse_error": True,
        "revenue_estimates": [],
        "ownership": {"type": "unknown"},
        "research_quality": {"sources_found": 0, "red_flags": ["json_parse_error"]}
    }


# =============================================================================
# Providers
# =============================================================================

def research_with_gemini(domain: str, company_name: str, api_key: str) -> Dict[str, Any]:
    """
    Research revenue using Gemini with Google Search grounding.

    The key advantage over OpenAI: Google Search grounding is built in,
    giving Gemini access to real-time indexed data without a separate search step.
    """
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise ImportError(
            "google-genai not installed. Run: pip install google-genai"
        )

    client = genai.Client(api_key=api_key)
    prompt = RESEARCH_PROMPT.format(company_name=company_name, domain=domain)

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=f"Research annual revenue for: {company_name} (domain: {domain})",
        config=types.GenerateContentConfig(
            system_instruction=prompt,
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.2
        )
    )

    data = extract_json(response.text)
    data.setdefault("domain", domain)
    data.setdefault("company_name", company_name)
    return data


def research_with_openai(domain: str, company_name: str, api_key: str) -> Dict[str, Any]:
    """
    Research revenue using OpenAI with built-in web search.

    Uses gpt-4o-search-preview which has web search baked in via the standard
    Chat Completions API — no beta Responses API required.

    Note: if you get a NotFoundError, this model may have been renamed or
    require a higher-tier OpenAI plan. Check https://platform.openai.com/docs/models
    for the current model name that supports web search via Chat Completions.
    """
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError(
            "openai not installed. Run: pip install openai"
        )

    client = OpenAI(api_key=api_key)
    prompt = RESEARCH_PROMPT.format(company_name=company_name, domain=domain)

    response = client.chat.completions.create(
        model="gpt-4o-search-preview",
        messages=[{"role": "user", "content": f"{prompt}\n\nCompany: {company_name} (domain: {domain})"}]
    )

    data = extract_json(response.choices[0].message.content)
    data.setdefault("domain", domain)
    data.setdefault("company_name", company_name)
    return data


# =============================================================================
# Confidence Scoring
#
# This is the core methodological contribution: rules-based confidence scoring
# based on source quality, count, and variance — no LLM call required.
#
# Why rules-based?
#   Asking an LLM "how confident are you?" produces inconsistent results across
#   runs and companies. A deterministic system gives scores you can sort, filter,
#   and act on across your entire prospect list.
#
#   Note: the LLM assigns credibility_score and source_tier as inputs, so two
#   runs may produce slightly different raw scores. The confidence tier logic
#   itself is fully deterministic given those inputs.
# =============================================================================

def calculate_confidence(data: Dict[str, Any]) -> str:
    """
    Score confidence in the revenue estimate using source quality and variance.

    Returns one of: HIGH | MODERATE-HIGH | MODERATE | LOW | INSUFFICIENT

    Base tiers:
        HIGH:          best source >= 80, 2+ valid sources, variance <= 20%
        MODERATE-HIGH: best source >= 70, 2+ valid sources, variance <= 40%
                       (or single source >= 80)
        MODERATE:      best source >= 50, 2+ valid sources
                       (or single source >= 60)
        LOW:           data found but doesn't meet above thresholds
        INSUFFICIENT:  no estimates with valid amounts found

    Overrides:
        sources spread >5x  -> cap at MODERATE (too far apart to trust)
        stale_data flag      -> downgrade one level, but never below LOW
    """
    estimates = data.get("revenue_estimates", [])

    # Only count estimates with actual amounts — zero/missing amounts don't
    # contribute to revenue confidence even if the source has a credibility score.
    valid = [e for e in estimates if e.get("amount_millions", 0) > 0]
    if not valid:
        return "INSUFFICIENT"

    best_score = max(e.get("credibility_score", 0) for e in valid)
    count = len(valid)
    amounts = [e["amount_millions"] for e in valid]

    # Use max/min ratio to detect outlier sources (e.g. $10M vs $60M = 6x spread).
    # Mean-based variance caps at ~200% for two data points, making a >300% or >500%
    # threshold mathematically unreachable. Ratio-based comparison has no such limit.
    spread_ratio = max(amounts) / min(amounts) if min(amounts) > 0 else 1.0

    # Variance percentage for display purposes only (used in format_result)
    mean = sum(amounts) / len(amounts)
    variance_pct_display = (max(amounts) - min(amounts)) / mean * 100 if mean > 0 else 0.0

    red_flags = data.get("research_quality", {}).get("red_flags", [])
    high_variance = spread_ratio > 5.0 or "high_variance" in red_flags
    stale = "stale_data" in red_flags

    # Base tier
    if best_score >= 80 and count >= 2 and variance_pct_display <= 20:
        confidence = "HIGH"
    elif best_score >= 70 and count >= 2 and variance_pct_display <= 40:
        confidence = "MODERATE-HIGH"
    elif best_score >= 80 and count == 1:
        confidence = "MODERATE-HIGH"
    elif best_score >= 50 and count >= 2:
        confidence = "MODERATE"
    elif best_score >= 60 and count == 1:
        confidence = "MODERATE"
    else:
        confidence = "LOW"

    # Override: extreme spread caps at MODERATE
    if high_variance and confidence in ("HIGH", "MODERATE-HIGH"):
        confidence = "MODERATE"

    # Override: stale data downgrades one level, but never below LOW
    # (INSUFFICIENT means "no data found" — stale data is still data)
    if stale and confidence not in ("INSUFFICIENT", "LOW"):
        order = ["INSUFFICIENT", "LOW", "MODERATE", "MODERATE-HIGH", "HIGH"]
        confidence = order[max(0, order.index(confidence) - 1)]

    return confidence


def variance_pct(estimates: List[Dict]) -> float:
    """Calculate variance percentage across revenue estimates."""
    amounts = [e["amount_millions"] for e in estimates if e.get("amount_millions", 0) > 0]
    if len(amounts) < 2:
        return 0.0
    mean = sum(amounts) / len(amounts)
    return (max(amounts) - min(amounts)) / mean * 100 if mean > 0 else 0.0


# =============================================================================
# Output
# =============================================================================

def format_result(data: Dict[str, Any], confidence: str, provider: str) -> Dict[str, Any]:
    """Structure the research output."""
    estimates = data.get("revenue_estimates", [])
    ownership = data.get("ownership", {})
    today = datetime.now().strftime("%Y-%m-%d")

    sorted_ests = sorted(estimates, key=lambda x: x.get("credibility_score", 0), reverse=True)
    best = sorted_ests[0] if sorted_ests else None

    summary_parts = [
        f"{e.get('amount_display')} ({e.get('source_name')} {e.get('year', '')})"
        for e in sorted_ests[:4]
    ]

    return {
        "company": data.get("company_name"),
        "domain": data.get("domain"),
        "research_date": today,
        "provider": provider,
        "recommended_estimate": best.get("amount_display") if best else None,
        "recommended_source": best.get("source_name") if best else None,
        "confidence": confidence,
        "estimates_summary": ", ".join(summary_parts) if summary_parts else "No data found",
        "revenue_estimates": sorted_ests,
        "ownership_type": ownership.get("type", "unknown") if isinstance(ownership, dict) else "unknown",
        "parent_company": ownership.get("parent_company_name", "") if isinstance(ownership, dict) else "",
        "employee_count": data.get("employee_count", {}).get("count"),
        "company_context": data.get("company_context", ""),
        "red_flags": data.get("research_quality", {}).get("red_flags", []),
        "sources_found": len(estimates),
        "variance_pct": round(variance_pct(estimates), 1),
    }


def print_result(result: Dict[str, Any]) -> None:
    """Human-readable output."""
    print(f"\n{'='*60}")
    print(f"  {result['company']} ({result['domain']})")
    print(f"{'='*60}")

    if result.get("recommended_estimate"):
        print(f"\n  Recommended:  {result['recommended_estimate']}  [{result['confidence']}]")
        print(f"  Source:       {result.get('recommended_source')}")
    else:
        print(f"\n  Result:  INSUFFICIENT DATA")

    if result.get("revenue_estimates"):
        print(f"\n  All estimates ({result['sources_found']} found):")
        for e in result["revenue_estimates"]:
            amount = str(e.get("amount_display") or "N/A")
            score = e.get("credibility_score") or 0
            print(
                f"    {amount:>8}  "
                f"Tier {e.get('source_tier', '?')}  "
                f"{score:>3}/100  "
                f"{e.get('source_name', 'Unknown')} ({e.get('year', '?')})"
            )

    if result.get("variance_pct", 0) > 0:
        print(f"\n  Variance:     {result['variance_pct']:.0f}% across sources")

    if result.get("ownership_type"):
        print(f"  Ownership:    {result['ownership_type']}")

    if result.get("employee_count"):
        print(f"  Employees:    {result['employee_count']:,}")

    if result.get("company_context"):
        print(f"\n  Context:      {result['company_context']}")

    if result.get("red_flags"):
        print(f"\n  Red flags:    {', '.join(result['red_flags'])}")

    print(f"\n  Provider:     {result['provider']}")
    print(f"  Date:         {result['research_date']}")
    print()


# =============================================================================
# Orchestration
# =============================================================================

def process_company(
    domain: str,
    company_name: str,
    provider: str,
    gemini_key: Optional[str],
    openai_key: Optional[str],
    verbose: bool = True
) -> Dict[str, Any]:
    """Research revenue for a single company."""
    start = datetime.now()

    if verbose:
        print(f"Researching {company_name} ({domain}) via {provider}...", end=" ", flush=True)

    try:
        if provider == "gemini":
            if not gemini_key:
                raise ValueError(
                    "GEMINI_API_KEY not set.\n"
                    "Get a free key at https://aistudio.google.com\n"
                    "Then: export GEMINI_API_KEY=your_key"
                )
            data = research_with_gemini(domain, company_name, gemini_key)
        else:
            if not openai_key:
                raise ValueError(
                    "OPENAI_API_KEY not set.\n"
                    "Get a key at https://platform.openai.com\n"
                    "Then: export OPENAI_API_KEY=your_key"
                )
            data = research_with_openai(domain, company_name, openai_key)
    except Exception as e:
        if verbose:
            print("ERROR")
        return {
            "success": False,
            "domain": domain,
            "company": company_name,
            "provider": provider,
            "research_date": datetime.now().strftime("%Y-%m-%d"),
            "error": str(e),
            "elapsed_seconds": round((datetime.now() - start).total_seconds(), 1)
        }

    confidence = calculate_confidence(data)
    result = format_result(data, confidence, provider)
    result["elapsed_seconds"] = round((datetime.now() - start).total_seconds(), 1)
    result["success"] = True

    if verbose:
        print(f"done ({result['elapsed_seconds']}s)")

    return result


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Estimate annual revenue for private companies using AI-powered research.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python revenue_estimator.py --domain acme.com
  python revenue_estimator.py --domain acme.com --company-name "Acme Corp"
  python revenue_estimator.py --domain acme.com --provider openai
  python revenue_estimator.py --batch companies.csv
  python revenue_estimator.py --domain acme.com --json

environment variables:
  GEMINI_API_KEY    required for --provider gemini (default)
  OPENAI_API_KEY    required for --provider openai
        """
    )

    parser.add_argument("--domain", help="Company domain (e.g. acme.com)")
    parser.add_argument("--company-name", help="Company name (derived from domain if omitted)")
    parser.add_argument(
        "--provider", choices=["gemini", "openai"], default="gemini",
        help="AI provider (default: gemini, ~$0.04/co | openai, ~$0.03/co)"
    )
    parser.add_argument(
        "--batch", metavar="FILE",
        help="CSV with columns: domain, company_name"
    )
    parser.add_argument(
        "--json", action="store_true", dest="json_output",
        help="Output as JSON"
    )

    args = parser.parse_args()

    gemini_key = os.environ.get("GEMINI_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    verbose = not args.json_output

    if args.batch:
        if not os.path.exists(args.batch):
            print(f"Error: file not found: {args.batch}", file=sys.stderr)
            sys.exit(1)

        results = []
        with open(args.batch, newline="") as f:
            for row in csv.DictReader(f):
                domain = row.get("domain", "").strip()
                if not domain:
                    continue
                company = row.get("company_name", domain.split(".")[0].title()).strip()
                result = process_company(domain, company, args.provider, gemini_key, openai_key, verbose)
                results.append(result)
                if verbose:
                    print_result(result)

        if args.json_output:
            print(json.dumps(results, indent=2, default=str))
        return

    if not args.domain:
        parser.print_help()
        sys.exit(1)

    company = args.company_name or args.domain.split(".")[0].title()
    result = process_company(args.domain, company, args.provider, gemini_key, openai_key, verbose)

    if verbose:
        print_result(result)
    else:
        print(json.dumps(result, indent=2, default=str))

    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()
