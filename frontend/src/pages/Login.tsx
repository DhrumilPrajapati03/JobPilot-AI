// ============================================================
// JobPilot AI — Login Page
// ============================================================

import { LoginForm } from '../components/auth/LoginForm';
import { Rocket } from 'lucide-react';

export default function Login() {
  return (
    <div className="login-page">
      {/* Left Panel — Brand */}
      <div className="login-brand-panel">
        <div className="login-brand-content">
          <div className="login-logo">
            <div className="login-logo-icon">
              <Rocket size={32} />
            </div>
            <h1>JobPilot AI</h1>
          </div>
          <p className="login-tagline">
            Your autonomous career intelligence system.
            <br />
            Tailored resumes, personalised outreach, zero friction.
          </p>
          <div className="login-features">
            <div className="login-feature-item">
              <div className="login-feature-dot" />
              <span>AI-tailored resumes in seconds</span>
            </div>
            <div className="login-feature-item">
              <div className="login-feature-dot" />
              <span>Personalised cold emails & LinkedIn DMs</span>
            </div>
            <div className="login-feature-item">
              <div className="login-feature-dot" />
              <span>Full application pipeline tracking</span>
            </div>
          </div>
        </div>
      </div>

      {/* Right Panel — Form */}
      <div className="login-form-panel">
        <div className="login-form-container">
          <h2>Welcome back</h2>
          <p className="login-form-subtitle">
            Enter your email to receive a magic login link.
          </p>
          <LoginForm />
        </div>
      </div>
    </div>
  );
}
