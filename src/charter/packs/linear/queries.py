# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
The GraphQL documents this pack sends.

Each one is a constant: it is what the tool *is*, not something the model
chooses. They are declared as ``static_body`` on the tool, which keeps them off
the schema entirely — a model filling in arguments cannot see a query document,
and so cannot rewrite one.

That matters more than it sounds. A GraphQL endpoint is a single URL that
accepts arbitrary documents; a tool that let the model supply the query would
not be an integration with a boundary, it would be a shell. Fixing the document
and typing only the variables is what makes ``issues_list`` a narrower
capability than "call Linear".

**The selection sets are deliberately small, and shared.** Linear charges a
complexity budget — 0.1 points per property, 1 per object, multiplied by the
page size for a connection, capped at 10,000 points for a single query — so
asking for fields nobody reads costs real quota. The per-resource ``_FIELDS``
constants exist so that the read, the list and the mutation that touch one
resource cannot drift into returning three different shapes of it.

**Mutation payloads come in three shapes**, and the difference is not
cosmetic: an ordinary payload names the thing it changed after the resource
(``issue``, ``comment``, ``project``), an *archive* payload calls it ``entity``
whatever the resource was, and a *delete* payload carries no entity at all —
only ``entityId``. Selecting the wrong one is a GraphQL error, not a silent
empty field.

API Reference: https://linear.app/developers/graphql
"""

from __future__ import annotations

__all__ = [
    # workspace
    "VIEWER",
    "ORGANIZATION",
    "TEAMS",
    "TEAM",
    "USERS",
    "USER",
    "WORKFLOW_STATES",
    "WORKFLOW_STATE",
    "WORKFLOW_STATE_CREATE",
    "WORKFLOW_STATE_UPDATE",
    "WORKFLOW_STATE_ARCHIVE",
    "TEAM_MEMBERSHIPS",
    "TEAM_MEMBERSHIP",
    "TEAM_MEMBERSHIP_CREATE",
    "TEAM_MEMBERSHIP_UPDATE",
    "TEAM_MEMBERSHIP_DELETE",
    # issues
    "ISSUES",
    "ISSUE",
    "ISSUE_CREATE",
    "ISSUE_UPDATE",
    "ISSUE_DELETE",
    "ISSUE_ARCHIVE",
    "ISSUE_UNARCHIVE",
    "ISSUE_ADD_LABEL",
    "ISSUE_REMOVE_LABEL",
    "ISSUE_SUBSCRIBE",
    "ISSUE_UNSUBSCRIBE",
    "ISSUE_BATCH_UPDATE",
    "ISSUE_RELATIONS",
    "ISSUE_RELATION",
    "ISSUE_RELATION_CREATE",
    "ISSUE_RELATION_UPDATE",
    "ISSUE_RELATION_DELETE",
    # comments
    "COMMENTS",
    "COMMENT",
    "COMMENT_CREATE",
    "COMMENT_UPDATE",
    "COMMENT_DELETE",
    "COMMENT_RESOLVE",
    "COMMENT_UNRESOLVE",
    "REACTION_CREATE",
    "REACTION_DELETE",
    # labels
    "ISSUE_LABELS",
    "ISSUE_LABEL",
    "ISSUE_LABEL_CREATE",
    "ISSUE_LABEL_UPDATE",
    "ISSUE_LABEL_DELETE",
    "PROJECT_LABELS",
    # projects
    "PROJECTS",
    "PROJECT",
    "PROJECT_CREATE",
    "PROJECT_UPDATE",
    "PROJECT_DELETE",
    "PROJECT_UNARCHIVE",
    "PROJECT_ADD_LABEL",
    "PROJECT_REMOVE_LABEL",
    "PROJECT_STATUSES",
    "PROJECT_MILESTONES",
    "PROJECT_MILESTONE",
    "PROJECT_MILESTONE_CREATE",
    "PROJECT_MILESTONE_UPDATE",
    "PROJECT_MILESTONE_DELETE",
    "PROJECT_UPDATES",
    "PROJECT_UPDATE_GET",
    "PROJECT_UPDATE_CREATE",
    "PROJECT_UPDATE_UPDATE",
    "PROJECT_UPDATE_ARCHIVE",
    # cycles
    "CYCLES",
    "CYCLE",
    "CYCLE_UPDATE",
    "CYCLE_ARCHIVE",
    "CYCLE_START_UPCOMING_CYCLE_TODAY",
    # initiatives
    "INITIATIVES",
    "INITIATIVE",
    "INITIATIVE_CREATE",
    "INITIATIVE_UPDATE",
    "INITIATIVE_DELETE",
    "INITIATIVE_ARCHIVE",
    "INITIATIVE_UNARCHIVE",
    "INITIATIVE_TO_PROJECT_CREATE",
    "INITIATIVE_TO_PROJECT_DELETE",
    "INITIATIVE_UPDATES",
    "INITIATIVE_UPDATE_CREATE",
    # documents
    "DOCUMENTS",
    "DOCUMENT",
    "DOCUMENT_CREATE",
    "DOCUMENT_UPDATE",
    "DOCUMENT_DELETE",
    "DOCUMENT_UNARCHIVE",
    # attachments
    "ATTACHMENTS",
    "ATTACHMENT",
    "ATTACHMENTS_FOR_URL",
    "ATTACHMENT_CREATE",
    "ATTACHMENT_UPDATE",
    "ATTACHMENT_DELETE",
    # customers
    "CUSTOMERS",
    "CUSTOMER",
    "CUSTOMER_CREATE",
    "CUSTOMER_UPDATE",
    "CUSTOMER_DELETE",
    "CUSTOMER_NEEDS",
    "CUSTOMER_NEED_CREATE",
    "CUSTOMER_NEED_UPDATE",
    "CUSTOMER_NEED_DELETE",
    "CUSTOMER_STATUSES",
    "CUSTOMER_TIERS",
    # inbox
    "NOTIFICATIONS",
    "NOTIFICATION",
    "NOTIFICATION_UPDATE",
    "NOTIFICATION_ARCHIVE",
    "NOTIFICATION_UNARCHIVE",
    "NOTIFICATION_MARK_READ_ALL",
    "FAVORITES",
    "FAVORITE_CREATE",
    "FAVORITE_UPDATE",
    "FAVORITE_DELETE",
    "CUSTOM_VIEWS",
    "CUSTOM_VIEW",
    "CUSTOM_VIEW_CREATE",
    "CUSTOM_VIEW_DELETE",
    # search
    "SEARCH_ISSUES",
    "SEARCH_PROJECTS",
    "SEARCH_DOCUMENTS",
    # webhooks
    "WEBHOOKS",
    "WEBHOOK",
    "WEBHOOK_CREATE",
    "WEBHOOK_UPDATE",
    "WEBHOOK_DELETE",
]

# Relay's page marker, on every connection this pack pages through.
_PAGE_INFO = "pageInfo { hasNextPage endCursor }"

# ---------------------------------------------------------------------------
# shared selection sets
# ---------------------------------------------------------------------------

# The fields worth having on every issue we return. Kept in one place so the
# read, list and mutation documents cannot drift apart.
_ISSUE_FIELDS = """
    id
    identifier
    title
    description
    priority
    priorityLabel
    url
    branchName
    createdAt
    updatedAt
    dueDate
    estimate
    state { id name type }
    assignee { id name email }
    team { id key name }
    project { id name }
    cycle { id number name }
    parent { id identifier title }
    labels { nodes { id name } }
