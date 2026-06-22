// ============================================================
// JobPilot AI — New Application Page
// ============================================================

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Link2, FileText, Zap, Loader2 } from 'lucide-react';

export default function NewApplication() {
  const [jdUrl, setJdUrl] = useState('');
  const [jdText, setJdText] = useState('');
  const [activeTab, setActiveTab] = useState('url');

  return (
    <div className="page-new-application">
      <div className="new-app-header">
        <h2>Create a New Application</h2>
        <p className="text-muted">
          Paste a job URL or the job description text, and let the AI agents do the rest.
        </p>
      </div>

      <Card className="new-app-card">
        <CardHeader>
          <CardTitle className="new-app-card-title">
            <FileText size={20} />
            Job Description Input
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList className="new-app-tabs">
              <TabsTrigger value="url">
                <Link2 size={16} />
                Paste URL
              </TabsTrigger>
              <TabsTrigger value="text">
                <FileText size={16} />
                Paste JD Text
              </TabsTrigger>
            </TabsList>

            <TabsContent value="url" className="new-app-tab-content">
              <Label htmlFor="jd-url">Job Listing URL</Label>
              <Input
                id="jd-url"
                type="url"
                placeholder="https://linkedin.com/jobs/view/..."
                value={jdUrl}
                onChange={(e) => setJdUrl(e.target.value)}
              />
              <p className="new-app-hint">
                Supports LinkedIn, Indeed, Glassdoor, Naukri, and most job boards.
              </p>
            </TabsContent>

            <TabsContent value="text" className="new-app-tab-content">
              <Label htmlFor="jd-text">Job Description</Label>
              <textarea
                id="jd-text"
                className="new-app-textarea"
                placeholder="Paste the full job description here..."
                value={jdText}
                onChange={(e) => setJdText(e.target.value)}
                rows={12}
              />
              <p className="new-app-char-count">
                {jdText.length} characters
              </p>
            </TabsContent>
          </Tabs>

          <Button
            className="new-app-submit"
            disabled={activeTab === 'url' ? !jdUrl.trim() : !jdText.trim()}
          >
            <Zap size={18} />
            Analyse Job & Generate Materials
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
