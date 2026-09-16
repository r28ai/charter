"""
Spreadsheet resource types for the Google Sheets pack.

Field names, types, enums and descriptions follow the Sheets API v4 reference.
Server-set fields are ``Mode("response_only")``; deprecated colour and filter
map fields are ``Mode("disabled")``. The ``FieldMask`` fields live on the edits
in :mod:`.requests`, where ``Format("field_mask")`` marks them.

Classes are alphabetical, except for the Developer Preview comment types, which
are kept together at the end beside the ``CommentThread`` they describe.

API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets
"""
from __future__ import annotations

from typing import Annotated, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from charter.types import Mode

# Enums

BaselineValueFormatComparisonType = Literal[
    "COMPARISON_TYPE_UNDEFINED",
    "ABSOLUTE_DIFFERENCE",
    "PERCENTAGE_DIFFERENCE",
]

BasicChartSeriesTargetAxis = Literal[
    "BASIC_CHART_AXIS_POSITION_UNSPECIFIED",
    "BOTTOM_AXIS",
    "LEFT_AXIS",
    "RIGHT_AXIS",
]

BasicChartSeriesType = Literal[
    "BASIC_CHART_TYPE_UNSPECIFIED",
    "BAR",
    "LINE",
    "AREA",
    "COLUMN",
    "SCATTER",
    "COMBO",
    "STEPPED_AREA",
]

BasicChartSpecCompareMode = Literal[
    "BASIC_CHART_COMPARE_MODE_UNSPECIFIED",
    "DATUM",
    "CATEGORY",
]

BasicChartSpecLegendPosition = Literal[
    "BASIC_CHART_LEGEND_POSITION_UNSPECIFIED",
    "BOTTOM_LEGEND",
    "LEFT_LEGEND",
    "RIGHT_LEGEND",
    "TOP_LEGEND",
    "NO_LEGEND",
]

BasicChartSpecStackedType = Literal[
    "BASIC_CHART_STACKED_TYPE_UNSPECIFIED",
    "NOT_STACKED",
    "STACKED",
    "PERCENT_STACKED",
]

BooleanConditionType = Literal[
    "CONDITION_TYPE_UNSPECIFIED",
    "NUMBER_GREATER",
    "NUMBER_GREATER_THAN_EQ",
    "NUMBER_LESS",
    "NUMBER_LESS_THAN_EQ",
    "NUMBER_EQ",
    "NUMBER_NOT_EQ",
    "NUMBER_BETWEEN",
    "NUMBER_NOT_BETWEEN",
    "TEXT_CONTAINS",
    "TEXT_NOT_CONTAINS",
    "TEXT_STARTS_WITH",
    "TEXT_ENDS_WITH",
    "TEXT_EQ",
    "TEXT_IS_EMAIL",
    "TEXT_IS_URL",
    "DATE_EQ",
    "DATE_BEFORE",
    "DATE_AFTER",
    "DATE_ON_OR_BEFORE",
    "DATE_ON_OR_AFTER",
    "DATE_BETWEEN",
    "DATE_NOT_BETWEEN",
    "DATE_IS_VALID",
    "ONE_OF_RANGE",
    "ONE_OF_LIST",
    "BLANK",
    "NOT_BLANK",
    "CUSTOM_FORMULA",
    "BOOLEAN",
    "TEXT_NOT_EQ",
    "DATE_NOT_EQ",
    "FILTER_EXPRESSION",
]

BorderStyle = Literal[
    "STYLE_UNSPECIFIED",
    "DOTTED",
    "DASHED",
    "SOLID",
    "SOLID_MEDIUM",
    "SOLID_THICK",
    "NONE",
    "DOUBLE",
]

BubbleChartSpecLegendPosition = Literal[
    "BUBBLE_CHART_LEGEND_POSITION_UNSPECIFIED",
    "BOTTOM_LEGEND",
    "LEFT_LEGEND",
    "RIGHT_LEGEND",
    "TOP_LEGEND",
    "NO_LEGEND",
    "INSIDE_LEGEND",
]

CellFormatHyperlinkDisplayType = Literal[
    "HYPERLINK_DISPLAY_TYPE_UNSPECIFIED",
    "LINKED",
    "PLAIN_TEXT",
]

CellFormatTextDirection = Literal[
    "TEXT_DIRECTION_UNSPECIFIED",
    "LEFT_TO_RIGHT",
    "RIGHT_TO_LEFT",
]

ChartAxisViewWindowOptionsViewWindowMode = Literal[
    "DEFAULT_VIEW_WINDOW_MODE",
    "VIEW_WINDOW_MODE_UNSUPPORTED",
    "EXPLICIT",
    "PRETTY",
]

ChartDateTimeRuleType = Literal[
    "CHART_DATE_TIME_RULE_TYPE_UNSPECIFIED",
    "SECOND",
    "MINUTE",
    "HOUR",
    "HOUR_MINUTE",
    "HOUR_MINUTE_AMPM",
    "DAY_OF_WEEK",
    "DAY_OF_YEAR",
    "DAY_OF_MONTH",
    "DAY_MONTH",
    "MONTH",
    "QUARTER",
    "YEAR",
    "YEAR_MONTH",
    "YEAR_QUARTER",
    "YEAR_MONTH_DAY",
]

ChartSpecHiddenDimensionStrategy = Literal[
    "CHART_HIDDEN_DIMENSION_STRATEGY_UNSPECIFIED",
    "SKIP_HIDDEN_ROWS_AND_COLUMNS",
    "SKIP_HIDDEN_ROWS",
    "SKIP_HIDDEN_COLUMNS",
    "SHOW_ALL",
]

ConditionValueRelativeDate = Literal[
    "RELATIVE_DATE_UNSPECIFIED",
    "PAST_YEAR",
    "PAST_MONTH",
    "PAST_WEEK",
    "YESTERDAY",
    "TODAY",
    "TOMORROW",
]

DataExecutionStatusErrorCode = Literal[
    "DATA_EXECUTION_ERROR_CODE_UNSPECIFIED",
    "TIMED_OUT",
    "TOO_MANY_ROWS",
    "TOO_MANY_COLUMNS",
    "TOO_MANY_CELLS",
    "ENGINE",
    "PARAMETER_INVALID",
    "UNSUPPORTED_DATA_TYPE",
    "DUPLICATE_COLUMN_NAMES",
    "INTERRUPTED",
    "CONCURRENT_QUERY",
    "OTHER",
    "TOO_MANY_CHARS_PER_CELL",
    "DATA_NOT_FOUND",
    "PERMISSION_DENIED",
    "MISSING_COLUMN_ALIAS",
    "OBJECT_NOT_FOUND",
    "OBJECT_IN_ERROR_STATE",
    "OBJECT_SPEC_INVALID",
    "DATA_EXECUTION_CANCELLED",
]

DataExecutionStatusState = Literal[
    "DATA_EXECUTION_STATE_UNSPECIFIED",
    "NOT_STARTED",
    "RUNNING",
    "CANCELLING",
    "SUCCEEDED",
    "FAILED",
]

DataLabelPlacement = Literal[
    "DATA_LABEL_PLACEMENT_UNSPECIFIED",
    "CENTER",
    "LEFT",
    "RIGHT",
    "ABOVE",
    "BELOW",
    "INSIDE_END",
    "INSIDE_BASE",
    "OUTSIDE_END",
]

DataLabelType = Literal[
    "DATA_LABEL_TYPE_UNSPECIFIED",
    "NONE",
    "DATA",
    "CUSTOM",
]

DataSourceRefreshScheduleRefreshScope = Literal[
    "DATA_SOURCE_REFRESH_SCOPE_UNSPECIFIED",
    "ALL_DATA_SOURCES",
]

DataSourceRefreshWeeklyScheduleDaysOfWeekItem = Literal[
    "DAY_OF_WEEK_UNSPECIFIED",
    "MONDAY",
    "TUESDAY",
    "WEDNESDAY",
    "THURSDAY",
    "FRIDAY",
    "SATURDAY",
    "SUNDAY",
]

DataSourceTableColumnSelectionType = Literal[
    "DATA_SOURCE_TABLE_COLUMN_SELECTION_TYPE_UNSPECIFIED",
    "SELECTED",
    "SYNC_ALL",
]

DateTimeRuleType = Literal[
    "DATE_TIME_RULE_TYPE_UNSPECIFIED",
    "SECOND",
    "MINUTE",
    "HOUR",
    "HOUR_MINUTE",
    "HOUR_MINUTE_AMPM",
    "DAY_OF_WEEK",
    "DAY_OF_YEAR",
    "DAY_OF_MONTH",
    "DAY_MONTH",
    "MONTH",
    "QUARTER",
    "YEAR",
    "YEAR_MONTH",
    "YEAR_QUARTER",
    "YEAR_MONTH_DAY",
]

DelimiterType = Literal[
    "DELIMITER_TYPE_UNSPECIFIED",
    "COMMA",
    "SEMICOLON",
    "PERIOD",
    "SPACE",
    "CUSTOM",
    "AUTODETECT",
]

DeveloperMetadataLocationMatchingStrategy = Literal[
    "DEVELOPER_METADATA_LOCATION_MATCHING_STRATEGY_UNSPECIFIED",
    "EXACT_LOCATION",
    "INTERSECTING_LOCATION",
]

DeveloperMetadataLocationType = Literal[
    "DEVELOPER_METADATA_LOCATION_TYPE_UNSPECIFIED",
    "ROW",
    "COLUMN",
    "SHEET",
    "SPREADSHEET",
]

DeveloperMetadataVisibility = Literal[
    "DEVELOPER_METADATA_VISIBILITY_UNSPECIFIED",
    "DOCUMENT",
    "PROJECT",
]

Dimension = Literal[
    "DIMENSION_UNSPECIFIED",
    "ROWS",
    "COLUMNS",
]

CommentsViewMode = Literal[
    "COMMENTS_VIEW_MODE_UNSPECIFIED",
    "COMMENTS_VIEW_MODE_DEFAULT_FOR_CURRENT_ACCESS",
    "COMMENTS_VIEW_MODE_OMITTED",
    "COMMENTS_VIEW_MODE_INCLUDED",
]

CommentUpdateState = Literal[
    "COMMENT_UPDATE_STATE_UNSPECIFIED",
    "NO_UPDATES_REQUESTED",
    "ALL_SAVED",
    "ALL_FAILED_UNKNOWN_REASON",
]

CommentActionType = Literal[
    "COMMENT_ACTION_TYPE_UNSPECIFIED",
    "NO_COMMENT_ACTION_CHANGE",
    "RESOLVE",
    "REOPEN",
]

CommentThreadStatus = Literal[
    "STATUS_UNSPECIFIED",
    "OPEN",
    "RESOLVED",
]

ErrorValueType = Literal[
    "ERROR_TYPE_UNSPECIFIED",
    "ERROR",
    "NULL_VALUE",
    "DIVIDE_BY_ZERO",
    "VALUE",
    "REF",
    "NAME",
    "NUM",
    "N_A",
    "LOADING",
]

HistogramChartSpecLegendPosition = Literal[
    "HISTOGRAM_CHART_LEGEND_POSITION_UNSPECIFIED",
    "BOTTOM_LEGEND",
    "LEFT_LEGEND",
    "RIGHT_LEGEND",
    "TOP_LEGEND",
    "NO_LEGEND",
    "INSIDE_LEGEND",
]

HorizontalAlign = Literal[
    "HORIZONTAL_ALIGN_UNSPECIFIED",
    "LEFT",
    "CENTER",
    "RIGHT",
]

InterpolationPointType = Literal[
    "INTERPOLATION_POINT_TYPE_UNSPECIFIED",
    "MIN",
    "MAX",
    "NUMBER",
    "PERCENT",
    "PERCENTILE",
]

LineStyleType = Literal[
    "LINE_DASH_TYPE_UNSPECIFIED",
    "INVISIBLE",
    "CUSTOM",
    "SOLID",
    "DOTTED",
    "MEDIUM_DASHED",
    "MEDIUM_DASHED_DOTTED",
    "LONG_DASHED",
    "LONG_DASHED_DOTTED",
]

MergeType = Literal[
    "MERGE_ALL",
    "MERGE_COLUMNS",
    "MERGE_ROWS",
]

NumberFormatType = Literal[
    "NUMBER_FORMAT_TYPE_UNSPECIFIED",
    "TEXT",
    "NUMBER",
    "PERCENT",
    "CURRENCY",
    "DATE",
    "TIME",
    "DATE_TIME",
    "SCIENTIFIC",
]

OrgChartSpecNodeSize = Literal[
    "ORG_CHART_LABEL_SIZE_UNSPECIFIED",
    "SMALL",
    "MEDIUM",
    "LARGE",
]

PasteOrientation = Literal[
    "NORMAL",
    "TRANSPOSE",
]

PasteType = Literal[
    "PASTE_NORMAL",
    "PASTE_VALUES",
    "PASTE_FORMAT",
    "PASTE_NO_BORDERS",
    "PASTE_FORMULA",
    "PASTE_DATA_VALIDATION",
    "PASTE_CONDITIONAL_FORMATTING",
]

PersonPropertiesDisplayFormat = Literal[
    "DISPLAY_FORMAT_UNSPECIFIED",
    "DEFAULT",
    "LAST_NAME_COMMA_FIRST_NAME",
    "EMAIL",
]

PieChartSpecLegendPosition = Literal[
    "PIE_CHART_LEGEND_POSITION_UNSPECIFIED",
    "BOTTOM_LEGEND",
    "LEFT_LEGEND",
    "RIGHT_LEGEND",
    "TOP_LEGEND",
    "NO_LEGEND",
    "LABELED_LEGEND",
]

PivotTableValueLayout = Literal[
    "HORIZONTAL",
    "VERTICAL",
]

PivotValueCalculatedDisplayType = Literal[
    "PIVOT_VALUE_CALCULATED_DISPLAY_TYPE_UNSPECIFIED",
    "PERCENT_OF_ROW_TOTAL",
    "PERCENT_OF_COLUMN_TOTAL",
    "PERCENT_OF_GRAND_TOTAL",
]

PivotValueSummarizeFunction = Literal[
    "PIVOT_STANDARD_VALUE_FUNCTION_UNSPECIFIED",
    "SUM",
    "COUNTA",
    "COUNT",
    "COUNTUNIQUE",
    "AVERAGE",
    "MAX",
    "MIN",
    "MEDIAN",
    "PRODUCT",
    "STDEV",
    "STDEVP",
    "VAR",
    "VARP",
    "CUSTOM",
    "NONE",
]

PointStyleShape = Literal[
    "POINT_SHAPE_UNSPECIFIED",
    "CIRCLE",
    "DIAMOND",
    "HEXAGON",
    "PENTAGON",
    "SQUARE",
    "STAR",
    "TRIANGLE",
    "X_MARK",
]

RecalculationInterval = Literal[
    "RECALCULATION_INTERVAL_UNSPECIFIED",
    "ON_CHANGE",
    "MINUTE",
    "HOUR",
]

RefreshCancellationStatusErrorCode = Literal[
    "REFRESH_CANCELLATION_ERROR_CODE_UNSPECIFIED",
    "EXECUTION_NOT_FOUND",
    "CANCEL_PERMISSION_DENIED",
    "QUERY_EXECUTION_COMPLETED",
    "CONCURRENT_CANCELLATION",
    "CANCEL_OTHER_ERROR",
]

RefreshCancellationStatusState = Literal[
    "REFRESH_CANCELLATION_STATE_UNSPECIFIED",
    "CANCEL_SUCCEEDED",
    "CANCEL_FAILED",
]

ScorecardChartSpecAggregateType = Literal[
    "CHART_AGGREGATE_TYPE_UNSPECIFIED",
    "AVERAGE",
    "COUNT",
    "MAX",
    "MEDIAN",
    "MIN",
    "SUM",
]

ScorecardChartSpecNumberFormatSource = Literal[
    "CHART_NUMBER_FORMAT_SOURCE_UNDEFINED",
    "FROM_DATA",
    "CUSTOM",
]

SheetType = Literal[
    "SHEET_TYPE_UNSPECIFIED",
    "GRID",
    "OBJECT",
    "DATA_SOURCE",
]

SortOrder = Literal[
    "SORT_ORDER_UNSPECIFIED",
    "ASCENDING",
    "DESCENDING",
]

TableColumnPropertiesColumnType = Literal[
    "COLUMN_TYPE_UNSPECIFIED",
    "DOUBLE",
    "CURRENCY",
    "PERCENT",
    "DATE",
    "TIME",
    "DATE_TIME",
    "TEXT",
    "BOOLEAN",
    "DROPDOWN",
    "FILES_CHIP",
    "PEOPLE_CHIP",
    "FINANCE_CHIP",
    "PLACE_CHIP",
    "RATINGS_CHIP",
]

ThemeColorType = Literal[
    "THEME_COLOR_TYPE_UNSPECIFIED",
    "TEXT",
    "BACKGROUND",
    "ACCENT1",
    "ACCENT2",
    "ACCENT3",
    "ACCENT4",
    "ACCENT5",
    "ACCENT6",
    "LINK",
]

VerticalAlign = Literal[
    "VERTICAL_ALIGN_UNSPECIFIED",
    "TOP",
    "MIDDLE",
    "BOTTOM",
]

WaterfallChartSpecStackedType = Literal[
    "WATERFALL_STACKED_TYPE_UNSPECIFIED",
    "STACKED",
    "SEQUENTIAL",
]

WrapStrategy = Literal[
    "WRAP_STRATEGY_UNSPECIFIED",
    "OVERFLOW_CELL",
    "LEGACY_WRAP",
    "CLIP",
    "WRAP",
]


class BandedRange(BaseModel):
    """
    A banded (alternating colors) range in a sheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/sheets#BandedRange
    """
    column_properties: Optional[BandingProperties] = Field(
        default=None, description="Properties for column bands. These properties are applied on a column- by-column basis throughout all the columns in the range. At least one of row_properties or column_properties must be specified.",
    )

    row_properties: Optional[BandingProperties] = Field(
        default=None, description="Properties for row bands. These properties are applied on a row-by-row basis throughout all the rows in the range. At least one of row_properties or column_properties must be specified.",
    )

    range: Optional[GridRange] = Field(
        default=None, description="The range over which these properties are applied.",
    )

    banded_range_id: Optional[int] = Field(
        default=None, description="The ID of the banded range. If unset, refer to banded_range_reference.",
    )

    banded_range_reference: Annotated[
        Optional[str],
        Mode("response_only"), Field(default=None, description="Output only. The reference of the banded range, used to identify the ID that is not supported by the banded_range_id."),
    ] = None


class BandingProperties(BaseModel):
    """
    Properties referring a single dimension (either row or column). If both BandedRange.row_properties and BandedRange.column_properties are set, the fill colors are applied to cells according to the following rules: * header_color and footer_color take priority over band colors. * first_band_color takes priority over second_band_color. * row_properties takes priority over column_properties. For example, the first row color takes priority over the first column color, but the first column color takes priority over the second row color. Similarly, the row header takes priority over the column header in the top left cell, but the column header takes priority over the first row color if the row header is not set.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/sheets#BandingProperties
    """
    second_band_color: Annotated[
        Optional[Color],
        Mode("disabled"), Field(default=None, description="The second color that is alternating. (Required) Deprecated: Use second_band_color_style."),
    ] = None

    header_color: Annotated[
        Optional[Color],
        Mode("disabled"), Field(default=None, description="The color of the first row or column. If this field is set, the first row or column is filled with this color and the colors alternate between first_band_color and second_band_color starting from the second row or column. Otherwise, the first row or column is filled with first_band_color and the colors proceed to alternate as they normally would. Deprecated: Use header_color_style."),
    ] = None

    first_band_color_style: Optional[ColorStyle] = Field(
        default=None, description="The first color that is alternating. (Required) If first_band_color is also set, this field takes precedence.",
    )

    footer_color_style: Optional[ColorStyle] = Field(
        default=None, description="The color of the last row or column. If this field is not set, the last row or column is filled with either first_band_color or second_band_color, depending on the color of the previous row or column. If footer_color is also set, this field takes precedence.",
    )

    footer_color: Annotated[
        Optional[Color],
        Mode("disabled"), Field(default=None, description="The color of the last row or column. If this field is not set, the last row or column is filled with either first_band_color or second_band_color, depending on the color of the previous row or column. Deprecated: Use footer_color_style."),
    ] = None

    first_band_color: Annotated[
        Optional[Color],
        Mode("disabled"), Field(default=None, description="The first color that is alternating. (Required) Deprecated: Use first_band_color_style."),
    ] = None

    header_color_style: Optional[ColorStyle] = Field(
        default=None, description="The color of the first row or column. If this field is set, the first row or column is filled with this color and the colors alternate between first_band_color and second_band_color starting from the second row or column. Otherwise, the first row or column is filled with first_band_color and the colors proceed to alternate as they normally would. If header_color is also set, this field takes precedence.",
    )

    second_band_color_style: Optional[ColorStyle] = Field(
        default=None, description="The second color that is alternating. (Required) If second_band_color is also set, this field takes precedence.",
    )


