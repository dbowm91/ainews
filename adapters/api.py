import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import requests

from adapters.base import BaseSourceAdapter, RawItem, register_adapter
from adapters.session import get_crawl_session
from schemas.source import APIConfig
from utils.url import validate_url_safe

logger = logging.getLogger(__name__)


@register_adapter("api")
class APIAdapter(BaseSourceAdapter):
    config_class = APIConfig

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._session = get_crawl_session()
        self._user_agent = self.adapter_config.user_agent

    def close(self):
        pass

    def fetch(self) -> list[Any]:
        cfg = self.adapter_config
        validate_url_safe(cfg.list_url)

        all_items: list[Any] = []
        next_url = cfg.list_url
        pages_fetched = 0

        while next_url and pages_fetched < cfg.pagination.max_pages:
            self._current_url = next_url
            resp = self._session.get(next_url, headers={"User-Agent": self._user_agent}, timeout=cfg.request_timeout)
            resp.raise_for_status()
            data = resp.json()

            if cfg.list_method == "json_array":
                items = data if isinstance(data, list) else []
            elif cfg.list_method == "json_object_items" and cfg.list_items_path:
                items = self._resolve_path(data, cfg.list_items_path) or []
            else:
                items = data if isinstance(data, list) else []

            for item in items:
                if len(all_items) >= cfg.max_items:
                    break
                if self._passes_filters(item, cfg.filters):
                    all_items.append(item)

            if len(all_items) >= cfg.max_items:
                break

            pages_fetched += 1
            next_url = self._get_next_url(data, cfg.pagination, pages_fetched - 1)
            if next_url:
                validate_url_safe(next_url)

        if cfg.item_url:
            ext_id_path = cfg.fields.get("external_id", "$.id")
            if ext_id_path == "$.id":
                logger.warning(
                    "item_url is configured but external_id is not explicitly set. "
                    "Using default path '$.id' which may not exist in API response data."
                )

        if cfg.item_url and all_items:
            fetched = []
            for item in all_items[: cfg.max_items]:
                item_id = self._resolve_path(item, cfg.fields.get("external_id", "$.id"))
                if item_id:
                    fetched_item = self._fetch_item(item_id)
                    if fetched_item:
                        fetched.append(fetched_item)
            return fetched

        return all_items

    def _get_next_url(self, data: Any, pagination: Any, current_page: int) -> Optional[str]:
        if pagination.type == "next_link" and pagination.next_link_selector:
            result = self._resolve_path(data, pagination.next_link_selector)
            return result if isinstance(result, str) else None
        if pagination.type == "query_param":
            return self._increment_query_param(current_page)
        return None

    def _increment_query_param(self, page: int) -> str:
        from urllib.parse import parse_qs, urlencode, urlparse

        parsed = urlparse(self._current_url)
        qs = parse_qs(parsed.query)

        page_param = "page" if "page" in qs else "offset"
        qs[page_param] = [str(page + 1)]

        new_query = urlencode(qs, doseq=True)
        return parsed._replace(query=new_query).geturl()

    def parse_item(self, raw: Any) -> Optional[RawItem]:
        cfg = self.adapter_config

        ext_id = str(
            self._resolve_path(raw, cfg.fields.get("external_id", "$.id"))
            or hashlib.sha256(str(raw).encode()).hexdigest()[:16]
        )
        title = self._resolve_path(raw, cfg.fields.get("title", "$.title")) or ""
        if not title:
            return None

        # Published_at handling
        published = None
        pub_raw = self._resolve_path(raw, cfg.fields.get("published_at", "$.time"))
        if pub_raw:
            fmt = cfg.fields.get("published_at_format", "unix")
            if fmt == "unix":
                try:
                    published = datetime.fromtimestamp(float(pub_raw), tz=timezone.utc)
                except (ValueError, TypeError, OSError):
                    pass
            elif fmt == "iso":
                try:
                    raw_str = str(pub_raw).strip().replace("Z", "+00:00")
                    published = datetime.fromisoformat(raw_str)
                except (ValueError, TypeError):
                    pass

        # Score
        score_raw = self._resolve_path(raw, cfg.fields.get("raw_score", "$.score"))
        try:
            score = float(score_raw) if score_raw is not None else 0.0
        except (ValueError, TypeError):
            score = 0.0

        # Metadata
        raw_meta = {}
        for meta_key, meta_path in (cfg.metadata or {}).items():
            val = self._resolve_path(raw, meta_path)
            if val is not None:
                raw_meta[meta_key] = val

        # Velocity calculation for time-based scoring
        if published and score > 0:
            age_hours = max(
                (datetime.now(timezone.utc) - published).total_seconds() / 3600, 0.1
            )
            raw_meta["velocity"] = round(score / age_hours, 2)

        text_content = self._resolve_path(raw, cfg.fields.get("text_content", "$.text"))

        return RawItem(
            source_id=self.source_id,
            external_id=ext_id,
            title=str(title),
            url=self._resolve_path(raw, cfg.fields.get("url", "$.url")),
            author=self._resolve_path(raw, cfg.fields.get("author", "$.by")),
            published_at=published,
            text_content=self._truncate(str(text_content)) if text_content else None,
            raw_score=score,
            raw_metadata=raw_meta,
        )

    def _get_match_text(self, item: RawItem) -> str:
        if item.text_content:
            return f"{item.title} {item.text_content}"
        return item.title

    def _fetch_item(self, item_id: Any) -> Optional[dict[str, Any]]:
        # Note: Sequential fetching - could benefit from async/threaded fetching for large item counts
        cfg = self.adapter_config
        try:
            url = cfg.item_url.format(id=item_id)
            validate_url_safe(url)
            headers = {"User-Agent": self._user_agent}
            if cfg.api_key:
                if cfg.auth_header:
                    headers[cfg.auth_header] = f"Bearer {cfg.api_key}"
                else:
                    headers["Authorization"] = f"Bearer {cfg.api_key}"
            resp = self._session.get(url, headers=headers, timeout=cfg.request_timeout)
            if resp.ok:
                result = resp.json()
                return result if isinstance(result, dict) else None
        except requests.RequestException as e:
            logger.warning("Failed to fetch item from API: %s", type(e).__name__)
        return None

    @staticmethod
    def _resolve_path(data: Any, path: str) -> Any:
        if not path or not path.startswith("$"):
            return data
        parts = path.lstrip("$.").split(".")
        current = data
        for part in parts:
            if current is None:
                return None
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list) and part.isdigit():
                idx = int(part)
                current = current[idx] if idx < len(current) else None
            else:
                return None
        return current

    def _passes_filters(self, data: Any, filters: list[dict]) -> bool:
        if not filters:
            return True
        for f in filters:
            current = self._resolve_path(data, f.get("field", ""))
            if "equals" in f and current != f["equals"]:
                return False
            if "min" in f:
                try:
                    if float(current) < f["min"]:
                        return False
                except (ValueError, TypeError):
                    return False
            if "exists" in f and f["exists"] and current is None:
                return False
            if "contains" in f and f["contains"] not in str(current):
                return False
        return True
