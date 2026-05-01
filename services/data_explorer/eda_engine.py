from io import StringIO
import os

import numpy as np
import pandas as pd

from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    silhouette_score,
)
from sklearn.model_selection import train_test_split
from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor, NearestNeighbors
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.datasets import load_iris


# =============================================================================
# CONFIGURATION
# =============================================================================

MAX_ROWS = 5000
MAX_COLUMNS = 100
MAX_CHARTS = 60
MAX_CHART_ROWS = 1000
MAX_SEGMENTATION_ROWS = 1000
RANDOM_STATE = 42

KNN_CLASSIFICATION_CANDIDATES = [1, 3, 5, 7, 9, 11, 15, 21]
KNN_REGRESSION_CANDIDATES = [3, 5, 7, 9, 11, 15, 21]


# =============================================================================
# DATA LOADING / SAMPLE DATA
# =============================================================================

def parse_csv_dataset(raw_data, max_rows=MAX_ROWS, max_columns=MAX_COLUMNS):
    """
    Parse pasted CSV text into a pandas DataFrame.

    This intentionally raises ValueError for user-facing validation errors
    so the Flask route can return a clean JSON error response.
    """
    if not raw_data or not raw_data.strip():
        raise ValueError("No dataset provided.")

    try:
        df = pd.read_csv(StringIO(raw_data))
    except Exception as exc:
        raise ValueError(f"Could not parse dataset as CSV: {str(exc)}")

    if df.empty:
        raise ValueError("The dataset appears to be empty.")

    if df.shape[1] > max_columns:
        raise ValueError(
            f"Dataset has too many columns. Maximum supported for now is {max_columns}."
        )

    if df.shape[0] > max_rows:
        df = df.head(max_rows)

    return df


def get_sample_dataset_csv(dataset_name):
    """
    Return a sample dataset as CSV text for frontend testing.
    """
    dataset_name = dataset_name.lower().strip()

    if dataset_name == "iris":
        iris = load_iris(as_frame=True)
        df = iris.frame.copy()

        df["species"] = df["target"].map(
            {index: name for index, name in enumerate(iris.target_names)}
        )
        df = df.drop(columns=["target"])

        return df.to_csv(index=False)

    if dataset_name == "titanic":
        path = os.path.join("static", "data", "titanic.csv")

        if not os.path.exists(path):
            raise ValueError("Titanic dataset file not found at static/data/titanic.csv.")

        df = pd.read_csv(path)
        return df.to_csv(index=False)

    raise ValueError(f"Unknown sample dataset: {dataset_name}")


# =============================================================================
# MAIN EDA ORCHESTRATION
# =============================================================================

def build_eda_report(df):
    """
    Build the full exploratory data analysis report returned to the frontend.

    The original dataframe is used for quality reporting. Then we create an
    analysis dataframe with safe derived features such as has_cabin.
    """
    original_df = df.copy()

    # Quality report should describe the original uploaded/pasted data.
    quality = build_quality_report(original_df)

    # Analysis dataframe may include safe derived features, without overwriting
    # the user's original data.
    analysis_df, derived_features = add_derived_features(original_df, quality)

    # Re-infer schema after derived columns are added.
    schema = infer_schema(analysis_df)

    # Build expensive advanced analysis once, then reuse it for charts.
    segmentation = build_segmentation_report(analysis_df, schema)

    summary = build_dataset_summary(analysis_df, schema)
    columns = build_column_report(analysis_df, schema)
    charts = recommend_charts(analysis_df, schema, segmentation=segmentation)
    relationships = analyse_relationships(analysis_df, schema)
    neighbours = analyse_nearest_neighbours(analysis_df, schema)
    advanced = build_advanced_report(analysis_df, schema)
    ml = build_ml_report(analysis_df, schema)
    theses = generate_theses(analysis_df, schema, quality, relationships)

    return {
        "summary": summary,
        "schema": schema,
        "quality": quality,
        "columns": columns,
        "charts": charts,
        "relationships": relationships,
        "nearest_neighbours": neighbours,
        "advanced": advanced,
        "segmentation": segmentation,
        "ml": ml,
        "derived_features": derived_features,
        "theses": theses,
    }


# =============================================================================
# SCHEMA INFERENCE / DATA QUALITY / DERIVED FEATURES
# =============================================================================

def infer_schema(df):
    """
    Infer broad column types from the actual data held in each column.

    Important principles:
    - Missing values should not stop a column being numeric/date if the
      non-missing values fit.
    - Date columns should be detected before generic ID detection.
    - Obvious ID columns should be excluded before numeric modelling.
    - Low-cardinality numeric columns can still be used later as categorical-like
      fields.
    """
    schema = {
        "numeric": [],
        "categorical": [],
        "datetime": [],
        "boolean": [],
        "text": [],
        "likely_id": [],
        "high_cardinality": [],
    }

    row_count = len(df)

    for column in df.columns:
        series = df[column]
        non_null = series.dropna()
        unique_count = non_null.nunique()
        unique_ratio = unique_count / max(row_count, 1)
        column_lower = str(column).lower()

        if non_null.empty:
            schema["text"].append(column)
            continue

        id_name_hints = ["id", "uuid", "guid", "reference", "ref", "key"]
        looks_like_id_name = any(hint in column_lower for hint in id_name_hints)

        date_name_hints = [
            "date", "time", "created", "updated", "submitted", "month", "year", "timestamp",
        ]
        looks_like_date_name = any(hint in column_lower for hint in date_name_hints)

        if pd.api.types.is_bool_dtype(series):
            schema["boolean"].append(column)
            continue

        normalised_values = {str(value).strip().lower() for value in non_null.unique()}
        boolean_like_values = {"true", "false", "yes", "no", "y", "n", "0", "1"}

        if 2 <= len(normalised_values) <= 3 and normalised_values.issubset(boolean_like_values):
            schema["boolean"].append(column)
            continue

        datetime_series = pd.to_datetime(non_null, errors="coerce")
        datetime_ratio_non_null = datetime_series.notna().mean()

        if looks_like_date_name and datetime_ratio_non_null > 0.75:
            schema["datetime"].append(column)
            continue

        if datetime_ratio_non_null > 0.9 and not pd.api.types.is_numeric_dtype(series):
            schema["datetime"].append(column)
            continue

        if looks_like_id_name and unique_ratio > 0.8:
            schema["likely_id"].append(column)
            continue

        numeric_series = pd.to_numeric(non_null, errors="coerce")
        numeric_ratio_non_null = numeric_series.notna().mean()

        if numeric_ratio_non_null > 0.85:
            schema["numeric"].append(column)
            continue

        if unique_ratio > 0.95 and row_count >= 20:
            average_length = non_null.astype(str).str.len().mean()

            if average_length >= 12 and looks_like_id_name:
                schema["likely_id"].append(column)
                continue

            if average_length >= 20:
                schema["high_cardinality"].append(column)
                schema["text"].append(column)
                continue

        missing_ratio = series.isna().mean()

        if missing_ratio > 0.5 and unique_count > 10:
            schema["high_cardinality"].append(column)
            schema["text"].append(column)
            continue

        if unique_count <= min(30, max(10, row_count * 0.2)):
            schema["categorical"].append(column)
            continue

        if unique_ratio > 0.5:
            schema["high_cardinality"].append(column)
            schema["text"].append(column)
            continue

        schema["categorical"].append(column)

    return schema


