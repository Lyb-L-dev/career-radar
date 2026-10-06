import { lazy, Suspense } from 'react'
import { Navigate, Routes, Route } from 'react-router'
import AppLayout from '@/components/layout/AppLayout'
import { PageSkeleton } from '@/components/common/StateViews'

const OnboardingPage = lazy(() => import('@/pages/Onboarding'))
const DashboardPage = lazy(() => import('@/pages/Dashboard'))
const GrowthPage = lazy(() => import('@/pages/Growth'))
const JobHubPage = lazy(() => import('@/pages/JobHub'))
const JobDetailPage = lazy(() => import('@/pages/JobDetail'))
const CompaniesPage = lazy(() => import('@/pages/Companies'))
const CompanyCandidatesPage = lazy(() => import('@/pages/CompanyCandidates'))
const CompanyDetailPage = lazy(() => import('@/pages/CompanyDetail'))
const RunsPage = lazy(() => import('@/pages/Runs'))
const RunDetailPage = lazy(() => import('@/pages/RunDetail'))
const ReportsPage = lazy(() => import('@/pages/Reports'))
const ReportDetailPage = lazy(() => import('@/pages/ReportDetail'))
const ProfilePage = lazy(() => import('@/pages/Profile'))
const SettingsPage = lazy(() => import('@/pages/Settings'))
const NotificationsPage = lazy(() => import('@/pages/Notifications'))
const SearchResultsPage = lazy(() => import('@/pages/SearchResults'))
const ApplicationsPage = lazy(() => import('@/pages/Applications'))
const ApplicationDetailPage = lazy(() => import('@/pages/ApplicationDetail'))
const NotFoundPage = lazy(() => import('@/pages/NotFound'))

export default function App() {
  return (
    <Suspense fallback={<div className="p-6"><PageSkeleton /></div>}>
      <Routes>
        <Route path="/onboarding" element={<OnboardingPage />} />
        <Route element={<AppLayout />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/growth" element={<GrowthPage />} />
          <Route path="/jobs" element={<JobHubPage />} />
          <Route path="/platform-leads" element={<Navigate to="/jobs?source=boss" replace />} />
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
    </Suspense>
  )
}
