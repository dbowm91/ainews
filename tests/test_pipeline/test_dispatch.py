from unittest.mock import patch, MagicMock


class TestDispatchNextCache:
    """Test _task_fn_cache population and clear_task_fn_cache()."""

    @staticmethod
    def _get_cache():
        import tasks.pipeline as tp

        return tp._task_fn_cache

    def test_dispatch_populates_cache(self):
        from tasks.pipeline import _dispatch_next, clear_task_fn_cache

        clear_task_fn_cache()
        cache = self._get_cache()
        assert len(cache) == 0

        mock_task = MagicMock()
        mock_module = MagicMock(select_article=mock_task)
        with patch("importlib.import_module", return_value=mock_module):
            _dispatch_next(1, next_status="pending")

        assert "pending" in cache
        mock_task.apply_async.assert_called_once_with(args=[1], kwargs={"run_id": None}, headers=None)

    def test_clear_empties_cache(self):
        from tasks.pipeline import clear_task_fn_cache

        cache = self._get_cache()
        cache["pending"] = ("mod", "fn")
        cache["selected"] = ("mod2", "fn2")
        assert len(cache) == 2

        clear_task_fn_cache()

        assert len(self._get_cache()) == 0

    def test_dispatch_reuses_cached_entry(self):
        from tasks.pipeline import _dispatch_next, clear_task_fn_cache

        clear_task_fn_cache()

        mock_task = MagicMock()
        mock_module = MagicMock(research_article=mock_task)
        with patch("importlib.import_module", return_value=mock_module):
            _dispatch_next(1, next_status="selected")
            _dispatch_next(2, next_status="selected")

        assert len(self._get_cache()) == 1
        assert mock_task.apply_async.call_count == 2

    def test_clear_allows_repopulation(self):
        from tasks.pipeline import _dispatch_next, clear_task_fn_cache

        mock_task = MagicMock()
        mock_module = MagicMock(write_article=mock_task)

        clear_task_fn_cache()
        with patch("importlib.import_module", return_value=mock_module):
            _dispatch_next(1, next_status="writing")

        assert "writing" in self._get_cache()

        clear_task_fn_cache()
        assert len(self._get_cache()) == 0

        with patch("importlib.import_module", return_value=mock_module):
            _dispatch_next(2, next_status="writing")

        assert "writing" in self._get_cache()
