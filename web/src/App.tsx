import { Routes, Route } from 'react-router'
import AppLayout from '@/components/layout/AppLayout'
import OnboardingPage from '@/pages/Onboarding'
import DashboardPage from '@/pages/Dashboard'
import JobsPage from '@/pages/Jobs'
import JobDetailPage from '@/pages/JobDetail'
import CompaniesPage from '@/pages/Companies'
import CompanyCandidatesPage from '@/pages/CompanyCandidates'
import CompanyDetailPage from '@/pages/CompanyDetail'
import RunsPage from '@/pages/Runs'
import RunDetailPage from '@/pages/RunDetail'
import ReportsPage from '@/pages/Reports'
import ReportDetailPage from '@/pages/ReportDetail'
import ProfilePage from '@/pages/Profile'
import SettingsPage from '@/pages/Settings'
import NotificationsPage from '@/pages/Notifications'
import SearchResultsPage from '@/pages/SearchResults'
import ApplicationsPage from '@/pages/Applications'
import ApplicationDetailPage from '@/pages/ApplicationDetail'
import NotFoundPage from '@/pages/NotFound'

export default function App() {
  return (
    <Routes>
      <Route path="/onboarding" element={<OnboardingPage />} />
      <Route element={<AppLayout />}>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/jobs" element={<JobsPage />} />
        <Route path="/jobs/:id" element={<JobDetailPage />} />
        <Route path="/applications" element={<ApplicationsPage />} />
        <Route path="/applications/:id" element={<ApplicationDetailPage />} />
        <Route path="/companies" element={<CompaniesPage />} />
        <Route path="/company-candidates" element={<CompanyCandidatesPage />} />
        <Route path="/companies/:id" element={<CompanyDetailPage />} />
        <Route path="/runs" element={<RunsPage />} />
        <Route path="/runs/:id" element={<RunDetailPage />} />
        <Route path="/reports" element={<ReportsPage />} />
        <Route path="/reports/:date" element={<ReportDetailPage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/notifications" element={<NotificationsPage />} />
        <Route path="/search" element={<SearchResultsPage />} />
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}