"""

_COMMENT_FIELDS = """
    id
    body
    createdAt
    updatedAt
    editedAt
    url
    resolvedAt
    user { id name email }
"""

_LABEL_FIELDS = """
    id
    name
    color
    description
    isGroup
"""

_PROJECT_FIELDS = """
    id
    name
    description
    url
    progress
    priority
    startDate
    targetDate
    status { id name type }
    lead { id name email }
    teams { nodes { id key } }
"""

_MILESTONE_FIELDS = """
    id
    name
    description
    targetDate
    sortOrder
    createdAt
    updatedAt
"""

_PROJECT_UPDATE_FIELDS = """
    id
    body
    health
    url
    createdAt
    updatedAt
    user { id name email }
    project { id name }
"""

_CYCLE_FIELDS = """
    id
    number
    name
    description
    startsAt
    endsAt
    completedAt
    progress
    team { id key name }
"""

_INITIATIVE_FIELDS = """
    id
    name
    description
    status
    url
    targetDate
    createdAt
    updatedAt
    owner { id name email }
"""

_DOCUMENT_FIELDS = """
    id
    title
    content
    url
    icon
    color
    createdAt
    updatedAt
    creator { id name email }
    project { id name }
    initiative { id name }
"""

_ATTACHMENT_FIELDS = """
    id
    title
    subtitle
    url
    sourceType
    createdAt
    updatedAt
    creator { id name email }
"""

_CUSTOMER_FIELDS = """
    id
    name
    domains
    externalIds
    revenue
    size
    logoUrl
    createdAt
    updatedAt
    owner { id name email }
    status { id name }
    tier { id name }
"""

_CUSTOMER_NEED_FIELDS = """
    id
    body
    priority
    createdAt
    updatedAt
    customer { id name }
    issue { id identifier title }
"""

_NOTIFICATION_FIELDS = """
    id
    type
    readAt
    emailedAt
    snoozedUntilAt
    createdAt
    actor { id name email }
"""

_FAVORITE_FIELDS = """
    id
    type
    folderName
    sortOrder
    createdAt
    issue { id identifier title }
    project { id name }
    document { id title }
    customView { id name }
"""

_CUSTOM_VIEW_FIELDS = """
    id
    name
    description
    icon
    color
    shared
    filterData
    createdAt
    updatedAt
    owner { id name email }
    team { id key name }
"""

_WEBHOOK_FIELDS = """
    id
    label
    url
    enabled
    resourceTypes
    allPublicTeams
    createdAt
    updatedAt
    team { id key name }
"""

_TEAM_FIELDS = """
    id
    key
    name
    description
    visibility
    icon
    color
    cyclesEnabled
    triageEnabled
"""

_USER_FIELDS = """
    id
    name
    displayName
    email
    avatarUrl
    active
    admin
    isMe
    createdAt
"""

_WORKFLOW_STATE_FIELDS = """
    id
    name
    type
    color
    description
    position
    team { id key }
"""

_MEMBERSHIP_FIELDS = """
    id
    owner
    sortOrder
    createdAt
    user { id name email }
    team { id key name }
