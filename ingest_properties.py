import os
from elasticsearch import Elasticsearch, helpers
from dotenv import load_dotenv
import json

load_dotenv()

ELASTIC_ENDPOINT = os.getenv("ELASTIC_ENDPOINT")
if not ELASTIC_ENDPOINT:
    raise ValueError("ELASTIC_ENDPOINT environment variable must be set")

ELASTIC_API_KEY = os.getenv("ELASTIC_API_KEY")
if not ELASTIC_API_KEY:
    raise ValueError("ELASTIC_API_KEY environment variable must be set")


INDEX_NAME = os.getenv("ES_INDEX", "properties")
TEMPLATE_ID = "properties-search-template"

SEARCH_TEMPLATE_FILE = "./data/search_template.mustache"
PROPERTIES_INDEX_MAPPING_FILE = "./data/properties_index_mapping.json"

PROPERTY_LISTINGS = "./data/florida_properties.json"

RAW_INDEX_MAPPING_FILE = "./data/raw_index_mapping.json"


def connect_to_elasticsearch():
    try:
        es = Elasticsearch(hosts=[ELASTIC_ENDPOINT], api_key=ELASTIC_API_KEY).options(
            request_timeout=600
        )
        connected = es.ping()
        print(f"1. ✅ Connected to Elasticsearch: {connected}")
        return es
    except Exception as e:
        print(f"❌ Error connecting to Elasticsearch: {e}")


# Load index mapping from external file
def load_index_mapping(mapping_file):
    """Load index mapping from external JSON file"""
    try:
        with open(mapping_file, "r") as f:
            mapping_content = f.read()
        print(f"2. ✅ Loaded index mapping from {mapping_file}")
        return mapping_content
    except FileNotFoundError:
        print(f"❌ Index mapping file not found: {mapping_file}")
        raise
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in mapping file {mapping_file}: {e}")
        raise


def create_properties_index(index_mappings):
    print(f"3. 🏗️ Creating properties index '{INDEX_NAME}'...")

    if es.indices.exists(index=INDEX_NAME):
        es.indices.delete(index=INDEX_NAME)
        print(f"\t🗑️ Previous index '{INDEX_NAME}' deleted.")

    es.indices.create(index=INDEX_NAME, body=index_mappings)
    print(f"\t✅ Index '{INDEX_NAME}' created.")


# Load search template from external file
def load_search_template(template_file):
    """Load search template content from external file"""
    try:
        with open(template_file, "r") as f:
            template_source = f.read()
        print(f"4. ✅ Loaded search template from {template_file}")
        return {"script": {"lang": "mustache", "source": template_source}}
    except FileNotFoundError:
        print(f"❌ Search template file not found: {template_file}")
        raise


def create_search_template(template_id=TEMPLATE_ID, template_content=None):
    """Creates a new search template"""
    print(f"5.📝 Creating search template '{template_id}'...")
    try:
        es.put_script(id=template_id, body=template_content)
        print(f"\t✅ Created search template: {template_id}")
    except Exception as e:
        print(f"\t❌ Error creating template '{template_id}': {e}")


def load_data_set():
    # load PROPERTY_LISTINGS into dataset as json
    with open(PROPERTY_LISTINGS, "r") as f:
        data_set = json.load(f)
        print(f"6. ✅ Loaded property listings from {PROPERTY_LISTINGS}")
        return data_set


# Parallel bulk loading of property data into Elasticsearch
def parallel_bulk_load(data_set):

    def generate_actions():
        doc_count = 0
        for line in data_set:
            doc_count += 1
            if doc_count % 100 == 0:
                print(f"\t📊 Processing {doc_count} documents...")
            yield {"_index": INDEX_NAME, "_source": line}

        print("\t=====================================")
        print(f"\t📊 Total documents to index: {doc_count}")

    print("7. 🚀 Starting parallel bulk indexing...")
    success_count = 0
    error_count = 0
    failed_docs = []  # Track failed documents

    chunk_size = 50

    for ok, result in helpers.parallel_bulk(
        es,
        actions=generate_actions(),
        thread_count=4,
        chunk_size=chunk_size,
    ):
        if ok:
            success_count += 1
            if success_count % 250 == 0:
                print(f"\t✅ Successfully indexed {success_count} documents...")
        else:
            error_count += 1
            # Capture detailed error information
            error_info = {
                "error_type": result.get("index", {})
                .get("error", {})
                .get("type", "unknown"),
                "error_reason": result.get("index", {})
                .get("error", {})
                .get("reason", "unknown"),
                "doc_id": result.get("index", {}).get("_id", "unknown"),
                "line_number": result.get("index", {}).get("_line_number", "unknown"),
            }
            failed_docs.append(error_info)

            if error_count % 100 == 0:
                print(f"❌ Encountered {error_count} errors...")
            elif error_count <= 10:  # Show first 10 errors immediately
                print(
                    f"❌ Error {error_count}: {error_info['error_type']} - {error_info['error_reason']}"
                )

        if error_count > 0:
            print(f"⚠️ Encountered {error_count} errors during indexing")

            # Report failed documents in detail
            print(f"\n🔍 DETAILED ERROR REPORT:")
            print(f"Total errors: {error_count}")
            print(f"Failed documents:")
            for i, failed_doc in enumerate(failed_docs, 1):
                print(
                    f"  {i}. Line {failed_doc.get('line_number', 'unknown')}: {failed_doc.get('error_type', 'unknown')} - {failed_doc.get('error_reason', 'unknown')}"
                )

    # Verify the final document count
    final_count = es.count(index=INDEX_NAME)["count"]

    print(f"📊 Final document count in '{INDEX_NAME}': {final_count}")


# Connect to Elasticsearch
es = connect_to_elasticsearch()

# Load the index mappings
index_mappings = load_index_mapping(PROPERTIES_INDEX_MAPPING_FILE)

# Create the properties index
create_properties_index(index_mappings)

# Load the search template content
search_template_content = load_search_template(SEARCH_TEMPLATE_FILE)

# Create the search template
create_search_template(template_content=search_template_content)

# Load Florida properties from local json file
properties_list = load_data_set()

# Add properties to Elasticsearch Index
parallel_bulk_load(properties_list)

print("🎉 Property data ingestion and processing complete!")
print(f"📋 Final index '{INDEX_NAME}' is ready for semantic search")
