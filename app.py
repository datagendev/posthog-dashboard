import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os
import requests
from dotenv import load_dotenv
from collections import defaultdict
from datagen_sdk import DatagenClient, DatagenError, DatagenAuthError

# Load environment variables
load_dotenv()

# Page configuration
st.set_page_config(
    page_title="PostHog Analytics Dashboard",
    page_icon="📊",
    layout="wide"
)

# DataGen API configuration
DATAGEN_API_KEY = os.getenv("DATAGEN_API_KEY")

# Initialize DataGen client
@st.cache_resource
def get_datagen_client():
    """Initialize and cache the DataGen client"""
    if not DATAGEN_API_KEY:
        return None
    return DatagenClient(api_key=DATAGEN_API_KEY)


def call_datagen_tool(tool_name, parameters):
    """Call DataGen MCP tool using the SDK"""
    client = get_datagen_client()

    if not client:
        st.error("DATAGEN_API_KEY not found. Please set it in your .env file.")
        return None

    try:
        result = client.execute_tool(tool_name, parameters)
        return result
    except DatagenAuthError as e:
        st.error(f"Authentication Error: {str(e)}\n\nPlease check your DATAGEN_API_KEY or MCP server configuration.")
        return None
    except DatagenError as e:
        st.error(f"Error calling DataGen tool '{tool_name}': {str(e)}")
        return None
    except Exception as e:
        st.error(f"Unexpected error: {str(e)}")
        return None


# ===== PAGE VIEW ANALYTICS =====

@st.cache_data(ttl=300)
def fetch_page_views_data(date_from="-7d"):
    """Fetch page view data excluding internal users"""
    query = {
        "kind": "DataVisualizationNode",
        "source": {
            "kind": "HogQLQuery",
            "query": f"""
                SELECT
                    toDate(timestamp) as date,
                    count() as page_views,
                    uniq(person_id) as unique_users
                FROM events
                WHERE event = 'page_viewed'
                    AND timestamp >= now() - INTERVAL 7 DAY
                    AND (person.properties.email NOT LIKE '%@datagen.dev' OR person.properties.email IS NULL)
                GROUP BY date
                ORDER BY date
            """
        }
    }
    result = call_datagen_tool("mcp_Posthog_query_run", {"query": query})
    return result


@st.cache_data(ttl=300)
def fetch_top_pages(date_from="-7d"):
    """Fetch top pages by views excluding internal users"""
    query = {
        "kind": "DataVisualizationNode",
        "source": {
            "kind": "HogQLQuery",
            "query": f"""
                SELECT
                    properties.$current_url as page,
                    count() as views
                FROM events
                WHERE event = 'page_viewed'
                    AND timestamp >= now() - INTERVAL 7 DAY
                    AND (person.properties.email NOT LIKE '%@datagen.dev' OR person.properties.email IS NULL)
                GROUP BY page
                ORDER BY views DESC
                LIMIT 10
            """
        }
    }
    result = call_datagen_tool("mcp_Posthog_query_run", {"query": query})
    return result


@st.cache_data(ttl=300)
def fetch_referrer_data(date_from="-7d"):
    """Fetch traffic sources excluding internal users"""
    query = {
        "kind": "DataVisualizationNode",
        "source": {
            "kind": "HogQLQuery",
            "query": f"""
                SELECT
                    properties.$referring_domain as referrer,
                    count() as visits
                FROM events
                WHERE event = '$pageview'
                    AND timestamp >= now() - INTERVAL 7 DAY
                    AND properties.$referring_domain IS NOT NULL
                    AND (person.properties.email NOT LIKE '%@datagen.dev' OR person.properties.email IS NULL)
                GROUP BY referrer
                ORDER BY visits DESC
                LIMIT 10
            """
        }
    }
    result = call_datagen_tool("mcp_Posthog_query_run", {"query": query})
    return result


