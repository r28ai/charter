Google's `documents.batchUpdate` takes 53 kinds of edit.

| | Charter (`gdocs`) | Composio (`googledocs`) |
|---|---:|---:|
| Docs tools | 3 | 28 (of 32 listed) |
| kinds of edit with a typed schema | 33 | 22 |
| kinds reachable only untyped | 0 | 31 |
| kinds not reachable | 20 | 0 |
| tool fields that are a name in Google's Docs API | 155/155 | 172/186 |

Typed by neither (20): `insertRichLink`, `updateDocumentTabProperties`, `insertDropdown`, `deleteComment`, `updateCommentPost`, `acceptSuggestion`, `deleteCommentReply`, `updateDropdownDefinitionProperties`, `addDocumentTab`, `deleteTab`, `deleteDropdownDefinition`, `rejectSuggestion`, `deleteSuggestion`, `createDropdownDefinition`, `insertPerson`, `updateDropdownProperties`, `addCommentReply`, `insertComment`, `insertDate`, `updateNamedStyle`

Composio fields that are no name in Google's Docs API: `editDocs`, `find_text`, `insertAtEndOfSegment`, `insertion_index`, `markdown_text`, `new_markdown_text`, `oddPageFooterId`, `oddPageHeaderId`, `rangeEndIndex`, `rangeSegmentId`, `rangeStartIndex`, `table_end_index`, `table_start_index`, `text_to_insert`

Charter fields that are no name in Google's Docs API: none

Composio tools left out as not Docs operations: `GOOGLEDOCS_COPY_DOCUMENT` (copies through Drive), `GOOGLEDOCS_GET_CHARTS_FROM_SPREADSHEET` (reads a Sheets spreadsheet), `GOOGLEDOCS_LIST_SPREADSHEET_CHARTS_ACTION` (reads a Sheets spreadsheet), `GOOGLEDOCS_SEARCH_DOCUMENTS` (searches Drive)
