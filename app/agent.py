# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import datetime
import json
import os
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from dotenv import load_dotenv
from google import genai
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.memory import VertexAiMemoryBankService
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.cloud import firestore, storage
from google.genai import types

from .a2ui_utils import a2ui_callback

load_dotenv()

# HARDCODED CONSTANTS (Do NOT use GOOGLE_CLOUD_PROJECT or google.auth.default())
FIRESTORE_PROJECT_ID = "qwiklabs-gcp-01-29de6ff10d50"
DATABASE_ID = "travel-db"
GCS_BUCKET_NAME = "qwiklabs-gcp-01-29de6ff10d50-static-assets-bucket"
MEMORY_BANK_ID = "1457044221826433024"
LOCATION = "us-east1"


def memory_bank_service_builder():
    """Builds the VertexAiMemoryBankService instance for deployed runs."""
    return VertexAiMemoryBankService(
        project=FIRESTORE_PROJECT_ID,
        location=LOCATION,
        agent_engine_id=MEMORY_BANK_ID,
    )


async def generate_memories_callback(callback_context: CallbackContext):
    """WRITE: after each turn, send the session events to Memory Bank for fact extraction."""
    try:
        await callback_context.add_session_to_memory()
    except Exception:
        pass
    return None


def _get_agent_engine_resource_name() -> str | None:
    """Reads the remote Agent Engine resource ID from deployment_metadata.json if available."""
    possible_paths = [
        os.path.join(os.path.dirname(__file__), "..", "deployment_metadata.json"),
        os.path.join(os.path.dirname(__file__), "deployment_metadata.json"),
        "deployment_metadata.json",
    ]
    for path in possible_paths:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    engine_id = data.get("remote_agent_runtime_id")
                    if engine_id:
                        return engine_id
            except Exception:
                pass
    return None


def _get_firestore_client():
    try:
        return firestore.Client(project=FIRESTORE_PROJECT_ID, database=DATABASE_ID)
    except Exception:
        return firestore.Client(project=FIRESTORE_PROJECT_ID)


def search_destinations(category: str = "", max_daily_budget: float = 0.0) -> str:
    """Searches the travel destinations catalog stored in Firestore.

    Args:
        category: Optional category filter (e.g. 'Culture & History', 'Beach & Nature', 'Adventure & Nature').
        max_daily_budget: Optional maximum average daily budget limit in USD.

    Returns:
        JSON string list of matching destination items.
    """
    db = _get_firestore_client()
    docs = db.collection("destinations").stream()

    results = []
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id

        # Apply category filter if provided
        if category and category.lower() not in data.get("category", "").lower():
            continue

        # Apply budget filter if provided
        if max_daily_budget > 0 and data.get("avg_daily_budget_usd", 0) > max_daily_budget:
            continue

        results.append(data)

    if not results:
        return f"No destinations found matching category='{category}' and max_daily_budget={max_daily_budget}."

    return json.dumps(results, indent=2)


def get_destination_details(destination_id: str) -> str:
    """Retrieves detailed information for a specific travel destination from Firestore.

    Args:
        destination_id: The document ID of the destination (e.g. 'paris', 'kyoto', 'rio_de_janeiro', 'cape_town', 'banff').

    Returns:
        JSON string with detailed information about the destination.
    """
    db = _get_firestore_client()
    doc_ref = db.collection("destinations").document(destination_id.lower().strip())
    doc = doc_ref.get()

    if not doc.exists:
        return f"Destination with ID '{destination_id}' was not found in Firestore."

    data = doc.to_dict()
    data["id"] = doc.id
    return json.dumps(data, indent=2)


