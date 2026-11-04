import asyncio

from app.agent.gemini_client import generate_gemini_text


async def main():
    prompt = """
    Write a short product description for Basil Seeds.

    Only use these facts:
    Product name: Basil Seeds
    Product type: Seeds

    Do not invent specifications.
    """

    result = await generate_gemini_text(prompt)

    print("\nGemini response:")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())