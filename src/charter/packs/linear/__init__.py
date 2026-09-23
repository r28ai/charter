# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Linear — the work-management surface of the Linear GraphQL API.

    from charter.packs import linear

    linear.configure(api_key="lin_api_...")
    await linear.issue_create.ainvoke(
        variables={"input": {"team_id": TEAM_UUID, "title": "Flaky test on main"}}
    )

``configure()`` is optional if ``$LINEAR_API_KEY`` is set.

This is the pack that made the GraphQL case work, and it is worth saying what
that took, because a GraphQL API breaks three assumptions a REST-shaped runtime
makes.

**One URL, one method, and the operation lives in the body.** Every tool here
POSTs to the same ``/graphql``. What distinguishes ``issues_list`` from
``issue_create`` is the *query document*, which is a constant belonging to the
tool — not a parameter. It is declared as ``static_body`` and never appears in
the schema, so a model filling in arguments cannot see it and cannot rewrite it.
That is the whole boundary: a GraphQL endpoint accepts arbitrary documents, so a
tool that let the model supply one would not be an integration, it would be a
shell. The documents live in :mod:`~charter.packs.linear.queries`.

**Failure arrives as HTTP 200, twice over.** GraphQL puts document-level
problems in an ``errors`` array beside the data. But a *mutation* Linear
understood and declined comes back with no ``errors`` at all and
``success: false`` in the payload. Both are caught by one declaration:
``ok_field="data.*.success"``, where ``*`` stands for whichever operation the
tool called, so it covers every mutation in the pack including ones added later.
That wildcard is load-bearing at this size — ``success`` is present on 118 of
the 121 mutation payloads in Linear's schema, and the three without it are all
in domains this pack does not carry.

**Its cursor is nested.** Linear pages Relay-style, so the cursor comes back at
``pageInfo.endCursor`` and goes out at ``variables.after`` — inside the
variables object, not beside it. ``cursor_param`` takes a dotted path for
exactly this.

One more thing, small but easy to get wrong: **a personal API key goes in
``Authorization`` with no scheme.** Not ``Bearer``, not ``Token`` — the raw key.
An OAuth access token, by contrast, does take ``Bearer``. This pack is built for
the personal-key case; for OAuth, build the factory yourself with
``oauth_tool_factory``, which adds the prefix.

What is here, and what is not
-----------------------------

Linear's schema declares 155 queries and 367 mutations. This pack carries 128
tools, covering the domains work actually happens in: issues and their
relations, comments and reactions, labels, teams, members, workflow states,
projects with their milestones and status updates, cycles, initiatives,
documents, attachments, customers and their requests, notifications, favorites,
saved views, search and webhooks.

The rest is left out on purpose, and it is worth naming rather than hiding:

* **Integration plumbing** (66 operations) — ``integrationSlack``,
  ``integrationGithubConnect`` and their like exist to complete OAuth handshakes
  with third parties. They are setup, not work, and several cannot be driven
  from an API key at all.
* **Releases** (37 operations) — a distinct product surface with its own
  pipelines and access keys.
* **Authentication and OAuth application management** — session, passkey, SAML
  and client-secret operations. A tool that can rotate the credential it
  authenticates with is a tool worth not having.
* **Organization administration and billing** — ``organizationDelete``,
  ``userSuspend``, ``organizationStartTrialForPlan``, domain claims, trials.
* **Team settings** — ``teamCreate`` and ``teamUpdate`` carry 40 and 55 fields of
  workspace configuration. Teams are readable here and their membership is
  writable; their settings are not.
* **Imports, exports and git automation** — bulk migration machinery.
* **Linear's own agent-delegation surface** (``agentSession*``,
  ``agentActivity*``) — for building an agent that Linear delegates *to*, which
  is the other side of this integration.
* **Deprecated domains.** The whole ``roadmap`` family is deprecated in favour
  of initiatives, and ``cycleCreate`` is deprecated in favour of a team's cycle
  cadence. Neither is a tool here, and ``ProjectFilter`` does not expose the
  leftover ``roadmaps`` collection.

Known limits, named rather than hidden:

* **Fields Linear marks ``[Internal]`` or ``[DEPRECATED]`` are absent**, as are
  ``createAsUser`` / ``displayIconUrl`` — those last two are only accepted by
  OAuth applications acting as an external user, not by a personal API key.
  Prosemirror ``bodyData`` / ``descriptionData`` JSON is likewise unsendable
  from here; markdown ``body`` / ``description`` is the public shape.
* **Selection sets are fixed.** Each tool asks for the fields in its document
  and no others. That is a deliberate trade: it is what makes the response shape
  a property of this file, and it is what keeps Linear's complexity budget
  predictable.
"""

from __future__ import annotations

from charter.factories import api_key_tool_factory
from charter.packs._config import DeferredApiKeyHeaders, api_key_headers
from charter.packs.linear import curation, queries, types
from charter.packs.linear.response_handlers import unwrap, unwrap_mutation
from charter.tool import Tool
from charter.types.envelope import Envelope
from charter.types.pagination import Pagination

# Linear fails in two places, and one declaration covers both.
#
# `errors` is GraphQL's own array, for a document the server would not run.
# `data.*.success` is the other one: a mutation Linear understood and then
# declined comes back HTTP 200, with no `errors`, and `success: false` inside the
# payload. The `*` stands for whichever operation the tool called, so this covers
# every mutation in the pack — including one added later by someone who never
# read this comment. A query has no `success` anywhere, so it matches nothing.
LINEAR_ENVELOPE = Envelope(
    errors_field="errors",
    ok_field="data.*.success",
)

BASE_URL = "https://api.linear.app/"
GRAPHQL_PATH = "graphql"
QUOTA_DOC_URL = "https://linear.app/developers/rate-limiting"

# Relay-style pagination. The cursor comes back nested under the connection and
# goes out nested inside `variables` — which is why cursor_param is a path.
# The response handler has already stripped `data` and the operation name by the
# time this is read, so `pageInfo` is at the root.
# https://linear.app/developers/pagination
LINEAR_PAGINATION = Pagination(
    cursor_field="pageInfo.endCursor",
    cursor_param="variables.after",
    # Relay reports the end of a connection here, and Linear keeps sending an
    # endCursor on the last page — so without this the walk never terminates.
    more_field="pageInfo.hasNextPage",
)

# A personal API key is sent raw, with no `Bearer` prefix — this is the one
# place Linear differs from almost every other API in this repository.
# https://linear.app/developers/graphql#authentication
_headers: DeferredApiKeyHeaders = api_key_headers(
    "linear",
    {"Authorization": "CHARTER_UNCONFIGURED"},
    "Authorization",
    "LINEAR_API_KEY",
)


def configure(api_key: str) -> None:
    """Supply the Linear personal API key for this pack's tools."""
    _headers.configure(api_key)