def add_destination(
    destination_id: str,
    name: str,
    country: str,
    category: str,
    description: str,
    avg_daily_budget_usd: float,
    best_season: str,
    highlights: str,
) -> str:
    """Adds or updates a travel destination in the Firestore database.

    Args:
        destination_id: Unique slug ID for the destination (e.g., 'tokyo', 'rome').
        name: Name of the destination city or spot (e.g., 'Tokyo').
        country: Country where the destination is located (e.g., 'Japan').
        category: Category of travel (e.g., 'Culture & History', 'Food & Nightlife').
        description: Brief description of the destination.
        avg_daily_budget_usd: Estimated average daily travel budget in USD.
        best_season: Best season or time of year to visit.
        highlights: Comma-separated list of top highlights or attractions.

    Returns:
        Confirmation message upon saving to Firestore.
    """
    db = _get_firestore_client()
    clean_id = destination_id.lower().replace(" ", "_").strip()

    highlights_list = [h.strip() for h in highlights.split(",") if h.strip()]

    item = {
        "id": clean_id,
        "name": name,
        "country": country,
        "category": category,
        "description": description,
        "avg_daily_budget_usd": float(avg_daily_budget_usd),
        "best_season": best_season,
        "highlights": highlights_list,
    }

    doc_ref = db.collection("destinations").document(clean_id)
    doc_ref.set(item)

    return f"Successfully added destination '{name}' (ID: {clean_id}) to Firestore."


def calculate_trip_budget(
    avg_daily_budget_usd: float,
    duration_days: int,
    num_travelers: int = 1,
    flight_cost_per_person_usd: float = 0.0,
) -> str:
    """Calculates an estimated total budget breakdown for a trip.

    Args:
        avg_daily_budget_usd: Estimated average daily expenses per person in USD (lodging, food, activities).
        duration_days: Total number of days for the trip.
        num_travelers: Number of people traveling together (default 1).
        flight_cost_per_person_usd: Estimated flight/transportation cost per person in USD (default 0.0).

    Returns:
        JSON string with itemized costs (daily subtotal, flight subtotal, contingency reserve, grand total).
    """
    if duration_days <= 0 or num_travelers <= 0 or avg_daily_budget_usd < 0:
        return "Invalid input parameters for budget calculation."

    daily_total = avg_daily_budget_usd * duration_days * num_travelers
    flights_total = flight_cost_per_person_usd * num_travelers
    subtotal = daily_total + flights_total
    contingency_reserve = subtotal * 0.10  # 10% emergency reserve
    grand_total = subtotal + contingency_reserve

    budget_summary = {
        "duration_days": duration_days,
        "num_travelers": num_travelers,
        "per_person_daily_usd": avg_daily_budget_usd,
        "daily_expenses_subtotal_usd": round(daily_total, 2),
        "flights_subtotal_usd": round(flights_total, 2),
        "contingency_reserve_10_percent_usd": round(contingency_reserve, 2),
        "grand_total_usd": round(grand_total, 2),
        "estimated_cost_per_traveler_usd": round(grand_total / num_travelers, 2),
    }

    return json.dumps(budget_summary, indent=2)


