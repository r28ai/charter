# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Tools ask for what each vendor documents, and no more, under every kind of credential.

The tables below are the vendors' own statements, copied on 2026-10-24, kept apart
from the declarations so the two can disagree: GitHub's per-endpoint sentence in
its OpenAPI description (``api.github.com.json`` 1.1.4) and the
``X-Accepted-GitHub-Permissions`` header it sent for every tool, Linear's list of
OAuth scopes, the "Requires … access scope" line on every Shopify Admin GraphQL
object and mutation a tool's document touches, Microsoft Graph's permission table
on each Outlook operation's page, and Stripe's API permissions reference. Google's
are in ``test_google_scopes.py``.
"""

from __future__ import annotations

import itertools

import pytest

from charter.auth import AnyOf, Unavailable, scopes_for
from charter.packs import github, linear, outlook, shopify, stripe


def _options(requirement) -> tuple[str, ...]:
    if isinstance(requirement, Unavailable):
        return ()
    return requirement.options if isinstance(requirement, AnyOf) else (requirement,)


# -----------------------------------------------------------------------------
# GitHub
# -----------------------------------------------------------------------------

# The classic scopes GitHub's description of each endpoint names. An endpoint it
# says nothing about follows the general rule: no scope for a public repository,
# `repo` for a private one.
GITHUB_DOCUMENTED = {
    "users_get_authenticated": {"read:user", "user"},
    "dependabot_list_alerts": {"security_events"},
    "dependabot_get_alert": {"security_events"},
    "dependabot_update_alert": {"security_events"},
    "code_scanning_list_alerts": {"security_events", "public_repo"},
    "code_scanning_get_alert": {"security_events", "public_repo"},
    "secret_scanning_list_alerts": {"repo", "security_events"},
    "releases_create": {"workflow"},
    "releases_update": {"workflow"},
}
# GitHub's scope list: `repo` grants `security_events` and `public_repo`, and
# notifications are readable with `repo` as well as `notifications`.
GITHUB_COVERED_BY_REPO = {"security_events", "public_repo", "notifications"}
NO_SCOPE = {"search_users", "rate_limit_get"}


def test_no_github_tool_offers_a_scope_that_reaches_only_public_repositories():
    offered = {o for t in github.TOOLS for r in t.scopes for o in _options(r)}
    assert "public_repo" not in offered


@pytest.mark.parametrize("tool", github.TOOLS, ids=lambda t: t.name)
def test_each_github_tool_asks_for_what_github_documents(tool):
    options = [o for r in tool.scopes for o in _options(r)]
    if tool.name in NO_SCOPE:
        assert options == []
        return
    documented = GITHUB_DOCUMENTED.get(tool.name, {"repo"})
    if tool.name in ("releases_create", "releases_update"):
        # `workflow` only for a commit that changes workflow files: not asked for.
        assert options == ["repo"]
        return
    allowed = documented | (
        {"repo"} if documented & GITHUB_COVERED_BY_REPO or "repo" in documented else set()
    )
    if tool.name.startswith("notifications_"):
        allowed = {"notifications", "repo"}
    assert set(options) <= allowed, f"{tool.name}: {options} beyond {sorted(allowed)}"
    assert options, f"{tool.name} declares no scope"


def test_githubs_whole_pack_asks_for_repo_and_the_private_profile():
    assert scopes_for(github.TOOLS) == github.SCOPES == ["repo", "read:user"]


# What GitHub's `X-Accepted-GitHub-Permissions` header named for each tool, sent to
# a fine-grained token on 2026-10-24 by `live_github_scopes_check.py --kind
# fine_grained`, every call aimed at a repository that does not exist. `a; b` is
# either set, `a,b` is both. None where GitHub sent no header: the notification
# endpoints, which no fine-grained token can call, the two writes there that were
# not sent, and the upload host. `allows_permissionless_access=true` is no
# permission at all.
GITHUB_ACCEPTED_PERMISSIONS = {
    "issues_list_for_repo": "issues=read",
    "issues_get": "issues=read",
    "issues_create": "issues=write",
    "issues_update": "issues=write; pull_requests=write",
    "issues_create_comment": "issues=write; pull_requests=write",
    "issues_list_comments": "issues=read; pull_requests=read",
    "pulls_list": "pull_requests=read",
    "pulls_get": "pull_requests=read; contents=read",
    "pulls_create": "pull_requests=write",
    "pulls_list_files": "pull_requests=read",
    "repos_get": "metadata=read",
    "repos_list_for_authenticated_user": "metadata=read",
    "repos_get_content": "contents=read",
    "repos_list_commits": "contents=read",
    "search_issues": "allows_permissionless_access=true",
    "search_repositories": "allows_permissionless_access=true",
    "users_get_authenticated": "allows_permissionless_access=true",
    "pulls_update": "pull_requests=write",
    "pulls_merge": "contents=write",
    "pulls_create_review": "pull_requests=write",
    "pulls_list_reviews": "pull_requests=read",
    "pulls_request_reviewers": "pull_requests=write",
    "repos_create_or_update_file": "contents=write; contents=write,workflows=write",
    "branches_list": "contents=read",
    "git_refs_create": "contents=write; contents=write,workflows=write",
    "actions_list_workflow_runs": "actions=read",
    "actions_rerun_workflow": "actions=write",
    "actions_cancel_workflow_run": "actions=write",
    "search_code": None,
    "actions_get_workflow_run": "actions=read",
    "actions_list_jobs_for_run": "actions=read",
    "actions_get_job": "actions=read",
    "actions_download_job_logs": "actions=read",
    "actions_download_run_logs": "actions=read",
    "actions_rerun_failed_jobs": "actions=write",
    "actions_list_workflows": "actions=read",
    "actions_get_workflow": "actions=read",
    "actions_create_workflow_dispatch": "actions=write",
    "actions_list_runs_for_workflow": "actions=read",
    "actions_list_run_artifacts": "actions=read",
    "actions_get_artifact": "actions=read",
    "actions_download_artifact": "actions=read",
    "actions_get_run_usage": "actions=read",
    "actions_list_pending_deployments": "actions=read",
    "actions_review_pending_deployments": "deployments=write",
    "actions_list_repo_secrets": "secrets=read",
    "checks_list_for_ref": "checks=read",
    "checks_get_run": "checks=read",
    "checks_list_annotations": "checks=read",
    "checks_list_suites_for_ref": "checks=read",
    "repos_get_combined_status": "contents=read",
    "pulls_create_review_comment": "pull_requests=write",
    "pulls_list_review_comments": "pull_requests=read",
    "pulls_reply_to_review_comment": "pull_requests=write",
    "pulls_update_review_comment": "pull_requests=write",
    "pulls_delete_review_comment": "pull_requests=write",
    "pulls_list_review_comments_for_repo": "pull_requests=read",
    "pulls_get_review": "pull_requests=read",
    "pulls_submit_review": "pull_requests=write",
    "pulls_update_review": "pull_requests=write",
    "pulls_dismiss_review": "pull_requests=write",
    "pulls_delete_pending_review": "pull_requests=write",
    "pulls_list_comments_for_review": "pull_requests=read",
    "pulls_get_diff": "pull_requests=read; contents=read",
    "pulls_list_commits": "pull_requests=read",
    "pulls_update_branch": "pull_requests=write",
    "pulls_check_merged": "pull_requests=read",
    "pulls_list_requested_reviewers": "pull_requests=read",
    "pulls_remove_requested_reviewers": "pull_requests=write",
    "git_refs_get": "contents=read",
    "git_refs_update": "contents=write; contents=write,workflows=write",
    "git_refs_delete": "contents=write",
    "git_refs_list_matching": "contents=read",
    "git_blobs_create": "contents=write",
    "git_blobs_get": "contents=read",
    "git_trees_create": "contents=write",
    "git_trees_get": "contents=read",
    "git_commits_create": "contents=write",
    "git_commits_get": "contents=read",
    "git_tags_create": "contents=write",
    "repos_get_commit": "contents=read",
    "repos_compare_commits": "contents=read",
    "repos_delete_file": "contents=write; contents=write,workflows=write",
    "repos_merge_branches": "contents=write",
    "repos_get_branch": "contents=read",
    "repos_rename_branch": "contents=write",
    "repos_get_branch_protection": "administration=read",
    "repos_list_branches_for_head_commit": "contents=read",
    "repos_get_readme": "contents=read",
    "repos_list_tags": "metadata=read",
    "repos_create_fork": "administration=write,contents=read; contents=read,repository_creation=write",
    "issues_list_labels_for_repo": "issues=read; pull_requests=read",
    "issues_add_labels": "issues=write; pull_requests=write",
    "issues_set_labels": "issues=write; pull_requests=write",
    "issues_remove_label": "issues=write; pull_requests=write",
    "issues_create_label": "issues=write; pull_requests=write",
    "issues_update_label": "issues=write; pull_requests=write",
    "issues_delete_label": "issues=write; pull_requests=write",
    "issues_add_assignees": "issues=write; pull_requests=write",
    "issues_remove_assignees": "issues=write; pull_requests=write",
    "issues_list_milestones": "issues=read; pull_requests=read",
    "issues_create_milestone": "issues=write; pull_requests=write",
    "issues_update_milestone": "issues=write; pull_requests=write",
    "issues_get_comment": "issues=read; pull_requests=read",
    "issues_update_comment": "issues=write; pull_requests=write",
    "issues_delete_comment": "issues=write; pull_requests=write",
    "issues_list_timeline": "issues=read; pull_requests=read",
    "issues_list_events": "issues=read; pull_requests=read",
    "issues_lock": "issues=write; pull_requests=write",
    "issues_unlock": "issues=write; pull_requests=write",
    "issues_list_for_authenticated_user": "allows_permissionless_access=true",
    "issues_list_sub_issues": "issues=read",
    "issues_add_sub_issue": "issues=write",
    "releases_list": "contents=read",
    "releases_get": "contents=read",
    "releases_get_latest": "contents=read",
    "releases_get_by_tag": "contents=read",
    "releases_create": "contents=write; contents=write,workflows=write",
    "releases_update": "contents=write; contents=write,workflows=write",
    "releases_delete": "contents=write",
    "releases_generate_notes": "contents=write",
    "releases_list_assets": "contents=read",
    "releases_upload_asset": None,
    "notifications_list": None,
    "notifications_get_thread": None,
    "dependabot_list_alerts": "vulnerability_alerts=read",
    "dependabot_get_alert": "vulnerability_alerts=read",
    "dependabot_update_alert": "vulnerability_alerts=write",
    "code_scanning_list_alerts": "security_events=read",
    "code_scanning_get_alert": "security_events=read",
    "secret_scanning_list_alerts": "secret_scanning_alerts=read",
    "search_commits": "allows_permissionless_access=true",
    "search_users": "allows_permissionless_access=true",
    "repos_list_for_org": "metadata=read",
    "repos_list_languages": "metadata=read",
    "repos_list_contributors": "metadata=read",
    "rate_limit_get": "allows_permissionless_access=true",
}

# Served to a user's token only, per each endpoint's "Fine-grained access tokens"
# section ("works with … GitHub App user access tokens, Fine-grained personal
# access tokens"), so an installation token cannot call them.
GITHUB_USER_TOKEN_ONLY = {
    "users_get_authenticated",
    "issues_list_for_authenticated_user",
    "repos_list_for_authenticated_user",
}
GITHUB_NO_FINE_GRAINED = {
    "notifications_list",
    "notifications_mark_read",
    "notifications_get_thread",
    "notifications_mark_thread_read",
}


def _accepted_sets(header: str) -> list[frozenset[str]]:
    return [
        frozenset(p.strip() for p in alt.split(",") if p.strip())
        for alt in header.split(";")
        if alt.strip()
    ]


def _with_reads(granted: set[str]) -> set[str]:
    """Write access to a permission includes read."""
    return granted | {g.replace("=write", "=read") for g in granted if g.endswith("=write")}


def test_every_github_tool_is_in_the_permission_table():
    assert set(GITHUB_ACCEPTED_PERMISSIONS) | {
        "notifications_mark_read",
        "notifications_mark_thread_read",
    } == {t.name for t in github.TOOLS}


@pytest.mark.parametrize("tool", github.TOOLS, ids=lambda t: t.name)
def test_every_way_to_meet_a_github_tools_permissions_meets_what_github_accepts(tool):
    """Each AnyOf option, combined with each of the others, is a set GitHub takes."""
    declared = tool.kind_scopes[github.FINE_GRAINED]
    if tool.name in GITHUB_NO_FINE_GRAINED:
        assert [type(r) for r in declared] == [Unavailable]
        return
    header = GITHUB_ACCEPTED_PERMISSIONS[tool.name]
    if header is None or header.startswith("allows_permissionless_access"):
        # The upload host names nothing; every other release write is contents=write.
        assert declared == ([github.CONTENTS_WRITE] if tool.name == "releases_upload_asset" else [])
        return
    accepted = _accepted_sets(header)
    clauses = [_options(r) for r in declared]
    assert clauses, f"{tool.name} declares no permission for {header!r}"
    for choice in itertools.product(*clauses):
        assert any(s <= _with_reads(set(choice)) for s in accepted), (
            f"{tool.name}: {sorted(choice)} meets none of {header!r}"
        )


@pytest.mark.parametrize("tool", github.TOOLS, ids=lambda t: t.name)
def test_an_installation_token_differs_from_a_users_only_where_github_says(tool):
    app, user = tool.kind_scopes[github.APP], tool.kind_scopes[github.FINE_GRAINED]
    if tool.name in GITHUB_USER_TOKEN_ONLY:
        assert [type(r) for r in app] == [Unavailable] and not any(
            isinstance(r, Unavailable) for r in user
        )
    else:
        assert app == user


def test_an_issue_endpoint_does_not_offer_the_pull_request_permission():
    """GitHub takes `pull_requests` on an issue endpoint only for a pull request's
    number, so offering it would let a grant pass that fails on a plain issue."""
    for tool in (github.issues_update, github.issues_create_comment, github.issues_add_labels):
        offered = {o for r in tool.kind_scopes[github.APP] for o in _options(r)}
        assert offered == {"issues=write"}, tool.name
    assert scopes_for([github.issues_add_labels, github.pulls_create], kind=github.APP) == [
        "issues=write",
        "pull_requests=write",
    ]


def test_a_github_app_reading_and_writing_issues_asks_for_write_alone():
    assert scopes_for([github.issues_get, github.issues_create], kind=github.APP) == [
        "issues=write"
    ]


# -----------------------------------------------------------------------------
# Linear
# -----------------------------------------------------------------------------

LINEAR_DOCUMENTED = {
    "read",
    "write",
    "issues:create",
    "comments:create",
    "timeSchedule:write",
    "admin",
}


@pytest.mark.parametrize("tool", linear.TOOLS, ids=lambda t: t.name)
def test_each_linear_tool_asks_for_a_scope_linear_documents(tool):
    options = [o for r in tool.scopes for o in _options(r)]
    assert options and set(options) <= LINEAR_DOCUMENTED, (tool.name, options)


def test_reading_linear_webhooks_asks_for_admin_and_writing_them_does_not():
    """Linear's refusal to a `read` grant, 2026-10-24: "Invalid scope: `admin` required"
    for `webhooks` and `webhook`, and `write` for the webhook mutations."""
    assert scopes_for([linear.webhooks_list]) == scopes_for([linear.webhook_get]) == ["admin"]
    assert scopes_for([linear.webhook_create]) == scopes_for([linear.webhook_delete]) == ["write"]


def test_linear_reads_ask_for_read_and_creates_for_the_narrow_scopes():
    assert scopes_for([linear.issues_list, linear.issue_get]) == ["read"]
    assert scopes_for([linear.issue_create]) == ["issues:create"]
    assert scopes_for([linear.attachment_create]) == ["issues:create"]
    assert scopes_for([linear.comment_create]) == ["comments:create"]
    assert scopes_for([linear.issue_update]) == ["write"]
    assert scopes_for([linear.issue_create, linear.issue_update]) == ["write"]


# -----------------------------------------------------------------------------
# Shopify
# -----------------------------------------------------------------------------

# "Requires … access scope" from each object's and mutation's reference page. The
# alternatives Shopify gives for other kinds of resource (marketplace and
# buyer-membership orders, quick-sale drafts, fulfillment orders at other kinds of
# location) are kept out: they reach a different class, not the same one.
SHOPIFY_DOCUMENTED = {
    "Product": {"read_products"},
    "ProductVariant": {"read_products"},
    "InventoryItem": {"read_inventory", "read_products"},
    "InventoryLevel": {"read_inventory"},
    "Order": {"read_orders"},
    "Customer": {"read_customers"},
    "Location": {"read_locations", "read_inventory"},
    "FulfillmentOrder": {"read_merchant_managed_fulfillment_orders"},
    "DraftOrder": {"read_draft_orders"},
    "productCreate": {"write_products"},
    "productUpdate": {"write_products"},
    "productVariantsBulkCreate": {"write_products"},
    "customerCreate": {"write_customers"},
    "customerUpdate": {"write_customers"},
    "fulfillmentCreate": {"write_merchant_managed_fulfillment_orders"},
    "inventoryAdjustQuantities": {"write_inventory"},
    "orderClose": {"write_orders"},
    "orderOpen": {"write_orders"},
    "orderCancel": {"write_orders"},
    "draftOrderCreate": {"write_draft_orders"},
    "draftOrderComplete": {"write_draft_orders"},
}
# What each tool's document touches: its mutation, then every object it reads.
SHOPIFY_TOUCHES = {
    "shop_get": [],
    "products_list": ["Product"],
    "product_get": ["Product", "ProductVariant"],
    "product_create": ["productCreate"],
    "product_update": ["productUpdate"],
    "product_variants_bulk_create": ["productVariantsBulkCreate", "InventoryItem"],
    "orders_list": ["Order", "Customer"],
    "order_get": ["Order", "Customer"],
    "customers_list": ["Customer"],
    "customer_get": ["Customer"],
    "customer_create": ["customerCreate"],
    "customer_update": ["customerUpdate"],
    "order_fulfillment_orders": ["Order", "FulfillmentOrder", "Location"],
    "fulfillment_create": ["fulfillmentCreate"],
    "inventory_adjust_quantities": ["inventoryAdjustQuantities"],
    "variant_inventory_level": ["ProductVariant", "InventoryItem", "InventoryLevel", "Location"],
    "locations_list": ["Location"],
    "order_close": ["orderClose"],
    "order_open": ["orderOpen"],
    "order_cancel": ["orderCancel"],
    "draft_order_create": ["draftOrderCreate"],
    "draft_order_complete": ["draftOrderComplete", "Order"],
}


def _with_writes(scopes: set[str]) -> set[str]:
    """Shopify: any scope that writes a resource also grants read access to it."""
    return scopes | {s.replace("read_", "write_", 1) for s in scopes if s.startswith("read_")}


def test_every_shopify_tool_is_in_the_table():
    assert sorted(t.name for t in shopify.TOOLS) == sorted(SHOPIFY_TOUCHES)


@pytest.mark.parametrize("tool", shopify.TOOLS, ids=lambda t: t.name)
def test_each_shopify_tool_covers_everything_its_document_touches(tool):
    """A grant meeting the tool's requirements meets what each object and mutation needs."""
    granted = set(scopes_for([tool]))
    for touched in SHOPIFY_TOUCHES[tool.name]:
        assert granted & _with_writes(SHOPIFY_DOCUMENTED[touched]), (
            f"{tool.name} reads {touched}, which needs one of "
            f"{sorted(SHOPIFY_DOCUMENTED[touched])}; scopes_for gives {sorted(granted)}"
        )


