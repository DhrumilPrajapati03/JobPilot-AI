// ============================================================
// JobPilot AI — Templates Library Page
// ============================================================

import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Mail, MessageSquare, FileText, Plus } from 'lucide-react';

export default function Templates() {
  return (
    <div className="page-templates">
      <div className="templates-header">
        <div>
          <h2>Templates Library</h2>
          <p className="text-muted">
            Manage your email, DM, and cover letter templates. These are used by the AI agents as base templates.
          </p>
        </div>
        <Button>
          <Plus size={16} />
          New Template
        </Button>
      </div>

      <Tabs defaultValue="email" className="templates-tabs">
        <TabsList>
          <TabsTrigger value="email">
            <Mail size={16} />
            Cold Emails
          </TabsTrigger>
          <TabsTrigger value="dm">
            <MessageSquare size={16} />
            LinkedIn DMs
          </TabsTrigger>
          <TabsTrigger value="cover">
            <FileText size={16} />
            Cover Letters
          </TabsTrigger>
        </TabsList>

        <TabsContent value="email">
          <Card>
            <CardContent className="templates-empty">
              <Mail size={40} className="templates-empty-icon" />
              <h3>No email templates yet</h3>
              <p className="text-muted">
                Create your first cold email template to get started.
              </p>
              <Button variant="outline">
                <Plus size={16} />
                Create Email Template
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="dm">
          <Card>
            <CardContent className="templates-empty">
              <MessageSquare size={40} className="templates-empty-icon" />
              <h3>No DM templates yet</h3>
              <p className="text-muted">
                Create your first LinkedIn DM template.
              </p>
              <Button variant="outline">
                <Plus size={16} />
                Create DM Template
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="cover">
          <Card>
            <CardContent className="templates-empty">
              <FileText size={40} className="templates-empty-icon" />
              <h3>No cover letter templates yet</h3>
              <p className="text-muted">
                Create your first cover letter template.
              </p>
              <Button variant="outline">
                <Plus size={16} />
                Create Cover Letter Template
              </Button>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