def get_live_destination_weather(city_name: str) -> str:
    """Fetches real-time current weather data for any destination worldwide using Open-Meteo public API.

    Args:
        city_name: The name of the city or destination to look up (e.g. 'Paris', 'Tokyo', 'Cape Town').

    Returns:
        JSON string with live temperature (°C and °F), humidity, wind speed, timezone, and weather condition description.
    """
    if not city_name or not city_name.strip():
        return "Please provide a valid city name."

    # Read optional weather API key if set in environment
    api_key = os.getenv("WEATHER_API_KEY", "").strip()

    try:
        encoded_city = urllib.parse.quote(city_name.strip())
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={encoded_city}&count=1"
        geo_req = urllib.request.Request(geo_url, headers={"User-Agent": "TravelPlannerApp/1.0"})

        with urllib.request.urlopen(geo_req, timeout=5) as resp:
            geo_data = json.loads(resp.read().decode("utf-8"))

        if not geo_data.get("results"):
            return f"Could not locate geographic coordinates for city '{city_name}'."

        location = geo_data["results"][0]
        lat = location["latitude"]
        lon = location["longitude"]
        city_full_name = location.get("name", city_name)
        country = location.get("country", "")
        timezone = location.get("timezone", "UTC")

        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
        weather_req = urllib.request.Request(weather_url, headers={"User-Agent": "TravelPlannerApp/1.0"})

        with urllib.request.urlopen(weather_req, timeout=5) as resp:
            weather_data = json.loads(resp.read().decode("utf-8"))

        current = weather_data.get("current", {})
        temp_c = current.get("temperature_2m")
        temp_f = round((temp_c * 9 / 5) + 32, 1) if temp_c is not None else None
        humidity = current.get("relative_humidity_2m")
        wind_kmh = current.get("wind_speed_10m")
        weather_code = current.get("weather_code", 0)

        wmo_conditions = {
            0: "Clear sky",
            1: "Mainly clear",
            2: "Partly cloudy",
            3: "Overcast",
            45: "Foggy",
            48: "Rime fog",
            51: "Light drizzle",
            61: "Slight rain",
            63: "Moderate rain",
            65: "Heavy rain",
            71: "Slight snow",
            75: "Heavy snow",
            80: "Rain showers",
            95: "Thunderstorm",
        }
        condition = wmo_conditions.get(weather_code, "Varied weather")

        result = {
            "city": city_full_name,
            "country": country,
            "latitude": lat,
            "longitude": lon,
            "timezone": timezone,
            "current_temperature_celsius": temp_c,
            "current_temperature_fahrenheit": temp_f,
            "humidity_percent": humidity,
            "wind_speed_kmh": wind_kmh,
            "condition": condition,
            "data_source": "Open-Meteo Public API",
        }

        return json.dumps(result, indent=2)

    except Exception as e:
        return f"Error fetching live weather data for '{city_name}': {str(e)}"


def geocode_address(address: str) -> str:
    """Geocodes an address or location name into geographic latitude and longitude using Google Maps Geocoding API.

    Args:
        address: Street address, landmark, or city name (e.g. 'Eiffel Tower, Paris', '1600 Amphitheatre Pkwy, Mountain View, CA').

    Returns:
        JSON string with formatted name/address, location coordinates (latitude and longitude), place ID, and types.
    """
    if not address or not address.strip():
        return "Please provide a valid address string."

    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
    if not api_key:
        return "GOOGLE_MAPS_API_KEY environment variable is not configured."

    try:
        encoded_address = urllib.parse.quote(address.strip())
        url = f"https://maps.googleapis.com/maps/api/geocode/json?address={encoded_address}&key={api_key}"
        req = urllib.request.Request(url, headers={"User-Agent": "TravelPlannerApp/1.0"})

        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        if data.get("status") != "OK" or not data.get("results"):
            return f"Geocoding failed for address '{address}'. Status: {data.get('status')}."

        first_result = data["results"][0]
        formatted_address = first_result.get("formatted_address")
        location = first_result.get("geometry", {}).get("location", {})
        place_id = first_result.get("place_id")
        types_list = first_result.get("types", [])

        result = {
            "name": formatted_address,
            "address": formatted_address,
            "location": {
                "latitude": location.get("lat"),
                "longitude": location.get("lng"),
            },
            "place_id": place_id,
            "types": types_list,
        }

        return json.dumps(result, indent=2)

    except Exception as e:
        return f"Error geocoding address '{address}': {str(e)}"


