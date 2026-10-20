import { useState, type KeyboardEvent } from "react"
import { X } from "lucide-react"

import { cn } from "@/lib/utils"

interface TagInputProps {
  id?: string
  value: string[]
  onChange: (next: string[]) => void
  placeholder?: string
  className?: string
}

/** Comma/Enter-separated list editor. Backspace on an empty input removes the last tag. */
export function TagInput({ id, value, onChange, placeholder, className }: TagInputProps) {
  const [text, setText] = useState("")

  const add = (raw: string) => {
    const items = raw
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean)
      .filter((s) => !value.some((v) => v.toLowerCase() === s.toLowerCase()))
    if (items.length) onChange([...value, ...items])
    setText("")
  }

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault()
      add(text)
    } else if (e.key === "Backspace" && !text && value.length) {
      onChange(value.slice(0, -1))
    }
  }

  return (
    <div
      className={cn(
        "flex min-h-9 flex-wrap items-center gap-1.5 rounded-md border border-input bg-card px-2 py-1.5 focus-within:ring-1 focus-within:ring-ring",
        className
      )}
    >
      {value.map((tag) => (
        <span key={tag} className="inline-flex items-center gap-1 rounded-md bg-secondary px-2 py-0.5 text-xs">
          {tag}
          <button
            type="button"
            onClick={() => onChange(value.filter((v) => v !== tag))}
            className="text-muted-foreground hover:text-foreground"
            aria-label={`Remove ${tag}`}
          >
            <X size={12} />
          </button>
        </span>
      ))}
      <input
        id={id}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKeyDown}
        onBlur={() => text.trim() && add(text)}
        placeholder={value.length ? "" : placeholder}
        className="min-w-[120px] flex-1 bg-transparent px-1 text-sm placeholder:text-muted-foreground focus:outline-none"
      />
    </div>
  )
}
