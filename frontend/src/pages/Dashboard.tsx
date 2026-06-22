// ============================================================
// JobPilot AI — Dashboard Page
// ============================================================

import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import {
  FileText,
  Send,
  TrendingUp,
  Clock,
  PlusCircle,
  ArrowRight,
  Zap,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';

const STATS = [
  { label: 'Total Applications', value: '0', icon: FileText, trend: null },
  { label: 'Emails Sent', value: '0', icon: Send, trend: null },
  { label: 'Response Rate', value: '—', icon: TrendingUp, trend: null },
  { label: 'Pending Follow-ups', value: '0', icon: Clock, trend: null },
];

export default function Dashboard() {
  const navigate = useNavigate();

  return (
    <div className="page-dashboard">
      {/* Welcome Section */}
      <div className="dashboard-welcome">
        <div>
          <h2 className="dashboard-welcome-title">Welcome back, Dhrumil 👋</h2>
          <p className="dashboard-welcome-subtitle">
            Here's your job application overview. Let's land that next role.
          </p>
        </div>
        <Button
          onClick={() => navigate('/applications/new')}
          className="dashboard-cta"
        >
          <PlusCircle size={18} />
          New Application
        </Button>
      </div>

      {/* Stats Grid */}
      <div className="dashboard-stats-grid">
        {STATS.map((stat) => {
          const Icon = stat.icon;
          return (
            <Card key={stat.label} className="dashboard-stat-card">
              <CardHeader className="dashboard-stat-header">
                <div className="dashboard-stat-icon-wrapper">
                  <Icon size={20} />
                </div>
                <CardTitle className="dashboard-stat-label">{stat.label}</CardTitle>
              </CardHeader>
              <CardContent className="dashboard-stat-content">
                <span className="dashboard-stat-value">{stat.value}</span>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Quick Actions & Recent Activity */}
      <div className="dashboard-grid-2">
        {/* Quick Actions */}
        <Card className="dashboard-card">
          <CardHeader>
            <CardTitle className="dashboard-card-title">
              <Zap size={18} />
              Quick Actions
            </CardTitle>
          </CardHeader>
          <CardContent className="dashboard-quick-actions">
            <button
              className="dashboard-action-item"
              onClick={() => navigate('/applications/new')}
            >
              <PlusCircle size={18} />
              <span>Apply to a new job</span>
              <ArrowRight size={16} className="dashboard-action-arrow" />
            </button>
            <button
              className="dashboard-action-item"
              onClick={() => navigate('/profile')}
            >
              <FileText size={18} />
              <span>Update your resume</span>
              <ArrowRight size={16} className="dashboard-action-arrow" />
            </button>
            <button
              className="dashboard-action-item"
              onClick={() => navigate('/templates')}
            >
              <Send size={18} />
              <span>Manage email templates</span>
              <ArrowRight size={16} className="dashboard-action-arrow" />
            </button>
          </CardContent>
        </Card>

        {/* Recent Activity */}
        <Card className="dashboard-card">
          <CardHeader>
            <CardTitle className="dashboard-card-title">
              <Clock size={18} />
              Recent Activity
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="dashboard-empty-state">
              <p>No recent activity yet.</p>
              <p className="text-muted">
                Start by creating your first application to see activity here.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
