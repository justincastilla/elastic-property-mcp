# Property MCP
This is a simplified version of [the original](https://github.com/sunilemanjee/Elastic-Python-MCP-Server/tree/main) repository by [Sunile Manjee](https://github.com/sunilemanjee). This MCP server will assist in searching for properties in Florida, USA on the Claude Desktop Application

## Description
This MCP (Model Context Protocol) server provides a search interface for property listings using Elasticsearch. It exposes tools for querying property data, rendering search templates, and integrating with Claude Desktop for conversational search. A sample data-set of all houses in FLorida was chosen to keep the data ingestion small and relatively fast at setup.

### Dataset
The dataset consists of property listings in the state of Florida, USA. Each listing contains details such as address, price, bedrooms, bathrooms, features, and agent information.

### FastMCP
The server uses the FastMCP framework to define and expose tools for property search and template parameter extraction. FastMCP enables rapid development of MCP-compliant servers with async tool definitions and easy integration with clients.

### Elasticsearch Search Template
Search queries are rendered using a Mustache-based template [`search_template.mustache`]('data/search_template.mustache'). This template supports dynamic filtering by location, price, bedrooms, bathrooms, and other property features, allowing flexible and powerful search capabilities.

The query combines a semantic_text query with the above filtering. More information on the `semantic_text` field type may be found [here](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/semantic-text).

### Google Maps Geocoding
This MCP server uses the Google Maps Geocoding service, which returns a Latitude and Longitude coordinate pair when a natural langauge location is submitted. This is helpful for creating geolocation searches, such as properties within 5 miles of a city, or when a user submits a city name without coordinates. A Google Maps API Key is required for this service and may be obtained [here](https://cloud.google.com/looker/docs/studio/add-a-google-maps-api-key).

### Workflow
1. The user sends a search request via Claude Desktop.
2. The server normalizes parameters and renders the search template.
3. The template is sent to Elasticsearch for execution.
4. Results are returned to the client, including property details and metadata.

### Installation and Usage
1. Clone this repository.
```bash
git clone https://github.com/justincastilla/elastic-property-mcp.git
cd elastic-property-mcp
```

2. Create a virtual environment and install dependencies:
```bash
python -m venv .venv 
source .venv/bin/activate
pip install -r requirements.txt
```
3. Duplicate the example.env file and rename to `.env`.

4. In the `.env` file, set environment variables for the Elasticsearch endpoint and API key as well as the Google Maps API key.

```bash
# Elastic environment variables
ELASTIC_ENDPOINT=<your endpoint here>
ELASTIC_API_KEY=<your api key here>

# Google environment variables
GOOGLE_MAPS_API_KEY = <your endpoint here>

# Search Configuration (optional - defaults provided)
PROPERTIES_SEARCH_TEMPLATE=properties-search-template
ES_INDEX=properties
```

5. Run the `ingest_properties.py` file:
```bash
python ingest_properties.py
```
6. Install the server into the Claude Desktop MCP Server manifest:

```bash
mcp install elastic_mcp_server.py
```

The MCP CLI will install an entry into Claude Desktop's MCP profile manifest that should but not necessarily look similar to this:

```json
"elasticsearch-mcp-server": {
  "command": "/Users/justin/.pyenv/shims/uv",
  "args": [
    "run",
    "--with",
    "mcp[cli]",
    "mcp",
    "run",
    "/Users/justin/Code/property-mcp/elastic_mcp_server.py"
  ],
  "env": {
    "ES_ENDPOINT": "<your-elastic-endpoint>",
    "ES_API_KEY": "<your-elastic-api-key>",
    "GOOGLE_MAPS_API_KEY": "<your-google-maps-api-key>"
  }
}
```

7. Open your Claude Desktop Application and start searching for properties in Florida!