import importlib.util

if importlib.util.find_spec("aiohttp"):
    from .aiohttp_client_impl import AioHttpClientImpl as ClientImpl
else:
    from .legacy_client_impl import LegacyClientImpl as ClientImpl
