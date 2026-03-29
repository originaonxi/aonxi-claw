"""
Base adapter — common patterns for all agent adapters.
"""

import json
import os


def write_context_file(agent_dir, filename, data):
    """Write a JSON sidecar file into an agent's data directory.
    Agents check for these files at start of run for Claw enrichment."""
    data_dir = os.path.join(agent_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    filepath = os.path.join(data_dir, filename)

    # Merge with existing context if file exists
    existing = {}
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

    if isinstance(existing, dict) and isinstance(data, dict):
        existing.update(data)
        data = existing

    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

    return filepath


def read_context_file(agent_dir, filename):
    """Read a JSON sidecar file from an agent's data directory."""
    filepath = os.path.join(agent_dir, "data", filename)
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None
