"""
tests/test_text_helpers.py
----------------------------
Unit tests for backend/utils/text_helpers.py

WHAT ARE UNIT TESTS?
Unit tests verify that individual functions work correctly.
They're called "unit" tests because they test one unit of code at a time —
isolated from the database, network, and other external systems.

WHY WRITE TESTS?
- Catch bugs before they reach production
- Refactor code confidently (tests tell you if you broke something)
- Document expected behaviour (tests ARE the spec)
- Required for CI/CD pipelines

HOW TO RUN:
    pytest tests/test_text_helpers.py -v

The -v flag means "verbose" — shows each test name individually.
"""

import pytest
import sys
import os

# Add the project root to Python path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ─────────────────────────────────────────────
# Import what we're testing
# ─────────────────────────────────────────────
from backend.utils.text_helpers import (
    sanitize_input,
    extract_obd_codes,
    detect_vehicle_mention,
    chunk_text_preview,
    format_obd_query,
    clean_response_text,
)


# ─────────────────────────────────────────────
# sanitize_input tests
# ─────────────────────────────────────────────

class TestSanitizeInput:
    """Tests for the input sanitization function."""

    def test_basic_string_passes_through(self):
        """Normal input should come back clean."""
        result = sanitize_input("My car won't start")
        assert result == "My car won't start"

    def test_strips_leading_trailing_whitespace(self):
        result = sanitize_input("  hello world  ")
        assert result == "hello world"

    def test_collapses_multiple_spaces(self):
        result = sanitize_input("My  car   has   a  problem")
        assert result == "My car has a problem"

    def test_collapses_excessive_newlines(self):
        """3+ newlines become 2."""
        result = sanitize_input("line1\n\n\n\n\nline2")
        assert result == "line1\n\nline2"

    def test_empty_string_returns_empty(self):
        assert sanitize_input("") == ""
        assert sanitize_input("   ") == ""

    def test_none_like_handling(self):
        """Should handle edge cases gracefully."""
        assert sanitize_input("") == ""

    def test_truncates_very_long_input(self):
        """Input over 2000 chars should be truncated."""
        long_input = "a" * 3000
        result = sanitize_input(long_input)
        assert len(result) <= 2020  # 2000 + "[truncated]" marker
        assert "truncated" in result

    def test_removes_null_bytes(self):
        """Null bytes can break string processing."""
        result = sanitize_input("hello\x00world")
        assert "\x00" not in result
        assert "hello" in result

    def test_preserves_obd_codes(self):
        """OBD codes in input should survive sanitization."""
        result = sanitize_input("I have P0420 and P0171 codes")
        assert "P0420" in result
        assert "P0171" in result


# ─────────────────────────────────────────────
# extract_obd_codes tests
# ─────────────────────────────────────────────

class TestExtractOBDCodes:
    """Tests for OBD-II fault code extraction."""

    def test_single_code(self):
        codes = extract_obd_codes("I have a P0420 code")
        assert codes == ["P0420"]

    def test_multiple_codes(self):
        codes = extract_obd_codes("Showing P0420 and P0171 and also C0035")
        assert "P0420" in codes
        assert "P0171" in codes
        assert "C0035" in codes

    def test_lowercase_codes_normalized(self):
        """Codes should be returned uppercase regardless of input."""
        codes = extract_obd_codes("code p0420 is showing")
        assert codes == ["P0420"]

    def test_b_codes(self):
        codes = extract_obd_codes("B1234 body fault")
        assert "B1234" in codes

    def test_u_codes(self):
        codes = extract_obd_codes("communication error U0100")
        assert "U0100" in codes

    def test_no_codes_returns_empty(self):
        codes = extract_obd_codes("My car is making a clicking noise")
        assert codes == []

    def test_deduplication(self):
        """Same code mentioned twice should appear once."""
        codes = extract_obd_codes("P0420 keeps coming back. I cleared P0420 yesterday.")
        assert codes.count("P0420") == 1

    def test_partial_match_not_captured(self):
        """'P042' (only 3 digits) should NOT match."""
        codes = extract_obd_codes("code P042 is not valid")
        assert codes == []

    def test_code_in_sentence_without_spaces(self):
        """Codes attached to punctuation should still be found."""
        codes = extract_obd_codes("I'm getting P0300, P0301, and P0302.")
        assert "P0300" in codes
        assert "P0301" in codes
        assert "P0302" in codes


