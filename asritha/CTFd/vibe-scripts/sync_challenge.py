#!/usr/bin/env python3
"""
Sync a challenge YAML file to CTFd.

This script validates a challenge YAML file against the JSON Schema,
then creates or updates the challenge via the CTFd API.

Usage:
    python sync_challenge.py <path_to_challenge.yaml>

Environment variables or modify the configuration below:
    CTFD_URL: Base URL of the CTFd instance (e.g., http://localhost:4000)
    CTFD_API_TOKEN: API token for authentication (generate in CTFd admin panel)
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

import jsonschema
import requests
import yaml

# =============================================================================
# CONFIGURATION
# =============================================================================

CTFD_URL = os.environ.get("CTFD_URL", "http://localhost:4000")
CTFD_API_TOKEN = os.environ.get("CTFD_API_TOKEN", "")

# =============================================================================
# JSON SCHEMA DEFINITION
# =============================================================================

CHALLENGE_JSON_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Challenge",
    "description": "A CTFd challenge definition",
    "type": "object",
    "required": ["name", "category", "value"],
    "additionalProperties": False,
    "properties": {
        "name": {
            "type": "string",
            "maxLength": 80,
            "description": "Challenge title",
        },
        "category": {
            "type": "string",
            "maxLength": 80,
            "description": "Challenge category",
        },
        "description": {
            "type": ["string", "null"],
            "maxLength": 65535,
            "description": "Challenge description (Markdown)",
        },
        "attribution": {
            "type": ["string", "null"],
            "description": "Author or source attribution",
        },
        "connection_info": {
            "type": ["string", "null"],
            "description": "Connection details for challenge",
        },
        "type": {
            "type": "string",
            "maxLength": 80,
            "default": "standard",
            "description": "Challenge type (standard, dynamic, etc.)",
        },
        "state": {
            "type": "string",
            "maxLength": 80,
            "enum": ["visible", "hidden"],
            "default": "visible",
            "description": "Challenge visibility state",
        },
        "value": {
            "type": "integer",
            "description": "Points awarded for solving",
        },
        "max_attempts": {
            "type": "integer",
            "default": 0,
            "description": "Maximum attempts allowed (0 = unlimited)",
        },
        "next_id": {
            "type": ["integer", "null"],
            "description": "Next challenge in sequence (prerequisite)",
        },
        "logic": {
            "type": "string",
            "maxLength": 80,
            "enum": ["any", "all"],
            "default": "any",
            "description": "Prerequisite logic type",
        },
        "initial": {
            "type": ["integer", "null"],
            "description": "Dynamic scoring: initial point value",
        },
        "minimum": {
            "type": ["integer", "null"],
            "description": "Dynamic scoring: minimum point value",
        },
        "decay": {
            "type": ["integer", "null"],
            "description": "Dynamic scoring: decay rate",
        },
        "function": {
            "type": "string",
            "maxLength": 32,
            "enum": ["static", "linear", "logarithmic"],
            "default": "static",
            "description": "Scoring function type",
        },
        "requirements": {
            "type": ["object", "null"],
            "description": "Challenge prerequisites",
            "properties": {
                "prerequisites": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "List of challenge IDs that must be solved first",
                },
                "anonymize": {
                    "type": "boolean",
                    "description": "Hide challenge details until prerequisites are met",
                },
            },
            "additionalProperties": False,
        },
    },
}


class ValidationError(Exception):
    """Raised when YAML validation fails."""

    pass


def validate_challenge_yaml(data: Dict) -> List[str]:
    """
    Validate challenge data against the JSON Schema.

    Args:
        data: Parsed YAML data

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    validator = jsonschema.Draft202012Validator(CHALLENGE_JSON_SCHEMA)

    for error in validator.iter_errors(data):
        # Format the error message nicely
        path = ".".join(str(p) for p in error.absolute_path) if error.absolute_path else "root"
        if path == "root":
            errors.append(error.message)
        else:
            errors.append(f"{path}: {error.message}")

    return errors


# =============================================================================
# API CLIENT
# =============================================================================


