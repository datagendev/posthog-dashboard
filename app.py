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
    page_title="PostHog DAU Dashboard",
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


@st.cache_data(ttl=300)
def fetch_reddit_traffic():
    """Fetch DAU from Reddit traffic specifically"""
    query = {
        "kind": "InsightVizNode",
        "source": {
            "kind": "TrendsQuery",
            "series": [{
                "kind": "EventsNode",
                "event": "$pageview",
                "math": "dau",
                "custom_name": "DAU from Reddit"
            }],
            "dateRange": {
                "date_from": "-30d",
                "date_to": None
            },
            "interval": "day",
            "filterTestAccounts": True,
            "properties": [{
                "key": "$referring_domain",
                "operator": "icontains",
                "value": "reddit",
                "type": "event"
            }]
        }
    }
    result = call_datagen_tool("mcp_Posthog_query_run", {"query": query})
    return result


@st.cache_data(ttl=600)
def fetch_reddit_activity(username="AccurateSuggestion54", limit=100):
    """Fetch Reddit posts and comments for a user"""
    url = f"https://www.reddit.com/user/{username}.json?limit={limit}"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; Streamlit Dashboard)"}

    all_posts = []

    try:
        while url and len(all_posts) < limit:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()

            for child in data['data']['children']:
                post_data = child['data']

                # Determine if it's a post or comment
                is_comment = child['kind'] == 't1'

                activity = {
                    'type': 'comment' if is_comment else 'post',
                    'created_utc': post_data['created_utc'],
                    'created_date': datetime.fromtimestamp(post_data['created_utc']).strftime('%Y-%m-%d'),
                    'title': post_data.get('link_title') or post_data.get('title', ''),
                    'subreddit': post_data['subreddit'],
                    'score': post_data['score'],
                    'num_comments': post_data.get('num_comments', 0),
                    'url': f"https://reddit.com{post_data['permalink']}"
                }
                all_posts.append(activity)

            # Pagination
            after = data['data'].get('after')
            if after and len(all_posts) < limit:
                url = f"https://www.reddit.com/user/{username}.json?after={after}&limit={limit}"
            else:
                url = None

        return pd.DataFrame(all_posts)
    except Exception as e:
        st.warning(f"Could not fetch Reddit data: {str(e)}")
        return pd.DataFrame()


def aggregate_reddit_by_date(reddit_df):
    """Aggregate Reddit activity by date"""
    if reddit_df.empty:
        return pd.DataFrame(columns=['date', 'post_count', 'comment_count', 'total_score'])

    # Group by date
    daily = reddit_df.groupby('created_date').agg({
        'type': lambda x: (x == 'post').sum(),
        'score': 'sum'
    }).reset_index()

    daily.columns = ['date', 'post_count', 'total_score']

    # Add comment count
    comment_counts = reddit_df[reddit_df['type'] == 'comment'].groupby('created_date').size()
    daily['comment_count'] = daily['date'].map(comment_counts).fillna(0).astype(int)
    daily['total_activity'] = daily['post_count'] + daily['comment_count']

    return daily


def parse_dau_trend(result):
    """Parse DAU trend results"""
    if not result or not isinstance(result, list) or len(result) == 0:
        return None

    # Extract the first result
    data = result[0]

    # Parse the data - PostHog returns arrays in string format
    dau_values = data.split("data[")[1].split("]:")[1].split("\n")[0].strip().split(",")
    dau_values = [int(x) for x in dau_values if x.strip().isdigit()]

    labels_str = data.split("labels[")[1].split("]:")[1].split("\n")[0].strip()
    labels_raw = [x.strip() for x in labels_str.split(",")]

    # Convert PostHog date format (e.g., "20-Nov-2025") to YYYY-MM-DD
    labels = []
    for label in labels_raw:
        try:
            # Parse PostHog date format
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
        # Extract label (breakdown value)
        if "label:" in item:
            label = item.split("label:")[1].split("\n")[0].strip()
        else:
            continue

        # Extract count
        if "count:" in item:
            count_str = item.split("count:")[1].split("\n")[0].strip()
            count = int(count_str) if count_str.isdigit() else 0
        else:
            count = 0

        # Skip null/empty breakdowns
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

    # Extract hourly data
    dau_values = data.split("data[")[1].split("]:")[1].split("\n")[0].strip().split(",")
    dau_values = [int(x) for x in dau_values if x.strip().lstrip('-').isdigit()]

    # Extract hour labels
    labels_str = data.split("labels[")[1].split("]:")[1].split("\n")[0].strip()
    labels = [x.strip().strip('"') for x in labels_str.split('","')]

    # Aggregate by hour of day (0-23)
    hourly_totals = defaultdict(list)

    for label, value in zip(labels, dau_values):
        # Extract hour from label like "20-Nov 08:00"
        if ":" in label:
            hour_part = label.split()[-1].split(":")[0]
            hour = int(hour_part)
            hourly_totals[hour].append(value)

    # Calculate average for each hour
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


