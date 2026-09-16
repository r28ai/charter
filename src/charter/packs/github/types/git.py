"""Request schemas for GitHub's Git database API — the raw object store.

Everything else in this pack writes through a convenience:
``repos_create_or_update_file`` makes a blob, a tree, a commit and a ref update
in one call, which is why it can only ever touch **one file per commit**. An
agent that refactors across six files with it produces six commits and six CI
runs, and no intermediate state that compiles.

This module is the layer underneath, where a commit is assembled before it
exists:

1. ``git_blobs_create`` for each new file's content, or put the content inline
   on the tree entry and skip this;
2. ``git_trees_create`` with ``base_tree`` set to the current commit's tree and
   one entry per changed path — this is the step that makes it *one* commit;
3. ``git_commits_create`` pointing at that tree, with the current head as its
   parent;
4. ``git_refs_update`` to move the branch onto the new commit.

Nothing is visible until step 4. A failure before it leaves unreferenced
objects, which is to say nothing at all.

**The ref spelling is the trap in this whole module.** The path parameter is
``heads/my-branch``, *without* the ``refs/`` prefix that
``git_refs_create`` requires in its body. GitHub documents both spellings, in
adjacent endpoints, and the two are not interchangeable. Each schema below says
which one it wants, and the validators refuse the other rather than letting a
404 explain it.

API Reference: https://docs.github.com/en/rest/git
"""

from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from charter.packs.github.types.common import RepoRequest
from charter.types import Body, Path, Query
from charter.types.markers import TransportOverride

__all__ = [
    "BlobEncoding",
    "TreeEntryMode",
    "TreeEntryType",
    "TagObjectType",
    "TreeEntry",
    "GitCommitAuthor",
    "GitRefsGetRequest",
    "GitRefsUpdateRequest",
    "GitRefsDeleteRequest",
    "GitRefsListMatchingRequest",
    "GitBlobsCreateRequest",
    "GitBlobsGetRequest",
    "GitTreesCreateRequest",
    "GitTreesGetRequest",
    "GitCommitsCreateRequest",
    "GitCommitsGetRequest",
    "GitTagsCreateRequest",
    "compile_tree_deletions",
]


BlobEncoding = Literal["utf-8", "base64"]
"""How a blob's ``content`` is encoded. GitHub's own words: "Currently,
``utf-8`` and ``base64`` are supported."."""

TreeEntryMode = Literal["100644", "100755", "040000", "160000", "120000"]
"""A tree entry's file mode, in Git's octal spelling.

``100644`` file, ``100755`` executable, ``040000`` subdirectory, ``160000``
submodule, ``120000`` symlink. These are strings, not numbers: ``040000`` is
not ``40000``, and sending the integer loses the leading zero."""

TreeEntryType = Literal["blob", "tree", "commit"]

TagObjectType = Literal["commit", "tree", "blob"]


def _unprefixed_ref(value: str, field: str) -> str:
    """Refuse the ``refs/`` prefix on the endpoints that do not take it."""
    if value.startswith("refs/"):
        raise ValueError(
            f"`{field}` must not start with 'refs/' on this endpoint — GitHub wants "
            f"'{value[len('refs/'):]}', not '{value}'. The fully qualified spelling "
            "is what `git_refs_create` takes in its body; the path parameter here "
            "takes the short one."
        )
    return value


class GitRefsGetRequest(RepoRequest):
    """Get one reference and the object it points at.

    How you learn a branch's current head SHA, which is the parent of the next
    commit and the thing ``git_refs_update`` moves.

    Note the singular ``git/ref/`` in this endpoint's URL against the plural
    ``git/refs/`` in the two that write. That is GitHub's, not a typo here.

    API Reference: https://docs.github.com/en/rest/git/refs#get-a-reference
    """

    ref: Annotated[
        str,
        Field(
            ...,
            description=(
                "The Git reference, formatted as `heads/BRANCH_NAME` for a branch or "
                "`tags/TAG_NAME` for a tag. Without the `refs/` prefix."
            ),
        ),
        Path(allow_slash=True),
    ]

    @model_validator(mode="after")
    def _ref_is_unprefixed(self) -> GitRefsGetRequest:
        _unprefixed_ref(self.ref, "ref")
        return self


class GitRefsUpdateRequest(RepoRequest):
    """Move a reference to a different commit — the step that publishes work.

    Steps 1 to 3 of building a commit leave objects nothing points at. This is
    the one that makes them the branch.

    API Reference: https://docs.github.com/en/rest/git/refs#update-a-reference
    """

    ref: Annotated[
        str,
        Field(
            ...,
            description=(
                "The Git reference to move, formatted as `heads/BRANCH_NAME` or "
                "`tags/TAG_NAME`. Without the `refs/` prefix."
            ),
        ),
        Path(allow_slash=True),
    ]
    sha: Annotated[
        str,
        Field(..., description="The SHA1 value to set this reference to."),
        Body(),
    ]
    force: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Indicates whether to force the update or to make sure the update is a "
                "fast-forward update. Leaving this out or setting it to `false` will "
                "make sure you're not overwriting work."
            ),
        ),
        Body(),
    ]

    @model_validator(mode="after")
    def _ref_is_unprefixed(self) -> GitRefsUpdateRequest:
        _unprefixed_ref(self.ref, "ref")
        return self