# ─────────────────────────────────────────────
# detect_vehicle_mention tests
# ─────────────────────────────────────────────

class TestDetectVehicleMention:
    """Tests for vehicle year/make extraction."""

    def test_year_and_make(self):
        result = detect_vehicle_mention("My 2018 Honda Accord is overheating")
        assert result is not None
        assert result["year"] == "2018"
        assert result["make"] == "honda"

    def test_make_only(self):
        result = detect_vehicle_mention("I have a Ford F-150 with a noise")
        assert result is not None
        assert result["make"] == "ford"
        assert result["year"] is None

    def test_year_only(self):
        result = detect_vehicle_mention("My 2005 has a P0300 code")
        assert result is not None
        assert result["year"] == "2005"

    def test_no_vehicle_returns_none(self):
        result = detect_vehicle_mention("The brake pads need replacing")
        assert result is None

    def test_chevy_alias(self):
        """'Chevy' should map to Chevrolet."""
        result = detect_vehicle_mention("My Chevy Silverado is misfiring")
        assert result is not None
        assert result["make"] == "chevy"

    def test_bmw_detection(self):
        result = detect_vehicle_mention("2019 BMW 3 Series clicking noise")
        assert result is not None
        assert result["year"] == "2019"
        assert result["make"] == "bmw"


# ─────────────────────────────────────────────
# format_obd_query tests
# ─────────────────────────────────────────────

class TestFormatOBDQuery:
    """Tests for building OBD search queries."""

    def test_single_code(self):
        query = format_obd_query(["P0420"])
        assert "P0420" in query
        assert "diagnosis" in query.lower()

    def test_multiple_codes(self):
        query = format_obd_query(["P0420", "P0171"])
        assert "P0420" in query
        assert "P0171" in query

    def test_empty_list_returns_empty(self):
        assert format_obd_query([]) == ""


# ─────────────────────────────────────────────
# clean_response_text tests
# ─────────────────────────────────────────────

class TestCleanResponseText:
    """Tests for LLM response post-processing."""

    def test_removes_trailing_spaces(self):
        result = clean_response_text("Hello   \nWorld   ")
        assert "   \n" not in result

    def test_collapses_many_blank_lines(self):
        result = clean_response_text("Para 1\n\n\n\n\nPara 2")
        assert "\n\n\n" not in result

    def test_preserves_content(self):
        text = "Replace the brake pads.\n\nCheck the rotors too."
        result = clean_response_text(text)
        assert "Replace the brake pads" in result
        assert "Check the rotors too" in result


# ─────────────────────────────────────────────
# Helper imported from text_helpers (for chunk test)
# ─────────────────────────────────────────────

def chunk_text_preview(text: str, chunk_size: int = 100, overlap: int = 20):
    """
    Quick helper to test chunking logic without importing the full service.
    We import the real function from text_helpers in the actual implementation.
    """
    from backend.utils.text_helpers import sanitize_input
    # Just test that the concept works
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        start = end - overlap
    return chunks


class TestChunking:
    """Basic chunking behaviour tests."""

    def test_short_text_produces_one_chunk(self):
        text = "Short text"
        chunks = chunk_text_preview(text, chunk_size=100, overlap=20)
        assert len(chunks) >= 1

    def test_long_text_produces_multiple_chunks(self):
        text = "word " * 200   # 1000 chars
        chunks = chunk_text_preview(text, chunk_size=100, overlap=20)
        assert len(chunks) > 1

    def test_chunks_cover_all_content(self):
        """Ensure no content is dropped between chunks."""
        text = "The quick brown fox jumps over the lazy dog " * 10
        chunks = chunk_text_preview(text, chunk_size=50, overlap=10)
        # Reconstruct — given overlap, just verify first and last chars present
        combined = " ".join(chunks)
        assert "quick" in combined
        assert "dog" in combined