def generate_summary(dau_df, geo_df, hourly_df):
    """Generate summary insights"""
    summary = "## 📊 DAU Summary\n\n"

    if dau_df is not None and len(dau_df) > 0:
        today_dau = dau_df.iloc[-1]['dau']
        yesterday_dau = dau_df.iloc[-2]['dau'] if len(dau_df) > 1 else 0
        avg_7d = dau_df.iloc[-7:]['dau'].mean() if len(dau_df) >= 7 else 0
        avg_30d = dau_df['dau'].mean()

        summary += f"### Key Metrics\n"
        summary += f"- **Today's DAU**: {today_dau:,} users\n"
        summary += f"- **7-Day Average**: {avg_7d:.1f} users\n"
        summary += f"- **30-Day Average**: {avg_30d:.1f} users\n"

        # Trend analysis
        if yesterday_dau > 0:
            change_pct = ((today_dau - yesterday_dau) / yesterday_dau) * 100
            trend = "increased" if change_pct > 0 else "decreased"
            summary += f"- **Day-over-day**: {trend} by {abs(change_pct):.1f}%\n"

        summary += "\n"

    if geo_df is not None and len(geo_df) > 0:
        top_country = geo_df.iloc[0]['label']
        top_count = geo_df.iloc[0]['count']
        total_countries = len(geo_df)

        summary += f"### Geographic Distribution\n"
        summary += f"- **Top Country**: {top_country} ({top_count} DAU)\n"
        summary += f"- **Total Countries**: {total_countries}\n"

        # Top 3 countries
        if len(geo_df) > 1:
            summary += f"- **Top 3**: {', '.join(geo_df.head(3)['label'].tolist())}\n"
        summary += "\n"

    if hourly_df is not None and len(hourly_df) > 0:
        peak_hour_row = hourly_df.loc[hourly_df['avg_dau'].idxmax()]
        peak_hour = int(peak_hour_row['hour'])
        peak_dau = peak_hour_row['avg_dau']

        summary += f"### Peak Activity\n"
        summary += f"- **Peak Hour**: {peak_hour:02d}:00 UTC ({peak_dau:.1f} avg DAU)\n"

        # Activity pattern
        morning_avg = hourly_df[(hourly_df['hour'] >= 6) & (hourly_df['hour'] < 12)]['avg_dau'].mean()
        afternoon_avg = hourly_df[(hourly_df['hour'] >= 12) & (hourly_df['hour'] < 18)]['avg_dau'].mean()
        evening_avg = hourly_df[(hourly_df['hour'] >= 18) & (hourly_df['hour'] < 24)]['avg_dau'].mean()

        peak_period = "morning" if morning_avg > max(afternoon_avg, evening_avg) else \
                     "afternoon" if afternoon_avg > evening_avg else "evening"
        summary += f"- **Most Active Period**: {peak_period.capitalize()}\n"

    summary += "\n---\n"
    summary += "*Note: All data excludes internal @datagen.dev users*\n"

    return summary


