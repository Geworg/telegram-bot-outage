import os
import httpx
import logging
from typing import Optional, Dict, Any
# Configure logger for this module
log = logging.getLogger(__name__)

# Fetch the API key from environment variables once
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")

async def get_verified_address_from_yandex(address_text: str, lang: str = "ru_RU") -> Optional[Dict[str, Any]]:
    """
    Uses Yandex Geocoder API to get a canonical address and coordinates.
    The search is geographically biased towards Armenia for better accuracy.

    Args:
        address_text (str): The user-provided address string (e.g., "Ереван, Абовяна 5").
        lang (str): The language for the response ('ru_RU', 'en_US', etc.).

    Returns:
        A dictionary with verified address details if successful, otherwise None.
        Example structure:
        {
            'full_address': 'Армения, Ереван, улица Абовяна, 5',
            'country': 'Армения',
            'province': 'Ереван',
            'area': 'административный район Кентрон',
            'street': 'улица Абовяна',
            'house': '5',
            'latitude': 40.1825,
            'longitude': 44.5165
        }
    """
    if not YANDEX_API_KEY:
        log.warning("YANDEX_API_KEY is not set in environment variables. Geocoding is disabled.")
        return None
    # We bias the search by prepending "Armenia" and setting a search area (ll and spn).
    # ll (longitude, latitude) is the center of the search area.
    # spn (longitude span, latitude span) is the size of the search area.
    # An ll in Yerevan and a large spn will cover the country well.
    params = {
        "apikey": YANDEX_API_KEY,
        "format": "json",
        "geocode": f"Армения, {address_text}",
        "lang": lang,
        "ll": "44.5125,40.1772",  # Longitude, Latitude for Yerevan
        "spn": "8.0,8.0",         # A large search area covering all of Armenia
        "rspn": "1",              # Restrict search to the defined span
        "results": "1"            # We only need the most relevant result
    }

    url = "https://geocode-maps.yandex.ru/1.x/"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()  # Raises an exception for 4XX/5XX responses
            data = response.json()

            geo_objects = data.get("response", {}).get("GeoObjectCollection", {}).get("featureMember", [])
            if not geo_objects:
                log.warning(f"Yandex Geocoder found no results for address: '{address_text}'")
                return None

            # --- Parse the first and most relevant result ---
            first_geo_object = geo_objects[0].get("GeoObject", {})
            meta_data = first_geo_object.get("metaDataProperty", {}).get("GeocoderMetaData", {})
            
            # For reliability, we only accept results with good precision.
            precision = meta_data.get("precision")
            if precision not in ["exact", "number", "street", "near"]:
                 log.warning(f"Yandex Geocoder result for '{address_text}' has low precision: '{precision}'. Ignoring.")
                 return None

            components = meta_data.get("Address", {}).get("Components", [])
            point_str = first_geo_object.get("Point", {}).get("pos", "").split()
            lon, lat = (float(point_str[0]), float(point_str[1])) if len(point_str) == 2 else (None, None)
            address_parts = {comp['kind']: comp['name'] for comp in components}
            verified_data = {
                'full_address': meta_data.get("text"),
                'country': address_parts.get('country'),
                'province': address_parts.get('province'),
                'area': address_parts.get('area'),
                'locality': address_parts.get('locality'),
                'street': address_parts.get('street'),
                'house': address_parts.get('house'),
                'latitude': lat,
                'longitude': lon
            }
            log.info(f"Yandex API successfully geocoded '{address_text}' to '{verified_data['full_address']}'")
            return verified_data

        except httpx.HTTPStatusError as e:
            log.error(f"Yandex Geocoder API returned HTTP error {e.response.status_code} for address '{address_text}'. Response: {e.response.text}")
            return None
        except (httpx.RequestError, KeyError, IndexError, ValueError) as e:
            log.error(f"Failed to process Yandex Geocoder response for '{address_text}': {e}", exc_info=True)
            return None

# <3