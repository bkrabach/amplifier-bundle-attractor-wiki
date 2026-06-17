import asyncio
from amplifier_foundation import load_bundle

B = "/home/bkrabach/dev/llm-wiki-pipeline/amplifier-bundle-attractor"
CASES = [
    ("local-profile-yaml", f"{B}/profiles/attractor-profile-anthropic.yaml"),
    ("file-uri-profile", f"file://{B}/profiles/attractor-profile-anthropic.yaml"),
    ("local-pipeline-bundle", f"{B}/bundles/attractor-pipeline.yaml"),
    ("git-yaml-suffix", "git+https://github.com/microsoft/amplifier-bundle-attractor@main#subdirectory=profiles/attractor-profile-anthropic.yaml"),
]


async def main():
    for label, src in CASES:
        try:
            b = await load_bundle(src)
            print(f"OK   {label}: name={getattr(b, 'name', '?')}")
        except Exception as e:
            print(f"FAIL {label}: {type(e).__name__}: {str(e)[:160]}")


asyncio.run(main())
