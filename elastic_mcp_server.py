#!/usr/bin/env python3

"""
Copyright Elasticsearch B.V. and contributors
SPDX-License-Identifier: Apache-2.0
"""

import os
import json
import re
import logging
from typing import Dict, Any, Optional
import requests
from elasticsearch import Elasticsearch
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

ELASTIC_ENDPOINT = os.getenv("ELASTIC_ENDPOINT")
if not ELASTIC_ENDPOINT:
    raise ValueError("ELASTIC_ENDPOINT environment variable must be set")

ELASTIC_API_KEY = os.getenv("ELASTIC_API_KEY")
if not ELASTIC_API_KEY:
    raise ValueError("ELASTIC_API_KEY environment variable must be set")

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
if not GOOGLE_MAPS_API_KEY:
    raise ValueError("GOOGLE_MAPS_API_KEY environment variable must be set")

SEARCH_TEMPLATE_ID = os.environ.get("PROPERTIES_SEARCH_TEMPLATE")
SEARCH_INDEX = os.getenv("ES_INDEX", "properties")

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

mcp = FastMCP("elasticsearch-mcp-server")

es = Elasticsearch(
    hosts=[ELASTIC_ENDPOINT],
    api_key=ELASTIC_API_KEY,
)


def get_template_script(template_id: str) -> Optional[str]:

    # Get template from Elasticsearch using the client's get_script API
    try:
        response = es.get_script(id=template_id)
        source = response["script"]["source"]
        source = "".join(c for c in source if c.isprintable() or c in "\n\r\t")
        return source
    except Exception as e:
        logger.error(f"Failed to get template: {str(e)}")
        return None


@mcp.tool("get_properties_template_params")
async def get_properties_template_params() -> Dict[str, Any]:
    """Get the required parameters for the properties search template."""
    template_id = SEARCH_TEMPLATE_ID
    source = get_template_script(template_id)
    if not source:
        return {"type": "text", "text": "Error getting template script."}

    # Find parameters in template
    param_matches = re.findall(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", source)
    parameters = list(set(param_matches))
    parameters_list = ", ".join(parameters)
    logger.info(f"Found parameters for template {template_id}: {parameters}")

    params_content = f"""Required parameters for properties search template: {parameters_list}

    Parameter descriptions:
      - bathrooms: Number of bathrooms
      - tax: Real estate tax amount
      - maintenance: Maintenance fee amount
      - square_footage_min: Minimum property square footage. If only a max square footage is provided, set this to 0. otherwise, set this to the minimum square footage specified by the user.
      - square_footage_max: Maximum property square footage
      - home_price_min: Minimum home price.  If only a max home price is provided, set this to 0. otherwise, set this to the minimum home price specified by the user.
      - home_price_max: Maximum home price
      - property_features: Home features such as AC, pool, updated kitchens, etc should be listed as a single string For example features such as pool and updated kitchen should be formated as pool updated kitchen
      """

    params_context = {
        "content": {"type": "text", "text": params_content},
        "data": {"type": "text", "text": parameters_list},
    }

    return {"type": "object", "parameters": params_context}


@mcp.tool("geocode_location")
async def geocode_location(location: str) -> Dict[str, Any]:
    """Geocode a location string into a geo_point."""

    try:
        base_url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {
            "address": location,
            "region": "us",
            "key": GOOGLE_MAPS_API_KEY,
        }

        logger.info(f"Attempting to geocode: '{location}'")
        response = requests.get(base_url, params=params)
        data = response.json()

        logger.info(f"Geocoding status: {data.get('status')}")

        if data.get("status") != "OK":
            logger.error(
                f"Google API error: {data.get('status')} - {data.get('error_message', 'No detailed error message')}"
            )
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Geocoding failed: {data.get('status', 'Unknown error')} for location '{location}'",
                    }
                ]
            }

        result = data.get("results", [{}])[0]

        # If no results, try appending "Florida"
        if not result:
            logger.info("No results found, trying variations...")
            fallback_location = f"{location}, Florida"
            logger.info(f"Trying fallback: '{fallback_location}'")
            params["address"] = fallback_location
            fallback_response = requests.get(base_url, params=params)
            fallback_data = fallback_response.json()
            result = fallback_data.get("results", [{}])[0]

        if (
            not result
            or "geometry" not in result
            or "location" not in result["geometry"]
        ):
            logger.error("No geocoding results found after all attempts")
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Could not geocode location: '{location}'",
                    }
                ]
            }

        geo_point = {
            "latitude": result["geometry"]["location"]["lat"],
            "longitude": result["geometry"]["location"]["lng"],
        }

        logger.info(f"Successfully geocoded to: {json.dumps(geo_point)}")
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Geocoded '{location}' to: {json.dumps(geo_point)}",
                }
            ],
            "data": geo_point,
        }
    except Exception as e:
        logger.error(f"Geocoding error: {str(e)}")
        return {"content": [{"type": "text", "text": f"Error: {str(e)}"}]}