def build_quality_report(df):
    total_cells = df.shape[0] * df.shape[1]
    total_missing_cells = int(df.isna().sum().sum())

    missing_by_column = []

    for column in df.columns:
        missing_count = int(df[column].isna().sum())
        missing_by_column.append({
            "column": column,
            "missing": missing_count,
            "missing_percent": round((missing_count / max(len(df), 1)) * 100, 2),
        })

    return {
        "duplicate_rows": int(df.duplicated().sum()),
        "total_missing_cells": total_missing_cells,
        "missing_percent_total": round((total_missing_cells / max(total_cells, 1)) * 100, 2),
        "missing_by_column": missing_by_column,
    }


def add_derived_features(df, quality, missing_threshold=30):
    """
    Add safe derived features for analysis.
    """
    analysis_df = df.copy()
    derived_features = []

    for item in quality.get("missing_by_column", []):
        column = item["column"]
        missing_percent = item["missing_percent"]

        if column not in analysis_df.columns or missing_percent < missing_threshold:
            continue

        derived_name = make_derived_feature_name(f"has_{column}", analysis_df.columns)
        analysis_df[derived_name] = analysis_df[column].notna()

        derived_features.append({
            "name": derived_name,
            "source_column": column,
            "type": "missingness_indicator",
            "missing_percent": missing_percent,
            "reason": (
                f"{column} is missing in {missing_percent}% of rows. "
                "Missingness may be analytically meaningful, so a boolean presence indicator was created."
            ),
        })

    return analysis_df, derived_features


def make_derived_feature_name(base_name, existing_columns):
    safe_name = safe_chart_id(base_name)
    candidate = safe_name
    counter = 2
    existing = {str(column) for column in existing_columns}

    while candidate in existing:
        candidate = f"{safe_name}_{counter}"
        counter += 1

    return candidate


def build_dataset_summary(df, schema):
    return {
        "rows": int(df.shape[0]),
        "columns": int(df.shape[1]),
        "numeric_columns": len(schema["numeric"]),
        "categorical_columns": len(schema["categorical"]),
        "datetime_columns": len(schema["datetime"]),
        "text_columns": len(schema["text"]),
        "duplicate_rows": int(df.duplicated().sum()),
        "total_missing_cells": int(df.isna().sum().sum()),
    }


def build_column_report(df, schema):
    report = []

    for column in df.columns:
        series = df[column]
        item = {
            "name": column,
            "missing": int(series.isna().sum()),
            "unique": int(series.nunique(dropna=True)),
            "inferred_type": get_column_type(column, schema),
        }

        if column in schema["numeric"]:
            numeric = pd.to_numeric(series, errors="coerce")
            item.update({
                "mean": safe_round(numeric.mean()),
                "median": safe_round(numeric.median()),
                "min": safe_round(numeric.min()),
                "max": safe_round(numeric.max()),
                "std": safe_round(numeric.std()),
            })

        if column in schema["categorical"] or column in schema["boolean"]:
            top_values = series.value_counts(dropna=True).head(10)
            item["top_values"] = [
                {"value": str(index), "count": int(value)}
                for index, value in top_values.items()
            ]

        report.append(item)

    return report


def get_column_type(column, schema):
    for type_name, columns in schema.items():
        if column in columns:
            return type_name
    return "unknown"


def get_categorical_like_columns(df, schema, max_unique=12):
    columns = list(schema.get("categorical", [])) + list(schema.get("boolean", []))

    for column in schema.get("numeric", []):
        unique_count = df[column].dropna().nunique()
        if 2 <= unique_count <= max_unique and column not in columns:
            columns.append(column)

    return columns


# =============================================================================
# CHART RECOMMENDATION / CHART DATA BUILDERS
# =============================================================================

def recommend_charts(df, schema, segmentation=None):
    charts = []
    numeric_cols = schema["numeric"]
    categorical_cols = schema["categorical"] + schema["boolean"]
    datetime_cols = schema["datetime"]

    charts.extend(build_numeric_charts(df, numeric_cols))
    charts.extend(build_categorical_charts(df, categorical_cols))
    charts.extend(build_correlation_charts(df, numeric_cols))
    charts.extend(build_categorical_numeric_charts(df, categorical_cols, numeric_cols))
    charts.extend(build_time_series_charts(df, datetime_cols, numeric_cols))
    charts.extend(build_scatter_charts(df, numeric_cols))
    charts.extend(build_3d_scatter_charts(df, numeric_cols, categorical_cols))
    charts.extend(build_bubble_charts(df, numeric_cols))
    charts.extend(build_radar_charts(df, categorical_cols, numeric_cols))
    charts.extend(build_category_distribution_charts(df, categorical_cols, numeric_cols))
    charts.extend(build_stacked_bar_charts(df, categorical_cols))
    charts.extend(build_area_charts(df, datetime_cols, numeric_cols))
    charts.extend(build_target_charts(df, schema))
    charts.extend(build_segmentation_charts(df, schema, segmentation=segmentation))

    return charts[:MAX_CHARTS]


def build_numeric_charts(df, numeric_cols):
    charts = []
    for column in numeric_cols:
        numeric = pd.to_numeric(df[column], errors="coerce").dropna()
        charts.append({"id": safe_chart_id(f"histogram_{column}"), "title": f"Distribution of {column}", "chart_type": "histogram", "data_role": "numeric", "phase": "univariate", "columns": [column], "values": numeric.head(500).tolist(), "why": "Shows the distribution, spread and possible skew of a numeric field."})
        charts.append({"id": safe_chart_id(f"boxplot_{column}"), "title": f"Outlier check for {column}", "chart_type": "boxplot", "data_role": "numeric", "phase": "univariate", "columns": [column], "values": numeric.head(500).tolist(), "why": "Highlights median, quartiles and possible outliers."})
    return charts


def build_categorical_charts(df, categorical_cols):
    charts = []
    for column in categorical_cols[:10]:
        counts = df[column].value_counts(dropna=True).head(15)
        charts.append({"id": safe_chart_id(f"bar_{column}"), "title": f"Category counts for {column}", "chart_type": "bar", "data_role": "categorical", "phase": "univariate", "columns": [column], "labels": [str(index) for index in counts.index], "values": [int(value) for value in counts.values], "why": "Shows the most common groups or categories."})
    return charts


