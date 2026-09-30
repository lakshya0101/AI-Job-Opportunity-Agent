# AI Job Opportunity Agent 🚀

A production-ready automated job opportunity intelligence agent that collects, normalizes, deduplicates, detects updates, scores, filters, and delivers structured daily job reports via Resend with professional HTML emails and multi-sheet Excel attachments.

---

## 🏗️ System Architecture

```text
               ┌──────────────────────────────┐
               │    config/preferences.yaml   │
               └──────────────┬───────────────┘
                              │
                      [ 1. COLLECTORS ]
         Official Career Boards (Greenhouse, Lever)
             [Isolated per-source fault tolerance]
                              │
                      [ 2. NORMALIZE ]
           Standardized Data Model (src/models/job.py)
                              │
                     [ 3. DEDUPLICATE ]
          Stable key: (company | title | location)
                              │
                  [ 4. CHANGE DETECTION ]
          SQLite JobStore (is_new vs is_updated)
                 [Read-only query phase]
                              │
                   [ 5. FRESHNESS & URGENCY ]
      Posting age classification (NEW_TODAY, FRESH, etc.)
                   Deadline urgency detection
                              │
                     [ 6. MATCH ENGINE ]
       Role (30) + Skill (30) + Location (20) + Exp (10) + Fresh (10)
                              │
                      [ 7. FILTERING ]
     Location, experience, role, skill, and score thresholds
                              │
                    [ 8. REPORT BUILDER ]
               Structured DailyReport Object
               ┌──────────────┴──────────────┐
               ▼                             ▼
       [ 9. HTML EMAIL ]             [ 10. EXCEL (.XLSX) ]
   Responsive Multi-Section       Multi-Sheet Styled Workbook
   HTML Template (templates.py)   Hyperlinks & Summary (excel_report.py)
               └──────────────┬──────────────┘
                              ▼
                   [ 11. RESEND DISPATCH ]
              HTML Body + Excel Attachment (.xlsx)
                              │
                   [ 12. STATE PERSISTENCE ]
             Jobs persisted to SQLite database ONLY
                after verified email dispatch!
```

---

## 🎯 Candidate Profile & Matching Strategy

- **Candidate Degree:** B.Tech Computer Science & Engineering (Specialization: Data Science)
- **Experience Level:** Fresher / Entry-Level / Trainee (0–2 Years Experience)
- **Preferred Locations:**
  1. Noida / Greater Noida
  2. New Delhi / Delhi
  3. Gurugram / Gurgaon
  4. Bangalore / Bengaluru
  5. Jaipur
  6. Pune
  7. Mumbai / Navi Mumbai
  8. Remote India / India Remote
- **Target Roles:**
  - AI/ML Engineer, Applied AI Engineer, Machine Learning Engineer
  - GenAI Engineer, LLM Engineer, RAG Engineer, Agentic AI Engineer
  - Python Backend Engineer, FastAPI Developer, Python SDE
  - Data Scientist, Data Analyst, BI Analyst, Business Analyst
- **Scoring Engine Factors (100 Total Points):**
  - **Role Match:** 30 pts (Target role title compatibility)
  - **Skill Match:** 30 pts (Core Python, ML/GenAI, SQL, FastAPI, LangChain, RAG overlap)
  - **Location Match:** 20 pts (Priority tiers & Remote India)
  - **Experience Match:** 10 pts (Fresher compatibility, senior role filtering)
  - **Freshness:** 10 pts (New / urgent opportunities)

---

## 📡 Collector Source Matrix

