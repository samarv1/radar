"""
Shared HQ location classification helpers.

Buckets a company's raw city/state/country into one of:
    'bay_area', 'new_york', 'other_usa', 'international', 'unknown'

Used by scrapers/yc.py, scrapers/techstars.py, and scrapers/enrich_location.py
so all sources classify consistently.
"""

BAY_AREA_CITIES = {
    "san francisco", "oakland", "san jose", "palo alto", "mountain view",
    "berkeley", "redwood city", "sunnyvale", "menlo park", "santa clara",
    "fremont", "san mateo", "cupertino", "emeryville", "south san francisco",
    "burlingame", "belmont", "san bruno", "daly city", "milpitas",
    "foster city", "los altos", "east palo alto", "san carlos", "alameda",
}

NYC_CITIES = {
    "new york", "new york city", "brooklyn", "manhattan", "queens",
    "bronx", "nyc", "staten island",
}

US_COUNTRY_NAMES = {"united states", "united states of america", "usa", "us"}

# Form D's stateOrCountryDescription field holds a US state name for domestic
# issuers, or a country name for foreign ones — same field, different meaning.
US_STATE_NAMES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new hampshire", "new jersey", "new mexico", "new york",
    "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode island", "south carolina", "south dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington",
    "west virginia", "wisconsin", "wyoming", "district of columbia",
    "puerto rico",
}


def classify_edgar_state_field(city: str | None, state_or_country: str | None) -> str:
    """
    Classify a location from EDGAR's stateOrCountryDescription field, which is
    a US state name for domestic issuers or a country name for foreign ones.
    """
    value_n = _clean(state_or_country)
    country = "united states" if value_n in US_STATE_NAMES else state_or_country
    return classify_location(city, state_or_country, country)


def _clean(value: str | None) -> str:
    return (value or "").strip().lower()


def classify_location(city: str | None, state: str | None, country: str | None) -> str:
    city_n = _clean(city)
    country_n = _clean(country)

    if city_n in BAY_AREA_CITIES:
        return "bay_area"
    if city_n in NYC_CITIES:
        return "new_york"

    if country_n in US_COUNTRY_NAMES:
        return "other_usa"
    if country_n:
        return "international"

    return "unknown"


def parse_yc_all_locations(all_locations: str | None) -> tuple[str | None, str | None, str | None]:
    """
    Parse YC's Algolia `all_locations` field, e.g. "San Francisco, CA, USA"
    or "London, United Kingdom". Returns (city, state, country).

    Only the first listed location is used when a company lists multiple,
    comma-separated by "; " or similar — YC's field is a single free-text
    string per company, so we just take it as one location.
    """
    if not all_locations or not all_locations.strip():
        return None, None, None

    # Field can list multiple semicolon-separated locations (e.g.
    # "San Francisco, CA, USA; Remote") — only the first is used.
    first_location = all_locations.split(";")[0]
    parts = [p.strip() for p in first_location.split(",") if p.strip()]
    if not parts:
        return None, None, None

    if len(parts) >= 3:
        # "City, ST, USA" (or similar three-part US-style address)
        return parts[0], parts[1], parts[-1]
    if len(parts) == 2:
        # "City, Country" — no state
        return parts[0], None, parts[1]
    # Just one part — treat as city, no state/country known
    return parts[0], None, None
