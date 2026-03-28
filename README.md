# HVAC Lead Audit Engine

**"Find the Bleeding Neck" GTM Pipeline — Automated**

A Python pipeline that finds local service businesses, audits their websites for fixable incompetence, scores them as sales leads, and generates personalized diagnostic cold emails. Output: a ranked XLSX spreadsheet ready for outreach.

Built on the premise that the best prospects aren't those who need to be convinced they need marketing — they're the ones **already spending money on marketing that's visibly broken.**

---

## How It Works

```
Google Places API → Find HVAC businesses in 10 US metros
         ↓
   Website Auditor → Check 13 incompetence signals per site
         ↓
    Lead Scorer → Rank 0-130 (higher = worse site = better lead)
         ↓
  Email Generator → Personalized diagnostic cold outreach
         ↓
    XLSX Output → Two sheets: Audit Results + Email Drafts
```

### 13 Signals Audited

| Signal | Weight | Why It Matters |
|--------|--------|----------------|
| No phone visible | 20 | #1 conversion killer for emergency services |
| Slow load (>3s) | 15 | 53% of mobile users abandon after 3 seconds |
| No click-to-call | 15 | Mobile users can't tap to dial |
| Homepage as landing | 15 | Ads → generic homepage = 50%+ conversion loss |
| No SSL | 10 | Browser shows "Not Secure" warning |
| No contact form | 10 | After-hours customers have no way to reach |
| No analytics | 10 | Zero visibility into traffic or conversions |
| No mobile viewport | 10 | Site is broken on phones |
| No GTM | 5 | Can't track ad conversions |
| No meta description | 5 | Google shows random page text in results |
| No H1 tag | 5 | Hurts local search ranking |
| No schema markup | 5 | No rich snippets in Google results |
| No reviews on site | 5 | Missing social proof |

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run in demo mode (no API key needed)

```bash
python run_audit.py --demo
```

This audits 5 real manufacturer websites to show the pipeline working end-to-end.

### 3. Run with your own URLs

Add businesses to `urls.txt`:

```
Joe's HVAC|https://www.joeshvac.com|Dallas|TX
ComfortAir|https://comfortairsolutions.com|Phoenix|AZ
```

Then run:

```bash
python run_audit.py --urls
```

### 4. Full run with Google Places API

```bash
export GOOGLE_PLACES_API_KEY="your-key-here"
python run_audit.py
```

Get a free API key at [Google Cloud Console](https://console.cloud.google.com/apis/credentials). Enable "Places API (New)". Free tier = $200/month credit (~1,000 searches).

### 5. Switch niches

```bash
python run_audit.py --niche "pest control"
python run_audit.py --niche "garage door repair"
python run_audit.py --niche "roofing contractor"
```

---

## Output

Two-sheet XLSX:

- **Sheet 1 — Audit Results**: Ranked by score, color-coded (🔥 Hot ≥80, 🟡 Warm ≥50), with top 3 issues per business
- **Sheet 2 — Email Drafts**: Ready-to-send diagnostic cold emails personalized to each business's specific issues

---

## File Structure

```
hvac-gtm-pipeline/
├── config.py            # API keys, metro targets, scoring weights
├── find_businesses.py   # Google Places API search module
├── audit_engine.py      # 13-signal website auditor + scorer
├── email_generator.py   # Diagnostic cold email generator
├── run_audit.py         # Main orchestrator (entry point)
├── urls.txt             # Manual URL input (for --urls mode)
├── requirements.txt     # Python dependencies
└── README.md            # This file
```

---

## Architecture Decisions

- **No database** — XLSX is the deliverable. Operators in this market live in spreadsheets, not dashboards.
- **Scoring, not classification** — A continuous 0-130 scale lets you prioritize outreach by severity, not binary qualify/disqualify.
- **Diagnostic emails, not sales emails** — "You're bleeding here" converts 3x better than "hire me" for this buyer profile.
- **Niche-agnostic core** — The audit engine works on any website. Swap the Places API keyword and email copy to enter a new vertical in 10 minutes.

---

## Expanding to New Niches

The `config.py` file includes 10 pre-mapped alternate niches. To add a new one:

1. Add the keyword to `ALTERNATE_NICHES` in `config.py`
2. Run: `python run_audit.py --niche "your niche"`
3. Optionally customize email copy in `email_generator.py` (swap "HVAC" references)

---

## License

MIT
