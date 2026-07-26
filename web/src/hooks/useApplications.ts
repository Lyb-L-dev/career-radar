import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as applicationsApi from '@/services/applications'
import type { ApplicationTask } from '@/types'

const ACTIVE_APPLICATION_STATUSES = new Set<ApplicationTask['status']>([
  'evaluating',
  'drafting',
  'factual_review',
  'recruiter_review',
  'revising',
  'rendering',
  'verifying',
])

function shouldPoll(task?: ApplicationTask): boolean {
  return Boolean(task?.isRunning || (task && ACTIVE_APPLICATION_STATUSES.has(task.status)))
}

export function useApplicationProfileStatus() {
  return useQuery({
    queryKey: ['application-profile-status'],
    queryFn: applicationsApi.getApplicationProfileStatus,
  })
}

export function useApplications() {
  return useQuery({
    queryKey: ['applications'],
    queryFn: applicationsApi.getApplications,
    refetchInterval: (query) =>
      query.state.data?.some((task) => shouldPoll(task)) ? 1_500 : false,
  })
}

export function useApplication(id: string) {
  return useQuery({
    queryKey: ['application', id],
    queryFn: () => applicationsApi.getApplication(id),
    enabled: Boolean(id),
    refetchInterval: (query) => (shouldPoll(query.state.data) ? 1_500 : false),
  })
}

export function useJobApplications(jobId: string) {
  return useQuery({
    queryKey: ['job-applications', jobId],
    queryFn: () => applicationsApi.getJobApplications(jobId),
    enabled: Boolean(jobId),
    refetchInterval: (query) =>
      query.state.data?.some((task) => shouldPoll(task)) ? 1_500 : false,
  })
}

function useInvalidateApplications() {
  const queryClient = useQueryClient()
  return (jobId?: string, applicationId?: string) => {
    queryClient.invalidateQueries({ queryKey: ['applications'] })
    if (jobId) queryClient.invalidateQueries({ queryKey: ['job-applications', jobId] })
    if (applicationId) queryClient.invalidateQueries({ queryKey: ['application', applicationId] })
  }
}

export function useCreateApplication() {
  const invalidate = useInvalidateApplications()
  return useMutation({
    mutationFn: applicationsApi.createApplication,
    onSuccess: (result, jobId) => invalidate(jobId, result.applicationId),
  })
}

function useApplicationAction(
  action: (id: string) => Promise<{ ok: boolean; applicationId: string }>,
) {
  const invalidate = useInvalidateApplications()
  return useMutation({
    mutationFn: action,
    onSuccess: (result) => invalidate(undefined, result.applicationId),
  })
}

export function useApproveApplication() {
  return useApplicationAction(applicationsApi.approveApplication)
}

export function useResumeApplication() {
  return useApplicationAction(applicationsApi.resumeApplication)
}

export function useRenderApplication() {
  return useApplicationAction(applicationsApi.renderApplication)
}

export function useRejectApplication() {
  return useApplicationAction(applicationsApi.rejectApplication)
}
