# ic-engine v4.0-cpu — Bill of Materials & Trim Audit

**Image:** `mnemos-os/ic-engine:4.0-cpu` (2.27 GB compressed)  
**Digest:** `sha256:0510c3016f03fe35d7c59b8433a6494253de1892cce2be2029a0e5974b9d1e03`  
**Generated:** 2026-05-01T07:04:36.399831+00:00  
**Total Python packages:** 164

## Trim-audit candidates (by size, descending)

These are the high-cost packages flagged for the ic-engine maintainer to review for actual usage. The recommendations are not prescriptive — the maintainer is the source of truth on whether each package is load-bearing for the deterministic-engine path.

| Package | Version | Size (MB) | License | Trim recommendation |
|---|---|---:|---|---|
| `torch` | 2.11.0+cpu | 714 | BSD-3-Clause | ML — used only by clio vision-extract; lazy-load or replace with regex parsers |
| `pyarrow` | 24.0.0 | 150 | Apache-2.0 | Transitive of polars and parquet I/O — keep |
| `scipy` | 1.17.1 | 84 | BSD-3-Clause | — |
| `litellm` | 1.83.14 | 62 | MIT | LLM gateway — only used in rendering/stonkmode.py for narrative; could split into separate `narrative` extra |
| `PyMuPDF` | 1.27.2.3 | 58 | GPL-3.0-or-later | PDF text extraction — used by clio; likely needed |
| `transformers` | 5.6.2 | 48 | Apache-2.0 | NLP — clio schema-mapping models; consider rule-based mapper for top brokers |
| `pandas` | 3.0.2 | 43 | BSD-3-Clause | — |
| `numpy` | 1.26.4 | 31 | BSD-3-Clause | — |
| `curl_cffi` | 0.15.0 | 31 | MIT | — |
| `sympy` | 1.14.0 | 31 | BSD-3-Clause | — |
| `matplotlib` | 3.10.9 | 23 | Python-2.0 | — |
| `fonttools` | 4.62.1 | 22 | MIT | — |
| `uvloop` | 0.22.1 | 17 | Apache-2.0 | — |
| `fastexcel` | 0.20.1 | 15 | MIT | — |
| `SQLAlchemy` | 2.0.49 | 15 | MIT | — |
| `cryptography` | 47.0.0 | 15 | Apache-2.0 OR BSD-3-Clause | — |
| `RapidFuzz` | 3.14.5 | 13 | MIT | — |
| `lxml` | 6.1.0 | 13 | BSD-3-Clause | — |
| `hf-xet` | 1.4.3 | 12 | Apache-2.0 | — |
| `tokenizers` | 0.22.2 | 11 | Apache-2.0 | Transitive of transformers; goes if transformers goes |
| `networkx` | 3.6.1 | 10 | BSD-3-Clause | — |

## Full package inventory