class GitRefsDeleteRequest(RepoRequest):
    """Delete a reference — the way a merged branch is tidied away.

    GitHub answers 422 rather than deleting when the reference is the
    repository's default branch.

    API Reference: https://docs.github.com/en/rest/git/refs#delete-a-reference
    """

    ref: Annotated[
        str,
        Field(
            ...,
            description=(
                "The Git reference to delete, formatted as `heads/BRANCH_NAME` or "
                "`tags/TAG_NAME`. Without the `refs/` prefix."
            ),
        ),
        Path(allow_slash=True),
    ]

    @model_validator(mode="after")
    def _ref_is_unprefixed(self) -> GitRefsDeleteRequest:
        _unprefixed_ref(self.ref, "ref")
        return self


class GitRefsListMatchingRequest(RepoRequest):
    """List every reference under a prefix.

    A prefix match, not an exact one: `heads/feature` returns
    `heads/feature-a` and `heads/feature/b`. `heads/` alone lists every branch.

    API Reference: https://docs.github.com/en/rest/git/refs#list-matching-references
    """

    ref: Annotated[
        str,
        Field(
            ...,
            description=(
                "The reference prefix to match, such as `heads/` for every branch or "
                "`tags/v2` for the v2 tags. Without the `refs/` prefix."
            ),
        ),
        Path(allow_slash=True),
    ]

    @model_validator(mode="after")
    def _ref_is_unprefixed(self) -> GitRefsListMatchingRequest:
        _unprefixed_ref(self.ref, "ref")
        return self


class GitBlobsCreateRequest(RepoRequest):
    """Write a file's content into the object store, without committing it.

    The blob exists immediately and is part of nothing until a tree names it.
    Small files are usually cheaper inline on the tree entry's `content`;
    this endpoint is for the ones worth uploading once and referencing by SHA,
    and for binary content, which a tree entry cannot carry.

    GitHub supports blobs up to 100 megabytes here.

    API Reference: https://docs.github.com/en/rest/git/blobs#create-a-blob
    """

    content: Annotated[
        str,
        Field(..., description="The new blob's content."),
        Body(),
    ]
    encoding: Annotated[
        Optional[BlobEncoding],
        Field(
            None,
            description=(
                "The encoding used for `content`. Currently, `utf-8` and `base64` are "
                "supported. GitHub uses `utf-8` when this is absent — pass `base64` "
                "with base64-encoded content for a binary file."
            ),
        ),
        Body(),
    ]


class GitBlobsGetRequest(RepoRequest):
    """Read a blob by its SHA.

    Answers with the content base64-encoded; the response handler decodes it,
    and says so plainly when the bytes are not text.

    API Reference: https://docs.github.com/en/rest/git/blobs#get-a-blob
    """

    file_sha: Annotated[
        str,
        Field(..., description="The SHA of the blob, as it appears in a tree entry."),
        Path(),
    ]