def build_radar_charts(df, categorical_cols, numeric_cols):
    """
    Build radar charts comparing average numeric profiles across categories.

    Values are normalised 0-1 so variables with different scales can be compared
    on the same radar chart.
    """
    charts = []

    if not categorical_cols or len(numeric_cols) < 3:
        return charts

    for category_col in categorical_cols[:5]:
        unique_count = df[category_col].dropna().nunique()

        # Radar charts become unreadable with too many groups.
        if unique_count < 2 or unique_count > 6:
            continue

        selected_numeric_cols = numeric_cols[:6]
        selected_columns = [category_col] + selected_numeric_cols

        temp = df[selected_columns].copy()

        for column in selected_numeric_cols:
            temp[column] = pd.to_numeric(temp[column], errors="coerce")

        temp = temp.dropna(subset=[category_col])

        if temp.empty:
            continue

        grouped = (
            temp
            .groupby(category_col)[selected_numeric_cols]
            .mean()
            .dropna(how="all")
        )

        if grouped.empty or len(grouped) < 2:
            continue

        # Keep the largest category groups to avoid a messy radar chart.
        largest_groups = (
            temp[category_col]
            .value_counts(dropna=True)
            .head(6)
            .index
        )

        grouped = grouped.loc[grouped.index.intersection(largest_groups)]

        if grouped.empty or len(grouped) < 2:
            continue

        normalised = normalise_grouped_values(grouped)

        charts.append(
            {
                "id": safe_chart_id(f"radar_profile_by_{category_col}"),
                "title": f"Numeric profile by {category_col}",
                "chart_type": "radar",
                "data_role": "categoric_numeric_profile",
                "phase": "multivariate",
                "columns": selected_columns,
                "category": category_col,
                "variables": selected_numeric_cols,
                "series": [
                    {
                        "name": str(index),
                        "values": [safe_round(value) for value in normalised.loc[index].tolist()],
                        "raw_values": [
                            safe_round(value)
                            for value in grouped.loc[index].tolist()
                        ],
                    }
                    for index in normalised.index
                ],
                "why": (
                    "Compares the average numeric profile of each category. "
                    "Values are normalised so fields with different scales can be shown together."
                ),
            }
        )

        # Start with one radar chart. Later we can return more.
        return charts

    return charts


def build_correlation_charts(df, numeric_cols):
    if len(numeric_cols) < 2:
        return []
    corr_df = df[numeric_cols].apply(pd.to_numeric, errors="coerce").corr()
    return [{"id": "correlation_matrix", "title": "Correlation matrix", "chart_type": "correlation_heatmap", "data_role": "relational", "phase": "bivariate", "columns": numeric_cols, "matrix": corr_df.round(3).replace({np.nan: None}).to_dict(), "why": "Shows which numeric fields move together or against each other."}]


def build_categorical_numeric_charts(df, categorical_cols, numeric_cols):
    charts = []
    for cat in categorical_cols[:5]:
        for num in numeric_cols[:5]:
            temp = df[[cat, num]].copy()
            temp[num] = pd.to_numeric(temp[num], errors="coerce")
            temp = temp.dropna()
            if temp.empty:
                continue
            grouped = temp.groupby(cat)[num].mean().sort_values(ascending=False).head(15)
            charts.append({"id": safe_chart_id(f"mean_{num}_by_{cat}"), "title": f"Average {num} by {cat}", "chart_type": "grouped_bar", "data_role": "categoric_numeric", "phase": "bivariate", "columns": [cat, num], "labels": [str(index) for index in grouped.index], "values": [safe_round(value) for value in grouped.values], "why": "Compares a numeric measure across categories."})
    return charts


def build_time_series_charts(df, datetime_cols, numeric_cols):
    charts = []
    for date_col in datetime_cols[:3]:
        date_series = pd.to_datetime(df[date_col], errors="coerce")
        for num in numeric_cols[:5]:
            temp = pd.DataFrame({date_col: date_series, num: pd.to_numeric(df[num], errors="coerce")}).dropna()
            if temp.empty:
                continue
            monthly = temp.set_index(date_col).resample("ME")[num].mean().dropna().head(36)
            charts.append({"id": safe_chart_id(f"time_{num}_by_{date_col}"), "title": f"{num} over time by {date_col}", "chart_type": "line", "data_role": "time_series", "phase": "time_series", "columns": [date_col, num], "labels": [str(index.date()) for index in monthly.index], "values": [safe_round(value) for value in monthly.values], "why": "Shows movement, trend or seasonality over time."})
    return charts


def build_scatter_charts(df, numeric_cols):
    charts = []
    if len(numeric_cols) < 2:
        return charts
    max_pairs = 8
    pair_count = 0
    for i, x_col in enumerate(numeric_cols):
        for y_col in numeric_cols[i + 1:]:
            if pair_count >= max_pairs:
                return charts
            temp = df[[x_col, y_col]].copy()
            temp[x_col] = pd.to_numeric(temp[x_col], errors="coerce")
            temp[y_col] = pd.to_numeric(temp[y_col], errors="coerce")
            temp = temp.dropna().head(500)
            if temp.empty:
                continue
            charts.append({"id": safe_chart_id(f"scatter_{x_col}_vs_{y_col}"), "title": f"{y_col} vs {x_col}", "chart_type": "scatter", "data_role": "numeric_numeric", "phase": "bivariate", "columns": [x_col, y_col], "x": temp[x_col].tolist(), "y": temp[y_col].tolist(), "x_label": x_col, "y_label": y_col, "why": "Shows the relationship, clustering and possible outliers between two numeric fields."})
            pair_count += 1
    return charts


def build_3d_scatter_charts(df, numeric_cols, categorical_cols):
    """
    Build 3D scatter plots when at least three numeric columns exist.

    If a categorical column is available with a manageable number of groups,
    use it as the colour dimension.
    """
    charts = []

    if len(numeric_cols) < 3:
        return charts

    x_col = numeric_cols[0]
    y_col = numeric_cols[1]
    z_col = numeric_cols[2]

    selected_columns = [x_col, y_col, z_col]

    colour_col = None

    for column in categorical_cols:
        unique_count = df[column].dropna().nunique()

        if 2 <= unique_count <= 12:
            colour_col = column
            selected_columns.append(column)
            break

    temp = df[selected_columns].copy()

    temp[x_col] = pd.to_numeric(temp[x_col], errors="coerce")
    temp[y_col] = pd.to_numeric(temp[y_col], errors="coerce")
    temp[z_col] = pd.to_numeric(temp[z_col], errors="coerce")

    temp = temp.dropna(subset=[x_col, y_col, z_col]).head(1000)

    if temp.empty:
        return charts

    chart = {
        "id": safe_chart_id(f"scatter_3d_{x_col}_{y_col}_{z_col}"),
        "title": f"3D view: {x_col}, {y_col} and {z_col}",
        "chart_type": "scatter_3d",
        "data_role": "numeric_numeric_numeric",
        "phase": "multivariate",
        "columns": [x_col, y_col, z_col],
        "x": temp[x_col].tolist(),
        "y": temp[y_col].tolist(),
        "z": temp[z_col].tolist(),
        "x_label": x_col,
        "y_label": y_col,
        "z_label": z_col,
        "why": "Shows how rows are positioned across three numeric fields at the same time. You can rotate and zoom the chart to explore clusters and outliers.",
    }

    if colour_col:
        chart["colour_label"] = colour_col
        chart["colour"] = temp[colour_col].astype(str).tolist()
        chart["hover"] = [
            f"{colour_col}: {value}"
            for value in temp[colour_col].astype(str).tolist()
        ]
    else:
        chart["colour"] = None
        chart["hover"] = [
            f"Row {index}"
            for index in temp.index.tolist()
        ]

    charts.append(chart)

    return charts