@pytest.mark.parametrize("tool", shopify.TOOLS, ids=lambda t: t.name)
def test_each_shopify_tool_offers_only_scopes_shopify_documents(tool):
    documented = set().union(*(_with_writes(v) for v in SHOPIFY_DOCUMENTED.values()))
    options = {o for r in tool.scopes for o in _options(r)}
    assert options <= documented, f"{tool.name}: {sorted(options - documented)}"


def test_no_shopify_tool_asks_for_the_scopes_shopify_approves_per_app():
    offered = {o for t in shopify.TOOLS for r in t.scopes for o in _options(r)}
    assert "read_all_orders" not in offered


# -----------------------------------------------------------------------------
# Outlook (Microsoft Graph)
# -----------------------------------------------------------------------------

# Each operation's "Permissions" table on learn.microsoft.com, the delegated
# work-or-school row: least privileged, then the higher ones. Read 2026-10-24 from
# microsoft-graph-docs-contrib (api-reference/v1.0, the page or its
# includes/permissions file). The message row where a page has one per resource.
GRAPH_DOCUMENTED = {
    "messages_list": ["Mail.ReadBasic", "Mail.ReadWrite", "Mail.Read"],
    "messages_get": ["Mail.ReadBasic", "Mail.Read"],
    "messages_get_content": ["Mail.ReadBasic", "Mail.Read"],
    "messages_delta": ["Mail.ReadBasic", "Mail.Read", "Mail.ReadWrite"],
    "messages_create": ["Mail.ReadWrite"],
    "messages_update": ["Mail.ReadWrite"],
    "messages_delete": ["Mail.ReadWrite"],
    "messages_permanent_delete": ["Mail.ReadWrite"],
    "messages_move": ["Mail.ReadWrite"],
    "messages_copy": ["Mail.ReadWrite"],
    "messages_send": ["Mail.Send"],
    "messages_reply": ["Mail.Send"],
    "messages_reply_all": ["Mail.Send"],
    "messages_forward": ["Mail.Send"],
    "messages_create_reply": ["Mail.ReadWrite"],
    "messages_create_reply_all": ["Mail.ReadWrite"],
    "messages_create_forward": ["Mail.ReadWrite"],
    "send_mail": ["Mail.Send"],
    "attachments_list": ["Mail.Read"],
    "attachments_get": ["Mail.Read"],
    "attachments_get_content": ["Mail.Read"],
    "attachments_create": ["Mail.ReadWrite"],
    "attachments_create_upload_session": ["Calendars.ReadWrite", "Mail.ReadWrite"],
    "attachments_delete": ["Mail.ReadWrite"],
    "mail_folders_list": ["Mail.ReadBasic", "Mail.ReadWrite", "Mail.Read"],
    "mail_folders_get": ["Mail.ReadBasic", "Mail.ReadWrite", "Mail.Read"],
    "mail_folders_create": ["Mail.ReadWrite"],
    "mail_folders_update": ["Mail.ReadWrite"],
    "mail_folders_delete": ["Mail.ReadWrite"],
    "mail_folders_permanent_delete": ["Mail.ReadWrite"],
    "mail_folders_move": ["Mail.ReadWrite"],
    "mail_folders_copy": ["Mail.ReadWrite"],
    "mail_folders_delta": ["Mail.ReadBasic", "Mail.Read", "Mail.ReadWrite"],
    "master_categories_list": ["MailboxSettings.Read"],
    "master_categories_get": ["MailboxSettings.Read"],
    "master_categories_create": ["MailboxSettings.ReadWrite"],
    "master_categories_update": ["MailboxSettings.ReadWrite"],
    "master_categories_delete": ["MailboxSettings.ReadWrite"],
    "message_rules_list": ["MailboxSettings.Read"],
    "message_rules_get": ["MailboxSettings.Read"],
    "message_rules_create": ["MailboxSettings.ReadWrite"],
    "message_rules_update": ["MailboxSettings.ReadWrite"],
    "message_rules_delete": ["MailboxSettings.ReadWrite"],
    "mailbox_settings_get": ["MailboxSettings.Read", "MailboxSettings.ReadWrite"],
    "mailbox_settings_update": ["MailboxSettings.ReadWrite"],
    "supported_languages": ["User.Read", "User.Read.All", "User.ReadBasic.All"],
    "supported_time_zones": ["User.Read", "User.Read.All", "User.ReadBasic.All"],
    "inference_overrides_list": ["Mail.Read"],
    "inference_overrides_create": ["Mail.ReadWrite"],
    "inference_overrides_update": ["Mail.ReadWrite"],
    "inference_overrides_delete": ["Mail.ReadWrite"],
    "extensions_get": ["Mail.Read"],
    "extensions_create": ["Mail.ReadWrite"],
    "extensions_delete": ["Mail.ReadWrite"],
    "get_mail_tips": ["Mail.Read", "Mail.Read.Shared", "MailTips.ReadBasic.Shared"],
    "translate_exchange_ids": [
        "User.ReadBasic.All",
        "AgentIdUser.ReadWrite.All",
        "AgentIdUser.ReadWrite.IdentityParentedBy",
        "User.Read",
        "User.Read.All",
        "User.ReadWrite",
        "User.ReadWrite.All",
    ],
}
# Microsoft's permissions reference: every *.ReadWrite "allows the app to create,
# read, update, and delete", so it is accepted wherever its *.Read is.
GRAPH_IMPLIED = {"Mail.Read": "Mail.ReadWrite", "MailboxSettings.Read": "MailboxSettings.ReadWrite"}
# Accepted, and left out because they reach less than the tool can name, or
# another kind of principal.
GRAPH_LEFT_OUT = {
    "Mail.ReadBasic": "no body and no attachments",
    "Calendars.ReadWrite": "an event's attachments, not a message's",
    "AgentIdUser.ReadWrite.All": "agent identities",
    "AgentIdUser.ReadWrite.IdentityParentedBy": "agent identities",
}
_FOLDER_READS = {"mail_folders_list", "mail_folders_get", "mail_folders_delta"}


