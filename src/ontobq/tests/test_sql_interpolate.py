"""Interpolator quoting and comment scanning. No mocks."""

from __future__ import annotations

import pytest  # pyright: ignore[reportMissingImports]

from ontobq.ir import ColumnMapping, ExpressionMapping
from ontobq.sql.interpolate import quote_identifier, render_mapping_value, select_item


def test_quote_identifier_backticks_reserved_keywords() -> None:
    assert quote_identifier("SELECT") == "`SELECT`"
    assert quote_identifier("from") == "`from`"
    assert quote_identifier("Select") == "`Select`"
    assert quote_identifier("FROM") == "`FROM`"
    assert quote_identifier("customer_id") == "customer_id"
    assert quote_identifier("id") == "id"


def test_quote_identifier_still_quotes_unsafe_names() -> None:
    assert quote_identifier("from-col") == "`from-col`"
    assert quote_identifier("1id") == "`1id`"


def test_select_item_quotes_reserved_column_and_alias() -> None:
    item = select_item(ColumnMapping(column="FROM"), "SELECT")
    assert item == "`FROM` AS `SELECT`"


def test_block_comment_may_contain_as_and_comma() -> None:
    as_comment = ExpressionMapping(expression="value /* AS alias */")
    comma_comment = ExpressionMapping(expression="value /* note, retained */")
    assert render_mapping_value(as_comment) == "value /* AS alias */"
    assert render_mapping_value(comma_comment) == "value /* note, retained */"
    assert select_item(as_comment, "id") == "value /* AS alias */ AS id"
    assert select_item(comma_comment, "id") == "value /* note, retained */ AS id"


def test_unterminated_block_comment_is_rejected() -> None:
    with pytest.raises(ValueError, match="unterminated block comment"):
        render_mapping_value(ExpressionMapping(expression="value /* oops"))


def test_quoted_block_comment_text_is_not_scanned_as_comment() -> None:
    expression = "'/* AS , */'"
    assert render_mapping_value(ExpressionMapping(expression=expression)) == expression
