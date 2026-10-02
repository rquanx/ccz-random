import type {
  BootstrapData,
  DistributionData,
  OverviewData,
  StatisticsFilters,
} from "@/types"

const rootPath = window.location.pathname.replace(/\/$/, "")

export function apiUrl(name: string) {
  return `${rootPath}/api/${name}`
}

export async function getBootstrap(): Promise<BootstrapData> {
  const response = await fetch(apiUrl("bootstrap"))
  const data = await response.json()
  if (!response.ok || data.error) throw new Error(data.error || "初始化失败")
  return data
}

export async function post<T>(
  name: string,
  payload: Record<string, unknown>,
): Promise<T> {
  const response = await fetch(apiUrl(name), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
  const data = await response.json()
  if (!response.ok || data.error) throw new Error(data.error || "请求失败")
  return data as T
}

export function getOverview(filters: StatisticsFilters, page: number) {
  return post<OverviewData>("overview", { ...filters, page })
}

export function getDistribution(
  filters: StatisticsFilters,
  kind: string,
  memberId = "",
  targetId = "",
  section = "all",
) {
  return post<DistributionData>("distribution", {
    ...filters,
    kind,
    memberId,
    targetId,
    section,
  })
}

export function exportUrl(format: "csv" | "json", filters: StatisticsFilters) {
  return `${apiUrl("export")}?format=${format}&filters=${encodeURIComponent(JSON.stringify(filters))}`
}
