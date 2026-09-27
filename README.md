# Smart Travel & Itinerary Planner

An intelligent AI Travel & Itinerary Concierge built with the **Agent Development Kit (ADK)** and powered by **Gemini 2.5 Flash**, **Vertex AI Memory Bank**, **Firestore**, and **Google Cloud Storage**.

![Agent Demo](./demo.gif)

---

## Key Features & Capabilities

- **Cross-Session Long-Term Memory**: Powered by **Vertex AI Memory Bank** to automatically remember user preferences, travel styles, and critical dietary/allergy constraints across chat sessions.
- **Firestore Travel Database**: Reads and updates travel destination profiles, category recommendations, and daily budgets in Google Cloud Firestore (`travel-db`).
- **Real-Time Live Weather**: Fetches current weather conditions, temperatures (°C and °F), humidity, and wind speed for any destination worldwide via Open-Meteo API.
- **Google Maps & Places Integration**: Geocodes address landmarks and discovers nearby attractions, restaurants, and museums using Google Maps Geocoding and Places API (New).
- **Itemized Trip Budgeting**: Calculates comprehensive budget breakdowns including daily per-person expenses, flights, and a 10% contingency reserve.
- **AI Image Generation**: Generates high-resolution destination preview photography using `gemini-3.1-flash-lite-image` in the `global` region, saving session artifacts and hosting public images on Google Cloud Storage.
- **AI Video Generation**: Produces short visual video clips for travel destinations using Google's **Omni model** (`gemini-omni-flash-preview`) via the Interactions API in the `global` region, uploaded directly to Cloud Storage.
- **Sandboxed Code Execution**: Executes Python code safely in isolated environments using `AgentEngineSandboxCodeExecutor`.
- **Adaptive UI (A2UI v0.8)**: Generates structured, responsive A2UI card layouts that render cleanly in the chat interface.

---

## Google Cloud Services & Technologies

- **Vertex AI Reasoning Engine**: Hosts and serves the agent reasoning pipeline via Agent Development Kit (ADK).
- **Vertex AI Memory Bank**: Provides persistent vector memory bank indexing for cross-session recall.
- **Google Cloud Firestore**: NoSQL database backing destination information and travel itineraries (`travel-db`).
- **Google Cloud Storage**: Public bucket hosting generated destination images (`destinations/`) and video clips (`videos/`).
- **Google Maps Platform**: Geocoding API and Places API (New) for location discovery and spatial search.
- **Gemini & Google GenAI Models**:
  - `gemini-2.5-flash`: Primary reasoning and tool execution model.
  - `gemini-3.1-flash-lite-image`: Destination image generation.
  - `gemini-omni-flash-preview`: Destination video clip generation via Google Omni Interactions API.
- **FastAPI Proxy & Web Frontend**: Lightweight Python FastAPI server and plain HTML/CSS/JS frontend supporting A2UI mini-rendering and quick-prompt chips.

---

## Setup & Local Development

### 1. Prerequisites
Ensure you have Python 3.11+, `uv` (or `pip`), and the `gcloud` CLI installed and authenticated to your GCP project.

```bash
gcloud auth application-default login
```

### 2. Environment Variables
Configure your environment variables in a `.env` file or export them in your shell:

```bash
export GOOGLE_MAPS_API_KEY=<YOUR_KEY>
export WEATHER_API_KEY=<YOUR_KEY>
```

### 3. Running the Agent Locally
Run the ADK agent server locally using `adk`:

```bash
uv run adk web --port 8080 --allow_origins "*" --reload_agents
```

### 4. Running the Frontend Proxy Locally
Navigate to the `frontend/` directory, set the deployment metadata environment variables, and start the FastAPI proxy server:

```bash
cd frontend
export AGENT_ENGINE_RESOURCE_NAME="projects/<PROJECT_NUMBER>/locations/<LOCATION>/reasoningEngines/<ENGINE_ID>"
export AGENT_DIRECTORY="app"

uv run uvicorn main:app --host 0.0.0.0 --port 8080
```

---

## Deployment Instructions

### Deploying the Agent to Vertex AI Reasoning Engine
Deploy the agent to Agent Platform using `agents-cli`:

```bash
agents-cli deploy --update-env-vars GOOGLE_MAPS_API_KEY=$GOOGLE_MAPS_API_KEY --no-confirm-project
```

### Deploying the Frontend Proxy to Cloud Run
Build and deploy the FastAPI proxy container to Cloud Run:

```bash
gcloud run deploy travel-planner-frontend \
  --source ./frontend \
  --region us-east1 \
  --set-env-vars AGENT_ENGINE_RESOURCE_NAME=<RESOURCE_NAME>,AGENT_DIRECTORY=app \
  --allow-unauthenticated
```
