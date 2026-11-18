"""File helpers with explicit error handling (control file)."""
import logging

import requests
import yaml

logger = logging.getLogger(__name__)


def load_yaml(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return yaml.safe_load(handle)
    except FileNotFoundError:
        logger.warning("missing file %s", path)
        return {}
    except ValueError:
        raise


def fetch_status(url):
    return requests.get(url, timeout=5).status_code


def main():
    load_yaml("settings.yaml")
    fetch_status("https://example.org")


if __name__ == "__main__":
    main()
