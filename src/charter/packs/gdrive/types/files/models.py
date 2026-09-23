# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
File resource and the nested objects it carries.

API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/files
"""

from __future__ import annotations

from typing import Annotated, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from charter.types import Format, Mode

from ..common import User
from ..permissions.models import Permission

Aes256GcmChunkSize = Literal["default", "small"]
ContentRestrictionType = Literal["globalContentRestriction"]


class Thumbnail(BaseModel):
    """
    A thumbnail for the file. This will only be used if Google Drive cannot
    generate a standard thumbnail.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/files#File.ContentHints.Thumbnail
    """

    image: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The thumbnail data encoded with URL-safe Base64 (RFC 4648 section 5). "
                "A base64-encoded string."
            ),
        ),
        Format("bytes"),
    ] = None
    mime_type: Optional[str] = Field(None, description="The MIME type of the thumbnail.")


class ContentHints(BaseModel):
    """
    Additional information about the content of the file. These fields are never
    populated in responses.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/files#File.ContentHints
    """

    indexable_text: Optional[str] = Field(
        None,
        max_length=131072,
        description=(
            "Text to be indexed for the file to improve fullText queries. This is "
            "limited to 128 KB in length and may contain HTML elements."
        ),
    )
    thumbnail: Optional[Thumbnail] = Field(
        None,
        description=(
            "A thumbnail for the file. This will only be used if Google Drive "
            "cannot generate a standard thumbnail."
        ),
    )


class ImageLocation(BaseModel):
    """
    Geographic location information stored in the image.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/files#File.ImageMediaMetadata.Location
    """

    latitude: Annotated[
        Optional[float],
        Field(None, description="Output only. The latitude stored in the image."),
        Mode("response_only"),
    ] = None
    longitude: Annotated[
        Optional[float],
        Field(None, description="Output only. The longitude stored in the image."),
        Mode("response_only"),
    ] = None
    altitude: Annotated[
        Optional[float],
        Field(None, description="Output only. The altitude stored in the image."),
        Mode("response_only"),
    ] = None


class ImageMediaMetadata(BaseModel):
    """
    Output only. Additional metadata about image media, if available.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/files#File.ImageMediaMetadata
    """

    width: Annotated[
        Optional[int],
        Field(None, description="Output only. The width of the image in pixels."),
        Mode("response_only"),
    ] = None
    height: Annotated[
        Optional[int],
        Field(None, description="Output only. The height of the image in pixels."),
        Mode("response_only"),
    ] = None
    rotation: Annotated[
        Optional[int],
        Field(
            None,
            description=(
                "Output only. The number of clockwise 90 degree rotations applied "
                "from the image's original orientation."
            ),
        ),
        Mode("response_only"),
    ] = None
    location: Annotated[
        Optional[ImageLocation],
        Field(
            None,
            description="Output only. Geographic location information stored in the image.",
        ),
        Mode("response_only"),
    ] = None
    time: Annotated[
        Optional[str],
        Field(
            None,
            description="Output only. The date and time the photo was taken (EXIF DateTime).",
        ),
        Mode("response_only"),
    ] = None
    camera_make: Annotated[
        Optional[str],
        Field(
            None,
            description="Output only. The make of the camera used to create the photo.",
        ),
        Mode("response_only"),
    ] = None
    camera_model: Annotated[
        Optional[str],
        Field(
            None,
            description="Output only. The model of the camera used to create the photo.",
        ),
        Mode("response_only"),
    ] = None
    exposure_time: Annotated[
        Optional[float],
        Field(
            None,
            description="Output only. The length of the exposure, in seconds.",
        ),
        Mode("response_only"),
    ] = None
    aperture: Annotated[
        Optional[float],
        Field(
            None,
            description="Output only. The aperture used to create the photo (f-number).",
        ),
        Mode("response_only"),
    ] = None
    flash_used: Annotated[
        Optional[bool],
        Field(
            None,
            description="Output only. Whether a flash was used to create the photo.",
        ),
        Mode("response_only"),
    ] = None
    focal_length: Annotated[
        Optional[float],
        Field(
            None,
            description="Output only. The focal length used to create the photo, in millimeters.",
        ),
        Mode("response_only"),
    ] = None
    iso_speed: Annotated[
        Optional[int],
        Field(
            None,
            description="Output only. The ISO speed used to create the photo.",
        ),
        Mode("response_only"),
    ] = None
    metering_mode: Annotated[
        Optional[str],
        Field(
            None,
            description="Output only. The metering mode used to create the photo.",
        ),
        Mode("response_only"),
    ] = None
    sensor: Annotated[
        Optional[str],
        Field(
            None,
            description="Output only. The type of sensor used to create the photo.",
        ),
        Mode("response_only"),
    ] = None
    exposure_mode: Annotated[
        Optional[str],
        Field(
            None,
            description="Output only. The exposure mode used to create the photo.",
        ),
        Mode("response_only"),
    ] = None
    color_space: Annotated[
        Optional[str],
        Field(None, description="Output only. The color space of the photo."),
        Mode("response_only"),
    ] = None
    white_balance: Annotated[
        Optional[str],
        Field(
            None,
            description="Output only. The white balance mode used to create the photo.",
        ),
        Mode("response_only"),
    ] = None
    exposure_bias: Annotated[
        Optional[float],
        Field(
            None,
            description="Output only. The exposure bias of the photo (APEX value).",
        ),
        Mode("response_only"),
    ] = None
    max_aperture_value: Annotated[
        Optional[float],
        Field(
            None,
            description=(
                "Output only. The smallest f-number of the lens at the focal length "
                "used to create the photo (APEX value)."
            ),
        ),
        Mode("response_only"),
    ] = None
    subject_distance: Annotated[
        Optional[int],
        Field(
            None,
            description="Output only. The distance to the subject of the photo, in meters.",
        ),
        Mode("response_only"),
    ] = None
    lens: Annotated[
        Optional[str],
        Field(None, description="Output only. The lens used to create the photo."),
        Mode("response_only"),
    ] = None


class VideoMediaMetadata(BaseModel):
    """
    Output only. Additional metadata about video media. This may not be
    available immediately upon upload.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/files#File.VideoMediaMetadata
    """

    width: Annotated[
        Optional[int],
        Field(None, description="Output only. The width of the video in pixels."),
        Mode("response_only"),
    ] = None
    height: Annotated[
        Optional[int],
        Field(None, description="Output only. The height of the video in pixels."),
        Mode("response_only"),
    ] = None
    duration_millis: Annotated[
        Optional[str],
        Field(
            None,
            description="Output only. The duration of the video in milliseconds.",
        ),
        Mode("response_only"),
    ] = None


class ShortcutDetails(BaseModel):
    """
    Information about a shortcut file. Apps creating shortcuts with
    `files.create` must specify the MIME type `application/vnd.google-apps.shortcut`.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/files#File.ShortcutDetails
    """

    target_id: Optional[str] = Field(
        None,
        description=(
            "The ID of the file that this shortcut points to. Can only be set on "
            "`files.create` requests."
        ),
    )
    target_mime_type: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Output only. The MIME type of the file that this shortcut points "
                "to. The value of this field is a snapshot of the target's MIME "
                "type, captured when the shortcut is created."
            ),
        ),
        Mode("response_only"),
    ] = None
    target_resource_key: Annotated[
        Optional[str],
        Field(None, description="Output only. The `resourceKey` for the target file."),
        Mode("response_only"),
    ] = None


class ContentRestriction(BaseModel):
    """
    A restriction for accessing the content of the file.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/files#ContentRestriction
    """

    read_only: Optional[bool] = Field(
        None,
        description=(
            "Whether the content of the file is read-only. If a file is read-only, "
            "a new revision of the file may not be added, comments may not be added "
            "or modified, and the title of the file may not be modified."
        ),
    )
    reason: Optional[str] = Field(
        None,
        description=(
            "Reason for why the content of the file is restricted. This is only "
            "mutable on requests that also set `readOnly=true`."
        ),
    )
    owner_restricted: Optional[bool] = Field(
        None,
        description=(
            "Whether the content restriction can only be modified or removed by a "
            "user who owns the file. For files in shared drives, any user with "
            "`organizer` capabilities can modify or remove this content restriction."
        ),
    )
    type: Annotated[
        Optional[ContentRestrictionType],
        Field(
            None,
            description=(
                "Output only. The type of the content restriction. Currently the "
                "only possible value is `globalContentRestriction`."
            ),
        ),
        Mode("response_only"),
    ] = None
    restricting_user: Annotated[
        Optional[User],
        Field(
            None,
            description=(
                "Output only. The user who set the content restriction. Only "
                "populated if `readOnly=true`."
            ),
        ),
        Mode("response_only"),
    ] = None
    restriction_time: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The time at which the content restriction was set (formatted RFC "
                "3339 timestamp). Only populated if readOnly is true."
            ),
        ),
        Mode("response_only"),
    ] = None
    system_restricted: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Output only. Whether the content restriction was applied by the "
                "system, for example due to an esignature. Users cannot modify or "
                "remove system restricted content restrictions."
            ),
        ),
        Mode("response_only"),
    ] = None


class DownloadRestriction(BaseModel):
    """
    A restriction for copy and download of the file.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/files#DownloadRestriction
    """

    restricted_for_readers: Optional[bool] = Field(
        None,
        description="Whether download and copy is restricted for readers.",
    )
    restricted_for_writers: Optional[bool] = Field(
        None,
        description=(
            "Whether download and copy is restricted for writers. If true, "
            "download is also restricted for readers."
        ),
    )


class DownloadRestrictionsMetadata(BaseModel):
    """
    Download restrictions applied to the file.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/files#DownloadRestrictionsMetadata
    """

    item_download_restriction: Optional[DownloadRestriction] = Field(
        None,
        description=(
            "The download restriction of the file applied directly by the owner or "
            "organizer. This doesn't take into account shared drive settings or "
            "DLP rules."
        ),
    )
    effective_download_restriction_with_context: Annotated[
        Optional[DownloadRestriction],
        Field(
            None,
            description=(
                "Output only. The effective download restriction applied to this "
                "file. This considers all restriction settings and DLP rules."
            ),
        ),
        Mode("response_only"),
    ] = None


class LinkShareMetadata(BaseModel):
    """
    Contains details about the link URLs that clients are using to refer to
    this item.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/files#File.LinkShareMetadata
    """

    security_update_eligible: Annotated[
        Optional[bool],
        Field(
            None,
            description="Output only. Whether the file is eligible for security update.",
        ),
        Mode("response_only"),
    ] = None
    security_update_enabled: Annotated[
        Optional[bool],
        Field(
            None,
            description="Output only. Whether the security update is enabled for this file.",
        ),
        Mode("response_only"),
    ] = None


class LabelField(BaseModel):
    """
    Representation of a field, which is a typed key-value pair.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/LabelField
    """

    kind: Annotated[
        Optional[str],
        Field(None, description="This is always drive#labelField."),
        Mode("response_only"),
    ] = None
    id: Annotated[
        Optional[str],
        Field(None, description="The identifier of this label field."),
        Mode("response_only"),
    ] = None
    value_type: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The field type. While new values may be supported in the future, "
                "the following are currently allowed: `dateString`, `integer`, "
                "`selection`, `text`, `user`."
            ),
        ),
        Mode("response_only"),
    ] = None
    date_string: Annotated[
        Optional[List[str]],
        Field(
            None,
            description=(
                "Only present if valueType is dateString. RFC 3339 formatted date: YYYY-MM-DD."
            ),
        ),
        Mode("response_only"),
    ] = None
    integer: Annotated[
        Optional[List[str]],
        Field(None, description="Only present if `valueType` is `integer`."),
        Mode("response_only"),
    ] = None
    selection: Annotated[
        Optional[List[str]],
        Field(None, description="Only present if `valueType` is `selection`."),
        Mode("response_only"),
    ] = None
    text: Annotated[
        Optional[List[str]],
        Field(None, description="Only present if `valueType` is `text`."),
        Mode("response_only"),
    ] = None
    user: Annotated[
        Optional[List[User]],
        Field(None, description="Only present if `valueType` is `user`."),
        Mode("response_only"),
    ] = None


class Label(BaseModel):
    """
    Representation of a label and its fields.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/Label
    """

    id: Annotated[
        Optional[str],
        Field(None, description="The ID of the label."),
        Mode("response_only"),
    ] = None
    revision_id: Annotated[
        Optional[str],
        Field(None, description="The revision ID of the label."),
        Mode("response_only"),
    ] = None
    kind: Annotated[
        Optional[str],
        Field(None, description="This is always drive#label."),
        Mode("response_only"),
    ] = None
    fields: Annotated[
        Optional[Dict[str, LabelField]],
        Field(
            None,
            description="A map of the fields on the label, keyed by the field's ID.",
        ),
        Mode("response_only"),
    ] = None


class LabelInfo(BaseModel):
    """
    Label information on the file.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/files#File.LabelInfo
    """

    labels: Annotated[
        Optional[List[Label]],
        Field(
            None,
            description=(
                "Output only. The set of labels on the file as requested by the "
                "label IDs in the `includeLabels` parameter. By default, no labels "
                "are returned."
            ),
        ),
        Mode("response_only"),
    ] = None


class DecryptionMetadata(BaseModel):
    """
    Representation of the CSE DecryptionMetadata.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/files#DecryptionMetadata
    """

    wrapped_key: Optional[str] = Field(
        None,
        description=(
            "The URL-safe Base64 encoded wrapped key used to encrypt the contents of the file."
        ),
    )
    kacls_id: Optional[str] = Field(
        None,
        description="The ID of the KACLS (Key ACL Service) used to encrypt the file.",
    )
    kacls_name: Optional[str] = Field(
        None,
        description="The name of the KACLS (Key ACL Service) used to encrypt the file.",
    )
    aes256_gcm_chunk_size: Optional[Aes256GcmChunkSize] = Field(
        None,
        description=(
            "Chunk size used if content was encrypted with the AES 256 GCM Cipher. "
            "Possible values are: `default`, `small`."
        ),
    )
    jwt: Optional[str] = Field(
        None,
        description=(
            "The signed JSON Web Token (JWT) which can be used to authorize the "
            "requesting user with the Key ACL Service (KACLS). The JWT asserts "
            "that the requesting user has at least read permissions on the file."
        ),
    )
    key_format: Optional[str] = Field(
        None,
        description="Key format for the unwrapped key. Must be `tinkAesGcmKey`.",
    )
    encryption_resource_key_hash: Optional[str] = Field(
        None,
        description=(
            "The URL-safe Base64 encoded HMAC-SHA256 digest of the resource "
            "metadata with its DEK (Data Encryption Key)."
        ),
    )


class ClientEncryptionDetails(BaseModel):
    """
    Details about the client-side encryption applied to the file.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/files#ClientEncryptionDetails
    """

    encryption_state: Optional[str] = Field(
        None,
        description=(
            "The encryption state of the file. The values expected here are: "
            "`encrypted`, `unencrypted`."
        ),
    )
    decryption_metadata: Optional[DecryptionMetadata] = Field(
        None,
        description="The metadata used for client-side operations.",
    )


class FileCapabilities(BaseModel):
    """
    Output only. Capabilities the current user has on this file. Each
    capability corresponds to a fine-grained action that a user may take.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/files#File.Capabilities
    """

    can_accept_ownership: Optional[bool] = Field(
        None,
        description=(
            "Output only. Whether the current user is the pending owner of the "
            "file. Not populated for shared drive files."
        ),
    )
    can_access_via_gen_ai: Optional[bool] = Field(
        None,
        description="Whether the current user can access this file via Gen AI features.",
    )
    can_add_children: Optional[bool] = Field(
        None,
        description=(
            "Output only. Whether the current user can add children to this folder. "
            "This is always `false` when the item isn't a folder."
        ),
    )
    can_add_folder_from_another_drive: Optional[bool] = Field(
        None,
        description=(
            "Output only. Whether the current user can add a folder from another "
            "drive (different shared drive or My Drive) to this folder. This is "
            "`false` when the item isn't a folder. Only populated for items in "
            "shared drives."
        ),
    )
    can_add_my_drive_parent: Optional[bool] = Field(
        None,
        description=(
            "Output only. Whether the current user can add a parent for the item "
            "without removing an existing parent in the same request. Not populated "
            "for shared drive files."
        ),
    )
    can_change_copy_requires_writer_permission: Optional[bool] = Field(
        None,
        description=(
            "Output only. Whether the current user can change the "
            "`copyRequiresWriterPermission` restriction of this file."
        ),
    )
    can_change_item_download_restriction: Optional[bool] = Field(
        None,
        description=(
            "Output only. Whether the current user can change the owner or "
            "organizer-applied download restrictions of the file."
        ),
    )
    can_change_security_update_enabled: Optional[bool] = Field(
        None,
        description=(
            "Output only. Whether the current user can change the "
            "`securityUpdateEnabled` field on link share metadata."
        ),
    )
    can_change_viewers_can_copy_content: Annotated[
        Optional[bool],
        Field(None, description="Deprecated: Output only."),
        Mode("disabled"),
    ] = None
    can_comment: Optional[bool] = Field(
        None,
        description="Output only. Whether the current user can comment on this file.",
    )
    can_copy: Optional[bool] = Field(
        None,
        description=(
            "Output only. Whether the current user can copy this file. For an item "
            "in a shared drive, whether the current user can copy non-folder "
            "descendants of this item, or this item if it's not a folder."
        ),
    )
    can_delete: Optional[bool] = Field(
        None,
        description="Output only. Whether the current user can delete this file.",
    )
    can_delete_children: Optional[bool] = Field(
        None,
        description=(
            "Output only. Whether the current user can delete children of this "
            "folder. This is `false` when the item isn't a folder. Only populated "
            "for items in shared drives."
        ),
    )
    can_disable_inherited_permissions: Optional[bool] = Field(
        None,
        description="Whether a user can disable inherited permissions.",
    )
    can_download: Optional[bool] = Field(
        None,
        description="Output only. Whether the current user can download this file.",
    )
    can_edit: Optional[bool] = Field(
        None,
        description=(
            "Output only. Whether the current user can edit this file. Other "
            "factors may limit the type of changes a user can make to a file. For "
            "example, see `canChangeCopyRequiresWriterPermission` or "
            "`canModifyContent`."
        ),
    )
    can_enable_inherited_permissions: Optional[bool] = Field(
        None,
        description="Whether a user can re-enable inherited permissions.",
    )
    can_list_children: Optional[bool] = Field(
        None,
        description=(
            "Output only. Whether the current user can list the children of this "
            "folder. This is always `false` when the item isn't a folder."
        ),
    )
    can_modify_content: Optional[bool] = Field(
        None,
        description="Output only. Whether the current user can modify the content of this file.",
    )
    can_modify_content_restriction: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Deprecated: Output only. Use one of `canModifyEditorContentRestriction`, "
                "`canModifyOwnerContentRestriction`, or `canRemoveContentRestriction`."
            ),
        ),
        Mode("disabled"),
    ] = None
    can_modify_editor_content_restriction: Optional[bool] = Field(
        None,
        description=(
            "Output only. Whether the current user can add or modify content "
            "restrictions on the file which are editor restricted."
        ),
    )
    can_modify_labels: Optional[bool] = Field(
        None,
        description="Output only. Whether the current user can modify the labels on the file.",
    )
    can_modify_owner_content_restriction: Optional[bool] = Field(
        None,
        description=(
            "Output only. Whether the current user can add or modify content "
            "restrictions which are owner restricted."
        ),
    )
    can_move_children_out_of_drive: Optional[bool] = Field(
        None,
        description=(
            "Output only. Whether the current user can move children of this folder "
            "outside of the shared drive. This is `false` when the item isn't a "
            "folder. Only populated for items in shared drives."
        ),
    )
    can_move_children_out_of_team_drive: Annotated[
        Optional[bool],
        Field(
            None,
            description="Deprecated: Output only. Use `canMoveChildrenOutOfDrive` instead.",
        ),
        Mode("disabled"),
    ] = None
    can_move_children_within_drive: Optional[bool] = Field(
        None,
        description=(
            "Output only. Whether the current user can move children of this folder "
            "within this drive. This is `false` when the item isn't a folder."
        ),
    )
    can_move_children_within_team_drive: Annotated[
        Optional[bool],
        Field(
            None,
            description="Deprecated: Output only. Use `canMoveChildrenWithinDrive` instead.",
        ),
        Mode("disabled"),
    ] = None
    can_move_item_into_team_drive: Annotated[
        Optional[bool],
        Field(
            None,
            description="Deprecated: Output only. Use `canMoveItemOutOfDrive` instead.",
        ),
        Mode("disabled"),
    ] = None
    can_move_item_out_of_drive: Optional[bool] = Field(
        None,
        description=(
            "Output only. Whether the current user can move this item outside of "
            "this drive by changing its parent."
        ),
    )
    can_move_item_out_of_team_drive: Annotated[
        Optional[bool],
        Field(
            None,
            description="Deprecated: Output only. Use `canMoveItemOutOfDrive` instead.",
        ),
        Mode("disabled"),
    ] = None
    can_move_item_within_drive: Optional[bool] = Field(
        None,
        description="Output only. Whether the current user can move this item within this drive.",
    )
    can_move_item_within_team_drive: Annotated[
        Optional[bool],
        Field(
            None,
            description="Deprecated: Output only. Use `canMoveItemWithinDrive` instead.",
        ),
        Mode("disabled"),
    ] = None
    can_move_team_drive_item: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Deprecated: Output only. Use `canMoveItemWithinDrive` or "
                "`canMoveItemOutOfDrive` instead."
            ),
        ),
        Mode("disabled"),
    ] = None
    can_read_drive: Optional[bool] = Field(
        None,
        description=(
            "Output only. Whether the current user can read the shared drive to "
            "which this file belongs. Only populated for items in shared drives."
        ),
    )
    can_read_labels: Optional[bool] = Field(
        None,
        description="Output only. Whether the current user can read the labels on the file.",
    )
    can_read_revisions: Optional[bool] = Field(
        None,
        description=(
            "Output only. Whether the current user can read the revisions resource "
            "of this file. For a shared drive item, whether revisions of non-folder "
            "descendants of this item, or this item if it's not a folder, can be "
            "read."
        ),
    )
    can_read_team_drive: Annotated[
        Optional[bool],
        Field(None, description="Deprecated: Output only. Use `canReadDrive` instead."),
        Mode("disabled"),
    ] = None
    can_remove_children: Optional[bool] = Field(
        None,
        description=(
            "Output only. Whether the current user can remove children from this "
            "folder. This is always `false` when the item isn't a folder. For a "
            "folder in a shared drive, use `canDeleteChildren` or `canTrashChildren` "
            "instead."
        ),
    )
    can_remove_content_restriction: Optional[bool] = Field(
        None,
        description=(
            "Output only. Whether there's a content restriction on the file that "
            "can be removed by the current user."
        ),
    )
    can_remove_my_drive_parent: Optional[bool] = Field(
        None,
        description=(
            "Output only. Whether the current user can remove a parent from the "
            "item without adding another parent in the same request. Not populated "
            "for shared drive files."
        ),
    )
    can_rename: Optional[bool] = Field(
        None,
        description="Output only. Whether the current user can rename this file.",
    )
    can_share: Optional[bool] = Field(
        None,
        description=(
            "Output only. Whether the current user can modify the sharing settings for this file."
        ),
    )
    can_start_approval: Optional[bool] = Field(
        None,
        description="Whether the current user can start an approval on the file.",
    )
    can_trash: Optional[bool] = Field(
        None,
        description="Output only. Whether the current user can move this file to trash.",
    )
    can_trash_children: Optional[bool] = Field(
        None,
        description=(
            "Output only. Whether the current user can trash children of this "
            "folder. This is `false` when the item isn't a folder. Only populated "
            "for items in shared drives."
        ),
    )
    can_untrash: Optional[bool] = Field(
        None,
        description="Output only. Whether the current user can restore this file from trash.",
    )


class File(BaseModel):
    """
    The metadata for a file. Some resource methods (such as `files.update`)
    require a `fileId`. Use the `files.list` method to retrieve the ID for a
    file.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/files#File
    """

    id: Optional[str] = Field(
        None,
        description=(
            "The ID of the file. This is generated by the server for new files. A "
            "pre-generated ID from `files.generateIds` may be supplied on create."
        ),
    )
    name: Optional[str] = Field(
        None,
        description=(
            "The name of the file. This isn't necessarily unique within a folder. "
            "Note that for immutable items such as the top-level folders of shared "
            "drives, the My Drive root folder, and the Application Data folder, "
            "the name is constant."
        ),
    )
    mime_type: Optional[str] = Field(
        None,
        description=(
            "The MIME type of the file. Google Drive attempts to automatically "
            "detect an appropriate value from uploaded content, if no value is "
            "provided. The value cannot be changed unless a new revision is "
            "uploaded. If a file is created with a Google Doc MIME type, the "
            "uploaded content is imported, if possible. The supported import "
            "formats are published in the `about` resource. For a folder, use "
            "`application/vnd.google-apps.folder`. For a shortcut, use "
            "`application/vnd.google-apps.shortcut`."
        ),
    )
    description: Optional[str] = Field(None, description="A short description of the file.")
    parents: Optional[List[str]] = Field(
        None,
        description=(
            "The ID of the parent folder containing the file. A file can only have "
            "one parent folder; specifying multiple parents isn't supported. If "
            "not specified as part of a create request, the file is placed directly "
            "in the user's My Drive folder. If not specified as part of a copy "
            "request, the file inherits any discoverable parent of the source file. "
            "Update requests must use the `addParents` and `removeParents` "
            "parameters to modify the parents list."
        ),
    )
    starred: Optional[bool] = Field(None, description="Whether the user has starred the file.")
    trashed: Optional[bool] = Field(
        None,
        description=(
            "Whether the file has been trashed, either explicitly or from a trashed "
            "parent folder. Only the owner may trash a file, but other users can "
            "still access the file in the owner's trash until it's permanently "
            "deleted."
        ),
    )
    folder_color_rgb: Optional[str] = Field(
        None,
        description=(
            "The color for a folder or a shortcut to a folder as an RGB hex string. "
            "The supported colors are published in the `folderColorPalette` field "
            "of the `about` resource. If an unsupported color is specified, the "
            "closest color in the palette is used instead."
        ),
    )
    original_filename: Optional[str] = Field(
        None,
        description=(
            "The original filename of the uploaded content if available, or else "
            "the original value of the `name` field. This is only available for "
            "files with binary content in Google Drive."
        ),
    )
    writers_can_share: Optional[bool] = Field(
        None,
        description=(
            "Whether users with only `writer` permission can modify the file's "
            "permissions. Not populated for items in shared drives."
        ),
    )
    copy_requires_writer_permission: Optional[bool] = Field(
        None,
        description=(
            "Whether the options to copy, print, or download this file should be "
            "disabled for readers and commenters."
        ),
    )
    viewers_can_copy_content: Annotated[
        Optional[bool],
        Field(None, description="Deprecated: Use `copyRequiresWriterPermission` instead."),
        Mode("disabled"),
    ] = None
    created_time: Optional[str] = Field(
        None,
        description="The time at which the file was created (RFC 3339 date-time).",
    )
    modified_time: Optional[str] = Field(
        None,
        description=(
            "The last time the file was modified by anyone (RFC 3339 date-time). "
            "Note that setting `modifiedTime` also updates `modifiedByMeTime` for "
            "the user."
        ),
    )
    viewed_by_me_time: Optional[str] = Field(
        None,
        description="The last time the file was viewed by the user (RFC 3339 date-time).",
    )
    properties: Optional[Dict[str, str]] = Field(
        None,
        description=(
            "A collection of arbitrary key-value pairs which are visible to all "
            "apps. Entries with null values are cleared in update and copy requests."
        ),
    )
    app_properties: Optional[Dict[str, str]] = Field(
        None,
        description=(
            "A collection of arbitrary key-value pairs which are private to the "
            "requesting app. Entries with null values are cleared in update and "
            "copy requests. These properties can only be retrieved using an "
            "authenticated request. An authenticated request uses an access token "
            "obtained with an OAuth 2.0 client ID. You cannot use an API key to "
            "retrieve private properties."
        ),
    )
    content_hints: Optional[ContentHints] = Field(
        None,
        description=(
            "Additional information about the content of the file. These fields "
            "are never populated in responses."
        ),
    )
    shortcut_details: Optional[ShortcutDetails] = Field(
        None,
        description="Information about a shortcut file.",
    )
    content_restrictions: Optional[List[ContentRestriction]] = Field(
        None,
        description=(
            "Restrictions for accessing the content of the file. Only populated if "
            "such a restriction exists."
        ),
    )
    inherited_permissions_disabled: Optional[bool] = Field(
        None,
        description=(
            "Whether this file has inherited permissions disabled. Inherited "
            "permissions are enabled by default."
        ),
    )
    download_restrictions: Optional[DownloadRestrictionsMetadata] = Field(
        None,
        description="Download restrictions applied on the file.",
    )
    client_encryption_details: Optional[ClientEncryptionDetails] = Field(
        None,
        description=(
            "Client Side Encryption related details. Contains details about the "
            "encryption state of the file and details regarding the encryption "
            "mechanism that clients need to use when decrypting the contents of "
            "this item. This will only be present on files and not on folders or "
            "shortcuts."
        ),
    )

    kind: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Output only. Identifies what kind of resource this is. Value: the "
                'fixed string `"drive#file"`.'
            ),
        ),
        Mode("response_only"),
    ] = None
    drive_id: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Output only. ID of the shared drive the file resides in. Only "
                "populated for items in shared drives."
            ),
        ),
        Mode("response_only"),
    ] = None
    team_drive_id: Annotated[
        Optional[str],
        Field(None, description="Deprecated: Output only. Use `driveId` instead."),
        Mode("disabled"),
    ] = None
    file_extension: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Output only. The final component of `fullFileExtension`. This is "
                "only available for files with binary content in Google Drive."
            ),
        ),
        Mode("response_only"),
    ] = None
    full_file_extension: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Output only. The full file extension extracted from the `name` "
                "field. May contain multiple concatenated extensions, such as "
                '"tar.gz". This is only available for files with binary content in '
                "Google Drive. This is automatically updated when the `name` field "
                "changes, however it's not cleared if the new name doesn't contain "
                "a valid extension."
            ),
        ),
        Mode("response_only"),
    ] = None
    md5_checksum: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Output only. The MD5 checksum for the content of the file. This is "
                "only applicable to files with binary content in Google Drive."
            ),
        ),
        Mode("response_only"),
    ] = None
    sha1_checksum: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Output only. The SHA1 checksum associated with this file, if "
                "available. This field is only populated for files with content "
                "stored in Google Drive; it's not populated for Docs Editors or "
                "shortcut files."
            ),
        ),
        Mode("response_only"),
    ] = None
    sha256_checksum: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Output only. The SHA256 checksum associated with this file, if "
                "available. This field is only populated for files with content "
                "stored in Google Drive; it's not populated for Docs Editors or "
                "shortcut files."
            ),
        ),
        Mode("response_only"),
    ] = None
    size: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Output only. Size in bytes of blobs and Google Workspace editor "
                "files. Won't be populated for files that have no size, like "
                "shortcuts and folders."
            ),
        ),
        Mode("response_only"),
    ] = None
    quota_bytes_used: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Output only. The number of storage quota bytes used by the file. "
                "This includes the head revision as well as previous revisions with "
                "`keepForever` enabled."
            ),
        ),
        Mode("response_only"),
    ] = None
    version: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Output only. A monotonically increasing version number for the "
                "file. This reflects every change made to the file on the server, "
                "even those not visible to the user."
            ),
        ),
        Mode("response_only"),
    ] = None
    head_revision_id: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Output only. The ID of the file's head revision. This is currently "
                "only available for files with binary content in Google Drive."
            ),
        ),
        Mode("response_only"),
    ] = None
    viewed_by_me: Annotated[
        Optional[bool],
        Field(None, description="Output only. Whether the file has been viewed by this user."),
        Mode("response_only"),
    ] = None
    modified_by_me: Annotated[
        Optional[bool],
        Field(
            None,
            description="Output only. Whether the file has been modified by this user.",
        ),
        Mode("response_only"),
    ] = None
    modified_by_me_time: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Output only. The last time the file was modified by the user (RFC 3339 date-time)."
            ),
        ),
        Mode("response_only"),
    ] = None
    shared_with_me_time: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Output only. The time at which the file was shared with the user, "
                "if applicable (RFC 3339 date-time)."
            ),
        ),
        Mode("response_only"),
    ] = None
    shared: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Output only. Whether the file has been shared. Not populated for "
                "items in shared drives."
            ),
        ),
        Mode("response_only"),
    ] = None
    owned_by_me: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Output only. Whether the user owns the file. Not populated for "
                "items in shared drives."
            ),
        ),
        Mode("response_only"),
    ] = None
    owners: Annotated[
        Optional[List[User]],
        Field(
            None,
            description=(
                "Output only. The owner of this file. Only certain legacy files may "
                "have more than one owner. This field isn't populated for items in "
                "shared drives."
            ),
        ),
        Mode("response_only"),
    ] = None
    last_modifying_user: Annotated[
        Optional[User],
        Field(
            None,
            description=(
                "Output only. The last user to modify the file. This field is only "
                "populated when the last modification was performed by a signed-in "
                "user."
            ),
        ),
        Mode("response_only"),
    ] = None
    sharing_user: Annotated[
        Optional[User],
        Field(
            None,
            description=(
                "Output only. The user who shared the file with the requesting user, if applicable."
            ),
        ),
        Mode("response_only"),
    ] = None
    trashing_user: Annotated[
        Optional[User],
        Field(
            None,
            description=(
                "Output only. If the file has been explicitly trashed, the user who "
                "trashed it. Only populated for items in shared drives."
            ),
        ),
        Mode("response_only"),
    ] = None
    trashed_time: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The time that the item was trashed (RFC 3339 date-time). Only "
                "populated for items in shared drives."
            ),
        ),
        Mode("response_only"),
    ] = None
    explicitly_trashed: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Output only. Whether the file has been explicitly trashed, as "
                "opposed to recursively trashed from a parent folder."
            ),
        ),
        Mode("response_only"),
    ] = None
    web_view_link: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Output only. A link for opening the file in a relevant Google "
                "editor or viewer in a browser."
            ),
        ),
        Mode("response_only"),
    ] = None
    web_content_link: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Output only. A link for downloading the content of the file in a "
                "browser. This is only available for files with binary content in "
                "Google Drive."
            ),
        ),
        Mode("response_only"),
    ] = None
    export_links: Annotated[
        Optional[Dict[str, str]],
        Field(
            None,
            description="Output only. Links for exporting Docs Editors files to specific formats.",
        ),
        Mode("response_only"),
    ] = None
    thumbnail_link: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Output only. A short-lived link to the file's thumbnail, if "
                "available. Typically lasts on the order of hours. Not intended for "
                "direct usage on web applications due to Cross-Origin Resource "
                "Sharing (CORS) policies. Consider using a proxy server. Only "
                "populated when the requesting app can access the file's content. "
                "If the file isn't shared publicly, the URL returned in "
                "`files.thumbnailLink` must be fetched using a credentialed request."
            ),
        ),
        Mode("response_only"),
    ] = None
    thumbnail_version: Annotated[
        Optional[str],
        Field(
            None,
            description="Output only. The thumbnail version for use in thumbnail cache invalidation.",
        ),
        Mode("response_only"),
    ] = None
    has_thumbnail: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Output only. Whether this file has a thumbnail. This doesn't "
                "indicate whether the requesting app has access to the thumbnail. "
                "To check access, look for the presence of the thumbnailLink field."
            ),
        ),
        Mode("response_only"),
    ] = None
    icon_link: Annotated[
        Optional[str],
        Field(
            None,
            description="Output only. A static, unauthenticated link to the file's icon.",
        ),
        Mode("response_only"),
    ] = None
    spaces: Annotated[
        Optional[List[str]],
        Field(
            None,
            description=(
                "Output only. The list of spaces which contain the file. The "
                "currently supported values are `drive`, `appDataFolder`, and "
                "`photos`."
            ),
        ),
        Mode("response_only"),
    ] = None
    is_app_authorized: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Output only. Whether the file was created or opened by the requesting app."
            ),
        ),
        Mode("response_only"),
    ] = None
    has_augmented_permissions: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Output only. Whether there are permissions directly on this file. "
                "This field is only populated for items in shared drives."
            ),
        ),
        Mode("response_only"),
    ] = None
    permissions: Annotated[
        Optional[List[Permission]],
        Field(
            None,
            description=(
                "Output only. The full list of permissions for the file. This is "
                "only available if the requesting user can share the file. Not "
                "populated for items in shared drives."
            ),
        ),
        Mode("response_only"),
    ] = None
    permission_ids: Annotated[
        Optional[List[str]],
        Field(
            None,
            description="Output only. List of permission IDs for users with access to this file.",
        ),
        Mode("response_only"),
    ] = None
    resource_key: Annotated[
        Optional[str],
        Field(
            None,
            description="Output only. A key needed to access the item via a shared link.",
        ),
        Mode("response_only"),
    ] = None
    capabilities: Annotated[
        Optional[FileCapabilities],
        Field(
            None,
            description=(
                "Output only. Capabilities the current user has on this file. Each "
                "capability corresponds to a fine-grained action that a user may "
                "take."
            ),
        ),
        Mode("response_only"),
    ] = None
    image_media_metadata: Annotated[
        Optional[ImageMediaMetadata],
        Field(
            None,
            description="Output only. Additional metadata about image media, if available.",
        ),
        Mode("response_only"),
    ] = None
    video_media_metadata: Annotated[
        Optional[VideoMediaMetadata],
        Field(
            None,
            description=(
                "Output only. Additional metadata about video media. This may not "
                "be available immediately upon upload."
            ),
        ),
        Mode("response_only"),
    ] = None
    link_share_metadata: Annotated[
        Optional[LinkShareMetadata],
        Field(
            None,
            description=(
                "Contains details about the link URLs that clients are using to refer to this item."
            ),
        ),
        Mode("response_only"),
    ] = None
    label_info: Annotated[
        Optional[LabelInfo],
        Field(None, description="Label information on the file."),
        Mode("response_only"),
    ] = None