class BaselineValueFormat(BaseModel):
    """
    Formatting options for baseline value.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/charts#BaselineValueFormat
    """
    description: Optional[str] = Field(
        default=None, description="Description which is appended after the baseline value. This field is optional.",
    )

    text_format: Optional[TextFormat] = Field(
        default=None, description="Text formatting options for baseline value. The link field is not supported.",
    )

    positive_color: Annotated[
        Optional[Color],
        Mode("disabled"), Field(default=None, description="Color to be used, in case baseline value represents a positive change for key value. This field is optional. Deprecated: Use positive_color_style."),
    ] = None

    position: Optional[TextPosition] = Field(
        default=None, description="Specifies the horizontal text positioning of baseline value. This field is optional. If not specified, default positioning is used.",
    )

    comparison_type: Optional[BaselineValueFormatComparisonType] = Field(
        default=None, description="The comparison type of key value with baseline value.",
    )

    negative_color_style: Optional[ColorStyle] = Field(
        default=None, description="Color to be used, in case baseline value represents a negative change for key value. This field is optional. If negative_color is also set, this field takes precedence.",
    )

    positive_color_style: Optional[ColorStyle] = Field(
        default=None, description="Color to be used, in case baseline value represents a positive change for key value. This field is optional. If positive_color is also set, this field takes precedence.",
    )

    negative_color: Annotated[
        Optional[Color],
        Mode("disabled"), Field(default=None, description="Color to be used, in case baseline value represents a negative change for key value. This field is optional. Deprecated: Use negative_color_style."),
    ] = None


class BasicChartAxis(BaseModel):
    """
    An axis of the chart. A chart may not have more than one axis per axis position.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/charts#BasicChartAxis
    """
    title: Optional[str] = Field(
        default=None, description="The title of this axis. If set, this overrides any title inferred from headers of the data.",
    )

    format: Optional[TextFormat] = Field(
        default=None, description="The format of the title. Only valid if the axis is not associated with the domain. The link field is not supported.",
    )

    view_window_options: Optional[ChartAxisViewWindowOptions] = Field(
        default=None, description="The view window options for this axis.",
    )

    title_text_position: Optional[TextPosition] = Field(
        default=None, description="The axis title text position.",
    )

    position: Optional[BasicChartSeriesTargetAxis] = Field(
        default=None, description="The position of this axis.",
    )


class BasicChartDomain(BaseModel):
    """
    The domain of a chart. For example, if charting stock prices over time, this would be the date.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/charts#BasicChartDomain
    """
    domain: Optional[ChartData] = Field(
        default=None, description="The data of the domain. For example, if charting stock prices over time, this is the data representing the dates.",
    )

    reversed: Optional[bool] = Field(
        default=None, description="True to reverse the order of the domain values (horizontal axis).",
    )


class BasicChartSeries(BaseModel):
    """
    A single series of data in a chart. For example, if charting stock prices over time, multiple series may exist, one for the "Open Price", "High Price", "Low Price" and "Close Price".

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/charts#BasicChartSeries
    """
    series: Optional[ChartData] = Field(
        default=None, description="The data being visualized in this chart series.",
    )

    data_label: Optional[DataLabel] = Field(
        default=None, description="Information about the data labels for this series.",
    )

    point_style: Optional[PointStyle] = Field(
        default=None, description="The style for points associated with this series. Valid only if the chartType is AREA, LINE, or SCATTER. COMBO charts are also supported if the series chart type is AREA, LINE, or SCATTER. If empty, a default point style is used.",
    )

    type: Optional[BasicChartSeriesType] = Field(
        default=None, description="The type of this series. Valid only if the chartType is COMBO. Different types will change the way the series is visualized. Only LINE, AREA, and COLUMN are supported.",
    )

    target_axis: Optional[BasicChartSeriesTargetAxis] = Field(
        default=None, description="The minor axis that will specify the range of values for this series. For example, if charting stocks over time, the \"Volume\" series may want to be pinned to the right with the prices pinned to the left, because the scale of trading volume is different than the scale of prices. It is an error to specify an axis that isn't a valid minor axis for the chart's type.",
    )

    style_overrides: Optional[List[BasicSeriesDataPointStyleOverride]] = Field(
        default=None, description="Style override settings for series data points.",
    )

    color: Annotated[
        Optional[Color],
        Mode("disabled"), Field(default=None, description="The color for elements (such as bars, lines, and points) associated with this series. If empty, a default color is used. Deprecated: Use color_style."),
    ] = None

    line_style: Optional[LineStyle] = Field(
        default=None, description="The line style of this series. Valid only if the chartType is AREA, LINE, or SCATTER. COMBO charts are also supported if the series chart type is AREA or LINE.",
    )

    color_style: Optional[ColorStyle] = Field(
        default=None, description="The color for elements (such as bars, lines, and points) associated with this series. If empty, a default color is used. If color is also set, this field takes precedence.",
    )


class BasicChartSpec(BaseModel):
    """
    The specification for a basic chart. See BasicChartType for the list of charts this supports.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/charts#BasicChartSpec
    """
    legend_position: Optional[BasicChartSpecLegendPosition] = Field(
        default=None, description="The position of the chart legend.",
    )

    chart_type: Optional[BasicChartSeriesType] = Field(
        default=None, description="The type of the chart.",
    )

    stacked_type: Optional[BasicChartSpecStackedType] = Field(
        default=None, description="The stacked type for charts that support vertical stacking. Applies to Area, Bar, Column, Combo, and Stepped Area charts.",
    )

    series: Optional[List[BasicChartSeries]] = Field(
        default=None, description="The data this chart is visualizing.",
    )

    compare_mode: Optional[BasicChartSpecCompareMode] = Field(
        default=None, description="The behavior of tooltips and data highlighting when hovering on data and chart area.",
    )

    domains: Optional[List[BasicChartDomain]] = Field(
        default=None, description="The domain of data this is charting. Only a single domain is supported.",
    )

    three_dimensional: Optional[bool] = Field(
        default=None, description="True to make the chart 3D. Applies to Bar and Column charts.",
    )

    interpolate_nulls: Optional[bool] = Field(
        default=None, description="If some values in a series are missing, gaps may appear in the chart (e.g, segments of lines in a line chart will be missing). To eliminate these gaps set this to true. Applies to Line, Area, and Combo charts.",
    )

    line_smoothing: Optional[bool] = Field(
        default=None, description="Gets whether all lines should be rendered smooth or straight by default. Applies to Line charts.",
    )

    header_count: Optional[int] = Field(
        default=None, description="The number of rows or columns in the data that are \"headers\". If not set, Google Sheets will guess how many rows are headers based on the data. (Note that BasicChartAxis.title may override the axis title inferred from the header values.)",
    )

    total_data_label: Optional[DataLabel] = Field(
        default=None, description="Controls whether to display additional data labels on stacked charts which sum the total value of all stacked values at each value along the domain axis. These data labels can only be set when chart_type is one of AREA, BAR, COLUMN, COMBO or STEPPED_AREA and stacked_type is either STACKED or PERCENT_STACKED. In addition, for COMBO, this will only be supported if there is only one type of stackable series type or one type has more series than the others and each of the other types have no more than one series. For example, if a chart has two stacked bar series and one area series, the total data labels will be supported. If it has three bar series and two area series, total data labels are not allowed. Neither CUSTOM nor placement can be set on the total_data_label.",
    )

    axis: Optional[List[BasicChartAxis]] = Field(
        default=None, description="The axis on the chart.",
    )


class BasicFilter(BaseModel):
    """
    The default filter associated with a sheet. For more information, see [Manage data visibility with filters](https://developers.google.com/workspace/sheets/api/guides/filters).

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/sheets#BasicFilter
    """
    criteria: Annotated[
        Optional[Dict[str, FilterCriteria]],
        Mode("disabled"), Field(default=None, description="The criteria for showing/hiding values per column. The map's key is the column index, and the value is the criteria for that column. This field is deprecated in favor of filter_specs."),
    ] = None

    table_id: Optional[str] = Field(
        default=None, description="The table this filter is backed by, if any. When writing, only one of range or table_id may be set.",
    )

    sort_specs: Optional[List[SortSpec]] = Field(
        default=None, description="The sort order per column. Later specifications are used when values are equal in the earlier specifications.",
    )

    range: Optional[GridRange] = Field(
        default=None, description="The range the filter covers.",
    )

    filter_specs: Optional[List[FilterSpec]] = Field(
        default=None, description="The filter criteria per column. Both criteria and filter_specs are populated in responses. If both fields are specified in an update request, this field takes precedence.",
    )


class BasicSeriesDataPointStyleOverride(BaseModel):
    """
    Style override settings for a single series data point.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/charts#BasicSeriesDataPointStyleOverride
    """
    color_style: Optional[ColorStyle] = Field(
        default=None, description="Color of the series data point. If empty, the series default is used. If color is also set, this field takes precedence.",
    )

    point_style: Optional[PointStyle] = Field(
        default=None, description="Point style of the series data point. Valid only if the chartType is AREA, LINE, or SCATTER. COMBO charts are also supported if the series chart type is AREA, LINE, or SCATTER. If empty, the series default is used.",
    )

    color: Annotated[
        Optional[Color],
        Mode("disabled"), Field(default=None, description="Color of the series data point. If empty, the series default is used. Deprecated: Use color_style."),
    ] = None

    index: Optional[int] = Field(
        default=None, description="The zero-based index of the series data point.",
    )


class BatchClearValuesByDataFilterResponse(BaseModel):
    """
    The response when clearing a range of values selected with DataFilters in a spreadsheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets#BatchClearValuesByDataFilterResponse
    """
    cleared_ranges: Optional[List[str]] = Field(
        default=None, description="The ranges that were cleared, in [A1 notation](https://developers.google.com/workspace/sheets/api/guides/concepts#cell). If the requests are for an unbounded range or a range larger than the bounds of the sheet, this is the actual ranges that were cleared, bounded to the sheet's limits.",
    )

    spreadsheet_id: Optional[str] = Field(
        default=None, description="The spreadsheet the updates were applied to.",
    )


class BigQueryDataSourceSpec(BaseModel):
    """
    The specification of a BigQuery data source that's connected to a sheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets#BigQueryDataSourceSpec
    """
    query_spec: Optional[BigQueryQuerySpec] = Field(
        default=None, description="A BigQueryQuerySpec.",
    )

    project_id: Optional[str] = Field(
        default=None, description="The ID of a BigQuery enabled Google Cloud project with a billing account attached. For any queries executed against the data source, the project is charged.",
    )

    table_spec: Optional[BigQueryTableSpec] = Field(
        default=None, description="A BigQueryTableSpec.",
    )

    @model_validator(mode="after")
    def _at_most_one(self) -> BigQueryDataSourceSpec:
        provided = [n for n in ('query_spec', 'table_spec') if getattr(self, n) is not None]
        if len(provided) > 1:
            raise ValueError(
                f"At most one of 'query_spec', 'table_spec' may be set, found: {provided}"
            )
        return self


class BigQueryQuerySpec(BaseModel):
    """
    Specifies a custom BigQuery query.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets#BigQueryQuerySpec
    """
    raw_query: Optional[str] = Field(
        default=None, description="The raw query string.",
    )


class BigQueryTableSpec(BaseModel):
    """
    Specifies a BigQuery table definition. Only [native tables](https://cloud.google.com/bigquery/docs/tables-intro) are allowed.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets#BigQueryTableSpec
    """
    dataset_id: Optional[str] = Field(
        default=None, description="The BigQuery dataset id.",
    )

    table_project_id: Optional[str] = Field(
        default=None, description="The ID of a BigQuery project the table belongs to. If not specified, the project_id is assumed.",
    )

    table_id: Optional[str] = Field(
        default=None, description="The BigQuery table id.",
    )


class BooleanCondition(BaseModel):
    """
    A condition that can evaluate to true or false. BooleanConditions are used by conditional formatting, data validation, and the criteria in filters.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/other#BooleanCondition
    """
    values: Optional[List[ConditionValue]] = Field(
        default=None, description="The values of the condition. The number of supported values depends on the condition type. Some support zero values, others one or two values, and ConditionType.ONE_OF_LIST supports an arbitrary number of values.",
    )

    type: Optional[BooleanConditionType] = Field(
        default=None, description="The type of condition.",
    )


class BooleanRule(BaseModel):
    """
    A rule that may or may not match, depending on the condition.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/sheets#BooleanRule
    """
    format: Optional[CellFormat] = Field(
        default=None, description="The format to apply. Conditional formatting can only apply a subset of formatting: bold, italic, strikethrough, foreground color and, background color.",
    )

    condition: Optional[BooleanCondition] = Field(
        default=None, description="The condition of the rule. If the condition evaluates to true, the format is applied.",
    )


class Border(BaseModel):
    """
    A border along a cell.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/cells#Border
    """
    width: Annotated[
        Optional[int],
        Mode("disabled"), Field(default=None, description="The width of the border, in pixels. Deprecated; the width is determined by the \"style\" field."),
    ] = None

    color_style: Optional[ColorStyle] = Field(
        default=None, description="The color of the border. If color is also set, this field takes precedence.",
    )

    style: Optional[BorderStyle] = Field(
        default=None, description="The style of the border.",
    )

    color: Annotated[
        Optional[Color],
        Mode("disabled"), Field(default=None, description="The color of the border. Deprecated: Use color_style."),
    ] = None


class Borders(BaseModel):
    """
    The borders of the cell.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/cells#Borders
    """
    left: Optional[Border] = Field(
        default=None, description="The left border of the cell.",
    )

    bottom: Optional[Border] = Field(
        default=None, description="The bottom border of the cell.",
    )

    top: Optional[Border] = Field(
        default=None, description="The top border of the cell.",
    )

    right: Optional[Border] = Field(
        default=None, description="The right border of the cell.",
    )


class BubbleChartSpec(BaseModel):
    """
    A bubble chart.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/charts#BubbleChartSpec
    """
    group_ids: Optional[ChartData] = Field(
        default=None, description="The data containing the bubble group IDs. All bubbles with the same group ID are drawn in the same color. If bubble_sizes is specified then this field must also be specified but may contain blank values. This field is optional.",
    )

    bubble_border_color_style: Optional[ColorStyle] = Field(
        default=None, description="The bubble border color. If bubble_border_color is also set, this field takes precedence.",
    )

    bubble_labels: Optional[ChartData] = Field(
        default=None, description="The data containing the bubble labels. These do not need to be unique.",
    )

    domain: Optional[ChartData] = Field(
        default=None, description="The data containing the bubble x-values. These values locate the bubbles in the chart horizontally.",
    )

    bubble_max_radius_size: Optional[int] = Field(
        default=None, description="The max radius size of the bubbles, in pixels. If specified, the field must be a positive value.",
    )

    series: Optional[ChartData] = Field(
        default=None, description="The data containing the bubble y-values. These values locate the bubbles in the chart vertically.",
    )

    bubble_border_color: Annotated[
        Optional[Color],
        Mode("disabled"), Field(default=None, description="The bubble border color. Deprecated: Use bubble_border_color_style."),
    ] = None

    bubble_opacity: Optional[float] = Field(
        default=None, description="The opacity of the bubbles between 0 and 1.0. 0 is fully transparent and 1 is fully opaque.",
    )

    bubble_text_style: Optional[TextFormat] = Field(
        default=None, description="The format of the text inside the bubbles. Strikethrough, underline, and link are not supported.",
    )

    legend_position: Optional[BubbleChartSpecLegendPosition] = Field(
        default=None, description="Where the legend of the chart should be drawn.",
    )

    bubble_min_radius_size: Optional[int] = Field(
        default=None, description="The minimum radius size of the bubbles, in pixels. If specific, the field must be a positive value.",
    )

    bubble_sizes: Optional[ChartData] = Field(
        default=None, description="The data containing the bubble sizes. Bubble sizes are used to draw the bubbles at different sizes relative to each other. If specified, group_ids must also be specified. This field is optional.",
    )


class CandlestickChartSpec(BaseModel):
    """
    A candlestick chart.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/charts#CandlestickChartSpec
    """
    data: Optional[List[CandlestickData]] = Field(
        default=None, description="The Candlestick chart data. Only one CandlestickData is supported.",
    )

    domain: Optional[CandlestickDomain] = Field(
        default=None, description="The domain data (horizontal axis) for the candlestick chart. String data will be treated as discrete labels, other data will be treated as continuous values.",
    )


class CandlestickData(BaseModel):
    """
    The Candlestick chart data, each containing the low, open, close, and high values for a series.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/charts#CandlestickData
    """
    high_series: Optional[CandlestickSeries] = Field(
        default=None, description="The range data (vertical axis) for the high/maximum value for each candle. This is the top of the candle's center line.",
    )

    close_series: Optional[CandlestickSeries] = Field(
        default=None, description="The range data (vertical axis) for the close/final value for each candle. This is the top of the candle body. If greater than the open value the candle will be filled. Otherwise the candle will be hollow.",
    )

    low_series: Optional[CandlestickSeries] = Field(
        default=None, description="The range data (vertical axis) for the low/minimum value for each candle. This is the bottom of the candle's center line.",
    )

    open_series: Optional[CandlestickSeries] = Field(
        default=None, description="The range data (vertical axis) for the open/initial value for each candle. This is the bottom of the candle body. If less than the close value the candle will be filled. Otherwise the candle will be hollow.",
    )


class CandlestickDomain(BaseModel):
    """
    The domain of a CandlestickChart.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/charts#CandlestickDomain
    """
    reversed: Optional[bool] = Field(
        default=None, description="True to reverse the order of the domain values (horizontal axis).",
    )

    data: Optional[ChartData] = Field(
        default=None, description="The data of the CandlestickDomain.",
    )


class CandlestickSeries(BaseModel):
    """
    The series of a CandlestickData.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/charts#CandlestickSeries
    """
    data: Optional[ChartData] = Field(
        default=None, description="The data of the CandlestickSeries.",
    )


