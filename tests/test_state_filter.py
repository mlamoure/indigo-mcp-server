"""
Tests for StateFilter type-coercion.

Indigo stores every variable value as a string ("true", "75", ...), while
conditions are typically supplied with native types (True, 50). These tests
cover the coercion that makes comparisons type-tolerant, plus regression
guards proving already-typed device states still behave.
"""

import sys
from pathlib import Path


plugin_path = Path(__file__).parent.parent / "MCP Server.indigoPlugin/Contents/Server Plugin"
sys.path.insert(0, str(plugin_path))

from mcp_server.common.state_filter import StateFilter


class TestBoolStringEquality:
    """Boolean condition vs. string variable value."""

    def test_bool_true_matches_string_true(self):
        assert StateFilter.matches_state({"value": "true"}, {"value": True}) is True

    def test_bool_true_does_not_match_string_false(self):
        assert StateFilter.matches_state({"value": "false"}, {"value": True}) is False

    def test_bool_false_matches_string_false(self):
        assert StateFilter.matches_state({"value": "false"}, {"value": False}) is True

    def test_bool_true_matches_alternate_truthy_strings(self):
        for truthy in ("True", "1", "yes", "on", "ON"):
            assert StateFilter.matches_state({"value": truthy}, {"value": True}) is True

    def test_bool_true_no_match_for_uncoercible_string(self):
        assert StateFilter.matches_state({"value": "maybe"}, {"value": True}) is False

    def test_eq_operator_bool_intent(self):
        assert StateFilter.matches_state({"value": "true"}, {"value": {"eq": True}}) is True

    def test_ne_operator_bool_intent(self):
        # "false" != True -> ne should match
        assert StateFilter.matches_state({"value": "false"}, {"value": {"ne": True}}) is True
        # "true" != True is False -> ne should NOT match
        assert StateFilter.matches_state({"value": "true"}, {"value": {"ne": True}}) is False


class TestNumericOnStringValues:
    """Numeric operators against string variable values."""

    def test_gt_match(self):
        assert StateFilter.matches_state({"value": "75"}, {"value": {"gt": 50}}) is True

    def test_gt_no_match(self):
        assert StateFilter.matches_state({"value": "40"}, {"value": {"gt": 50}}) is False

    def test_lexicographic_bug_fixed(self):
        # Lexicographically "100" < "99" (wrong); numerically 100 > 99 (right).
        assert StateFilter.matches_state({"value": "100"}, {"value": {"gt": 99}}) is True

    def test_uncoercible_value_no_match_no_raise(self):
        # Must not raise TypeError; just fails to match.
        assert StateFilter.matches_state({"value": "hello"}, {"value": {"gt": 50}}) is False

    def test_gte_lte_boundaries(self):
        assert StateFilter.matches_state({"value": "50"}, {"value": {"gte": 50}}) is True
        assert StateFilter.matches_state({"value": "50"}, {"value": {"lte": 50}}) is True
        assert StateFilter.matches_state({"value": "50"}, {"value": {"lt": 50}}) is False

    def test_float_string(self):
        assert StateFilter.matches_state({"value": "72.5"}, {"value": {"gt": 72}}) is True

    def test_eq_numeric_intent(self):
        assert StateFilter.matches_state({"value": "42"}, {"value": {"eq": 42}}) is True
        assert StateFilter.matches_state({"value": "42"}, {"value": 42}) is True


class TestStringEquality:
    """Plain string equality still works."""

    def test_exact_string_match(self):
        assert StateFilter.matches_state({"value": "open"}, {"value": "open"}) is True

    def test_string_mismatch(self):
        assert StateFilter.matches_state({"value": "open"}, {"value": "closed"}) is False

    def test_contains(self):
        assert StateFilter.matches_state({"value": "garage open"}, {"value": {"contains": "open"}}) is True

    def test_regex(self):
        assert StateFilter.matches_state({"value": "ABC123"}, {"value": {"regex": r"ABC\d+"}}) is True


class TestDeviceRegressionGuards:
    """Already-typed device states must behave exactly as before."""

    def test_onstate_bool_direct(self):
        assert StateFilter.matches_state({"onState": True}, {"onState": True}) is True
        assert StateFilter.matches_state({"onState": False}, {"onState": True}) is False

    def test_numeric_state_direct(self):
        assert StateFilter.matches_state({"brightnessLevel": 75}, {"brightnessLevel": {"gt": 50}}) is True
        assert StateFilter.matches_state({"brightnessLevel": 30}, {"brightnessLevel": {"gt": 50}}) is False

    def test_states_dict_lookup(self):
        entity = {"states": {"sensorValue": 80}}
        assert StateFilter.matches_state(entity, {"sensorValue": {"gte": 80}}) is True

    def test_empty_conditions_match_all(self):
        assert StateFilter.matches_state({"value": "anything"}, {}) is True

    def test_missing_key_fails(self):
        assert StateFilter.matches_state({"value": "x"}, {"nonexistent": "y"}) is False


class TestCoercionHelpers:
    """Direct unit tests of the helpers."""

    def test_to_bool(self):
        assert StateFilter._to_bool(True) is True
        assert StateFilter._to_bool("true") is True
        assert StateFilter._to_bool("off") is False
        assert StateFilter._to_bool("") is False
        assert StateFilter._to_bool("garbage") is None

    def test_to_number(self):
        assert StateFilter._to_number(5) == 5.0
        assert StateFilter._to_number("5.5") == 5.5
        assert StateFilter._to_number("nope") is None
        # bool is intentionally not a number
        assert StateFilter._to_number(True) is None

    def test_values_equal(self):
        assert StateFilter._values_equal("true", True) is True
        assert StateFilter._values_equal("75", 75) is True
        assert StateFilter._values_equal("open", "open") is True
        assert StateFilter._values_equal("open", "closed") is False