def parse_hogql_result(result):
    """Parse HogQL query result into DataFrame"""
    if not result or not isinstance(result, list):
        return None

    data_rows = []
    for item in result:
        if isinstance(item, str):
            # Split by newlines and look for data rows
            lines = item.split('\n')
            for line in lines:
                # Look for lines like: "  - [3]: 2025-11-21,271,7"
                if ' - [' in line and ']: ' in line:
                    # Extract data after "]: "
                    parts = line.split(']: ')
                    if len(parts) == 2:
                        # Remove quotes and split by comma
                        values = parts[1].strip().replace('"', '').split(',')
                        data_rows.append(values)

    if not data_rows:
        return None

    return pd.DataFrame(data_rows)


def render_page_view_analytics():
    """Render page view analytics tab"""
    st.header("📄 Page View Analytics")
    st.markdown("*Excluding @datagen.dev internal users*")

    # Fetch data
    with st.spinner("Loading page view data..."):
        page_views_data = fetch_page_views_data()
        top_pages_data = fetch_top_pages()
        referrer_data = fetch_referrer_data()

    # Parse page views trend
    if page_views_data:
        df = parse_hogql_result(page_views_data)
        if df is not None and len(df.columns) >= 3:
            df.columns = ['date', 'page_views', 'unique_users']
            df['page_views'] = pd.to_numeric(df['page_views'])
            df['unique_users'] = pd.to_numeric(df['unique_users'])

            # Metrics
            col1, col2, col3, col4 = st.columns(4)

            total_views = df['page_views'].sum()
            total_users = df['unique_users'].sum()
            avg_views_per_day = df['page_views'].mean()
            avg_views_per_user = total_views / total_users if total_users > 0 else 0

            with col1:
                st.metric("Total Page Views", f"{int(total_views):,}")
            with col2:
                st.metric("Unique Users", f"{int(total_users):,}")
            with col3:
                st.metric("Avg Views/Day", f"{avg_views_per_day:.1f}")
            with col4:
                st.metric("Avg Views/User", f"{avg_views_per_user:.1f}")

            # Page views trend
            st.subheader("📈 Page Views Trend (Last 7 Days)")
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df['date'],
                y=df['page_views'],
                name='Page Views',
                mode='lines+markers',
                line=dict(color='#0045AC', width=2)
            ))
            fig.add_trace(go.Scatter(
                x=df['date'],
                y=df['unique_users'],
                name='Unique Users',
                mode='lines+markers',
                line=dict(color='#FF4500', width=2)
            ))
            fig.update_layout(
                xaxis_title='Date',
                yaxis_title='Count',
                hovermode='x unified',
                height=400
            )
            st.plotly_chart(fig, width='stretch')

    # Top pages and referrers
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🔝 Top Pages")
        if top_pages_data:
            pages_df = parse_hogql_result(top_pages_data)
            if pages_df is not None and len(pages_df.columns) >= 2:
                pages_df.columns = ['page', 'views']
                pages_df['views'] = pd.to_numeric(pages_df['views'])

                fig = px.bar(
                    pages_df,
                    x='views',
                    y='page',
                    orientation='h',
                    color='views',
                    color_continuous_scale='Blues'
                )
                fig.update_layout(
                    showlegend=False,
                    height=400,
                    yaxis={'categoryorder': 'total ascending'}
                )
                st.plotly_chart(fig, width='stretch')

                with st.expander("View Data"):
                    st.dataframe(pages_df, width='stretch')

    with col2:
        st.subheader("🌐 Traffic Sources")
        if referrer_data:
            ref_df = parse_hogql_result(referrer_data)
            if ref_df is not None and len(ref_df.columns) >= 2:
                ref_df.columns = ['referrer', 'visits']
                ref_df['visits'] = pd.to_numeric(ref_df['visits'])

                fig = px.pie(
                    ref_df,
                    values='visits',
                    names='referrer',
                    hole=0.4
                )
                fig.update_layout(height=400)
                st.plotly_chart(fig, width='stretch')

                with st.expander("View Data"):
                    st.dataframe(ref_df, width='stretch')


