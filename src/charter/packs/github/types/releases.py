# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Request schemas for GitHub's releases and release assets.

Two things here are unlike the rest of this pack.

**``releases_generate_notes`` writes nothing.** GitHub: "The generated release
notes are not saved anywhere. They are intended to be generated and used when
creating a new release." It is a read that happens to be a POST — you take the
name and body it returns and pass them to ``releases_create`` yourself, or set
``generate_release_notes`` on the create and let GitHub do both at once.

**``releases_upload_asset`` talks to a different host.** The upload goes to
``uploads.github.com``, not ``api.github.com``, and the body is the file's raw
bytes rather than JSON. That is a second factory in the pack module, with its
own base URL and ``body_format="raw"`` — see ``UPLOAD_BASE_URL`` there.

API Reference: https://docs.github.com/en/rest/releases
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field

from charter.packs.github.types.common import GitHubListRequest, RepoRequest
from charter.types import Body, Path, Query
from charter.types.markers import TransportOverride

__all__ = [
    "MakeLatest",
    "ReleasesListRequest",
    "ReleasesGetRequest",
    "ReleasesGetLatestRequest",
    "ReleasesGetByTagRequest",
    "ReleasesCreateRequest",
    "ReleasesUpdateRequest",
    "ReleasesDeleteRequest",
    "ReleasesGenerateNotesRequest",
    "ReleasesListAssetsRequest",
    "ReleasesUploadAssetRequest",
    "unwrap_asset_body",
]


MakeLatest = Literal["true", "false", "legacy"]
"""Whether a release becomes the repository's "Latest".

Strings, not booleans — GitHub types this as an enum of three, because the
third value is not a boolean at all: ``legacy`` means "work it out from the
creation date and the semantic version". Sending a JSON ``true`` where the API
wants ``"true"`` is a 422."""


class _ReleaseId(RepoRequest):
    release_id: Annotated[
        int,
        Field(..., description="The unique identifier of the release."),
        Path(),
    ]


class ReleasesListRequest(RepoRequest, GitHubListRequest):
    """List a repository's releases, newest first.

    Releases only: a Git tag that was never made into a release does not appear
    here. ``repos_list_tags`` is the list that includes those. Draft releases
    are visible only to a caller with push access.

    API Reference: https://docs.github.com/en/rest/releases/releases#list-releases
    """


class ReleasesGetRequest(_ReleaseId):
    """Get one release by its id.

    API Reference: https://docs.github.com/en/rest/releases/releases#get-a-release
    """


class ReleasesGetLatestRequest(RepoRequest):
    """Get the latest published release.

    GitHub's definition, not a sort: the most recent non-prerelease, non-draft
    release. A repository whose newest release is a prerelease answers with the
    older stable one, which is the point.

    API Reference: https://docs.github.com/en/rest/releases/releases#get-the-latest-release
    """


class ReleasesGetByTagRequest(RepoRequest):
    """Get a release by its tag name.

    Usually the one you want: a tag name is something a changelog or a version
    string already carries, and a release id is not.

    API Reference: https://docs.github.com/en/rest/releases/releases#get-a-release-by-tag-name
    """

    tag: Annotated[
        str,
        Field(..., description="The name of the tag, for example `v1.4.0`."),
        Path(allow_slash=True),
    ]


class ReleasesCreateRequest(RepoRequest):
    """Publish a release, creating its tag if it does not exist.

    ``generate_release_notes`` is the field with the leverage: GitHub writes the
    changelog from the merged pull requests since the previous release. With
    ``body`` set as well, the text given is put *above* the generated notes
    rather than replacing them.

    Note the token requirement GitHub attaches to this endpoint: if the commit
    being released adds or changes anything under ``.github/workflows/``, the
    token needs authority over workflows, and a token without it gets a 404
    rather than a permission error.

    API Reference: https://docs.github.com/en/rest/releases/releases#create-a-release
    """

    tag_name: Annotated[str, Field(..., description="The name of the tag."), Body()]
    target_commitish: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Specifies the commitish value that determines where the Git tag is "
                "created from. Can be any branch or commit SHA. Unused if the Git tag "
                "already exists. Absent, the repository's default branch."
            ),
        ),
        Body(),
    ]
    name: Annotated[Optional[str], Field(None, description="The name of the release."), Body()]
    body: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Text describing the contents of the tag. With "
                "`generate_release_notes` set, this is placed above the generated "
                "notes rather than replacing them."
            ),
        ),
        Body(),
    ]
    draft: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "`true` to create a draft (unpublished) release, `false` to create a "
                "published one. GitHub publishes when this is absent."
            ),
        ),
        Body(),
    ]
    prerelease: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "`true` to identify the release as a prerelease. A prerelease is never "
                "returned by `releases_get_latest`."
            ),
        ),
        Body(),
    ]
    discussion_category_name: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "If specified, a discussion of the specified category is created and "
                "linked to the release. The value must be a category that already "
                "exists in the repository."
            ),
        ),
        Body(),
    ]
    generate_release_notes: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Whether to automatically generate the name and body for this release "
                "from the merged pull requests since the last one. If `name` is "
                "specified, the specified name will be used; otherwise, a name will be "
                "automatically generated."
            ),
        ),
        Body(),
    ]
    make_latest: Annotated[
        Optional[MakeLatest],
        Field(
            None,
            description=(
                "Whether this release should be set as the latest release for the "
                "repository — a string, not a boolean. Drafts and prereleases cannot "
                "be set as latest. `legacy` determines the latest release from the "
                "creation date and the higher semantic version. GitHub uses 'true' for "
                "newly published releases."
            ),
        ),
        Body(),
    ]


