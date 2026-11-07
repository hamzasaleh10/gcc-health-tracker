"""Refresh the GCC Health Systems Monitor data.

Pulls World Bank World Development Indicators, WHO Global Health Observatory estimates
(obesity, healthy life expectancy, hypertension, workforce) and WHO Global Health Estimates
(causes of death and years of life lost) for the six GCC states plus benchmarks, validates them,
and writes the JSON files the site reads from /data.

Usage: python scripts/refresh.py [DATA_DIR]   (default: data)

Exits non-zero, writing nothing, if a source fails or the data looks wrong,
so a bad month never replaces good data.
"""
import datetime as dt
import json
import math
import os
import sys
import time

import requests

GCC = ["SAU", "ARE", "QAT", "KWT", "OMN", "BHR"]
BENCHMARKS = ["HIC", "WLD", "USA"]  # high income, world, United States
COUNTRIES = GCC + BENCHMARKS

# World Bank indicator code -> short name used by the site
INDICATORS = {
    "SP.DYN.LE00.IN": "life_exp",          # Life expectancy at birth (years)
    "SP.DYN.IMRT.IN": "infant_mort",       # Infant mortality (per 1,000 live births)
    "SH.DYN.NCOM.ZS": "ncd_mort_30_70",    # Mortality 30-70 from CVD, cancer, diabetes, CRD (%) - WHO
    "SH.STA.DIAB.ZS": "diabetes_prev",     # Diabetes prevalence, ages 20-79 (%) - IDF
    "SH.STA.TRAF.P5": "road_deaths",       # Road traffic deaths per 100,000 - WHO
    "SH.XPD.CHEX.GD.ZS": "che_gdp",        # Current health expenditure (% of GDP) - WHO GHED
    "SH.XPD.CHEX.PC.CD": "che_pc_usd",     # Current health expenditure per capita (US$)
    "SH.XPD.GHED.CH.ZS": "gov_share_che",  # Government share of current health expenditure (%)
    "SH.XPD.OOPC.CH.ZS": "oop_share_che",  # Out-of-pocket share of current health expenditure (%)
    "SH.MED.PHYS.ZS": "physicians_1k",     # Physicians per 1,000 people
    "SH.MED.NUMW.P3": "nurses_1k",         # Nurses and midwives per 1,000 people
    "SH.MED.BEDS.ZS": "beds_1k",           # Hospital beds per 1,000 people
    "SP.POP.TOTL": "population",           # Population, total
    "SP.POP.65UP.TO.ZS": "pop65_share",    # Population ages 65+ (% of total)
    "EN.ATM.PM25.MC.M3": "pm25",           # Mean annual exposure to PM2.5 (micrograms per cubic metre)
    "SH.STA.AIRP.P5": "airpol_deaths",     # Deaths from household and ambient air pollution, per 100,000, age-standardized - WHO
}
# Aggregates come back without an ISO3 code; map the World Bank ids.
AGGREGATE_IDS = {"XD": "HIC", "1W": "WLD"}

# WHO Global Health Observatory (OData API). Both sexes; the World Bank high-income
# group and the global estimate map to the codes the World Bank data uses.
GHO_URL = "https://ghoapi.azureedge.net/api/{code}?$filter=Dim1%20eq%20'SEX_BTSX'"
GHO_AREAS = {**{c: c for c in GCC + ["USA"]}, "WB_HI": "HIC", "GLOBAL": "WLD"}
WHO_AREAS = GCC + ["USA", "HIC", "WLD"]


def get_json(url, tries=4):
    for i in range(tries):
        try:
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            return r.json()
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(3 * (i + 1))


def fetch_world_bank():
    rows, last_updated = [], None
    year = dt.date.today().year
    for code, key in INDICATORS.items():
        url = (f"https://api.worldbank.org/v2/country/{';'.join(COUNTRIES)}/indicator/{code}"
               f"?format=json&date=2000:{year}&per_page=1000")
        meta, data = get_json(url)
        last_updated = meta.get("lastupdated") or last_updated
        n = 0
        for d in data or []:
            if d["value"] is None:
                continue
            iso = d["countryiso3code"] or AGGREGATE_IDS.get(d["country"]["id"], d["country"]["id"])
            if iso not in COUNTRIES:
                continue
            rows.append({"iso3": iso, "country": d["country"]["value"], "indicator": key,
                         "year": int(d["date"]), "value": round(float(d["value"]), 6)})
            n += 1
        print(f"  {code:<20} {key:<16} {n:>4} rows")
    return rows, last_updated


