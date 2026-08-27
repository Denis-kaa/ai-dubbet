import axios from 'axios'
import { getApiUrl } from './runtime-config'

const API_URL = getApiUrl()

export interface AdminStats {
  users: { total: number; verified: number; last_7d: number; last_24h: number }
  jobs: {
    total: number
    with_registered_user: number
    anonymous: number
    by_status: Record<string, number>
    last_7d: number
    last_24h: number
  }
  payments: { approved_count: number; revenue_total_uzs: number }
  recent_users: { email: string; created_at: string | null; is_verified: boolean }[]
  recent_jobs: {
    id: string
    created_at: string | null
    video_title: string | null
    youtube_url: string
    user_email: string | null
    status: string
    error_code: string | null
    error_message: string | null
  }[]
  trends: {
    daily: { date: string; users: number; jobs: number }[]
    monthly: { date: string; users: number; jobs: number }[]
    yearly: { date: string; users: number; jobs: number }[]
    today: { users: number; jobs: number }
    yesterday: { users: number; jobs: number }
    this_month: { users: number; jobs: number }
    last_month: { users: number; jobs: number }
  }
}

export async function apiAdminStats(token: string): Promise<AdminStats> {
  const res = await axios.get(`${API_URL}/admin/stats`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  return res.data
}


export interface BlockedUsersReport {
  total_blocked_accounts: number
  total_violations: number
  users: {
    user_id: string
    name: string | null
    email: string | null
    phone: string | null
    violation_count: number
    last_violation_at: string | null
  }[]
  recent_violations: {
    id: string
    user_id: string
    video_title: string | null
    stage: string
    category: string
    reason: string | null
    created_at: string
  }[]
}

export async function apiAdminBlockedUsers(token: string): Promise<BlockedUsersReport> {
  const res = await axios.get(`${API_URL}/admin/blocked-users`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  return res.data
}

export interface RefundsNeededReport {
  total_amount: number
  payments: {
    payment_id: string
    user_name: string | null
    user_email: string | null
    user_phone: string | null
    amount: number
    video_title: string | null
    error_message: string | null
    click_transaction_id: string | null
    paid_at: string | null
  }[]
}

export async function apiAdminRefundsNeeded(token: string): Promise<RefundsNeededReport> {
  const res = await axios.get(`${API_URL}/admin/refunds-needed`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  return res.data
}