_linear = api_key_tool_factory(
    pack="linear",
    base_url=BASE_URL,
    api_key_headers=_headers,
    # GraphQL variables are camelCase, which is Charter's default for bodies; said
    # out loud because it is the reason `team_id` arrives as `teamId`.
    body_case="camel",
    quota_doc_url=QUOTA_DOC_URL,
    envelope=LINEAR_ENVELOPE,
)


def _query(name, schema, document, operation, description, action_label, *, paginates=False):
    """Declare one GraphQL operation as a tool.

    Every Linear tool is the same POST to the same URL; the document is what
    makes them different, and it goes on the wire through ``static_body``.
    """
    return _linear(
        name=name,
        args_schema=schema,
        method="POST",
        url_template=GRAPHQL_PATH,
        description=description,
        action_label=action_label,
        static_body={"query": document},
        response_handler=unwrap(operation),
        pagination_override=LINEAR_PAGINATION if paginates else None,
    )


def _mutation(name, schema, document, operation, description, action_label):
    """Declare one GraphQL mutation, with the success check its payload needs."""
    return _linear(
        name=name,
        args_schema=schema,
        method="POST",
        url_template=GRAPHQL_PATH,
        description=description,
        action_label=action_label,
        static_body={"query": document},
        response_handler=unwrap_mutation(operation),
    )


# ---------- account and workspace ----------

viewer = _query(
    "viewer",
    types.ViewerRequest,
    queries.VIEWER,
    "viewer",
    "Get the authenticated Linear user. Use this to resolve 'me' to the UUID "
    "that assignee filters and issue assignment expect.",
    "Checks the Linear account.",
)

organization = _query(
    "organization",
    types.OrganizationRequest,
    queries.ORGANIZATION,
    "organization",
    "Get the workspace itself — its name, URL key and member count.",
    "Reads the Linear workspace.",
)

teams_list_full = _query(
    "teams_list",
    types.TeamsListRequest,
    queries.TEAMS,
    "teams",
    "List the workspace's teams. Use this to resolve a team key such as 'ENG' "
    "to the UUID that issue creation requires.",
    "Lists Linear teams.",
    paginates=True,
)

teams_list = teams_list_full.derived(
    name="teams_list", keep=curation.list_filter_paths(teams_list_full.args_schema)
)

team_get = _query(
    "team_get",
    types.TeamGetRequest,
    queries.TEAM,
    "team",
    "Get one team, with its workflow states and current cycle. Accepts the "
    "team's UUID or its key, such as 'ENG'.",
    "Reads a Linear team.",
)

users_list_full = _query(
    "users_list",
    types.UsersListRequest,
    queries.USERS,
    "users",
    "List workspace members. Use this to resolve a person's name or email to "
    "the UUID that assignment expects.",
    "Lists Linear members.",
    paginates=True,
)

users_list = users_list_full.derived(
    name="users_list", keep=curation.list_filter_paths(users_list_full.args_schema)
)

user_get = _query(
    "user_get",
    types.UserGetRequest,
    queries.USER,
    "user",
    "Get one workspace member. Pass 'me' to get the authenticated user.",
    "Reads a Linear member.",
)

workflow_states_list_full = _query(
    "workflow_states_list",
    types.WorkflowStatesListRequest,
    queries.WORKFLOW_STATES,
    "workflowStates",
    "List workflow states — the statuses an issue can move between. Each has a "
    "`type` ('triage', 'backlog', 'unstarted', 'started', 'completed', "
    "'canceled') and a UUID. States are per-team, so filter by team to get the "
    "right ones.",
    "Lists Linear statuses.",
    paginates=True,
)

workflow_states_list = workflow_states_list_full.derived(
    name="workflow_states_list",
    keep=curation.list_filter_paths(workflow_states_list_full.args_schema),
)

workflow_state_get = _query(
    "workflow_state_get",
    types.WorkflowStateGetRequest,
    queries.WORKFLOW_STATE,
    "workflowState",
    "Get one workflow state by its UUID.",
    "Reads a Linear status.",
)

workflow_state_create = _mutation(
    "workflow_state_create",
    types.WorkflowStateCreateRequest,
    queries.WORKFLOW_STATE_CREATE,
    "workflowStateCreate",
    "Create a workflow state for a team. `name`, `team_id`, `type` and `color` are all required.",
    "Creates a Linear status.",
)

workflow_state_update = _mutation(
    "workflow_state_update",
    types.WorkflowStateUpdateRequest,
    queries.WORKFLOW_STATE_UPDATE,
    "workflowStateUpdate",
    "Rename a workflow state, recolour it or move its position. A state's type "
    "and team are fixed at creation and cannot be changed.",
    "Updates a Linear status.",
)

workflow_state_archive = _mutation(
    "workflow_state_archive",
    types.WorkflowStateArchiveRequest,
    queries.WORKFLOW_STATE_ARCHIVE,
    "workflowStateArchive",
    "Archive a workflow state, taking it out of the team's workflow.",
    "Archives a Linear status.",
)

team_memberships_list = _query(
    "team_memberships_list",
    types.TeamMembershipsListRequest,
    queries.TEAM_MEMBERSHIPS,
    "teamMemberships",
    "List who belongs to which team, and who owns each one.",
    "Lists Linear team members.",
    paginates=True,
)

team_membership_get = _query(
    "team_membership_get",
    types.TeamMembershipGetRequest,
    queries.TEAM_MEMBERSHIP,
    "teamMembership",
    "Get one team membership by its UUID.",
    "Reads a Linear team membership.",
)

team_membership_create = _mutation(
    "team_membership_create",
    types.TeamMembershipCreateRequest,
    queries.TEAM_MEMBERSHIP_CREATE,
    "teamMembershipCreate",
    "Add a member to a team.",
    "Adds a member to a Linear team.",
)

team_membership_update = _mutation(
    "team_membership_update",
    types.TeamMembershipUpdateRequest,
    queries.TEAM_MEMBERSHIP_UPDATE,
    "teamMembershipUpdate",
    "Change a team membership — chiefly to make someone the team's owner.",
    "Updates a Linear team membership.",
)

team_membership_delete = _mutation(
    "team_membership_delete",
    types.TeamMembershipDeleteRequest,
    queries.TEAM_MEMBERSHIP_DELETE,
    "teamMembershipDelete",
    "Remove a member from a team.",
    "Removes a member from a Linear team.",
)