"""

# A delete answers with the id it removed and nothing else — there is no entity
# left to select.
_DELETED = "success entityId"

# ---------------------------------------------------------------------------
# workspace
# ---------------------------------------------------------------------------

VIEWER = f"""
query Viewer {{
  viewer {{{_USER_FIELDS}}}
}}
"""

ORGANIZATION = """
query Organization {
  organization {
    id
    name
    urlKey
    logoUrl
    userCount
    createdAt
    releaseChannel
  }
}
"""

TEAMS = f"""
query Teams($first: Int, $after: String, $filter: TeamFilter, $includeArchived: Boolean, $orderBy: PaginationOrderBy) {{
  teams(first: $first, after: $after, filter: $filter, includeArchived: $includeArchived, orderBy: $orderBy) {{
    nodes {{{_TEAM_FIELDS}}}
    {_PAGE_INFO}
  }}
}}
"""

TEAM = f"""
query Team($id: String!) {{
  team(id: $id) {{
    {_TEAM_FIELDS}
    states {{ nodes {{ id name type }} }}
    activeCycle {{ id number name }}
  }}
}}
"""

USERS = f"""
query Users($first: Int, $after: String, $filter: UserFilter, $includeArchived: Boolean, $includeDisabled: Boolean, $orderBy: PaginationOrderBy) {{
  users(first: $first, after: $after, filter: $filter, includeArchived: $includeArchived, includeDisabled: $includeDisabled, orderBy: $orderBy) {{
    nodes {{{_USER_FIELDS}}}
    {_PAGE_INFO}
  }}
}}
"""

USER = f"""
query User($id: String!) {{
  user(id: $id) {{{_USER_FIELDS}}}
}}
"""

WORKFLOW_STATES = f"""
query WorkflowStates($first: Int, $after: String, $filter: WorkflowStateFilter, $includeArchived: Boolean, $orderBy: PaginationOrderBy) {{
  workflowStates(first: $first, after: $after, filter: $filter, includeArchived: $includeArchived, orderBy: $orderBy) {{
    nodes {{{_WORKFLOW_STATE_FIELDS}}}
    {_PAGE_INFO}
  }}
}}
"""

WORKFLOW_STATE = f"""
query WorkflowState($id: String!) {{
  workflowState(id: $id) {{{_WORKFLOW_STATE_FIELDS}}}
}}
"""

WORKFLOW_STATE_CREATE = f"""
mutation WorkflowStateCreate($input: WorkflowStateCreateInput!) {{
  workflowStateCreate(input: $input) {{
    success
    workflowState {{{_WORKFLOW_STATE_FIELDS}}}
  }}
}}
"""

WORKFLOW_STATE_UPDATE = f"""
mutation WorkflowStateUpdate($id: String!, $input: WorkflowStateUpdateInput!) {{
  workflowStateUpdate(id: $id, input: $input) {{
    success
    workflowState {{{_WORKFLOW_STATE_FIELDS}}}
  }}
}}
"""

WORKFLOW_STATE_ARCHIVE = f"""
mutation WorkflowStateArchive($id: String!) {{
  workflowStateArchive(id: $id) {{
    success
    entity {{{_WORKFLOW_STATE_FIELDS}}}
  }}
}}
"""

TEAM_MEMBERSHIPS = f"""
query TeamMemberships($first: Int, $after: String, $includeArchived: Boolean, $orderBy: PaginationOrderBy) {{
  teamMemberships(first: $first, after: $after, includeArchived: $includeArchived, orderBy: $orderBy) {{
    nodes {{{_MEMBERSHIP_FIELDS}}}
    {_PAGE_INFO}
  }}
}}
"""

TEAM_MEMBERSHIP = f"""
query TeamMembership($id: String!) {{
  teamMembership(id: $id) {{{_MEMBERSHIP_FIELDS}}}
}}
"""

TEAM_MEMBERSHIP_CREATE = f"""
mutation TeamMembershipCreate($input: TeamMembershipCreateInput!) {{
  teamMembershipCreate(input: $input) {{
    success
    teamMembership {{{_MEMBERSHIP_FIELDS}}}
  }}
}}
"""

TEAM_MEMBERSHIP_UPDATE = f"""
mutation TeamMembershipUpdate($id: String!, $input: TeamMembershipUpdateInput!) {{
  teamMembershipUpdate(id: $id, input: $input) {{
    success
    teamMembership {{{_MEMBERSHIP_FIELDS}}}
  }}
}}
"""

TEAM_MEMBERSHIP_DELETE = f"""
mutation TeamMembershipDelete($id: String!) {{
  teamMembershipDelete(id: $id) {{ {_DELETED} }}
}}
"""

# ---------------------------------------------------------------------------
# issues
# ---------------------------------------------------------------------------

# The list path asks for less than the get path, which is the GraphQL form of the
# cap `gcalendar.events_list` puts on `description`. Calendar's REST endpoint
# returns the whole event whether or not the caller wants it, so the only place
# to shed weight is the response handler. Here the weight can simply not be
# requested.
#
# `description` is the field that matters: a real issue description is a
# paragraph or a pasted stack trace, it is carried for every node in a page of
# 250, and nothing about picking an issue out of a list needs it. `branchName`,
# `estimate`, `cycle` and `parent` go for the same reason - they answer questions
# about one issue, and the tool for one issue is `issue_get`, which keeps the
# full selection.
_ISSUE_LIST_FIELDS = """
    id
    identifier
    title
    priority
    priorityLabel
    url
    createdAt
    updatedAt
    dueDate
    state { id name type }
    assignee { id name email }
    team { id key name }
    project { id name }
    labels { nodes { id name } }
"""

ISSUES = f"""
query Issues($first: Int, $after: String, $filter: IssueFilter, $orderBy: PaginationOrderBy, $includeArchived: Boolean) {{
  issues(first: $first, after: $after, filter: $filter, orderBy: $orderBy, includeArchived: $includeArchived) {{
    nodes {{{_ISSUE_LIST_FIELDS}}}
    {_PAGE_INFO}
  }}
}}
"""

ISSUE = f"""
query Issue($id: String!) {{
  issue(id: $id) {{
    {_ISSUE_FIELDS}
    comments {{ nodes {{ id body createdAt user {{ name }} }} }}
    children {{ nodes {{ id identifier title state {{ name type }} }} }}
    relations {{ nodes {{ id type relatedIssue {{ id identifier title }} }} }}
    attachments {{ nodes {{ id title url sourceType }} }}
  }}
}}
"""

ISSUE_CREATE = f"""
mutation IssueCreate($input: IssueCreateInput!) {{
  issueCreate(input: $input) {{
    success
    issue {{{_ISSUE_FIELDS}}}
  }}
}}
"""

ISSUE_UPDATE = f"""
mutation IssueUpdate($id: String!, $input: IssueUpdateInput!) {{
  issueUpdate(id: $id, input: $input) {{
    success
    issue {{{_ISSUE_FIELDS}}}
  }}
}}
"""

ISSUE_BATCH_UPDATE = f"""
mutation IssueBatchUpdate($ids: [UUID!]!, $input: IssueUpdateInput!) {{
  issueBatchUpdate(ids: $ids, input: $input) {{
    success
    issues {{{_ISSUE_FIELDS}}}
  }}
}}
"""

# Delete and archive both answer with an archive payload, whose entity is named
# `entity` rather than `issue`.
ISSUE_DELETE = f"""
mutation IssueDelete($id: String!, $permanentlyDelete: Boolean) {{
  issueDelete(id: $id, permanentlyDelete: $permanentlyDelete) {{
    success
    entity {{{_ISSUE_FIELDS}}}
  }}
}}
"""

ISSUE_ARCHIVE = f"""
mutation IssueArchive($id: String!, $trash: Boolean) {{
  issueArchive(id: $id, trash: $trash) {{
    success
    entity {{{_ISSUE_FIELDS}}}
  }}
}}
"""

ISSUE_UNARCHIVE = f"""
mutation IssueUnarchive($id: String!) {{
  issueUnarchive(id: $id) {{
    success
    entity {{{_ISSUE_FIELDS}}}
  }}
}}
"""

ISSUE_ADD_LABEL = f"""
mutation IssueAddLabel($id: String!, $labelId: String!) {{
  issueAddLabel(id: $id, labelId: $labelId) {{
    success
    issue {{{_ISSUE_FIELDS}}}
  }}
}}
"""

ISSUE_REMOVE_LABEL = f"""
mutation IssueRemoveLabel($id: String!, $labelId: String!) {{
  issueRemoveLabel(id: $id, labelId: $labelId) {{
    success
    issue {{{_ISSUE_FIELDS}}}
  }}
}}
"""

ISSUE_SUBSCRIBE = f"""
mutation IssueSubscribe($id: String!, $userId: String, $userEmail: String) {{
  issueSubscribe(id: $id, userId: $userId, userEmail: $userEmail) {{
    success
    issue {{{_ISSUE_FIELDS}}}
  }}
}}
"""

ISSUE_UNSUBSCRIBE = f"""
mutation IssueUnsubscribe($id: String!, $userId: String, $userEmail: String) {{
  issueUnsubscribe(id: $id, userId: $userId, userEmail: $userEmail) {{
    success
    issue {{{_ISSUE_FIELDS}}}
  }}
}}
"""

_RELATION_FIELDS = """
    id
    type
    createdAt
    issue { id identifier title }
    relatedIssue { id identifier title }
