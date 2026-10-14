"""The 'no non-standard fields' guarantee.

Our output must be a valid OSV record. OSV has exactly these 16 top-level
fields; everything our resolver adds lives inside `database_specific`, which
is the schema's sanctioned free-form slot. This check is the contract in code:
emit fails loudly rather than shipping a record with a stray top-level key.
"""

ALLOWED_TOP = {
    "schema_version", "id", "modified", "published", "withdrawn",
    "aliases", "related", "upstream", "summary", "details",
    "severity", "affected", "references", "credits", "database_specific",
}


def check_standard(record: dict) -> bool:
    """Raise if the record carries any top-level field OSV does not define."""
    extra = set(record) - ALLOWED_TOP
    if extra:
        raise ValueError(f"non-standard top-level fields: {sorted(extra)}")
    if "id" not in record or "modified" not in record:
        raise ValueError("OSV record missing required field: id/modified")
    return True