# ===== DAU ANALYTICS =====

def build_posthog_query(event="$pageview", math="dau", interval="day",
                       breakdown=None, breakdown_type=None, date_from="-30d", custom_name="Daily Active Users"):
    """Build PostHog query structure"""
    query = {
        "kind": "InsightVizNode",
        "source": {
            "kind": "TrendsQuery",
            "series": [{
                "kind": "EventsNode",
                "event": event,
                "math": math,
                "custom_name": custom_name
            }],
            "dateRange": {
                "date_from": date_from,
                "date_to": None
            },
            "interval": interval,
            "filterTestAccounts": True
        }
    }

    # Add breakdown if specified
    if breakdown:
        query["source"]["breakdownFilter"] = {
            "breakdown": breakdown,
            "breakdown_type": breakdown_type or "event"
        }

    return query


@st.cache_data(ttl=300)
def fetch_dau_trend():
    """Fetch DAU trend data"""
    query = build_posthog_query(date_from="-30d", interval="day")
    result = call_datagen_tool("mcp_Posthog_query_run", {"query": query})
    return result


@st.cache_data(ttl=300)
def fetch_geography():
    """Fetch DAU by geography"""
    query = build_posthog_query(
        date_from="-7d",
        breakdown="$geoip_country_name",
        breakdown_type="event",
        custom_name="DAU by Country"
    )
    result = call_datagen_tool("mcp_Posthog_query_run", {"query": query})
    return result


@st.cache_data(ttl=300)
def fetch_hourly_pattern():
    """Fetch hourly DAU pattern"""
    query = build_posthog_query(
        date_from="-7d",
        interval="hour",
        custom_name="DAU by Hour"
    )
    result = call_datagen_tool("mcp_Posthog_query_run", {"query": query})
    return result


def parse_dau_trend(result):
    """Parse DAU trend results"""
    if not result or not isinstance(result, list) or len(result) == 0:
        return None

    data = result[0]

    dau_values = data.split("data[")[1].split("]:")[1].split("\n")[0].strip().split(",")
    dau_values = [int(x) for x in dau_values if x.strip().isdigit()]

    labels_str = data.split("labels[")[1].split("]:")[1].split("\n")[0].strip()
    labels_raw = [x.strip() for x in labels_str.split(",")]

    labels = []
    for label in labels_raw:
        try:
            date_obj = datetime.strptime(label, '%d-%b-%Y')
            labels.append(date_obj.strftime('%Y-%m-%d'))
        except:
            labels.append(label)

    df = pd.DataFrame({
        'date': labels,
        'dau': dau_values
    })

    return df


def parse_breakdown(result):
    """Parse breakdown results (geography, traffic sources, etc.)"""
    if not result or not isinstance(result, list):
        return None

    breakdown_data = []

    for item in result:
        if "label:" in item:
            label = item.split("label:")[1].split("\n")[0].strip()
        else:
            continue

        if "count:" in item:
            count_str = item.split("count:")[1].split("\n")[0].strip()
            count = int(count_str) if count_str.isdigit() else 0
        else:
            count = 0

        if label and label != "$$_posthog_breakdown_null_$$" and count > 0:
            breakdown_data.append({
                'label': label,
                'count': count
            })

    if not breakdown_data:
        return None

    df = pd.DataFrame(breakdown_data)
    df = df.sort_values('count', ascending=False)

    return df


