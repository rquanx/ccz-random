import { useCallback, useEffect, useRef, useState } from "react"
import {
  BarChart3,
  ChevronRight,
  FileImage,
  Play,
  Plus,
  RotateCcw,
  Search,
  Settings2,
  Square,
  Trash2,
  Upload,
  Wrench,
  X,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { apiUrl, post } from "@/lib/api"
import { cn } from "@/lib/utils"

type Json = Record<string, any>

type Bootstrap = {
  build: Json
  changelog: Json[]
  rules: Json
  catalogs: Json
  state: AppState
  startupWarning?: string
}

type AppState = {
  running: boolean
  stopping: boolean
  settings: {
    mode: "three" | "seven"
    loopRandom: boolean
    concurrency: number
    compatibilityMode: boolean
    activeProfile: string
  }
  profiles: string[]
  consoleText: string
  singleDetails: Json[]
  concurrent: {
    enabled: boolean
    rounds: Array<{
      round: number
      image: string
      slots: Array<{
        slot: number
        attempt: number
        stage: string
        completed: boolean
        detail?: Json
        attempts: Array<{ attempt: number; memberSummary: string; detail?: Json }>
      }>
    }>
    footer: string
    activeRound: number
  }
  resultImage: string
  notifications?: Array<{ id: number; message: string; duration?: number }>
}

const typeLabels: Record<string, string> = {
  ALL_ROUNDER: "全能型",
  WARRIOR: "武将型",
  MASTER: "文官型",
  NONE: "无",
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value))
}

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url)
  const data = await response.json()
  if (!response.ok || data.error) throw new Error(data.error || "请求失败")
  return data as T
}

function Field({
  label,
  children,
  hint,
}: {
  label: string
  children: React.ReactNode
  hint?: string
}) {
  return (
    <label className="grid gap-1.5">
      <span className="text-xs font-medium text-foreground">{label}</span>
      {children}
      {hint && <span className="text-[11px] text-muted-foreground">{hint}</span>}
    </label>
  )
}

function ToggleRow({
  checked,
  label,
  description,
  disabled,
  onChange,
}: {
  checked: boolean
  label: string
  description?: string
  disabled?: boolean
  onChange: (checked: boolean) => void
}) {
  return (
    <label className="flex cursor-pointer items-start gap-3 rounded-md border p-3 hover:bg-muted/40">
      <Checkbox checked={checked} disabled={disabled} onCheckedChange={(value) => onChange(value === true)} />
      <span>
        <span className="block text-sm font-medium">{label}</span>
        {description && <span className="mt-0.5 block text-xs text-muted-foreground">{description}</span>}
      </span>
    </label>
  )
}

