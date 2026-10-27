"""Import a local HERE CSV/XLSX through the same validation/API path as the UI.

Usage: python import_customer_files.py --aoi "Divisoria" path/to/baseline.csv
Run from backend/ with DATABASE_URL configured. Existing identical imports are skipped.
"""
import argparse
from pathlib import Path

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.auth import current_user
from app.main import app
from app.services.customer_import import AOIS

# Local command-line operator: the API now requires sign-in, so this script acts as a system Operations Manager.
SYSTEM_OPERATOR = SimpleNamespace(id=None, username="cli", display_name="CLI import", roles=["ops_manager"], aois=[], active=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--aoi', required=True, choices=list(AOIS))
    parser.add_argument('file', type=Path)
    args = parser.parse_args()
    app.dependency_overrides[current_user] = lambda: SYSTEM_OPERATOR
    with args.file.open('rb') as stream, TestClient(app) as client:
        response = client.post('/api/customer-data/imports', data={'aoi': args.aoi},
                               files={'file': (args.file.name, stream)})
    if response.status_code == 201:
        data = response.json()
        print(f"Saved {data['row_count']:,} POIs for {data['aoi']} (dataset {data['id']})")
    elif response.status_code == 409:
        print(response.json()['detail'])
    else:
        print(response.json())
        raise SystemExit(1)


if __name__ == '__main__':
    main()
