"""Tests for AST-based condition evaluation (W1.3/W1.4)."""
import pytest

from services.subagent import _evaluate_condition


class TestEvaluateConditionPositive:
    """Positive test cases - conditions that should evaluate to True."""

    def test_numeric_less_than(self):
        context = {"count": 5, "status": "active"}
        assert _evaluate_condition("results.count < 10", context) is True
        assert _evaluate_condition("results.count < 3", context) is False

    def test_numeric_greater_than(self):
        context = {"count": 5, "status": "active"}
        assert _evaluate_condition("results.count > 3", context) is True
        assert _evaluate_condition("results.count > 7", context) is False

    def test_numeric_less_than_or_equal(self):
        context = {"count": 5}
        assert _evaluate_condition("results.count <= 5", context) is True
        assert _evaluate_condition("results.count <= 4", context) is False

    def test_numeric_greater_than_or_equal(self):
        context = {"count": 5}
        assert _evaluate_condition("results.count >= 5", context) is True
        assert _evaluate_condition("results.count >= 6", context) is False

    def test_numeric_equality(self):
        context = {"count": 5, "status": "active"}
        assert _evaluate_condition("results.count == 5", context) is True
        assert _evaluate_condition("results.count == 6", context) is False

    def test_numeric_inequality(self):
        context = {"count": 5}
        assert _evaluate_condition("results.count != 6", context) is True
        assert _evaluate_condition("results.count != 5", context) is False

    def test_string_equality(self):
        context = {"status": "active"}
        assert _evaluate_condition("results.status == 'active'", context) is True
        assert _evaluate_condition("results.status == 'pending'", context) is False

    def test_string_inequality(self):
        context = {"status": "active"}
        assert _evaluate_condition("results.status != 'pending'", context) is True

    def test_boolean_and(self):
        context = {"count": 5, "status": "active"}
        assert (
            _evaluate_condition(
                "results.count > 3 and results.status == 'active'", context
            )
            is True
        )
        assert (
            _evaluate_condition(
                "results.count > 3 and results.status == 'pending'", context
            )
            is False
        )

    def test_boolean_or(self):
        context = {"count": 5, "status": "active"}
        assert (
            _evaluate_condition(
                "results.count > 10 or results.status == 'active'", context
            )
            is True
        )
        assert (
            _evaluate_condition(
                "results.count > 10 or results.status == 'pending'", context
            )
            is False
        )

    def test_boolean_not(self):
        context = {"status": "active"}
        assert _evaluate_condition("not results.status == 'pending'", context) is True
        assert _evaluate_condition("not results.status == 'active'", context) is False

    def test_attribute_access(self):
        class User:
            name = "Alice"

        context = {"user": User(), "count": 5}
        assert _evaluate_condition("results.user.name == 'Alice'", context) is True
        assert _evaluate_condition("results.user.name == 'Bob'", context) is False

    def test_dictionary_key_access(self):
        context = {"data": {"key": "value", "count": 42}}
        assert _evaluate_condition("results['data']['key'] == 'value'", context) is True
        assert _evaluate_condition("results['data']['count'] == 42", context) is True
        assert _evaluate_condition("results['data']['count'] == 0", context) is False

    def test_list_index_access(self):
        context = {"items": [10, 20, 30], "name": "test"}
        assert _evaluate_condition("results.items[0] == 10", context) is True
        assert _evaluate_condition("results.items[1] == 20", context) is True
        assert _evaluate_condition("results.items[2] == 30", context) is True
        assert _evaluate_condition("results.items[2] == 40", context) is False

    def test_in_operator(self):
        context = {
            "status": "active",
            "valid_statuses": ["active", "pending", "review"],
        }
        assert (
            _evaluate_condition("results.status in results.valid_statuses", context)
            is True
        )
        assert (
            _evaluate_condition("results.status not in results.valid_statuses", context)
            is False
        )

    def test_not_in_operator(self):
        context = {
            "status": "deleted",
            "valid_statuses": ["active", "pending", "review"],
        }
        assert (
            _evaluate_condition("results.status not in results.valid_statuses", context)
            is True
        )

    def test_chained_comparisons(self):
        context = {"count": 5}
        assert _evaluate_condition("0 < results.count < 10", context) is True
        assert _evaluate_condition("0 < results.count < 3", context) is False

    def test_complex_nested(self):
        context = {"a": True, "b": False, "count": 10}
        result = _evaluate_condition(
            "(results.a and results.count > 5) or results.b", context
        )
        assert result is True


class TestEvaluateConditionNegative:
    """Negative test cases - should raise ValueError for unsafe constructs."""

    def test_function_call(self):
        context = {"count": 5}
        with pytest.raises(ValueError, match="Function calls not allowed"):
            _evaluate_condition("len(results)", context)
        with pytest.raises(ValueError):
            _evaluate_condition("results.count.__class__", context)

    def test_dunder_access(self):
        context = {"count": 5}
        with pytest.raises(ValueError):
            _evaluate_condition("results.__class__", context)
        with pytest.raises(ValueError):
            _evaluate_condition("results.__init__", context)
        with pytest.raises(ValueError):
            _evaluate_condition("results.__builtins__", context)

    def test_lambda_definition(self):
        context = {"count": 5}
        with pytest.raises(ValueError, match="Lambda expressions not allowed"):
            _evaluate_condition("lambda x: x", context)

    def test_assignment(self):
        context = {"count": 5}
        assert _evaluate_condition("x = 5", context) is False

    def test_subscript_assignment(self):
        context = {"data": {}}
        assert _evaluate_condition("results['data']['key'] = 'value'", context) is False

    def test_subscript_with_non_constant_index(self):
        context = {"data": {"key": "value"}, "idx": 0}
        assert _evaluate_condition("results['data'][results.idx]", context) is False


class TestEvaluateConditionEdgeCases:
    """Edge cases - should return False gracefully."""

    def test_empty_condition(self):
        context = {"count": 5}
        assert _evaluate_condition("", context) is False

    def test_whitespace_only(self):
        context = {"count": 5}
        assert _evaluate_condition("   ", context) is False

    def test_nonexistent_key(self):
        context = {"count": 5}
        assert _evaluate_condition("results.nonexistent == 'value'", context) is False

    def test_missing_result_key(self):
        context = {}
        assert _evaluate_condition("results.count > 5", context) is False

    def test_invalid_syntax(self):
        context = {"count": 5}
        assert _evaluate_condition("count >>> 5", context) is False

    def test_unknown_operator(self):
        context = {"count": 5}
        with pytest.raises(ValueError):
            _evaluate_condition("results.count ** 2", context)

    def test_unsupported_node_type(self):
        context = {"count": 5}
        assert _evaluate_condition("yield results.count", context) is False


class TestEvaluateConditionSpecialValues:
    """Test special Python values."""

    def test_true_literal(self):
        context = {"flag": True}
        assert _evaluate_condition("results.flag == True", context) is True

    def test_false_literal(self):
        context = {"flag": False}
        assert _evaluate_condition("results.flag == False", context) is True

    def test_none_literal(self):
        context = {"value": None}
        assert _evaluate_condition("results.value == None", context) is True
