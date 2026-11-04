
import re

from app.core.config import settings


def clean_text(value: str) -> str:
    if not value:
        return ""

    value = re.sub(r"<[^>]*>", " ", str(value))
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def valid_positive_number(value) -> bool:
    try:
        return float(value) > 0
    except (ValueError, TypeError):
        return False


def audit_product(product: dict) -> dict:
    issues = []
    fields = []

    def add_field(
        name: str,
        value,
        problem: str | None,
        action: str,
        affected_count: int | None = None,
    ):
        item = {
            "field": name,
            "value": value,
            "status": "issue" if problem else "ok",
            "issue": problem,
            "action": action if problem else None,
        }

        if affected_count is not None:
            item["affected_count"] = affected_count

        fields.append(item)

        if problem:
            issues.append({
                "field": name,
                "issue": problem,
                "action": action,
            })

    title = (product.get("title") or "").strip()
    description = clean_text(product.get("descriptionHtml"))
    vendor = (product.get("vendor") or "").strip()
    product_type = (product.get("productType") or "").strip()
    tags = product.get("tags") or []
    category = product.get("category") or {}
    seo = product.get("seo") or {}
    images = (product.get("images") or {}).get("nodes", [])
    variants = (product.get("variants") or {}).get("nodes", [])
    metafields = (product.get("metafields") or {}).get("nodes", [])

    # 1. Title
    unclear_title = (
        len(title) < 3
        or title.lower() in {"product", "untitled", "new product"}
    )

    add_field(
        "title",
        title,
        "Title is empty or unclear." if unclear_title else None,
        "Generate an improved title suggestion.",
    )

    # 2. Description
    word_count = len(description.split())

    generic_phrases = [
        "best quality",
        "premium quality",
        "good product",
        "high quality product",
        "best product",
    ]

    weak_description = (
        not description
        or word_count < settings.MIN_DESCRIPTION_WORDS
        or any(
            phrase in description.lower()
            for phrase in generic_phrases
        )
    )

    add_field(
        "description",
        {
            "text": description,
            "word_count": word_count,
        },
        "Description is empty or weak." if weak_description else None,
        "Generate a factual customer-facing description.",
    )

    # 3. Shopify category
    category_name = category.get("fullName")

    add_field(
        "category",
        category_name,
        "Product category is missing." if not category_name else None,
        "Suggest a suitable Shopify product category.",
    )

    # 4. Product type
    add_field(
        "product_type",
        product_type,
        "Product type is missing." if not product_type else None,
        "Suggest a product type using verified product information.",
    )

    # 5. Vendor
    add_field(
        "vendor",
        vendor,
        "Vendor is missing." if not vendor else None,
        "Ask the merchant to provide the actual brand or vendor.",
    )

    # 6. Tags
    tag_count = len(tags)

    add_field(
        "tags",
        tags,
        "No product tags found." if tag_count == 0 else None,
        "Generate relevant tags using verified product facts.",
    )

    # 7. Images
    image_count = len(images)

    missing_alt = sum(
        1 for image in images
        if not (image.get("altText") or "").strip()
    )

    image_problem = None

    if image_count == 0:
        image_problem = "Product has no images."
    elif missing_alt:
        image_problem = f"{missing_alt} image(s) have no alt text."

    add_field(
        "images",
        {
            "image_count": image_count,
            "missing_alt_text": missing_alt,
        },
        image_problem,
        "Recommend image upload or suggest factual image alt text.",
    )

    # 8. Variants, SKU and barcode
    missing_sku = sum(
        1 for variant in variants
        if not (variant.get("sku") or "").strip()
    )

    missing_barcode = sum(
        1 for variant in variants
        if not (variant.get("barcode") or "").strip()
    )

    add_field(
        "sku",
        None if not variants else [
            variant.get("sku") for variant in variants
        ],
        f"{missing_sku} variant(s) have no SKU." if missing_sku else None,
        "Ask the merchant to provide unique SKUs.",
        missing_sku,
    )

    add_field(
        "barcode",
        None if not variants else [
            variant.get("barcode") for variant in variants
        ],
        (
            f"{missing_barcode} variant(s) have no barcode."
            if missing_barcode else None
        ),
        "Ask for genuine barcodes. Never invent them.",
        missing_barcode,
    )

    # 9. Price and compare-at price
    invalid_prices = sum(
        1 for variant in variants
        if not valid_positive_number(variant.get("price"))
    )

    add_field(
        "price",
        [variant.get("price") for variant in variants],
        (
            f"{invalid_prices} variant(s) have a missing or invalid price."
            if invalid_prices else None
        ),
        "Ask the merchant to provide the correct selling price.",
        invalid_prices,
    )

    invalid_compare_prices = sum(
        1 for variant in variants
        if (
            variant.get("compareAtPrice") is not None
            and (
                not valid_positive_number(variant.get("compareAtPrice"))
                or float(variant["compareAtPrice"])
                <= float(variant.get("price") or 0)
            )
        )
    )

    add_field(
        "compare_at_price",
        [variant.get("compareAtPrice") for variant in variants],
        (
            f"{invalid_compare_prices} variant(s) have an invalid compare-at price."
            if invalid_compare_prices else None
        ),
        "Review compare-at prices only if the product has a genuine higher reference price.",
        invalid_compare_prices,
    )

    # 10. Inventory tracking
    untracked = sum(
        1 for variant in variants
        if not (
            (variant.get("inventoryItem") or {}).get("tracked") is True
        )
    )

    add_field(
        "inventory",
        [
            {
                "variant": variant.get("title"),
                "tracked": (
                    variant.get("inventoryItem") or {}
                ).get("tracked"),
                "quantity": variant.get("inventoryQuantity"),
            }
            for variant in variants
        ],
        (
            f"{untracked} variant(s) are not inventory tracked."
            if untracked else None
        ),
        "Review inventory tracking and stock availability.",
        untracked,
    )

    # 11. Weight
    missing_weight = 0

    for variant in variants:
        inventory_item = variant.get("inventoryItem") or {}
        measurement = inventory_item.get("measurement") or {}
        weight = measurement.get("weight") or {}

        if not valid_positive_number(weight.get("value")):
            missing_weight += 1

    add_field(
        "weight",
        [
            (
                (variant.get("inventoryItem") or {})
                .get("measurement") or {}
            ).get("weight")
            for variant in variants
        ],
        (
            f"{missing_weight} variant(s) have no valid weight."
            if missing_weight else None
        ),
        "Ask the merchant for the actual product weight.",
        missing_weight,
    )

    # 12. Shipping
    physical_variants = [
        variant for variant in variants
        if variant.get("requiresShipping") is True
    ]

    add_field(
        "shipping",
        {
            "physical_variant_count": len(physical_variants),
            "shipping_required": bool(physical_variants),
        },
        None,
        "Review shipping configuration.",
    )

    # 13. Metafields
    metafield_count = len(metafields)

    add_field(
        "metafields",
        [
            {
                "namespace": item.get("namespace"),
                "key": item.get("key"),
                "value": item.get("value"),
            }
            for item in metafields
        ],
        (
            "No product metafields found."
            if metafield_count == 0 else None
        ),
        "Suggest relevant product attributes after identifying the product type.",
    )

    # 14. SEO title
    seo_title = (seo.get("title") or "").strip()

    add_field(
        "seo_title",
        seo_title,
        "SEO title is missing." if not seo_title else None,
        "Generate an SEO title using verified product facts.",
    )

    # 15. SEO description
    seo_description = (seo.get("description") or "").strip()

    add_field(
        "seo_description",
        seo_description,
        (
            "SEO description is missing."
            if not seo_description else None
        ),
        "Generate an SEO description using verified product facts.",
    )

    return {
        "product_id": product.get("id"),
        "title": title,
        "status": product.get("status"),
        "issue_count": len(issues),
        "is_ready": len(issues) == 0,
        "fields": fields,
        "issues": issues,
    }


def audit_products(products: list) -> dict:
    results = [
        audit_product(product)
        for product in products
    ]

    return {
        "total_products": len(results),
        "ready_products": sum(
            1 for item in results if item["is_ready"]
        ),
        "products_with_issues": sum(
            1 for item in results if not item["is_ready"]
        ),
        "total_issues": sum(
            item["issue_count"] for item in results
        ),
        "results": results,
    }
