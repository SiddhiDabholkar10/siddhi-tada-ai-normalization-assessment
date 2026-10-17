"""Parts shared by several canonical records."""
from pydantic import Field

from .base import CanonicalPart
from .enums import AddressType
from .values import SENSITIVE


class PostalAddress(CanonicalPart):
    """A business address (company, work location). Not sensitive."""

    type: AddressType
    line1: str | None = None
    line2: str | None = None
    city: str | None = None
    county: str | None = None
    state: str | None = Field(default=None, description="State or province code as sent, e.g. 'UT'.")
    postal_code: str | None = None
    country: str | None = Field(default=None, description="Country as sent, e.g. 'USA'.")


class PersonalAddress(PostalAddress):
    """A person's address. Street lines and postal code are sensitive; city and state are not,
    because they are needed for tax and work-location context and identify little alone."""

    line1: str | None = Field(default=None, json_schema_extra=SENSITIVE)
    line2: str | None = Field(default=None, json_schema_extra=SENSITIVE)
    postal_code: str | None = Field(default=None, json_schema_extra=SENSITIVE)


class PersonName(CanonicalPart):
    first: str | None = None
    middle: str | None = None
    last: str | None = None
    prefix: str | None = None
    suffix: str | None = None
    preferred_first: str | None = None


class Reference(CanonicalPart):
    """A provider code-table entry referred to by a record (a job, a pay code, a parent
    organization): the provider's id, code and name, whichever the source gives."""

    source_id: str | None = None
    code: str | None = None
    name: str | None = None
