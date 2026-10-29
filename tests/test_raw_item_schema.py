"""Tests for the raw item schema.

The raw item schema is the single ingress point for crawled text, so it is
where escaped text is normalised. A title that arrives HTML-escaped would
otherwise be stored verbatim and then escaped again by the template, which
shows the entity to the reader (``Amazon&#8217;s``).
"""

from __future__ import annotations

from schemas.item import RawItem


def _item(**overrides: object) -> RawItem:
    data: dict = {
        "source_id": "src",
        "external_id": "ext",
        "title": "Plain title",
    }
    data.update(overrides)
    return RawItem(**data)


class TestEntityDecoding:
    def test_numeric_entity_is_decoded(self):
        item = _item(title="Everything announced at Amazon&#8217;s event")
        assert item.title == "Everything announced at Amazon’s event"

    def test_named_entity_is_decoded(self):
        item = _item(title="Tom &amp; Jerry &quot;again&quot;")
        assert item.title == 'Tom & Jerry "again"'

    def test_double_escaped_text_is_decoded_once(self):
        item = _item(title="Tom &amp;amp; Jerry")
        assert item.title == "Tom &amp; Jerry"

    def test_plain_ampersand_is_left_alone(self):
        item = _item(title="AT&T and Rooms & Co")
        assert item.title == "AT&T and Rooms & Co"

    def test_text_without_entities_is_unchanged(self):
        item = _item(title="A perfectly normal headline")
        assert item.title == "A perfectly normal headline"

    def test_author_is_decoded(self):
        item = _item(author="Jane &amp; John Doe")
        assert item.author == "Jane & John Doe"

    def test_none_author_is_preserved(self):
        item = _item(author=None)
        assert item.author is None

    def test_title_is_required(self):
        import pydantic

        try:
            _item(title=None)
        except pydantic.ValidationError:
            return
        raise AssertionError("a null title must be rejected")
