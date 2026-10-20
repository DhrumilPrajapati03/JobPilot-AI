// Route-level code splitting: pages load on first use. Shared by the router and the chat workspace panel.
import { lazy } from 'react';

export const Chat = lazy(() => import('./Chat'));
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
export const Landing = lazy(() => import('./Landing'));
