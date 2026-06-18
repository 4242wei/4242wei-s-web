from __future__ import annotations

import hashlib
import json
import re
import statistics
from datetime import datetime
from typing import Any
from urllib.parse import quote

import requests


REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    ),
}

GPU_FAMILY_CONFIGS: dict[str, dict[str, Any]] = {
    "H100": {
        "slug": "h100",
        "gpusio_url": "https://gpus.io/en/gpus/h100",
        "getdeploying_url": "https://getdeploying.com/gpus/nvidia-h100",
        "variant": "h100_sxm",
        "vram_gb": 80,
        "mem_bw_gbps": 3350,
        "fp16_tflops": 989,
    },
    "H200": {
        "slug": "h200",
        "gpusio_url": "https://gpus.io/en/gpus/h200",
        "getdeploying_url": "https://getdeploying.com/gpus/nvidia-h200",
        "variant": "h200_sxm",
        "vram_gb": 141,
        "mem_bw_gbps": 4800,
        "fp16_tflops": 989,
    },
    "B200": {
        "slug": "b200",
        "gpusio_url": "https://gpus.io/en/gpus/b200",
        "getdeploying_url": "https://getdeploying.com/gpus/nvidia-b200",
        "variant": "b200_sxm",
        "vram_gb": 180,
        "mem_bw_gbps": 8000,
        "fp16_tflops": 2250,
    },
    "B100": {
        "slug": "b100",
        "gpusio_url": "https://gpus.io/en/gpus/b100",
        "getdeploying_url": "https://getdeploying.com/gpus/nvidia-b100",
        "variant": "b100_sxm",
        "vram_gb": 192,
        "mem_bw_gbps": None,
        "fp16_tflops": None,
        "price_index_enabled": False,
        "coverage_note": "B100 public price discovery is too thin; showing provider availability instead of a price index.",
    },
}

GPU_PRICE_CACHE_VERSION = 1
GPU_PRICE_PARSE_VERSION = "gpusio-next-flight-primary-v1"
PRIMARY_QUALITY_CPU_RANGE = (16.0, 32.0)
PRIMARY_QUALITY_RAM_RANGE = (120.0, 256.0)
PRIMARY_QUALITY_STORAGE_RANGE = (0.0, 1500.0)
GPU_PRICE_STORAGE_POLICY = {
    "daily_index": "one row per date and series_key; later refreshes replace earlier same-day rows",
    "csp_daily_index": "one Azure CSP row per date and series_key; later refreshes replace earlier same-day rows",
    "history": "one snapshot per date; later refreshes replace earlier same-day snapshots",
    "normalized_offers": "current refresh snapshot only",
    "raw_snapshots": "current refresh snapshot only",
}
GPU_PRICE_DAILY_INDEX_BILLING_TYPES = ("on_demand", "spot")
AZURE_RETAIL_PRICES_ENDPOINT = "https://prices.azure.com/api/retail/prices"
AZURE_SOURCE_URL = "https://prices.azure.com/api/retail/prices"


def utcnow_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


def normalize_gpu_families(families: list[str] | tuple[str, ...] | None = None) -> list[str]:
    if not families:
        return ["H100"]
    resolved: list[str] = []
    for value in families:
        family = str(value or "").strip().upper()
        if family in GPU_FAMILY_CONFIGS and family not in resolved:
            resolved.append(family)
    return resolved or ["H100"]


def default_gpu_price_cache(families: list[str] | tuple[str, ...] | None = None) -> dict[str, Any]:
    resolved_families = normalize_gpu_families(families)
    return {
        "version": GPU_PRICE_CACHE_VERSION,
        "updated_at": "",
        "families": resolved_families,
        "source": {
            "name": "GPUs.io + GetDeploying + Azure Retail Prices",
            "url": "https://gpus.io/en/gpus/h100",
            "endpoint": "public GPU pages + Next.js flight parser + Azure Retail Prices API + daily median indexes",
        },
        "notes": (
            "MVP keeps GPUs.io on-demand provider summary rows as the primary price curve. "
            "Azure Retail Prices rows are stored as a separate CSP reference curve."
        ),
        "storage_policy": GPU_PRICE_STORAGE_POLICY,
        "summary": {
            "offer_count": 0,
            "raw_snapshot_count": 0,
            "daily_index_count": 0,
            "csp_daily_index_count": 0,
            "source_health_count": 0,
            "provider_count": 0,
        },
        "latest": [],
        "raw_snapshots": [],
        "normalized_offers": [],
        "daily_index": [],
        "csp_daily_index": [],
        "source_health": [],
        "history": [],
    }


