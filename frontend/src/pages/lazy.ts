// Route-level code splitting: pages load on first use. Shared by the router and the chat workspace panel.
import { lazy } from 'react';

export const Chat = lazy(() => import('./Chat'));
export const Overview = lazy(() => import('./Overview'));
export const Applications = lazy(() => import('./Applications'));
export const JobFeed = lazy(() => import('./JobFeed'));
export const Network = lazy(() => import('./Network'));
export const ApplyQueue = lazy(() => import('./ApplyQueue'));
export const NewApplication = lazy(() => import('./NewApplication'));
export const ApplicationDetail = lazy(() => import('./ApplicationDetail'));
export const Profile = lazy(() => import('./Profile'));
export const Templates = lazy(() => import('./Templates'));
export const Analytics = lazy(() => import('./Analytics'));
export const Settings = lazy(() => import('./Settings'));
export const Login = lazy(() => import('./Login'));

// JobDots command center (Day 9)
export const Command = lazy(() => import('./jobdots/Command'));
export const Cases = lazy(() => import('./jobdots/Cases'));
export const CaseThread = lazy(() => import('./jobdots/CaseThread'));
export const Approvals = lazy(() => import('./jobdots/Approvals'));
export const Contacts = lazy(() => import('./jobdots/Contacts'));
export const AnswerBank = lazy(() => import('./jobdots/AnswerBank'));
export const Dashboard = lazy(() => import('./jobdots/Dashboard'));
export const ExpertPage = lazy(() => import('./jobdots/ExpertPage'));
export const NewExpert = lazy(() => import('./jobdots/CustomExpert').then(m => ({ default: m.NewExpert })));
