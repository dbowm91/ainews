from services.provider_base import BaseProvider, ProviderManager


class _ClosableProvider(BaseProvider):
    def __init__(self, provider_id: str):
        super().__init__(provider_id, {})
        self.close_count = 0

    def close(self) -> None:
        self.close_count += 1


def test_clear_cache_retires_provider_until_process_close():
    manager = ProviderManager("test", retire_on_clear=True)
    provider = _ClosableProvider("local")
    manager._cache[provider.provider_id] = provider

    manager.clear_cache()

    assert manager._cache == {}
    assert provider.close_count == 0

    manager.close_all()
    assert provider.close_count == 1


def test_close_all_closes_provider_once_when_cached_and_retired():
    manager = ProviderManager("test")
    provider = _ClosableProvider("local")
    manager._cache[provider.provider_id] = provider
    manager._retired.append(provider)

    manager.close_all()

    assert provider.close_count == 1


def test_default_manager_preserves_immediate_cache_close_behavior():
    manager = ProviderManager("test")
    provider = _ClosableProvider("search")
    manager._cache[provider.provider_id] = provider

    manager.clear_cache()

    assert provider.close_count == 1