def normalize_gpu_price_cache(raw: Any, families: list[str] | tuple[str, ...] | None = None) -> dict[str, Any]:
    baseline = default_gpu_price_cache(families)
    source = raw if isinstance(raw, dict) else {}
    summary = source.get("summary") if isinstance(source.get("summary"), dict) else {}
    source_info = source.get("source") if isinstance(source.get("source"), dict) else {}
    return {
        **baseline,
        "version": int(source.get("version") or GPU_PRICE_CACHE_VERSION),
        "updated_at": str(source.get("updated_at") or "").strip(),
        "families": normalize_gpu_families(source.get("families") if isinstance(source.get("families"), list) else families),
        "source": {
            "name": str(source_info.get("name") or baseline["source"]["name"]).strip(),
            "url": str(source_info.get("url") or baseline["source"]["url"]).strip(),
            "endpoint": str(source_info.get("endpoint") or baseline["source"]["endpoint"]).strip(),
        },
        "notes": str(source.get("notes") or baseline["notes"]).strip(),
        "storage_policy": source.get("storage_policy") if isinstance(source.get("storage_policy"), dict) else baseline["storage_policy"],
        "summary": {
            "offer_count": int(summary.get("offer_count") or 0),
            "raw_snapshot_count": int(summary.get("raw_snapshot_count") or 0),
            "daily_index_count": int(summary.get("daily_index_count") or 0),
            "csp_daily_index_count": int(summary.get("csp_daily_index_count") or 0),
            "source_health_count": int(summary.get("source_health_count") or 0),
            "provider_count": int(summary.get("provider_count") or 0),
        },
        "latest": source.get("latest") if isinstance(source.get("latest"), list) else [],
        "raw_snapshots": source.get("raw_snapshots") if isinstance(source.get("raw_snapshots"), list) else [],
        "normalized_offers": source.get("normalized_offers") if isinstance(source.get("normalized_offers"), list) else [],
        "daily_index": source.get("daily_index") if isinstance(source.get("daily_index"), list) else [],
        "csp_daily_index": source.get("csp_daily_index") if isinstance(source.get("csp_daily_index"), list) else [],
        "source_health": source.get("source_health") if isinstance(source.get("source_health"), list) else [],
        "history": source.get("history") if isinstance(source.get("history"), list) else [],
    }


def request_html(url: str, *, timeout: float = 30.0) -> tuple[str, int, str]:
    response = requests.get(url, headers=REQUEST_HEADERS, timeout=timeout)
    status_code = int(response.status_code)
    final_url = str(response.url or url)
    response.raise_for_status()
    return response.text, status_code, final_url


def decode_next_flight_strings(html_text: str) -> str:
    chunks: list[str] = []
    for match in re.finditer(r"self\.__next_f\.push\((.*?)\)</script>", html_text, re.S):
        try:
            payload = json.loads(match.group(1))
        except Exception:
            continue
        if len(payload) > 1 and isinstance(payload[1], str):
            chunks.append(payload[1])
    return "".join(chunks)


def extract_balanced_json_object(text: str, start: int) -> str:
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return ""


def numeric_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if not cleaned or cleaned.startswith("$"):
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def size_to_gb(value: Any) -> float | None:
    if not isinstance(value, dict):
        return None
    size = numeric_value(value.get("size"))
    if size is None:
        return None
    unit = str(value.get("unit") or "GB").strip().upper()
    if unit in {"TB", "TIB"}:
        return size * 1024.0
    if unit in {"MB", "MIB"}:
        return size / 1024.0
    return size


def price_usd(value: Any) -> float | None:
    if isinstance(value, dict):
        return numeric_value(value.get("usd"))
    return numeric_value(value)


def provider_slug(raw_name: str, raw_slug: str = "") -> str:
    normalized = str(raw_slug or raw_name or "").strip().lower()
    alias = {
        "lambda labs": "lambda",
        "lambda": "lambda",
        "digitalocean": "digitalocean",
        "digital ocean": "digitalocean",
        "theta edgecloud": "theta_edgecloud",
        "latitude.sh": "latitude",
        "datacrunch": "verda",
    }.get(normalized)
    if alias:
        return alias
    slug = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    return slug or "unknown"


def canonical_gpu_variant(family: str, descriptor: str = "") -> str:
    text = f"{family} {descriptor}".upper()
    family_key = str(family or "").strip().upper()
    if "GB200" in text or "B200" in text and "NVL" in text:
        return "b200_nvl"
    if "NVL" in text:
        return f"{family_key.lower()}_nvl"
    if "PCIE" in text or "PCI-E" in text:
        return f"{family_key.lower()}_pcie"
    if family_key in GPU_FAMILY_CONFIGS:
        return str(GPU_FAMILY_CONFIGS[family_key]["variant"])
    return "unknown"


def contract_term_bucket(months: float | None, billing_type: str) -> str:
    if billing_type != "reserved":
        return "none"
    if months is None:
        return "unknown"
    if months < 1:
        return "lt_1m"
    if months <= 3:
        return "1_3m"
    if months <= 12:
        return "4_12m"
    return "gt_12m"


def gpu_count_bucket(gpu_count: int) -> str:
    if gpu_count in {1, 2, 4, 8}:
        return f"{gpu_count}gpu"
    return "other"


def infer_azure_gpu_family(item: dict[str, Any]) -> str:
    text = " ".join(
        str(item.get(key) or "")
        for key in ["meterName", "skuName", "armSkuName", "productName"]
    ).upper()
    if "GB200" in text or "B200" in text:
        return "B200"
    if "B100" in text:
        return "B100"
    if "H200" in text:
        return "H200"
    if "H100" in text:
        return "H100"
    return ""


def infer_azure_gpu_count(item: dict[str, Any], family: str) -> int:
    text = " ".join(
        str(item.get(key) or "")
        for key in ["meterName", "skuName", "armSkuName", "productName"]
    ).upper()
    if family == "H100":
        if re.search(r"NCC?40", text):
            return 1
        if re.search(r"NCC?80", text):
            return 2
        if re.search(r"ND96", text):
            return 8
    if family == "H200":
        if re.search(r"ND96", text):
            return 8
    return 0


def infer_azure_vcpu_total(item: dict[str, Any]) -> float | None:
    text = " ".join(str(item.get(key) or "") for key in ["armSkuName", "meterName", "skuName"]).upper()
    match = re.search(r"N(?:CC?|D)(\d+)", text)
    if not match:
        return None
    return float(match.group(1))


