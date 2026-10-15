"""Read-only queries against Tesfa AI's own database (the `tesfa` schema)."""
from django.db import connections

# Each conflict counted once per country involved (a country fighting itself counts once).
SIDES_SQL = """
    SELECT id, country_a AS country FROM tesfa.conflicts_full
    UNION
    SELECT id, country_b AS country FROM tesfa.conflicts_full
"""

COUNTRY_STATS_SQL = f"""
    SELECT
        c.id,
        c.name,
        COUNT(f.id) AS conflict_count,
        COALESCE(AVG(f.predicted_risk_score), 0) AS avg_risk_score,
        COALESCE(SUM(f.civilian_deaths), 0) AS total_civilian_deaths,
        COALESCE(SUM(f.refugees_millions), 0) AS total_refugees_millions,
        COALESCE(SUM(f.economic_loss_usd_billions), 0) AS total_economic_loss_usd_billions
    FROM tesfa.countries c
    LEFT JOIN ({SIDES_SQL}) s ON s.country = c.name
    LEFT JOIN tesfa.conflicts_full f ON f.id = s.id
"""

CONFLICT_FIELDS = """
    id, country_a, country_b, conflict_type, year, duration_days, civilian_deaths,
    military_deaths_a, military_deaths_b, economic_loss_usd_billions, refugees_millions,
    outcome, latitude, longitude, predicted_risk_score, risk_category,
    predicted_postwar_consequence, evidence_reference_links
"""


def _fetch(sql, params=None):
    with connections['tesfa'].cursor() as cursor:
        cursor.execute(sql, params or [])
        columns = [col.name for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _round(rows, *fields):
    for row in rows:
        for field in fields:
            row[field] = round(float(row[field]), 2)
    return rows


def list_countries():
    rows = _fetch(COUNTRY_STATS_SQL + " GROUP BY c.id, c.name ORDER BY c.name")
    return _round(rows, "avg_risk_score", "total_refugees_millions", "total_economic_loss_usd_billions")


def get_country(country_id, limit=50):
    rows = _fetch(COUNTRY_STATS_SQL + " WHERE c.id = %s GROUP BY c.id, c.name", [country_id])
    if not rows:
        return None
    country = _round(rows, "avg_risk_score", "total_refugees_millions", "total_economic_loss_usd_billions")[0]
    country["conflicts"] = _fetch(
        f"SELECT {CONFLICT_FIELDS} FROM tesfa.conflicts_full"
        " WHERE country_a = %s OR country_b = %s"
        " ORDER BY predicted_risk_score DESC NULLS LAST LIMIT %s",
        [country["name"], country["name"], limit],
    )
    return country


def _chart(title, rows, label_field, value_field, chart_type="bar"):
    return {
        "chart_type": chart_type,
        "title": title,
        "labels": [row[label_field] for row in rows],
        "values": [round(float(row[value_field] or 0), 2) for row in rows],
    }


def get_graphs(country=None):
    """Chart-ready data (labels + values) for the dashboard, optionally for one country."""
    where, params = "", []
    if country:
        where, params = " WHERE country_a ILIKE %s OR country_b ILIKE %s", [country, country]
    conflicts = f"(SELECT * FROM tesfa.conflicts_full{where}) f"

    summary = _fetch(f"""
        SELECT COUNT(*) AS conflict_count,
               COALESCE(AVG(predicted_risk_score), 0) AS avg_risk_score,
               COALESCE(SUM(civilian_deaths), 0) AS total_civilian_deaths,
               COALESCE(SUM(refugees_millions), 0) AS total_refugees_millions,
               COALESCE(SUM(economic_loss_usd_billions), 0) AS total_economic_loss_usd_billions
        FROM {conflicts}
    """, params)
    summary = _round(summary, "avg_risk_score", "total_refugees_millions", "total_economic_loss_usd_billions")[0]

    by_country = _fetch(f"""
        SELECT s.country, COUNT(*) AS conflict_count, AVG(f.predicted_risk_score) AS avg_risk_score,
               SUM(f.civilian_deaths) AS civilian_deaths, SUM(f.refugees_millions) AS refugees_millions,
               SUM(f.economic_loss_usd_billions) AS economic_loss
        FROM {conflicts} JOIN ({SIDES_SQL}) s ON s.id = f.id
        GROUP BY s.country ORDER BY conflict_count DESC
    """, params)
    per_year = _fetch(f"SELECT year, COUNT(*) AS count FROM {conflicts} GROUP BY year ORDER BY year", params)
    risk_categories = _fetch(f"""
        SELECT risk_category, COUNT(*) AS count FROM {conflicts}
        GROUP BY risk_category ORDER BY MIN(predicted_risk_score)
    """, params)
    conflict_types = _fetch(f"""
        SELECT conflict_type, COUNT(*) AS count FROM {conflicts}
        GROUP BY conflict_type ORDER BY count DESC
    """, params)
    outcomes = _fetch(f"""
        SELECT outcome, COUNT(*) AS count FROM {conflicts}
        GROUP BY outcome ORDER BY count DESC
    """, params)
    top_risk = _fetch(f"""
        SELECT country_a || ' vs ' || country_b || ' (' || year || ')' AS label, predicted_risk_score
        FROM {conflicts} ORDER BY predicted_risk_score DESC NULLS LAST LIMIT 10
    """, params)
    map_points = _fetch(f"""
        SELECT id, country_a, country_b, year, latitude, longitude, predicted_risk_score, risk_category
        FROM {conflicts} WHERE latitude IS NOT NULL AND longitude IS NOT NULL
        ORDER BY predicted_risk_score DESC NULLS LAST LIMIT 100
    """, params)

    return {
        "country": country,
        "summary": summary,
        "charts": {
            "conflicts_by_country": _chart("Conflicts by country", by_country, "country", "conflict_count"),
            "risk_by_country": _chart("Average predicted risk score by country", by_country, "country", "avg_risk_score"),
            "civilian_deaths_by_country": _chart("Civilian deaths by country", by_country, "country", "civilian_deaths"),
            "refugees_by_country": _chart("Refugees (millions) by country", by_country, "country", "refugees_millions"),
            "economic_loss_by_country": _chart("Economic loss (USD billions) by country", by_country, "country", "economic_loss"),
            "conflicts_per_year": _chart("Conflicts per year", per_year, "year", "count", "line"),
            "risk_categories": _chart("Conflicts by risk category", risk_categories, "risk_category", "count", "pie"),
            "conflict_types": _chart("Conflicts by type", conflict_types, "conflict_type", "count", "pie"),
            "outcomes": _chart("Conflict outcomes", outcomes, "outcome", "count", "pie"),
            "top_risk_conflicts": _chart("Highest predicted risk conflicts", top_risk, "label", "predicted_risk_score"),
        },
        "map_points": map_points,
    }