def _graph(scope: str) -> str:
    return scope.removeprefix("https://graph.microsoft.com/")


def test_every_outlook_tool_is_in_the_table():
    assert sorted(GRAPH_DOCUMENTED) == sorted(t.name for t in outlook.TOOLS)


@pytest.mark.parametrize("tool", outlook.TOOLS, ids=lambda t: t.name)
def test_each_outlook_tool_offers_what_microsoft_accepts_and_leaves_out_only_partial_ones(tool):
    documented = GRAPH_DOCUMENTED[tool.name]
    accepted = set(documented) | {GRAPH_IMPLIED[s] for s in documented if s in GRAPH_IMPLIED}
    offered = [_graph(o) for r in tool.scopes for o in _options(r)]
    assert offered and set(offered) <= accepted, (tool.name, offered)
    missing = accepted - set(offered)
    if tool.name in _FOLDER_READS:
        missing.discard("Mail.ReadBasic")  # a folder carries no body: offered there
    assert missing <= set(GRAPH_LEFT_OUT), f"{tool.name} leaves out {sorted(missing)}"


def test_a_folder_reader_offers_basic_and_a_message_reader_does_not():
    assert scopes_for([outlook.mail_folders_list]) == [outlook.MAIL_READ_BASIC]
    assert scopes_for([outlook.messages_list]) == [outlook.MAIL_READ]