# ---------- issues ----------

issues_list_full = _query(
    "issues_list",
    types.IssuesListRequest,
    queries.ISSUES,
    "issues",
    "List issues, optionally filtered. Conditions on one filter object combine "
    "with AND; use `and_` and `or_` for anything else. To find a team's open "
    "work, filter on team.key and state.type.",
    "Lists Linear issues.",
    paginates=True,
)

# One rule rather than one rule and an exception. A hand-picked set for this tool
# alone came to half the size, 15.5KB against 33.7KB, and measured identically -
# 96% and 100% filter use against the policy's 96% and 100%, on glm-5p3-flash and
# deepseek-v4p1, thirty generations each. Identical outcomes do not justify a
# second rule to maintain, and the tool that most needs to stay predictable is
# the one people reach for first.
issues_list = issues_list_full.derived(
    name="issues_list",
    keep=curation.list_filter_paths(issues_list_full.args_schema),
    description=(
        "List issues, optionally filtered. Conditions on one filter object "
        "combine with AND. To find a team's open work, filter on team.key and "
        "state.type."
    ),
)

issue_get = _query(
    "issue_get",
    types.IssueGetRequest,
    queries.ISSUE,
    "issue",
    "Get one issue with its description, comments, sub-issues, relations and "
    "attachments. Accepts either the issue's UUID or its human identifier, "
    "such as 'ENG-123'.",
    "Reads a Linear issue.",
)

issue_create = _mutation(
    "issue_create",
    types.IssueCreateRequest,
    queries.ISSUE_CREATE,
    "issueCreate",
    "Create an issue. `team_id` and `title` are required; everything else is "
    "optional. The UUIDs for team, assignee, state and labels come from "
    "`teams_list`, `users_list` and `workflow_states_list` — Linear does not "
    "accept names here. Set `parent_id` to create a sub-issue.",
    "Creates a Linear issue.",
)

issue_update = _mutation(
    "issue_update",
    types.IssueUpdateRequest,
    queries.ISSUE_UPDATE,
    "issueUpdate",
    "Update an issue. Only the fields provided are changed. To close an issue, "
    "set `state_id` to a state whose type is 'completed' or 'canceled' — "
    "Linear has no separate close operation. Use `added_label_ids` and "
    "`removed_label_ids` to adjust labels; `label_ids` replaces them outright.",
    "Updates a Linear issue.",
)

issue_batch_update = _mutation(
    "issue_batch_update",
    types.IssueBatchUpdateRequest,
    queries.ISSUE_BATCH_UPDATE,
    "issueBatchUpdate",
    "Apply one change to many issues at once — reassigning a queue, moving a "
    "set into a cycle. `ids` must be UUIDs rather than identifiers like "
    "'ENG-123'.",
    "Updates several Linear issues.",
)

issue_delete = _mutation(
    "issue_delete",
    types.IssueDeleteRequest,
    queries.ISSUE_DELETE,
    "issueDelete",
    "Move an issue to the trash, from where it can be restored. Set "
    "`permanently_delete` to erase it instead — that cannot be undone.",
    "Deletes a Linear issue.",
)

issue_archive = _mutation(
    "issue_archive",
    types.IssueArchiveRequest,
    queries.ISSUE_ARCHIVE,
    "issueArchive",
    "Archive an issue, taking it out of the active lists while keeping it "
    "findable. `issue_unarchive` reverses it.",
    "Archives a Linear issue.",
)

issue_unarchive = _mutation(
    "issue_unarchive",
    types.IssueUnarchiveRequest,
    queries.ISSUE_UNARCHIVE,
    "issueUnarchive",
    "Restore an archived issue to the active lists.",
    "Restores an archived Linear issue.",
)

issue_add_label = _mutation(
    "issue_add_label",
    types.IssueAddLabelRequest,
    queries.ISSUE_ADD_LABEL,
    "issueAddLabel",
    "Add one label to an issue, leaving its other labels alone.",
    "Labels a Linear issue.",
)

issue_remove_label = _mutation(
    "issue_remove_label",
    types.IssueRemoveLabelRequest,
    queries.ISSUE_REMOVE_LABEL,
    "issueRemoveLabel",
    "Remove one label from an issue, leaving its other labels alone.",
    "Unlabels a Linear issue.",
)

issue_subscribe = _mutation(
    "issue_subscribe",
    types.IssueSubscribeRequest,
    queries.ISSUE_SUBSCRIBE,
    "issueSubscribe",
    "Subscribe someone to an issue's updates. Name them by UUID or email; give "
    "neither to subscribe the authenticated user.",
    "Subscribes to a Linear issue.",
)

issue_unsubscribe = _mutation(
    "issue_unsubscribe",
    types.IssueUnsubscribeRequest,
    queries.ISSUE_UNSUBSCRIBE,
    "issueUnsubscribe",
    "Unsubscribe someone from an issue's updates.",
    "Unsubscribes from a Linear issue.",
)

issue_relations_list = _query(
    "issue_relations_list",
    types.IssueRelationsListRequest,
    queries.ISSUE_RELATIONS,
    "issueRelations",
    "List the links between issues across the workspace. To see one issue's "
    "links, read the issue with `issue_get` instead.",
    "Lists Linear issue links.",
    paginates=True,
)

issue_relation_get = _query(
    "issue_relation_get",
    types.IssueRelationGetRequest,
    queries.ISSUE_RELATION,
    "issueRelation",
    "Get one issue relation by its UUID.",
    "Reads a Linear issue link.",
)

issue_relation_create = _mutation(
    "issue_relation_create",
    types.IssueRelationCreateRequest,
    queries.ISSUE_RELATION_CREATE,
    "issueRelationCreate",
    "Link two issues as blocking, duplicate, related or similar. 'blocks' and "
    "'duplicate' are directional: the issue in `issue_id` is the one doing the "
    "blocking, or the one that is the duplicate.",
    "Links two Linear issues.",
)

issue_relation_update = _mutation(
    "issue_relation_update",
    types.IssueRelationUpdateRequest,
    queries.ISSUE_RELATION_UPDATE,
    "issueRelationUpdate",
    "Change how two issues are linked, or which issues the link joins.",
    "Updates a Linear issue link.",
)

issue_relation_delete = _mutation(
    "issue_relation_delete",
    types.IssueRelationDeleteRequest,
    queries.ISSUE_RELATION_DELETE,
    "issueRelationDelete",
    "Unlink two issues.",
    "Unlinks two Linear issues.",
)

# ---------- comments and reactions ----------

