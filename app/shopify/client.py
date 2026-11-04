
import httpx

from app.core.config import settings


class ShopifyClient:

    def __init__(self):
        self.url = (
            f"https://{settings.SHOPIFY_STORE_DOMAIN}"
            f"/admin/api/{settings.SHOPIFY_API_VERSION}/graphql.json"
        )

        self.headers = {
            "X-Shopify-Access-Token": settings.SHOPIFY_ADMIN_ACCESS_TOKEN,
            "Content-Type": "application/json",
        }

    # -------------------------------------------------
    # 1. COMMON GRAPHQL REQUEST
    # -------------------------------------------------

    async def graphql(self, query: str, variables: dict | None = None):
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                self.url,
                headers=self.headers,
                json={
                    "query": query,
                    "variables": variables or {},
                },
            )

        if response.status_code != 200:
            raise RuntimeError(
                f"Shopify API HTTP {response.status_code}: {response.text}"
            )

        result = response.json()

        if result.get("errors"):
            raise RuntimeError(
                f"Shopify GraphQL errors: {result['errors']}"
            )

        data = result.get("data")

        if data is None:
            raise RuntimeError("Shopify returned no GraphQL data.")

        return data

    # -------------------------------------------------
    # 2. NORMALIZE PRODUCT ID
    # -------------------------------------------------

    def normalize_product_id(self, product_id: str) -> str:
        product_id = str(product_id).strip()

        if product_id.isdigit():
            return f"gid://shopify/Product/{product_id}"

        if product_id.startswith("gid://shopify/Product/"):
            return product_id

        raise ValueError("Invalid Shopify product ID.")

    # -------------------------------------------------
    # 3. TEST SHOPIFY CONNECTION
    # -------------------------------------------------

    async def test_connection(self):
        query = """
        query {
            shop {
                name
                myshopifyDomain
            }
        }
        """

        data = await self.graphql(query)
        return data["shop"]

    # -------------------------------------------------
    # 4. REUSABLE PRODUCT FIELDS
    # -------------------------------------------------

    def product_fields(self):
        return """
            id
            title
            handle
            descriptionHtml
            vendor
            productType
            status
            tags

            category {
                id
                fullName
            }

            seo {
                title
                description
            }

            featuredImage {
                url
                altText
            }

            images(first: 20) {
                nodes {
                    id
                    url
                    altText
                }
            }

            metafields(first: 50) {
                nodes {
                    id
                    namespace
                    key
                    value
                    type
                }
            }

            variants(first: 50) {
                nodes {
                    id
                    title
                    sku
                    barcode
                    price
                    compareAtPrice
                    inventoryQuantity

                    inventoryItem {
                        tracked
                        requiresShipping

                        measurement {
                            weight {
                                value
                                unit
                            }
                        }
                    }
                }
            }
        """

    # -------------------------------------------------
    # 5. GET ONE EXACT PRODUCT
    # -------------------------------------------------

    async def get_product_by_id(self, product_id: str):
        product_gid = self.normalize_product_id(product_id)

        query = """
        query GetProductReadiness($id: ID!) {
            product(id: $id) {
                """ + self.product_fields() + """
            }
        }
        """

        data = await self.graphql(
            query,
            {"id": product_gid},
        )

        product = data.get("product")

        if not product:
            raise ValueError(
                f"Shopify product not found: {product_gid}"
            )

        if product.get("id") != product_gid:
            raise RuntimeError(
                "PRODUCT_ID_MISMATCH: Shopify returned a different product."
            )

        return product

    # -------------------------------------------------
    # 6. GET ALL PRODUCTS FOR AUDIT
    # -------------------------------------------------

    async def get_products(self, limit: int = 50):

        query = """
        query GetProducts($first: Int!, $after: String) {
            products(first: $first, after: $after) {
                pageInfo {
                    hasNextPage
                    endCursor
                }

                nodes {
                    """ + self.product_fields() + """
                }
            }
        }
        """

        maximum = max(
            1,
            min(limit, settings.MAX_PRODUCTS_PER_AUDIT),
        )

        products = []
        cursor = None

        while len(products) < maximum:

            batch_size = min(25, maximum - len(products))

            data = await self.graphql(
                query,
                {
                    "first": batch_size,
                    "after": cursor,
                },
            )

            connection = data["products"]
            nodes = connection["nodes"]

            products.extend(nodes)

            page_info = connection["pageInfo"]

            if not page_info["hasNextPage"] or not nodes:
                break

            cursor = page_info["endCursor"]

        return products

    # -------------------------------------------------
    # 7. UPDATE ONLY PRODUCT DESCRIPTION
    # -------------------------------------------------

    async def update_product_description(
        self,
        product_id: str,
        description_html: str,
    ):

        product_gid = self.normalize_product_id(product_id)

        query = """
        mutation UpdateProductDescription(
            $product: ProductUpdateInput!
        ) {
            productUpdate(product: $product) {
                product {
                    id
                    title
                    descriptionHtml
                }

                userErrors {
                    field
                    message
                }
            }
        }
        """

        data = await self.graphql(
            query,
            {
                "product": {
                    "id": product_gid,
                    "descriptionHtml": description_html,
                }
            },
        )

        result = data["productUpdate"]

        if result["userErrors"]:
            raise RuntimeError(
                f"Shopify update errors: {result['userErrors']}"
            )

        updated_product = result.get("product")

        if (
            not updated_product
            or updated_product.get("id") != product_gid
        ):
            raise RuntimeError(
                "Shopify update verification failed."
            )

        return updated_product


    # -------------------------------------------------
    # 8. UPDATE APPROVED PRODUCT FIELDS
    # -------------------------------------------------

    async def update_product_fields(
        self,
        product_id: str,
        updates: dict,
    ):
        product_gid = self.normalize_product_id(product_id)

        allowed_fields = {
            "title",
            "descriptionHtml",
            "productType",
            "tags",
            "seo",
        }

        if not updates:
            raise ValueError("No product fields were approved.")

        invalid_fields = set(updates.keys()) - allowed_fields

        if invalid_fields:
            raise ValueError(
                f"Unsupported product fields: {invalid_fields}"
            )

        product_input = {
            "id": product_gid,
        }

        # Validate title
        if "title" in updates:
            if not isinstance(updates["title"], str) or not updates["title"].strip():
                raise ValueError("Invalid product title.")

            product_input["title"] = updates["title"].strip()

        # Validate description
        if "descriptionHtml" in updates:
            if not isinstance(updates["descriptionHtml"], str):
                raise ValueError("Invalid product description.")

            product_input["descriptionHtml"] = updates["descriptionHtml"]

        # Validate product type
        if "productType" in updates:
            if not isinstance(updates["productType"], str) or not updates["productType"].strip():
                raise ValueError("Invalid product type.")

            product_input["productType"] = updates["productType"].strip()

        # Validate tags
        if "tags" in updates:
            if not isinstance(updates["tags"], list):
                raise ValueError("Tags must be a list.")

            product_input["tags"] = updates["tags"]

        # Validate SEO
        if "seo" in updates:
            seo = updates["seo"]

            if not isinstance(seo, dict):
                raise ValueError("SEO must be an object.")

            if set(seo.keys()) - {"title", "description"}:
                raise ValueError("Unsupported SEO field.")

            product_input["seo"] = seo

        query = """
        mutation UpdateApprovedProductFields(
            $product: ProductUpdateInput!
        ) {
            productUpdate(product: $product) {
                product {
                    id
                    title
                    descriptionHtml
                    productType
                    tags
                    seo {
                        title
                        description
                    }
                }

                userErrors {
                    field
                    message
                }
            }
        }
        """

        data = await self.graphql(
            query,
            {
                "product": product_input,
            },
        )

        result = data["productUpdate"]

        if result["userErrors"]:
            raise RuntimeError(
                f"Shopify update errors: {result['userErrors']}"
            )

        updated_product = result.get("product")

        if (
            not updated_product
            or updated_product.get("id") != product_gid
        ):
            raise RuntimeError(
                "Shopify product update verification failed."
            )

        return updated_product


# Shared Shopify client instance
shopify_client = ShopifyClient()
