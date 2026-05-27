#!/usr/bin/env python3
import os
import sys
import json
import argparse
import requests

NR_GRAPHQL_URL = "https://api.newrelic.com/graphql"

QUERY = """
query listworkflows($accountId: Int!) {
  actor {
    account(id: $accountId) {
      aiWorkflows {
        workflows {
          totalCount
          entities {
            id
            name
            accountId
            workflowEnabled
            destinationsEnabled
            updatedAt
            lastRun
            destinationConfigurations {
              type
              channelId
            }
          }
        }
      }
      aiNotifications {
        destinations {
          totalCount
          entities {
            id
            name
            type
            active
            accountId
            properties {
              key
              value
            }
          }
        }
      }
    }
  }
}
"""

from datetime import datetime, timedelta, timezone

def parse_timestamp(ts):
    """
    Accepts:
      - YYYY-MM-DD
      - YYYY-MM-DDTHH:MM:SSZ
      - ISO8601 variants
    Returns timezone-aware UTC datetime.
    """
    try:
        # Try full ISO8601
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass

    try:
        # Try simple date
        dt = datetime.strptime(ts, "%Y-%m-%d")
        return dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def get_api_key():
    key = os.getenv("NEW_RELIC_USER_API_KEY")
    if not key:
        print("ERROR: NEW_RELIC_USER_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)
    return key


def run_query(account_id, api_key, verbose=False):
    headers = {
        "Content-Type": "application/json",
        "API-Key": api_key,
    }

    payload = {
        "query": QUERY,
        "variables": {"accountId": int(account_id)},
    }

    if verbose:
        print("Executing NerdGraph query…", file=sys.stderr)

    resp = requests.post(NR_GRAPHQL_URL, headers=headers, json=payload)
    resp.raise_for_status()
    return resp.json()


# ------------------------------
# Workflows Command
# ------------------------------

def print_workflows(workflows):
    print(f"\nFound {len(workflows)} workflows:\n")

    for wf in workflows:
        print("=" * 80)
        print(f"Workflow: {wf['name']} (ID: {wf['id']})")
        print(f"Workflow Enabled: {wf['workflowEnabled']}")
        print(f"Destinations Enabled: {wf['destinationsEnabled']}")
        print(f"Updated At: {wf['updatedAt']}")
        print(f"Last Run: {wf['lastRun']}")

        print("\nDestination Configurations:")
        for dc in wf.get("destinationConfigurations", []):
            print(f"  - Type: {dc['type']}")
            print(f"    ChannelId: {dc['channelId']}")

        print()


def workflows_command(account, args):
    workflows = account["aiWorkflows"]["workflows"]["entities"]

    # Filter: never run (alias for lastRun is None)
    if args.never_run:
        workflows = [w for w in workflows if w.get("lastRun") is None]

    # Filter: lastRun before timestamp
    if args.last_run_before:
        cutoff = parse_timestamp(args.last_run_before)
        if cutoff:
            workflows = [
                w for w in workflows
                if w.get("lastRun") is not None
                and parse_timestamp(w["lastRun"]) < cutoff
            ]

    # Filter: lastRun after timestamp
    if args.last_run_after:
        cutoff = parse_timestamp(args.last_run_after)
        if cutoff:
            workflows = [
                w for w in workflows
                if w.get("lastRun") is not None
                and parse_timestamp(w["lastRun"]) > cutoff
            ]

    # Filter: lastRun older than N days
    if args.last_run_days_ago is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=args.last_run_days_ago)
        workflows = [
            w for w in workflows
            if w.get("lastRun") is not None
            and parse_timestamp(w["lastRun"]) < cutoff
        ]

    # Exact case-insensitive workflow name match
    if args.name:
        needle = args.name.lower()
        workflows = [
            w for w in workflows
            if w.get("name", "").lower() == needle
        ]

    # Fuzzy case-insensitive workflow name match
    if args.name_contains:
        needle = args.name_contains.lower()
        workflows = [
            w for w in workflows
            if needle in w.get("name", "").lower()
        ]

    # Exclude workflows whose name contains substring (case-insensitive)
    if args.name_not_contains:
        needle = args.name_not_contains.lower()
        workflows = [
            w for w in workflows
            if needle not in w.get("name", "").lower()
        ]


    # Filter: workflowEnabled
    if args.workflow_enabled:
        val = args.workflow_enabled.lower() == "true"
        workflows = [
            w for w in workflows
            if w.get("workflowEnabled") == val
        ]

    # Filter: destinationsEnabled
    if args.destinations_enabled:
        val = args.destinations_enabled.lower() == "true"
        workflows = [
            w for w in workflows
            if w.get("destinationsEnabled") == val
        ]


    # Filter: include only workflows where lastRun is None
    if args.include_last_run_none:
        workflows = [w for w in workflows if w.get("lastRun") is None]

    # Filter: exclude workflows where lastRun is None
    if args.exclude_last_run_none:
        workflows = [w for w in workflows if w.get("lastRun") is not None]

    # Optional filtering
    if args.enabled:
        enabled = args.enabled.lower() == "true"
        workflows = [w for w in workflows if w["workflowEnabled"] == enabled]

    if args.json:
        print(json.dumps(workflows, indent=2))
    else:
        print_workflows(workflows)


