#!/usr/bin/env python3
"""
Simple test script for DataGen Python SDK
Tests basic connectivity and PostHog queries
"""

import os
from dotenv import load_dotenv
from datagen_sdk import DatagenClient, DatagenError, DatagenAuthError

# Load environment variables
load_dotenv()

def test_api_key():
    """Test if API key is set"""
    api_key = os.getenv('DATAGEN_API_KEY')
    if not api_key:
        print("❌ DATAGEN_API_KEY not found in environment")
        return False
    print(f"✅ API key found: {api_key[:20]}...")
    return True

def test_client_init():
    """Test DataGen client initialization"""
    try:
        client = DatagenClient()
        print("✅ DataGen client initialized successfully")
        return client
    except Exception as e:
        print(f"❌ Failed to initialize client: {e}")
        return None

def test_posthog_projects(client):
    """Test fetching PostHog projects"""
    print("\n--- Testing PostHog Projects ---")
    try:
        result = client.execute_tool("mcp_Posthog_projects_get")
        print(f"✅ Successfully fetched PostHog projects")
        print(f"Result: {result}")
        return True
    except DatagenAuthError as e:
        print(f"❌ Authentication error: {e}")
        return False
    except DatagenError as e:
        print(f"❌ DataGen error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_posthog_query(client):
    """Test running a simple PostHog query"""
    print("\n--- Testing PostHog Query ---")

    query = {
        "kind": "InsightVizNode",
        "source": {
            "kind": "TrendsQuery",
            "series": [{
                "kind": "EventsNode",
                "event": "$pageview",
                "math": "dau",
                "custom_name": "Daily Active Users"
            }],
            "dateRange": {
                "date_from": "-7d",
                "date_to": None
            },
            "interval": "day",
            "filterTestAccounts": True
        }
    }

    try:
        result = client.execute_tool("mcp_Posthog_query_run", {"query": query})
        print(f"✅ Successfully ran PostHog query")
        print(f"Result type: {type(result)}")

        if isinstance(result, list) and len(result) > 0:
            print(f"First 200 chars: {str(result[0])[:200]}...")
        else:
            print(f"Result: {result}")

        return True
    except DatagenAuthError as e:
        print(f"❌ Authentication error: {e}")
        return False
    except DatagenError as e:
        print(f"❌ DataGen error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def main():
    """Run all tests"""
    print("=" * 50)
    print("DataGen SDK Test Suite")
    print("=" * 50)

    # Test 1: API key
    if not test_api_key():
        print("\n❌ Tests failed: No API key")
        return

    # Test 2: Client initialization
    client = test_client_init()
    if not client:
        print("\n❌ Tests failed: Could not initialize client")
        return

    # Test 3: PostHog projects
    projects_ok = test_posthog_projects(client)

    # Test 4: PostHog query
    query_ok = test_posthog_query(client)

    # Summary
    print("\n" + "=" * 50)
    print("Test Summary")
    print("=" * 50)
    print(f"API Key: ✅")
    print(f"Client Init: ✅")
    print(f"PostHog Projects: {'✅' if projects_ok else '❌'}")
    print(f"PostHog Query: {'✅' if query_ok else '❌'}")

    if projects_ok and query_ok:
        print("\n🎉 All tests passed!")
    else:
        print("\n⚠️ Some tests failed")

if __name__ == "__main__":
    main()
