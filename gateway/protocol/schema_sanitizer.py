"""JSON schema sanitizer for Gemini and Google Cloud Code protobuf compatibility."""

import copy
from typing import Any, Dict, List, Set

# Strict allowlist of permitted protobuf OpenAPI fields
ALLOWED_FIELDS: Set[str] = {
    "type",
    "description",
    "properties",
    "required",
    "items",
    "enum",
}

GOOGLE_TYPE_MAP = {
    "string": "STRING",
    "number": "NUMBER",
    "integer": "INTEGER",
    "boolean": "BOOLEAN",
    "array": "ARRAY",
    "object": "OBJECT",
}


def score_schema_option(schema: Dict[str, Any]) -> int:
    """Score schema option for anyOf/oneOf selection. Higher = more informative."""
    if not isinstance(schema, dict):
        return 0
    if schema.get("type") in ("object", "OBJECT") or "properties" in schema:
        return 3
    if schema.get("type") in ("array", "ARRAY") or "items" in schema:
        return 2
    t = str(schema.get("type", "")).lower()
    if t and t != "null":
        return 1
    return 0


def sanitize_schema(raw_schema: Any) -> Dict[str, Any]:
    """Recursively clean and transform a JSON schema for Google protobuf OpenAPI compliance."""
    if not isinstance(raw_schema, dict):
        return {"type": "OBJECT", "properties": {}}

    schema = copy.deepcopy(raw_schema)

    # 1. Convert const -> enum
    if "const" in schema:
        const_val = schema.pop("const")
        schema["enum"] = [str(const_val)]

    # 2. Flatten allOf
    if "allOf" in schema and isinstance(schema["allOf"], list):
        merged_props = {}
        merged_required = set()
        for sub in schema["allOf"]:
            sub_sanitized = sanitize_schema(sub)
            if "properties" in sub_sanitized and isinstance(sub_sanitized["properties"], dict):
                merged_props.update(sub_sanitized["properties"])
            if "required" in sub_sanitized and isinstance(sub_sanitized["required"], list):
                merged_required.update(sub_sanitized["required"])

        schema.pop("allOf", None)
        schema["type"] = "OBJECT"
        schema["properties"] = merged_props
        if merged_required:
            schema["required"] = sorted(list(merged_required))

    # 3. Flatten anyOf / oneOf
    for key in ("anyOf", "oneOf"):
        if key in schema and isinstance(schema[key], list):
            options = [opt for opt in schema[key] if isinstance(opt, dict)]
            if options:
                best_opt = max(options, key=score_schema_option)
                sanitized_best = sanitize_schema(best_opt)
                schema.pop(key, None)
                for k, v in sanitized_best.items():
                    schema[k] = v
            else:
                schema.pop(key, None)

    # 4. Handle array of types, e.g. ["string", "null"]
    if isinstance(schema.get("type"), list):
        types = [t for t in schema["type"] if str(t).lower() != "null"]
        schema["type"] = types[0] if types else "string"

    # 5. Normalize type to Google protobuf uppercase
    raw_type = schema.get("type")
    if raw_type:
        type_str = str(raw_type).lower()
        schema["type"] = GOOGLE_TYPE_MAP.get(type_str, "STRING")
    else:
        if "properties" in schema:
            schema["type"] = "OBJECT"
        elif "items" in schema:
            schema["type"] = "ARRAY"
        else:
            schema["type"] = "STRING"

    # 6. Apply strict allowlist filtering
    sanitized: Dict[str, Any] = {}
    for key in ALLOWED_FIELDS:
        if key in schema:
            sanitized[key] = schema[key]

    # Description must be string
    if "description" in sanitized and not isinstance(sanitized["description"], str):
        sanitized["description"] = str(sanitized["description"])

    # Enum must contain strings
    if "enum" in sanitized and isinstance(sanitized["enum"], list):
        sanitized["enum"] = [str(x) for x in sanitized["enum"]]

    # 7. Array validation
    if sanitized.get("type") == "ARRAY":
        if "items" not in sanitized or not isinstance(sanitized["items"], (dict, list)):
            sanitized["items"] = {"type": "STRING"}
        elif isinstance(sanitized["items"], list):
            best = max(sanitized["items"], key=score_schema_option) if sanitized["items"] else {"type": "STRING"}
            sanitized["items"] = sanitize_schema(best)
        else:
            sanitized["items"] = sanitize_schema(sanitized["items"])

    # 8. Object validation
    if sanitized.get("type") == "OBJECT":
        props = sanitized.get("properties")
        if not isinstance(props, dict):
            sanitized["properties"] = {}
        else:
            cleaned_props = {}
            for pk, pv in props.items():
                cleaned_props[str(pk)] = sanitize_schema(pv)
            sanitized["properties"] = cleaned_props

        # Prune required to only defined properties
        if "required" in sanitized and isinstance(sanitized["required"], list):
            valid_keys = set(sanitized["properties"].keys())
            sanitized["required"] = [r for r in sanitized["required"] if r in valid_keys]
            if not sanitized["required"]:
                sanitized.pop("required", None)

    return sanitized
