__all__ = ["APIAdapter", "RSSAdapter", "WebAdapter", "get_adapter_class", "SOURCE_ADAPTERS"]

import adapters.api
import adapters.rss
import adapters.web  # noqa: F401, RUF100
