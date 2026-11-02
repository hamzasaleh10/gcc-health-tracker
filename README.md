# GCC Health System Tracker

**Live site: [hamzasaleh10.github.io/gcc-health-tracker](https://hamzasaleh10.github.io/gcc-health-tracker/)** · [العربية](https://hamzasaleh10.github.io/gcc-health-tracker/?lang=ar)

A bilingual (English/Arabic) dashboard that benchmarks the six Gulf Cooperation Council health systems (Saudi Arabia, the UAE, Qatar, Kuwait, Oman and Bahrain) against high-income countries and the world. It covers health outcomes, chronic disease risk, financing and workforce, and sets Saudi Vision 2030 official figures beside international estimates. The data refreshes automatically every month.

![The tracker in English](assets/screenshot-en.png)

## What it shows

| Section | Question it answers | Key finding (latest data) |
| --- | --- | --- |
| Outcomes | Are Gulf states on track for the 2030 goal on premature chronic-disease deaths (UN SDG 3.4)? | Qatar, Kuwait and Oman are on track; Saudi Arabia, the UAE and Bahrain are off track. |
| Chronic disease risk | How large is the obesity and diabetes burden? | Adult obesity averages 36.6% across the GCC against 16.2% worldwide; diabetes 22.2% against 10.8%. |
| Financing | Who pays for health care, and how much? | GCC states spend 2.5–5.7% of GDP on health against 12.5% in high-income countries; governments fund 59–89%. |
| Workforce and capacity | Are there enough clinicians and beds? | Physician supply is near high-income levels in several states; nurses and hospital beds lag well behind. |
| Saudi Vision 2030 | How do official KPIs compare with international estimates? | Official road traffic deaths were 13.1 per 100,000 in 2023; WHO's modelled estimate for 2019 was 35.9. |

An [executive summary](https://hamzasaleh10.github.io/gcc-health-tracker/summary.html) ([العربية](https://hamzasaleh10.github.io/gcc-health-tracker/summary.html?lang=ar)) sets out the key findings, eight metrics for strategic leadership and six strategic insights.

Pick any focus country to update every section. Views can be shared by link: `?lang=ar&focus=QAT` opens the Arabic view focused on Qatar.

## How it works

```
World Bank API ─┐
                ├─> scripts/refresh.py ──> data/*.json ──> index.html (D3.js) ──> GitHub Pages
Our World in   ─┘    (fetch, validate)       (committed)     (calculations
Data (WHO)                                                    run in browser)
        ▲
        └── GitHub Actions, 2nd of every month (.github/workflows/refresh-data.yml)
```

- **Pipeline.** `scripts/refresh.py` pulls 14 World Bank indicators and WHO adult-obesity estimates for the six GCC states plus benchmarks, validates row counts, country and indicator coverage and value types, and only then writes the JSON files. A failed source or a suspicious result stops the run without touching the published data.
- **Automation.** A scheduled GitHub Actions workflow runs the pipeline monthly and commits the data only when it changed. GitHub Pages republishes the site on each commit.
- **Front end.** A single static page with D3.js charts. Derived metrics (latest values, GCC averages, SDG 3.4 projections, spending tables) are computed in the browser from the raw data, so every figure traces back to a source row.
- **Bilingual.** Full English and Arabic versions with right-to-left layout, translated labels, tables and chart annotations.

Run it locally:

```bash
pip install -r requirements.txt
python scripts/refresh.py data      # refresh the data
python -m http.server 8000          # then open http://localhost:8000
```

## Data sources

| Data | Source |
| --- | --- |
| Life expectancy, infant mortality, population, age structure | [World Bank World Development Indicators](https://data.worldbank.org/indicator) (UN Population Division) |
| Premature chronic-disease mortality (ages 30–70), road traffic deaths | World Bank WDI, from WHO Global Health Estimates |
| Diabetes prevalence (ages 20–79) | World Bank WDI, from the International Diabetes Federation |
| Health spending, government and out-of-pocket shares | World Bank WDI, from the WHO Global Health Expenditure Database |
| Physicians, nurses and midwives, hospital beds | World Bank WDI, from WHO and OECD |
| Adult obesity (age-standardized) | [WHO Global Health Observatory via Our World in Data](https://ourworldindata.org/grapher/obesity-prevalence-adults-who-gho) |
| Saudi Vision 2030 official figures | [Health Sector Transformation Program 2023 Achievements Report](https://vision2030.gov.sa/media/c3ld5ltz/hstp-annual-report-2023-en.pdf); [Ministry of Health release on the 2025 report](https://www.moh.gov.sa/en/Ministry/MediaCenter/News/Pages/news-2026-06-20-001.aspx) (entered by hand in `data/saudi_vision2030.json`) |

## Methods and limitations

- Each figure is the latest year a country reported, so years differ across countries and indicators.
- SDG 3.4 goal = each country's 2015 rate of premature chronic-disease mortality cut by one third. The projection extends the average yearly change from 2015 to the latest year (2021) in a straight line; it shows direction, not a forecast. The 2021 figures may still carry pandemic-era deaths.
- GCC averages are simple means of the six states, not population-weighted.
- Figures cover all residents, nationals and expatriates combined.
- Official national figures and WHO modelled estimates use different methods and are not directly comparable; the dashboard shows both deliberately.

## About

Built by Hamza Saleh, MPH, as a portfolio project on public data. It is not affiliated with any government or organization named here.

![The tracker in Arabic](assets/screenshot-ar.png)
