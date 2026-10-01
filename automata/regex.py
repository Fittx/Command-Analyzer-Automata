import re

IDENTIFIER = r"[a-z][a-z0-9]*"
NO_ARG = r"(?:LOGOUT|EXIT|HELP);"
ARG = rf"(?:LOGIN|SAVE|LOAD) {IDENTIFIER};"
PATTERN = rf"^(?:{NO_ARG}|{ARG})$"

compiled = re.compile(PATTERN)

def matches(text: str) -> bool:
    return compiled.fullmatch(text) is not None