class ReleasesUpdateRequest(_ReleaseId):
    """Update a release. Anything omitted is left unchanged.

    Publishing a draft is this endpoint with ``draft: false``.

    API Reference: https://docs.github.com/en/rest/releases/releases#update-a-release
    """

    tag_name: Annotated[Optional[str], Field(None, description="The name of the tag."), Body()]
    target_commitish: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Specifies the commitish value that determines where the Git tag is "
                "created from. Can be any branch or commit SHA. Unused if the Git tag "
                "already exists."
            ),
        ),
        Body(),
    ]
    name: Annotated[Optional[str], Field(None, description="The name of the release."), Body()]
    body: Annotated[
        Optional[str], Field(None, description="Text describing the contents of the tag."), Body()
    ]
    draft: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "`true` to make this a draft (unpublished) release, `false` to publish "
                "it. Setting it to `false` is how a draft is published."
            ),
        ),
        Body(),
    ]
    prerelease: Annotated[
        Optional[bool],
        Field(None, description="`true` to identify the release as a prerelease."),
        Body(),
    ]
    discussion_category_name: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "If specified, a discussion of the specified category is created and "
                "linked to the release."
            ),
        ),
        Body(),
    ]
    make_latest: Annotated[
        Optional[MakeLatest],
        Field(
            None,
            description=(
                "Whether this release should be set as the latest release for the "
                "repository — a string, not a boolean. Drafts and prereleases cannot "
                "be set as latest."
            ),
        ),
        Body(),
    ]


class ReleasesDeleteRequest(_ReleaseId):
    """Delete a release.

    The Git tag survives: this removes the release, not what it pointed at.
    ``git_refs_delete`` on `tags/NAME` removes the tag.

    API Reference: https://docs.github.com/en/rest/releases/releases#delete-a-release
    """


class ReleasesGenerateNotesRequest(RepoRequest):
    """Generate release-note text from the merged pull requests in a range.

    Creates nothing. GitHub returns a name and a markdown body and saves neither
    — which makes this safe to call for a draft changelog, and means the text
    has to be passed to ``releases_create`` to become anything.

    API Reference: https://docs.github.com/en/rest/releases/releases#generate-release-notes-content-for-a-release
    """

    tag_name: Annotated[
        str,
        Field(
            ...,
            description="The tag name for the release. This can be an existing tag or a new one.",
        ),
        Body(),
    ]
    target_commitish: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Specifies the commitish value that will be the target for the "
                "release's tag. Required if the supplied `tag_name` does not reference "
                "an existing tag. Ignored if the `tag_name` already exists."
            ),
        ),
        Body(),
    ]
    previous_tag_name: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The name of the previous tag to use as the starting point for the "
                "release notes. Use to manually specify the range for the set of "
                "changes considered as part of this release."
            ),
        ),
        Body(),
    ]
    configuration_file_path: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Specifies a path to a file in the repository containing configuration "
                "settings used for generating the release notes. Absent, GitHub uses "
                "`.github/release.yml` or `.github/release.yaml` if either exists."
            ),
        ),
        Body(),
    ]


class ReleasesListAssetsRequest(_ReleaseId, GitHubListRequest):
    """List the files attached to a release.

    API Reference: https://docs.github.com/en/rest/releases/assets#list-release-assets
    """


class ReleasesUploadAssetRequest(_ReleaseId):
    """Attach a file to a release.

    The one endpoint in this pack that does not go to ``api.github.com``: the
    upload host is ``uploads.github.com``, and the body is the file itself
    rather than a JSON document. Both are declared on a second factory rather
    than worked around here.

    Two GitHub behaviours worth knowing before reading a response as success:
    "GitHub renames asset filenames that have special characters,
    non-alphanumeric characters, and leading or trailing periods" — so the
    ``name`` that comes back may not be the one sent — and uploading a name that
    already exists on the release is refused rather than replacing it.

    The ``Content-Type`` header describes the bytes and defaults to
    ``application/octet-stream``. A host that knows better — uploading a
    ``text/markdown`` changelog, say — sets it for the call with
    ``ainvoke(..., headers={"Content-Type": ...})``, which is where a value the
    host decides per call belongs.

    API Reference: https://docs.github.com/en/rest/releases/assets#upload-a-release-asset
    """

    name: Annotated[
        str,
        Field(
            ...,
            description=(
                "The file name of the asset, for example `charter-1.2.0.tar.gz`. "
                "GitHub rewrites names containing special characters."
            ),
        ),
        Query(),
    ]
    label: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "An alternate short description shown in place of the file name on the "
                "release page."
            ),
        ),
        Query(),
    ]
    content: Annotated[
        str,
        Field(
            ...,
            description=(
                "The asset's contents, which are sent as the raw body. Text is sent as "
                "written; binary content is not expressible here — build the release "
                "asset from a text artifact, or upload binaries outside this tool."
            ),
        ),
        Body(),
    ]


def unwrap_asset_body(tool_input: BaseModel) -> TransportOverride:
    """Send the asset's bytes as the body, rather than an object around them.

    A single ``Body()`` field that holds a *scalar* keeps its name — Slack's
    ``join(channel=Body())`` sends ``{"channel": "C1"}``, which is right, and is
    why the runtime does it. Here it is wrong: GitHub wants the file, and
    ``{"content": "..."}`` is a JSON document describing the file.

    There is no marker for "unwrap a scalar" because every other API in this
    repository wants the name. So the one endpoint that does not says so here,
    where the transport override replaces the body outright.

    API Reference: https://docs.github.com/en/rest/releases/assets#upload-a-release-asset
    """
    return {"body": getattr(tool_input, "content", "")}