def parse_hourly_pattern(result):
    """Parse hourly pattern and aggregate by hour of day"""
    if not result or not isinstance(result, list) or len(result) == 0:
        return None

    data = result[0]

    dau_values = data.split("data[")[1].split("]:")[1].split("\n")[0].strip().split(",")
    dau_values = [int(x) for x in dau_values if x.strip().lstrip('-').isdigit()]

    labels_str = data.split("labels[")[1].split("]:")[1].split("\n")[0].strip()
    labels = [x.strip().strip('"') for x in labels_str.split('","')]

    hourly_totals = defaultdict(list)

    for label, value in zip(labels, dau_values):
        if ":" in label:
            hour_part = label.split()[-1].split(":")[0]
            hour = int(hour_part)
            hourly_totals[hour].append(value)

    hourly_avg = []
    for hour in range(24):
        if hour in hourly_totals and len(hourly_totals[hour]) > 0:
            avg = sum(hourly_totals[hour]) / len(hourly_totals[hour])
        else:
            avg = 0
        hourly_avg.append({
            'hour': hour,
            'avg_dau': round(avg, 2)
        })

    df = pd.DataFrame(hourly_avg)

    return df


def render_dau_analytics():
    """Render DAU analytics tab"""
    st.header("👥 Daily Active Users (DAU)")
    st.markdown("*Excluding @datagen.dev internal users (via filterTestAccounts)*")

    # Fetch data
    with st.spinner("Loading DAU data..."):
        dau_trend = fetch_dau_trend()
        geography = fetch_geography()
        hourly = fetch_hourly_pattern()

    # Parse data
    dau_df = parse_dau_trend(dau_trend)
    geo_df = parse_breakdown(geography)
    hourly_df = parse_hourly_pattern(hourly)

    # Metrics
    if dau_df is not None and len(dau_df) > 0:
        today_dau = dau_df.iloc[-1]['dau']
        yesterday_dau = dau_df.iloc[-2]['dau'] if len(dau_df) > 1 else 0
        avg_7d = int(dau_df.iloc[-7:]['dau'].mean()) if len(dau_df) >= 7 else 0
        avg_30d = int(dau_df['dau'].mean())

        today_delta = today_dau - yesterday_dau if yesterday_dau > 0 else 0
        today_delta_pct = f"{((today_delta / yesterday_dau) * 100):.1f}%" if yesterday_dau > 0 else "N/A"

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric(
                label="Today's DAU",
                value=f"{today_dau:,}",
                delta=today_delta_pct
            )

        with col2:
            st.metric(
                label="7-Day Average",
                value=f"{avg_7d:,}"
            )

        with col3:
            st.metric(
                label="30-Day Average",
                value=f"{avg_30d:,}"
            )

    # DAU Trend Chart
    st.subheader("📈 DAU Trend (Last 30 Days)")
    if dau_df is not None:
        fig = px.line(
            dau_df,
            x='date',
            y='dau',
            title='Daily Active Users Over Time',
            labels={'date': 'Date', 'dau': 'Daily Active Users'},
            markers=True
        )
        fig.update_layout(
            hovermode='x unified',
            xaxis_tickangle=-45
        )
        st.plotly_chart(fig, width='stretch')
    else:
        st.warning("No DAU trend data available")

    # Two columns for breakdowns
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🌍 Geographic Distribution")
        if geo_df is not None:
            fig = px.bar(
                geo_df,
                x='label',
                y='count',
                title='DAU by Country (Last 7 Days)',
                labels={'label': 'Country', 'count': 'DAU'},
                color='count',
                color_continuous_scale='Blues'
            )
            fig.update_layout(
                xaxis_tickangle=-45,
                showlegend=False
            )
            st.plotly_chart(fig, width='stretch')

            with st.expander("View Data"):
                st.dataframe(geo_df, width='stretch')
        else:
            st.info("No geographic breakdown data available")

    with col2:
        st.subheader("⏰ Hourly Activity Pattern")
        if hourly_df is not None:
            fig = px.line(
                hourly_df,
                x='hour',
                y='avg_dau',
                title='Average DAU by Hour of Day (Last 7 Days)',
                labels={'hour': 'Hour (UTC)', 'avg_dau': 'Average DAU'},
                markers=True
            )
            fig.update_layout(
                xaxis=dict(
                    tickmode='linear',
                    tick0=0,
                    dtick=2
                )
            )
            st.plotly_chart(fig, width='stretch')

            with st.expander("View Data"):
                st.dataframe(hourly_df, width='stretch')
        else:
            st.info("No hourly pattern data available")


