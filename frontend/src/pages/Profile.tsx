// ============================================================
// JobPilot AI — Identity Vault (Profile) Page
// ============================================================

import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Separator } from '../components/ui/separator';
import {
  User,
  Briefcase,
  GraduationCap,
  Code2,
  FolderKanban,
  Award,
  Upload,
  Edit3,
} from 'lucide-react';

export default function Profile() {
  return (
    <div className="page-profile">
      <div className="profile-header">
        <div>
          <h2>Identity Vault</h2>
          <p className="text-muted">
            Your central professional profile. This data powers all AI-tailored materials.
          </p>
        </div>
        <div className="profile-header-actions">
          <Button variant="outline">
            <Upload size={16} />
            Import Resume
          </Button>
          <Button>
            <Edit3 size={16} />
            Edit Profile
          </Button>
        </div>
      </div>

      <div className="profile-grid">
        {/* Personal Info */}
        <Card className="profile-card">
          <CardHeader>
            <CardTitle className="profile-card-title">
              <User size={18} />
              Personal Information
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-muted">
              Add your name, headline, location, and work preferences.
            </p>
          </CardContent>
        </Card>

        {/* Experience */}
        <Card className="profile-card">
          <CardHeader>
            <CardTitle className="profile-card-title">
              <Briefcase size={18} />
              Experience
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-muted">
              Add your work experience entries with bullet points.
            </p>
          </CardContent>
        </Card>

        {/* Education */}
        <Card className="profile-card">
          <CardHeader>
            <CardTitle className="profile-card-title">
              <GraduationCap size={18} />
              Education
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-muted">
              Add your educational background.
            </p>
          </CardContent>
        </Card>

        {/* Skills */}
        <Card className="profile-card">
          <CardHeader>
            <CardTitle className="profile-card-title">
              <Code2 size={18} />
              Skills
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-muted">
              Add your primary and secondary skills for ATS matching.
            </p>
          </CardContent>
        </Card>

        {/* Projects */}
        <Card className="profile-card">
          <CardHeader>
            <CardTitle className="profile-card-title">
              <FolderKanban size={18} />
              Projects
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-muted">
              Add notable projects with tech stacks used.
            </p>
          </CardContent>
        </Card>

        {/* Certifications */}
        <Card className="profile-card">
          <CardHeader>
            <CardTitle className="profile-card-title">
              <Award size={18} />
              Certifications
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-muted">
              Add your professional certifications.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
