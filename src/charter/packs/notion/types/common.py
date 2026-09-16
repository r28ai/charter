"""
The objects every Notion resource is built out of.

Notion has a small shared vocabulary and reuses it everywhere: a page title, a
heading, a table cell and a comment are all *arrays of rich text*; a page icon,
a callout icon and a database icon are all the same icon union; every list
endpoint pages the same way. Declared once here, they are referenced by the
pages, blocks, data sources and comments modules rather than restated in each.

Notion's union shape is a discriminator beside its payload — ``{"type": "text",
"text": {...}}`` — so each union below is one model carrying ``type`` and a
sibling field per variant, with a validator that the payload matching ``type``
is the one that is present. That keeps the wire bytes exact and puts the rule
where a wrong call is caught locally instead of as a 400.

API Reference: https://developers.notion.com/reference/intro
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from charter.types import Mode, Query

__all__ = [
    "NotionColor",
    "SelectColor",
    "Annotations",
    "TextLink",
    "TextContent",
    "EquationContent",
    "DateValue",
    "TemplateMention",
    "Mention",
    "RichText",
    "PartialUser",
    "ExternalFileData",
    "NotionHostedFileData",
    "FileUploadRef",
    "FileObject",
    "CustomEmojiData",
    "NotionIconData",
    "Icon",
    "Parent",
    "PaginatedQuery",
    "PaginatedBody",
    "exactly_one_of",
]


# -----------------------------------------------------
# Colours
# -----------------------------------------------------

NotionColor = Literal[
    "default",
    "default_background",
    "blue",
    "blue_background",
    "brown",
    "brown_background",
    "gray",
    "gray_background",
    "green",
    "green_background",
    "orange",
    "orange_background",
    "pink",
    "pink_background",
    "purple",
    "purple_background",
    "red",
    "red_background",
    "yellow",
    "yellow_background",
]
"""The colour a block or a rich text annotation carries.

Ten hues, each available as a text colour and as a highlight (``_background``),
plus ``default`` and ``default_background`` — twenty values. The last is the one
the prose table omits and the API's own ``apiColor`` carries. This is the set used on block objects and on
:class:`Annotations`; the palette a *select option* draws from is smaller and is
:data:`SelectColor`.

API Reference: https://developers.notion.com/reference/rich-text#the-annotation-object
"""

SelectColor = Literal[
    "default",
    "blue",
    "brown",
    "gray",
    "green",
    "orange",
    "pink",
    "purple",
    "red",
    "yellow",
]
"""The colour a select, multi-select or status option carries.

The same ten hues as :data:`NotionColor` with no ``_background`` variants — an
option is a chip, so there is no text-versus-highlight distinction to make.