class CellData(BaseModel):
    """
    Data about a specific cell.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/cells#CellData
    """
    data_source_table: Optional[DataSourceTable] = Field(
        default=None, description="A data source table anchored at this cell. The size of data source table itself is computed dynamically based on its configuration. Only the first cell of the data source table contains the data source table definition. The other cells will contain the display values of the data source table result in their effective_value fields.",
    )

    data_validation: Optional[DataValidationRule] = Field(
        default=None, description="A data validation rule on the cell, if any. When writing, the new data validation rule will overwrite any prior rule.",
    )

    chip_runs: Optional[List[ChipRun]] = Field(
        default=None, description="Optional. Runs of chips applied to subsections of the cell. Properties of a run start at a specific index in the text and continue until the next run. When reading, all chipped and non-chipped runs are included. Non-chipped runs will have an empty Chip. When writing, only runs with chips are included. Runs containing chips are of length 1 and are represented in the user-entered text by an “@” placeholder symbol. New runs will overwrite any prior runs. Writing a new user_entered_value will erase previous runs.",
    )

    pivot_table: Optional[PivotTable] = Field(
        default=None, description="A pivot table anchored at this cell. The size of pivot table itself is computed dynamically based on its data, grouping, filters, values, etc. Only the top-left cell of the pivot table contains the pivot table definition. The other cells will contain the calculated values of the results of the pivot in their effective_value fields.",
    )

    effective_value: Annotated[
        Optional[ExtendedValue],
        Mode("response_only"), Field(default=None, description="The effective value of the cell. For cells with formulas, this is the calculated value. For cells with literals, this is the same as the user_entered_value. This field is read-only."),
    ] = None

    text_format_runs: Optional[List[TextFormatRun]] = Field(
        default=None, description="Runs of rich text applied to subsections of the cell. Runs are only valid on user entered strings, not formulas, bools, or numbers. Properties of a run start at a specific index in the text and continue until the next run. Runs will inherit the properties of the cell unless explicitly changed. When writing, the new runs will overwrite any prior runs. When writing a new user_entered_value, previous runs are erased.",
    )

    user_entered_format: Optional[CellFormat] = Field(
        default=None, description="The format the user entered for the cell. When writing, the new format will be merged with the existing format.",
    )

    data_source_formula: Annotated[
        Optional[DataSourceFormula],
        Mode("response_only"), Field(default=None, description="Output only. Information about a data source formula on the cell. The field is set if user_entered_value is a formula referencing some DATA_SOURCE sheet, e.g. `=SUM(DataSheet!Column)`."),
    ] = None

    hyperlink: Annotated[
        Optional[str],
        Mode("response_only"), Field(default=None, description="A hyperlink this cell points to, if any. If the cell contains multiple hyperlinks, this field will be empty. This field is read-only. To set it, use a `=HYPERLINK` formula in the userEnteredValue.formulaValue field. A cell-level link can also be set from the userEnteredFormat.textFormat field. Alternatively, set a hyperlink in the textFormatRun.format.link field that spans the entire cell."),
    ] = None

    user_entered_value: Optional[ExtendedValue] = Field(
        default=None, description="The value the user entered in the cell. e.g., `1234`, `'Hello'`, or `=NOW()` Note: Dates, Times and DateTimes are represented as doubles in serial number format.",
    )

    note: Optional[str] = Field(
        default=None, description="Any note on the cell.",
    )

    formatted_value: Annotated[
        Optional[str],
        Mode("response_only"), Field(default=None, description="The formatted value of the cell. This is the value as it's shown to the user. This field is read-only."),
    ] = None

    effective_format: Annotated[
        Optional[CellFormat],
        Mode("response_only"), Field(default=None, description="The effective format being used by the cell. This includes the results of applying any conditional formatting and, if the cell contains a formula, the computed number format. If the effective format is the default format, effective format will not be written. This field is read-only."),
    ] = None


class CellFormat(BaseModel):
    """
    The format of a cell.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/cells#CellFormat
    """
    hyperlink_display_type: Optional[CellFormatHyperlinkDisplayType] = Field(
        default=None, description="If one exists, how a hyperlink should be displayed in the cell.",
    )

    text_direction: Optional[CellFormatTextDirection] = Field(
        default=None, description="The direction of the text in the cell.",
    )

    padding: Optional[Padding] = Field(
        default=None, description="The padding of the cell.",
    )

    background_color_style: Optional[ColorStyle] = Field(
        default=None, description="The background color of the cell. If background_color is also set, this field takes precedence.",
    )

    horizontal_alignment: Optional[HorizontalAlign] = Field(
        default=None, description="The horizontal alignment of the value in the cell.",
    )

    borders: Optional[Borders] = Field(
        default=None, description="The borders of the cell.",
    )

    vertical_alignment: Optional[VerticalAlign] = Field(
        default=None, description="The vertical alignment of the value in the cell.",
    )

    text_rotation: Optional[TextRotation] = Field(
        default=None, description="The rotation applied to text in the cell.",
    )

    number_format: Optional[NumberFormat] = Field(
        default=None, description="A format describing how number values should be represented to the user.",
    )

    wrap_strategy: Optional[WrapStrategy] = Field(
        default=None, description="The wrap strategy for the value in the cell.",
    )

    background_color: Annotated[
        Optional[Color],
        Mode("disabled"), Field(default=None, description="The background color of the cell. Deprecated: Use background_color_style."),
    ] = None

    text_format: Optional[TextFormat] = Field(
        default=None, description="The format of the text in the cell (unless overridden by a format run). Setting a cell-level link here clears the cell's existing links. Setting the link field in a TextFormatRun takes precedence over the cell-level link.",
    )


class ChartAxisViewWindowOptions(BaseModel):
    """
    The options that define a "view window" for a chart (such as the visible values in an axis).

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/charts#ChartAxisViewWindowOptions
    """
    view_window_min: Optional[float] = Field(
        default=None, description="The minimum numeric value to be shown in this view window. If unset, will automatically determine a minimum value that looks good for the data.",
    )

    view_window_max: Optional[float] = Field(
        default=None, description="The maximum numeric value to be shown in this view window. If unset, will automatically determine a maximum value that looks good for the data.",
    )

    view_window_mode: Optional[ChartAxisViewWindowOptionsViewWindowMode] = Field(
        default=None, description="The view window's mode.",
    )


class ChartCustomNumberFormatOptions(BaseModel):
    """
    Custom number formatting options for chart attributes.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/charts#ChartCustomNumberFormatOptions
    """
    prefix: Optional[str] = Field(
        default=None, description="Custom prefix to be prepended to the chart attribute. This field is optional.",
    )

    suffix: Optional[str] = Field(
        default=None, description="Custom suffix to be appended to the chart attribute. This field is optional.",
    )


class ChartData(BaseModel):
    """
    The data included in a domain or series.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/charts#ChartData
    """
    source_range: Optional[ChartSourceRange] = Field(
        default=None, description="The source ranges of the data.",
    )

    column_reference: Optional[DataSourceColumnReference] = Field(
        default=None, description="The reference to the data source column that the data reads from.",
    )

    aggregate_type: Optional[ScorecardChartSpecAggregateType] = Field(
        default=None, description="The aggregation type for the series of a data source chart. Only supported for data source charts.",
    )

    group_rule: Optional[ChartGroupRule] = Field(
        default=None, description="The rule to group the data by if the ChartData backs the domain of a data source chart. Only supported for data source charts.",
    )

    # The union is `type`, and it holds `source_range` and `column_reference`
    # alone. `group_rule` and `aggregate_type` sit outside it — they describe how
    # a data source chart buckets and aggregates whichever of the two it reads —
    # so a domain that groups its source range sets two of these four fields and
    # is what the reference documents.
    @model_validator(mode="after")
    def _exactly_one(self) -> ChartData:
        provided = [n for n in ('source_range', 'column_reference') if getattr(self, n) is not None]
        if len(provided) != 1:
            raise ValueError(
                f"Exactly one of 'source_range', 'column_reference' must be set, found: {provided}"
            )
        return self


class ChartDateTimeRule(BaseModel):
    """
    Allows you to organize the date-time values in a source data column into buckets based on selected parts of their date or time values.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/charts#ChartDateTimeRule
    """
    type: Optional[ChartDateTimeRuleType] = Field(
        default=None, description="The type of date-time grouping to apply.",
    )


class ChartGroupRule(BaseModel):
    """
    An optional setting on the ChartData of the domain of a data source chart that defines buckets for the values in the domain rather than breaking out each individual value. For example, when plotting a data source chart, you can specify a histogram rule on the domain (it should only contain numeric values), grouping its values into buckets. Any values of a chart series that fall into the same bucket are aggregated based on the aggregate_type.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/charts#ChartGroupRule
    """
    histogram_rule: Optional[ChartHistogramRule] = Field(
        default=None, description="A ChartHistogramRule",
    )

    date_time_rule: Optional[ChartDateTimeRule] = Field(
        default=None, description="A ChartDateTimeRule.",
    )

    @model_validator(mode="after")
    def _at_most_one(self) -> ChartGroupRule:
        provided = [n for n in ('date_time_rule', 'histogram_rule') if getattr(self, n) is not None]
        if len(provided) > 1:
            raise ValueError(
                f"At most one of 'date_time_rule', 'histogram_rule' may be set, found: {provided}"
            )
        return self


class ChartHistogramRule(BaseModel):
    """
    Allows you to organize numeric values in a source data column into buckets of constant size.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/charts#ChartHistogramRule
    """
    min_value: Optional[float] = Field(
        default=None, description="The minimum value at which items are placed into buckets. Values that are less than the minimum are grouped into a single bucket. If omitted, it is determined by the minimum item value.",
    )

    interval_size: Optional[float] = Field(
        default=None, description="The size of the buckets that are created. Must be positive.",
    )

    max_value: Optional[float] = Field(
        default=None, description="The maximum value at which items are placed into buckets. Values greater than the maximum are grouped into a single bucket. If omitted, it is determined by the maximum item value.",
    )


class ChartSourceRange(BaseModel):
    """
    Source ranges for a chart.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/charts#ChartSourceRange
    """
    sources: Optional[List[GridRange]] = Field(
        default=None, description="The ranges of data for a series or domain. Exactly one dimension must have a length of 1, and all sources in the list must have the same dimension with length 1. The domain (if it exists) & all series must have the same number of source ranges. If using more than one source range, then the source range at a given offset must be in order and contiguous across the domain and series. For example, these are valid configurations: domain sources: A1:A5 series1 sources: B1:B5 series2 sources: D6:D10 domain sources: A1:A5, C10:C12 series1 sources: B1:B5, D10:D12 series2 sources: C1:C5, E10:E12",
    )


class ChartSpec(BaseModel):
    """
    The specifications of a chart.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/charts#ChartSpec
    """
    scorecard_chart: Optional[ScorecardChartSpec] = Field(
        default=None, description="A scorecard chart specification.",
    )

    bubble_chart: Optional[BubbleChartSpec] = Field(
        default=None, description="A bubble chart specification.",
    )

    histogram_chart: Optional[HistogramChartSpec] = Field(
        default=None, description="A histogram chart specification.",
    )

    candlestick_chart: Optional[CandlestickChartSpec] = Field(
        default=None, description="A candlestick chart specification.",
    )

    waterfall_chart: Optional[WaterfallChartSpec] = Field(
        default=None, description="A waterfall chart specification.",
    )

    org_chart: Optional[OrgChartSpec] = Field(
        default=None, description="An org chart specification.",
    )

    background_color_style: Optional[ColorStyle] = Field(
        default=None, description="The background color of the entire chart. Not applicable to Org charts. If background_color is also set, this field takes precedence.",
    )

    sort_specs: Optional[List[SortSpec]] = Field(
        default=None, description="The order to sort the chart data by. Only a single sort spec is supported. Only supported for data source charts.",
    )

    title: Optional[str] = Field(
        default=None, description="The title of the chart.",
    )

    pie_chart: Optional[PieChartSpec] = Field(
        default=None, description="A pie chart specification.",
    )

    alt_text: Optional[str] = Field(
        default=None, description="The alternative text that describes the chart. This is often used for accessibility.",
    )

    title_text_position: Optional[TextPosition] = Field(
        default=None, description="The title text position. This field is optional.",
    )

    title_text_format: Optional[TextFormat] = Field(
        default=None, description="The title text format. Strikethrough, underline, and link are not supported.",
    )

    filter_specs: Optional[List[FilterSpec]] = Field(
        default=None, description="The filters applied to the source data of the chart. Only supported for data source charts.",
    )

    subtitle_text_format: Optional[TextFormat] = Field(
        default=None, description="The subtitle text format. Strikethrough, underline, and link are not supported.",
    )

    subtitle: Optional[str] = Field(
        default=None, description="The subtitle of the chart.",
    )

    subtitle_text_position: Optional[TextPosition] = Field(
        default=None, description="The subtitle text position. This field is optional.",
    )

    background_color: Annotated[
        Optional[Color],
        Mode("disabled"), Field(default=None, description="The background color of the entire chart. Not applicable to Org charts. Deprecated: Use background_color_style."),
    ] = None

    font_name: Optional[str] = Field(
        default=None, description="The name of the font to use by default for all chart text (e.g. title, axis labels, legend). If a font is specified for a specific part of the chart it will override this font name.",
    )

    maximized: Optional[bool] = Field(
        default=None, description="True to make a chart fill the entire space in which it's rendered with minimum padding. False to use the default padding. (Not applicable to Geo and Org charts.)",
    )

    hidden_dimension_strategy: Optional[ChartSpecHiddenDimensionStrategy] = Field(
        default=None, description="Determines how the charts will use hidden rows or columns.",
    )

    data_source_chart_properties: Optional[DataSourceChartProperties] = Field(
        default=None, description="If present, the field contains data source chart specific properties.",
    )

    basic_chart: Optional[BasicChartSpec] = Field(
        default=None, description="A basic chart specification, can be one of many kinds of charts. See BasicChartType for the list of all charts this supports.",
    )

    treemap_chart: Optional[TreemapChartSpec] = Field(
        default=None, description="A treemap chart specification.",
    )

    @model_validator(mode="after")
    def _exactly_one(self) -> ChartSpec:
        provided = [n for n in ('basic_chart', 'pie_chart', 'bubble_chart', 'candlestick_chart', 'org_chart', 'histogram_chart', 'waterfall_chart', 'treemap_chart', 'scorecard_chart') if getattr(self, n) is not None]
        if len(provided) != 1:
            raise ValueError(
                f"Exactly one of 'basic_chart', 'pie_chart', 'bubble_chart', 'candlestick_chart', 'org_chart', 'histogram_chart', 'waterfall_chart', 'treemap_chart', 'scorecard_chart' must be set, found: {provided}"
            )
        return self


class Chip(BaseModel):
    """
    The Smart Chip.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/cells#Chip
    """
    rich_link_properties: Optional[RichLinkProperties] = Field(
        default=None, description="Properties of a rich link.",
    )

    person_properties: Optional[PersonProperties] = Field(
        default=None, description="Properties of a linked person.",
    )

    @model_validator(mode="after")
    def _at_most_one(self) -> Chip:
        provided = [n for n in ('person_properties', 'rich_link_properties') if getattr(self, n) is not None]
        if len(provided) > 1:
            raise ValueError(
                f"At most one of 'person_properties', 'rich_link_properties' may be set, found: {provided}"
            )
        return self


class ChipRun(BaseModel):
    """
    The run of a chip. The chip continues until the start index of the next run.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/cells#ChipRun
    """
    start_index: Optional[int] = Field(
        default=None, description="Required. The zero-based character index where this run starts, in UTF-16 code units.",
    )

    chip: Optional[Chip] = Field(
        default=None, description="Optional. The chip of this run.",
    )


class Color(BaseModel):
    """
    Represents a color in the RGBA color space. This representation is designed for simplicity of conversion to and from color representations in various languages over compactness. For example, the fields of this representation can be trivially provided to the constructor of `java.awt.Color` in Java; it can also be trivially provided to UIColor's `+colorWithRed:green:blue:alpha` method in iOS; and, with just a little work, it can be easily formatted into a CSS `rgba()` string in JavaScript. This reference page doesn't have information about the absolute color space that should be used to interpret the RGB value—for example, sRGB, Adobe RGB, DCI-P3, and BT.2020. By default, applications should assume the sRGB color space. When color equality needs to be decided, implementations, unless documented otherwise, treat two colors as equal if all their red, green, blue, and alpha values each differ by at most `1e-5`. Example (Java): import com.google.type.Color; // ... public static java.awt.Color fromProto(Color protocolor) { float alpha = protocolor.hasAlpha() ? protocolor.getAlpha().getValue() : 1.0; return new java.awt.Color( protocolor.getRed(), protocolor.getGreen(), protocolor.getBlue(), alpha); } public static Color toProto(java.awt.Color color) { float red = (float) color.getRed(); float green = (float) color.getGreen(); float blue = (float) color.getBlue(); float denominator = 255.0; Color.Builder resultBuilder = Color .newBuilder() .setRed(red / denominator) .setGreen(green / denominator) .setBlue(blue / denominator); int alpha = color.getAlpha(); if (alpha != 255) { result.setAlpha( FloatValue .newBuilder() .setValue(((float) alpha) / denominator) .build()); } return resultBuilder.build(); } // ... Example (iOS / Obj-C): // ... static UIColor* fromProto(Color* protocolor) { float red = [protocolor red]; float green = [protocolor green]; float blue = [protocolor blue]; FloatValue* alpha_wrapper = [protocolor alpha]; float alpha = 1.0; if (alpha_wrapper != nil) { alpha = [alpha_wrapper value]; } return [UIColor colorWithRed:red green:green blue:blue alpha:alpha]; } static Color* toProto(UIColor* color) { CGFloat red, green, blue, alpha; if (![color getRed:&red green:&green blue:&blue alpha:&alpha]) { return nil; } Color* result = [[Color alloc] init]; [result setRed:red]; [result setGreen:green]; [result setBlue:blue]; if (alpha <= 0.9999) { [result setAlpha:floatWrapperWithValue(alpha)]; } [result autorelease]; return result; } // ... Example (JavaScript): // ... var protoToCssColor = function(rgb_color) { var redFrac = rgb_color.red || 0.0; var greenFrac = rgb_color.green || 0.0; var blueFrac = rgb_color.blue || 0.0; var red = Math.floor(redFrac * 255); var green = Math.floor(greenFrac * 255); var blue = Math.floor(blueFrac * 255); if (!('alpha' in rgb_color)) { return rgbToCssColor(red, green, blue); } var alphaFrac = rgb_color.alpha.value || 0.0; var rgbParams = [red, green, blue].join(','); return ['rgba(', rgbParams, ',', alphaFrac, ')'].join(''); }; var rgbToCssColor = function(red, green, blue) { var rgbNumber = new Number((red << 16) | (green << 8) | blue); var hexString = rgbNumber.toString(16); var missingZeros = 6 - hexString.length; var resultBuilder = ['#']; for (var i = 0; i < missingZeros; i++) { resultBuilder.push('0'); } resultBuilder.push(hexString); return resultBuilder.join(''); }; // ...

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/other#Color
    """
    green: Optional[float] = Field(
        default=None, description="The amount of green in the color as a value in the interval [0, 1].",
    )

    blue: Optional[float] = Field(
        default=None, description="The amount of blue in the color as a value in the interval [0, 1].",
    )

    alpha: Optional[float] = Field(
        default=None, description="The fraction of this color that should be applied to the pixel. That is, the final pixel color is defined by the equation: `pixel color = alpha * (this color) + (1.0 - alpha) * (background color)` This means that a value of 1.0 corresponds to a solid color, whereas a value of 0.0 corresponds to a completely transparent color. This uses a wrapper message rather than a simple float scalar so that it is possible to distinguish between a default value and the value being unset. If omitted, this color object is rendered as a solid color (as if the alpha value had been explicitly given a value of 1.0).",
    )

    red: Optional[float] = Field(
        default=None, description="The amount of red in the color as a value in the interval [0, 1].",
    )


class ColorStyle(BaseModel):
    """
    A color value.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/other#ColorStyle
    """
    theme_color: Optional[ThemeColorType] = Field(
        default=None, description="Theme color.",
    )

    rgb_color: Optional[Color] = Field(
        default=None, description="RGB color. The [`alpha`](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/other#Color.FIELDS.alpha) value in the [`Color`](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/other#color) object isn't generally supported.",
    )

    @model_validator(mode="after")
    def _at_most_one(self) -> ColorStyle:
        provided = [n for n in ('rgb_color', 'theme_color') if getattr(self, n) is not None]
        if len(provided) > 1:
            raise ValueError(
                f"At most one of 'rgb_color', 'theme_color' may be set, found: {provided}"
            )
        return self


class ConditionValue(BaseModel):
    """
    The value of the condition.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/other#ConditionValue
    """
    user_entered_value: Optional[str] = Field(
        default=None, description="A value the condition is based on. The value is parsed as if the user typed into a cell. Formulas are supported (and must begin with an `=` or a '+').",
    )

    relative_date: Optional[ConditionValueRelativeDate] = Field(
        default=None, description="A relative date (based on the current date). Valid only if the type is DATE_BEFORE, DATE_AFTER, DATE_ON_OR_BEFORE or DATE_ON_OR_AFTER. Relative dates are not supported in data validation. They are supported only in conditional formatting and conditional filters.",
    )

    @model_validator(mode="after")
    def _exactly_one(self) -> ConditionValue:
        provided = [n for n in ('relative_date', 'user_entered_value') if getattr(self, n) is not None]
        if len(provided) != 1:
            raise ValueError(
                f"Exactly one of 'relative_date', 'user_entered_value' must be set, found: {provided}"
            )
        return self