# Main app
def main():
    st.title("📊 PostHog Daily Active Users Dashboard")
    st.markdown("*Excluding @datagen.dev users (via filterTestAccounts)*")

    # Refresh button
    col1, col2 = st.columns([6, 1])
    with col2:
        if st.button("🔄 Refresh", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # Check API key
    if not DATAGEN_API_KEY:
        st.error("⚠️ DATAGEN_API_KEY not configured. Please create a .env file with your API key.")
        st.code("DATAGEN_API_KEY=your-api-key-here", language="bash")
        return

    # Fetch data
    with st.spinner("Fetching PostHog data..."):
        dau_trend = fetch_dau_trend()
        geography = fetch_geography()
        hourly = fetch_hourly_pattern()

    # Fetch Reddit data
    with st.spinner("Fetching Reddit activity..."):
        reddit_df = fetch_reddit_activity()
        reddit_traffic = fetch_reddit_traffic()

    # Parse data
    dau_df = parse_dau_trend(dau_trend)
    reddit_traffic_df = parse_dau_trend(reddit_traffic)
    geo_df = parse_breakdown(geography)
    hourly_df = parse_hourly_pattern(hourly)

    # Display summary section
    st.header("📝 Summary")
    summary_text = generate_summary(dau_df, geo_df, hourly_df)
    st.markdown(summary_text)

    # Main metrics
    st.header("📈 DAU Overview")

    if dau_df is not None and len(dau_df) > 0:
        today_dau = dau_df.iloc[-1]['dau']
        yesterday_dau = dau_df.iloc[-2]['dau'] if len(dau_df) > 1 else 0
        avg_7d = int(dau_df.iloc[-7:]['dau'].mean()) if len(dau_df) >= 7 else 0
        avg_30d = int(dau_df['dau'].mean())

        # Calculate deltas
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
                value=f"{avg_7d:,}",
                delta=None
            )

        with col3:
            st.metric(
                label="30-Day Average",
                value=f"{avg_30d:,}",
                delta=None
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
        st.plotly_chart(fig, use_container_width=True)
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
            st.plotly_chart(fig, use_container_width=True)

            # Show data table
            with st.expander("View Data"):
                st.dataframe(geo_df, use_container_width=True)
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
            st.plotly_chart(fig, use_container_width=True)

            # Show data table
            with st.expander("View Data"):
                st.dataframe(hourly_df, use_container_width=True)
        else:
            st.info("No hourly pattern data available")

    # Reddit Impact Analysis Section
    st.markdown("---")
    st.header("🔥 Reddit Activity Impact Analysis")

    if not reddit_df.empty and reddit_traffic_df is not None:
        # Aggregate Reddit data
        reddit_daily = aggregate_reddit_by_date(reddit_df)

        # Merge with Reddit traffic data (users who came from reddit.com)
        merged_df = reddit_traffic_df.merge(reddit_daily, on='date', how='left')
        merged_df['post_count'] = merged_df['post_count'].fillna(0).astype(int)
        merged_df['comment_count'] = merged_df['comment_count'].fillna(0).astype(int)
        merged_df['total_activity'] = merged_df['total_activity'].fillna(0).astype(int)
        merged_df['total_score'] = merged_df['total_score'].fillna(0).astype(int)

        # Calculate correlation
        if merged_df['total_activity'].sum() > 0:
            corr = merged_df[['dau', 'total_activity']].corr().iloc[0, 1]

            # Display correlation metrics
            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric(
                    label="Total Reddit Posts",
                    value=f"{int(reddit_df[reddit_df['type'] == 'post'].shape[0]):,}"
                )

            with col2:
                st.metric(
                    label="Total Reddit Comments",
                    value=f"{int(reddit_df[reddit_df['type'] == 'comment'].shape[0]):,}"
                )

            with col3:
                corr_color = "🟢" if corr > 0.1 else "🟡" if corr > 0 else "🔴"
                st.metric(
                    label=f"{corr_color} Correlation with DAU",
                    value=f"{corr:.3f}"
                )

            # Create overlay visualization
            st.subheader("📊 Reddit Traffic vs Reddit Activity Overlay")

            fig = go.Figure()

            # Reddit-sourced DAU line (primary y-axis)
            fig.add_trace(go.Scatter(
                x=merged_df['date'],
                y=merged_df['dau'],
                name='DAU from Reddit',
                mode='lines+markers',
                line=dict(color='#0045AC', width=2),
                yaxis='y'
            ))

            # Reddit posts (secondary y-axis)
            fig.add_trace(go.Bar(
                x=merged_df['date'],
                y=merged_df['post_count'],
                name='Reddit Posts',
                marker=dict(color='#FF4500', opacity=0.6),
                yaxis='y2'
            ))

            # Reddit comments (secondary y-axis)
            fig.add_trace(go.Bar(
                x=merged_df['date'],
                y=merged_df['comment_count'],
                name='Reddit Comments',
                marker=dict(color='#FFA07A', opacity=0.6),
                yaxis='y2'
            ))

            # Update layout with dual y-axes
            fig.update_layout(
                xaxis=dict(title='Date', tickangle=-45),
                yaxis=dict(
                    title='DAU from Reddit Traffic',
                    titlefont=dict(color='#0045AC'),
                    tickfont=dict(color='#0045AC')
                ),
                yaxis2=dict(
                    title='Reddit Activity Count',
                    titlefont=dict(color='#FF4500'),
                    tickfont=dict(color='#FF4500'),
                    overlaying='y',
                    side='right'
                ),
                hovermode='x unified',
                height=500,
                barmode='stack'
            )

            st.plotly_chart(fig, use_container_width=True)

            # High-impact days
            st.subheader("🎯 High-Impact Reddit Activities")

            active_days = merged_df[merged_df['total_activity'] > 0].copy()
            if not active_days.empty:
                active_days = active_days.sort_values('total_score', ascending=False).head(5)

                for _, row in active_days.iterrows():
                    date = row['date']
                    dau = int(row['dau'])
                    posts = int(row['post_count'])
                    comments = int(row['comment_count'])
                    score = int(row['total_score'])

                    with st.expander(f"📅 {date} - DAU: {dau:,} | Score: {score}"):
                        st.write(f"**Activity**: {posts} post(s), {comments} comment(s)")

                        # Show actual posts from that day
                        day_posts = reddit_df[reddit_df['created_date'] == date].head(3)
                        for _, post in day_posts.iterrows():
                            st.markdown(f"- [{post['type']}] {post['title'][:100]}... (+{post['score']})")
                            st.caption(f"  r/{post['subreddit']} - [link]({post['url']})")
            else:
                st.info("No Reddit activity found in the current DAU period")
        else:
            st.info("No Reddit activity overlaps with the DAU data period")
    else:
        st.warning("Could not load Reddit data for impact analysis")

    # Footer
    st.markdown("---")
    st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
