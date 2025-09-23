"""
Geographical utilities for network optimization.
"""

import os
import asyncio
import aiohttp
from typing import Optional, Dict, Any
import warnings


class GeoDetector:
    """Detect user's geographical location for network optimization."""

    _is_china_mainland: Optional[bool] = None
    _detection_attempted = False

    @classmethod
    def is_china_mainland(cls) -> Optional[bool]:
        """
        Check if the user is in China mainland.

        Returns:
            True if in China mainland, False if not, None if detection failed/disabled
        """
        return cls._is_china_mainland

    @classmethod
    async def detect_location(cls, timeout: float = 5.0) -> Optional[bool]:
        """
        Detect if user is in China mainland.

        Args:
            timeout: Detection timeout in seconds

        Returns:
            True if in China mainland, False if not, None if detection failed
        """
        if cls._detection_attempted:
            return cls._is_china_mainland

        cls._detection_attempted = True

        # Check if detection is disabled via environment variable
        if os.getenv("TRIPO_DISABLE_GEO_DETECTION", "").lower() in ("1", "true", "yes"):
            return None

        try:
            # Try multiple detection methods
            result = await cls._detect_via_api(timeout)
            if result is not None:
                cls._is_china_mainland = result
                return result

            # Fallback to DNS-based detection
            result = await cls._detect_via_dns(timeout)
            if result is not None:
                cls._is_china_mainland = result
                return result

        except Exception:
            # Silently fail detection
            pass

        return None

    @classmethod
    async def _detect_via_api(cls, timeout: float) -> Optional[bool]:
        """Detect location via IP geolocation API."""
        apis = [
            "http://ip-api.com/json/?fields=countryCode",
            "https://ipapi.co/json/",
            "http://ipinfo.io/json"
        ]

        connector = aiohttp.TCPConnector(limit=1, limit_per_host=1)
        client_timeout = aiohttp.ClientTimeout(total=timeout, connect=timeout/2)

        try:
            async with aiohttp.ClientSession(
                connector=connector,
                timeout=client_timeout
            ) as session:
                for api_url in apis:
                    try:
                        async with session.get(api_url) as response:
                            if response.status == 200:
                                data = await response.json()

                                # Check different response formats
                                country_code = (
                                    data.get("countryCode") or
                                    data.get("country_code") or
                                    data.get("country")
                                )

                                if country_code:
                                    return country_code.upper() == "CN"

                    except Exception:
                        continue  # Try next API

        except Exception:
            pass

        return None

    @classmethod
    async def _detect_via_dns(cls, timeout: float) -> Optional[bool]:
        """Detect location via DNS resolution patterns."""
        try:
            import socket

            # Test if we can resolve China-specific domains quickly
            china_domains = ["baidu.com", "qq.com", "taobao.com"]
            global_domains = ["google.com", "facebook.com", "twitter.com"]

            china_resolve_count = 0
            global_resolve_count = 0

            # Test China domains
            for domain in china_domains:
                try:
                    socket.getaddrinfo(domain, 80, family=socket.AF_INET,
                                     proto=socket.IPPROTO_TCP)
                    china_resolve_count += 1
                except Exception:
                    pass

            # Test global domains (often blocked in China)
            for domain in global_domains:
                try:
                    socket.getaddrinfo(domain, 80, family=socket.AF_INET,
                                     proto=socket.IPPROTO_TCP)
                    global_resolve_count += 1
                except Exception:
                    pass

            # Heuristic: if we can resolve most China domains but few global ones
            if china_resolve_count >= 2 and global_resolve_count <= 1:
                return True
            elif global_resolve_count >= 2:
                return False

        except Exception:
            pass

        return None


def detect_china_mainland_sync(timeout: float = 3.0) -> Optional[bool]:
    """
    Synchronous wrapper for China mainland detection.

    Args:
        timeout: Detection timeout in seconds

    Returns:
        True if in China mainland, False if not, None if detection failed
    """
    try:
        # Try to use existing event loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If loop is running, create a task but don't wait
            # This prevents blocking during import
            return None
        else:
            return loop.run_until_complete(GeoDetector.detect_location(timeout))
    except RuntimeError:
        # No event loop, create a new one
        try:
            return asyncio.run(GeoDetector.detect_location(timeout))
        except Exception:
            return None
    except Exception:
        return None


# Global variable to store detection result
_IS_CHINA_MAINLAND: Optional[bool] = None

def get_china_mainland_status() -> Optional[bool]:
    """Get the cached China mainland detection result."""
    return _IS_CHINA_MAINLAND

def set_china_mainland_status(status: Optional[bool]) -> None:
    """Manually set the China mainland status (for testing or manual override)."""
    global _IS_CHINA_MAINLAND
    _IS_CHINA_MAINLAND = status
    GeoDetector._is_china_mainland = status
    GeoDetector._detection_attempted = True
