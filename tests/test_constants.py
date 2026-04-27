import pytest
from constants import PipelineStatus, VALID_TRANSITIONS
from tasks.pipeline import InvalidStateTransitionError, _transition_article_status


class DummyArticle:
    def __init__(self, id=None):
        self.pipeline_status = None
        self.id = id

    def __repr__(self):
        return f"DummyArticle(id={self.id}, pipeline_status={self.pipeline_status})"


class TestPipelineStatusTransitions:
    def test_pending_to_review_succeeds(self, app):
        with app.app_context():
            article = DummyArticle()
            article.pipeline_status = PipelineStatus.PENDING
            _transition_article_status(article, PipelineStatus.REVIEW)
            assert article.pipeline_status == PipelineStatus.REVIEW

    def test_pending_to_research_succeeds(self, app):
        with app.app_context():
            article = DummyArticle()
            article.pipeline_status = PipelineStatus.PENDING
            _transition_article_status(article, PipelineStatus.RESEARCHING)
            assert article.pipeline_status == PipelineStatus.RESEARCHING

    def test_pending_to_invalid_raises(self, app):
        with app.app_context():
            article = DummyArticle(id=1)
            article.pipeline_status = PipelineStatus.PENDING
            with pytest.raises(InvalidStateTransitionError):
                _transition_article_status(article, PipelineStatus.WRITING)

    def test_valid_transitions_dict_structure(self):
        assert PipelineStatus.PENDING in VALID_TRANSITIONS
        assert PipelineStatus.REVIEW in VALID_TRANSITIONS[PipelineStatus.PENDING]
        assert PipelineStatus.RESEARCHING in VALID_TRANSITIONS[PipelineStatus.PENDING]