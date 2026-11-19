"""Strict JSON boundary shared by evidence and oracle readers."""

import json


class InvalidJSON(ValueError):
    pass


def json_object(raw: bytes) -> dict:
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise InvalidJSON("duplicate JSON key")
            result[key] = value
        return result

    value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_pairs)
    if not isinstance(value, dict):
        raise InvalidJSON("expected a JSON object")
    return value