def build_bubble_charts(df, numeric_cols):
    charts = []
    if len(numeric_cols) < 3:
        return charts
    x_col, y_col, size_col = numeric_cols[0], numeric_cols[1], numeric_cols[2]
    temp = df[[x_col, y_col, size_col]].copy()
    temp[x_col] = pd.to_numeric(temp[x_col], errors="coerce")
    temp[y_col] = pd.to_numeric(temp[y_col], errors="coerce")
    temp[size_col] = pd.to_numeric(temp[size_col], errors="coerce")
    temp = temp.dropna().head(500)
    if temp.empty:
        return charts
    size_values = temp[size_col].abs()
    if size_values.max() == size_values.min():
        marker_sizes = [16 for _ in size_values]
    else:
        marker_sizes = (8 + 32 * ((size_values - size_values.min()) / (size_values.max() - size_values.min()))).tolist()
    charts.append({"id": safe_chart_id(f"bubble_{x_col}_{y_col}_size_{size_col}"), "title": f"{y_col} vs {x_col}, sized by {size_col}", "chart_type": "bubble", "data_role": "numeric_numeric_numeric", "phase": "multivariate", "columns": [x_col, y_col, size_col], "x": temp[x_col].tolist(), "y": temp[y_col].tolist(), "size": marker_sizes, "x_label": x_col, "y_label": y_col, "size_label": size_col, "why": "Adds a third numeric measure as bubble size to show a richer multivariate relationship."})
    return charts


def build_category_distribution_charts(df, categorical_cols, numeric_cols):
    charts = []
    if not categorical_cols or not numeric_cols:
        return charts
    max_charts = 10
    chart_count = 0
    for cat_col in categorical_cols[:5]:
        category_count = df[cat_col].dropna().nunique()
        if category_count < 2 or category_count > 12:
            continue
        for num_col in numeric_cols[:5]:
            if chart_count >= max_charts:
                return charts
            temp = df[[cat_col, num_col]].copy()
            temp[num_col] = pd.to_numeric(temp[num_col], errors="coerce")
            temp = temp.dropna().head(MAX_CHART_ROWS)
            if temp.empty:
                continue
            charts.append({"id": safe_chart_id(f"boxplot_{num_col}_by_{cat_col}"), "title": f"{num_col} distribution by {cat_col}", "chart_type": "boxplot_by_category", "data_role": "categoric_numeric", "phase": "bivariate", "columns": [cat_col, num_col], "x": temp[cat_col].astype(str).tolist(), "y": temp[num_col].tolist(), "x_label": cat_col, "y_label": num_col, "why": "Compares medians, spread and outliers across categories."})
            charts.append({"id": safe_chart_id(f"violin_{num_col}_by_{cat_col}"), "title": f"{num_col} shape by {cat_col}", "chart_type": "violin_by_category", "data_role": "categoric_numeric", "phase": "bivariate", "columns": [cat_col, num_col], "x": temp[cat_col].astype(str).tolist(), "y": temp[num_col].tolist(), "x_label": cat_col, "y_label": num_col, "why": "Shows the distribution shape of a numeric field within each category."})
            chart_count += 2
    return charts


def build_stacked_bar_charts(df, categorical_cols):
    charts = []
    if len(categorical_cols) < 2:
        return charts
    max_charts = 5
    chart_count = 0
    for i, x_col in enumerate(categorical_cols):
        for stack_col in categorical_cols[i + 1:]:
            if chart_count >= max_charts:
                return charts
            x_unique = df[x_col].dropna().nunique()
            stack_unique = df[stack_col].dropna().nunique()
            if x_unique < 2 or stack_unique < 2 or x_unique > 12 or stack_unique > 8:
                continue
            counts = df[[x_col, stack_col]].dropna().astype(str).groupby([x_col, stack_col]).size().unstack(fill_value=0)
            charts.append({"id": safe_chart_id(f"stacked_bar_{x_col}_by_{stack_col}"), "title": f"{x_col} split by {stack_col}", "chart_type": "stacked_bar", "data_role": "categoric_categoric", "phase": "bivariate", "columns": [x_col, stack_col], "x_labels": [str(index) for index in counts.index], "series": [{"name": str(column), "values": [int(value) for value in counts[column].values]} for column in counts.columns], "x_label": x_col, "stack_label": stack_col, "why": "Shows the composition of one categorical field within another."})
            chart_count += 1
    return charts


def build_area_charts(df, datetime_cols, numeric_cols):
    charts = []
    if not datetime_cols or not numeric_cols:
        return charts
    for date_col in datetime_cols[:2]:
        date_series = pd.to_datetime(df[date_col], errors="coerce")
        for num_col in numeric_cols[:4]:
            temp = pd.DataFrame({date_col: date_series, num_col: pd.to_numeric(df[num_col], errors="coerce")}).dropna()
            if temp.empty:
                continue
            monthly = temp.set_index(date_col).resample("ME")[num_col].mean().dropna().head(36)
            if monthly.empty:
                continue
            charts.append({"id": safe_chart_id(f"area_{num_col}_by_{date_col}"), "title": f"{num_col} area trend over time", "chart_type": "area", "data_role": "time_series", "phase": "time_series", "columns": [date_col, num_col], "labels": [str(index.date()) for index in monthly.index], "values": [safe_round(value) for value in monthly.values], "why": "Shows the size and movement of a numeric measure over time."})
    return charts


def build_target_charts(df, schema):
    charts = []
    target_column = detect_target_column(df, schema)
    if not target_column:
        return charts
    distribution = build_target_distribution(df, target_column)
    charts.append({"id": safe_chart_id(f"target_distribution_{target_column}"), "title": f"Target distribution: {target_column}", "chart_type": "bar", "data_role": "target", "phase": "advanced", "columns": [target_column], "labels": [row["target_value"] for row in distribution], "values": [row["count"] for row in distribution], "why": "Shows how the likely target or outcome column is distributed."})
    target_numeric = pd.to_numeric(df[target_column], errors="coerce")
    target_is_numeric = target_numeric.notna().mean() > 0.85
    categorical_cols = [col for col in get_categorical_like_columns(df, schema) if col != target_column]
    if target_is_numeric:
        for column in categorical_cols[:6]:
            temp = df[[column, target_column]].copy()
            temp[target_column] = pd.to_numeric(temp[target_column], errors="coerce")
            temp = temp.dropna()
            if temp.empty:
                continue
            grouped = temp.groupby(column)[target_column].mean().sort_values(ascending=False).head(15)
            charts.append({"id": safe_chart_id(f"target_rate_{target_column}_by_{column}"), "title": f"Average {target_column} by {column}", "chart_type": "bar", "data_role": "target", "phase": "advanced", "columns": [column, target_column], "labels": [str(index) for index in grouped.index], "values": [safe_round(value) for value in grouped.values], "why": "Shows how the target or outcome varies by category."})
    return charts


