"""
backend/utils/text_helpers.py
------------------------------
Pure utility functions for text processing.

WHY SEPARATE FROM SERVICES?
Services have dependencies (database, OpenAI). Utilities are pure functions
with zero dependencies — they're easier to test and can be used anywhere.

FUNCTIONS:
- sanitize_input:          Clean and validate user messages
- count_tokens:            Count tokens before sending to OpenAI (avoid surprises)
- truncate_to_token_limit: Trim text to fit within token limits
- extract_obd_codes:       Automatically detect OBD fault codes in messages
- detect_vehicle_mention:  Extract year/make/model from natural language
"""

import re
from typing import Optional, List
import tiktoken


# ─────────────────────────────────────────────
# Input Sanitization
# ─────────────────────────────────────────────

def sanitize_input(text: str) -> str:
    """
    Cleans user input before processing.

    WHAT IT DOES:
    - Strips leading/trailing whitespace
    - Collapses multiple spaces into one
    - Collapses more than 2 newlines into 2 (prevents prompt injection via blank lines)
    - Truncates to 2000 characters max (prevents abuse/cost explosion)
    - Removes null bytes (can break some processing)

    WHAT IT DOES NOT DO:
    - Does not filter "bad words" — we rely on OpenAI's content policy
    - Does not escape HTML — that's Chainlit's job

    Args:
        text: Raw user input

    Returns:
        Cleaned text safe for processing
    """
    if not text:
        return ""

    # Remove null bytes and control characters (except newlines and tabs)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

    # Collapse whitespace
    text = re.sub(r'[ \t]+', ' ', text)           # Multiple spaces → single space
    text = re.sub(r'\n{3,}', '\n\n', text)        # 3+ newlines → double newline

    # Strip edges
    text = text.strip()

    # Enforce maximum length (prevent token cost explosion)
    if len(text) > 2000:
        text = text[:2000] + "... [truncated]"

    return text


# ─────────────────────────────────────────────
# Token Counting
# ─────────────────────────────────────────────

# Cache the encoder — loading it is slow, we only want to do it once
_encoder_cache: dict = {}


def _get_encoder(model: str = "gpt-4o") -> tiktoken.Encoding:
    """
    Returns the tiktoken encoder for a given model, with caching.

    WHY TIKTOKEN?
    OpenAI charges per token, not per character. Different words/punctuation
    use different numbers of tokens. tiktoken gives us the exact count that
    OpenAI will use, so we can avoid unexpected API costs.
    """
    if model not in _encoder_cache:
        try:
            _encoder_cache[model] = tiktoken.encoding_for_model(model)
        except KeyError:
            # Fallback for unknown models
            _encoder_cache[model] = tiktoken.get_encoding("cl100k_base")
    return _encoder_cache[model]


def count_tokens(text: str, model: str = "gpt-4o") -> int:
    """
    Counts the number of tokens in a string for a given OpenAI model.

    RULE OF THUMB (English text):
    - ~4 characters per token on average
    - "brake pad replacement" ≈ 4 tokens
    - A typical user message ≈ 50-100 tokens
    - A full repair manual section ≈ 500-2000 tokens

    GPT-4o context limit: 128,000 tokens
    We stay well under this to keep costs reasonable.

    Args:
        text:  The text to count
        model: The OpenAI model name (affects tokenization)

    Returns:
        Exact token count
    """
    enc = _get_encoder(model)
    return len(enc.encode(text))


def truncate_to_token_limit(
    text: str,
    max_tokens: int = 2000,
    model: str = "gpt-4o"
) -> str:
    """
    Truncates text to fit within a token limit.

    Used when repair document chunks might be too long to fit in the context window.
    Instead of hard-cutting at characters (which can break mid-word), we
    tokenize first then decode back — preserving clean word boundaries.

    Args:
        text:       Input text
        max_tokens: Maximum allowed tokens
        model:      OpenAI model name

    Returns:
        Text truncated to max_tokens (or original if already within limit)
    """
    enc = _get_encoder(model)
    tokens = enc.encode(text)

    if len(tokens) <= max_tokens:
        return text  # Already within limit

    # Decode back to string — this handles word boundaries cleanly
    truncated_tokens = tokens[:max_tokens]
    return enc.decode(truncated_tokens)