AGE_GROUPS = ["0004", "0509", "1014", "1519", "2024", "2529", "3034", "3539", "4044",
              "4549", "5054", "5559", "6064", "6569", "7074", "7579", "80UP"]
PROJ_YEARS = [2024, 2025, 2030, 2035, 2040, 2045, 2050]


def fetch_projections():
    """World Bank population estimates and projections (source 40): GCC population by
    five-year age group, both sexes, for the base year and projection years."""
    rows, by = [], {}
    codes = [f"SP.POP.{g}.{s}" for g in AGE_GROUPS for s in ("MA", "FE")]
    for i in range(0, len(codes), 17):
        url = (f"https://api.worldbank.org/v2/country/{';'.join(GCC)}/indicator/{';'.join(codes[i:i + 17])}"
               f"?source=40&format=json&date={PROJ_YEARS[0]}:{PROJ_YEARS[-1]}&per_page=5000")
        meta, data = get_json(url)
        for d in data or []:
            y = int(d["date"])
            if y not in PROJ_YEARS or d["value"] is None:
                continue
            g = d["indicator"]["id"].split(".")[2]
            k = (d["countryiso3code"], y, g)
            by[k] = by.get(k, 0) + float(d["value"])
    for (iso, y, g), v in sorted(by.items()):
        rows.append({"iso3": iso, "year": y, "age": g, "pop": round(v)})
    return rows


def fetch_gho(code):
    rows = []
    for d in get_json(GHO_URL.format(code=code))["value"]:
        iso = GHO_AREAS.get(d["SpatialDim"])
        if iso is None or d.get("NumericValue") is None or int(d["TimeDim"]) < 2000:
            continue
        rows.append({"iso3": iso, "year": int(d["TimeDim"]), "value": round(float(d["NumericValue"]), 2)})
    return sorted(rows, key=lambda r: (r["iso3"], r["year"]))


def fetch_obesity():
    """WHO adult obesity (BMI 30+, age-standardized, ages 18+)."""
    return fetch_gho("NCD_BMI_30A")


def fetch_nurse_midwife():
    """WHO National Health Workforce Accounts: nursing personnel and midwifery personnel (numbers), GCC only."""
    rows = []
    for code, key in (("HWF_0008", "nurses"), ("HWF_0009", "midwives")):
        url = f"https://ghoapi.azureedge.net/api/{code}?$filter=" + "%20or%20".join(f"SpatialDim%20eq%20'{c}'" for c in GCC)
        for d in get_json(url)["value"]:
            if d.get("NumericValue") is None or int(d["TimeDim"]) < 2010:
                continue
            rows.append({"iso3": d["SpatialDim"], "indicator": key, "year": int(d["TimeDim"]), "value": round(float(d["NumericValue"]))})
    return sorted(rows, key=lambda r: (r["iso3"], r["indicator"], r["year"]))


def fetch_hypertension():
    """WHO hypertension among adults 30-79 (age-standardized): prevalence, and the share of
    people with hypertension whose blood pressure is controlled."""
    rows = []
    for code, key in (("NCD_HYP_PREVALENCE_A", "hyp_prev"), ("NCD_HYP_CONTROL_A", "hyp_control")):
        rows += [{**r, "indicator": key} for r in fetch_gho(code)]
    return rows


# WHO Global Health Estimates (xMart API): deaths and years of life lost by cause.
GHE_URL = "https://xmart-api-public.who.int/DEX_CMS/{table}"
GHE_FIELDS = ("DIM_GHECAUSE_CODE,DIM_GHECAUSE_TITLE,FLAG_LEVEL,FLAG_RANKABLE,DIM_CAUSE_GROUP,"
              "VAL_YLL_COUNT_NUMERIC,VAL_YLL_RATE100K_NUMERIC,VAL_DTHS_COUNT_NUMERIC,VAL_DTHS_RATE100K_NUMERIC")