comments_list_full = _query(
    "comments_list",
    types.CommentsListRequest,
    queries.COMMENTS,
    "comments",
    "Read comments. To read one issue's thread, filter on `issue.id.eq` with "
    "the issue's UUID from `issues_list` or `issue_get`.",
    "Reads Linear comments.",
    paginates=True,
)

comments_list = comments_list_full.derived(
    name="comments_list", keep=curation.list_filter_paths(comments_list_full.args_schema)
)

comment_get = _query(
    "comment_get",
    types.CommentGetRequest,
    queries.COMMENT,
    "comment",
    "Get one comment with its replies. Name it by UUID, or by the hash from a Linear comment URL.",
    "Reads a Linear comment.",
)

comment_create = _mutation(
    "comment_create",
    types.CommentCreateRequest,
    queries.COMMENT_CREATE,
    "commentCreate",
    "Post a comment. Give exactly one parent — an issue, project, project "
    "update, initiative, initiative update or document. Markdown is supported "
    "in the body, and `parent_id` makes it a threaded reply.",
    "Comments in Linear.",
)

comment_update = _mutation(
    "comment_update",
    types.CommentUpdateRequest,
    queries.COMMENT_UPDATE,
    "commentUpdate",
    "Edit a comment's text, by its UUID.",
    "Edits a Linear comment.",
)

comment_delete = _mutation(
    "comment_delete",
    types.CommentDeleteRequest,
    queries.COMMENT_DELETE,
    "commentDelete",
    "Delete a comment.",
    "Deletes a Linear comment.",
)

comment_resolve = _mutation(
    "comment_resolve",
    types.CommentResolveRequest,
    queries.COMMENT_RESOLVE,
    "commentResolve",
    "Mark a comment thread resolved.",
    "Resolves a Linear comment thread.",
)

comment_unresolve = _mutation(
    "comment_unresolve",
    types.CommentUnresolveRequest,
    queries.COMMENT_UNRESOLVE,
    "commentUnresolve",
    "Reopen a resolved comment thread.",
    "Reopens a Linear comment thread.",
)

reaction_create = _mutation(
    "reaction_create",
    types.ReactionCreateRequest,
    queries.REACTION_CREATE,
    "reactionCreate",
    "React to a comment, issue or status update with an emoji. Give the emoji "
    "by name without colons, such as '+1', and exactly one target.",
    "Reacts in Linear.",
)

reaction_delete = _mutation(
    "reaction_delete",
    types.ReactionDeleteRequest,
    queries.REACTION_DELETE,
    "reactionDelete",
    "Remove a reaction.",
    "Removes a Linear reaction.",
)

# ---------- labels ----------

issue_labels_list_full = _query(
    "issue_labels_list",
    types.IssueLabelsListRequest,
    queries.ISSUE_LABELS,
    "issueLabels",
    "List the workspace's issue labels, with the UUIDs `issue_create` and `issue_update` need.",
    "Lists Linear labels.",
    paginates=True,
)

issue_labels_list = issue_labels_list_full.derived(
    name="issue_labels_list", keep=curation.list_filter_paths(issue_labels_list_full.args_schema)
)

issue_label_get = _query(
    "issue_label_get",
    types.IssueLabelGetRequest,
    queries.ISSUE_LABEL,
    "issueLabel",
    "Get one label by its UUID.",
    "Reads a Linear label.",
)

issue_label_create = _mutation(
    "issue_label_create",
    types.IssueLabelCreateRequest,
    queries.ISSUE_LABEL_CREATE,
    "issueLabelCreate",
    "Create a label. Give a `team_id` for a label one team uses, or omit it for "
    "one the whole workspace shares.",
    "Creates a Linear label.",
)

issue_label_update = _mutation(
    "issue_label_update",
    types.IssueLabelUpdateRequest,
    queries.ISSUE_LABEL_UPDATE,
    "issueLabelUpdate",
    "Rename a label, recolour it, or retire it. Retiring keeps the label on the "
    "issues that already carry it while taking it out of the picker.",
    "Updates a Linear label.",
)

issue_label_delete = _mutation(
    "issue_label_delete",
    types.IssueLabelDeleteRequest,
    queries.ISSUE_LABEL_DELETE,
    "issueLabelDelete",
    "Delete a label, removing it from every issue that carries it.",
    "Deletes a Linear label.",
)

project_labels_list = _query(
    "project_labels_list",
    types.ProjectLabelsListRequest,
    queries.PROJECT_LABELS,
    "projectLabels",
    "List the labels that tag projects. These are a different set from issue "
    "labels and are not interchangeable.",
    "Lists Linear project labels.",
    paginates=True,
)

# ---------- projects ----------

projects_list_full = _query(
    "projects_list",
    types.ProjectsListRequest,
    queries.PROJECTS,
    "projects",
    "List projects in the workspace, with their status and progress.",
    "Lists Linear projects.",
    paginates=True,
)

projects_list = projects_list_full.derived(
    name="projects_list", keep=curation.list_filter_paths(projects_list_full.args_schema)
)

project_get = _query(
    "project_get",
    types.ProjectGetRequest,
    queries.PROJECT,
    "project",
    "Get one project with its content, milestones and members. Accepts the "
    "project's UUID or the slug from its URL.",
    "Reads a Linear project.",
)

project_create = _mutation(
    "project_create",
    types.ProjectCreateRequest,
    queries.PROJECT_CREATE,
    "projectCreate",
    "Create a project. `name` and at least one team UUID are required; team "
    "UUIDs come from `teams_list`.",
    "Creates a Linear project.",
)

project_update = _mutation(
    "project_update",
    types.ProjectUpdateRequest,
    queries.PROJECT_UPDATE,
    "projectUpdate",
    "Update a project's name, description, lead, dates or status. A project's "
    "status is a UUID from `project_statuses_list`, not a word — this is how a "
    "project is completed or cancelled. To post a status *update* on a "
    "project, use `project_update_create` instead.",
    "Updates a Linear project.",
)

project_delete = _mutation(
    "project_delete",
    types.ProjectDeleteRequest,
    queries.PROJECT_DELETE,
    "projectDelete",
    "Move a project to the trash. `project_unarchive` restores it.",
    "Deletes a Linear project.",
)

project_unarchive = _mutation(
    "project_unarchive",
    types.ProjectUnarchiveRequest,
    queries.PROJECT_UNARCHIVE,
    "projectUnarchive",
    "Restore a trashed project.",
    "Restores a Linear project.",
)

project_add_label = _mutation(
    "project_add_label",
    types.ProjectAddLabelRequest,
    queries.PROJECT_ADD_LABEL,
    "projectAddLabel",
    "Add one project label to a project.",
    "Labels a Linear project.",
)

