import requests
import json
import sys
import os

# ==== CONFIGURATION ====
API_KEY = os.getenv("NEW_RELIC_USER_API_KEY")  # Must be set in environment
NR_GRAPHQL_URL = "https://api.newrelic.com/graphql"

# ==== GRAPHQL QUERY TEMPLATE ====
QUERY_TEMPLATE = """
query($accountId: Int!, $cursor: String) {
  actor {
    account(id: $accountId) {
      name
      alerts {
        nrqlConditionsSearch(cursor: $cursor) {
          totalCount
          nextCursor
          nrqlConditions {
            id
            name
            enabled
            policyId
            nrql {
              query
            }
            createdAt
            updatedAt
          }
        }
      }
    }
  }
}
"""

def fetch_all_nrql_conditions(account_id):
    """Fetch all NRQL conditions with pagination."""
    all_conditions = []
    cursor = None
    account_name = None

    headers = {
        "Content-Type": "application/json",
        "API-Key": API_KEY
    }

    while True:
        try:
            response = requests.post(
                NR_GRAPHQL_URL,
                headers=headers,
                json={"query": QUERY_TEMPLATE, "variables": {"accountId": account_id, "cursor": cursor}}
            )
            response.raise_for_status()
            data = response.json()

            if "errors" in data:
                print("GraphQL errors:", json.dumps(data["errors"], indent=2))
                sys.exit(1)

            account_data = data["data"]["actor"]["account"]
            if account_name is None:
                account_name = account_data["name"]

            search_result = account_data["alerts"]["nrqlConditionsSearch"]
            conditions = search_result["nrqlConditions"]
            all_conditions.extend(conditions)

            cursor = search_result.get("nextCursor")
            if not cursor:
                break  # No more pages

        except requests.exceptions.RequestException as e:
            print("HTTP Request failed:", e)
            sys.exit(1)

    return account_name, all_conditions

def main():
    # Validate API key
    if not API_KEY:
        print("Error: Environment variable NEW_RELIC_USER_API_KEY is not set.")
        sys.exit(1)

    # Validate account ID argument
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <ACCOUNT_ID>")
        sys.exit(1)

    try:
        account_id = int(sys.argv[1])
    except ValueError:
        print("Error: ACCOUNT_ID must be an integer.")
        sys.exit(1)

    account_name, all_conditions = fetch_all_nrql_conditions(account_id)
    enabled_conditions = [c for c in all_conditions if c.get("enabled")]

    print(f"Account: {account_name} (ID: {account_id})")
    print(f"Total NRQL conditions: {len(all_conditions)}")
    print(f"Enabled NRQL conditions: {len(enabled_conditions)}\n")

    for cond in enabled_conditions:
        print(f"- {cond['name']} (ID: {cond['id']}, Policy: {cond['policyId']})")

if __name__ == "__main__":
    main()
