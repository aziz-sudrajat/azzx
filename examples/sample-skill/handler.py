"""Example AZZX skill handler.

Install:  azzx skills install examples/sample-skill
Trust:    azzx skills trust shout && azzx skills enable shout
Invoke:   azzx skills invoke shout --args '{"text":"hello"}'
"""


def main(text: str) -> dict:
    return {"shouted": text.upper()}