API Reference: https://developers.notion.com/reference/property-object#select
"""


# -----------------------------------------------------
# A shared rule
# -----------------------------------------------------


def exactly_one_of(model: Any, discriminator: str, variants: tuple) -> Any:
    """Enforce Notion's ``{"type": t, t: {...}}`` shape on a union model.

    Notion tags a union with a ``type`` string and puts the payload in the
    field of the same name. Two ways to get that wrong are worth catching here
    rather than as a 400: naming a ``type`` whose payload was not sent, and
    sending two payloads so the server picks one and silently drops the other.

    ``type`` itself stays optional where Notion infers it from the payload on
    write; when it is given it must name the payload that is present.
    """
    present = [name for name in variants if getattr(model, name, None) is not None]
    if len(present) > 1:
        raise ValueError(
            f"exactly one of {', '.join(present)} may be set; Notion reads the one "
            f"named by `{discriminator}` and drops the rest"
        )
    declared = getattr(model, discriminator, None)
    if declared is not None and declared in variants and not present:
        raise ValueError(f"{discriminator}={declared!r} but no `{declared}` object was given")
    if present and declared is not None and declared != present[0]:
        raise ValueError(f"{discriminator}={declared!r} does not name the `{present[0]}` object given")
    return model


# -----------------------------------------------------
# Rich text
# -----------------------------------------------------


class Annotations(BaseModel):
    """The styling applied to one run of rich text.

    Every field is optional; Notion applies the default (off, and ``default``
    colour) to anything omitted.

    API Reference: https://developers.notion.com/reference/rich-text#the-annotation-object
    """

    bold: Optional[bool] = Field(None, description="Whether the text is bolded.")
    italic: Optional[bool] = Field(None, description="Whether the text is italicized.")
    strikethrough: Optional[bool] = Field(
        None, description="Whether the text is struck through."
    )
    underline: Optional[bool] = Field(None, description="Whether the text is underlined.")
    code: Optional[bool] = Field(
        None, description="Whether the text is code style."
    )
    color: Optional[NotionColor] = Field(
        None,
        description=(
            "Color of the text. Possible values include the ten hues as text colors "
            "and again as `_background` highlights, plus `default`."
        ),
    )


class TextLink(BaseModel):
    """The link on a text run.

    API Reference: https://developers.notion.com/reference/rich-text#text
    """

    url: str = Field(
        ...,
        max_length=2000,
        description="The URL this text links to. Maximum 2000 characters.",
    )


class TextContent(BaseModel):
    """A literal run of text.

    API Reference: https://developers.notion.com/reference/rich-text#text
    """

    content: str = Field(
        ...,
        max_length=2000,
        description=(
            "The actual text content of the text. Maximum 2000 characters; longer "
            "text must be split across several rich text objects."
        ),
    )
    link: Optional[TextLink] = Field(
        None,
        description=(
            "An object with information about any inline link in this text, if "
            "included. Null when the text is not a link."
        ),
    )


class EquationContent(BaseModel):
    """An inline LaTeX equation.

    API Reference: https://developers.notion.com/reference/rich-text#equation
    """

    expression: str = Field(
        ...,
        max_length=1000,
        description="The LaTeX string representing the inline equation. Maximum 1000 characters.",
    )


class DateValue(BaseModel):
    """A date, or a date range, with an optional time zone.

    API Reference: https://developers.notion.com/reference/page-property-values#date
    """

    start: str = Field(
        ...,
        description=(
            "An ISO 8601 format date, with optional time. A date without a time "
            "(`2024-05-01`) and a datetime (`2024-05-01T10:00:00-04:00`) are both "
            "accepted."
        ),
    )
    end: Optional[str] = Field(
        None,
        description=(
            "An ISO 8601 formatted date, with optional time. Null if this is not a "
            "range."
        ),
    )
    time_zone: Optional[str] = Field(
        None,
        description=(
            "Time zone information for `start` and `end`, as an IANA database name "
            "such as `America/New_York`. When set, `start` and `end` must not carry "
            "their own UTC offset. Null when the dates carry their own offsets."
        ),
    )


class PageRef(BaseModel):
    """A reference to a page by ID.

    API Reference: https://developers.notion.com/reference/rich-text#mention
    """

    id: str = Field(..., description="The ID of the page.")


class DatabaseRef(BaseModel):
    """A reference to a database by ID.

    API Reference: https://developers.notion.com/reference/rich-text#mention
    """

    id: str = Field(..., description="The ID of the database.")


class LinkPreviewRef(BaseModel):
    """A mention of a third-party URL that Notion renders as a preview.

    API Reference: https://developers.notion.com/reference/rich-text#mention
    """

    url: str = Field(..., max_length=2000, description="The URL of the link preview.")


class TemplateMention(BaseModel):
    """A placeholder that resolves when a template is instantiated.

    API Reference: https://developers.notion.com/reference/rich-text#mention
    """

    type: Optional[Literal["template_mention_date", "template_mention_user"]] = Field(
        None, description="The type of the template mention."
    )
    template_mention_date: Optional[Literal["today", "now"]] = Field(
        None, description="Resolves to the date the template is used."
    )
    template_mention_user: Optional[Literal["me"]] = Field(
        None, description="Resolves to the user who uses the template."
    )


class PartialUser(BaseModel):
    """A user, referenced by ID.

    Notion returns a fuller object than this — a name, an avatar, and an email
    where the integration has the capability for it — but ``id`` is the only
    field it accepts when a user is being *set*, on a people property or in a
    mention.

    API Reference: https://developers.notion.com/reference/user
    """

    object: Optional[Literal["user"]] = Field(
        "user", description="Always `user`."
    )
    id: str = Field(..., description="The ID of the user.")


class Mention(BaseModel):
    """An inline reference to something else in the workspace.

    API Reference: https://developers.notion.com/reference/rich-text#mention
    """

    type: Optional[
        Literal["user", "page", "database", "date", "link_preview", "template_mention"]
    ] = Field(None, description="The type of the inline mention.")
    user: Optional[PartialUser] = Field(None, description="The mentioned user.")
    page: Optional[PageRef] = Field(None, description="The mentioned page.")
    database: Optional[DatabaseRef] = Field(None, description="The mentioned database.")
    date: Optional[DateValue] = Field(None, description="The mentioned date.")
    link_preview: Optional[LinkPreviewRef] = Field(
        None, description="The mentioned link preview."
    )
    template_mention: Optional[TemplateMention] = Field(
        None, description="The template placeholder being mentioned."
    )

    @model_validator(mode="after")
    def _one_mention(self):
        return exactly_one_of(
            self,
            "type",
            ("user", "page", "database", "date", "link_preview", "template_mention"),
        )


class RichText(BaseModel):
    """One run of styled text.

    Notion has no plain-string text anywhere: a title, a paragraph, a table cell
    and a comment are all arrays of these. A run carries its own styling, so
    "the **word** bold" is three runs rather than one string with markup.

    API Reference: https://developers.notion.com/reference/rich-text
    """

    type: Optional[Literal["text", "mention", "equation"]] = Field(
        None, description="The type of this rich text object."
    )
    text: Optional[TextContent] = Field(
        None, description="The literal text, present when `type` is `text`."
    )
    mention: Optional[Mention] = Field(
        None,
        description=(
            "An inline mention of a user, page, database, date or link preview, "
            "present when `type` is `mention`."
        ),
    )
    equation: Optional[EquationContent] = Field(
        None, description="An inline LaTeX equation, present when `type` is `equation`."
    )
    annotations: Optional[Annotations] = Field(
        None, description="The styling applied to this run of text."
    )
    plain_text: Annotated[
        Optional[str],
        Field(
            None,
            description="The plain text without annotations.",
        ),
        Mode("response_only"),
    ]
    href: Annotated[
        Optional[str],
        Field(
            None,
            description="The URL of any link or Notion mention in this text, if any.",
        ),
        Mode("response_only"),
    ]

    @model_validator(mode="after")
    def _one_kind(self):
        return exactly_one_of(self, "type", ("text", "mention", "equation"))


# -----------------------------------------------------
# Files, icons and covers
# -----------------------------------------------------


class ExternalFileData(BaseModel):
    """A file Notion links to but does not host.

    API Reference: https://developers.notion.com/reference/file-object#external-files
    """

    url: str = Field(
        ...,
        max_length=2000,
        description=(
            "A link to the externally hosted content. Maximum 2000 characters. "
            "Notion does not copy the file, so the link must stay reachable."
        ),
    )


class NotionHostedFileData(BaseModel):
    """A file Notion hosts, returned with a signed URL that expires.

    Never accepted on write: to attach a file to Notion, upload it through the
    File Upload API and reference the upload's ID instead.

    API Reference: https://developers.notion.com/reference/file-object#notion-hosted-files
    """

    url: str = Field(
        ...,
        description=(
            "An authenticated S3 URL to the file. The link expires one hour after "
            "the response is generated, so it is for immediate use rather than "
            "storage."
        ),
    )
    expiry_time: Optional[str] = Field(
        None,
        description="The date and time when the signed URL stops working, in ISO 8601 format.",
    )


class FileUploadRef(BaseModel):
    """A completed file upload, by ID.

    This is how a file becomes Notion-hosted content: create a file upload, send
    the bytes, complete it, then reference the upload's ID here.

    API Reference: https://developers.notion.com/reference/file-upload
    """

    id: str = Field(..., description="The ID of a completed File Upload object.")


class FileObject(BaseModel):
    """A file, either linked externally or hosted by Notion.

    API Reference: https://developers.notion.com/reference/file-object
    """

    type: Optional[Literal["external", "file", "file_upload"]] = Field(
        None, description="The type of this file object."
    )
    external: Optional[ExternalFileData] = Field(
        None, description="A file hosted somewhere else, referenced by URL."
    )
    file_upload: Optional[FileUploadRef] = Field(
        None, description="A completed file upload to attach, referenced by its ID."
    )
    file: Annotated[
        Optional[NotionHostedFileData],
        Field(
            None,
            description=(
                "A file Notion hosts, with a signed URL that expires after an hour. "
                "Returned, never sent — attach a `file_upload` instead."
            ),
        ),
        Mode("response_only"),
    ]
    name: Optional[str] = Field(
        None,
        description=(
            "The name of the file, as shown in Notion. Required for an `external` "
            "entry in a files property; optional for a `file_upload`, which carries "
            "the name it was uploaded with."
        ),
    )

    @model_validator(mode="after")
    def _one_source(self):
        return exactly_one_of(self, "type", ("external", "file_upload", "file"))


class CustomEmojiData(BaseModel):
    """A workspace's own uploaded emoji.

    API Reference: https://developers.notion.com/reference/emoji-object
    """

    id: str = Field(..., description="The ID of the custom emoji.")
    name: Annotated[
        Optional[str],
        Field(None, description="The name of the custom emoji, without colons."),
        Mode("response_only"),
    ]
    url: Annotated[
        Optional[str],
        Field(None, description="The URL of the custom emoji image."),
        Mode("response_only"),
    ]


class NotionIconData(BaseModel):
    """One of Notion's own built-in icons.

    API Reference: https://developers.notion.com/reference/page
    """

    name: str = Field(..., description="The name of the built-in Notion icon.")
    color: Optional[str] = Field(None, description="The color applied to the icon.")



class Icon(BaseModel):
    """A page, database or callout icon.

    Five shapes, one of which is set. Pass ``None`` for the whole object on an
    update to remove the icon.

    API Reference: https://developers.notion.com/reference/page#page-icon
    """

    type: Optional[Literal["emoji", "external", "file_upload", "custom_emoji", "icon"]] = (
        Field(None, description="The type of this icon.")
    )
    emoji: Optional[str] = Field(
        None, description="A standard emoji character, for example `🥬`."
    )
    external: Optional[ExternalFileData] = Field(
        None, description="An externally hosted image, referenced by URL."
    )
    file_upload: Optional[FileUploadRef] = Field(
        None, description="A completed file upload to use as the icon."
    )
    custom_emoji: Optional[CustomEmojiData] = Field(
        None, description="One of the workspace's own uploaded emoji."
    )
    icon: Optional[NotionIconData] = Field(
        None, description="One of Notion's own built-in icons."
    )
    file: Annotated[
        Optional[NotionHostedFileData],
        Field(
            None,
            description="A Notion-hosted image. Returned, never sent.",
        ),
        Mode("response_only"),
    ]

    @model_validator(mode="after")
    def _one_icon(self):
        return exactly_one_of(
            self, "type", ("emoji", "external", "file_upload", "custom_emoji", "icon", "file")
        )


class Cover(BaseModel):
    """A page or database cover image.

    Unlike an icon, a cover is always an image: no emoji shape is accepted.

    API Reference: https://developers.notion.com/reference/page#page-cover
    """

    type: Optional[Literal["external", "file_upload"]] = Field(
        None, description="The type of this cover."
    )
    external: Optional[ExternalFileData] = Field(
        None, description="An externally hosted image, referenced by URL."
    )
    file_upload: Optional[FileUploadRef] = Field(
        None, description="A completed file upload to use as the cover."
    )
    file: Annotated[
        Optional[NotionHostedFileData],
        Field(None, description="A Notion-hosted image. Returned, never sent."),
        Mode("response_only"),
    ]

    @model_validator(mode="after")
    def _one_cover(self):
        return exactly_one_of(self, "type", ("external", "file_upload", "file"))


# -----------------------------------------------------
# Parents
# -----------------------------------------------------


class Parent(BaseModel):
    """What an object lives under.

    Which shapes are accepted depends on what is being created: a page takes a
    ``page_id`` or a ``data_source_id``, a database takes a ``page_id``, a
    block's parent is read back rather than set. The endpoint's own schema says
    which; this model carries them all, since Notion returns any of them.

    ``workspace`` and ``agent_id`` are returned, never sent.

    API Reference: https://developers.notion.com/reference/parent-object
    """

    type: Optional[
        Literal["database_id", "data_source_id", "page_id", "workspace", "block_id", "agent_id"]
    ] = Field(None, description="The type of the parent.")
    data_source_id: Optional[str] = Field(
        None,
        description=(
            "The ID of the data source this object belongs to. This is the parent a "
            "page in a database takes."
        ),
    )
    database_id: Optional[str] = Field(
        None,
        description=(
            "The ID of the database. On a data source's parent this is the database "
            "that contains it. As a page's parent it is the pre-2025-09-03 spelling: "
            "prefer `data_source_id`, which names the table the page is a row of."
        ),
    )
    page_id: Optional[str] = Field(None, description="The ID of the parent page.")
    block_id: Optional[str] = Field(None, description="The ID of the parent block.")
    workspace: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Always true, on an object that sits at the top level of the "
                "workspace."
            ),
        ),
        Mode("response_only"),
    ]
    agent_id: Annotated[
        Optional[str],
        Field(
            None,
            description="The ID of the agent, on an agent's own instruction pages.",
        ),
        Mode("response_only"),
    ]

    @model_validator(mode="after")
    def _one_parent(self):
        present = [
            name
            for name in ("data_source_id", "page_id", "block_id", "workspace", "agent_id")
            if getattr(self, name, None) is not None
        ]
        # `database_id` rides along on a data source's parent, so it is only a
        # second parent when it arrives alone.
        if self.database_id is not None and not present:
            present.append("database_id")
        if len(present) > 1:
            raise ValueError(
                f"a parent is one of {', '.join(present)}, not several — Notion reads "
                f"the one named by `type`"
            )
        if not present and self.type is None:
            raise ValueError(
                "a parent needs an ID: set `page_id`, or `data_source_id` to create a "
                "page as a row of a database"
            )
        return self


# -----------------------------------------------------
# Pagination
# -----------------------------------------------------

START_CURSOR = (
    "A `next_cursor` value returned in a previous response. Returns the results "
    "immediately after this cursor; omit it to start from the beginning."
)
PAGE_SIZE = (
    "The number of items from the full list desired in the response. Maximum 100, "
    "and 100 is also what the server returns when this is absent."
)


class PaginatedQuery(BaseModel):
    """The two pagination parameters every GET list endpoint takes as query.

    API Reference: https://developers.notion.com/reference/intro#pagination
    """

    start_cursor: Annotated[
        Optional[str], Field(None, description=START_CURSOR), Query()
    ]
    page_size: Annotated[
        Optional[int],
        Field(None, ge=1, le=100, description=PAGE_SIZE),
        Query(),
    ]


class PaginatedBody(BaseModel):
    """The same two parameters, where the endpoint is a POST and takes a body.

    Notion's search and data source query take their filters in a body, so their
    paging markers go in the body beside them rather than on the query string.

    API Reference: https://developers.notion.com/reference/intro#pagination
    """

    start_cursor: Optional[str] = Field(None, description=START_CURSOR)
    page_size: Optional[int] = Field(None, ge=1, le=100, description=PAGE_SIZE)


# -----------------------------------------------------
# Where new content lands, and what it is made from
# -----------------------------------------------------


class AfterBlockRef(BaseModel):
    """The block that new content is inserted after.

    API Reference: https://developers.notion.com/reference/patch-block-children
    """

    id: str = Field(..., description="The ID of the existing block to insert after.")


class Position(BaseModel):
    """Where new blocks are placed among a parent's existing children.

    Replaces the ``after`` parameter, which earlier API versions took on block
    append. Absent, new content is appended to the end.

    API Reference: https://developers.notion.com/reference/patch-block-children
    """

    type: Optional[Literal["after_block", "page_start", "page_end"]] = Field(
        None, description="Where to insert the new content."
    )
    after_block: Optional[AfterBlockRef] = Field(
        None,
        description="The existing block to insert after, when `type` is `after_block`.",
    )

    @model_validator(mode="after")
    def _placed(self):
        if self.type == "after_block" and self.after_block is None:
            raise ValueError("type='after_block' needs `after_block` naming the block to follow")
        if self.after_block is not None and self.type not in (None, "after_block"):
            raise ValueError(f"`after_block` is not read when type is {self.type!r}")
        return self


class Template(BaseModel):
    """The template a new or updated page is built from.

    API Reference: https://developers.notion.com/reference/post-page
    """

    type: Literal["none", "default", "template_id"] = Field(
        ...,
        description=(
            "Which template to apply: `none` for an empty page, `default` for the "
            "parent database's default template, or `template_id` for a specific one."
        ),
    )
    template_id: Optional[str] = Field(
        None,
        description="The ID of the template page to apply, when `type` is `template_id`.",
    )
    timezone: Optional[str] = Field(
        None,
        description=(
            "An IANA time zone name, for example `America/New_York`, used to resolve "
            "date placeholders in the template."
        ),
    )

    @model_validator(mode="after")
    def _identified(self):
        if self.type == "template_id" and self.template_id is None:
            raise ValueError("type='template_id' needs `template_id`")
        if self.template_id is not None and self.type != "template_id":
            raise ValueError(f"`template_id` is not read when type is {self.type!r}")
        return self