# ------------------------------
# Destinations Command
# ------------------------------

def print_destinations(destinations):
    print(f"\nFound {len(destinations)} destinations:\n")

    for d in destinations:
        print("=" * 80)
        print(f"Destination: {d['name']} (ID: {d['id']})")
        print(f"Type: {d['type']}")
        print(f"Active: {d['active']}")

        print("\nProperties:")
        for prop in d.get("properties", []):
            print(f"  - {prop['key']}: {prop['value']}")

        print()


def destinations_command(account, args):
    destinations = account["aiNotifications"]["destinations"]["entities"]

    # Normalize type filter
    if args.type:
        t = args.type.upper()
        destinations = [d for d in destinations if d["type"].upper() == t]

    # Exact email match
    if args.email:
        email = args.email.lower()
        destinations = [
            d for d in destinations
            if any(
                p["key"] == "email" and p["value"].lower() == email
                for p in d.get("properties", [])
            )
        ]

    # Fuzzy email match
    if args.email_contains:
        needle = args.email_contains.lower()
        destinations = [
            d for d in destinations
            if any(
                p["key"] == "email" and needle in p["value"].lower()
                for p in d.get("properties", [])
            )
        ]

    # Exact PagerDuty name match
    if args.pagerduty_name:
        name = args.pagerduty_name
        destinations = [
            d for d in destinations
            if d["type"].startswith("PAGERDUTY") and d["name"] == name
        ]

    # Fuzzy PagerDuty name match
    if args.pagerduty_name_contains:
        needle = args.pagerduty_name_contains.lower()
        destinations = [
            d for d in destinations
            if d["type"].startswith("PAGERDUTY") and needle in d["name"].lower()
        ]

    # Output
    if args.json:
        print(json.dumps(destinations, indent=2))
    else:
        print_destinations(destinations)


# ------------------------------
# CLI Setup
# ------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="New Relic AI Workflows & Destinations CLI"
    )

    parser.add_argument("--account-id", required=True)
    parser.add_argument("--verbose", action="store_true")

    sub = parser.add_subparsers(dest="command")

    # workflows
    wf = sub.add_parser("workflows")
    wf_sub = wf.add_subparsers(dest="subcommand")

    wf_list = wf_sub.add_parser("list")
    wf_list.add_argument("--enabled", choices=["true", "false"])
    wf_list.add_argument("--json", action="store_true")

    wf_list.add_argument(
        "--include-last-run-none",
        action="store_true",
        help="Include only workflows where lastRun is None"
    )

    wf_list.add_argument(
        "--name",
        help="Exact case-insensitive match on workflow name"
    )

    wf_list.add_argument(
        "--name-contains",
        help="Case-insensitive substring match on workflow name"
)

    wf_list.add_argument(
        "--name-not-contains",
        help="Exclude workflows whose name contains this substring (case-insensitive)"
    )

    wf_list.add_argument(
    "--exclude-last-run-none",
    action="store_true",
    help="Exclude workflows where lastRun is None"
)
    
    wf_list.add_argument(
    "--workflow-enabled",
    choices=["true", "false"],
    help="Filter by workflowEnabled"
)

    wf_list.add_argument(
        "--destinations-enabled",
        choices=["true", "false"],
        help="Filter by destinationsEnabled"
)

    wf_list.add_argument(
        "--never-run",
        action="store_true",
        help="Include only workflows that have never run (lastRun is None)"
    )

    wf_list.add_argument(
        "--last-run-before",
        help="Include workflows whose lastRun is before this timestamp (YYYY-MM-DD or ISO8601)"
    )

    wf_list.add_argument(
        "--last-run-after",
        help="Include workflows whose lastRun is after this timestamp (YYYY-MM-DD or ISO8601)"
    )

    wf_list.add_argument(
        "--last-run-days-ago",
        type=int,
        help="Include workflows whose lastRun was more than N days ago"
    )


    # destinations
    dest = sub.add_parser("destinations")
    dest_sub = dest.add_subparsers(dest="subcommand")

    dest_list = dest_sub.add_parser("list")
    dest_list.add_argument("--json", action="store_true")

    dest_list.add_argument("--type", help="Filter by destination type")
    dest_list.add_argument("--email", help="Exact email match")
    dest_list.add_argument("--email-contains", help="Case-insensitive substring match on email")
    dest_list.add_argument("--pagerduty-name", help="Exact PagerDuty integration name")
    dest_list.add_argument("--pagerduty-name-contains", help="Case-insensitive substring match on PagerDuty name")
    
    return parser.parse_args()

def main():
    args = parse_args()
    api_key = get_api_key()

    # Default subcommands
    if args.command == "workflows" and args.subcommand is None:
        args.subcommand = "list"

    if args.command == "destinations" and args.subcommand is None:
        args.subcommand = "list"

    data = run_query(args.account_id, api_key, verbose=args.verbose)
    account = data["data"]["actor"]["account"]

    if args.command == "workflows":
        workflows_command(account, args)

    elif args.command == "destinations":
        destinations_command(account, args)


if __name__ == "__main__":
    main()