class ConditionalFormatRule(BaseModel):
    """
    A rule describing a conditional format.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/sheets#ConditionalFormatRule
    """
    ranges: Optional[List[GridRange]] = Field(
        default=None, description="The ranges that are formatted if the condition is true. All the ranges must be on the same grid.",
    )

    boolean_rule: Optional[BooleanRule] = Field(
        default=None, description="The formatting is either \"on\" or \"off\" according to the rule.",
    )

    gradient_rule: Optional[GradientRule] = Field(
        default=None, description="The formatting will vary based on the gradients in the rule.",
    )

    @model_validator(mode="after")
    def _exactly_one(self) -> ConditionalFormatRule:
        provided = [n for n in ('boolean_rule', 'gradient_rule') if getattr(self, n) is not None]
        if len(provided) != 1:
            raise ValueError(
                f"Exactly one of 'boolean_rule', 'gradient_rule' must be set, found: {provided}"
            )
        return self


class DataExecutionStatus(BaseModel):
    """
    The data execution status. A data execution is created to sync a data source object with the latest data from a DataSource. It is usually scheduled to run at background, you can check its state to tell if an execution completes There are several scenarios where a data execution is triggered to run: * Adding a data source creates an associated data source sheet as well as a data execution to sync the data from the data source to the sheet. * Updating a data source creates a data execution to refresh the associated data source sheet similarly. * You can send refresh request to explicitly refresh one or multiple data source objects.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/other#DataExecutionStatus
    """
    state: Optional[DataExecutionStatusState] = Field(
        default=None, description="The state of the data execution.",
    )

    error_code: Optional[DataExecutionStatusErrorCode] = Field(
        default=None, description="The error code.",
    )

    error_message: Optional[str] = Field(
        default=None, description="The error message, which may be empty.",
    )

    last_refresh_time: Optional[str] = Field(
        default=None, description="Gets the time the data last successfully refreshed.",
    )


class DataFilter(BaseModel):
    """
    Filter that describes what data should be selected or returned from a request. For more information, see [Read, write, and search metadata](https://developers.google.com/workspace/sheets/api/guides/metadata).

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets#DataFilter
    """
    developer_metadata_lookup: Optional[DeveloperMetadataLookup] = Field(
        default=None, description="Selects data associated with the developer metadata matching the criteria described by this DeveloperMetadataLookup.",
    )

    grid_range: Optional[GridRange] = Field(
        default=None, description="Selects data that matches the range described by the GridRange.",
    )

    a1_range: Optional[str] = Field(
        default=None, description="Selects data that matches the specified A1 range.",
    )

    @model_validator(mode="after")
    def _exactly_one(self) -> DataFilter:
        provided = [n for n in ('developer_metadata_lookup', 'a1_range', 'grid_range') if getattr(self, n) is not None]
        if len(provided) != 1:
            raise ValueError(
                f"Exactly one of 'developer_metadata_lookup', 'a1_range', 'grid_range' must be set, found: {provided}"
            )
        return self


class DataLabel(BaseModel):
    """
    Settings for one set of data labels. Data labels are annotations that appear next to a set of data, such as the points on a line chart, and provide additional information about what the data represents, such as a text representation of the value behind that point on the graph.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/charts#DataLabel
    """
    custom_label_data: Optional[ChartData] = Field(
        default=None, description="Data to use for custom labels. Only used if type is set to CUSTOM. This data must be the same length as the series or other element this data label is applied to. In addition, if the series is split into multiple source ranges, this source data must come from the next column in the source data. For example, if the series is B2:B4,E6:E8 then this data must come from C2:C4,F6:F8.",
    )

    text_format: Optional[TextFormat] = Field(
        default=None, description="The text format used for the data label. The link field is not supported.",
    )

    type: Optional[DataLabelType] = Field(
        default=None, description="The type of the data label.",
    )

    placement: Optional[DataLabelPlacement] = Field(
        default=None, description="The placement of the data label relative to the labeled data.",
    )


class DataSource(BaseModel):
    """
    Information about an external data source in the spreadsheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets#DataSource
    """
    spec: Optional[DataSourceSpec] = Field(
        default=None, description="The DataSourceSpec for the data source connected with this spreadsheet.",
    )

    data_source_id: Optional[str] = Field(
        default=None, description="The spreadsheet-scoped unique ID that identifies the data source. Example: 1080547365.",
    )

    calculated_columns: Optional[List[DataSourceColumn]] = Field(
        default=None, description="All calculated columns in the data source.",
    )

    sheet_id: Optional[int] = Field(
        default=None, description="The ID of the Sheet connected with the data source. The field cannot be changed once set. When creating a data source, an associated DATA_SOURCE sheet is also created, if the field is not specified, the ID of the created sheet will be randomly generated.",
    )


class DataSourceChartProperties(BaseModel):
    """
    Properties of a data source chart.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/charts#DataSourceChartProperties
    """
    data_source_id: Optional[str] = Field(
        default=None, description="ID of the data source that the chart is associated with.",
    )

    data_execution_status: Annotated[
        Optional[DataExecutionStatus],
        Mode("response_only"), Field(default=None, description="Output only. The data execution status."),
    ] = None


class DataSourceColumn(BaseModel):
    """
    A column in a data source.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/other#DataSourceColumn
    """
    formula: Optional[str] = Field(
        default=None, description="The formula of the calculated column.",
    )

    reference: Optional[DataSourceColumnReference] = Field(
        default=None, description="The column reference.",
    )


class DataSourceColumnReference(BaseModel):
    """
    An unique identifier that references a data source column.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/other#DataSourceColumnReference
    """
    name: Optional[str] = Field(
        default=None, description="The display name of the column. It should be unique within a data source.",
    )


class DataSourceFormula(BaseModel):
    """
    A data source formula.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/cells#DataSourceFormula
    """
    data_source_id: Optional[str] = Field(
        default=None, description="The ID of the data source the formula is associated with.",
    )

    data_execution_status: Annotated[
        Optional[DataExecutionStatus],
        Mode("response_only"), Field(default=None, description="Output only. The data execution status."),
    ] = None


class DataSourceParameter(BaseModel):
    """
    A parameter in a data source's query. The parameter allows the user to pass in values from the spreadsheet into a query.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets#DataSourceParameter
    """
    range: Optional[GridRange] = Field(
        default=None, description="A range that contains the value of the parameter. Its size must be 1x1.",
    )

    name: Optional[str] = Field(
        default=None, description="Named parameter. Must be a legitimate identifier for the DataSource that supports it. For example, [BigQuery identifier](https://cloud.google.com/bigquery/docs/reference/standard-sql/lexical#identifiers).",
    )

    named_range_id: Optional[str] = Field(
        default=None, description="ID of a NamedRange. Its size must be 1x1.",
    )

    @model_validator(mode="after")
    def _at_most_one(self) -> DataSourceParameter:
        provided = [n for n in ("named_range_id", "range") if getattr(self, n) is not None]
        if len(provided) > 1:
            raise ValueError(
                f"At most one of 'named_range_id', 'range' may be set, found: {provided}"
            )
        return self


class DataSourceRefreshDailySchedule(BaseModel):
    """
    A schedule for data to refresh every day in a given time interval.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets#DataSourceRefreshDailySchedule
    """
    start_time: Optional[TimeOfDay] = Field(
        default=None, description="The start time of a time interval in which a data source refresh is scheduled. Only `hours` part is used. The time interval size defaults to that in the Sheets editor.",
    )


class DataSourceRefreshMonthlySchedule(BaseModel):
    """
    A monthly schedule for data to refresh on specific days in the month in a given time interval.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets#DataSourceRefreshMonthlySchedule
    """
    start_time: Optional[TimeOfDay] = Field(
        default=None, description="The start time of a time interval in which a data source refresh is scheduled. Only `hours` part is used. The time interval size defaults to that in the Sheets editor.",
    )

    days_of_month: Optional[List[int]] = Field(
        default=None, description="Days of the month to refresh. Only 1-28 are supported, mapping to the 1st to the 28th day. At least one day must be specified.",
    )


class DataSourceRefreshSchedule(BaseModel):
    """
    Schedule for refreshing the data source. Data sources in the spreadsheet are refreshed within a time interval. You can specify the start time by clicking the Scheduled Refresh button in the Sheets editor, but the interval is fixed at 4 hours. For example, if you specify a start time of 8 AM , the refresh will take place between 8 AM and 12 PM every day.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets#DataSourceRefreshSchedule
    """
    enabled: Optional[bool] = Field(
        default=None, description="True if the refresh schedule is enabled, or false otherwise.",
    )

    next_run: Annotated[
        Optional[Interval],
        Mode("response_only"), Field(default=None, description="Output only. The time interval of the next run."),
    ] = None

    refresh_scope: Optional[DataSourceRefreshScheduleRefreshScope] = Field(
        default=None, description="The scope of the refresh. Must be ALL_DATA_SOURCES.",
    )

    monthly_schedule: Optional[DataSourceRefreshMonthlySchedule] = Field(
        default=None, description="Monthly refresh schedule.",
    )

    weekly_schedule: Optional[DataSourceRefreshWeeklySchedule] = Field(
        default=None, description="Weekly refresh schedule.",
    )

    daily_schedule: Optional[DataSourceRefreshDailySchedule] = Field(
        default=None, description="Daily refresh schedule.",
    )

    @model_validator(mode="after")
    def _at_most_one(self) -> DataSourceRefreshSchedule:
        provided = [n for n in ('daily_schedule', 'weekly_schedule', 'monthly_schedule') if getattr(self, n) is not None]
        if len(provided) > 1:
            raise ValueError(
                f"At most one of 'daily_schedule', 'weekly_schedule', 'monthly_schedule' may be set, found: {provided}"
            )
        return self


class DataSourceRefreshWeeklySchedule(BaseModel):
    """
    A weekly schedule for data to refresh on specific days in a given time interval.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets#DataSourceRefreshWeeklySchedule
    """
    start_time: Optional[TimeOfDay] = Field(
        default=None, description="The start time of a time interval in which a data source refresh is scheduled. Only `hours` part is used. The time interval size defaults to that in the Sheets editor.",
    )

    days_of_week: Optional[List[DataSourceRefreshWeeklyScheduleDaysOfWeekItem]] = Field(
        default=None, description="Days of the week to refresh. At least one day must be specified.",
    )


class DataSourceSheetProperties(BaseModel):
    """
    Additional properties of a DATA_SOURCE sheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/sheets#DataSourceSheetProperties
    """
    columns: Optional[List[DataSourceColumn]] = Field(
        default=None, description="The columns displayed on the sheet, corresponding to the values in RowData.",
    )

    data_source_id: Optional[str] = Field(
        default=None, description="ID of the DataSource the sheet is connected to.",
    )

    data_execution_status: Optional[DataExecutionStatus] = Field(
        default=None, description="The data execution status.",
    )


class DataSourceSpec(BaseModel):
    """
    This specifies the details of the data source. For example, for BigQuery, this specifies information about the BigQuery source.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets#DataSourceSpec
    """
    big_query: Optional[BigQueryDataSourceSpec] = Field(
        default=None, description="A BigQueryDataSourceSpec.",
    )

    looker: Optional[LookerDataSourceSpec] = Field(
        default=None, description="A LookerDatasourceSpec.",
    )

    parameters: Optional[List[DataSourceParameter]] = Field(
        default=None, description="The parameters of the data source, used when querying the data source.",
    )

    @model_validator(mode="after")
    def _at_most_one(self) -> DataSourceSpec:
        provided = [n for n in ('big_query', 'looker') if getattr(self, n) is not None]
        if len(provided) > 1:
            raise ValueError(
                f"At most one of 'big_query', 'looker' may be set, found: {provided}"
            )
        return self


class DataSourceTable(BaseModel):
    """
    A data source table, which allows the user to import a static table of data from the DataSource into Sheets. This is also known as "Extract" in the Sheets editor.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/cells#DataSourceTable
    """
    columns: Optional[List[DataSourceColumnReference]] = Field(
        default=None, description="Columns selected for the data source table. The column_selection_type must be SELECTED.",
    )

    data_source_id: Optional[str] = Field(
        default=None, description="The ID of the data source the data source table is associated with.",
    )

    data_execution_status: Annotated[
        Optional[DataExecutionStatus],
        Mode("response_only"), Field(default=None, description="Output only. The data execution status."),
    ] = None

    row_limit: Optional[int] = Field(
        default=None, description="The limit of rows to return. If not set, a default limit is applied. Please refer to the Sheets editor for the default and max limit.",
    )

    sort_specs: Optional[List[SortSpec]] = Field(
        default=None, description="Sort specifications in the data source table. The result of the data source table is sorted based on the sort specifications in order.",
    )

    column_selection_type: Optional[DataSourceTableColumnSelectionType] = Field(
        default=None, description="The type to select columns for the data source table. Defaults to SELECTED.",
    )

    filter_specs: Optional[List[FilterSpec]] = Field(
        default=None, description="Filter specifications in the data source table.",
    )


class DataValidationRule(BaseModel):
    """
    A data validation rule.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/cells#DataValidationRule
    """
    show_custom_ui: Optional[bool] = Field(
        default=None, description="True if the UI should be customized based on the kind of condition. If true, \"List\" conditions will show a dropdown.",
    )

    input_message: Optional[str] = Field(
        default=None, description="A message to show the user when adding data to the cell.",
    )

    condition: Optional[BooleanCondition] = Field(
        default=None, description="The condition that data in the cell must match.",
    )

    strict: Optional[bool] = Field(
        default=None, description="True if invalid data should be rejected.",
    )


class DateTimeRule(BaseModel):
    """
    Allows you to organize the date-time values in a source data column into buckets based on selected parts of their date or time values. For example, consider a pivot table showing sales transactions by date: +----------+--------------+ | Date | SUM of Sales | +----------+--------------+ | 1/1/2017 | $621.14 | | 2/3/2017 | $708.84 | | 5/8/2017 | $326.84 | ... +----------+--------------+ Applying a date-time group rule with a DateTimeRuleType of YEAR_MONTH results in the following pivot table. +--------------+--------------+ | Grouped Date | SUM of Sales | +--------------+--------------+ | 2017-Jan | $53,731.78 | | 2017-Feb | $83,475.32 | | 2017-Mar | $94,385.05 | ... +--------------+--------------+

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/pivot-tables#DateTimeRule
    """
    type: Optional[DateTimeRuleType] = Field(
        default=None, description="The type of date-time grouping to apply.",
    )


class DeveloperMetadata(BaseModel):
    """
    Developer metadata associated with a location or object in a spreadsheet. For more information, see [Read, write, and search metadata](https://developers.google.com/workspace/sheets/api/guides/metadata). Developer metadata may be used to associate arbitrary data with various parts of a spreadsheet and it will remain associated at those locations as they move around and the spreadsheet is edited. For example, if developer metadata is associated with row 5 and another row is then subsequently inserted above row 5, that original metadata is still associated with the row it was first associated with (what is now row 6). If the associated object is deleted then its metadata is deleted too.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.developerMetadata#DeveloperMetadata
    """
    location: Optional[DeveloperMetadataLocation] = Field(
        default=None, description="The location where the metadata is associated.",
    )

    metadata_id: Optional[int] = Field(
        default=None, description="The spreadsheet-scoped unique ID that identifies the metadata. IDs may be specified when metadata is created, otherwise one will be randomly generated and assigned. Must be positive.",
    )

    metadata_key: Optional[str] = Field(
        default=None, description="The metadata key. There may be multiple metadata in a spreadsheet with the same key. Developer metadata must always have a key specified.",
    )

    visibility: Optional[DeveloperMetadataVisibility] = Field(
        default=None, description="The metadata visibility. Developer metadata must always have visibility specified.",
    )

    metadata_value: Optional[str] = Field(
        default=None, description="Data associated with the metadata's key.",
    )


class DeveloperMetadataLocation(BaseModel):
    """
    A location where metadata may be associated in a spreadsheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets#DeveloperMetadataLocation
    """
    spreadsheet: Optional[bool] = Field(
        default=None, description="True when metadata is associated with an entire spreadsheet.",
    )

    dimension_range: Optional[DimensionRange] = Field(
        default=None, description="Represents the row or column when metadata is associated with a dimension. The specified DimensionRange must represent a single row or column. It cannot be unbounded or span multiple rows or columns.",
    )

    sheet_id: Optional[int] = Field(
        default=None, description="The ID of the sheet when metadata is associated with an entire sheet.",
    )

    location_type: Annotated[
        Optional[DeveloperMetadataLocationType],
        Mode("response_only"), Field(default=None, description="The type of location this object represents. This field is read-only."),
    ] = None

    @model_validator(mode="after")
    def _at_most_one(self) -> DeveloperMetadataLocation:
        provided = [n for n in ('spreadsheet', 'sheet_id', 'dimension_range') if getattr(self, n) is not None]
        if len(provided) > 1:
            raise ValueError(
                f"At most one of 'spreadsheet', 'sheet_id', 'dimension_range' may be set, found: {provided}"
            )
        return self


class DeveloperMetadataLookup(BaseModel):
    """
    Selects DeveloperMetadata that matches all of the specified fields. For example, if only a metadata ID is specified this considers the DeveloperMetadata with that particular unique ID. If a metadata key is specified, this considers all developer metadata with that key. If a key, visibility, and location type are all specified, this considers all developer metadata with that key and visibility that are associated with a location of that type. In general, this selects all DeveloperMetadata that match the intersection of all the specified fields; any field or combination of fields may be specified.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/DataFilter#DeveloperMetadataLookup
    """
    metadata_id: Optional[int] = Field(
        default=None, description="Limits the selected developer metadata to that which has a matching DeveloperMetadata.metadata_id.",
    )

    metadata_value: Optional[str] = Field(
        default=None, description="Limits the selected developer metadata to that which has a matching DeveloperMetadata.metadata_value.",
    )

    visibility: Optional[DeveloperMetadataVisibility] = Field(
        default=None, description="Limits the selected developer metadata to that which has a matching DeveloperMetadata.visibility. If left unspecified, all developer metadata visible to the requesting project is considered.",
    )

    metadata_location: Optional[DeveloperMetadataLocation] = Field(
        default=None, description="Limits the selected developer metadata to those entries associated with the specified location. This field either matches exact locations or all intersecting locations according the specified locationMatchingStrategy.",
    )

    metadata_key: Optional[str] = Field(
        default=None, description="Limits the selected developer metadata to that which has a matching DeveloperMetadata.metadata_key.",
    )

    location_matching_strategy: Optional[DeveloperMetadataLocationMatchingStrategy] = Field(
        default=None, description="Determines how this lookup matches the location. If this field is specified as EXACT, only developer metadata associated on the exact location specified is matched. If this field is specified to INTERSECTING, developer metadata associated on intersecting locations is also matched. If left unspecified, this field assumes a default value of INTERSECTING. If this field is specified, a metadataLocation must also be specified.",
    )

    location_type: Optional[DeveloperMetadataLocationType] = Field(
        default=None, description="Limits the selected developer metadata to those entries which are associated with locations of the specified type. For example, when this field is specified as ROW this lookup only considers developer metadata associated on rows. If the field is left unspecified, all location types are considered. This field cannot be specified as SPREADSHEET when the locationMatchingStrategy is specified as INTERSECTING or when the metadataLocation is specified as a non-spreadsheet location. Spreadsheet metadata cannot intersect any other developer metadata location. This field also must be left unspecified when the locationMatchingStrategy is specified as EXACT.",
    )

    @model_validator(mode="after")
    def _strategy_requires_location(self) -> DeveloperMetadataLookup:
        if (
            self.location_matching_strategy is not None
            and self.metadata_location is None
        ):
            raise ValueError(
                "If locationMatchingStrategy is specified, a metadataLocation must "
                "also be specified."
            )
        if (
            self.location_matching_strategy == "EXACT_LOCATION"
            and self.location_type is not None
        ):
            raise ValueError(
                "locationType must be left unspecified when locationMatchingStrategy "
                "is EXACT_LOCATION."
            )
        return self


