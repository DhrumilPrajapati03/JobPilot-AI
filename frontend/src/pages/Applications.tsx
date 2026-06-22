// ============================================================
// JobPilot AI — Applications Tracker Page
// ============================================================

import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { PlusCircle, LayoutGrid, Table, Search, Filter } from 'lucide-react';
import { Input } from '../components/ui/input';
import { useNavigate } from 'react-router-dom';
import { useUIStore } from '../stores/ui-store';
import { KANBAN_COLUMNS, APPLICATION_STATUS_CONFIG } from '../lib/constants';

export default function Applications() {
  const navigate = useNavigate();
  const { trackerViewMode, setTrackerViewMode } = useUIStore();

  return (
    <div className="page-applications">
      {/* Toolbar */}
      <div className="applications-toolbar">
        <div className="applications-toolbar-left">
          <div className="applications-search">
            <Search size={16} className="applications-search-icon" />
            <Input placeholder="Search applications..." className="applications-search-input" />
          </div>
          <Button variant="outline" size="sm">
            <Filter size={16} />
            Filters
          </Button>
        </div>
        <div className="applications-toolbar-right">
          <div className="applications-view-toggle">
            <Button
              variant={trackerViewMode === 'kanban' ? 'default' : 'ghost'}
              size="sm"
              onClick={() => setTrackerViewMode('kanban')}
            >
              <LayoutGrid size={16} />
            </Button>
            <Button
              variant={trackerViewMode === 'table' ? 'default' : 'ghost'}
              size="sm"
              onClick={() => setTrackerViewMode('table')}
            >
              <Table size={16} />
            </Button>
          </div>
          <Button onClick={() => navigate('/applications/new')}>
            <PlusCircle size={16} />
            New Application
          </Button>
        </div>
      </div>

      {/* Kanban View */}
      {trackerViewMode === 'kanban' && (
        <div className="kanban-board">
          {KANBAN_COLUMNS.map((status) => {
            const config = APPLICATION_STATUS_CONFIG[status];
            return (
              <div key={status} className="kanban-column">
                <div className="kanban-column-header">
                  <Badge
                    style={{ backgroundColor: config.bgColor, color: config.color }}
                    className="kanban-column-badge"
                  >
                    {config.label}
                  </Badge>
                  <span className="kanban-column-count">0</span>
                </div>
                <div className="kanban-column-body">
                  <div className="kanban-empty">
                    <p>No applications</p>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Table View */}
      {trackerViewMode === 'table' && (
        <Card>
          <CardContent className="applications-table-empty">
            <p>No applications yet. Start by creating your first application.</p>
            <Button onClick={() => navigate('/applications/new')} variant="outline">
              <PlusCircle size={16} />
              Create First Application
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
