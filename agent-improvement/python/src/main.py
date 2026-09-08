"""Interactive terminal entry point for the support agent."""

from __future__ import annotations

import sys

from .agent import AgentConfigurationError, AgentSession


def main() -> int:
    print("## Support Agent")
    print("Type 'exit' or press Ctrl-D to finish.\n")

    try:
        session = AgentSession()
    except AgentConfigurationError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    while True:
        try:
            user_input = input("You: ").strip()
        except EOFError:
            print()
            break
        except KeyboardInterrupt:
            print("\n")
            break

        if user_input.lower() in {"exit", "quit"}:
            break
        if not user_input:
            continue

        result = session.run(user_input)
        if result.error:
            print(f"Agent error: {result.error}")
        else:
            print(f"Agent: {result.response}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