project_remove_label = _mutation(
    "project_remove_label",
    types.ProjectRemoveLabelRequest,
    queries.PROJECT_REMOVE_LABEL,
    "projectRemoveLabel",
    "Remove one project label from a project.",
    "Unlabels a Linear project.",
)

project_statuses_list = _query(
    "project_statuses_list",
    types.ProjectStatusesListRequest,
    queries.PROJECT_STATUSES,
    "projectStatuses",
    "List the statuses a project can be in, with the UUIDs `project_create` and "
    "`project_update` need. Each has a `type`: 'backlog', 'planned', 'started', "
    "'paused', 'completed' or 'canceled'.",
    "Lists Linear project statuses.",
    paginates=True,
)

project_milestones_list_full = _query(
    "project_milestones_list",
    types.ProjectMilestonesListRequest,
    queries.PROJECT_MILESTONES,
    "projectMilestones",
    "List project milestones. Filter by project to get one project's.",
    "Lists Linear milestones.",
    paginates=True,
)

project_milestones_list = project_milestones_list_full.derived(
    name="project_milestones_list",
    keep=curation.list_filter_paths(project_milestones_list_full.args_schema),
)

project_milestone_get = _query(
    "project_milestone_get",
    types.ProjectMilestoneGetRequest,
    queries.PROJECT_MILESTONE,
    "projectMilestone",
    "Get one project milestone by its UUID.",
    "Reads a Linear milestone.",
)

project_milestone_create = _mutation(
    "project_milestone_create",
    types.ProjectMilestoneCreateRequest,
    queries.PROJECT_MILESTONE_CREATE,
    "projectMilestoneCreate",
    "Create a milestone inside a project.",
    "Creates a Linear milestone.",
)

project_milestone_update = _mutation(
    "project_milestone_update",
    types.ProjectMilestoneUpdateRequest,
    queries.PROJECT_MILESTONE_UPDATE,
    "projectMilestoneUpdate",
    "Rename a milestone, move its target date, or move it to another project.",
    "Updates a Linear milestone.",
)

project_milestone_delete = _mutation(
    "project_milestone_delete",
    types.ProjectMilestoneDeleteRequest,
    queries.PROJECT_MILESTONE_DELETE,
    "projectMilestoneDelete",
    "Delete a project milestone.",
    "Deletes a Linear milestone.",
)

project_updates_list_full = _query(
    "project_updates_list",
    types.ProjectUpdatesListRequest,
    queries.PROJECT_UPDATES,
    "projectUpdates",
    "Read the status updates posted on projects — the periodic 'on track, here "
    "is what moved' notes. Filter by project for one project's history.",
    "Reads Linear project updates.",
    paginates=True,
)

project_updates_list = project_updates_list_full.derived(
    name="project_updates_list",
    keep=curation.list_filter_paths(project_updates_list_full.args_schema),
)

project_update_get = _query(
    "project_update_get",
    types.ProjectUpdateGetRequest,
    queries.PROJECT_UPDATE_GET,
    "projectUpdate",
    "Get one project status update by its UUID.",
    "Reads a Linear project update.",
)

project_update_create = _mutation(
    "project_update_create",
    types.ProjectUpdateCreateRequest,
    queries.PROJECT_UPDATE_CREATE,
    "projectUpdateCreate",
    "Post a status update on a project, optionally reporting health as "
    "'onTrack', 'atRisk' or 'offTrack'. This writes a note; to change the "
    "project itself, use `project_update`.",
    "Posts a Linear project update.",
)

project_update_update = _mutation(
    "project_update_update",
    types.ProjectUpdateUpdateRequest,
    queries.PROJECT_UPDATE_UPDATE,
    "projectUpdateUpdate",
    "Edit a project status update that has already been posted.",
    "Edits a Linear project update.",
)

project_update_archive = _mutation(
    "project_update_archive",
    types.ProjectUpdateArchiveRequest,
    queries.PROJECT_UPDATE_ARCHIVE,
    "projectUpdateArchive",
    "Archive a project status update.",
    "Archives a Linear project update.",
)

# ---------- cycles ----------

cycles_list_full = _query(
    "cycles_list",
    types.CyclesListRequest,
    queries.CYCLES,
    "cycles",
    "List cycles — Linear's name for a team's time-box. Filter on "
    "`is_active.eq` for the cycle a team is in now.",
    "Lists Linear cycles.",
    paginates=True,
)

cycles_list = cycles_list_full.derived(
    name="cycles_list", keep=curation.list_filter_paths(cycles_list_full.args_schema)
)

cycle_get = _query(
    "cycle_get",
    types.CycleGetRequest,
    queries.CYCLE,
    "cycle",
    "Get one cycle with the issues in it.",
    "Reads a Linear cycle.",
)

cycle_update = _mutation(
    "cycle_update",
    types.CycleUpdateRequest,
    queries.CYCLE_UPDATE,
    "cycleUpdate",
    "Rename a cycle or move its dates. Cycles are created by a team's cadence "
    "settings rather than by hand.",
    "Updates a Linear cycle.",
)

cycle_archive = _mutation(
    "cycle_archive",
    types.CycleArchiveRequest,
    queries.CYCLE_ARCHIVE,
    "cycleArchive",
    "Archive a cycle.",
    "Archives a Linear cycle.",
)

cycle_start_upcoming_today = _mutation(
    "cycle_start_upcoming_today",
    types.CycleStartUpcomingCycleTodayRequest,
    queries.CYCLE_START_UPCOMING_CYCLE_TODAY,
    "cycleStartUpcomingCycleToday",
    "Start a team's next cycle today rather than on its scheduled date.",
    "Starts a Linear cycle early.",
)

# ---------- initiatives ----------

initiatives_list_full = _query(
    "initiatives_list",
    types.InitiativesListRequest,
    queries.INITIATIVES,
    "initiatives",
    "List initiatives — the grouping above a project, and what Linear replaced roadmaps with.",
    "Lists Linear initiatives.",
    paginates=True,
)

initiatives_list = initiatives_list_full.derived(
    name="initiatives_list", keep=curation.list_filter_paths(initiatives_list_full.args_schema)
)

initiative_get = _query(
    "initiative_get",
    types.InitiativeGetRequest,
    queries.INITIATIVE,
    "initiative",
    "Get one initiative with its projects and links.",
    "Reads a Linear initiative.",
)

initiative_create = _mutation(
    "initiative_create",
    types.InitiativeCreateRequest,
    queries.INITIATIVE_CREATE,
    "initiativeCreate",
    "Create an initiative. Only `name` is required.",
    "Creates a Linear initiative.",
)

