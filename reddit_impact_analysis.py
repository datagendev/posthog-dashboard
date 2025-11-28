#!/usr/bin/env python3
"""
Reddit Impact Analysis
Correlates Reddit posts/comments with PostHog DAU metrics
"""

import os
import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
from dotenv import load_dotenv
from datagen_sdk import DatagenClient, DatagenError

# Load environment variables
load_dotenv()

# Configuration
REDDIT_USERNAME = "AccurateSuggestion54"
DATAGEN_API_KEY = os.getenv("DATAGEN_API_KEY")


def fetch_reddit_activity(username, limit=100):
    """Fetch Reddit posts and comments for a user"""
    print(f"Fetching Reddit activity for u/{username}...")

    url = f"https://www.reddit.com/user/{username}.json?limit={limit}"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; Python script)"}

    all_posts = []

    while url:
        response = requests.get(url, headers=headers)
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

    print(f"✅ Found {len(all_posts)} Reddit activities")
    return pd.DataFrame(all_posts)


def fetch_posthog_dau(days=90):
    """Fetch PostHog DAU data"""
    print(f"\nFetching PostHog DAU for last {days} days...")

    if not DATAGEN_API_KEY:
        raise ValueError("DATAGEN_API_KEY not set")

    client = DatagenClient(api_key=DATAGEN_API_KEY)

    query = {
        "kind": "InsightVizNode",
        "source": {
            "kind": "TrendsQuery",
            "series": [{
                "kind": "EventsNode",
                "event": "$pageview",
                "math": "dau",
                "custom_name": "Daily Active Users"
            }],
            "dateRange": {
                "date_from": f"-{days}d",
                "date_to": None
            },
            "interval": "day",
            "filterTestAccounts": True
        }
    }

    result = client.execute_tool("mcp_Posthog_query_run", {"query": query})

    # Parse the result
    if not result or not isinstance(result, list) or len(result) == 0:
        raise ValueError("No DAU data returned")

    data_str = result[0]

    # Extract DAU values
    dau_line = [line for line in data_str.split('\n') if 'data[' in line][0]
    dau_values = dau_line.split(']:')[1].split('\n')[0].strip().split(',')
    dau_values = [int(x) for x in dau_values if x.strip().isdigit()]

    # Extract labels
    labels_line = [line for line in data_str.split('\n') if 'labels[' in line][0]
    labels_raw = labels_line.split(']:')[1].split('\n')[0].strip().split(',')

    # Convert PostHog date format (e.g., "20-Nov-2025") to YYYY-MM-DD
    labels = []
    for label in labels_raw:
        try:
            # Parse PostHog date format
            date_obj = datetime.strptime(label.strip(), '%d-%b-%Y')
            labels.append(date_obj.strftime('%Y-%m-%d'))
        except:
            labels.append(label.strip())

    df = pd.DataFrame({
        'date': labels,
        'dau': dau_values
    })

    print(f"✅ Fetched {len(df)} days of DAU data")
    return df


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

    return daily


