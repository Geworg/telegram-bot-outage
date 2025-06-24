import os
import httpx
import logging
from typing import Optional, Dict, Any

log = logging.getLogger(__name__)

async def get_verified_address_from_yandex(address_text: str, lang: str = "ru_RU") -> Optional[Dict[str, Any]]:
    YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
    if not YANDEX_API_KEY:
        log.warning("YANDEX_API_KEY is not set. Geocoding is disabled.")
        return None

    params = {
        "apikey": YANDEX_API_KEY,
        "format": "json",
        "geocode": f"Армения, {address_text}",
        "lang": lang,
        "ll": "44.5125,40.1772",
        "spn": "8.0,8.0",
        "rspn": "1",
        "results": "1"
    }
    url = "https://geocode-maps.yandex.ru/1.x/"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            geo_objects = data.get("response", {}).get("GeoObjectCollection", {}).get("featureMember", [])
            if not geo_objects:
                log.warning(f"Yandex Geocoder found no results for address: '{address_text}'")
                return None

            first_geo_object = geo_objects[0].get("GeoObject", {})
            meta_data = first_geo_object.get("metaDataProperty", {}).get("GeocoderMetaData", {})
            
            precision = meta_data.get("precision")
            if precision not in ["exact", "number", "near", "street"]:
                 log.warning(f"Yandex result for '{address_text}' has low precision: '{precision}'. Ignoring.")
                 return None

            components = meta_data.get("Address", {}).get("Components", [])
            point_str = first_geo_object.get("Point", {}).get("pos", "").split()
            
            lon, lat = (float(point_str[0]), float(point_str[1])) if len(point_str) == 2 else (None, None)
            if lat is None:
                log.warning(f"Could not extract coordinates for '{address_text}'")
                return None

            address_parts = {comp.get('kind'): comp.get('name') for comp in components}

            street_name = address_parts.get('street', '')
            house_number = address_parts.get('house', '')
            full_street = f"{street_name}, {house_number}" if street_name and house_number else street_name

            verified_data = {
                'full_address': meta_data.get("text", address_text),
                'region': address_parts.get('province') or address_parts.get('area'),
                'street': full_street,
                'latitude': lat,
                'longitude': lon
            }
            log.info(f"Yandex API successfully geocoded '{address_text}' to '{verified_data['full_address']}'")
            return verified_data

        except httpx.HTTPStatusError as e:
            log.error(f"Yandex Geocoder API returned HTTP error {e.response.status_code}. Response: {e.response.text}")
            return None
        except Exception as e:
            log.error(f"Failed to process Yandex Geocoder response for '{address_text}': {e}", exc_info=True)
            return None
