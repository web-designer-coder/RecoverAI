import * as DialogPrimitive from "@radix-ui/react-dialog"
import { useState, useRef, useEffect, useCallback, Fragment } from "react"
import { useNavigate } from "@tanstack/react-router"
import { Search, X, ArrowUpDown } from "lucide-react"
import { cn } from "@/lib/utils"
import { toast } from "sonner"

// Define the command structure
type CommandItem = {
  id: string
  name: string
  description?: string
  action: (navigate: ReturnType<typeof useNavigate>) => void
  section?: string
  keywords?: string[]
}

// Define the sections and commands
const sections: { id: string; title: string; commands: Omit<CommandItem, "section">[] }[] = [
  {
    id: "navigation",
    title: "Navigation",
    commands: [
      {
        id: "dashboard",
        name: "Dashboard",
        description: "Overview of recovery performance",
        keywords: ["home", "overview", "kpi", "metrics"],
        action: (nav) => nav({ to: "/app/dashboard" }),
      },
      {
        id: "recovery-queue",
        name: "Recovery Queue",
        description: "View and manage recoveries in progress",
        keywords: ["payments", "failed", "retry", "queue"],
        action: (nav) => nav({ to: "/app/recovery" }),
      },
      {
        id: "analytics",
        name: "Analytics",
        description: "Deep dive into recovery metrics",
        keywords: ["charts", "reports", "data", "insights"],
        action: (nav) => nav({ to: "/app/analytics" }),
      },
      {
        id: "simulator",
        name: "Simulator",
        description: "Run recovery simulations",
        keywords: ["test", "simulate", "what-if", "model"],
        action: (nav) => nav({ to: "/app/simulator" }),
      },
      {
        id: "audit",
        name: "Audit Trail",
        description: "Immutable log of AI decisions and actions",
        keywords: ["log", "history", "decisions", "activity"],
        action: (nav) => nav({ to: "/app/audit" }),
      },
      {
        id: "policies",
        name: "Policies",
        description: "Configure recovery policies and rules",
        keywords: ["rules", "config", "settings", "automation"],
        action: (nav) => nav({ to: "/app/policies" }),
      },
      {
        id: "settings",
        name: "Settings",
        description: "Manage account, integrations, and preferences",
        keywords: ["account", "razorpay", "webhook", "profile"],
        action: (nav) => nav({ to: "/app/settings" }),
      },
    ],
  },
  {
    id: "actions",
    title: "Actions",
    commands: [
      {
        id: "run-simulation",
        name: "Run Simulation",
        description: "Start a new recovery simulation",
        keywords: ["run", "simulate", "test"],
        action: (nav) => {
          nav({ to: "/app/simulator" })
          toast.info("Go to Simulator to run a simulation", {
            description: "Set your parameters and click Run Simulation",
          })
        },
      },
      {
        id: "refresh-recoveries",
        name: "Refresh Recoveries",
        description: "Reload the latest recovery data",
        keywords: ["reload", "update", "fetch"],
        action: (nav) => {
          nav({ to: "/app/recovery" })
          toast.info("Navigated to Recovery Queue", {
            description: "Click the refresh button to reload data",
          })
        },
      },
      {
        id: "view-at-risk",
        name: "View At-Risk Payments",
        description: "Go to the recovery queue to see payments at risk",
        keywords: ["at-risk", "urgent", "high-priority"],
        action: (nav) => {
          nav({ to: "/app/recovery" })
          toast.info("Navigated to Recovery Queue", {
            description: "At-risk payments are highlighted in the queue",
          })
        },
      },
    ],
  },
  {
    id: "system",
    title: "System",
    commands: [
      {
        id: "shortcut-help",
        name: "Keyboard Shortcuts",
        description: "View all available keyboard shortcuts",
        keywords: ["help", "shortcuts", "keys", "hotkeys"],
        action: () => {
          // Delay so the command palette closes first (Radix dialog overlay check)
          setTimeout(() => {
            document.dispatchEvent(new CustomEvent("open-shortcuts"))
          }, 100)
        },
      },
    ],
  },
]

// Flatten all commands with section info
const allCommands: CommandItem[] = sections.flatMap((section) =>
  section.commands.map((cmd) => ({ ...cmd, section: section.title }))
)

