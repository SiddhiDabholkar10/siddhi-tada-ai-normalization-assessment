"""Crawl plans, one per provider (D-092). Each module declares ``PROVIDER``, ``ROUTES`` (exactly the
selected routes of ``mappings/data/<provider>/routes.json``), ``QUERY`` (each route's fixed query
parameters, also used by the fixture generator so fixtures record what the live fetch sends),
``PAGE_SIZES`` and ``crawl(c)``."""
