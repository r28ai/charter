"""
Google Forms response trimming — the responses collection only.

A ``FormResponse`` spends most of its bytes on the wrapping around an answer
rather than on the answer. One respondent picking "Yes" arrives as::

    {"questionId": "1a2b", "textAnswers": {"answers": [{"value": "Yes"}]}}

— 64 bytes of shape for 3 bytes of answer, repeated once per question and again
once per response, and ``forms.responses.list`` returns up to 5000 of them. The
handlers below keep the answer, the grade and the identifiers a caller can act
on, and drop the nesting.

**The form itself is deliberately not trimmed.** Google's documented way to
change an item is to read the form, edit your copy of the item and write it
back through ``UpdateItemRequest`` "with the IDs being the same", so an item
that came back reshaped is an item that cannot be written back. That round trip
is worth more than the bytes a projection would save, and a handler that broke
it would be the Docs pack's index lesson made again: the response would read
better and the tool would stop working.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

__all__ = [
    "extract_response",
    "extract_responses",
]

# The keys of a FormResponse worth carrying through, in the order a reader
# wants them. `formId` is absent on list responses by design — Google says so
# on the list page — so it is copied when present rather than assumed.
_RESPONSE_KEYS = (
    "responseId",
    "formId",
    "createTime",
    "lastSubmittedTime",
    "respondentEmail",
    "totalScore",
)


def _grade(answer: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The grade on one answer, if the form was a quiz.

    ``correct`` survives even when it is ``False``, and ``score`` even when it
    is ``0``: both are answers to the question being asked, and a falsy-value
    filter here would report an incorrect answer as an ungraded one.
    """
    grade = answer.get("grade")
    if not isinstance(grade, dict):
        return None
    out: Dict[str, Any] = {}
    if "score" in grade:
        out["score"] = grade["score"]
    if "correct" in grade:
        out["correct"] = grade["correct"]
    feedback = grade.get("feedback")
    if isinstance(feedback, dict) and feedback.get("text"):
        out["feedback"] = feedback["text"]
    return out or None


def _answer(answer: Dict[str, Any]) -> Dict[str, Any]:
    """One answer, flattened.

    A text answer becomes its values, a file upload answer becomes its files.
    An answer that is neither is *reported*, not dropped: Google's `value` union
    can grow, and a handler that silently returned `{}` for a kind it did not
    know would hand the model a response that looks complete and is not.
    """
    out: Dict[str, Any] = {}

    text = answer.get("textAnswers")
    uploads = answer.get("fileUploadAnswers")

    if isinstance(text, dict):
        out["values"] = [
            entry.get("value")
            for entry in text.get("answers") or []
            if isinstance(entry, dict)
        ]
    elif isinstance(uploads, dict):
        out["files"] = [
            {
                key: entry[key]
                for key in ("fileId", "fileName", "mimeType")
                if key in entry
            }
            for entry in uploads.get("answers") or []
            if isinstance(entry, dict)
        ]
    else:
        # Not a shape this handler knows. Say so and carry the payload, so the
        # caller can see what arrived instead of an empty answer.
        known = {"questionId", "grade"}
        out["unrecognizedAnswer"] = {
            key: value for key, value in answer.items() if key not in known
        }

    grade = _grade(answer)
    if grade is not None:
        out["grade"] = grade
    return out


def _trim_response(response: Dict[str, Any]) -> Dict[str, Any]:
    """One ``FormResponse``, with its answers flattened and keyed by question."""
    out: Dict[str, Any] = {key: response[key] for key in _RESPONSE_KEYS if key in response}

    answers = response.get("answers")
    if isinstance(answers, dict):
        out["answers"] = {
            question_id: _answer(answer)
            for question_id, answer in answers.items()
            if isinstance(answer, dict)
        }
    return out


async def extract_response(response: Dict[str, Any]) -> Dict[str, Any]:
    """Trim one response — ``forms.responses.get``."""
    return _trim_response(response)


async def extract_responses(response: Dict[str, Any]) -> Dict[str, Any]:
    """Trim ``forms.responses.list``.

    ``nextPageToken`` is carried whenever the API sent one. It is the only
    thing that says there is another page, so dropping it would strand the walk
    on page one while reporting a complete answer — the failure the trimming
    rule in AGENTS.md names.
    """
    responses: List[Dict[str, Any]] = [
        _trim_response(entry)
        for entry in response.get("responses") or []
        if isinstance(entry, dict)
    ]
    out: Dict[str, Any] = {"responses": responses}
    if response.get("nextPageToken"):
        out["nextPageToken"] = response["nextPageToken"]
    return out