GHE_AREAS = {**{c: ("GHE_FULL", "DIM_COUNTRY_CODE", c) for c in GCC},
             "HIC": ("GHE_REGIONS", "DIM_REGION_CODE", "HIC"), "WLD": ("GHE_REGIONS", "DIM_REGION_CODE", "WRLD")}
GHE_BASE_YEAR = 2019  # last year before the pandemic


def ghe_latest_year():
    url = GHE_URL.format(table="GHE_FULL") + "?$apply=filter(DIM_COUNTRY_CODE%20eq%20'SAU')/groupby((DIM_YEAR_CODE))"
    return max(int(r["DIM_YEAR_CODE"]) for r in get_json(url)["value"])


def fetch_causes():
    """Leading causes of death and years of life lost, both sexes, all ages: the GCC states,
    the high-income group and the world, for the pre-pandemic year and the latest year.
    Keeps WHO's rankable causes (each death counted once) plus the broad groups (levels 1-2)."""
    latest = ghe_latest_year()
    rows = []
    for iso, (table, dim, code) in GHE_AREAS.items():
        for year in sorted({GHE_BASE_YEAR, latest}):
            flt = (f"{dim} eq '{code}' and DIM_YEAR_CODE eq {year} and DIM_SEX_CODE eq 'TOTAL' "
                   f"and DIM_AGEGROUP_CODE eq 'TOTAL'")
            url = GHE_URL.format(table=table) + "?" + requests.compat.urlencode({"$filter": flt, "$select": GHE_FIELDS})
            got = get_json(url)["value"]
            tot = next(r for r in got if int(r["DIM_GHECAUSE_CODE"]) == 0)
            yll0, dth0 = tot["VAL_YLL_COUNT_NUMERIC"], tot["VAL_DTHS_COUNT_NUMERIC"]
            for r in got:
                lvl, rank = int(r["FLAG_LEVEL"]), bool(r["FLAG_RANKABLE"])
                if not (lvl in (1, 2) or rank):
                    continue
                yll_pct = 100 * r["VAL_YLL_COUNT_NUMERIC"] / yll0
                if lvl > 2 and yll_pct < 0.1:
                    continue
                rows.append({"iso3": iso, "year": year, "code": int(r["DIM_GHECAUSE_CODE"]),
                             "cause": r["DIM_GHECAUSE_TITLE"], "level": lvl, "group": int(r["DIM_CAUSE_GROUP"]),
                             "rankable": rank, "yll_pct": round(yll_pct, 2),
                             "dth_pct": round(100 * r["VAL_DTHS_COUNT_NUMERIC"] / dth0, 2),
                             "yll_rate": round(r["VAL_YLL_RATE100K_NUMERIC"], 1),
                             "deaths": round(r["VAL_DTHS_COUNT_NUMERIC"]),
                             "dth_rate": round(r["VAL_DTHS_RATE100K_NUMERIC"], 2)})
    return sorted(rows, key=lambda r: (r["iso3"], r["year"], -r["yll_pct"])), latest


def fetch_le():
    """WHO life expectancy at birth, paired with HALE to give years in poor health."""
    return fetch_gho("WHOSIS_000001")


def fetch_hale():
    """WHO healthy life expectancy (HALE) at birth."""
    return fetch_gho("WHOSIS_000002")


