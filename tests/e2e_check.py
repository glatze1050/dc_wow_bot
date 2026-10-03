# -*- coding: utf-8 -*-
"""Runs the real /wow check callback against a fake interaction.

The renderers were tested in isolation and shipped broken twice, because the
failures sat in the command body that glues them together. This exercises
that body end to end.
"""
import asyncio
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import bot as B  # noqa: E402

# Rendered pages land here so a failure can be looked at; gitignored.
OUT = os.path.join(ROOT, "tests", "output")
os.makedirs(OUT, exist_ok=True)

# Two profiles: one ranked everywhere, one with gaps. Override with
#   python tests/e2e_check.py <name> <realm> [region]
CHARACTERS = [
    ("nariak", "blackrock", "eu"),
    ("ellariasand", "blackrock", "eu"),
]
if len(sys.argv) >= 3:
    CHARACTERS = [(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "eu")]


def fake_interaction():
    captured = {}

    async def defer(*args, **kwargs):
        captured["deferred"] = True

    async def send(*args, **kwargs):
        # The command answers immediately with a placeholder, then edits it.
        captured.setdefault("placeholder", kwargs.get("embed"))
        if kwargs.get("embeds"):
            captured["embeds"] = kwargs["embeds"]
        captured["files"] = kwargs.get("files") or kwargs.get("attachments") or []
        if kwargs.get("embed") is not None and captured.get("placeholder") is not None:
            captured["error"] = kwargs.get("embed")

    async def edit(*args, **kwargs):
        captured["embeds"] = kwargs.get("embeds") or captured.get("embeds") or []
        if kwargs.get("attachments"):
            captured["files"] = kwargs["attachments"]
        if kwargs.get("embed") is not None:
            captured["error"] = kwargs["embed"]

    interaction = types.SimpleNamespace()
    interaction.response = types.SimpleNamespace(defer=defer, send_message=send)
    interaction.followup = types.SimpleNamespace(send=send)
    interaction.edit_original_response = edit
    interaction.guild_id = 1234567890
    interaction.captured = captured
    return interaction


async def run_one(name, realm, region):
    group = B.WowGroup()
    interaction = fake_interaction()
    print(f"\n=== /wow check {name}-{realm} ({region}) ===")
    await group.check.callback(group, interaction, name=name, realm=realm, region=region)

    captured = interaction.captured
    embeds = captured.get("embeds") or []
    if captured.get("error") is not None and not embeds:
        print("  ERROR EMBED:", captured["error"].description)
        return False

    files = captured.get("files") or []
    if files is B.discord.utils.MISSING:
        files = []
    print(f"  embeds: {len(embeds)} | attachments: {len(files)}")

    total = 0
    for index, embed in enumerate(embeds, 1):
        author = getattr(embed.author, "name", "") or "(no author)"
        total += len(embed)
        print(f"   {index}. {author}  fields={len(embed.fields)} chars={len(embed)}"
              f" image={'yes' if embed.image else 'no'}")
        for field in embed.fields:
            assert len(field.value) <= 1024, f"field too long: {field.name}"
        assert len(embed.fields) <= 25, "too many fields"
    print(f"  characters across embeds: {total} (Discord allows 6000)")
    assert total <= 6000, "message exceeds the 6000 character budget"

    for handle in files:
        data = handle.fp.getvalue()
        with open(os.path.join(OUT, f"e2e_{name}_{handle.filename}"), "wb") as fh:
            fh.write(data)
        print(f"   saved {handle.filename}: {len(data) // 1024} KB")
    return True


async def main():
    results = []
    for name, realm, region in CHARACTERS:
        try:
            results.append(await run_one(name, realm, region))
        except Exception:
            import traceback
            traceback.print_exc()
            results.append(False)
    print("\nRESULT:", "all passed" if all(results) else "FAILURES PRESENT")
    sys.exit(0 if all(results) else 1)


asyncio.run(main())
