// ============================================================
// JobPilot AI — Settings Page
// ============================================================

import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Separator } from '../components/ui/separator';
import {
  Key,
  Mail,
  Bell,
  Shield,
  Globe,
  Palette,
} from 'lucide-react';

export default function Settings() {
  return (
    <div className="page-settings">
      <div className="settings-header">
        <h2>Settings</h2>
        <p className="text-muted">
          Configure your API keys, email integration, and application preferences.
        </p>
      </div>

      <div className="settings-grid">
        {/* API Keys */}
        <Card className="settings-card">
          <CardHeader>
            <CardTitle className="settings-card-title">
              <Key size={18} />
              API Keys
            </CardTitle>
          </CardHeader>
          <CardContent className="settings-card-content">
            <div className="settings-field">
              <Label>Anthropic API Key</Label>
              <Input type="password" placeholder="sk-ant-..." />
            </div>
            <div className="settings-field">
              <Label>OpenAI API Key</Label>
              <Input type="password" placeholder="sk-..." />
            </div>
            <div className="settings-field">
              <Label>Hunter.io API Key</Label>
              <Input type="password" placeholder="..." />
            </div>
            <Button className="settings-save-btn">Save API Keys</Button>
          </CardContent>
        </Card>

        {/* Email Configuration */}
        <Card className="settings-card">
          <CardHeader>
            <CardTitle className="settings-card-title">
              <Mail size={18} />
              Email Integration
            </CardTitle>
          </CardHeader>
          <CardContent className="settings-card-content">
            <p className="text-muted">
              Connect your Gmail or configure Resend API for sending cold emails.
            </p>
            <Button variant="outline">Connect Gmail</Button>
          </CardContent>
        </Card>

        {/* Notifications */}
        <Card className="settings-card">
          <CardHeader>
            <CardTitle className="settings-card-title">
              <Bell size={18} />
              Notifications
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-muted">
              Configure follow-up reminders and notification preferences.
            </p>
          </CardContent>
        </Card>

        {/* Security */}
        <Card className="settings-card">
          <CardHeader>
            <CardTitle className="settings-card-title">
              <Shield size={18} />
              Security
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-muted">
              Manage your authentication settings and data privacy preferences.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
