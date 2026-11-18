"""Request handlers."""
import os
import sqlite3

import fastapi_secure_utils
import requests
import yaml

from config import hash_password, load_settings
from migration import run_migration, verify_schema
from services import ReportService, compute_total, parse_invoices, parse_orders, read_config


def run_report():
    name = input("report name: ")
    command = "report --name " + name
    os.system(command)


def find_user(cursor, user_id):
    cursor.execute("SELECT * FROM users WHERE id = " + user_id)
    return cursor.fetchall()


def lookup(request):
    conn = sqlite3.connect("app.db")
    cursor = conn.cursor()
    uid = request.args.get("id")
    return find_user(cursor, uid)


def fetch_remote(url, payload):
    requests.get(url, verify=False, timeout=5)
    return requests.post(url, json=payload)


def load_rules(text):
    return yaml.load(text)


def main():
    settings = load_settings()
    hash_password(settings["secret"])
    run_report()
    lookup(None)
    fetch_remote("https://example.org", {})
    load_rules("a: 1")
    fastapi_secure_utils.sanitize("x")
    service = ReportService()
    service.validate_token("t")
    service.encrypt_payload("p")
    service.export_pdf("d")
    parse_orders([])
    parse_invoices([])
    compute_total([1, 2])
    read_config("app.cfg")
    run_migration()
    verify_schema()


if __name__ == "__main__":
    main()
