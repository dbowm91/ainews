import threading
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_CRAWL_SESSION: requests.Session | None = None
_CRAWL_SESSION_LOCK = threading.Lock()


def get_crawl_session() -> requests.Session:
    global _CRAWL_SESSION
    if _CRAWL_SESSION is None:
        with _CRAWL_SESSION_LOCK:
            if _CRAWL_SESSION is None:
                _CRAWL_SESSION = requests.Session()
                retry = Retry(
                    total=3,
                    backoff_factor=1,
                    status_forcelist=[500, 502, 503, 504],
                )
                adapter = HTTPAdapter(
                    pool_connections=10,
                    pool_maxsize=20,
                    max_retries=retry,
                )
                _CRAWL_SESSION.mount("http://", adapter)
                _CRAWL_SESSION.mount("https://", adapter)
    return _CRAWL_SESSION