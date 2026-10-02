import { useCallback, useEffect, useState } from "react"
import {
  Area,
  AreaChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip as ChartTooltip,
  XAxis,
  YAxis,
} from "recharts"
import {
  Database,
  Download,
  FileJson,
  FileSpreadsheet,
  Printer,
  RefreshCw,
  Search,
  Trash2,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { DateRangeFilter } from "@/components/date-range-filter"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Input } from "@/components/ui/input"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { VirtualBarChart } from "@/components/virtual-bar-chart"
import { exportUrl, getBootstrap, getDistribution, getOverview, post } from "@/lib/api"
import type {
  BootstrapData,
  DistributionData,
  MemberOption,
  Option,
  OverviewData,
  StatisticsFilters,
} from "@/types"

const defaultFilters: StatisticsFilters = {
  content: "all",
  mode: "all",
  rule: "",
  after: "",
  before: "",
}

const pieColors = ["#3472e8", "#ce6972", "#d69b45"]

function ErrorState({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
      统计数据加载失败：{message}
    </div>
  )
}

function LoadingState() {
  return (
    <div className="grid min-h-[420px] place-items-center text-sm text-muted-foreground">
      正在加载统计数据
    </div>
  )
}

function RefreshIndicator() {
  return (
    <div className="pointer-events-none absolute right-3 top-3 z-10 flex items-center gap-2 rounded-md border bg-card/95 px-3 py-2 text-xs text-muted-foreground shadow-sm">
      <RefreshCw className="size-3.5 animate-spin" />
      正在更新
    </div>
  )
}