class TreeEntry(BaseModel):
    """One path in a tree: what is at it, and in what mode.

    Two rules, both of which GitHub answers with an error rather than a guess:

    * "Use either ``tree.sha`` or ``content`` to specify the contents of the
      entry. Using both ``tree.sha`` and ``content`` will return an error."
    * ``sha: null`` deletes the path — and "Returns an error if you try to
      delete a file that does not exist."

    Deleting is the one case where `sha` must be present *and* null, which
    Pydantic's `exclude_none` dump cannot express. Set `delete` instead and the
    request carries the explicit null.

    API Reference: https://docs.github.com/en/rest/git/trees#create-a-tree
    """

    path: str = Field(..., description="The file referenced in the tree.")
    mode: Optional[TreeEntryMode] = Field(
        None,
        description=(
            "The file mode; one of `100644` for file (blob), `100755` for executable "
            "(blob), `040000` for subdirectory (tree), `160000` for submodule "
            "(commit), or `120000` for a blob that specifies the path of a symlink."
        ),
    )
    type: Optional[TreeEntryType] = Field(
        None, description="Either `blob`, `tree`, or `commit`."
    )
    sha: Optional[str] = Field(
        None,
        description=(
            "The SHA1 checksum ID of an existing object to place at this path, from "
            "`git_blobs_create`. Use either this or `content`, never both."
        ),
    )
    content: Optional[str] = Field(
        None,
        description=(
            "The content you want this file to have, as plain text. GitHub will write "
            "this blob out and use that SHA for this entry. Use either this or `sha`."
        ),
    )
    delete: Optional[bool] = Field(
        None,
        description=(
            "Set true to remove this path from the tree. GitHub answers with an error "
            "if the path is not in `base_tree`."
        ),
    )
    """Deletion, stated as a flag because the wire form cannot be stated at all.

    GitHub deletes a path when its entry carries ``"sha": null`` — an explicit
    null, which is a different thing from an absent key. Pydantic dumps with
    ``exclude_none``, so a ``None`` sha never reaches the wire and the entry
    arrives as a no-op. This flag is the semantic form; the tool's
    ``build_request`` compiles it back into the null GitHub is looking for.
    """

    @model_validator(mode="after")
    def _content_is_given_exactly_once(self) -> TreeEntry:
        given = [n for n in ("sha", "content") if getattr(self, n) is not None]
        if self.delete:
            if given:
                raise ValueError(
                    f"`delete` cannot be combined with {', '.join(given)} on "
                    f"'{self.path}' — a deletion has no content."
                )
            return self
        if len(given) > 1:
            raise ValueError(
                f"Use either `sha` or `content` on '{self.path}', not both. GitHub "
                "returns an error for an entry carrying both."
            )
        if not given and self.type != "tree":
            raise ValueError(
                f"'{self.path}' needs `content` (the new text), `sha` (an existing "
                "object) or `delete: true`."
            )
        return self


class GitTreesCreateRequest(RepoRequest):
    """Build a tree: one commit's worth of changes across any number of files.

    This is the endpoint that makes an atomic multi-file change possible, and
    ``base_tree`` is the field that decides whether it is one. GitHub, on
    omitting it: "GitHub will create a new Git tree object from only the entries
    defined in the ``tree`` parameter. If you create a new commit pointing to
    such a tree, then all files which were a part of the parent commit's tree
    and were not defined in the ``tree`` parameter will be listed as deleted by
    the new commit."

    So: pass the current commit's tree SHA as ``base_tree`` and list only what
    changed. Leave it out and you have written a commit that deletes the
    repository.

    A tree may hold up to 100,000 entries, to a maximum of 7 MB.

    API Reference: https://docs.github.com/en/rest/git/trees#create-a-tree
    """

    tree: Annotated[
        List[TreeEntry],
        Field(
            ...,
            min_length=1,
            max_length=100_000,
            description="One entry per path being added, changed or removed.",
        ),
        Body(),
    ]
    base_tree: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The SHA1 of an existing Git tree object which will be used as the base "
                "for the new tree — normally the `tree.sha` of the commit you are "
                "building on. Entries in `tree` overwrite entries with the same path. "
                "Omitting it means the new tree contains *only* the entries listed, so "
                "a commit on it deletes every other file in the repository."
            ),
        ),
        Body(),
    ]


class GitTreesGetRequest(RepoRequest):
    """Read a tree: what is at each path, and the SHA of each object.

    API Reference: https://docs.github.com/en/rest/git/trees#get-a-tree
    """

    tree_sha: Annotated[
        str,
        Field(
            ...,
            description=(
                "The SHA1 value or ref (branch or tag) name of the tree. A branch name "
                "works here, which saves resolving it first."
            ),
        ),
        Path(allow_slash=True),
    ]
    recursive: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Set to '1' to return every object in every subtree, rather than the "
                "top level only. GitHub treats *any* value as true here, including "
                "'0' and 'false' — omit the parameter to stay shallow. The recursive "
                "form is capped at 100,000 entries and 7 MB, and sets `truncated` when "
                "it hits that."
            ),
        ),
        Query(),
    ]


class GitCommitAuthor(BaseModel):
    """Who a Git commit object is attributed to.

    GitHub: "You must provide values for both `name` and `email`." `date`
    defaults to now.
    """

    name: str = Field(..., description="The name of the author (or committer) of the commit.")
    email: str = Field(..., description="The email of the author (or committer) of the commit.")
    date: Optional[str] = Field(
        None,
        description=(
            "Indicates when this commit was authored (or committed). This is a "
            "timestamp in ISO 8601 format: `YYYY-MM-DDTHH:MM:SSZ`."
        ),
    )


