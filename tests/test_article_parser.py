"""Tests for article parser service."""

import json
from unittest.mock import MagicMock


class TestArticleParser:
    def test_parse_article_json_with_valid_json(self):
        from services.article_parser import parse_article_json

        article = MagicMock()
        article.final_article = json.dumps({"headline": "Test", "tldr": "Summary"})
        article.summary = None

        parse_article_json(article)

        assert article._fa == {"headline": "Test", "tldr": "Summary"}
        assert article._summary is None

    def test_parse_article_json_with_invalid_json(self):
        from services.article_parser import parse_article_json

        article = MagicMock()
        article.final_article = "not json"
        article.summary = "also not json"

        parse_article_json(article)

        assert article._fa is None
        assert article._summary is None

    def test_parse_article_json_with_none(self):
        from services.article_parser import parse_article_json

        article = MagicMock()
        article.final_article = None
        article.summary = None

        parse_article_json(article)

        assert article._fa is None
        assert article._summary is None

    def test_parse_articles_batch(self):
        from services.article_parser import parse_articles

        articles = []
        for i in range(3):
            a = MagicMock()
            a.final_article = json.dumps({"headline": f"Article {i}"})
            a.summary = None
            articles.append(a)

        result = parse_articles(articles)

        assert len(result) == 3
        for i, a in enumerate(result):
            assert a._fa["headline"] == f"Article {i}"
