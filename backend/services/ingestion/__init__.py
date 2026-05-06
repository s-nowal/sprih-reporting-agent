"""Ingestion sub-package — raw data collection and bronze storage pipeline.

Sub-modules:
- store: check_duplicate, store_page, store_binary (bronze S3 + data_sources DB)
- search: record_search_query, get_search_result, search_web (Serper API + provenance)
- crawl: fetch_url, binary download, web crawl (httpx + crawl4ai)
- source: SourceService stub (enterprise upload handling, pending implementation)
"""