class DimensionGroup(BaseModel):
    """
    A group over an interval of rows or columns on a sheet, which can contain or be contained within other groups. A group can be collapsed or expanded as a unit on the sheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/sheets#DimensionGroup
    """
    depth: Optional[int] = Field(
        default=None, description="The depth of the group, representing how many groups have a range that wholly contains the range of this group.",
    )

    range: Optional[DimensionRange] = Field(
        default=None, description="The range over which this group exists.",
    )

    collapsed: Optional[bool] = Field(
        default=None, description="This field is true if this group is collapsed. A collapsed group remains collapsed if an overlapping group at a shallower depth is expanded. A true value does not imply that all dimensions within the group are hidden, since a dimension's visibility can change independently from this group property. However, when this property is updated, all dimensions within it are set to hidden if this field is true, or set to visible if this field is false.",
    )


class DimensionProperties(BaseModel):
    """
    Properties about a dimension.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/sheets#DimensionProperties
    """
    pixel_size: Optional[int] = Field(
        default=None, description="The height (if a row) or width (if a column) of the dimension in pixels.",
    )

    developer_metadata: Optional[List[DeveloperMetadata]] = Field(
        default=None, description="The developer metadata associated with a single row or column.",
    )

    hidden_by_filter: Annotated[
        Optional[bool],
        Mode("response_only"), Field(default=None, description="True if this dimension is being filtered. This field is read-only."),
    ] = None

    data_source_column_reference: Annotated[
        Optional[DataSourceColumnReference],
        Mode("response_only"), Field(default=None, description="Output only. If set, this is a column in a data source sheet."),
    ] = None

    hidden_by_user: Optional[bool] = Field(
        default=None, description="True if this dimension is explicitly hidden.",
    )


class DimensionRange(BaseModel):
    """
    A range along a single dimension on a sheet. All indexes are zero-based. Indexes are half open: the start index is inclusive and the end index is exclusive. Missing indexes indicate the range is unbounded on that side.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets#DimensionRange
    """
    end_index: Optional[int] = Field(
        default=None, description="The end (exclusive) of the span, or not set if unbounded.",
    )

    start_index: Optional[int] = Field(
        default=None, description="The start (inclusive) of the span, or not set if unbounded.",
    )

    dimension: Optional[Dimension] = Field(
        default=None, description="The dimension of the span.",
    )

    sheet_id: Optional[int] = Field(
        default=None, description="The sheet this span is on.",
    )


class Editors(BaseModel):
    """
    The editors of a protected range.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/sheets#Editors
    """
    domain_users_can_edit: Optional[bool] = Field(
        default=None, description="True if anyone in the document's domain has edit access to the protected range. Domain protection is only supported on documents within a domain.",
    )

    users: Optional[List[str]] = Field(
        default=None, description="The email addresses of users with edit access to the protected range.",
    )

    groups: Optional[List[str]] = Field(
        default=None, description="The email addresses of groups with edit access to the protected range.",
    )


class EmbeddedChart(BaseModel):
    """
    A chart embedded in a sheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/charts#EmbeddedChart
    """
    spec: Optional[ChartSpec] = Field(
        default=None, description="The specification of the chart.",
    )

    chart_id: Optional[int] = Field(
        default=None, description="The ID of the chart.",
    )

    position: Optional[EmbeddedObjectPosition] = Field(
        default=None, description="The position of the chart.",
    )

    border: Optional[EmbeddedObjectBorder] = Field(
        default=None, description="The border of the chart.",
    )


class EmbeddedObjectBorder(BaseModel):
    """
    A border along an embedded object.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/charts#EmbeddedObjectBorder
    """
    color: Annotated[
        Optional[Color],
        Mode("disabled"), Field(default=None, description="The color of the border. Deprecated: Use color_style."),
    ] = None

    color_style: Optional[ColorStyle] = Field(
        default=None, description="The color of the border. If color is also set, this field takes precedence.",
    )


class EmbeddedObjectPosition(BaseModel):
    """
    The position of an embedded object such as a chart.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/other#EmbeddedObjectPosition
    """
    overlay_position: Optional[OverlayPosition] = Field(
        default=None, description="The position at which the object is overlaid on top of a grid.",
    )

    sheet_id: Optional[int] = Field(
        default=None, ge=0, description="The sheet this is on. Set only if the embedded object is on its own sheet. Must be non-negative.",
    )

    new_sheet: Optional[bool] = Field(
        default=None, description="If true, the embedded object is put on a new sheet whose ID is chosen for you. Used only when writing.",
    )

    @model_validator(mode="after")
    def _exactly_one(self) -> EmbeddedObjectPosition:
        provided = [n for n in ('sheet_id', 'overlay_position', 'new_sheet') if getattr(self, n) is not None]
        if len(provided) != 1:
            raise ValueError(
                f"Exactly one of 'sheet_id', 'overlay_position', 'new_sheet' must be set, found: {provided}"
            )
        return self


class ErrorValue(BaseModel):
    """
    An error in a cell.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/other#ErrorValue
    """
    message: Optional[str] = Field(
        default=None, description="A message with more information about the error (in the spreadsheet's locale).",
    )

    type: Optional[ErrorValueType] = Field(
        default=None, description="The type of error.",
    )


class ExtendedValue(BaseModel):
    """
    The kinds of value that a cell in a spreadsheet can have.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/other#ExtendedValue
    """
    number_value: Optional[float] = Field(
        default=None, description="Represents a double value. Note: Dates, Times and DateTimes are represented as doubles in SERIAL_NUMBER format.",
    )

    error_value: Annotated[
        Optional[ErrorValue],
        Mode("response_only"), Field(default=None, description="Represents an error. This field is read-only."),
    ] = None

    string_value: Optional[str] = Field(
        default=None, description="Represents a string value. Leading single quotes are not included. For example, if the user typed `'123` into the UI, this would be represented as a `stringValue` of `\"123\"`.",
    )

    formula_value: Optional[str] = Field(
        default=None, description="Represents a formula.",
    )

    bool_value: Optional[bool] = Field(
        default=None, description="Represents a boolean value.",
    )

    @model_validator(mode="after")
    def _at_most_one(self) -> ExtendedValue:
        provided = [n for n in ('number_value', 'string_value', 'bool_value', 'formula_value', 'error_value') if getattr(self, n) is not None]
        if len(provided) > 1:
            raise ValueError(
                f"At most one of 'number_value', 'string_value', 'bool_value', 'formula_value', 'error_value' may be set, found: {provided}"
            )
        return self


class FilterCriteria(BaseModel):
    """
    Criteria for showing or hiding rows in a filter or filter view.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/other#FilterCriteria
    """
    visible_background_color_style: Optional[ColorStyle] = Field(
        default=None, description="The background fill color to filter by; only cells with this fill color are shown. This field is mutually exclusive with visible_foreground_color, and must be set to an RGB-type color. If visible_background_color is also set, this field takes precedence.",
    )

    hidden_values: Optional[List[str]] = Field(
        default=None, description="Values that should be hidden.",
    )

    visible_background_color: Annotated[
        Optional[Color],
        Mode("disabled"), Field(default=None, description="The background fill color to filter by; only cells with this fill color are shown. Mutually exclusive with visible_foreground_color. Deprecated: Use visible_background_color_style."),
    ] = None

    visible_foreground_color_style: Optional[ColorStyle] = Field(
        default=None, description="The foreground color to filter by; only cells with this foreground color are shown. This field is mutually exclusive with visible_background_color, and must be set to an RGB-type color. If visible_foreground_color is also set, this field takes precedence.",
    )

    condition: Optional[BooleanCondition] = Field(
        default=None, description="A condition that must be `true` for values to be shown. (This does not override hidden_values -- if a value is listed there, it will still be hidden.)",
    )

    visible_foreground_color: Annotated[
        Optional[Color],
        Mode("disabled"), Field(default=None, description="The foreground color to filter by; only cells with this foreground color are shown. Mutually exclusive with visible_background_color. Deprecated: Use visible_foreground_color_style."),
    ] = None


class FilterSpec(BaseModel):
    """
    The filter criteria associated with a specific column.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/other#FilterSpec
    """
    filter_criteria: Optional[FilterCriteria] = Field(
        default=None, description="The criteria for the column.",
    )

    column_index: Optional[int] = Field(
        default=None, description="The zero-based column index.",
    )

    data_source_column_reference: Optional[DataSourceColumnReference] = Field(
        default=None, description="Reference to a data source column.",
    )

    @model_validator(mode="after")
    def _at_most_one(self) -> FilterSpec:
        provided = [n for n in ('column_index', 'data_source_column_reference') if getattr(self, n) is not None]
        if len(provided) > 1:
            raise ValueError(
                f"At most one of 'column_index', 'data_source_column_reference' may be set, found: {provided}"
            )
        return self


class FilterView(BaseModel):
    """
    A filter view. For more information, see [Manage data visibility with filters](https://developers.google.com/workspace/sheets/api/guides/filters).

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/sheets#FilterView
    """
    table_id: Optional[str] = Field(
        default=None, description="The table this filter view is backed by, if any. When writing, only one of range, named_range_id, or table_id may be set.",
    )

    named_range_id: Optional[str] = Field(
        default=None, description="The named range this filter view is backed by, if any. When writing, only one of range, named_range_id, or table_id may be set.",
    )

    criteria: Annotated[
        Optional[Dict[str, FilterCriteria]],
        Mode("disabled"), Field(default=None, description="The criteria for showing/hiding values per column. The map's key is the column index, and the value is the criteria for that column. This field is deprecated in favor of filter_specs."),
    ] = None

    range: Optional[GridRange] = Field(
        default=None, description="The range this filter view covers. When writing, only one of range, named_range_id, or table_id may be set.",
    )

    sort_specs: Optional[List[SortSpec]] = Field(
        default=None, description="The sort order per column. Later specifications are used when values are equal in the earlier specifications.",
    )

    title: Optional[str] = Field(
        default=None, description="The name of the filter view.",
    )

    filter_view_id: Optional[int] = Field(
        default=None, description="The ID of the filter view.",
    )

    filter_specs: Optional[List[FilterSpec]] = Field(
        default=None, description="The filter criteria for showing or hiding values per column. Both criteria and filter_specs are populated in responses. If both fields are specified in an update request, this field takes precedence.",
    )


class GradientRule(BaseModel):
    """
    A rule that applies a gradient color scale format, based on the interpolation points listed. The format of a cell will vary based on its contents as compared to the values of the interpolation points.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/sheets#GradientRule
    """
    midpoint: Optional[InterpolationPoint] = Field(
        default=None, description="An optional midway interpolation point.",
    )

    minpoint: Optional[InterpolationPoint] = Field(
        default=None, description="The starting interpolation point.",
    )

    maxpoint: Optional[InterpolationPoint] = Field(
        default=None, description="The final interpolation point.",
    )


class GridCoordinate(BaseModel):
    """
    A coordinate in a sheet. All indexes are zero-based.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/other#GridCoordinate
    """
    column_index: Optional[int] = Field(
        default=None, description="The column index of the coordinate.",
    )

    sheet_id: Optional[int] = Field(
        default=None, description="The sheet this coordinate is on.",
    )

    row_index: Optional[int] = Field(
        default=None, description="The row index of the coordinate.",
    )


class GridData(BaseModel):
    """
    Data in the grid, as well as metadata about the dimensions.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/sheets#GridData
    """
    row_metadata: Optional[List[DimensionProperties]] = Field(
        default=None, description="Metadata about the requested rows in the grid, starting with the row in start_row.",
    )

    start_column: Optional[int] = Field(
        default=None, description="The first column this GridData refers to, zero-based.",
    )

    row_data: Optional[List[RowData]] = Field(
        default=None, description="The data in the grid, one entry per row, starting with the row in startRow. The values in RowData will correspond to columns starting at start_column.",
    )

    column_metadata: Optional[List[DimensionProperties]] = Field(
        default=None, description="Metadata about the requested columns in the grid, starting with the column in start_column.",
    )

    start_row: Optional[int] = Field(
        default=None, description="The first row this GridData refers to, zero-based.",
    )


class GridProperties(BaseModel):
    """
    Properties of a grid.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/sheets#GridProperties
    """
    frozen_row_count: Optional[int] = Field(
        default=None, description="The number of rows that are frozen in the grid.",
    )

    row_group_control_after: Optional[bool] = Field(
        default=None, description="True if the row grouping control toggle is shown after the group.",
    )

    column_count: Optional[int] = Field(
        default=None, description="The number of columns in the grid.",
    )

    column_group_control_after: Optional[bool] = Field(
        default=None, description="True if the column grouping control toggle is shown after the group.",
    )

    frozen_column_count: Optional[int] = Field(
        default=None, description="The number of columns that are frozen in the grid.",
    )

    row_count: Optional[int] = Field(
        default=None, description="The number of rows in the grid.",
    )

    hide_gridlines: Optional[bool] = Field(
        default=None, description="True if the grid isn't showing gridlines in the UI.",
    )


class GridRange(BaseModel):
    """
    A range on a sheet. All indexes are zero-based. Indexes are half open, i.e. the start index is inclusive and the end index is exclusive -- [start_index, end_index). Missing indexes indicate the range is unbounded on that side. For example, if `"Sheet1"` is sheet ID 123456, then: `Sheet1!A1:A1 == sheet_id: 123456, start_row_index: 0, end_row_index: 1, start_column_index: 0, end_column_index: 1` `Sheet1!A3:B4 == sheet_id: 123456, start_row_index: 2, end_row_index: 4, start_column_index: 0, end_column_index: 2` `Sheet1!A:B == sheet_id: 123456, start_column_index: 0, end_column_index: 2` `Sheet1!A5:B == sheet_id: 123456, start_row_index: 4, start_column_index: 0, end_column_index: 2` `Sheet1 == sheet_id: 123456` The start index must always be less than or equal to the end index. If the start index equals the end index, then the range is empty. Empty ranges are typically not meaningful and are usually rendered in the UI as `#REF!`.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/other#GridRange
    """
    sheet_id: Optional[int] = Field(
        default=None, description="The sheet this range is on.",
    )

    start_column_index: Optional[int] = Field(
        default=None, description="The start column (inclusive) of the range, or not set if unbounded.",
    )

    end_row_index: Optional[int] = Field(
        default=None, description="The end row (exclusive) of the range, or not set if unbounded.",
    )

    end_column_index: Optional[int] = Field(
        default=None, description="The end column (exclusive) of the range, or not set if unbounded.",
    )

    start_row_index: Optional[int] = Field(
        default=None, description="The start row (inclusive) of the range, or not set if unbounded.",
    )


class HistogramChartSpec(BaseModel):
    """
    A histogram chart. A histogram chart groups data items into bins, displaying each bin as a column of stacked items. Histograms are used to display the distribution of a dataset. Each column of items represents a range into which those items fall. The number of bins can be chosen automatically or specified explicitly.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/charts#HistogramChartSpec
    """
    outlier_percentile: Optional[float] = Field(
        default=None, ge=0.0, le=0.5, description="The outlier percentile is used to ensure that outliers do not adversely affect the calculation of bucket sizes. For example, setting an outlier percentile of 0.05 indicates that the top and bottom 5% of values when calculating buckets. The values are still included in the chart, they will be added to the first or last buckets instead of their own buckets. Must be between 0.0 and 0.5.",
    )

    series: Optional[List[HistogramSeries]] = Field(
        default=None, description="The series for a histogram may be either a single series of values to be bucketed or multiple series, each of the same length, containing the name of the series followed by the values to be bucketed for that series.",
    )

    bucket_size: Optional[float] = Field(
        default=None, description="By default the bucket size (the range of values stacked in a single column) is chosen automatically, but it may be overridden here. E.g., A bucket size of 1.5 results in buckets from 0 - 1.5, 1.5 - 3.0, etc. Cannot be negative. This field is optional.",
    )

    show_item_dividers: Optional[bool] = Field(
        default=None, description="Whether horizontal divider lines should be displayed between items in each column.",
    )

    legend_position: Optional[HistogramChartSpecLegendPosition] = Field(
        default=None, description="The position of the chart legend.",
    )


class HistogramRule(BaseModel):
    """
    Allows you to organize the numeric values in a source data column into buckets of a constant size. All values from HistogramRule.start to HistogramRule.end are placed into groups of size HistogramRule.interval. In addition, all values below HistogramRule.start are placed in one group, and all values above HistogramRule.end are placed in another. Only HistogramRule.interval is required, though if HistogramRule.start and HistogramRule.end are both provided, HistogramRule.start must be less than HistogramRule.end. For example, a pivot table showing average purchase amount by age that has 50+ rows: +-----+-------------------+ | Age | AVERAGE of Amount | +-----+-------------------+ | 16 | $27.13 | | 17 | $5.24 | | 18 | $20.15 | ... +-----+-------------------+ could be turned into a pivot table that looks like the one below by applying a histogram group rule with a HistogramRule.start of 25, an HistogramRule.interval of 20, and an HistogramRule.end of 65. +-------------+-------------------+ | Grouped Age | AVERAGE of Amount | +-------------+-------------------+ | < 25 | $19.34 | | 25-45 | $31.43 | | 45-65 | $35.87 | | > 65 | $27.55 | +-------------+-------------------+ | Grand Total | $29.12 | +-------------+-------------------+

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/pivot-tables#HistogramRule
    """
    end: Optional[float] = Field(
        default=None, description="The maximum value at which items are placed into buckets of constant size. Values above end are lumped into a single bucket. This field is optional.",
    )

    start: Optional[float] = Field(
        default=None, description="The minimum value at which items are placed into buckets of constant size. Values below start are lumped into a single bucket. This field is optional.",
    )

    interval: Optional[float] = Field(
        default=None, description="The size of the buckets that are created. Must be positive.",
    )


class HistogramSeries(BaseModel):
    """
    A histogram series containing the series color and data.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/charts#HistogramSeries
    """
    bar_color: Annotated[
        Optional[Color],
        Mode("disabled"), Field(default=None, description="The color of the column representing this series in each bucket. This field is optional. Deprecated: Use bar_color_style."),
    ] = None

    bar_color_style: Optional[ColorStyle] = Field(
        default=None, description="The color of the column representing this series in each bucket. This field is optional. If bar_color is also set, this field takes precedence.",
    )

    data: Optional[ChartData] = Field(
        default=None, description="The data for this histogram series.",
    )


class InterpolationPoint(BaseModel):
    """
    A single interpolation point on a gradient conditional format. These pin the gradient color scale according to the color, type and value chosen.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/sheets#InterpolationPoint
    """
    color: Annotated[
        Optional[Color],
        Mode("disabled"), Field(default=None, description="The color this interpolation point should use. Deprecated: Use color_style."),
    ] = None

    type: Optional[InterpolationPointType] = Field(
        default=None, description="How the value should be interpreted.",
    )

    color_style: Optional[ColorStyle] = Field(
        default=None, description="The color this interpolation point should use. If color is also set, this field takes precedence.",
    )

    value: Optional[str] = Field(
        default=None, description="The value this interpolation point uses. May be a formula. Unused if type is MIN or MAX.",
    )


class Interval(BaseModel):
    """
    Represents a time interval, encoded as a Timestamp start (inclusive) and a Timestamp end (exclusive). The start must be less than or equal to the end. When the start equals the end, the interval is empty (matches no time). When both start and end are unspecified, the interval matches any time.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets#Interval
    """
    end_time: Optional[str] = Field(
        default=None, description="Optional. Exclusive end of the interval. If specified, a Timestamp matching this interval will have to be before the end.",
    )

    start_time: Optional[str] = Field(
        default=None, description="Optional. Inclusive start of the interval. If specified, a Timestamp matching this interval will have to be the same or after the start.",
    )


class IterativeCalculationSettings(BaseModel):
    """
    Settings to control how circular dependencies are resolved with iterative calculation.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets#IterativeCalculationSettings
    """
    convergence_threshold: Optional[float] = Field(
        default=None, description="When iterative calculation is enabled and successive results differ by less than this threshold value, the calculation rounds stop.",
    )

    max_iterations: Optional[int] = Field(
        default=None, description="When iterative calculation is enabled, the maximum number of calculation rounds to perform.",
    )