def build_segmentation_charts(df, schema, segmentation=None):
    if segmentation is None:
        segmentation = build_segmentation_report(df, schema)
    if not segmentation.get("available"):
        return []
    points = segmentation["pca"]["points"]
    charts = [{"id": "pca_scatter_by_cluster", "title": "PCA projection coloured by KMeans cluster", "chart_type": "pca_scatter", "data_role": "segmentation", "phase": "advanced", "columns": segmentation["numeric_columns"], "x": [point["pc1"] for point in points], "y": [point["pc2"] for point in points], "colour": [str(point["cluster"]) for point in points], "hover": [f"Row {point['row_index']} | Cluster {point['cluster']}" for point in points], "x_label": f"PC1 ({segmentation['pca']['explained_variance_pc1']}%)", "y_label": f"PC2 ({segmentation['pca']['explained_variance_pc2']}%)", "why": "Uses PCA to reduce numeric features into two dimensions, then colours rows by KMeans cluster."}]
    has_target = any(point.get("target") is not None for point in points)
    if has_target:
        charts.append({"id": "pca_scatter_by_target", "title": "PCA projection coloured by detected target", "chart_type": "pca_scatter", "data_role": "segmentation", "phase": "advanced", "columns": segmentation["numeric_columns"], "x": [point["pc1"] for point in points], "y": [point["pc2"] for point in points], "colour": [str(point["target"]) for point in points], "hover": [f"Row {point['row_index']} | Target {point['target']}" for point in points], "x_label": f"PC1 ({segmentation['pca']['explained_variance_pc1']}%)", "y_label": f"PC2 ({segmentation['pca']['explained_variance_pc2']}%)", "why": "Uses PCA to show whether the detected target separates naturally in the numeric feature space."})
    return charts


def normalise_grouped_values(grouped):
    """
    Normalise each numeric column to 0-1 across category groups.

    This makes radar charts readable when variables have different units
    or very different scales.
    """
    normalised = grouped.copy()

    for column in normalised.columns:
        col_min = normalised[column].min()
        col_max = normalised[column].max()

        if pd.isna(col_min) or pd.isna(col_max) or col_max == col_min:
            normalised[column] = 0.5
        else:
            normalised[column] = (
                (normalised[column] - col_min) / (col_max - col_min)
            )

    return normalised

# =============================================================================
# RELATIONSHIPS / NEAREST NEIGHBOURS / THESES
# =============================================================================

def analyse_relationships(df, schema):
    numeric_cols = schema["numeric"]
    if len(numeric_cols) < 2:
        return {"strong_correlations": [], "message": "Not enough numeric columns for correlation analysis."}
    corr = df[numeric_cols].apply(pd.to_numeric, errors="coerce").corr()
    strong = []
    for i, col_a in enumerate(numeric_cols):
        for col_b in numeric_cols[i + 1:]:
            value = corr.loc[col_a, col_b]
            if pd.notna(value) and abs(value) >= 0.5:
                strong.append({"column_a": col_a, "column_b": col_b, "correlation": safe_round(value), "strength": "strong" if abs(value) >= 0.7 else "moderate", "direction": "positive" if value > 0 else "negative"})
    return {"strong_correlations": strong, "message": "Correlation is not causation, but these relationships may deserve investigation."}


def analyse_nearest_neighbours(df, schema):
    numeric_cols = schema["numeric"]
    if len(numeric_cols) < 2 or len(df) < 5:
        return {"available": False, "message": "Not enough numeric data for nearest-neighbour analysis."}
    numeric_df = df[numeric_cols].apply(pd.to_numeric, errors="coerce").dropna()
    if len(numeric_df) < 5:
        return {"available": False, "message": "Not enough complete numeric rows for nearest-neighbour analysis."}
    sample = numeric_df.head(500)
    scaler = StandardScaler()
    scaled = scaler.fit_transform(sample)
    n_neighbors = min(5, len(sample))
    model = NearestNeighbors(n_neighbors=n_neighbors)
    model.fit(scaled)
    distances, indices = model.kneighbors(scaled[:1])
    return {"available": True, "columns_used": numeric_cols, "reference_row_index": int(sample.index[0]), "nearest_rows": [{"row_index": int(sample.index[idx]), "distance": safe_round(dist)} for idx, dist in zip(indices[0], distances[0])], "message": "Nearest-neighbour analysis finds rows with similar numeric profiles. This can later power segmentation and lookalike analysis."}


def generate_theses(df, schema, quality, relationships):
    theses = []
    if quality["missing_percent_total"] > 10:
        theses.append({"title": "Data quality may be limiting confidence in the analysis", "evidence": f"{quality['missing_percent_total']}% of all cells are missing.", "input_level_improvement": "Review the data collection process and make key fields mandatory where possible.", "operational_improvement": "Avoid making major decisions from columns with high missingness until the capture process is improved."})
    for relationship in relationships.get("strong_correlations", [])[:5]:
        theses.append({"title": f"{relationship['column_a']} and {relationship['column_b']} appear related", "evidence": f"The correlation is {relationship['correlation']}, which is {relationship['strength']} and {relationship['direction']}.", "input_level_improvement": "Check whether both fields are captured consistently and whether either is derived from the other.", "operational_improvement": "Investigate whether movement in one field can help explain or predict movement in the other."})
    if schema["datetime"] and schema["numeric"]:
        theses.append({"title": "Time-based trends may explain changes in performance", "evidence": f"Detected date fields: {', '.join(schema['datetime'])}. Numeric fields can be trended over time.", "input_level_improvement": "Ensure dates are captured in a consistent format.", "operational_improvement": "Use monthly or weekly trend views to separate one-off variation from genuine change."})
    if schema["categorical"] and schema["numeric"]:
        theses.append({"title": "Performance may vary by group or segment", "evidence": f"Detected categorical fields such as {', '.join(schema['categorical'][:3])} and numeric fields such as {', '.join(schema['numeric'][:3])}.", "input_level_improvement": "Make sure category labels are standardised to avoid duplicate groups caused by spelling or formatting differences.", "operational_improvement": "Compare averages by segment to identify which groups may need targeted improvement."})
    if not theses:
        theses.append({"title": "The dataset is valid but may need richer fields for deeper insight", "evidence": "The tool did not find strong missingness, time trends or numeric relationships in the first pass.", "input_level_improvement": "Add dates, categories, outcomes and operational context fields to make future analysis more useful.", "operational_improvement": "Use this dataset as a baseline and compare it with future extracts."})
    return theses