def azure_billing_type(item: dict[str, Any]) -> str:
    text = " ".join(str(item.get(key) or "") for key in ["meterName", "skuName"]).upper()
    if "SPOT" in text or "LOW PRIORITY" in text:
        return "spot"
    return "on_demand"


def normalize_azure_retail_price_item(item: dict[str, Any], *, fetch_ts: str) -> dict[str, Any] | None:
    if str(item.get("type") or "") != "Consumption":
        return None
    product_name = str(item.get("productName") or "")
    if "Windows" in product_name:
        return None
    family = infer_azure_gpu_family(item)
    if family not in GPU_FAMILY_CONFIGS:
        return None
    gpu_count = infer_azure_gpu_count(item, family)
    unit_price = numeric_value(item.get("unitPrice"))
    retail_price = numeric_value(item.get("retailPrice"))
    total_price = unit_price if unit_price is not None else retail_price
    price_per_gpu = (total_price / gpu_count) if total_price is not None and gpu_count > 0 else None
    family_config = GPU_FAMILY_CONFIGS[family]
    variant = canonical_gpu_variant(family, " ".join(str(item.get(key) or "") for key in ["armSkuName", "meterName", "skuName"]))
    vcpu_total = infer_azure_vcpu_total(item)
    billing_type = azure_billing_type(item)
    region = str(item.get("armRegionName") or "").strip().lower()
    meter_id = str(item.get("meterId") or item.get("meterName") or item.get("skuName") or "")
    normalized = {
        "id": f"azure-{family.lower()}-{region}-{meter_id}-{billing_type}".replace(" ", "-"),
        "source_name": "azure_retail_prices",
        "source_page_url": AZURE_SOURCE_URL,
        "source_fetch_ts": fetch_ts,
        "source_fetch_date": fetch_ts[:10],
        "gpu_family": family,
        "gpu_variant_raw": str(item.get("meterName") or item.get("skuName") or family),
        "gpu_variant_canonical": variant,
        "provider_name": "Microsoft Azure",
        "provider_slug": "azure",
        "provider_source_url": "https://azure.microsoft.com/pricing/details/virtual-machines/",
        "billing_type": billing_type,
        "contract_term_months": None,
        "contract_term_bucket": "none",
        "gpu_count": gpu_count,
        "gpu_count_bucket": gpu_count_bucket(gpu_count),
        "total_vram_gb": (float(family_config["vram_gb"]) * gpu_count) if gpu_count > 0 and family_config.get("vram_gb") else None,
        "vram_per_gpu_gb": float(family_config["vram_gb"]) if family_config.get("vram_gb") else None,
        "vcpu_total": vcpu_total,
        "vcpu_per_gpu": (vcpu_total / gpu_count) if vcpu_total is not None and gpu_count > 0 else None,
        "ram_total_gb": None,
        "ram_per_gpu_gb": None,
        "storage_total_gb": None,
        "storage_per_gpu_gb": None,
        "region_codes": [region] if region else [],
        "availability_status": "available",
        "price_per_gpu_hour_usd": price_per_gpu,
        "price_total_hour_usd": total_price,
        "currency": str(item.get("currencyCode") or "USD"),
        "record_granularity": "official_region_meter",
        "visible_config_count": None,
        "page_last_updated_ts": str(item.get("effectiveStartDate") or ""),
        "source_confidence_score": 0.94,
        "completeness_score": 0.78 if price_per_gpu is not None else 0.58,
        "is_primary_candidate": True,
        "quality_exclusion_reason": None,
        "html_hash": "",
        "parse_version": "azure-retail-prices-v1",
        "raw_json": item,
    }
    normalized["quality_exclusion_reason"] = quality_exclusion_reason(normalized)
    normalized["dedupe_key"] = build_dedupe_key(normalized)
    return normalized


def build_dedupe_key(offer: dict[str, Any]) -> str:
    parts = [
        str(offer.get("source_name") or ""),
        str(offer.get("provider_slug") or ""),
        str(offer.get("gpu_variant_canonical") or ""),
        str(offer.get("billing_type") or ""),
        str(offer.get("gpu_count") or ""),
        str(round(float(offer.get("vcpu_total") or 0.0), 0)),
        str(round(float(offer.get("ram_total_gb") or 0.0), 0)),
        str(round(float(offer.get("price_per_gpu_hour_usd") or 0.0), 4)),
        str(offer.get("source_fetch_date") or ""),
    ]
    return "|".join(parts)


def quality_exclusion_reason(offer: dict[str, Any]) -> str | None:
    if str(offer.get("billing_type") or "") == "custom":
        return "custom_billing"
    if offer.get("price_per_gpu_hour_usd") is None:
        return "missing_price"
    if str(offer.get("gpu_variant_canonical") or "") == "unknown":
        return "unknown_variant"
    if int(offer.get("gpu_count") or 0) not in {1, 2, 4, 8}:
        return "unsupported_gpu_count"
    vram_per_gpu = numeric_value(offer.get("vram_per_gpu_gb"))
    family = str(offer.get("gpu_family") or "").upper()
    nominal_vram = GPU_FAMILY_CONFIGS.get(family, {}).get("vram_gb")
    if vram_per_gpu is not None and nominal_vram and abs(vram_per_gpu - float(nominal_vram)) > max(8.0, float(nominal_vram) * 0.15):
        return "unexpected_vram"
    return None


