import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useProfile, useUpdateProfile, useResume, useUpdateResume } from '../hooks/use-profile';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Separator } from '../components/ui/separator';
import { User, Briefcase, Code2, FolderKanban, Plus, Trash2, Save, Loader2 } from 'lucide-react';
import { PreferencesPanel } from '../components/profile/PreferencesPanel';
import { AnswerBankPanel } from '../components/profile/AnswerBankPanel';

export default function Profile() {
  // 1. Fetch data from backend using our custom React Query hooks
  const { data: profile, isLoading: isProfileLoading } = useProfile();
  const { data: resume, isLoading: isResumeLoading } = useResume();

  const [searchParams] = useSearchParams();
  const initialTab = searchParams.get('tab') || 'personal';
  const updateProfileMutation = useUpdateProfile();
  const updateResumeMutation = useUpdateResume();

  // 2. Local State for Forms (initialized from queries once loaded)
  const [profileForm, setProfileForm] = useState({
    name: '',
    headline: '',
    location: '',
    salary_range: ''
  });

  const [experience, setExperience] = useState<any[]>([]);
  const [projects, setProjects] = useState<any[]>([]);
  const [education, setEducation] = useState<any[]>([]);
  const [skills, setSkills] = useState({ primary: [] as string[], secondary: [] as string[] });
  
  const [skillInput, setSkillInput] = useState('');
  const [secSkillInput, setSecSkillInput] = useState('');

  // 3. Keep local form state in sync when database queries complete loading
  useEffect(() => {
    if (profile) {
      setProfileForm({
        name: profile.name || '',
        headline: profile.headline || '',
        location: profile.location || '',
        salary_range: profile.salary_range || ''
      });
    }
  }, [profile]);

  useEffect(() => {
    if (resume) {
      setExperience(resume.experience || []);
      setProjects(resume.projects || []);
      setEducation(resume.education || []);
      setSkills(resume.skills || { primary: [], secondary: [] });
    }
  }, [resume]);

  // 4. Handle Loading States
  if (isProfileLoading || isResumeLoading) {
    return (
      <div className="flex h-[50vh] items-center justify-center">
        <Loader2 className="animate-spin text-primary" size={32} />
      </div>
    );
  }

  // ==========================================
  // Form Update Handlers
  // ==========================================

  const handleSaveProfile = () => {
    updateProfileMutation.mutate(profileForm);
  };

  const handleSaveResume = () => {
    if (!resume) return;
    const updatedResume = {
      ...resume,
      name: profileForm.name,
      headline: profileForm.headline,
      experience,
      projects,
      education,
      skills
    };
    updateResumeMutation.mutate(updatedResume);
  };

  // --- Experience Handlers ---
  const addExperience = () => {
    setExperience([...experience, { company: '', role: '', duration: '', bullets: [''] }]);
  };

  const removeExperience = (index: number) => {
    setExperience(experience.filter((_, i) => i !== index));
  };

  const updateExperience = (index: number, field: string, value: string) => {
    setExperience(experience.map((exp, i) => i === index ? { ...exp, [field]: value } : exp));
  };

  const addBullet = (expIndex: number) => {
    setExperience(experience.map((exp, i) => {
      if (i !== expIndex) return exp;
      return { ...exp, bullets: [...exp.bullets, ''] };
    }));
  };

  const removeBullet = (expIndex: number, bulletIndex: number) => {
    setExperience(experience.map((exp, i) => {
      if (i !== expIndex) return exp;
      return { ...exp, bullets: exp.bullets.filter((_: any, bIdx: number) => bIdx !== bulletIndex) };
    }));
  };

  const updateBullet = (expIndex: number, bulletIndex: number, value: string) => {
    setExperience(experience.map((exp, i) => {
      if (i !== expIndex) return exp;
      const updatedBullets = exp.bullets.map((b: string, bIdx: number) => bIdx === bulletIndex ? value : b);
      return { ...exp, bullets: updatedBullets };
    }));
  };

  // --- Project Handlers ---
  const addProject = () => {
    setProjects([...projects, { name: '', description: '', tech: [] }]);
  };

  const removeProject = (index: number) => {
    setProjects(projects.filter((_, i) => i !== index));
  };

  const updateProject = (index: number, field: string, value: any) => {
    setProjects(projects.map((proj, i) => i === index ? { ...proj, [field]: value } : proj));
  };

  // --- Skills Tags Handlers ---
  const addSkill = (type: 'primary' | 'secondary', skillName: string) => {
    const trimmed = skillName.trim();
    if (!trimmed) return;
    
    if (type === 'primary') {
      if (!skills.primary.includes(trimmed)) {
        setSkills({ ...skills, primary: [...skills.primary, trimmed] });
      }
      setSkillInput('');
    } else {
      if (!skills.secondary.includes(trimmed)) {
        setSkills({ ...skills, secondary: [...skills.secondary, trimmed] });
      }
      setSecSkillInput('');
    }
  };

  const removeSkill = (type: 'primary' | 'secondary', skillName: string) => {
    if (type === 'primary') {
      setSkills({ ...skills, primary: skills.primary.filter(s => s !== skillName) });
    } else {
      setSkills({ ...skills, secondary: skills.secondary.filter(s => s !== skillName) });
    }
  };

  return (
    <div className="page-profile space-y-6">
      <div className="profile-header flex justify-between items-center">
        <div>
          <h2>Profile & resume</h2>
          <p className="text-muted">Your base resume, job preferences and saved answers — everything the assistant works from.</p>
        </div>
      </div>

      <Tabs defaultValue={initialTab} className="w-full">
        <TabsList className="flex w-full max-w-2xl overflow-x-auto rounded-lg bg-secondary p-1">
          {[
            ['personal', 'Personal'],
            ['experience', 'Experience'],
            ['projects', 'Projects'],
            ['skills', 'Skills'],
            ['preferences', 'Preferences'],
            ['answers', 'Answers'],
          ].map(([value, label]) => (
            <TabsTrigger
              key={value}
              value={value}
              className="flex-1 whitespace-nowrap rounded-md px-3 py-1.5 text-sm text-muted-foreground data-[state=active]:bg-card data-[state=active]:text-foreground data-[state=active]:shadow-sm"
            >
              {label}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="preferences" className="mt-4">
          <PreferencesPanel profile={profile} />
        </TabsContent>
        <TabsContent value="answers" className="mt-4">
          <AnswerBankPanel skills={skills.primary} />
        </TabsContent>

        {/* ------------------- PERSONAL INFO TAB ------------------- */}
        <TabsContent value="personal">
          <Card>
            <CardHeader className="flex flex-row items-center gap-2">
              <User size={20} className="text-primary" />
              <CardTitle>Personal Info & Preferences</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="name">Full Name</Label>
                  <Input 
                    id="name" 
                    value={profileForm.name} 
                    onChange={e => setProfileForm({ ...profileForm, name: e.target.value })} 
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="location">Location</Label>
                  <Input 
                    id="location" 
                    value={profileForm.location} 
                    onChange={e => setProfileForm({ ...profileForm, location: e.target.value })} 
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="headline">Professional Headline</Label>
                <Input 
                  id="headline" 
                  value={profileForm.headline} 
                  onChange={e => setProfileForm({ ...profileForm, headline: e.target.value })} 
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="salary_range">Target Salary Expectations</Label>
                <Input 
                  id="salary_range" 
                  placeholder="e.g. $120,000 - $140,000"
                  value={profileForm.salary_range} 
                  onChange={e => setProfileForm({ ...profileForm, salary_range: e.target.value })} 
                />
              </div>

              <Button 
                onClick={handleSaveProfile} 
                disabled={updateProfileMutation.isPending}
                className="mt-4"
              >
                {updateProfileMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
                Save Personal Details
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ------------------- EXPERIENCE TAB ------------------- */}
        <TabsContent value="experience">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div className="flex items-center gap-2">
                <Briefcase size={20} className="text-primary" />
                <CardTitle>Work Experience</CardTitle>
              </div>
              <Button onClick={addExperience} size="sm" variant="outline">
                <Plus size={16} className="mr-1" /> Add Job
              </Button>
            </CardHeader>
            <CardContent className="space-y-6">
              {experience.map((exp, expIdx) => (
                <div key={expIdx} className="space-y-4 border p-4 rounded-lg relative bg-surface">
                  <button 
                    onClick={() => removeExperience(expIdx)}
                    className="absolute top-2 right-2 text-destructive hover:bg-destructive/10 p-1.5 rounded-md"
                  >
                    <Trash2 size={16} />
                  </button>

                  <div className="grid grid-cols-3 gap-4">
                    <div className="space-y-2">
                      <Label>Company Name</Label>
                      <Input 
                        value={exp.company} 
                        onChange={e => updateExperience(expIdx, 'company', e.target.value)} 
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>Job Role</Label>
                      <Input 
                        value={exp.role} 
                        onChange={e => updateExperience(expIdx, 'role', e.target.value)} 
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>Duration (e.g. 2022-2024)</Label>
                      <Input 
                        value={exp.duration} 
                        onChange={e => updateExperience(expIdx, 'duration', e.target.value)} 
                      />
                    </div>
                  </div>

                  <div className="space-y-2">
                    <div className="flex justify-between items-center">
                      <Label>Description Bullet Points</Label>
                      <Button onClick={() => addBullet(expIdx)} size="sm" variant="ghost" className="h-7 text-xs">
                        <Plus size={12} className="mr-1" /> Add Bullet
                      </Button>
                    </div>
                    <div className="space-y-2">
                      {exp.bullets.map((bullet: string, bIdx: number) => (
                        <div key={bIdx} className="flex gap-2 items-center">
                          <span className="text-muted text-xs">•</span>
                          <Input 
                            value={bullet} 
                            onChange={e => updateBullet(expIdx, bIdx, e.target.value)} 
                          />
                          <button onClick={() => removeBullet(expIdx, bIdx)} className="text-destructive p-1">
                            <Trash2 size={14} />
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              ))}

              <Button onClick={handleSaveResume} disabled={updateResumeMutation.isPending} className="w-full">
                {updateResumeMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
                Save Work History
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ------------------- PROJECTS TAB ------------------- */}
        <TabsContent value="projects">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div className="flex items-center gap-2">
                <FolderKanban size={20} className="text-primary" />
                <CardTitle>Portfolio Projects</CardTitle>
              </div>
              <Button onClick={addProject} size="sm" variant="outline">
                <Plus size={16} className="mr-1" /> Add Project
              </Button>
            </CardHeader>
            <CardContent className="space-y-6">
              {projects.map((proj, projIdx) => (
                <div key={projIdx} className="space-y-4 border p-4 rounded-lg relative bg-surface">
                  <button 
                    onClick={() => removeProject(projIdx)}
                    className="absolute top-2 right-2 text-destructive hover:bg-destructive/10 p-1.5 rounded-md"
                  >
                    <Trash2 size={16} />
                  </button>

                  <div className="space-y-2">
                    <Label>Project Title</Label>
                    <Input 
                      value={proj.name} 
                      onChange={e => updateProject(projIdx, 'name', e.target.value)} 
                    />
                  </div>

                  <div className="space-y-2">
                    <Label>Project Description</Label>
                    <textarea 
                      className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                      value={proj.description} 
                      onChange={e => updateProject(projIdx, 'description', e.target.value)} 
                    />
                  </div>

                  <div className="space-y-2">
                    <Label>Tech Stack (Comma-separated)</Label>
                    <Input 
                      value={proj.tech ? proj.tech.join(', ') : ''} 
                      placeholder="e.g. React, Node.js, SQLite"
                      onChange={e => updateProject(projIdx, 'tech', e.target.value.split(',').map((s: string) => s.trim()))} 
                    />
                  </div>
                </div>
              ))}

              <Button onClick={handleSaveResume} disabled={updateResumeMutation.isPending} className="w-full">
                {updateResumeMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
                Save Projects
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ------------------- SKILLS TAB ------------------- */}
        <TabsContent value="skills">
          <Card>
            <CardHeader className="flex flex-row items-center gap-2">
              <Code2 size={20} className="text-primary" />
              <CardTitle>Technical Skills (ATS Tags)</CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Primary Skills */}
              <div className="space-y-3">
                <Label className="text-sm font-semibold">Primary Core Skills (Languages, Frameworks, Libraries)</Label>
                <div className="flex gap-2">
                  <Input 
                    value={skillInput} 
                    placeholder="Type skill and press Enter or Add"
                    onChange={e => setSkillInput(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        addSkill('primary', skillInput);
                      }
                    }}
                  />
                  <Button onClick={() => addSkill('primary', skillInput)} variant="secondary">Add</Button>
                </div>
                <div className="flex flex-wrap gap-1.5 pt-2">
                  {skills.primary.map(s => (
                    <span key={s} className="inline-flex items-center gap-1 bg-primary/10 text-primary px-2.5 py-1 rounded-full text-xs font-medium">
                      {s}
                      <button onClick={() => removeSkill('primary', s)} className="text-primary/70 hover:text-primary hover:bg-primary/20 rounded-full p-0.5">×</button>
                    </span>
                  ))}
                </div>
              </div>

              <Separator />

              {/* Secondary Skills */}
              <div className="space-y-3">
                <Label className="text-sm font-semibold">Secondary Skills (Cloud Tools, Methodologies, Databases)</Label>
                <div className="flex gap-2">
                  <Input 
                    value={secSkillInput} 
                    placeholder="Type skill and press Enter or Add"
                    onChange={e => setSecSkillInput(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        addSkill('secondary', secSkillInput);
                      }
                    }}
                  />
                  <Button onClick={() => addSkill('secondary', secSkillInput)} variant="secondary">Add</Button>
                </div>
                <div className="flex flex-wrap gap-1.5 pt-2">
                  {skills.secondary.map(s => (
                    <span key={s} className="inline-flex items-center gap-1 bg-accent/10 text-accent px-2.5 py-1 rounded-full text-xs font-medium">
                      {s}
                      <button onClick={() => removeSkill('secondary', s)} className="text-accent/70 hover:text-accent hover:bg-accent/20 rounded-full p-0.5">×</button>
                    </span>
                  ))}
                </div>
              </div>

              <Button onClick={handleSaveResume} disabled={updateResumeMutation.isPending} className="w-full">
                {updateResumeMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
                Save Skills
              </Button>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
