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

"""Seed script to populate Firestore with sample destination data."""

from google.cloud import firestore

# HARDCODED PROJECT ID (Do NOT use GOOGLE_CLOUD_PROJECT or google.auth.default())
FIRESTORE_PROJECT_ID = "qwiklabs-gcp-01-29de6ff10d50"
DATABASE_ID = "travel-db"

SEEDED_DESTINATIONS = [
    {
        "id": "paris",
        "name": "Paris",
        "country": "France",
        "category": "Culture & History",
        "description": "The City of Light, famous for its iconic art, gastronomy, fashion, and romantic architecture.",
        "avg_daily_budget_usd": 180.0,
        "best_season": "Spring",
        "highlights": ["Eiffel Tower", "Louvre Museum", "Seine River Cruise", "Montmartre"],
    },
    {
        "id": "kyoto",
        "name": "Kyoto",
        "country": "Japan",
        "category": "Culture & History",
        "description": "Japan's cultural heartland with thousands of classical Buddhist temples, gardens, and traditional wooden houses.",
        "avg_daily_budget_usd": 140.0,
        "best_season": "Spring / Autumn",
        "highlights": ["Fushimi Inari Shrine", "Kinkaku-ji (Golden Pavilion)", "Arashiyama Bamboo Grove"],
    },
    {
        "id": "rio_de_janeiro",
        "name": "Rio de Janeiro",
        "country": "Brazil",
        "category": "Beach & Nature",
        "description": "Famous for its stunning coastal landscapes, vibrant Samba culture, Copacabana beach, and Christ the Redeemer.",
        "avg_daily_budget_usd": 110.0,
        "best_season": "Summer",
        "highlights": ["Christ the Redeemer", "Sugarloaf Mountain", "Copacabana Beach", "Tijuca National Park"],
    },
    {
        "id": "cape_town",
        "name": "Cape Town",
        "country": "South Africa",
        "category": "Adventure & Nature",
        "description": "A breathtaking port city on South Africa's southwest coast, dominated by Table Mountain.",
        "avg_daily_budget_usd": 120.0,
        "best_season": "Summer",
        "highlights": ["Table Mountain", "Cape Point", "Boulders Beach Penguins", "Kirstenbosch Botanical Gardens"],
    },
    {
        "id": "banff",
        "name": "Banff National Park",
        "country": "Canada",
        "category": "Adventure & Nature",
        "description": "Canada's oldest national park featuring turquoise glacial lakes, majestic mountains, and abundant wildlife.",
        "avg_daily_budget_usd": 160.0,
        "best_season": "Summer / Winter",
        "highlights": ["Lake Louise", "Moraine Lake", "Banff Upper Hot Springs", "Icefields Parkway"],
    },
]


def seed():
    print(f"Connecting to Firestore for project: '{FIRESTORE_PROJECT_ID}', database: '{DATABASE_ID}'...")
    try:
        db = firestore.Client(project=FIRESTORE_PROJECT_ID, database=DATABASE_ID)
    except Exception:
        db = firestore.Client(project=FIRESTORE_PROJECT_ID)

    collection_ref = db.collection("destinations")

    for item in SEEDED_DESTINATIONS:
        doc_id = item["id"]
        doc_ref = collection_ref.document(doc_id)
        doc_ref.set(item)
        print(f"Seeded destination: {item['name']} (ID: {doc_id})")

    print("Firestore seeding complete!")


if __name__ == "__main__":
    seed()
