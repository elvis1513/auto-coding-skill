#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request


class CheckError(RuntimeError):
    pass


def fetch(method: str, url: str, headers: dict[str, str] | None = None) -> tuple[int, str]:
    req = urllib.request.Request(url, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def cmd_status(args: argparse.Namespace) -> None:
    status, body = fetch("GET", args.url)
    if status != args.expect:
        raise CheckError(f"GET {args.url} expected {args.expect}, got {status}: {body[:400]}")
    print(f"[status] OK: {args.url} -> {status}")


def cmd_text_contains(args: argparse.Namespace) -> None:
    status, body = fetch("GET", args.url)
    if status != args.expect:
        raise CheckError(f"GET {args.url} expected {args.expect}, got {status}: {body[:400]}")
    if args.contains not in body:
        raise CheckError(f"Response from {args.url} does not contain expected text: {args.contains}")
    print(f"[text-contains] OK: {args.url}")


def cmd_json_field(args: argparse.Namespace) -> None:
    status, body = fetch("GET", args.url, headers={"Accept": "application/json"})
    if status != args.expect:
        raise CheckError(f"GET {args.url} expected {args.expect}, got {status}: {body[:400]}")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise CheckError(f"Response from {args.url} is not valid JSON: {exc}") from exc

    current = payload
    for part in args.path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
            continue
        raise CheckError(f"JSON path not found: {args.path}")

    if str(current) != args.equals:
        raise CheckError(f"JSON field {args.path} expected {args.equals}, got {current}")
    print(f"[json-field] OK: {args.url} {args.path}={current}")


def main() -> int:
    parser = argparse.ArgumentParser(prog="http_checks")
    sub = parser.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("status")
    s.add_argument("url")
    s.add_argument("--expect", type=int, default=200)
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("text-contains")
    s.add_argument("url")
    s.add_argument("--contains", required=True)
    s.add_argument("--expect", type=int, default=200)
    s.set_defaults(func=cmd_text_contains)

    s = sub.add_parser("json-field")
    s.add_argument("url")
    s.add_argument("--path", required=True)
    s.add_argument("--equals", required=True)
    s.add_argument("--expect", type=int, default=200)
    s.set_defaults(func=cmd_json_field)

    try:
        args = parser.parse_args()
        args.func(args)
        return 0
    except CheckError as exc:
        print(f"[ERROR] {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
