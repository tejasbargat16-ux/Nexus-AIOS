"""
Nexus AIOS CLI Terminal (Phase 2).

Interactive natural-language terminal for communicating with the nexusd daemon.
Supports one-off commands, interactive conversational mode with local/cloud routing flags,
tools inspection, memory facts inspection, and interactive permission confirmation.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
import requests


def parse_arguments() -> argparse.Namespace:
    """Parse command line options and flags."""
    parser = argparse.ArgumentParser(
        description="Nexus AIOS - Natural Language Intent Terminal",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Force inference through the local offline model",
    )
    parser.add_argument(
        "--cloud",
        action="store_true",
        help="Force inference through the cloud provider model",
    )
    parser.add_argument(
        "--once",
        type=str,
        metavar="INTENT",
        help="Send a single intent and exit without entering interactive shell",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=os.getenv("NEXUS_API_HOST", "127.0.0.1"),
        help="nexusd daemon HTTP API host",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("NEXUS_API_PORT", "8765")),
        help="nexusd daemon HTTP API port",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Display daemon status and active LLM configuration",
    )
    parser.add_argument(
        "--tools",
        action="store_true",
        help="List all tools registered in nexusd",
    )
    parser.add_argument(
        "--facts",
        action="store_true",
        help="Display stored memory facts and user preferences",
    )
    return parser.parse_args()


def get_base_url(host: str, port: int) -> str:
    """Construct daemon base URL."""
    return f"http://{host}:{port}"


def send_intent(
    base_url: str,
    text: str,
    prefer: str | None = None,
    confirmed: bool = False,
) -> dict[str, Any] | None:
    """
    Send natural language intent to nexusd daemon.

    Args:
        base_url: nexusd API base URL.
        text: Natural language user input.
        prefer: Optional provider override ('local' | 'cloud').
        confirmed: Flag indicating user approved action if prompted.

    Returns:
        dict: Parsed API response or None on failure.
    """
    payload: dict[str, Any] = {"text": text, "confirmed": confirmed}
    if prefer:
        payload["prefer"] = prefer

    try:
        resp = requests.post(f"{base_url}/intent", json=payload, timeout=30)
        data = resp.json()

        # Handle pending confirmation
        if data.get("status") == "confirmation_required":
            action = data.get("action", "unknown")
            params = data.get("params", {})
            print(f"\n[Security Guard] Action '{action}' requires user confirmation.")
            print(f"Parameters: {json.dumps(params, indent=2)}")
            choice = input(f"Authorize execution of '{action}'? [y/N]: ").strip().lower()
            if choice in ("y", "yes"):
                return send_intent(base_url, text, prefer=prefer, confirmed=True)
            else:
                print("Action declined by user.\n")
                return {"reply": f"Action '{action}' cancelled by user.", "provider": "guard"}

        if resp.status_code == 200:
            return data

        error_msg = data.get("error", resp.text)
        print(f"\n[Error {resp.status_code}] {error_msg}\n", file=sys.stderr)
        return None
    except requests.exceptions.ConnectionError:
        print(
            f"\n[Error] Unable to reach nexusd at {base_url}.\n"
            "Please ensure the daemon is running:\n"
            "   python3 -m nexusd.main\n",
            file=sys.stderr,
        )
        return None
    except requests.exceptions.Timeout:
        print("\n[Timeout] The daemon did not respond in time.\n", file=sys.stderr)
        return None


def show_status(base_url: str) -> None:
    """Fetch and print daemon status."""
    try:
        resp = requests.get(f"{base_url}/status", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            print("==> Nexus AIOS Daemon Status")
            print(f"  Service:    {data.get('service')} (v{data.get('version')})")
            print(f"  Status:     {data.get('status')}")
            print(f"  Uptime:     {data.get('uptime_seconds')}s")
            comps = data.get("components", {})
            if comps:
                print(f"  Tools:      {comps.get('tools_registered')} registered")
                print(f"  Memory:     {comps.get('stored_facts')} facts recorded")
                print(f"  Policies:   {comps.get('permission_rules')} security rules")
            providers = data.get("providers", {})
            print(f"  Preferred:  {providers.get('preferred')}")
            local = providers.get("local", {})
            print(f"  Local:      {local.get('type')} @ {local.get('url')} ({local.get('model')})")
            cloud = providers.get("cloud", {})
            cloud_state = "Configured" if cloud.get("configured") else "No API Key Set"
            print(f"  Cloud:      {cloud.get('provider')} ({cloud.get('model')}) [{cloud_state}]")
        else:
            print(f"[Error] Failed to get status: {resp.status_code}")
    except requests.exceptions.ConnectionError:
        print(f"[Error] nexusd is not running at {base_url}.")


def show_tools(base_url: str) -> None:
    """Fetch and print registered tools catalog."""
    try:
        resp = requests.get(f"{base_url}/tools", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            tools = data.get("tools", [])
            print(f"==> Nexus Registered Tools ({len(tools)} available)")
            print(f"{'Action':<25} {'Description':<50}")
            print("-" * 75)
            for t in tools:
                print(f"{t.get('action'):<25} {t.get('description', '')[:48]:<50}")
        else:
            print(f"[Error] Failed to list tools: {resp.status_code}")
    except requests.exceptions.ConnectionError:
        print(f"[Error] nexusd is not running at {base_url}.")


def show_facts(base_url: str) -> None:
    """Fetch and print stored memory facts."""
    try:
        resp = requests.get(f"{base_url}/memory/facts", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            facts = data.get("facts", [])
            print(f"==> Nexus Memory Facts ({len(facts)} stored)")
            if not facts:
                print("  No facts recorded yet.")
                return
            for f in facts:
                print(f"  [{f.get('category', 'general')}] {f.get('key')}: {f.get('value')}")
        else:
            print(f"[Error] Failed to list memory facts: {resp.status_code}")
    except requests.exceptions.ConnectionError:
        print(f"[Error] nexusd is not running at {base_url}.")


def run_interactive_loop(base_url: str, prefer: str | None) -> None:
    """Run interactive REPL terminal session."""
    mode_tag = f" [{prefer}]" if prefer else ""
    print(f"Nexus AIOS CLI (Phase 2){mode_tag}")
    print("Type your intent or 'exit' / 'quit' to close. Use Ctrl+C to cancel line.")
    print("-" * 55)

    while True:
        try:
            prompt = f"nexus{mode_tag}> "
            user_input = input(prompt).strip()
            if not user_input:
                continue

            if user_input.lower() in ("exit", "quit", "q"):
                print("Exiting Nexus CLI. Goodbye!")
                break

            result = send_intent(base_url, user_input, prefer=prefer)
            if result:
                provider_tag = f"[{result.get('provider', 'ai')}]"
                reply = result.get("reply", "")
                print(f"\n{provider_tag} {reply}")
                tool_res = result.get("tool_result")
                if tool_res:
                    print(f"[Tool Result] {json.dumps(tool_res, indent=2)}")
                print()

        except (KeyboardInterrupt, EOFError):
            print("\nExiting Nexus CLI. Goodbye!")
            break


def main() -> None:
    """Main CLI entrypoint."""
    args = parse_arguments()
    base_url = get_base_url(args.host, args.port)

    prefer: str | None = None
    if args.local:
        prefer = "local"
    elif args.cloud:
        prefer = "cloud"

    if args.status:
        show_status(base_url)
        sys.exit(0)

    if args.tools:
        show_tools(base_url)
        sys.exit(0)

    if args.facts:
        show_facts(base_url)
        sys.exit(0)

    if args.once:
        result = send_intent(base_url, args.once, prefer=prefer)
        if result:
            provider_tag = f"[{result.get('provider', 'ai')}]"
            print(f"{provider_tag} {result.get('reply')}")
            sys.exit(0)
        sys.exit(1)

    run_interactive_loop(base_url, prefer)


if __name__ == "__main__":
    main()
