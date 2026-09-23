# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Response models for the Firecrawl POST /scrape endpoint.

All fields use Mode("response_only") — they are populated by the API response
and never sent in requests. The LLM reads these rich typed models; the framework
handles wire-format conversion transparently.

API Reference: https://docs.firecrawl.dev/api-reference/endpoint/scrape
"""

from __future__ import annotations

from typing import Annotated, Any, List, Optional

from pydantic import BaseModel, Field

from charter.types import Mode

# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


class ScrapeMetadata(BaseModel):
    """Metadata extracted from the scraped page.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/scrape
    """

    title: Annotated[
        Optional[Any],
        Field(
            None, description="Title extracted from the page, can be a string or array of strings"
        ),
        Mode("response_only"),
    ]
    description: Annotated[
        Optional[Any],
        Field(
            None,
            description="Description extracted from the page, can be a string or array of strings",
        ),
        Mode("response_only"),
    ]
    language: Annotated[
        Optional[Any],
        Field(
            None,
            description="Language extracted from the page, can be a string or array of strings",
        ),
        Mode("response_only"),
    ]
    source_url: Annotated[
        Optional[str],
        Field(
            None,
            description="The original URL that was requested. May differ from the page's final URL if redirects occurred.",
        ),
        Mode("response_only"),
    ]
    url: Annotated[
        Optional[str],
        Field(
            None, description="The final URL of the page after all redirects have been followed."
        ),
        Mode("response_only"),
    ]
    keywords: Annotated[
        Optional[Any],
        Field(
            None,
            description="Keywords extracted from the page, can be a string or array of strings",
        ),
        Mode("response_only"),
    ]
    og_locale_alternate: Annotated[
        Optional[List[str]],
        Field(None, description="Alternative locales for the page"),
        Mode("response_only"),
    ]
    status_code: Annotated[
        Optional[int], Field(None, description="The status code of the page"), Mode("response_only")
    ]
    error: Annotated[
        Optional[str],
        Field(None, description="The error message of the page"),
        Mode("response_only"),
    ]


# ---------------------------------------------------------------------------
# Actions result types
# ---------------------------------------------------------------------------


class ActionsScrape(BaseModel):
    """Content captured by a scrape action during page interaction.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/scrape
    """

    url: Annotated[
        Optional[str],
        Field(None, description="URL of the page at the time of the scrape action"),
        Mode("response_only"),
    ]
    html: Annotated[
        Optional[str],
        Field(None, description="HTML content captured by the scrape action"),
        Mode("response_only"),
    ]


class JavascriptReturn(BaseModel):
    """Return value from an executeJavascript action.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/scrape
    """

    type_: Annotated[
        Optional[str],
        Field(None, description="The JavaScript type of the returned value"),
        Mode("response_only"),
    ]


class ScrapeActionsResult(BaseModel):
    """Results of all actions performed on the page before content capture.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/scrape
    """

    screenshots: Annotated[
        Optional[List[str]],
        Field(
            None,
            description="Screenshot URLs, in the same order as the screenshot actions provided.",
        ),
        Mode("response_only"),
    ]
    scrapes: Annotated[
        Optional[List[ActionsScrape]],
        Field(
            None, description="Scrape contents, in the same order as the scrape actions provided."
        ),
        Mode("response_only"),
    ]
    javascript_returns: Annotated[
        Optional[List[JavascriptReturn]],
        Field(
            None,
            description="JavaScript return values, in the same order as the executeJavascript actions provided.",
        ),
        Mode("response_only"),
    ]
    pdfs: Annotated[
        Optional[List[str]],
        Field(None, description="PDFs generated, in the same order as the pdf actions provided."),
        Mode("response_only"),
    ]


# ---------------------------------------------------------------------------
# Change tracking
# ---------------------------------------------------------------------------


class ChangeTrackingResult(BaseModel):
    """Change tracking information comparing the current page against a previous scrape.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/scrape
    """

    previous_scrape_at: Annotated[
        Optional[str],
        Field(
            None,
            description="The timestamp of the previous scrape that the current page is being compared against. Null if no previous scrape exists.",
        ),
        Mode("response_only"),
    ]
    change_status: Annotated[
        Optional[str],
        Field(
            None,
            description="The result of the comparison between the two page versions. 'new' means this page did not exist before, 'same' means content has not changed, 'changed' means content has changed, 'removed' means the page was removed.",
        ),
        Mode("response_only"),
    ]
    visibility: Annotated[
        Optional[str],
        Field(None, description="The visibility of the current page/URL."),
        Mode("response_only"),
    ]
    diff: Annotated[
        Optional[str],
        Field(
            None,
            description="Git-style diff of changes when using 'git-diff' mode. Only present when the mode is set to 'git-diff'.",
        ),
        Mode("response_only"),
    ]
    json_result: Annotated[
        Optional[Any],
        Field(None, alias="json", description="JSON comparison results when using 'json' mode."),
        Mode("response_only"),
    ]


# ---------------------------------------------------------------------------
# Branding
# ---------------------------------------------------------------------------


class BrandingColors(BaseModel):
    """Brand colors extracted from the page.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/scrape
    """

    primary: Annotated[
        Optional[str], Field(None, description="Primary brand color (hex)."), Mode("response_only")
    ]
    secondary: Annotated[
        Optional[str],
        Field(None, description="Secondary brand color (hex)."),
        Mode("response_only"),
    ]
    accent: Annotated[
        Optional[str], Field(None, description="Accent color (hex)."), Mode("response_only")
    ]
    background: Annotated[
        Optional[str], Field(None, description="Background color (hex)."), Mode("response_only")
    ]
    text_primary: Annotated[
        Optional[str], Field(None, description="Primary text color (hex)."), Mode("response_only")
    ]
    text_secondary: Annotated[
        Optional[str], Field(None, description="Secondary text color (hex)."), Mode("response_only")
    ]
    link: Annotated[
        Optional[str], Field(None, description="Link color (hex)."), Mode("response_only")
    ]
    success: Annotated[
        Optional[str],
        Field(None, description="Success/positive color (hex)."),
        Mode("response_only"),
    ]
    warning: Annotated[
        Optional[str], Field(None, description="Warning color (hex)."), Mode("response_only")
    ]
    error: Annotated[
        Optional[str], Field(None, description="Error/danger color (hex)."), Mode("response_only")
    ]


class BrandingFont(BaseModel):
    """A font family used on the page.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/scrape
    """

    family: Annotated[
        Optional[str], Field(None, description="Font family name."), Mode("response_only")
    ]


class BrandingTypographyFontFamilies(BaseModel):
    """Font families by role.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/scrape
    """

    primary: Annotated[
        Optional[str], Field(None, description="Primary font family."), Mode("response_only")
    ]
    heading: Annotated[
        Optional[str], Field(None, description="Heading font family."), Mode("response_only")
    ]
    code: Annotated[
        Optional[str], Field(None, description="Code/monospace font family."), Mode("response_only")
    ]


class BrandingTypographyFontSizes(BaseModel):
    """Font sizes for different text levels.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/scrape
    """

    h1: Annotated[
        Optional[str], Field(None, description="Font size for h1 headings."), Mode("response_only")
    ]
    h2: Annotated[
        Optional[str], Field(None, description="Font size for h2 headings."), Mode("response_only")
    ]
    h3: Annotated[
        Optional[str], Field(None, description="Font size for h3 headings."), Mode("response_only")
    ]
    body: Annotated[
        Optional[str], Field(None, description="Font size for body text."), Mode("response_only")
    ]


class BrandingTypographyFontWeights(BaseModel):
    """Font weight definitions.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/scrape
    """

    light: Annotated[
        Optional[int], Field(None, description="Light font weight value."), Mode("response_only")
    ]
    regular: Annotated[
        Optional[int], Field(None, description="Regular font weight value."), Mode("response_only")
    ]
    medium: Annotated[
        Optional[int], Field(None, description="Medium font weight value."), Mode("response_only")
    ]
    bold: Annotated[
        Optional[int], Field(None, description="Bold font weight value."), Mode("response_only")
    ]


class BrandingTypographyLineHeights(BaseModel):
    """Line height values for different text types.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/scrape
    """

    heading: Annotated[
        Optional[str], Field(None, description="Line height for headings."), Mode("response_only")
    ]
    body: Annotated[
        Optional[str], Field(None, description="Line height for body text."), Mode("response_only")
    ]


class BrandingTypography(BaseModel):
    """Detailed typography information extracted from the page.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/scrape
    """

    font_families: Annotated[
        Optional[BrandingTypographyFontFamilies],
        Field(None, description="Font families by role."),
        Mode("response_only"),
    ]
    font_sizes: Annotated[
        Optional[BrandingTypographyFontSizes],
        Field(None, description="Font sizes for different text levels."),
        Mode("response_only"),
    ]
    font_weights: Annotated[
        Optional[BrandingTypographyFontWeights],
        Field(None, description="Font weight definitions."),
        Mode("response_only"),
    ]
    line_heights: Annotated[
        Optional[BrandingTypographyLineHeights],
        Field(None, description="Line height values for different text types."),
        Mode("response_only"),
    ]


class BrandingButtonStyle(BaseModel):
    """Primary button styles.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/scrape
    """

    background: Annotated[
        Optional[str], Field(None, description="Button background color."), Mode("response_only")
    ]
    text_color: Annotated[
        Optional[str], Field(None, description="Button text color."), Mode("response_only")
    ]
    border_radius: Annotated[
        Optional[str], Field(None, description="Button border radius."), Mode("response_only")
    ]


class BrandingButtonSecondaryStyle(BaseModel):
    """Secondary button styles.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/scrape
    """

    background: Annotated[
        Optional[str], Field(None, description="Button background color."), Mode("response_only")
    ]
    text_color: Annotated[
        Optional[str], Field(None, description="Button text color."), Mode("response_only")
    ]
    border_color: Annotated[
        Optional[str], Field(None, description="Button border color."), Mode("response_only")
    ]
    border_radius: Annotated[
        Optional[str], Field(None, description="Button border radius."), Mode("response_only")
    ]


class BrandingComponents(BaseModel):
    """UI component styles extracted from the page.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/scrape
    """

    button_primary: Annotated[
        Optional[BrandingButtonStyle],
        Field(None, description="Primary button styles."),
        Mode("response_only"),
    ]
    button_secondary: Annotated[
        Optional[BrandingButtonSecondaryStyle],
        Field(None, description="Secondary button styles."),
        Mode("response_only"),
    ]
    input: Annotated[
        Optional[Any], Field(None, description="Input field styles."), Mode("response_only")
    ]


class BrandingSpacing(BaseModel):
    """Spacing and layout information extracted from the page.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/scrape
    """

    base_unit: Annotated[
        Optional[int],
        Field(None, description="Base spacing unit in pixels."),
        Mode("response_only"),
    ]
    border_radius: Annotated[
        Optional[str], Field(None, description="Default border radius."), Mode("response_only")
    ]
    padding: Annotated[
        Optional[Any], Field(None, description="Padding values."), Mode("response_only")
    ]
    margins: Annotated[
        Optional[Any], Field(None, description="Margin values."), Mode("response_only")
    ]


class BrandingImages(BaseModel):
    """Brand images extracted from the page.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/scrape
    """

    logo: Annotated[
        Optional[str], Field(None, description="Logo image URL."), Mode("response_only")
    ]
    favicon: Annotated[
        Optional[str], Field(None, description="Favicon URL."), Mode("response_only")
    ]
    og_image: Annotated[
        Optional[str], Field(None, description="Open Graph image URL."), Mode("response_only")
    ]


class BrandingResult(BaseModel):
    """Branding information extracted from the page when the 'branding' format is requested.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/scrape
    """

    color_scheme: Annotated[
        Optional[str],
        Field(None, description="The detected color scheme of the page."),
        Mode("response_only"),
    ]
    logo: Annotated[
        Optional[str], Field(None, description="URL of the primary logo."), Mode("response_only")
    ]
    colors: Annotated[
        Optional[BrandingColors],
        Field(None, description="Brand colors extracted from the page."),
        Mode("response_only"),
    ]
    fonts: Annotated[
        Optional[List[BrandingFont]],
        Field(None, description="Array of font families used on the page."),
        Mode("response_only"),
    ]
    typography: Annotated[
        Optional[BrandingTypography],
        Field(None, description="Detailed typography information."),
        Mode("response_only"),
    ]
    spacing: Annotated[
        Optional[BrandingSpacing],
        Field(None, description="Spacing and layout information."),
        Mode("response_only"),
    ]
    components: Annotated[
        Optional[BrandingComponents],
        Field(None, description="UI component styles."),
        Mode("response_only"),
    ]
    icons: Annotated[
        Optional[Any], Field(None, description="Icon style information."), Mode("response_only")
    ]
    images: Annotated[
        Optional[BrandingImages], Field(None, description="Brand images."), Mode("response_only")
    ]
    animations: Annotated[
        Optional[Any],
        Field(None, description="Animation and transition settings."),
        Mode("response_only"),
    ]
    layout: Annotated[
        Optional[Any],
        Field(None, description="Layout configuration (grid, header/footer heights)."),
        Mode("response_only"),
    ]
    personality: Annotated[
        Optional[Any],
        Field(None, description="Brand personality traits (tone, energy, target audience)."),
        Mode("response_only"),
    ]


# ---------------------------------------------------------------------------
# Top-level data and response
# ---------------------------------------------------------------------------


class ScrapeData(BaseModel):
    """All content and metadata extracted from the scraped page.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/scrape
    """

    markdown: Annotated[
        Optional[str],
        Field(None, description="Markdown content of the page."),
        Mode("response_only"),
    ]
    summary: Annotated[
        Optional[str],
        Field(None, description="Summary of the page if 'summary' is in formats."),
        Mode("response_only"),
    ]
    html: Annotated[
        Optional[str],
        Field(None, description="Cleaned HTML of the page if 'html' is in formats."),
        Mode("response_only"),
    ]
    raw_html: Annotated[
        Optional[str],
        Field(
            None,
            description="The exact, unmodified HTML as received from the page if 'rawHtml' is in formats.",
        ),
        Mode("response_only"),
    ]
    screenshot: Annotated[
        Optional[str],
        Field(
            None,
            description="Screenshot of the page if 'screenshot' is in formats. Screenshots expire after 24 hours and can no longer be downloaded.",
        ),
        Mode("response_only"),
    ]
    links: Annotated[
        Optional[List[str]],
        Field(None, description="List of links on the page if 'links' is in formats."),
        Mode("response_only"),
    ]
    actions: Annotated[
        Optional[ScrapeActionsResult],
        Field(
            None,
            description="Results of the actions specified in the 'actions' parameter. Only present if the 'actions' parameter was provided in the request.",
        ),
        Mode("response_only"),
    ]
    metadata: Annotated[
        Optional[ScrapeMetadata],
        Field(None, description="Metadata extracted from the page."),
        Mode("response_only"),
    ]
    warning: Annotated[
        Optional[str],
        Field(
            None,
            description="Can be displayed when using LLM Extraction. Warning message will let you know any issues with the extraction.",
        ),
        Mode("response_only"),
    ]
    change_tracking: Annotated[
        Optional[ChangeTrackingResult],
        Field(
            None,
            description="Change tracking information if 'changeTracking' is in formats. Only present when the 'changeTracking' format is requested.",
        ),
        Mode("response_only"),
    ]
    branding: Annotated[
        Optional[BrandingResult],
        Field(
            None,
            description="Branding information extracted from the page if 'branding' is in formats.",
        ),
        Mode("response_only"),
    ]


class ScrapeResponse(BaseModel):
    """Root response from the Firecrawl POST /scrape endpoint.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/scrape
    """

    success: Annotated[
        Optional[bool],
        Field(None, description="Whether the scrape was successful."),
        Mode("response_only"),
    ]
    data: Annotated[
        Optional[ScrapeData],
        Field(None, description="The scraped page data."),
        Mode("response_only"),
    ]