# =============================================================================
# SEGMENTATION: PCA + KMEANS
# =============================================================================

def build_segmentation_report(df, schema):
    numeric_cols = schema.get("numeric", [])
    if len(numeric_cols) < 2:
        return {"available": False, "message": "At least two numeric columns are needed for PCA and clustering.", "numeric_columns": numeric_cols, "selected_k": None, "k_scores": [], "pca": None, "clusters": None, "cluster_profiles": []}
    numeric_df = df[numeric_cols].apply(pd.to_numeric, errors="coerce").dropna()
    if len(numeric_df) < 10:
        return {"available": False, "message": "At least ten complete numeric rows are needed for useful PCA and clustering.", "numeric_columns": numeric_cols, "selected_k": None, "k_scores": [], "pca": None, "clusters": None, "cluster_profiles": []}
    sample = numeric_df.sample(n=min(MAX_SEGMENTATION_ROWS, len(numeric_df)), random_state=RANDOM_STATE)
    scaler = StandardScaler()
    scaled = scaler.fit_transform(sample)
    k_selection = choose_best_kmeans_k(scaled)
    selected_k = k_selection["selected_k"]
    kmeans = KMeans(n_clusters=selected_k, random_state=RANDOM_STATE, n_init=10)
    cluster_labels = kmeans.fit_predict(scaled)
    pca = PCA(n_components=2)
    pca_points = pca.fit_transform(scaled)
    pca_loadings = build_pca_loadings(pca, numeric_cols)
    target_column = detect_target_column(df, schema)
    target_values = get_target_values_for_indices(df, sample.index, target_column)
    cluster_profiles = build_cluster_profiles(sample=sample, numeric_cols=numeric_cols, cluster_labels=cluster_labels)
    points = []
    for position, index in enumerate(sample.index):
        points.append({"row_index": int(index), "pc1": safe_round(pca_points[position, 0]), "pc2": safe_round(pca_points[position, 1]), "cluster": int(cluster_labels[position]), "target": target_values[position] if target_values else None})
    return {"available": True, "message": f"Built a 2D PCA projection and KMeans segmentation using {len(sample)} complete rows and {len(numeric_cols)} numeric columns. Selected K={selected_k} using silhouette score.", "numeric_columns": numeric_cols, "selected_k": selected_k, "cluster_count": selected_k, "k_scores": k_selection["k_scores"], "pca": {"explained_variance_pc1": safe_round(pca.explained_variance_ratio_[0] * 100, 2), "explained_variance_pc2": safe_round(pca.explained_variance_ratio_[1] * 100, 2), "total_explained_variance": safe_round(pca.explained_variance_ratio_.sum() * 100, 2), "loadings": pca_loadings, "points": points}, "clusters": {"labels": [int(label) for label in cluster_labels], "inertia": safe_round(kmeans.inertia_)}, "cluster_profiles": cluster_profiles}


def choose_best_kmeans_k(scaled_data):
    row_count = len(scaled_data)
    max_k = min(8, row_count - 1)
    if max_k < 2:
        return {"selected_k": 2, "k_scores": []}
    k_scores = []
    best_k = 2
    best_score = -1
    for k in range(2, max_k + 1):
        try:
            model = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=10)
            labels = model.fit_predict(scaled_data)
            if len(set(labels)) < 2:
                continue
            score = silhouette_score(scaled_data, labels)
            result = {"k": int(k), "inertia": safe_round(model.inertia_), "silhouette": safe_round(score)}
            k_scores.append(result)
            if score > best_score:
                best_score = score
                best_k = k
        except Exception:
            continue
    return {"selected_k": int(best_k), "k_scores": k_scores}


def build_pca_loadings(pca, numeric_cols):
    loadings = []
    for component_index, component_name in enumerate(["PC1", "PC2"]):
        component = pca.components_[component_index]
        rows = []
        for column, loading in zip(numeric_cols, component):
            rows.append({"column": column, "loading": safe_round(loading), "absolute_loading": safe_round(abs(loading)), "direction": "positive" if loading >= 0 else "negative"})
        rows = sorted(rows, key=lambda item: item["absolute_loading"] or 0, reverse=True)
        loadings.append({"component": component_name, "top_drivers": rows})
    return loadings


def get_target_values_for_indices(df, indices, target_column):
    if not target_column or target_column not in df.columns:
        return None
    return [None if pd.isna(value) else str(value) for value in df.loc[indices, target_column].tolist()]


def build_cluster_profiles(sample, numeric_cols, cluster_labels):
    temp = sample.copy()
    temp["cluster"] = cluster_labels
    profiles = []
    grouped = temp.groupby("cluster")
    for cluster_id, cluster_df in grouped:
        profile = {"cluster": int(cluster_id), "count": int(len(cluster_df)), "numeric_summary": []}
        for column in numeric_cols:
            profile["numeric_summary"].append({"column": column, "mean": safe_round(cluster_df[column].mean()), "median": safe_round(cluster_df[column].median()), "min": safe_round(cluster_df[column].min()), "max": safe_round(cluster_df[column].max())})
        profiles.append(profile)
    return profiles


# =============================================================================
# ADVANCED TARGET ANALYSIS
# =============================================================================

def build_advanced_report(df, schema):
    target_column = detect_target_column(df, schema)
    if not target_column:
        return {"target_detected": False, "message": "No obvious target/outcome column detected yet.", "target": None, "target_distribution": [], "target_by_category": [], "numeric_by_target": []}
    return {"target_detected": True, "message": f"Detected '{target_column}' as a likely target or outcome column.", "target": target_column, "target_distribution": build_target_distribution(df, target_column), "target_by_category": build_target_by_category(df, schema, target_column), "numeric_by_target": build_numeric_by_target(df, schema, target_column)}


def detect_target_column(df, schema):
    preferred_names = ["survived", "species", "target", "label", "class", "outcome", "result", "status", "churn", "converted", "conversion", "purchased", "purchase", "nps", "score", "rating", "satisfaction", "sentiment"]
    all_columns = list(df.columns)
    lower_to_original = {str(col).lower(): col for col in all_columns}
    for name in preferred_names:
        if name in lower_to_original:
            return lower_to_original[name]
    for column in all_columns:
        column_lower = str(column).lower()
        for name in preferred_names:
            if name in column_lower:
                return column
    candidate_columns = schema.get("categorical", []) + schema.get("boolean", [])
    for column in candidate_columns:
        unique_count = df[column].dropna().nunique()
        if 2 <= unique_count <= 10:
            return column
    for column in schema.get("numeric", []):
        unique_values = sorted(df[column].dropna().unique())
        if 2 <= len(unique_values) <= 10:
            return column
    return None


def build_target_distribution(df, target_column):
    counts = df[target_column].value_counts(dropna=False).head(20)
    return [{"target_value": "Missing" if pd.isna(index) else str(index), "count": int(value), "percent": safe_round((value / max(len(df), 1)) * 100, 2)} for index, value in counts.items()]


