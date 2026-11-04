
from bson import ObjectId
from bson.errors import InvalidId

from app.agent.auditor import audit_products, audit_product
from app.agent.recommender import (
    generate_product_suggestions,
    prepare_description_proposal,
)
from app.core.config import settings
from app.db.mongodb import audit_collection, proposal_collection
from app.shopify.client import shopify_client


async def run_product_audit():
    products = await shopify_client.get_products(
        limit=settings.MAX_PRODUCTS_PER_AUDIT
    )

    report = audit_products(products)

    saved_report = {
        **report,
        "store": settings.SHOPIFY_STORE_DOMAIN,
    }

    result = audit_collection.insert_one(saved_report)

    report["audit_id"] = str(result.inserted_id)

    return report


async def get_product_readiness(product_id: str):
    product = await shopify_client.get_product_by_id(product_id)

    return audit_product(product)


async def get_product_suggestions(product_id: str):
    product = await shopify_client.get_product_by_id(product_id)

    audit = audit_product(product)

    suggestions = await generate_product_suggestions(product)

    return {
        "product_id": product["id"],
        "product_title": product["title"],
        "audit": audit,
        "suggestions": suggestions,
    }


async def create_description_proposal(product_id: str):
    product = await shopify_client.get_product_by_id(product_id)

    proposal = await prepare_description_proposal(product)

    saved_proposal = {
        **proposal,
        "store": settings.SHOPIFY_STORE_DOMAIN,
        "product_id": product["id"],
        "approval_status": "pending",
    }

    result = proposal_collection.insert_one(saved_proposal)

    proposal["proposal_id"] = str(result.inserted_id)

    return proposal


async def approve_description_proposal(proposal_id: str):
    try:
        object_id = ObjectId(proposal_id)
    except (InvalidId, TypeError):
        raise ValueError("Invalid proposal ID.")

    proposal_filter = {
        "_id": object_id,
        "store": settings.SHOPIFY_STORE_DOMAIN,
    }

    # Claim the proposal so it cannot be approved twice.
    claim = proposal_collection.update_one(
        {
            **proposal_filter,
            "approval_status": "pending",
        },
        {
            "$set": {
                "approval_status": "approving",
            }
        },
    )

    if claim.modified_count != 1:
        existing = proposal_collection.find_one(proposal_filter)

        if not existing:
            raise ValueError("Proposal not found.")

        raise ValueError(
            "Proposal is not pending. It may already be processed."
        )

    shopify_updated = False

    try:
        proposal = proposal_collection.find_one(proposal_filter)

        if not proposal:
            raise ValueError("Proposal not found.")

        product_id = proposal.get("product_id")
        proposed_updates = proposal.get("proposed_updates") or {}
        original_values = proposal.get("current_values") or {}

        if not product_id or not proposed_updates:
            raise ValueError(
                "Proposal has no product ID or approved field suggestions. "
                "Create a new proposal."
            )

        # Fetch the exact Shopify product.
        current_product = await shopify_client.get_product_by_id(
            product_id
        )

        if current_product.get("id") != product_id:
            raise ValueError("Shopify product ID mismatch.")

        # Check that the product fields have not changed
        # since the proposal was created.
        current_seo = current_product.get("seo") or {}

        current_values = {
            "title": current_product.get("title") or "",
            "descriptionHtml": current_product.get("descriptionHtml") or "",
            "productType": current_product.get("productType") or "",
            "tags": current_product.get("tags") or [],
            "seo_title": current_seo.get("title") or "",
            "seo_description": current_seo.get("description") or "",
        }

        for field in proposed_updates:

            if field == "seo":
                if (
                    "title" in proposed_updates["seo"]
                    and current_values["seo_title"]
                    != original_values.get("seo_title", "")
                ):
                    raise ValueError(
                        "SEO title changed after proposal creation. "
                        "Generate a new proposal."
                    )

                if (
                    "description" in proposed_updates["seo"]
                    and current_values["seo_description"]
                    != original_values.get("seo_description", "")
                ):
                    raise ValueError(
                        "SEO description changed after proposal creation. "
                        "Generate a new proposal."
                    )

            elif field in current_values:

                if current_values[field] != original_values.get(field):
                    raise ValueError(
                        f"Product field '{field}' changed after proposal "
                        "creation. Generate a new proposal."
                    )

        # Update only the fields included in this proposal.
        updated_product = await shopify_client.update_product_fields(
            product_id=product_id,
            updates=proposed_updates,
        )

        shopify_updated = True

        if updated_product.get("id") != product_id:
            raise RuntimeError("Updated product ID does not match.")

        # Save approval status and Shopify result.
        saved = proposal_collection.update_one(
            {
                **proposal_filter,
                "approval_status": "approving",
            },
            {
                "$set": {
                    "approval_status": "approved",
                    "updated_product": updated_product,
                }
            },
        )

        if saved.modified_count != 1:
            raise RuntimeError(
                "Shopify was updated, but MongoDB could not save "
                "the approval status. Check Shopify before retrying."
            )

        return {
            "message": "Approved product fields updated successfully.",
            "approval_status": "approved",
            "updated_fields": list(proposed_updates.keys()),
            "product": updated_product,
        }

    except Exception:
        # Do not restore pending after Shopify has been updated.
        if not shopify_updated:
            proposal_collection.update_one(
                {
                    **proposal_filter,
                    "approval_status": "approving",
                },
                {
                    "$set": {
                        "approval_status": "pending",
                    }
                },
            )

        raise


def reject_description_proposal(proposal_id: str):
    try:
        object_id = ObjectId(proposal_id)
    except (InvalidId, TypeError):
        raise ValueError("Invalid proposal ID.")

    result = proposal_collection.update_one(
        {
            "_id": object_id,
            "store": settings.SHOPIFY_STORE_DOMAIN,
            "approval_status": "pending",
        },
        {
            "$set": {
                "approval_status": "rejected",
            }
        },
    )

    if result.modified_count != 1:
        raise ValueError(
            "Pending proposal not found. It may already be processed."
        )

    return {
        "message": "Description proposal rejected.",
        "approval_status": "rejected",
    }