@mcp.tool("search_template")
async def search_template(
    original_query: str,
    query: str,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    distance: Optional[int] = None,
    tax: Optional[float] = None,
    bedrooms: Optional[int] = None,
    home_price_min: Optional[float] = None,
    home_price_max: Optional[float] = None,
    bathrooms: Optional[float] = None,
    square_footage: Optional[int] = None,
    property_features: Optional[str] = None,
    maintenance: Optional[float] = None,
) -> Dict[str, Any]:
    """Execute a search template with the given parameters."""
    logger.info(f"Using template ID: {SEARCH_TEMPLATE_ID} for index: {SEARCH_INDEX}")
    logger.info(f"Original user query: {original_query}")
    try:
        # Set default distance if lat/long provided but distance not specified
        if latitude is not None and longitude is not None and distance is None:
            distance = "25"
            logger.info(f"Setting default distance to 25")

        params = {
            "query": original_query,
            "latitude": latitude,
            "longitude": longitude,
            "distance": (f"{distance}mi" if distance is not None else None),
            "tax": tax,
            "bedrooms": bedrooms,
            "home_price_min": home_price_min,
            "home_price_max": home_price_max,
            "bathrooms": bathrooms,
            "square_footage": square_footage,
            "property_features": property_features,
            "maintenance": maintenance,
        }

        # Remove None values
        params = {k: v for k, v in params.items() if v is not None}

        logger.info(f"Normalized parameters: {json.dumps(params)}")

        resp = es.render_search_template(id=SEARCH_TEMPLATE_ID, params=params)

        print(resp)
        logging.info(f"Search template render response: {resp}")

        # Execute search template
        response = es.search_template(
            index=SEARCH_INDEX, id=SEARCH_TEMPLATE_ID, params=params
        )
        logging.info(f"Search template response: {response}")
        # Extract hits
        hits = response.get("hits", {}).get("hits", [])
        total = response.get("hits", {}).get("total", {}).get("value", 0)

        if not hits:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"No results found for query: {original_query}. Here is the original return from Elasticsearch: {response}",
                    }
                ]
            }

        # Format results
        results = []
        for hit in hits:
            fields = hit.get("fields", {})
            logging.info(f"Hit fields: {fields}")
            result = {
                "title": fields.get("title", ["No title"])[0],
                "tax": fields.get("tax", ["N/A"])[0],
                "maintenance_fee": fields.get("maintenance_fee", ["N/A"])[0],
                "bathrooms": fields.get("bathrooms", ["N/A"])[0],
                "bedrooms": fields.get("bedrooms", ["N/A"])[0],
                "square_footage": fields.get("square_footage", ["N/A"])[0],
                "home_price": fields.get("home_price", ["N/A"])[0],
                "property_features": fields.get("property_features", ["N/A"])[0],
            }
            results.append(result)

        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Found {total} properties matching your criteria. Here are the top {len(hits)} results:",
                },
                {"type": "text", "text": json.dumps(results, indent=2)},
            ],
            "data": {"total": total, "results": results},
        }
    except Exception as e:
        logger.error(f"Search template failed: {str(e)}")
        return {"content": [{"type": "text", "text": f"Error: {str(e)}"}]}


if __name__ == "__main__":
    mcp.run()