"""

ISSUE_RELATIONS = f"""
query IssueRelations($first: Int, $after: String, $includeArchived: Boolean, $orderBy: PaginationOrderBy) {{
  issueRelations(first: $first, after: $after, includeArchived: $includeArchived, orderBy: $orderBy) {{
    nodes {{{_RELATION_FIELDS}}}
    {_PAGE_INFO}
  }}
}}
"""

ISSUE_RELATION = f"""
query IssueRelation($id: String!) {{
  issueRelation(id: $id) {{{_RELATION_FIELDS}}}
}}
"""

ISSUE_RELATION_CREATE = f"""
mutation IssueRelationCreate($input: IssueRelationCreateInput!) {{
  issueRelationCreate(input: $input) {{
    success
    issueRelation {{{_RELATION_FIELDS}}}
  }}
}}
"""

ISSUE_RELATION_UPDATE = f"""
mutation IssueRelationUpdate($id: String!, $input: IssueRelationUpdateInput!) {{
  issueRelationUpdate(id: $id, input: $input) {{
    success
    issueRelation {{{_RELATION_FIELDS}}}
  }}
}}
"""

ISSUE_RELATION_DELETE = f"""
mutation IssueRelationDelete($id: String!) {{
  issueRelationDelete(id: $id) {{ {_DELETED} }}
}}
"""

# ---------------------------------------------------------------------------
# comments and reactions
# ---------------------------------------------------------------------------

COMMENTS = f"""
query Comments($filter: CommentFilter, $first: Int, $after: String, $includeArchived: Boolean) {{
  comments(filter: $filter, first: $first, after: $after, includeArchived: $includeArchived) {{
    nodes {{{_COMMENT_FIELDS}}}
    {_PAGE_INFO}
  }}
}}
"""

COMMENT = f"""
query Comment($id: String, $hash: String) {{
  comment(id: $id, hash: $hash) {{
    {_COMMENT_FIELDS}
    issue {{ id identifier title }}
    children {{ nodes {{ id body createdAt user {{ name }} }} }}
  }}
}}
"""

COMMENT_CREATE = f"""
mutation CommentCreate($input: CommentCreateInput!) {{
  commentCreate(input: $input) {{
    success
    comment {{{_COMMENT_FIELDS}}}
  }}
}}
"""

COMMENT_UPDATE = f"""
mutation CommentUpdate($id: String!, $input: CommentUpdateInput!) {{
  commentUpdate(id: $id, input: $input) {{
    success
    comment {{{_COMMENT_FIELDS}}}
  }}
}}
"""

COMMENT_DELETE = f"""
mutation CommentDelete($id: String!) {{
  commentDelete(id: $id) {{ {_DELETED} }}
}}
"""

COMMENT_RESOLVE = f"""
mutation CommentResolve($id: String!, $resolvingCommentId: String) {{
  commentResolve(id: $id, resolvingCommentId: $resolvingCommentId) {{
    success
    comment {{{_COMMENT_FIELDS}}}
  }}
}}
"""

COMMENT_UNRESOLVE = f"""
mutation CommentUnresolve($id: String!) {{
  commentUnresolve(id: $id) {{
    success
    comment {{{_COMMENT_FIELDS}}}
  }}
}}
"""

REACTION_CREATE = """
mutation ReactionCreate($input: ReactionCreateInput!) {
  reactionCreate(input: $input) {
    success
    reaction { id emoji createdAt user { id name } }
  }
}
"""

REACTION_DELETE = f"""
mutation ReactionDelete($id: String!) {{
  reactionDelete(id: $id) {{ {_DELETED} }}
}}
"""

# ---------------------------------------------------------------------------
# labels
# ---------------------------------------------------------------------------

ISSUE_LABELS = f"""
query IssueLabels($filter: IssueLabelFilter, $first: Int, $after: String, $includeArchived: Boolean, $orderBy: PaginationOrderBy) {{
  issueLabels(filter: $filter, first: $first, after: $after, includeArchived: $includeArchived, orderBy: $orderBy) {{
    nodes {{{_LABEL_FIELDS}}}
    {_PAGE_INFO}
  }}
}}
"""

ISSUE_LABEL = f"""
query IssueLabel($id: String!) {{
  issueLabel(id: $id) {{
    {_LABEL_FIELDS}
    team {{ id key name }}
  }}
}}
"""

ISSUE_LABEL_CREATE = f"""
mutation IssueLabelCreate($input: IssueLabelCreateInput!) {{
  issueLabelCreate(input: $input) {{
    success
    issueLabel {{{_LABEL_FIELDS}}}
  }}
}}
"""

ISSUE_LABEL_UPDATE = f"""
mutation IssueLabelUpdate($id: String!, $input: IssueLabelUpdateInput!) {{
  issueLabelUpdate(id: $id, input: $input) {{
    success
    issueLabel {{{_LABEL_FIELDS}}}
  }}
}}
"""

ISSUE_LABEL_DELETE = f"""
mutation IssueLabelDelete($id: String!) {{
  issueLabelDelete(id: $id) {{ {_DELETED} }}
}}
"""

PROJECT_LABELS = f"""
query ProjectLabels($first: Int, $after: String, $includeArchived: Boolean, $orderBy: PaginationOrderBy) {{
  projectLabels(first: $first, after: $after, includeArchived: $includeArchived, orderBy: $orderBy) {{
    nodes {{{_LABEL_FIELDS}}}
    {_PAGE_INFO}
  }}
}}
"""

# ---------------------------------------------------------------------------
# projects
# ---------------------------------------------------------------------------

PROJECTS = f"""
query Projects($first: Int, $after: String, $filter: ProjectFilter, $includeArchived: Boolean, $orderBy: PaginationOrderBy) {{
  projects(first: $first, after: $after, filter: $filter, includeArchived: $includeArchived, orderBy: $orderBy) {{
    nodes {{{_PROJECT_FIELDS}}}
    {_PAGE_INFO}
  }}
}}
"""

PROJECT = f"""
query Project($id: String!) {{
  project(id: $id) {{
    {_PROJECT_FIELDS}
    content
    projectMilestones {{ nodes {{ id name targetDate }} }}
    members {{ nodes {{ id name email }} }}
  }}
}}
"""

PROJECT_CREATE = f"""
mutation ProjectCreate($input: ProjectCreateInput!) {{
  projectCreate(input: $input) {{
    success
    project {{{_PROJECT_FIELDS}}}
  }}
}}
"""

PROJECT_UPDATE = f"""
mutation ProjectUpdate($id: String!, $input: ProjectUpdateInput!) {{
  projectUpdate(id: $id, input: $input) {{
    success
    project {{{_PROJECT_FIELDS}}}
  }}
}}
"""

# projectDelete trashes rather than erasing, so it answers with an *archive*
# payload — `entity`, not the `entityId` a true delete returns.
PROJECT_DELETE = f"""
mutation ProjectDelete($id: String!) {{
  projectDelete(id: $id) {{
    success
    entity {{{_PROJECT_FIELDS}}}
  }}
}}
"""

PROJECT_UNARCHIVE = f"""
mutation ProjectUnarchive($id: String!) {{
  projectUnarchive(id: $id) {{
    success
    entity {{{_PROJECT_FIELDS}}}
  }}
}}
"""

PROJECT_ADD_LABEL = f"""
mutation ProjectAddLabel($id: String!, $labelId: String!) {{
  projectAddLabel(id: $id, labelId: $labelId) {{
    success
    project {{{_PROJECT_FIELDS}}}
  }}
}}
"""

PROJECT_REMOVE_LABEL = f"""
mutation ProjectRemoveLabel($id: String!, $labelId: String!) {{
  projectRemoveLabel(id: $id, labelId: $labelId) {{
    success
    project {{{_PROJECT_FIELDS}}}
  }}
}}
"""

PROJECT_STATUSES = f"""
query ProjectStatuses($first: Int, $after: String) {{
  projectStatuses(first: $first, after: $after) {{
    nodes {{ id name type color description position }}
    {_PAGE_INFO}
  }}
}}
"""

PROJECT_MILESTONES = f"""
query ProjectMilestones($first: Int, $after: String, $filter: ProjectMilestoneFilter, $includeArchived: Boolean, $orderBy: PaginationOrderBy) {{
  projectMilestones(first: $first, after: $after, filter: $filter, includeArchived: $includeArchived, orderBy: $orderBy) {{
    nodes {{{_MILESTONE_FIELDS}}}
    {_PAGE_INFO}
  }}
}}
"""

PROJECT_MILESTONE = f"""
query ProjectMilestone($id: String!) {{
  projectMilestone(id: $id) {{
    {_MILESTONE_FIELDS}
    project {{ id name }}
  }}
}}
"""

PROJECT_MILESTONE_CREATE = f"""
mutation ProjectMilestoneCreate($input: ProjectMilestoneCreateInput!) {{
  projectMilestoneCreate(input: $input) {{
    success
    projectMilestone {{{_MILESTONE_FIELDS}}}
  }}
}}
"""

PROJECT_MILESTONE_UPDATE = f"""
mutation ProjectMilestoneUpdate($id: String!, $input: ProjectMilestoneUpdateInput!) {{
  projectMilestoneUpdate(id: $id, input: $input) {{
    success
    projectMilestone {{{_MILESTONE_FIELDS}}}
  }}
}}
"""

PROJECT_MILESTONE_DELETE = f"""
mutation ProjectMilestoneDelete($id: String!) {{
  projectMilestoneDelete(id: $id) {{ {_DELETED} }}
}}
"""

PROJECT_UPDATES = f"""
query ProjectUpdates($first: Int, $after: String, $filter: ProjectUpdateFilter, $includeArchived: Boolean, $orderBy: PaginationOrderBy) {{
  projectUpdates(first: $first, after: $after, filter: $filter, includeArchived: $includeArchived, orderBy: $orderBy) {{
    nodes {{{_PROJECT_UPDATE_FIELDS}}}
    {_PAGE_INFO}
  }}
}}
"""

PROJECT_UPDATE_GET = f"""
query ProjectUpdateGet($id: String!) {{
  projectUpdate(id: $id) {{{_PROJECT_UPDATE_FIELDS}}}
}}
"""

PROJECT_UPDATE_CREATE = f"""
mutation ProjectUpdateCreate($input: ProjectUpdateCreateInput!) {{
  projectUpdateCreate(input: $input) {{
    success
    projectUpdate {{{_PROJECT_UPDATE_FIELDS}}}
  }}
}}
"""

PROJECT_UPDATE_UPDATE = f"""
mutation ProjectUpdateUpdate($id: String!, $input: ProjectUpdateUpdateInput!) {{
  projectUpdateUpdate(id: $id, input: $input) {{
    success
    projectUpdate {{{_PROJECT_UPDATE_FIELDS}}}
  }}
}}
"""

PROJECT_UPDATE_ARCHIVE = f"""
mutation ProjectUpdateArchive($id: String!) {{
  projectUpdateArchive(id: $id) {{
    success
    entity {{{_PROJECT_UPDATE_FIELDS}}}
  }}
}}
"""

# ---------------------------------------------------------------------------
# cycles
# ---------------------------------------------------------------------------

CYCLES = f"""
query Cycles($first: Int, $after: String, $filter: CycleFilter, $includeArchived: Boolean, $orderBy: PaginationOrderBy) {{
  cycles(first: $first, after: $after, filter: $filter, includeArchived: $includeArchived, orderBy: $orderBy) {{
    nodes {{{_CYCLE_FIELDS}}}
    {_PAGE_INFO}
  }}
}}
"""

CYCLE = f"""
query Cycle($id: String!) {{
  cycle(id: $id) {{
    {_CYCLE_FIELDS}
    issues {{ nodes {{ id identifier title state {{ name type }} }} }}
  }}
}}
"""

CYCLE_UPDATE = f"""
mutation CycleUpdate($id: String!, $input: CycleUpdateInput!) {{
  cycleUpdate(id: $id, input: $input) {{
    success
    cycle {{{_CYCLE_FIELDS}}}
  }}
}}
"""

CYCLE_ARCHIVE = f"""
mutation CycleArchive($id: String!) {{
  cycleArchive(id: $id) {{
    success
    entity {{{_CYCLE_FIELDS}}}
  }}
}}
"""

CYCLE_START_UPCOMING_CYCLE_TODAY = f"""
mutation CycleStartUpcomingCycleToday($id: String!) {{
  cycleStartUpcomingCycleToday(id: $id) {{
    success
    cycle {{{_CYCLE_FIELDS}}}
  }}
}}
"""

# ---------------------------------------------------------------------------
# initiatives
# ---------------------------------------------------------------------------

INITIATIVES = f"""
query Initiatives($first: Int, $after: String, $filter: InitiativeFilter, $includeArchived: Boolean, $orderBy: PaginationOrderBy) {{
  initiatives(first: $first, after: $after, filter: $filter, includeArchived: $includeArchived, orderBy: $orderBy) {{
    nodes {{{_INITIATIVE_FIELDS}}}
    {_PAGE_INFO}
  }}
}}
"""

INITIATIVE = f"""
query Initiative($id: String!) {{
  initiative(id: $id) {{
    {_INITIATIVE_FIELDS}
    content
    projects {{ nodes {{ id name status {{ name type }} }} }}
    links {{ nodes {{ id label url }} }}
  }}
}}
"""

INITIATIVE_CREATE = f"""
mutation InitiativeCreate($input: InitiativeCreateInput!) {{
  initiativeCreate(input: $input) {{
    success
    initiative {{{_INITIATIVE_FIELDS}}}
  }}
}}
"""

INITIATIVE_UPDATE = f"""
mutation InitiativeUpdate($id: String!, $input: InitiativeUpdateInput!) {{
  initiativeUpdate(id: $id, input: $input) {{
    success
    initiative {{{_INITIATIVE_FIELDS}}}
  }}
}}
"""

INITIATIVE_DELETE = f"""
mutation InitiativeDelete($id: String!) {{
  initiativeDelete(id: $id) {{ {_DELETED} }}
}}
"""

INITIATIVE_ARCHIVE = f"""
mutation InitiativeArchive($id: String!) {{
  initiativeArchive(id: $id) {{
    success
    entity {{{_INITIATIVE_FIELDS}}}
  }}
}}
"""

INITIATIVE_UNARCHIVE = f"""
mutation InitiativeUnarchive($id: String!) {{
  initiativeUnarchive(id: $id) {{
    success
    entity {{{_INITIATIVE_FIELDS}}}
  }}
}}
"""

INITIATIVE_TO_PROJECT_CREATE = """
mutation InitiativeToProjectCreate($input: InitiativeToProjectCreateInput!) {
  initiativeToProjectCreate(input: $input) {
    success
    initiativeToProject {
      id
      sortOrder
      initiative { id name }
      project { id name }
    }
  }
}
"""

INITIATIVE_TO_PROJECT_DELETE = f"""
mutation InitiativeToProjectDelete($id: String!) {{
  initiativeToProjectDelete(id: $id) {{ {_DELETED} }}
}}
"""

_INITIATIVE_UPDATE_POST_FIELDS = """
    id
    body
    health
    url
    createdAt
    updatedAt
    user { id name email }
    initiative { id name }
