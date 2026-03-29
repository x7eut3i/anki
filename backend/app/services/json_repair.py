"""Shared JSON repair and robust parsing for AI responses.

All AI-generated JSON parsing should go through repair_json() before json.loads(),
or use robust_json_parse() for multi-strategy parsing.
"""

import json
import logging
import re

logger = logging.getLogger("anki.json_repair")


def repair_json(text: str) -> str:
    """Attempt to repair common JSON issues from AI responses.

    Handles: code fences, trailing backticks/garbage, trailing commas,
    single quotes, control characters in strings, truncated JSON.
    """
    # Strip code fences (including fences that appear mid/end of text)
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
    # Remove trailing ``` (possibly preceded by whitespace)
    text = re.sub(r"\s*`{1,4}\s*$", "", text)

    # ── Strip leading non-JSON text (e.g. "Here is the result:\n{...") ──
    text = text.strip()
    if text and text[0] not in ('{', '['):
        first_brace = text.find('{')
        first_bracket = text.find('[')
        starts = [p for p in (first_brace, first_bracket) if p >= 0]
        if starts:
            text = text[min(starts):]

    # ── Strip trailing garbage after the last balanced } or ] ──
    # Walk string-aware to find the position where the top-level JSON value ends,
    # then discard anything after it (e.g. trailing ```, extra chars, etc.)
    _in_str = False
    _esc = False
    _braces = 0
    _brackets = 0
    _first_open = None
    _end_pos = len(text)
    for _i, _ch in enumerate(text):
        if _esc:
            _esc = False
            continue
        if _ch == '\\' and _in_str:
            _esc = True
            continue
        if _ch == '"':
            _in_str = not _in_str
            continue
        if _in_str:
            continue
        if _ch == '{':
            if _first_open is None:
                _first_open = _ch
            _braces += 1
        elif _ch == '}':
            _braces -= 1
            if _first_open == '{' and _braces == 0 and _brackets == 0:
                _end_pos = _i + 1
        elif _ch == '[':
            if _first_open is None:
                _first_open = _ch
            _brackets += 1
        elif _ch == ']':
            _brackets -= 1
            if _first_open == '[' and _brackets == 0 and _braces == 0:
                _end_pos = _i + 1
    if _end_pos < len(text) and _first_open is not None:
        text = text[:_end_pos]

    text = text.strip()

    # Remove trailing commas before } or ]
    text = re.sub(r",\s*([}\]])", r"\1", text)

    # Fix single-quoted strings → double-quoted
    # Only apply if no double quotes exist (rough heuristic)
    if '"' not in text and "'" in text:
        text = text.replace("'", '"')

    # Escape unescaped control characters inside JSON strings
    def _escape_control_chars(s: str) -> str:
        result = []
        in_str = False
        esc = False
        for ch in s:
            if esc:
                result.append(ch)
                esc = False
                continue
            if ch == '\\' and in_str:
                result.append(ch)
                esc = True
                continue
            if ch == '"':
                in_str = not in_str
                result.append(ch)
                continue
            if in_str:
                if ch == '\n':
                    result.append('\\n')
                    continue
                elif ch == '\r':
                    continue
                elif ch == '\t':
                    result.append('\\t')
                    continue
            result.append(ch)
        return ''.join(result)

    text = _escape_control_chars(text)

    # Early exit if already valid
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass

    # String-aware brace/bracket counting for truncation repair
    in_string = False
    escape_next = False
    open_braces = 0
    open_brackets = 0
    last_complete_pos = 0

    for idx, ch in enumerate(text):
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '{':
            open_braces += 1
        elif ch == '}':
            open_braces -= 1
            if open_braces == 0 and open_brackets == 0:
                last_complete_pos = idx + 1
        elif ch == '[':
            open_brackets += 1
        elif ch == ']':
            open_brackets -= 1

    # If we ended inside a string, the JSON is truncated mid-value
    if in_string:
        last_quote = text.rfind('"')
        if last_quote > 0:
            in_str2 = False
            esc2 = False
            for c2 in text[:last_quote]:
                if esc2:
                    esc2 = False
                    continue
                if c2 == '\\' and in_str2:
                    esc2 = True
                    continue
                if c2 == '"':
                    in_str2 = not in_str2
            if not in_str2:
                trunc_pos = last_quote
                while trunc_pos > 0 and text[trunc_pos - 1] in ' \t\n\r':
                    trunc_pos -= 1
                if trunc_pos > 0 and text[trunc_pos - 1] == ':':
                    key_start = text.rfind('"', 0, trunc_pos - 1)
                    if key_start > 0:
                        trunc_pos = key_start
                        while trunc_pos > 0 and text[trunc_pos - 1] in ' \t\n\r,':
                            trunc_pos -= 1
                elif trunc_pos > 0 and text[trunc_pos - 1] == ',':
                    trunc_pos -= 1
                text = text[:trunc_pos]

    # Remove trailing commas
    text = re.sub(r",\s*$", "", text)

    # Recount and close remaining open structures
    in_string = False
    escape_next = False
    open_braces = 0
    open_brackets = 0
    for ch in text:
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '{':
            open_braces += 1
        elif ch == '}':
            open_braces -= 1
        elif ch == '[':
            open_brackets += 1
        elif ch == ']':
            open_brackets -= 1

    if open_brackets > 0:
        text += "]" * open_brackets
    if open_braces > 0:
        text += "}" * open_braces

    return text