# -----------------------------------------------------------------------------
# Stripe
# -----------------------------------------------------------------------------

# Stripe's API permissions reference, the permission it names for each endpoint.
STRIPE_DOCUMENTED = {
    ("GET", "v1/customers"): "customer_read",
    ("GET", "v1/customers/{}"): "customer_read",
    ("POST", "v1/customers"): "customer_write",
    ("GET", "v1/customers/search"): "customer_read",
    ("GET", "v1/payment_intents"): "payment_intent_read",
    ("GET", "v1/payment_intents/search"): "payment_intent_read",
    ("POST", "v1/payment_intents/{}/capture"): "payment_intent_write",
    ("GET", "v1/charges"): "charge_read",
    ("GET", "v1/charges/{}"): "charge_read",
    ("GET", "v1/charges/search"): "charge_read",
    ("GET", "v1/refunds"): "charge_read",
    ("GET", "v1/refunds/{}"): "charge_read",
    ("GET", "v1/products"): "product_read",
    ("POST", "v1/products"): "product_write",
    ("POST", "v1/products/{}"): "product_write",
    ("GET", "v1/products/search"): "product_read",
    ("GET", "v1/prices"): "plan_read",
    ("POST", "v1/prices"): "plan_write",
    ("POST", "v1/prices/{}"): "plan_write",
    ("GET", "v1/prices/search"): "plan_read",
    ("GET", "v1/subscriptions"): "subscription_read",
    ("POST", "v1/subscriptions"): "subscription_write",
    ("POST", "v1/subscriptions/{}"): "subscription_write",
    ("DELETE", "v1/subscriptions/{}"): "subscription_write",
    ("GET", "v1/subscriptions/search"): "subscription_read",
    ("GET", "v1/invoices"): "invoice_read",
    ("GET", "v1/invoices/{}"): "invoice_read",
    ("POST", "v1/invoices"): "invoice_write",
    ("POST", "v1/invoices/{}"): "invoice_write",
    ("POST", "v1/invoices/{}/finalize"): "invoice_write",
    ("POST", "v1/invoices/{}/send"): "invoice_write",
    ("POST", "v1/invoices/{}/void"): "invoice_write",
    ("POST", "v1/invoices/{}/mark_uncollectible"): "invoice_write",
    ("GET", "v1/invoices/search"): "invoice_read",
    ("POST", "v1/invoiceitems"): "invoice_write",
    ("GET", "v1/invoiceitems"): "invoice_read",
    ("POST", "v1/invoiceitems/{}"): "invoice_write",
    ("DELETE", "v1/invoiceitems/{}"): "invoice_write",
    ("GET", "v1/checkout/sessions"): "checkout_session_read",
    ("GET", "v1/checkout/sessions/{}"): "checkout_session_read",
    ("GET", "v1/checkout/sessions/{}/line_items"): "checkout_session_read",
    ("POST", "v1/checkout/sessions"): "checkout_session_write",
    ("GET", "v1/payment_methods"): "payment_method_read",
    ("GET", "v1/payment_methods/{}"): "payment_method_read",
    ("POST", "v1/payment_methods/{}/attach"): "payment_method_write",
    ("POST", "v1/payment_methods/{}/detach"): "payment_method_write",
    ("GET", "v1/customers/{}/payment_methods"): "payment_method_read",
    ("GET", "v1/customers/{}/payment_methods/{}"): "payment_method_read",
    ("GET", "v1/disputes"): "dispute_read",
    ("GET", "v1/disputes/{}"): "dispute_read",
    ("POST", "v1/disputes/{}"): "dispute_write",
    ("POST", "v1/disputes/{}/close"): "dispute_write",
    ("GET", "v1/accounts"): "connected_account_read",
    ("GET", "v1/accounts/{}"): "connected_account_read",
    ("GET", "v1/payouts"): "payout_read",
    ("GET", "v1/payouts/{}"): "payout_read",
    ("GET", "v1/application_fees"): "application_fee_read",
    ("GET", "v1/balance_transactions"): "balance_read",
    ("GET", "v1/balance"): "balance_read",
}
# Missing from Stripe's table, so declared from the resource's neighbours. Stripe's
# refusals to a key without them confirmed all but refunds_create on 2026-10-24
# (scripts/live_stripe_permissions_check.py): Stripe looks a refund's charge up
# first, and answers a key that cannot read charges that it does not exist.
STRIPE_INFERRED = {
    "customers_update": "customer_write",
    "payment_intents_create": "payment_intent_write",
    "payment_intents_retrieve": "payment_intent_read",
    "payment_intents_cancel": "payment_intent_write",
    "refunds_create": "charge_write",
    "transfers_list": "transfer_read",
    "transfers_retrieve": "transfer_read",
}