def build_target_by_category(df, schema, target_column):
    results = []
    target_numeric = pd.to_numeric(df[target_column], errors="coerce")
    target_is_numeric = target_numeric.notna().mean() > 0.85
    categorical_cols = [col for col in get_categorical_like_columns(df, schema) if col != target_column]
    for column in categorical_cols[:8]:
        temp = df[[column, target_column]].dropna()
        if temp.empty:
            continue
        if target_is_numeric:
            temp = temp.copy()
            temp[target_column] = pd.to_numeric(temp[target_column], errors="coerce")
            grouped = temp.dropna().groupby(column)[target_column].agg(["mean", "count"]).sort_values("mean", ascending=False).head(15)
            results.append({"column": column, "target": target_column, "analysis_type": "target_rate_by_category", "rows": [{"category": str(index), "target_average": safe_round(row["mean"]), "count": int(row["count"])} for index, row in grouped.iterrows()]})
        else:
            grouped = temp.groupby(column)[target_column].agg(lambda values: values.value_counts().index[0]).head(15)
            results.append({"column": column, "target": target_column, "analysis_type": "most_common_target_by_category", "rows": [{"category": str(index), "most_common_target": str(value)} for index, value in grouped.items()]})
    return results


def build_numeric_by_target(df, schema, target_column):
    results = []
    numeric_cols = [col for col in schema.get("numeric", []) if col != target_column]
    if not numeric_cols:
        return results
    target_unique_count = df[target_column].dropna().nunique()
    if target_unique_count > 20:
        return results
    for numeric_column in numeric_cols[:10]:
        temp = df[[target_column, numeric_column]].copy()
        temp[numeric_column] = pd.to_numeric(temp[numeric_column], errors="coerce")
        temp = temp.dropna()
        if temp.empty:
            continue
        grouped = temp.groupby(target_column)[numeric_column].agg(["mean", "median", "count"]).sort_values("mean", ascending=False)
        results.append({"numeric_column": numeric_column, "target": target_column, "rows": [{"target_value": str(index), "mean": safe_round(row["mean"]), "median": safe_round(row["median"]), "count": int(row["count"])} for index, row in grouped.iterrows()]})
    return results


# =============================================================================
# MACHINE LEARNING / PREDICTION
# =============================================================================

def prepare_ml_features(df, schema, target_column):
    numeric_cols = [column for column in schema.get("numeric", []) if column != target_column]
    boolean_cols = [column for column in schema.get("boolean", []) if column != target_column]
    categorical_cols = [column for column in schema.get("categorical", []) if column != target_column]
    selected_cols = numeric_cols + boolean_cols + categorical_cols
    if not selected_cols:
        return None, [], {"numeric": [], "boolean": [], "categorical": [], "encoded": []}
    feature_df = df[selected_cols].copy()
    for column in numeric_cols:
        feature_df[column] = pd.to_numeric(feature_df[column], errors="coerce")
        median_value = feature_df[column].median()
        if pd.isna(median_value):
            median_value = 0
        feature_df[column] = feature_df[column].fillna(median_value)
    for column in boolean_cols:
        feature_df[column] = boolean_to_numeric(feature_df[column])
        feature_df[column] = feature_df[column].fillna(0).astype(int)
    if categorical_cols:
        for column in categorical_cols:
            feature_df[column] = feature_df[column].astype("object").where(feature_df[column].notna(), "Missing").astype(str)
        feature_df = pd.get_dummies(feature_df, columns=categorical_cols, dummy_na=False, drop_first=False)
    feature_columns = list(feature_df.columns)
    feature_groups = {"numeric": numeric_cols, "boolean": boolean_cols, "categorical": categorical_cols, "encoded": feature_columns}
    return feature_df, feature_columns, feature_groups


def build_ml_report(df, schema):
    target_column = detect_target_column(df, schema)
    if not target_column:
        return {"available": False, "message": "No target column detected, so supervised ML was not run.", "target": None, "task_type": None, "feature_columns": [], "feature_groups": {}, "models": []}
    X, feature_columns, feature_groups = prepare_ml_features(df, schema, target_column)
    if X is None or len(feature_columns) < 2:
        return {"available": False, "message": "At least two usable feature columns are needed for this first ML pass.", "target": target_column, "task_type": None, "feature_columns": feature_columns, "feature_groups": feature_groups, "models": []}
    model_df = X.copy()
    model_df[target_column] = df[target_column]
    model_df = model_df.dropna(subset=[target_column])
    if len(model_df) < 30:
        return {"available": False, "message": "At least 30 complete target rows are recommended before running supervised ML.", "target": target_column, "task_type": None, "feature_columns": feature_columns, "feature_groups": feature_groups, "models": []}
    task_type = infer_ml_task_type(model_df[target_column])
    if task_type == "classification":
        return build_classification_report(model_df=model_df, feature_columns=feature_columns, target_column=target_column, feature_groups=feature_groups)
    if task_type == "regression":
        return build_regression_report(model_df=model_df, feature_columns=feature_columns, target_column=target_column, feature_groups=feature_groups)
    return {"available": False, "message": "Could not confidently infer whether the target is classification or regression.", "target": target_column, "task_type": None, "feature_columns": feature_columns, "feature_groups": feature_groups, "models": []}


def infer_ml_task_type(target_series):
    non_null = target_series.dropna()
    unique_count = non_null.nunique()
    if unique_count <= 20:
        return "classification"
    numeric_target = pd.to_numeric(non_null, errors="coerce")
    numeric_ratio = numeric_target.notna().mean()
    if numeric_ratio > 0.85:
        return "regression"
    return "classification"


def choose_best_knn_k(X_train_scaled, X_test_scaled, y_train, y_test, task_type):
    max_train_rows = len(X_train_scaled)
    candidate_ks = KNN_CLASSIFICATION_CANDIDATES if task_type == "classification" else KNN_REGRESSION_CANDIDATES
    candidate_ks = [k for k in candidate_ks if k <= max_train_rows]
    if not candidate_ks:
        candidate_ks = [1]
    results = []
    best_k = candidate_ks[0]
    best_score = -999
    for k in candidate_ks:
        if task_type == "classification":
            model = KNeighborsClassifier(n_neighbors=k)
            model.fit(X_train_scaled, y_train)
            predictions = model.predict(X_test_scaled)
            score = accuracy_score(y_test, predictions)
            score_name = "accuracy"
        else:
            model = KNeighborsRegressor(n_neighbors=k)
            model.fit(X_train_scaled, y_train)
            predictions = model.predict(X_test_scaled)
            score = r2_score(y_test, predictions)
            score_name = "R²"
        results.append({"k": int(k), "score_name": score_name, "score": safe_round(score, 4)})
        if score > best_score:
            best_score = score
            best_k = k
    return {"selected_k": int(best_k), "scores": results}