def normalize_gpusio_primary_offer(
    offering: dict[str, Any],
    *,
    family: str,
    source_url: str,
    fetch_ts: str,
    html_hash: str,
) -> dict[str, Any] | None:
    provider = offering.get("provider") if isinstance(offering.get("provider"), dict) else {}
    provider_id = str(provider.get("id") or "").strip()
    provider_name = str(provider.get("name") or provider_id or "Unknown").strip()
    gpu_count = int(numeric_value(offering.get("gpuCount")) or 0)
    if gpu_count <= 0:
        return None
    price_per_gpu = price_usd(offering.get("pricePerGpuHour"))
    ram_total = size_to_gb(offering.get("ram"))
    storage_total = size_to_gb(offering.get("bootDisk"))
    vcpu_total = numeric_value(offering.get("vcpu"))
    family_config = GPU_FAMILY_CONFIGS[family]
    vram_per_gpu = float(family_config["vram_gb"])
    variant = canonical_gpu_variant(family)
    regions = offering.get("regions") if isinstance(offering.get("regions"), list) else []
    availability_status = "unknown"
    if offering.get("available") is True:
        availability_status = "available"
    elif offering.get("available") is False:
        availability_status = "unavailable"
    normalized = {
        "id": f"gpusio-{family.lower()}-{provider_id or provider_slug(provider_name)}-{offering.get('id')}",
        "source_name": "gpusio",
        "source_page_url": source_url,
        "source_fetch_ts": fetch_ts,
        "source_fetch_date": fetch_ts[:10],
        "gpu_family": family,
        "gpu_variant_raw": family,
        "gpu_variant_canonical": variant,
        "provider_name": provider_name,
        "provider_slug": provider_slug(provider_name, provider_id),
        "provider_source_url": str(provider.get("website") or provider.get("affiliateUrl") or "").strip(),
        "billing_type": "on_demand",
        "contract_term_months": None,
        "contract_term_bucket": "none",
        "gpu_count": gpu_count,
        "gpu_count_bucket": gpu_count_bucket(gpu_count),
        "total_vram_gb": vram_per_gpu * gpu_count,
        "vram_per_gpu_gb": vram_per_gpu,
        "vcpu_total": vcpu_total,
        "vcpu_per_gpu": (vcpu_total / gpu_count) if vcpu_total is not None else None,
        "ram_total_gb": ram_total,
        "ram_per_gpu_gb": (ram_total / gpu_count) if ram_total is not None else None,
        "storage_total_gb": storage_total,
        "storage_per_gpu_gb": (storage_total / gpu_count) if storage_total is not None else None,
        "region_codes": [str(region).strip().lower() for region in regions if str(region).strip()],
        "availability_status": availability_status,
        "price_per_gpu_hour_usd": price_per_gpu,
        "price_total_hour_usd": (
            float(offering.get("totalPrice"))
            if numeric_value(offering.get("totalPrice")) is not None
            else (price_per_gpu * gpu_count if price_per_gpu is not None else None)
        ),
        "currency": "USD",
        "record_granularity": "provider_summary",
        "visible_config_count": len(provider.get("offerings", [])) if isinstance(provider.get("offerings"), list) else None,
        "page_last_updated_ts": None,
        "source_confidence_score": 0.86,
        "completeness_score": 0.72,
        "is_primary_candidate": True,
        "quality_exclusion_reason": None,
        "html_hash": html_hash,
        "parse_version": GPU_PRICE_PARSE_VERSION,
        "raw_json": offering,
    }
    normalized["quality_exclusion_reason"] = quality_exclusion_reason(normalized)
    normalized["dedupe_key"] = build_dedupe_key(normalized)
    return normalized


def parse_gpusio_offers(
    html_text: str,
    *,
    family: str,
    source_url: str,
    fetch_ts: str,
) -> list[dict[str, Any]]:
    family = str(family or "").strip().upper()
    if family not in GPU_FAMILY_CONFIGS:
        return []
    rsc_text = decode_next_flight_strings(html_text)
    html_hash = hashlib.sha256(html_text.encode("utf-8", errors="ignore")).hexdigest()
    offers: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in re.finditer(r'"provider":(?=\{"id")', rsc_text):
        start = rsc_text.rfind('{"id":', 0, match.start())
        if start < 0:
            continue
        raw_object = extract_balanced_json_object(rsc_text, start)
        if not raw_object:
            continue
        try:
            offering = json.loads(raw_object)
        except Exception:
            continue
        normalized = normalize_gpusio_primary_offer(
            offering,
            family=family,
            source_url=source_url,
            fetch_ts=fetch_ts,
            html_hash=html_hash,
        )
        if not normalized:
            continue
        key = str(normalized.get("dedupe_key") or normalized.get("id") or "")
        if key in seen:
            continue
        seen.add(key)
        offers.append(normalized)
    offers.sort(
        key=lambda item: (
            str(item.get("gpu_family") or ""),
            float(item.get("price_per_gpu_hour_usd") or 999999.0),
            str(item.get("provider_name") or ""),
        )
    )
    return offers