function ScoreDetailDialog({
  detail,
  onOpenChange,
}: {
  detail: Json | null
  onOpenChange: (open: boolean) => void
}) {
  const job = detail?.job
  const skill = detail?.skill
  return (
    <Dialog open={Boolean(detail)} onOpenChange={onOpenChange}>
      <DialogContent className="w-[min(820px,calc(100vw-40px))]">
        <DialogHeader>
          <DialogTitle>
            存档 {detail?.resultSlot ?? "-"} · 第 {detail?.attempt ?? "-"} 次尝试
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className={cn(
            "rounded-md border px-4 py-3 text-sm font-medium",
            detail?.status === "accepted" ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-rose-200 bg-rose-50 text-rose-800",
          )}>
            {detail?.mode === "three" ? "3人" : "7人"} · {detail?.label || "未知结果"}
          </div>
          {job && (
            <Card>
              <CardHeader><CardTitle>兵种评分</CardTitle></CardHeader>
              <CardContent className="grid grid-cols-2 gap-2 max-[700px]:grid-cols-1">
                {(job.members || []).map((member: Json, index: number) => (
                  <div key={`${member.name}-${index}`} className="flex justify-between rounded-md bg-muted px-3 py-2 text-sm">
                    <span>{member.name} · {member.job}</span>
                    <strong>{member.score ?? "-"}</strong>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
          <Card>
            <CardHeader><CardTitle>特技评分</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              {skill ? (skill.members || []).map((member: Json, index: number) => (
                <div key={`${member.name}-${index}`} className="rounded-md bg-muted px-3 py-2 text-sm">
                  <div className="flex justify-between gap-3">
                    <strong>{member.name}</strong>
                    <span>计分 {member.score ?? "-"}</span>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">{(member.skills || []).join("、") || "未识别到有效特技"}</p>
                </div>
              )) : <p className="text-sm text-muted-foreground">兵种未通过，本次未继续检查特技。</p>}
            </CardContent>
          </Card>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function ConsoleView({
  state,
  openDetail,
  openFile,
}: {
  state: AppState
  openDetail: (detail: Json) => void
  openFile: (path: string) => void
}) {
  if (!state.concurrent.enabled) {
    return (
      <div className="relative h-full min-h-[360px] overflow-auto border bg-[#fafafa] p-4 font-mono text-[13px] leading-6 text-foreground">
        <pre className="whitespace-pre-wrap">{state.consoleText || "等待开始随机"}</pre>
        {state.singleDetails.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2 border-t pt-4">
            {state.singleDetails.slice(-12).map((detail, index) => (
              <Button key={`${detail.attempt}-${index}`} size="sm" variant="outline" onClick={() => openDetail(detail)}>
                第 {detail.attempt} 次 · {detail.label}
              </Button>
            ))}
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="h-full min-h-[360px] space-y-4 overflow-auto border bg-[#fafafa] p-4 font-mono text-[13px] leading-6 text-foreground">
      {state.concurrent.rounds.map((round) => (
        <section key={round.round}>
          {state.settings.loopRandom && <h3 className="mb-2 font-semibold">第 {round.round} 轮</h3>}
          <div className="space-y-1.5">
            {round.slots.map((slot) => (
              <div key={slot.slot} className="grid grid-cols-[48px_1fr_auto] items-center gap-2 px-1 py-0.5">
                <button
                  className="text-left text-xs font-medium text-primary hover:underline"
                  onClick={() => {
                    const last = [...slot.attempts].reverse().find((item) => item.detail)
                    if (last?.detail) openDetail(last.detail)
                  }}
                >
                  明细
                </button>
                <span className="text-sm">
                  存档{slot.slot}
                  {slot.attempt ? `　第 ${slot.attempt} 次尝试　` : "　"}
                  <span className={slot.completed ? "text-emerald-700" : ""}>{slot.stage}</span>
                </span>
                {slot.detail && (
                  <button className="text-xs text-primary hover:underline" onClick={() => openDetail(slot.detail!)}>
                    查看评分
                  </button>
                )}
              </div>
            ))}
          </div>
          {round.image && (
            <button className="mt-2 text-sm text-primary hover:underline" onClick={() => openFile(round.image)}>
              查看本轮结果图
            </button>
          )}
        </section>
      ))}
      {state.concurrent.footer && <p className="border-t pt-3 text-sm font-medium">{state.concurrent.footer}</p>}
    </div>
  )
}

function RuleEditor({
  open,
  bootstrap,
  onOpenChange,
  onSaved,
  notify,
}: {
  open: boolean
  bootstrap: Bootstrap
  onOpenChange: (open: boolean) => void
  onSaved: (rules: Json) => void
  notify: (message: string) => void
}) {
  const [working, setWorking] = useState(() => clone(bootstrap.rules))
  const [newName, setNewName] = useState("")
  const [scoreSearch, setScoreSearch] = useState({ job: "", skill: "", jobType: "" })
  const [ruleSection, setRuleSection] = useState("simple")
  const [saving, setSaving] = useState(false)
  const [pendingDelete, setPendingDelete] = useState(false)
  const [affinityOpen, setAffinityOpen] = useState(false)
  const importRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open) {
      setWorking(clone(bootstrap.rules))
      setPendingDelete(false)
      setRuleSection("simple")
      setScoreSearch({ job: "", skill: "", jobType: "" })
    } else {
      setAffinityOpen(false)
    }
  }, [bootstrap.rules, open])

  useEffect(() => {
    if (!open) return
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = "hidden"
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !affinityOpen) onOpenChange(false)
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener("keydown", handleKeyDown)
    }
  }, [affinityOpen, onOpenChange, open])

  const activeName = working.activeProfile
  const profile = working.profiles[activeName]
  const readonly = Boolean(profile?.builtin)
  const catalogs = bootstrap.catalogs

  const updateProfile = (updater: (draft: Json) => void) => {
    if (readonly) return
    setWorking((current: Json) => {
      const next = clone(current)
      updater(next.profiles[next.activeProfile])
      return next
    })
  }

  const setPath = (path: string[], value: any) => {
    updateProfile((draft) => {
      let target = draft
      path.slice(0, -1).forEach((key) => { target = target[key] })
      target[path[path.length - 1]] = value
    })
  }

  const createProfile = () => {
    const name = newName.trim()
    if (!name) return
    if (working.profiles[name]) {
      notify("规则名称已经存在")
      return
    }
    setWorking((current: Json) => {
      const next = clone(current)
      const source = clone(next.profiles[next.activeProfile])
      source.builtin = false
      next.profiles[name] = source
      next.activeProfile = name
      return next
    })
    setNewName("")
  }

  const duplicateProfile = () => {
    const base = `${activeName} 副本`
    let name = base
    let index = 2
    while (working.profiles[name]) name = `${base} ${index++}`
    setWorking((current: Json) => {
      const next = clone(current)
      const source = clone(next.profiles[next.activeProfile])
      source.builtin = false
      next.profiles[name] = source
      next.activeProfile = name
      return next
    })
  }

  const deleteProfile = () => {
    if (readonly || Object.keys(working.profiles).length <= 1) return
    if (!pendingDelete) {
      setPendingDelete(true)
      return
    }
    setWorking((current: Json) => {
      const next = clone(current)
      delete next.profiles[next.activeProfile]
      next.activeProfile = Object.keys(next.profiles)[0]
      return next
    })
    setPendingDelete(false)
  }

  const save = async () => {
    setSaving(true)
    try {
      const result = await post<{ rules: Json; notice: string }>("app/rules-save", { config: working })
      onSaved(result.rules)
      notify(result.notice)
      onOpenChange(false)
    } catch (reason) {
      notify((reason as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const importRules = async (file?: File) => {
    if (!file) return
    try {
      const value = JSON.parse(await file.text())
      const result = await post<{ rules: Json; notice: string }>("app/rules-import", { value })
      setWorking(result.rules)
      onSaved(result.rules)
      notify(result.notice)
    } catch (reason) {
      notify(`规则导入失败：${(reason as Error).message}`)
    }
  }

  const numberField = (label: string, path: string[], hint?: string) => {
    let value: any = profile
    path.forEach((key) => { value = value[key] })
    return (
      <Field label={label} hint={hint}>
        <Input
          type="number"
          step="0.01"
          disabled={readonly}
          value={value}
          onChange={(event) => setPath(path, Number(event.target.value))}
        />
      </Field>
    )
  }

  const scoreRows = (kind: "job" | "skill") => {
    const isJob = kind === "job"
    const rows = isJob ? catalogs.jobs : catalogs.skills
    const scorePath = isJob ? ["jobScoring", "jobBaseScores"] : ["sevenPerson", "skillBaseScores"]
    const typePath = isJob ? ["jobScoring", "jobTypeOverrides"] : ["sevenPerson", "skillTypeOverrides"]
    const scores = isJob ? profile.jobScoring.jobBaseScores : profile.sevenPerson.skillBaseScores
    const overrides = isJob ? profile.jobScoring.jobTypeOverrides : profile.sevenPerson.skillTypeOverrides
    const typeOptions = isJob ? catalogs.jobTypes : catalogs.skillTypes
    const query = scoreSearch[kind].trim().toLocaleLowerCase()
    const visible = rows.filter((row: Json) => {
      const typeLabel = typeLabels[overrides[row.name] ?? row.type] || ""
      return `${row.name} ${row.tier || ""} ${typeLabel}`.toLocaleLowerCase().includes(query)
    })
    const skillTier = (row: Json) => {
      const score = Number(scores[row.name] ?? row.score)
      if (score >= Number(profile.sevenPerson.specialSkillWeight)) return "特殊"
      if (score >= Number(profile.sevenPerson.strongSkillWeight)) return "强力"
      if (score >= Number(profile.sevenPerson.ordinarySkillWeight)) return "优质"
      return "其他"
    }
    const tierClass = (tier: string) => ({
      特殊: "border-l-[#b24747]",
      强力: "border-l-[#496fa8]",
      优质: "border-l-[#4d8560]",
      其他: "border-l-[#888888]",
    }[tier] || "border-l-border")
    return (
      <div className="grid min-h-0 grid-rows-[auto_1fr] gap-3">
        <div className="flex items-center gap-2 rounded-md bg-muted/55 px-3 py-2">
          <span className="text-xs font-medium text-muted-foreground">搜索</span>
          <div className="relative min-w-0 flex-1">
            <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={scoreSearch[kind]}
              onChange={(event) => setScoreSearch((current) => ({ ...current, [kind]: event.target.value }))}
              placeholder="输入名称、档次或类型"
              className="bg-card pl-9 pr-9"
            />
            {scoreSearch[kind] && (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                title="清空搜索"
                className="absolute right-1 top-1/2 size-7 -translate-y-1/2"
                onClick={() => setScoreSearch((current) => ({ ...current, [kind]: "" }))}
              >
                <X className="size-4" />
              </Button>
            )}
          </div>
          <span className="w-14 text-right text-xs text-muted-foreground">{visible.length} 项</span>
        </div>
        <div className="min-h-0 overflow-auto rounded-md bg-muted/30 p-2">
          <div className="grid grid-cols-4 gap-2 max-[980px]:grid-cols-3 max-[760px]:grid-cols-2">
            {visible.map((row: Json) => {
              const tier = isJob ? "" : skillTier(row)
              return (
                <div
                  key={row.name}
                  className={cn(
                    "relative min-h-[82px] rounded-sm border bg-card p-2.5",
                    !isJob && "min-h-[116px] border-l-[3px]",
                    !isJob && tierClass(tier),
                  )}
                >
                  <div className="mb-2 flex min-w-0 items-center justify-between gap-2">
                    <strong className="truncate text-sm font-medium" title={row.name}>{row.name}</strong>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      title="恢复默认"
                      disabled={readonly}
                      className="size-7 shrink-0 text-muted-foreground"
                      onClick={() => updateProfile((draft) => {
                        let scoreTarget = draft
                        scorePath.forEach((key) => { scoreTarget = scoreTarget[key] })
                        delete scoreTarget[row.name]
                        if (!isJob) {
                          let typeTarget = draft
                          typePath.forEach((key) => { typeTarget = typeTarget[key] })
                          delete typeTarget[row.name]
                        }
                      })}
                    >
                      <RotateCcw className="size-3.5" />
                    </Button>
                  </div>
                  {!isJob && (
                    <label className="mb-1.5 grid h-8 grid-cols-[82px_1fr] items-center overflow-hidden rounded-sm border bg-muted/20 text-xs">
                      <span className="px-2 text-muted-foreground">匹配类型</span>
                      <Select
                        disabled={readonly}
                        value={overrides[row.name] ?? row.type}
                        onValueChange={(value) => updateProfile((draft) => {
                          let target = draft
                          typePath.forEach((key) => { target = target[key] })
                          target[row.name] = value
                        })}
                      >
                        <SelectTrigger className="h-8 rounded-none border-y-0 border-r-0 bg-card px-2 focus:ring-0">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {typeOptions.map((value: string) => <SelectItem key={value} value={value}>{typeLabels[value]}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    </label>
                  )}
                  <label className="grid h-8 grid-cols-[minmax(92px,1fr)_58px] items-center overflow-hidden rounded-sm border bg-muted/20 text-xs">
                    <span className="truncate px-2 text-muted-foreground">
                      {tier ? `${tier} · 基础分` : "基础分"}
                    </span>
                    <Input
                      type="number"
                      step="0.1"
                      disabled={readonly}
                      value={scores[row.name] ?? row.score}
                      className="h-8 rounded-none border-y-0 border-r-0 bg-card px-2 text-right font-semibold focus-visible:ring-0"
                      onChange={(event) => {
                        const value = Number(event.target.value)
                        updateProfile((draft) => {
                          let target = draft
                          scorePath.forEach((key) => { target = target[key] })
                          target[row.name] = value
                        })
                      }}
                    />
                  </label>
                </div>
              )
            })}
          </div>
          {!visible.length && (
            <div className="grid h-40 place-items-center text-sm text-muted-foreground">没有匹配的项目</div>
          )}
        </div>
      </div>
    )
  }

  const jobTypeRows = () => {
    const overrides = profile.jobScoring.jobTypeOverrides
    const query = scoreSearch.jobType.trim().toLocaleLowerCase()
    const visible = catalogs.jobs.filter((row: Json) => (
      `${row.name} ${typeLabels[overrides[row.name] ?? row.type] || ""}`
        .toLocaleLowerCase()
        .includes(query)
    ))
    return (
      <div className="space-y-3">
        <div className="relative ml-auto w-64">
          <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={scoreSearch.jobType}
            onChange={(event) => setScoreSearch((current) => ({ ...current, jobType: event.target.value }))}
            placeholder="搜索兵种"
            className="pl-9"
          />
        </div>
        <div className="max-h-[520px] overflow-auto rounded-md border">
          {visible.map((row: Json) => (
            <div key={row.name} className="grid grid-cols-[1fr_180px_70px] items-center gap-3 border-b px-3 py-2 last:border-0">
              <strong className="text-sm">{row.name}</strong>
              <Select
                disabled={readonly}
                value={overrides[row.name] ?? row.type}
                onValueChange={(value) => updateProfile((draft) => { draft.jobScoring.jobTypeOverrides[row.name] = value })}
              >
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {catalogs.jobTypes.map((value: string) => <SelectItem key={value} value={value}>{typeLabels[value]}</SelectItem>)}
                </SelectContent>
              </Select>
              <Button variant="ghost" size="sm" disabled={readonly} onClick={() => updateProfile((draft) => { delete draft.jobScoring.jobTypeOverrides[row.name] })}>重置</Button>
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (!profile) return null

  return (
    <>
    {open && (
      <div
        className="fixed inset-0 z-50 grid place-items-center bg-slate-950/45 p-4"
        onMouseDown={(event) => {
          if (event.target === event.currentTarget) onOpenChange(false)
        }}
      >
        <div
          role="dialog"
          aria-modal="true"
          aria-label="规则设置"
          className="relative h-[min(860px,92vh)] w-[min(1180px,calc(100vw-32px))] overflow-hidden rounded-lg border bg-background shadow-2xl"
        >
          <Button
            type="button"
            variant="ghost"
            size="icon"
            title="关闭"
            className="absolute right-3 top-3 z-20 size-8 text-muted-foreground"
            onClick={() => onOpenChange(false)}
          >
            <X className="size-4" />
          </Button>
        <div className="grid h-full grid-rows-[auto_1fr_auto]">
          <header className="border-b px-6 py-4">
            <div className="flex flex-wrap items-end gap-3 pr-8">
              <Field label="规则方案">
                <Select
                  value={activeName}
                  onValueChange={(value) => setWorking((current: Json) => ({ ...current, activeProfile: value }))}
                >
                  <SelectTrigger className="w-56"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {Object.keys(working.profiles).map((name) => <SelectItem key={name} value={name}>{name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </Field>
              <Button variant="outline" onClick={duplicateProfile}><Plus />创建副本</Button>
              <div className="flex items-end gap-2">
                <Field label="新规则名称">
                  <Input value={newName} onChange={(event) => setNewName(event.target.value)} className="w-48" />
                </Field>
                <Button variant="outline" onClick={createProfile} disabled={!newName.trim()}>新建</Button>
              </div>
              <Button variant="outline" className={pendingDelete ? "border-destructive text-destructive" : ""} disabled={readonly} onClick={deleteProfile}>
                <Trash2 />{pendingDelete ? "再次点击确认" : "删除"}
              </Button>
              <div className="ml-auto flex gap-2">
                <input ref={importRef} type="file" accept=".json,application/json" className="hidden" onChange={(event) => importRules(event.target.files?.[0])} />
                <Button variant="outline" onClick={() => importRef.current?.click()}><Upload />导入</Button>
                <Button variant="outline" onClick={() => { window.location.href = apiUrl("app/rules-export") }}>导出</Button>
              </div>
            </div>
            {readonly && <p className="mt-3 text-xs text-amber-700">内置默认规则只读，请先创建副本再修改。</p>}
          </header>
          <Tabs
            value={ruleSection}
            onValueChange={setRuleSection}
            className="grid min-h-0 grid-rows-[auto_1fr] px-6 pt-3"
          >
            <TabsList className="hide-scrollbar w-full justify-start overflow-x-auto">
              <TabsTrigger value="simple">简单模式</TabsTrigger>
              <TabsTrigger value="threshold">阶段门槛</TabsTrigger>
              <TabsTrigger value="job">兵种评分</TabsTrigger>
              <TabsTrigger value="job-scores">兵种基础分</TabsTrigger>
              <TabsTrigger value="skill">特技评分</TabsTrigger>
              <TabsTrigger value="skill-scores">特技基础设置</TabsTrigger>
              <TabsTrigger value="job-types">兵种类型</TabsTrigger>
            </TabsList>
            <div className="min-h-0 min-w-0 overflow-auto py-4">
              <TabsContent value="simple" className="m-0 space-y-5">
                <div>
                  <h2 className="text-lg font-semibold">简单模式</h2>
                  <p className="mt-1 text-sm text-muted-foreground">通过六个选项调整整体规则强度，保存时自动换算为详细参数。</p>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  {[
                    ["jobQuality", "兵种质量要求"],
                    ["affinityImportance", "人物适配重视程度"],
                    ["teamBalance", "队伍兵种平衡"],
                    ["skillQuality", "特技质量要求"],
                    ["strongSkillImportance", "强力特技重视程度"],
                    ["highJobPreference", "高质量兵种优先程度"],
                  ].map(([key, label]) => (
                    <Field key={key} label={label}>
                      <Select disabled={readonly} value={profile.simpleSettings[key]} onValueChange={(value) => setPath(["simpleSettings", key], value)}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {catalogs.simpleOptions[key].map((value: string) => <SelectItem key={value} value={value}>{value}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    </Field>
                  ))}
                </div>
                {!readonly && (
                  <ToggleRow
                    checked={profile.editorMode === "simple"}
                    label="保存时使用简单模式参数"
                    description="关闭后保留高级设置中的具体数值。"
                    onChange={(checked) => setPath(["editorMode"], checked ? "simple" : "advanced")}
                  />
                )}
              </TabsContent>
                    <TabsContent value="threshold" className="m-0 space-y-5">
                      <h2 className="text-lg font-semibold">阶段门槛</h2>
                      <div className="grid grid-cols-3 gap-4">
                        {numberField("3人兵种合格门槛", ["threePerson", "minJobAverage"])}
                        {numberField("7人兵种合格门槛", ["sevenPerson", "minJobAverage"])}
                        {numberField("普通兵种质量分界", ["sevenPerson", "normalJobAverage"])}
                        {numberField("高兵种质量分界", ["sevenPerson", "highJobAverage"])}
                      </div>
                      {(["threePerson", "sevenPerson"] as const).map((section) => {
                        const label = section === "threePerson" ? "3人" : "7人"
                        const members = section === "threePerson" ? catalogs.threeMembers : catalogs.members
                        const value = profile[section]
                        return (
                          <Card key={section}>
                            <CardHeader><CardTitle>{label}兵种合格方式</CardTitle></CardHeader>
                            <CardContent className="space-y-4">
                              <Select disabled={readonly} value={value.jobQualificationMode} onValueChange={(next) => setPath([section, "jobQualificationMode"], next)}>
                                <SelectTrigger className="w-52"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="average">按平均分判断</SelectItem>
                                  <SelectItem value="count">按达标人数判断</SelectItem>
                                </SelectContent>
                              </Select>
                              {value.jobQualificationMode === "count" && (
                                <>
                                  <Field label="至少达到门槛人数">
                                    <Input className="w-36" type="number" min="1" max={members.length} disabled={readonly} value={value.minQualifiedCount} onChange={(event) => setPath([section, "minQualifiedCount"], Number(event.target.value))} />
                                  </Field>
                                  <div className="flex flex-wrap gap-3">
                                    {members.map((member: string) => (
                                      <label key={member} className="flex items-center gap-2 text-sm">
                                        <Checkbox
                                          disabled={readonly}
                                          checked={value.qualifiedMembers.includes(member)}
                                          onCheckedChange={(checked) => {
                                            const next = checked
                                              ? [...value.qualifiedMembers, member]
                                              : value.qualifiedMembers.filter((item: string) => item !== member)
                                            setPath([section, "qualifiedMembers"], next)
                                          }}
                                        />
                                        {member}
                                      </label>
                                    ))}
                                  </div>
                                </>
                              )}
                            </CardContent>
                          </Card>
                        )
                      })}
                    </TabsContent>
                    <TabsContent value="job" className="m-0 space-y-5">
                      <h2 className="text-lg font-semibold">兵种评分</h2>
                      <div className="grid grid-cols-3 gap-4">
                        {numberField("兵种基础分权重", ["jobScoring", "baseScoreWeight"])}
                        {numberField("适配加成最低基础分", ["jobScoring", "affinityMinBaseScore"])}
                        {numberField("主要倾向加成比例", ["jobScoring", "primaryBonusRate"])}
                        {numberField("次要倾向加成比例", ["jobScoring", "secondaryBonusRate"])}
                        {numberField("夏侯惇为文官型时扣分", ["jobScoring", "xiahouDunMasterPenalty"])}
                        {numberField("文官型兵种过多扣分权重", ["jobScoring", "extraMasterPenaltyWeight"])}
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        <ToggleRow checked={profile.jobScoring.affinityEnabled} disabled={readonly} label="人物兵种适配加成" onChange={(value) => setPath(["jobScoring", "affinityEnabled"], value)} />
                        <ToggleRow checked={profile.jobScoring.extraMasterPenaltyEnabled} disabled={readonly} label="文官型兵种过多扣分" onChange={(value) => setPath(["jobScoring", "extraMasterPenaltyEnabled"], value)} />
                      </div>
                      <Button variant="outline" onClick={() => setAffinityOpen(true)}>设置人物倾向</Button>
                    </TabsContent>
                    <TabsContent value="job-scores" className="m-0 grid h-full min-h-0 grid-rows-[auto_1fr]">
                      <h2 className="mb-3 text-lg font-semibold">兵种基础分</h2>
                      {scoreRows("job")}
                    </TabsContent>
                    <TabsContent value="skill" className="m-0 space-y-5">
                      <h2 className="text-lg font-semibold">特技评分</h2>
                      <div className="grid grid-cols-3 gap-4">
                        {numberField("优质特技基础分", ["sevenPerson", "ordinarySkillWeight"])}
                        {numberField("强力特技基础分", ["sevenPerson", "strongSkillWeight"])}
                        {numberField("特殊特技基础分", ["sevenPerson", "specialSkillWeight"])}
                        {numberField("普通兵种组合所需特技分", ["sevenPerson", "mediumMinSkillScore"])}
                        {numberField("较低兵种组合所需特技分", ["sevenPerson", "lowMinSkillScore"])}
                      </div>
                      <div className="grid grid-cols-3 gap-3">
                        <ToggleRow checked={profile.sevenPerson.specialSkillAutoPass} disabled={readonly} label="出现特殊特技时直接合格" onChange={(value) => setPath(["sevenPerson", "specialSkillAutoPass"], value)} />
                        <ToggleRow checked={profile.sevenPerson.highJobAutoPass} disabled={readonly} label="达到高兵种质量分界时直接合格" onChange={(value) => setPath(["sevenPerson", "highJobAutoPass"], value)} />
                        <ToggleRow checked={profile.sevenPerson.skillTypeMatchingEnabled} disabled={readonly} label="启用特技类型匹配" onChange={(value) => setPath(["sevenPerson", "skillTypeMatchingEnabled"], value)} />
                      </div>
                    </TabsContent>
                    <TabsContent value="skill-scores" className="m-0 grid h-full min-h-0 grid-rows-[auto_1fr]">
                      <h2 className="mb-3 text-lg font-semibold">特技基础设置</h2>
                      {scoreRows("skill")}
                    </TabsContent>
                    <TabsContent value="job-types" className="m-0">
                      <h2 className="mb-4 text-lg font-semibold">兵种类型</h2>
                      {jobTypeRows()}
                    </TabsContent>
            </div>
          </Tabs>
          <footer className="flex items-center justify-between border-t px-6 py-4">
            <span className="text-xs text-muted-foreground">规则保存后，正在运行的流程仍使用启动时的规则快照。</span>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
              <Button onClick={save} disabled={saving}>{saving ? "正在保存" : "保存规则"}</Button>
            </div>
          </footer>
        </div>
        </div>
      </div>
    )}
    <Dialog open={affinityOpen} onOpenChange={setAffinityOpen}>
      <DialogContent className="w-[min(780px,calc(100vw-40px))]">
        <DialogHeader><DialogTitle>人物倾向设置</DialogTitle></DialogHeader>
        <div className="max-h-[620px] overflow-auto rounded-md border">
          {catalogs.members.map((member: string) => (
            <div key={member} className="grid grid-cols-[140px_1fr_1fr] items-center gap-4 border-b px-4 py-3 last:border-0">
              <strong>{member}</strong>
              <Field label="主要倾向">
                <Select disabled={readonly} value={profile.memberAffinity[member].primaryType} onValueChange={(value) => setPath(["memberAffinity", member, "primaryType"], value)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{catalogs.affinityTypes.map((value: string) => <SelectItem key={value} value={value}>{typeLabels[value]}</SelectItem>)}</SelectContent>
                </Select>
              </Field>
              <Field label="次要倾向">
                <Select disabled={readonly} value={profile.memberAffinity[member].secondaryType} onValueChange={(value) => setPath(["memberAffinity", member, "secondaryType"], value)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{catalogs.affinityTypes.map((value: string) => <SelectItem key={value} value={value}>{typeLabels[value]}</SelectItem>)}</SelectContent>
                </Select>
              </Field>
            </div>
          ))}
        </div>
        <div className="flex justify-end"><Button onClick={() => setAffinityOpen(false)}>完成</Button></div>
      </DialogContent>
    </Dialog>
    </>
  )
}

export function HistoryDialog({
  open,
  onOpenChange,
  notify,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  notify: (message: string) => void
}) {
  const [data, setData] = useState<Json | null>(null)
  const [page, setPage] = useState(1)
  const [round, setRound] = useState<Json | null>(null)
  const [pendingDelete, setPendingDelete] = useState<number | null>(null)

  const load = useCallback(async (nextPage: number) => {
    try {
      const next = await getJson<Json>(`${apiUrl("app/history")}?page=${nextPage}`)
      setData(next)
      setPage(nextPage)
    } catch (reason) {
      notify((reason as Error).message)
    }
  }, [notify])

  useEffect(() => { if (open) load(1) }, [load, open])

  const openRound = async (roundId: number) => {
    try {
      setRound(await getJson<Json>(`${apiUrl("app/history-round")}?id=${roundId}`))
    } catch (reason) {
      notify((reason as Error).message)
    }
  }

  const remove = async (roundId: number) => {
    if (pendingDelete !== roundId) {
      setPendingDelete(roundId)
      return
    }
    try {
      const next = await post<Json>("app/history-manage", { action: "delete-round", roundId })
      setData(next)
      setPendingDelete(null)
      notify("历史轮次已删除")
    } catch (reason) {
      notify((reason as Error).message)
    }
  }

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="h-[min(820px,90vh)] w-[min(1120px,calc(100vw-40px))] max-w-none">
          <DialogHeader>
            <DialogTitle>历史结果</DialogTitle>
          </DialogHeader>
          <div className="h-[calc(100%-54px)] overflow-auto">
            {data?.rows?.length ? (
              <div className="space-y-2">
                {data.rows.map((item: Json) => (
                  <div key={item.id} className="grid grid-cols-[1fr_110px_110px_120px_auto] items-center gap-4 rounded-md border px-4 py-3">
                    <div>
                      <strong className="text-sm">{String(item.started_at || "").replace("T", " ").slice(0, 19)}</strong>
                      <p className="mt-1 text-xs text-muted-foreground">{item.rule_name} · 第 {item.round_number} 轮</p>
                    </div>
                    <span className="text-sm">{item.mode === "three" ? "3人" : "7人"}</span>
                    <span className="text-sm">{item.result_count} 个结果</span>
                    <span className="text-sm">{item.status}</span>
                    <div className="flex justify-end gap-2">
                      <Button size="sm" variant="outline" onClick={() => openRound(item.id)}>查看</Button>
                      <Button size="sm" variant="ghost" className={pendingDelete === item.id ? "text-destructive" : ""} onClick={() => remove(item.id)}>
                        {pendingDelete === item.id ? "确认删除" : <Trash2 />}
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            ) : <div className="grid h-64 place-items-center text-sm text-muted-foreground">没有历史结果</div>}
          </div>
          {data && (
            <div className="flex items-center justify-end gap-3 border-t pt-3 text-xs text-muted-foreground">
              <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => load(page - 1)}>上一页</Button>
              <span>第 {page}/{data.pageCount} 页，共 {data.total} 轮</span>
              <Button size="sm" variant="outline" disabled={page >= data.pageCount} onClick={() => load(page + 1)}>下一页</Button>
            </div>
          )}
        </DialogContent>
      </Dialog>
      <Dialog open={Boolean(round)} onOpenChange={(value) => !value && setRound(null)}>
        <DialogContent className="h-[min(820px,90vh)] w-[min(1180px,calc(100vw-40px))] max-w-none">
          <DialogHeader><DialogTitle>本轮全部结果</DialogTitle></DialogHeader>
          <div className="grid max-h-[700px] grid-cols-2 gap-3 overflow-auto max-[850px]:grid-cols-1">
            {(round?.results || []).map((snapshot: Json, index: number) => (
              <Card key={snapshot.slot || index}>
                <CardHeader>
                  <CardTitle>存档 {snapshot.slot || index + 1}</CardTitle>
                  <CardDescription>第 {snapshot.attempt || snapshot.acceptedAttempt || "-"} 次尝试</CardDescription>
                </CardHeader>
                <CardContent className="space-y-2">
                  {(snapshot.members || []).map((member: Json, memberIndex: number) => (
                    <div key={`${member.name}-${memberIndex}`} className="rounded-md bg-muted px-3 py-2 text-sm">
                      <strong>{member.name || member.memberName} · {member.job || member.jobName}</strong>
                      <p className="mt-1 text-xs text-muted-foreground">个人天赋：{(member.personalSkills || []).map((item: Json) => item.name || item.skillName).join("、") || "无"}</p>
                      <p className="mt-1 text-xs text-muted-foreground">兵种技能：{(member.jobSkills || []).map((item: Json) => item.name || item.skillName).join("、") || "无"}</p>
                    </div>
                  ))}
                </CardContent>
              </Card>
            ))}
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}

function RepairDialog({
  open,
  onOpenChange,
  runAction,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  runAction: (name: string) => void
}) {
  const [selected, setSelected] = useState<string | null>(null)
  const repairs = [
    {
      id: "repair-sishui",
      title: "汜水关卡关",
      description: "用于处理汜水关结束后剧情关卡异常。目前该功能尚未完善。",
    },
    {
      id: "repair-sound",
      title: "游戏没声音",
      description: "恢复旧版本在 Windows 音量合成器中修改的正常游戏声音状态。",
    },
    {
      id: "repair-s00",
      title: "第一关跳过",
      description: "把 RS\\S_00.eex 恢复为工具内置的正常版本。",
    },
  ]
  return (
    <Dialog open={open} onOpenChange={(value) => { onOpenChange(value); if (!value) setSelected(null) }}>
      <DialogContent>
        <DialogHeader><DialogTitle>错误修正</DialogTitle></DialogHeader>
        <p className="text-sm text-muted-foreground">仅在出现对应问题时使用。执行前请先关闭正在进行的随机流程。</p>
        <div className="mt-4 space-y-2">
          {repairs.map((repair) => (
            <button key={repair.id} className={cn("flex w-full items-center gap-4 rounded-md border p-4 text-left hover:bg-muted", selected === repair.id && "border-primary bg-accent")} onClick={() => setSelected(repair.id)}>
              <Wrench className="size-5 text-primary" />
              <span className="flex-1">
                <strong className="block text-sm">{repair.title}</strong>
                <span className="mt-1 block text-xs text-muted-foreground">{repair.description}</span>
              </span>
              <ChevronRight className="size-4 text-muted-foreground" />
            </button>
          ))}
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
          <Button disabled={!selected} onClick={() => { if (selected) runAction(selected) }}>确认执行</Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function DesktopApp() {
  const [bootstrap, setBootstrap] = useState<Bootstrap | null>(null)
  const [state, setState] = useState<AppState | null>(null)
  const [error, setError] = useState("")
  const [toast, setToast] = useState("")
  const [ruleOpen, setRuleOpen] = useState(false)
  const [repairOpen, setRepairOpen] = useState(false)
  const [changelogOpen, setChangelogOpen] = useState(false)
  const [statisticsUrl, setStatisticsUrl] = useState("")
  const [detail, setDetail] = useState<Json | null>(null)
  const stateRef = useRef<AppState | null>(null)
  const lastNotificationRef = useRef(0)

  const notify = useCallback((message: string) => setToast(message), [])
  useEffect(() => {
    if (!toast) return
    const timer = window.setTimeout(() => setToast(""), 4800)
    return () => window.clearTimeout(timer)
  }, [toast])

  useEffect(() => {
    getJson<Bootstrap>(apiUrl("app/bootstrap")).then((data) => {
      setBootstrap(data)
      setState(data.state)
      stateRef.current = data.state
      const notification = data.state.notifications?.at(-1)
      if (notification) {
        lastNotificationRef.current = notification.id
        setToast(notification.message)
      }
      if (data.startupWarning) setToast(data.startupWarning)
    }).catch((reason: Error) => setError(reason.message))
  }, [])

  useEffect(() => {
    const timer = window.setInterval(() => {
      getJson<AppState>(apiUrl("app/state")).then((next) => {
        setState(next)
        stateRef.current = next
        const notification = next.notifications?.at(-1)
        if (notification && notification.id > lastNotificationRef.current) {
          lastNotificationRef.current = notification.id
          setToast(notification.message)
        }
      }).catch(() => undefined)
    }, state?.running ? 350 : 1200)
    return () => window.clearInterval(timer)
  }, [state?.running])

  useEffect(() => {
    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      if (stateRef.current?.running) {
        event.preventDefault()
        event.returnValue = ""
      }
    }
    window.addEventListener("beforeunload", handleBeforeUnload)
    return () => window.removeEventListener("beforeunload", handleBeforeUnload)
  }, [])

  useEffect(() => {
    const handlePageHide = () => {
      const body = new Blob(
        [JSON.stringify({ name: "page-hidden" })],
        { type: "application/json" },
      )
      navigator.sendBeacon(apiUrl("app/action"), body)
    }
    window.addEventListener("pagehide", handlePageHide)
    return () => window.removeEventListener("pagehide", handlePageHide)
  }, [])

  useEffect(() => {
    if (!statisticsUrl) return
    const previousOverflow = document.body.style.overflow
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setStatisticsUrl("")
    }
    document.body.style.overflow = "hidden"
    window.addEventListener("keydown", closeOnEscape)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener("keydown", closeOnEscape)
    }
  }, [statisticsUrl])

  const action = async (name: string, payload: Json = {}) => {
    try {
      const result = await post<Json>("app/action", { name, ...payload })
      if (result.state) {
        setState(result.state)
        stateRef.current = result.state
      }
      if (result.toast) notify(result.toast)
      if (result.message) notify(result.message)
      return result
    } catch (reason) {
      notify((reason as Error).message)
      return null
    }
  }

  const updateSettings = (patch: Partial<AppState["settings"]>) => {
    if (!state || state.running) return
    const next = { ...state.settings, ...patch }
    setState({ ...state, settings: next })
    action("settings", next)
  }

  const openFile = (path: string) => action("open-file", { path })

  if (error) return <main className="mx-auto max-w-4xl p-8"><div className="rounded-md border border-destructive/30 bg-rose-50 p-4 text-rose-800">{error}</div></main>
  if (!bootstrap || !state) return <div className="grid min-h-screen place-items-center text-sm text-muted-foreground">正在启动随机工具</div>

  const version = String(bootstrap.build.version || "")

  return (
    <div className="mx-auto flex min-h-screen w-[min(980px,calc(100%-28px))] flex-col py-4">
      <header className="flex items-center justify-between">
        <h1 className="text-[22px] font-bold">2.10 随机工具</h1>
        <button className="text-sm text-muted-foreground hover:text-primary" onDoubleClick={() => setChangelogOpen(true)}>V{version}</button>
      </header>

      <section className="mt-3 space-y-1 text-[13px] leading-5 text-[#444]">
        <p>请将本工具放置到游戏目录下，双击运行。</p>
        <p>
          开始前请确认：已在许子将处完成配置，并将配置后的存档保存到
          <span className="group relative ml-1 inline-block">
            <button className="text-primary hover:underline">第20栏</button>
            <span className="pointer-events-none invisible absolute left-0 top-full z-50 mt-1 border bg-white p-1 opacity-0 shadow-xl transition group-hover:visible group-hover:opacity-100">
              <img className="max-w-[520px]" src="source_slot_20_help.png" alt="第20栏位置示意" />
            </span>
          </span>
          。
        </p>
        <p>运行前会自动校验并保护 S_00.eex，停止后恢复原文件。合格结果会生成结果图并保存在 randResult 目录。</p>
      </section>

      <section className="mt-3 space-y-2">
        <div className="flex min-h-9 flex-wrap items-center gap-x-4 gap-y-2">
          <span className="text-sm">运行模式</span>
          <div className="flex items-center gap-3">
            {(["seven", "three"] as const).map((mode) => (
              <label key={mode} className="flex cursor-pointer items-center gap-1.5 text-sm">
                <input
                  type="radio"
                  name="random-mode"
                  disabled={state.running}
                  checked={state.settings.mode === mode}
                  onChange={() => updateSettings({ mode })}
                />
                {mode === "three" ? "3人" : "7人"}
              </label>
            ))}
          </div>
          <label className="flex items-center gap-1.5 text-sm">
            <Checkbox disabled={state.running} checked={state.settings.loopRandom} onCheckedChange={(value) => updateSettings({ loopRandom: value === true })} />
            循环随机（每轮15个）
          </label>
          <label className="flex items-center gap-2 text-sm">
            同时运行数量
            <Input className="h-8 w-20 text-center" type="number" min="1" max={state.settings.loopRandom ? undefined : 15} disabled={state.running} value={state.settings.concurrency} onChange={(event) => updateSettings({ concurrency: Math.max(1, Number(event.target.value)) })} />
          </label>
          <label className="flex items-center gap-1.5 text-sm">
            <Checkbox disabled={state.running} checked={state.settings.compatibilityMode} onCheckedChange={(value) => updateSettings({ compatibilityMode: value === true })} />
            兼容模式
          </label>
        </div>

        <div className="flex min-h-9 items-center gap-2">
          <span className="mr-1 text-sm">规则</span>
          <div className="w-52">
            <Select disabled={state.running} value={state.settings.activeProfile} onValueChange={(profile) => action("profile", { profile })}>
              <SelectTrigger className="h-8"><SelectValue /></SelectTrigger>
              <SelectContent>{state.profiles.map((name) => <SelectItem key={name} value={name}>{name}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <Button size="sm" variant="outline" onClick={() => setRuleOpen(true)}><Settings2 />规则设置</Button>
          <Button size="sm" variant="outline" disabled={state.running} onClick={() => setRepairOpen(true)}><Wrench />错误修正</Button>
          <Button
            size="sm"
            variant="outline"
            onClick={async () => {
              const result = await action("statistics")
              if (result?.url) setStatisticsUrl(String(result.url))
            }}
          >
            <BarChart3 />统计
          </Button>
          <Button
            className={cn("ml-auto min-w-28", state.running && "bg-destructive hover:bg-destructive/90")}
            size="sm"
            disabled={state.stopping}
            onClick={() => action(state.running ? "stop" : "start")}
          >
            {state.running ? <Square /> : <Play />}
            {state.stopping ? "正在停止" : state.running ? "停止随机" : "开始随机"}
          </Button>
        </div>
      </section>

      <main className="mt-2 min-h-0 flex-1">
        <ConsoleView state={state} openDetail={setDetail} openFile={openFile} />
      </main>

      {state.resultImage && (
        <button className="mt-2 self-start text-sm text-primary hover:underline" onClick={() => openFile(state.resultImage)}>
          <FileImage className="mr-1 inline size-4" />点击查看结果图
        </button>
      )}

      <RuleEditor
        open={ruleOpen}
        bootstrap={bootstrap}
        onOpenChange={setRuleOpen}
        notify={notify}
        onSaved={(rules) => {
          setBootstrap({ ...bootstrap, rules })
          setState((current) => current ? ({ ...current, profiles: Object.keys(rules.profiles), settings: { ...current.settings, activeProfile: rules.activeProfile } }) : current)
        }}
      />
      <RepairDialog open={repairOpen} onOpenChange={setRepairOpen} runAction={async (name) => {
        await action(name)
        setRepairOpen(false)
      }} />
      <ScoreDetailDialog detail={detail} onOpenChange={(open) => !open && setDetail(null)} />
      {statisticsUrl && (
        <div className="fixed inset-0 z-[100] grid grid-rows-[44px_1fr] bg-background">
          <div className="flex items-center justify-end border-b bg-background px-3">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              title="关闭统计"
              aria-label="关闭统计"
              onClick={() => setStatisticsUrl("")}
            >
              <X />
            </Button>
          </div>
          <iframe
            title="结果统计"
            src={statisticsUrl}
            className="h-full min-h-0 w-full border-0 bg-background"
          />
        </div>
      )}
      <Dialog open={changelogOpen} onOpenChange={setChangelogOpen}>
        <DialogContent className="w-[min(760px,calc(100vw-40px))]">
          <DialogHeader><DialogTitle>版本更新记录</DialogTitle></DialogHeader>
          <div className="max-h-[620px] space-y-4 overflow-auto">
            {bootstrap.changelog.map((entry, index) => (
              <section key={`${entry.version}-${index}`} className="rounded-md border p-4">
                <div className="flex items-center justify-between">
                  <strong>V{entry.version}</strong>
                  <span className="text-xs text-muted-foreground">{entry.date || ""}</span>
                </div>
                <ul className="mt-3 space-y-1 text-sm text-muted-foreground">
                  {(entry.items || entry.changes || []).map((item: string, itemIndex: number) => <li key={itemIndex}>· {item}</li>)}
                </ul>
              </section>
            ))}
          </div>
        </DialogContent>
      </Dialog>
      {toast && <div className="fixed bottom-6 right-6 z-[120] max-w-md rounded-md bg-slate-900 px-4 py-3 text-sm text-white shadow-2xl">{toast}</div>}
    </div>
  )
}

export default DesktopApp