class KeyValueFormat(BaseModel):
    """
    Formatting options for key value.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/charts#KeyValueFormat
    """
    position: Optional[TextPosition] = Field(
        default=None, description="Specifies the horizontal text positioning of key value. This field is optional. If not specified, default positioning is used.",
    )

    text_format: Optional[TextFormat] = Field(
        default=None, description="Text formatting options for key value. The link field is not supported.",
    )


class LineStyle(BaseModel):
    """
    Properties that describe the style of a line.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/charts#LineStyle
    """
    type: Optional[LineStyleType] = Field(
        default=None, description="The dash type of the line.",
    )

    width: Optional[int] = Field(
        default=None, description="The thickness of the line, in px.",
    )


class Link(BaseModel):
    """
    An external or local reference.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/other#Link
    """
    uri: Optional[str] = Field(
        default=None, description="The link identifier.",
    )


class LookerDataSourceSpec(BaseModel):
    """
    The specification of a Looker data source.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets#LookerDataSourceSpec
    """
    model: Optional[str] = Field(
        default=None, description="Name of a Looker model.",
    )

    explore: Optional[str] = Field(
        default=None, description="Name of a Looker model explore.",
    )

    instance_uri: Optional[str] = Field(
        default=None, description="A Looker instance URL.",
    )


class ManualRule(BaseModel):
    """
    Allows you to manually organize the values in a source data column into buckets with names of your choosing. For example, a pivot table that aggregates population by state: +-------+-------------------+ | State | SUM of Population | +-------+-------------------+ | AK | 0.7 | | AL | 4.8 | | AR | 2.9 | ... +-------+-------------------+ could be turned into a pivot table that aggregates population by time zone by providing a list of groups (for example, groupName = 'Central', items = ['AL', 'AR', 'IA', ...]) to a manual group rule. Note that a similar effect could be achieved by adding a time zone column to the source data and adjusting the pivot table. +-----------+-------------------+ | Time Zone | SUM of Population | +-----------+-------------------+ | Central | 106.3 | | Eastern | 151.9 | | Mountain | 17.4 | ... +-----------+-------------------+

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/pivot-tables#ManualRule
    """
    groups: Optional[List[ManualRuleGroup]] = Field(
        default=None, description="The list of group names and the corresponding items from the source data that map to each group name.",
    )


class ManualRuleGroup(BaseModel):
    """
    A group name and a list of items from the source data that should be placed in the group with this name.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/pivot-tables#ManualRuleGroup
    """
    items: Optional[List[ExtendedValue]] = Field(
        default=None, description="The items in the source data that should be placed into this group. Each item may be a string, number, or boolean. Items may appear in at most one group within a given ManualRule. Items that do not appear in any group will appear on their own.",
    )

    group_name: Optional[ExtendedValue] = Field(
        default=None, description="The group name, which must be a string. Each group in a given ManualRule must have a unique group name.",
    )


class MatchedDeveloperMetadata(BaseModel):
    """
    A developer metadata entry and the data filters specified in the original request that matched it.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets#MatchedDeveloperMetadata
    """
    data_filters: Optional[List[DataFilter]] = Field(
        default=None, description="All filters matching the returned developer metadata.",
    )

    developer_metadata: Optional[DeveloperMetadata] = Field(
        default=None, description="The developer metadata matching the specified filters.",
    )


class NamedRange(BaseModel):
    """
    A named range.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets#NamedRange
    """
    name: Optional[str] = Field(
        default=None, description="The name of the named range.",
    )

    range: Optional[GridRange] = Field(
        default=None, description="The range this represents.",
    )

    named_range_id: Optional[str] = Field(
        default=None, description="The ID of the named range.",
    )


class NumberFormat(BaseModel):
    """
    The number format of a cell.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/cells#NumberFormat
    """
    pattern: Optional[str] = Field(
        default=None, description="Pattern string used for formatting. If not set, a default pattern based on the spreadsheet's locale will be used if necessary for the given type. See the [Date and Number Formats guide](https://developers.google.com/workspace/sheets/api/guides/formats) for more information about the supported patterns.",
    )

    type: Optional[NumberFormatType] = Field(
        default=None, description="The type of the number format. When writing, this field must be set.",
    )


class OrgChartSpec(BaseModel):
    """
    An org chart. Org charts require a unique set of labels in labels and may optionally include parent_labels and tooltips. parent_labels contain, for each node, the label identifying the parent node. tooltips contain, for each node, an optional tooltip. For example, to describe an OrgChart with Alice as the CEO, Bob as the President (reporting to Alice) and Cathy as VP of Sales (also reporting to Alice), have labels contain "Alice", "Bob", "Cathy", parent_labels contain "", "Alice", "Alice" and tooltips contain "CEO", "President", "VP Sales".

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/charts#OrgChartSpec
    """
    selected_node_color: Annotated[
        Optional[Color],
        Mode("disabled"), Field(default=None, description="The color of the selected org chart nodes. Deprecated: Use selected_node_color_style."),
    ] = None

    parent_labels: Optional[ChartData] = Field(
        default=None, description="The data containing the label of the parent for the corresponding node. A blank value indicates that the node has no parent and is a top-level node. This field is optional.",
    )

    node_color_style: Optional[ColorStyle] = Field(
        default=None, description="The color of the org chart nodes. If node_color is also set, this field takes precedence.",
    )

    node_size: Optional[OrgChartSpecNodeSize] = Field(
        default=None, description="The size of the org chart nodes.",
    )

    tooltips: Optional[ChartData] = Field(
        default=None, description="The data containing the tooltip for the corresponding node. A blank value results in no tooltip being displayed for the node. This field is optional.",
    )

    labels: Optional[ChartData] = Field(
        default=None, description="The data containing the labels for all the nodes in the chart. Labels must be unique.",
    )

    node_color: Annotated[
        Optional[Color],
        Mode("disabled"), Field(default=None, description="The color of the org chart nodes. Deprecated: Use node_color_style."),
    ] = None

    selected_node_color_style: Optional[ColorStyle] = Field(
        default=None, description="The color of the selected org chart nodes. If selected_node_color is also set, this field takes precedence.",
    )


class OverlayPosition(BaseModel):
    """
    The location an object is overlaid on top of a grid.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/other#OverlayPosition
    """
    offset_y_pixels: Optional[int] = Field(
        default=None, description="The vertical offset, in pixels, that the object is offset from the anchor cell.",
    )

    height_pixels: Optional[int] = Field(
        default=None, description="The height of the object, in pixels. Defaults to 371.",
    )

    anchor_cell: Optional[GridCoordinate] = Field(
        default=None, description="The cell the object is anchored to.",
    )

    width_pixels: Optional[int] = Field(
        default=None, description="The width of the object, in pixels. Defaults to 600.",
    )

    offset_x_pixels: Optional[int] = Field(
        default=None, description="The horizontal offset, in pixels, that the object is offset from the anchor cell.",
    )


class Padding(BaseModel):
    """
    The amount of padding around the cell, in pixels. When updating padding, every field must be specified.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/cells#Padding
    """
    right: Optional[int] = Field(
        default=None, description="The right padding of the cell.",
    )

    left: Optional[int] = Field(
        default=None, description="The left padding of the cell.",
    )

    bottom: Optional[int] = Field(
        default=None, description="The bottom padding of the cell.",
    )

    top: Optional[int] = Field(
        default=None, description="The top padding of the cell.",
    )


class PersonProperties(BaseModel):
    """
    Properties specific to a linked person.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/cells#PersonProperties
    """
    email: Optional[str] = Field(
        default=None, description="Required. The email address linked to this person. This field is always present.",
    )

    display_format: Optional[PersonPropertiesDisplayFormat] = Field(
        default=None, description="Optional. The display format of the person chip. If not set, the default display format is used.",
    )


class PieChartSpec(BaseModel):
    """
    A pie chart.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/charts#PieChartSpec
    """
    domain: Optional[ChartData] = Field(
        default=None, description="The data that covers the domain of the pie chart.",
    )

    legend_position: Optional[PieChartSpecLegendPosition] = Field(
        default=None, description="Where the legend of the pie chart should be drawn.",
    )

    series: Optional[ChartData] = Field(
        default=None, description="The data that covers the one and only series of the pie chart.",
    )

    pie_hole: Optional[float] = Field(
        default=None, description="The size of the hole in the pie chart.",
    )

    three_dimensional: Optional[bool] = Field(
        default=None, description="True if the pie is three dimensional.",
    )


class PivotFilterCriteria(BaseModel):
    """
    Criteria for showing/hiding rows in a pivot table.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/pivot-tables#PivotFilterCriteria
    """
    visible_by_default: Optional[bool] = Field(
        default=None, description="Whether values are visible by default. If true, the visible_values are ignored, all values that meet condition (if specified) are shown. If false, values that are both in visible_values and meet condition are shown.",
    )

    visible_values: Optional[List[str]] = Field(
        default=None, description="Values that should be included. Values not listed here are excluded.",
    )

    condition: Optional[BooleanCondition] = Field(
        default=None, description="A condition that must be true for values to be shown. (`visibleValues` does not override this -- even if a value is listed there, it is still hidden if it does not meet the condition.) Condition values that refer to ranges in A1-notation are evaluated relative to the pivot table sheet. References are treated absolutely, so are not filled down the pivot table. For example, a condition value of `=A1` on \"Pivot Table 1\" is treated as `'Pivot Table 1'!$A$1`. The source data of the pivot table can be referenced by column header name. For example, if the source data has columns named \"Revenue\" and \"Cost\" and a condition is applied to the \"Revenue\" column with type `NUMBER_GREATER` and value `=Cost`, then only columns where \"Revenue\" > \"Cost\" are included.",
    )


class PivotFilterSpec(BaseModel):
    """
    The pivot table filter criteria associated with a specific source column offset.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/pivot-tables#PivotFilterSpec
    """
    data_source_column_reference: Optional[DataSourceColumnReference] = Field(
        default=None, description="The reference to the data source column.",
    )

    filter_criteria: Optional[PivotFilterCriteria] = Field(
        default=None, description="The criteria for the column.",
    )

    column_offset_index: Optional[int] = Field(
        default=None, description="The zero-based column offset of the source range.",
    )

    @model_validator(mode="after")
    def _at_most_one(self) -> PivotFilterSpec:
        provided = [n for n in ('column_offset_index', 'data_source_column_reference') if getattr(self, n) is not None]
        if len(provided) > 1:
            raise ValueError(
                f"At most one of 'column_offset_index', 'data_source_column_reference' may be set, found: {provided}"
            )
        return self


class PivotGroup(BaseModel):
    """
    A single grouping (either row or column) in a pivot table.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/pivot-tables#PivotGroup
    """
    show_totals: Optional[bool] = Field(
        default=None, description="True if the pivot table should include the totals for this grouping.",
    )

    label: Optional[str] = Field(
        default=None, description="The labels to use for the row/column groups which can be customized. For example, in the following pivot table, the row label is `Region` (which could be renamed to `State`) and the column label is `Product` (which could be renamed `Item`). Pivot tables created before December 2017 do not have header labels. If you'd like to add header labels to an existing pivot table, please delete the existing pivot table and then create a new pivot table with same parameters. +--------------+---------+-------+ | SUM of Units | Product | | | Region | Pen | Paper | +--------------+---------+-------+ | New York | 345 | 98 | | Oregon | 234 | 123 | | Tennessee | 531 | 415 | +--------------+---------+-------+ | Grand Total | 1110 | 636 | +--------------+---------+-------+",
    )

    source_column_offset: Optional[int] = Field(
        default=None, description="The column offset of the source range that this grouping is based on. For example, if the source was `C10:E15`, a `sourceColumnOffset` of `0` means this group refers to column `C`, whereas the offset `1` would refer to column `D`.",
    )

    value_bucket: Optional[PivotGroupSortValueBucket] = Field(
        default=None, description="The bucket of the opposite pivot group to sort by. If not specified, sorting is alphabetical by this group's values.",
    )

    repeat_headings: Optional[bool] = Field(
        default=None, description="True if the headings in this pivot group should be repeated. This is only valid for row groupings and is ignored by columns. By default, we minimize repetition of headings by not showing higher level headings where they are the same. For example, even though the third row below corresponds to \"Q1 Mar\", \"Q1\" is not shown because it is redundant with previous rows. Setting repeat_headings to true would cause \"Q1\" to be repeated for \"Feb\" and \"Mar\". +--------------+ | Q1 | Jan | | | Feb | | | Mar | +--------+-----+ | Q1 Total | +--------------+",
    )

    value_metadata: Optional[List[PivotGroupValueMetadata]] = Field(
        default=None, description="Metadata about values in the grouping.",
    )

    group_rule: Optional[PivotGroupRule] = Field(
        default=None, description="The group rule to apply to this row/column group.",
    )

    sort_order: Optional[SortOrder] = Field(
        default=None, description="The order the values in this group should be sorted.",
    )

    group_limit: Optional[PivotGroupLimit] = Field(
        default=None, description="The count limit on rows or columns to apply to this pivot group.",
    )

    data_source_column_reference: Optional[DataSourceColumnReference] = Field(
        default=None, description="The reference to the data source column this grouping is based on.",
    )

    @model_validator(mode="after")
    def _at_most_one(self) -> PivotGroup:
        provided = [n for n in ('source_column_offset', 'data_source_column_reference') if getattr(self, n) is not None]
        if len(provided) > 1:
            raise ValueError(
                f"At most one of 'source_column_offset', 'data_source_column_reference' may be set, found: {provided}"
            )
        return self


class PivotGroupLimit(BaseModel):
    """
    The count limit on rows or columns in the pivot group.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/pivot-tables#PivotGroupLimit
    """
    count_limit: Optional[int] = Field(
        default=None, description="The count limit.",
    )

    apply_order: Optional[int] = Field(
        default=None, description="The order in which the group limit is applied to the pivot table. Pivot group limits are applied from lower to higher order number. Order numbers are normalized to consecutive integers from 0. For write request, to fully customize the applying orders, all pivot group limits should have this field set with an unique number. Otherwise, the order is determined by the index in the PivotTable.rows list and then the PivotTable.columns list.",
    )


class PivotGroupRule(BaseModel):
    """
    An optional setting on a PivotGroup that defines buckets for the values in the source data column rather than breaking out each individual value. Only one PivotGroup with a group rule may be added for each column in the source data, though on any given column you may add both a PivotGroup that has a rule and a PivotGroup that does not.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/pivot-tables#PivotGroupRule
    """
    manual_rule: Optional[ManualRule] = Field(
        default=None, description="A ManualRule.",
    )

    date_time_rule: Optional[DateTimeRule] = Field(
        default=None, description="A DateTimeRule.",
    )

    histogram_rule: Optional[HistogramRule] = Field(
        default=None, description="A HistogramRule.",
    )

    @model_validator(mode="after")
    def _at_most_one(self) -> PivotGroupRule:
        provided = [n for n in ('manual_rule', 'histogram_rule', 'date_time_rule') if getattr(self, n) is not None]
        if len(provided) > 1:
            raise ValueError(
                f"At most one of 'manual_rule', 'histogram_rule', 'date_time_rule' may be set, found: {provided}"
            )
        return self


class PivotGroupSortValueBucket(BaseModel):
    """
    Information about which values in a pivot group should be used for sorting.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/pivot-tables#PivotGroupSortValueBucket
    """
    values_index: Optional[int] = Field(
        default=None, description="The offset in the PivotTable.values list which the values in this grouping should be sorted by.",
    )

    buckets: Optional[List[ExtendedValue]] = Field(
        default=None, description="Determines the bucket from which values are chosen to sort. For example, in a pivot table with one row group & two column groups, the row group can list up to two values. The first value corresponds to a value within the first column group, and the second value corresponds to a value in the second column group. If no values are listed, this would indicate that the row should be sorted according to the \"Grand Total\" over the column groups. If a single value is listed, this would correspond to using the \"Total\" of that bucket.",
    )


class PivotGroupValueMetadata(BaseModel):
    """
    Metadata about a value in a pivot grouping.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/pivot-tables#PivotGroupValueMetadata
    """
    collapsed: Optional[bool] = Field(
        default=None, description="True if the data corresponding to the value is collapsed.",
    )

    value: Optional[ExtendedValue] = Field(
        default=None, description="The calculated value the metadata corresponds to. (Note that formulaValue is not valid, because the values will be calculated.)",
    )


class PivotTable(BaseModel):
    """
    A pivot table.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/pivot-tables#PivotTable
    """
    filter_specs: Optional[List[PivotFilterSpec]] = Field(
        default=None, description="The filters applied to the source columns before aggregating data for the pivot table. Both criteria and filter_specs are populated in responses. If both fields are specified in an update request, this field takes precedence.",
    )

    source: Optional[GridRange] = Field(
        default=None, description="The range the pivot table is reading data from.",
    )

    values: Optional[List[PivotValue]] = Field(
        default=None, description="A list of values to include in the pivot table.",
    )

    data_source_id: Optional[str] = Field(
        default=None, description="The ID of the data source the pivot table is reading data from.",
    )

    value_layout: Optional[PivotTableValueLayout] = Field(
        default=None, description="Whether values should be listed horizontally (as columns) or vertically (as rows).",
    )

    criteria: Annotated[
        Optional[Dict[str, PivotFilterCriteria]],
        Mode("disabled"), Field(default=None, description="An optional mapping of filters per source column offset. The filters are applied before aggregating data into the pivot table. The map's key is the column offset of the source range that you want to filter, and the value is the criteria for that column. For example, if the source was `C10:E15`, a key of `0` will have the filter for column `C`, whereas the key `1` is for column `D`. This field is deprecated in favor of filter_specs."),
    ] = None

    data_execution_status: Annotated[
        Optional[DataExecutionStatus],
        Mode("response_only"), Field(default=None, description="Output only. The data execution status for data source pivot tables."),
    ] = None

    rows: Optional[List[PivotGroup]] = Field(
        default=None, description="Each row grouping in the pivot table.",
    )

    columns: Optional[List[PivotGroup]] = Field(
        default=None, description="Each column grouping in the pivot table.",
    )

    @model_validator(mode="after")
    def _at_most_one(self) -> PivotTable:
        provided = [n for n in ('source', 'data_source_id') if getattr(self, n) is not None]
        if len(provided) > 1:
            raise ValueError(
                f"At most one of 'source', 'data_source_id' may be set, found: {provided}"
            )
        return self


class PivotValue(BaseModel):
    """
    The definition of how a value in a pivot table should be calculated.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/pivot-tables#PivotValue
    """
    data_source_column_reference: Optional[DataSourceColumnReference] = Field(
        default=None, description="The reference to the data source column that this value reads from.",
    )

    calculated_display_type: Optional[PivotValueCalculatedDisplayType] = Field(
        default=None, description="If specified, indicates that pivot values should be displayed as the result of a calculation with another pivot value. For example, if calculated_display_type is specified as PERCENT_OF_GRAND_TOTAL, all the pivot values are displayed as the percentage of the grand total. In the Sheets editor, this is referred to as \"Show As\" in the value section of a pivot table.",
    )

    name: Optional[str] = Field(
        default=None, description="A name to use for the value.",
    )

    summarize_function: Optional[PivotValueSummarizeFunction] = Field(
        default=None, description="A function to summarize the value. If formula is set, the only supported values are SUM and CUSTOM. If sourceColumnOffset is set, then `CUSTOM` is not supported.",
    )

    source_column_offset: Optional[int] = Field(
        default=None, description="The column offset of the source range that this value reads from. For example, if the source was `C10:E15`, a `sourceColumnOffset` of `0` means this value refers to column `C`, whereas the offset `1` would refer to column `D`.",
    )

    formula: Optional[str] = Field(
        default=None, description="A custom formula to calculate the value. The formula must start with an `=` character.",
    )

    @model_validator(mode="after")
    def _exactly_one(self) -> PivotValue:
        provided = [n for n in ('formula', 'source_column_offset', 'data_source_column_reference') if getattr(self, n) is not None]
        if len(provided) != 1:
            raise ValueError(
                f"Exactly one of 'formula', 'source_column_offset', 'data_source_column_reference' must be set, found: {provided}"
            )
        return self


class PointStyle(BaseModel):
    """
    The style of a point on the chart.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/charts#PointStyle
    """
    shape: Optional[PointStyleShape] = Field(
        default=None, description="The point shape. If empty or unspecified, a default shape is used.",
    )

    size: Optional[float] = Field(
        default=None, description="The point size. If empty, a default size is used.",
    )


