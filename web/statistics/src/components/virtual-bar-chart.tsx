import { useMemo, useRef, useState } from "react"
import { useVirtualizer } from "@tanstack/react-virtual"
import { Search } from "lucide-react"

import { Input } from "@/components/ui/input"
import type { DistributionRow } from "@/types"

export function VirtualBarChart({
  rows,
  searchable = false,
  height = 500,
}: {
  rows: DistributionRow[]
  searchable?: boolean
  height?: number
}) {
  const [query, setQuery] = useState("")
  const scrollRef = useRef<HTMLDivElement>(null)
  const filtered = useMemo(() => {
    const term = query.trim().toLocaleLowerCase()
    return term
      ? rows.filter((row) => row.label.toLocaleLowerCase().includes(term))
      : rows
  }, [query, rows])
  const max = Math.max(1, ...filtered.map((row) => Number(row.count || 0)))
  const virtualizer = useVirtualizer({
    count: filtered.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 44,
    overscan: 8,
  })

  if (!rows.length) {
    return <div className="grid h-56 place-items-center text-sm text-muted-foreground">当前筛选条件下没有数据</div>
  }

  return (
    <div className="space-y-3">
      {searchable && (
        <div className="relative ml-auto w-56">
          <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索名称"
            className="pl-9"
          />
        </div>
      )}
      <div ref={scrollRef} className="hide-scrollbar overflow-auto border-t" style={{ height }}>
        <div className="relative w-full" style={{ height: virtualizer.getTotalSize() }}>
          {virtualizer.getVirtualItems().map((item) => {
            const row = filtered[item.index]
            const percentage = Number(row.ratio || 0) * 100
            return (
              <div
                key={`${row.value}-${item.index}`}
                className="absolute left-0 top-0 grid w-full grid-cols-[minmax(130px,210px)_minmax(160px,1fr)_96px] items-center gap-3 border-b px-1 text-sm"
                style={{ height: item.size, transform: `translateY(${item.start}px)` }}
              >
                <span className="truncate" title={row.label}>{row.label || "未知"}</span>
                <span className="h-2 overflow-hidden rounded-full bg-muted">
                  <span
                    className="block h-full rounded-full bg-primary"
                    style={{ width: row.count ? `${Math.max(1.5, row.count / max * 100)}%` : 0 }}
                  />
                </span>
                <span className="text-right text-xs text-muted-foreground">
                  {row.count} · {percentage.toFixed(1)}%
                </span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
