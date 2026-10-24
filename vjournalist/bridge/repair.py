"""Conservative JSON syntax repairs: never synthesize semantic field values."""

import json
import re


def decode(text):
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        return json.loads(text), False
    except json.JSONDecodeError:
        pass
    cleaned, in_string, escape = [], False, False
    for index, char in enumerate(text):
        if not in_string and char == "," and text[index + 1 :].lstrip().startswith(("}", "]")):
            continue
        cleaned.append(char)
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
    text = "".join(cleaned)
    stack, quoted, escaped = [], False, False
    for c in text:
        if quoted:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                quoted = False
        elif c == '"':
            quoted = True
        elif c in "{[":
            stack.append("}" if c == "{" else "]")
        elif c in "}]":
            if not stack or stack.pop() != c:
                raise ValueError("JSON mismatched delimiters; local repair unsafe")
    if quoted:
        raise ValueError("Truncated JSON string; local repair unsafe")
    return json.loads(text + "".join(reversed(stack))), True