| Package | Version | Size (MB) | License |
|---|---|---:|---|
| `aiohappyeyeballs` | 2.6.1 | 2 | Python-2.0 |
| `aiohttp` | 3.13.4 | 8 | Apache-2.0 |
| `aiosignal` | 1.4.0 | 2 | Apache-2.0 |
| `aiosqlite` | 0.22.1 | 2 | MIT |
| `annotated-doc` | 0.0.4 | 2 | MIT |
| `annotated-types` | 0.7.0 | 2 | MIT |
| `anyio` | 4.13.0 | 2 | MIT |
| `attrs` | 26.1.0 | 2 | MIT |
| `beautifulsoup4` | 4.14.3 | 1 | MIT |
| `black` | 26.3.1 | 2 | MIT |
| `Bottleneck` | 1.6.0 | 3 | BSD-3-Clause |
| `cachetools` | 7.0.6 | 2 | MIT |
| `camelot-py` | 1.0.9 | 1 | MIT |
| `certifi` | 2025.11.12 | 2 | MPL-2.0 |
| `cffi` | 2.0.0 | 2 | MIT |
| `chardet` | 7.4.3 | 3 | 0BSD |
| `charset-normalizer` | 3.4.7 | 2 | MIT |
| `clarabel` | 0.11.1 | 4 | Apache-2.0 |
| `click` | 8.1.8 | 2 | BSD-3-Clause |
| `clio` | 0.1.0 | 2 | Apache-2.0 |
| `contourpy` | 1.3.3 | 3 | BSD-3-Clause |
| `coverage` | 7.13.5 | 2 | Apache-2.0 |
| `cryptography` | 47.0.0 | 15 | Apache-2.0 OR BSD-3-Clause |
| `cssselect` | 1.4.0 | 2 | BSD-3-Clause |
| `cssutils` | 2.15.0 | 2 | LGPL-3.0-or-later |
| `cuda-bindings` | 13.2.0 | 1 | LicenseRef-NVIDIA-SOFTWARE-LICENSE |
| `cuda-pathfinder` | 1.5.4 | 1 | Apache-2.0 |
| `cuda-toolkit` | 13.0.2 | 1 | NOASSERTION |
| `curl_cffi` | 0.15.0 | 31 | MIT |
| `cvxpy` | 1.7.5 | 5 | Apache-2.0 |
| `cycler` | 0.12.1 | 2 | BSD-3-Clause |
| `distro` | 1.9.0 | 2 | Apache-2.0 |
| `empyrical-reloaded` | 0.5.12 | 1 | Apache-2.0 |
| `encutils` | 1.0.0 | 2 | LGPL-3.0-or-later |
| `et_xmlfile` | 2.0.0 | 2 | MIT |
| `fastapi` | 0.136.1 | 2 | MIT |
| `fastexcel` | 0.20.1 | 15 | MIT |
| `fastuuid` | 0.14.0 | 2 | BSD-3-Clause |
| `filelock` | 3.29.0 | 2 | MIT |
| `finnhub-python` | 2.4.28 | 1 | Apache-2.0 |
| `fonttools` | 4.62.1 | 22 | MIT |
| `frozendict` | 2.4.7 | 2 | LGPL-3.0-or-later |
| `frozenlist` | 1.8.0 | 2 | Apache-2.0 |
| `fsspec` | 2026.3.0 | 2 | BSD-3-Clause |
| `greenlet` | 3.5.0 | 4 | MIT AND PSF-2.0 |
| `h11` | 0.16.0 | 2 | MIT |
| `hf-xet` | 1.4.3 | 12 | Apache-2.0 |
| `httpcore` | 1.0.9 | 2 | BSD-3-Clause |
| `httptools` | 0.7.1 | 3 | MIT |
| `httpx` | 0.28.1 | 2 | BSD-3-Clause |
| `httpx-sse` | 0.4.3 | 2 | MIT |
| `huggingface_hub` | 1.12.0 | 4 | Apache-2.0 |
| `ic-engine` | 2.6.3 | 5 | Apache-2.0 |
| `idna` | 3.13 | 2 | BSD-3-Clause |
| `importlib_metadata` | 8.5.0 | 2 | Apache-2.0 |
| `iniconfig` | 2.3.0 | 2 | MIT |
| `investorclaw` | 2.6.3 | 1 | Apache-2.0 |
| `investorclaw-bridge` | 4.0.0a1 | 2 | Apache-2.0 |
| `Jinja2` | 3.1.6 | 2 | BSD-3-Clause |
| `jiter` | 0.14.0 | 2 | MIT |
| `joblib` | 1.5.3 | 3 | BSD-3-Clause |
| `jsonschema` | 4.23.0 | 2 | MIT |
| `jsonschema-specifications` | 2025.9.1 | 2 | MIT |
| `kiwisolver` | 1.5.0 | 7 | BSD-3-Clause |
| `litellm` | 1.83.14 | 62 | MIT |
| `lxml` | 6.1.0 | 13 | BSD-3-Clause |
| `markdown-it-py` | 4.0.0 | 1 | MIT |
| `MarkupSafe` | 3.0.3 | 2 | BSD-3-Clause |
| `matplotlib` | 3.10.9 | 23 | Python-2.0 |
| `mcp` | 1.27.0 | 3 | MIT |
| `mdurl` | 0.1.2 | 2 | MIT |
| `more-itertools` | 11.0.2 | 2 | MIT |
| `mpmath` | 1.3.0 | 4 | BSD-3-Clause |
| `multidict` | 6.7.1 | 2 | Apache-2.0 |
| `multitasking` | 0.0.13 | 2 | Apache-2.0 |
| `mypy_extensions` | 1.1.0 | 1 | MIT |
| `networkx` | 3.6.1 | 10 | BSD-3-Clause |
| `newsapi-python` | 0.2.7 | 1 | MIT |
| `numpy` | 1.26.4 | 31 | BSD-3-Clause |
| `openai` | 2.24.0 | 8 | Apache-2.0 |
| `opencv-python-headless` | 4.11.0.86 | 1 | Apache-2.0 |
| `openpyxl` | 3.1.5 | 3 | MIT |
| `orjson` | 3.11.8 | 2 | MPL-2.0 AND (Apache-2.0 OR MIT) |
| `osqp` | 1.1.1 | 3 | Apache-2.0 |
| `packaging` | 26.2 | 2 | Apache-2.0 OR BSD-2-Clause |
| `pandas` | 3.0.2 | 43 | BSD-3-Clause |
| `pathspec` | 1.1.1 | 2 | MPL-2.0 |
| `pdfminer.six` | 20251230 | — | MIT |
| `pdfplumber` | 0.11.9 | 2 | MIT |
| `peewee` | 3.17.3 | 1 | MIT |
| `pillow` | 12.2.0 | 1 | MIT-CMU |
| `platformdirs` | 4.9.6 | 2 | MIT |
| `pluggy` | 1.6.0 | 2 | MIT |
| `polars` | 1.40.1 | 6 | MIT |
| `polars-runtime-32` | 1.40.1 | 1 | MIT |
| `polygon-api-client` | 1.16.3 | 1 | MIT |
| `premailer` | 3.10.0 | 2 | Python-2.0 |
| `propcache` | 0.4.1 | 2 | Apache-2.0 |
| `protobuf` | 7.34.1 | 1 | BSD-3-Clause |
| `pyarrow` | 24.0.0 | 150 | Apache-2.0 |
| `pycparser` | 3.0 | 2 | BSD-3-Clause |
| `pydantic` | 2.12.5 | 3 | MIT |
| `pydantic-settings` | 2.14.0 | 2 | MIT |
| `pydantic_core` | 2.41.5 | 6 | MIT |
| `Pygments` | 2.20.0 | 6 | BSD-2-Clause |
| `PyJWT` | 2.12.1 | 1 | MIT |
| `PyMuPDF` | 1.27.2.3 | 58 | GPL-3.0-or-later |
| `pyparsing` | 3.3.2 | 2 | MIT |
| `pypdf` | 5.9.0 | 3 | BSD-3-Clause |
| `PyPDF2` | 3.0.1 | 3 | BSD-3-Clause |
| `pypdfium2` | 5.7.1 | 2 | Apache-2.0 |
| `pyportfolioopt` | 1.6.0 | 1 | MIT |
| `pytest` | 9.0.3 | 2 | MIT |
| `pytest-cov` | 7.1.0 | 2 | MIT |
| `python-dateutil` | 2.9.0.post0 | 1 | BSD-3-Clause |
| `python-dotenv` | 1.2.2 | 1 | BSD-3-Clause |
| `python-multipart` | 0.0.27 | 2 | Apache-2.0 |
| `pytokens` | 0.4.1 | 2 | MIT |
| `pytz` | 2026.1.post1 | 4 | MIT |
| `PyYAML` | 6.0.3 | 1 | MIT |
| `RapidFuzz` | 3.14.5 | 13 | MIT |
| `ratelimit` | 2.2.1 | 2 | MIT |
| `referencing` | 0.37.0 | 2 | MIT |
| `regex` | 2026.4.4 | 4 | Apache-2.0 AND CNRI-Python |
| `requests` | 2.33.1 | 2 | Apache-2.0 |
| `rich` | 15.0.0 | 3 | MIT |
| `rpds-py` | 0.30.0 | 1 | MIT |
| `ruff` | 0.15.12 | 2 | MIT |
| `safetensors` | 0.7.0 | 3 | Apache-2.0 |
| `scikit-base` | 0.13.2 | 1 | BSD-3-Clause |
| `scikit-learn` | 1.8.0 | 1 | BSD-3-Clause |
| `scipy` | 1.17.1 | 84 | BSD-3-Clause |
| `scs` | 3.2.11 | 2 | MIT |
| `sentence-transformers` | 5.4.1 | 4 | Apache-2.0 |
| `setuptools` | 81.0.0 | 6 | MIT |
| `shellingham` | 1.5.4 | 2 | ISC |
| `six` | 1.17.0 | 1 | MIT |
| `sniffio` | 1.3.1 | 2 | MIT |
| `soupsieve` | 2.8.3 | 2 | MIT |
| `SQLAlchemy` | 2.0.49 | 15 | MIT |
| `sse-starlette` | 3.4.1 | 2 | BSD-3-Clause |
| `starlette` | 1.0.0 | 2 | BSD-3-Clause |
| `structlog` | 25.5.0 | 2 | MIT OR Apache-2.0 |
| `sympy` | 1.14.0 | 31 | BSD-3-Clause |
| `tabula-py` | 2.10.0 | 1 | MIT |
| `tabulate` | 0.10.0 | 2 | MIT |
| `threadpoolctl` | 3.6.0 | 1 | BSD-3-Clause |
| `tiktoken` | 0.12.0 | 5 | MIT |
| `tokenizers` | 0.22.2 | 11 | Apache-2.0 |
| `torch` | 2.11.0+cpu | 714 | BSD-3-Clause |
| `tqdm` | 4.67.3 | 2 | MIT |
| `transformers` | 5.6.2 | 48 | Apache-2.0 |
| `typer` | 0.23.1 | 2 | MIT |
| `typing-inspection` | 0.4.2 | 2 | MIT |
| `typing_extensions` | 4.15.0 | 1 | PSF-2.0 |
| `urllib3` | 2.6.3 | 2 | MIT |
| `uvicorn` | 0.46.0 | 2 | BSD-3-Clause |
| `uvloop` | 0.22.1 | 17 | Apache-2.0 |
| `watchfiles` | 1.1.1 | 3 | MIT |
| `websockets` | 16.0 | 2 | BSD-3-Clause |
| `xlrd` | 2.0.2 | 2 | BSD-3-Clause |
| `yarl` | 1.23.0 | 2 | Apache-2.0 |
| `yfinance` | 1.3.0 | 2 | Apache-2.0 |
| `zipp` | 3.23.1 | 2 | MIT |