def build_raw_snapshots(offers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    for index, offer in enumerate(offers, start=1):
        raw_json = offer.get("raw_json") if isinstance(offer.get("raw_json"), dict) else {}
        snapshots.append(
            {
                "id": f"{offer.get('source_name')}-{offer.get('gpu_family')}-{index}",
                "source_name": str(offer.get("source_name") or ""),
                "source_page_url": str(offer.get("source_page_url") or ""),
                "source_fetch_ts": str(offer.get("source_fetch_ts") or ""),
                "gpu_family_raw": str(offer.get("gpu_family") or ""),
                "provider_raw": str(offer.get("provider_name") or ""),
                "row_text_raw": " ".join(
                    [
                        str(offer.get("provider_name") or ""),
                        str(offer.get("gpu_family") or ""),
                        str(offer.get("gpu_count") or ""),
                        str(offer.get("price_per_gpu_hour_usd") or ""),
                    ]
                ).strip(),
                "html_hash": str(offer.get("html_hash") or ""),
                "page_last_updated_raw": "",
                "parse_version": str(offer.get("parse_version") or GPU_PRICE_PARSE_VERSION),
                "raw_json": raw_json,
            }
        )
    return snapshots


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    sorted_values = sorted(values)
    position = (len(sorted_values) - 1) * pct
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = position - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def offer_in_primary_quality_window(offer: dict[str, Any], *, available_only: bool, billing_type: str = "on_demand") -> bool:
    if str(offer.get("billing_type") or "") != billing_type:
        return False
    if offer.get("price_per_gpu_hour_usd") is None:
        return False
    if offer.get("quality_exclusion_reason"):
        return False
    if available_only and str(offer.get("availability_status") or "") == "unavailable":
        return False
    if billing_type == "spot":
        family = str(offer.get("gpu_family") or "").upper()
        return family in {"H100", "H200", "B200"} and int(offer.get("gpu_count") or 0) in {1, 2, 4, 8}
    if int(offer.get("gpu_count") or 0) != 1:
        return False
    vcpu_per_gpu = numeric_value(offer.get("vcpu_per_gpu"))
    ram_per_gpu = numeric_value(offer.get("ram_per_gpu_gb"))
    storage_per_gpu = numeric_value(offer.get("storage_per_gpu_gb"))
    storage_value = 0.0 if storage_per_gpu is None else storage_per_gpu
    if vcpu_per_gpu is None or ram_per_gpu is None:
        return False
    return (
        PRIMARY_QUALITY_CPU_RANGE[0] <= vcpu_per_gpu <= PRIMARY_QUALITY_CPU_RANGE[1]
        and PRIMARY_QUALITY_RAM_RANGE[0] <= ram_per_gpu <= PRIMARY_QUALITY_RAM_RANGE[1]
        and PRIMARY_QUALITY_STORAGE_RANGE[0] <= storage_value <= PRIMARY_QUALITY_STORAGE_RANGE[1]
    )


def collapse_daily_index_latest(rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Keep the latest in-file row for each date + series_key pair."""
    latest_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for item in rows or []:
        if not isinstance(item, dict):
            continue
        date_value = str(item.get("date") or "")
        series_key = str(item.get("series_key") or "")
        if not date_value or not series_key:
            continue
        latest_by_key[(date_value, series_key)] = item
    return sorted(latest_by_key.values(), key=lambda item: (str(item.get("date") or ""), str(item.get("series_key") or "")))


def collapse_history_latest(rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    latest_by_date: dict[str, dict[str, Any]] = {}
    for item in rows or []:
        if not isinstance(item, dict):
            continue
        date_value = str(item.get("updated_at") or item.get("date") or "")[:10]
        if not date_value:
            continue
        latest_by_date[date_value] = item
    return sorted(latest_by_date.values(), key=lambda item: str(item.get("updated_at") or item.get("date") or ""))


def build_daily_index_row(
    *,
    index_date: str,
    fetch_ts: str,
    series_key: str,
    family: str,
    variant: str,
    billing_type: str,
    contract_bucket: str,
    gpu_count_bucket_value: str,
    mode: str,
    values: list[float],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    provider_count = len({str(item.get("provider_slug") or "") for item in candidates if item.get("provider_slug")})
    source_mix = dict(
        sorted(
            {
                source: sum(1 for item in candidates if str(item.get("source_name") or "") == source)
                for source in {str(item.get("source_name") or "") for item in candidates}
            }.items()
        )
    )
    median_value = float(statistics.median(values))
    return {
        "date": index_date,
        "updated_at": fetch_ts,
        "series_key": series_key,
        "gpu_family": family,
        "gpu_variant_canonical": variant,
        "billing_type": billing_type,
        "contract_term_bucket": contract_bucket,
        "gpu_count_bucket": gpu_count_bucket_value,
        "region_bucket": "all",
        "availability_mode": mode,
        "index_method": "trimmed_median",
        "price_native": median_value,
        "price_standardized": median_value,
        "sample_size": len(values),
        "provider_count": provider_count,
        "freshness_score": 1.0,
        "stale_flag": False,
        "dispersion_p10": percentile(values, 0.10),
        "dispersion_p25": percentile(values, 0.25),
        "dispersion_p50": median_value,
        "dispersion_p75": percentile(values, 0.75),
        "source_mix_json": source_mix,
    }


def build_daily_index(
    offers: list[dict[str, Any]],
    *,
    fetch_ts: str,
    previous_daily_index: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    index_date = fetch_ts[:10]
    previous = [
        item
        for item in collapse_daily_index_latest(previous_daily_index)
        if isinstance(item, dict) and str(item.get("date") or "") != index_date
    ]
    rows: list[dict[str, Any]] = []
    variants = sorted({str(item.get("gpu_variant_canonical") or "") for item in offers if item.get("gpu_variant_canonical")})
    for variant in variants:
        variant_offers = [item for item in offers if str(item.get("gpu_variant_canonical") or "") == variant]
        family = str(variant_offers[0].get("gpu_family") or "").upper() if variant_offers else ""
        if not GPU_FAMILY_CONFIGS.get(family, {}).get("price_index_enabled", True):
            continue
        for mode, available_only in [("posted", False), ("available", True)]:
            candidates = [
                item
                for item in variant_offers
                if offer_in_primary_quality_window(item, available_only=available_only, billing_type="on_demand")
            ]
            values = [float(item["price_per_gpu_hour_usd"]) for item in candidates if item.get("price_per_gpu_hour_usd") is not None]
            if not values:
                continue
            rows.append(
                build_daily_index_row(
                    index_date=index_date,
                    fetch_ts=fetch_ts,
                    series_key=f"{variant}:on_demand:1gpu:all:{mode}",
                    family=family,
                    variant=variant,
                    billing_type="on_demand",
                    contract_bucket="none",
                    gpu_count_bucket_value="1gpu",
                    mode=mode,
                    values=values,
                    candidates=candidates,
                )
            )

    spot_families = sorted(
        {
            str(item.get("gpu_family") or "").upper()
            for item in offers
            if str(item.get("billing_type") or "") == "spot" and str(item.get("gpu_family") or "").upper() in {"H100", "H200", "B200"}
        }
    )
    for family in spot_families:
        family_offers = [item for item in offers if str(item.get("gpu_family") or "").upper() == family]
        variant = str(GPU_FAMILY_CONFIGS.get(family, {}).get("variant") or f"{family.lower()}_spot")
        for mode, available_only in [("posted", False), ("available", True)]:
            candidates = [
                item
                for item in family_offers
                if offer_in_primary_quality_window(item, available_only=available_only, billing_type="spot")
            ]
            values = [float(item["price_per_gpu_hour_usd"]) for item in candidates if item.get("price_per_gpu_hour_usd") is not None]
            if not values:
                continue
            rows.append(
                build_daily_index_row(
                    index_date=index_date,
                    fetch_ts=fetch_ts,
                    series_key=f"{family.lower()}:spot:allgpu:all:{mode}",
                    family=family,
                    variant=variant,
                    billing_type="spot",
                    contract_bucket="none",
                    gpu_count_bucket_value="allgpu",
                    mode=mode,
                    values=values,
                    candidates=candidates,
                )
            )
    return collapse_daily_index_latest(previous + rows)


def build_csp_daily_index(
    offers: list[dict[str, Any]],
    *,
    fetch_ts: str,
    previous_csp_daily_index: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    index_date = fetch_ts[:10]
    previous = [
        item
        for item in collapse_daily_index_latest(previous_csp_daily_index)
        if isinstance(item, dict) and str(item.get("date") or "") != index_date
    ]
    azure_offers = [
        item
        for item in offers
        if isinstance(item, dict)
        and str(item.get("source_name") or "") == "azure_retail_prices"
        and str(item.get("gpu_family") or "").upper() in {"H100", "H200", "B200"}
    ]
    rows: list[dict[str, Any]] = []
    for family in sorted({str(item.get("gpu_family") or "").upper() for item in azure_offers if item.get("gpu_family")}):
        family_offers = [item for item in azure_offers if str(item.get("gpu_family") or "").upper() == family]
        if not GPU_FAMILY_CONFIGS.get(family, {}).get("price_index_enabled", True):
            continue
        for billing_type in GPU_PRICE_DAILY_INDEX_BILLING_TYPES:
            candidates = [
                item
                for item in family_offers
                if str(item.get("billing_type") or "") == billing_type
                and str(item.get("availability_status") or "") != "unavailable"
                and item.get("price_per_gpu_hour_usd") is not None
                and item.get("quality_exclusion_reason") is None
            ]
            values = [float(item["price_per_gpu_hour_usd"]) for item in candidates if item.get("price_per_gpu_hour_usd") is not None]
            if not values:
                continue
            variant = str(GPU_FAMILY_CONFIGS.get(family, {}).get("variant") or f"{family.lower()}_csp")
            rows.append(
                build_daily_index_row(
                    index_date=index_date,
                    fetch_ts=fetch_ts,
                    series_key=f"azure:{family.lower()}:{billing_type}:allgpu:all:available",
                    family=family,
                    variant=variant,
                    billing_type=billing_type,
                    contract_bucket="none",
                    gpu_count_bucket_value="allgpu",
                    mode="available",
                    values=values,
                    candidates=candidates,
                )
            )
    return collapse_daily_index_latest(previous + rows)


def build_latest_summary(offers: list[dict[str, Any]], daily_index: list[dict[str, Any]], *, fetch_ts: str) -> list[dict[str, Any]]:
    today = fetch_ts[:10]
    latest_rows: list[dict[str, Any]] = []
    for family in sorted({str(item.get("gpu_family") or "") for item in offers if item.get("gpu_family")}):
        family_offers = [item for item in offers if str(item.get("gpu_family") or "") == family]
        visible_prices = [
            item
            for item in family_offers
            if item.get("price_per_gpu_hour_usd") is not None and str(item.get("availability_status") or "") != "unavailable"
        ]
        cheapest = min(visible_prices, key=lambda item: float(item.get("price_per_gpu_hour_usd") or 999999.0), default={})
        family_index = [
            item
            for item in daily_index
            if str(item.get("date") or "") == today
            and str(item.get("gpu_family") or "") == family
            and str(item.get("billing_type") or "") == "on_demand"
            and str(item.get("availability_mode") or "") == "available"
        ]
        index_row = family_index[0] if family_index else {}
        family_spot_index = [
            item
            for item in daily_index
            if str(item.get("date") or "") == today
            and str(item.get("gpu_family") or "") == family
            and str(item.get("billing_type") or "") == "spot"
            and str(item.get("availability_mode") or "") == "available"
        ]
        spot_row = family_spot_index[0] if family_spot_index else {}
        on_demand_price = numeric_value(index_row.get("price_standardized"))
        spot_price = numeric_value(spot_row.get("price_standardized"))
        spot_discount = (
            1 - (spot_price / on_demand_price)
            if spot_price is not None and on_demand_price is not None and on_demand_price > 0
            else None
        )
        latest_rows.append(
            {
                "gpu_family": family,
                "variant": str(index_row.get("gpu_variant_canonical") or GPU_FAMILY_CONFIGS.get(family, {}).get("variant") or ""),
                "available_standardized_price": index_row.get("price_standardized"),
                "available_sample_size": int(index_row.get("sample_size") or 0),
                "available_provider_count": int(index_row.get("provider_count") or 0),
                "spot_standardized_price": spot_row.get("price_standardized"),
                "spot_sample_size": int(spot_row.get("sample_size") or 0),
                "spot_provider_count": int(spot_row.get("provider_count") or 0),
                "spot_discount": spot_discount,
                "cheapest_provider": str(cheapest.get("provider_name") or ""),
                "cheapest_price": cheapest.get("price_per_gpu_hour_usd"),
                "cheapest_regions": cheapest.get("region_codes") if isinstance(cheapest.get("region_codes"), list) else [],
                "offer_count": len(family_offers),
            }
        )
    return latest_rows


def build_source_health_row(
    *,
    source_name: str,
    family: str,
    url: str,
    fetch_ts: str,
    fetch_ok: bool,
    rows_parsed: int,
    providers_found: int,
    status_code: int | None = None,
    notes: str = "",
) -> dict[str, Any]:
    return {
        "date": fetch_ts[:10],
        "source_name": source_name,
        "gpu_family": family,
        "source_page_url": url,
        "fetch_ok": bool(fetch_ok),
        "status_code": status_code,
        "rows_parsed": int(rows_parsed or 0),
        "providers_found": int(providers_found or 0),
        "sample_last_updated_age_hours": None,
        "schema_changed": False,
        "cross_source_median_gap": None,
        "notes": notes,
    }


def probe_getdeploying_health(family: str, fetch_ts: str, *, timeout: float = 20.0) -> dict[str, Any]:
    url = str(GPU_FAMILY_CONFIGS[family]["getdeploying_url"])
    try:
        html_text, status_code, final_url = request_html(url, timeout=timeout)
        blocked = "Just a moment" in html_text[:5000] or "cf-browser-verification" in html_text[:5000].lower()
        return build_source_health_row(
            source_name="getdeploying",
            family=family,
            url=final_url,
            fetch_ts=fetch_ts,
            fetch_ok=not blocked,
            rows_parsed=0,
            providers_found=0,
            status_code=status_code,
            notes="parser_not_enabled" if not blocked else "cloudflare_challenge",
        )
    except Exception as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        return build_source_health_row(
            source_name="getdeploying",
            family=family,
            url=url,
            fetch_ts=fetch_ts,
            fetch_ok=False,
            rows_parsed=0,
            providers_found=0,
            status_code=status_code,
            notes=str(exc)[:240],
        )


def azure_query_terms_for_family(family: str) -> list[str]:
    if family == "B200":
        return ["B200", "GB200"]
    return [family]


def fetch_azure_retail_price_items(term: str, *, timeout: float = 30.0, max_pages: int = 8) -> tuple[list[dict[str, Any]], int]:
    filter_expr = f"serviceName eq 'Virtual Machines' and contains(meterName, '{term}') and type eq 'Consumption'"
    encoded_filter = quote(filter_expr, safe="() ',")
    url = f"{AZURE_RETAIL_PRICES_ENDPOINT}?$top=1000&$filter={encoded_filter}"
    items: list[dict[str, Any]] = []
    status_code = 0
    pages = 0
    while url and pages < max_pages:
        response = requests.get(url, headers=REQUEST_HEADERS, timeout=timeout)
        status_code = int(response.status_code)
        response.raise_for_status()
        payload = response.json()
        page_items = payload.get("Items") if isinstance(payload.get("Items"), list) else []
        items.extend(item for item in page_items if isinstance(item, dict))
        url = str(payload.get("NextPageLink") or "")
        pages += 1
    return items, status_code


def fetch_azure_retail_offers(
    families: list[str] | tuple[str, ...],
    *,
    fetch_ts: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    offers: list[dict[str, Any]] = []
    health: list[dict[str, Any]] = []
    for family in normalize_gpu_families(families):
        family_items: list[dict[str, Any]] = []
        status_codes: list[int] = []
        errors: list[str] = []
        seen_items: set[str] = set()
        for term in azure_query_terms_for_family(family):
            try:
                items, status_code = fetch_azure_retail_price_items(term)
                status_codes.append(status_code)
                for item in items:
                    item_key = "|".join(
                        str(item.get(key) or "")
                        for key in ["meterId", "armRegionName", "skuName", "meterName", "type"]
                    )
                    if item_key in seen_items:
                        continue
                    seen_items.add(item_key)
                    family_items.append(item)
            except Exception as exc:
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                if status_code:
                    status_codes.append(int(status_code))
                errors.append(str(exc)[:180])
        family_offers = [
            normalized
            for item in family_items
            if (normalized := normalize_azure_retail_price_item(item, fetch_ts=fetch_ts)) is not None
            and str(normalized.get("gpu_family") or "") == family
        ]
        offers.extend(family_offers)
        providers_found = 1 if family_offers else 0
        billing_counts = {
            billing: sum(1 for item in family_offers if str(item.get("billing_type") or "") == billing)
            for billing in sorted({str(item.get("billing_type") or "") for item in family_offers if item.get("billing_type")})
        }
        notes = "billing_counts=" + json.dumps(billing_counts, sort_keys=True) if billing_counts else ""
        if errors:
            notes = (notes + "; " if notes else "") + "; ".join(errors)
        health.append(
            build_source_health_row(
                source_name="azure_retail_prices",
                family=family,
                url=AZURE_SOURCE_URL,
                fetch_ts=fetch_ts,
                fetch_ok=bool(family_offers) and not errors,
                rows_parsed=len(family_offers),
                providers_found=providers_found,
                status_code=status_codes[-1] if status_codes else None,
                notes=notes or "no_matching_linux_consumption_rows",
            )
        )
    return offers, health


def build_gpu_price_dataset(
    *,
    families: list[str] | tuple[str, ...] | None = None,
    previous_cache: dict[str, Any] | None = None,
    fetch_ts: str | None = None,
) -> dict[str, Any]:
    resolved_families = normalize_gpu_families(families)
    current_fetch_ts = fetch_ts or utcnow_iso()
    previous = normalize_gpu_price_cache(previous_cache or {}, resolved_families)
    offers: list[dict[str, Any]] = []
    source_health: list[dict[str, Any]] = []
    for family in resolved_families:
        gpusio_url = str(GPU_FAMILY_CONFIGS[family]["gpusio_url"])
        try:
            html_text, status_code, final_url = request_html(gpusio_url)
            family_offers = parse_gpusio_offers(
                html_text,
                family=family,
                source_url=final_url,
                fetch_ts=current_fetch_ts,
            )
            offers.extend(family_offers)
            source_health.append(
                build_source_health_row(
                    source_name="gpusio",
                    family=family,
                    url=final_url,
                    fetch_ts=current_fetch_ts,
                    fetch_ok=bool(family_offers),
                    rows_parsed=len(family_offers),
                    providers_found=len({str(item.get("provider_slug") or "") for item in family_offers}),
                    status_code=status_code,
                    notes="" if family_offers else "no_provider_rows_parsed",
                )
            )
        except Exception as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            source_health.append(
                build_source_health_row(
                    source_name="gpusio",
                    family=family,
                    url=gpusio_url,
                    fetch_ts=current_fetch_ts,
                    fetch_ok=False,
                    rows_parsed=0,
                    providers_found=0,
                    status_code=status_code,
                    notes=str(exc)[:240],
                )
            )
        source_health.append(probe_getdeploying_health(family, current_fetch_ts))

    azure_offers, azure_health = fetch_azure_retail_offers(resolved_families, fetch_ts=current_fetch_ts)
    offers.extend(azure_offers)
    source_health.extend(azure_health)

    raw_snapshots = build_raw_snapshots(offers)
    core_index_offers = [item for item in offers if str(item.get("source_name") or "") != "azure_retail_prices"]
    daily_index = build_daily_index(
        core_index_offers,
        fetch_ts=current_fetch_ts,
        previous_daily_index=previous.get("daily_index") if isinstance(previous.get("daily_index"), list) else [],
    )
    csp_daily_index = build_csp_daily_index(
        offers,
        fetch_ts=current_fetch_ts,
        previous_csp_daily_index=previous.get("csp_daily_index") if isinstance(previous.get("csp_daily_index"), list) else [],
    )
    latest = build_latest_summary(core_index_offers, daily_index, fetch_ts=current_fetch_ts)
    provider_count = len({str(item.get("provider_slug") or "") for item in offers if item.get("provider_slug")})
    history_snapshot = {
        "updated_at": current_fetch_ts,
        "families": resolved_families,
        "offer_count": len(offers),
        "provider_count": provider_count,
        "daily_index": [item for item in daily_index if str(item.get("date") or "") == current_fetch_ts[:10]],
        "csp_daily_index": [item for item in csp_daily_index if str(item.get("date") or "") == current_fetch_ts[:10]],
        "latest": latest,
    }
    history = [
        item
        for item in collapse_history_latest(previous.get("history", []))
        if isinstance(item, dict) and str(item.get("updated_at") or "")[:10] != current_fetch_ts[:10]
    ]
    history.append(history_snapshot)
    history = collapse_history_latest(history)[-120:]
    return {
        "version": GPU_PRICE_CACHE_VERSION,
        "updated_at": current_fetch_ts,
        "families": resolved_families,
        "source": {
            "name": "GPUs.io + GetDeploying + Azure Retail Prices",
            "url": str(GPU_FAMILY_CONFIGS[resolved_families[0]]["gpusio_url"]),
            "endpoint": "public GPU pages + Next.js flight parser + Azure Retail Prices API + daily median indexes",
        },
        "notes": (
            "GPUs.io on-demand provider summaries feed the core GPU market index. "
            "Azure Retail Prices rows feed a separate CSP reference curve; GetDeploying is probed and logged."
        ),
        "storage_policy": GPU_PRICE_STORAGE_POLICY,
        "summary": {
            "offer_count": len(offers),
            "raw_snapshot_count": len(raw_snapshots),
            "daily_index_count": len(daily_index),
            "csp_daily_index_count": len(csp_daily_index),
            "source_health_count": len(source_health),
            "provider_count": provider_count,
        },
        "latest": latest,
        "raw_snapshots": raw_snapshots,
        "normalized_offers": offers,
        "daily_index": daily_index,
        "csp_daily_index": csp_daily_index,
        "source_health": source_health,
        "history": history,
    }
