
import html
import json
import re

from app.agent.gemini_client import generate_gemini_text


def clean_description(text: str) -> str:
    """Keep only customer-facing description text."""

    if not text:
        return ""

    text = re.sub(r"```(?:html|text)?", "", text, flags=re.IGNORECASE)
    text = text.replace("```", "").strip()

    unwanted_sections = [
        "merchant information needed",
        "missing information",
        "information needed from merchant",
        "additional information required",
        "internal notes",
    ]

    lower_text = text.lower()

    positions = [
        lower_text.find(section)
        for section in unwanted_sections
        if lower_text.find(section) >= 0
    ]

    if positions:
        text = text[:min(positions)]

    lines = []

    for line in text.splitlines():
        line = line.strip()

        if not line:
            continue

        if line.lower() in {
            "description:",
            "product description:",
            "improved description:",
            "customer-facing description:",
        }:
            continue

        line = re.sub(r"^[-*•]\s*", "", line)
        line = re.sub(r"^#{1,6}\s*", "", line)
        line = line.replace("**", "").replace("__", "")

        lines.append(line)

    return "\n".join(lines).strip()

def text_to_html(text: str) -> str:
    """Convert AI description into safe paragraph HTML."""

    if not text:
        return ""

    # Gemini may already return HTML paragraphs.
    # Convert them back to plain text before rebuilding HTML.
    text = html.unescape(str(text))
    text = re.sub(r"<[^>]*>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return ""

    return f"<p>{html.escape(text)}</p>"


def parse_ai_json(text: str) -> dict:
    """Parse a JSON object returned by the AI."""

    text = (text or "").strip()

    text = re.sub(
        r"^```(?:json)?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\s*```$", "", text)

    start = text.find("{")
    end = text.rfind("}")

    if start < 0 or end < start:
        raise ValueError("AI did not return valid JSON suggestions.")

    try:
        result = json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError("AI returned invalid JSON.") from exc

    if not isinstance(result, dict):
        raise ValueError("AI response must be a JSON object.")

    return result


def build_verified_product_facts(product: dict) -> dict:
    """Pass actual Shopify facts to the AI, not invented facts."""

    variants = (product.get("variants") or {}).get("nodes", [])
    images = (product.get("images") or {}).get("nodes", [])
    category = product.get("category") or {}
    seo = product.get("seo") or {}

    return {
        "id": product.get("id"),
        "title": product.get("title"),
        "vendor": product.get("vendor"),
        "product_type": product.get("productType"),
        "category": category.get("fullName"),
        "tags": product.get("tags") or [],
        "existing_description": product.get("descriptionHtml") or "",
        "seo_title": seo.get("title"),
        "seo_description": seo.get("description"),
        "images": [
            {
                "alt_text": image.get("altText"),
            }
            for image in images
        ],
        "variants": [
            {
                "title": variant.get("title"),
                "sku": variant.get("sku"),
                "barcode": variant.get("barcode"),
                "price": variant.get("price"),
                "compare_at_price": variant.get("compareAtPrice"),
                "requires_shipping": variant.get("requiresShipping"),
            }
            for variant in variants
        ],
    }


async def generate_product_suggestions(product: dict) -> dict:
    """Generate suggestions for a complete Shopify product."""

    facts = build_verified_product_facts(product)

    prompt = f"""
You are a Shopify product catalog improvement assistant.

Use the following verified Shopify product data:
{json.dumps(facts, ensure_ascii=False)}

Return ONE valid JSON object with these keys:

{{
  "title_suggestion": "",
  "description_suggestion": "",
  "product_type_suggestion": "",
  "category_suggestion": "",
  "tags_suggestion": [],
  "seo_title_suggestion": "",
  "seo_description_suggestion": "",
  "image_alt_suggestions": [],
  "missing_information": [],
  "explanations": []
}}

STRICT RULES:

1. Never invent product facts.
2. Do not invent SKU, barcode, weight, price, inventory, dimensions,
   material, growing instructions, sunlight, watering, or shipping facts.
3. Do not invent vendor or brand names.
4. If a fact is missing, add a clear question to missing_information.
5. Suggest a category only when the actual product identity supports it.
   Do not pretend that your suggestion is already a Shopify category.
6. For category_suggestion, provide a suggested category name as text,
   not a made-up Shopify category ID.
7. Tags must be based on verified product facts.
8. SEO suggestions must not contain unsupported claims.
9. Description must contain only customer-facing product copy.
10. Do not put missing-information notes inside the description.
11. Do not put internal notes or explanations inside the description.
12. If the existing description is already accurate and useful,
    do not change it unnecessarily.
13. Return empty strings or empty arrays when a suggestion is not justified.
14. Return JSON only. No Markdown and no text outside the JSON.

For missing_information, ask for real facts that the merchant can supply.
Do not ask for a barcode if the merchant does not use one for this product.
"""

    raw = await generate_gemini_text(prompt)
    result = parse_ai_json(raw)

    description = clean_description(
        str(result.get("description_suggestion") or "")
    )

    return {
        "product_id": product.get("id"),
        "product_title": product.get("title"),
        "title_suggestion": str(
            result.get("title_suggestion") or ""
        ).strip(),
        "description_suggestion": description,
        "product_type_suggestion": str(
            result.get("product_type_suggestion") or ""
        ).strip(),
        "category_suggestion": str(
            result.get("category_suggestion") or ""
        ).strip(),
        "tags_suggestion": (
            result.get("tags_suggestion")
            if isinstance(result.get("tags_suggestion"), list)
            else []
        ),
        "seo_title_suggestion": str(
            result.get("seo_title_suggestion") or ""
        ).strip(),
        "seo_description_suggestion": str(
            result.get("seo_description_suggestion") or ""
        ).strip(),
        "image_alt_suggestions": (
            result.get("image_alt_suggestions")
            if isinstance(result.get("image_alt_suggestions"), list)
            else []
        ),
        "missing_information": (
            result.get("missing_information")
            if isinstance(result.get("missing_information"), list)
            else []
        ),
        "explanations": (
            result.get("explanations")
            if isinstance(result.get("explanations"), list)
            else []
        ),
    }

async def prepare_description_proposal(product: dict) -> dict:
    """
    Prepare a complete product proposal.
    Includes all supported AI suggestions, not just description.
    """

    suggestions = await generate_product_suggestions(product)

    current_seo = product.get("seo") or {}
    current_tags = product.get("tags") or []

    current_values = {
        "title": product.get("title") or "",
        "descriptionHtml": product.get("descriptionHtml") or "",
        "productType": product.get("productType") or "",
        "tags": current_tags,
        "seo_title": current_seo.get("title") or "",
        "seo_description": current_seo.get("description") or "",
    }

    proposed_updates = {}

    # 1. Product title
    new_title = suggestions.get("title_suggestion", "").strip()

    if new_title and new_title != current_values["title"]:
        proposed_updates["title"] = new_title

    # 2. Product description
    new_description = suggestions.get("description_suggestion", "")

    if new_description:
        new_description_html = text_to_html(new_description)

        if new_description_html != current_values["descriptionHtml"]:
            proposed_updates["descriptionHtml"] = new_description_html

    # 3. Product type
    new_product_type = (
        suggestions.get("product_type_suggestion") or ""
    ).strip()

    if (
        new_product_type
        and new_product_type != current_values["productType"]
    ):
        proposed_updates["productType"] = new_product_type

    # 4. Product tags
    new_tags = suggestions.get("tags_suggestion") or []

    if isinstance(new_tags, list):
        # Preserve existing tags and add new suggestions.
        merged_tags = list(dict.fromkeys(
            current_tags + [
                str(tag).strip()
                for tag in new_tags
                if str(tag).strip()
            ]
        ))

        if merged_tags != current_tags:
            proposed_updates["tags"] = merged_tags

    # 5. SEO title
    new_seo_title = (
        suggestions.get("seo_title_suggestion") or ""
    ).strip()

    if new_seo_title and new_seo_title != current_values["seo_title"]:
        proposed_updates["seo"] = {}

        proposed_updates["seo"]["title"] = new_seo_title

    # 6. SEO description
    new_seo_description = (
        suggestions.get("seo_description_suggestion") or ""
    ).strip()

    if (
        new_seo_description
        and new_seo_description != current_values["seo_description"]
    ):
        proposed_updates.setdefault("seo", {})

        proposed_updates["seo"]["description"] = new_seo_description

    if not proposed_updates:
        raise ValueError(
            "AI did not generate any new product field suggestions."
        )

    return {
        "product_id": product["id"],
        "product_title": product.get("title"),

        "current_values": current_values,
        "proposed_updates": proposed_updates,

        "missing_information": suggestions.get(
            "missing_information", []
        ),

        "explanations": suggestions.get(
            "explanations", []
        ),

        "approval_status": "pending",
    }