class ProtectedRange(BaseModel):
    """
    A protected range.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/sheets#ProtectedRange
    """
    named_range_id: Optional[str] = Field(
        default=None, description="The named range this protected range is backed by, if any. When writing, only one of range or named_range_id or table_id may be set.",
    )

    unprotected_ranges: Optional[List[GridRange]] = Field(
        default=None, description="The list of unprotected ranges within a protected sheet. Unprotected ranges are only supported on protected sheets.",
    )

    description: Optional[str] = Field(
        default=None, description="The description of this protected range.",
    )

    warning_only: Optional[bool] = Field(
        default=None, description="True if this protected range will show a warning when editing. Warning-based protection means that every user can edit data in the protected range, except editing will prompt a warning asking the user to confirm the edit. When writing: if this field is true, then editors are ignored. Additionally, if this field is changed from true to false and the `editors` field is not set (nor included in the field mask), then the editors will be set to all the editors in the document.",
    )

    editors: Optional[Editors] = Field(
        default=None, description="The users and groups with edit access to the protected range. This field is only visible to users with edit access to the protected range and the document. Editors are not supported with warning_only protection.",
    )

    requesting_user_can_edit: Annotated[
        Optional[bool],
        Mode("response_only"), Field(default=None, description="True if the user who requested this protected range can edit the protected area. This field is read-only."),
    ] = None

    table_id: Optional[str] = Field(
        default=None, description="The table this protected range is backed by, if any. When writing, only one of range or named_range_id or table_id may be set.",
    )

    protected_range_id: Annotated[
        Optional[int],
        Mode("response_only"), Field(default=None, description="The ID of the protected range. This field is read-only."),
    ] = None

    range: Optional[GridRange] = Field(
        default=None, description="The range that is being protected. The range may be fully unbounded, in which case this is considered a protected sheet. When writing, only one of range or named_range_id or table_id may be set.",
    )


class RichLinkProperties(BaseModel):
    """
    Properties of a link to a Google resource (such as a file in Drive, a YouTube video, a Maps address, or a Calendar event). Only Drive files can be written as chips. All other rich link types are read only. URIs cannot exceed 2000 bytes when writing. NOTE: Writing Drive file chips requires at least one of the `drive.file`, `drive.readonly`, or `drive` OAuth scopes.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/cells#RichLinkProperties
    """
    mime_type: Annotated[
        Optional[str],
        Mode("response_only"), Field(default=None, description="Output only. The [MIME type](https://developers.google.com/drive/api/v3/mime-types) of the link, if there's one (for example, when it's a file in Drive)."),
    ] = None

    uri: Optional[str] = Field(
        default=None, description="Required. The URI to the link. This is always present.",
    )


class RowData(BaseModel):
    """
    Data about each cell in a row.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/sheets#RowData
    """
    values: Optional[List[CellData]] = Field(
        default=None, description="The values in the row, one per column.",
    )


class ScorecardChartSpec(BaseModel):
    """
    A scorecard chart. Scorecard charts are used to highlight key performance indicators, known as KPIs, on the spreadsheet. A scorecard chart can represent things like total sales, average cost, or a top selling item. You can specify a single data value, or aggregate over a range of data. Percentage or absolute difference from a baseline value can be highlighted, like changes over time.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/charts#ScorecardChartSpec
    """
    aggregate_type: Optional[ScorecardChartSpecAggregateType] = Field(
        default=None, description="The aggregation type for key and baseline chart data in scorecard chart. This field is not supported for data source charts. Use the ChartData.aggregateType field of the key_value_data or baseline_value_data instead for data source charts. This field is optional.",
    )

    custom_format_options: Optional[ChartCustomNumberFormatOptions] = Field(
        default=None, description="Custom formatting options for numeric key/baseline values in scorecard chart. This field is used only when number_format_source is set to CUSTOM. This field is optional.",
    )

    number_format_source: Optional[ScorecardChartSpecNumberFormatSource] = Field(
        default=None, description="The number format source used in the scorecard chart. This field is optional.",
    )

    key_value_data: Optional[ChartData] = Field(
        default=None, description="The data for scorecard key value.",
    )

    key_value_format: Optional[KeyValueFormat] = Field(
        default=None, description="Formatting options for key value.",
    )

    baseline_value_data: Optional[ChartData] = Field(
        default=None, description="The data for scorecard baseline value. This field is optional.",
    )

    baseline_value_format: Optional[BaselineValueFormat] = Field(
        default=None, description="Formatting options for baseline value. This field is needed only if baseline_value_data is specified.",
    )

    scale_factor: Optional[float] = Field(
        default=None, description="Value to scale scorecard key and baseline value. For example, a factor of 10 can be used to divide all values in the chart by 10. This field is optional.",
    )


class SearchDeveloperMetadataRequest(BaseModel):
    """
    A request to retrieve all developer metadata matching the set of specified criteria.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets#SearchDeveloperMetadataRequest
    """
    data_filters: Optional[List[DataFilter]] = Field(
        default=None, description="The data filters describing the criteria used to determine which DeveloperMetadata entries to return. DeveloperMetadata matching any of the specified filters are included in the response.",
    )


class SearchDeveloperMetadataResponse(BaseModel):
    """
    A reply to a developer metadata search request.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets#SearchDeveloperMetadataResponse
    """
    matched_developer_metadata: Optional[List[MatchedDeveloperMetadata]] = Field(
        default=None, description="The metadata matching the criteria of the search request.",
    )


class Sheet(BaseModel):
    """
    A sheet in a spreadsheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/sheets#Sheet
    """
    row_groups: Optional[List[DimensionGroup]] = Field(
        default=None, description="All row groups on this sheet, ordered by increasing range start index, then by group depth.",
    )

    slicers: Optional[List[Slicer]] = Field(
        default=None, description="The slicers on this sheet.",
    )

    tables: Optional[List[Table]] = Field(
        default=None, description="The tables on this sheet.",
    )

    conditional_formats: Optional[List[ConditionalFormatRule]] = Field(
        default=None, description="The conditional format rules in this sheet.",
    )

    basic_filter: Optional[BasicFilter] = Field(
        default=None, description="The filter on this sheet, if any.",
    )

    merges: Optional[List[GridRange]] = Field(
        default=None, description="The ranges that are merged together.",
    )

    column_groups: Optional[List[DimensionGroup]] = Field(
        default=None, description="All column groups on this sheet, ordered by increasing range start index, then by group depth.",
    )

    properties: Optional[SheetProperties] = Field(
        default=None, description="The properties of the sheet.",
    )

    banded_ranges: Optional[List[BandedRange]] = Field(
        default=None, description="The banded (alternating colors) ranges on this sheet.",
    )

    developer_metadata: Optional[List[DeveloperMetadata]] = Field(
        default=None, description="The developer metadata associated with a sheet.",
    )

    data: Optional[List[GridData]] = Field(
        default=None, description="Data in the grid, if this is a grid sheet. The number of GridData objects returned is dependent on the number of ranges requested on this sheet. For example, if this is representing `Sheet1`, and the spreadsheet was requested with ranges `Sheet1!A1:C10` and `Sheet1!D15:E20`, then the first GridData will have a startRow/startColumn of `0`, while the second one will have `startRow 14` (zero-based row 15), and `startColumn 3` (zero-based column D). For a DATA_SOURCE sheet, you can not request a specific range, the GridData contains all the values.",
    )

    charts: Optional[List[EmbeddedChart]] = Field(
        default=None, description="The specifications of every chart on this sheet.",
    )

    filter_views: Optional[List[FilterView]] = Field(
        default=None, description="The filter views in this sheet.",
    )

    protected_ranges: Optional[List[ProtectedRange]] = Field(
        default=None, description="The protected ranges in this sheet.",
    )

    comment_anchors: Optional[List[CommentAnchor]] = Field(
        default=None, description="The comment anchors on this sheet. Developer Preview.",
    )


class SheetProperties(BaseModel):
    """
    Properties of a sheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/sheets#SheetProperties
    """
    title: Optional[str] = Field(
        default=None, description="The name of the sheet.",
    )

    hidden: Optional[bool] = Field(
        default=None, description="True if the sheet is hidden in the UI, false if it's visible.",
    )

    right_to_left: Optional[bool] = Field(
        default=None, description="True if the sheet is an RTL sheet instead of an LTR sheet.",
    )

    grid_properties: Optional[GridProperties] = Field(
        default=None, description="Additional properties of the sheet if this sheet is a grid. (If the sheet is an object sheet, containing a chart or image, then this field will be absent.) When writing it is an error to set any grid properties on non-grid sheets. If this sheet is a DATA_SOURCE sheet, this field is output only but contains the properties that reflect how a data source sheet is rendered in the UI, e.g. row_count.",
    )

    sheet_id: Optional[int] = Field(
        default=None, ge=0, description="The ID of the sheet. Must be non-negative. This field cannot be changed once set.",
    )

    data_source_sheet_properties: Annotated[
        Optional[DataSourceSheetProperties],
        Mode("response_only"), Field(default=None, description="Output only. If present, the field contains DATA_SOURCE sheet specific properties."),
    ] = None

    sheet_type: Optional[SheetType] = Field(
        default=None, description="The type of sheet. Defaults to GRID. This field cannot be changed once set.",
    )

    tab_color_style: Optional[ColorStyle] = Field(
        default=None, description="The color of the tab in the UI. If tab_color is also set, this field takes precedence.",
    )

    tab_color: Annotated[
        Optional[Color],
        Mode("disabled"), Field(default=None, description="The color of the tab in the UI. Deprecated: Use tab_color_style."),
    ] = None

    index: Optional[int] = Field(
        default=None, description="The index of the sheet within the spreadsheet. When adding or updating sheet properties, if this field is excluded then the sheet is added or moved to the end of the sheet list. When updating sheet indices or inserting sheets, movement is considered in \"before the move\" indexes. For example, if there were three sheets (S1, S2, S3) in order to move S1 ahead of S2 the index would have to be set to 2. A sheet index update request is ignored if the requested index is identical to the sheets current index or if the requested new index is equal to the current sheet index + 1.",
    )


class Slicer(BaseModel):
    """
    A slicer in a sheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/sheets#Slicer
    """
    spec: Optional[SlicerSpec] = Field(
        default=None, description="The specification of the slicer.",
    )

    slicer_id: Optional[int] = Field(
        default=None, description="The ID of the slicer.",
    )

    position: Optional[EmbeddedObjectPosition] = Field(
        default=None, description="The position of the slicer. Note that slicer can be positioned only on existing sheet. Also, width and height of slicer can be automatically adjusted to keep it within permitted limits.",
    )


class SlicerSpec(BaseModel):
    """
    The specifications of a slicer.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/sheets#SlicerSpec
    """
    data_range: Optional[GridRange] = Field(
        default=None, description="The data range of the slicer.",
    )

    background_color: Annotated[
        Optional[Color],
        Mode("disabled"), Field(default=None, description="The background color of the slicer. Deprecated: Use background_color_style."),
    ] = None

    title: Optional[str] = Field(
        default=None, description="The title of the slicer.",
    )

    text_format: Optional[TextFormat] = Field(
        default=None, description="The text format of title in the slicer. The link field is not supported.",
    )

    column_index: Optional[int] = Field(
        default=None, description="The zero-based column index in the data table on which the filter is applied to.",
    )

    filter_criteria: Optional[FilterCriteria] = Field(
        default=None, description="The filtering criteria of the slicer.",
    )

    horizontal_alignment: Optional[HorizontalAlign] = Field(
        default=None, description="The horizontal alignment of title in the slicer. If unspecified, defaults to `LEFT`",
    )

    background_color_style: Optional[ColorStyle] = Field(
        default=None, description="The background color of the slicer. If background_color is also set, this field takes precedence.",
    )

    apply_to_pivot_tables: Optional[bool] = Field(
        default=None, description="True if the filter should apply to pivot tables. If not set, default to `True`.",
    )


class SortSpec(BaseModel):
    """
    A sort order associated with a specific column or row.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/other#SortSpec
    """
    sort_order: Optional[SortOrder] = Field(
        default=None, description="The order data should be sorted.",
    )

    foreground_color: Annotated[
        Optional[Color],
        Mode("disabled"), Field(default=None, description="The foreground color to sort by; cells with this foreground color are sorted to the top. Mutually exclusive with background_color. Deprecated: Use foreground_color_style."),
    ] = None

    background_color: Annotated[
        Optional[Color],
        Mode("disabled"), Field(default=None, description="The background fill color to sort by; cells with this fill color are sorted to the top. Mutually exclusive with foreground_color. Deprecated: Use background_color_style."),
    ] = None

    data_source_column_reference: Optional[DataSourceColumnReference] = Field(
        default=None, description="Reference to a data source column.",
    )

    background_color_style: Optional[ColorStyle] = Field(
        default=None, description="The background fill color to sort by; cells with this fill color are sorted to the top. Mutually exclusive with foreground_color, and must be an RGB-type color. If background_color is also set, this field takes precedence.",
    )

    dimension_index: Optional[int] = Field(
        default=None, description="The dimension the sort should be applied to.",
    )

    foreground_color_style: Optional[ColorStyle] = Field(
        default=None, description="The foreground color to sort by; cells with this foreground color are sorted to the top. Mutually exclusive with background_color, and must be an RGB-type color. If foreground_color is also set, this field takes precedence.",
    )

    @model_validator(mode="after")
    def _at_most_one(self) -> SortSpec:
        provided = [n for n in ('dimension_index', 'data_source_column_reference') if getattr(self, n) is not None]
        if len(provided) > 1:
            raise ValueError(
                f"At most one of 'dimension_index', 'data_source_column_reference' may be set, found: {provided}"
            )
        return self


class Spreadsheet(BaseModel):
    """
    Resource that represents a spreadsheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets#Spreadsheet
    """
    properties: Optional[SpreadsheetProperties] = Field(
        default=None, description="Overall properties of a spreadsheet.",
    )

    sheets: Optional[List[Sheet]] = Field(
        default=None, description="The sheets that are part of a spreadsheet.",
    )

    spreadsheet_url: Annotated[
        Optional[str],
        Mode("response_only"), Field(default=None, description="The url of the spreadsheet. This field is read-only."),
    ] = None

    developer_metadata: Optional[List[DeveloperMetadata]] = Field(
        default=None, description="The developer metadata associated with a spreadsheet.",
    )

    data_sources: Optional[List[DataSource]] = Field(
        default=None, description="A list of external data sources connected with the spreadsheet.",
    )

    data_source_schedules: Annotated[
        Optional[List[DataSourceRefreshSchedule]],
        Mode("response_only"), Field(default=None, description="Output only. A list of data source refresh schedules."),
    ] = None

    named_ranges: Optional[List[NamedRange]] = Field(
        default=None, description="The named ranges defined in a spreadsheet.",
    )

    spreadsheet_id: Annotated[
        Optional[str],
        Mode("response_only"), Field(default=None, description="The ID of the spreadsheet. This field is read-only."),
    ] = None

    comments: Optional[List[CommentThread]] = Field(
        default=None,
        description="The comment threads associated with the spreadsheet. Developer Preview.",
    )

    comments_view_mode: Annotated[
        Optional[CommentsViewMode],
        Mode("response_only"),
        Field(
            default=None,
            description=(
                "Output only. The comments view mode applied to the spreadsheet. "
                "Developer Preview."
            ),
        ),
    ] = None


class SpreadsheetProperties(BaseModel):
    """
    Properties of a spreadsheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets#SpreadsheetProperties
    """
    import_functions_external_url_access_allowed: Optional[bool] = Field(
        default=None, description="Whether to allow external URL access for image and import functions. Read only when true. When false, you can set to true. This value will be bypassed and always return true if the admin has enabled the [allowlisting feature](https://support.google.com/a?p=url_allowlist).",
    )

    default_format: Annotated[
        Optional[CellFormat],
        Mode("response_only"), Field(default=None, description="The default format of all cells in the spreadsheet. CellData.effectiveFormat will not be set if the cell's format is equal to this default format. This field is read-only."),
    ] = None

    locale: Optional[str] = Field(
        default=None, description="The locale of the spreadsheet in one of the following formats: * an ISO 639-1 language code such as `en` * an ISO 639-2 language code such as `fil`, if no 639-1 code exists * a combination of the ISO language code and country code, such as `en_US` Note: when updating this field, not all locales/languages are supported.",
    )

    auto_recalc: Optional[RecalculationInterval] = Field(
        default=None, description="The amount of time to wait before volatile functions are recalculated.",
    )

    title: Optional[str] = Field(
        default=None, description="The title of the spreadsheet.",
    )

    spreadsheet_theme: Optional[SpreadsheetTheme] = Field(
        default=None, description="Theme applied to the spreadsheet.",
    )

    time_zone: Optional[str] = Field(
        default=None, description="The time zone of the spreadsheet, in CLDR format such as `America/New_York`. If the time zone isn't recognized, this may be a custom time zone such as `GMT-07:00`.",
    )

    iterative_calculation_settings: Optional[IterativeCalculationSettings] = Field(
        default=None, description="Determines whether and how circular references are resolved with iterative calculation. Absence of this field means that circular references result in calculation errors.",
    )


class SpreadsheetTheme(BaseModel):
    """
    Represents spreadsheet theme

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets#SpreadsheetTheme
    """
    theme_colors: Optional[List[ThemeColorPair]] = Field(
        default=None, description="The spreadsheet theme color pairs. To update you must provide all theme color pairs.",
    )

    primary_font_family: Optional[str] = Field(
        default=None, description="Name of the primary font family.",
    )


class Table(BaseModel):
    """
    A table.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/sheets#Table
    """
    name: Optional[str] = Field(
        default=None, description="The table name. This is unique to all tables in the same spreadsheet.",
    )

    rows_properties: Optional[TableRowsProperties] = Field(
        default=None, description="The table rows properties.",
    )

    table_id: Optional[str] = Field(
        default=None, description="The id of the table.",
    )

    range: Optional[GridRange] = Field(
        default=None, description="The table range.",
    )

    column_properties: Optional[List[TableColumnProperties]] = Field(
        default=None, description="The table column properties.",
    )


class TableColumnDataValidationRule(BaseModel):
    """
    A data validation rule for a column in a table.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/sheets#TableColumnDataValidationRule
    """
    condition: Optional[BooleanCondition] = Field(
        default=None, description="The condition that data in the cell must match. Valid only if the [BooleanCondition.type] is ONE_OF_LIST.",
    )


class TableColumnProperties(BaseModel):
    """
    The table column.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/sheets#TableColumnProperties
    """
    column_name: Optional[str] = Field(
        default=None, description="The column name.",
    )

    data_validation_rule: Optional[TableColumnDataValidationRule] = Field(
        default=None, description="The column data validation rule. Only set for dropdown column type.",
    )

    column_type: Optional[TableColumnPropertiesColumnType] = Field(
        default=None, description="The column type.",
    )

    column_index: Optional[int] = Field(
        default=None, description="The 0-based column index. This index is relative to its position in the table and is not necessarily the same as the column index in the sheet.",
    )


class TableRowsProperties(BaseModel):
    """
    The table row properties.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/sheets#TableRowsProperties
    """
    footer_color_style: Optional[ColorStyle] = Field(
        default=None, description="The color of the last row. If this field is not set a footer is not added, the last row is filled with either first_band_color_style or second_band_color_style, depending on the color of the previous row. If updating an existing table without a footer to have a footer, the range will be expanded by 1 row. If updating an existing table with a footer and removing a footer, the range will be shrunk by 1 row.",
    )

    header_color_style: Optional[ColorStyle] = Field(
        default=None, description="The color of the header row. If this field is set, the header row is filled with the specified color. Otherwise, the header row is filled with a default color.",
    )

    first_band_color_style: Optional[ColorStyle] = Field(
        default=None, description="The first color that is alternating. If this field is set, the first banded row is filled with the specified color. Otherwise, the first banded row is filled with a default color.",
    )

    second_band_color_style: Optional[ColorStyle] = Field(
        default=None, description="The second color that is alternating. If this field is set, the second banded row is filled with the specified color. Otherwise, the second banded row is filled with a default color.",
    )


