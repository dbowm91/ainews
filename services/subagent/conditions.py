from __future__ import annotations

import ast
import logging
import operator
from typing import Any

logger = logging.getLogger(__name__)


def _eval_handle_expression(node: ast.Expression, eval_node_fn) -> Any:
    return eval_node_fn(node.body)


def _eval_handle_bool_op(node: ast.BoolOp, eval_node_fn, allowed_ops) -> Any:
    values = [eval_node_fn(v) for v in node.values]
    if isinstance(node.op, ast.And):
        return all(values)
    elif isinstance(node.op, ast.Or):
        return any(values)
    raise ValueError(f"Unsupported boolean operator: {type(node.op).__name__}")


def _eval_handle_unary_not(node: ast.UnaryOp, eval_node_fn) -> Any:
    return not eval_node_fn(node.operand)


def _eval_handle_compare(node: ast.Compare, eval_node_fn, allowed_ops) -> Any:
    left = eval_node_fn(node.left)
    for op_node, comparator in zip(node.ops, node.comparators):
        op = allowed_ops[type(op_node)]
        right = eval_node_fn(comparator)
        logger.debug("Compare: left=%s, right=%s, op=%s, result=%s", left, right, op, op(left, right))
        if not op(left, right):
            return False
        left = right
    return True


def _eval_handle_name(node: ast.Name, allowed_names, context) -> Any:
    if node.id not in allowed_names:
        raise ValueError(f"Unknown identifier: {node.id}")
    if node.id in ("results", "previous"):
        return context.get(node.id, context)
    result = context.get(node.id)
    if result is None:
        raise ValueError(f"Context has no key '{node.id}'")
    return result


def _eval_handle_constant(node: ast.Constant) -> Any:
    return node.value


def _eval_handle_attribute(node: ast.Attribute, eval_node_fn, context) -> Any:
    obj = eval_node_fn(node.value)
    if isinstance(obj, dict) and node.attr in obj:
        return obj[node.attr]
    if obj is None:
        return {}
    if node.attr.startswith("__") or node.attr.startswith("_"):
        raise ValueError(f"Access to protected attribute '{node.attr}' is not allowed")
    try:
        return getattr(obj, node.attr)
    except AttributeError:
        if isinstance(obj, dict):
            raise
        if node.attr in context:
            return context[node.attr]
        raise


def _eval_handle_subscript(node: ast.Subscript, eval_node_fn) -> Any:
    obj = eval_node_fn(node.value)
    idx = eval_node_fn(node.slice)
    logger.debug("Subscript: obj=%s, idx=%s, obj type=%s", obj, idx, type(obj))
    if isinstance(obj, dict):
        return obj[idx]
    elif isinstance(obj, (list, tuple)):
        if isinstance(idx, int):
            return obj[idx]
        raise ValueError("List index must be an integer")
    raise ValueError("Subscript target must be dict or list")


def _eval_node(
    node: ast.AST,
    allowed_ops: dict,
    allowed_names: set,
    context: dict,
) -> Any:
    """Recursively evaluate an AST node with given allowed ops/names/context."""
    # Create a callback with the extra arguments bound
    def _eval(node: ast.AST) -> Any:
        return _eval_node(node, allowed_ops, allowed_names, context)

    node_type = type(node)
    if node_type is ast.Expression:
        return _eval_handle_expression(node, _eval)
    elif node_type is ast.BoolOp:
        return _eval_handle_bool_op(node, _eval, allowed_ops)
    elif node_type is ast.UnaryOp:
        if isinstance(node.op, ast.Not):
            return _eval_handle_unary_not(node, _eval)
        else:
            raise ValueError("Unary operations not allowed in conditions")
    elif node_type is ast.Compare:
        return _eval_handle_compare(node, _eval, allowed_ops)
    elif node_type is ast.Name:
        return _eval_handle_name(node, allowed_names, context)
    elif node_type is ast.Constant:
        return _eval_handle_constant(node)
    elif node_type is ast.Attribute:
        return _eval_handle_attribute(node, _eval, context)
    elif node_type is ast.Subscript:
        return _eval_handle_subscript(node, _eval)
    elif node_type in (ast.Call, ast.Lambda, ast.BinOp):
        disallowed_msgs = {
            ast.Call: "Function calls not allowed in conditions",
            ast.Lambda: "Lambda expressions not allowed in conditions",
            ast.BinOp: "Binary operations not allowed in conditions",
        }
        raise ValueError(disallowed_msgs[node_type])
    else:
        raise ValueError(f"Unsupported node type: {node_type.__name__}")


def _evaluate_condition(condition: str, context: dict[str, Any]) -> bool:
    """Evaluate a condition expression against the context using AST-based parsing."""
    _ALLOWED_OPS = {
        ast.Eq: operator.eq,
        ast.NotEq: operator.ne,
        ast.Lt: operator.lt,
        ast.LtE: operator.le,
        ast.Gt: operator.gt,
        ast.GtE: operator.ge,
        ast.Not: operator.not_,
        ast.In: lambda a, b: a in b,
        ast.NotIn: lambda a, b: a not in b,
    }

    _ALLOWED_NAMES = {"True", "False", "None", "results", "previous"}

    try:
        tree = ast.parse(condition, mode="eval")
    except (SyntaxError, ValueError):
        return False

    try:
        return bool(_eval_node(tree, _ALLOWED_OPS, _ALLOWED_NAMES, context))
    except ValueError as e:
        if any(seg in str(e) for seg in ("Unsupported node type", "not allowed")):
            raise
        return False
    except (TypeError, AttributeError) as e:
        logger.debug("Condition evaluation failed for '%s': %s", condition, e)
        return False