initiative_update = _mutation(
    "initiative_update",
    types.InitiativeUpdateRequest,
    queries.INITIATIVE_UPDATE,
    "initiativeUpdate",
    "Update an initiative's name, owner, status or target date. Status is one "
    "of 'Planned', 'Proposed', 'Active', 'Completed' or 'Canceled', "
    "capitalised. To post a status update on one, use "
    "`initiative_update_create`.",
    "Updates a Linear initiative.",
)

initiative_delete = _mutation(
    "initiative_delete",
    types.InitiativeDeleteRequest,
    queries.INITIATIVE_DELETE,
    "initiativeDelete",
    "Move an initiative to the trash.",
    "Deletes a Linear initiative.",
)

initiative_archive = _mutation(
    "initiative_archive",
    types.InitiativeArchiveRequest,
    queries.INITIATIVE_ARCHIVE,
    "initiativeArchive",
    "Archive an initiative.",
    "Archives a Linear initiative.",
)

initiative_unarchive = _mutation(
    "initiative_unarchive",
    types.InitiativeUnarchiveRequest,
    queries.INITIATIVE_UNARCHIVE,
    "initiativeUnarchive",
    "Restore an archived initiative.",
    "Restores a Linear initiative.",
)

initiative_to_project_create = _mutation(
    "initiative_to_project_create",
    types.InitiativeToProjectCreateRequest,
    queries.INITIATIVE_TO_PROJECT_CREATE,
    "initiativeToProjectCreate",
    "Add a project to an initiative.",
    "Adds a project to a Linear initiative.",
)

initiative_to_project_delete = _mutation(
    "initiative_to_project_delete",
    types.InitiativeToProjectDeleteRequest,
    queries.INITIATIVE_TO_PROJECT_DELETE,
    "initiativeToProjectDelete",
    "Remove a project from an initiative. The id is the link's, not the "
    "project's; it comes back from `initiative_get`.",
    "Removes a project from a Linear initiative.",
)

initiative_updates_list = _query(
    "initiative_updates_list",
    types.InitiativeUpdatesListRequest,
    queries.INITIATIVE_UPDATES,
    "initiativeUpdates",
    "Read the status updates posted on initiatives.",
    "Reads Linear initiative updates.",
    paginates=True,
)

initiative_update_create = _mutation(
    "initiative_update_create",
    types.InitiativeUpdateCreateRequest,
    queries.INITIATIVE_UPDATE_CREATE,
    "initiativeUpdateCreate",
    "Post a status update on an initiative.",
    "Posts a Linear initiative update.",
)

# ---------- documents ----------

documents_list_full = _query(
    "documents_list",
    types.DocumentsListRequest,
    queries.DOCUMENTS,
    "documents",
    "List documents. Filter by project or initiative to scope them.",
    "Lists Linear documents.",
    paginates=True,
)

documents_list = documents_list_full.derived(
    name="documents_list", keep=curation.list_filter_paths(documents_list_full.args_schema)
)

document_get = _query(
    "document_get",
    types.DocumentGetRequest,
    queries.DOCUMENT,
    "document",
    "Get one document with its full content. Accepts the document's UUID or the slug from its URL.",
    "Reads a Linear document.",
)

document_create = _mutation(
    "document_create",
    types.DocumentCreateRequest,
    queries.DOCUMENT_CREATE,
    "documentCreate",
    "Create a document. Only `title` is required — a document can hang off a "
    "project, initiative, issue, cycle or team, or off nothing at all.",
    "Creates a Linear document.",
)

document_update = _mutation(
    "document_update",
    types.DocumentUpdateRequest,
    queries.DOCUMENT_UPDATE,
    "documentUpdate",
    "Update a document. Note that `content` replaces the document's body "
    "rather than appending to it.",
    "Updates a Linear document.",
)

document_delete = _mutation(
    "document_delete",
    types.DocumentDeleteRequest,
    queries.DOCUMENT_DELETE,
    "documentDelete",
    "Move a document to the trash. `document_unarchive` restores it.",
    "Deletes a Linear document.",
)

document_unarchive = _mutation(
    "document_unarchive",
    types.DocumentUnarchiveRequest,
    queries.DOCUMENT_UNARCHIVE,
    "documentUnarchive",
    "Restore a trashed document.",
    "Restores a Linear document.",
)

# ---------- attachments ----------

attachments_list_full = _query(
    "attachments_list",
    types.AttachmentsListRequest,
    queries.ATTACHMENTS,
    "attachments",
    "List attachments — the links between Linear issues and things outside it.",
    "Lists Linear attachments.",
    paginates=True,
)

attachments_list = attachments_list_full.derived(
    name="attachments_list", keep=curation.list_filter_paths(attachments_list_full.args_schema)
)

attachment_get = _query(
    "attachment_get",
    types.AttachmentGetRequest,
    queries.ATTACHMENT,
    "attachment",
    "Get one attachment and the issue it is on.",
    "Reads a Linear attachment.",
)

attachments_for_url = _query(
    "attachments_for_url",
    types.AttachmentsForUrlRequest,
    queries.ATTACHMENTS_FOR_URL,
    "attachmentsForURL",
    "Find which issues an external URL is attached to. This is the tool for "
    "'is this pull request already linked to an issue?'.",
    "Looks up a Linear attachment by URL.",
    paginates=True,
)

attachment_create = _mutation(
    "attachment_create",
    types.AttachmentCreateRequest,
    queries.ATTACHMENT_CREATE,
    "attachmentCreate",
    "Link an issue to something outside Linear. Linear deduplicates by URL: "
    "creating an attachment whose URL is already on the issue updates that one "
    "rather than adding a second.",
    "Attaches a link to a Linear issue.",
)

attachment_update = _mutation(
    "attachment_update",
    types.AttachmentUpdateRequest,
    queries.ATTACHMENT_UPDATE,
    "attachmentUpdate",
    "Update an attachment's title, subtitle or icon. `title` is required even "
    "when you only mean to change the subtitle — that is Linear's rule, so "
    "read the attachment first if you do not know it.",
    "Updates a Linear attachment.",
)

attachment_delete = _mutation(
    "attachment_delete",
    types.AttachmentDeleteRequest,
    queries.ATTACHMENT_DELETE,
    "attachmentDelete",
    "Remove an attachment from its issue.",
    "Removes a Linear attachment.",
)

# ---------- customers ----------

customers_list_full = _query(
    "customers_list",
    types.CustomersListRequest,
    queries.CUSTOMERS,
    "customers",
    "List customers — the companies whose requests Linear tracks against issues.",
    "Lists Linear customers.",
    paginates=True,
)