export function CommandPalette() {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [searchTerm, setSearchTerm] = useState("")
  const [selectedIndex, setSelectedIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  // Open the command palette
  const openPalette = useCallback(() => {
    setOpen(true)
    setSearchTerm("")
    setSelectedIndex(0)
  }, [])

  // Close the command palette
  const closePalette = useCallback(() => {
    setOpen(false)
  }, [])

  // Filter commands based on search term (includes keywords)
  const filteredCommands = allCommands.filter((cmd) => {
    if (!searchTerm) return true
    const term = searchTerm.toLowerCase()
    const searchable = [
      cmd.name,
      cmd.description ?? "",
      cmd.section ?? "",
      ...(cmd.keywords ?? []),
    ]
      .join(" ")
      .toLowerCase()
    return searchable.includes(term)
  })

  // Group filtered commands by section for display
  const groupedCommands = sections
    .map((section) => ({
      ...section,
      commands: filteredCommands.filter((cmd) => cmd.section === section.title),
    }))
    .filter((group) => group.commands.length > 0)

  // Scroll selected item into view
  useEffect(() => {
    if (!open) return
    const selectedEl = listRef.current?.querySelector(`[data-command-index="${selectedIndex}"]`)
    if (selectedEl) {
      selectedEl.scrollIntoView({ block: "nearest" })
    }
  }, [selectedIndex, open])

  // Handle keyboard shortcut globally
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      // Check for Cmd/Ctrl + K
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k" && !event.shiftKey) {
        event.preventDefault()
        const activeElement = document.activeElement as HTMLElement
        if (
          activeElement.tagName !== "INPUT" &&
          activeElement.tagName !== "TEXTAREA" &&
          !activeElement.isContentEditable
        ) {
          openPalette()
        }
      }
    }

    document.addEventListener("keydown", handleKeyDown)
    return () => {
      document.removeEventListener("keydown", handleKeyDown)
    }
  }, [openPalette])

  // Listen for custom event from global / shortcut
  useEffect(() => {
    const handler = () => openPalette()
    document.addEventListener("open-command-palette", handler)
    return () => document.removeEventListener("open-command-palette", handler)
  }, [openPalette])

  // Reset selected index when search changes
  useEffect(() => {
    setSelectedIndex(0)
  }, [searchTerm])

  // Handle keyboard navigation within the palette
  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      switch (event.key) {
        case "ArrowDown":
          event.preventDefault()
          setSelectedIndex((prev) =>
            prev < filteredCommands.length - 1 ? prev + 1 : 0
          )
          break
        case "ArrowUp":
          event.preventDefault()
          setSelectedIndex((prev) =>
            prev > 0 ? prev - 1 : filteredCommands.length - 1
          )
          break
        case "Enter": {
          event.preventDefault()
          const cmd = filteredCommands[selectedIndex]
          if (cmd) {
            cmd.action(navigate)
            closePalette()
          }
          break
        }
        case "Escape":
          event.preventDefault()
          closePalette()
          break
      }
    },
    [filteredCommands, selectedIndex, navigate, closePalette]
  )

  // Handle search input change
  const handleSearchChange = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      setSearchTerm(event.target.value)
    },
    []
  )

  // When open, focus the input
  useEffect(() => {
    if (open) {
      // Small delay to ensure portal is mounted
      requestAnimationFrame(() => {
        inputRef.current?.focus()
      })
    }
  }, [open])

  // Build a flat index map: for each section's commands, track their global index
  let globalIndex = -1

  return (
    <DialogPrimitive.Root open={open} onOpenChange={setOpen}>
      <DialogPrimitive.Trigger asChild>
        <button
          type="button"
          className={cn(
            "flex items-center gap-2 rounded-lg border border-border/60 bg-surface-low px-3 py-1.5",
            "text-[0.75rem] text-muted-foreground transition-all duration-200",
            "hover:border-border hover:text-foreground hover:bg-surface-high/40",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ai-vivid focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          )}
          aria-label="Open command palette"
        >
          <Search className="h-3.5 w-3.5" aria-hidden="true" />
          <span className="hidden sm:inline">Search…</span>
          <kbd className="ml-2 hidden rounded border border-border/60 bg-surface-low px-1.5 py-0.5 font-mono text-[0.625rem] text-faint sm:inline">
            ⌘K
          </kbd>
        </button>
      </DialogPrimitive.Trigger>

      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />

        <DialogPrimitive.Content
          className={cn(
            "fixed left-[50%] top-[20%] z-50 w-full max-w-lg translate-x-[-50%]",
            "rounded-xl border border-border bg-graphite-deep shadow-[0_25px_50px_-12px_rgba(0,0,0,0.5)]",
            "data-[state=open]:animate-in data-[state=closed]:animate-out",
            "data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
            "data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95",
            "data-[state=closed]:slide-out-to-top-2 data-[state=open]:slide-in-from-top-2",
            "duration-200"
          )}
          onKeyDown={handleKeyDown}
          onOpenAutoFocus={(e) => e.preventDefault()}
        >
          {/* Accessible labels */}
          <DialogPrimitive.Title className="sr-only">
            Command Palette
          </DialogPrimitive.Title>
          <DialogPrimitive.Description className="sr-only">
            Search and navigate to any page or action in RecoverAI
          </DialogPrimitive.Description>

          {/* Search input */}
          <div className="flex items-center border-b border-border px-4">
            <Search className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
            <input
              ref={inputRef}
              type="text"
              placeholder="Type a command or search…"
              className="flex-1 bg-transparent px-3 py-3.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
              value={searchTerm}
              onChange={handleSearchChange}
              aria-label="Search commands"
              aria-controls="command-palette-list"
              aria-activedescendant={
                selectedIndex >= 0 ? `command-${selectedIndex}` : undefined
              }
              role="combobox"
              aria-expanded={open}
              aria-autocomplete="list"
            />
            <DialogPrimitive.Close asChild>
              <button
                type="button"
                className={cn(
                  "ml-2 rounded p-1 text-muted-foreground transition-colors",
                  "hover:text-foreground hover:bg-white/[0.05]",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ai-vivid"
                )}
                aria-label="Close command palette"
              >
                <X className="h-4 w-4" />
              </button>
            </DialogPrimitive.Close>
          </div>

          {/* Command list */}
          <div
            ref={listRef}
            id="command-palette-list"
            role="listbox"
            aria-label="Commands"
            className="max-h-[300px] overflow-y-auto p-2"
          >
            {filteredCommands.length === 0 ? (
              <div className="py-8 text-center">
                <p className="text-sm text-muted-foreground">No commands found</p>
                <p className="mt-1 text-xs text-faint">Try a different search term</p>
              </div>
            ) : (
              groupedCommands.map((group) => (
                <Fragment key={group.id}>
                  <p className="px-2 pt-3 pb-1.5 text-[0.6875rem] font-medium uppercase tracking-wider text-faint">
                    {group.title}
                  </p>
                  {group.commands.map((cmd) => {
                    globalIndex++
                    const idx = globalIndex
                    const isSelected = selectedIndex === idx
                    return (
                      <div
                        key={cmd.id}
                        id={`command-${idx}`}
                        data-command-index={idx}
                        role="option"
                        aria-selected={isSelected}
                        className={cn(
                          "flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors duration-100",
                          isSelected
                            ? "bg-ai/10 text-foreground"
                            : "text-muted-foreground hover:bg-white/[0.04] hover:text-foreground"
                        )}
                        onMouseEnter={() => setSelectedIndex(idx)}
                        onClick={() => {
                          cmd.action(navigate)
                          closePalette()
                        }}
                      >
                        <div className="flex-1 min-w-0">
                          <p className="truncate font-medium">{cmd.name}</p>
                          {cmd.description && (
                            <p className="mt-0.5 truncate text-xs text-faint">
                              {cmd.description}
                            </p>
                          )}
                        </div>
                        <ArrowUpDown
                          className={cn(
                            "h-3.5 w-3.5 shrink-0 transition-opacity",
                            isSelected ? "opacity-60" : "opacity-0"
                          )}
                          aria-hidden="true"
                        />
                      </div>
                    )
                  })}
                </Fragment>
              ))
            )}
          </div>

          {/* Footer with keyboard hints */}
          <div className="flex items-center gap-4 border-t border-border px-4 py-2.5 text-[0.6875rem] text-faint">
            <span className="flex items-center gap-1">
              <kbd className="rounded border border-border/60 bg-surface-low px-1 py-0.5 font-mono text-[0.625rem]">↑↓</kbd>
              navigate
            </span>
            <span className="flex items-center gap-1">
              <kbd className="rounded border border-border/60 bg-surface-low px-1 py-0.5 font-mono text-[0.625rem]">↵</kbd>
              select
            </span>
            <span className="flex items-center gap-1">
              <kbd className="rounded border border-border/60 bg-surface-low px-1 py-0.5 font-mono text-[0.625rem]">esc</kbd>
              close
            </span>
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}