class CTFdAPIClient:
    """Client for interacting with the CTFd API."""

    def __init__(self, base_url: str, api_token: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Token {api_token}",
                "Content-Type": "application/json",
            }
        )

    def _request(self, method: str, endpoint: str, **kwargs) -> Dict:
        """Make an API request."""
        url = f"{self.base_url}/api/v1/{endpoint.lstrip('/')}"
        response = self.session.request(method, url, **kwargs)

        try:
            data = response.json()
        except requests.exceptions.JSONDecodeError:
            raise Exception(
                f"Invalid JSON response from API: {response.status_code} {response.text[:200]}"
            )

        if not response.ok:
            errors = data.get("errors", data.get("message", "Unknown error"))
            raise Exception(f"API error ({response.status_code}): {errors}")

        return data

    def get_challenges(self, name: str = None) -> List[Dict]:
        """Get all challenges, optionally filtered by name."""
        params = {"view": "admin"}
        if name:
            params["name"] = name
        response = self._request("GET", "/challenges", params=params)
        return response.get("data", [])

    def get_challenge_by_id(self, challenge_id: int) -> Dict:
        """Get a specific challenge by ID."""
        response = self._request("GET", f"/challenges/{challenge_id}")
        return response.get("data", {})

    def create_challenge(self, data: Dict) -> Dict:
        """Create a new challenge."""
        response = self._request("POST", "/challenges", json=data)
        return response.get("data", {})

    def update_challenge(self, challenge_id: int, data: Dict) -> Dict:
        """Update an existing challenge."""
        response = self._request("PATCH", f"/challenges/{challenge_id}", json=data)
        return response.get("data", {})

    def find_challenge_by_name(self, name: str) -> Optional[Dict]:
        """Find a challenge by exact name match."""
        challenges = self.get_challenges(name=name)
        for challenge in challenges:
            if challenge.get("name") == name:
                return challenge
        return None


# =============================================================================
# MAIN LOGIC
# =============================================================================


def load_yaml_file(path: Path) -> Dict:
    """Load and parse a YAML file."""
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValidationError(f"Invalid YAML syntax: {e}")

    if not isinstance(data, dict):
        raise ValidationError("YAML file must contain a mapping/object at the root")

    return data


def sync_challenge(yaml_path: Path, dry_run: bool = False) -> None:
    """
    Sync a challenge from a YAML file to CTFd.

    Args:
        yaml_path: Path to the challenge YAML file
        dry_run: If True, validate only without making API calls
    """
    # Load and validate YAML
    print(f"Loading {yaml_path}...")
    data = load_yaml_file(yaml_path)

    print("Validating against JSON Schema...")
    errors = validate_challenge_yaml(data)
    if errors:
        print("Validation failed:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)

    print("Validation passed!")

    if dry_run:
        print("\nDry run mode - no changes made.")
        print(f"Would sync challenge: {data.get('name')}")
        return

    # Check configuration
    if not CTFD_API_TOKEN:
        print("\nError: CTFD_API_TOKEN is not set.")
        print("Generate an API token in the CTFd admin panel and set it as an environment variable.")
        sys.exit(1)

    # Connect to API
    print(f"\nConnecting to {CTFD_URL}...")
    client = CTFdAPIClient(CTFD_URL, CTFD_API_TOKEN)

    # Check if challenge exists
    challenge_name = data["name"]
    print(f"Looking for existing challenge: {challenge_name}...")

    existing = client.find_challenge_by_name(challenge_name)

    if existing:
        # Update existing challenge
        challenge_id = existing["id"]
        print(f"Found existing challenge (ID: {challenge_id}). Updating...")

        # Don't send 'id' in the update payload
        update_data = {k: v for k, v in data.items() if k != "id"}
        result = client.update_challenge(challenge_id, update_data)
        print(f"Successfully updated challenge: {result.get('name')} (ID: {result.get('id')})")
    else:
        # Create new challenge
        print("Challenge not found. Creating new challenge...")
        result = client.create_challenge(data)
        print(f"Successfully created challenge: {result.get('name')} (ID: {result.get('id')})")


def main():
    global CTFD_URL, CTFD_API_TOKEN

    parser = argparse.ArgumentParser(
        description="Sync a challenge YAML file to CTFd",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python sync_challenge.py challenges/web/sqli.yaml
  python sync_challenge.py --dry-run challenges/crypto/rsa.yaml

Environment variables:
  CTFD_URL         Base URL of CTFd (default: http://localhost:4000)
  CTFD_API_TOKEN   API token for authentication (required)
        """,
    )
    parser.add_argument(
        "yaml_file",
        type=Path,
        help="Path to the challenge YAML file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate only, don't make API calls",
    )
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="CTFd URL (default: http://localhost:4000)",
    )
    parser.add_argument(
        "--token",
        type=str,
        default=None,
        help="CTFd API token (or use CTFD_API_TOKEN env var)",
    )

    args = parser.parse_args()

    # Override config from command line args
    if args.url:
        CTFD_URL = args.url
    if args.token:
        CTFD_API_TOKEN = args.token

    try:
        sync_challenge(args.yaml_file, dry_run=args.dry_run)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except ValidationError as e:
        print(f"Validation error: {e}")
        sys.exit(1)
    except requests.exceptions.ConnectionError:
        print(f"Error: Could not connect to {CTFD_URL}")
        print("Make sure CTFd is running and the URL is correct.")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