def build_classification_report(model_df, feature_columns, target_column, feature_groups=None):
    X = model_df[feature_columns].apply(pd.to_numeric, errors="coerce").fillna(0)
    y_raw = model_df[target_column].astype(str)
    label_encoder = LabelEncoder()
    y = label_encoder.fit_transform(y_raw)
    if len(set(y)) < 2:
        return {"available": False, "message": "The detected target has only one class after cleaning, so classification cannot run.", "target": target_column, "task_type": "classification", "feature_columns": feature_columns, "feature_groups": feature_groups or {}, "models": []}
    stratify = y if min(np.bincount(y)) >= 2 else None
    try:
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=RANDOM_STATE, stratify=stratify)
    except ValueError:
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=RANDOM_STATE)
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    models = []
    knn_selection = choose_best_knn_k(X_train_scaled=X_train_scaled, X_test_scaled=X_test_scaled, y_train=y_train, y_test=y_test, task_type="classification")
    neighbour_count = knn_selection["selected_k"]
    knn_model = KNeighborsClassifier(n_neighbors=neighbour_count)
    knn_model.fit(X_train_scaled, y_train)
    knn_predictions = knn_model.predict(X_test_scaled)
    knn_accuracy = accuracy_score(y_test, knn_predictions)
    models.append({"name": "K Nearest Neighbours Classifier", "model_key": "knn_classifier", "score_name": "accuracy", "score": safe_round(knn_accuracy, 4), "neighbours": int(neighbour_count), "k_scores": knn_selection["scores"], "notes": "Predicts the target from nearby rows in scaled numeric, boolean and encoded categorical feature space."})
    rf_model = RandomForestClassifier(n_estimators=200, random_state=RANDOM_STATE, class_weight="balanced", max_depth=None, min_samples_leaf=2)
    rf_model.fit(X_train, y_train)
    rf_predictions = rf_model.predict(X_test)
    rf_accuracy = accuracy_score(y_test, rf_predictions)
    feature_importance = build_feature_importance(feature_columns=feature_columns, importances=rf_model.feature_importances_)
    models.append({"name": "Random Forest Classifier", "model_key": "random_forest_classifier", "score_name": "accuracy", "score": safe_round(rf_accuracy, 4), "notes": "Builds many decision trees and combines them. Useful for non-linear patterns and feature importance.", "feature_importance": feature_importance})
    best_model = max(models, key=lambda item: item.get("score") or -999)
    best_predictions = rf_predictions if best_model["model_key"] == "random_forest_classifier" else knn_predictions
    matrix = confusion_matrix(y_test, best_predictions)
    return {"available": True, "message": f"Ran first-pass classification models to predict '{target_column}'. These are exploratory and should not be treated as production models.", "target": target_column, "task_type": "classification", "feature_columns": feature_columns, "feature_groups": feature_groups or {}, "train_rows": int(len(X_train)), "test_rows": int(len(X_test)), "models": models, "best_model": best_model, "class_labels": [str(label) for label in label_encoder.classes_], "confusion_matrix": matrix.astype(int).tolist()}


def build_regression_report(model_df, feature_columns, target_column, feature_groups=None):
    model_df = model_df.copy()
    model_df[target_column] = pd.to_numeric(model_df[target_column], errors="coerce")
    model_df = model_df.dropna()
    if len(model_df) < 30:
        return {"available": False, "message": "At least 30 complete rows are recommended before running regression.", "target": target_column, "task_type": "regression", "feature_columns": feature_columns, "feature_groups": feature_groups or {}, "models": []}
    X = model_df[feature_columns].apply(pd.to_numeric, errors="coerce").fillna(0)
    y = model_df[target_column]
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=RANDOM_STATE)
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    models = []
    knn_selection = choose_best_knn_k(X_train_scaled=X_train_scaled, X_test_scaled=X_test_scaled, y_train=y_train, y_test=y_test, task_type="regression")
    neighbour_count = knn_selection["selected_k"]
    knn_model = KNeighborsRegressor(n_neighbors=neighbour_count)
    knn_model.fit(X_train_scaled, y_train)
    knn_predictions = knn_model.predict(X_test_scaled)
    knn_mae = mean_absolute_error(y_test, knn_predictions)
    knn_rmse = np.sqrt(mean_squared_error(y_test, knn_predictions))
    knn_r2 = r2_score(y_test, knn_predictions)
    models.append({"name": "K Nearest Neighbours Regressor", "model_key": "knn_regressor", "score_name": "R²", "score": safe_round(knn_r2, 4), "mae": safe_round(knn_mae, 4), "rmse": safe_round(knn_rmse, 4), "neighbours": int(neighbour_count), "k_scores": knn_selection["scores"], "notes": "Predicts the numeric target from nearby rows in scaled numeric, boolean and encoded categorical feature space."})
    rf_model = RandomForestRegressor(n_estimators=200, random_state=RANDOM_STATE, max_depth=None, min_samples_leaf=2)
    rf_model.fit(X_train, y_train)
    rf_predictions = rf_model.predict(X_test)
    rf_mae = mean_absolute_error(y_test, rf_predictions)
    rf_rmse = np.sqrt(mean_squared_error(y_test, rf_predictions))
    rf_r2 = r2_score(y_test, rf_predictions)
    feature_importance = build_feature_importance(feature_columns=feature_columns, importances=rf_model.feature_importances_)
    models.append({"name": "Random Forest Regressor", "model_key": "random_forest_regressor", "score_name": "R²", "score": safe_round(rf_r2, 4), "mae": safe_round(rf_mae, 4), "rmse": safe_round(rf_rmse, 4), "notes": "Builds many decision trees and combines them. Useful for non-linear patterns and feature importance.", "feature_importance": feature_importance})
    best_model = max(models, key=lambda item: item.get("score") or -999)
    return {"available": True, "message": f"Ran first-pass regression models to predict '{target_column}'. These are exploratory and should not be treated as production models.", "target": target_column, "task_type": "regression", "feature_columns": feature_columns, "feature_groups": feature_groups or {}, "train_rows": int(len(X_train)), "test_rows": int(len(X_test)), "models": models, "best_model": best_model}


def build_feature_importance(feature_columns, importances, limit=15):
    rows = [{"feature": column, "importance": safe_round(importance, 5)} for column, importance in zip(feature_columns, importances)]
    rows = sorted(rows, key=lambda item: item["importance"] or 0, reverse=True)
    return rows[:limit]


# =============================================================================
# GENERAL UTILS
# =============================================================================

def boolean_to_numeric(series):
    if pd.api.types.is_bool_dtype(series):
        return series.astype(int)
    mapping = {"true": 1, "false": 0, "yes": 1, "no": 0, "y": 1, "n": 0, "1": 1, "0": 0}
    return series.astype(str).str.strip().str.lower().map(mapping)


def safe_round(value, digits=3):
    if pd.isna(value):
        return None
    try:
        return round(float(value), digits)
    except Exception:
        return None


def safe_chart_id(value):
    return str(value).replace(" ", "_").replace("/", "_").replace("\\", "_").replace(".", "_").replace(":", "_").lower()
