// ============================================================
// JobPilot AI — Analytics Page
// ============================================================

import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import {
  BarChart3,
  TrendingUp,
  Target,
  Percent,
  ArrowUpRight,
} from 'lucide-react';

const ANALYTICS_STATS = [
  { label: 'Total Applications', value: '0', icon: BarChart3, change: null },
  { label: 'Response Rate', value: '—', icon: TrendingUp, change: null },
  { label: 'Interview Rate', value: '—', icon: Target, change: null },
  { label: 'Avg ATS Score', value: '—', icon: Percent, change: null },
];

export default function Analytics() {
  return (
    <div className="page-analytics">
      <div className="analytics-header">
        <h2>Analytics</h2>
        <p className="text-muted">
          Track your job application performance, response rates, and weekly trends.
        </p>
      </div>

      {/* Stats Row */}
      <div className="analytics-stats-grid">
        {ANALYTICS_STATS.map((stat) => {
          const Icon = stat.icon;
          return (
            <Card key={stat.label} className="analytics-stat-card">
              <CardHeader className="analytics-stat-header">
                <div className="analytics-stat-icon-wrapper">
                  <Icon size={20} />
                </div>
                <CardTitle className="analytics-stat-label">{stat.label}</CardTitle>
              </CardHeader>
              <CardContent className="analytics-stat-content">
                <span className="analytics-stat-value">{stat.value}</span>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Charts Placeholder */}
      <div className="analytics-charts-grid">
        <Card className="analytics-chart-card">
          <CardHeader>
            <CardTitle>Application Funnel</CardTitle>
          </CardHeader>
          <CardContent className="analytics-chart-placeholder">
            <BarChart3 size={48} className="analytics-placeholder-icon" />
            <p className="text-muted">
              Funnel chart will appear once you have application data.
            </p>
          </CardContent>
        </Card>

        <Card className="analytics-chart-card">
          <CardHeader>
            <CardTitle>Weekly Trends</CardTitle>
          </CardHeader>
          <CardContent className="analytics-chart-placeholder">
            <TrendingUp size={48} className="analytics-placeholder-icon" />
            <p className="text-muted">
              Weekly application trends will appear here.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
