"""Sole live lab boundary; no provider implementation or credential is shipped.

The service supplies a trusted transport that MUST honor both total token
ceilings, the pinned provider/version, and make at most one request (no retry).
It receives immutable request bytes, not authority to alter admission or spend.
"""
from dataclasses import dataclass
from typing import Awaitable, Callable

from .admission import Admission, AdmissionRecord, NotAdmitted, OverCap
from .envelope import check_caps
from .labs import MAX_MESSAGE_BYTES, Request


@dataclass(frozen=True)
class ModelCall:
    record: AdmissionRecord
    operation: str
    role: str
    request_json: bytes
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class AdmittedLab:
    model_id: str
    provider: str
    model_version: str
    admission: Admission
    transport: Callable[[ModelCall], Awaitable[dict]]
    input_tokens: int
    output_tokens: int

    def __post_init__(self):
        if type(self.admission) is not Admission or not callable(self.transport):
            raise NotAdmitted("trusted admission and transport required")
        for value in (self.input_tokens, self.output_tokens):
            if type(value) is not int or not 1 <= value <= 1000000000:
                raise OverCap("positive bounded token ceiling required")

    async def _call(self, operation, request):
        record = self.admission.check(self.model_id)
        role = "judge" if operation == "review" else "lead"
        if (role not in record.roles or record.provider != self.provider or
                record.model_version != self.model_version):
            raise NotAdmitted("model route or role is not admitted")
        wire = check_caps(request.wire())
        if len(wire) > min(MAX_MESSAGE_BYTES, self.input_tokens):
            raise OverCap("request exceeds input ceiling")
        # Charge the full configured ceiling, including provider prompt overhead;
        # the trusted transport must bound actual total input/output to this quote.
        self.admission.meter(self.model_id, record.ceiling_usd(self.input_tokens, self.output_tokens),
                             expected_record=record)
        call = ModelCall(record, operation, role, wire, self.input_tokens, self.output_tokens)
        return await self.transport(call)

    async def propose(self, request: Request):
        return await self._call("propose", request)

    async def review(self, request: Request):
        return await self._call("review", request)

    async def repair(self, request: Request):
        return await self._call("repair", request)
