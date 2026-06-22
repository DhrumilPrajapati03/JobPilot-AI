"""Analytics and reporting endpoints.

Provides application funnel metrics, response rates,
and weekly activity summaries.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/summary")
async def get_analytics_summary():
    """Get application statistics and funnel metrics.

    Returns aggregated data: total applications, response rate,
    interview rate, offer rate, and weekly trends.
    """
    # TODO: Compute analytics from Supabase data
    return {
        "total_applications": 0,
        "status_breakdown": {
            "saved": 0,
            "applied": 0,
            "interviewing": 0,
            "offer": 0,
            "rejected": 0,
            "archived": 0,
        },
        "response_rate": 0.0,
        "interview_rate": 0.0,
        "weekly_applications": [],
        "avg_time_per_application_mins": 0,
    }
