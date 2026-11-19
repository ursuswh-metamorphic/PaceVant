from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator

Address = Annotated[str, StringConstraints(pattern=r"^0x[0-9a-fA-F]{40}$")]
Hash = Annotated[str, StringConstraints(pattern=r"^0x[0-9a-f]{64}$")]
HexBytes = Annotated[str, StringConstraints(pattern=r"^0x(?:[0-9a-f]{2})*$")]
UInt = Annotated[str, StringConstraints(pattern=r"^(0|[1-9][0-9]*)$")]
Delta = Annotated[str, StringConstraints(pattern=r"^-?(0|[1-9][0-9]*)$")]


class Wire(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    @field_validator("*", mode="after")
    @classmethod
    def uint_range(cls, value, info):
        if (
            isinstance(value, str)
            and any(
                getattr(meta, "pattern", None) in {r"^(0|[1-9][0-9]*)$", r"^-?(0|[1-9][0-9]*)$"}
                for meta in cls.model_fields[info.field_name].metadata
            )
            and abs(int(value)) >= 2**256
        ):
            raise ValueError("uint256 overflow")
        return value