# ===== ERROR TRACKER =====

@st.cache_data(ttl=300)
def fetch_errors():
    """Fetch error list from PostHog"""
    result = call_datagen_tool("mcp_Posthog_list_errors", {})
    return result


@st.cache_data(ttl=300)
def fetch_error_details(error_id):
    """Fetch error details from PostHog"""
    result = call_datagen_tool("mcp_Posthog_error_details", {"error_id": error_id})
    return result


@st.cache_data(ttl=300)
def fetch_error_timeline(days=30):
    """Fetch error occurrences over time"""
    query = {
        "kind": "DataVisualizationNode",
        "source": {
            "kind": "HogQLQuery",
            "query": f"""
                SELECT
                    toDate(timestamp) as date,
                    count() as error_count,
                    uniq(person_id) as affected_users
                FROM events
                WHERE event = '$exception'
                    AND timestamp >= now() - INTERVAL {days} DAY
                GROUP BY date
                ORDER BY date
            """
        }
    }
    result = call_datagen_tool("mcp_Posthog_query_run", {"query": query})
    return result


@st.cache_data(ttl=300)
def fetch_error_timeline_by_type(days=30):
    """Fetch error occurrences by error type over time"""
    query = {
        "kind": "DataVisualizationNode",
        "source": {
            "kind": "HogQLQuery",
            "query": f"""
                SELECT
                    toDate(timestamp) as date,
                    replaceAll(arrayElement(JSONExtractArrayRaw(properties, '$exception_types'), 1), '"', '') as error_type,
                    count() as count
                FROM events
                WHERE event = '$exception'
                    AND timestamp >= now() - INTERVAL {days} DAY
                GROUP BY date, error_type
                ORDER BY date, count DESC
            """
        }
    }
    result = call_datagen_tool("mcp_Posthog_query_run", {"query": query})
    return result


def parse_errors(result):
    """Parse error list result"""
    if not result or not isinstance(result, list):
        return None

    errors = []
    for item in result:
        if isinstance(item, str):
            # Parse error data from string format
            error_data = {}

            # Extract key fields
            if "id:" in item:
                error_data['id'] = item.split("id:")[1].split("\n")[0].strip()
            if "name:" in item:
                error_data['name'] = item.split("name:")[1].split("\n")[0].strip()
            if "description:" in item:
                error_data['description'] = item.split("description:")[1].split("\n")[0].strip()
            if "source:" in item:
                error_data['source'] = item.split("source:")[1].split("\n")[0].strip()
            if "status:" in item:
                error_data['status'] = item.split("status:")[1].split("\n")[0].strip()

            # Parse aggregations
            if "occurrences:" in item:
                occ_str = item.split("occurrences:")[1].split("\n")[0].strip()
                error_data['occurrences'] = int(occ_str) if occ_str.isdigit() else 0

            if "users:" in item:
                users_str = item.split("users:")[1].split("\n")[0].strip()
                error_data['users'] = int(users_str) if users_str.isdigit() else 0

            if "sessions:" in item:
                sessions_str = item.split("sessions:")[1].split("\n")[0].strip()
                error_data['sessions'] = int(sessions_str) if sessions_str.isdigit() else 0

            if "first_seen:" in item:
                error_data['first_seen'] = item.split("first_seen:")[1].split("\n")[0].strip().replace('"', '')

            if "last_seen:" in item:
                error_data['last_seen'] = item.split("last_seen:")[1].split("\n")[0].strip().replace('"', '')

            if error_data:
                errors.append(error_data)

    if not errors:
        return None

    return pd.DataFrame(errors)


