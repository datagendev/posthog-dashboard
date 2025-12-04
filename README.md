# PostHog Analytics Dashboard

A comprehensive Streamlit dashboard to visualize PostHog analytics including page views, DAU metrics, and error tracking.

## Features

### 📄 Page View Analytics
- **Total page views** and **unique users** metrics
- **Page views trend** with 7-day historical data
- **Top pages** by view count
- **Traffic sources** breakdown (referrer analysis)
- **Automatic filtering** of @datagen.dev internal users

### 👥 DAU Analytics
- **Daily Active Users** with day-over-day changes
- **7-day and 30-day averages**
- **30-day trend** visualization
- **Geographic distribution** by country
- **Hourly activity patterns** (24-hour view)

### 🐛 Error Tracker
- **Error summary** metrics (total errors, occurrences, affected users)
- **Detailed error list** with expandable cards
- **Error statistics** visualization
- **First/last seen** timestamps
- **Active vs resolved** status tracking

## Quick Start

### Option 1: Automated Setup (Recommended)

```bash
# Run the setup script
./setup.sh

# Edit .env file with your API key
nano .env
# Add: DATAGEN_API_KEY=your-actual-api-key

# Run the dashboard
./run.sh
```

### Option 2: Manual Setup

1. **Create virtual environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**:
   ```bash
   cp .env.example .env
   nano .env  # Add your DATAGEN_API_KEY
   ```

4. **Run the dashboard**:
   ```bash
   streamlit run app.py
   ```

5. **Access the dashboard**:
   Open your browser to `http://localhost:8501`

## Requirements

- **Python**: 3.13+ (currently using 3.13.3)
- **DataGen API Key**: Required for PostHog MCP access
- **Dependencies**: See `requirements.txt`

## Project Structure

```
posthog-dashboard/
├── app.py                          # Main Streamlit dashboard (tab-based)
├── reddit_impact_analysis.py      # Reddit correlation analysis script
├── requirements.txt                # Python dependencies
├── .env                            # Environment variables (create from .env.example)
├── .env.example                    # Example environment file
├── setup.sh                        # Automated setup script
├── run.sh                          # Quick run script
└── README.md                       # This file
```

## Data Source

This dashboard uses PostHog data via **DataGen MCP tools**:

- **Tool**: `mcp_Posthog_query_run`
- **Events**: `page_viewed`, `$pageview`, `$exception`, `$rageclick`
- **Query Types**:
  - HogQL queries for page view analytics (with custom filtering)
  - TrendsQuery for DAU metrics
  - Error tracking via `mcp_Posthog_list_errors`
- **Filters**: Automatically excludes @datagen.dev internal users

### Internal User Filtering

Page view analytics use HogQL filtering:
```sql
WHERE (person.properties.email NOT LIKE '%@datagen.dev' OR person.properties.email IS NULL)
```

DAU analytics use PostHog's built-in test account filtering:
```json
"filterTestAccounts": true
```

## Usage

### Tab Navigation
- **📄 Page Views**: View page-level analytics and traffic sources
- **👥 DAU Analytics**: Monitor daily active user metrics
- **🐛 Error Tracker**: Track and debug application errors

### Performance Features
- **Lazy loading**: Data loads only when you click on a tab
- **Caching**: All API calls cached for 5 minutes (300 seconds)
- **Refresh button**: Clear cache and reload all data

### Tips
- Use the **Refresh** button in the top-right to get latest data
- Expand data tables under visualizations for detailed views
- Error tracker shows expandable cards with full error details

## Troubleshooting

### Missing API Key
```
Error: DATAGEN_API_KEY not found
Solution: Edit .env file and add your API key
```

### Authentication Error
```
Error: Authentication Error
Solution: Verify your DATAGEN_API_KEY is correct
```

### No Data Showing
```
Issue: Dashboard shows "No data available"
Solution:
1. Check your PostHog project has events
2. Verify MCP server connection
3. Check date ranges in queries
```

### Module Not Found
```
Error: ModuleNotFoundError: No module named 'streamlit'
Solution: Activate virtual environment and reinstall dependencies
  source venv/bin/activate
  pip install -r requirements.txt
```

## Development

To modify the dashboard:

1. **Activate virtual environment**: `source venv/bin/activate`
2. **Make changes** to `app.py`
3. **Test locally**: `streamlit run app.py`
4. **Streamlit auto-reloads** when you save changes

## Railway Deployment

### Prerequisites
- Railway account (sign up at https://railway.app)
- DataGen API key

### Deployment Steps

1. **Fork or push this repository to GitHub**

2. **Create a new project on Railway**:
   - Go to https://railway.app/new
   - Click "Deploy from GitHub repo"
   - Select your repository

3. **Configure environment variables**:
   - In Railway dashboard, go to your service
   - Click on "Variables" tab
   - Add variable: `DATAGEN_API_KEY` with your API key value
   - Railway will automatically use the `PORT` variable

4. **Deploy**:
   - Railway will automatically detect the Python app
   - It will use `Procfile` for the start command
   - Build and deployment happen automatically

5. **Access your dashboard**:
   - Once deployed, Railway provides a public URL
   - Click "Generate Domain" in the Settings tab
   - Access your dashboard at `https://your-app.up.railway.app`

### Railway Configuration Files

- **Procfile**: Defines the web process command
- **railway.toml**: Railway-specific configuration (build, deploy, health checks)
- **runtime.txt**: Specifies Python version (3.13.3)
- **requirements.txt**: Python dependencies

### Post-Deployment

- **Monitor logs**: View real-time logs in Railway dashboard
- **Scaling**: Railway auto-scales based on traffic
- **Custom domain**: Add your own domain in Settings > Domains
- **Environment updates**: Change variables in Railway dashboard

### Troubleshooting Railway Deployment

**Build fails**:
- Check that `requirements.txt` is present
- Verify Python version in `runtime.txt` is supported

**App crashes**:
- Check Railway logs for errors
- Verify `DATAGEN_API_KEY` is set correctly
- Ensure all dependencies are in `requirements.txt`

**Connection errors**:
- Verify your DataGen API key is valid
- Check Railway service logs for authentication errors

## License

Internal tool for DataGen analytics