class GitCommitsCreateRequest(RepoRequest):
    """Create a commit object pointing at a tree.

    Still invisible when this returns: a commit nothing references is garbage
    until ``git_refs_update`` moves a branch onto it.

    ``parents`` is what makes this a commit *on* a branch rather than a new
    history. GitHub: "If omitted or empty, the commit will be written as a root
    commit" — which is almost never what was meant, so the validator asks for it
    explicitly rather than letting an omission produce an orphan.

    API Reference: https://docs.github.com/en/rest/git/commits#create-a-commit
    """

    message: Annotated[str, Field(..., description="The commit message."), Body()]
    tree: Annotated[
        str,
        Field(..., description="The SHA of the tree object this commit points to."),
        Body(),
    ]
    parents: Annotated[
        Optional[List[str]],
        Field(
            None,
            description=(
                "The full SHAs of the commits that were the parents of this commit — "
                "normally one, the current head of the branch. For a merge commit, "
                "more than one. Required: an explicit empty list writes a root commit "
                "with no history, and omitting the field altogether is refused rather "
                "than treated as that."
            ),
        ),
        Body(),
    ]
    author: Annotated[
        Optional[GitCommitAuthor],
        Field(
            None,
            description=(
                "Information about the author of the commit. By default, the `author` "
                "will be the authenticated user and the current date."
            ),
        ),
        Body(),
    ]
    committer: Annotated[
        Optional[GitCommitAuthor],
        Field(
            None,
            description=(
                "Information about the person who is making the commit. By default, "
                "`committer` will use the information set in `author`."
            ),
        ),
        Body(),
    ]
    signature: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The PGP signature of the commit, as an ASCII-armored detached "
                "signature. GitHub adds it to the `gpgsig` header of the created "
                "commit."
            ),
        ),
        Body(),
    ]

    @model_validator(mode="after")
    def _parents_are_stated(self) -> GitCommitsCreateRequest:
        """A root commit has to be asked for, not fallen into.

        GitHub treats an absent `parents` as "write a root commit" — a commit
        with no history, which then cannot be fast-forwarded onto any branch.
        The failure surfaces one step later, at `git_refs_update`, as a
        non-fast-forward rejection that says nothing about the cause.
        """
        if self.parents is None:
            raise ValueError(
                "`parents` is required here. GitHub treats an omitted `parents` as a "
                "request to write a *root* commit — one with no history, which the "
                "branch update that follows then refuses as a non-fast-forward, with "
                "an error that says nothing about the cause. Pass the branch's current "
                "head SHA (from `git_refs_get`) as the single parent. An explicit "
                "empty list is accepted, and is how a root commit is asked for on "
                "purpose."
            )
        return self


class GitCommitsGetRequest(RepoRequest):
    """Read a commit object: its message, its tree, its parents.

    The Git-level view. ``repos_get_commit`` is the repository-level one, which
    adds the diff and the file list.

    API Reference: https://docs.github.com/en/rest/git/commits#get-a-commit
    """

    commit_sha: Annotated[
        str,
        Field(..., description="The SHA of the commit."),
        Path(),
    ]


class GitTagsCreateRequest(RepoRequest):
    """Create an annotated tag *object* — which is not yet a tag.

    GitHub is explicit and this catches everyone once: "Note that creating a tag
    object does not create the reference that makes a tag in Git." Follow this
    with ``git_refs_create`` pointing `refs/tags/NAME` at the SHA that comes
    back. A *lightweight* tag skips this endpoint entirely and is just the
    reference.

    API Reference: https://docs.github.com/en/rest/git/tags#create-a-tag-object
    """

    tag: Annotated[
        str,
        Field(..., description='The tag\'s name. This is typically a version (e.g., "v0.0.1").'),
        Body(),
    ]
    message: Annotated[str, Field(..., description="The tag message."), Body()]
    object: Annotated[
        str,
        Field(..., description="The SHA of the git object this is tagging."),
        Body(),
    ]
    type: Annotated[
        TagObjectType,
        Field(
            ...,
            description=(
                "The type of the object being tagged. Normally this is a `commit` but "
                "it can also be a `tree` or a `blob`."
            ),
        ),
        Body(),
    ]
    tagger: Annotated[
        Optional[GitCommitAuthor],
        Field(None, description="An object with information about the individual creating the tag."),
        Body(),
    ]


def compile_tree_deletions(tool_input: BaseModel) -> TransportOverride:
    """Turn every ``delete: true`` tree entry into the explicit ``sha: null``.

    GitHub's signal for "remove this path" is a present-and-null ``sha``.
    Pydantic's dump drops ``None`` — which is right everywhere else, because
    most APIs reject explicit nulls — so the one place it is wrong is compiled
    here instead of being worked around in the schema.

    Passed to the tool as ``build_request``, so it runs on the validated input
    on every call and the model never sees the wire form.

    API Reference: https://docs.github.com/en/rest/git/trees#create-a-tree
    """
    entries: List[Dict[str, Any]] = []
    for entry in getattr(tool_input, "tree", None) or []:
        wire = entry.model_dump(exclude_none=True, mode="json")
        if wire.pop("delete", False):
            # Present and null. That is the whole instruction.
            wire["sha"] = None
        entries.append(wire)
    return {"body": {"tree": entries}}
