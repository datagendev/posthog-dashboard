# PostHog DAU Dashboard

A Streamlit dashboard to visualize Daily Active Users (DAU) from PostHog, with breakdowns by traffic source, geography, and hourly patterns.

## Features

- **DAU Summary**: Overview of daily active users with trend analysis
- **Traffic Sources**: Breakdown of users by traffic source
- **Geographic Distribution**: Users by country
- **Hourly Patterns**: Peak activity times (24-hour view)
- **Automated Summary**: Generated insights about DAU metrics
- **User Filtering**: Automatically excludes @datagen.dev users

## Setup

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment**:
   Create a `.env` file with your DataGen API key:
   ```bash
   cp .env.example .env
   # Edit .env and add your DATAGEN_API_KEY
   ```

3. **Run the dashboard**:
   ```bash
   streamlit run app.py
   ```

4. **Access the dashboard**:
   Open your browser to `http://localhost:8501`

## Data Source

This dashboard uses PostHog data via DataGen MCP tools:
- Tool: `mcp_Posthog_query_run`
- Event: `$pageview` events
- Math: Daily Active Users (DAU)
- Filters: Excludes users with @datagen.dev email addresses

## Usage

- Click the **Refresh** button to fetch the latest data
- Data is cached for 5 minutes to improve performance
- All visualizations automatically exclude @datagen.dev users
