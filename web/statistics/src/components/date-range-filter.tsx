import { useMemo, useState } from "react"
import { addDays, endOfDay, format, startOfMonth, startOfToday, subDays } from "date-fns"
import { zhCN } from "date-fns/locale"
import { CalendarDays, ChevronDown } from "lucide-react"
import type { DateRange } from "react-day-picker"

import { Button } from "@/components/ui/button"
import { Calendar } from "@/components/ui/calendar"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { cn } from "@/lib/utils"

export type DateSelection = {
  after: string
  before: string
}

type Preset = {
  id: string
  label: string
  range: () => DateRange | undefined
}

const presets: Preset[] = [
  { id: "all", label: "全部时间", range: () => undefined },
  { id: "today", label: "今天", range: () => ({ from: startOfToday(), to: startOfToday() }) },
  { id: "last7", label: "近 7 天", range: () => ({ from: subDays(startOfToday(), 6), to: startOfToday() }) },
  { id: "last30", label: "近 30 天", range: () => ({ from: subDays(startOfToday(), 29), to: startOfToday() }) },
  { id: "month", label: "本月", range: () => ({ from: startOfMonth(startOfToday()), to: startOfToday() }) },
]

function toSelection(range?: DateRange): DateSelection {
  if (!range?.from || !range.to) return { after: "", before: "" }
  return {
    after: format(range.from, "yyyy-MM-dd"),
    before: format(addDays(endOfDay(range.to), 1), "yyyy-MM-dd"),
  }
}

export function DateRangeFilter({
  onChange,
}: {
  onChange: (selection: DateSelection) => void
}) {
  const [open, setOpen] = useState(false)
  const [activePreset, setActivePreset] = useState("all")
  const [range, setRange] = useState<DateRange | undefined>()
  const label = useMemo(() => {
    const preset = presets.find((item) => item.id === activePreset)
    if (activePreset !== "custom") return preset?.label || "全部时间"
    if (!range?.from || !range.to) return "自定义周期"
    return `${format(range.from, "MM-dd")} 至 ${format(range.to, "MM-dd")}`
  }, [activePreset, range])

  const selectPreset = (preset: Preset) => {
    const next = preset.range()
    setActivePreset(preset.id)
    setRange(next)
    onChange(toSelection(next))
    setOpen(false)
  }

  const applyCustom = () => {
    if (!range?.from || !range.to) return
    setActivePreset("custom")
    onChange(toSelection(range))
    setOpen(false)
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" className="h-9 w-full justify-between px-3 font-normal">
          <span className="flex min-w-0 items-center gap-2">
            <CalendarDays className="size-4 shrink-0 text-muted-foreground" />
            <span className="truncate">{label}</span>
          </span>
          <ChevronDown className="size-4 shrink-0 text-muted-foreground" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="flex w-auto gap-3 p-3">
        <div className="flex w-28 shrink-0 flex-col gap-1 border-r pr-3">
          {presets.map((preset) => (
            <Button
              key={preset.id}
              variant="ghost"
              size="sm"
              className={cn("justify-start", activePreset === preset.id && "bg-accent text-primary")}
              onClick={() => selectPreset(preset)}
            >
              {preset.label}
            </Button>
          ))}
          <div className="my-1 h-px bg-border" />
          <span className="px-3 py-1 text-xs text-muted-foreground">自定义周期</span>
        </div>
        <div>
          <Calendar
            mode="range"
            defaultMonth={range?.from}
            selected={range}
            onSelect={(next, selectedDay) => {
              if (activePreset !== "custom") {
                setActivePreset("custom")
                setRange({ from: selectedDay, to: undefined })
                return
              }
              setRange(next)
            }}
            numberOfMonths={2}
            locale={zhCN}
          />
          <div className="flex justify-end gap-2 border-t pt-3">
            <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>取消</Button>
            <Button size="sm" disabled={!range?.from || !range.to} onClick={applyCustom}>应用</Button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  )
}
