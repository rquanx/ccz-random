import * as React from "react"
import { ChevronLeft, ChevronRight } from "lucide-react"
import { DayPicker } from "react-day-picker"

import { cn } from "@/lib/utils"
import { buttonVariants } from "@/components/ui/button"

export type CalendarProps = React.ComponentProps<typeof DayPicker>

function Calendar({ className, classNames, showOutsideDays = true, ...props }: CalendarProps) {
  return (
    <DayPicker
      showOutsideDays={showOutsideDays}
      className={cn("p-2", className)}
      classNames={{
        months: "flex flex-col gap-4 sm:flex-row",
        month: "space-y-3",
        month_caption: "relative flex h-8 items-center justify-center",
        caption_label: "text-sm font-medium",
        nav: "absolute inset-x-0 top-0 flex justify-between",
        button_previous: cn(buttonVariants({ variant: "outline", size: "icon" }), "size-8 bg-transparent p-0"),
        button_next: cn(buttonVariants({ variant: "outline", size: "icon" }), "size-8 bg-transparent p-0"),
        month_grid: "w-full border-collapse space-y-1",
        weekdays: "flex",
        weekday: "w-9 text-center text-xs font-normal text-muted-foreground",
        week: "mt-1 flex w-full",
        day: "relative size-9 p-0 text-center text-sm",
        day_button: cn(buttonVariants({ variant: "ghost", size: "icon" }), "size-9 p-0 font-normal aria-selected:opacity-100"),
        selected: "rounded-md bg-primary text-primary-foreground hover:bg-primary hover:text-primary-foreground",
        range_start: "rounded-l-md bg-primary text-primary-foreground",
        range_end: "rounded-r-md bg-primary text-primary-foreground",
        range_middle: "rounded-none bg-accent text-accent-foreground",
        today: "rounded-md bg-muted font-semibold",
        outside: "text-muted-foreground opacity-45",
        disabled: "text-muted-foreground opacity-40",
        hidden: "invisible",
        ...classNames,
      }}
      components={{
        Chevron: ({ orientation }) => orientation === "left"
          ? <ChevronLeft className="size-4" />
          : <ChevronRight className="size-4" />,
      }}
      {...props}
    />
  )
}

export { Calendar }