customers_list = customers_list_full.derived(
    name="customers_list", keep=curation.list_filter_paths(customers_list_full.args_schema)
)

customer_get = _query(
    "customer_get",
    types.CustomerGetRequest,
    queries.CUSTOMER,
    "customer",
    "Get one customer by its UUID.",
    "Reads a Linear customer.",
)

customer_create = _mutation(
    "customer_create",
    types.CustomerCreateRequest,
    queries.CUSTOMER_CREATE,
    "customerCreate",
    "Create a customer. Only `name` is required.",
    "Creates a Linear customer.",
)

customer_update = _mutation(
    "customer_update",
    types.CustomerUpdateRequest,
    queries.CUSTOMER_UPDATE,
    "customerUpdate",
    "Update a customer's name, owner, tier, revenue or size.",
    "Updates a Linear customer.",
)

customer_delete = _mutation(
    "customer_delete",
    types.CustomerDeleteRequest,
    queries.CUSTOMER_DELETE,
    "customerDelete",
    "Delete a customer.",
    "Deletes a Linear customer.",
)

customer_needs_list_full = _query(
    "customer_needs_list",
    types.CustomerNeedsListRequest,
    queries.CUSTOMER_NEEDS,
    "customerNeeds",
    "List customer requests. Filter by issue to see what a piece of work is "
    "wanted for, or by customer to see everything one company has asked for.",
    "Lists Linear customer requests.",
    paginates=True,
)

customer_needs_list = customer_needs_list_full.derived(
    name="customer_needs_list",
    keep=curation.list_filter_paths(customer_needs_list_full.args_schema),
)

customer_need_create = _mutation(
    "customer_need_create",
    types.CustomerNeedCreateRequest,
    queries.CUSTOMER_NEED_CREATE,
    "customerNeedCreate",
    "Record a customer request, optionally attached to an issue or project. "
    "This is the one Linear mutation whose reply carries no object — it "
    "answers only with whether it worked.",
    "Records a Linear customer request.",
)

customer_need_update = _mutation(
    "customer_need_update",
    types.CustomerNeedUpdateRequest,
    queries.CUSTOMER_NEED_UPDATE,
    "customerNeedUpdate",
    "Update a customer request, chiefly to attach it to an issue.",
    "Updates a Linear customer request.",
)

customer_need_delete = _mutation(
    "customer_need_delete",
    types.CustomerNeedDeleteRequest,
    queries.CUSTOMER_NEED_DELETE,
    "customerNeedDelete",
    "Delete a customer request.",
    "Deletes a Linear customer request.",
)

customer_statuses_list = _query(
    "customer_statuses_list",
    types.CustomerStatusesListRequest,
    queries.CUSTOMER_STATUSES,
    "customerStatuses",
    "List the statuses a customer can be in, with the UUIDs customer writes need.",
    "Lists Linear customer statuses.",
    paginates=True,
)

customer_tiers_list = _query(
    "customer_tiers_list",
    types.CustomerTiersListRequest,
    queries.CUSTOMER_TIERS,
    "customerTiers",
    "List the tiers a customer can be assigned to.",
    "Lists Linear customer tiers.",
    paginates=True,
)

# ---------- notifications, favorites, saved views ----------

notifications_list = _query(
    "notifications_list",
    types.NotificationsListRequest,
    queries.NOTIFICATIONS,
    "notifications",
    "Read the authenticated user's notifications — what Linear has told them "
    "about and what is still unread.",
    "Reads Linear notifications.",
    paginates=True,
)

notification_get = _query(
    "notification_get",
    types.NotificationGetRequest,
    queries.NOTIFICATION,
    "notification",
    "Get one notification by its UUID.",
    "Reads a Linear notification.",
)

notification_update = _mutation(
    "notification_update",
    types.NotificationUpdateRequest,
    queries.NOTIFICATION_UPDATE,
    "notificationUpdate",
    "Mark a notification read by setting `read_at`, or snooze it with `snoozed_until_at`.",
    "Updates a Linear notification.",
)

notification_archive = _mutation(
    "notification_archive",
    types.NotificationArchiveRequest,
    queries.NOTIFICATION_ARCHIVE,
    "notificationArchive",
    "Archive a notification.",
    "Archives a Linear notification.",
)

notification_unarchive = _mutation(
    "notification_unarchive",
    types.NotificationUnarchiveRequest,
    queries.NOTIFICATION_UNARCHIVE,
    "notificationUnarchive",
    "Restore an archived notification.",
    "Restores a Linear notification.",
)

notification_mark_read_all = _mutation(
    "notification_mark_read_all",
    types.NotificationMarkReadAllRequest,
    queries.NOTIFICATION_MARK_READ_ALL,
    "notificationMarkReadAll",
    "Mark every notification raised by one issue, project or initiative as "
    "read. This is scoped to an entity rather than to the whole inbox.",
    "Marks Linear notifications read.",
)

favorites_list = _query(
    "favorites_list",
    types.FavoritesListRequest,
    queries.FAVORITES,
    "favorites",
    "List what the authenticated user has starred.",
    "Lists Linear favorites.",
    paginates=True,
)

favorite_create = _mutation(
    "favorite_create",
    types.FavoriteCreateRequest,
    queries.FAVORITE_CREATE,
    "favoriteCreate",
    "Star an issue, project, document, view, label, team or user. Give exactly one target.",
    "Stars something in Linear.",
)

favorite_update = _mutation(
    "favorite_update",
    types.FavoriteUpdateRequest,
    queries.FAVORITE_UPDATE,
    "favoriteUpdate",
    "Move a favorite into a folder, or reorder it.",
    "Updates a Linear favorite.",
)

favorite_delete = _mutation(
    "favorite_delete",
    types.FavoriteDeleteRequest,
    queries.FAVORITE_DELETE,
    "favoriteDelete",
    "Unstar something.",
    "Unstars something in Linear.",
)

custom_views_list = _query(
    "custom_views_list",
    types.CustomViewsListRequest,
    queries.CUSTOM_VIEWS,
    "customViews",
    "List the workspace's saved views, each with the filter it holds.",
    "Lists Linear saved views.",
    paginates=True,
)

custom_view_get = _query(
    "custom_view_get",
    types.CustomViewGetRequest,
    queries.CUSTOM_VIEW,
    "customView",
    "Get one saved view. Its `filterData` is an issue filter, and can be "
    "replayed through `issues_list`.",
    "Reads a Linear saved view.",
)

