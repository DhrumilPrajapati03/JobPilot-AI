// ============================================================
// JobPilot AI — Application Detail Page
// ============================================================

import { useParams } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Separator } from '../components/ui/separator';
import {
  FileText,
  Mail,
  MessageSquare,
  Clock,
  Building2,
  Briefcase,
} from 'lucide-react';

export default function ApplicationDetail() {
  const { id } = useParams<{ id: string }>();

  return (
    <div className="page-application-detail">
      {/* Application Header */}
      <Card className="app-detail-header-card">
        <CardContent className="app-detail-header-content">
          <div className="app-detail-company">
            <div className="app-detail-company-logo">
              <Building2 size={24} />
            </div>
            <div>
              <h2 className="app-detail-role">Software Engineer</h2>
              <p className="app-detail-company-name">Example Company</p>
            </div>
          </div>
          <div className="app-detail-meta">
            <Badge>Saved</Badge>
            <span className="app-detail-id">ID: {id}</span>
          </div>
        </CardContent>
      </Card>

      {/* Tabs */}
      <Tabs defaultValue="resume" className="app-detail-tabs">
        <TabsList>
          <TabsTrigger value="resume">
            <FileText size={16} />
            Resume
          </TabsTrigger>
          <TabsTrigger value="email">
            <Mail size={16} />
            Cold Email
          </TabsTrigger>
          <TabsTrigger value="dm">
            <MessageSquare size={16} />
            LinkedIn DM
          </TabsTrigger>
          <TabsTrigger value="timeline">
            <Clock size={16} />
            Timeline
          </TabsTrigger>
        </TabsList>

        <TabsContent value="resume">
          <Card>
            <CardHeader>
              <CardTitle>Tailored Resume</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-muted">
                No tailored resume generated yet. Run the agent pipeline to generate materials.
              </p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="email">
          <Card>
            <CardHeader>
              <CardTitle>Cold Email Draft</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-muted">
                No email draft generated yet.
              </p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="dm">
          <Card>
            <CardHeader>
              <CardTitle>LinkedIn DM Draft</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-muted">
                No DM draft generated yet.
              </p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="timeline">
          <Card>
            <CardHeader>
              <CardTitle>Application Timeline</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-muted">
                Timeline will appear here as you progress through the application pipeline.
              </p>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