def robust_json_parse(text: str):
    """Try multiple strategies to parse JSON from AI response.

    Returns the parsed object or None if all strategies fail.
    """
    # Strategy 1: Direct parse (already repaired)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e1:
        logger.debug("JSON parse strategy 1 (direct) failed: %s", e1)

    # Strategy 2: Extract JSON array/object from mixed content
    for pattern in [
        r'(\[\s*\{.*\}\s*\])',
        r'(\{[^{}]*"cards"\s*:\s*\[.*\]\s*\})',
    ]:
        m = re.search(pattern, text, re.DOTALL)
        if m:
            try:
                candidate = repair_json(m.group(1))
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

    # Strategy 3: Find the outermost [ ... ] or { ... } using bracket matching
    for start_char, end_char in [('[', ']'), ('{', '}')]:
        start_idx = text.find(start_char)
        if start_idx == -1:
            continue
        depth = 0
        in_str = False
        esc = False
        end_idx = -1
        for i in range(start_idx, len(text)):
            ch = text[i]
            if esc:
                esc = False
                continue
            if ch == '\\' and in_str:
                esc = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == start_char:
                depth += 1
            elif ch == end_char:
                depth -= 1
                if depth == 0:
                    end_idx = i
                    break
        if end_idx > start_idx:
            candidate = text[start_idx:end_idx + 1]
            try:
                candidate = repair_json(candidate)
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

    # Strategy 4: Parse individual JSON objects and collect them
    objects = []
    brace_depth = 0
    in_str = False
    esc = False
    obj_start = -1
    for i, ch in enumerate(text):
        if esc:
            esc = False
            continue
        if ch == '\\' and in_str:
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == '{':
            if brace_depth == 0:
                obj_start = i
            brace_depth += 1
        elif ch == '}':
            brace_depth -= 1
            if brace_depth == 0 and obj_start >= 0:
                obj_text = text[obj_start:i + 1]
                try:
                    obj = json.loads(repair_json(obj_text))
                    if isinstance(obj, dict) and "front" in obj:
                        objects.append(obj)
                    elif isinstance(obj, dict) and "cards" in obj:
                        cards = obj["cards"]
                        if isinstance(cards, list):
                            objects.extend(cards)
                except json.JSONDecodeError:
                    pass
                obj_start = -1

    if objects:
        logger.debug("JSON parse strategy 4 (individual objects): recovered %d cards", len(objects))
        return objects

    logger.warning("All JSON parse strategies failed. Text preview: %s", text)
    return None
