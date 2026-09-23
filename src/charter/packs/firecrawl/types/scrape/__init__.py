# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

from charter.packs.firecrawl.types.common import (
    Action,
    Format,
    PdfParser,
    ScrapeLocation,
    Viewport,
)

from .actions import ScrapeRequest, ScrapeStatusRequest
from .interact_actions import ScrapeInteractRequest, ScrapeInteractStopRequest
from .models import (
    ActionsScrape,
    BrandingButtonSecondaryStyle,
    BrandingButtonStyle,
    BrandingColors,
    BrandingComponents,
    BrandingFont,
    BrandingImages,
    BrandingResult,
    BrandingSpacing,
    BrandingTypography,
    BrandingTypographyFontFamilies,
    BrandingTypographyFontSizes,
    BrandingTypographyFontWeights,
    BrandingTypographyLineHeights,
    ChangeTrackingResult,
    JavascriptReturn,
    ScrapeActionsResult,
    ScrapeData,
    ScrapeMetadata,
    ScrapeResponse,
)

__all__ = [
    # Request schemas
    "ScrapeRequest",
    "ScrapeStatusRequest",
    "ScrapeInteractRequest",
    "ScrapeInteractStopRequest",
    # Nested request types
    "Viewport",
    "Format",
    "PdfParser",
    "Action",
    "ScrapeLocation",
    # Metadata
    "ScrapeMetadata",
    # Actions result types
    "ActionsScrape",
    "JavascriptReturn",
    "ScrapeActionsResult",
    # Change tracking
    "ChangeTrackingResult",
    # Branding
    "BrandingColors",
    "BrandingFont",
    "BrandingTypographyFontFamilies",
    "BrandingTypographyFontSizes",
    "BrandingTypographyFontWeights",
    "BrandingTypographyLineHeights",
    "BrandingTypography",
    "BrandingButtonStyle",
    "BrandingButtonSecondaryStyle",
    "BrandingComponents",
    "BrandingSpacing",
    "BrandingImages",
    "BrandingResult",
    # Top-level response
    "ScrapeData",
    "ScrapeResponse",
]
