"""Refresh the GCC Health System Tracker data.

Pulls World Bank World Development Indicators and WHO adult-obesity and healthy
life expectancy estimates (WHO Global Health Observatory API) for the six GCC states plus benchmarks, validates them,
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


def fetch_hale():
    """WHO healthy life expectancy (HALE) at birth."""
    return fetch_gho("WHOSIS_000002")


def validate(wb, ob, hale=None):
    problems = []
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

    problems = validate(wb, ob, hale)
    if problems:
        print("Validation failed; no files written:\n  " + "\n  ".join(problems))
        sys.exit(1)

    os.makedirs(out_dir, exist_ok=True)
    dump = lambda obj, name: json.dump(obj, open(os.path.join(out_dir, name), "w"), separators=(",", ":"))
    dump(wb, "gcc_worldbank.json")
    dump(ob, "gcc_obesity_who.json")
    dump(hale, "gcc_hale_who.json")
    dump({"refreshed_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
          "worldbank_last_updated": wb_updated,
          "rows": {"worldbank": len(wb), "obesity": len(ob), "hale": len(hale)}}, "meta.json")
    print(f"Wrote {len(wb)} World Bank rows and {len(ob)} obesity rows to {out_dir}/")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data")