def create_overlay_visualization(posthog_df, reddit_df):
    """Create visualization overlaying Reddit activity and DAU"""
    print("\nCreating visualization...")

    # Aggregate Reddit data by date
    reddit_daily = aggregate_reddit_by_date(reddit_df)

    # Merge datasets
    merged = posthog_df.merge(reddit_daily, on='date', how='left')
    merged['post_count'] = merged['post_count'].fillna(0).astype(int)
    merged['comment_count'] = merged['comment_count'].fillna(0).astype(int)
    merged['total_score'] = merged['total_score'].fillna(0).astype(int)

    # Create figure with secondary y-axis
    fig = go.Figure()

    # DAU line (primary y-axis)
    fig.add_trace(go.Scatter(
        x=merged['date'],
        y=merged['dau'],
        name='Daily Active Users',
        mode='lines+markers',
        line=dict(color='#0045AC', width=2),
        yaxis='y'
    ))

    # Reddit posts (secondary y-axis)
    fig.add_trace(go.Bar(
        x=merged['date'],
        y=merged['post_count'],
        name='Reddit Posts',
        marker=dict(color='#FF4500', opacity=0.6),
        yaxis='y2'
    ))

    # Reddit comments (secondary y-axis)
    fig.add_trace(go.Bar(
        x=merged['date'],
        y=merged['comment_count'],
        name='Reddit Comments',
        marker=dict(color='#FFA07A', opacity=0.6),
        yaxis='y2'
    ))

    # Update layout with dual y-axes
    fig.update_layout(
        title=f'Reddit Activity Impact on DAU<br><sub>User: u/{REDDIT_USERNAME}</sub>',
        xaxis=dict(title='Date', tickangle=-45),
        yaxis=dict(
            title='Daily Active Users (DAU)',
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
        height=600,
        template='plotly_white',
        barmode='stack'
    )

    return fig, merged


def calculate_correlation(merged_df):
    """Calculate correlation between Reddit activity and DAU"""
    print("\nCalculating correlations...")

    # Calculate total Reddit activity
    merged_df['total_reddit_activity'] = merged_df['post_count'] + merged_df['comment_count']

    # Calculate correlations
    post_corr = merged_df[['dau', 'post_count']].corr().iloc[0, 1]
    comment_corr = merged_df[['dau', 'comment_count']].corr().iloc[0, 1]
    total_corr = merged_df[['dau', 'total_reddit_activity']].corr().iloc[0, 1]

    print(f"\n📊 Correlation Analysis:")
    print(f"   Posts vs DAU: {post_corr:.3f}")
    print(f"   Comments vs DAU: {comment_corr:.3f}")
    print(f"   Total Activity vs DAU: {total_corr:.3f}")

    return {
        'post_corr': post_corr,
        'comment_corr': comment_corr,
        'total_corr': total_corr
    }


def find_impact_moments(merged_df, reddit_df):
    """Find days with high Reddit activity and their DAU impact"""
    print("\n🔍 High-Impact Reddit Activities:")

    # Filter days with Reddit activity
    active_days = merged_df[merged_df['total_reddit_activity'] > 0].copy()

    if active_days.empty:
        print("   No Reddit activity found in the DAU period")
        return

    # Sort by total score
    active_days = active_days.sort_values('total_score', ascending=False)

    # Show top 5 impactful days
    for idx, row in active_days.head(5).iterrows():
        date = row['date']
        dau = int(row['dau'])
        posts = int(row['post_count'])
        comments = int(row['comment_count'])
        score = int(row['total_score'])

        print(f"\n   📅 {date}:")
        print(f"      DAU: {dau:,}")
        print(f"      Reddit: {posts} posts, {comments} comments (score: {score})")

        # Find the actual posts from that day
        day_posts = reddit_df[reddit_df['created_date'] == date]
        for _, post in day_posts.head(2).iterrows():
            print(f"      - {post['type']}: {post['title'][:60]}... (+{post['score']})")


def main():
    print("=" * 60)
    print("Reddit Impact Analysis on PostHog DAU")
    print("=" * 60)

    try:
        # Fetch Reddit data
        reddit_df = fetch_reddit_activity(REDDIT_USERNAME, limit=100)

        # Fetch PostHog DAU data
        posthog_df = fetch_posthog_dau(days=90)

        # Create visualization
        fig, merged_df = create_overlay_visualization(posthog_df, reddit_df)

        # Calculate correlations
        correlations = calculate_correlation(merged_df)

        # Find impact moments
        find_impact_moments(merged_df, reddit_df)

        # Save visualization
        output_file = "reddit_impact_analysis.html"
        fig.write_html(output_file)
        print(f"\n✅ Visualization saved to: {output_file}")

        # Save data
        merged_df.to_csv("reddit_impact_data.csv", index=False)
        print(f"✅ Data saved to: reddit_impact_data.csv")

        print("\n" + "=" * 60)
        print("Analysis Complete!")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise


if __name__ == "__main__":
    main()