"""

INITIATIVE_UPDATES = f"""
query InitiativeUpdates($first: Int, $after: String, $includeArchived: Boolean, $orderBy: PaginationOrderBy) {{
  initiativeUpdates(first: $first, after: $after, includeArchived: $includeArchived, orderBy: $orderBy) {{
    nodes {{{_INITIATIVE_UPDATE_POST_FIELDS}}}
    {_PAGE_INFO}
  }}
}}
"""

INITIATIVE_UPDATE_CREATE = f"""
mutation InitiativeUpdateCreate($input: InitiativeUpdateCreateInput!) {{
  initiativeUpdateCreate(input: $input) {{
    success
    initiativeUpdate {{{_INITIATIVE_UPDATE_POST_FIELDS}}}
  }}
}}
"""

# ---------------------------------------------------------------------------
# documents
# ---------------------------------------------------------------------------

DOCUMENTS = f"""
query Documents($first: Int, $after: String, $filter: DocumentFilter, $includeArchived: Boolean, $orderBy: PaginationOrderBy) {{
  documents(first: $first, after: $after, filter: $filter, includeArchived: $includeArchived, orderBy: $orderBy) {{
    nodes {{{_DOCUMENT_FIELDS}}}
    {_PAGE_INFO}
  }}
}}
"""

DOCUMENT = f"""
query Document($id: String!) {{
  document(id: $id) {{{_DOCUMENT_FIELDS}}}
}}
"""

DOCUMENT_CREATE = f"""
mutation DocumentCreate($input: DocumentCreateInput!) {{
  documentCreate(input: $input) {{
    success
    document {{{_DOCUMENT_FIELDS}}}
  }}
}}
"""

DOCUMENT_UPDATE = f"""
mutation DocumentUpdate($id: String!, $input: DocumentUpdateInput!) {{
  documentUpdate(id: $id, input: $input) {{
    success
    document {{{_DOCUMENT_FIELDS}}}
  }}
}}
"""

# Like projectDelete, this trashes and answers with an archive payload.
DOCUMENT_DELETE = f"""
mutation DocumentDelete($id: String!) {{
  documentDelete(id: $id) {{
    success
    entity {{{_DOCUMENT_FIELDS}}}
  }}
}}
"""

DOCUMENT_UNARCHIVE = f"""
mutation DocumentUnarchive($id: String!) {{
  documentUnarchive(id: $id) {{
    success
    entity {{{_DOCUMENT_FIELDS}}}
  }}
}}
"""

# ---------------------------------------------------------------------------
# attachments
# ---------------------------------------------------------------------------

ATTACHMENTS = f"""
query Attachments($first: Int, $after: String, $filter: AttachmentFilter, $includeArchived: Boolean, $orderBy: PaginationOrderBy) {{
  attachments(first: $first, after: $after, filter: $filter, includeArchived: $includeArchived, orderBy: $orderBy) {{
    nodes {{{_ATTACHMENT_FIELDS}}}
    {_PAGE_INFO}
  }}
}}
"""

ATTACHMENT = f"""
query Attachment($id: String!) {{
  attachment(id: $id) {{
    {_ATTACHMENT_FIELDS}
    issue {{ id identifier title }}
  }}
}}
"""

ATTACHMENTS_FOR_URL = f"""
query AttachmentsForURL($url: String!, $first: Int, $after: String) {{
  attachmentsForURL(url: $url, first: $first, after: $after) {{
    nodes {{
      {_ATTACHMENT_FIELDS}
      issue {{ id identifier title }}
    }}
    {_PAGE_INFO}
  }}
}}
"""

ATTACHMENT_CREATE = f"""
mutation AttachmentCreate($input: AttachmentCreateInput!) {{
  attachmentCreate(input: $input) {{
    success
    attachment {{{_ATTACHMENT_FIELDS}}}
  }}
}}
"""

ATTACHMENT_UPDATE = f"""
mutation AttachmentUpdate($id: String!, $input: AttachmentUpdateInput!) {{
  attachmentUpdate(id: $id, input: $input) {{
    success
    attachment {{{_ATTACHMENT_FIELDS}}}
  }}
}}
"""

ATTACHMENT_DELETE = f"""
mutation AttachmentDelete($id: String!) {{
  attachmentDelete(id: $id) {{ {_DELETED} }}
}}
"""

# ---------------------------------------------------------------------------
# customers
# ---------------------------------------------------------------------------

CUSTOMERS = f"""
query Customers($first: Int, $after: String, $filter: CustomerFilter, $includeArchived: Boolean, $orderBy: PaginationOrderBy) {{
  customers(first: $first, after: $after, filter: $filter, includeArchived: $includeArchived, orderBy: $orderBy) {{
    nodes {{{_CUSTOMER_FIELDS}}}
    {_PAGE_INFO}
  }}
}}
"""

CUSTOMER = f"""
query Customer($id: String!) {{
  customer(id: $id) {{{_CUSTOMER_FIELDS}}}
}}
"""

CUSTOMER_CREATE = f"""
mutation CustomerCreate($input: CustomerCreateInput!) {{
  customerCreate(input: $input) {{
    success
    customer {{{_CUSTOMER_FIELDS}}}
  }}
}}
"""

CUSTOMER_UPDATE = f"""
mutation CustomerUpdate($id: String!, $input: CustomerUpdateInput!) {{
  customerUpdate(id: $id, input: $input) {{
    success
    customer {{{_CUSTOMER_FIELDS}}}
  }}
}}
"""

CUSTOMER_DELETE = f"""
mutation CustomerDelete($id: String!) {{
  customerDelete(id: $id) {{ {_DELETED} }}
}}
"""

CUSTOMER_NEEDS = f"""
query CustomerNeeds($first: Int, $after: String, $filter: CustomerNeedFilter, $includeArchived: Boolean, $orderBy: PaginationOrderBy) {{
  customerNeeds(first: $first, after: $after, filter: $filter, includeArchived: $includeArchived, orderBy: $orderBy) {{
    nodes {{{_CUSTOMER_NEED_FIELDS}}}
    {_PAGE_INFO}
  }}
}}
"""

# The one mutation in this pack whose payload carries no entity: Linear answers
# `{success}` alone. The envelope still reads it, so a refusal still raises.
CUSTOMER_NEED_CREATE = """
mutation CustomerNeedCreate($input: CustomerNeedCreateInput!) {
  customerNeedCreate(input: $input) {
    success
  }
}
"""

CUSTOMER_NEED_UPDATE = f"""
mutation CustomerNeedUpdate($id: String!, $input: CustomerNeedUpdateInput!) {{
  customerNeedUpdate(id: $id, input: $input) {{
    success
    need {{{_CUSTOMER_NEED_FIELDS}}}
  }}
}}
"""

CUSTOMER_NEED_DELETE = f"""
mutation CustomerNeedDelete($id: String!) {{
  customerNeedDelete(id: $id) {{ {_DELETED} }}
}}
"""

CUSTOMER_STATUSES = f"""
query CustomerStatuses($first: Int, $after: String) {{
  customerStatuses(first: $first, after: $after) {{
    nodes {{ id name description color type position }}
    {_PAGE_INFO}
  }}
}}
"""

CUSTOMER_TIERS = f"""
query CustomerTiers($first: Int, $after: String) {{
  customerTiers(first: $first, after: $after) {{
    nodes {{ id name description color position }}
    {_PAGE_INFO}
  }}
}}
"""

# ---------------------------------------------------------------------------
# notifications, favorites, saved views
# ---------------------------------------------------------------------------

NOTIFICATIONS = f"""
query Notifications($first: Int, $after: String, $includeArchived: Boolean, $orderBy: PaginationOrderBy) {{
  notifications(first: $first, after: $after, includeArchived: $includeArchived, orderBy: $orderBy) {{
    nodes {{{_NOTIFICATION_FIELDS}}}
    {_PAGE_INFO}
  }}
}}
"""

NOTIFICATION = f"""
query Notification($id: String!) {{
  notification(id: $id) {{{_NOTIFICATION_FIELDS}}}
}}
"""

NOTIFICATION_UPDATE = f"""
mutation NotificationUpdate($id: String!, $input: NotificationUpdateInput!) {{
  notificationUpdate(id: $id, input: $input) {{
    success
    notification {{{_NOTIFICATION_FIELDS}}}
  }}
}}
"""

NOTIFICATION_ARCHIVE = f"""
mutation NotificationArchive($id: String!) {{
  notificationArchive(id: $id) {{
    success
    entity {{{_NOTIFICATION_FIELDS}}}
  }}
}}
"""

NOTIFICATION_UNARCHIVE = f"""
mutation NotificationUnarchive($id: String!) {{
  notificationUnarchive(id: $id) {{
    success
    entity {{{_NOTIFICATION_FIELDS}}}
  }}
}}
"""

# Not "mark everything read": Linear scopes this to one entity, and requires
# both the entity and the timestamp.
NOTIFICATION_MARK_READ_ALL = """
mutation NotificationMarkReadAll($input: NotificationEntityInput!, $readAt: DateTime!) {
  notificationMarkReadAll(input: $input, readAt: $readAt) {
    success
  }
}
"""

FAVORITES = f"""
query Favorites($first: Int, $after: String) {{
  favorites(first: $first, after: $after) {{
    nodes {{{_FAVORITE_FIELDS}}}
    {_PAGE_INFO}
  }}
}}
"""

FAVORITE_CREATE = f"""
mutation FavoriteCreate($input: FavoriteCreateInput!) {{
  favoriteCreate(input: $input) {{
    success
    favorite {{{_FAVORITE_FIELDS}}}
  }}
}}
"""

FAVORITE_UPDATE = f"""
mutation FavoriteUpdate($id: String!, $input: FavoriteUpdateInput!) {{
  favoriteUpdate(id: $id, input: $input) {{
    success
    favorite {{{_FAVORITE_FIELDS}}}
  }}
}}
"""

FAVORITE_DELETE = f"""
mutation FavoriteDelete($id: String!) {{
  favoriteDelete(id: $id) {{ {_DELETED} }}
}}
"""

CUSTOM_VIEWS = f"""
query CustomViews($first: Int, $after: String, $includeArchived: Boolean, $orderBy: PaginationOrderBy) {{
  customViews(first: $first, after: $after, includeArchived: $includeArchived, orderBy: $orderBy) {{
    nodes {{{_CUSTOM_VIEW_FIELDS}}}
    {_PAGE_INFO}
  }}
}}
"""

CUSTOM_VIEW = f"""
query CustomView($id: String!) {{
  customView(id: $id) {{{_CUSTOM_VIEW_FIELDS}}}
}}
"""

CUSTOM_VIEW_CREATE = f"""
mutation CustomViewCreate($input: CustomViewCreateInput!) {{
  customViewCreate(input: $input) {{
    success
    customView {{{_CUSTOM_VIEW_FIELDS}}}
  }}
}}
"""

CUSTOM_VIEW_DELETE = f"""
mutation CustomViewDelete($id: String!) {{
  customViewDelete(id: $id) {{ {_DELETED} }}
}}
"""

# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

# The payloads are not connections, but they carry the same pageInfo, so the
# declared cursor still works.
SEARCH_ISSUES = f"""
query SearchIssues(
  $term: String!
  $filter: IssueFilter
  $first: Int
  $after: String
  $includeComments: Boolean
  $includeArchived: Boolean
  $orderBy: PaginationOrderBy
  $teamId: String
) {{
  searchIssues(
    term: $term
    filter: $filter
    first: $first
    after: $after
    includeComments: $includeComments
    includeArchived: $includeArchived
    orderBy: $orderBy
    teamId: $teamId
  ) {{
    nodes {{{_ISSUE_FIELDS}}}
    totalCount
    {_PAGE_INFO}
  }}
}}
"""

SEARCH_PROJECTS = f"""
query SearchProjects(
  $term: String!
  $first: Int
  $after: String
  $includeComments: Boolean
  $includeArchived: Boolean
  $orderBy: PaginationOrderBy
  $teamId: String
) {{
  searchProjects(
    term: $term
    first: $first
    after: $after
    includeComments: $includeComments
    includeArchived: $includeArchived
    orderBy: $orderBy
    teamId: $teamId
  ) {{
    nodes {{{_PROJECT_FIELDS}}}
    totalCount
    {_PAGE_INFO}
  }}
}}
"""

SEARCH_DOCUMENTS = f"""
query SearchDocuments(
  $term: String!
  $first: Int
  $after: String
  $includeComments: Boolean
  $includeArchived: Boolean
  $orderBy: PaginationOrderBy
  $teamId: String
) {{
  searchDocuments(
    term: $term
    first: $first
    after: $after
    includeComments: $includeComments
    includeArchived: $includeArchived
    orderBy: $orderBy
    teamId: $teamId
  ) {{
    nodes {{{_DOCUMENT_FIELDS}}}
    totalCount
    {_PAGE_INFO}
  }}
}}
"""

# ---------------------------------------------------------------------------
# webhooks
# ---------------------------------------------------------------------------

WEBHOOKS = f"""
query Webhooks($first: Int, $after: String, $includeArchived: Boolean, $orderBy: PaginationOrderBy) {{
  webhooks(first: $first, after: $after, includeArchived: $includeArchived, orderBy: $orderBy) {{
    nodes {{{_WEBHOOK_FIELDS}}}
    {_PAGE_INFO}
  }}
}}
"""

WEBHOOK = f"""
query Webhook($id: String!) {{
  webhook(id: $id) {{{_WEBHOOK_FIELDS}}}
}}
"""

WEBHOOK_CREATE = f"""
mutation WebhookCreate($input: WebhookCreateInput!) {{
  webhookCreate(input: $input) {{
    success
    webhook {{{_WEBHOOK_FIELDS}}}
  }}
}}
"""

WEBHOOK_UPDATE = f"""
mutation WebhookUpdate($id: String!, $input: WebhookUpdateInput!) {{
  webhookUpdate(id: $id, input: $input) {{
    success
    webhook {{{_WEBHOOK_FIELDS}}}
  }}
}}
"""

WEBHOOK_DELETE = f"""
mutation WebhookDelete($id: String!) {{
  webhookDelete(id: $id) {{ {_DELETED} }}
}}
"""