# ─────────────────────────────────────────────
# OBD Code Detection
# ─────────────────────────────────────────────

# OBD-II code pattern:
# - Letter: P (powertrain), B (body), C (chassis), U (network)
# - 4 digits
# Examples: P0300, B1234, C0035, U0100
OBD_CODE_PATTERN = re.compile(
    r'\b([PBCU][0-9]{4})\b',
    re.IGNORECASE
)


def extract_obd_codes(text: str) -> List[str]:
    """
    Finds all OBD-II fault codes mentioned in a message.

    This lets us give the user targeted code-specific information even
    if they mention codes naturally in a sentence.

    Examples:
        "I have a P0420 and also P0171" → ["P0420", "P0171"]
        "My car shows code b1234"       → ["B1234"]
        "My car is making a noise"      → []

    Args:
        text: User message text

    Returns:
        List of OBD codes found, uppercased and deduplicated
    """
    codes = OBD_CODE_PATTERN.findall(text)
    # Uppercase and deduplicate while preserving order
    seen = set()
    result = []
    for code in codes:
        code = code.upper()
        if code not in seen:
            seen.add(code)
            result.append(code)
    return result


# ─────────────────────────────────────────────
# Vehicle Detection
# ─────────────────────────────────────────────

# Common vehicle makes (helps us detect when users mention their car)
VEHICLE_MAKES = [
    "toyota", "honda", "ford", "chevrolet", "chevy", "gmc", "dodge", "ram",
    "jeep", "chrysler", "buick", "cadillac", "lincoln", "mercury",
    "nissan", "infiniti", "mazda", "mitsubishi", "subaru", "suzuki",
    "hyundai", "kia", "genesis", "bmw", "mercedes", "benz", "audi",
    "volkswagen", "vw", "volvo", "saab", "porsche", "jaguar", "land rover",
    "rover", "mini", "fiat", "alfa romeo", "ferrari", "lamborghini",
    "lexus", "acura", "pontiac", "oldsmobile", "saturn", "isuzu",
    "hummer", "tesla", "rivian", "lucid", "polestar",
]

# Pattern for model year (1900-2030)
YEAR_PATTERN = re.compile(r'\b(19[0-9]{2}|20[0-2][0-9]|2030)\b')


def detect_vehicle_mention(text: str) -> Optional[dict]:
    """
    Attempts to extract vehicle year and make from natural language.

    This is used to log which vehicles users ask about most — helpful for
    knowing which repair docs to expand.

    Examples:
        "My 2018 Honda Accord..."  → {"year": "2018", "make": "honda"}
        "I have a Ford F-150"      → {"year": None,   "make": "ford"}
        "My car is making noise"   → None

    NOTE: This is a simple heuristic — not perfect. It's for analytics,
    not for routing — the LLM handles the actual vehicle-specific logic.

    Args:
        text: User message

    Returns:
        Dict with "year" and "make" keys, or None if no vehicle detected
    """
    text_lower = text.lower()

    # Find year
    year_match = YEAR_PATTERN.search(text)
    year = year_match.group(0) if year_match else None

    # Find make
    detected_make = None
    for make in VEHICLE_MAKES:
        if make in text_lower:
            detected_make = make
            break

    if year or detected_make:
        return {"year": year, "make": detected_make}

    return None


# ─────────────────────────────────────────────
# Message Formatting
# ─────────────────────────────────────────────

def format_obd_query(codes: List[str]) -> str:
    """
    Builds a targeted search query from a list of OBD codes.
    Used to improve vector search when codes are detected.

    Example:
        ["P0420", "P0171"] → "OBD fault code P0420 P0171 diagnosis repair causes"
    """
    if not codes:
        return ""
    code_str = " ".join(codes)
    return f"OBD fault code {code_str} diagnosis repair causes symptoms"


def clean_response_text(text: str) -> str:
    """
    Light post-processing of LLM responses before storing.
    - Removes trailing whitespace from each line
    - Normalises multiple blank lines to at most two
    """
    lines = [line.rstrip() for line in text.split('\n')]
    # Collapse 3+ consecutive blank lines → 2
    result = re.sub(r'\n{3,}', '\n\n', '\n'.join(lines))
    return result.strip()
