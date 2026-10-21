import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class TesfaAIError(Exception):
    def __init__(self, message, status_code=502):
        super().__init__(message)
        self.status_code = status_code


def query_tesfa(query, region=None, conflict_type=None):
    """Send a query to Tesfa AI's POST /api/query and return a normalised dict.

    Tesfa AI answers either with plain text (simple answers) or with JSON that also
    carries metrics, top_conflicts and a chart spec (when the user asks for details).
    """
    url = settings.TESFA_AI_URL.rstrip('/') + '/api/query'
    payload = {"query": query, "region": region, "conflict_type": conflict_type}
    headers = {"X-API-Key": settings.TESFA_AI_API_KEY} if settings.TESFA_AI_API_KEY else {}
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=settings.TESFA_AI_TIMEOUT)
    except requests.Timeout:
        raise TesfaAIError("Tesfa AI took too long to respond.", 504)
    except requests.RequestException:
        raise TesfaAIError("Could not reach Tesfa AI.", 503)

    if response.status_code != 200:
        logger.warning("Tesfa AI returned %s: %s", response.status_code, response.text[:500])
        try:
            detail = response.json().get("detail", "Tesfa AI returned an error.")
        except ValueError:
            detail = f"Tesfa AI returned an error (HTTP {response.status_code})."
        status_code = response.status_code if response.status_code in (422, 503, 504) else 502
        raise TesfaAIError(detail, status_code)

    if 'application/json' not in response.headers.get('Content-Type', ''):
        return {"analysis_text": response.text.strip(), "metrics": None, "top_conflicts": None, "chart": None, "countries": []}

    result = response.json().get("result", {})
    top_conflicts = result.get("top_conflicts")
    return {
        "analysis_text": result.get("analysis_text", ""),
        "metrics": result.get("metrics"),
        "top_conflicts": top_conflicts,
        "chart": result.get("chart"),
        "countries": extract_countries(top_conflicts),
    }


def extract_countries(top_conflicts):
    countries = []
    for conflict in top_conflicts or []:
        for key in ("country_a", "country_b"):
            country = conflict.get(key)
            if country and country not in countries:
                countries.append(country)
    return countries
