from __future__ import annotations

from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field

from charter.types import Mode

from ..message.models import Message

Format = Literal['full', 'metadata', 'minimal']


class ListThreadsResponse(BaseModel):
    """
    Response model for users.threads.list.

    API Reference: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.threads/list
    """

    threads: Annotated[
        Optional[List[Thread]],
        Field(None, description="List of threads. Note that each thread resource does not contain a list of messages. The list of messages for a given thread can be fetched using the threads.get method."),
        Mode("response_only"),
    ]
    next_page_token: Annotated[
        Optional[str],
        Field(None, description="Page token to retrieve the next page of results in the list."),
        Mode("response_only"),
    ]
    result_size_estimate: Annotated[
        Optional[int],
        Field(None, description="Estimated total number of results."),
        Mode("response_only"),
    ]


class Thread(BaseModel):
    """Gmail thread resource (conversation).

    API Reference: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.threads#Thread
    """

    id: Annotated[
        Optional[str],
        Field(None, description="The unique ID of the thread."),
        Mode("response_only")
    ]
    snippet: Annotated[
        Optional[str],
        Field(None, description="A short part of the message text."),
        Mode("response_only")
    ]
    history_id: Annotated[
        Optional[str],
        Field(None, description="The ID of the last history record that modified this thread."),
        Mode("response_only")
    ]
    messages: Annotated[
        Optional[List[Message]],
        Field(None, description="The list of messages in the thread."),
        Mode("response_only")
    ]


ListThreadsResponse.model_rebuild()