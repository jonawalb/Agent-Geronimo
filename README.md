# Agent Geronimo

**Exhaustive Funding Opportunity Discovery System**

Agent Geronimo is a production-ready local agent that searches, aggregates, scores, and exports funding opportunities relevant to:

- **Taiwan Security Monitor (TSM)** — OSINT, Indo-Pacific analysis, narrative warfare monitoring
- **George Mason University's Schar School / CSPS** — National security center programming
- **Security studies organizations** — Think tanks, university policy centers, defense research

## Quick Start

```bash
# 1. Setup (one time)
cd ~/agent-geronimo
chmod +x setup.sh
./setup.sh

# 2. Run
source .venv/bin/activate
python geronimo.py run

# Or after shell restart:
geronimo
run-agent-geronimo
```

## What It Does

Agent Geronimo runs a 6-stage pipeline:

| Stage | What Happens |
|-------|-------------|
| **1. Discovery** | Queries Grants.gov, SAM.gov, RSS feeds, foundation websites, and web searches |
| **2. Deduplication** | Removes duplicates using fuzzy title matching, URL normalization, and ID matching |
| **3. Enrichment** | Visits opportunity pages to extract details, deadlines, eligibility, and portal links |
| **4. Scoring** | Scores each opportunity for TSM fit, GMU center fit, and general security relevance |
| **5. Local Alignment** | Reads TSM!!! folder and local files to match against existing pipeline and concepts |
| **6. Export** | Produces formatted Excel workbook, CSV, JSON, and Markdown summary |

## Output

The primary output is an Excel workbook saved to `output/`:

```
Agent_Geronimo_Funding_Results_YYYY_MM_DD.xlsx
```

### Sheets

1. **Master Opportunities** — All opportunities with 65+ columns, color-coded by priority
2. **Top Priority - TSM** — Highest TSM-fit opportunities
3. **Top Priority - GMU Center** — Highest GMU center-fit opportunities
4. **Federal Grants** — Federal grant opportunities
5. **Contracts / BAAs / RFPs** — Contract and solicitation opportunities
6. **Foundations** — Foundation and philanthropic opportunities
7. **Past Award Analysis** — Funder intelligence and prior award profiles
8. **Source Log** — Which sources were queried and their status
9. **Run Notes** — Run statistics and methodology notes
10. **Pipeline Fit Notes** — TSM pipeline alignment analysis

### Key Columns

- **TSM Fit Score** (0-100) — Relevance to Taiwan Security Monitor
- **GMU Center Fit Score** (0-100) — Relevance to a GMU national security center
- **Overall Relevance Score** (0-100) — Weighted composite score
- **Why This Could Work** — Plain-English synthesis of opportunity-TSM-funder fit
- **Suggested Framing** — How to position a proposal for TSM and GMU
- **Suggested Proposal Angle** — Concrete proposal direction
- **Final Recommendation** — Apply / Consider / Track / Low fit

## Sources

### APIs (Structured)
- **Grants.gov** — Federal grants (no API key needed)
- **SAM.gov** — Federal contracts/BAAs (free API key recommended)
- **USAspending.gov** — Past award intelligence (public API)

### RSS Feeds
- Grants.gov by agency (DOD, DOS, DHS, NSF)

### Web Scraping
- Smith Richardson Foundation
- Carnegie Corporation
- National Endowment for Democracy (NED)
- MacArthur Foundation
- Henry Luce Foundation
- Ploughshares Fund
- Stanton Foundation
- Open Society Foundations
- DARPA, DIU, Minerva, Challenge.gov
- Additional sites via config

### Local Context
- `~/Desktop/TSM!!!` — TSM proposal drafts, pitch decks, concept notes
- `~/Desktop/Grants` — Prior grant materials

## Configuration

### API Keys (Optional but Recommended)

Edit `.env`:

```bash
# SAM.gov — Free from https://api.sam.gov
SAM_GOV_API_KEY=your_key_here

# Google Custom Search — For broader web discovery
GOOGLE_API_KEY=your_key
GOOGLE_CSE_ID=your_cse_id
```

### Source Registry

Edit `config/sources.yaml` to add/remove/enable sources.

### Keywords

Edit `config/keywords.yaml` to modify search terms and categories.

### Settings

Edit `config/settings.yaml` for output paths, cache TTL, rate limits, etc.

## Architecture

```
agent-geronimo/
├── geronimo.py              # CLI entry point
├── config/
│   ├── settings.yaml        # General settings
│   ├── keywords.yaml        # Search keywords and categories
│   └── sources.yaml         # Source registry (extensible)
├── src/
│   ├── pipeline.py          # Main 6-stage orchestrator
│   ├── models.py            # Data models (Opportunity, RunStats)
│   ├── discovery/           # Stage 1: Source scrapers
│   │   ├── base.py          # Abstract base scraper
│   │   ├── grants_gov.py    # Grants.gov API
│   │   ├── sam_gov.py       # SAM.gov API
│   │   ├── usaspending.py   # Past award data
│   │   ├── web_search.py    # Web scraping + Google CSE
│   │   └── rss_feeds.py     # RSS feed parser
│   ├── enrichment/          # Stage 2-4: Detail and award enrichment
│   │   ├── detail_fetcher.py
│   │   └── award_analyzer.py
│   ├── scoring/             # Stage 3-5: Relevance scoring
│   │   ├── relevance.py     # Multi-lens keyword scoring
│   │   └── local_context.py # TSM local file matching
│   ├── dedup/               # Deduplication
│   │   └── deduplicator.py  # Fuzzy + exact dedup
│   ├── export/              # Stage 6: Output generation
│   │   ├── excel_writer.py  # Formatted Excel workbook
│   │   ├── csv_json_writer.py
│   │   └── markdown_writer.py
│   └── utils/
│       ├── http_client.py   # Rate-limited HTTP client
│       ├── cache.py         # SQLite response cache
│       └── logging_config.py
├── output/                  # Generated reports
├── cache/                   # SQLite cache database
├── requirements.txt
├── .env.template
├── .env                     # Your API keys (gitignored)
├── setup.sh                 # One-time setup script
└── README.md
```

## Extending

### Add a New Source

1. Create a new scraper in `src/discovery/` inheriting from `BaseScraper`
2. Implement the `search()` method
3. Add the source to `config/sources.yaml`
4. Import and instantiate in `src/pipeline.py` Stage 1

### Add Keywords

Edit `config/keywords.yaml` and add terms to the appropriate category.

### Modify Scoring

Edit `src/scoring/relevance.py` to adjust keyword weights or add new scoring dimensions.

## CLI Reference

```bash
python geronimo.py run              # Full pipeline
python geronimo.py run --fresh      # Clear cache first
python geronimo.py run --log-level DEBUG  # Verbose logging
python geronimo.py status           # Check last output
python geronimo.py clear-cache      # Clear cached data
```

## Notes

- **Rate limiting**: Default 2 req/sec. Adjust in `config/settings.yaml`.
- **Cache**: Responses cached for 24 hours. Use `--fresh` to bypass.
- **Robots.txt**: Respected by default. Web scraping is polite.
- **No fabrication**: If data can't be verified, fields are left blank with confidence notes.
- **SAM.gov DEMO_KEY**: Works but has low rate limits. Register for a free key for better results.

## Sources Requiring Credentials

| Source | Key Required | How to Get |
|--------|-------------|-----------|
| SAM.gov | Recommended | Free at https://api.sam.gov |
| Google CSE | Optional | Google Cloud Console |
| Grants.gov | Not needed | Public API |
| USAspending | Not needed | Public API |
| All others | Not needed | Public web scraping |