def _stripe_key(tool) -> tuple[str, str]:
    import re

    return tool.method, re.sub(r"\{[^}]+\}", "{}", tool.url_template)


@pytest.mark.parametrize("tool", stripe.TOOLS, ids=lambda t: t.name)
def test_each_stripe_tool_asks_a_restricted_key_for_the_permission_stripe_names(tool):
    named = STRIPE_DOCUMENTED.get(_stripe_key(tool)) or STRIPE_INFERRED[tool.name]
    declared = tool.kind_scopes[stripe.RESTRICTED_KEY]
    assert len(declared) == 1
    options = _options(declared[0])
    # Narrowest first; a read also takes the resource's write, which includes it.
    assert options[0] == named
    assert options[1:] in ((), (named.replace("_read", "_write"),))
    assert tool.scopes == []  # a secret key needs nothing


def test_the_inferred_stripe_permissions_are_the_ones_not_in_the_table():
    inferred = {t.name for t in stripe.TOOLS if _stripe_key(t) not in STRIPE_DOCUMENTED}
    assert inferred == set(STRIPE_INFERRED)


# -----------------------------------------------------------------------------
# Granola, Firecrawl
# -----------------------------------------------------------------------------


def test_granola_reads_the_audit_log_only_with_an_audit_key_and_nothing_else_with_one():
    """docs.granola.ai/audit: "An audit key reads the audit log and nothing else.\""""
    from charter.packs import granola

    for tool in granola.TOOLS:
        audit = tool.kind_scopes[granola.AUDIT_KEY]
        if tool is granola.audit_list:
            assert audit == [] and [type(r) for r in tool.scopes] == [Unavailable]
        else:
            assert [type(r) for r in audit] == [Unavailable], tool.name


def test_granola_note_tools_ask_a_personal_key_for_both_kinds_of_note():
    from charter.packs import granola

    assert scopes_for([granola.notes_list]) == ["personal", "public"]
    assert scopes_for([granola.notes_get], kind=granola.WORKSPACE_KEY) == ["workspace"]
    assert scopes_for([granola.webhook_endpoints_create]) == []


# Firecrawl's endpoint groups (docs.firecrawl.dev/features/key-restrictions).
FIRECRAWL_GROUPS = {
    "scrape",
    "batch-scrape",
    "crawl",
    "map",
    "search",
    "extract",
    "agent",
    "parse",
    "browser",
    "monitor",
    "research",
    "llmstxt",
    "deep-research",
    "fireclaw",
}
# Named by the feature pages rather than by the path, and unchecked: restrictions
# need an enterprise key.
FIRECRAWL_FROM_FEATURE_PAGES = {
    "scrape_interact": "scrape",
    "scrape_interact_stop": "scrape",
    "interact_create": "browser",
    "interact_execute": "browser",
    "interact_list": "browser",
    "interact_delete": "browser",
    "research_papers_search": "research",
    "research_paper_get": "research",
    "research_similar_papers": "research",
    "developer_search": "search",
}


def test_each_firecrawl_tool_names_the_group_its_path_belongs_to():
    from charter.packs import firecrawl

    for tool in firecrawl.TOOLS:
        groups = tool.kind_scopes[firecrawl.RESTRICTED_KEY]
        assert tool.scopes == []
        if tool.url_template.startswith("team/"):
            assert groups == [], tool.name  # always reachable
            continue
        assert len(groups) == 1 and groups[0] in FIRECRAWL_GROUPS, (tool.name, groups)
        if tool.name in FIRECRAWL_FROM_FEATURE_PAGES:
            assert groups == [FIRECRAWL_FROM_FEATURE_PAGES[tool.name]]
        else:
            # The path's first segment, with batch/scrape as batch-scrape.
            head = tool.url_template.replace("batch/scrape", "batch-scrape").split("/")[0]
            assert groups == [head], (tool.name, groups)