def validate(wb, ob, hale=None, proj=None, le=None, nm=None, hyp=None, causes=None):
    problems = []
    if hyp is not None:
        for key in ("hyp_prev", "hyp_control"):
            for iso in WHO_AREAS:
                if not any(r["iso3"] == iso and r["indicator"] == key for r in hyp):
                    problems.append(f"WHO {key}: no rows for {iso}")
    if causes is not None:
        for iso in GHE_AREAS:
            for y in {r["year"] for r in causes}:
                n = sum(1 for r in causes if r["iso3"] == iso and r["year"] == y and r["rankable"])
                if n < 40:
                    problems.append(f"WHO causes of death: only {n} causes for {iso} {y}")
                grp = sum(r["yll_pct"] for r in causes if r["iso3"] == iso and r["year"] == y and r["level"] == 1)
                if abs(grp - 100) > 1:
                    problems.append(f"WHO causes of death: groups sum to {grp:.1f}% for {iso} {y}")
    if len(wb) < 2300:
        problems.append(f"World Bank: only {len(wb)} rows (expected 2,300+)")
    for iso in COUNTRIES:
        if not any(r["iso3"] == iso for r in wb):
            problems.append(f"World Bank: no rows for {iso}")
    for key in INDICATORS.values():
        if not any(r["indicator"] == key for r in wb):
            problems.append(f"World Bank: no rows for {key}")
    if len(ob) < 180:
        problems.append(f"Obesity: only {len(ob)} rows (expected 180+)")
    for iso in WHO_AREAS:
        if not any(r["iso3"] == iso for r in ob):
            problems.append(f"Obesity: no rows for {iso}")
    if le is not None:
        for iso in WHO_AREAS:
            if not any(r["iso3"] == iso for r in le):
                problems.append(f"WHO life expectancy: no rows for {iso}")
    if nm is not None:
        for iso in GCC:
            if not any(r["iso3"] == iso and r["indicator"] == "nurses" for r in nm):
                problems.append(f"WHO nursing personnel: no rows for {iso}")
    if proj is not None:
        want = len(GCC) * len(AGE_GROUPS) * len(PROJ_YEARS)
        if len(proj) != want:
            problems.append(f"Population projections: {len(proj)} rows (expected {want})")
    if hale is not None:
        if len(hale) < 120:
            problems.append(f"Healthy life expectancy: only {len(hale)} rows (expected 120+)")
        for iso in WHO_AREAS:
            if not any(r["iso3"] == iso for r in hale):
                problems.append(f"Healthy life expectancy: no rows for {iso}")
    for r in wb + ob + (hale or []):
        if not math.isfinite(r["value"]):
            problems.append(f"Non-numeric value: {r}")
            break
    return problems


def main(out_dir):
    print("World Bank WDI")
    wb, wb_updated = fetch_world_bank()
    print("WHO obesity (Global Health Observatory)")
    ob = fetch_obesity()
    print(f"  {len(ob)} rows, latest year {max(r['year'] for r in ob)}")
    print("WHO healthy life expectancy (Global Health Observatory)")
    hale = fetch_hale()
    print(f"  {len(hale)} rows, latest year {max(r['year'] for r in hale)}")
    print("WHO life expectancy (Global Health Observatory)")
    le = fetch_le()
    print(f"  {len(le)} rows, latest year {max(r['year'] for r in le)}")

    print("WHO nursing and midwifery personnel")
    nm = fetch_nurse_midwife()
    print(f"  {len(nm)} rows")
    print("World Bank population projections")
    proj = fetch_projections()
    print(f"  {len(proj)} rows")

    print("WHO hypertension (Global Health Observatory)")
    hyp = fetch_hypertension()
    print(f"  {len(hyp)} rows")
    print("WHO Global Health Estimates: causes of death and years of life lost")
    causes, ghe_year = fetch_causes()
    print(f"  {len(causes)} rows, years {GHE_BASE_YEAR} and {ghe_year}")

    problems = validate(wb, ob, hale, proj, le, nm, hyp, causes)
    if problems:
        print("Validation failed; no files written:\n  " + "\n  ".join(problems))
        sys.exit(1)

    os.makedirs(out_dir, exist_ok=True)
    dump = lambda obj, name: json.dump(obj, open(os.path.join(out_dir, name), "w"), separators=(",", ":"))
    dump(wb, "gcc_worldbank.json")
    dump(ob, "gcc_obesity_who.json")
    dump(hale, "gcc_hale_who.json")
    dump(le, "gcc_le_who.json")
    dump(nm, "gcc_nurse_midwife_who.json")
    dump(proj, "gcc_population_projections.json")
    dump(hyp, "gcc_hypertension_who.json")
    dump(causes, "gcc_causes_who.json")
    dump({"refreshed_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
          "worldbank_last_updated": wb_updated,
          "rows": {"worldbank": len(wb), "obesity": len(ob), "hale": len(hale), "le_who": len(le), "nurse_midwife": len(nm), "projections": len(proj), "hypertension": len(hyp), "causes": len(causes)}}, "meta.json")
    print(f"Wrote {len(wb)} World Bank rows and {len(ob)} obesity rows to {out_dir}/")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data")
