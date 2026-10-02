export type StatisticsFilters = {
  content: "all" | "accepted" | "rejected" | "other"
  mode: "all" | "three" | "seven"
  rule: string
  after: string
  before: string
}

export type Option = {
  value: string
  label: string
}

export type MemberOption = {
  member_id: string
  member_name: string
}

export type RunOption = {
  id: string
  started_at?: string
  mode?: string
  rule_name?: string
  attempt_count?: number
}

export type BootstrapData = {
  rules: Option[]
  members: MemberOption[]
  runs: RunOption[]
}

export type DistributionRow = {
  value: string
  label: string
  count: number
  ratio?: number
  save_count?: number
  member_count?: number
}

export type TrendRow = {
  date: string
  completed?: number
  accepted?: number
  rejected?: number
  qualification_rate?: number
  average_attempts?: number
}

export type OverviewData = {
  summary: {
    rule_count?: number
    save_count?: number
  }
  counts: {
    all: number
    accepted: number
    rejected: number
    other: number
  }
  trend: TrendRow[]
  recognition: {
    known_positions: number
    total_positions: number
  }
  validation: {
    valid: boolean
    issues: string[]
  }
}

export type DistributionData = {
  rows: DistributionRow[]
  memberRows: DistributionRow[]
  targetRows: DistributionRow[]
  members: MemberOption[]
  targets: Option[]
}