def render_error_tracker():
    """Render error tracker tab"""
    st.header("🐛 Error Tracker")
    st.markdown("*Monitor and track application errors*")

    # Fetch errors
    with st.spinner("Loading errors..."):
        errors_data = fetch_errors()

    if not errors_data:
        st.info("No errors found")
        return

    errors_df = parse_errors(errors_data)

    if errors_df is None or len(errors_df) == 0:
        st.success("✅ No errors found!")
        return

    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)

    total_errors = len(errors_df)
    total_occurrences = errors_df['occurrences'].sum() if 'occurrences' in errors_df.columns else 0
    total_users = errors_df['users'].sum() if 'users' in errors_df.columns else 0
    active_errors = len(errors_df[errors_df['status'] == 'active']) if 'status' in errors_df.columns else 0

    with col1:
        st.metric("Total Errors", total_errors)
    with col2:
        st.metric("Total Occurrences", int(total_occurrences))
    with col3:
        st.metric("Affected Users", int(total_users))
    with col4:
        st.metric("Active Errors", active_errors)

    # Error Timeline
    st.subheader("📅 Error Timeline")

    # Time range selector
    col1, col2 = st.columns([3, 1])
    with col2:
        timeline_days = st.selectbox(
            "Time Range",
            options=[7, 14, 30, 60, 90],
            index=2,  # Default to 30 days
            format_func=lambda x: f"Last {x} days"
        )

    with st.spinner("Loading error timeline..."):
        timeline_data = fetch_error_timeline(days=timeline_days)
        timeline_by_type_data = fetch_error_timeline_by_type(days=timeline_days)

    # Parse and display timeline
    if timeline_data:
        timeline_df = parse_hogql_result(timeline_data)
        if timeline_df is not None and len(timeline_df.columns) >= 3:
            timeline_df.columns = ['date', 'error_count', 'affected_users']
            timeline_df['error_count'] = pd.to_numeric(timeline_df['error_count'])
            timeline_df['affected_users'] = pd.to_numeric(timeline_df['affected_users'])

            # Create timeline chart
            fig = go.Figure()

            # Add error count line
            fig.add_trace(go.Scatter(
                x=timeline_df['date'],
                y=timeline_df['error_count'],
                name='Error Occurrences',
                mode='lines+markers',
                line=dict(color='#DC2626', width=2),
                marker=dict(size=8),
                yaxis='y'
            ))

            # Add affected users line
            fig.add_trace(go.Scatter(
                x=timeline_df['date'],
                y=timeline_df['affected_users'],
                name='Affected Users',
                mode='lines+markers',
                line=dict(color='#F59E0B', width=2),
                marker=dict(size=8),
                yaxis='y2'
            ))

            fig.update_layout(
                title=f'Error Timeline - Last {timeline_days} Days',
                xaxis=dict(title='Date'),
                yaxis=dict(
                    title='Error Occurrences',
                    tickfont=dict(color='#DC2626'),
                    title_font=dict(color='#DC2626')
                ),
                yaxis2=dict(
                    title='Affected Users',
                    tickfont=dict(color='#F59E0B'),
                    title_font=dict(color='#F59E0B'),
                    overlaying='y',
                    side='right'
                ),
                hovermode='x unified',
                height=400,
                showlegend=True,
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1
                )
            )

            st.plotly_chart(fig, width='stretch')

            # Show timeline data table
            with st.expander("View Timeline Data"):
                st.dataframe(timeline_df, width='stretch')
        else:
            st.info(f"No errors recorded in the last {timeline_days} days")
    else:
        st.info(f"No error timeline data available for the last {timeline_days} days")

    # Daily error trend by type
    if timeline_by_type_data:
        st.subheader("📈 Daily Error Trend by Type")

        type_df = parse_hogql_result(timeline_by_type_data)
        if type_df is not None and len(type_df.columns) >= 3:
            type_df.columns = ['date', 'error_type', 'count']
            type_df['count'] = pd.to_numeric(type_df['count'])

            # Create line trend chart
            fig = px.line(
                type_df,
                x='date',
                y='count',
                color='error_type',
                title=f'Daily Error Trend by Type - Last {timeline_days} Days',
                labels={'count': 'Error Count', 'date': 'Date', 'error_type': 'Error Type'},
                markers=True
            )
            fig.update_layout(
                hovermode='x unified',
                height=400,
                showlegend=True,
                legend=dict(
                    orientation="v",
                    yanchor="top",
                    y=1,
                    xanchor="left",
                    x=1.02
                )
            )
            fig.update_traces(line=dict(width=2), marker=dict(size=6))
            st.plotly_chart(fig, width='stretch')

            with st.expander("View Error Trend Data"):
                # Pivot table for better viewing
                pivot_df = type_df.pivot(index='date', columns='error_type', values='count').fillna(0)
                pivot_df = pivot_df.astype(int)
                st.dataframe(pivot_df, width='stretch')

    # Error list
    st.subheader("📋 Error List")

    # Display errors as expandable cards
    for idx, error in errors_df.iterrows():
        status_emoji = "🔴" if error.get('status') == 'active' else "🟢"

        with st.expander(f"{status_emoji} {error.get('name', 'Unknown Error')} - {error.get('description', '')}"):
            col1, col2 = st.columns(2)

            with col1:
                st.markdown(f"**Error ID:** `{error.get('id', 'N/A')}`")
                st.markdown(f"**Source:** `{error.get('source', 'N/A')}`")
                st.markdown(f"**Status:** {error.get('status', 'N/A')}")

            with col2:
                st.markdown(f"**Occurrences:** {error.get('occurrences', 0)}")
                st.markdown(f"**Affected Users:** {error.get('users', 0)}")
                st.markdown(f"**Sessions:** {error.get('sessions', 0)}")

            if 'first_seen' in error and error['first_seen']:
                st.markdown(f"**First Seen:** {error['first_seen']}")
            if 'last_seen' in error and error['last_seen']:
                st.markdown(f"**Last Seen:** {error['last_seen']}")

    # Error trends
    st.subheader("📊 Error Statistics")

    if 'occurrences' in errors_df.columns:
        # Top errors by occurrence
        top_errors = errors_df.nlargest(10, 'occurrences')[['name', 'occurrences', 'users']]

        fig = px.bar(
            top_errors,
            x='occurrences',
            y='name',
            orientation='h',
            title='Top Errors by Occurrence',
            color='occurrences',
            color_continuous_scale='Reds',
            labels={'name': 'Error', 'occurrences': 'Occurrences'}
        )
        fig.update_layout(
            yaxis={'categoryorder': 'total ascending'},
            showlegend=False,
            height=400
        )
        st.plotly_chart(fig, width='stretch')


# ===== MAIN APP =====

def main():
    st.title("📊 PostHog Analytics Dashboard")

    # Refresh button
    col1, col2 = st.columns([6, 1])
    with col2:
        if st.button("🔄 Refresh", width='stretch'):
            st.cache_data.clear()
            st.rerun()

    # Check API key
    if not DATAGEN_API_KEY:
        st.error("⚠️ DATAGEN_API_KEY not configured. Please create a .env file with your API key.")
        st.code("DATAGEN_API_KEY=your-api-key-here", language="bash")
        return

    # Tab-based navigation with lazy loading
    tabs = st.tabs(["📄 Page Views", "👥 DAU Analytics", "🐛 Error Tracker"])

    with tabs[0]:
        render_page_view_analytics()

    with tabs[1]:
        render_dau_analytics()

    with tabs[2]:
        render_error_tracker()

    # Footer
    st.markdown("---")
    st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