custom_view_create_full = _mutation(
    "custom_view_create",
    types.CustomViewCreateRequest,
    queries.CUSTOM_VIEW_CREATE,
    "customViewCreate",
    "Save a filter as a view. `filter_data` takes the same shape `issues_list` accepts.",
    "Creates a Linear saved view.",
)

# A saved view carries four filters, not one, and they sit on `variables.input`
# rather than `variables.filter` - which is why `curation` looks for filters by
# type. Four mirrors on one tool is what made this the largest in the pack.
custom_view_create = custom_view_create_full.derived(
    name="custom_view_create",
    keep=curation.list_filter_paths(custom_view_create_full.args_schema),
)

custom_view_delete = _mutation(
    "custom_view_delete",
    types.CustomViewDeleteRequest,
    queries.CUSTOM_VIEW_DELETE,
    "customViewDelete",
    "Delete a saved view.",
    "Deletes a Linear saved view.",
)

# ---------- search ----------

search_issues_full = _query(
    "search_issues",
    types.SearchIssuesRequest,
    queries.SEARCH_ISSUES,
    "searchIssues",
    "Search issues by text, across titles and descriptions. Set "
    "`include_comments` to search inside comments too. This is full-text "
    "search; to filter on fields such as state or assignee, use `issues_list`.",
    "Searches Linear issues.",
    paginates=True,
)

search_issues = search_issues_full.derived(
    name="search_issues", keep=curation.list_filter_paths(search_issues_full.args_schema)
)

search_projects = _query(
    "search_projects",
    types.SearchProjectsRequest,
    queries.SEARCH_PROJECTS,
    "searchProjects",
    "Search projects by text, across names and descriptions.",
    "Searches Linear projects.",
    paginates=True,
)

search_documents = _query(
    "search_documents",
    types.SearchDocumentsRequest,
    queries.SEARCH_DOCUMENTS,
    "searchDocuments",
    "Search documents by text, across titles and content.",
    "Searches Linear documents.",
    paginates=True,
)

# ---------- webhooks ----------

webhooks_list = _query(
    "webhooks_list",
    types.WebhooksListRequest,
    queries.WEBHOOKS,
    "webhooks",
    "List the workspace's webhooks.",
    "Lists Linear webhooks.",
    paginates=True,
)

webhook_get = _query(
    "webhook_get",
    types.WebhookGetRequest,
    queries.WEBHOOK,
    "webhook",
    "Get one webhook by its UUID.",
    "Reads a Linear webhook.",
)

webhook_create = _mutation(
    "webhook_create",
    types.WebhookCreateRequest,
    queries.WEBHOOK_CREATE,
    "webhookCreate",
    "Create a webhook. Scope it to one team with `team_id` or to every public "
    "team with `all_public_teams`, and name the resource types it should fire "
    "for, such as 'Issue' or 'Comment'.",
    "Creates a Linear webhook.",
)

webhook_update = _mutation(
    "webhook_update",
    types.WebhookUpdateRequest,
    queries.WEBHOOK_UPDATE,
    "webhookUpdate",
    "Update a webhook's URL, resource types, secret, or whether it is enabled.",
    "Updates a Linear webhook.",
)

webhook_delete = _mutation(
    "webhook_delete",
    types.WebhookDeleteRequest,
    queries.WEBHOOK_DELETE,
    "webhookDelete",
    "Delete a webhook.",
    "Deletes a Linear webhook.",
)


TOOLS: list[Tool] = [
    # workspace
    viewer,
    organization,
    teams_list,
    team_get,
    users_list,
    user_get,
    workflow_states_list,
    workflow_state_get,
    workflow_state_create,
    workflow_state_update,
    workflow_state_archive,
    team_memberships_list,
    team_membership_get,
    team_membership_create,
    team_membership_update,
    team_membership_delete,
    # issues
    issues_list,
    issue_get,
    issue_create,
    issue_update,
    issue_batch_update,
    issue_delete,
    issue_archive,
    issue_unarchive,
    issue_add_label,
    issue_remove_label,
    issue_subscribe,
    issue_unsubscribe,
    issue_relations_list,
    issue_relation_get,
    issue_relation_create,
    issue_relation_update,
    issue_relation_delete,
    # comments and reactions
    comments_list,
    comment_get,
    comment_create,
    comment_update,
    comment_delete,
    comment_resolve,
    comment_unresolve,
    reaction_create,
    reaction_delete,
    # labels
    issue_labels_list,
    issue_label_get,
    issue_label_create,
    issue_label_update,
    issue_label_delete,
    project_labels_list,
    # projects
    projects_list,
    project_get,
    project_create,
    project_update,
    project_delete,
    project_unarchive,
    project_add_label,
    project_remove_label,
    project_statuses_list,
    project_milestones_list,
    project_milestone_get,
    project_milestone_create,
    project_milestone_update,
    project_milestone_delete,
    project_updates_list,
    project_update_get,
    project_update_create,
    project_update_update,
    project_update_archive,
    # cycles
    cycles_list,
    cycle_get,
    cycle_update,
    cycle_archive,
    cycle_start_upcoming_today,
    # initiatives
    initiatives_list,
    initiative_get,
    initiative_create,
    initiative_update,
    initiative_delete,
    initiative_archive,
    initiative_unarchive,
    initiative_to_project_create,
    initiative_to_project_delete,
    initiative_updates_list,
    initiative_update_create,
    # documents
    documents_list,
    document_get,
    document_create,
    document_update,
    document_delete,
    document_unarchive,
    # attachments
    attachments_list,
    attachment_get,
    attachments_for_url,
    attachment_create,
    attachment_update,
    attachment_delete,
    # customers
    customers_list,
    customer_get,
    customer_create,
    customer_update,
    customer_delete,
    customer_needs_list,
    customer_need_create,
    customer_need_update,
    customer_need_delete,
    customer_statuses_list,
    customer_tiers_list,
    # notifications, favorites, saved views
    notifications_list,
    notification_get,
    notification_update,
    notification_archive,
    notification_unarchive,
    notification_mark_read_all,
    favorites_list,
    favorite_create,
    favorite_update,
    favorite_delete,
    custom_views_list,
    custom_view_get,
    custom_view_create,
    custom_view_delete,
    # search
    search_issues,
    search_projects,
    search_documents,
    # webhooks
    webhooks_list,
    webhook_get,
    webhook_create,
    webhook_update,
    webhook_delete,
]

__all__ = [
    "TOOLS",
    "configure",
    "BASE_URL",
    "GRAPHQL_PATH",
    "QUOTA_DOC_URL",
    "LINEAR_PAGINATION",
    "LINEAR_ENVELOPE",
    "queries",
    "types",
] + [tool.name.split("__")[-1] for tool in TOOLS]