function FilterSelect({
  value,
  options,
  onChange,
}: {
  value: string
  options: Option[]
  onChange: (value: string) => void
}) {
  const normalized = value || "__all__"
  return (
    <Select value={normalized} onValueChange={(next) => onChange(next === "__all__" ? "" : next)}>
      <SelectTrigger><SelectValue /></SelectTrigger>
      <SelectContent>
        {options.map((option) => (
          <SelectItem key={option.value || "__all__"} value={option.value || "__all__"}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

function FilterBar({
  filters,
  rules,
  onChange,
}: {
  filters: StatisticsFilters
  rules: Option[]
  onChange: (next: StatisticsFilters) => void
}) {
  const patch = (value: Partial<StatisticsFilters>) => onChange({ ...filters, ...value })
  return (
    <section
      aria-label="统计筛选"
      className="grid grid-cols-[minmax(130px,.8fr)_minmax(130px,.8fr)_minmax(220px,1.35fr)_minmax(190px,1fr)] gap-3 rounded-lg border bg-card p-3 max-[900px]:grid-cols-2"
    >
      <label className="filter-label">
        统计内容
        <FilterSelect
          value={filters.content}
          options={[
            { value: "all", label: "全部" },
            { value: "accepted", label: "合格" },
            { value: "rejected", label: "不合格" },
            { value: "other", label: "其他" },
          ]}
          onChange={(content) => patch({ content: content as StatisticsFilters["content"] })}
        />
      </label>
      <label className="filter-label">
        随机模式
        <FilterSelect
          value={filters.mode}
          options={[
            { value: "all", label: "全部" },
            { value: "three", label: "3人" },
            { value: "seven", label: "7人" },
          ]}
          onChange={(mode) => patch({ mode: mode as StatisticsFilters["mode"] })}
        />
      </label>
      <label className="filter-label">
        规则配置
        <FilterSelect value={filters.rule} options={rules} onChange={(rule) => patch({ rule })} />
      </label>
      <label className="filter-label">
        时间周期
        <DateRangeFilter onChange={(range) => patch(range)} />
      </label>
    </section>
  )
}

function Overview({
  active,
  filters,
  refreshKey,
  onStatus,
}: {
  active: boolean
  filters: StatisticsFilters
  refreshKey: number
  onStatus: (value: string) => void
}) {
  const [data, setData] = useState<OverviewData | null>(null)
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const [trendMetric, setTrendMetric] = useState("completed")

  useEffect(() => {
    if (!active) return
    let current = true
    setLoading(true)
    setError("")
    getOverview(filters, 1).then((next) => {
      if (!current) return
      setData(next)
      onStatus(`全部历史 · ${next.summary.rule_count || 0} 个规则 · ${next.summary.save_count || 0} 个存档 · 识别 ${next.recognition.known_positions}/${next.recognition.total_positions}`)
    }).catch((reason: Error) => {
      if (current) setError(reason.message)
    }).finally(() => {
      if (current) setLoading(false)
    })
    return () => { current = false }
  }, [active, filters, onStatus, refreshKey])

  if (error && !data) return <ErrorState message={error} />
  if (!data) return <LoadingState />
  const metricCards = [
    ["全部", data.counts.all],
    ["合格", data.counts.accepted],
    ["不合格", data.counts.rejected],
    ["其他", data.counts.other],
  ]
  const pieData = [
    { name: "合格", value: data.counts.accepted },
    { name: "不合格", value: data.counts.rejected },
    { name: "其他", value: data.counts.other },
  ]
  const trendOptions = [
    { value: "completed", label: "已评分" },
    { value: "accepted", label: "合格数" },
    { value: "rejected", label: "不合格数" },
    { value: "qualification_rate", label: "合格率" },
    { value: "average_attempts", label: "平均尝试次数" },
  ]
  const trendRows = data.trend.map((row) => ({
    ...row,
    qualification_rate: Number(row.qualification_rate || 0) * 100,
  }))

  return (
    <div className="relative space-y-3">
      {loading && <RefreshIndicator />}
      {error && <ErrorState message={error} />}
      <section className="grid grid-cols-4 gap-3 max-[800px]:grid-cols-2">
        {metricCards.map(([label, value]) => (
          <Card key={label}>
            <CardContent className="p-4">
              <span className="text-xs text-muted-foreground">{label}</span>
              <strong className="mt-1 block text-2xl">{Number(value).toLocaleString()}</strong>
            </CardContent>
          </Card>
        ))}
      </section>
      <section className="grid grid-cols-2 gap-3 max-[900px]:grid-cols-1">
        <Card>
          <CardHeader>
            <CardTitle>结果分布</CardTitle>
            <CardDescription>全部已完成评分结果的状态构成</CardDescription>
          </CardHeader>
          <CardContent className="h-[280px]">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={pieData}
                  dataKey="value"
                  nameKey="name"
                  innerRadius={62}
                  outerRadius={92}
                  paddingAngle={2}
                  isAnimationActive={false}
                >
                  {pieData.map((entry, index) => <Cell key={entry.name} fill={pieColors[index]} />)}
                </Pie>
                <ChartTooltip />
              </PieChart>
            </ResponsiveContainer>
            <div className="-mt-5 flex justify-center gap-5 text-xs text-muted-foreground">
              {pieData.map((entry, index) => (
                <span key={entry.name} className="flex items-center gap-2">
                  <i className="size-2 rounded-full" style={{ background: pieColors[index] }} />
                  {entry.name} {entry.value}
                </span>
              ))}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex-row items-start justify-between">
            <div>
              <CardTitle>历史趋势</CardTitle>
              <CardDescription>横轴为日期，悬停节点查看数值</CardDescription>
            </div>
            <div className="w-40">
              <FilterSelect value={trendMetric} options={trendOptions} onChange={setTrendMetric} />
            </div>
          </CardHeader>
          <CardContent className="h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={trendRows} margin={{ top: 8, right: 12, left: -16, bottom: 4 }}>
                <defs>
                  <linearGradient id="trend-fill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#3472e8" stopOpacity={0.2} />
                    <stop offset="100%" stopColor="#3472e8" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid vertical={false} stroke="#e7ebf0" />
                <XAxis dataKey="date" tickFormatter={(value) => String(value).slice(5)} tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <ChartTooltip />
                <Area
                  type="monotone"
                  dataKey={trendMetric}
                  stroke="#3472e8"
                  strokeWidth={2.5}
                  fill="url(#trend-fill)"
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </section>
      {!data.validation.valid && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-900">
          数据不完整：{data.validation.issues.join("；")}
        </div>
      )}
    </div>
  )
}

function distributionMeta(kind: string) {
  if (kind === "jobs") return {
    main: "兵种出现分布", mainDescription: "汇总所有武将位置随机出的兵种次数与占比",
    memberSuffix: "的兵种分布", memberDescription: "查看该武将被分配到的兵种",
    targetSuffix: "分配给不同武将的分布", targetDescription: "查看该兵种在不同武将之间的分配情况",
    memberLabel: "武将", targetLabel: "兵种",
  }
  if (kind === "treasure") return {
    main: "宝物特性出现分布", mainDescription: "汇总所有宝物被分配到的特性次数与占比",
    memberSuffix: "的特性分布", memberDescription: "查看该宝物被分配到的特性",
    targetSuffix: "分配给不同宝物的分布", targetDescription: "查看该特性在不同宝物之间的分配情况",
    memberLabel: "宝物", targetLabel: "特性",
  }
  const label = kind === "personal" ? "个人天赋" : "兵种技能"
  return {
    main: `${label}出现分布`, mainDescription: `汇总所有武将位置出现的${label}，多项特技分别计数`,
    memberSuffix: `的${label}分布`, memberDescription: `查看该武将被分配到的${label}`,
    targetSuffix: "分配给不同武将的分布", targetDescription: `查看该${label}在不同武将之间的分配情况`,
    memberLabel: "武将", targetLabel: label,
  }
}

function DistributionView({
  active,
  kind,
  filters,
  refreshKey,
  onStatus,
}: {
  active: boolean
  kind: "jobs" | "personal" | "job" | "treasure"
  filters: StatisticsFilters
  refreshKey: number
  onStatus: (value: string) => void
}) {
  const [data, setData] = useState<DistributionData | null>(null)
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const [memberId, setMemberId] = useState("")
  const [targetId, setTargetId] = useState("")
  const [mainQuery, setMainQuery] = useState("")
  const meta = distributionMeta(kind)

  useEffect(() => {
    if (!active) return
    let current = true
    setLoading(true)
    setError("")
    getDistribution(filters, kind).then(async (initial) => {
      if (!current) return
      const nextMember = initial.members[0]?.member_id || ""
      const nextTarget = initial.targets[0]?.value || ""
      setMemberId(nextMember)
      setTargetId(nextTarget)
      const [memberData, targetData] = await Promise.all([
        nextMember ? getDistribution(filters, kind, nextMember, nextTarget, "member") : Promise.resolve(initial),
        nextTarget ? getDistribution(filters, kind, nextMember, nextTarget, "target") : Promise.resolve(initial),
      ])
      if (!current) return
      setData({ ...initial, memberRows: memberData.memberRows, targetRows: targetData.targetRows })
      onStatus(`全部历史 · ${initial.rows.length} 个可统计项目 · 当前仅渲染可视区域`)
    }).catch((reason: Error) => {
      if (current) setError(reason.message)
    }).finally(() => {
      if (current) setLoading(false)
    })
    return () => { current = false }
  }, [active, filters, kind, onStatus, refreshKey])

  const updateMember = async (value: string) => {
    setMemberId(value)
    if (!data) return
    try {
      const next = await getDistribution(filters, kind, value, targetId, "member")
      setData({ ...data, memberRows: next.memberRows })
    } catch (reason) {
      setError((reason as Error).message)
    }
  }

  const updateTarget = async (value: string) => {
    setTargetId(value)
    if (!data) return
    try {
      const next = await getDistribution(filters, kind, memberId, value, "target")
      setData({ ...data, targetRows: next.targetRows })
    } catch (reason) {
      setError((reason as Error).message)
    }
  }

  if (error && !data) return <ErrorState message={error} />
  if (!data) return <LoadingState />
  const memberOptions = data.members.map((item: MemberOption) => ({ value: item.member_id, label: item.member_name }))
  const memberName = memberOptions.find((item) => item.value === memberId)?.label || "指定对象"
  const targetName = data.targets.find((item) => item.value === targetId)?.label || "指定内容"
  const normalizedQuery = mainQuery.trim().toLocaleLowerCase()
  const mainRows = normalizedQuery
    ? data.rows.filter((row) => row.label.toLocaleLowerCase().includes(normalizedQuery))
    : data.rows
  const splitAt = Math.ceil(mainRows.length / 2)
  const mainColumns = [
    mainRows.slice(0, splitAt),
    mainRows.slice(splitAt),
  ]

  return (
    <div className="relative space-y-3">
      {loading && <RefreshIndicator />}
      {error && <ErrorState message={error} />}
      <Card>
        <CardHeader className="flex-row items-start justify-between">
          <div>
            <CardTitle>{meta.main}</CardTitle>
            <CardDescription>{meta.mainDescription}</CardDescription>
          </div>
          <div className="relative w-56">
            <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={mainQuery}
              onChange={(event) => setMainQuery(event.target.value)}
              placeholder="搜索名称"
              className="pl-9"
            />
          </div>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-6 max-[900px]:grid-cols-1">
          {mainColumns.map((rows, index) => (
            <div key={index} className={index ? "border-l pl-6 max-[900px]:border-l-0 max-[900px]:border-t max-[900px]:pl-0 max-[900px]:pt-4" : ""}>
              <VirtualBarChart rows={rows} height={460} />
            </div>
          ))}
        </CardContent>
      </Card>
      <section className="grid grid-cols-2 gap-3 max-[900px]:grid-cols-1">
        <Card>
          <CardHeader className="flex-row items-start justify-between">
            <div>
              <CardTitle>{memberName}{meta.memberSuffix}</CardTitle>
              <CardDescription>{meta.memberDescription}</CardDescription>
            </div>
            <label className="w-44 text-xs text-muted-foreground">
              {meta.memberLabel}
              <FilterSelect value={memberId} options={memberOptions} onChange={updateMember} />
            </label>
          </CardHeader>
          <CardContent><VirtualBarChart rows={data.memberRows} height={360} /></CardContent>
        </Card>
        <Card>
          <CardHeader className="flex-row items-start justify-between">
            <div>
              <CardTitle>{targetName}{meta.targetSuffix}</CardTitle>
              <CardDescription>{meta.targetDescription}</CardDescription>
            </div>
            <label className="w-44 text-xs text-muted-foreground">
              {meta.targetLabel}
              <FilterSelect value={targetId} options={data.targets} onChange={updateTarget} />
            </label>
          </CardHeader>
          <CardContent><VirtualBarChart rows={data.targetRows} height={360} /></CardContent>
        </Card>
      </section>
    </div>
  )
}

function RunManager({
  open,
  runs,
  onOpenChange,
  onDelete,
}: {
  open: boolean
  runs: BootstrapData["runs"]
  onOpenChange: (open: boolean) => void
  onDelete: (runId: string) => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>删除运行记录</DialogTitle></DialogHeader>
        <div className="max-h-[520px] space-y-2 overflow-auto">
          {runs.length ? runs.map((run) => (
            <div key={run.id} className="flex items-center justify-between gap-4 rounded-md border p-3">
              <div>
                <strong className="text-sm">{run.rule_name || "未命名规则"}</strong>
                <p className="mt-1 text-xs text-muted-foreground">
                  {run.started_at} · {run.mode} · {run.attempt_count || 0} 次尝试
                </p>
              </div>
              <Button variant="outline" size="sm" className="text-destructive" onClick={() => onDelete(run.id)}>
                <Trash2 />删除
              </Button>
            </div>
          )) : <div className="grid h-48 place-items-center text-sm text-muted-foreground">没有可删除的运行记录</div>}
        </div>
      </DialogContent>
    </Dialog>
  )
}

function App() {
  const [bootstrap, setBootstrap] = useState<BootstrapData | null>(null)
  const [filters, setFilters] = useState(defaultFilters)
  const [tab, setTab] = useState("overview")
  const [skillTab, setSkillTab] = useState("personal")
  const [status, setStatus] = useState("正在读取历史结果")
  const [error, setError] = useState("")
  const [refreshKey, setRefreshKey] = useState(0)
  const [runManagerOpen, setRunManagerOpen] = useState(false)
  const [toast, setToast] = useState("")
  const stableStatus = useCallback((value: string) => setStatus(value), [])

  useEffect(() => {
    getBootstrap().then(setBootstrap).catch((reason: Error) => setError(reason.message))
  }, [])
  useEffect(() => {
    if (!toast) return
    const timer = window.setTimeout(() => setToast(""), 3200)
    return () => window.clearTimeout(timer)
  }, [toast])

  const manage = async (action: "rebuild" | "clear") => {
    const message = action === "clear"
      ? "只隐藏统计历史，不删除存档、结果图或日志。确定继续吗？"
      : "将根据已有历史快照重建统计索引。确定继续吗？"
    if (!window.confirm(message)) return
    try {
      const result = await post<{ bootstrap: BootstrapData }>("manage", { action })
      setBootstrap(result.bootstrap)
      setToast(action === "clear" ? "统计历史已清空" : "统计索引已重建")
      setRefreshKey((value) => value + 1)
    } catch (reason) {
      setError((reason as Error).message)
    }
  }

  const deleteRun = async (runId: string) => {
    if (!window.confirm("只删除该运行的统计事实和历史快照，不删除游戏存档、结果图或日志。确定继续吗？")) return
    try {
      const result = await post<{ bootstrap: BootstrapData }>("manage", { action: "delete", runId })
      setBootstrap(result.bootstrap)
      setToast("运行记录已删除")
      setRefreshKey((value) => value + 1)
    } catch (reason) {
      setError((reason as Error).message)
    }
  }

  if (error) return <main className="mx-auto max-w-5xl p-8"><ErrorState message={error} /></main>
  if (!bootstrap) return <LoadingState />

  return (
    <div className="mx-auto w-[min(1480px,calc(100%-36px))] py-7">
      <header className="mb-5 flex items-start justify-between gap-6 max-[760px]:flex-col">
        <div>
          <div className="text-[11px] font-bold text-primary">CCZ RANDOM ANALYTICS</div>
          <h1 className="mt-1 text-3xl font-bold">结果统计</h1>
          <p className="mt-1 text-sm text-muted-foreground">{status}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={() => setRefreshKey((value) => value + 1)}><RefreshCw />刷新</Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild><Button variant="outline"><Download />导出</Button></DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={() => { window.location.href = exportUrl("csv", filters) }}><FileSpreadsheet />明细 CSV</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => { window.location.href = exportUrl("json", filters) }}><FileJson />完整数据 JSON</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => window.print()}><Printer />打印当前页面</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <DropdownMenu>
            <DropdownMenuTrigger asChild><Button variant="outline"><Database />数据管理</Button></DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={() => manage("rebuild")}><RefreshCw />重建统计</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => setRunManagerOpen(true)}><Trash2 />删除指定运行</DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem className="text-destructive" onSelect={() => manage("clear")}><Trash2 />清空统计</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </header>
      <FilterBar filters={filters} rules={bootstrap.rules} onChange={setFilters} />
      <Tabs value={tab} onValueChange={setTab} className="mt-4">
        <TabsList className="w-full justify-start">
          <TabsTrigger value="overview">总览</TabsTrigger>
          <TabsTrigger value="jobs">兵种分布</TabsTrigger>
          <TabsTrigger value="skills">特技分布</TabsTrigger>
          <TabsTrigger value="treasure">宝物分布</TabsTrigger>
        </TabsList>
      </Tabs>
      <main className="mt-4">
        <section hidden={tab !== "overview"}>
          <Overview
            active={tab === "overview"}
            filters={filters}
            refreshKey={refreshKey}
            onStatus={stableStatus}
          />
        </section>
        <section hidden={tab !== "jobs"}>
          <DistributionView
            active={tab === "jobs"}
            kind="jobs"
            filters={filters}
            refreshKey={refreshKey}
            onStatus={stableStatus}
          />
        </section>
        <section hidden={tab !== "skills"}>
          <Tabs value={skillTab} onValueChange={setSkillTab}>
            <TabsList>
              <TabsTrigger value="personal">个人</TabsTrigger>
              <TabsTrigger value="job">兵种</TabsTrigger>
            </TabsList>
            <TabsContent forceMount value="personal" hidden={skillTab !== "personal"}>
              <DistributionView
                active={tab === "skills" && skillTab === "personal"}
                kind="personal"
                filters={filters}
                refreshKey={refreshKey}
                onStatus={stableStatus}
              />
            </TabsContent>
            <TabsContent forceMount value="job" hidden={skillTab !== "job"}>
              <DistributionView
                active={tab === "skills" && skillTab === "job"}
                kind="job"
                filters={filters}
                refreshKey={refreshKey}
                onStatus={stableStatus}
              />
            </TabsContent>
          </Tabs>
        </section>
        <section hidden={tab !== "treasure"}>
          <DistributionView
            active={tab === "treasure"}
            kind="treasure"
            filters={filters}
            refreshKey={refreshKey}
            onStatus={stableStatus}
          />
        </section>
      </main>
      <RunManager open={runManagerOpen} runs={bootstrap.runs} onOpenChange={setRunManagerOpen} onDelete={deleteRun} />
      {toast && <div className="fixed bottom-6 right-6 z-[100] rounded-md bg-slate-800 px-4 py-3 text-sm text-white shadow-xl">{toast}</div>}
    </div>
  )
}

export default App