class TextFormat(BaseModel):
    """
    The format of a run of text in a cell. Absent values indicate that the field isn't specified.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/other#TextFormat
    """
    font_family: Optional[str] = Field(
        default=None, description="The font family.",
    )

    strikethrough: Optional[bool] = Field(
        default=None, description="True if the text has a strikethrough.",
    )

    underline: Optional[bool] = Field(
        default=None, description="True if the text is underlined.",
    )

    foreground_color_style: Optional[ColorStyle] = Field(
        default=None, description="The foreground color of the text. If foreground_color is also set, this field takes precedence.",
    )

    bold: Optional[bool] = Field(
        default=None, description="True if the text is bold.",
    )

    font_size: Optional[int] = Field(
        default=None, description="The size of the font.",
    )

    italic: Optional[bool] = Field(
        default=None, description="True if the text is italicized.",
    )

    link: Optional[Link] = Field(
        default=None, description="The link destination of the text, if any. Setting the link field in a TextFormatRun will clear the cell's existing links or a cell-level link set in the same request. When a link is set, the text foreground color will be set to the default link color and the text will be underlined. If these fields are modified in the same request, those values will be used instead of the link defaults.",
    )

    foreground_color: Annotated[
        Optional[Color],
        Mode("disabled"), Field(default=None, description="The foreground color of the text. Deprecated: Use foreground_color_style."),
    ] = None


class TextFormatRun(BaseModel):
    """
    A run of a text format. The format of this run continues until the start index of the next run. When updating, all fields must be set.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/cells#TextFormatRun
    """
    start_index: Optional[int] = Field(
        default=None, description="The zero-based character index where this run starts, in UTF-16 code units.",
    )

    format: Optional[TextFormat] = Field(
        default=None, description="The format of this run. Absent values inherit the cell's format.",
    )


class TextPosition(BaseModel):
    """
    Position settings for text.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/charts#TextPosition
    """
    horizontal_alignment: Optional[HorizontalAlign] = Field(
        default=None, description="Horizontal alignment setting for the piece of text.",
    )


class TextRotation(BaseModel):
    """
    The rotation applied to text in a cell.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/cells#TextRotation
    """
    angle: Optional[int] = Field(
        default=None, description="The angle between the standard orientation and the desired orientation. Measured in degrees. Valid values are between -90 and 90. Positive angles are angled upwards, negative are angled downwards. Note: For LTR text direction positive angles are in the counterclockwise direction, whereas for RTL they are in the clockwise direction",
    )

    vertical: Optional[bool] = Field(
        default=None, description="If true, text reads top to bottom, but the orientation of individual characters is unchanged. For example: | V | | e | | r | | t | | i | | c | | a | | l |",
    )

    @model_validator(mode="after")
    def _at_most_one(self) -> TextRotation:
        provided = [n for n in ('angle', 'vertical') if getattr(self, n) is not None]
        if len(provided) > 1:
            raise ValueError(
                f"At most one of 'angle', 'vertical' may be set, found: {provided}"
            )
        return self


class ThemeColorPair(BaseModel):
    """
    A pair mapping a spreadsheet theme color type to the concrete color it represents.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets#ThemeColorPair
    """
    color: Optional[ColorStyle] = Field(
        default=None, description="The concrete color corresponding to the theme color type.",
    )

    color_type: Optional[ThemeColorType] = Field(
        default=None, description="The type of the spreadsheet theme color.",
    )


class TimeOfDay(BaseModel):
    """
    Represents a time of day. The date and time zone are either not significant or are specified elsewhere. An API may choose to allow leap seconds. Related types are google.type.Date and `google.protobuf.Timestamp`.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets#TimeOfDay
    """
    minutes: Optional[int] = Field(
        default=None, description="Minutes of an hour. Must be greater than or equal to 0 and less than or equal to 59.",
    )

    seconds: Optional[int] = Field(
        default=None, description="Seconds of a minute. Must be greater than or equal to 0 and typically must be less than or equal to 59. An API may allow the value 60 if it allows leap-seconds.",
    )

    nanos: Optional[int] = Field(
        default=None, description="Fractions of seconds, in nanoseconds. Must be greater than or equal to 0 and less than or equal to 999,999,999.",
    )

    hours: Optional[int] = Field(
        default=None, description="Hours of a day in 24 hour format. Must be greater than or equal to 0 and typically must be less than or equal to 23. An API may choose to allow the value \"24:00:00\" for scenarios like business closing time.",
    )


class TreemapChartColorScale(BaseModel):
    """
    A color scale for a treemap chart.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/charts#TreemapChartColorScale
    """
    min_value_color_style: Optional[ColorStyle] = Field(
        default=None, description="The background color for cells with a color value less than or equal to minValue. Defaults to #dc3912 if not specified. If min_value_color is also set, this field takes precedence.",
    )

    max_value_color: Annotated[
        Optional[Color],
        Mode("disabled"), Field(default=None, description="The background color for cells with a color value greater than or equal to maxValue. Defaults to #109618 if not specified. Deprecated: Use max_value_color_style."),
    ] = None

    min_value_color: Annotated[
        Optional[Color],
        Mode("disabled"), Field(default=None, description="The background color for cells with a color value less than or equal to minValue. Defaults to #dc3912 if not specified. Deprecated: Use min_value_color_style."),
    ] = None

    mid_value_color: Annotated[
        Optional[Color],
        Mode("disabled"), Field(default=None, description="The background color for cells with a color value at the midpoint between minValue and maxValue. Defaults to #efe6dc if not specified. Deprecated: Use mid_value_color_style."),
    ] = None

    max_value_color_style: Optional[ColorStyle] = Field(
        default=None, description="The background color for cells with a color value greater than or equal to maxValue. Defaults to #109618 if not specified. If max_value_color is also set, this field takes precedence.",
    )

    no_data_color: Annotated[
        Optional[Color],
        Mode("disabled"), Field(default=None, description="The background color for cells that have no color data associated with them. Defaults to #000000 if not specified. Deprecated: Use no_data_color_style."),
    ] = None

    mid_value_color_style: Optional[ColorStyle] = Field(
        default=None, description="The background color for cells with a color value at the midpoint between minValue and maxValue. Defaults to #efe6dc if not specified. If mid_value_color is also set, this field takes precedence.",
    )

    no_data_color_style: Optional[ColorStyle] = Field(
        default=None, description="The background color for cells that have no color data associated with them. Defaults to #000000 if not specified. If no_data_color is also set, this field takes precedence.",
    )


class TreemapChartSpec(BaseModel):
    """
    A Treemap chart.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/charts#TreemapChartSpec
    """
    size_data: Optional[ChartData] = Field(
        default=None, description="The data that determines the size of each treemap data cell. This data is expected to be numeric. The cells corresponding to non-numeric or missing data will not be rendered. If color_data is not specified, this data is used to determine data cell background colors as well.",
    )

    parent_labels: Optional[ChartData] = Field(
        default=None, description="The data the contains the treemap cells' parent labels.",
    )

    min_value: Optional[float] = Field(
        default=None, description="The minimum possible data value. Cells with values less than this will have the same color as cells with this value. If not specified, defaults to the actual minimum value from color_data, or the minimum value from size_data if color_data is not specified.",
    )

    color_data: Optional[ChartData] = Field(
        default=None, description="The data that determines the background color of each treemap data cell. This field is optional. If not specified, size_data is used to determine background colors. If specified, the data is expected to be numeric. color_scale will determine how the values in this data map to data cell background colors.",
    )

    hide_tooltips: Optional[bool] = Field(
        default=None, description="True to hide tooltips.",
    )

    text_format: Optional[TextFormat] = Field(
        default=None, description="The text format for all labels on the chart. The link field is not supported.",
    )

    header_color_style: Optional[ColorStyle] = Field(
        default=None, description="The background color for header cells. If header_color is also set, this field takes precedence.",
    )

    color_scale: Optional[TreemapChartColorScale] = Field(
        default=None, description="The color scale for data cells in the treemap chart. Data cells are assigned colors based on their color values. These color values come from color_data, or from size_data if color_data is not specified. Cells with color values less than or equal to min_value will have minValueColor as their background color. Cells with color values greater than or equal to max_value will have maxValueColor as their background color. Cells with color values between min_value and max_value will have background colors on a gradient between minValueColor and maxValueColor, the midpoint of the gradient being midValueColor. Cells with missing or non-numeric color values will have noDataColor as their background color.",
    )

    header_color: Annotated[
        Optional[Color],
        Mode("disabled"), Field(default=None, description="The background color for header cells. Deprecated: Use header_color_style."),
    ] = None

    levels: Optional[int] = Field(
        default=None, description="The number of data levels to show on the treemap chart. These levels are interactive and are shown with their labels. Defaults to 2 if not specified.",
    )

    max_value: Optional[float] = Field(
        default=None, description="The maximum possible data value. Cells with values greater than this will have the same color as cells with this value. If not specified, defaults to the actual maximum value from color_data, or the maximum value from size_data if color_data is not specified.",
    )

    labels: Optional[ChartData] = Field(
        default=None, description="The data that contains the treemap cell labels.",
    )

    hinted_levels: Optional[int] = Field(
        default=None, description="The number of additional data levels beyond the labeled levels to be shown on the treemap chart. These levels are not interactive and are shown without their labels. Defaults to 0 if not specified.",
    )


class WaterfallChartColumnStyle(BaseModel):
    """
    Styles for a waterfall chart column.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/charts#WaterfallChartColumnStyle
    """
    label: Optional[str] = Field(
        default=None, description="The label of the column's legend.",
    )

    color: Annotated[
        Optional[Color],
        Mode("disabled"), Field(default=None, description="The color of the column. Deprecated: Use color_style."),
    ] = None

    color_style: Optional[ColorStyle] = Field(
        default=None, description="The color of the column. If color is also set, this field takes precedence.",
    )


class WaterfallChartCustomSubtotal(BaseModel):
    """
    A custom subtotal column for a waterfall chart series.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/charts#WaterfallChartCustomSubtotal
    """
    subtotal_index: Optional[int] = Field(
        default=None, description="The zero-based index of a data point within the series. If data_is_subtotal is true, the data point at this index is the subtotal. Otherwise, the subtotal appears after the data point with this index. A series can have multiple subtotals at arbitrary indices, but subtotals do not affect the indices of the data points. For example, if a series has three data points, their indices will always be 0, 1, and 2, regardless of how many subtotals exist on the series or what data points they are associated with.",
    )

    label: Optional[str] = Field(
        default=None, description="A label for the subtotal column.",
    )

    data_is_subtotal: Optional[bool] = Field(
        default=None, description="True if the data point at subtotal_index is the subtotal. If false, the subtotal will be computed and appear after the data point.",
    )


class WaterfallChartDomain(BaseModel):
    """
    The domain of a waterfall chart.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/charts#WaterfallChartDomain
    """
    reversed: Optional[bool] = Field(
        default=None, description="True to reverse the order of the domain values (horizontal axis).",
    )

    data: Optional[ChartData] = Field(
        default=None, description="The data of the WaterfallChartDomain.",
    )


class WaterfallChartSeries(BaseModel):
    """
    A single series of data for a waterfall chart.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/charts#WaterfallChartSeries
    """
    negative_columns_style: Optional[WaterfallChartColumnStyle] = Field(
        default=None, description="Styles for all columns in this series with negative values.",
    )

    subtotal_columns_style: Optional[WaterfallChartColumnStyle] = Field(
        default=None, description="Styles for all subtotal columns in this series.",
    )

    hide_trailing_subtotal: Optional[bool] = Field(
        default=None, description="True to hide the subtotal column from the end of the series. By default, a subtotal column will appear at the end of each series. Setting this field to true will hide that subtotal column for this series.",
    )

    data_label: Optional[DataLabel] = Field(
        default=None, description="Information about the data labels for this series.",
    )

    data: Optional[ChartData] = Field(
        default=None, description="The data being visualized in this series.",
    )

    custom_subtotals: Optional[List[WaterfallChartCustomSubtotal]] = Field(
        default=None, description="Custom subtotal columns appearing in this series. The order in which subtotals are defined is not significant. Only one subtotal may be defined for each data point.",
    )

    positive_columns_style: Optional[WaterfallChartColumnStyle] = Field(
        default=None, description="Styles for all columns in this series with positive values.",
    )


class WaterfallChartSpec(BaseModel):
    """
    A waterfall chart.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/charts#WaterfallChartSpec
    """
    connector_line_style: Optional[LineStyle] = Field(
        default=None, description="The line style for the connector lines.",
    )

    total_data_label: Optional[DataLabel] = Field(
        default=None, description="Controls whether to display additional data labels on stacked charts which sum the total value of all stacked values at each value along the domain axis. stacked_type must be STACKED and neither CUSTOM nor placement can be set on the total_data_label.",
    )

    series: Optional[List[WaterfallChartSeries]] = Field(
        default=None, description="The data this waterfall chart is visualizing.",
    )

    stacked_type: Optional[WaterfallChartSpecStackedType] = Field(
        default=None, description="The stacked type.",
    )

    domain: Optional[WaterfallChartDomain] = Field(
        default=None, description="The domain data (horizontal axis) for the waterfall chart.",
    )

    first_value_is_total: Optional[bool] = Field(
        default=None, description="True to interpret the first value as a total.",
    )

    hide_connector_lines: Optional[bool] = Field(
        default=None, description="True to hide connector lines between columns.",
    )



class PostAuthor(BaseModel):
    """
    Represents a user who authored a comment post.

    Developer Preview: available as part of the Google Workspace Developer
    Preview Program.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets#PostAuthor
    """

    display_name: Optional[str] = Field(
        default=None,
        description="The display name of the user. May be absent if the author is anonymous.",
    )
    me: Optional[bool] = Field(
        default=None,
        description="Whether the user is the authenticated user making the request.",
    )
    anonymous: Optional[bool] = Field(
        default=None,
        description="Whether the user is anonymous.",
    )
    user: Optional[str] = Field(
        default=None,
        description=(
            "The resource name of the post author user, which can also be used to "
            "identify the user in the Google People API. Format: `users/{user}`. "
            "Will not be populated if the anonymous field is true or if the post is "
            "from an imported spreadsheet."
        ),
    )


class Post(BaseModel):
    """
    A post on a comment thread: the head post or a reply.

    Developer Preview: available as part of the Google Workspace Developer
    Preview Program.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets#Post
    """

    post_id: Annotated[
        Optional[str],
        Mode("response_only"),
        Field(default=None, description="Output only. The unique ID of the post."),
    ] = None
    content: Optional[str] = Field(
        default=None,
        max_length=2048,
        description=(
            "The content of the post. Required to be non-empty if commentAction is "
            "not RESOLVE or REOPEN. This text content will be handled similarly to "
            "comments created in the Sheets editor. It will have similar behaviors "
            "for formatting, notifications, etc. May not exceed 2048 UTF-8 code "
            "units."
        ),
    )
    content_html: Annotated[
        Optional[str],
        Mode("response_only"),
        Field(default=None, description="Output only. The content of the post as HTML."),
    ] = None
    author: Annotated[
        Optional[PostAuthor],
        Mode("response_only"),
        Field(default=None, description="Output only. The user who created the post."),
    ] = None
    create_time: Annotated[
        Optional[str],
        Mode("response_only"),
        Field(default=None, description="Output only. The time the post was created."),
    ] = None
    update_time: Annotated[
        Optional[str],
        Mode("response_only"),
        Field(default=None, description="Output only. The time the post was last updated."),
    ] = None
    deleted: Annotated[
        Optional[bool],
        Mode("response_only"),
        Field(
            default=None,
            description=(
                "Output only. Whether the post is deleted. If `true`, the content "
                "and author fields will be empty."
            ),
        ),
    ] = None
    from_imported_spreadsheet: Annotated[
        Optional[bool],
        Mode("response_only"),
        Field(
            default=None,
            description=(
                "Output only. Whether the post is from an imported spreadsheet. "
                "This field cannot be set directly by callers."
            ),
        ),
    ] = None
    from_copied_spreadsheet: Annotated[
        Optional[bool],
        Mode("response_only"),
        Field(
            default=None,
            description=(
                "Output only. Whether the post is from a copied spreadsheet. This "
                "field cannot be set directly by callers."
            ),
        ),
    ] = None
    assignee_email: Optional[str] = Field(
        default=None,
        max_length=2048,
        description=(
            "Optional. The email of the user who is being newly assigned to the "
            "thread as part of this post. Returns a 400 bad request error if: the "
            "parent thread is a CommentThread whose headPost does not have an "
            "assignee; commentAction is specified as RESOLVE or REOPEN; or "
            "assigneeEmail exceeds 2048 UTF-8 code units."
        ),
    )
    comment_action: Optional[CommentActionType] = Field(
        default=None,
        description="Action taken as part of creating the post.",
    )


class CommentAnchor(BaseModel):
    """
    A location in the spreadsheet that is tied to a CommentThread with the same
    anchorId. Note: Multiple anchors may refer to the same location.

    Developer Preview: available as part of the Google Workspace Developer
    Preview Program.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/sheets#CommentAnchor
    """

    anchor_id: Annotated[
        Optional[str],
        Mode("response_only"),
        Field(default=None, description="The unique ID of the comment anchor. Output only."),
    ] = None
    range: Optional[GridRange] = Field(
        default=None,
        description=(
            "The coordinate range inside the sheet where this comment is anchored."
        ),
    )


class CommentThread(BaseModel):
    """
    Represents a single comment thread inside a spreadsheet.

    Developer Preview: available as part of the Google Workspace Developer
    Preview Program.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets#CommentThread
    """

    comment_id: Optional[str] = Field(
        default=None,
        description="The unique ID of the comment thread.",
    )
    anchor_id: Optional[str] = Field(
        default=None,
        description="The ID of the comment anchor.",
    )
    head_post: Optional[Post] = Field(
        default=None,
        description="The first post in the comment thread.",
    )
    replies: Optional[List[Post]] = Field(
        default=None,
        description="The reply posts in the comment thread.",
    )
    status: Optional[CommentThreadStatus] = Field(
        default=None,
        description="The status of the comment thread.",
    )
    plain_text_quote: Optional[str] = Field(
        default=None,
        description="The quoted spreadsheet content the comment is anchored to, as plain text.",
    )


class DataSourceObjectReference(BaseModel):
    """
    Reference to a data source object.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/response#DataSourceObjectReference
    """

    chart_id: Optional[int] = Field(
        default=None, description="References to a data source chart.",
    )
    data_source_table_anchor_cell: Optional[GridCoordinate] = Field(
        default=None, description="References to a DataSourceTable anchored at the cell.",
    )
    data_source_formula_cell: Optional[GridCoordinate] = Field(
        default=None, description="References to a cell containing DataSourceFormula.",
    )
    sheet_id: Optional[str] = Field(
        default=None, description="References to a DATA_SOURCE sheet.",
    )
    data_source_pivot_table_anchor_cell: Optional[GridCoordinate] = Field(
        default=None, description="References to a data source PivotTable anchored at the cell.",
    )

    @model_validator(mode="after")
    def _exactly_one(self) -> DataSourceObjectReference:
        provided = [
            n
            for n in (
                "sheet_id",
                "chart_id",
                "data_source_table_anchor_cell",
                "data_source_pivot_table_anchor_cell",
                "data_source_formula_cell",
            )
            if getattr(self, n) is not None
        ]
        if len(provided) != 1:
            raise ValueError(
                f"Exactly one of sheet_id, chart_id, data_source_table_anchor_cell, "
                f"data_source_pivot_table_anchor_cell, data_source_formula_cell must "
                f"be set, found: {provided}"
            )
        return self


class DataSourceObjectReferences(BaseModel):
    """
    A list of references to data source objects.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#DataSourceObjectReferences
    """

    references: Optional[List[DataSourceObjectReference]] = Field(
        default=None, description="The references.",
    )


def _rebuild_forward_refs() -> None:
    for obj in list(globals().values()):
        if (
            isinstance(obj, type)
            and issubclass(obj, BaseModel)
            and obj is not BaseModel
            and obj.__module__ == __name__
        ):
            obj.model_rebuild()


_rebuild_forward_refs()
