
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agent.service import (
    run_product_audit,
    get_product_readiness,
    get_product_suggestions,
    create_description_proposal,
    approve_description_proposal,
    reject_description_proposal,
)

from app.shopify.client import shopify_client
from app.db.mongodb import check_mongodb


router = APIRouter(
    prefix="/agent",
    tags=["Commerce Readiness Agent"],
)


class ProposalRequest(BaseModel):
    product_id: str = Field(min_length=1, max_length=200)


@router.get("/health")
async def agent_health():
    return {
        "status": "running",
        "mongodb_connected": check_mongodb(),
    }


@router.get("/shopify/test")
async def test_shopify():
    try:
        shop = await shopify_client.test_connection()

        return {
            "connected": True,
            "shop": shop,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )


@router.post("/audit")
async def audit_store_products():
    try:
        return await run_product_audit()

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


@router.get("/products/{product_id}/readiness")
async def product_readiness(product_id: str):
    try:
        return await get_product_readiness(product_id)

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        )

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )


@router.get("/products/{product_id}/suggestions")
async def product_suggestions(product_id: str):
    try:
        return await get_product_suggestions(product_id)

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        )

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )


@router.post("/proposals")
async def create_proposal(request: ProposalRequest):
    try:
        return await create_description_proposal(
            request.product_id
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        )

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )


@router.post("/proposals/{proposal_id}/approve")
async def approve_proposal(proposal_id: str):
    try:
        return await approve_description_proposal(proposal_id)

    except ValueError as exc:
        message = str(exc)

        if "invalid" in message.lower():
            status_code = 400
        elif "not found" in message.lower():
            status_code = 404
        else:
            status_code = 409

        raise HTTPException(
            status_code=status_code,
            detail=message,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )


@router.post("/proposals/{proposal_id}/reject")
async def reject_proposal(proposal_id: str):
    try:
        return reject_description_proposal(proposal_id)

    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )
