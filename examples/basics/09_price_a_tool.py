"""Find the field that makes a tool expensive."""

from charter import format_path_costs, schema_tokens
from charter.packs import linear

tool = linear.issues_list_full
print(f"linear.issues_list_full costs {schema_tokens(tool):,} tokens on every turn. By field:")
# linear.issues_list_full costs 45,072 tokens on every turn. By field:
print(format_path_costs(tool.paths(under="variables", by_cost=True)))
# filter            44,828
# order_by              52
# first                 45
# after                 43
# include_archived      36
