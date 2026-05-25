"""contacts_tool — read-only lookup via Contacts.framework."""

from __future__ import annotations

from typing import Any

from yuki.tools.native.registry import DangerLevel, tool


def _make_store() -> Any:  # pragma: no cover
    try:
        from Contacts import CNContactStore  # type: ignore[import-untyped]

        return CNContactStore.alloc().init()
    except Exception:
        return None


def _key_descriptors() -> list[Any]:  # pragma: no cover
    from Contacts import (
        CNContactEmailAddressesKey,
        CNContactFamilyNameKey,
        CNContactGivenNameKey,
        CNContactPhoneNumbersKey,
    )

    return [
        CNContactGivenNameKey,
        CNContactFamilyNameKey,
        CNContactEmailAddressesKey,
        CNContactPhoneNumbersKey,
    ]


@tool(name="contacts", danger=DangerLevel.READ_ONLY)
async def contacts_tool(query: str) -> Any:
    """Search the macOS contacts database (read-only)."""
    store = _make_store()
    if store is None:
        return {"error": "Contacts unavailable"}
    try:
        from Contacts import CNContact

        pred = CNContact.predicateForContactsMatchingName_(query)
    except Exception:  # pragma: no cover
        return {"error": "predicate unavailable"}
    contacts, _ = store.unifiedContactsMatchingPredicate_keysToFetch_error_(
        pred, _key_descriptors(), None
    )
    out: list[dict[str, Any]] = []
    for c in contacts or []:
        emails = [e.value() for e in (c.emailAddresses() or [])]
        phones = [p.value().stringValue() for p in (c.phoneNumbers() or [])]
        out.append(
            {
                "name": f"{c.givenName()} {c.familyName()}".strip(),
                "emails": emails,
                "phones": phones,
            }
        )
    return out