def search_nearby_places(
    latitude: float,
    longitude: float,
    place_type: str = "tourist_attraction",
    radius_meters: float = 2000.0,
) -> str:
    """Finds nearby places (e.g. tourist attractions, restaurants, museums) around coordinates using Google Places API (New).

    Args:
        latitude: Geographic latitude coordinate (e.g. 48.85837).
        longitude: Geographic longitude coordinate (e.g. 2.29448).
        place_type: Type of place to search for (e.g. 'tourist_attraction', 'restaurant', 'museum', 'park', 'cafe').
        radius_meters: Search radius distance in meters around coordinates (default 2000.0 meters).

    Returns:
        JSON string listing nearby places with name, address, location coordinates, rating, and Google Maps URI.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
    if not api_key:
        return "GOOGLE_MAPS_API_KEY environment variable is not configured."

    try:
        url = "https://places.googleapis.com/v1/places:searchNearby"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location,places.types,places.rating,places.googleMapsUri",
        }

        clean_type = place_type.strip().lower()

        payload = {
            "includedTypes": [clean_type],
            "maxResultCount": 10,
            "locationRestriction": {
                "circle": {
                    "center": {
                        "latitude": float(latitude),
                        "longitude": float(longitude),
                    },
                    "radius": float(radius_meters),
                }
            },
        }

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")

        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        raw_places = data.get("places", [])
        if not raw_places:
            return f"No nearby places of type '{place_type}' found within {radius_meters}m of ({latitude}, {longitude})."

        places_summary = []
        for p in raw_places:
            display_name = p.get("displayName", {}).get("text", "")
            formatted_addr = p.get("formattedAddress", "")
            loc = p.get("location", {})
            rating = p.get("rating")
            types_list = p.get("types", [])
            maps_uri = p.get("googleMapsUri", "")

            places_summary.append(
                {
                    "name": display_name,
                    "address": formatted_addr,
                    "location": {
                        "latitude": loc.get("latitude"),
                        "longitude": loc.get("longitude"),
                    },
                    "rating": rating,
                    "types": types_list,
                    "google_maps_uri": maps_uri,
                }
            )

        return json.dumps(places_summary, indent=2)

    except Exception as e:
        return f"Error searching nearby places: {str(e)}"


def generate_destination_image(
    destination_name: str,
    prompt_details: str = "",
    tool_context: ToolContext = None,
) -> str:
    """Generates a visual preview image for a travel destination or attraction using the gemini-3.1-flash-lite-image model in global location.

    Saves the image as a session artifact and uploads image bytes directly to a public Cloud Storage bucket.

    Args:
        destination_name: Name of the travel destination or landmark (e.g. 'Kyoto Bamboo Grove', 'Eiffel Tower Sunset').
        prompt_details: Optional extra description details to enhance the image prompt.
        tool_context: Injected ADK ToolContext used for saving Playground artifacts.

    Returns:
        JSON string containing the destination name, prompt, and public Cloud Storage image URL.
    """
    if not destination_name or not destination_name.strip():
        return "Please provide a valid destination or landmark name."

    try:
        client = genai.Client(
            vertexai=True,
            project=FIRESTORE_PROJECT_ID,
            location="global",
        )

        full_prompt = f"A stunning, high-resolution travel photography style image of {destination_name.strip()}."
        if prompt_details.strip():
            full_prompt += f" {prompt_details.strip()}"

        response = client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=full_prompt,
        )

        image_bytes = None
        mime_type = "image/jpeg"

        if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    image_bytes = part.inline_data.data
                    mime_type = part.inline_data.mime_type or "image/jpeg"
                    break

        if not image_bytes:
            return f"Failed to generate image bytes for '{destination_name}'."

        clean_slug = destination_name.lower().replace(" ", "_").replace(",", "")
        slug = "".join(c for c in clean_slug if c.isalnum() or c == "_").strip("_")
        timestamp_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
        ext = "jpg"
        if "png" in mime_type:
            ext = "png"
        filename = f"{slug}_{timestamp_str}.{ext}"

        if tool_context:
            artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
            tool_context.save_artifact(filename=filename, artifact=artifact_part)

        storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(f"destinations/{filename}")
        blob.upload_from_string(image_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/destinations/{filename}"

        result = {
            "destination": destination_name,
            "prompt": full_prompt,
            "public_image_url": public_url,
            "artifact_saved": filename if tool_context else "saved_without_context",
        }

        return json.dumps(result, indent=2)

    except Exception as e:
        return f"Error generating destination image for '{destination_name}': {str(e)}"


def generate_destination_video(
    destination_name: str,
    prompt_details: str = "",
    tool_context: ToolContext = None,
) -> str:
    """Generates a short visual video clip for a travel destination or landmark using Google's Omni model (gemini-omni-flash-preview) in global location.

    Saves the video as a session artifact and uploads video bytes directly to a public Cloud Storage bucket.

    Args:
        destination_name: Name of the travel destination or landmark (e.g. 'Kyoto Bamboo Grove', 'Bali Beach Palm Trees').
        prompt_details: Optional extra description details to enhance the video prompt.
        tool_context: Injected ADK ToolContext used for saving Playground artifacts.

    Returns:
        JSON string containing the destination name, prompt, and public Cloud Storage video URL.
    """
    if not destination_name or not destination_name.strip():
        return "Please provide a valid destination or landmark name."

    try:
        client = genai.Client(
            vertexai=True,
            project=FIRESTORE_PROJECT_ID,
            location="global",
        )

        full_prompt = f"Generate a short video clip of {destination_name.strip()}."
        if prompt_details.strip():
            full_prompt += f" {prompt_details.strip()}"

        interaction = client.interactions.create(
            model="gemini-omni-flash-preview",
            input=full_prompt,
            response_modalities=["text", "video"],
        )

        out_vid = getattr(interaction, "output_video", None)
        raw_data = getattr(out_vid, "data", None) if out_vid else None
        if raw_data is None and isinstance(out_vid, dict):
            raw_data = out_vid.get("data")

        video_bytes = None
        if isinstance(raw_data, str):
            video_bytes = base64.b64decode(raw_data)
        elif isinstance(raw_data, bytes):
            video_bytes = raw_data

        if not video_bytes:
            return f"Failed to generate video bytes for '{destination_name}'."

        clean_slug = destination_name.lower().replace(" ", "_").replace(",", "")
        slug = "".join(c for c in clean_slug if c.isalnum() or c == "_").strip("_")
        timestamp_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{slug}_{timestamp_str}.mp4"

        if tool_context:
            artifact_part = types.Part.from_bytes(data=video_bytes, mime_type="video/mp4")
            tool_context.save_artifact(filename=filename, artifact=artifact_part)

        storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(f"videos/{filename}")
        blob.upload_from_string(video_bytes, content_type="video/mp4")

        public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/videos/{filename}"

        result = {
            "destination": destination_name,
            "prompt": full_prompt,
            "public_video_url": public_url,
            "artifact_saved": filename if tool_context else "saved_without_context",
        }

        return json.dumps(result, indent=2)

    except Exception as e:
        return f"Error generating destination video for '{destination_name}': {str(e)}"


# Configure AgentEngineSandboxCodeExecutor using deployment_metadata.json if present
agent_engine_resource_name = _get_agent_engine_resource_name()
code_executor = (
    AgentEngineSandboxCodeExecutor(agent_engine_resource_name=agent_engine_resource_name)
    if agent_engine_resource_name
    else AgentEngineSandboxCodeExecutor()
)

# Configure A2UI Schema Manager (v0.8) & System Prompt
schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

a2ui_instruction = schema_manager.generate_system_prompt(
    role_description=(
        "An expert AI Travel & Itinerary Concierge. "
        "You help users discover travel destinations, explore budgets and highlights, check live weather, geocode locations, "
        "search nearby places, generate visual destination previews, execute code in a sandboxed environment, and plan custom travel itineraries. "
        "You have cross-session long-term memory via Vertex AI Memory Bank to remember facts across conversations. "
        "CRITICAL MEMORY REQUIREMENT: You MUST actively detect, remember, and preserve ALL user allergies (including food allergies like nuts or gluten, environmental allergies, and medical allergies) and dietary restrictions across sessions. "
        "Whenever a user mentions an allergy or dietary constraint (e.g., 'I am allergic to shellfish', 'I have a severe peanut allergy'), "
        "you MUST acknowledge it, store it in Memory Bank, and strictly filter out any destination, restaurant, or activity recommendations that pose an allergy risk."
    ),
    workflow_description="Analyze the user request and return structured UI when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        '{"Image": {"url": {"literalString": "https://..."}}}. Never point an '
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)

root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=a2ui_instruction,
    code_executor=code_executor,
    tools=[
        PreloadMemoryTool(),
        search_destinations,
        get_destination_details,
        add_destination,
        calculate_trip_budget,
        get_live_destination_weather,
        geocode_address,
        search_nearby_places,
        generate_destination_image,
        generate_destination_video,
    ],
    after_model_callback=a2ui_callback,
    after_agent_callback=generate_memories_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)