| Source | Status | Method | Freshness Reliability | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Official Careers (Greenhouse)** | **IMPLEMENTED** | Public REST API (`boards-api.greenhouse.io`) | **High** (`first_published` preferred over `updated_at`) | 17 verified live boards collected concurrently with fault isolation |
| **Official Careers (Lever)** | **IMPLEMENTED** | Public REST API (`api.lever.co/v0/postings`) | **High** (`createdAt` ISO 8601 timestamp) | 12 verified live boards collected concurrently with fault isolation |
| **Unstop** | **IMPLEMENTED** | Public REST Search API (`unstop.com/api/public/opportunity/search-result`) | **High** (`approved_date` / `updated_at` + explicit application deadlines) | Fresh jobs & technical internships with verified stipend/salary metadata |
| **YC Jobs** | **IMPLEMENTED** | Public Firebase API (`hacker-news.firebaseio.com/v0/jobstories`) | **High** (HN story timestamp converted to UTC ISO) | Active Y Combinator startup hiring posts with title/company parsing |
| **Wellfound (AngelList)** | **NOT IMPLEMENTED** | GraphQL / Web | N/A | Requires authenticated user sessions and protected by Cloudflare Turnstile |
| **Internshala** | **NOT IMPLEMENTED** | Web Scraper | N/A | Blocks non-browser HTTP clients with Cloudflare 403 anti-bot challenges |
| **Cutshort** | **NOT IMPLEMENTED** | Private REST API | N/A | Requires private App ID, device headers, and authenticated tokens |
| **Indeed** | **NOT IMPLEMENTED** | Web / RSS | N/A | Enforces Cloudflare anti-scraping shields and IP rate limiting |
| **Naukri** | **NOT IMPLEMENTED** | Private API | N/A | Requires proprietary `appId` signature and authenticated session cookies |
| **Foundit (Monster)** | **NOT IMPLEMENTED** | Web / Private API | N/A | Requires authenticated headers and active anti-bot bypass |
| **LinkedIn** | **NOT IMPLEMENTED** | Web / API | N/A | Strict authwall; public endpoints redirect to mandatory login |

*Note: Unimplemented sources are documented above and safely tracked as `NOT_IMPLEMENTED` in source health reporting. No credentials, cookies, or aggressive scrapers are used.*

---

## 🔒 Reliability & Safety Guarantees

1. **Email-Guarded Persistence:** Newly discovered jobs are persisted to SQLite (`jobs.db`) **strictly after** email delivery succeeds. If Resend fails, jobs remain flagged as new for the next run.
2. **Concurrent Fault-Tolerant Collection:** Official career boards are polled concurrently via `ThreadPoolExecutor` with a strict 10s per-board timeout. A single slow or broken board never halts or fails the overall collection.
3. **All-Collectors-Failed Circuit Breaker:** If 100% of active collectors fail, the agent halts with exit code `1` rather than dispatching a misleading "0 jobs found" email.
4. **Calibrated Freshness Strategy:**
   - `NEW_TODAY` / `FRESH` (0–3 days): Always reportable if score >= 55.
   - `ACTIVE` (4–7 days): Requires match score >= 70.
   - `OLDER_ACTIVE` (8–14 days): Requires match score >= 80.
   - `OLDER` (>14 days): Requires match score >= 90.
   - `EXPIRED`: Always discarded.
5. **No Unhashable Set Bugs:** All report categorizations use stable string identities (`_job_identity`), preventing mutable dataclass hash errors.
6. **No URL/Contact Fabrication:** Direct application URLs are extracted directly from official ATS APIs or fall back to official company careers boards.

---

## ⚙️ Environment Variables

| Variable | Required | Description | Default |
| :--- | :--- | :--- | :--- |
| `RESEND_API_KEY` | **Yes** | Resend Bearer API Key (`re_...`) | *None* |
| `JOB_REPORT_EMAIL` | Optional | Destination email address | `lakshyadogra05@gmail.com` |
| `EMAIL_SENDER` | Optional | Verified sender email | `onboarding@resend.dev` |

---

## 🚀 Quickstart & Usage

### 1. Installation
```bash
git clone https://github.com/lakshya0101/AI-Job-Opportunity-Agent.git
cd AI-Job-Opportunity-Agent
pip install -r requirements.txt
```

### 2. Run Test Suite
```bash
python -m pytest -q
```

### 3. Run Dry Run (Recommended for previewing results)
Runs collection, matching, report generation, and Excel export **without sending email or modifying SQLite**:
```bash
python -m src.main --dry-run
```

### 4. Run Live Production Dispatch
Executes complete pipeline, sends HTML email with Excel attachment via Resend, and records persistent state:
```bash
export RESEND_API_KEY="re_your_api_key_here"
python -m src.main
```

---

---

## 🔍 Diagnostic & Data Baseline Notes

During live collector dry-runs against the initial 6 official career boards (565 postings collected / 564 deduplicated):
- **Role Fit:** ~91.7% of company board jobs are non-target roles (Sales, Legal, Operations, Consulting).
- **Seniority:** ~70.9% are explicitly Senior/Lead/Principal (0.0 exp score) or require 3+ years experience.
- **Freshness & Location:** Target entry-level roles on Lever boards were posted >14–70 days ago (`OLDER` / `OLDER_ACTIVE`).
- The pipeline's scoring engine strictly prevents low-relevance and stale postings from polluting the daily report. Expand configured boards in `config/preferences.yaml` or collector sources to scale daily candidate volume.